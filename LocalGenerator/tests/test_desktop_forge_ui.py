"""Desktop shell contracts; no inference, account calls or game launch."""
from __future__ import annotations

from types import SimpleNamespace
import pytest

from infini_local.desktop import settings_gui_ui as ui
from infini_local.desktop.settings_gui import SettingsGui
from test_settings_gui_contract import _UiVar


# Literal field inventory of the pre-redesign UI.
EDITABLE_FIELD_KEYS = (
    'INFINI_A1111_URL',
    'INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK',
    'INFINI_ALPHA_THRESHOLD',
    'INFINI_ASSET_PUBLIC_BASE_URL',
    'INFINI_BALANCE_MODE',
    'INFINI_BG_COLOR',
    'INFINI_BG_REMOVE_MODE',
    'INFINI_CHROMA_TOLERANCE',
    'INFINI_CODEX_IMAGE_MODEL',
    'INFINI_CODEX_IMAGE_QUALITY',
    'INFINI_CODEX_IMAGE_SIZE',
    'INFINI_CODEX_IMAGE_TIMEOUT',
    'INFINI_CODEX_LLM_MODEL',
    'INFINI_CODEX_VISUAL_REASONING',
    'INFINI_COMBINE_BUSY_WAIT_SECONDS',
    'INFINI_COMFYUI_URL',
    'INFINI_CONSOLE_EVENT_LEVEL',
    'INFINI_CRAFT_HTTP_ATTEMPTS',
    'INFINI_CRAFT_HTTP_TIMEOUT_SECONDS',
    'INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD',
    'INFINI_DEBUG_ATTACK_CONSUMABLE_MIN_YIELD_ENABLED',
    'INFINI_HOST',
    'INFINI_IMAGE_API_BASE_URL',
    'INFINI_IMAGE_API_KEY',
    'INFINI_IMAGE_API_MODEL',
    'INFINI_IMAGE_API_PATH',
    'INFINI_IMAGE_API_SIZE',
    'INFINI_IMAGE_API_TIMEOUT',
    'INFINI_IMAGE_BACKEND',
    'INFINI_IMAGE_MAX_CONCURRENCY',
    'INFINI_LLM_API_MODE',
    'INFINI_LLM_FALLBACK_API_KEY',
    'INFINI_LLM_FALLBACK_BASE_URL',
    'INFINI_LLM_FALLBACK_MODEL',
    'INFINI_LLM_FALLBACK_NETWORK_FAILS',
    'INFINI_LLM_FALLBACK_OPENROUTER_PROVIDER',
    'INFINI_LLM_FALLBACK_PROVIDER',
    'INFINI_LLM_LOCAL_REASONING_PROMPT',
    'INFINI_LLM_MAX_TOKENS',
    'INFINI_LLM_POOL_2_API_KEY',
    'INFINI_LLM_POOL_2_API_MODE',
    'INFINI_LLM_POOL_2_BASE_URL',
    'INFINI_LLM_POOL_2_ENABLED',
    'INFINI_LLM_POOL_2_MODEL',
    'INFINI_LLM_POOL_2_OPENROUTER_PROVIDER',
    'INFINI_LLM_POOL_2_PROVIDER',
    'INFINI_LLM_POOL_3_API_KEY',
    'INFINI_LLM_POOL_3_API_MODE',
    'INFINI_LLM_POOL_3_BASE_URL',
    'INFINI_LLM_POOL_3_ENABLED',
    'INFINI_LLM_POOL_3_MODEL',
    'INFINI_LLM_POOL_3_OPENROUTER_PROVIDER',
    'INFINI_LLM_POOL_3_PROVIDER',
    'INFINI_LLM_POOL_4_API_KEY',
    'INFINI_LLM_POOL_4_API_MODE',
    'INFINI_LLM_POOL_4_BASE_URL',
    'INFINI_LLM_POOL_4_ENABLED',
    'INFINI_LLM_POOL_4_MODEL',
    'INFINI_LLM_POOL_4_OPENROUTER_PROVIDER',
    'INFINI_LLM_POOL_4_PROVIDER',
    'INFINI_LLM_POOL_FAILURE_COOLDOWN_SECONDS',
    'INFINI_LLM_PROVIDER',
    'INFINI_LLM_REASONING_EXCLUDE',
    'INFINI_LLM_REASONING_MAX_TOKENS',
    'INFINI_LLM_REASONING_MODE',
    'INFINI_LLM_REAUTHOR_TEMPERATURE',
    'INFINI_LLM_RESPONSE_FORMAT',
    'INFINI_LLM_TEMPERATURE',
    'INFINI_LMSTUDIO_MODEL',
    'INFINI_LMSTUDIO_URL',
    'INFINI_MAX_COLORS',
    'INFINI_MP_ASSET_TRANSPORT',
    'INFINI_MULTIDEV_CONCURRENCY',
    'INFINI_OPENAI_COMPAT_API_KEY',
    'INFINI_OPENAI_COMPAT_BASE_URL',
    'INFINI_OPENAI_COMPAT_MODEL',
    'INFINI_OPENROUTER_API_KEY',
    'INFINI_OPENROUTER_APP_TITLE',
    'INFINI_OPENROUTER_HTTP_REFERER',
    'INFINI_OPENROUTER_MODEL',
    'INFINI_OPENROUTER_PROVIDER',
    'INFINI_PIXEL_POSTERIZE',
    'INFINI_PORT',
    'INFINI_PROMPT_STYLE',
    'INFINI_REMOVE_BG',
    'INFINI_SAVE_SPRITE_STAGES',
    'INFINI_SDCPP_CFG',
    'INFINI_SDCPP_HEIGHT',
    'INFINI_SDCPP_LLM',
    'INFINI_SDCPP_LORA_FILE',
    'INFINI_SDCPP_LORA_PROMPT_TAGS',
    'INFINI_SDCPP_LORA_WEIGHT',
    'INFINI_SDCPP_MODEL',
    'INFINI_SDCPP_ROCM_COMPAT_ROOT',
    'INFINI_SDCPP_SAMPLER',
    'INFINI_SDCPP_SEED',
    'INFINI_SDCPP_SERVER_AUTOSTART',
    'INFINI_SDCPP_SERVER_COMMAND_MODE',
    'INFINI_SDCPP_SERVER_COMMAND_TEMPLATE',
    'INFINI_SDCPP_SERVER_EXE',
    'INFINI_SDCPP_SERVER_EXTRA_ARGS',
    'INFINI_SDCPP_SERVER_LOG_FILE',
    'INFINI_SDCPP_SERVER_SHOW_CONSOLE',
    'INFINI_SDCPP_SERVER_URL',
    'INFINI_SDCPP_STEPS',
    'INFINI_SDCPP_VAE',
    'INFINI_SDCPP_WIDTH',
    'INFINI_SPRITE_CHROMA_DEFRINGE',
    'INFINI_SPRITE_DOWNSCALE_FILTER',
    'INFINI_SPRITE_KEYER_RESIDUE_STEPS',
    'INFINI_SPRITE_KEYER_SPILL_RADIUS',
    'INFINI_SPRITE_MASTER_CANVAS',
    'INFINI_SPRITE_PREMULTIPLIED_RESIZE',
    'INFINI_SPRITE_RETRIES',
    'INFINI_TERRARIA_PORT',
    'INFINI_TRACE_EVENTS_TAIL',
    'INFINI_TRACE_MAX_PROMPT_CHARS',
    'INFINI_TRACE_PROMPTS',
    'INFINI_USE_LLM',
    'INFINI_VFX_LLM_DIRECTOR',
    'INFINI_VISUAL_ALLOW_PROCEDURAL_FALLBACK',
    'INFINI_VISUAL_ASSET_MODE',
    'INFINI_VISUAL_DIRECTOR_LLM',
    'INFINI_VISUAL_DIRECTOR_MAX_TOKENS',
    'INFINI_VISUAL_DIRECTOR_TEMPERATURE',
    'INFINI_VISUAL_REQUIRE_ITEM_SPRITE',
    'INFINI_VISUAL_STRICT_AI_AUTHORSHIP',
    'INFINI_ZIMAGE_POSITIVE_ONLY',
    'INFINI_ZIMAGE_PROMPT_CONTRACT',
)


def test_font_resolution_prefers_segoe_but_uses_scalable_native_fallback():
    from infini_local.desktop.settings_gui_theme import resolve_ui_font
    assert resolve_ui_font(("Segoe UI", "helvetica")) == "Segoe UI"
    assert resolve_ui_font(("fixed", "helvetica", "courier")) == "helvetica"
    assert resolve_ui_font(("DejaVu Sans", "fixed")) == "DejaVu Sans"


def test_sidebar_routes_have_operate_default_and_explicit_configuration_pages():
    from infini_local.desktop.settings_gui_shell import PAGE_SPECS
    assert PAGE_SPECS[0].key == "operate"
    assert {page.key for page in PAGE_SPECS} == {
        "operate", "providers", "models", "images", "sprites", "diagnostics", "multiplayer", "configure",
    }
    assert len({page.key for page in PAGE_SPECS}) == len(PAGE_SPECS)
    assert next(page for page in PAGE_SPECS if page.key == "providers").index == 1
    assert next(page for page in PAGE_SPECS if page.key == "images").index == 3


def test_field_hover_does_not_overwrite_action_or_failure_status():
    gui = object.__new__(SettingsGui)
    gui.status_var = _UiVar("Server failed: retain this diagnostic")
    gui._field_help_text = lambda key: "Helpful field description"
    gui._show_field_help("INFINI_LLM_PROVIDER")
    assert gui.status_var.get() == "Server failed: retain this diagnostic"


def test_inactive_fields_stay_hidden_in_advanced_mode_without_rewriting_values():
    calls = {}
    inactive, advanced_field = object(), object()
    gui = SimpleNamespace(advanced_var=_UiVar(True),
        field_widgets={"INFINI_SDCPP_MODEL": [inactive], "INFINI_LLM_REASONING_MAX_TOKENS": [advanced_field]},
        field_hint_labels={}, field_disabled_reasons={"INFINI_SDCPP_MODEL": "Not selected"}, _ui_sections=[],
        vars={"INFINI_SDCPP_MODEL": _UiVar("retained.gguf")})
    gui._set_packed_visible = lambda widget, visible: calls.update({widget: visible})
    SettingsGui._apply_view_mode(gui)
    assert calls[inactive] is False
    assert calls[advanced_field] is True
    assert gui.vars["INFINI_SDCPP_MODEL"].get() == "retained.gguf"


def test_home_health_feedback_is_honest_when_check_failed_or_stale():
    from infini_local.desktop.settings_page_operate import OperatePageMixin
    class Home(OperatePageMixin):
        pass
    home = Home()
    home.data = {}
    home.vars = {}
    home.status_var = _UiVar("Готово")
    home.applied_config_var = _UiVar("Runtime config unconfirmed: unavailable")
    home.home_state_var = _UiVar()
    home.home_detail_var = _UiVar()
    home.home_pipeline_var = _UiVar()
    home.home_config_var = _UiVar()
    home.home_notice_var = _UiVar()
    home.home_model_vars = [_UiVar() for _ in range(3)]
    home._refresh_operate_summary()
    assert home.home_state_var.get() == "Соединение не подтверждено"
    home.applied_config_var.set("Checking runtime config")
    home._refresh_operate_summary()
    assert home.home_state_var.get() == "Проверяем состояние…"
    home.activity_var = _UiVar("Backend last health snapshot: active=2, waiting=1, accepting=True")
    home._applied_config_ack = {"pid": 1234}
    home.applied_config_var.set("Runtime config matches (partial)")
    home._refresh_operate_summary()
    assert home.home_state_var.get() == "Идёт генерация"
    assert "2" in home.home_detail_var.get() and "1" in home.home_detail_var.get()
    assert "снимок" in home.home_detail_var.get().lower()
    home.applied_config_var.set("Runtime config differs; restart")
    home._refresh_operate_summary()
    assert "Настройки изменены" in home.home_config_var.get()
    assert "перезапуск" in home.home_config_var.get()

    # A negative status phrase must never certify a successful stop.
    home.status_var.set("Port still busy: helper has not stopped; no new server launched.")
    home._refresh_operate_summary()
    assert home.home_state_var.get() == "Нужно внимание"
    home._applied_config_ack = None
    home._server_lifecycle = "stopped"
    home.applied_config_var.set("Stopped; Runtime config unconfirmed")
    for unrelated in ("Server stopped through guarded /shutdown.", "Saved: config.env", "Codex OAuth: сессия готова"):
        home.status_var.set(unrelated)
        home._refresh_operate_summary()
        assert home.home_state_var.get() == "Сервер остановлен"
    home._server_lifecycle = "starting"
    home.status_var.set("Saved: config.env")
    home._refresh_operate_summary()
    assert home.home_state_var.get() == "Сервер запускается"
    home._server_lifecycle = "responding"
    home._applied_config_ack = {"pid": 1234}
    home.activity_var.set("Backend activity unknown")
    home.status_var.set("Codex OAuth: сессия готова")
    home._refresh_operate_summary()
    assert home.home_state_var.get() == "Сервер отвечает"


def test_real_tk_shell_navigation_save_and_secret_regression(tmp_path, monkeypatch):
    from infini_local.desktop.tk_compat import TKINTER_AVAILABLE, tk
    if not TKINTER_AVAILABLE:
        pytest.skip("real Tk check runs separately under a Tk-capable interpreter and Xvfb")
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip("real Tk check requires a display (Xvfb)")
    from infini_local.desktop import settings_gui, settings_gui_trace_state as state
    from infini_local.desktop.settings_env import parse_env
    config = tmp_path / "config.env"
    config.write_text("INFINI_MANUAL_FUTURE_OPTION=retained\nINFINI_LLM_PROVIDER=local\n"
        "INFINI_IMAGE_BACKEND=off\nINFINI_OPENROUTER_API_KEY=FAKE-HIDDEN-TOKEN\n"
        "INFINI_LLM_MAX_TOKENS=4321\nINFINI_TRACE_PROMPTS=0\n", encoding="utf-8")
    monkeypatch.setattr(settings_gui, "CONFIG_PATH", config)
    monkeypatch.setattr(state, "CONFIG_PATH", config)
    app = SettingsGui()
    try:
        app.update()
        assert app.tabs.index(app.tabs.select()) == 0
        for page in app.page_specs:
            app.navigate(page.key)
            app.update()
            assert app.tabs.index(app.tabs.select()) == page.index
            assert app.page_title_var.get() == page.title
        app.advanced_var.set(True)
        app._apply_view_mode()
        assert app.field_widgets["INFINI_SDCPP_MODEL"][0].winfo_manager() == ""
        assert app.secret_entries and all(entry.cget("show") == "*" for entry in app.secret_entries)
        app.vars["INFINI_LLM_PROVIDER"].set("openai_compat")
        app._refresh_visibility()
        app.navigate("operate")
        app.save()
        saved = parse_env(config)
        assert saved["INFINI_MANUAL_FUTURE_OPTION"] == "retained"
        assert saved["INFINI_OPENROUTER_API_KEY"] == "FAKE-HIDDEN-TOKEN"
        assert saved["INFINI_LLM_MAX_TOKENS"] == "4321"
        assert saved["INFINI_TRACE_PROMPTS"] == "0"
        assert saved["INFINI_LLM_PROVIDER"] == "openai_compat"
        assert "FAKE-HIDDEN-TOKEN" not in app.home_pipeline_var.get()
        assert "FAKE-HIDDEN-TOKEN" not in app.home_state_var.get()
        assert all(key in app.vars or key in app.text_widgets for key in EDITABLE_FIELD_KEYS)
        # All supported provider/backend branches retain inputs through navigation.
        for provider in ("local", "openrouter", "openai_compat", "openai_codex"):
            app.vars["INFINI_LLM_PROVIDER"].set(provider)
            app._refresh_visibility()
            assert app.vars["INFINI_OPENROUTER_API_KEY"].get() == "FAKE-HIDDEN-TOKEN"
        for backend in ("sdcpp", "openai_codex", "image_api", "off", "a1111", "comfyui"):
            app.vars["INFINI_IMAGE_BACKEND"].set(backend)
            app._refresh_visibility()
            assert bool(app.field_widgets["INFINI_SDCPP_MODEL"][0].winfo_manager()) is (backend == "sdcpp")
            assert app.vars["INFINI_LLM_MAX_TOKENS"].get() == "4321"
        app.geometry("1040x740")
        for page in app.page_specs:
            app.navigate(page.key)
            app.update()
            assert app.tabs.winfo_width() > 600
            assert app.tab_nav_buttons[page.index].winfo_ismapped()
        app.navigate("operate")
        app.update()
        assert not app.view_options.winfo_ismapped()
        app.navigate("images")
        app.update()
        assert app.view_options.winfo_ismapped()
        assert app.operate_actions["start"].cget("command")
        assert app.operate_actions["stop"].cget("command")
        assert app.operate_actions["health"].cget("command")
    finally:
        app.on_close()
