#!/usr/bin/env python3
"""Run an explicit focused pytest set without requiring unrelated optional plugins."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TEST_ROOTS = ((ROOT / "LocalGenerator" / "tests").resolve(), (ROOT / "toolbox" / "tests").resolve())


def _safe_test_path(raw: str) -> Path:
    path = (ROOT / raw).resolve()
    if not any(path == root or path.is_relative_to(root) for root in TEST_ROOTS):
        raise ValueError(f"focused pytest path must stay under a test root: {raw!r}")
    if not path.exists():
        raise ValueError(f"focused pytest path does not exist: {raw!r}")
    if path.is_file() and not (path.name.startswith("test_") and path.suffix == ".py"):
        raise ValueError(f"focused pytest path must be a test module: {raw!r}")
    return path


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: run_focused_pytests.py <test path> [<test path> ...]", file=sys.stderr)
        return 2
    try:
        selected = [_safe_test_path(raw) for raw in sys.argv[1:]]
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "LocalGenerator")
    env["INFINI_FOCUSED_PYTEST"] = "1"
    env["INFINI_TEST_USE_PROJECT_CONFIG"] = "0"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *(str(path) for path in selected)],
        cwd=ROOT,
        env=env,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
