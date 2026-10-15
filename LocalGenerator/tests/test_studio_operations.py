"""Headless operation boundaries: owner-loop publication and guarded side effects."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from infini_local.desktop import studio_operations as operations
from infini_local.desktop.settings_schema import DEFAULTS
from infini_local.services import codex_auth, codex_catalog
from infini_local.services.codex_catalog import CodexModel


class OperationHost(operations.StudioOperations):
    """Explicit scheduler/config boundary; real operation implementations run unchanged."""
    def __init__(self, root):
        self.config_path = root / 'config.env'
        self.example_path = root / 'example.env'
        self.example_path.write_text('INFINI_PORT=5055\n')
        self.values = dict(DEFAULTS)
        self.values['INFINI_CACHE_DIR'] = str(root / 'cache')
        self.owner = threading.get_ident()
        self.jobs = {}
        self.serial = 0
        self.proc = None
        self.trace = {}
        self.lan_enabled = False
        self.status = self.activity = self.applied_config = self.trace_status = ''
        self.codex_catalog = self.codex_image_account = ''
        self.codex_models = []
        self.receipts = []
        self._ui_action_sink = lambda *args, **kwargs: self.receipts.append((args, kwargs))

    def collect(self):
        assert threading.get_ident() == self.owner
        return dict(self.values)

    def after(self, delay, callback):
        assert threading.get_ident() == self.owner
        self.serial += 1
        self.jobs[self.serial] = callback
        return self.serial

    def after_cancel(self, identifier):
        self.jobs.pop(identifier, None)

    def cancel_scheduled(self):
        self.jobs.clear()

    def drain_until(self, predicate):
        end = time.monotonic() + 3
        while not predicate() and time.monotonic() < end:
            jobs, self.jobs = self.jobs, {}
            for callback in jobs.values():
                callback()
            time.sleep(.005)
        assert predicate(), 'operation did not finish'

    def _lora_dir_from_file(self, value):
        return str(Path(value).parent) if value else ''


@pytest.fixture
def host(tmp_path, monkeypatch):
    monkeypatch.setattr(operations, 'ROOT', tmp_path)
    app = OperationHost(tmp_path)
    yield app
    app.on_close()


def test_worker_failure_is_redacted_and_applied_on_owner_loop(host):
    host._studio_command_id = 'failure'
    seen = []
    def work(cancel):
        assert threading.get_ident() != host.owner
        raise RuntimeError('SECRET-CANARY')
    def apply(ok, result):
        assert threading.get_ident() == host.owner
        seen.append((ok, result))
    host._run_gui_task('test', work, apply)
    host.drain_until(lambda: bool(seen))
    assert seen == [(False, None)]
    assert 'CANARY' not in str(host.receipts) + host.status


def test_latest_worker_replaces_pending_request_and_retires_all_receipts(host):
    started, release = threading.Event(), threading.Event()
    seen = []
    def work(cancel):
        started.set()
        assert release.wait(3)
        return 'first'
    host._studio_command_id = 'first'
    host._run_gui_task('trace', work, lambda ok, result: seen.append(result))
    assert started.wait(1)
    try:
        for name in ('second', 'third'):
            host._studio_command_id = name
            host._run_gui_task('trace', lambda cancel, value=name: value, lambda ok, value: seen.append(value))
    finally:
        release.set()
    host.drain_until(lambda: not host._gui_tasks)
    assert seen == ['third']
    assert {args[0] for args, kwargs in host.receipts} == {'first', 'second', 'third'}
    assert {args[0] for args, kwargs in host.receipts if kwargs.get('cancelled')} == {'first', 'second'}


def test_catalog_preserves_saved_slug_and_unsupported_effort(host, monkeypatch):
    host.values.update(INFINI_CODEX_LLM_MODEL='saved-custom', INFINI_LLM_REASONING_MODE='high', INFINI_CODEX_VISUAL_REASONING='inherit')
    monkeypatch.setattr(codex_catalog, 'list_text_models', lambda: [CodexModel('account-model', 'Account', ('low', 'medium', 'ultra'), 'low', 1)])
    host.refresh_codex_text_catalog()
    host.drain_until(lambda: 'account-model' in host.codex_models)
    assert host.values['INFINI_CODEX_LLM_MODEL'] == 'saved-custom'
    host.values['INFINI_CODEX_LLM_MODEL'] = 'account-model'
    host._update_codex_efforts()
    assert host.codex_efforts == ['off', 'low', 'medium']
    assert host.codex_visual_efforts == ['inherit', 'model_default', 'low', 'medium']
    assert host.values['INFINI_LLM_REASONING_MODE'] == 'high'
    assert 'не поддерживается' in host.codex_catalog


def test_logout_retires_old_account_catalog(host, monkeypatch):
    started, release = threading.Event(), threading.Event()
    def fetch():
        started.set()
        assert release.wait(3)
        return [CodexModel('old-account', 'Old', ('low',), 'low', 1)]
    monkeypatch.setattr(codex_catalog, 'list_text_models', fetch)
    monkeypatch.setattr(codex_auth, 'logout', lambda: None)
    host.refresh_codex_text_catalog()
    assert started.wait(1)
    try:
        host.codex_logout()
    finally:
        release.set()
    host.drain_until(lambda: not host.jobs)
    assert host._codex_text_models == {}
    assert 'old-account' not in host.codex_models
    assert 'удалена' in host.status


@pytest.mark.parametrize('action', ['clear_trace_files', 'force_restart_server'])
def test_destructive_operation_requires_explicit_confirmation(host, action):
    result = getattr(host, action)()
    assert result['ok'] is False
    assert not host.jobs


@pytest.mark.parametrize('health', [
    {'ok': True, 'pid': 42, 'serverRoot': '/foreign'},
    {'ok': True, 'pid': True},
    {'ok': False, 'pid': 42},
])
def test_stop_never_shuts_down_unverified_identity(host, monkeypatch, health):
    monkeypatch.setattr(host, '_fetch_health_snapshot', lambda **kwargs: health)
    monkeypatch.setattr(host, '_try_http_shutdown_current_server', lambda **kwargs: pytest.fail('unsafe shutdown'))
    host.stop_server()
    host.drain_until(lambda: not host._gui_tasks)
    assert 'refused' in host.status.lower()


def test_trace_clear_does_not_turn_timeout_into_local_truncation(host, monkeypatch):
    cache = host._effective_cache_dir()
    cache.mkdir()
    events = cache / 'events.ndjson'
    events.write_text('preserve\n')
    def unavailable(**kwargs):
        raise TimeoutError('SECRET-CANARY')
    monkeypatch.setattr(host, '_fetch_health_snapshot', unavailable)
    host.clear_trace_files(confirmed=True)
    host.drain_until(lambda: not host._gui_tasks)
    assert events.read_text() == 'preserve\n'
    assert 'refused' in host.trace_status.lower()
    assert 'CANARY' not in host.trace_status


def test_trace_render_preserves_full_prompt_and_response(host):
    prompt = 'p' * 30000
    host._render_trace_snapshot({'promptTrace': [{'stage': 'author', 'prompt': prompt, 'response': 'complete response'}]})
    assert prompt in host.trace['prompts']
    assert 'complete response' in host.trace['prompts']


def test_close_cancels_oauth_and_callbacks_without_stopping_server(host):
    host._codex_login_running = True
    host._codex_login_cancel = threading.Event()
    host.after(1, lambda: pytest.fail('closed callback'))
    host.on_close()
    assert host._gui_closed
    assert host._codex_login_cancel.is_set()
    assert not host.jobs


def test_close_finishes_running_pending_and_oauth_receipts_once(host):
    cancel = threading.Event()
    host._gui_tasks = {'work': {'cancel': cancel, 'command_id': 'running', 'pending': (None, None, 'pending')}}
    host._studio_async_ids = {'running', 'pending', 'oauth'}
    host._codex_login_command_id = 'oauth'
    host.on_close()
    assert cancel.is_set()
    assert not host._studio_async_ids
    assert sorted(args[0] for args, kwargs in host.receipts) == ['oauth', 'pending', 'running']
    assert all(kwargs['cancelled'] for args, kwargs in host.receipts)


@pytest.mark.parametrize('operation, task', [('refresh_codex_text_catalog', 'codex-catalog'), ('ping_codex_image_account', 'codex-image-ping')])
def test_repeated_account_requests_use_one_worker_and_one_pending(host, monkeypatch, operation, task):
    started, release = threading.Event(), threading.Event()
    calls = []
    def fetch():
        calls.append(threading.get_ident())
        started.set()
        assert release.wait(3)
        return []
    monkeypatch.setattr(codex_catalog, 'list_text_models', fetch)
    host._studio_command_id = 'first'
    getattr(host, operation)()
    assert started.wait(1)
    try:
        for i in range(20):
            host._studio_command_id = str(i)
            getattr(host, operation)()
        assert len(calls) == 1
        assert set(host._gui_tasks) == {task}
    finally:
        release.set()
    host.drain_until(lambda: not host._gui_tasks)
    assert len(calls) == 2
    assert len(host.receipts) == 21
    assert not host._studio_async_ids
