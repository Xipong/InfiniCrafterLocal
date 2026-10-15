"""Offline selection contracts for the two supported pytest roots."""
from __future__ import annotations

from pathlib import Path
import json
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import agentctl  # noqa: E402
import run_changed_pytests as changed  # noqa: E402
import run_focused_pytests as focused  # noqa: E402
import run_pytest_shards as shards  # noqa: E402


def _git_status(monkeypatch: pytest.MonkeyPatch, status: str) -> None:
    monkeypatch.setattr(agentctl, "changed_files", lambda base=None: [line[3:] for line in status.splitlines() if line])


def test_production_change_selects_existing_owner_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    _git_status(monkeypatch, " M LocalGenerator/infini_local/core/runtime_authoring/program_schema.py\n")
    plan = changed.build_plan()
    assert "LocalGenerator/tests/test_registry_vertical_contract.py" in plan["selected"]
    assert "LocalGenerator/tests/test_web_studio.py" not in plan["selected"]
    assert plan["mode"] == "owner_areas"
    assert plan["fullSelectionTriggers"] == []
    assert plan["releaseReady"] is False


def test_no_changed_paths_is_not_a_test_pass(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _git_status(monkeypatch, "")
    assert changed.main([]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "not_selected"
    assert report["ok"] is False
    assert report["selected"] == []


@pytest.mark.parametrize("path", [
    "pyproject.toml", "LocalGenerator/infini_local/new_owner.py", "toolbox/fixtures/items.jsonl",
    "LocalGenerator/tests/conftest.py", "LocalGenerator/tests/test_deleted.py",
])
def test_shared_config_or_deleted_test_selects_both_roots(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    status = " D " if path.endswith("test_deleted.py") else " M "
    _git_status(monkeypatch, status + path + "\n")
    assert changed.build_plan()["selected"] == ["LocalGenerator/tests", "toolbox/tests"]


def test_changed_runner_does_not_select_external_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    test_root = root / "toolbox/tests"
    test_root.mkdir(parents=True)
    outside = tmp_path / "test_external.py"
    outside.write_text("def test_external(): pass\n", encoding="utf-8")
    (test_root / "test_external.py").symlink_to(outside)
    monkeypatch.setattr(changed, "ROOT", root)
    monkeypatch.setattr(agentctl, "ROOT", root)
    _git_status(monkeypatch, "?? toolbox/tests/test_external.py\n")
    plan = changed.build_plan()
    assert plan["changedModules"] == []
    assert plan["selected"] == ["LocalGenerator/tests", "toolbox/tests"]


def test_changed_toolbox_module_is_selected_without_broad_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    _git_status(monkeypatch, " M toolbox/tests/test_live20_support_v5.py\n")
    plan = changed.build_plan()
    assert plan["mode"] == "changed_modules"
    assert plan["selected"] == ["toolbox/tests/test_live20_support_v5.py"]
    assert plan["uncoveredChangePaths"] == []


@pytest.mark.parametrize("doc", ["docs/overview.md", "README.md", "AGENTS.md", "START_HERE.html"])
def test_selected_subset_with_uncovered_docs_is_not_a_complete_pass(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], doc: str
) -> None:
    status = f" M toolbox/tests/test_live20_support_v5.py\n M {doc}\n"
    def fake_run(cmd, **kw):
        if cmd[:2] == ["git", "status"]:
            return SimpleNamespace(returncode=0, stdout=status, stderr="")
        return SimpleNamespace(returncode=0, stdout="1 passed", stderr="")
    _git_status(monkeypatch, status)
    monkeypatch.setattr(changed.subprocess, "run", fake_run)
    assert changed.main([]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "partial"
    assert report["uncoveredChangePaths"] == [doc]
    assert report["selected"] == ["toolbox/tests/test_live20_support_v5.py"]


def test_focused_accepts_toolbox_test_but_rejects_outside_and_non_tests() -> None:
    assert focused._safe_test_path("toolbox/tests/test_live20_support_v5.py") == ROOT / "toolbox/tests/test_live20_support_v5.py"
    for raw in ("toolbox/live-generation", "toolbox/tests/../live-generation", "tools/run_pytest_shards.py"):
        with pytest.raises(ValueError):
            focused._safe_test_path(raw)


def test_focused_forces_offline_config_even_if_parent_enables_live(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INFINI_TEST_USE_PROJECT_CONFIG", "1")
    monkeypatch.setattr(focused.sys, "argv", ["run_focused_pytests.py", "toolbox/tests/test_live20_support_v5.py"])
    def fake_run(command, **kwargs):
        assert kwargs["env"]["INFINI_TEST_USE_PROJECT_CONFIG"] == "0"
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(focused.subprocess, "run", fake_run)
    assert focused.main() == 0


def test_shard_inventory_includes_toolbox_offline_tests() -> None:
    files = {path.relative_to(ROOT).as_posix() for path in shards._test_files()}
    assert "LocalGenerator/tests/test_pytest_runner_selection.py" in files
    assert "toolbox/tests/test_live20_support_v5.py" in files


def test_shard_inventory_rejects_symlink_outside_supported_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "toolbox/tests"
    root.mkdir(parents=True)
    outside = tmp_path / "test_external.py"
    outside.write_text("def test_external(): pass\n", encoding="utf-8")
    (root / "test_external.py").symlink_to(outside)
    monkeypatch.setattr(shards, "TEST_ROOTS", (root,))
    assert shards._test_files() == []


@pytest.mark.parametrize("local_count", [1, 4], ids=["single-batch", "bounded-batches"])
def test_shard_sandbox_executes_both_roots_with_repo_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, local_count: int
) -> None:
    repo = tmp_path / "repo"
    local = repo / "LocalGenerator/tests/test_local_selection.py"
    toolbox = repo / "toolbox/tests/test_toolbox_selection.py"
    for metadata in (repo / ".gitnexus/index.db", repo / ".gitnexusrc"):
        metadata.parent.mkdir(parents=True, exist_ok=True)
        metadata.write_text("workspace index is not a test dependency", encoding="utf-8")
    locals_ = [local, *[local.with_name(f"test_local_selection_{i}.py") for i in range(1, local_count)]]
    files = [*locals_, toolbox]
    for test_file in files:
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("import os\nfrom pathlib import Path\n\ndef test_offline():\n    assert os.environ['INFINI_TEST_USE_PROJECT_CONFIG'] == '0'\n    assert not (Path.cwd().parent / '.gitnexus').exists()\n    assert not (Path.cwd().parent / '.gitnexusrc').exists()\n", encoding="utf-8")
    (repo / "toolbox/__init__.py").write_text("OFFLINE_MARKER = 1\n", encoding="utf-8")
    toolbox.write_text("from toolbox import OFFLINE_MARKER\n\ndef test_offline():\n    assert OFFLINE_MARKER == 1\n", encoding="utf-8")
    monkeypatch.setenv("INFINI_TEST_USE_PROJECT_CONFIG", "1")
    monkeypatch.setattr(shards, "ROOT", repo)
    monkeypatch.setattr(shards, "_test_files", lambda: files)
    monkeypatch.setattr(shards, "missing_full_test_dependencies", lambda: [])
    report = shards.run(shard_count=1, timeout_seconds=30)
    assert report["status"] == "passed", json.dumps(report, ensure_ascii=False)
    assert report["passed"] == len(files)
    assert report["shards"][0]["files"] == [path.relative_to(repo).as_posix() for path in files]
    expected = ["tests/" + path.name for path in locals_] + ["../toolbox/tests/test_toolbox_selection.py"]
    commands = report["shards"][0]["commandResults"]
    assert [command["files"] for command in commands] == [expected[start:start + 4] for start in range(0, len(expected), 4)]
    assert all(command["mode"] == "batched" and not command["timedOut"] for command in commands)


def test_default_pytest_discovery_includes_both_supported_roots(pytestconfig: pytest.Config) -> None:
    assert pytestconfig.getini("testpaths") == ["LocalGenerator/tests", "toolbox/tests"]


def test_changed_runner_forces_offline_config(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("INFINI_TEST_USE_PROJECT_CONFIG", "1")
    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "status"]:
            return SimpleNamespace(returncode=0, stdout=" M toolbox/tests/test_live20_support_v5.py\n", stderr="")
        assert kwargs["env"]["INFINI_TEST_USE_PROJECT_CONFIG"] == "0"
        return SimpleNamespace(returncode=0, stdout="1 passed")
    _git_status(monkeypatch, " M toolbox/tests/test_live20_support_v5.py\n")
    monkeypatch.setattr(changed.subprocess, "run", fake_run)
    assert changed.main([]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "passed"


def test_shards_without_files_are_not_reported_as_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shards, "missing_full_test_dependencies", lambda: [])
    monkeypatch.setattr(shards, "_test_files", lambda: [])
    report = shards.run(shard_count=1)
    assert report["status"] == "not_selected"
    assert report["ok"] is False


def test_hosted_shards_use_the_accepted_finite_command_budget() -> None:
    manifest = json.loads((ROOT / ".agent/manifest.json").read_text(encoding="utf-8"))
    command = manifest["checks"]["pytest"]
    assert command[command.index("--timeout-seconds") + 1] == "300"
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "python tools/validate_release.py --group python" in workflow


def test_hosted_suite_executes_supported_roots_once() -> None:
    import validate_release as validation

    manifest = json.loads((ROOT / ".agent/manifest.json").read_text(encoding="utf-8"))
    groups = [name for group in ("python", "static", "build") for name in validation.checks_for_group(group, manifest)]
    assert len(groups) == len(set(groups))
    assert groups == validation.checks_for_group("full", manifest)
    assert groups.count("pytest") == groups.count("tml_build") == 1
    assert manifest["checks"]["pytest"][1] == "tools/run_pytest_shards.py"


def test_failed_shard_cli_explains_command_termination(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(shards.sys, "argv", ["run_pytest_shards.py"])
    monkeypatch.setattr(shards, "run", lambda *args: {
        "ok": False, "passed": 0, "durationSeconds": 1,
        "shards": [{"status": "failed", "output": "partial progress without pytest summary",
                    "commandResults": [{"status": "failed", "exitCode": 124, "timedOut": True,
                                        "durationSeconds": 1, "mode": "batched", "files": ["tests/test_slow.py"]}]}],
    })
    assert shards.main() == 1
    output = capsys.readouterr().out
    assert "exitCode=124" in output and "timedOut=True" in output
    assert "tests/test_slow.py" in output and "partial progress without pytest summary" in output


@pytest.mark.parametrize("slow", [False, True], ids=["completed", "finite-timeout"])
def test_native_pytest_command_timeout_has_a_distinct_receipt(tmp_path: Path, slow: bool) -> None:
    import os

    local = tmp_path / "repo/LocalGenerator"
    local.mkdir(parents=True)
    test = local / "test_command_timeout.py"
    test.write_text("import time\ndef test_command():\n    time.sleep(5)\n" if slow else "def test_command():\n    assert True\n", encoding="utf-8")
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    receipt = shards._run_pytest_command(temp_root=local.parent, relatives=[test.name], env=env,
                                          timeout_seconds=1 if slow else 30, log_path=tmp_path / "command.log", mode="batched")
    assert receipt["timedOut"] is slow
    assert receipt["exitCode"] == (124 if slow else 0)
    assert receipt["status"] == ("failed" if slow else "passed")
    assert receipt["passed"] == (None if slow else 1)


def _workflow_section(name: str, *, indent: int = 0) -> list[str]:
    """Read a workflow block at its declared indent, without optional YAML deps."""
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    lines = workflow.split(" " * indent + name + ":\n", 1)[1].splitlines()
    block: list[str] = []
    for line in lines:
        if line and not line.lstrip().startswith("#") and not line.startswith(" " * (indent + 1)):
            break
        if line.strip() and not line.lstrip().startswith("#"):
            block.append(line)
    return block


def test_hosted_events_keep_every_pr_main_push_and_manual_run_without_branch_duplicates() -> None:
    # No path/type/base-branch filters: contract/docs/tooling changes and fork or
    # draft PRs still receive the full suite. Standalone branches use manual CI.
    assert _workflow_section("on") == [
        "  push:", "    branches: [main]", "  pull_request:", "  workflow_dispatch:",
    ]


@pytest.mark.parametrize("previous,current,same_group,cancel_current", [
    (("pull_request", 41, 100), ("pull_request", 41, 101), True, True),
    (("pull_request", 41, 100), ("pull_request", 42, 101), False, True),
    (("push", None, 100), ("push", None, 101), False, False),
    (("workflow_dispatch", None, 100), ("workflow_dispatch", None, 101), False, False),
    (("pull_request", 41, 100), ("workflow_dispatch", None, 41), False, False),
    (("push", None, 41), ("pull_request", 41, 101), False, True),
], ids=["superseded-same-pr", "independent-prs", "every-main-commit", "independent-manual-runs", "manual-cannot-cancel-pr", "pr-cannot-cancel-main"])
def test_hosted_concurrency_only_replaces_the_same_pull_request(previous, current, same_group, cancel_current) -> None:
    # Pin the small supported Actions expression, then substitute its contexts.
    # This tests our grouping policy; it is not an Actions scheduler emulator.
    group, cancellation = (line.split(": ", 1)[1] for line in _workflow_section("concurrency"))
    assert group == "${{ github.workflow }}-${{ github.event_name }}-${{ github.event.pull_request.number || github.run_id }}"
    assert cancellation == "${{ github.event_name == 'pull_request' }}"

    def key(context, workflow="InfiniCrafterLocal CI"):
        event, number, run_id = context
        return (group.replace("${{ github.workflow }}", workflow)
                .replace("${{ github.event_name }}", event)
                .replace("${{ github.event.pull_request.number || github.run_id }}", str(number or run_id)))

    assert (key(previous) == key(current)) is same_group
    assert (current[0] == "pull_request") is cancel_current
    assert key(previous) != key(previous, workflow="Another workflow")


def test_hosted_python_cache_uses_the_lockfile_without_skipping_installation() -> None:
    for job in ("python-tests", "strict-hygiene"):
        block = "\n".join(_workflow_section(job, indent=2))
        assert "          cache: pip\n          cache-dependency-path: LocalGenerator/requirements-dev.lock" in block
        assert "python -m pip install -r LocalGenerator/requirements-dev.lock" in block
        assert "cache-hit" not in block


def test_validation_missing_native_environment_is_not_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    import validate_release as validation

    monkeypatch.setattr(validation.shutil, 'which', lambda name: None)
    for name in ('tml_build', 'native_checks'):
        row = validation.run_check(name, ['dotnet', 'build'], env={})
        assert row['status'] == 'unavailable'
        assert row['exitCode'] is None
    assert validation.run_check('tml_runtime_selftest', [], env={})['status'] == 'notRun'


def test_validation_native_checks_build_once_then_execute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import validate_release as validation

    for relative in ('refs/tModLoader.dll', 'deps/ParticleLibrary/ParticleLibrary.dll',
                     'deps/Luminance/bin/Debug/net8.0/Luminance.dll'):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    monkeypatch.setattr(validation.shutil, 'which', lambda name: '/usr/bin/dotnet' if name == 'dotnet' else None)
    calls = []

    def execute(command, root, env):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='ok')

    monkeypatch.setattr(validation, '_execute', execute)
    row = validation.run_check('native_checks', ['dotnet', 'build'], root=tmp_path,
                               env={'INFINI_TML_REFERENCE_DIR': str(tmp_path / 'refs'), 'INFINI_TML_DEPS_SRC': str(tmp_path / 'deps')})
    assert row['status'] == 'passed'
    assert len(calls) == 2
    assert calls[0][1:3] == ['build', 'tools/EngineRuntimeChecks.csproj']
    assert calls[1][1] == 'tools/bin/Debug/net8.0/EngineRuntimeChecks.dll'


def test_validation_native_failure_does_not_execute_stale_dll(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import validate_release as validation

    for relative in ('refs/tModLoader.dll', 'deps/ParticleLibrary/ParticleLibrary.dll',
                     'deps/Luminance/bin/Debug/net8.0/Luminance.dll'):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    monkeypatch.setattr(validation.shutil, 'which', lambda name: '/usr/bin/dotnet' if name == 'dotnet' else None)
    calls = []

    def execute(command, root, env):
        calls.append(command)
        return SimpleNamespace(returncode=1, stdout='build failed')

    monkeypatch.setattr(validation, '_execute', execute)
    row = validation.run_check('native_checks', [], root=tmp_path,
                               env={'INFINI_TML_REFERENCE_DIR': str(tmp_path / 'refs'), 'INFINI_TML_DEPS_SRC': str(tmp_path / 'deps')})
    assert row['status'] == 'failed'
    assert len(calls) == 1


def test_refresh_groups_delegate_to_existing_producers() -> None:
    manifest = json.loads((ROOT / '.agent/manifest.json').read_text(encoding='utf-8'))
    groups = manifest['refreshGroups']
    assert set(groups) == {'runtime', 'config', 'docs'}
    for commands in groups.values():
        for command in commands:
            assert command[0] == 'python'
            assert (ROOT / command[1]).is_file()
            assert '--check' not in command


@pytest.mark.parametrize("path,expected,absent", [
    ("LocalGenerator/infini_local/core/runtime_authoring/capability_registry.py", "schema_check", "mutation_gate"),
    ("LocalGenerator/infini_local/desktop/settings_page_configure.py", "config_registry", "schema_check"),
    ("ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.Mobility.cs", "native_checks", "pytest"),
    ("ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Executors.cs", "native_checks", "pytest"),
])
def test_owner_iteration_selects_relevant_gates_without_final_campaign(path, expected, absent) -> None:
    plan = agentctl.verification_plan([path])
    assert plan["mode"] == "iteration"
    assert expected in plan["checks"] and absent not in plan["checks"]
    assert not plan["releaseScope"]
    if path.startswith("ModSources/"):
        assert plan["requiresBuild"]
    if "/desktop/" in path:
        assert "LocalGenerator/tests/test_web_studio.py" in plan["tests"]


def test_unmapped_change_and_final_mode_require_complete_plan() -> None:
    manifest = json.loads(agentctl.MANIFEST_PATH.read_text())
    path = "LocalGenerator/infini_local/unmapped_new_feature.py"
    unknown = agentctl.verification_plan([path])
    assert unknown["unmappedPaths"] == [path]
    assert unknown["mode"] == "final_fallback"
    assert unknown["checks"] == manifest["fullChecks"]
    final = agentctl.verification_plan(["LocalGenerator/tests/test_web_studio.py"], final=True)
    assert final["checks"] == manifest["fullChecks"] and not final["tests"]
    assert final["releaseScope"]


def test_branch_selection_includes_commits_worktree_and_both_rename_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30).stdout.strip()
    git("init", "-b", "main")
    git("config", "user.name", "Offline test")
    git("config", "user.email", "offline@example.invalid")
    (tmp_path / "old name.py").write_text("baseline\n")
    git("add", ".")
    git("commit", "-m", "baseline")
    base = git("rev-parse", "HEAD")
    git("checkout", "-b", "task")
    git("mv", "old name.py", "new name.py")
    git("commit", "-m", "move")
    (tmp_path / "new name.py").write_text("working tree\n")
    (tmp_path / "untracked.py").write_text("new\n")
    monkeypatch.setattr(agentctl, "ROOT", tmp_path)
    assert agentctl.changed_files(base) == ["new name.py", "old name.py", "untracked.py"]
    assert agentctl.changed_files() == ["new name.py", "untracked.py"]
    with pytest.raises(ValueError, match="invalid --base"):
        agentctl.changed_files("not-a-revision")


def test_clean_task_context_selects_entrypoints_before_tool_metadata(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(agentctl, "changed_files", lambda base=None: [])
    args = SimpleNamespace(base=None, path=None, area=["runtime"], task="new capability", budget=14000, out=None)
    assert agentctl.command_context(args) == 0
    report = json.loads(capsys.readouterr().out)
    paths = [row["path"] for row in report["documents"]]
    assert "LocalGenerator/infini_local/AGENTS.md" in paths
    assert "docs/development/ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md" in paths
    assert not any(path.startswith(".agent/") for path in paths)
    assert sum(len(row.get("content", "")) for row in report["documents"]) <= 14000
    args.path = ["../outside.py"]
    with pytest.raises(ValueError, match="inside checkout"):
        agentctl.command_context(args)


@pytest.mark.parametrize("status,exit_code", [("passed", 0), ("notRun", 2), ("unavailable", 2), ("failed", 1)])
def test_iteration_never_claims_release_or_missing_execution_passed(
    status: str, exit_code: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(agentctl, "changed_files", lambda base=None: ["LocalGenerator/tests/test_web_studio.py"])
    monkeypatch.setattr(agentctl, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(agentctl, "_run_check", lambda name, command: {"name": name, "status": status})
    args = SimpleNamespace(base=None, changed=True, require_build=False, plan=False, out=None)
    assert agentctl.command_verify(args) == exit_code
    report = json.loads(capsys.readouterr().out)
    assert report["releaseReady"] is False
    assert report["ok"] is (status == "passed")


def test_native_iteration_runs_one_native_owner_without_duplicate_tml_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(agentctl, "changed_files", lambda base=None: ["ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.Mobility.cs"])
    monkeypatch.setattr(agentctl, "ARTIFACTS", tmp_path)
    calls = []
    def run(name, command):
        calls.append(name)
        return {"name": name, "status": "passed"}
    monkeypatch.setattr(agentctl, "_run_check", run)
    assert agentctl.command_verify(SimpleNamespace(base=None, changed=True, require_build=False, plan=False, out=None)) == 0
    capsys.readouterr()
    assert calls == ["csharp_contracts", "native_checks"]


@pytest.mark.parametrize('group', ['runtime', 'config', 'docs'])
def test_refresh_rebuilds_handbook_once(group: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import validate_release as validation

    calls = []

    def run_check(name, command):
        calls.append(command)
        return {'name': name, 'status': 'passed'}

    monkeypatch.setattr(validation, 'run_check', run_check)
    validation.refresh(group)
    assert calls[-1] == ['python', 'tools/build_documentation.py']
    assert calls.count(calls[-1]) == 1


def test_refresh_stops_before_handbook_on_producer_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import validate_release as validation

    calls = []

    def run_check(name, command):
        calls.append(command)
        return {'name': name, 'status': 'failed'}

    monkeypatch.setattr(validation, 'run_check', run_check)
    rows = validation.refresh('runtime')
    assert len(calls) == len(rows) == 1
    assert calls[0][1] != 'tools/build_documentation.py'


def test_validation_forces_offline_config_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    import validate_release as validation

    def execute(command, root, env):
        assert env['INFINI_SKIP_CONFIG_FILE'] == '1'
        assert env['INFINI_TEST_USE_PROJECT_CONFIG'] == '0'
        assert env['PYTHONPATH'] == str(ROOT / 'LocalGenerator')
        return SimpleNamespace(returncode=0, stdout='ok')

    monkeypatch.setattr(validation, '_execute', execute)
    row = validation.run_check('probe', ['python', '-c', 'pass'], env={
        'INFINI_SKIP_CONFIG_FILE': '0', 'INFINI_TEST_USE_PROJECT_CONFIG': '1', 'PYTHONPATH': '/wrong'})
    assert row['status'] == 'passed'


def test_diff_reports_git_scope_without_running_validation(monkeypatch, capsys):
    import subprocess

    calls = []
    def git(*args):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="changed source", stderr="")
    monkeypatch.setattr(agentctl, "_git", git)
    monkeypatch.setattr(agentctl, "changed_files", lambda base=None: ["example.py"])
    monkeypatch.setattr(agentctl, "_run_check", lambda *_: pytest.fail("diff must not execute validation"))
    assert agentctl.command_diff(SimpleNamespace(base="origin/main")) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["changedFiles"] == ["example.py"] and report["comparisonBase"] == "origin/main"
    assert report["validationRun"] is False
    assert ("diff", "--stat", "origin/main...HEAD") in calls


def test_docs_reuses_one_audit_for_both_renderers(monkeypatch, tmp_path, capsys):
    import generate_low_level_runtime_docs as docs

    calls = []
    report = {"ok": True, "issues": []}
    def audit():
        calls.append("audit")
        return report
    def render(value):
        assert value is report
        return "one projection"
    monkeypatch.setattr(docs, "ROOT", tmp_path)
    monkeypatch.setattr(docs, "capability_library_audit", audit)
    monkeypatch.setattr(docs, "inventory_markdown", render)
    monkeypatch.setattr(docs, "audit_markdown", render)
    monkeypatch.setattr(docs, "lowering_markdown", lambda: "lowering")
    monkeypatch.setattr(docs.sys, "argv", ["generate_low_level_runtime_docs.py"])
    assert docs.main() == 0
    assert calls == ["audit"]
    capsys.readouterr()
    report["ok"] = False
    assert docs.main() == 1  # a current projection cannot conceal a failed audit


def test_validation_translates_paths_only_for_windows_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    import validate_release as validation

    monkeypatch.setattr(validation.os, 'name', 'posix')
    monkeypatch.setattr(validation.shutil, 'which', lambda name: '/usr/bin/wslpath')
    monkeypatch.setattr(validation.subprocess, 'run', lambda command, **kwargs: SimpleNamespace(returncode=0, stdout='C:\\repo\\tools\\check.csproj\n'))
    assert validation._host_path('dotnet', 'tools/check.csproj', ROOT) == 'tools/check.csproj'
    assert validation._host_path('dotnet.exe', 'tools/check.csproj', ROOT) == 'C:\\repo\\tools\\check.csproj'
