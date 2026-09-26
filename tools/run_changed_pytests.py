#!/usr/bin/env python3
"""Run only changed pytest modules during agent iteration.

Release verification still runs the full sharded suite.  This helper is for dirty-tree
feedback: ordinary test edits run their own modules, while shared test support or
fixture changes deliberately fall back to the full suite because their consumers
cannot be inferred safely.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from run_pytest_shards import missing_full_test_dependencies

ROOT = Path(__file__).resolve().parents[1]
TEST_ROOTS = (ROOT / "LocalGenerator" / "tests", ROOT / "toolbox" / "tests")


def _changed_test_paths() -> tuple[list[Path], list[str], list[str]]:
    proc = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git status failed")

    modules: set[Path] = set()
    shared: set[str] = set()
    uncovered: set[str] = set()
    prefixes = ("LocalGenerator/tests/", "toolbox/tests/")
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        status = line[:2]
        relative = line[3:]
        if " -> " in relative:
            relative = relative.split(" -> ", 1)[1]
        relative = relative.replace("\\", "/")
        prefix = next((item for item in prefixes if relative.startswith(item)), None)
        if prefix:
            path = ROOT / relative
            if (relative.startswith(prefix + "test_") and relative.endswith(".py") and "D" not in status
                    and path.is_file() and path.resolve().is_relative_to((ROOT / prefix).resolve())):
                modules.add(path)
            else:
                shared.add(relative)
        elif relative.startswith(("LocalGenerator/", "toolbox/", "tools/")) or relative in {
            "pyproject.toml", "pytest.ini", "setup.cfg", "conftest.py"
        }:
            shared.add(relative)
        else:
            uncovered.add(relative)
    return sorted(modules), sorted(shared), sorted(uncovered)


def build_plan() -> dict[str, Any]:
    modules, shared, uncovered = _changed_test_paths()
    if shared:
        selected = list(TEST_ROOTS)
        mode = ("full_due_to_non_test_change" if any(not path.startswith(("LocalGenerator/tests/", "toolbox/tests/")) for path in shared)
                else "full_due_to_shared_test_surface")
    else:
        selected = modules
        mode = "changed_modules" if modules else "none"
    return {
        "schema": "infini.changed-pytests.v1",
        "ok": bool(selected) and not uncovered,
        "mode": mode,
        "changedModules": [path.relative_to(ROOT).as_posix() for path in modules],
        "fullSelectionTriggers": shared,
        "sharedTestChanges": [path for path in shared if path.startswith(("LocalGenerator/tests/", "toolbox/tests/"))],
        "uncoveredChangePaths": uncovered,
        "selected": [path.relative_to(ROOT).as_posix() for path in selected],
    }


def main() -> int:
    try:
        plan = build_plan()
    except Exception as exc:
        print(json.dumps({
            "schema": "infini.changed-pytests.v1",
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    selected = [ROOT / relative for relative in plan["selected"]]
    if not selected:
        plan.update({"ok": False, "status": "not_selected"})
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    if plan["mode"].startswith("full_due_to_"):
        missing = missing_full_test_dependencies()
        if missing:
            plan.update({
                "ok": False,
                "status": "unavailable",
                "fullSuiteAvailable": False,
                "missingDependencies": missing,
                "portableCommand": f"{sys.executable} tools/validate_sandbox.py",
                "errors": ["full pytest dependencies are unavailable; collection was not started"],
            })
            print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
            return 2

    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "LocalGenerator")
    env["INFINI_FOCUSED_PYTEST"] = "1"
    env["INFINI_TEST_USE_PROJECT_CONFIG"] = "0"
    command = [sys.executable, "-m", "pytest", "-q", *(str(path) for path in selected)]
    proc = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    tests_passed = proc.returncode == 0
    complete = tests_passed and not plan["uncoveredChangePaths"]
    plan.update({
        "ok": complete,
        "status": ("failed" if not tests_passed else "partial" if not complete else "passed"),
        "exitCode": proc.returncode,
        "command": command,
        "outputTail": proc.stdout[-12000:],
    })
    print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if complete else 2 if tests_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
