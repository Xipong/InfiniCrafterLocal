"""Consent-based upgrades touch only changed recommendations, not personal config."""
from __future__ import annotations

import importlib


def test_accept_updates_only_previewed_lines_and_keeps_unrelated_bytes(tmp_path, monkeypatch):
    owner = importlib.import_module('infini_local.desktop.settings_defaults')
    from infini_local.desktop.settings_schema import DEFAULTS
    monkeypatch.setitem(DEFAULTS, 'INFINI_LLM_MAX_TOKENS', '18000')
    config = tmp_path / 'config.env'
    original = (b'\xef\xbb\xbf# personal config\r\nINFINI_LLM_MAX_TOKENS = "9000"\r\n'
                b'INFINI_LLM_PROVIDER=personal-provider\r\n'
                b'INFINI_OPENAI_COMPAT_API_KEY="opaque-test-key"\r\n'
                b'INFINI_SDCPP_MODEL=C:\\Models\\keep.gguf\r\n'
                b'INFINI_LLM_TEMPERATURE=0.5\r\nINFINI_EXTENSION=retain\r\n')
    config.write_bytes(original)
    offer = owner.defaults_offer(config)
    assert offer['version'] == '0.5.02'
    row = next(change for change in offer['changes'] if change['key'] == 'INFINI_LLM_MAX_TOKENS')
    assert row['current'] == '9000' and row['recommended'] == DEFAULTS[row['key']]
    assert {change['key'] for change in offer['changes']} == {'INFINI_LLM_MAX_TOKENS'}
    assert config.read_bytes() == original  # Opening/preview never writes.
    owner.decide_defaults(config, offer['revision'], accept=True)
    assert config.read_bytes() == original.replace(b'"9000"', ('"' + row['recommended'] + '"').encode())
    assert owner.defaults_offer(config)['changes'] == []


def test_change_after_preview_is_not_overwritten(tmp_path, monkeypatch):
    import pytest
    owner = importlib.import_module('infini_local.desktop.settings_defaults')
    from infini_local.desktop.settings_schema import DEFAULTS
    monkeypatch.setitem(DEFAULTS, 'INFINI_LLM_MAX_TOKENS', '18000')
    config = tmp_path / 'config.env'
    config.write_text('INFINI_LLM_MAX_TOKENS=9000\n', encoding='utf-8')
    offer = owner.defaults_offer(config)
    original_offer = owner.defaults_offer
    updated = b'INFINI_LLM_MAX_TOKENS=30000\n# changed in editor\n'
    def change_after_read(path):
        result = original_offer(path)
        config.write_bytes(updated)
        return result
    monkeypatch.setattr(owner, 'defaults_offer', change_after_read)
    with pytest.raises(ValueError, match='изменился'):
        owner.decide_defaults(config, offer['revision'], accept=True)
    assert config.read_bytes() == updated
    assert not config.with_name('config.env.defaults.json').exists()


def test_accept_preserves_config_permissions(tmp_path, monkeypatch):
    import os
    import pytest
    if os.name == 'nt':
        pytest.skip('POSIX mode observer')
    owner = importlib.import_module('infini_local.desktop.settings_defaults')
    from infini_local.desktop.settings_schema import DEFAULTS
    monkeypatch.setitem(DEFAULTS, 'INFINI_LLM_MAX_TOKENS', '18000')
    config = tmp_path / 'config.env'
    config.write_text('INFINI_LLM_MAX_TOKENS=9000\n', encoding='utf-8')
    config.chmod(0o640)
    owner.decide_defaults(config, owner.defaults_offer(config)['revision'], accept=True)
    assert config.stat().st_mode & 0o777 == 0o640


def test_decline_survives_reopen_without_writing_settings(tmp_path, monkeypatch):
    owner = importlib.import_module('infini_local.desktop.settings_defaults')
    from infini_local.desktop.settings_schema import DEFAULTS
    monkeypatch.setitem(DEFAULTS, 'INFINI_LLM_MAX_TOKENS', '18000')
    config = tmp_path / 'config.env'
    original = b'# keep comments\nINFINI_LLM_MAX_TOKENS=9000\nINFINI_EXTENSION_SECRET=opaque-fixture\n'
    config.write_bytes(original)
    offer = owner.defaults_offer(config)
    assert not offer['dismissed']
    assert owner.decide_defaults(config, offer['revision'], accept=False) == {}
    assert config.read_bytes() == original
    reopened = owner.defaults_offer(config)
    assert reopened['dismissed'] and reopened['changes'] == offer['changes']
    assert 'opaque-fixture' not in config.with_name('config.env.defaults.json').read_text()
    # A future recommendation is a new offer, not permanently suppressed.
    monkeypatch.setitem(DEFAULTS, 'INFINI_LLM_MAX_TOKENS', '20000')
    assert not owner.defaults_offer(config)['dismissed']


def test_fresh_missing_and_unchanged_defaults_do_not_touch_config(tmp_path, monkeypatch):
    owner = importlib.import_module('infini_local.desktop.settings_defaults')
    from infini_local.desktop.settings_schema import DEFAULTS
    monkeypatch.setitem(DEFAULTS, 'INFINI_LLM_MAX_TOKENS', '18000')
    monkeypatch.setitem(DEFAULTS, 'INFINI_LLM_TEMPERATURE', '0.42')
    monkeypatch.setattr(owner, 'UPDATED_DEFAULTS', {'INFINI_LLM_MAX_TOKENS': 'budget'})
    config = tmp_path / 'config.env'
    assert owner.defaults_offer(config)['changes'] == [] and not config.exists()
    original = b'INFINI_LLM_MAX_TOKENS=18000\nINFINI_LLM_TEMPERATURE=0.99\n# missing fields inherit\n'
    config.write_bytes(original)
    assert owner.defaults_offer(config)['changes'] == []
    assert config.read_bytes() == original


def test_failed_replace_keeps_original_and_does_not_acknowledge_update(tmp_path, monkeypatch):
    import pytest
    owner = importlib.import_module('infini_local.desktop.settings_defaults')
    from infini_local.desktop.settings_schema import DEFAULTS
    monkeypatch.setitem(DEFAULTS, 'INFINI_LLM_MAX_TOKENS', '18000')
    config = tmp_path / 'config.env'
    original = b'INFINI_LLM_MAX_TOKENS=9000\n'
    config.write_bytes(original)
    def locked_file(_source, _destination):
        raise PermissionError('locked config')
    monkeypatch.setattr(owner.os, 'replace', locked_file)
    with pytest.raises(PermissionError, match='locked config'):
        owner.decide_defaults(config, owner.defaults_offer(config)['revision'], accept=True)
    assert config.read_bytes() == original
    assert not config.with_name('config.env.defaults.json').exists()
    assert not list(tmp_path.glob('*.tmp'))


def test_blank_budget_already_inherits_new_default_and_is_not_materialized(tmp_path, monkeypatch):
    owner = importlib.import_module('infini_local.desktop.settings_defaults')
    from infini_local.desktop.settings_schema import DEFAULTS
    monkeypatch.setitem(DEFAULTS, 'INFINI_LLM_MAX_TOKENS', '18000')
    config = tmp_path / 'config.env'
    original = b'INFINI_LLM_MAX_TOKENS=\n# intentional inheritance\n'
    config.write_bytes(original)
    assert owner.defaults_offer(config)['changes'] == []
    assert config.read_bytes() == original


def test_duplicate_budget_preview_matches_runtime_first_assignment(tmp_path, monkeypatch):
    owner = importlib.import_module('infini_local.desktop.settings_defaults')
    from infini_local.desktop.settings_schema import DEFAULTS
    from infini_local.core.env_utils import load_env_file
    import os
    monkeypatch.setitem(DEFAULTS, 'INFINI_LLM_MAX_TOKENS', '18000')
    monkeypatch.delenv('INFINI_SKIP_CONFIG_FILE', raising=False)
    # Register the key with monkeypatch before the real loader inserts it.
    monkeypatch.setenv('INFINI_LLM_MAX_TOKENS', '18000')
    monkeypatch.delenv('INFINI_LLM_MAX_TOKENS')
    config = tmp_path / 'config.env'
    original = b'INFINI_LLM_MAX_TOKENS=9000\nINFINI_LLM_MAX_TOKENS = "18000"\n'
    config.write_bytes(original)
    offer = owner.defaults_offer(config)
    load_env_file(config)
    assert offer['changes'][0]['current'] == os.environ['INFINI_LLM_MAX_TOKENS'] == '9000'
    owner.decide_defaults(config, offer['revision'], accept=True)
    assert config.read_bytes() == original.replace(b'=9000', b'=18000')


def test_runtime_ui_and_example_use_same_recommended_generation_defaults():
    from pathlib import Path
    import re
    from infini_local.desktop.settings_schema import DEFAULTS
    from infini_local.core import llm_config
    example = (Path(__file__).parents[1] / 'config.example.env').read_text()
    assert DEFAULTS['INFINI_LLM_MAX_TOKENS'] == '18000'
    assert llm_config.LLM_MAX_TOKENS == 18000
    assert DEFAULTS['INFINI_LLM_TIMEOUT'] == '600'
    assert DEFAULTS['INFINI_LLM_REASONING_MODE'] == 'medium'
    assert DEFAULTS['INFINI_LLM_TEMPERATURE'] == '0.5'
    assert DEFAULTS['INFINI_VISUAL_DIRECTOR_TEMPERATURE'] == '0.45'
    for key in ('INFINI_LLM_MAX_TOKENS', 'INFINI_LLM_TIMEOUT', 'INFINI_LLM_REASONING_MODE', 'INFINI_LLM_TEMPERATURE', 'INFINI_VISUAL_DIRECTOR_TEMPERATURE'):
        assert re.search(r'^' + key + '=' + re.escape(DEFAULTS[key]) + r'$', example, re.MULTILINE)


def test_multi_setting_accept_preserves_explicit_stage_budgets_and_unchanged_fields(tmp_path):
    from infini_local.desktop.settings_defaults import defaults_offer, decide_defaults
    from infini_local.desktop.settings_schema import DEFAULTS
    config = tmp_path / 'config.env'
    original = (b'# all revised global defaults\nINFINI_LLM_MAX_TOKENS=9000\nINFINI_LLM_TIMEOUT=95\n'
                b'INFINI_LLM_REASONING_MODE=off\nINFINI_LLM_TEMPERATURE=0.38\n'
                b'INFINI_VISUAL_DIRECTOR_TEMPERATURE=0.42\n'
                b'INFINI_VISUAL_DIRECTOR_MAX_TOKENS=22000\nINFINI_VFX_LLM_DIRECTOR_MAX_TOKENS=24000\n'
                b'INFINI_VFX_LLM_DIRECTOR_TIMEOUT=700\nINFINI_LLM_REAUTHOR_TEMPERATURE=0.22\n'
                b'INFINI_LLM_PROVIDER=my-provider\nINFINI_GUI_PIPELINE_PRESET=Custom\n'
                b'INFINI_CRAFT_HTTP_TIMEOUT_SECONDS=240\n')
    config.write_bytes(original)
    offer = defaults_offer(config)
    assert len(offer['changes']) == 5
    expected = original
    for row in offer['changes']:
        assert row['recommended'] == DEFAULTS[row['key']]
        expected = expected.replace((row['key'] + '=' + row['current'] + '\n').encode(),
                                    (row['key'] + '=' + row['recommended'] + '\n').encode())
    changed = decide_defaults(config, offer['revision'], accept=True)
    assert changed == {row['key']: row['recommended'] for row in offer['changes']}
    assert config.read_bytes() == expected


def test_accept_is_acknowledged_without_a_second_sidecar_write(tmp_path, monkeypatch):
    owner = importlib.import_module('infini_local.desktop.settings_defaults')
    config = tmp_path / 'config.env'
    config.write_bytes(b'INFINI_LLM_MAX_TOKENS=9000\n')
    offer = owner.defaults_offer(config)
    real_write = owner._atomic_write
    def config_write_only(path, content, **kwargs):
        if path != config:
            raise PermissionError('decision sidecar is locked')
        return real_write(path, content, **kwargs)
    monkeypatch.setattr(owner, '_atomic_write', config_write_only)
    assert owner.decide_defaults(config, offer['revision'], accept=True) == {'INFINI_LLM_MAX_TOKENS': '18000'}
    assert config.read_bytes() == b'INFINI_LLM_MAX_TOKENS=18000\n'
    assert owner.defaults_offer(config)['changes'] == []


def test_blank_reasoning_is_explicit_off_not_numeric_inheritance(tmp_path):
    from infini_local.desktop.settings_defaults import defaults_offer, decide_defaults
    config = tmp_path / 'config.env'
    original = b'INFINI_LLM_MAX_TOKENS=\nINFINI_LLM_REASONING_MODE=\n'
    config.write_bytes(original)
    offer = defaults_offer(config)
    assert [(row['key'], row['current'], row['recommended']) for row in offer['changes']] == [
        ('INFINI_LLM_REASONING_MODE', '', 'medium')]
    decide_defaults(config, offer['revision'], accept=True)
    assert config.read_bytes() == original.replace(b'INFINI_LLM_REASONING_MODE=\n', b'INFINI_LLM_REASONING_MODE=medium\n')


def test_equivalent_recommendations_keep_original_spelling_and_bytes(tmp_path):
    from infini_local.desktop.settings_defaults import defaults_offer
    config = tmp_path / 'config.env'
    original = (b'INFINI_LLM_MAX_TOKENS="18000.0"\r\nINFINI_LLM_TIMEOUT=0600\r\n'
                b'INFINI_LLM_TEMPERATURE=.50\r\nINFINI_VISUAL_DIRECTOR_TEMPERATURE=0.450\r\n'
                b'INFINI_LLM_REASONING_MODE=Medium\r\n')
    config.write_bytes(original)
    assert defaults_offer(config)['changes'] == []
    assert config.read_bytes() == original
