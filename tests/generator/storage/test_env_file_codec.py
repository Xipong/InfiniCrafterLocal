"""Lossless config.env values across Studio, runtime, defaults and toolbox."""
from __future__ import annotations
from suite_paths import GENERATOR_ROOT, REPO_ROOT

import importlib.util
import json
import os
from pathlib import Path

import pytest

from infini_local.core.env_file import FORMAT_HEADER, encode_value, parse_env_text, read_env_file
from infini_local.core.env_utils import load_env_file
from infini_local.core.generation_defaults import GENERATION_DEFAULTS
from infini_local.desktop import settings_defaults, settings_env
from infini_local.desktop.settings_schema import DEFAULTS
from infini_local.services.sdcpp_backend import DEFAULT_COMMAND_TEMPLATE


VALUES = {
    'INFINI_SDCPP_LORA_PROMPT_TAGS': '<lora:first:0.2>\n<lora:second:0.3>',
    'INFINI_SDCPP_SERVER_COMMAND_TEMPLATE': DEFAULT_COMMAND_TEMPLATE.replace('{exe}', '"{exe}"'),
    'INFINI_SDCPP_MODEL': 'C:\\new\\tools\\model #1.gguf',
    'INFINI_CUSTOM_UNC': '\\\\server\\share\\model.gguf',
    'INFINI_CUSTOM_EMPTY': '',
    'INFINI_CUSTOM_QUOTES': '''first "double" then 'single' and \\\\"''',
    'INFINI_CUSTOM_SPACE': '  keep outer whitespace  ',
    'INFINI_CUSTOM_CONTROL': 'line\r\nnext\tcolumn\vform\fend',
    'INFINI_CUSTOM_UNICODE': 'Террария 🔧 café\u2028middle\u2029end\x85next',
    'INFINI_CUSTOM_LITERAL_ESCAPES': r'\n\r\t\u0041\x00',
    'INFINI_CUSTOM_ASSIGNMENT': 'hello\nINFINI_PORT=6066\n# not a config comment',
    'INFINI_PORT': '5055',
    'CUSTOM_EXTENSION': 'retained=with#punctuation',
}


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    monkeypatch.setattr(os, 'environ', dict(os.environ))
    monkeypatch.delenv('INFINI_SKIP_CONFIG_FILE', raising=False)


def toolbox_module():
    source = REPO_ROOT / 'toolbox' / 'project.py'
    spec = importlib.util.spec_from_file_location('_test_toolbox_env', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_writer_and_every_reader_roundtrip_exact_values(tmp_path, monkeypatch):
    project = tmp_path / 'project'
    (project / 'generator').mkdir(parents=True)
    config = project / 'generator/config.env'
    settings_env.write_env(config, VALUES)
    text = config.read_text()
    assert FORMAT_HEADER in text
    assert '\\nINFINI_PORT=6066' in text
    assert all(settings_env.parse_env(config)[key] == value for key, value in VALUES.items())
    assert all(read_env_file(config)[key] == value for key, value in VALUES.items())
    for key in (*DEFAULTS, *VALUES):
        monkeypatch.delenv(key, raising=False)
    load_env_file(config)
    assert all(os.environ[key] == value for key, value in VALUES.items())
    for key in (*DEFAULTS, *VALUES):
        monkeypatch.delenv(key, raising=False)
    toolbox_values = toolbox_module().read_config_env(config)
    assert all(toolbox_values[key] == value for key, value in VALUES.items())


def test_environment_precedence_and_skip_config_are_preserved(tmp_path, monkeypatch):
    config = tmp_path / 'config.env'
    settings_env.write_env(config, {'INFINI_CUSTOM_TEST': 'from file'})
    monkeypatch.setenv('INFINI_CUSTOM_TEST', 'from environment')
    load_env_file(config)
    assert os.environ['INFINI_CUSTOM_TEST'] == 'from environment'
    monkeypatch.delenv('INFINI_CUSTOM_TEST')
    monkeypatch.setenv('INFINI_SKIP_CONFIG_FILE', '1')
    load_env_file(config)
    assert 'INFINI_CUSTOM_TEST' not in os.environ


def test_unversioned_config_is_refused_without_touching_file_or_environment(tmp_path, monkeypatch):
    config = tmp_path / 'config.env'
    original = (b'\xef\xbb\xbf# personal config\r\nINFINI_SDCPP_MODEL="C:\\new\\tools\\model.gguf"\r\n'
                b'INFINI_OPENAI_COMPAT_API_KEY="secret\\n\\t\\u0041"\r\n')
    config.write_bytes(original)
    monkeypatch.delenv('INFINI_OPENAI_COMPAT_API_KEY', raising=False)
    with pytest.raises(ValueError, match='Missing config.env format declaration'):
        read_env_file(config)
    with pytest.raises(ValueError, match='Missing config.env format declaration'):
        parse_env_text(original.decode('utf-8-sig'))
    assert 'INFINI_OPENAI_COMPAT_API_KEY' not in os.environ
    assert config.read_bytes() == original


def test_first_duplicate_matches_runtime_for_all_readers(tmp_path, monkeypatch):
    config = tmp_path / 'config.env'
    config.write_text(FORMAT_HEADER + '\nINFINI_DUPLICATE=first\nINFINI_DUPLICATE=second\n')
    assert settings_env.parse_env(config)['INFINI_DUPLICATE'] == 'first'
    monkeypatch.delenv('INFINI_DUPLICATE', raising=False)
    load_env_file(config)
    assert os.environ['INFINI_DUPLICATE'] == 'first'


def test_versioned_files_allow_bare_manual_values_and_reject_invalid_json_without_leaking(tmp_path, monkeypatch):
    assert parse_env_text(FORMAT_HEADER + '\nINFINI_PORT=5055\n')['INFINI_PORT'] == '5055'
    config = tmp_path / 'config.env'
    config.write_text(FORMAT_HEADER + '\nINFINI_BEFORE="valid"\nINFINI_API_KEY="private-test-secret\\qbad"\n')
    monkeypatch.delenv('INFINI_BEFORE', raising=False)
    with pytest.raises(ValueError) as error:
        load_env_file(config)
    assert 'private-test-secret' not in str(error.value)
    assert 'line 3' in str(error.value)
    assert 'INFINI_BEFORE' not in os.environ


@pytest.mark.parametrize('header', [
    '# infini-config-format: unknown-v9', '# infini-config-format:',
    FORMAT_HEADER + ' trailing-garbage', 'INFINI_TEST=value\n' + FORMAT_HEADER,
    FORMAT_HEADER + '\nINFINI_TEST=value\n' + FORMAT_HEADER,
])
def test_unknown_or_late_version_is_not_silently_loaded(header):
    with pytest.raises(ValueError, match='format declaration'):
        parse_env_text(header + '\nINFINI_TEST=value\n')


def test_default_acceptance_preserves_encoded_personal_bytes_and_line_endings(tmp_path, monkeypatch):
    monkeypatch.setitem(GENERATION_DEFAULTS, 'INFINI_LLM_MAX_TOKENS', '18000')
    config = tmp_path / 'config.env'
    original = ('\ufeff' + FORMAT_HEADER + '\r\n'
        '# keep comments\r\nINFINI_LLM_MAX_TOKENS = "9000"  \r\n'
        'INFINI_SDCPP_LORA_PROMPT_TAGS=' + encode_value(VALUES['INFINI_SDCPP_LORA_PROMPT_TAGS']) + '\r\n'
        'INFINI_CUSTOM_UNICODE=' + encode_value(VALUES['INFINI_CUSTOM_UNICODE']) + '\r\n'
        'INFINI_SDCPP_MODEL=' + encode_value(VALUES['INFINI_SDCPP_MODEL']) + '\r\n').encode('utf-8')
    config.write_bytes(original)
    offer = settings_defaults.defaults_offer(config)
    assert {row['key'] for row in offer['changes']} == {'INFINI_LLM_MAX_TOKENS'}
    settings_defaults.decide_defaults(config, offer['revision'], accept=True)
    assert config.read_bytes() == original.replace(b'"9000"', b'"18000"')
    assert settings_defaults.defaults_offer(config)['changes'] == []
    assert read_env_file(config)['INFINI_SDCPP_LORA_PROMPT_TAGS'] == VALUES['INFINI_SDCPP_LORA_PROMPT_TAGS']


def test_full_save_preserves_current_values_without_migration(tmp_path):
    config = tmp_path / 'config.env'
    settings_env.write_env(config, VALUES)
    current = settings_env.parse_env(config)
    settings_env.write_env(config, current)
    assert settings_env.parse_env(config) == current


def test_atomic_replace_failure_keeps_original_and_cleans_temporary(tmp_path, monkeypatch):
    config = tmp_path / 'config.env'
    original = b'# personal file\nINFINI_TEST=keep\n'
    config.write_bytes(original)
    def fail(*args):
        raise OSError('synthetic replace failure')
    monkeypatch.setattr(settings_env.os, 'replace', fail)
    with pytest.raises(OSError):
        settings_env.write_env(config, {'INFINI_TEST': 'new'})
    assert config.read_bytes() == original
    assert sorted(path.name for path in tmp_path.iterdir()) == ['config.env']


def test_atomic_write_failure_keeps_original(tmp_path, monkeypatch):
    config = tmp_path / 'config.env'
    config.write_text('INFINI_TEST=keep\n')
    monkeypatch.setattr(settings_env.os, 'fsync', lambda *_args: (_ for _ in ()).throw(OSError('synthetic flush failure')))
    with pytest.raises(OSError):
        settings_env.write_env(config, {'INFINI_TEST': 'new'})
    assert config.read_text() == 'INFINI_TEST=keep\n'
    assert sorted(path.name for path in tmp_path.iterdir()) == ['config.env']


def test_atomic_save_preserves_existing_symlink_and_file_permissions(tmp_path):
    original = tmp_path / 'personal.env'
    original.write_text('INFINI_TEST=keep\n')
    original.chmod(0o600)
    config = tmp_path / 'config.env'
    try:
        config.symlink_to(original)
    except OSError:
        pytest.skip('Test environment cannot create symlinks')
    settings_env.write_env(config, {'INFINI_TEST': 'updated'})
    assert config.is_symlink()
    assert read_env_file(original)['INFINI_TEST'] == 'updated'
    assert original.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('data', [{'INFINI_TEST': 'a\x00b'}, {'bad\nkey': 'value'}, {'#comment': 'value'}, {' spaced ': 'value'}])
def test_unsupported_keys_or_values_fail_before_replacing_file(tmp_path, data):
    config = tmp_path / 'config.env'
    config.write_text('INFINI_TEST=keep\n')
    with pytest.raises(ValueError):
        settings_env.write_env(config, data)
    assert config.read_text() == 'INFINI_TEST=keep\n'


@pytest.mark.parametrize('escaped', [r'\ud800', r'\udfff', r'\u0000'])
def test_invalid_environment_codepoints_rejected_before_any_mutation(tmp_path, monkeypatch, escaped):
    config = tmp_path / 'config.env'
    config.write_text(FORMAT_HEADER + '\nINFINI_BEFORE="value"\nINFINI_BAD="' + escaped + '"\n')
    monkeypatch.delenv('INFINI_BEFORE', raising=False)
    with pytest.raises(ValueError):
        load_env_file(config)
    assert 'INFINI_BEFORE' not in os.environ
    with pytest.raises(ValueError):
        encode_value(json.loads('"' + escaped + '"'))


def test_cr_only_records_share_decoder_and_defaults_patch(tmp_path, monkeypatch):
    monkeypatch.setitem(GENERATION_DEFAULTS, 'INFINI_LLM_MAX_TOKENS', '18000')
    config = tmp_path / 'config.env'
    original = (FORMAT_HEADER + '\r').encode() + b'# Mac record endings\rINFINI_LLM_MAX_TOKENS=9000\rINFINI_CUSTOM=preserve\r'
    config.write_bytes(original)
    assert read_env_file(config) == parse_env_text(original.decode())
    offer = settings_defaults.defaults_offer(config)
    assert {row['key'] for row in offer['changes']} == {'INFINI_LLM_MAX_TOKENS'}
    settings_defaults.decide_defaults(config, offer['revision'], accept=True)
    assert config.read_bytes() == original.replace(b'9000', b'"18000"')


@pytest.mark.parametrize('raw, expected', [
    ('bare value', 'bare value'),
    ("'literal quotes'", "'literal quotes'"),
    ('C:\\new\\tools\\', 'C:\\new\\tools\\'),
    ('"line\\nnext"', 'line\nnext'),
])
def test_current_manual_values_use_only_the_declared_codec(raw, expected):
    assert parse_env_text(FORMAT_HEADER + '\nVALUE=' + raw) == {'VALUE': expected}


def test_current_example_is_readable_without_migration():
    example = GENERATOR_ROOT / 'config.example.env'
    original = example.read_bytes()
    values = read_env_file(example)
    assert values['INFINI_LLM_MAX_TOKENS'] == '18000'
    assert example.read_bytes() == original


def test_selective_patch_encodes_multiline_and_ignores_absent_keys():
    from infini_local.core.env_file import replace_env_values
    original = FORMAT_HEADER + '\r\n# keep\r\nEXISTING = old  \r\nUNKNOWN=retain'
    patched = replace_env_values(original, {'EXISTING': 'new\nvalue', 'ABSENT': 'never inserted'})
    assert patched == original.replace('old', '"new\\nvalue"')
    assert parse_env_text(patched) == {'EXISTING': 'new\nvalue', 'UNKNOWN': 'retain'}


def test_selective_patch_refuses_unversioned_wire():
    from infini_local.core.env_file import replace_env_values
    with pytest.raises(ValueError, match='Missing config.env format declaration'):
        replace_env_values('EXISTING=old\n', {'EXISTING': 'new'})


@pytest.mark.parametrize('header', [FORMAT_HEADER, ''])
def test_raw_nul_rejected_before_runtime_mutation(tmp_path, monkeypatch, header):
    config = tmp_path / 'config.env'
    original = (header + '\nINFINI_BEFORE=valid\nINFINI_SECRET=secret\x00data\n').encode()
    config.write_bytes(original)
    monkeypatch.delenv('INFINI_BEFORE', raising=False)
    with pytest.raises(ValueError) as error:
        load_env_file(config)
    assert 'secret' not in str(error.value)
    assert 'INFINI_BEFORE' not in os.environ
    assert config.read_bytes() == original


def test_invalid_file_does_not_partially_change_process_environment(tmp_path, monkeypatch):
    config = tmp_path / 'config.env'
    original = (FORMAT_HEADER + '\nINFINI_BEFORE=valid\nINFINI_SECRET="bad\\qescape"\n').encode()
    config.write_bytes(original)
    monkeypatch.setenv('INFINI_LLM_REAUTHOR_TEMPERATURE', '0.23')
    monkeypatch.delenv('INFINI_LLM_REPAIR_TEMPERATURE', raising=False)
    monkeypatch.delenv('INFINI_BEFORE', raising=False)
    before = dict(os.environ)
    with pytest.raises(ValueError, match='Invalid JSON string'):
        load_env_file(config)
    assert dict(os.environ) == before
    assert config.read_bytes() == original
    assert list(tmp_path.iterdir()) == [config]
