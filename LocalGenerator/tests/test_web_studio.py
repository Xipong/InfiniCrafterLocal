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


def test_published_state_is_a_snapshot_not_an_alias_to_mutable_ui_state(bridge):
    state = {'values': {'a': 'before'}}
    bridge.publish(state)
    state['values']['a'] = 'after'
    assert get_json(bridge)['values']['a'] == 'before'


def test_real_controller_metadata_and_save_preserve_full_setting_surface(tmp_path, monkeypatch):
    module = bridge_module()
    from infini_local.desktop.tk_compat import TKINTER_AVAILABLE, tk
    if not TKINTER_AVAILABLE:
        pytest.skip('Native Tk adapter requires a Tk-capable interpreter')
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip('Native adapter requires a display')
    from infini_local.desktop import settings_gui, settings_gui_trace_state, settings_gui_server_controls
    from infini_local.desktop.settings_env import parse_env
    config = tmp_path / 'config.env'
    config.write_text('INFINI_PRIVATE_UNKNOWN=preserved\nINFINI_LLM_MAX_TOKENS=12345\nINFINI_OPENAI_COMPAT_API_KEY=keep-me\n', encoding='utf-8')
    for owner in (settings_gui, settings_gui_trace_state, settings_gui_server_controls):
        monkeypatch.setattr(owner, 'CONFIG_PATH', config)
    app = settings_gui.SettingsGui()
    app.withdraw()
    server = module.StudioServer(tmp_path)
    try:
        controller = module.StudioController(app, server)
        before = controller.snapshot()
        assert before['configPath'] == str(config)
        assert len(before['fields']) == 129
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
        assert app.vars['INFINI_SPRITE_DOWNSCALE_FILTER'].get() == 'box'
    finally:
        server.close()
        app.destroy()


def test_snapshot_distinguishes_controller_edits_from_persisted_settings(tmp_path, monkeypatch):
    """No Tk/display needed: use the actual bridge and settings file owner."""
    from types import SimpleNamespace
    from infini_local.desktop import settings_gui_trace_state
    from infini_local.desktop.settings_env import write_env, parse_env
    from infini_local.desktop.settings_gui import SettingsGui
    module = bridge_module()
    config = tmp_path / 'config.env'
    write_env(config, {'INFINI_PROMPT_STYLE': 'Default', 'INFINI_OPENAI_COMPAT_API_KEY': 'dummy-old'})
    monkeypatch.setattr(settings_gui_trace_state, 'CONFIG_PATH', config)
    value = lambda text='': SimpleNamespace(get=lambda: text)
    current = parse_env(config)
    app = SimpleNamespace(
        field_widgets={}, pages={}, field_disabled_reasons={}, user_presets={},
        _current_profile_settings=lambda: dict(current), preset_var=value('Custom'),
        status_var=value('Ready'), activity_var=value(), applied_config_var=value(),
        home_state_var=value(), home_detail_var=value(), home_config_var=value(),
        trace_texts={}, _gui_tasks={}, radmin_enabled=value(False),
        codex_catalog_var=value(), codex_image_account_var=value(),
        _pipeline_preset_from_config=SettingsGui._pipeline_preset_from_config,
    )
    controller = module.StudioController(app, None)
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
