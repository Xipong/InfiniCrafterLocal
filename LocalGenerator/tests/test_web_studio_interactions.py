"""Browser presentation must never invoke hidden desktop interactions."""
from pathlib import Path
from types import SimpleNamespace
import json
import urllib.error
import urllib.request

import pytest

from infini_local.desktop import settings_controller
from infini_local.desktop import studio_operations as controls
from infini_local.desktop.web_studio import StudioController, StudioServer
from test_settings_gui_contract import _GuiWorkflowHarness, held_gui_call


@pytest.fixture
def studio(tmp_path, monkeypatch):
    config = tmp_path / 'config.env'
    monkeypatch.setattr(controls, 'ROOT', tmp_path)
    app = _GuiWorkflowHarness(config)
    server = StudioServer(tmp_path)
    controller = StudioController(app, server)
    yield app, controller, server, config
    app.on_close()
    server.close()


def command(controller, name, identifier='command', values=None, extra=None):
    controller.apply({'id': identifier, 'action': name, 'values': values or {}, 'extra': extra or {}})
    return controller.action_results[identifier]


def test_snapshot_publishes_only_bounded_existing_text_catalog_metadata(studio, monkeypatch):
    from infini_local.services import codex_auth, codex_catalog

    app, controller, _server, config = studio
    auth = {'authenticated': True, 'expired': False, 'access_token': 'DO-NOT-PUBLISH-AUTH'}
    monkeypatch.setattr(codex_auth, 'auth_status', lambda: auth)
    monkeypatch.setattr(codex_catalog, 'list_text_models', lambda: pytest.fail('Snapshot must not fetch any catalog'))
    app._codex_text_models = {
        f'model-{index}': codex_catalog.CodexModel(f'model-{index}', 'DO-NOT-PUBLISH-LABEL',
                                                ('low', 'high', 'unsupported'), 'high', index)
        for index in range(260)
    }
    account = controller.snapshot()['account']
    assert account['authenticated'] is True
    assert len(account['textModels']) == 256
    assert account['textModels']['model-0'] == {'efforts': ['low', 'high'], 'defaultEffort': 'high'}
    assert 'DO-NOT-PUBLISH' not in json.dumps(account)
    assert not config.exists()
    assert not app._gui_tasks
    auth['authenticated'] = False
    app._codex_text_models = {}
    account = controller.snapshot()['account']
    assert account['authenticated'] is False and account['textModels'] == {}


@pytest.mark.parametrize('error_type', [OSError, ValueError, UnicodeError])
def test_malformed_saved_config_keeps_polling_stop_and_recovery_available(studio, monkeypatch, error_type):
    from infini_local.desktop import settings_env

    app, controller, server, config = studio
    config.write_text('INFINI_PROMPT_STYLE=last good disk\n', encoding='utf-8')
    good = controller.snapshot()
    app.proc = SimpleNamespace(pid=123456, poll=lambda: None)
    app._owned_launch_settings = dict(good['savedValues'])
    app._owned_server_base_url = 'http://127.0.0.1:5055'
    app._fetch_health_snapshot = lambda **kwargs: {
        'ok': True, 'pid': 123456, 'generationActivity': {'active': 0, 'waiting': 0, 'accepting': True}}
    app._shutdown_identity_is_safe = lambda snap: True
    app._safe_effective_config = lambda snap: {'cacheDir': 'cache'}
    app._try_http_shutdown_current_server = lambda **kwargs: (True, '')
    app._wait_until_helper_stops = lambda **kwargs: True
    parse_env = settings_env.parse_env
    def malformed(_path):
        raise error_type('Malformed saved configuration')
    monkeypatch.setattr(settings_env, 'parse_env', malformed)
    server.commands.put({'id': 'stop-with-malformed-config', 'action': 'stop', 'values': {}, 'extra': {}})
    controller.tick()
    assert server._state['savedValues'] == good['savedValues']
    assert server._state['savedRevision'] is None
    assert 'Не удалось проверить сохранённую конфигурацию' in server._state['status']
    assert app._scheduled_ids, 'Polling must remain scheduled after the read failure'
    app.drain_until(lambda: controller.action_results['stop-with-malformed-config']['status'] != 'running')
    assert controller.action_results['stop-with-malformed-config']['status'] == 'succeeded'
    assert app.proc is None
    monkeypatch.setattr(settings_env, 'parse_env', parse_env)
    config.write_text('INFINI_PROMPT_STYLE=repaired disk\n', encoding='utf-8')
    controller.tick()
    assert server._state['savedValues']['INFINI_PROMPT_STYLE'] == 'repaired disk'
    assert server._state['savedRevision'] is not None
    assert 'Не удалось проверить сохранённую конфигурацию' not in server._state['status']


def test_validation_and_missing_lora_are_browser_results(studio):
    app, controller, _server, _config = studio
    app.values['INFINI_LLM_PROVIDER'] = 'openrouter'
    app.values['INFINI_OPENROUTER_API_KEY'] = ''
    app.values['INFINI_IMAGE_BACKEND'] = 'off'
    result = command(controller, 'validate')
    assert result['status'] == 'failed'
    assert 'OpenRouter' in result['message']
    assert controller.notifications[-1]['level'] == 'warning'
    result = command(controller, 'useLora', 'lora')
    assert result['ok'] is False
    assert 'LoRA' in result['message']
    assert controller.snapshot()['notifications']


def test_clear_trace_requires_browser_confirmation_and_keeps_guard(studio):
    app, controller, _server, _config = studio
    called = []
    app._fetch_health_snapshot = lambda **kwargs: called.append(True) or {'ok': True, 'serverRoot': '/foreign', 'pid': 123}
    with pytest.raises(ValueError, match='Подтверди'):
        command(controller, 'clearTrace')
    assert not called
    result = command(controller, 'clearTrace', 'confirmed', extra={'confirm': True})
    assert result['status'] == 'running'
    app.drain_until(lambda: result['status'] != 'running')
    assert result['ok'] is False
    assert 'foreign' in result['message']
    assert controller.snapshot()['traceStatus'] == result['message']


def test_two_commands_in_one_tick_retain_both_receipts(studio):
    app, controller, server, _config = studio
    app.values['INFINI_IMAGE_BACKEND'] = 'off'
    app.values['INFINI_LLM_PROVIDER'] = 'local'
    for identifier in ('one', 'two'):
        server.commands.put({'id': identifier, 'action': 'validate', 'values': {}, 'extra': {}})
    controller.tick()
    assert {result['id'] for result in server._state['actionResults']} == {'one', 'two'}
    assert all(result['status'] == 'succeeded' for result in server._state['actionResults'])


def test_open_config_never_saves_and_masks_credential_assignments(studio):
    app, controller, _server, config = studio
    with pytest.raises(ValueError, match='Сначала явно сохрани'):
        command(controller, 'openConfig', values={'INFINI_PROMPT_STYLE': 'unsaved'})
    assert not config.exists()
    assert app.values['INFINI_PROMPT_STYLE'] != 'unsaved'
    config.write_text('INFINI_OPENAI_COMPAT_API_KEY=secret-fixture\nINFINI_LLM_MAX_TOKENS=12345\n', encoding='utf-8')
    result = command(controller, 'openConfig', 'view')
    assert result['result']['kind'] == 'document'
    assert 'secret-fixture' not in result['result']['content']
    assert '12345' in result['result']['content']
    assert 'secret-fixture' in config.read_text()


def test_help_returns_real_guide_without_desktop_browser(studio):
    _app, controller, _server, _config = studio
    result = command(controller, 'help')
    assert result['ok']
    assert result['result']['kind'] == 'guide'
    assert result['result']['url'].startswith('/guide?token=')
    assert result['result']['url'].endswith('START_RU.md')


@pytest.mark.parametrize('rejected_action', ['start', 'forceRestart'])
def test_rejected_cross_tab_launch_preserves_first_guarded_launch(studio, monkeypatch, held_gui_call, rejected_action):
    from infini_local.desktop.settings_env import parse_env
    from infini_local.desktop.settings_interactions import saved_config_revision

    app, controller, _server, config = studio
    config.write_text('INFINI_PROMPT_STYLE=original\n', encoding='utf-8')
    revision = saved_config_revision(config)
    hold = held_gui_call(app, '_fetch_health_snapshot', ConnectionRefusedError())
    launches = []
    monkeypatch.setattr(controls.subprocess, 'Popen',
                        lambda *args, **kwargs: launches.append(kwargs['env']) or SimpleNamespace(pid=123456, poll=lambda: None))
    first = command(controller, 'start', 'first-tab',
                    values={'INFINI_PORT': '6061', 'INFINI_GUI_PIPELINE_PRESET': 'first-tab-profile'},
                    extra={'savedRevision': revision, 'lanEnabled': False})
    assert hold.entered.wait(1)
    before = (dict(app.values), app.preset, app.lan_enabled,
              dict(app._profile_baseline), app._profile_baseline_label, config.read_bytes())
    try:
        rejected = command(controller, rejected_action, 'second-tab',
                           values={'INFINI_PORT': '7172', 'INFINI_GUI_PIPELINE_PRESET': 'second-tab-profile',
                                   'INFINI_SECOND_TAB_EXTENSION': 'must not escape'},
                           extra={'savedRevision': revision, 'lanEnabled': True, 'confirm': True})
        assert rejected['status'] == 'failed' and rejected['ok'] is False
        assert 'уже выполняется' in rejected['message']
        assert not rejected.get('saved')
        assert (app.values, app.preset, app.lan_enabled,
                app._profile_baseline, app._profile_baseline_label, config.read_bytes()) == before
        assert first['status'] == 'running' and not launches
    finally:
        hold.release.set()
    app.drain_until(lambda: first['status'] != 'running')
    assert first['status'] == 'succeeded' and first['saved'] is True
    assert len(launches) == 1 and hold.calls == ['http://127.0.0.1:6061']
    assert launches[0]['INFINI_PORT'] == '6061'
    assert launches[0]['INFINI_GUI_PIPELINE_PRESET'] == 'first-tab-profile'
    assert 'INFINI_SECOND_TAB_EXTENSION' not in launches[0]
    assert parse_env(config)['INFINI_PORT'] == '6061'
    assert first['savedRevision'] == saved_config_revision(config) != revision
    assert app._owned_server_base_url == 'http://127.0.0.1:6061'


@pytest.mark.parametrize('confirm', [None, False, 'true', 1])
def test_unconfirmed_force_restart_cannot_adopt_browser_draft(studio, monkeypatch, confirm):
    app, controller, _server, config = studio
    config.write_text('INFINI_DISK_EXTENSION=latest on disk\n', encoding='utf-8')
    app.values['INFINI_DISK_EXTENSION'] = 'cached value'
    app.values['INFINI_REMOVED_EXTENSION'] = 'retained only in controller'
    before = (dict(app.values), app.preset, app.lan_enabled,
              dict(app._profile_baseline), app._profile_baseline_label, config.read_bytes())
    monkeypatch.setattr(app, '_request_server_action', lambda **kwargs: pytest.fail('Unconfirmed force must not enter guard'))
    with pytest.raises(ValueError, match='confirmation'):
        command(controller, 'forceRestart', values={'INFINI_PORT': '7172', 'INFINI_GUI_PIPELINE_PRESET': 'unconfirmed'},
                extra={'confirm': confirm, 'lanEnabled': not app.lan_enabled})
    assert (app.values, app.preset, app.lan_enabled,
            app._profile_baseline, app._profile_baseline_label, config.read_bytes()) == before
    assert controller.last_action['status'] == 'failed'
    assert not controller.last_action.get('saved') and not app._gui_tasks


@pytest.mark.parametrize('action', ['start', 'forceRestart'])
def test_async_launch_failure_acknowledges_saved_settings_and_allows_retry(studio, monkeypatch, action):
    from infini_local.desktop.settings_env import parse_env
    from infini_local.desktop.settings_interactions import saved_config_revision

    app, controller, _server, config = studio
    config.write_text('INFINI_PROMPT_STYLE=original\n', encoding='utf-8')
    original_revision = saved_config_revision(config)
    submitted = {'INFINI_PROMPT_STYLE': 'submitted draft', 'INFINI_PRIVATE_UNKNOWN': 'retained value',
                 'INFINI_OPENAI_COMPAT_API_KEY': 'dummy-new-key'}
    app.values['INFINI_PROMPT_STYLE'] = 'original'
    app._fetch_health_snapshot = lambda **kwargs: (_ for _ in ()).throw(ConnectionRefusedError())
    launches = []
    def fail_launch(*args, **kwargs):
        launches.append(kwargs['env'])
        raise OSError('not executable: DO-NOT-EXPOSE-EXCEPTION')
    monkeypatch.setattr(controls.subprocess, 'Popen', fail_launch)
    result = command(controller, action, values=submitted, extra={'savedRevision': original_revision, 'confirm': True})
    assert result['status'] == 'running'
    app.drain_until(lambda: result['status'] != 'running')
    assert result['status'] == 'failed'
    assert result['ok'] is False and result['saved'] is True
    assert controller.notifications[-1]['level'] == 'error'
    assert 'сохранены в config.env' in result['message'] and 'server.py' in result['message']
    assert 'DO-NOT-EXPOSE' not in result['message']
    saved = parse_env(config)
    assert all(saved[key] == value for key, value in submitted.items())
    saved['INFINI_GUI_PIPELINE_PRESET'] = app._pipeline_preset_from_config(saved, app.user_presets)
    assert result['savedValues'] == saved
    assert result['savedRevision'] == saved_config_revision(config) != original_revision
    assert controller.snapshot()['savedValues'] == result['savedValues']
    assert app.proc is None and app._applied_config_ack is None
    assert app._server_lifecycle == 'unknown'
    assert len(launches) == 1
    # The failed-launch receipt is a valid disk baseline for an explicit retry.
    retry = command(controller, action, 'retry', values=submitted,
                    extra={'savedRevision': result['savedRevision'], 'confirm': True})
    app.drain_until(lambda: retry['status'] != 'running')
    assert retry['status'] == 'failed' and retry['saved'] is True
    assert len(launches) == 2


@pytest.mark.parametrize('failure', ['guard', 'save'])
def test_start_failure_before_persistence_does_not_acknowledge_draft(studio, monkeypatch, failure):
    app, controller, _server, config = studio
    original = 'INFINI_PROMPT_STYLE=original\n'
    config.write_text(original, encoding='utf-8')
    if failure == 'guard':
        app._fetch_health_snapshot = lambda **kwargs: {'ok': True, 'serverRoot': '/foreign', 'pid': 123}
    else:
        app._fetch_health_snapshot = lambda **kwargs: (_ for _ in ()).throw(ConnectionRefusedError())
        monkeypatch.setattr(settings_controller, 'write_env', lambda *args, **kwargs: (_ for _ in ()).throw(OSError('write denied')))
    monkeypatch.setattr(controls.subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('Must not launch before a successful save'))
    result = command(controller, 'start', values={'INFINI_PROMPT_STYLE': 'unsaved draft'})
    app.drain_until(lambda: result['status'] != 'running')
    assert result['status'] == 'failed'
    assert not result.get('saved')
    assert 'savedValues' not in result and 'savedRevision' not in result
    assert config.read_text(encoding='utf-8') == original


def test_file_picker_is_authenticated_filtered_bounded_and_read_only(studio, tmp_path):
    _app, _controller, server, _config = studio
    server.file_root = tmp_path
    (tmp_path / 'folder').mkdir()
    (tmp_path / 'model.gguf').write_text('model-data')
    (tmp_path / 'credentials.txt').write_text('private-data')
    (tmp_path / 'alias').symlink_to(tmp_path / 'credentials.txt')
    server.start()
    with pytest.raises(urllib.error.HTTPError) as denied:
        urllib.request.urlopen(server.base_url + '/api/files')
    assert denied.value.code == 403
    request = urllib.request.Request(server.base_url + '/api/files?kind=model', headers={'X-Infini-Token': server.token})
    result = json.load(urllib.request.urlopen(request))
    assert {item['name'] for item in result['entries']} == {'folder', 'model.gguf'}
    assert 'model-data' not in json.dumps(result)
    assert 'private-data' not in json.dumps(result)
    assert server.list_files(str(tmp_path / 'gone' / 'file.gguf'), 'model')['warning']
    for path in ('//server/share', '\\\\server\\share', '/\\server/share'):
        with pytest.raises(ValueError):
            server.list_files(path, 'file')
    for index in range(305):
        (tmp_path / f'model-{index}.gguf').touch()
    result = server.list_files('', 'model')
    assert len(result['entries']) == 300
    assert result['truncated'] is True
    exact = server.list_files(str(tmp_path / 'model-304.gguf'), 'model')
    assert exact['selected']['name'] == 'model-304.gguf'
    assert exact['truncated'] is True


def test_desktop_launcher_opens_browser_studio(monkeypatch):
    import runpy
    from infini_local.desktop import web_studio
    called = []
    monkeypatch.setattr(web_studio, 'main', lambda: called.append(True))
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "settings_gui.py"), run_name="__main__")
    assert called == [True]


def test_config_viewer_masks_parser_equivalent_whitespace_and_retained_keys(studio):
    _app, controller, _server, config = studio
    config.write_text('  INFINI_OPENAI_COMPAT_API_KEY = spaced-secret\nCUSTOM_PASSWORD = other-secret\nINFINI_LLM_MAX_TOKENS=123\n', encoding='utf-8')
    content = command(controller, 'openConfig')['result']['content']
    assert 'spaced-secret' not in content
    assert 'other-secret' not in content
    assert '123' in content


def test_stale_save_rejected_before_mutating_shared_state(studio):
    app, controller, _server, config = studio
    from infini_local.desktop.settings_interactions import saved_config_revision
    config.write_text('INFINI_PROMPT_STYLE=original\n')
    baseline = saved_config_revision(config)
    app.values['INFINI_PROMPT_STYLE'] = 'controller-original'
    config.write_text('INFINI_PROMPT_STYLE=other-tab-save\n')
    with pytest.raises(ValueError, match='другой вкладке'):
        command(controller, 'save', values={'INFINI_PROMPT_STYLE': 'stale-tab'}, extra={'savedRevision': baseline})
    assert app.values['INFINI_PROMPT_STYLE'] == 'controller-original'
    assert config.read_text() == 'INFINI_PROMPT_STYLE=other-tab-save\n'
    assert controller.action_results['command']['status'] == 'failed'


@pytest.mark.parametrize('action', ['save', 'start', 'forceRestart'])
@pytest.mark.parametrize('edit_removed', [False, True])
def test_persistence_does_not_resurrect_removed_retained_keys(studio, monkeypatch, action, edit_removed):
    from infini_local.desktop.settings_env import parse_env
    from infini_local.desktop.settings_interactions import saved_config_revision

    app, controller, _server, config = studio
    config.write_text('INFINI_KEEP=saved value\n', encoding='utf-8')
    app.values.update(INFINI_KEEP='old value', INFINI_REMOVED='stale removed value')
    app.values = {'INFINI_REMOVED': 'stale removed value'}
    values = parse_env(config)
    values['INFINI_KEEP'] = 'explicit new value'
    if edit_removed:
        values['INFINI_REMOVED'] = 'explicit restore'
    app._fetch_health_snapshot = lambda **kwargs: (_ for _ in ()).throw(ConnectionRefusedError())
    launches = []
    def launch(*args, **kwargs):
        launches.append(kwargs['env'])
        return SimpleNamespace(pid=123456, poll=lambda: None)
    monkeypatch.setattr(controls.subprocess, 'Popen', launch)
    result = command(controller, action, values=values,
                     extra={'savedRevision': saved_config_revision(config), 'confirm': True})
    app.drain_until(lambda: result['status'] != 'running')
    assert result['status'] == 'succeeded'
    assert parse_env(config)['INFINI_KEEP'] == 'explicit new value'
    for actual in (parse_env(config), app.values, app.values, result['savedValues']):
        if edit_removed:
            assert actual['INFINI_REMOVED'] == 'explicit restore'
        else:
            assert 'INFINI_REMOVED' not in actual
    if action != 'save':
        assert len(launches) == 1
        assert launches[0].get('INFINI_REMOVED') == ('explicit restore' if edit_removed else None)


def test_partial_save_keeps_current_disk_retained_keys(studio):
    from infini_local.desktop.settings_env import parse_env

    app, controller, _server, config = studio
    config.write_text('INFINI_KEEP=current disk value\n', encoding='utf-8')
    app.values.update(INFINI_KEEP='stale adapter value', INFINI_REMOVED='stale removed value')
    app.values = {'INFINI_REMOVED': 'stale removed value'}
    result = command(controller, 'save', values={'INFINI_PROMPT_STYLE': 'edited'})
    assert result['status'] == 'succeeded'
    assert parse_env(config)['INFINI_KEEP'] == 'current disk value'
    assert 'INFINI_REMOVED' not in parse_env(config)


def test_diagnostic_draft_does_not_mutate_other_tabs_launch_settings(studio):
    app, controller, _server, config = studio
    app.values['INFINI_PROMPT_STYLE'] = 'shared-draft'
    app.values['INFINI_IMAGE_BACKEND'] = 'off'
    app.values['INFINI_LLM_PROVIDER'] = 'local'
    config.write_text('INFINI_PROMPT_STYLE=saved\n')
    command(controller, 'validate', values={'INFINI_PROMPT_STYLE': 'other-tab', 'INFINI_PRIVATE_EXTENSION': 'temp'})
    assert app.values['INFINI_PROMPT_STYLE'] == 'shared-draft'
    assert 'INFINI_PRIVATE_EXTENSION' not in app.values
    assert config.read_text() == 'INFINI_PROMPT_STYLE=saved\n'
    command(controller, 'cancelTrace', 'cancel', values={'INFINI_PROMPT_STYLE': 'unrelated'})
    assert app.values['INFINI_PROMPT_STYLE'] == 'shared-draft'


def test_async_cancel_retires_original_receipt(studio):
    import threading
    app, controller, _server, _config = studio
    entered, release = threading.Event(), threading.Event()
    def held(**kwargs):
        entered.set()
        release.wait(2)
        return {'events': []}
    app._fetch_trace_snapshot = held
    result = command(controller, 'trace', 'held')
    assert entered.wait(1)
    command(controller, 'cancelTrace', 'cancel')
    release.set()
    app.drain_until(lambda: result['status'] != 'running')
    assert result['status'] == 'cancelled'
    assert not any(app.trace.values())


def test_coalesced_trace_commands_all_receive_terminal_receipt(studio):
    import threading
    app, controller, _server, _config = studio
    entered, release = threading.Event(), threading.Event()
    def held(**kwargs):
        entered.set()
        release.wait(2)
        return {'events': []}
    app._fetch_trace_snapshot = held
    first = command(controller, 'trace', 'first')
    assert entered.wait(1)
    second = command(controller, 'trace', 'second')
    third = command(controller, 'trace', 'third')
    assert first['status'] == 'running'
    assert second['status'] == 'cancelled'
    assert third['status'] == 'running'
    release.set()
    app.drain_until(lambda: third['status'] != 'running')
    assert first['status'] == 'cancelled'
    assert third['status'] == 'succeeded'


def test_file_picker_rejects_symlink_ancestors(studio, tmp_path):
    _app, _controller, server, _config = studio
    target = tmp_path / 'target'
    target.mkdir()
    link = tmp_path / 'linked'
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match='Linked'):
        server.list_files(str(link / 'absent'), 'model')


def test_action_receipts_bounded_without_overwriting_earlier_results(studio):
    app, controller, _server, _config = studio
    app.values['INFINI_IMAGE_BACKEND'] = 'off'
    app.values['INFINI_LLM_PROVIDER'] = 'local'
    for index in range(140):
        command(controller, 'validate', str(index))
    assert len(controller.action_results) == 128
    assert '139' in controller.action_results
    assert '12' in controller.action_results
    assert len(controller.notifications) == 64


def test_guarded_start_rechecks_saved_revision_before_launch(studio, monkeypatch):
    import threading
    from infini_local.desktop.settings_interactions import saved_config_revision
    app, controller, _server, config = studio
    config.write_text('INFINI_PROMPT_STYLE=original\n')
    revision = saved_config_revision(config)
    entered, release = threading.Event(), threading.Event()
    def held(**kwargs):
        entered.set()
        release.wait(2)
        raise ConnectionRefusedError()
    app._fetch_health_snapshot = held
    launches = []
    monkeypatch.setattr(controls.subprocess, 'Popen', lambda *args, **kwargs: launches.append(True))
    result = command(controller, 'start', extra={'savedRevision': revision})
    assert entered.wait(1)
    config.write_text('INFINI_PROMPT_STYLE=external-save\n')
    release.set()
    app.drain_until(lambda: result['status'] != 'running')
    assert result['status'] == 'failed'
    assert not launches
    assert config.read_text() == 'INFINI_PROMPT_STYLE=external-save\n'


def test_other_tab_diagnostic_draft_cannot_change_pending_start(studio, monkeypatch):
    import threading
    from infini_local.desktop.settings_interactions import saved_config_revision
    app, controller, _server, config = studio
    config.write_text('INFINI_PROMPT_STYLE=original\n')
    app.values['INFINI_PROMPT_STYLE'] = 'original'
    app.values['INFINI_IMAGE_BACKEND'] = 'off'
    app.values['INFINI_LLM_PROVIDER'] = 'local'
    entered, release = threading.Event(), threading.Event()
    def held(**kwargs):
        entered.set()
        release.wait(2)
        raise ConnectionRefusedError()
    app._fetch_health_snapshot = held
    launches = []
    def launch(*args, **kwargs):
        launches.append(kwargs['env']['INFINI_PROMPT_STYLE'])
        return SimpleNamespace(pid=123456, poll=lambda: None)
    monkeypatch.setattr(controls.subprocess, 'Popen', launch)
    result = command(controller, 'start', 'start', values={'INFINI_PROMPT_STYLE': 'tab-a-launch'}, extra={'savedRevision': saved_config_revision(config)})
    assert entered.wait(1)
    command(controller, 'validate', 'other-tab', values={'INFINI_PROMPT_STYLE': 'tab-b-diagnostic'})
    release.set()
    app.drain_until(lambda: result['status'] != 'running')
    assert result['status'] == 'succeeded'
    assert launches == ['tab-a-launch']
    assert result['savedValues']['INFINI_PROMPT_STYLE'] == 'tab-a-launch'
    assert result['savedRevision'] == saved_config_revision(config)


def test_fixed_offline_guide_route_requires_session(studio):
    _app, _controller, server, _config = studio
    server.start()
    with pytest.raises(urllib.error.HTTPError) as denied:
        urllib.request.urlopen(server.base_url + '/guide')
    assert denied.value.code == 403
    response = urllib.request.urlopen(server.base_url + '/guide?token=' + server.token)
    assert response.status == 200
    content = response.read()
    assert b'<!doctype html>' in content.lower()
    assert b'id="article"' in content


def test_health_uses_saved_target_not_submitted_or_hidden_draft(studio):
    app, controller, _server, config = studio
    config.write_text('INFINI_HOST=127.0.0.1\nINFINI_PORT=5055\n')
    app.values['INFINI_PORT'] = '6066'
    seen = []
    def health(**kwargs):
        seen.append(kwargs['base_url'])
        return {'pid': 123456, 'baseUrl': kwargs['base_url']}
    app._fetch_health_snapshot = health
    app._shutdown_identity_is_safe = lambda snap: True
    app._safe_effective_config = lambda snap: {'cacheDir': 'cache'}
    app._update_applied_config_feedback = lambda *args: setattr(app, 'applied_config', 'Verified')
    result = command(controller, 'health', values={'INFINI_PORT': '7077'})
    app.drain_until(lambda: result['status'] != 'running')
    assert result['status'] == 'succeeded'
    assert seen == ['http://127.0.0.1:5055']
    assert app.values['INFINI_PORT'] == '6066'


def test_transform_receipt_captures_lan_and_restores_controller(studio):
    app, controller, _server, _config = studio
    app.values['INFINI_HOST'] = '127.0.0.1'
    app.values['INFINI_PORT'] = '5055'
    app.lan_enabled = False
    app.user_presets['LAN'] = {'INFINI_HOST': '0.0.0.0', 'INFINI_PORT': '6066', 'INFINI_MP_ASSET_TRANSPORT': 'http'}
    result = command(controller, 'applyPreset', extra={'name': 'Мой: LAN'})
    assert result['values']['INFINI_PORT'] == '6066'
    assert result['lanEnabled'] is True
    assert app.values['INFINI_PORT'] == '5055'
    assert app.values['INFINI_HOST'] == '127.0.0.1'
    assert app.lan_enabled is False


def test_stop_targets_owned_launch_after_saved_port_changes(studio):
    app, controller, _server, config = studio
    config.write_text('INFINI_HOST=127.0.0.1\nINFINI_PORT=6066\n')
    app.values['INFINI_PORT'] = '7077'
    app.proc = SimpleNamespace(pid=123456, poll=lambda: None)
    app._owned_launch_settings = {'INFINI_HOST': '127.0.0.1', 'INFINI_PORT': '5055'}
    app._owned_server_base_url = 'http://127.0.0.1:5055'
    targets = []
    def health(**kwargs):
        targets.append(kwargs['base_url'])
        return {'ok': True, 'pid': 123456, 'generationActivity': {'active': 0, 'waiting': 0, 'accepting': True}}
    app._fetch_health_snapshot = health
    app._shutdown_identity_is_safe = lambda snap: True
    app._safe_effective_config = lambda snap: {'cacheDir': 'cache'}
    app._try_http_shutdown_current_server = lambda **kwargs: (True, '')
    app._wait_until_helper_stops = lambda **kwargs: True
    app._update_applied_config_feedback = lambda *args: None
    result = command(controller, 'stop', values={'INFINI_PORT': '8088'})
    app.drain_until(lambda: result['status'] != 'running')
    assert result['status'] == 'succeeded'
    assert targets == ['http://127.0.0.1:5055']
    assert app.proc is None
    assert app.values['INFINI_PORT'] == '7077'
    assert '6066' in config.read_text()


def test_closed_studio_rejects_actions_during_receipt_grace(studio):
    _app, controller, server, _config = studio
    server.start()
    result = command(controller, 'exitStudio')
    assert result['status'] == 'succeeded'
    request = urllib.request.Request(server.base_url + '/api/action',
        data=json.dumps({'action': 'save', 'values': {}, 'extra': {}}).encode(),
        headers={'X-Infini-Token': server.token, 'Content-Type': 'application/json'})
    with pytest.raises(urllib.error.HTTPError) as closed:
        urllib.request.urlopen(request)
    assert closed.value.code == 409
    assert server.commands.empty()


@pytest.mark.parametrize('validation_fails', [False, True])
def test_validate_restores_multiline_draft(studio, monkeypatch, validation_fails):
    app, controller, _server, config = studio

    key = 'INFINI_SDCPP_LORA_PROMPT_TAGS'
    app.values[key] = original = '<lora:shared:0.1>'
    submitted = '<lora:browser:0.2>\n<lora:draft:0.3>'
    observed = []

    def validate():
        observed.append(app.values[key])
        if validation_fails:
            raise ValueError('validation rejected draft')

    monkeypatch.setattr(app, 'validate_paths', validate)
    if validation_fails:
        with pytest.raises(ValueError, match='validation rejected draft'):
            command(controller, 'validate', values={key: submitted})
    else:
        assert command(controller, 'validate', values={key: submitted})['ok']
    assert observed == [submitted]
    assert app.values[key] == original
    assert app._current_profile_settings()[key] == original
    assert not config.exists()


@pytest.mark.parametrize('action', ['clearLora', 'useLora', 'applyPreset'])
def test_inactive_text_transform_receipts_and_rollback(studio, action):
    app, controller, _server, config = studio
    key = 'INFINI_SDCPP_LORA_PROMPT_TAGS'
    app.values[key] = '<lora:shared:0.1>'
    app.values['INFINI_IMAGE_BACKEND'] = 'off'
    app.values['INFINI_SDCPP_LORA_FILE'] = '/models/chosen.safetensors'
    app.values['INFINI_SDCPP_LORA_WEIGHT'] = '0.2'
    original = app.values[key]
    draft = '<lora:draft:0.3>'
    preset_value = '<lora:preset:0.4>\n<lora:other:0.5>'
    app.user_presets['Inactive text'] = {key: preset_value, 'INFINI_IMAGE_BACKEND': 'off'}
    extra = {'name': 'Мой: Inactive text'} if action == 'applyPreset' else {}
    result = command(controller, action, values={key: draft}, extra=extra)
    expected = {'clearLora': '', 'useLora': draft + ' <lora:chosen:0.2>',
                'applyPreset': preset_value}[action]
    assert result['ok'] is True
    assert result['values'][key] == expected
    assert app.values[key] == original
    assert not config.exists()


def test_inactive_extra_arguments_setter_updates_plain_state(studio):
    app, _controller, _server, _config = studio
    app.values['INFINI_SDCPP_SERVER_EXTRA_ARGS'] = '--old'
    app.update_values({'INFINI_SDCPP_SERVER_EXTRA_ARGS': '--new value'})
    assert app.values['INFINI_SDCPP_SERVER_EXTRA_ARGS'] == '--new value'
