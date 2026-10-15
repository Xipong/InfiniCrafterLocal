"""Real browser-controller form semantics, independent of a windowing toolkit."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

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


def test_studio_import_construct_pump_and_close_without_tk_or_display(tmp_path):
    # A fresh interpreter catches indirect imports that an already-loaded module
    # could conceal. The blocker fails even if Tcl/Tk is installed on the host.
    code = '''
import importlib.abc
import sys
from pathlib import Path
class RejectTk(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == '_tkinter' or fullname == 'tkinter' or fullname.startswith('tkinter.'):
            raise AssertionError('Studio attempted a Tk import: ' + fullname)
sys.meta_path.insert(0, RejectTk())
from infini_local.desktop.settings_controller import SettingsController
from infini_local.desktop.web_studio import StudioServer, StudioController
app = SettingsController(Path(sys.argv[1]))
server = StudioServer(Path(sys.argv[2]))
try:
    controller = StudioController(app, server)
    state = controller.snapshot()
    assert state['fields'] and state['values']
    app.pump()
finally:
    app.on_close()
    server.close()
'''
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, 'PYTHONPATH': str(root)}
    env.pop('DISPLAY', None)
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path / 'config.env'),
                             str(root / 'infini_local/desktop/webui')], env=env,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
