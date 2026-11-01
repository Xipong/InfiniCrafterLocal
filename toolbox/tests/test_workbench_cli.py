"""The public workbench entry delegates; it does not own native execution."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
OWNER = ROOT / 'tools/item-test-workbench/workbench.py'


def invoke(tmp_path, *args):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1',
               DOTNET=str(tmp_path / 'absent-dotnet'))
    return subprocess.run([sys.executable, '-m', 'toolbox', 'workbench', *args],
                          cwd=tmp_path, env=env, capture_output=True, text=True)


@pytest.mark.parametrize('status', [0, 1, 2, 7])
def test_forwarding_preserves_argv_exit_and_caller_context(monkeypatch, tmp_path, status):
    from toolbox.cli import main
    monkeypatch.chdir(tmp_path)
    args = ['run', '--item', 'my item.json', '--scenario', '../scene.json',
            '--out', 'new output', '--unknown-owner-flag']
    calls = []

    def child(command, **kwargs):
        calls.append(command)
        assert kwargs == {}  # inherit cwd, environment and all three streams
        assert Path.cwd() == tmp_path
        return subprocess.CompletedProcess(command, status)

    monkeypatch.setattr(subprocess, 'run', child)
    assert main(['workbench', *args]) == status
    assert calls == [[sys.executable, str(OWNER), *args]]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('args', [('--help',), ('run', '--help')])
def test_real_help_is_read_only_without_native_dependencies(tmp_path, args):
    result = invoke(tmp_path, *args)
    assert result.returncode == 0, result.stderr
    assert 'usage:' in result.stdout
    assert not result.stderr
    assert list(tmp_path.iterdir()) == []


def test_real_doctor_reports_missing_dependencies_without_execution(tmp_path):
    result = invoke(tmp_path, 'doctor')
    assert result.returncode == 2, result.stderr
    report = json.loads(result.stdout)
    assert report['ready'] is False
    assert report['checks']['dotnet'] is None
    assert list(tmp_path.iterdir()) == []


def test_unknown_run_flag_is_rejected_by_owner_before_outputs(tmp_path):
    result = invoke(tmp_path, 'run', '--item', 'item.json', '--scenario', 'scenario.json',
                    '--out', 'must-not-exist', '--unknown-owner-flag')
    assert result.returncode == 2
    assert 'unrecognized arguments: --unknown-owner-flag' in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_relative_input_is_resolved_in_caller_cwd(tmp_path):
    # Owner validation reaches this deliberately malformed local file rather than
    # looking under the checkout or creating a run/build as a hidden fallback.
    (tmp_path / 'trace.json').write_text('{}', encoding='utf-8')
    result = invoke(tmp_path, 'inspect', 'trace.json')
    assert result.returncode == 2
    assert 'schemaVersion' in result.stderr
    assert 'No such file' not in result.stderr
    assert sorted(p.name for p in tmp_path.iterdir()) == ['trace.json']
