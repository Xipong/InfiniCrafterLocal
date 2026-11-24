"""The public Workbench CLI works from the caller directory."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def invoke(tmp_path, *args):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1',
               DOTNET=str(tmp_path / 'absent-dotnet'))
    return subprocess.run([sys.executable, '-m', 'toolbox', 'workbench', *args],
                          cwd=tmp_path, env=env, capture_output=True, text=True)


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
