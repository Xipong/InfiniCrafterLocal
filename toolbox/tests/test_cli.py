"""Offline behavioral coverage: no external route is allowed, even on failure."""
from __future__ import annotations

import json
from pathlib import Path
import runpy
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]




def cli(monkeypatch, capsys, *args):
    monkeypatch.setattr(sys, 'argv', ['toolbox', *map(str, args)])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module('toolbox', run_name='__main__')
    return exc.value.code, capsys.readouterr()


@pytest.mark.parametrize('panel,count', [('live10', 10), ('live20', 20)])
def test_default_cli_preflight_selects_real_parents_without_bootstrap(monkeypatch, capsys, tmp_path, panel, count):
    before = set(tmp_path.rglob('*'))
    import builtins
    original_import = builtins.__import__
    def no_runtime(name, *args, **kwargs):
        if name.startswith('infini_local'):
            pytest.fail('preflight imported production runtime')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', no_runtime)
    code, captured = cli(monkeypatch, capsys, panel)
    assert code == 0, captured
    report = json.loads(captured.out)
    assert report['preflightOnly'] is True
    assert report['realImageGeneration'] is False
    assert report['caseCount'] == count
    assert len({case['case'] for case in report['cases']}) == count
    assert all(case['itemA'] and case['itemB'] for case in report['cases'])
    assert report['panelProvenance'].startswith('Live20')
    assert set(tmp_path.rglob('*')) == before


@pytest.mark.parametrize('flags,fragment', [
    (['--expected-case-count', '11'], 'expected 11'),
    (['--cases', 'missing'], 'unknown case'),
    (['--parallel-crafts', '0'], 'parallel-crafts'),
    (['--transport-retries', '-1'], 'transport-retries'),
    (['--transport-retry-delay-seconds', '1'], 'transport-retry-delay'),
    (['--min-first-author', '11'], 'min-first-author'),
    (['--expected-head', '0' * 40], 'HEAD'),
    (['--run'], 'requires'),
    (['--run', '--preflight-only'], 'mutually exclusive'),
])
def test_cli_refuses_invalid_boundaries_before_bootstrap(monkeypatch, capsys, flags, fragment):
    code, captured = cli(monkeypatch, capsys, 'live10', *flags)
    assert code == 2
    assert fragment in captured.err


def test_private_config_is_checked_not_printed(monkeypatch, capsys, tmp_path):
    config = tmp_path / 'private.env'
    config.write_text('INFINI_LLM_PROVIDER=openai_compat\nINFINI_OPENAI_COMPAT_MODEL=qa-model\nINFINI_OPENAI_COMPAT_API_KEY=TOP-SECRET\nINFINI_OPENAI_COMPAT_BASE_URL=https://example.invalid/v1/\n')
    code, captured = cli(monkeypatch, capsys, 'live10', '--config', config, '--expected-model', 'wrong')
    assert code == 2
    assert 'model' in captured.err.lower()
    assert 'TOP-SECRET' not in captured.out + captured.err
    code, captured = cli(monkeypatch, capsys, 'live10', '--config', config, '--expected-model', 'qa-model')
    assert code == 0
    assert json.loads(captured.out)['configured']['model'] == 'qa-model'
    assert 'TOP-SECRET' not in captured.out + captured.err


def test_clean_head_binding_rejects_dirty_source(monkeypatch, capsys, tmp_path):
    import subprocess
    project = tmp_path / 'source'
    (project / 'LocalGenerator/infini_local').mkdir(parents=True)
    subprocess.run(['git', 'init', '-q', str(project)], check=True)
    subprocess.run(['git', '-C', str(project), '-c', 'user.name=QA', '-c', 'user.email=qa@example.invalid', 'commit', '--allow-empty', '-qm', 'fixture'], check=True)
    head = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
    code, _ = cli(monkeypatch, capsys, 'live10', '--project', project, '--expected-head', head)
    assert code == 0
    (project / 'dirty.txt').write_text('changed input')
    code, captured = cli(monkeypatch, capsys, 'live10', '--project', project, '--expected-head', head)
    assert code == 2
    assert 'clean' in captured.err


def test_deliberate_run_dispatches_canonical_harness_and_propagates_status(monkeypatch, capsys, tmp_path):
    import subprocess
    project = tmp_path / 'source'
    (project / 'LocalGenerator/infini_local').mkdir(parents=True)
    subprocess.run(['git', 'init', '-q', str(project)], check=True)
    subprocess.run(['git', '-C', str(project), '-c', 'user.name=QA', '-c', 'user.email=qa@example.invalid', 'commit', '--allow-empty', '-qm', 'fixture'], check=True)
    head = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
    config = tmp_path / 'private.env'
    config.write_text('INFINI_LLM_PROVIDER=openai_compat\nINFINI_OPENAI_COMPAT_MODEL=qa-model\nINFINI_OPENAI_COMPAT_BASE_URL=https://example.invalid/v1\nINFINI_LLM_API_MODE=chat_completions\nINFINI_LLM_RESPONSE_FORMAT=json_object\n')
    config.write_text(config.read_text() + '\nINFINI_USE_LLM=1\n')
    calls = []
    original_run = subprocess.run
    def dispatched(command, **kwargs):
        if 'toolbox.live.runner' not in command:
            return original_run(command, **kwargs)
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 7)
    monkeypatch.setattr(subprocess, 'run', dispatched)
    flags = ['--run', '--project', project, '--config', config, '--output', tmp_path / 'out',
             '--expected-head', head, '--expected-provider', 'openai_compat', '--expected-model', 'qa-model',
             '--expected-base-url', 'https://example.invalid/v1', '--expected-api-mode', 'chat_completions',
             '--expected-response-format', 'json_object', '--expected-temperature', '0.5',
             '--expected-vfx-temperature', '0.34', '--expected-repair-temperature', '0.12',
             '--expected-max-tokens', '18000', '--expected-visual-max-tokens', '18000', '--expected-vfx-max-tokens', '18000']
    code, _ = cli(monkeypatch, capsys, 'live10', *flags)
    assert code == 7
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[:3] == [sys.executable, '-m', 'toolbox.live.runner']
    assert command[3:5] == ['--panel', 'live10']
    assert '--run' in command
    assert kwargs['cwd'] == ROOT
    assert not (tmp_path / 'out').exists()
    config.write_text(config.read_text().replace('INFINI_USE_LLM=1', 'INFINI_USE_LLM=0'))
    code, output = cli(monkeypatch, capsys, 'live10', *flags)
    assert code == 2
    assert 'INFINI_USE_LLM' in output.err
    assert len(calls) == 1


@pytest.mark.parametrize('kind,fragment', [('duplicate', 'repeats'), ('missing', 'missing'), ('invalid', 'invalid case')])
def test_custom_cases_validate_real_fixture(monkeypatch, capsys, tmp_path, kind, fragment):
    cases = [{'case': 'custom', 'itemA': 'WoodenSword', 'itemB': 'WorkBench'}]
    if kind == 'duplicate':
        cases *= 2
    elif kind == 'missing':
        cases[0]['itemA'] = 'NotInSnapshot'
    else:
        cases[0]['case'] = '../unsafe'
    file = tmp_path / 'cases.json'
    file.write_text(json.dumps(cases))
    code, captured = cli(monkeypatch, capsys, 'live10', '--cases-file', file)
    assert code == 2
    assert fragment in captured.err


@pytest.mark.parametrize('endpoint', ['https://secret:password@example.invalid', 'https://example.invalid/?token=secret'])
def test_credentials_in_endpoint_are_refused_without_echo(monkeypatch, capsys, tmp_path, endpoint):
    config = tmp_path / 'private.env'
    config.write_text('INFINI_OPENAI_COMPAT_BASE_URL=' + endpoint)
    code, captured = cli(monkeypatch, capsys, 'live10', '--config', config)
    assert code == 2
    assert 'secret' not in captured.out + captured.err


def test_explicit_missing_private_config_is_not_silently_ignored(monkeypatch, capsys, tmp_path):
    code, output = cli(monkeypatch, capsys, 'live10', '--config', tmp_path / 'missing.env')
    assert code == 2
    assert 'config' in output.err


def test_duplicate_parent_snapshot_identity_is_refused(monkeypatch, capsys, tmp_path):
    dump = tmp_path / 'duplicate.jsonl'
    fixture = (ROOT / 'toolbox/fixtures/items.jsonl').read_text(encoding='utf-8-sig')
    dump.write_text(fixture + '\n' + fixture.splitlines()[0] + '\n')
    code, output = cli(monkeypatch, capsys, 'live10', '--runtime-dump', dump)
    assert code == 2
    assert 'duplicate parent' in output.err


def test_skip_config_does_not_read_operator_profile_unless_explicit(monkeypatch, capsys, tmp_path):
    project = tmp_path / 'source'
    (project / 'LocalGenerator/infini_local').mkdir(parents=True)
    config = project / 'LocalGenerator/config.env'
    config.write_text('INFINI_OPENAI_COMPAT_MODEL=private-model\n')
    monkeypatch.setenv('INFINI_SKIP_CONFIG_FILE', '1')
    code, output = cli(monkeypatch, capsys, 'live10', '--project', project)
    assert code == 0
    assert json.loads(output.out)['configured']['model'] == ''
    code, output = cli(monkeypatch, capsys, 'live10', '--project', project, '--config', config)
    assert code == 0
    assert json.loads(output.out)['configured']['model'] == 'private-model'


def test_named_panel_is_not_silently_reduced_by_legacy_environment(monkeypatch, capsys):
    monkeypatch.setenv('INFINI_LIVE_CASES', 'woodwork_blade')
    code, output = cli(monkeypatch, capsys, 'live20')
    assert code == 0
    assert json.loads(output.out)['caseCount'] == 20


@pytest.mark.parametrize('selection', ['', 'woodwork_blade,woodwork_blade'])
def test_explicit_empty_or_duplicate_selection_is_refused(monkeypatch, capsys, selection):
    code, output = cli(monkeypatch, capsys, 'live10', '--cases', selection)
    assert code == 2
    assert '--cases' in output.err


def test_public_panel_name_cannot_be_overridden(monkeypatch, capsys):
    code, output = cli(monkeypatch, capsys, 'live10', '--panel', 'live20')
    assert code == 2
    assert 'unrecognized' in output.err
