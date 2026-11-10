"""Onboarding progress is isolated, validated, and durable without saving drafts."""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pytest


DEFAULT_PROGRESS = {'version': 1, 'seen': False, 'step': 0, 'completed': False}


def owner():
    return importlib.import_module('infini_local.desktop.studio_onboarding')


def sidecar(config):
    return config.with_name(config.name + '.studio.json')


def test_missing_progress_is_fresh_without_creating_files(tmp_path):
    config = tmp_path / 'config.env'
    assert owner().load_progress(config) == DEFAULT_PROGRESS
    assert list(tmp_path.iterdir()) == []
    # Callers cannot mutate the default for the next browser session.
    progress = owner().load_progress(config)
    progress['seen'] = True
    assert owner().load_progress(config) == DEFAULT_PROGRESS


def test_progress_round_trip_and_completion_never_regresses(tmp_path):
    config = tmp_path / 'config.env'
    original = b'# untouched config\r\nINFINI_PRIVATE_UNKNOWN=keep\r\n'
    config.write_bytes(original)
    for step in range(5):
        result = owner().save_progress(config, {'step': step})
        assert result == {'version': 1, 'seen': True, 'step': step, 'completed': False}
        assert owner().load_progress(config) == result
        assert json.loads(sidecar(config).read_text(encoding='utf-8')) == result
    complete = owner().save_progress(config, {'step': 4, 'completed': True})
    assert complete['completed'] is True
    for update in ({'step': 0}, {'step': 2, 'completed': False}):
        result = owner().save_progress(config, update)
        assert result == {'version': 1, 'seen': True, 'step': update['step'], 'completed': True}
        assert owner().load_progress(config) == result
    assert config.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ['config.env', 'config.env.studio.json']


@pytest.mark.parametrize('update', [
    None, [], '2', {}, {'step': -1}, {'step': 5}, {'step': True},
    {'step': False}, {'step': 1.0}, {'step': '1'}, {'step': None},
    {'step': 1, 'completed': 1}, {'step': 1, 'completed': 'true'},
    {'step': 1, 'completed': None}, {'step': 1, 'seen': False},
    {'step': 1, 'version': 2}, {'step': 1, 'unexpected': 'ignored?'},
])
def test_invalid_updates_refused_without_touching_persisted_progress(tmp_path, update):
    config = tmp_path / 'config.env'
    owner().save_progress(config, {'step': 3})
    before = sidecar(config).read_bytes()
    with pytest.raises(ValueError):
        owner().save_progress(config, update)
    assert sidecar(config).read_bytes() == before


@pytest.mark.parametrize('content', [
    b'{broken', b'[]', b'null', b'"text"', b'\xff\xfe',
    json.dumps({'version': 2, 'seen': True, 'step': 2, 'completed': False}).encode(),
    json.dumps({'version': 1, 'seen': 'true', 'step': 2, 'completed': False}).encode(),
    json.dumps({'version': 1, 'seen': True, 'step': True, 'completed': False}).encode(),
    json.dumps({'version': 1, 'seen': True, 'step': 5, 'completed': False}).encode(),
    json.dumps({'version': 1, 'seen': True, 'step': 2, 'completed': 1}).encode(),
])
def test_malformed_progress_is_a_fresh_session_and_is_not_rewritten(tmp_path, content):
    config = tmp_path / 'config.env'
    sidecar(config).write_bytes(content)
    assert owner().load_progress(config) == DEFAULT_PROGRESS
    assert sidecar(config).read_bytes() == content


def test_unreadable_progress_is_a_fresh_session(tmp_path):
    config = tmp_path / 'config.env'
    # Deterministic unreadable path even when tests run as root.
    sidecar(config).mkdir()
    assert owner().load_progress(config) == DEFAULT_PROGRESS
    assert sidecar(config).is_dir()


def test_atomic_replacement_failure_keeps_old_progress_and_cleans_temporary_file(tmp_path, monkeypatch):
    config = tmp_path / 'config.env'
    previous = owner().save_progress(config, {'step': 1})
    persisted = sidecar(config).read_bytes()
    attempts = []
    real_replace = os.replace

    def fail_replacement(source, target, *args, **kwargs):
        if Path(target) == sidecar(config):
            attempts.append((Path(source), Path(target)))
            assert Path(source) != Path(target)
            assert Path(source).parent == Path(target).parent
            assert json.loads(Path(source).read_text(encoding='utf-8'))['step'] == 3
            assert Path(target).read_bytes() == persisted
            raise OSError('simulated disk replacement failure')
        return real_replace(source, target, *args, **kwargs)

    monkeypatch.setattr(os, 'replace', fail_replacement)
    with pytest.raises(OSError, match='simulated disk replacement failure'):
        owner().save_progress(config, {'step': 3})
    assert len(attempts) == 1
    assert sidecar(config).read_bytes() == persisted
    assert owner().load_progress(config) == previous
    assert list(tmp_path.iterdir()) == [sidecar(config)]


@pytest.fixture
def studio(tmp_path, monkeypatch):
    from infini_local.desktop.settings_controller import SettingsController
    from infini_local.desktop.settings_env import write_env
    from infini_local.desktop.web_studio import StudioController, StudioServer
    from infini_local.services import codex_auth

    monkeypatch.setattr(codex_auth, 'auth_status', lambda: {'authenticated': False})
    config = tmp_path / 'config.env'
    write_env(config, {'INFINI_USE_LLM': '0', 'INFINI_IMAGE_BACKEND': 'off',
                      'INFINI_SDCPP_SERVER_AUTOSTART': '0',
                      'INFINI_CACHE_DIR': str(tmp_path / 'cache'),
                      'INFINI_OPENAI_COMPAT_API_KEY': 'isolated-fixture-secret'})
    app = SettingsController(config_path=config)
    server = StudioServer(tmp_path)
    try:
        yield StudioController(app, server), app, config
    finally:
        app.on_close()
        server.close()


def test_bridge_persists_progress_without_adopting_or_saving_config_draft(studio):
    controller, app, config = studio
    assert controller.snapshot()['onboarding'] == DEFAULT_PROGRESS
    persisted = config.read_bytes()
    values, lan = dict(app.values), app.lan_enabled
    controller.apply({'id': 'intro-step', 'action': 'onboardingProgress',
                      'values': {'INFINI_OPENAI_COMPAT_API_KEY': 'injected',
                                 'INFINI_PROMPT_STYLE': 'Injected draft'},
                      'extra': {'step': 2, 'completed': False}})
    expected = {'version': 1, 'seen': True, 'step': 2, 'completed': False}
    assert controller.snapshot()['onboarding'] == expected
    assert owner().load_progress(config) == expected
    assert app.actions.results['intro-step']['ok'] is True
    assert app.values == values
    assert app.lan_enabled == lan
    assert config.read_bytes() == persisted


def test_bridge_invalid_progress_has_failure_receipt_and_does_not_adopt_draft(studio):
    controller, app, config = studio
    persisted = config.read_bytes()
    values, lan = dict(app.values), app.lan_enabled
    with pytest.raises(ValueError):
        controller.apply({'id': 'bad-intro', 'action': 'onboardingProgress',
                          'values': {'INFINI_OPENAI_COMPAT_API_KEY': 'injected'},
                          'extra': {'step': 99, 'lanEnabled': not lan}})
    assert app.actions.results['bad-intro']['ok'] is False
    assert app.values == values
    assert app.lan_enabled == lan
    assert config.read_bytes() == persisted
    assert not sidecar(config).exists()


def test_shipped_onboarding_frontend_behavior():
    import shutil
    import subprocess
    from suite_paths import REPO_ROOT
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed to exercise the shipped JavaScript controller')
    result = subprocess.run([node, str(REPO_ROOT / 'tests/generator/studio_onboarding_frontend.cjs')],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'Onboarding frontend behavior passed' in result.stdout


def test_guide_progress_does_not_hide_previous_runtime_failure(studio):
    controller, app, config = studio
    identifier = app.actions.start({'id': 'failed-start', 'action': 'start'})
    app.actions.finish(identifier, False, 'Generator could not bind its port')
    failure = dict(app.actions.last_action)
    controller.apply({'id': 'guide-after-failure', 'action': 'onboardingProgress',
                      'values': {}, 'extra': {'step': 1}})
    assert app.actions.results['guide-after-failure']['ok'] is True
    assert owner().load_progress(config)['step'] == 1
    assert app.actions.last_action == failure
    assert controller.snapshot()['lastAction'] == failure


def test_latest_queued_progress_survives_earlier_post_failure(tmp_path):
    import shutil
    import subprocess
    from suite_paths import GENERATOR_ROOT
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed to exercise the shipped JavaScript controller')
    harness = tmp_path / 'onboarding-post-failure.cjs'
    harness.write_text(r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const events = {}, requests = [], body = {};
const target = {focus(){}, scrollTop:0, textContent:''};
const launcher = {focus(){}, isConnected:true};
const dialog = {
  open:false, querySelector(){return target;},
  showModal(){this.open=true;}, close(){this.open=false;events.close();},
  contains(){return false;}, addEventListener(name, handler){events[name]=handler;}
};
const document = {body, activeElement:body, documentElement:{lang:'en'},
  querySelector(selector){return selector==='#onboarding-dialog' ? dialog :
    selector==='#onboarding-launcher' ? launcher : dialog.open ? dialog : null;}};
const sandbox = {window:{}, document};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'), sandbox);
let rejectFirst;
const api = async(url, payload) => {
  requests.push(JSON.parse(JSON.stringify(payload)));
  if(requests.length===1) await new Promise((resolve,reject)=>{rejectFirst=reject;});
  return {ok:true,id:String(requests.length)};
};
const owner=sandbox.window.InfiniOnboarding.create({api, state:{shutdown:false,dirty:new Set(),lan:false,baselineLan:false},
  value:()=>'', focusField(){}, navigateTo(){}});
const remote={onboarding:{seen:false,step:0,completed:false},actionResults:[]};
const click=(dataset={},attributes=[])=>events.click({target:{closest(){return {
  dataset,hasAttribute:name=>attributes.includes(name)};}}});
(async()=>{
  owner.sync(remote);
  await click({onboardingStep:'4'});
  await click({},['data-onboarding-next']);
  assert.equal(dialog.open,false);
  assert.equal(requests.length,1);
  rejectFirst(Error('temporary transport failure'));
  await new Promise(resolve=>setImmediate(resolve));
  owner.sync(remote);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(requests.length,2,'Send the newer queued user update after the earlier POST fails');
  assert.deepEqual(requests[1],{action:'onboardingProgress',values:{},extra:{step:4,completed:true}});
})().catch(error=>{console.error(error);process.exitCode=1;});
''', encoding='utf-8')
    result = subprocess.run([node, str(harness),
                             str(GENERATOR_ROOT / 'infini_local/desktop/webui/studio-onboarding.js')],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(('system', 'machine', 'asset', 'executable'), [
    ('Linux', 'x86_64', 'sd-bin-linux-x64-vulkan.zip', 'sd-server'),
    ('Windows', 'AMD64', 'sd-bin-win-x64-vulkan.zip', 'sd-server.exe'),
])
def test_installer_http_requires_session_and_never_adopts_browser_draft(studio, monkeypatch, system, machine, asset, executable):
    import hashlib
    import io
    import urllib.error
    import urllib.request
    import zipfile
    from infini_local.desktop import studio_sdcpp_install as installer_owner

    controller, app, config = studio
    server = controller.server
    calls = []
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as package:
        package.writestr(f'bin/{executable}', b'fixture executable never run')
    data = archive.getvalue()
    url = f'https://github.com/leejet/stable-diffusion.cpp/releases/download/test/{asset}'
    metadata = {'tag_name': 'test', 'assets': [{'id': 42, 'name': asset,
        'browser_download_url': url, 'size': len(data), 'digest': 'sha256:' + hashlib.sha256(data).hexdigest()}]}
    def download(target):
        calls.append(target)
        return io.BytesIO(json.dumps(metadata).encode() if target == installer_owner.CATALOG_URL else data)
    monkeypatch.setattr(installer_owner, '_open_url', download)
    from types import SimpleNamespace
    monkeypatch.setattr(installer_owner, 'host_platform', SimpleNamespace(system=lambda: system, machine=lambda: machine))
    before, draft = config.read_bytes(), dict(app.values)
    controller.snapshot()
    assert calls == [], 'Opening Studio must not contact GitHub'
    server.start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def post(action, extra=None, headers=None):
        payload = {'action': action, 'extra': extra or {}, 'values': {'INFINI_PROMPT_STYLE': 'must not be adopted'}}
        request = urllib.request.Request(server.base_url + '/api/action', data=json.dumps(payload).encode(),
            headers=headers if headers is not None else {'X-Infini-Token': server.token}, method='POST')
        return json.load(opener.open(request, timeout=3))
    for headers in ({}, {'X-Infini-Token': server.token, 'Origin': 'https://evil.example'}):
        with pytest.raises(urllib.error.HTTPError) as error:
            post('sdCatalog', headers=headers)
        assert error.value.code == 403
    assert server.commands.empty() and calls == []
    failure = dict(app.actions.last_action)
    for action, extra in [('sdCatalog', {}), ('sdInstall', {'buildId': '42'})]:
        result = post(action, extra)
        command = server.commands.get_nowait()
        assert command['id'] == result['id']
        controller.apply(command)
        controller.installer._thread.join(3)
        assert not controller.installer._thread.is_alive()
        assert app.actions.results[result['id']]['ok']
    state = controller.snapshot()['sdcppInstall']
    assert state['status'] == 'installed'
    assert Path(state['installedPath']).read_bytes() == b'fixture executable never run'
    assert calls == [installer_owner.CATALOG_URL, url]
    assert config.read_bytes() == before and app.values == draft
    assert app.actions.last_action == failure


@pytest.mark.parametrize(('action', 'extra'), [
    ('sdCatalog', {'url': 'https://evil.example'}),
    ('sdInstall', {'buildId': '1', 'path': '/tmp/elsewhere'}),
    ('sdInstall', {'buildId': 'https://evil.example'}),
    ('sdCancel', {'url': 'https://evil.example'}),
])
def test_installer_refuses_client_destinations_and_unselected_builds(studio, action, extra):
    controller, app, config = studio
    before, draft = config.read_bytes(), dict(app.values)
    with pytest.raises(ValueError):
        controller.apply({'id': action, 'action': action, 'values': {}, 'extra': extra})
    assert app.actions.results[action]['ok'] is False
    assert config.read_bytes() == before and app.values == draft
    assert not controller.installer.snapshot()['busy']


def test_real_transport_progress_errors_clear_only_after_persistence(studio):
    """Run both shipped JS owners against the real HTTP/controller/disk path."""
    import queue
    import shutil
    import subprocess
    import threading
    from suite_paths import GENERATOR_ROOT, REPO_ROOT

    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the real transport onboarding regression')
    controller, app, config = studio
    server = controller.server
    before = config.read_bytes()
    for index in range(server.commands.maxsize):
        server.commands.put_nowait({'id': f'earlier-{index}', 'action': 'onboardingProgress',
                                    'values': {}, 'extra': {'step': 0}})
    server.publish(controller.snapshot())
    server.start()
    worker = subprocess.Popen(
        [node, str(REPO_ROOT / 'tests/generator/studio_onboarding_transport.cjs')],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env={**os.environ, 'IFC_GENERATOR': str(GENERATOR_ROOT),
             'IFC_BASE': server.base_url, 'IFC_TOKEN': server.token})
    messages = queue.Queue()

    def read_messages():
        for line in worker.stdout:
            messages.put(line)
        messages.put(None)

    reader = threading.Thread(target=read_messages, daemon=True)
    reader.start()

    def receive(expected):
        line = messages.get(timeout=10)
        assert line is not None, worker.stderr.read()
        assert json.loads(line)['event'] == expected

    def resume():
        worker.stdin.write('continue\n')
        worker.stdin.flush()

    try:
        receive('rejected')
        while not server.commands.empty():
            controller.apply(server.commands.get_nowait())
        server.publish(controller.snapshot())
        resume()
        receive('accepted')
        command = server.commands.get_nowait()
        controller.apply(command)
        assert app.actions.results[command['id']]['ok'] is True
        assert owner().load_progress(config)['step'] == 1
        server.publish(controller.snapshot())
        resume()
        receive('disk-request')
        sidecar(config).unlink()
        sidecar(config).mkdir()
        command = server.commands.get_nowait()
        with pytest.raises(OSError):
            controller.apply(command)
        assert app.actions.results[command['id']]['ok'] is False
        server.publish(controller.snapshot())
        resume()
        receive('recovery-request')
        sidecar(config).rmdir()
        command = server.commands.get_nowait()
        controller.apply(command)
        assert app.actions.results[command['id']]['ok'] is True
        assert owner().load_progress(config)['step'] == 3
        server.publish(controller.snapshot())
        resume()
        receive('passed')
        assert worker.wait(timeout=3) == 0, worker.stderr.read()
        assert config.read_bytes() == before
    finally:
        if worker.poll() is None:
            worker.terminate()
        worker.wait(timeout=3)
        reader.join(timeout=3)
        assert not reader.is_alive()
