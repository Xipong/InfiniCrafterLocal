#!/usr/bin/env python3
"""Run deterministic pytest shards with targeted process isolation.

Most tests are safe and fast in a shared pytest process. A small set of smoke
and tooling tests intentionally touches process-global signal/thread/socket or
subprocess state; those files run in fresh child processes so they cannot poison
later tests. This keeps the suite order-independent without paying one Python
startup per test file.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = ROOT / "LocalGenerator" / "tests"
FULL_TEST_MODULES = {
    "pytest": "pytest",
    "pydantic": "pydantic",
    "pydantic_core": "pydantic_core",
    "Pillow": "PIL",
    "Hypothesis": "hypothesis",
}

# These tests invoke subprocesses, temporary servers, runtime smoke paths, or
# agent/release tools. Keep the list narrow and behavior-based; ordinary test
# files remain batched. New files should only be added after reproducing shared-
# process pollution.
ISOLATED_TEST_FILES = {
    "test_239_golden_runtime_proof_contract.py",
    "test_240_http_boundary_bugfixes.py",
    "test_240_python_runtime_bugfixes.py",
    "test_csharp_compile_surface_contract.py",
    "test_environment_access_contract.py",
    "test_planner_prompt_usability_contract.py",
    "test_sdcpp_command_contract.py",
    "test_v18_contract_safety_stack.py",
    "test_zimage_prompt_contract.py",
}


def _test_files() -> list[Path]:
    return sorted(path for path in TEST_ROOT.glob("test_*.py") if path.is_file())


def _missing_test_dependencies() -> list[str]:
    missing: list[str] = []
    for label, import_name in FULL_TEST_MODULES.items():
        try:
            available = importlib.util.find_spec(import_name) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            available = False
        if not available:
            missing.append(label)
    return missing


def _partition(files: list[Path], count: int) -> list[list[Path]]:
    shards: list[list[Path]] = [[] for _ in range(count)]
    for index, path in enumerate(files):
        shards[index % count].append(path)
    return [shard for shard in shards if shard]


def _passed_count(output: str) -> int | None:
    matches = re.findall(r"(?:^|\s)(\d+) passed(?:,|\s|$)", output)
    return int(matches[-1]) if matches else None


def _stop_process_tree(proc: subprocess.Popen[str], *, hard: bool = False) -> None:
    if os.name == "nt":
        if proc.poll() is None:
            command = ["taskkill", "/PID", str(proc.pid), "/T"]
            if hard:
                command.append("/F")
            try:
                subprocess.run(
                    command,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            except (OSError, subprocess.SubprocessError):
                proc.kill() if hard else proc.terminate()
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL if hard else signal.SIGTERM)
    except ProcessLookupError:
        pass


def _run_pytest_command(
    *,
    temp_root: Path,
    relatives: list[str],
    env: dict[str, str],
    timeout_seconds: int,
    log_path: Path,
    mode: str,
) -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", "-q", *relatives]
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            command,
            cwd=temp_root / "LocalGenerator",
            env=env,
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=(os.name != "nt"),
        )
        timed_out = False
        try:
            exit_code = proc.wait(timeout=max(1, timeout_seconds))
        except subprocess.TimeoutExpired:
            timed_out = True
            _stop_process_tree(proc, hard=True)
            proc.wait()
            exit_code = 124
        finally:
            # A helper grandchild may survive after pytest exits. It belongs to
            # this isolated command and must not leak into the next command.
            _stop_process_tree(proc, hard=False)
    output = log_path.read_text(encoding="utf-8", errors="replace")
    return {
        "mode": mode,
        "files": relatives,
        "fileCount": len(relatives),
        "status": "passed" if exit_code == 0 else "failed",
        "exitCode": exit_code,
        "passed": _passed_count(output),
        "timedOut": timed_out,
        "durationSeconds": round(time.monotonic() - started, 3),
        "output": output,
    }


def run(shard_count: int, shard_index: int | None = None, timeout_seconds: int = 60) -> dict[str, Any]:
    missing = _missing_test_dependencies()
    if missing:
        return {
            "schema": "infini.pytest-shards.v3",
            "ok": False,
            "status": "unavailable",
            "fullSuiteAvailable": False,
            "missingDependencies": missing,
            "portableCommand": f"{sys.executable} tools/validate_sandbox.py",
            "errors": ["full pytest dependencies are unavailable; collection was not started"],
            "shards": [],
        }
    files = _test_files()
    if not files:
        return {"schema": "infini.pytest-shards.v3", "ok": False, "errors": ["no test files found"], "shards": []}

    partitions = _partition(files, max(1, shard_count))
    selected = list(enumerate(partitions, 1))
    if shard_index is not None:
        selected = [(number, shard) for number, shard in selected if number == shard_index]
        if not selected:
            return {
                "schema": "infini.pytest-shards.v3",
                "ok": False,
                "errors": [f"invalid shard index {shard_index}"],
                "shards": [],
            }

    rows: list[dict[str, Any]] = []
    started = time.monotonic()
    base_env = dict(os.environ)
    base_env["PYTHONUTF8"] = "1"
    base_env["INFINI_SKIP_CONFIG_FILE"] = "1"

    for number, shard in selected:
        print(f"[SHARD {number}] starting files={len(shard)}", flush=True)
        shard_started = time.monotonic()
        command_rows: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix=f"infini-pytest-shard-{number}-") as temp_dir:
            temp_root = Path(temp_dir) / "repo"
            shutil.copytree(
                ROOT,
                temp_root,
                ignore=shutil.ignore_patterns(
                    ".git",
                    ".hermes",
                    "__pycache__",
                    ".pytest_cache",
                    ".ruff_cache",
                    ".hypothesis",
                    "artifacts",
                    "cache",
                    "Runtime_dumps",
                    "config.env",
                    "*.pyc",
                    "*.pyo",
                ),
            )
            env = dict(base_env)
            env["PYTHONPATH"] = str(temp_root / "LocalGenerator")
            normal = [path for path in shard if path.name not in ISOLATED_TEST_FILES]
            isolated = [path for path in shard if path.name in ISOLATED_TEST_FILES]
            commands: list[tuple[str, list[Path]]] = []
            if normal:
                commands.append(("batched", normal))
            commands.extend(("isolated", [path]) for path in isolated)

            for command_index, (mode, command_files) in enumerate(commands, 1):
                relatives = [path.relative_to(ROOT / "LocalGenerator").as_posix() for path in command_files]
                row = _run_pytest_command(
                    temp_root=temp_root,
                    relatives=relatives,
                    env=env,
                    timeout_seconds=timeout_seconds,
                    log_path=Path(temp_dir) / f"command-{command_index}.log",
                    mode=mode,
                )
                command_rows.append(row)
                if row["status"] != "passed":
                    break

        shard_ok = all(row["status"] == "passed" for row in command_rows) and sum(row["fileCount"] for row in command_rows) == len(shard)
        rows.append(
            {
                "shard": number,
                "fileCount": len(shard),
                "executedFileCount": sum(row["fileCount"] for row in command_rows),
                "isolatedFileCount": len(isolated),
                "files": [path.relative_to(ROOT / "LocalGenerator").as_posix() for path in shard],
                "status": "passed" if shard_ok else "failed",
                "exitCode": 0 if shard_ok else next((int(row["exitCode"]) for row in command_rows if row["status"] != "passed"), 1),
                "passed": sum(int(row["passed"] or 0) for row in command_rows),
                "durationSeconds": round(time.monotonic() - shard_started, 3),
                "commandResults": command_rows,
                "output": "\n".join(row["output"] for row in command_rows if row["status"] != "passed"),
            }
        )
        print(
            f"[SHARD {number}] {rows[-1]['status']} passed={rows[-1]['passed']} "
            f"isolated={rows[-1]['isolatedFileCount']} duration={rows[-1]['durationSeconds']}s",
            flush=True,
        )
        if not shard_ok:
            break

    expected_rows = 1 if shard_index is not None else len(partitions)
    return {
        "schema": "infini.pytest-shards.v3",
        "ok": len(rows) == expected_rows and all(row["status"] == "passed" for row in rows),
        "status": "passed" if len(rows) == expected_rows and all(row["status"] == "passed" for row in rows) else "failed",
        "fullSuiteAvailable": True,
        "requestedShardCount": max(1, shard_count),
        "selectedShardIndex": shard_index,
        "timeoutSecondsPerCommand": max(1, timeout_seconds),
        "testFileCount": len(files),
        "isolatedPolicy": sorted(ISOLATED_TEST_FILES),
        "passed": sum(int(row["passed"] or 0) for row in rows),
        "durationSeconds": round(time.monotonic() - started, 3),
        "shards": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shards", type=int, default=4)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--timeout-seconds", type=int, default=60, help="Timeout per batched or isolated pytest command")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    report = run(args.shards, args.shard_index, args.timeout_seconds)
    text = json.dumps(report, ensure_ascii=False, indent=None if args.compact else 2, sort_keys=True) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")

    for row in report.get("shards", []):
        if row["status"] != "passed":
            print(row["output"])
    if report.get("status") == "unavailable":
        print(
            "[PYTEST] unavailable missing="
            + ",".join(report.get("missingDependencies", []))
            + f"; run {report['portableCommand']}"
        )
    print(f"[PYTEST] ok={report['ok']} passed={report.get('passed', 0)} duration={report.get('durationSeconds', 0)}s")
    if report.get("status") == "unavailable":
        return 2
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
