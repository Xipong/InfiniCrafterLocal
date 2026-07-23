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
TEST_ROOT = ROOT / "LocalGenerator" / "tests"


def _changed_test_paths() -> tuple[list[Path], list[str]]:
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
    prefix = "LocalGenerator/tests/"
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        status = line[:2]
        relative = line[3:]
        if " -> " in relative:
            relative = relative.split(" -> ", 1)[1]
        relative = relative.replace("\\", "/")
        if not relative.startswith(prefix):
            continue
        path = ROOT / relative
        if relative.startswith(prefix + "test_") and relative.endswith(".py"):
            if "D" not in status and path.is_file():
                modules.add(path)
        else:
            shared.add(relative)
    return sorted(modules), sorted(shared)


def build_plan() -> dict[str, Any]:
    modules, shared = _changed_test_paths()
    if shared:
        selected = [TEST_ROOT]
        mode = "full_due_to_shared_test_surface"
    else:
        selected = modules
        mode = "changed_modules" if modules else "none"
    return {
        "schema": "infini.changed-pytests.v1",
        "ok": True,
        "mode": mode,
        "changedModules": [path.relative_to(ROOT).as_posix() for path in modules],
        "sharedTestChanges": shared,
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
        plan["status"] = "passed"
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if plan["mode"] == "full_due_to_shared_test_surface":
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
    plan.update({
        "ok": proc.returncode == 0,
        "status": "passed" if proc.returncode == 0 else "failed",
        "exitCode": proc.returncode,
        "command": command,
        "outputTail": proc.stdout[-12000:],
    })
    print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if plan["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
