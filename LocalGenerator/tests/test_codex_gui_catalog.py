"""Codex settings contract and thread-safe account catalog UI (no credentials/network)."""
from __future__ import annotations

from pathlib import Path

from infini_local.desktop import settings_env, settings_schema as schema
from infini_local.desktop.settings_gui_ui import SettingsGuiUiMixin
from infini_local.desktop.settings_gui_server_controls import SettingsGuiServerControlsMixin
from infini_local.desktop.settings_gui_trace_state import SettingsGuiTraceStateMixin
from infini_local.services.codex_catalog import CodexModel


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Combo:
    def __init__(self):
        self.values = ()

    def configure(self, **kw):
        if "values" in kw:
            self.values = tuple(kw["values"])


class Harness(SettingsGuiServerControlsMixin):
    def __init__(self):
        self.vars = {key: Var(value) for key, value in {
            "INFINI_CODEX_LLM_MODEL": "saved-custom",
            "INFINI_LLM_REASONING_MODE": "high",
            "INFINI_CODEX_VISUAL_REASONING": "inherit",
        }.items()}
        self.codex_model_combo = Combo()
        self.codex_model_combo.configure(values=("saved-custom",))
        self.codex_reasoning_combo = Combo()
        self.codex_visual_reasoning_combo = Combo()
        self.codex_catalog_var = Var()
        self.codex_image_account_var = Var()
        self.status_var = Var()
        self.jobs = []

    def after(self, _delay, callback):
        self.jobs.append(callback)


def test_opening_codex_tabs_auto_pings_existing_session_once(monkeypatch):
    from infini_local.services import codex_auth
    class Tabs:
        def select(self, index):
            return index
    class Nav(SettingsGuiUiMixin):
        def __init__(self):
            self.tabs = Tabs()
            self.calls = []
        def _paint_tab_navigation(self):
            pass
        def _value(self, key, default=""):
            return {"INFINI_LLM_PROVIDER": "openai_codex", "INFINI_IMAGE_BACKEND": "openai_codex"}.get(key, default)
        def refresh_codex_text_catalog(self):
            self.calls.append("text")
        def ping_codex_image_account(self):
            self.calls.append("image")
    signed_in = [False]
    monkeypatch.setattr(codex_auth, "auth_status", lambda: {"authenticated": signed_in[0], "expired": False})
    nav = Nav()
    nav._select_settings_tab(1)
    nav._select_settings_tab(3)
    assert nav.calls == []
    signed_in[0] = True
    nav._select_settings_tab(1)
    nav._select_settings_tab(3)
    nav._select_settings_tab(1)
    nav._select_settings_tab(3)
    assert nav.calls == ["text", "image"]


def test_codex_fields_have_roundtrip_defaults_and_separate_visual_effort():
    assert schema.DEFAULTS["INFINI_CODEX_LLM_MODEL"] == ""
    assert schema.DEFAULTS["INFINI_CODEX_VISUAL_REASONING"] == "inherit"
    assert all(key in schema.FIELD_ORDER for key in ("INFINI_CODEX_LLM_MODEL", "INFINI_CODEX_VISUAL_REASONING"))
    assert "openai_codex" in schema.OPTION_HELP["INFINI_LLM_PROVIDER"]
    assert "Gameplay Author" in schema.OPTION_HELP["INFINI_LLM_REASONING_MODE"]["off"]


def test_codex_fields_roundtrip_without_losing_other_provider_settings(tmp_path):
    config = tmp_path / "config.env"
    values = dict(schema.DEFAULTS, INFINI_LLM_PROVIDER="openai_codex",
                  INFINI_CODEX_LLM_MODEL="custom-slug", INFINI_CODEX_VISUAL_REASONING="inherit",
                  INFINI_LLM_REASONING_MODE="low", INFINI_CODEX_IMAGE_QUALITY="high",
                  INFINI_OPENROUTER_MODEL="other/provider")
    settings_env.write_env(config, values)
    loaded = settings_env.parse_env(config)
    assert all(loaded[key] == values[key] for key in values)


def test_llm_and_image_panels_expose_codex_controls_and_account_ping():
    ui = Path(__import__(SettingsGuiUiMixin.__module__, fromlist=["__file__"]).__file__).read_text(encoding="utf-8")
    assert 'self.row(codex_card, "Codex text model", "INFINI_CODEX_LLM_MODEL"' in ui
    assert '"INFINI_CODEX_VISUAL_REASONING"' in ui
    assert '"INFINI_CODEX_IMAGE_MODEL"' in ui
    assert 'self.refresh_codex_text_catalog' in ui
    assert "Нет live-каталога image-моделей" in ui
    assert "Качество и размер влияют" in ui


def test_refresh_keeps_saved_slug_and_shows_actual_model_efforts(monkeypatch):
    from infini_local.services import codex_catalog
    monkeypatch.setattr(codex_catalog, "list_text_models", lambda: [
        CodexModel("gpt-5.1-codex", "GPT 5.1 Codex", ("low", "medium"), "medium", 1),
        CodexModel("gpt-5.2-codex", "GPT 5.2 Codex", ("low", "high", "ultra"), "low", 2),
    ])
    gui = Harness()
    gui.refresh_codex_text_catalog()
    # Worker cannot set Tk vars from its thread; drain on UI loop.
    while gui.jobs:
        gui.jobs.pop(0)()
    assert gui.vars["INFINI_CODEX_LLM_MODEL"].get() == "saved-custom"
    assert gui.codex_model_combo.values == ("saved-custom", "gpt-5.1-codex", "gpt-5.2-codex")
    gui.vars["INFINI_CODEX_LLM_MODEL"].set("gpt-5.2-codex")
    gui._update_codex_efforts()
    assert gui.codex_reasoning_combo.values == ("off", "low", "high")
    assert gui.codex_visual_reasoning_combo.values == ("inherit", "model_default", "low", "high")
    assert gui.vars["INFINI_LLM_REASONING_MODE"].get() == "high"


def test_mismatched_saved_effort_is_not_silently_replaced():
    gui = Harness()
    gui._codex_text_models = {"saved-custom": CodexModel("saved-custom", "Saved", ("low", "ultra"), "low", 1)}
    gui._update_codex_efforts()
    assert gui.vars["INFINI_LLM_REASONING_MODE"].get() == "high"
    assert "не поддерживается" in gui.codex_catalog_var.get()
    assert "ultra" not in gui.codex_reasoning_combo.values


def test_failed_refresh_preserves_saved_slug_and_ignores_stale_success(monkeypatch):
    from infini_local.services import codex_catalog
    gui = Harness()
    first = [CodexModel("old", "Old", ("low",), "low", 1)]
    monkeypatch.setattr(codex_catalog, "list_text_models", lambda: first)
    gui.refresh_codex_text_catalog()
    # Let first worker complete, but do not drain its queued UI result yet.
    monkeypatch.setattr(codex_catalog, "list_text_models", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    gui.refresh_codex_text_catalog()
    for _ in range(5):
        if not gui.jobs:
            break
        gui.jobs.pop(0)()
    assert gui.vars["INFINI_CODEX_LLM_MODEL"].get() == "saved-custom"
    assert "old" not in gui.codex_model_combo.values
    assert "saved-custom" in gui.codex_model_combo.values
    assert "offline" not in gui.codex_catalog_var.get()  # never expose raw exception
    assert "не удалось" in gui.codex_catalog_var.get().lower()


def test_image_account_ping_is_read_only_and_does_not_claim_image_entitlement(monkeypatch):
    from infini_local.services import codex_catalog
    calls = []
    monkeypatch.setattr(codex_catalog, "list_text_models", lambda: calls.append("text-only") or [
        CodexModel("text-only", "Text", ("low",), "low", 1)])
    gui = Harness()
    gui.ping_codex_image_account()
    while gui.jobs:
        gui.jobs.pop(0)()
    assert calls == ["text-only"]
    assert gui.codex_model_combo.values == ("saved-custom",)
    assert "image-доступ не проверен" in gui.codex_image_account_var.get()
    assert "image-доступ не проверен" in gui.status_var.get()


def test_logout_invalidates_pending_account_catalog_and_image_ping(monkeypatch):
    from infini_local.services import codex_auth, codex_catalog
    monkeypatch.setattr(codex_auth, "logout", lambda: None)
    monkeypatch.setattr(codex_catalog, "list_text_models", lambda: [CodexModel("old-account-model", "Old", ("low",), "low", 1)])
    gui = Harness()
    gui.refresh_codex_text_catalog()
    gui.ping_codex_image_account()
    gui.codex_logout()
    for _ in range(8):
        if not gui.jobs:
            break
        gui.jobs.pop(0)()
    assert gui.vars["INFINI_CODEX_LLM_MODEL"].get() == "saved-custom"
    assert "old-account-model" not in gui.codex_model_combo.values
    assert not getattr(gui, "_codex_text_models", {})
    assert "доступен" not in gui.codex_image_account_var.get()
    assert "удалена" in gui.status_var.get()


def test_codex_text_and_visual_controls_follow_llm_provider():
    class Visibility(SettingsGuiTraceStateMixin):
        def __init__(self):
            self.values = dict(schema.DEFAULTS)
            self.field_widgets = {}
            self.extra_arg_buttons = []
            self.sdcpp_debug_buttons = []
            self.radmin_enabled = Var(False)
            self.vars = {}
            self.enabled = {}

        def _value(self, key, default=""):
            return self.values.get(key, default)

        def _set_field_enabled(self, key, enabled, reason=""):
            self.enabled[key] = enabled

        def _set_widgets_enabled(self, _widgets, _enabled):
            pass

        def _refresh_secret_entries(self):
            pass

    gui = Visibility()
    gui._refresh_visibility()
    assert gui.enabled["INFINI_CODEX_LLM_MODEL"] is False
    assert gui.enabled["INFINI_LLM_MAX_TOKENS"] is True
    assert gui.enabled["INFINI_LLM_TEMPERATURE"] is True
    gui.values.update(INFINI_LLM_PROVIDER="openai_codex", INFINI_IMAGE_BACKEND="openai_codex")
    gui._refresh_visibility()
    assert gui.enabled["INFINI_CODEX_LLM_MODEL"] is True
    assert gui.enabled["INFINI_CODEX_VISUAL_REASONING"] is True
    assert gui.enabled["INFINI_CODEX_IMAGE_QUALITY"] is True
    assert gui.enabled["INFINI_LLM_MAX_TOKENS"] is False
    for key in ("INFINI_LLM_TEMPERATURE", "INFINI_LLM_REAUTHOR_TEMPERATURE", "INFINI_VISUAL_DIRECTOR_TEMPERATURE", "INFINI_LLM_REASONING_EXCLUDE"):
        assert gui.enabled[key] is False, key
