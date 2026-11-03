"""Native-folder action uses the existing receipt loop, never saves a draft."""
from pathlib import Path
import sys
import types

import pytest


@pytest.fixture
def picker_studio(tmp_path, monkeypatch):
    from infini_local.desktop.settings_controller import SettingsController
    from infini_local.desktop.web_studio import StudioController, StudioServer
    config = tmp_path / 'override config.env'
    config.write_text('INFINI_USE_LLM=0\nINFINI_IMAGE_BACKEND=off\n', encoding='utf-8')
    app = SettingsController(config_path=config)
    server = StudioServer(Path(__file__).parents[1] / 'infini_local/desktop/webui')
    server.file_root = tmp_path
    controller = StudioController(app, server)
    callbacks = []
    monkeypatch.setattr(app, 'after', lambda delay, callback: callbacks.append(callback))
    chosen = tmp_path / 'Selected folder Юникод'; chosen.mkdir()
    calls = []
    native = types.SimpleNamespace(is_available=lambda: True, choose_folder=lambda initial: calls.append(initial) or str(chosen))
    monkeypatch.setitem(sys.modules, 'infini_local.desktop.windows_folder_picker', native)
    try:
        yield app, controller, server, config, native, chosen, calls, callbacks
    finally:
        app.on_close(); server.close()


def finish_picker(app, callbacks):
    # Synchronize on the actual worker delivery, not an arbitrary sleep.
    task = app._gui_tasks['native-folder-picker']
    delivered = task['results'].get(timeout=5)
    task['results'].put_nowait(delivered)
    callbacks.pop(0)()


def test_native_folder_action_returns_only_selected_field_and_preserves_config(picker_studio):
    app, controller, server, config, native, chosen, calls, callbacks = picker_studio
    before, values = config.read_bytes(), dict(app.values)
    controller.apply({'id': 'folder-1', 'action': 'browse',
                      'values': {'INFINI_LLM_MAX_TOKENS': '999'},
                      'extra': {'key': 'INFINI_SDCPP_ROCM_COMPAT_ROOT', 'path': str(chosen.parent)}})
    finish_picker(app, callbacks)
    receipt = controller.action_results['folder-1']
    assert receipt['status'] == 'succeeded'
    assert receipt['result'] == {'kind': 'folderSelection', 'key': 'INFINI_SDCPP_ROCM_COMPAT_ROOT', 'path': str(chosen)}
    assert calls == [str(chosen.parent)]
    assert app.values == values and config.read_bytes() == before
    assert 'savedValues' not in receipt and 'values' not in receipt


@pytest.mark.parametrize('outcome', ['cancel', 'error', 'missing', 'network'])
def test_cancel_and_failed_selection_leave_draft_and_disk_untouched(picker_studio, outcome):
    app, controller, server, config, native, chosen, calls, callbacks = picker_studio
    def choose(initial):
        if outcome == 'error': raise OSError('private OS detail')
        return {'cancel': None, 'missing': str(chosen / 'no such folder'), 'network': '//untrusted/share'}[outcome]
    native.choose_folder = choose
    before, values = config.read_bytes(), dict(app.values)
    controller.apply({'id': 'failure', 'action': 'browse', 'values': {'INFINI_PORT': '7'},
                      'extra': {'key': 'INFINI_SDCPP_ROCM_COMPAT_ROOT', 'path': ''}})
    finish_picker(app, callbacks)
    receipt = controller.action_results['failure']
    assert receipt['status'] == ('cancelled' if outcome == 'cancel' else 'failed')
    assert 'result' not in receipt and 'private OS detail' not in receipt['message']
    assert app.values == values and config.read_bytes() == before


def test_busy_dialog_is_not_duplicated_and_missing_initial_uses_existing_parent(picker_studio):
    import threading
    app, controller, server, config, native, chosen, calls, callbacks = picker_studio
    entered, release = threading.Event(), threading.Event()
    def choose(initial):
        calls.append(initial); entered.set()
        assert release.wait(5)
        return str(chosen)
    native.choose_folder = choose
    command = {'id': 'first', 'action': 'browse', 'values': {},
               'extra': {'key': 'INFINI_SDCPP_ROCM_COMPAT_ROOT', 'path': str(chosen / 'missing/child')}}
    try:
        controller.apply(command); assert entered.wait(5)
        with pytest.raises(ValueError, match='уже открыто'):
            controller.apply({**command, 'id': 'duplicate'})
        assert calls == [str(chosen)]
        assert controller.action_results['first']['status'] == 'running'
    finally:
        release.set(); finish_picker(app, callbacks)
    assert controller.action_results['first']['status'] == 'succeeded'
    assert controller.action_results['duplicate']['status'] == 'failed'
    controller.apply({**command, 'id': 'repeat'})
    finish_picker(app, callbacks)
    assert controller.action_results['repeat']['status'] == 'succeeded' and len(calls) == 2


@pytest.mark.parametrize('extra', [
    {'key': 'INFINI_PORT'}, {'key': 'INFINI_OPENAI_COMPAT_API_KEY'},
    {'key': 'INFINI_INVENTED_ROOT'}, {'key': 'INFINI_SDCPP_ROCM_COMPAT_ROOT', 'path': '//host/share'},
])
def test_native_picker_rejects_unregistered_fields_and_network_initial_before_os(picker_studio, extra):
    app, controller, server, config, native, chosen, calls, callbacks = picker_studio
    before = dict(app.values)
    with pytest.raises(ValueError):
        controller.apply({'id': 'invalid', 'action': 'browse', 'values': {'INFINI_PORT': '7'}, 'extra': extra})
    assert calls == [] and not app._gui_tasks and app.values == before


def test_non_windows_keeps_browser_picker_and_does_not_start_os_worker(picker_studio):
    app, controller, server, config, native, chosen, calls, callbacks = picker_studio
    native.is_available = lambda: False
    with pytest.raises(ValueError, match='Windows'):
        controller.apply({'id': 'unsupported', 'action': 'browse', 'values': {},
                          'extra': {'key': 'INFINI_SDCPP_ROCM_COMPAT_ROOT'}})
    assert calls == [] and not app._gui_tasks


def test_shutdown_never_applies_late_worker_selection(picker_studio):
    import threading
    app, controller, server, config, native, chosen, calls, callbacks = picker_studio
    entered, release = threading.Event(), threading.Event()
    def choose(initial):
        entered.set(); assert release.wait(5)
        return str(chosen)
    native.choose_folder = choose
    before = config.read_bytes()
    try:
        controller.apply({'id': 'closing', 'action': 'browse', 'values': {},
                          'extra': {'key': 'INFINI_SDCPP_ROCM_COMPAT_ROOT'}})
        assert entered.wait(5)
        app.on_close()
        assert app._gui_closed
    finally:
        release.set()
        task = app._gui_tasks.get('native-folder-picker')
        if task is not None:
            task['results'].get(timeout=5)
        for callback in callbacks: callback()
    assert controller.action_results['closing']['status'] != 'succeeded'
    assert config.read_bytes() == before


def test_folder_action_requires_session_token_before_queueing_os_request(picker_studio):
    import json
    import urllib.error
    import urllib.request
    app, controller, server, config, native, chosen, calls, callbacks = picker_studio
    server.start()
    payload = json.dumps({'action': 'browse', 'values': {},
                          'extra': {'key': 'INFINI_SDCPP_ROCM_COMPAT_ROOT', 'path': str(chosen)}}).encode()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(token):
        return urllib.request.Request(server.base_url + '/api/action', data=payload,
            headers={'Content-Type': 'application/json', 'X-Infini-Token': token})
    with pytest.raises(urllib.error.HTTPError) as error:
        opener.open(request('not-the-session-token'), timeout=3)
    assert error.value.code == 403 and server.commands.empty() and calls == []
    with opener.open(request(server.token), timeout=3) as response:
        queued = json.load(response)
    controller.apply(server.commands.get(timeout=3)); finish_picker(app, callbacks)
    assert controller.action_results[queued['id']]['result']['path'] == str(chosen)
    assert calls == [str(chosen)]
