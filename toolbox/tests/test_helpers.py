from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from test_cli import cli

ROOT = Path(__file__).resolve().parents[2]


def test_doctor_reads_manifest_without_runtime_bootstrap(monkeypatch, capsys):
    code, output = cli(monkeypatch, capsys, 'doctor')
    assert code == 0, output
    report = json.loads(output.out)
    assert report['ok']
    assert report['native']['executed'] is False
    assert report['native']['command'] == json.loads((ROOT / '.agent/manifest.json').read_text())['checks']['native_checks']
    assert report['replayOwner'].endswith('replay_generation_case.py')


def test_verify_executes_existing_owner_with_exact_args_and_exit_status(monkeypatch, capsys):
    observed = []
    def process(command, **kwargs):
        observed.append((command, kwargs))
        return subprocess.CompletedProcess(command, 4)
    monkeypatch.setattr(subprocess, 'run', process)
    code, _ = cli(monkeypatch, capsys, 'verify', '--path', 'toolbox/cli.py', '--plan')
    assert code == 4
    assert observed == [([sys.executable, str(ROOT / 'tools/agentctl.py'), 'verify', '--path', 'toolbox/cli.py', '--plan'], {'cwd': ROOT})]


def test_replay_calls_real_saved_wire_validator_not_inference(monkeypatch, capsys, tmp_path):
    # Deliberately invalid saved wire: the real v5 owner must reject, not merely plan.
    case = tmp_path / 'saved'
    case.mkdir()
    (case / 'final_item.json').write_text('{"runtimeProgram":{"apiVersion":1}}')
    code, output = cli(monkeypatch, capsys, 'replay', case, '--compare')
    assert code == 1, output
    report = json.loads(output.out)
    assert not report['ok']
    assert report['checks'][0]['name'] == 'strict_wire'
    assert report['checks'][0]['status'] == 'failed'
    assert not (case / 'cache').exists()


def test_replay_refuses_live_flags(monkeypatch, capsys, tmp_path):
    code, output = cli(monkeypatch, capsys, 'replay', tmp_path, '--rerun')
    assert code == 2
    assert 'unrecognized' in output.err


def test_doctor_resolves_moved_tool_and_manifest_native_path(monkeypatch, capsys, tmp_path):
    (tmp_path / 'LocalGenerator/infini_local').mkdir(parents=True)
    (tmp_path / 'tools/testing').mkdir(parents=True)
    (tmp_path / '.agent').mkdir()
    (tmp_path / 'tools/agentctl.py').touch()
    (tmp_path / 'tools/testing/replay_generation_case.py').touch()
    (tmp_path / 'tools/testing/Native.csproj').touch()
    (tmp_path / '.agent/manifest.json').write_text(json.dumps({'checks': {'native_checks': ['dotnet', 'build', 'tools/testing/Native.csproj']}}))
    code, output = cli(monkeypatch, capsys, 'doctor', '--project', tmp_path)
    assert code == 0
    report = json.loads(output.out)
    assert report['replayOwner'].endswith('tools/testing/replay_generation_case.py')
    assert report['native']['projectExists'] is True
