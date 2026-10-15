"""Live headless control-plane security and concurrency regressions."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request

import pytest


@pytest.fixture
def studio(tmp_path, monkeypatch):
    from infini_local.desktop.settings_controller import SettingsController
    from infini_local.desktop.web_studio import StudioController, StudioServer
    from infini_local.desktop.settings_env import write_env
    from infini_local.services import codex_auth
    monkeypatch.setattr(codex_auth, 'auth_status', lambda: {'authenticated': False})
    monkeypatch.delenv('DISPLAY', raising=False)
    config = tmp_path / 'config.env'
    write_env(config, {'INFINI_USE_LLM': '0', 'INFINI_IMAGE_BACKEND': 'off',
                      'INFINI_SDCPP_SERVER_AUTOSTART': '0', 'INFINI_CACHE_DIR': str(tmp_path / 'cache'),
                      'INFINI_OPENAI_COMPAT_API_KEY': 'isolated-fixture-secret'})
    app = SettingsController(config_path=config)
    server = StudioServer(Path(__file__).parents[1] / 'infini_local/desktop/webui')
    controller = StudioController(app, server)
    server.publish(controller.snapshot())
    server.start()
    try:
        yield app, controller, server, config
    finally:
        app.on_close()
        server.close()


def request(server, path, payload=None, headers=None):
    headers = {'X-Infini-Token': server.token, **(headers or {})}
    data = json.dumps(payload).encode() if payload is not None else None
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(server.base_url + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def test_controller_constructs_and_snapshots_when_tk_import_is_forbidden(tmp_path):
    script = '''
import sys
from pathlib import Path
class NoTk:
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ('tkinter', '_tkinter') or fullname.startswith('tkinter.'):
            raise AssertionError('Unexpected toolkit import: ' + fullname)
sys.meta_path.insert(0, NoTk())
from infini_local.services import codex_auth
codex_auth.auth_status = lambda: {'authenticated': False}
from infini_local.desktop.settings_controller import SettingsController
from infini_local.desktop.web_studio import StudioController, StudioServer
config = Path(sys.argv[1])
config.write_text('INFINI_USE_LLM=0\\nINFINI_IMAGE_BACKEND=off\\nINFINI_SDCPP_SERVER_AUTOSTART=0\\n')
app = SettingsController(config_path=config)
server = StudioServer(Path(sys.argv[2]))
try:
    controller = StudioController(app, server)
    assert controller.snapshot()['fields']
    app.after(0, controller.tick)
    app.pump()
    assert server._state['fields']
finally:
    app.on_close()
    server.close()
'''
    env = dict(os.environ)
    env.pop('DISPLAY', None)
    root = Path(__file__).parents[1]
    env['PYTHONPATH'] = str(root)
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path / 'config.env'),
                             str(root / 'infini_local/desktop/webui')], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_live_http_guards_and_concurrent_receipts(studio):
    _app, controller, server, _config = studio
    for headers in ({'X-Infini-Token': ''}, {'Origin': 'https://foreign.example'}, {'Host': 'foreign.example'}):
        status, body = request(server, '/api/state', headers=headers)
        assert status == 403
        assert 'isolated-fixture-secret' not in json.dumps(body)
    assert request(server, '/api/files?path=%2F%2Fserver%2Fshare')[0] == 400
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: request(server, '/api/action', {'action': 'openConfig'}), range(12)))
    assert all(status == 202 for status, _ in results)
    identifiers = {body['id'] for _, body in results}
    assert len(identifiers) == 12
    controller.tick()
    controller.tick()
    for identifier in identifiers:
        receipt = controller.action_results[identifier]
        assert receipt['status'] == 'succeeded'
        assert 'isolated-fixture-secret' not in receipt['result']['content']


@pytest.mark.parametrize('cancel_login', [False, True])
def test_oauth_timeout_or_cancel_retires_receipt_without_live_auth(studio, monkeypatch, cancel_login):
    import threading
    import time
    from infini_local.services import codex_auth
    app, controller, _server, _config = studio
    entered = threading.Event()

    def fake_login(*, cancel):
        entered.set()
        if cancel_login:
            assert cancel.wait(2), 'Logout failed to signal cancellation'
            raise codex_auth.CodexError('Fixture login cancelled')
        raise codex_auth.CodexError('Fixture login timed out')

    monkeypatch.setattr(codex_auth, 'login', fake_login)
    monkeypatch.setattr(codex_auth, 'logout', lambda: pytest.fail('Cancelling a pending login must not delete a session'))
    controller.apply({'id': 'login', 'action': 'codexLogin', 'values': {}, 'extra': {}})
    assert entered.wait(1)
    assert controller.action_results['login']['status'] == 'running'
    if cancel_login:
        controller.apply({'id': 'cancel', 'action': 'codexLogout', 'values': {}, 'extra': {}})
    deadline = time.monotonic() + 3
    while app._codex_login_running and time.monotonic() < deadline:
        app.pump()
        time.sleep(0.01)
    assert not app._codex_login_running
    receipt = controller.action_results['login']
    assert receipt['status'] == 'failed'
    assert ('cancelled' if cancel_login else 'timed out') in receipt['message']
    assert not app._studio_async_ids
