#!/usr/bin/env python3
"""Pytest-only convenience command using agentctl's owner-area selection.

Includes committed branch changes with --base. Unknown/shared surfaces use the
full suite; use agentctl verify for non-pytest gates and final acceptance.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.testing.run_pytest_shards import missing_full_test_dependencies  # noqa: E402


def build_plan(base: str | None = None) -> dict[str, Any]:
    from tools.agentctl import changed_files, verification_plan
    files = changed_files(base)
    plan = verification_plan(files)
    selected = ["LocalGenerator/tests", "toolbox/tests"] if plan["releaseScope"] else plan["tests"]
    tests = [path for path in files if path in plan["tests"]]
    # Only standalone test edits are fully verified by this pytest-only helper.
    # Every production/docs/tooling surface has additional owner/final gates.
    uncovered = [path for path in files if path not in tests]
    return {
        "schema": "infini.changed-pytests.v2",
        "ok": bool(selected) and not uncovered,
        "mode": "full_due_to_unmapped_change" if plan["releaseScope"] else "changed_modules" if tests == files else "owner_areas",
        "changedModules": tests,
        "fullSelectionTriggers": plan["unmappedPaths"],
        "sharedTestChanges": [path for path in plan["unmappedPaths"] if path.startswith(("LocalGenerator/tests/", "toolbox/tests/"))],
        "uncoveredChangePaths": uncovered,
        "selected": selected,
        "comparisonBase": base,
        "scope": "pytest-only; use agentctl verify for other gates",
        "releaseReady": False,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base")
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = build_plan(args.base)
    except Exception as exc:
        print(json.dumps({
            "schema": "infini.changed-pytests.v1",
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    if args.plan:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
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
                "portableCommand": f"{sys.executable} tools/testing/validate_sandbox.py",
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
