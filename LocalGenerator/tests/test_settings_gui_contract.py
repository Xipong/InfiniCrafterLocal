from __future__ import annotations

import importlib.abc
import importlib.util
from pathlib import Path
import sys
import os
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

import pytest

from provider_test_support import OwnedProcess, loopback_server, write_json_response
from infini_local.desktop.settings_gui_server_controls import SettingsGuiServerControlsMixin

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.desktop import settings_env, settings_gui, settings_schema
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
    assert isinstance(module.tk.Tk(), module.tk.Widget)
    assert isinstance(module.ttk.Entry(), module.ttk.Widget)


def test_gui_settings_save_reload_preserves_choices_and_unknown_fields(tmp_path):
    path = tmp_path / "settings.env"
    values = {"INFINI_PROMPT_STYLE": "Terraria Like", "INFINI_IMAGE_BACKEND": "sdcpp", "INFINI_MANUAL_KEY": "retained"}
    settings_env.write_env(path, values)
    parsed = settings_gui.parse_env(path)
    assert {key: parsed[key] for key in values} == values
    parsed["INFINI_PROMPT_STYLE"] = "Default"
    settings_env.write_env(path, parsed)
    reloaded = settings_gui.parse_env(path)
    assert reloaded["INFINI_PROMPT_STYLE"] == "Default"
    assert reloaded["INFINI_MANUAL_KEY"] == "retained"


class _UiVar:
    """Strict UI-bound variable; a worker read or write is a test failure."""
    def __init__(self, value=""):
        self.value = value
        self.owner = threading.get_ident()

    def get(self):
        assert threading.get_ident() == self.owner, "worker read a Tk variable"
        return self.value

    def set(self, value):
        assert threading.get_ident() == self.owner, "worker wrote a Tk variable"
        self.value = value


class _GuiWorkflowHarness(SettingsGuiServerControlsMixin, settings_trace_state.SettingsGuiTraceStateMixin):
    """Real desktop callbacks with an explicit headless UI scheduling seam."""
    def __init__(self):
        self.vars = {}
        self.text_widgets = {}
        self.data = dict(settings_schema.DEFAULTS)
        self.radmin_enabled = _UiVar(False)
        self.status_var = _UiVar()
        self.applied_config_var = _UiVar("Runtime config not checked (partial non-secret projection).")
        self.trace_status_var = _UiVar()
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
    from infini_local.desktop import settings_gui_server_controls as controls
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


@pytest.mark.parametrize("saved,inherited,relative", [
    (None, None, "cache"),
    ("selected-cache", None, "selected-cache"),
    ("ABSOLUTE", None, "absolute-cache"),
    (None, "inherited-cache", "inherited-cache"),
    (None, "ABSOLUTE", "absolute-cache"),
    ("selected-cache", "inherited-cache", "selected-cache"),
    ("", "inherited-cache", "."),
])
def test_offline_trace_cache_root_matches_gui_launch_environment(gui_workflow, monkeypatch, saved, inherited, relative):
    gui, root, config = gui_workflow
    if saved is not None:
        config.write_text("INFINI_CACHE_DIR=" + (str(root / "absolute-cache") if saved == "ABSOLUTE" else saved) + "\n", encoding="utf-8")
    if inherited is not None:
        monkeypatch.setenv("INFINI_CACHE_DIR", str(root / "absolute-cache") if inherited == "ABSOLUTE" else inherited)
    selected = (root / relative).resolve()
    selected.mkdir(exist_ok=True)
    (selected / "events.ndjson").write_text('{"message":"selected"}\n', encoding="utf-8")
    launch_env = os.environ.copy()
    launch_env.update(gui.collect())
    launch_path = Path(launch_env.get("INFINI_CACHE_DIR", str(root / "cache")))
    if not launch_path.is_absolute():
        launch_path = root / launch_path
    assert launch_path.resolve() == selected
    snapshot = gui._load_local_trace_snapshot("offline")
    assert Path(snapshot["cacheDir"]).resolve() == selected
    assert snapshot["events"] == [{"message": "selected"}]


@pytest.fixture
def held_gui_call(monkeypatch):
    """Recording network hold; UI-thread invariants remain in each consumer test."""
    from types import SimpleNamespace

    holds = []

    def install(gui, method, response, *, timeout=3, first_only=False):
        entered, release, finished = (threading.Event() for _ in range(3))
        calls = []
        holds.append(release)

        def fetch(*args, **kwargs):
            calls.append((threading.get_ident(), args, kwargs))
            if not first_only or len(calls) == 1:
                entered.set()
                assert release.wait(timeout), "test network hold expired"
                finished.set()
            return response(**kwargs) if callable(response) else response

        monkeypatch.setattr(gui, method, fetch)
        return SimpleNamespace(entered=entered, release=release, finished=finished, calls=calls)

    yield install
    for release in holds:
        release.set()


def test_trace_refresh_returns_while_worker_is_held_and_only_ui_renders(gui_workflow, monkeypatch, held_gui_call):
    gui, root, config = gui_workflow
    config.write_text("INFINI_CACHE_DIR=selected-cache\n", encoding="utf-8")
    hold = held_gui_call(gui, "_fetch_trace_snapshot", {"serverRoot": str(root), "cacheDir": "held-server-cache", "events": [{"message": "from-worker"}]}, timeout=2, first_only=False)

    before = time.monotonic()
    gui.refresh_trace()
    elapsed = time.monotonic() - before
    assert elapsed < 0.2, "Refresh blocked the UI callback on network I/O"
    assert hold.entered.wait(1)
    assert not gui.rendered, "trace rendered before the held worker returned"
    assert hold.calls[0][0] != gui.owner
    hold.release.set()
    assert hold.finished.wait(1)
    gui.drain_until(lambda: "summary" in gui.rendered)
    assert "from-worker" in gui.rendered["events"]


def test_overlapping_trace_refresh_has_one_worker_and_only_latest_pending_request(gui_workflow, monkeypatch, held_gui_call):
    gui, root, _config = gui_workflow
    gui.vars["INFINI_PORT"] = _UiVar("5055")
    hold = held_gui_call(gui, "_fetch_trace_snapshot", lambda **kw: {"serverRoot": str(root), "cacheDir": kw["base_url"], "events": [{"message": kw["base_url"]}]}, timeout=3, first_only=True)

    gui.refresh_trace()
    assert hold.entered.wait(1)
    for port in range(5100, 5125):
        gui.vars["INFINI_PORT"].set(str(port))
        gui.refresh_trace()
    assert [call[2]["base_url"] for call in hold.calls] == ["http://127.0.0.1:5055"], "overlapping refresh spawned unbounded I/O workers"
    assert len(gui.jobs) == 1
    hold.release.set()
    gui.drain_until(lambda: "5124" in gui.rendered.get("summary", ""))
    assert [call[2]["base_url"] for call in hold.calls] == ["http://127.0.0.1:5055", "http://127.0.0.1:5124"]
    assert not gui.jobs


@pytest.mark.parametrize("action", ["cancel", "close"])
def test_trace_cancel_or_close_retires_held_and_pending_results(gui_workflow, monkeypatch, held_gui_call, action):
    gui, root, _config = gui_workflow
    hold = held_gui_call(gui, "_fetch_trace_snapshot", {"serverRoot": str(root), "cacheDir": "stale", "events": [{"message": "stale"}]}, timeout=3, first_only=False)

    gui.refresh_trace()
    assert hold.entered.wait(1)
    gui.refresh_trace()  # pending request must be retired as well
    if action == "close":
        gui.on_close()
        assert gui.destroyed
        assert not gui.jobs, "close retained a Tk after callback"
    else:
        cancel = getattr(gui, "cancel_trace_refresh", None)
        assert callable(cancel), "trace refresh has no cancellation action"
        cancel()
        assert "cancel" in gui.trace_status_var.get().lower()
    hold.release.set()
    assert hold.finished.wait(1)
    if action == "cancel":
        gui.drain_until(lambda: not gui.jobs)
    else:
        for callback in list(gui.jobs.values()):
            callback()
    assert not gui.rendered
    assert len(hold.calls) == 1
    assert not gui.__dict__.get("_gui_tasks", {})


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
    opened, requests = [], []
    monkeypatch.setattr(settings_trace_state.webbrowser, "open", lambda uri: opened.append(uri))
    monkeypatch.setattr(settings_trace_state.os, "startfile", lambda path: opened.append(Path(path).as_uri()), raising=False)
    monkeypatch.setattr(settings_trace_state.messagebox, "askyesno", lambda *a, **k: True)

    def read_gui_json(url, **kwargs):
        requests.append(str(url))
        assert online and "/trace_clear" in str(url)
        for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson"):
            settings_trace_state.trace_tools.clear_ndjson(selected / name)
        return {"ok": True, "cleared": [str(selected / name) for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson")]}

    def health(*args, **kwargs):
        if not online:
            raise ConnectionRefusedError("offline fixture")
        return {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000, "cacheDir": str(selected)}

    monkeypatch.setattr(gui, "_fetch_health_snapshot", health)
    monkeypatch.setattr(gui, "refresh_trace", lambda: None)
    monkeypatch.setattr(gui, "_read_gui_json", read_gui_json)
    gui.open_cache_folder()
    assert opened == [selected.as_uri()], "Open cache ignored selected launch root"
    gui.clear_trace_files()
    gui.drain_until(lambda: all((selected / name).read_bytes() == b"" for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson")))
    assert all(path.read_bytes() == data for path, data in preserved.items())
    assert len(requests) == (1 if online else 0)


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


@pytest.mark.parametrize("identity", ["foreign-health", "unknown-health", "foreign-trace", "changed-pid", "matching"])
def test_real_trace_http_checks_both_health_and_trace_identity_off_ui_thread(gui_workflow, monkeypatch, identity):
    gui, root, config = gui_workflow
    config.write_text("INFINI_CACHE_DIR=selected-cache\n", encoding="utf-8")
    cache = root / "selected-cache"
    cache.mkdir()
    (cache / "events.ndjson").write_text('{"message":"local-fixture"}\n', encoding="utf-8")
    pid = os.getpid() + 1000
    health = {"ok": True, "serverRoot": str(root), "pid": pid}
    trace = {"ok": True, "serverRoot": str(root), "pid": pid, "cacheDir": "online-cache", "events": [{"message": "online-fixture"}]}
    if identity == "foreign-health":
        health["serverRoot"] = str(root.parent / "foreign")
    elif identity == "unknown-health":
        health.pop("serverRoot")
    elif identity == "foreign-trace":
        trace["serverRoot"] = str(root.parent / "foreign")
    elif identity == "changed-pid":
        trace["pid"] = pid + 1
    with _gui_loopback_http({"/health": (200, health), "/trace.json": (200, trace)}) as (base, requests):
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        gui.refresh_trace()
        gui.drain_until(lambda: "summary" in gui.rendered)
    if identity == "matching":
        assert "online-fixture" in gui.rendered["events"]
        assert "local" not in gui.trace_status_var.get().lower()
    else:
        assert "local-fixture" in gui.rendered["events"], "accepted a foreign or replaced server's trace"
        assert "online-fixture" not in gui.rendered["events"]
    assert len(requests) == (1 if identity in {"foreign-health", "unknown-health"} else 2)


@pytest.fixture
def guarded_restart(gui_workflow, monkeypatch):
    """A saved launch with observable destructive actions, no real subprocess."""
    from infini_local.desktop import settings_gui_server_controls as controls

    gui, root, config = gui_workflow
    config.write_bytes(b"INFINI_IMAGE_BACKEND=off\n")
    actions = []
    original = config.read_bytes()
    monkeypatch.setattr(gui, "_wait_until_helper_stops", lambda *a, **k: True)
    monkeypatch.setattr(controls.subprocess, "Popen", lambda *a, **k: actions.append("spawn"))
    monkeypatch.setattr(controls.messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(gui, "_delayed_health_check", lambda *a, **k: None)
    return gui, root, config, original, actions


@pytest.mark.parametrize("activity", [
    {"active": 1, "waiting": 0, "accepting": True},
    {"active": 0, "waiting": 2, "accepting": True},
    {"active": 0, "waiting": 0, "accepting": False},
    None,
    {"active": "0", "waiting": 0, "accepting": True},
])
def test_safe_restart_does_not_save_shutdown_kill_or_spawn_busy_or_unknown_server(guarded_restart, monkeypatch, activity):
    gui, root, config, original, actions = guarded_restart


    gui.proc = OwnedProcess(actions)
    snap = {"ok": True, "serverRoot": str(root), "pid": gui.proc.pid}
    if activity is not None:
        snap["generationActivity"] = activity
    monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda *a, **k: snap)
    monkeypatch.setattr(gui, "_try_http_shutdown_current_server", lambda *a, **k: actions.append("shutdown") or True)
    gui.start_server()
    gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}))
    assert not actions, "safe restart interrupted occupied or unverifiable generation"
    assert config.read_bytes() == original, "busy restart saved before admission guard"
    assert any(word in gui.status_var.get().lower() for word in ("busy", "unknown", "accepting", "refused"))


@pytest.mark.parametrize("shutdown_code", [409, 200])
def test_safe_restart_uses_atomic_shutdown_and_never_falls_through_to_process_kill(gui_workflow, monkeypatch, shutdown_code):
    from infini_local.desktop import settings_gui_server_controls as controls
    gui, root, config = gui_workflow
    config.write_bytes(b"INFINI_CACHE_DIR=saved-cache\nINFINI_IMAGE_BACKEND=off\n")
    original = config.read_bytes()
    actions = []
    pid = os.getpid() + 1000


    gui.proc = OwnedProcess(actions, pid=pid)
    idle = {"ok": True, "serverRoot": str(root), "pid": pid,
            "effectiveConfig": gui._proposed_effective_config(),
            "generationActivity": {"active": 0, "waiting": 0, "accepting": True}}
    stopped = [False]

    def health(_path):
        return (503, {"ok": False}) if stopped[0] else (200, idle)

    def shutdown(path):
        if shutdown_code == 409:
            return 409, {"ok": False, "status": "generator_busy", "generationActivity": {"active": 1, "waiting": 0, "accepting": True}}
        stopped[0] = True
        return 200, {"ok": True}

    # This test owns only acknowledgement -> launch, not a real helper lifetime.
    monkeypatch.setattr(gui, "_wait_until_helper_stops", lambda *a, **k: True)
    monkeypatch.setattr(gui, "_delayed_health_check", lambda *a, **k: None)
    monkeypatch.setattr(controls.messagebox, "showwarning", lambda *a, **k: None)
    def capture_launch(cmd, **kwargs):
        # Never retain inherited credentials in pytest assertion diagnostics.
        safe_env = {key: kwargs["env"].get(key) for key in ("INFINI_CACHE_DIR", "INFINI_IMAGE_BACKEND")}
        actions.append((cmd, {"cwd": kwargs["cwd"], "env": safe_env}))
        return OwnedProcess(actions, pid=pid)

    monkeypatch.setattr(controls.subprocess, "Popen", capture_launch)
    monkeypatch.setenv("INFINI_CACHE_DIR", "inherited-cache")
    with _gui_loopback_http({"/health": health, "/shutdown": shutdown}) as (base, requests):
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        gui.start_server()
        gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}), timeout=8)
    assert "terminate" not in actions and "kill" not in actions, "safe path bypassed atomic server refusal"
    assert any(path.startswith("/shutdown") for path in requests), "idle health alone is not an atomic restart guard"
    assert not any("force=1" in path for path in requests)
    if shutdown_code == 409:
        assert not actions
        assert config.read_bytes() == original
        assert "busy" in gui.status_var.get().lower()
    else:
        assert len(actions) == 1
        cmd, kwargs = actions[0]
        assert cmd[-1] == str(root / "server.py")
        assert kwargs["cwd"] == str(root)
        assert kwargs["env"]["INFINI_CACHE_DIR"] == "saved-cache"
        assert kwargs["env"]["INFINI_IMAGE_BACKEND"] == "off"
        assert "запущен" in gui.status_var.get()


@pytest.mark.parametrize("identity,projection,force", [
    pytest.param("foreign-root", "identity-not-reached", False, id="foreign-root"),
    pytest.param("caller-pid", "identity-not-reached", False, id="caller-pid"),
    pytest.param("matching", None, False, id="missing-projection"),
    pytest.param("matching", {"sdcppAutostart": "0"}, True, id="force-cannot-bypass-invalid-projection"),
])
def test_restart_refuses_unverified_identity_or_projection_before_shutdown_or_save(
    guarded_restart, monkeypatch, identity, projection, force,
):
    from infini_local.desktop import settings_gui_server_controls as controls

    gui, root, config, original, actions = guarded_restart
    snap = {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000,
            "generationActivity": {"active": 0, "waiting": 0, "accepting": True}}
    if identity == "foreign-root":
        snap["serverRoot"] = str(root.parent / "foreign")
    elif identity == "unknown-root":
        snap.pop("serverRoot")
    elif identity == "caller-pid":
        snap["pid"] = os.getpid()
    elif identity == "invalid-pid":
        snap["pid"] = "123"
    elif identity == "unrelated-service":
        snap = {"ok": True, "service": "unrelated"}
    elif projection is not None:
        snap["effectiveConfig"] = projection
    monkeypatch.setattr(controls.messagebox, "askyesno", lambda *a, **k: True)
    with _gui_loopback_http({"/health": (200, snap), "/shutdown": (200, {"ok": True})}) as (base, requests):
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        (gui.force_restart_server if force else gui.start_server)()
        gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}))
    assert requests == ["/health"], "unverified identity/projection admitted shutdown"
    assert not actions
    assert config.read_bytes() == original
    if identity == "matching":
        assert "projection" in gui.status_var.get().lower()


@pytest.mark.parametrize("confirmed,identity", [(False, "matching"), (True, "matching"), (True, "foreign"), (True, "caller")])
def test_force_restart_requires_confirmation_and_still_checks_root_and_caller_pid(guarded_restart, monkeypatch, confirmed, identity):
    from infini_local.desktop import settings_gui_server_controls as controls
    gui, root, config, original, actions = guarded_restart
    snap = {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000,
            "effectiveConfig": gui._proposed_effective_config(),
            "generationActivity": {"active": 1, "waiting": 1, "accepting": True}}
    if identity == "foreign":
        snap["serverRoot"] = str(root.parent / "foreign")
    if identity == "caller":
        snap["pid"] = os.getpid()
    confirmations = []

    def ask(*args, **kwargs):
        assert threading.get_ident() == gui.owner
        confirmations.append(args)
        return confirmed

    monkeypatch.setattr(controls.messagebox, "askyesno", ask)
    with _gui_loopback_http({"/health": (200, snap), "/shutdown": (200, {"ok": True})}) as (base, requests):
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        force = getattr(gui, "force_restart_server", None)
        assert callable(force), "Force restart is not a separate explicit action"
        force()
        gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}))
    assert len(confirmations) == 1
    if confirmed and identity == "matching":
        assert requests == ["/health", "/shutdown?force=1"]
        assert actions == ["spawn"]
    else:
        assert requests == (["/health"] if confirmed else [])
        assert not actions
        assert config.read_bytes() == original


@pytest.mark.parametrize("action", [
    pytest.param("start_server", id="restart-busy"),
    pytest.param("stop_server", id="stop-busy"),
])
def test_server_actions_are_busy_aware_without_direct_terminate(gui_workflow, monkeypatch, action):
    gui, root, _config = gui_workflow
    actions = []
    gui.proc = OwnedProcess(actions)
    monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda *a, **k: {
        "ok": True, "serverRoot": str(root), "pid": gui.proc.pid,
        "generationActivity": {"active": 1, "waiting": 0, "accepting": True}})
    monkeypatch.setattr(gui, "_try_http_shutdown_current_server", lambda *a, **k: actions.append("shutdown") or (True, ""))
    getattr(gui, action)()
    gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}))
    assert not actions
    assert "busy" in gui.status_var.get().lower()


class _TrackedUiVar(_UiVar):
    def __init__(self, value=""):
        super().__init__(value)
        self.callbacks = []

    def trace_add(self, mode, callback):
        self.callbacks.append(callback)

    def set(self, value):
        super().set(value)
        for callback in self.callbacks:
            callback()


def test_setting_edits_create_custom_without_writing_saved_config(gui_workflow):
    gui, _root, config = gui_workflow
    config.write_text("INFINI_CODEX_IMAGE_QUALITY=medium\n", encoding="utf-8")
    before = config.read_bytes()
    gui.vars["INFINI_CODEX_IMAGE_QUALITY"] = _TrackedUiVar("medium")
    gui.preset_var = _UiVar("Мой: Обычный")
    gui._install_profile_tracking()
    gui.vars["INFINI_CODEX_IMAGE_QUALITY"].set("high")
    assert gui.preset_var.get() == "Custom"
    assert config.read_bytes() == before
    gui.vars["INFINI_CODEX_IMAGE_QUALITY"].set("medium")
    assert gui.preset_var.get() == "Мой: Обычный"


def test_gui_saves_named_profile_separately_and_restores_exact_settings(gui_workflow, monkeypatch):
    from infini_local.desktop.settings_env import load_user_presets
    from infini_local.desktop import settings_gui_trace_state
    gui, _root, config = gui_workflow
    config.write_text("INFINI_MANUAL_KNOB=disk\n", encoding="utf-8")
    before = config.read_bytes()
    gui.data["INFINI_MANUAL_KNOB"] = "keep"
    gui.vars["INFINI_PROMPT_STYLE"] = _TrackedUiVar("Terraria Like")
    gui.vars["INFINI_CODEX_IMAGE_QUALITY"] = _TrackedUiVar("high")
    gui.vars["INFINI_LLM_REASONING_MAX_TOKENS"] = _TrackedUiVar("7500")
    gui.vars["INFINI_OPENROUTER_API_KEY"] = _TrackedUiVar("test-only-credential")
    gui.preset_var = _UiVar("Custom")
    gui.user_presets = {}
    from types import SimpleNamespace
    gui.preset_combo = SimpleNamespace(configure=lambda **kwargs: None)
    gui._refresh_visibility = lambda: None
    gui._install_profile_tracking()
    monkeypatch.setattr(settings_gui_trace_state.simpledialog, "askstring", lambda *args, **kwargs: "Мой GPU")
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
    assert settings_gui.SettingsGui._pipeline_preset_from_config(
        {**profiles["Мой GPU"], "INFINI_GUI_PIPELINE_PRESET": "Мой: Мой GPU"}, profiles
    ) == "Мой: Мой GPU"
    gui.save()
    assert settings_gui.parse_env(config)["INFINI_PROMPT_STYLE"] == "Terraria Like"


def test_simple_view_keeps_active_basics_and_preserves_hidden_values():
    from types import SimpleNamespace
    calls = {}
    fields = {key: [object()] for key in ("INFINI_PROMPT_STYLE", "INFINI_CODEX_IMAGE_MODEL", "INFINI_SDCPP_MODEL", "INFINI_LLM_REASONING_MAX_TOKENS")}
    gui = SimpleNamespace(advanced_var=_UiVar(False), field_widgets=fields, field_hint_labels={},
                          field_disabled_reasons={"INFINI_SDCPP_MODEL": "Другой backend"}, _ui_sections=[])
    gui._set_packed_visible = lambda widget, visible: calls.update({widget: visible})
    settings_gui.SettingsGui._apply_view_mode(gui)
    assert calls[fields["INFINI_PROMPT_STYLE"][0]] is True
    assert calls[fields["INFINI_CODEX_IMAGE_MODEL"][0]] is True
    assert calls[fields["INFINI_SDCPP_MODEL"][0]] is False
    assert calls[fields["INFINI_LLM_REASONING_MAX_TOKENS"][0]] is False
    gui.advanced_var.set(True)
    settings_gui.SettingsGui._apply_view_mode(gui)
    assert all(calls[row[0]] for row in fields.values())


def test_codex_settings_do_not_display_an_unrelated_flux_preset():
    data = dict(settings_schema.DEFAULTS)
    data.update({"INFINI_GUI_PIPELINE_PRESET": "OpenAI-compatible + FLUX.2 Klein 4B hybrid",
                 "INFINI_LLM_PROVIDER": "openai_codex", "INFINI_IMAGE_BACKEND": "openai_codex"})
    assert settings_gui.SettingsGui._pipeline_preset_from_config(data) == "Custom"


def test_static_hover_help_does_not_replace_runtime_status(monkeypatch):
    from infini_local.desktop import settings_gui_ui as ui
    bindings = []
    class Widget:
        def bind(self, *args, **kwargs):
            bindings.append((args, kwargs))
    monkeypatch.setattr(ui, "ToolTip", lambda *args: None)
    gui = object.__new__(settings_gui.SettingsGui)
    gui.status_var = _UiVar("Server failed: useful diagnostic")
    gui._attach_static_help(Widget(), "Profile help\n" + "x" * 2000)
    for args, _kwargs in bindings:
        if args[0] == "<Enter>":
            args[1](None)
    assert gui.status_var.get() == "Server failed: useful diagnostic"


def test_loopback_gui_health_bypasses_system_proxy(monkeypatch):
    from infini_local.desktop import settings_gui_server_controls as controls
    import urllib.request
    with _gui_loopback_http({"/health": (200, {"ok": True})}) as (base, requests):
        with _gui_loopback_http({"/health": (200, {"route": "proxy"})}) as (proxy, proxy_requests):
            monkeypatch.setattr(urllib.request, "getproxies", lambda: {"http": proxy})
            monkeypatch.setattr(urllib.request, "proxy_bypass", lambda host: False)
            assert controls.SettingsGuiServerControlsMixin._read_gui_json(base + "/health", 2) == {"ok": True}
            assert requests == ["/health"]
            assert not proxy_requests
            assert controls.SettingsGuiServerControlsMixin._read_gui_json("http://provider.invalid/health", 2) == {"route": "proxy"}
            assert proxy_requests == ["http://provider.invalid/health"]


@pytest.mark.parametrize("owned", [False, True])
def test_start_on_refused_port_only_launches_when_no_owned_process_is_running(gui_workflow, monkeypatch, owned):
    from infini_local.desktop import settings_gui_server_controls as controls
    import socket
    gui, root, _config = gui_workflow
    calls = []

    gui.proc = OwnedProcess() if owned else None
    monkeypatch.setattr(controls.subprocess, "Popen", lambda *a, **k: calls.append("spawn") or OwnedProcess())
    # Reserve then close one ephemeral loopback port; no application is started.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    gui.vars["INFINI_PORT"] = _UiVar(str(port))
    gui.start_server()
    gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}))
    assert calls == ([] if owned else ["spawn"])


def test_overlapping_server_actions_do_not_queue_extra_shutdowns_or_block_ui(gui_workflow, monkeypatch, held_gui_call):
    gui, root, _config = gui_workflow
    hold = held_gui_call(gui, "_fetch_health_snapshot", {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000, "generationActivity": {"active": 1, "waiting": 0, "accepting": True}}, timeout=3, first_only=False)

    before = time.monotonic()
    gui.start_server()
    assert time.monotonic() - before < 0.2
    assert hold.entered.wait(1)
    for _ in range(25):
        gui.start_server()
    hold.release.set()
    assert hold.finished.wait(1)
    gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}))
    assert len(hold.calls) == 1, "repeated Start queued another restart after the initial guard"
    assert not gui.jobs


@pytest.mark.parametrize("failure,expected", [
    pytest.param("http", False, id="http-error-not-free"),
    pytest.param("timeout", False, id="timeout-not-free"),
    pytest.param("refused", True, id="refusal-is-free"),
])
def test_shutdown_wait_does_not_treat_http_error_or_timeout_as_port_free(gui_workflow, monkeypatch, failure, expected):
    gui, _root, _config = gui_workflow
    if failure == "http":
        with _gui_loopback_http({"/health": (503, {"ok": False})}) as (base, requests):
            assert gui._wait_until_helper_stops(timeout=0.1, base_url=base) is expected
            assert requests == ["/health"]
    else:
        error = TimeoutError if failure == "timeout" else ConnectionRefusedError
        monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda *a, **k: (_ for _ in ()).throw(error()))
        assert gui._wait_until_helper_stops(timeout=0.1, base_url="http://127.0.0.1:1") is expected


def _configure_applied_fixture(gui, root, config):
    config.write_text("\n".join((
        "INFINI_CACHE_DIR=selected-cache", "INFINI_WORLD_RECIPES_DIR=selected-worlds",
        "INFINI_IMAGE_BACKEND=off", "INFINI_LLM_PROVIDER=openrouter",
        "INFINI_OPENROUTER_MODEL=Provider/Model", "INFINI_OPENROUTER_PROVIDER=Exact-Slug",
        "INFINI_SDCPP_SERVER_AUTOSTART=0", "INFINI_OPENROUTER_API_KEY=FAKE-SAVED-SECRET-CANARY",
    )) + "\n", encoding="utf-8")
    return {"cacheDir": str((root / "selected-cache").resolve()),
            "worldRecipesDir": str((root / "selected-worlds").resolve()),
            "imageBackend": "off", "llmProvider": "openrouter", "llmModel": "Provider/Model",
            "openrouterProvider": "Exact-Slug", "sdcppAutostart": False}


@pytest.fixture
def applied_gui(gui_workflow):
    gui, root, config = gui_workflow
    effective = _configure_applied_fixture(gui, root, config)
    return gui, root, config, effective


def test_applied_config_health_is_async_partial_nonsecret_and_main_thread_only(applied_gui, monkeypatch, held_gui_call):
    gui, root, config, effective = applied_gui
    hold = held_gui_call(gui, "_fetch_health_snapshot", {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000, "effectiveConfig": {**effective, "unrelatedSecret": "FAKE-HEALTH-SECRET-CANARY"}, "llmAuth": {"secret": "FAKE-AUTH-SECRET-CANARY"}}, timeout=2, first_only=False)

    before = time.monotonic()
    gui._delayed_health_check()
    assert time.monotonic() - before < 0.2, "health confirmation blocked the UI callback"
    assert hold.entered.wait(1)
    hold.release.set()
    gui.drain_until(lambda: "matches" in gui.applied_config_var.get().lower())
    assert len(hold.calls) == 1 and hold.calls[0][0] != gui.owner
    feedback = gui.applied_config_var.get()
    assert "partial" in feedback.lower()
    assert "secret" in feedback.lower()
    assert "CANARY" not in feedback
    assert "CANARY" not in gui.status_var.get()
    assert "CANARY" not in repr(gui.__dict__.get("_applied_config_ack", {}))


@pytest.mark.parametrize("changed", ["pin-after-save", "pin-during-health", "missing-projection", "foreign-root"])
def test_applied_feedback_never_confirms_unsaved_or_unacknowledged_launch_changes(applied_gui, monkeypatch, changed):
    gui, root, config, effective = applied_gui
    entered, release = threading.Event(), threading.Event()
    def health(*args, **kwargs):
        entered.set()
        if changed == "pin-during-health":
            assert release.wait(2)
        snap = {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000, "effectiveConfig": effective}
        if changed == "missing-projection":
            snap.pop("effectiveConfig")
        if changed == "foreign-root":
            snap["serverRoot"] = str(root.parent / "foreign")
        return snap
    monkeypatch.setattr(gui, "_fetch_health_snapshot", health)
    try:
        gui._delayed_health_check()
        assert entered.wait(1)
        if changed == "pin-during-health":
            gui.vars["INFINI_OPENROUTER_PROVIDER"] = _UiVar("exact-slug")  # case is significant
        release.set()
        gui.drain_until(lambda: "health-config" not in gui.__dict__.get("_gui_tasks", {}))
        if changed == "pin-after-save":
            assert "matches" in gui.applied_config_var.get().lower()
            gui.vars["INFINI_OPENROUTER_PROVIDER"] = _UiVar("exact-slug")
            gui.save()
        text = gui.applied_config_var.get().lower()
        assert "matches" not in text, "stale health acknowledgement hid a new launch mismatch"
        if changed.startswith("pin"):
            assert "openrouterprovider" in text
            assert "restart" in text
        else:
            assert "unconfirmed" in text
        assert "partial" in text
        assert "CANARY" not in gui.applied_config_var.get()
    finally:
        release.set()


@pytest.mark.parametrize("linked_name", ["prompt_trace.ndjson", "prompt_trace.ndjson.lock"])
def test_offline_clear_refuses_symlinked_trace_or_lock_before_touching_any_cache_bytes(gui_workflow, monkeypatch, linked_name):
    gui, root, _config = gui_workflow
    cache = root / "cache"
    cache.mkdir()
    for name in ("events.ndjson", "prompt_trace.ndjson", "pipeline_trace.ndjson"):
        (cache / name).write_bytes(b'{"keep":true}\n')
    foreign = root.parent / "foreign-sprite.png"
    foreign.write_bytes(b"preserved-foreign-PNG")
    linked = cache / linked_name
    linked.unlink(missing_ok=True)
    linked.symlink_to(foreign)
    originals = {path: path.read_bytes() for path in (foreign, cache / "events.ndjson", cache / "pipeline_trace.ndjson")}
    monkeypatch.setattr(settings_trace_state.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda *a, **k: (_ for _ in ()).throw(ConnectionRefusedError()))
    monkeypatch.setattr(gui, "refresh_trace", lambda: None)
    gui.clear_trace_files()
    gui.drain_until(lambda: "trace-clear" not in gui.__dict__.get("_gui_tasks", {}))
    assert all(path.read_bytes() == value for path, value in originals.items()), "clear followed a trace/lock symlink or partially truncated the selected cache"
    assert "refused" in gui.trace_status_var.get().lower()


@pytest.mark.parametrize("identity", ["missing-pid", "invalid-pid", "caller-pid", "different-owned-pid"])
def test_applied_config_never_acknowledges_an_unverified_or_other_owned_process(applied_gui, monkeypatch, identity):
    gui, root, config, effective = applied_gui
    pid = os.getpid() + 1000

    gui.proc = OwnedProcess(pid=pid)
    snap = {"ok": True, "serverRoot": str(root), "pid": pid, "effectiveConfig": effective}
    if identity == "missing-pid":
        snap.pop("pid")
    elif identity == "invalid-pid":
        snap["pid"] = str(pid)
    elif identity == "caller-pid":
        snap["pid"] = os.getpid()
    else:
        snap["pid"] = pid + 1
    monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda *a, **k: snap)
    gui._delayed_health_check()
    gui.drain_until(lambda: "health-config" not in gui.__dict__.get("_gui_tasks", {}))
    assert "unconfirmed" in gui.applied_config_var.get().lower()
    assert gui.__dict__.get("_applied_config_ack") is None


def test_successful_safe_stop_retires_runtime_config_ack(applied_gui, monkeypatch):
    gui, root, config, effective = applied_gui
    gui._applied_config_ack = {"baseUrl": gui._server_base_url(), "pid": os.getpid() + 1000, "effectiveConfig": effective}
    gui._update_applied_config_feedback()
    assert "matches" in gui.applied_config_var.get().lower()
    health = {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000, "effectiveConfig": effective,
              "generationActivity": {"active": 0, "waiting": 0, "accepting": True}}
    monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda *a, **k: health)
    monkeypatch.setattr(gui, "_try_http_shutdown_current_server", lambda *a, **k: (True, ""))
    monkeypatch.setattr(gui, "_wait_until_helper_stops", lambda *a, **k: True)
    gui.stop_server()
    gui.drain_until(lambda: "server-action" not in gui.__dict__.get("_gui_tasks", {}))
    assert gui.__dict__.get("_applied_config_ack") is None
    assert "matches" not in gui.applied_config_var.get().lower()
    assert "stopped" in gui.status_var.get().lower()


@pytest.mark.parametrize("provider,secret,model,expected", [
    pytest.param("", "", "Provider/Model", "local", id="implicit-no-credential"),
    pytest.param("", "FAKE-INFER-CANARY", "auto", "local", id="implicit-auto-model"),
    pytest.param("", "FAKE-INFER-CANARY", "Provider/Model", "openrouter", id="implicit-configured-router"),
    pytest.param("", "", None, "local", id="empty-alias"),
    pytest.param("or", "", None, "openrouter", id="or-alias"),
    pytest.param("openai-compat", "", None, "openai_compat", id="compat-alias"),
    pytest.param("lm_studio", "", None, "local", id="lm-studio-alias"),
])
def test_gui_main_provider_projection_preserves_aliases_and_never_retains_secret(
    gui_workflow, monkeypatch, provider, secret, model, expected,
):
    gui, _root, config = gui_workflow
    values = {"INFINI_LLM_PROVIDER": provider}
    if model is not None:
        values.update(INFINI_OPENROUTER_API_KEY=secret, INFINI_OPENROUTER_MODEL=model)
    config.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    # Do not import runtime/server or evaluate inherited credentials.
    monkeypatch.delenv("INFINI_OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    projection = gui._proposed_effective_config()
    assert projection["llmProvider"] == expected
    assert "CANARY" not in repr(projection)


@pytest.mark.skipif(os.name == "nt", reason="POSIX roots are case-sensitive; native Windows names are not")
def test_gui_root_identity_preserves_posix_case_and_does_not_accept_different_copy(gui_workflow):
    gui, root, _config = gui_workflow
    assert gui._health_matches_this_gui({"serverRoot": str(root)})
    assert not gui._health_matches_this_gui({"serverRoot": str(root.with_name(root.name.swapcase()))})
    assert gui._norm_path_for_compare(r"C:\\Copies\\LocalGenerator") == gui._norm_path_for_compare("c:/copies/localgenerator")


@pytest.mark.parametrize("reply", [{"ok": False}, {"ok": True}, {"ok": True, "cleared": []}])
def test_trace_clear_never_reports_partial_server_ack_as_success(gui_workflow, monkeypatch, reply):
    gui, root, _config = gui_workflow
    cache = root / "cache"
    health = {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000, "cacheDir": str(cache)}
    monkeypatch.setattr(settings_trace_state.messagebox, "askyesno", lambda *a, **k: True)
    refreshes = []
    monkeypatch.setattr(gui, "refresh_trace", lambda: refreshes.append(True))
    with _gui_loopback_http({"/health": (200, health), "/trace_clear": (200, reply)}) as (base, requests):
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        gui.clear_trace_files()
        gui.drain_until(lambda: "trace-clear" not in gui.__dict__.get("_gui_tasks", {}))
    assert requests == ["/health", "/trace_clear"]
    assert "unavailable" in gui.trace_status_var.get().lower()
    assert not refreshes


@pytest.mark.parametrize("health_kind", ["forbidden", "timeout", "foreign", "different-cache", "missing-root"])
def test_trace_clear_refuses_unknown_or_different_live_target_instead_of_local_fallback(gui_workflow, monkeypatch, health_kind):
    gui, root, config = gui_workflow
    if health_kind != "missing-root":
        config.write_text("INFINI_CACHE_DIR=selected-cache\n", encoding="utf-8")
    cache = root / ("cache" if health_kind == "missing-root" else "selected-cache")
    cache.mkdir()
    trace_file = cache / "events.ndjson"
    trace_file.write_bytes(b'{"preserve":true}\n')
    monkeypatch.setattr(settings_trace_state.messagebox, "askyesno", lambda *a, **k: True)
    if health_kind == "timeout":
        monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    health = {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000,
              "cacheDir": str(root / "other-live-cache")}
    if health_kind == "foreign":
        health["serverRoot"] = str(root.parent / "foreign")
    elif health_kind == "missing-root":
        health.pop("serverRoot")
        health.pop("cacheDir")
    with _gui_loopback_http({"/health": (403 if health_kind == "forbidden" else 200, health),
                            "/trace_clear": (200, {"ok": True})}) as (base, requests):
        gui.vars["INFINI_PORT"] = _UiVar(base.rsplit(":", 1)[1])
        gui.clear_trace_files()
        gui.drain_until(lambda: "trace-clear" not in gui.__dict__.get("_gui_tasks", {}))
    assert requests == ([] if health_kind == "timeout" else ["/health"])
    assert trace_file.read_bytes() == b'{"preserve":true}\n', "health refusal/unverifiable liveness cleared local cache"
    assert any(word in gui.trace_status_var.get().lower() for word in ("refused", "unavailable"))
    if health_kind == "missing-root":
        assert "refused" in gui.trace_status_var.get().lower()


def test_spawn_retires_old_applied_ack_and_schedules_main_loop_health_confirmation(applied_gui, monkeypatch):
    from infini_local.desktop import settings_gui_server_controls as controls
    gui, root, config, effective = applied_gui
    gui._applied_config_ack = {"baseUrl": gui._server_base_url(), "pid": 987654, "effectiveConfig": effective}
    gui._update_applied_config_feedback()
    assert "matches" in gui.applied_config_var.get().lower()

    calls = []
    monkeypatch.setattr(controls.subprocess, "Popen", lambda *a, **k: OwnedProcess())
    monkeypatch.setattr(gui, "_delayed_health_check", lambda: calls.append(threading.get_ident()))
    gui._start_server_after_guard()
    assert gui.__dict__.get("_applied_config_ack") is None, "new process retained old PID's config acknowledgement"
    assert "matches" not in gui.applied_config_var.get().lower()
    assert gui.jobs, "launch never schedules asynchronous runtime acknowledgement"
    gui.drain_until(lambda: bool(calls))
    assert calls == [gui.owner]


def test_close_cancels_scheduled_post_launch_health_callback(gui_workflow, monkeypatch):
    from infini_local.desktop import settings_gui_server_controls as controls
    gui, _root, _config = gui_workflow

    monkeypatch.setattr(controls.subprocess, "Popen", lambda *a, **k: OwnedProcess())
    gui._start_server_after_guard()
    assert gui.jobs, "native health callback was never scheduled"
    gui.on_close()
    assert not gui.jobs, "post-launch health after callback survived destroyed GUI"


@pytest.mark.parametrize("provider,model_key,model_value,inherited_key,inherited_model,expected_model", [
    ("local", "INFINI_LMSTUDIO_MODEL", "", "OPENAI_MODEL", "Inherited/Model", "Inherited/Model"),
    ("openrouter", "INFINI_OPENROUTER_MODEL", "", "OPENROUTER_MODEL", "Inherited/Model", "Inherited/Model"),
    ("openai_compat", "INFINI_OPENAI_COMPAT_MODEL", "", "OPENAI_MODEL", "Inherited/Model", "Inherited/Model"),
    ("local", "INFINI_LMSTUDIO_MODEL", "", "OPENAI_MODEL", "", "auto"),
    ("openai_codex", "INFINI_CODEX_LLM_MODEL", "", "OPENAI_MODEL", "Inherited/Model", ""),
])
def test_applied_projection_matches_runtime_main_model_fallback_and_inactive_pin(gui_workflow, monkeypatch, provider, model_key, model_value, inherited_key, inherited_model, expected_model):
    gui, _root, config = gui_workflow
    config.write_text(f"INFINI_LLM_PROVIDER={provider}\n{model_key}={model_value}\n"
                      "INFINI_OPENROUTER_PROVIDER=Exact-Slug\nINFINI_IMAGE_BACKEND=off\n", encoding="utf-8")
    monkeypatch.setenv(inherited_key, inherited_model)
    projected = gui._proposed_effective_config()
    assert projected["llmProvider"] == provider
    assert projected["llmModel"] == expected_model
    assert projected["openrouterProvider"] == ("Exact-Slug" if provider == "openrouter" else "")


@pytest.mark.parametrize("started,expected", [(None, "unknown"), (False, "not started"), (True, "started")])
def test_health_activity_rows_keep_backend_identity_and_network_tristate(gui_workflow, monkeypatch, started, expected):
    gui, root, _config = gui_workflow
    gui.activity_var = _UiVar()
    snap = {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000,
            "effectiveConfig": {"cacheDir": "c", "worldRecipesDir": "w", "imageBackend": "off",
                "llmProvider": "local", "llmModel": "auto", "openrouterProvider": "", "sdcppAutostart": False},
            "generationActivity": {"active": 1, "waiting": 0, "accepting": True, "requestsOmitted": 2,
                "requests": [{"requestId": "a" * 32, "profileId": "llm_2", "stage": "05_visual_director",
                    "elapsedSeconds": 12.5, "stageElapsedSeconds": 3.25, "waitReason": "profile_slot",
                    "networkStarted": started, "active": True, "secret": "DO_NOT_DISPLAY"}]}}
    monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda **kwargs: snap)
    gui._delayed_health_check()
    gui.drain_until(lambda: "health-config" not in gui.__dict__.get("_gui_tasks", {}))
    text = gui.activity_var.get()
    for value in ("a" * 32, "llm_2", "05_visual_director", "12.5", "3.25", "profile_slot", "network=" + expected, "2 rows omitted"):
        assert value in text
    assert "DO_NOT_DISPLAY" not in text and "Hearth" not in text and "lane" not in text.lower()
    assert snap["generationActivity"]["requests"][0]["networkStarted"] is started


def test_health_activity_result_cannot_cross_changed_endpoint(gui_workflow, monkeypatch):
    gui, root, _config = gui_workflow
    gui.activity_var = _UiVar("Original")
    gui.vars["INFINI_PORT"] = _UiVar("5055")
    snap = {"ok": True, "serverRoot": str(root), "pid": os.getpid() + 1000,
            "effectiveConfig": {"cacheDir": "c", "worldRecipesDir": "w", "imageBackend": "off",
                "llmProvider": "local", "llmModel": "auto", "openrouterProvider": "", "sdcppAutostart": False},
            "generationActivity": {"active": 3, "waiting": 0, "accepting": True, "requests": []}}
    monkeypatch.setattr(gui, "_fetch_health_snapshot", lambda **kwargs: snap)
    gui._delayed_health_check()
    gui.vars["INFINI_PORT"].set("5056")
    gui.drain_until(lambda: "health-config" not in gui.__dict__.get("_gui_tasks", {}))
    assert "active=3" not in gui.activity_var.get(), "old endpoint result presented on edited target"


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


@pytest.mark.parametrize("endpoint", ["health", "shutdown"])
def test_gui_http_enforces_total_deadline_for_continuous_trickle(gui_workflow, endpoint):
    gui, _root, _config = gui_workflow
    class Trickle(BaseHTTPRequestHandler):
        def do_GET(self):
            # Every idle gap is shorter than the socket timeout.
            write_json_response(self, {"ok": True}, raw_body='{"ok":true}', trickle=0.03)

        def log_message(self, *_args):
            pass

    with loopback_server(Trickle) as server:
        base_url = f"http://127.0.0.1:{server.server_port}"
        if endpoint == "health":
            with pytest.raises(TimeoutError):
                gui._fetch_health_snapshot(timeout=0.1, base_url=base_url)
        else:
            assert gui._try_http_shutdown_current_server(timeout=0.1, base_url=base_url)[0] is False


class _SpriteGuiHarness(settings_trace_state.SettingsGuiTraceStateMixin):
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


@pytest.mark.parametrize("filter_name,expected", [("", "box"), ("box", "box"), ("bilinear", "bilinear"), ("bicubic", "bicubic"), ("lanczos", "lanczos")])
def test_apply_pipeline_preserves_explicit_resize_choices(filter_name, expected):
    gui = _SpriteGuiHarness(INFINI_SPRITE_DOWNSCALE_FILTER=filter_name, INFINI_SPRITE_PREMULTIPLIED_RESIZE="0")
    gui.apply_preset()
    assert gui.vars["INFINI_SPRITE_DOWNSCALE_FILTER"].get() == expected
    assert gui.vars["INFINI_SPRITE_PREMULTIPLIED_RESIZE"].get() == "0"


@pytest.mark.parametrize("remove_bg,bg_color,bg_mode,backend,keyer", [
    ("1", "transparent", "sprite_keyer", "openai_codex", False),
    ("0", "transparent", "sprite_keyer", "image_api", False),
    ("0", "magenta", "sprite_keyer", "image_api", False),
    ("1", "magenta", "off", "image_api", False),
    ("1", "magenta", "none", "image_api", False),
    ("1", "magenta", "sprite_keyer", "sdcpp", True),
    ("1", "green", "chroma", "sdcpp", True),
    ("1", "greenscreen", "legacy-keyer", "sdcpp", True),
    ("1", "unsupported-token", "sprite_keyer", "sdcpp", True),
    ("1", "transparent", "sprite_keyer", "off", False),
])
def test_gui_native_alpha_disables_only_local_keyer_controls(remove_bg, bg_color, bg_mode, backend, keyer):
    gui = _SpriteGuiHarness(INFINI_REMOVE_BG=remove_bg, INFINI_BG_COLOR=bg_color,
                            INFINI_BG_REMOVE_MODE=bg_mode, INFINI_IMAGE_BACKEND=backend)
    before = {key: var.get() for key, var in gui.vars.items()}
    gui._refresh_visibility()
    for key in ("INFINI_CHROMA_TOLERANCE", "INFINI_SPRITE_KEYER_SPILL_RADIUS",
                "INFINI_SPRITE_KEYER_RESIDUE_STEPS", "INFINI_SPRITE_CHROMA_DEFRINGE"):
        enabled, reason = gui.field_state[key]
        assert enabled is keyer, key
        if backend != "off" and not keyer:
            assert "Модель запрашивается с alpha; локальный keyer не применяется" in reason
    assert gui.field_state["INFINI_ALPHA_THRESHOLD"][0] is (backend != "off")
    assert gui.field_state["INFINI_BG_COLOR"][0] is (backend != "off")
    assert gui.field_state["INFINI_BG_REMOVE_MODE"][0] is keyer
    if bg_color == "transparent":
        assert gui.field_state["INFINI_REMOVE_BG"][0] is False
    for key in ("INFINI_BG_COLOR", "INFINI_BG_REMOVE_MODE", "INFINI_REMOVE_BG", "INFINI_SPRITE_DOWNSCALE_FILTER"):
        assert gui.vars[key].get() == before[key], "visibility rewrote an explicit choice"


def test_gui_resize_reset_restores_box_without_changing_background():
    gui = _SpriteGuiHarness(INFINI_SPRITE_DOWNSCALE_FILTER="lanczos", INFINI_SPRITE_PREMULTIPLIED_RESIZE="0", INFINI_BG_COLOR="transparent")
    reset = getattr(settings_gui.SettingsGui, "reset_sprite_resize", None)
    assert callable(reset), "GUI has no explicit base resize reset"
    reset(gui)
    assert gui.vars["INFINI_SPRITE_DOWNSCALE_FILTER"].get() == "box"
    assert gui.vars["INFINI_SPRITE_PREMULTIPLIED_RESIZE"].get() == "1"
    assert gui.vars["INFINI_BG_COLOR"].get() == "transparent"
