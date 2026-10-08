from __future__ import annotations

import importlib
import json

import pytest

from infini_local.desktop import settings_env, settings_schema, settings_gui, settings_gui_ui, settings_gui_trace_state
from infini_local.storage import trace_runtime, trace_tools


@pytest.mark.parametrize("stage", ["visual_director", "visual_repair", "vfx_director", "vfx_repair"])
@pytest.mark.parametrize("enabled", [True, False])
def test_real_director_seams_store_complete_response_and_request_without_semantic_changes(monkeypatch, tmp_path, stage, enabled):
    import copy
    from infini_local.pipelines import llm_authoring_pipeline as author, visual_generation_pipeline as visual
    from infini_local.core.runtime_authoring import compile_runtime_program
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", enabled)
    monkeypatch.setattr(author, "USE_LLM", True)
    captured = []
    raw = '{"note":"' + "ж" * 140000 + ' COMPLETE_RESPONSE_TAIL"}'
    def respond(request, **kwargs):
        captured.append(copy.deepcopy(request))
        return {"choices": [{"message": {"content": raw}}]}
    for owner in (author, visual):
        monkeypatch.setattr(owner, "llm_chat_json", respond)
        monkeypatch.setattr(owner, "resolve_llm_model", lambda: "offline-model")
    if stage.startswith("visual"):
        data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
        data.update(id="g_exact", recipeKey="r_exact")
        before = copy.deepcopy(data)
        kwargs = {"repair_errors": [{"path": "$.item.silhouette", "message": "required"}],
                  "previous": {"item": {"prompt": "frozen"}},
                  "repair_scope": {"itemMutable": True, "fieldPermissions": {"itemPaths": ["silhouette"]}}} if stage.endswith("repair") else {}
        result = visual._request_visual_kit(data, {}, {}, {}, {}, **kwargs)
        assert data == before
    else:
        keys = author.VFX_REPAIR_PROMPT_STATIC_KEYS if stage.endswith("repair") else author.VFX_PROMPT_STATIC_KEYS
        user = {**{key: {} for key in keys}, "item": {"id": "g_exact"}, "source": "exact\r\n " + "ж" * 140000 + " INPUT_TAIL"}
        before = copy.deepcopy(user)
        messages = [{"role": "system", "name": "vfx_repair_contract", "content": "exact contract"},
                    {"role": "user", "name": "vfx_repair_context", "content": json.dumps(user, ensure_ascii=False)}] if stage.endswith("repair") else None
        result = author.call_llm_vfx_director("exact contract", user, 123, 0.2, 5, messages=messages)
        assert user == before
    assert result == json.loads(raw)
    if enabled:
        artifacts = list((tmp_path / "stage_requests").glob("*.json"))
        assert len(artifacts) == 1
        artifact = json.loads(artifacts[0].read_bytes())
        assert artifact["stage"] == stage and artifact["messages"] == captured[0]["messages"]
        rows = trace_tools.tail_ndjson(trace_runtime.PROMPT_TRACE_FILE, 10)
        assert any(row.get("response") == raw for row in rows), "no response tail may disappear"
        assert any(row.get("prompt") == captured[0]["messages"][1]["content"] for row in rows)
    else:
        assert list(tmp_path.iterdir()) == []


def test_gui_displays_full_stored_record_even_when_older_rows_are_not_in_tail(monkeypatch, tmp_path):
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", True)
    clean = "exact\r\n " + "ж" * 140000 + " GUI_RECORD_TAIL"
    for index in range(121):
        trace_runtime.trace_event("response", "offline", str(index), response=clean if index == 120 else "old")
    gui = _Gui(settings_schema.DEFAULTS)
    gui.trace_texts = {key: _Widget() for key in ("summary", "prompts", "pipeline", "events", "sdcpp", "failure")}
    snapshot = gui._load_local_trace_snapshot(cache=tmp_path)
    gui._render_trace_snapshot(snapshot)
    assert len(snapshot["promptTrace"]) == 120
    assert clean in gui.trace_texts["prompts"].content
    assert len(trace_tools.tail_ndjson(trace_runtime.PROMPT_TRACE_FILE, 200)) == 121


def test_fatal_off_redacts_before_concise_clipping(monkeypatch, tmp_path):
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", False)
    secret = "offline-opaque-credential-123456"
    monkeypatch.setenv("INFINI_OPENAI_COMPAT_API_KEY", secret)
    trace_runtime.log_event("error", "x" * 490 + secret)
    message = trace_tools.tail_ndjson(tmp_path / "events.ndjson", 1)[0]["message"]
    assert "offline" not in message and "[REDACTED]" in message


def test_failure_artifact_redacts_without_truncating_partial_diagnostic(monkeypatch, tmp_path):
    from infini_local.pipelines import generation_debug
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", True)
    monkeypatch.setattr(generation_debug, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(generation_debug, "LAST_COMBINE_FAILURE_FILE", tmp_path / "failure.json")
    monkeypatch.setattr(generation_debug, "_LAST_COMBINE_FAILURE", {})
    secret = "offline-opaque-credential-123456"
    monkeypatch.setenv("INFINI_OPENAI_COMPAT_API_KEY", secret)
    clean = "ж" * 70000 + " PARTIAL_TAIL"
    generation_debug.record_combine_failure("author", RuntimeError(secret), None, {"text": clean, "secret": secret}, [])
    persisted = json.loads((tmp_path / "failure.json").read_bytes())
    assert secret not in json.dumps(persisted, ensure_ascii=False)
    assert persisted["partialData"]["text"] == clean


def test_http_access_diagnostics_are_silent_off_and_redacted_on(monkeypatch, capsys):
    from test_provider_http_contract import boundary_handler
    handler, _capture = boundary_handler()
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", False)
    handler.log_message('"GET /health HTTP/1.1" %s', 200)
    assert capsys.readouterr().out == ""
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", True)
    secret = "offline-opaque-credential-123456"
    monkeypatch.setenv("INFINI_OPENAI_COMPAT_API_KEY", secret)
    handler.log_message('"GET /%s HTTP/1.1"', secret)
    printed = capsys.readouterr().out
    assert secret not in printed and "[REDACTED]" in printed


@pytest.mark.parametrize("enabled", [True, False])
def test_sdcpp_lifecycle_recording_obeys_logging_toggle_without_launching_backend(monkeypatch, tmp_path, enabled):
    from infini_local.services import sdcpp_service
    from infini_local.pipelines import image_backend_pipeline as backend
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", enabled)
    state = sdcpp_service.SdcppServerState()
    monkeypatch.setattr(backend, "SDCPP_SERVER_STATE", state)
    monkeypatch.setattr(backend, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(backend, "ROOT", tmp_path)
    monkeypatch.setattr(backend, "SDCPP_SERVER_AUTOSTART", True)
    monkeypatch.setattr(backend, "SDCPP_SERVER_SHOW_CONSOLE", False)
    monkeypatch.setattr(backend, "SDCPP_SERVER_LOG_FILE", "")
    monkeypatch.setattr(backend, "build_sdcpp_server_command", lambda: (["never-launch"], False))
    alive = iter([False, True])
    monkeypatch.setattr(backend, "sdcpp_server_is_alive", lambda: next(alive))
    monkeypatch.setattr(sdcpp_service, "install_cleanup_handlers", lambda *args: None)
    calls = []
    class Process:
        def poll(self):
            return None
    def spawn(*args, **kwargs):
        calls.append(kwargs)
        return Process()
    monkeypatch.setattr(sdcpp_service.subprocess, "Popen", spawn)
    assert backend.ensure_sdcpp_server() is True
    if enabled:
        assert (tmp_path / "sdcpp_server.log").exists()
        state.process._infini_log_handle.close()
    else:
        assert calls[0]["stdout"] == sdcpp_service.subprocess.DEVNULL
        assert calls[0]["stderr"] == sdcpp_service.subprocess.DEVNULL
        assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("saved", ["0", "1"])
def test_saved_gui_logging_choice_reaches_fresh_runtime_writer(monkeypatch, tmp_path, saved):
    import os
    import subprocess
    import sys
    from pathlib import Path
    config = tmp_path / "config.env"
    settings_env.write_env(config, {**settings_schema.DEFAULTS, "INFINI_TRACE_PROMPTS": saved})
    reloaded = settings_env.parse_env(config)
    env = {**os.environ, **reloaded, "INFINI_SKIP_CONFIG_FILE": "1", "INFINI_CACHE_DIR": str(tmp_path / "cache")}
    script = """
from infini_local.storage import trace_runtime as t
assert t.TRACE_PROMPTS_ENABLED is EXPECTED
t.trace_event('response', 'offline', 'exact', response='fresh runtime tail')
t.trace_stage_request('offline', 'join', {'messages': [{'role': 'user', 'content': 'fresh request'}]})
t.log_event('info', 'extra diagnostics')
""".replace("EXPECTED", "True" if saved == "1" else "False")
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    cache = tmp_path / "cache"
    assert (cache / "prompt_trace.ndjson").exists() is (saved == "1")
    assert (cache / "events.ndjson").exists() is (saved == "1")
    assert (cache / "stage_requests").exists() is (saved == "1")


def test_gui_trace_fetch_accepts_complete_large_record_not_bounded_preview(monkeypatch):
    from test_settings_gui_contract import _gui_loopback_http
    clean = "x" * (17 * 1024 * 1024) + " GUI_FULL_RECORD_TAIL"
    snapshot = {"ok": True, "pid": 123, "promptTrace": [{"response": clean}]}
    with _gui_loopback_http({"/trace.json": (200, snapshot)}) as (base, requests):
        gui = _Gui(settings_schema.DEFAULTS)
        gui._fetch_health_snapshot = lambda **kwargs: {"pid": 123}
        gui._health_matches_this_gui = lambda value: True
        gui._read_gui_json = settings_gui.SettingsGui._read_gui_json
        read = gui._fetch_trace_snapshot(base)
        assert read["promptTrace"][0]["response"] == clean
        assert requests == ["/trace.json"]


def test_full_failure_snapshots_are_archived_per_request_not_only_latest(monkeypatch, tmp_path):
    from infini_local.pipelines import generation_debug
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", True)
    monkeypatch.setattr(generation_debug, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(generation_debug, "LAST_COMBINE_FAILURE_FILE", tmp_path / "failure.json")
    monkeypatch.setattr(generation_debug, "_LAST_COMBINE_FAILURE", {})
    for index in range(2):
        generation_debug.record_combine_failure("author", RuntimeError(str(index)), None, {"text": "ж" * 70000, "index": index}, [])
    rows = trace_tools.tail_ndjson(trace_runtime.TRACE_FILE, 5)
    assert [row["payload"]["partialData"]["index"] for row in rows] == [0, 1]
    assert all(row["payload"]["partialData"]["text"] == "ж" * 70000 for row in rows)


def test_default_web_trace_displays_complete_record_payload(monkeypatch):
    from infini_local.web import trace_dashboard
    monkeypatch.setattr(trace_runtime, "TRACE_MAX_PROMPT_CHARS", 0)
    clean = "x" * 20000 + " WEB_RECORD_PAYLOAD_TAIL"
    rendered = trace_dashboard.render_trace_snapshot_html({"pipelineTrace": [{"payload": {"text": clean}}]}, app_version="test", trace_clip=trace_runtime._trace_clip)
    assert clean in rendered


def test_optional_event_payload_failure_never_interrupts_operation(monkeypatch, tmp_path):
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", True)
    cycle = {}
    cycle["loop"] = cycle
    trace_runtime.log_event("info", "cyclic optional metadata", cycle)
    class Unprintable:
        def __str__(self):
            raise ValueError("private implementation")
    trace_runtime.log_event("info", "unprintable optional metadata", Unprintable())


def test_stringified_optional_metadata_is_sanitized_before_storage(monkeypatch, tmp_path):
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", True)
    secret = "offline-opaque-credential-123456"
    monkeypatch.setenv("INFINI_OPENAI_COMPAT_API_KEY", secret)
    class Value:
        def __str__(self):
            return secret
    trace_runtime.log_event("info", "optional metadata", {"text": Value()})
    assert secret not in (tmp_path / "events.ndjson").read_text()


def test_unlimited_json_diagnostic_fallback_does_not_erase_non_json_string():
    cycle = []
    cycle.append(cycle)
    assert trace_tools.json_slim(cycle, 0) == str(cycle)


class _Var:
    def __init__(self, value=""):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


class _Widget:
    instances = []
    def __init__(self, *args, **kwargs):
        self.options = kwargs
        self.visible = True
        self.content = ""
        self.instances.append(self)
    def pack(self, **kwargs):
        pass
    def configure(self, **kwargs):
        self.options.update(kwargs)
    def delete(self, *args):
        self.content = ""
    def insert(self, index, content):
        self.content += content
    def invoke(self):
        var = self.options["variable"]
        var.set(self.options["offvalue"] if var.get() == self.options["onvalue"] else self.options["onvalue"])
        self.options["command"]()


class _Gui(settings_gui_ui.SettingsGuiUiMixin, settings_gui_trace_state.SettingsGuiTraceStateMixin):
    def __init__(self, data):
        self.data = data
        self.vars = {}
        self.text_widgets = {}
        self.field_widgets = {}
        self.field_hint_labels = {}
        self.field_disabled_reasons = {}
        self.advanced_var = _Var(False)
        self.radmin_enabled = _Var(False)
        self.preset_var = _Var("Custom")
        self.status_var = _Var()
        self.user_presets = {}
        self.trace_texts = {}
    def _var(self, key):
        var = _Var(self.data.get(key, settings_schema.DEFAULTS.get(key, "")))
        self.vars[key] = var
        return var
    def _card(self, *args, **kwargs):
        return _Widget()
    def row(self, parent, label, key, **kwargs):
        self._var(key)
    def _modern_button(self, *args, **kwargs):
        return _Widget()
    def _attach_static_help(self, *args):
        pass
    def _info_panel(self, *args, **kwargs):
        pass
    def _bg_of(self, *args):
        return "unused"
    def _register_field_widgets(self, key, widgets, hint, hint_label):
        self.field_widgets[key] = widgets
    def _set_packed_visible(self, widget, visible):
        widget.visible = visible
    def _refresh_visibility(self):
        self._apply_view_mode()
    def _lora_dir_from_file(self, *args):
        return ""
    def _radmin_status_text(self):
        return "offline"
    force_restart_server = apply_radmin_overlay = apply_local_overlay = autofill_radmin_url = copy_radmin_friend_guide = open_mp_connect_page = on_radmin_toggle = _attach_static_help


@pytest.mark.parametrize("saved", [None, "0"])
def test_recording_checkbox_save_reload_and_presets_respect_explicit_off(monkeypatch, tmp_path, saved):
    config = tmp_path / "config.env"
    if saved is not None:
        config.write_text("INFINI_TRACE_PROMPTS=" + saved + "\n")
    monkeypatch.setattr(settings_gui_trace_state, "CONFIG_PATH", config)
    for name in ("Frame", "Checkbutton", "Label"):
        monkeypatch.setattr(settings_gui_ui.ttk, name, _Widget)
    monkeypatch.setattr(settings_gui_ui.tk, "StringVar", _Var)
    _Widget.instances = []
    gui = _Gui(settings_env.parse_env(config))
    gui._build_general(_Widget())
    widgets = [widget for widget in _Widget.instances if widget.options.get("variable") is gui.vars["INFINI_TRACE_PROMPTS"]]
    assert len(widgets) == 1, "logging must be a checkbox, not an advanced-only combo"
    checkbox = widgets[0]
    assert checkbox.options["onvalue"] == "1" and checkbox.options["offvalue"] == "0"
    gui._apply_view_mode()
    assert checkbox.visible and gui.vars["INFINI_TRACE_PROMPTS"].get() == (saved or "1")
    if saved is None:
        checkbox.invoke()
    gui.save()
    assert settings_env.parse_env(config)["INFINI_TRACE_PROMPTS"] == "0"
    for preset in settings_schema.PRESETS:
        gui.preset_var.set(preset)
        gui.apply_preset()
        assert gui.vars["INFINI_TRACE_PROMPTS"].get() == "0", preset
    path = tmp_path / "profiles.json"
    gui.user_presets = settings_env.save_user_preset(path, "quiet", gui.collect())
    gui.vars["INFINI_TRACE_PROMPTS"].set("1")
    gui.user_presets = settings_env.load_user_presets(path)
    gui.preset_var.set(settings_env.USER_PRESET_PREFIX + "quiet")
    gui.apply_preset()
    gui.save()
    assert settings_env.parse_env(config)["INFINI_TRACE_PROMPTS"] == "0"


def _runtime_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(trace_runtime, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_FILE", tmp_path / "pipeline_trace.ndjson")
    monkeypatch.setattr(trace_runtime, "PROMPT_TRACE_FILE", tmp_path / "prompt_trace.ndjson")


def test_unset_runtime_and_gui_default_is_on_with_zero_unlimited_sentinel(monkeypatch, tmp_path):
    monkeypatch.delenv("INFINI_TRACE_PROMPTS", raising=False)
    monkeypatch.delenv("INFINI_TRACE_MAX_PROMPT_CHARS", raising=False)
    try:
        importlib.reload(trace_runtime)
        assert trace_runtime.TRACE_PROMPTS_ENABLED is True
        assert trace_runtime.TRACE_MAX_PROMPT_CHARS == 0
        loaded = settings_env.parse_env(tmp_path / "missing.env")
        assert loaded["INFINI_TRACE_PROMPTS"] == "1"
        assert loaded["INFINI_TRACE_MAX_PROMPT_CHARS"] == "0"
    finally:
        monkeypatch.undo()
        importlib.reload(trace_runtime)


def test_full_runtime_record_preserves_every_content_field_and_payload(monkeypatch, tmp_path):
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", True)
    monkeypatch.setattr(trace_runtime, "TRACE_MAX_PROMPT_CHARS", 0)
    clean = "\r\nExact  Ж\\u0410 " + "ж" * 140000 + " COMPLETE_TAIL"
    trace_runtime.trace_event("prompt", "offline", "exact", {"text": clean},
                              prompt=clean, negative=clean, response=clean, error=clean)
    row = trace_tools.tail_ndjson(trace_runtime.PROMPT_TRACE_FILE, 1)[0]
    for field in ("prompt", "negative", "response", "error"):
        assert row[field].encode() == clean.encode(), field
    assert row["payload"] == {"text": clean}


def test_persisted_diagnostics_redact_known_credentials_without_mutating_clean_bytes(monkeypatch, tmp_path, capsys):
    import copy
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", True)
    monkeypatch.setattr(trace_runtime, "CONSOLE_EVENT_LEVELS", ("error",))
    secret = "offline-opaque-credential-123456"
    monkeypatch.setenv("INFINI_OPENAI_COMPAT_API_KEY", secret)
    pattern_secret = "sk-offlineSecret0123456789"
    escaped = "".join("\\u%04x" % ord(char) for char in secret)
    clean = 'Exact\r\n  ж {"dup":1,"dup":2,"escaped":"\\u0410"}'
    payload = {"Authorization": "Bearer " + secret, secret: {"nested": '{"credential":"' + escaped + '"}'}, "clean": clean}
    before = copy.deepcopy(payload)
    trace_runtime.trace_event("response", "offline", secret, payload, response=pattern_secret + " / " + escaped)
    trace_runtime.log_event("error", secret, payload)
    receipt = trace_runtime.trace_stage_request("offline", "recipe", {"messages": [{"role": "user", "content": clean}, {"role": "user", "content": secret}]})
    for path in (trace_runtime.PROMPT_TRACE_FILE, tmp_path / "events.ndjson", tmp_path / receipt["path"]):
        raw = path.read_text()
        assert secret not in raw and pattern_secret not in raw and escaped.replace("\\", "\\\\") not in raw
    assert payload == before
    event = trace_tools.tail_ndjson(trace_runtime.PROMPT_TRACE_FILE, 1)[0]
    assert event["payload"]["clean"].encode() == clean.encode()
    assert json.loads((tmp_path / receipt["path"]).read_bytes())["messages"][0]["content"].encode() == clean.encode()
    assert secret not in capsys.readouterr().out


@pytest.mark.parametrize("alias", ["OPENAI_API_KEY", "OPENROUTER_API_KEY"])
@pytest.mark.parametrize("enabled", [True, False])
def test_supported_credential_aliases_redact_all_diagnostics(monkeypatch, tmp_path, capsys, alias, enabled):
    import copy
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", enabled)
    monkeypatch.setattr(trace_runtime, "CONSOLE_EVENT_LEVELS", ("error",))
    secret = "alias-opaque-offline-secret-654321"
    monkeypatch.setenv(alias, secret)
    clean = "Exact\r\n  чистый authored text"
    payload = {"clean": clean, "nested": {"value": secret}}
    before = copy.deepcopy(payload)
    trace_runtime.trace_event("response", "offline", "alias", payload, response=secret)
    receipt = trace_runtime.trace_stage_request("offline", "join", {"messages": [{"role": "user", "content": clean}, {"role": "user", "content": secret}]})
    trace_runtime.log_event("error", "x" * 490 + secret, payload)
    assert payload == before
    output = capsys.readouterr().out
    assert "alias-opaque" not in output
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert "alias-opaque" not in path.read_text(), path.name
    if enabled:
        rows = trace_tools.tail_ndjson(trace_runtime.PROMPT_TRACE_FILE, 1)
        assert rows[0]["response"] == "[REDACTED]"
        assert rows[0]["payload"]["clean"] == clean
        artifact = json.loads((tmp_path / receipt["path"]).read_bytes())
        assert artifact["messages"][0]["content"] == clean
        assert artifact["messages"][1]["content"] == "[REDACTED]"
    else:
        assert receipt == {"status": "disabled"}
        assert not trace_runtime.PROMPT_TRACE_FILE.exists()
    assert "[REDACTED]" in trace_tools.tail_ndjson(tmp_path / "events.ndjson", 1)[0]["message"]


def test_full_runtime_trace_retains_records_past_former_rolling_limit(monkeypatch, tmp_path):
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", True)
    monkeypatch.setattr(trace_runtime, "TRACE_MAX_PROMPT_CHARS", 1000)
    clean = "x" * (4 * 1024 * 1024)
    for index in range(5):
        trace_runtime.trace_event("response", "offline", str(index), response=clean)
    rows = trace_tools.tail_ndjson(trace_runtime.PROMPT_TRACE_FILE, 10)
    assert [row["title"] for row in rows] == [str(index) for index in range(5)]
    assert all(row["response"] == clean for row in rows)
    assert not list(tmp_path.glob("prompt_trace.ndjson.[0-9]*"))


def test_stage_artifacts_have_no_payload_or_record_count_refusal(monkeypatch, tmp_path):
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", True)
    long_content = "ж" * (2 * 1024 * 1024) + " EXACT_PARENT_TAIL"
    receipt = trace_runtime.trace_stage_request("author", "large", {"messages": [{"role": "user", "content": long_content}]})
    assert receipt["status"] == "stored"
    assert json.loads((tmp_path / receipt["path"]).read_bytes())["messages"][0]["content"] == long_content
    for index in range(129):
        receipt = trace_runtime.trace_stage_request("author", str(index), {"messages": [{"role": "user", "content": str(index)}]})
        assert receipt["status"] == "stored", index
    assert len(list((tmp_path / "stage_requests").glob("*.json"))) == 130


def test_full_runtime_events_are_complete_and_append_only(monkeypatch, tmp_path):
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", True)
    clean = "x" * (4 * 1024 * 1024)
    for index in range(5):
        trace_runtime.log_event("info", str(index), {"text": clean})
    rows = trace_tools.tail_ndjson(tmp_path / "events.ndjson", 10)
    assert [row["message"] for row in rows] == [str(index) for index in range(5)]
    assert all(row["payload"] == {"text": clean} for row in rows)


@pytest.mark.parametrize("kind", ["prompt", "response", "step", "warn", "error", "request_artifact"])
def test_disabled_trace_writes_no_optional_kind_or_storage(monkeypatch, tmp_path, kind, capsys):
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", False)
    trace_runtime.trace_event(kind, "offline", "diagnostic", {"text": "private"}, prompt="private", error="private")
    assert trace_runtime.trace_stage_request("offline", "recipe", {"messages": [{"role": "user", "content": "full"}]}) == {"status": "disabled"}
    assert list(tmp_path.iterdir()) == []
    assert capsys.readouterr().out == ""


def test_disabled_events_keep_only_concise_fatal_baseline(monkeypatch, tmp_path, capsys):
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", False)
    monkeypatch.setattr(trace_runtime, "CONSOLE_EVENT_LEVELS", ("debug", "info", "warn", "error"))
    for level in ("debug", "info", "warn"):
        trace_runtime.log_event(level, "extra diagnostic", {"private": "not needed"})
    assert list(tmp_path.iterdir()) == []
    trace_runtime.log_event("error", "craft failed " + "x" * 800, {"body": "do not persist"})
    rows = trace_tools.tail_ndjson(tmp_path / "events.ndjson", 10)
    assert len(rows) == 1 and rows[0]["level"] == "error"
    assert len(rows[0]["message"]) <= 500 and rows[0]["payload"] is None
    assert "do not persist" not in (tmp_path / "events.ndjson").read_text()
    assert "extra diagnostic" not in capsys.readouterr().out


def test_disabled_startup_does_not_create_optional_trace_locks(monkeypatch, tmp_path):
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", False)
    trace_runtime.initialize_trace_storage()
    assert list(tmp_path.iterdir()) == []


def test_disabled_failure_preserves_in_memory_error_without_debug_artifact(monkeypatch, tmp_path):
    from infini_local.pipelines import generation_debug
    _runtime_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", False)
    monkeypatch.setattr(generation_debug, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(generation_debug, "LAST_COMBINE_FAILURE_FILE", tmp_path / "last_combine_failure.json")
    monkeypatch.setattr(generation_debug, "_LAST_COMBINE_FAILURE", {})
    result = generation_debug.record_combine_failure("author", RuntimeError("craft failed"), None, None, [])
    assert result["ok"] is False and "craft failed" in result["error"]
    assert generation_debug.last_combine_failure_summary()["stage"] == "author"
    assert list(tmp_path.iterdir()) == []
