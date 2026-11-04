"""File migration must not convert low-priority legacy values into overrides."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from infini_local.core import config_migration as migration
from infini_local.core.env_file import FORMAT_HEADER, read_env_file
from infini_local.core.env_utils import load_env_file


@pytest.fixture
def isolated_environment(monkeypatch, tmp_path):
    baseline = {'HOME': str(tmp_path), 'USERPROFILE': str(tmp_path), 'APPDATA': str(tmp_path)}
    monkeypatch.setattr(os, 'environ', dict(baseline))
    monkeypatch.setattr(migration, '_ENVIRONMENT_RECEIPT', {'changed': False, 'changes': []})
    monkeypatch.setattr(migration, '_ENVIRONMENT_ORIGINALS', [])
    return baseline


def test_legacy_env_wins_file_through_reloads_and_explicit_studio_save(tmp_path, monkeypatch, isolated_environment):
    from infini_local.desktop.settings_controller import SettingsController
    config = tmp_path / 'config.env'
    original = b'INFINI_LLM_FALLBACK_NETWORK_FAILS=2\nINFINI_OPENAI_COMPAT_IMAGE_API_KEY=file-secret\n'
    config.write_bytes(original)
    inherited = {**isolated_environment, 'INFINI_LLM_FALLBACK_NETWORK_FAILS': '7',
                 'INFINI_OPENAI_COMPAT_IMAGE_API_KEY': 'environment-secret'}
    for fresh_process in (False, False, True):
        if fresh_process or 'INFINI_LLM_NETWORK_ATTEMPTS' not in os.environ:
            monkeypatch.setattr(os, 'environ', dict(inherited))
        load_env_file(config)
        assert os.environ['INFINI_LLM_NETWORK_ATTEMPTS'] == '7'
        assert os.environ['INFINI_IMAGE_API_KEY'] == 'environment-secret'
        saved = read_env_file(config)
        assert saved['INFINI_LLM_NETWORK_ATTEMPTS'] == '2'
        assert saved['INFINI_IMAGE_API_KEY'] == 'file-secret'
        assert b'environment-secret' not in config.read_bytes()
    backups = list(tmp_path.glob('config.env.pre-migration-*.bak'))
    assert len(backups) == 1 and backups[0].read_bytes() == original
    app = SettingsController(config_path=config)
    assert app.values['INFINI_LLM_NETWORK_ATTEMPTS'] == '7'
    assert app.values['INFINI_IMAGE_API_KEY'] == 'environment-secret'
    app.save()  # Explicit user Save may persist the values shown in the editor.
    assert read_env_file(config)['INFINI_IMAGE_API_KEY'] == 'environment-secret'
    assert read_env_file(config)['INFINI_LLM_NETWORK_ATTEMPTS'] == '7'
    monkeypatch.setattr(os, 'environ', {**inherited, 'INFINI_LLM_FALLBACK_NETWORK_FAILS': '9',
                                      'INFINI_OPENAI_COMPAT_IMAGE_API_KEY': 'later-old-secret'})
    load_env_file(config)
    assert os.environ['INFINI_LLM_NETWORK_ATTEMPTS'] == '7'
    assert os.environ['INFINI_IMAGE_API_KEY'] == 'environment-secret'
    assert backups[0].read_bytes() == original


@pytest.mark.parametrize('canonical', ['', '4'])
def test_explicit_current_file_beats_old_environment_including_blank(tmp_path, isolated_environment, canonical):
    config = tmp_path / 'config.env'
    config.write_text(FORMAT_HEADER + f'\nINFINI_LLM_NETWORK_ATTEMPTS={canonical}\n')
    before = config.read_bytes()
    os.environ['INFINI_LLM_FALLBACK_NETWORK_FAILS'] = '7'
    load_env_file(config)
    assert os.environ['INFINI_LLM_NETWORK_ATTEMPTS'] == canonical
    assert config.read_bytes() == before
    assert not list(tmp_path.glob('*.bak'))


def test_current_environment_beats_current_file(tmp_path, isolated_environment):
    config = tmp_path / 'config.env'
    config.write_text(FORMAT_HEADER + '\nINFINI_LLM_NETWORK_ATTEMPTS=2\n')
    os.environ['INFINI_LLM_NETWORK_ATTEMPTS'] = '7'
    load_env_file(config)
    assert os.environ['INFINI_LLM_NETWORK_ATTEMPTS'] == '7'
    assert read_env_file(config)['INFINI_LLM_NETWORK_ATTEMPTS'] == '2'


def test_fallback_inherits_effective_primary_without_persisting_environment_secret(tmp_path, monkeypatch, isolated_environment):
    config = tmp_path / 'config.env'
    config.write_text('INFINI_LLM_FALLBACK_MODEL=secondary\n')
    original = config.read_bytes()
    inherited = {**isolated_environment, 'INFINI_LLM_PROVIDER': 'openrouter',
                 'INFINI_OPENROUTER_API_KEY': 'primary-environment-secret',
                 'INFINI_OPENROUTER_BASE_URL': 'https://primary.example.test/v1'}
    for _ in range(2):
        monkeypatch.setattr(os, 'environ', dict(inherited))
        load_env_file(config)
        assert os.environ['INFINI_LLM_POOL_2_PROVIDER'] == 'openrouter'
        assert os.environ['INFINI_LLM_POOL_2_API_KEY'] == 'primary-environment-secret'
        assert os.environ['INFINI_LLM_POOL_2_BASE_URL'] == 'https://primary.example.test/v1'
        assert os.environ['INFINI_LLM_POOL_2_ENABLED'] == '0'
        saved = read_env_file(config)
        assert saved['INFINI_LLM_POOL_2_PROVIDER'] == 'openrouter'
        assert 'primary-environment-secret' not in config.read_text()
        assert 'https://primary.example.test/v1' not in config.read_text()
    assert list(tmp_path.glob('*.bak'))[0].read_bytes() == original
