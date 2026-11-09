"""Offline CLI dispatch, without running a native executable or a provider."""
from __future__ import annotations

import builtins
from pathlib import Path
import subprocess

import pytest

from tests.toolbox.test_cli import cli

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('panel, manifest', [('live10', 'live10-midgame'), ('live40', 'live40-diverse')])
@pytest.mark.parametrize('dll', [False, True])
@pytest.mark.parametrize('returncode', [0, 7])
def test_capture_forwards_absolute_paths_and_native_status_without_bootstrap(monkeypatch, capsys, tmp_path, dll, returncode, panel, manifest):
    original_import = builtins.__import__
    def no_bootstrap(name, *args, **kwargs):
        if name.startswith('infini_local') or name in ('toolbox.live.preflight', 'toolbox.live.runner', 'toolbox.live.real_run'):
            pytest.fail('offline capture imported provider admission/runtime')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', no_bootstrap)
    executable = tmp_path / ('EngineRuntimeChecks.dll' if dll else 'EngineRuntimeChecks')
    executable.touch()
    host = tmp_path / 'dotnet'
    host.touch()
    monkeypatch.chdir(tmp_path)
    calls = []
    def process(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, returncode)
    monkeypatch.setattr(subprocess, 'run', process)
    flags = ['--dotnet', Path('dotnet')] if dll else []
    code, _ = cli(monkeypatch, capsys, panel, '--offline', '--native-executable', executable.name,
                  '--output', 'capture', *flags)
    assert code == returncode
    prefix = [str(host), str(executable)] if dll else [str(executable)]
    assert calls == [(prefix + ['--capture-parent-panel', str(ROOT / f'toolbox/fixtures/panels/{manifest}.json'), str(tmp_path / 'capture')], {})]
    assert not (tmp_path / 'capture').exists()


def test_dll_uses_dotnet_from_path_when_unspecified(monkeypatch, capsys, tmp_path):
    executable = tmp_path / 'EngineRuntimeChecks.dll'
    executable.touch()
    calls = []
    def process(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(subprocess, 'run', process)
    code, _ = cli(monkeypatch, capsys, 'live40', '--offline', '--native-executable', executable, '--output', tmp_path / 'capture')
    assert code == 0 and calls[0][:2] == ['dotnet', str(executable)]


@pytest.mark.parametrize('flag', ['--run', '--real-images', '--runtime-dump', '--config', '--cases-file', '--preset', '--preflight-only'])
def test_live_flags_cannot_enter_offline_capture(monkeypatch, capsys, tmp_path, flag):
    executable = tmp_path / 'EngineRuntimeChecks'
    executable.touch()
    def forbidden(*args, **kwargs):
        pytest.fail('invalid flags started native capture')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    code, output = cli(monkeypatch, capsys, 'live40', '--offline', '--native-executable', executable,
                       '--output', tmp_path / 'out', flag)
    assert code == 2 and 'unrecognized arguments' in output.err
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('kind', ['missing_executable', 'used_output', 'file_output', 'host_with_exe', 'missing_host'])
def test_capture_invalid_paths_never_start_process(monkeypatch, capsys, tmp_path, kind):
    executable = tmp_path / ('EngineRuntimeChecks.dll' if kind == 'missing_host' else 'EngineRuntimeChecks')
    if kind != 'missing_executable':
        executable.touch()
    output = tmp_path / 'out'
    if kind == 'used_output':
        output.mkdir()
        (output / 'prior-evidence').write_text('preserve')
    elif kind == 'file_output':
        output.touch()
    flags = ['--dotnet', tmp_path / 'missing'] if kind in ('host_with_exe', 'missing_host') else []
    def forbidden(*args, **kwargs):
        pytest.fail('invalid paths started native capture')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    code, _ = cli(monkeypatch, capsys, 'live40', '--offline', '--native-executable', executable, '--output', output, *flags)
    assert code == 2
    if kind == 'used_output':
        assert (output / 'prior-evidence').read_text() == 'preserve'


def test_capture_missing_dotnet_is_clear_error(monkeypatch, capsys, tmp_path):
    executable = tmp_path / 'EngineRuntimeChecks.dll'
    executable.touch()
    def missing(*args, **kwargs):
        raise FileNotFoundError('dotnet host is not available')
    monkeypatch.setattr(subprocess, 'run', missing)
    code, output = cli(monkeypatch, capsys, 'live40', '--offline', '--native-executable', executable, '--output', tmp_path / 'out')
    assert code == 2 and 'dotnet host is not available' in output.err
    assert 'Traceback' not in output.err
