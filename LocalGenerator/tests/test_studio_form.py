"""Real browser-controller form semantics, independent of a windowing toolkit."""
from __future__ import annotations


from infini_local.desktop.settings_controller import SettingsController
from infini_local.desktop.settings_env import parse_env
from infini_local.desktop.settings_fields import FIELDS


def test_home_health_feedback_is_honest_when_check_failed_or_stale(tmp_path):
    home = SettingsController(tmp_path / 'config.env')
    try:
        home.status = 'Готово'
        home.applied_config = 'Runtime config unconfirmed: unavailable'
        home.refresh_home()
        assert home.home_state == 'Соединение не подтверждено'
        home.applied_config = 'Checking runtime config'
        home.refresh_home()
        assert home.home_state == 'Проверяем состояние…'
        home.activity = 'Backend last health snapshot: active=2, waiting=1, accepting=True'
        home._applied_config_ack = {'pid': 1234}
        home.applied_config = 'Runtime config matches (partial)'
        home.refresh_home()
        assert home.home_state == 'Идёт генерация'
        assert '2' in home.home_detail and '1' in home.home_detail
        assert 'снимок' in home.home_detail.lower()
        home.applied_config = 'Runtime config differs; restart'
        home.refresh_home()
        assert 'Настройки изменены' in home.home_config
        assert 'перезапуск' in home.home_config
        # A negative status phrase never certifies successful stop.
        home.status = 'Port still busy: helper has not stopped; no new server launched.'
        home.refresh_home()
        assert home.home_state == 'Нужно внимание'
        home._applied_config_ack = None
        home._server_lifecycle = 'stopped'
        home.applied_config = 'Stopped; Runtime config unconfirmed'
        for unrelated in ('Server stopped through guarded /shutdown.', 'Saved: config.env', 'Codex OAuth: сессия готова'):
            home.status = unrelated
            home.refresh_home()
            assert home.home_state == 'Сервер остановлен'
        home._server_lifecycle = 'starting'
        home.status = 'Saved: config.env'
        home.refresh_home()
        assert home.home_state == 'Сервер запускается'
        home._server_lifecycle = 'responding'
        home._applied_config_ack = {'pid': 1234}
        home.activity = 'Backend activity unknown'
        home.status = 'Codex OAuth: сессия готова'
        home.refresh_home()
        assert home.home_state == 'Сервер отвечает'
    finally:
        home.on_close()


def test_form_branches_preserve_secrets_unknown_keys_and_explicit_choices(tmp_path):
    config = tmp_path / 'config.env'
    config.write_text('INFINI_MANUAL_FUTURE_OPTION=retained\nINFINI_LLM_PROVIDER=local\n'
        'INFINI_IMAGE_BACKEND=off\nINFINI_OPENROUTER_API_KEY=FAKE-HIDDEN-TOKEN\n'
        'INFINI_LLM_MAX_TOKENS=4321\nINFINI_TRACE_PROMPTS=0\n'
        'INFINI_SDCPP_MODEL=retained.gguf\n', encoding='utf-8')
    app = SettingsController(config)
    try:
        assert all(field['key'] in app.values for field in FIELDS)
        assert next(field for field in FIELDS if field['key'] == 'INFINI_OPENROUTER_API_KEY')['secret']
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
