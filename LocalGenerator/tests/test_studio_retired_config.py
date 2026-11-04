"""The real bundled editor migrates old inputs before admitting current settings."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SECRET = 'synthetic-retired-secret-never-print'
KEYS = {'INFINI_LLM_FALLBACK_NETWORK_FAILS': '2', 'INFINI_LLM_FALLBACK_API_KEY': SECRET}


@pytest.mark.parametrize('source', ['config', 'environment'])
def test_bundled_editor_migrates_retired_config_before_readiness(tmp_path, source):
    config = tmp_path / 'config.env'
    content = 'INFINI_CUSTOM_EXTENSION=keep\n'
    if source == 'config':
        content += ''.join(f'{key}={value}\n' for key, value in KEYS.items())
    else:
        content = '# infini-config-format: json-string-v1\n' + content
    config.write_text(content)
    before = config.read_bytes()
    env = {key: value for key, value in os.environ.items() if not key.startswith('INFINI_')}
    env.update(HOME=str(tmp_path), USERPROFILE=str(tmp_path), APPDATA=str(tmp_path),
               XDG_CONFIG_HOME=str(tmp_path), PYTHONDONTWRITEBYTECODE='1',
               PROBE_SOURCE=source)
    if source == 'environment':
        env.update(KEYS)
    probe = r'''
import builtins, json, os, runpy, sys, urllib.parse, urllib.request
read_fd, write_fd = os.pipe()
sys.stdin = os.fdopen(read_fd, "r")
original_print = builtins.print
observed = []
def inspect_ready(*values, **kwargs):
    if values and str(values[0]).startswith("IFC_STUDIO_READY "):
        url = json.loads(str(values[0]).partition(" ")[2])["url"]
        with urllib.request.urlopen(url, timeout=5) as response:
            page = response.read()
            assert response.status == 200 and b'id="retired-config"' in page
        parsed = urllib.parse.urlsplit(url)
        token = urllib.parse.parse_qs(parsed.query)['token'][0]
        request = urllib.request.Request(f'{parsed.scheme}://{parsed.netloc}/api/state',
                                        headers={'X-Infini-Token': token})
        with urllib.request.urlopen(request, timeout=5) as response:
            state = json.load(response)
        report = state['configMigration']['file' if os.environ['PROBE_SOURCE'] == 'config' else 'environment']
        issues = report['changes']
        assert {'INFINI_LLM_FALLBACK_NETWORK_FAILS', 'INFINI_LLM_FALLBACK_API_KEY'} <= {issue['source'] for issue in issues}
        assert 'synthetic-retired-secret-never-print' not in json.dumps(issues)
        assert not any(key.startswith('INFINI_LLM_FALLBACK_') for key in state['values'])
        assert state['values']['INFINI_LLM_NETWORK_ATTEMPTS'] == '2'
        assert state['values']['INFINI_LLM_POOL_2_ENABLED'] == '0'
        assert state['values']['INFINI_LLM_POOL_2_API_KEY'] == 'synthetic-retired-secret-never-print'
        assert state['values']['INFINI_CUSTOM_EXTENSION'] == 'keep'
        assert 'infini_local.core.config_bootstrap' not in sys.modules
        observed.append('ready')
        os.close(write_fd)
    else:
        original_print(*values, **kwargs)
builtins.print = inspect_ready
sys.argv = sys.argv[1:]
try:
    runpy.run_path(sys.argv[0], run_name='__main__')
except SystemExit as exc:
    assert exc.code == 0, exc.code
assert observed == ['ready']
original_print('STUDIO_RETIRED_PROBE_OK')
'''
    command = [sys.executable, '-B', '-c', probe,
               str(ROOT / 'LocalGenerator/scripts/bundled_studio.py'),
               '--data-dir', str(tmp_path), '--managed', '--no-browser']
    result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=20)
    assert result.returncode == 0, result.stderr
    assert 'STUDIO_RETIRED_PROBE_OK' in result.stdout
    assert SECRET not in result.stdout + result.stderr
    if source == 'config':
        assert config.read_bytes() != before
        backups = list(tmp_path.glob('config.env.pre-migration-*.bak'))
        assert len(backups) == 1 and backups[0].read_bytes() == before
    else:
        assert config.read_bytes() == before


def test_migrated_settings_can_be_explicitly_saved_without_reactivating_fallback(tmp_path):
    from infini_local.core.config_migration import migrate_config_file
    from infini_local.desktop.settings_controller import SettingsController
    from infini_local.desktop.settings_env import parse_env
    from infini_local.desktop.web_studio import StudioController
    config = tmp_path / 'config.env'
    config.write_text('INFINI_CUSTOM_EXTENSION=keep\n' + ''.join(f'{key}={value}\n' for key, value in KEYS.items()))
    before = config.read_bytes()
    app = SettingsController(config_path=config)
    controller = StudioController(app, None)
    snapshot = controller.snapshot()
    assert snapshot['configMigration']['file']['state'] == 'completed'
    assert snapshot['values']['INFINI_LLM_POOL_2_ENABLED'] == '0'
    assert snapshot['values']['INFINI_LLM_POOL_2_API_KEY'] == SECRET
    app.update_values({'INFINI_LLM_NETWORK_ATTEMPTS': '3'})
    app.save()
    saved_bytes = config.read_bytes()
    assert migrate_config_file(config)['changed'] is False
    assert config.read_bytes() == saved_bytes
    saved = parse_env(config)
    assert not any(key in saved for key in KEYS)
    assert saved['INFINI_CUSTOM_EXTENSION'] == 'keep'
    assert saved['INFINI_LLM_NETWORK_ATTEMPTS'] == '3'
    assert saved['INFINI_LLM_POOL_2_API_KEY'] == SECRET
    assert saved['INFINI_LLM_POOL_2_ENABLED'] == '0'
    assert list(tmp_path.glob('config.env.pre-migration-*.bak'))[0].read_bytes() == before
