"""Headless controller behavior: real callbacks, isolated files and loopback IO."""
from __future__ import annotations

import os
from pathlib import Path
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from provider_test_support import OwnedProcess, loopback_server, write_json_response
from infini_local.desktop import settings_env, settings_schema
from infini_local.desktop import studio_operations as controls
from infini_local.desktop.settings_controller import SettingsController


class _GuiWorkflowHarness(SettingsController):
    def drain_until(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.pump()
            time.sleep(0.005)
        assert predicate(), 'worker result did not reach control loop within test deadline'


@pytest.fixture
def gui_workflow(tmp_path, monkeypatch):
    root = tmp_path / 'LocalGenerator'
    root.mkdir()
    config = root / 'config.env'
    monkeypatch.setattr(controls, 'ROOT', root)
    monkeypatch.delenv('INFINI_CACHE_DIR', raising=False)
    monkeypatch.setenv('NO_PROXY', '127.0.0.1,localhost')
    monkeypatch.setenv('no_proxy', '127.0.0.1,localhost')
    app = _GuiWorkflowHarness(config)
    yield app, root, config
    app.on_close()


@pytest.fixture
def held_gui_call(monkeypatch):
    """Hold IO until the test releases it; verify callbacks return with IO pending."""
    holds = []
    workers = []

    def install(target, method, response, *, first_only=False):
        entered, release, finished = (threading.Event() for _ in range(3))
        calls = []
        call_threads = []
        holds.append(release)

        def fetch(*args, **kwargs):
            worker = threading.current_thread()
            workers.append(worker)
            call_threads.append(worker)
            calls.append(kwargs.get("base_url"))
            try:
                if not first_only or len(calls) == 1:
                    entered.set()
                    assert release.wait(5), "test worker hold expired"
                if isinstance(response, Exception):
                    raise response
                return response(**kwargs) if callable(response) else response
            finally:
                finished.set()

        def assert_pending():
            # This is a deadlock watchdog, not a performance budget. A callback
            # may be descheduled on CI; it must still return before IO completes.
            assert entered.wait(3), "callback did not start the IO worker"
            assert call_threads[0] is not threading.current_thread(), "IO ran on the controller thread"
            assert not release.is_set(), "test released IO before checking responsiveness"
            assert not finished.is_set(), "callback waited for held IO instead of returning"

        monkeypatch.setattr(target, method, fetch)
        return SimpleNamespace(entered=entered, release=release, finished=finished,
                               calls=calls, assert_pending=assert_pending)

    yield install
    for release in holds:
        release.set()
    for worker in workers:
        if worker is threading.current_thread():
            continue  # A synchronous-IO regression is reported by assert_pending.
        worker.join(timeout=3)
        assert not worker.is_alive(), "held worker did not finish"


@contextmanager
def _gui_loopback_http(responses):
    """Synthetic diagnostic HTTP only, not the application's real server."""
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert urlsplit(self.path).path not in {"/shutdown", "/trace_clear"}
            self.reply()

        def reply(self):
            requests.append(self.path)
            response = responses.get(urlsplit(self.path).path, (404, {"ok": False}))
            if callable(response):
                response = response(self.path)
            code, value = response
            write_json_response(self, value, status=code)

        def do_POST(self):
            assert urlsplit(self.path).path in {"/shutdown", "/trace_clear"}
            assert self.headers["Content-Type"] == "application/json"
            assert self.rfile.read(int(self.headers.get("Content-Length", "0"))) == b"{}"
            self.reply()

        def log_message(self, *_args):
            pass

    with loopback_server(Handler) as server:
        yield f"http://127.0.0.1:{server.server_port}", requests


def test_gui_save_reload_preserves_choices_and_unknown_settings(gui_workflow):
    gui, _root, config = gui_workflow
    settings_env.write_env(config, {
        "INFINI_PROMPT_STYLE": "Default", "INFINI_IMAGE_BACKEND": "sdcpp",
        "INFINI_MANUAL_KEY": "retained",
    })
    gui.values["INFINI_PROMPT_STYLE"] = "Terraria Like"
    gui.save()
    reloaded = settings_env.parse_env(config)
    assert reloaded["INFINI_PROMPT_STYLE"] == "Terraria Like"
    assert reloaded["INFINI_IMAGE_BACKEND"] == "sdcpp"
    assert reloaded["INFINI_MANUAL_KEY"] == "retained"
    gui.update_values({"INFINI_PROMPT_STYLE": "Default"})
    gui.save()
    assert settings_env.parse_env(config)["INFINI_MANUAL_KEY"] == "retained"


def test_gui_saves_named_profile_separately_and_restores_exact_settings(gui_workflow, monkeypatch):
    from infini_local.desktop.settings_env import load_user_presets
    gui, _root, config = gui_workflow
    config.write_text("INFINI_MANUAL_KNOB=disk\n", encoding="utf-8")
    before = config.read_bytes()
    gui.values["INFINI_MANUAL_KNOB"] = "keep"
    gui.values["INFINI_PROMPT_STYLE"] = "Terraria Like"
    gui.values["INFINI_CODEX_IMAGE_QUALITY"] = "high"
    gui.values["INFINI_LLM_REASONING_MAX_TOKENS"] = "7500"
    gui.values["INFINI_OPENROUTER_API_KEY"] = "test-only-credential"
    gui.preset = "Custom"
    gui.user_presets = {}
    gui._refresh_visibility = lambda: None
    gui._capture_profile_baseline()
    gui.user_presets = settings_env.save_user_preset(config.with_name("gui_user_presets.json"), "Мой GPU", gui._current_profile_settings())
    gui.preset = settings_env.USER_PRESET_PREFIX + "Мой GPU"
    gui._capture_profile_baseline()
    path = config.with_name("gui_user_presets.json")
    profiles = load_user_presets(path)
    assert gui.preset == "Мой: Мой GPU"
    assert profiles["Мой GPU"]["INFINI_PROMPT_STYLE"] == "Terraria Like"
    assert profiles["Мой GPU"]["INFINI_LLM_REASONING_MAX_TOKENS"] == "7500"
    assert profiles["Мой GPU"]["INFINI_MANUAL_KNOB"] == "keep"
    assert "INFINI_OPENROUTER_API_KEY" not in profiles["Мой GPU"]
    assert config.read_bytes() == before
    gui.update_values({"INFINI_PROMPT_STYLE": "Default"})
    gui.update_values({"INFINI_CODEX_IMAGE_QUALITY": "low"})
    assert gui.preset == "Custom"
    gui.preset = "Мой: Мой GPU"
    gui.apply_preset()
    assert gui.values["INFINI_PROMPT_STYLE"] == "Terraria Like"
    assert gui.values["INFINI_CODEX_IMAGE_QUALITY"] == "high"
    assert gui.values["INFINI_OPENROUTER_API_KEY"] == "test-only-credential"
    assert gui.preset == "Мой: Мой GPU"
    assert config.read_bytes() == before
    assert gui.collect()["INFINI_MANUAL_KNOB"] == "keep"
    gui.save()
    assert settings_env.parse_env(config)["INFINI_PROMPT_STYLE"] == "Terraria Like"


def test_trace_refresh_is_nonblocking_and_only_latest_endpoint_renders(gui_workflow, held_gui_call):
    gui, root, _config = gui_workflow
    gui.values["INFINI_PORT"] = "5055"
    hold = held_gui_call(gui, "_fetch_trace_snapshot", lambda **kw: {
        "serverRoot": str(root), "cacheDir": kw["base_url"],
        "events": [{"message": kw["base_url"]}],
    }, first_only=True)
    gui.refresh_trace()
    hold.assert_pending()
    assert not any(gui.trace.values())
    for port in (5056, 5057):
        gui.update_values({"INFINI_PORT": str(port)})
        gui.refresh_trace()
    assert hold.calls == ["http://127.0.0.1:5055"]
    hold.release.set()
    gui.drain_until(lambda: "5057" in gui.trace.get("events", ""))
    assert "5055" not in gui.trace["events"]
    assert hold.calls == ["http://127.0.0.1:5055", "http://127.0.0.1:5057"]


@pytest.mark.parametrize("action", ["cancel", "close"])
def test_cancel_or_close_discards_held_trace_results(gui_workflow, held_gui_call, action):
    gui, root, _config = gui_workflow
    hold = held_gui_call(gui, "_fetch_trace_snapshot", {
        "serverRoot": str(root), "events": [{"message": "stale"}],
    })
    gui.refresh_trace()
    assert hold.entered.wait(1)
    gui.refresh_trace()
    if action == "close":
        gui.on_close()
        assert gui._gui_closed
    else:
        gui.cancel_trace_refresh()
        assert "cancel" in gui.trace_status.lower()
    hold.release.set()
    assert hold.finished.wait(1)
    gui.drain_until(lambda: not gui._scheduled_ids)
    assert not any(gui.trace.values())
    assert len(hold.calls) == 1


@pytest.mark.parametrize("identity", ["matching", "foreign-health", "changed-pid"])
def test_trace_http_uses_verified_server_or_selected_local_cache(gui_workflow, identity):
    gui, root, config = gui_workflow
    config.write_text("INFINI_CACHE_DIR=selected-cache\n", encoding="utf-8")
    cache = root / "selected-cache"
    cache.mkdir()
    (cache / "events.ndjson").write_text('{"message":"local-fixture"}\n', encoding="utf-8")
    pid = os.getpid() + 1000
    health = {"ok": True, "serverRoot": str(root), "pid": pid}
    trace = {"ok": True, "serverRoot": str(root), "pid": pid, "cacheDir": "online-cache",
             "events": [{"message": "online-fixture"}]}
    if identity == "foreign-health":
        health["serverRoot"] = str(root.parent / "foreign")
    elif identity == "changed-pid":
        trace["pid"] += 1
    with _gui_loopback_http({"/health": (200, health), "/trace.json": (200, trace)}) as (base, _requests):
        gui.values["INFINI_PORT"] = base.rsplit(":", 1)[1]
        gui.refresh_trace()
        gui.drain_until(lambda: bool(gui.trace["summary"]))
    expected = "online-fixture" if identity == "matching" else "local-fixture"
    rejected = "local-fixture" if identity == "matching" else "online-fixture"
    assert expected in gui.trace["events"]
    assert rejected not in gui.trace["events"]


@pytest.mark.parametrize("online", [False, True])
def test_open_and_clear_use_selected_cache_and_preserve_recipes_pngs_and_other_roots(gui_workflow, monkeypatch, online):
    gui, root, config = gui_workflow
    config.write_text("INFINI_CACHE_DIR=selected-cache\n", encoding="utf-8")
    selected, other = root / "selected-cache", root / "cache"
    preserved = {}
    for cache in (selected, other):
        cache.mkdir()
        for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson"):
            (cache / name).write_text('{"message":"' + cache.name + '"}\n', encoding="utf-8")
        (cache / "recipes").mkdir()
        (cache / "recipes" / "recipe.json").write_bytes(b'{"authoritative":true}')
        (cache / "sprite.png").write_bytes(b"PNG-fixture-bytes")
        (cache / "last_combine_failure.json").write_bytes(b'{"keepFailure":true}')
        for path in cache.rglob("*"):
            if path.is_file() and (cache == other or path.name not in {"events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson"}):
                preserved[path] = path.read_bytes()
    opened = []
    monkeypatch.setattr(controls.webbrowser, "open", lambda uri: opened.append(uri))
    monkeypatch.setattr(controls.os, "startfile", lambda path: opened.append(Path(path).as_uri()), raising=False)

    def read_gui_json(url, **kwargs):
        assert online and "/trace_clear" in str(url)
        assert kwargs["method"] == "POST"
        for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson"):
            controls.trace_tools.clear_ndjson(selected / name)
        return {"ok": True, "cleared": [str(selected / name) for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson")]}

    def health(*args, **kwargs):
        if not online:
            raise ConnectionRefusedError("offline fixture")
        return {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000, "cacheDir": str(selected)}

    monkeypatch.setattr(gui, "_fetch_health_snapshot", health)
    monkeypatch.setattr(gui, "refresh_trace", lambda **_kwargs: None)
    monkeypatch.setattr(gui, "_read_gui_json", read_gui_json)
    gui.open_cache_folder()
    assert opened == [selected.as_uri()], "Open cache ignored selected launch root"
    gui.clear_trace_files(confirmed=True)
    gui.drain_until(lambda: "Trace cleared" in gui.trace_status)
    assert all((selected / name).read_bytes() == b"" for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson"))
    assert all(path.read_bytes() == data for path, data in preserved.items())


def test_clear_refuses_a_different_live_cache_without_local_fallback(gui_workflow, monkeypatch):
    gui, root, config = gui_workflow
    config.write_text("INFINI_CACHE_DIR=selected-cache\n", encoding="utf-8")
    selected = root / "selected-cache"
    selected.mkdir()
    trace = selected / "events.ndjson"
    trace.write_bytes(b'{"keep":true}\n')
    health = {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000,
              "cacheDir": str(root / "different-cache")}
    with _gui_loopback_http({"/health": (200, health)}) as (base, requests):
        gui.values["INFINI_PORT"] = base.rsplit(":", 1)[1]
        gui.clear_trace_files(confirmed=True)
        gui.drain_until(lambda: "refused" in gui.trace_status.lower())
    assert trace.read_bytes() == b'{"keep":true}\n'
    assert "/trace_clear" not in requests


def test_offline_clear_refuses_symlinked_trace_before_touching_cache_bytes(gui_workflow, monkeypatch):
    gui, root, _config = gui_workflow
    cache = root / "cache"
    cache.mkdir()
    for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson"):
        (cache / name).write_bytes(b'{"keep":true}\n')
    foreign = root.parent / "foreign-sprite.png"
    foreign.write_bytes(b"preserved-foreign-PNG")
    linked = cache / "prompt_trace.ndjson"
    linked.unlink(missing_ok=True)
    linked.symlink_to(foreign)
    originals = {path: path.read_bytes() for path in (foreign, cache / "events.ndjson", cache / "pipeline_trace.ndjson")}
    monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda *a, **k: (_ for _ in ()).throw(ConnectionRefusedError()))
    monkeypatch.setattr(gui, "refresh_trace", lambda **_kwargs: None)
    gui.clear_trace_files(confirmed=True)
    gui.drain_until(lambda: "refused" in gui.trace_status.lower())
    assert all(path.read_bytes() == value for path, value in originals.items()), "clear followed a trace/lock symlink or partially truncated the selected cache"
    assert "refused" in gui.trace_status.lower()


@pytest.fixture
def guarded_restart(gui_workflow, monkeypatch):
    """One saved launch and one recording owned process; never spawn a helper."""
    gui, root, config = gui_workflow
    config.write_bytes(b"INFINI_CACHE_DIR=saved-cache\nINFINI_IMAGE_BACKEND=off\nINFINI_MANUAL_KEY=keep\n")
    actions = []
    gui.proc = OwnedProcess(actions)
    monkeypatch.setattr(gui, "_wait_until_helper_stops", lambda *a, **k: True)
    monkeypatch.setattr(controls.subprocess, "Popen", lambda *a, **k: actions.append("spawn") or OwnedProcess(actions))
    monkeypatch.setattr(gui, "_delayed_health_check", lambda: None)
    return gui, root, config, config.read_bytes(), actions


@pytest.mark.parametrize("refusal", [
    pytest.param("busy", id="active-generation"),
    pytest.param("unknown", id="unknown-activity"),
    pytest.param("foreign", id="foreign-root"),
    pytest.param("caller", id="caller-pid"),
    pytest.param("projection", id="missing-runtime-projection"),
])
def test_restart_refusal_never_saves_kills_or_spawns(guarded_restart, monkeypatch, refusal):
    gui, root, config, original, actions = guarded_restart
    snap = {"ok": True, "serverRoot": str(root), "pid": gui.proc.pid,
            "effectiveConfig": gui._proposed_effective_config(),
            "generationActivity": {"active": 0, "waiting": 0, "accepting": True}}
    if refusal == "busy":
        snap["generationActivity"]["active"] = 1
    elif refusal == "unknown":
        snap.pop("generationActivity")
    elif refusal == "foreign":
        snap["serverRoot"] = str(root.parent / "foreign")
    elif refusal == "caller":
        snap["pid"] = os.getpid()
    else:
        snap.pop("effectiveConfig")
    monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda **kwargs: snap)
    monkeypatch.setattr(gui, "_try_http_shutdown_current_server", lambda **kwargs: actions.append("shutdown"))
    gui.start_server()
    gui.drain_until(lambda: "refused" in gui.status.lower())
    assert not actions
    assert config.read_bytes() == original


@pytest.mark.parametrize("shutdown_code", [409, 200], ids=["atomic-busy-refusal", "acknowledged-restart"])
def test_safe_restart_obeys_atomic_shutdown_before_saving_or_launching(guarded_restart, shutdown_code):
    gui, root, config, original, actions = guarded_restart
    health = {"ok": True, "serverRoot": str(root), "pid": gui.proc.pid,
              "effectiveConfig": gui._proposed_effective_config(),
              "generationActivity": {"active": 0, "waiting": 0, "accepting": True}}
    gui.values["INFINI_PROMPT_STYLE"] = "Terraria Like"
    with _gui_loopback_http({"/health": (200, health), "/shutdown": (shutdown_code, {"ok": shutdown_code == 200})}) as (base, requests):
        gui.values["INFINI_PORT"] = base.rsplit(":", 1)[1]
        gui.start_server()
        gui.drain_until(lambda: "busy" in gui.status.lower() or "запущен" in gui.status)
    assert "/shutdown" in requests
    assert not any("force=1" in path for path in requests)
    assert "terminate" not in actions and "kill" not in actions
    if shutdown_code == 409:
        assert not actions
        assert config.read_bytes() == original
    else:
        assert actions == ["spawn"]
        saved = settings_env.parse_env(config)
        assert saved["INFINI_PROMPT_STYLE"] == "Terraria Like"
        assert saved["INFINI_MANUAL_KEY"] == "keep"


@pytest.mark.parametrize("confirmed,foreign", [(False, False), (True, False), (True, True)],
                         ids=["cancelled", "confirmed-own-server", "cannot-force-foreign-server"])
def test_force_restart_requires_confirmation_and_verified_identity(guarded_restart, monkeypatch, confirmed, foreign):
    gui, root, config, original, actions = guarded_restart
    health = {"ok": True, "serverRoot": str(root.parent / "foreign" if foreign else root),
              "pid": gui.proc.pid, "effectiveConfig": gui._proposed_effective_config(),
              "generationActivity": {"active": 1, "waiting": 1, "accepting": True}}

    with _gui_loopback_http({"/health": (200, health), "/shutdown": (200, {"ok": True})}) as (base, requests):
        gui.values["INFINI_PORT"] = base.rsplit(":", 1)[1]
        result = gui.force_restart_server(confirmed=confirmed)
        if not confirmed:
            assert result["ok"] is False
            assert "confirmation" in result["message"]
            assert not actions and config.read_bytes() == original
            return
        gui.drain_until(lambda: any(word in gui.status.lower() for word in ("cancelled", "refused", "запущен")))
    if confirmed and not foreign:
        assert "/shutdown?force=1" in requests
        assert actions == ["spawn"]
    else:
        assert not any(path.startswith("/shutdown") for path in requests)
        assert not actions
        assert config.read_bytes() == original


@pytest.mark.parametrize("action", ["start_server", "stop_server"])
def test_server_actions_return_while_health_is_held_and_do_not_duplicate_work(gui_workflow, held_gui_call, action):
    gui, root, _config = gui_workflow
    actions = []
    gui.proc = OwnedProcess(actions)
    hold = held_gui_call(gui, "_fetch_health_snapshot", {
        "ok": True, "serverRoot": str(root), "pid": gui.proc.pid,
        "generationActivity": {"active": 1, "waiting": 0, "accepting": True},
    })
    callback = getattr(gui, action)
    callback()
    hold.assert_pending()
    callback()
    hold.release.set()
    gui.drain_until(lambda: "busy" in gui.status.lower())
    assert len(hold.calls) == 1
    assert not actions


@pytest.fixture
def applied_gui(gui_workflow):
    gui, root, config = gui_workflow
    config.write_text(
        "INFINI_CACHE_DIR=selected-cache\nINFINI_WORLD_RECIPES_DIR=selected-worlds\n"
        "INFINI_IMAGE_BACKEND=off\nINFINI_LLM_PROVIDER=openrouter\n"
        "INFINI_OPENROUTER_MODEL=Provider/Model\nINFINI_OPENROUTER_PROVIDER=Exact-Slug\n"
        "INFINI_SDCPP_SERVER_AUTOSTART=0\nINFINI_OPENROUTER_API_KEY=FAKE-SAVED-SECRET-CANARY\n",
        encoding="utf-8",
    )
    gui.values = settings_env.parse_env(config)
    effective = {"cacheDir": str(root / "selected-cache"), "worldRecipesDir": str(root / "selected-worlds"),
                 "imageBackend": "off", "llmProvider": "openrouter", "llmModel": "Provider/Model",
                 "openrouterProvider": "Exact-Slug", "sdcppAutostart": False}
    gui.proc = OwnedProcess()
    return gui, root, config, effective


def test_health_feedback_is_async_bounded_truthful_and_nonsecret(applied_gui, held_gui_call):
    gui, root, _config, effective = applied_gui
    rows = [{"requestId": f"{index:032x}", "profileId": "llm_2", "stage": "05_visual_director",
             "elapsedSeconds": 12.5, "stageElapsedSeconds": 3.25, "waitReason": "profile_slot",
             "networkStarted": started, "secret": "DO_NOT_DISPLAY"}
            for index, started in enumerate([None, False, True] + [False] * 31)]
    health = {"ok": True, "serverRoot": str(root), "pid": gui.proc.pid,
              "effectiveConfig": {**effective, "extraSecret": "FAKE-HEALTH-SECRET-CANARY"},
              "llmAuth": {"secret": "FAKE-AUTH-SECRET-CANARY"},
              "generationActivity": {"active": 1, "waiting": 0, "accepting": True,
                                     "requests": rows, "requestsOmitted": 2}}
    hold = held_gui_call(gui, "_fetch_health_snapshot", health)
    gui._delayed_health_check()
    hold.assert_pending()
    hold.release.set()
    gui.drain_until(lambda: "matches" in gui.applied_config.lower())
    feedback = gui.applied_config
    assert "partial" in feedback.lower() and "secret" in feedback.lower()
    text = gui.activity
    for value in ("llm_2", "05_visual_director", "12.5", "3.25", "profile_slot",
                  "network=unknown", "network=not started", "network=started", "4 rows omitted"):
        assert value in text
    assert rows[0]["requestId"] in text and rows[-1]["requestId"] not in text
    assert "CANARY" not in feedback + gui.status + text
    assert "DO_NOT_DISPLAY" not in text
    gui.values["INFINI_OPENROUTER_PROVIDER"] = "exact-slug"  # case-sensitive pin
    gui.save()
    assert "matches" not in gui.applied_config.lower()
    assert "openrouterProvider" in gui.applied_config


@pytest.mark.parametrize("change", ["endpoint", "owned-pid", "projection", "error"])
def test_health_feedback_cannot_confirm_stale_unverified_or_failed_results(applied_gui, held_gui_call, change):
    gui, root, _config, effective = applied_gui
    gui.values["INFINI_PORT"] = "5055"
    health = {"ok": True, "serverRoot": str(root), "pid": gui.proc.pid,
              "effectiveConfig": effective,
              "generationActivity": {"active": 3, "waiting": 0, "accepting": True, "requests": []}}
    if change == "owned-pid":
        health["pid"] += 1
    elif change == "projection":
        health.pop("effectiveConfig")
    response = RuntimeError("FAKE-SECRET-CANARY") if change == "error" else health
    hold = held_gui_call(gui, "_fetch_health_snapshot", response)
    gui._delayed_health_check()
    assert hold.entered.wait(1)
    if change == "endpoint":
        gui.update_values({"INFINI_PORT": "5056"})
    hold.release.set()
    gui.drain_until(lambda: "unconfirmed" in gui.applied_config.lower())
    assert "active=3" not in gui.activity
    assert "CANARY" not in gui.applied_config + gui.status


def test_health_activity_display_consumes_actual_backend_owner():
    from infini_local.services import combine_endpoint as backend
    from infini_local.desktop.studio_operations import StudioOperations as controls
    with backend._GenerationAdmission("llm_3") as owner:
        assert owner.activate()
        with backend.generation_stage("06_vfx_director"):
            backend.update_generation_activity(wait_reason="provider_cooldown", network_started=False)
            text = controls._generation_activity_text(backend.generation_activity_snapshot())
            for value in (owner.request_id, "llm_3", "06_vfx_director", "provider_cooldown", "network=not started"):
                assert value in text
        between = controls._generation_activity_text(backend.generation_activity_snapshot())
        assert owner.request_id in between and "stage=unknown" in between
    assert owner.request_id not in controls._generation_activity_text(backend.generation_activity_snapshot())


class _SpriteGuiHarness(_GuiWorkflowHarness):
    def __init__(self, config_path, **overrides):
        super().__init__(config_path)
        self.values = dict(settings_schema.DEFAULTS)
        self.values.update(overrides)
        self.preset = next(iter(settings_schema.PRESETS))
        self._capture_profile_baseline()
        self._refresh_visibility()


def test_pipeline_preserves_explicit_resize_until_user_resets_it(tmp_path):
    gui = _SpriteGuiHarness(tmp_path / "config.env", INFINI_SPRITE_DOWNSCALE_FILTER="lanczos",
                            INFINI_SPRITE_PREMULTIPLIED_RESIZE="0", INFINI_BG_COLOR="transparent")
    gui.apply_preset()
    assert gui.values["INFINI_SPRITE_DOWNSCALE_FILTER"] == "lanczos"
    assert gui.values["INFINI_SPRITE_PREMULTIPLIED_RESIZE"] == "0"
    gui.update_values({"INFINI_BG_COLOR": "transparent"})
    gui.reset_sprite_resize()
    assert gui.values["INFINI_SPRITE_DOWNSCALE_FILTER"] == "box"
    assert gui.values["INFINI_SPRITE_PREMULTIPLIED_RESIZE"] == "1"
    assert gui.values["INFINI_BG_COLOR"] == "transparent"


@pytest.mark.parametrize("backend,background,keyer", [
    pytest.param("openai_codex", "transparent", False, id="native-alpha"),
    pytest.param("sdcpp", "magenta", True, id="local-keyer"),
    pytest.param("off", "transparent", False, id="no-image-backend"),
])
def test_visibility_preserves_background_choice_and_only_enables_applicable_controls(tmp_path, backend, background, keyer):
    gui = _SpriteGuiHarness(tmp_path / "config.env", INFINI_REMOVE_BG="1", INFINI_BG_COLOR=background,
                            INFINI_BG_REMOVE_MODE="sprite_keyer", INFINI_IMAGE_BACKEND=backend)
    gui._refresh_visibility()
    assert (not gui.field_disabled_reasons.get("INFINI_CHROMA_TOLERANCE")) is keyer
    assert (not gui.field_disabled_reasons.get("INFINI_BG_COLOR")) is (backend != "off")
    assert (not gui.field_disabled_reasons.get("INFINI_ALPHA_THRESHOLD")) is (backend != "off")
    assert gui.values["INFINI_BG_COLOR"] == background
    assert gui.values["INFINI_BG_REMOVE_MODE"] == "sprite_keyer"


@pytest.mark.parametrize('transient', [ConnectionResetError(), TimeoutError(), ValueError('partial shutdown response')])
def test_shutdown_wait_retries_transient_failures_until_connection_refusal(gui_workflow, monkeypatch, transient):
    gui, _root, _config = gui_workflow
    observed = []
    ticks = [0.0]
    monkeypatch.setattr(controls.time, 'monotonic', lambda: ticks[0])
    monkeypatch.setattr(controls.time, 'sleep', lambda delay: ticks.__setitem__(0, ticks[0] + delay))
    replies = iter([transient, ConnectionRefusedError()])
    def probe(**kwargs):
        observed.append(kwargs['timeout'])
        raise next(replies)
    monkeypatch.setattr(gui, '_fetch_health_snapshot', probe)
    assert gui._wait_until_helper_stops(timeout=4, base_url='http://127.0.0.1:5055') is True
    assert len(observed) == 2
    assert observed[1] < observed[0]


@pytest.mark.parametrize('transient', [ConnectionResetError(), TimeoutError(), ValueError('bad JSON')])
def test_shutdown_wait_never_certifies_unknown_failures_as_free_port(gui_workflow, monkeypatch, transient):
    gui, _root, _config = gui_workflow
    ticks = [0.0]
    monkeypatch.setattr(controls.time, 'monotonic', lambda: ticks[0])
    monkeypatch.setattr(controls.time, 'sleep', lambda delay: ticks.__setitem__(0, ticks[0] + delay))
    def probe(**kwargs):
        raise transient
    monkeypatch.setattr(gui, '_fetch_health_snapshot', probe)
    assert gui._wait_until_helper_stops(timeout=1, base_url='http://127.0.0.1:5055') is False
    assert ticks[0] == pytest.approx(1)


def test_shutdown_wait_honors_cancellation(gui_workflow, monkeypatch):
    gui, _root, _config = gui_workflow
    cancel = threading.Event()
    def probe(**kwargs):
        cancel.set()
        raise ConnectionResetError()
    monkeypatch.setattr(gui, '_fetch_health_snapshot', probe)
    assert gui._wait_until_helper_stops(timeout=4, cancel=cancel) is False
