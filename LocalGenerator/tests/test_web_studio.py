from __future__ import annotations

import importlib
import json
from pathlib import Path
import queue
import threading
import urllib.error
import urllib.request

import pytest


def bridge_module():
    from importlib.util import find_spec
    assert find_spec('infini_local.desktop.web_studio') is not None, 'Production web Studio bridge is missing'
    return importlib.import_module('infini_local.desktop.web_studio')


@pytest.fixture
def bridge(tmp_path):
    module = bridge_module()
    assets = tmp_path / 'webui'
    assets.mkdir()
    (assets / 'index.html').write_text('<html><head></head><body>real studio</body></html>', encoding='utf-8')
    (assets / 'studio.css').write_text('body{color:black}', encoding='utf-8')
    server = module.StudioServer(assets, port=0)
    server.publish({'values': {'INFINI_OPENAI_COMPAT_API_KEY': 'private-key'}, 'status': 'ready'})
    server.start()
    yield server
    server.close()


def get_json(bridge, route='/api/state', *, token=True):
    request = urllib.request.Request(bridge.base_url + route)
    if token:
        request.add_header('X-Infini-Token', bridge.token)
    return json.load(urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=3))


def test_api_secrets_require_session_capability_and_are_never_in_unauthorized_response(bridge):
    with pytest.raises(urllib.error.HTTPError) as error:
        get_json(bridge, token=False)
    assert error.value.code == 403
    assert b'private-key' not in error.value.read()
    assert get_json(bridge)['values']['INFINI_OPENAI_COMPAT_API_KEY'] == 'private-key'


def test_bootstrap_html_requires_token_and_injects_only_client_session(bridge):
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(bridge.base_url + '/', timeout=3)
    response = urllib.request.urlopen(bridge.url, timeout=3)
    page = response.read().decode()
    assert 'INFINI_BOOTSTRAP' in page and bridge.token in page
    assert 'private-key' not in page
    assert response.headers['Cache-Control'] == 'no-store'


def test_action_http_only_enqueues_and_never_executes_controller_on_worker_thread(bridge):
    owner = threading.get_ident()
    payload = {'action': 'save', 'values': {'INFINI_LLM_PROVIDER': 'local'}, 'extra': {}}
    request = urllib.request.Request(bridge.base_url + '/api/action', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', 'X-Infini-Token': bridge.token}, method='POST')
    response = json.load(urllib.request.urlopen(request, timeout=3))
    assert response['ok'] is True
    command = bridge.commands.get_nowait()
    assert command['action'] == 'save' and command['values'] == payload['values']
    assert threading.get_ident() == owner
    assert bridge.commands.empty()


def test_foreign_origin_unknown_actions_and_path_traversal_are_rejected(bridge):
    request = urllib.request.Request(bridge.base_url + '/api/action', data=b'{"action":"save"}', headers={'X-Infini-Token': bridge.token, 'Origin': 'https://evil.example'}, method='POST')
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request, timeout=3)
    assert error.value.code == 403
    request = urllib.request.Request(bridge.base_url + '/api/action', data=b'{"action":"executePython"}', headers={'X-Infini-Token': bridge.token}, method='POST')
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request, timeout=3)
    assert error.value.code == 400
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(bridge.base_url + '/../../config.env', timeout=3)
    assert bridge.commands.empty()


@pytest.mark.parametrize('action', ['acceptDefaults', 'declineDefaults'])
def test_defaults_decision_is_queued_as_a_dedicated_action(bridge, action):
    payload = {'action': action, 'values': {}, 'extra': {'revision': 'opaque-offer'}}
    request = urllib.request.Request(
        bridge.base_url + '/api/action', data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json', 'X-Infini-Token': bridge.token}, method='POST')
    response = json.load(urllib.request.urlopen(request, timeout=3))
    assert response['ok'] is True
    command = bridge.commands.get_nowait()
    assert command['action'] == action
    assert command['values'] == {}
    assert command['extra'] == {'revision': 'opaque-offer'}


def test_published_state_is_a_snapshot_not_an_alias_to_mutable_ui_state(bridge):
    state = {'values': {'a': 'before'}}
    bridge.publish(state)
    state['values']['a'] = 'after'
    assert get_json(bridge)['values']['a'] == 'before'


def test_real_controller_metadata_and_save_preserve_full_setting_surface(tmp_path, monkeypatch):
    module = bridge_module()
    from infini_local.desktop.settings_controller import SettingsController
    from infini_local.desktop.settings_env import parse_env
    config = tmp_path / 'config.env'
    config.write_text('INFINI_PRIVATE_UNKNOWN=preserved\nINFINI_LLM_MAX_TOKENS=12345\nINFINI_OPENAI_COMPAT_API_KEY=keep-me\n', encoding='utf-8')
    app = SettingsController(config)
    server = module.StudioServer(tmp_path)
    try:
        controller = module.StudioController(app, server)
        before = controller.snapshot()
        assert before['configPath'] == str(config)
        assert len(before['fields']) == 128
        assert 'INFINI_BALANCE_MODE' not in {field['key'] for field in before['fields']}
        assert {field['page'] for field in before['fields']} == {'configure','providers','images','sprites','models','multiplayer','diagnostics'}
        assert next(field for field in before['fields'] if field['key'] == 'INFINI_OPENAI_COMPAT_API_KEY')['secret'] is True
        controller.apply({'id':'save-proof','action':'save','values':{'INFINI_PROMPT_STYLE':'Terraria Like'},'extra':{}})
        saved = parse_env(config)
        assert saved['INFINI_PRIVATE_UNKNOWN'] == 'preserved'
        assert saved['INFINI_OPENAI_COMPAT_API_KEY'] == 'keep-me'
        assert saved['INFINI_LLM_MAX_TOKENS'] == '12345'
        assert saved['INFINI_PROMPT_STYLE'] == 'Terraria Like'
        assert controller.last_action['ok'] is True
        controller.apply({'id':'unknown-edit','action':'save','values':{'INFINI_PRIVATE_UNKNOWN':'edited-explicitly'},'extra':{}})
        assert parse_env(config)['INFINI_PRIVATE_UNKNOWN'] == 'edited-explicitly'
        controller.apply({'id':'reset-proof','action':'resetSprite','values':{},'extra':{}})
        assert controller.action_results['reset-proof']['values']['INFINI_SPRITE_DOWNSCALE_FILTER'] == 'box'
        # Browser drafts intentionally allow editing inactive provider settings.
        # Disabled controls must not discard explicit browser draft edits.
        key = 'INFINI_SDCPP_LORA_PROMPT_TAGS'
        for index, backend in enumerate(('off', 'sdcpp', 'off', 'off')):
            app.update_values({'INFINI_IMAGE_BACKEND': backend})
            app._refresh_visibility()
            assert (not app.field_disabled_reasons.get(key)) == (backend == 'sdcpp')
            tags = f'<lora:a:{index}.2>\n<lora:b:{index}.3>' if index != 3 else ''
            identifier = f'inactive-text-{index}'
            controller.apply({'id': identifier, 'action': 'save',
                              'values': {key: tags}, 'extra': {}})
            receipt = controller.action_results[identifier]
            assert receipt['ok'] is True
            assert app.values[key] == tags
            assert (not app.field_disabled_reasons.get(key)) == (backend == 'sdcpp')
            assert parse_env(config)[key] == tags
            assert receipt['savedValues'][key] == tags
            assert controller.snapshot()['savedValues'][key] == tags
    finally:
        server.close()
        app.on_close()


def test_real_controller_defaults_consent_only_updates_offer_keys(tmp_path, monkeypatch):
    from infini_local.desktop.settings_controller import SettingsController
    from infini_local.desktop.settings_schema import DEFAULTS
    from infini_local.desktop.settings_env import parse_env
    monkeypatch.setitem(DEFAULTS, 'INFINI_LLM_MAX_TOKENS', '18000')
    config = tmp_path / 'config.env'
    original = (b'# isolated consent proof\r\nINFINI_LLM_MAX_TOKENS=9000\r\n'
                b'INFINI_USE_LLM=0\r\nINFINI_IMAGE_BACKEND=off\r\n'
                b'INFINI_SDCPP_SERVER_AUTOSTART=0\r\nINFINI_LLM_PROVIDER=local\r\n'
                b'INFINI_OPENAI_COMPAT_API_KEY=opaque-fixture\r\nINFINI_PRIVATE_UNKNOWN=keep\r\n'
                b'INFINI_SDCPP_MODEL=C:\\Models\\keep.gguf\r\nINFINI_PROMPT_STYLE=Default\r\n'
                b'INFINI_CACHE_DIR=' + str(tmp_path / 'cache').encode() + b'\r\n')
    config.write_bytes(original)
    app = SettingsController(config)
    server = bridge_module().StudioServer(tmp_path)
    try:
        controller = bridge_module().StudioController(app, server)
        before = controller.snapshot()
        assert 'defaultsUpdate' in before, 'Studio snapshots must carry the consent offer'
        offer = before['defaultsUpdate']
        assert {row['key'] for row in offer['changes']} == {'INFINI_LLM_MAX_TOKENS'}
        assert config.read_bytes() == original
        app.update_values({'INFINI_PROMPT_STYLE': 'Unsaved controller draft'})
        preset = app.preset
        baseline = dict(app._profile_baseline)
        def forbidden(*_args, **_kwargs):
            pytest.fail('Defaults decisions must not save/collect/capture the entire draft')
        monkeypatch.setattr(app, 'save', forbidden)
        monkeypatch.setattr(app, 'collect', forbidden)
        monkeypatch.setattr(app, '_capture_profile_baseline', forbidden)
        app.lan_enabled = False
        controller.apply({'id': 'accept-offer', 'action': 'acceptDefaults',
                          'values': {'INFINI_PRIVATE_UNKNOWN': 'malicious-draft', 'INFINI_PROMPT_STYLE': 'sent-draft'},
                          'extra': {'revision': offer['revision'], 'lanEnabled': True}})
        assert config.read_bytes() == original.replace(b'9000', b'18000')
        assert app.values['INFINI_LLM_MAX_TOKENS'] == '18000'
        assert app.values['INFINI_LLM_MAX_TOKENS'] == '18000'
        assert app.values['INFINI_PROMPT_STYLE'] == 'Unsaved controller draft'
        assert app.values['INFINI_PRIVATE_UNKNOWN'] == 'keep'
        assert app.lan_enabled is False
        assert app.preset == preset
        assert app._profile_baseline == baseline
        assert parse_env(config)['INFINI_PROMPT_STYLE'] == 'Default'
        assert controller.last_action['ok'] is True
    finally:
        server.close()
        app.on_close()


@pytest.mark.parametrize('fresh_install', [False, True])
def test_snapshot_distinguishes_controller_edits_from_persisted_settings(tmp_path, monkeypatch, fresh_install):
    """No Tk/display needed: use the actual bridge and settings file owner."""
    from infini_local.desktop.settings_env import write_env, parse_env
    from infini_local.desktop.settings_controller import SettingsController
    module = bridge_module()
    config = tmp_path / 'config.env'
    example = tmp_path / 'config.example.env'
    initial = {'INFINI_PROMPT_STYLE': 'Default', 'INFINI_OPENAI_COMPAT_API_KEY': 'dummy-old',
               'INFINI_SDCPP_SERVER_AUTOSTART': '0', 'INFINI_SDCPP_SERVER_EXE': ''}
    write_env(example, initial)
    if not fresh_install:
        # Existing personal config wins even when it differs from the example.
        write_env(config, dict(initial, INFINI_SDCPP_SERVER_EXE='personal-sd-server'))
    app = SettingsController(config, example_path=example)
    current = app.values
    controller = module.StudioController(app, None)
    initial_snapshot = controller.snapshot()
    from infini_local.core.config_bootstrap import APP_VERSION
    assert initial_snapshot['version'] == APP_VERSION
    assert initial_snapshot['fieldHelp']['INFINI_LLM_TIMEOUT']
    assert initial_snapshot['fieldHelp']['INFINI_VFX_LLM_DIRECTOR_MAX_TOKENS']
    assert initial_snapshot['values'] == initial_snapshot['savedValues']
    assert config.exists() is not fresh_install
    current.update(INFINI_PROMPT_STYLE='Terraria Like', INFINI_OPENAI_COMPAT_API_KEY='dummy-new')
    unsaved = controller.snapshot()
    assert unsaved['values']['INFINI_PROMPT_STYLE'] == 'Terraria Like'
    assert unsaved['savedValues']['INFINI_PROMPT_STYLE'] == 'Default'
    assert unsaved['savedValues']['INFINI_OPENAI_COMPAT_API_KEY'] == 'dummy-old'
    # A fresh browser/controller snapshot still distinguishes a prepared profile
    # or non-saving action from a real write; no localStorage carries credentials.
    assert module.StudioController(app, None).snapshot()['savedValues'] == unsaved['savedValues']
    write_env(config, current)
    saved = controller.snapshot()
    assert saved['savedValues']['INFINI_PROMPT_STYLE'] == 'Terraria Like'
    assert saved['savedValues']['INFINI_OPENAI_COMPAT_API_KEY'] == 'dummy-new'
    current['INFINI_PROMPT_STYLE'] = 'Default'
    assert controller.snapshot()['savedValues']['INFINI_PROMPT_STYLE'] == 'Terraria Like'
    from infini_local.desktop import settings_env
    def unreadable(_path):
        raise PermissionError('test config is temporarily unreadable')
    monkeypatch.setattr(settings_env, 'parse_env', unreadable)
    failed_read = controller.snapshot()
    assert failed_read['savedValues'] == saved['savedValues']
    assert 'temporarily unreadable' in failed_read['status']
    for parse_error in (ValueError('Invalid config.env JSON at line 2'), UnicodeError('Invalid UTF-8 config.env')):
        def malformed(_path, error=parse_error):
            raise error
        monkeypatch.setattr(settings_env, 'parse_env', malformed)
        bad_snapshot = controller.snapshot()
        assert bad_snapshot['savedValues'] == saved['savedValues']
        assert str(parse_error) in bad_snapshot['status']
    monkeypatch.setattr(settings_env, 'parse_env', unreadable)
    from infini_local.desktop import settings_defaults
    monkeypatch.setattr(settings_defaults, 'defaults_offer', unreadable)
    failed_offer = controller.snapshot()
    assert failed_offer['savedValues'] == saved['savedValues']
    assert failed_offer['defaultsUpdate']['changes'] == []
    assert 'temporarily unreadable' in failed_offer['status']


@pytest.mark.parametrize('error', [ValueError('Invalid config.env JSON at line 2'), UnicodeError('Invalid UTF-8 config.env')])
def test_studio_startup_reports_malformed_config_without_starting_server(monkeypatch, error):
    module = bridge_module()
    from infini_local.desktop import settings_controller

    def malformed():
        raise error

    def unexpected_server(*args, **kwargs):
        pytest.fail('Studio must not start with fabricated settings after a parse error')

    monkeypatch.setattr(settings_controller, 'SettingsController', malformed)
    monkeypatch.setattr(module, 'StudioServer', unexpected_server)
    with pytest.raises(SystemExit, match='config.env') as failure:
        module.main(['--no-browser'])
    assert str(error) in str(failure.value)
    assert 'редакторе' in str(failure.value)
