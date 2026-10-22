"""Behavior of the advisory growth report; no production-size snapshots."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import agentctl
from tools.checks import check_code_health as health


def _long_function(statements: int, name: str = "work") -> str:
    return f"def {name}():\n" + "    value = 1\n" * statements


def test_existing_debt_can_stay_or_shrink_but_growth_is_visible():
    source = _long_function(320)
    before = {"tools/owner.py": source}
    assert health.compare(before, before)["warnings"] == []
    assert health.compare(before, {"tools/owner.py": _long_function(310)})["warnings"] == []
    warning, = health.compare(before, {"tools/owner.py": _long_function(325)})["warnings"]
    assert warning["metric"] == "function_lines"
    assert (warning["before"], warning["after"], warning["cap"]) == (321, 326, 321)


def test_new_functions_do_not_inherit_unrelated_debt():
    before = {"tools/owner.py": _long_function(400)}
    after = {"tools/owner.py": before["tools/owner.py"] + "\n" + _long_function(310, "other")}
    warning, = health.compare(before, after)["warnings"]
    assert warning["function"] == "other"
    assert warning["before"] == 0 and warning["cap"] == 300


def test_exact_moves_keep_function_caps_when_both_owners_are_selected():
    source = _long_function(320)
    result = health.compare({"tools/old.py": source}, {"tools/old.py": "", "tools/new.py": source})
    assert result["warnings"] == []


def test_copying_an_old_large_function_does_not_inherit_its_debt():
    source = _long_function(320)
    before = {"tools/original.py": source}
    warning, = health.compare(before, {**before, "tools/copy.py": source})["warnings"]
    assert warning["path"] == "tools/copy.py" and warning["before"] == 0
    assert warning["cap"] == 300
    deleted = health.compare(before, {})
    assert deleted["files"] == [{"path": "tools/original.py", "beforeFunctionLines": 321, "afterFunctionLines": 0}]


def test_declarative_catalog_size_does_not_count_as_function_growth():
    catalog = "CATALOG = {\n" + "    'entry': {'value': 1},\n" * 3000 + "}\n"
    result = health.compare({}, {"tools/catalog.py": catalog + "\ndef lookup():\n    return CATALOG\n"})
    assert result["warnings"] == []
    assert result["files"][0]["afterFunctionLines"] == 2
    # Procedural code in a catalog still has its own cap.
    assert health.compare({}, {"tools/catalog.py": catalog + _long_function(320)})["warnings"]


def test_nested_functions_and_elif_chains_have_local_control_flow():
    source = """def outer(value):
    def inner():
        if value:
            for item in value:
                if item:
                    return item
    return inner()

def chain(value):
    if value == 1:
        return 1
    elif value == 2:
        return 2
    elif value == 3:
        return 3
"""
    measured = health.measure(source, "tools/owner.py")
    functions = measured["functions"]
    assert (functions["outer"]["branches"], functions["outer"]["nesting"]) == (0, 0)
    assert (functions["outer.inner"]["branches"], functions["outer.inner"]["nesting"]) == (3, 3)
    assert (functions["chain"]["branches"], functions["chain"]["nesting"]) == (3, 1)
    assert measured["file_function_lines"] == functions["outer"]["function_lines"] + functions["chain"]["function_lines"]


def test_branch_and_nesting_growth_are_independent_of_line_count():
    source = "def work(values):\n" + "    if values: pass\n" * 21
    warning, = health.compare({}, {"tools/owner.py": source})["warnings"]
    assert warning["metric"] == "branches" and warning["after"] == 21
    nested = "def work():\n" + "".join("    " * level + "while True:\n" for level in range(1, 8)) + "    " * 8 + "pass\n"
    warning, = health.compare({}, {"tools/owner.py": nested})["warnings"]
    assert warning["metric"] == "nesting" and warning["after"] == 7


def test_advisory_cli_reports_growth_without_failing_or_claiming_release(monkeypatch, capsys):
    report = {"status": "warnings", "advisory": True, "releaseReady": False, "warnings": [{"metric": "branches"}]}
    monkeypatch.setattr(health, "build_report", lambda *_: report)
    assert health.main([]) == 0
    assert json.loads(capsys.readouterr().out) == report


@pytest.mark.parametrize("error", [ValueError("unavailable base"), SyntaxError("invalid source")])
def test_incomplete_measurement_is_not_a_clean_report(monkeypatch, capsys, error):
    def fail(*_):
        raise error
    monkeypatch.setattr(health, "build_report", fail)
    assert health.main([]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "unavailable"


def test_git_baseline_includes_committed_worktree_and_untracked_sources(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30).stdout.strip()

    (tmp_path / "tools").mkdir()
    owner = tmp_path / "tools/owner.py"
    owner.write_text(_long_function(320))
    git("init", "-b", "main")
    git("config", "user.name", "Offline test")
    git("config", "user.email", "offline@example.invalid")
    git("add", ".")
    git("commit", "-m", "baseline")
    base = git("rev-parse", "HEAD")
    git("switch", "-c", "task")
    owner.write_text(_long_function(322))
    git("commit", "-am", "committed growth")
    owner.write_text(_long_function(325))
    (tmp_path / "tools/new.py").write_text(_long_function(310, "fresh"))
    (tmp_path / "tools/test_unrelated.py").write_text(_long_function(500))
    monkeypatch.setattr(agentctl, "ROOT", tmp_path)
    report = health.build_report("main")
    assert report["baselineRevision"] == base
    assert report["paths"] == ["tools/new.py", "tools/owner.py"]
    assert {(row["function"], row["before"], row["after"]) for row in report["warnings"]} == {
        ("fresh", 0, 311), ("work", 321, 326),
    }
    monkeypatch.setattr(agentctl, "changed_files", lambda *_: pytest.fail("explicit path does not scan changes"))
    assert health.build_report("main", ["tools/owner.py"])["paths"] == ["tools/owner.py"]
    with pytest.raises(ValueError, match="Git --base"):
        health.build_report("missing-base")


def test_code_health_is_not_added_to_release_gates():
    manifest = json.loads(agentctl.MANIFEST_PATH.read_text())
    assert "code_health" not in manifest["fullChecks"]
