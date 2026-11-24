"""Real browser-controller form semantics, independent of a windowing toolkit."""
from __future__ import annotations


from infini_local.desktop.settings_controller import SettingsController
from infini_local.desktop.settings_env import parse_env
from infini_local.desktop.web_studio import StudioController


def test_home_health_feedback_uses_status_data_not_translated_prose(tmp_path):
    app = SettingsController(tmp_path / "config.env")
    controller = StudioController(app, None)
    try:
        # Supply server/action facts, not the rendered prose the browser receives.
        app._health_checked = True
        assert controller.snapshot()["home"]["code"] == "unconfirmed"
        app.actions.tasks["health-config"] = {}
        assert controller.snapshot()["home"]["code"] == "checking"
        app.actions.tasks.clear()
        app._applied_config_ack = {"pid": 1234, "activity": {"active": 2, "waiting": 1, "accepting": True}}
        app._config_match = "match"
        for noise in ("failed checking restart", "Сервер остановлен", ""):
            app.status = app.activity = app.applied_config = noise
            snapshot = controller.snapshot()
            assert snapshot["home"]["code"] == "generating"
            runtime = snapshot["runtime"]
            assert (runtime["active"], runtime["waiting"], runtime["config_match"]) == (2, 1, "match")
        app._config_match = "mismatch"
        assert controller.snapshot()["runtime"]["config_match"] == "mismatch"
        app.actions.last_action = {"status": "failed", "action": "stop"}
        assert controller.snapshot()["home"]["code"] == "attention"
        app._applied_config_ack = None
        app.actions.last_action = {}
        for lifecycle in ("stopped", "starting"):
            app._server_lifecycle = lifecycle
            app.status = "Codex OAuth: сессия готова"
            assert controller.snapshot()["home"]["code"] == lifecycle
        app._server_lifecycle = "responding"
        app._applied_config_ack = {"pid": 1234}
        assert controller.snapshot()["home"]["code"] == "responding"
    finally:
        app.on_close()


def test_form_branches_preserve_secrets_unknown_keys_and_explicit_choices(tmp_path):
    config = tmp_path / 'config.env'
    config.write_text(('# infini-config-format: json-string-v1\nINFINI_MANUAL_FUTURE_OPTION=retained\nINFINI_LLM_PROVIDER=local\n'
        'INFINI_IMAGE_BACKEND=off\nINFINI_OPENROUTER_API_KEY=FAKE-HIDDEN-TOKEN\n'
        'INFINI_LLM_MAX_TOKENS=4321\nINFINI_TRACE_PROMPTS=0\n'
        'INFINI_SDCPP_MODEL=retained.gguf\n'), encoding='utf-8')
    app = SettingsController(config)
    try:
        for provider in ('local', 'openrouter', 'openai_compat', 'openai_codex'):
            app.values['INFINI_LLM_PROVIDER'] = provider
            app._refresh_visibility()
            assert app.values['INFINI_OPENROUTER_API_KEY'] == 'FAKE-HIDDEN-TOKEN'
        for backend in ('sdcpp', 'openai_codex', 'image_api', 'off', 'a1111', 'comfyui'):
            app.values['INFINI_IMAGE_BACKEND'] = backend
            app._refresh_visibility()
            assert bool(app.field_disabled_reasons.get('INFINI_SDCPP_MODEL')) is (backend != 'sdcpp')
            assert app.values['INFINI_SDCPP_MODEL'] == 'retained.gguf'
            assert app.values['INFINI_LLM_MAX_TOKENS'] == '4321'
        app.values['INFINI_LLM_PROVIDER'] = 'openai_compat'
        app.save()
        saved = parse_env(config)
        assert saved['INFINI_MANUAL_FUTURE_OPTION'] == 'retained'
        assert saved['INFINI_OPENROUTER_API_KEY'] == 'FAKE-HIDDEN-TOKEN'
        assert saved['INFINI_TRACE_PROMPTS'] == '0'
        assert saved['INFINI_LLM_MAX_TOKENS'] == '4321'
        assert saved['INFINI_LLM_PROVIDER'] == 'openai_compat'
        app.refresh_home()
        assert 'FAKE-HIDDEN-TOKEN' not in app.home_state + app.home_detail + app.home_config
    finally:
        app.on_close()
