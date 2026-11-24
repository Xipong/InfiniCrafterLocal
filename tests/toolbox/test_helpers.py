from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from tests.toolbox.test_cli import cli

ROOT = Path(__file__).resolve().parents[2]


def test_doctor_reads_manifest_without_runtime_bootstrap(monkeypatch, capsys):
    code, output = cli(monkeypatch, capsys, 'doctor')
    assert code == 0, output
    report = json.loads(output.out)
    assert report['ok']
    assert report['native']['executed'] is False


def test_verify_plans_the_requested_test_from_an_external_directory(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    command = [sys.executable, "-m", "toolbox", "verify", "--path", "tests/toolbox/test_helpers.py", "--plan"]
    plan = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15)
    assert plan.returncode == 0, plan.stderr
    report = json.loads(plan.stdout)
    assert report["scope"] == "paths"
    assert report["tests"] == ["tests/toolbox/test_helpers.py"]
    failure = subprocess.run([*command, "--changed"], cwd=tmp_path, env=env,
                             capture_output=True, text=True, timeout=15)
    assert failure.returncode == 2
    assert json.loads(failure.stderr)["ok"] is False


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


def test_replay_preserves_caller_relative_case_and_project(monkeypatch, capsys, tmp_path):
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture

    case = tmp_path / 'saved'
    case.mkdir()
    source = json.dumps(compile_runtime_program(build_runtime_fixture('workbench_blade')))
    (case / 'final_item.json').write_text(source)
    for cwd, path, project in ((tmp_path, case, ROOT), (tmp_path, Path('saved'), ROOT),
                               (ROOT.parent, case, Path(ROOT.name))):
        monkeypatch.chdir(cwd)
        code, output = cli(monkeypatch, capsys, 'replay', path, '--project', project)
        assert code == 0, output
        report = json.loads(output.out)
        assert report['ok'] is True
        assert Path(report['caseDir']) == case
    assert (case / 'final_item.json').read_text() == source
    assert sorted(p.name for p in case.iterdir()) == ['final_item.json']


def test_doctor_resolves_moved_tool_and_manifest_native_path(monkeypatch, capsys, tmp_path):
    (tmp_path / 'generator/infini_local').mkdir(parents=True)
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
