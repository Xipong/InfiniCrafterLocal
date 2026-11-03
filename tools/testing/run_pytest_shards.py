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

ROOT = Path(__file__).resolve().parents[2]
TEST_ROOTS = (ROOT / "LocalGenerator" / "tests", ROOT / "toolbox" / "tests")
FULL_TEST_MODULES = {
    "pytest": "pytest",
    "pydantic": "pydantic",
    "pydantic_core": "pydantic_core",
    "Pillow": "PIL",
    "Hypothesis": "hypothesis",
    "jsonschema": "jsonschema",
}

# These tests invoke subprocesses, temporary servers, runtime smoke paths, or
# agent/release tools. Keep the list narrow and behavior-based; ordinary test
# files remain batched. New files should only be added after reproducing shared-
# process pollution.
ISOLATED_TEST_FILES = {
    "test_provider_http_contract.py",
    "test_provider_runtime_contract.py",
    "test_csharp_compile_surface_contract.py",
    "test_environment_access_contract.py",
    "test_sdcpp_command_contract.py",
}


def _test_files() -> list[Path]:
    return sorted(path for root in TEST_ROOTS for path in root.glob("test_*.py")
                  if path.is_file() and path.resolve().is_relative_to(root.resolve()))


def missing_full_test_dependencies() -> list[str]:
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
    missing = missing_full_test_dependencies()
    if missing:
        return {
            "schema": "infini.pytest-shards.v3",
            "ok": False,
            "status": "unavailable",
            "fullSuiteAvailable": False,
            "missingDependencies": missing,
            "portableCommand": f"{sys.executable} tools/testing/validate_sandbox.py",
            "errors": ["full pytest dependencies are unavailable; collection was not started"],
            "shards": [],
        }
    files = _test_files()
    if not files:
        return {"schema": "infini.pytest-shards.v3", "ok": False, "status": "not_selected", "errors": ["no test files found"], "shards": []}

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
    base_env["INFINI_TEST_USE_PROJECT_CONFIG"] = "0"

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
                    ".gitnexus",
                    ".gitnexusrc",
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
            env["PYTHONPATH"] = os.pathsep.join((str(temp_root / "LocalGenerator"), str(temp_root)))
            normal = [path for path in shard if path.name not in ISOLATED_TEST_FILES]
            isolated = [path for path in shard if path.name in ISOLATED_TEST_FILES]
            # Keep one finite command timeout meaningful as parameterized
            # corpora grow; never omit cases or give a hung test an unlimited run.
            commands: list[tuple[str, list[Path]]] = [
                ("batched", normal[start:start + 4]) for start in range(0, len(normal), 4)
            ]
            commands.extend(("isolated", [path]) for path in isolated)

            for command_index, (mode, command_files) in enumerate(commands, 1):
                relatives = [
                    path.relative_to(ROOT / "LocalGenerator").as_posix()
                    if path.is_relative_to(ROOT / "LocalGenerator")
                    else "../" + path.relative_to(ROOT).as_posix()
                    for path in command_files
                ]
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
                "files": [path.relative_to(ROOT).as_posix() for path in shard],
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



def merge_reports(directory: Path, shard_count: int, source_revision: str) -> dict[str, Any]:
    """Admit this CI run's complete partition receipts; never a cache or local-test substitute."""
    if not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        raise ValueError("Shard aggregation requires the exact CI source revision")
    files = _test_files()
    if not files:
        raise ValueError("No test files selected for aggregation")
    partitions = _partition(files, shard_count)
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.rglob("pytest_shards.json"))]
    if len(reports) != len(partitions):
        raise ValueError("Missing or extra shard reports")
    selected: dict[int, dict[str, Any]] = {}
    for report in reports:
        if not isinstance(report, dict):
            raise ValueError("Shard report must be an object")
        index = report.get("selectedShardIndex")
        if type(index) is not int or not 1 <= index <= len(partitions) or index in selected:
            raise ValueError("Invalid or duplicate shard identity")
        if (report.get("schema") != "infini.pytest-shards.v3" or report.get("sourceRevision") != source_revision
                or report.get("requestedShardCount") != shard_count or report.get("testFileCount") != len(files)
                or report.get("isolatedPolicy") != sorted(ISOLATED_TEST_FILES)
                or report.get("ok") is not True or report.get("status") != "passed"):
            raise ValueError("Failed shard or incompatible source/selection receipt")
        rows = report.get("shards", [])
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise ValueError("Each matrix job must report exactly one shard")
        row = rows[0]
        expected = partitions[index - 1]
        expected_files = [path.relative_to(ROOT).as_posix() for path in expected]
        if (row.get("shard") != index or row.get("files") != expected_files
                or row.get("fileCount") != len(expected) or row.get("executedFileCount") != len(expected)
                or row.get("status") != "passed" or row.get("exitCode") != 0):
            raise ValueError("Incomplete or changed shard file coverage")
        commands = row.get("commandResults", [])
        if not isinstance(commands, list):
            raise ValueError("Command receipts must be an array")
        executed = []
        total = 0
        for command in commands:
            if (not isinstance(command, dict) or not isinstance(command.get("files"), list)
                    or not all(isinstance(name, str) for name in command["files"])):
                raise ValueError("Malformed command/file receipt")
            if (command.get("status") != "passed" or command.get("exitCode") != 0
                    or command.get("timedOut") is not False or type(command.get("passed")) is not int
                    or command["passed"] < 0 or command.get("fileCount") != len(command.get("files", []))):
                raise ValueError("Failed or malformed pytest command receipt")
            isolated = any(Path(name).name in ISOLATED_TEST_FILES for name in command["files"])
            if (isolated and (command.get("mode") != "isolated" or len(command["files"]) != 1)
                    or not isolated and (command.get("mode") != "batched" or not 1 <= len(command["files"]) <= 4)):
                raise ValueError("Changed pytest process-isolation coverage")
            executed.extend(command["files"])
            total += command["passed"]
        expected_commands = [path.relative_to(ROOT / "LocalGenerator").as_posix()
                             if path.is_relative_to(ROOT / "LocalGenerator")
                             else "../" + path.relative_to(ROOT).as_posix() for path in expected]
        if sorted(executed) != sorted(expected_commands) or total != row.get("passed") or total != report.get("passed"):
            raise ValueError("Missing/duplicate executed files or inconsistent pytest counts")
        selected[index] = row
    rows = [selected[index] for index in sorted(selected)]
    return {"schema": "infini.pytest-shards.v3", "ok": True, "status": "passed",
            "sourceRevision": source_revision, "requestedShardCount": shard_count, "selectedShardIndex": None,
            "testFileCount": len(files), "passed": sum(row["passed"] for row in rows), "shards": rows,
            "executionMode": "ci-partition-aggregation",
            "durationSeconds": max(row["durationSeconds"] for row in rows)}


def configured_shard_count() -> int:
    command = json.loads((ROOT / ".agent/manifest.json").read_text(encoding="utf-8"))["checks"]["pytest"]
    if not isinstance(command, list) or command.count("--shards") != 1:
        raise ValueError("Canonical pytest command must declare one shard count")
    index = command.index("--shards") + 1
    if index >= len(command) or not isinstance(command[index], str) or not command[index].isdigit():
        raise ValueError("Canonical pytest shard count must be a positive integer")
    count = int(command[index])
    if not 1 <= count <= 256:
        raise ValueError("Canonical pytest shard count exceeds matrix bounds")
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shards", type=int, help="Override the canonical manifest shard count")
    parser.add_argument("--matrix", action="store_true", help="Print the canonical CI partition matrix without running tests")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--timeout-seconds", type=int, default=60, help="Timeout per batched or isolated pytest command")
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--merge-reports", type=Path, help="Validate complete same-revision CI partition receipts instead of executing tests")
    args = parser.parse_args()

    try:
        count = args.shards if args.shards is not None else configured_shard_count()
        if not 1 <= count <= 256:
            raise ValueError("Pytest shard count exceeds matrix bounds")
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.error(str(exc))
    if args.matrix:
        print(json.dumps({"shard": list(range(1, count + 1))}))
        return 0

    report: dict[str, Any]
    if args.merge_reports:
        try:
            report = merge_reports(args.merge_reports, count, os.environ.get("GITHUB_SHA", ""))
        except (ValueError, TypeError, KeyError, OSError) as exc:
            report = {"schema": "infini.pytest-shards.v3", "ok": False, "status": "failed", "errors": [str(exc)], "shards": []}
    else:
        report = run(count, args.shard_index, args.timeout_seconds)
        report["sourceRevision"] = os.environ.get("GITHUB_SHA")
    text = json.dumps(report, ensure_ascii=False, indent=None if args.compact else 2, sort_keys=True) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")

    for error in report.get("errors", []):
        print(f"[PYTEST] {error}")
    for row in report.get("shards", []):
        if row["status"] != "passed":
            for command in row.get("commandResults", []):
                if command["status"] != "passed":
                    print(
                        f"[PYTEST COMMAND] mode={command['mode']} exitCode={command['exitCode']} "
                        f"timedOut={command['timedOut']} duration={command['durationSeconds']}s "
                        f"files={','.join(command['files'])}"
                    )
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
