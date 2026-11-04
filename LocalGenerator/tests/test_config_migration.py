"""One-time conversion, exact recovery bytes and current-only routing settings."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from infini_local.core import config_migration as migration
from infini_local.core.env_file import FORMAT_HEADER, read_env_file


@pytest.mark.parametrize('source,target', list(migration.SIMPLE_ALIASES.items()))
def test_simple_alias_moves_once_and_preserves_values(source, target):
    original = {source: 'synthetic-secret\\literal', 'CUSTOM': 'keep'}
    converted, changes = migration.migrate_values(original)
    assert converted == {target: original[source], 'CUSTOM': 'keep'}
    assert migration.migrate_values(converted) == (converted, [])
    assert original[source] not in json.dumps(changes)


@pytest.mark.parametrize('canonical', ['', 'current'])
def test_canonical_wins_even_empty(canonical):
    converted, changes = migration.migrate_values({'INFINI_LLM_REPAIR_TEMPERATURE': canonical,
                                                  'INFINI_LLM_REAUTHOR_TEMPERATURE': '0.7'})
    assert converted == {'INFINI_LLM_REPAIR_TEMPERATURE': canonical}
    assert changes[0]['review']


@pytest.mark.parametrize('attempts', ['1', '2', '10', 'invalid', '2.9'])
def test_network_threshold_is_not_incremented(attempts):
    converted, _ = migration.migrate_values({'INFINI_LLM_FALLBACK_NETWORK_FAILS': attempts})
    assert converted['INFINI_LLM_NETWORK_ATTEMPTS'] == attempts


@pytest.mark.parametrize('key,old,new', [
    ('INFINI_LLM_PROVIDER', 'lm-studio', 'local'),
    ('INFINI_LLM_PROVIDER', 'or', 'openrouter'),
    ('INFINI_LLM_POOL_2_PROVIDER', 'api', 'openai_compat'),
    ('INFINI_LLM_POOL_3_API_MODE', 'chat-completion', 'chat_completions'),
    ('INFINI_LLM_API_MODE', 'response', 'responses'),
    ('INFINI_IMAGE_BACKEND', 'stable-diffusion.cpp', 'sdcpp'),
    ('INFINI_IMAGE_BACKEND', 'openai_compat_image', 'image_api'),
    ('INFINI_IMAGE_BACKEND', 'disabled', 'off'),
])
def test_known_enums_only(key, old, new):
    converted, _ = migration.migrate_values({key: old})
    assert converted[key] == new
    assert migration.migrate_values({key: 'unknown-invalid'}) == ({key: 'unknown-invalid'}, [])


def test_fallback_becomes_disabled_current_pool_without_runtime_aliases():
    values = {'INFINI_LLM_PROVIDER': 'openrouter', 'INFINI_OPENROUTER_API_KEY': 'primary-secret',
              'INFINI_OPENROUTER_BASE_URL': 'https://example.test/v1',
              'INFINI_LLM_FALLBACK_MODEL': 'secondary', 'INFINI_LLM_FALLBACK_OPENROUTER_PROVIDER': 'vendor'}
    converted, changes = migration.migrate_values(values)
    assert converted['INFINI_LLM_POOL_2_ENABLED'] == '0'
    assert converted['INFINI_LLM_POOL_2_PROVIDER'] == 'openrouter'
    assert converted['INFINI_LLM_POOL_2_MODEL'] == 'secondary'
    assert converted['INFINI_LLM_POOL_2_BASE_URL'] == 'https://example.test/v1'
    assert converted['INFINI_LLM_POOL_2_API_KEY'] == 'primary-secret'
    assert converted['INFINI_LLM_POOL_2_API_MODE'] == 'chat_completions'
    assert not any(key.startswith('INFINI_LLM_FALLBACK_') for key in converted)
    assert any(row['action'] == 'pool_requires_review_round_robin' for row in changes)
    assert 'primary-secret' not in json.dumps(changes)


def test_key_only_never_enables_or_invents_model():
    converted, _ = migration.migrate_values({'INFINI_LLM_FALLBACK_API_KEY': 'secondary-secret'})
    assert converted['INFINI_LLM_POOL_2_ENABLED'] == '0'
    assert 'INFINI_LLM_POOL_2_MODEL' not in converted


@pytest.mark.parametrize('suffix,value', [('ENABLED', '1'), ('MODEL', 'modern'), ('API_KEY', 'modern-secret'),
                                         ('BASE_URL', 'https://modern.test'), ('PROVIDER', 'local'),
                                         ('API_MODE', 'responses'), ('OPENROUTER_PROVIDER', 'vendor')])
def test_occupied_pool_keeps_entire_legacy_group_out(suffix, value):
    modern = {'INFINI_LLM_POOL_2_' + suffix: value}
    converted, changes = migration.migrate_values({**modern, 'INFINI_LLM_FALLBACK_MODEL': 'legacy-model',
                                                  'INFINI_LLM_FALLBACK_API_KEY': 'legacy-secret'})
    assert converted == modern
    assert all(change['review'] for change in changes)
    assert 'legacy-secret' not in json.dumps(changes)


def test_empty_explicit_pool_fields_still_win_without_auto_enable():
    canonical = {'INFINI_LLM_POOL_2_MODEL': '', 'INFINI_LLM_POOL_2_API_KEY': '',
                 'INFINI_LLM_POOL_2_ENABLED': '0', 'INFINI_LLM_POOL_2_PROVIDER': 'openai_compat',
                 'INFINI_LLM_POOL_2_API_MODE': 'auto'}
    converted, changes = migration.migrate_values({**canonical, 'INFINI_LLM_PROVIDER': 'openai_compat', 'INFINI_LLM_FALLBACK_MODEL': 'old-model',
                                                  'INFINI_LLM_FALLBACK_API_KEY': 'old-secret'})
    assert all(converted[key] == value for key, value in canonical.items())
    assert any(change['action'] == 'pool_conflict_preserved_in_backup' for change in changes)


def test_file_backup_bytes_secrets_and_idempotence(tmp_path):
    config = tmp_path / 'config.env'
    original = ('\ufeff# personal comment\r\nINFINI_SDCPP_MODEL="C:\\new\\tools\\model.gguf"\r\n'
                'INFINI_OPENAI_COMPAT_IMAGE_API_KEY="test-secret"\r\n'
                'INFINI_LLM_FALLBACK_MODEL=old-model\r\n').encode()
    config.write_bytes(original)
    receipt = migration.migrate_config_file(config)
    assert receipt['changed'] and receipt['state'] == 'completed'
    backup = Path(receipt['backup_path'])
    assert backup.read_bytes() == original
    if os.name != 'nt':
        assert backup.stat().st_mode & 0o777 == 0o600
    assert read_env_file(config)['INFINI_SDCPP_MODEL'] == r'C:\new\tools\model.gguf'
    assert read_env_file(config)['INFINI_IMAGE_API_KEY'] == 'test-secret'
    assert 'test-secret' not in Path(receipt['receipt_path']).read_text()
    assert 'old-model' not in Path(receipt['receipt_path']).read_text()
    current = config.read_bytes()
    assert migration.migrate_config_file(config) == {'changed': False, 'changes': []}
    assert config.read_bytes() == current
    assert migration.read_migration_receipt(config)['target_sha256'] == receipt['target_sha256']
    assert len(list(tmp_path.glob('*.bak'))) == 1


def test_current_noop_has_no_side_effects(tmp_path):
    config = tmp_path / 'config.env'
    original = (FORMAT_HEADER + '\r\n# preserve\r\nINFINI_LLM_PROVIDER="local"\r\n').encode()
    config.write_bytes(original)
    assert not migration.migrate_config_file(config)['changed']
    assert config.read_bytes() == original
    assert list(tmp_path.iterdir()) == [config]


def test_corrupt_config_is_untouched(tmp_path):
    config = tmp_path / 'config.env'
    original = (FORMAT_HEADER + '\nINFINI_API_KEY="private-secret\\q"\n').encode()
    config.write_bytes(original)
    with pytest.raises(ValueError) as error:
        migration.migrate_config_file(config)
    assert 'private-secret' not in str(error.value)
    assert config.read_bytes() == original
    assert list(tmp_path.iterdir()) == [config]


def test_target_replace_failure_keeps_original(tmp_path, monkeypatch):
    config = tmp_path / 'config.env'
    original = b'INFINI_LLM_FALLBACK_NETWORK_FAILS=2\n'
    config.write_bytes(original)
    real_replace = os.replace
    def fail_target(source, target):
        if Path(target) == config:
            raise OSError('synthetic write error')
        return real_replace(source, target)
    monkeypatch.setattr(migration.os, 'replace', fail_target)
    with pytest.raises(OSError):
        migration.migrate_config_file(config)
    assert config.read_bytes() == original
    assert not list(tmp_path.glob('*.tmp'))
    assert migration.read_migration_receipt(config)['state'] == 'not_applied'


def test_final_receipt_failure_does_not_repeat_successful_migration(tmp_path, monkeypatch):
    config = tmp_path / 'config.env'
    config.write_text('INFINI_LLM_FALLBACK_NETWORK_FAILS=2\n')
    real_write = migration._atomic_write
    writes = []
    def fail_final(path, data, **kwargs):
        writes.append(path)
        if len(writes) == 2:
            raise OSError('synthetic final receipt error')
        return real_write(path, data, **kwargs)
    monkeypatch.setattr(migration, '_atomic_write', fail_final)
    receipt = migration.migrate_config_file(config)
    assert receipt['state'] == 'completed_receipt_pending'
    assert migration.read_migration_receipt(config)['state'] == 'completed'
    assert not migration.migrate_config_file(config)['changed']
    assert read_env_file(config)['INFINI_LLM_NETWORK_ATTEMPTS'] == '2'


def test_concurrent_file_change_is_not_overwritten(tmp_path, monkeypatch):
    config = tmp_path / 'config.env'
    config.write_text('INFINI_LLM_FALLBACK_NETWORK_FAILS=2\n')
    real_write = migration._atomic_write
    newer = b'INFINI_LLM_FALLBACK_NETWORK_FAILS=5\n'
    def race(path, data, **kwargs):
        real_write(path, data, **kwargs)
        config.write_bytes(newer)
    monkeypatch.setattr(migration, '_atomic_write', race)
    with pytest.raises(OSError, match='changed during migration'):
        migration.migrate_config_file(config)
    assert config.read_bytes() == newer


def test_environment_is_current_only_and_private_recovery_retained(monkeypatch):
    monkeypatch.setattr(migration, '_ENVIRONMENT_ORIGINALS', [])
    monkeypatch.setattr(migration, '_ENVIRONMENT_RECEIPT', {'changed': False, 'changes': []})
    env = {'INFINI_OPENAI_COMPAT_IMAGE_API_KEY': 'old-secret', 'INFINI_IMAGE_API_KEY': '', 'OTHER': 'kept'}
    report = migration.migrate_environment(env)
    assert env == {'INFINI_IMAGE_API_KEY': '', 'OTHER': 'kept'}
    assert migration._ENVIRONMENT_ORIGINALS == [{'INFINI_OPENAI_COMPAT_IMAGE_API_KEY': 'old-secret'}]
    assert 'old-secret' not in json.dumps(report)
    assert not migration.migrate_environment(env)['changed']
    assert migration.environment_migration_status()['changed']
    assert 'old-secret' not in json.dumps(migration.environment_migration_status())


def test_symlink_target_preserved(tmp_path):
    target = tmp_path / 'personal.env'
    target.write_text('INFINI_LLM_FALLBACK_NETWORK_FAILS=2\n')
    config = tmp_path / 'config.env'
    try:
        config.symlink_to(target)
    except OSError:
        pytest.skip('symlinks unavailable')
    report = migration.migrate_config_file(config)
    assert config.is_symlink()
    assert read_env_file(config)['INFINI_LLM_NETWORK_ATTEMPTS'] == '2'
    assert migration.read_migration_receipt(config)['target_sha256'] == report['target_sha256']


def test_backup_conflict_never_overwrites_original(tmp_path):
    config = tmp_path / 'config.env'
    original = b'INFINI_LLM_FALLBACK_NETWORK_FAILS=2\n'
    config.write_bytes(original)
    backup = config.with_name(config.name + '.pre-migration-' + migration._hash(original)[:16] + '.bak')
    backup.write_text('unrelated backup')
    with pytest.raises(OSError, match='backup conflict'):
        migration.migrate_config_file(config)
    assert config.read_bytes() == original
    assert backup.read_text() == 'unrelated backup'


def test_default_canonical_provider_does_not_receive_another_providers_credentials():
    values = {'INFINI_LLM_PROVIDER': 'openrouter', 'INFINI_LLM_POOL_2_PROVIDER': 'openai_compat',
              'INFINI_LLM_POOL_2_ENABLED': '0', 'INFINI_LLM_FALLBACK_MODEL': 'legacy-model',
              'INFINI_LLM_FALLBACK_API_KEY': 'legacy-secret'}
    converted, changes = migration.migrate_values(values)
    assert 'INFINI_LLM_POOL_2_API_KEY' not in converted
    assert 'INFINI_LLM_POOL_2_MODEL' not in converted
    assert converted['INFINI_LLM_POOL_2_PROVIDER'] == 'openai_compat'
    assert all(change['review'] for change in changes)


@pytest.mark.parametrize('suffix', ['PROVIDER', 'BASE_URL', 'MODEL'])
def test_blank_structural_canonical_choice_keeps_profile_credentials_isolated(suffix):
    values = {'INFINI_LLM_PROVIDER': 'openai_compat', 'INFINI_LLM_FALLBACK_PROVIDER': 'openai_compat',
              'INFINI_LLM_FALLBACK_MODEL': 'legacy-model', 'INFINI_LLM_FALLBACK_API_KEY': 'legacy-secret',
              'INFINI_LLM_FALLBACK_BASE_URL': 'https://legacy.test/v1', 'INFINI_LLM_POOL_2_' + suffix: ''}
    converted, changes = migration.migrate_values(values)
    assert converted == {'INFINI_LLM_PROVIDER': 'openai_compat', 'INFINI_LLM_POOL_2_' + suffix: ''}
    assert all(change['review'] for change in changes)
    assert 'legacy-secret' not in json.dumps(changes)


def test_file_fallback_cannot_fill_credentials_for_enabled_environment_pool(tmp_path):
    config = tmp_path / 'config.env'
    config.write_text('INFINI_LLM_FALLBACK_PROVIDER=openai_compat\nINFINI_LLM_FALLBACK_MODEL=old\n'
                      'INFINI_LLM_FALLBACK_BASE_URL=https://old.example/v1\n'
                      'INFINI_LLM_FALLBACK_API_KEY=old-secret\n')
    environment = {'INFINI_LLM_POOL_2_ENABLED': '1', 'INFINI_LLM_POOL_2_MODEL': 'new',
                   'INFINI_LLM_POOL_2_BASE_URL': 'https://new.example/v1'}
    original_environment = dict(environment)
    report = migration.migrate_config_file(config, environment=environment)
    persisted = read_env_file(config)
    effective = {**persisted, **environment}
    assert 'INFINI_LLM_POOL_2_API_KEY' not in effective
    assert persisted == {}
    assert environment == original_environment
    assert 'old-secret' in Path(report['backup_path']).read_text()
    assert 'old-secret' not in json.dumps(report)


@pytest.mark.parametrize('suffix,value', [('ENABLED', '1'), ('BASE_URL', ''), ('API_KEY', ''),
                                         ('PROVIDER', 'openai_compat'), ('MODEL', 'new')])
def test_canonical_process_pool_context_is_not_persisted_or_mixed(suffix, value):
    context = {'INFINI_LLM_POOL_2_' + suffix: value}
    result, changes = migration.migrate_values({'INFINI_LLM_FALLBACK_API_KEY': 'old-secret',
                                               'INFINI_LLM_FALLBACK_MODEL': 'old'}, environment=context)
    assert result == {}
    assert all(change['review'] for change in changes)


def test_reverse_old_environment_canonical_file_pool_is_not_mixed():
    environment = {'INFINI_LLM_FALLBACK_PROVIDER': 'openai_compat', 'INFINI_LLM_FALLBACK_MODEL': 'old',
                   'INFINI_LLM_FALLBACK_BASE_URL': 'https://old.example/v1',
                   'INFINI_LLM_FALLBACK_API_KEY': 'old-secret'}
    file_values = {'INFINI_LLM_POOL_2_ENABLED': '1', 'INFINI_LLM_POOL_2_MODEL': 'new',
                   'INFINI_LLM_POOL_2_BASE_URL': 'https://new.example/v1'}
    for key, value in file_values.items():
        environment.setdefault(key, value)
    migration.migrate_environment(environment)
    assert environment == file_values


@pytest.mark.parametrize('canonical', [
    {'INFINI_IMAGE_API_BASE_URL': 'https://new.example/v1'},
    {'INFINI_IMAGE_API_BASE_URL': ''},
    {'INFINI_IMAGE_API_KEY': 'new-secret'},
    {'INFINI_IMAGE_API_KEY': ''},
])
def test_image_profile_canonical_choices_cannot_mix_with_legacy_credentials(canonical):
    old = {'INFINI_OPENAI_COMPAT_IMAGE_BASE_URL': 'https://old.example/v1',
           'INFINI_OPENAI_COMPAT_IMAGE_API_KEY': 'old-secret',
           'INFINI_OPENAI_COMPAT_IMAGE_MODEL': 'old-model'}
    # Same-map migration covers the old-process/new-file direction.
    converted, changes = migration.migrate_values({**old, **canonical})
    assert converted == canonical
    assert all(change['review'] for change in changes)
    # Separate context covers the old-file/new-process direction without
    # persisting either canonical process keys or their secret values.
    converted, changes = migration.migrate_values(old, environment=canonical)
    assert converted == {}
    assert 'old-secret' not in json.dumps(changes)
    assert 'new-secret' not in json.dumps(changes)


def test_image_old_key_with_new_endpoint_and_no_old_url_uses_safe_default_evidence():
    converted, changes = migration.migrate_values({'INFINI_OPENAI_COMPAT_IMAGE_API_KEY': 'old-secret',
                                                  'INFINI_IMAGE_API_BASE_URL': 'https://new.example/v1'})
    assert converted == {'INFINI_IMAGE_API_BASE_URL': 'https://new.example/v1'}
    assert changes[0]['review']


def test_matching_image_endpoint_allows_safe_key_migration():
    converted, _ = migration.migrate_values({'INFINI_OPENAI_COMPAT_IMAGE_API_KEY': 'old-secret',
                                             'INFINI_OPENAI_COMPAT_IMAGE_BASE_URL': 'https://same.example/v1/',
                                             'INFINI_IMAGE_API_BASE_URL': 'https://same.example/v1'})
    assert converted['INFINI_IMAGE_API_KEY'] == 'old-secret'
    assert converted['INFINI_IMAGE_API_BASE_URL'] == 'https://same.example/v1'


def test_legacy_image_endpoint_cannot_capture_unpaired_canonical_key():
    converted, changes = migration.migrate_values({'INFINI_OPENAI_COMPAT_IMAGE_BASE_URL': 'https://old.example/v1',
                                                  'INFINI_IMAGE_API_KEY': 'new-secret'})
    assert converted == {'INFINI_IMAGE_API_KEY': 'new-secret'}
    assert changes[0]['review']


def _effective_start(config, original_environment):
    migration.migrate_config_file(config, environment=original_environment)
    source = migration.read_migration_source(config)
    after, changes = migration.migrate_values({**source, **original_environment})
    effective = dict(original_environment)
    migration.apply_environment_values(effective, after, changes)
    return effective


def test_legacy_environment_wins_legacy_file_on_first_repeat_and_save(tmp_path):
    config = tmp_path / 'config.env'
    original = b'INFINI_LLM_FALLBACK_NETWORK_FAILS=2\nINFINI_OPENAI_COMPAT_IMAGE_API_KEY=file-secret\n'
    config.write_bytes(original)
    env = {'INFINI_LLM_FALLBACK_NETWORK_FAILS': '7', 'INFINI_OPENAI_COMPAT_IMAGE_API_KEY': 'env-secret'}
    for _ in range(2):
        effective = _effective_start(config, env)
        assert effective['INFINI_LLM_NETWORK_ATTEMPTS'] == '7'
        assert effective['INFINI_IMAGE_API_KEY'] == 'env-secret'
        assert 'env-secret' not in config.read_text()
        assert 'INFINI_LLM_NETWORK_ATTEMPTS' not in migration.explicit_config_keys(config)
        assert migration.read_migration_source(config)['INFINI_OPENAI_COMPAT_IMAGE_API_KEY'] == 'file-secret'
    receipt = migration.read_migration_receipt(config)
    assert Path(receipt['backup_path']).read_bytes() == original
    assert 'env-secret' not in json.dumps(receipt)
    # Explicit GUI save adopts current effective values and breaks provenance.
    from infini_local.desktop.settings_env import write_env
    write_env(config, effective)
    assert 'INFINI_LLM_NETWORK_ATTEMPTS' in migration.explicit_config_keys(config)
    assert migration.read_migration_source(config)['INFINI_IMAGE_API_KEY'] == 'env-secret'
    changed_old_env = {**env, 'INFINI_LLM_FALLBACK_NETWORK_FAILS': '9'}
    assert _effective_start(config, changed_old_env)['INFINI_LLM_NETWORK_ATTEMPTS'] == '7'


@pytest.mark.parametrize('canonical', ['', '4'])
def test_explicit_canonical_file_wins_legacy_environment_with_provenance(tmp_path, canonical):
    config = tmp_path / 'config.env'
    config.write_text('INFINI_LLM_NETWORK_ATTEMPTS=' + canonical + '\nINFINI_LLM_FALLBACK_NETWORK_FAILS=2\n')
    for _ in range(2):
        effective = _effective_start(config, {'INFINI_LLM_FALLBACK_NETWORK_FAILS': '7'})
        assert effective['INFINI_LLM_NETWORK_ATTEMPTS'] == canonical
        assert 'INFINI_LLM_NETWORK_ATTEMPTS' in migration.explicit_config_keys(config)
        assert 'INFINI_LLM_FALLBACK_NETWORK_FAILS' not in migration.read_migration_source(config)


def test_context_primary_provider_inferred_but_context_secret_stays_process_only(tmp_path):
    config = tmp_path / 'config.env'
    config.write_text('INFINI_LLM_FALLBACK_MODEL=backup-model\n')
    environment = {'INFINI_LLM_PROVIDER': 'openrouter', 'INFINI_OPENROUTER_API_KEY': 'process-secret',
                   'INFINI_OPENROUTER_BASE_URL': 'https://process.example/v1'}
    for _ in range(2):
        effective = _effective_start(config, environment)
        persisted = read_env_file(config)
        assert persisted['INFINI_LLM_POOL_2_PROVIDER'] == 'openrouter'
        assert 'process-secret' not in config.read_text()
        assert 'process.example' not in config.read_text()
        assert 'INFINI_LLM_POOL_2_API_KEY' not in persisted
        assert effective['INFINI_LLM_POOL_2_PROVIDER'] == 'openrouter'
        assert effective['INFINI_LLM_POOL_2_API_KEY'] == 'process-secret'
        assert effective['INFINI_LLM_POOL_2_BASE_URL'] == 'https://process.example/v1'
        assert migration.read_migration_source(config) == {'INFINI_LLM_FALLBACK_MODEL': 'backup-model'}


def test_quarantined_values_never_reconstructed_from_backup(tmp_path):
    config = tmp_path / 'config.env'
    config.write_text('INFINI_LLM_POOL_2_MODEL=new\nINFINI_LLM_FALLBACK_MODEL=old\nINFINI_LLM_FALLBACK_API_KEY=old-secret\n')
    migration.migrate_config_file(config)
    source = migration.read_migration_source(config)
    assert source == {'INFINI_LLM_POOL_2_MODEL': 'new'}
    assert 'old-secret' not in json.dumps(source)


@pytest.mark.parametrize('different_contexts', [False, True])
def test_concurrent_migrations_serialize_entire_config_receipt_transaction(tmp_path, monkeypatch, different_contexts):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import contextmanager
    config = tmp_path / 'config.env'
    original = b'INFINI_LLM_FALLBACK_MODEL=old-model\nINFINI_LLM_FALLBACK_API_KEY=old-secret\n'
    config.write_bytes(original)
    first_inside = threading.Event()
    second_waiting = threading.Event()
    release_first = threading.Event()
    real_transaction = migration._migrate_config_file_locked
    real_lock = migration._configuration_lock
    entries = []
    @contextmanager
    def observed_lock(path):
        if first_inside.is_set():
            second_waiting.set()
        with real_lock(path):
            yield
    def observed_transaction(path, **kwargs):
        entries.append(dict(kwargs.get('environment') or {}))
        if len(entries) == 1:
            first_inside.set()
            assert release_first.wait(timeout=5)
        return real_transaction(path, **kwargs)
    monkeypatch.setattr(migration, '_configuration_lock', observed_lock)
    monkeypatch.setattr(migration, '_migrate_config_file_locked', observed_transaction)
    first_context = {'INFINI_LLM_PROVIDER': 'openrouter'}
    second_context = {'INFINI_LLM_POOL_2_ENABLED': '1', 'INFINI_LLM_POOL_2_BASE_URL': 'https://new.example'} if different_contexts else first_context
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(migration.migrate_config_file, config, environment=first_context)
        assert first_inside.wait(timeout=5)
        second = executor.submit(migration.migrate_config_file, config, environment=second_context)
        assert second_waiting.wait(timeout=5)
        assert len(entries) == 1
        release_first.set()
        results = [first.result(timeout=5), second.result(timeout=5)]
    assert results[0]['state'] == 'completed'
    assert results[1] == {'changed': False, 'changes': []}
    assert len(entries) == 2
    assert len(list(tmp_path.glob('*.bak'))) == 1
    assert next(tmp_path.glob('*.bak')).read_bytes() == original
    receipt = migration.read_migration_receipt(config)
    assert receipt['target_sha256'] == migration._hash(config.read_bytes())
    assert read_env_file(config)['INFINI_LLM_POOL_2_PROVIDER'] == 'openrouter'
    assert read_env_file(config)['INFINI_LLM_POOL_2_ENABLED'] == '0'
    assert not list(tmp_path.glob('*.tmp'))
    lock = tmp_path / 'config.env.migration.lock'
    assert lock.exists()
    if os.name != 'nt':
        assert lock.stat().st_mode & 0o777 == 0o600


def test_abandoned_partial_backup_temp_cannot_poison_migration(tmp_path, monkeypatch):
    config = tmp_path / 'config.env'
    original = b'INFINI_LLM_FALLBACK_NETWORK_FAILS=2\n'
    config.write_bytes(original)
    abandoned = tmp_path / '.config.env.pre-migration-abandoned.bak.crashed.tmp'
    abandoned.write_bytes(b'INFINI_')
    real_link = os.link
    def inspect_publication(source, destination):
        assert Path(source).read_bytes() == original
        assert not Path(destination).exists()
        return real_link(source, destination)
    monkeypatch.setattr(migration.os, 'link', inspect_publication)
    result = migration.migrate_config_file(config)
    assert Path(result['backup_path']).read_bytes() == original
    assert abandoned.read_bytes() == b'INFINI_'


def test_backup_link_failure_leaves_no_partial_visible_backup(tmp_path, monkeypatch):
    config = tmp_path / 'config.env'
    original = b'INFINI_LLM_FALLBACK_NETWORK_FAILS=2\n'
    config.write_bytes(original)
    monkeypatch.setattr(migration.os, 'link', lambda *_: (_ for _ in ()).throw(OSError('synthetic link failure')))
    with pytest.raises(OSError, match='link failure'):
        migration.migrate_config_file(config)
    assert config.read_bytes() == original
    assert set(tmp_path.iterdir()) == {config, tmp_path / 'config.env.migration.lock'}


def test_reconstructed_alias_application_is_noop_when_environment_already_matches(tmp_path, monkeypatch):
    config = tmp_path / 'config.env'
    config.write_text('INFINI_LLM_FALLBACK_NETWORK_FAILS=2\n')
    monkeypatch.setattr(migration, '_ENVIRONMENT_RECEIPT', {'changed': False, 'changes': []})
    first = _effective_start(config, {})
    original_status = migration.environment_migration_status()
    source = migration.read_migration_source(config)
    after, changes = migration.migrate_values({**source, **first})
    assert changes
    assert migration.apply_environment_values(first, after, changes) == {'changed': False, 'changes': []}
    assert migration.environment_migration_status() == original_status
    another = {}
    migration.apply_environment_values(another, after, changes)
    rows = migration.environment_migration_status()['changes']
    assert len(rows) == len({(row['action'], row['source'], row['target']) for row in rows})


def test_receipt_cannot_remove_or_rename_unknown_user_settings(tmp_path):
    config = tmp_path / 'config.env'
    config.write_text('CUSTOM_USER_SETTING=keep\nINFINI_LLM_FALLBACK_NETWORK_FAILS=2\n')
    report = migration.migrate_config_file(config)
    receipt_path = Path(report['receipt_path'])
    receipt = json.loads(receipt_path.read_text())
    receipt['derived_keys'].append('CUSTOM_USER_SETTING')
    receipt['original_keys'].remove('CUSTOM_USER_SETTING')
    receipt['original_keys'].append('EVIL_ALIAS')
    receipt['changes'].append({'action': 'rename', 'source': 'EVIL_ALIAS', 'target': 'CUSTOM_USER_SETTING'})
    receipt_path.write_text(json.dumps(receipt))
    source = migration.read_migration_source(config)
    assert source['CUSTOM_USER_SETTING'] == 'keep'
    assert 'EVIL_ALIAS' not in source
    assert 'CUSTOM_USER_SETTING' in migration.explicit_config_keys(config)


def test_blank_legacy_fallback_inheritance_uses_effective_primary_first_repeat_and_same_process(tmp_path):
    config = tmp_path / 'config.env'
    config.write_text('INFINI_LLM_PROVIDER=openrouter\nINFINI_OPENROUTER_API_KEY=file-secret\n'
                      'INFINI_OPENROUTER_BASE_URL=https://file.example/v1\n'
                      'INFINI_LLM_FALLBACK_PROVIDER=\nINFINI_LLM_FALLBACK_MODEL=secondary\n'
                      'INFINI_LLM_FALLBACK_BASE_URL=\nINFINI_LLM_FALLBACK_API_KEY=\n')
    original_environment = {'INFINI_OPENROUTER_API_KEY': 'env-secret',
                            'INFINI_OPENROUTER_BASE_URL': 'https://env.example/v1'}
    for _ in range(2):
        effective = _effective_start(config, original_environment)
        assert effective['INFINI_LLM_POOL_2_API_KEY'] == 'env-secret'
        assert effective['INFINI_LLM_POOL_2_BASE_URL'] == 'https://env.example/v1'
        assert effective['INFINI_LLM_POOL_2_PROVIDER'] == 'openrouter'
        assert 'env-secret' not in config.read_text()
        assert 'env.example' not in config.read_text()
        source = migration.read_migration_source(config)
        assert source['INFINI_LLM_FALLBACK_API_KEY'] == ''
        assert source['INFINI_LLM_FALLBACK_BASE_URL'] == ''
        assert source['INFINI_LLM_FALLBACK_PROVIDER'] == ''
    assert _effective_start(config, effective) == effective
    receipt = migration.read_migration_receipt(config)
    assert set(receipt['empty_legacy_keys']) == {
        'INFINI_LLM_FALLBACK_PROVIDER', 'INFINI_LLM_FALLBACK_API_KEY', 'INFINI_LLM_FALLBACK_BASE_URL'}
    assert 'env-secret' not in json.dumps(receipt)
    assert 'file-secret' not in json.dumps(receipt)


def test_explicit_legacy_profile_values_remain_explicit_with_primary_environment(tmp_path):
    config = tmp_path / 'config.env'
    config.write_text('INFINI_LLM_PROVIDER=openrouter\nINFINI_LLM_FALLBACK_PROVIDER=openai_compat\n'
                      'INFINI_LLM_FALLBACK_MODEL=secondary\nINFINI_LLM_FALLBACK_API_KEY=explicit-secret\n'
                      'INFINI_LLM_FALLBACK_BASE_URL=https://explicit.example/v1\n')
    for _ in range(2):
        effective = _effective_start(config, {'INFINI_OPENROUTER_API_KEY': 'env-secret',
                                             'INFINI_OPENROUTER_BASE_URL': 'https://env.example/v1'})
        assert effective['INFINI_LLM_POOL_2_API_KEY'] == 'explicit-secret'
        assert effective['INFINI_LLM_POOL_2_BASE_URL'] == 'https://explicit.example/v1'
        assert effective['INFINI_LLM_POOL_2_PROVIDER'] == 'openai_compat'
    assert migration.read_migration_receipt(config)['empty_legacy_keys'] == []


def test_blank_legacy_profile_provenance_cannot_override_explicit_current_profile(tmp_path):
    config = tmp_path / 'config.env'
    config.write_text('INFINI_LLM_PROVIDER=openrouter\nINFINI_LLM_FALLBACK_PROVIDER=\n'
                      'INFINI_LLM_FALLBACK_MODEL=secondary\nINFINI_LLM_FALLBACK_API_KEY=\n'
                      'INFINI_LLM_FALLBACK_BASE_URL=\nINFINI_LLM_POOL_2_MODEL=current-model\n'
                      'INFINI_LLM_POOL_2_API_KEY=current-secret\nINFINI_LLM_POOL_2_BASE_URL=https://current.example/v1\n')
    for _ in range(2):
        effective = _effective_start(config, {'INFINI_OPENROUTER_API_KEY': 'env-secret'})
        assert effective['INFINI_LLM_POOL_2_API_KEY'] == 'current-secret'
        assert effective['INFINI_LLM_POOL_2_BASE_URL'] == 'https://current.example/v1'
        assert effective['INFINI_LLM_POOL_2_MODEL'] == 'current-model'
        assert not any(key.startswith('INFINI_LLM_FALLBACK_') for key in migration.read_migration_source(config))
