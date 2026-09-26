"""Offline selection contracts for the two supported pytest roots."""
from __future__ import annotations

from pathlib import Path
import json
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import run_changed_pytests as changed  # noqa: E402
import run_focused_pytests as focused  # noqa: E402
import run_pytest_shards as shards  # noqa: E402


def _git_status(monkeypatch: pytest.MonkeyPatch, status: str) -> None:
    def fake_run(command, **kwargs):
        assert command[:2] == ["git", "status"]
        return SimpleNamespace(returncode=0, stdout=status, stderr="")

    monkeypatch.setattr(changed.subprocess, "run", fake_run)


def test_production_only_change_selects_both_offline_test_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    _git_status(monkeypatch, " M LocalGenerator/infini_local/core/runtime_authoring/program_schema.py\n")
    plan = changed.build_plan()
    assert plan["selected"] == ["LocalGenerator/tests", "toolbox/tests"]
    assert plan["mode"] == "full_due_to_non_test_change"
    assert plan["uncoveredChangePaths"] == []
    assert plan["fullSelectionTriggers"] == ["LocalGenerator/infini_local/core/runtime_authoring/program_schema.py"]
    assert plan["sharedTestChanges"] == []


def test_no_changed_paths_is_not_a_test_pass(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _git_status(monkeypatch, "")
    assert changed.main() == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "not_selected"
    assert report["ok"] is False
    assert report["selected"] == []


@pytest.mark.parametrize("path", [
    "pyproject.toml", "tools/run_focused_pytests.py", "toolbox/fixtures/items.jsonl",
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
    monkeypatch.setattr(changed, "TEST_ROOTS", (root / "LocalGenerator/tests", test_root))
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


def test_selected_subset_with_uncovered_docs_is_not_a_complete_pass(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    status = " M toolbox/tests/test_live20_support_v5.py\n M docs/overview.md\n"
    def fake_run(cmd, **kw):
        if cmd[:2] == ["git", "status"]:
            return SimpleNamespace(returncode=0, stdout=status, stderr="")
        return SimpleNamespace(returncode=0, stdout="1 passed", stderr="")
    monkeypatch.setattr(changed.subprocess, "run", fake_run)
    assert changed.main() == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "partial"
    assert report["uncoveredChangePaths"] == ["docs/overview.md"]
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


def test_shard_sandbox_executes_both_roots_with_repo_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    local = repo / "LocalGenerator/tests/test_local_selection.py"
    toolbox = repo / "toolbox/tests/test_toolbox_selection.py"
    for test_file in (local, toolbox):
        test_file.parent.mkdir(parents=True)
        test_file.write_text("import os\n\ndef test_offline():\n    assert os.environ['INFINI_TEST_USE_PROJECT_CONFIG'] == '0'\n", encoding="utf-8")
    (repo / "toolbox/__init__.py").write_text("OFFLINE_MARKER = 1\n", encoding="utf-8")
    toolbox.write_text("from toolbox import OFFLINE_MARKER\n\ndef test_offline():\n    assert OFFLINE_MARKER == 1\n", encoding="utf-8")
    monkeypatch.setenv("INFINI_TEST_USE_PROJECT_CONFIG", "1")
    monkeypatch.setattr(shards, "ROOT", repo)
    monkeypatch.setattr(shards, "_test_files", lambda: [local, toolbox])
    monkeypatch.setattr(shards, "missing_full_test_dependencies", lambda: [])
    report = shards.run(shard_count=1, timeout_seconds=30)
    assert report["status"] == "passed", report
    assert report["passed"] == 2
    assert report["shards"][0]["files"] == [
        "LocalGenerator/tests/test_local_selection.py", "toolbox/tests/test_toolbox_selection.py"
    ]
    assert report["shards"][0]["commandResults"][0]["files"] == [
        "tests/test_local_selection.py", "../toolbox/tests/test_toolbox_selection.py"
    ]


def test_default_pytest_discovery_includes_both_supported_roots(pytestconfig: pytest.Config) -> None:
    assert pytestconfig.getini("testpaths") == ["LocalGenerator/tests", "toolbox/tests"]


def test_changed_runner_forces_offline_config(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("INFINI_TEST_USE_PROJECT_CONFIG", "1")
    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "status"]:
            return SimpleNamespace(returncode=0, stdout=" M toolbox/tests/test_live20_support_v5.py\n", stderr="")
        assert kwargs["env"]["INFINI_TEST_USE_PROJECT_CONFIG"] == "0"
        return SimpleNamespace(returncode=0, stdout="1 passed")
    monkeypatch.setattr(changed.subprocess, "run", fake_run)
    assert changed.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "passed"


def test_shards_without_files_are_not_reported_as_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shards, "missing_full_test_dependencies", lambda: [])
    monkeypatch.setattr(shards, "_test_files", lambda: [])
    report = shards.run(shard_count=1)
    assert report["status"] == "not_selected"
    assert report["ok"] is False
