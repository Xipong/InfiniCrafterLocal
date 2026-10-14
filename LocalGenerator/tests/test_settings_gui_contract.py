"""Headless GUI behavior portfolio: real callbacks, isolated files and loopback IO."""
from __future__ import annotations

import importlib.abc
import importlib.util
import os
from pathlib import Path
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from provider_test_support import OwnedProcess, loopback_server, write_json_response
from infini_local.desktop import settings_env, settings_gui, settings_schema
from infini_local.desktop import settings_gui_server_controls as controls
from infini_local.desktop.settings_gui_image_args import SettingsGuiImageArgsMixin
import infini_local.desktop.settings_gui_trace_state as settings_trace_state


GUI_PATH = Path(settings_gui.__file__)


class _BlockTkinter(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path=None, target=None):  # type: ignore[override]
        if fullname == "tkinter" or fullname.startswith("tkinter."):
            raise ModuleNotFoundError("No module named 'tkinter'")
        return None


def test_settings_gui_imports_without_tkinter_installed() -> None:
    """Headless Python installs must import GUI helpers without tkinter/_tkinter."""
    module_path = GUI_PATH
    spec = importlib.util.spec_from_file_location("_infini_settings_gui_headless_probe", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    saved_tk_modules = {key: value for key, value in sys.modules.items() if key == "tkinter" or key.startswith("tkinter.")}
    saved_compat = {key: value for key, value in sys.modules.items() if key.endswith("desktop.tk_compat")}
    blocker = _BlockTkinter()
    try:
        for key in [*saved_tk_modules, *saved_compat]:
            sys.modules.pop(key, None)
        sys.meta_path.insert(0, blocker)
        spec.loader.exec_module(module)
    finally:
        if blocker in sys.meta_path:
            sys.meta_path.remove(blocker)
        for key in list(sys.modules):
            if key == "tkinter" or key.startswith("tkinter.") or key.endswith("desktop.tk_compat"):
                sys.modules.pop(key, None)
        sys.modules.update(saved_tk_modules)
        sys.modules.update(saved_compat)

    assert module.tk_compat.TKINTER_AVAILABLE is False


class _UiVar:
    """UI-owned value; worker reads/writes fail instead of silently passing."""
    def __init__(self, value=""):
        self.value = value
        self.owner = threading.get_ident()
        self.callbacks = []

    def get(self):
        assert threading.get_ident() == self.owner, "worker read a Tk variable"
        return self.value

    def set(self, value):
        assert threading.get_ident() == self.owner, "worker wrote a Tk variable"
        self.value = value
        for callback in self.callbacks:
            callback()

    def trace_add(self, _mode, callback):
        self.callbacks.append(callback)


class _GuiWorkflowHarness(controls.SettingsGuiServerControlsMixin, settings_trace_state.SettingsGuiTraceStateMixin):
    """Real desktop callbacks with an explicit headless UI scheduling seam."""
    def __init__(self):
        self.vars = {}
        self.text_widgets = {}
        self.data = dict(settings_schema.DEFAULTS)
        self.radmin_enabled = _UiVar(False)
        self.status_var = _UiVar()
        self.applied_config_var = _UiVar("Runtime config not checked (partial non-secret projection).")
        self.trace_status_var = _UiVar()
        self.activity_var = _UiVar()
        self.proc = None
        self.owner = threading.get_ident()
        self.jobs = {}
        self.serial = 0
        self.rendered = {}
        self.destroyed = False

    def after(self, _delay, callback):
        assert threading.get_ident() == self.owner, "worker scheduled Tk callback"
        self.serial += 1
        self.jobs[self.serial] = callback
        return self.serial

    def after_cancel(self, job):
        assert threading.get_ident() == self.owner
        self.jobs.pop(job, None)

    def drain_until(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            callbacks, self.jobs = self.jobs, {}
            for callback in callbacks.values():
                callback()
            time.sleep(0.005)
        assert predicate(), "worker result did not reach UI within test deadline"

    def _set_trace_text(self, key, content):
        assert threading.get_ident() == self.owner, "worker rendered Tk text"
        self.rendered[key] = content

    def _lora_dir_from_file(self, _filename):
        return ""

    def destroy(self):
        self.destroyed = True


@pytest.fixture
def gui_workflow(tmp_path, monkeypatch):
    root = tmp_path / "LocalGenerator"
    root.mkdir()
    config = root / "config.env"
    monkeypatch.setattr(settings_trace_state, "ROOT", root)
    monkeypatch.setattr(settings_trace_state, "CONFIG_PATH", config)
    monkeypatch.setattr(controls, "ROOT", root)
    monkeypatch.setattr(controls, "CONFIG_PATH", config)
    monkeypatch.delenv("INFINI_CACHE_DIR", raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    return _GuiWorkflowHarness(), root, config


@pytest.fixture
def held_gui_call(monkeypatch):
    """Hold one worker without touching Tk; teardown releases unfinished calls."""
    holds = []
    workers = []

    def install(target, method, response, *, first_only=False):
        entered, release, finished = (threading.Event() for _ in range(3))
        calls = []
        holds.append(release)

        def fetch(*args, **kwargs):
            workers.append(threading.current_thread())
            calls.append(kwargs.get("base_url"))
            if not first_only or len(calls) == 1:
                entered.set()
                assert release.wait(3), "test worker hold expired"
            try:
                if isinstance(response, Exception):
                    raise response
                return response(**kwargs) if callable(response) else response
            finally:
                finished.set()

        monkeypatch.setattr(target, method, fetch)
        return SimpleNamespace(entered=entered, release=release, finished=finished, calls=calls)

    yield install
    for release in holds:
        release.set()
    for worker in workers:
        worker.join(timeout=3)
        assert not worker.is_alive(), "held worker did not finish"


@contextmanager
def _gui_loopback_http(responses):
    """Synthetic diagnostic HTTP only, not the application's real server."""
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            response = responses.get(urlsplit(self.path).path, (404, {"ok": False}))
            if callable(response):
                response = response(self.path)
            code, value = response
            write_json_response(self, value, status=code)

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
    gui.vars["INFINI_PROMPT_STYLE"] = _UiVar("Terraria Like")
    gui.save()
    reloaded = settings_gui.parse_env(config)
    assert reloaded["INFINI_PROMPT_STYLE"] == "Terraria Like"
    assert reloaded["INFINI_IMAGE_BACKEND"] == "sdcpp"
    assert reloaded["INFINI_MANUAL_KEY"] == "retained"
    gui.vars["INFINI_PROMPT_STYLE"].set("Default")
    gui.save()
    assert settings_gui.parse_env(config)["INFINI_MANUAL_KEY"] == "retained"


def test_gui_saves_named_profile_separately_and_restores_exact_settings(gui_workflow, monkeypatch):
    from infini_local.desktop.settings_env import load_user_presets
    gui, _root, config = gui_workflow
    config.write_text("INFINI_MANUAL_KNOB=disk\n", encoding="utf-8")
    before = config.read_bytes()
    gui.data["INFINI_MANUAL_KNOB"] = "keep"
    gui.vars["INFINI_PROMPT_STYLE"] = _UiVar("Terraria Like")
    gui.vars["INFINI_CODEX_IMAGE_QUALITY"] = _UiVar("high")
    gui.vars["INFINI_LLM_REASONING_MAX_TOKENS"] = _UiVar("7500")
    gui.vars["INFINI_OPENROUTER_API_KEY"] = _UiVar("test-only-credential")
    gui.preset_var = _UiVar("Custom")
    gui.user_presets = {}
    gui.preset_combo = SimpleNamespace(configure=lambda **kwargs: None)
    gui._refresh_visibility = lambda: None
    gui._install_profile_tracking()
    monkeypatch.setattr(settings_trace_state.simpledialog, "askstring", lambda *args, **kwargs: "Мой GPU")
    gui.save_profile_as()
    path = config.with_name("gui_user_presets.json")
    profiles = load_user_presets(path)
    assert gui.preset_var.get() == "Мой: Мой GPU"
    assert profiles["Мой GPU"]["INFINI_PROMPT_STYLE"] == "Terraria Like"
    assert profiles["Мой GPU"]["INFINI_LLM_REASONING_MAX_TOKENS"] == "7500"
    assert profiles["Мой GPU"]["INFINI_MANUAL_KNOB"] == "keep"
    assert "INFINI_OPENROUTER_API_KEY" not in profiles["Мой GPU"]
    assert config.read_bytes() == before
    gui.vars["INFINI_PROMPT_STYLE"].set("Default")
    gui.vars["INFINI_CODEX_IMAGE_QUALITY"].set("low")
    assert gui.preset_var.get() == "Custom"
    gui.preset_var.set("Мой: Мой GPU")
    gui.apply_preset()
    assert gui.vars["INFINI_PROMPT_STYLE"].get() == "Terraria Like"
    assert gui.vars["INFINI_CODEX_IMAGE_QUALITY"].get() == "high"
    assert gui.vars["INFINI_OPENROUTER_API_KEY"].get() == "test-only-credential"
    assert gui.preset_var.get() == "Мой: Мой GPU"
    assert config.read_bytes() == before
    assert gui.collect()["INFINI_MANUAL_KNOB"] == "keep"
    gui.save()
    assert settings_gui.parse_env(config)["INFINI_PROMPT_STYLE"] == "Terraria Like"


def test_trace_refresh_is_nonblocking_and_only_latest_endpoint_renders(gui_workflow, held_gui_call):
    gui, root, _config = gui_workflow
    gui.vars["INFINI_PORT"] = _UiVar("5055")
    hold = held_gui_call(gui, "_fetch_trace_snapshot", lambda **kw: {
        "serverRoot": str(root), "cacheDir": kw["base_url"],
        "events": [{"message": kw["base_url"]}],
    }, first_only=True)
    before = time.monotonic()
    gui.refresh_trace()
    assert time.monotonic() - before < 0.2, "Refresh blocked the UI on IO"
    assert hold.entered.wait(1)
    assert not gui.rendered
    for port in (5056, 5057):
        gui.vars["INFINI_PORT"].set(str(port))
        gui.refresh_trace()
    assert hold.calls == ["http://127.0.0.1:5055"]
    hold.release.set()
    gui.drain_until(lambda: "5057" in gui.rendered.get("events", ""))
    assert "5055" not in gui.rendered["events"]
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
        assert gui.destroyed
    else:
        gui.cancel_trace_refresh()
        assert "cancel" in gui.trace_status_var.get().lower()
    hold.release.set()
    assert hold.finished.wait(1)
    gui.drain_until(lambda: not gui.jobs)
    assert not gui.rendered
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
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        gui.refresh_trace()
        gui.drain_until(lambda: "summary" in gui.rendered)
    expected = "online-fixture" if identity == "matching" else "local-fixture"
    rejected = "local-fixture" if identity == "matching" else "online-fixture"
    assert expected in gui.rendered["events"]
    assert rejected not in gui.rendered["events"]


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
    monkeypatch.setattr(settings_trace_state.webbrowser, "open", lambda uri: opened.append(uri))
    monkeypatch.setattr(settings_trace_state.os, "startfile", lambda path: opened.append(Path(path).as_uri()), raising=False)
    monkeypatch.setattr(settings_trace_state.messagebox, "askyesno", lambda *a, **k: True)

    def read_gui_json(url, **kwargs):
        assert online and "/trace_clear" in str(url)
        for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson"):
            settings_trace_state.trace_tools.clear_ndjson(selected / name)
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
    gui.clear_trace_files()
    gui.drain_until(lambda: "Trace cleared" in gui.trace_status_var.get())
    assert all((selected / name).read_bytes() == b"" for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson"))
    assert all(path.read_bytes() == data for path, data in preserved.items())


def test_clear_refuses_a_different_live_cache_without_local_fallback(gui_workflow, monkeypatch):
    gui, root, config = gui_workflow
    config.write_text("INFINI_CACHE_DIR=selected-cache\n", encoding="utf-8")
    selected = root / "selected-cache"
    selected.mkdir()
    trace = selected / "events.ndjson"
    trace.write_bytes(b'{"keep":true}\n')
    monkeypatch.setattr(settings_trace_state.messagebox, "askyesno", lambda *a, **k: True)
    health = {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000,
              "cacheDir": str(root / "different-cache")}
    with _gui_loopback_http({"/health": (200, health)}) as (base, requests):
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        gui.clear_trace_files()
        gui.drain_until(lambda: "refused" in gui.trace_status_var.get().lower())
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
    monkeypatch.setattr(settings_trace_state.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda *a, **k: (_ for _ in ()).throw(ConnectionRefusedError()))
    monkeypatch.setattr(gui, "refresh_trace", lambda **_kwargs: None)
    gui.clear_trace_files()
    gui.drain_until(lambda: "refused" in gui.trace_status_var.get().lower())
    assert all(path.read_bytes() == value for path, value in originals.items()), "clear followed a trace/lock symlink or partially truncated the selected cache"
    assert "refused" in gui.trace_status_var.get().lower()


@pytest.fixture
def guarded_restart(gui_workflow, monkeypatch):
    """One saved launch and one recording owned process; never spawn a helper."""
    gui, root, config = gui_workflow
    config.write_bytes(b"INFINI_CACHE_DIR=saved-cache\nINFINI_IMAGE_BACKEND=off\nINFINI_MANUAL_KEY=keep\n")
    actions = []
    gui.proc = OwnedProcess(actions)
    monkeypatch.setattr(gui, "_wait_until_helper_stops", lambda *a, **k: True)
    monkeypatch.setattr(controls.subprocess, "Popen", lambda *a, **k: actions.append("spawn") or OwnedProcess(actions))
    monkeypatch.setattr(controls.messagebox, "showwarning", lambda *a, **k: None)
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
    gui.drain_until(lambda: "refused" in gui.status_var.get().lower())
    assert not actions
    assert config.read_bytes() == original


@pytest.mark.parametrize("shutdown_code", [409, 200], ids=["atomic-busy-refusal", "acknowledged-restart"])
def test_safe_restart_obeys_atomic_shutdown_before_saving_or_launching(guarded_restart, shutdown_code):
    gui, root, config, original, actions = guarded_restart
    health = {"ok": True, "serverRoot": str(root), "pid": gui.proc.pid,
              "effectiveConfig": gui._proposed_effective_config(),
              "generationActivity": {"active": 0, "waiting": 0, "accepting": True}}
    gui.vars["INFINI_PROMPT_STYLE"] = _UiVar("Terraria Like")
    with _gui_loopback_http({"/health": (200, health), "/shutdown": (shutdown_code, {"ok": shutdown_code == 200})}) as (base, requests):
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        gui.start_server()
        gui.drain_until(lambda: "busy" in gui.status_var.get().lower() or "запущен" in gui.status_var.get())
    assert "/shutdown" in requests
    assert not any("force=1" in path for path in requests)
    assert "terminate" not in actions and "kill" not in actions
    if shutdown_code == 409:
        assert not actions
        assert config.read_bytes() == original
    else:
        assert actions == ["spawn"]
        saved = settings_gui.parse_env(config)
        assert saved["INFINI_PROMPT_STYLE"] == "Terraria Like"
        assert saved["INFINI_MANUAL_KEY"] == "keep"


@pytest.mark.parametrize("confirmed,foreign", [(False, False), (True, False), (True, True)],
                         ids=["cancelled", "confirmed-own-server", "cannot-force-foreign-server"])
def test_force_restart_requires_confirmation_and_verified_identity(guarded_restart, monkeypatch, confirmed, foreign):
    gui, root, config, original, actions = guarded_restart
    health = {"ok": True, "serverRoot": str(root.parent / "foreign" if foreign else root),
              "pid": gui.proc.pid, "effectiveConfig": gui._proposed_effective_config(),
              "generationActivity": {"active": 1, "waiting": 1, "accepting": True}}

    def ask(*args, **kwargs):
        assert threading.get_ident() == gui.owner
        return confirmed

    monkeypatch.setattr(controls.messagebox, "askyesno", ask)
    with _gui_loopback_http({"/health": (200, health), "/shutdown": (200, {"ok": True})}) as (base, requests):
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        gui.force_restart_server()
        gui.drain_until(lambda: any(word in gui.status_var.get().lower() for word in ("cancelled", "refused", "запущен")))
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
    before = time.monotonic()
    callback()
    assert time.monotonic() - before < 0.2
    assert hold.entered.wait(1)
    callback()
    hold.release.set()
    gui.drain_until(lambda: "busy" in gui.status_var.get().lower())
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
    before = time.monotonic()
    gui._delayed_health_check()
    assert time.monotonic() - before < 0.2
    assert hold.entered.wait(1)
    hold.release.set()
    gui.drain_until(lambda: "matches" in gui.applied_config_var.get().lower())
    feedback = gui.applied_config_var.get()
    assert "partial" in feedback.lower() and "secret" in feedback.lower()
    text = gui.activity_var.get()
    for value in ("llm_2", "05_visual_director", "12.5", "3.25", "profile_slot",
                  "network=unknown", "network=not started", "network=started", "4 rows omitted"):
        assert value in text
    assert rows[0]["requestId"] in text and rows[-1]["requestId"] not in text
    assert "CANARY" not in feedback + gui.status_var.get() + text
    assert "DO_NOT_DISPLAY" not in text
    gui.vars["INFINI_OPENROUTER_PROVIDER"] = _UiVar("exact-slug")  # case-sensitive pin
    gui.save()
    assert "matches" not in gui.applied_config_var.get().lower()
    assert "openrouterProvider" in gui.applied_config_var.get()


@pytest.mark.parametrize("change", ["endpoint", "owned-pid", "projection", "error"])
def test_health_feedback_cannot_confirm_stale_unverified_or_failed_results(applied_gui, held_gui_call, change):
    gui, root, _config, effective = applied_gui
    gui.vars["INFINI_PORT"] = _UiVar("5055")
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
        gui.vars["INFINI_PORT"].set("5056")
    hold.release.set()
    gui.drain_until(lambda: "unconfirmed" in gui.applied_config_var.get().lower())
    assert "active=3" not in gui.activity_var.get()
    assert "CANARY" not in gui.applied_config_var.get() + gui.status_var.get()


def test_health_activity_display_consumes_actual_backend_owner():
    from infini_local.services import combine_endpoint as backend
    from infini_local.desktop.settings_gui_server_controls import SettingsGuiServerControlsMixin as controls
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


class _SpriteGuiHarness(SettingsGuiImageArgsMixin, settings_trace_state.SettingsGuiTraceStateMixin):
    """Recording UI seam: real callbacks without Tk, credentials or backend IO."""
    def __init__(self, **overrides):
        self.data = dict(settings_schema.DEFAULTS)
        self.data.update(overrides)
        self.vars = {key: _UiVar(value) for key, value in self.data.items()}
        self.preset_var = _UiVar(next(iter(settings_schema.PRESETS)))
        self.status_var = _UiVar()
        self.radmin_enabled = _UiVar("")
        self.field_widgets = {key: [] for key in self.vars}
        self.extra_arg_buttons = []
        self.sdcpp_debug_buttons = []
        self.field_state = {}

    def _refresh_secret_entries(self):
        pass

    def _set_widgets_enabled(self, _widgets, _enabled):
        pass

    def _set_field_enabled(self, key, enabled, reason=""):
        self.field_state[key] = (enabled, reason)


def test_pipeline_preserves_explicit_resize_until_user_resets_it():
    gui = _SpriteGuiHarness(INFINI_SPRITE_DOWNSCALE_FILTER="lanczos",
                            INFINI_SPRITE_PREMULTIPLIED_RESIZE="0", INFINI_BG_COLOR="transparent")
    gui.apply_preset()
    assert gui.vars["INFINI_SPRITE_DOWNSCALE_FILTER"].get() == "lanczos"
    assert gui.vars["INFINI_SPRITE_PREMULTIPLIED_RESIZE"].get() == "0"
    gui.vars["INFINI_BG_COLOR"].set("transparent")
    gui.reset_sprite_resize()
    assert gui.vars["INFINI_SPRITE_DOWNSCALE_FILTER"].get() == "box"
    assert gui.vars["INFINI_SPRITE_PREMULTIPLIED_RESIZE"].get() == "1"
    assert gui.vars["INFINI_BG_COLOR"].get() == "transparent"


@pytest.mark.parametrize("backend,background,keyer", [
    pytest.param("openai_codex", "transparent", False, id="native-alpha"),
    pytest.param("sdcpp", "magenta", True, id="local-keyer"),
    pytest.param("off", "transparent", False, id="no-image-backend"),
])
def test_visibility_preserves_background_choice_and_only_enables_applicable_controls(backend, background, keyer):
    gui = _SpriteGuiHarness(INFINI_REMOVE_BG="1", INFINI_BG_COLOR=background,
                            INFINI_BG_REMOVE_MODE="sprite_keyer", INFINI_IMAGE_BACKEND=backend)
    gui._refresh_visibility()
    assert gui.field_state["INFINI_CHROMA_TOLERANCE"][0] is keyer
    assert gui.field_state["INFINI_BG_COLOR"][0] is (backend != "off")
    assert gui.field_state["INFINI_ALPHA_THRESHOLD"][0] is (backend != "off")
    assert gui.vars["INFINI_BG_COLOR"].get() == background
    assert gui.vars["INFINI_BG_REMOVE_MODE"].get() == "sprite_keyer"


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
