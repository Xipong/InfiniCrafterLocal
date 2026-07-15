#!/usr/bin/env python3
"""Dependency-free validation for restricted code-review sandboxes.

This is deliberately not a release gate.  It provides bounded structural checks
when pytest or runtime dependencies are unavailable, and reports that limitation
without attempting the full suite.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FULL_SUITE_MODULES = {
    "pytest": "pytest",
    "pydantic": "pydantic",
    "pydantic_core": "pydantic_core",
    "Pillow": "PIL",
    "Hypothesis": "hypothesis",
}
STATIC_COMMANDS = (
    ("config_registry", ("tools/config_registry.py", "--check")),
    ("csharp_contracts", ("tools/check_csharp_contracts.py",)),
    ("project_hygiene", ("tools/check_project_hygiene.py",)),
)


def _module_available(import_name: str) -> bool:
    try:
        return importlib.util.find_spec(import_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _stop_process_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            proc.kill()
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _run_static_command(name: str, args: tuple[str, ...], timeout_seconds: int) -> dict[str, Any]:
    command = [sys.executable, "-S", *args]
    started = time.monotonic()
    popen_kwargs: dict[str, Any] = {
        "cwd": ROOT,
        "text": True,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(command, **popen_kwargs)
    try:
        output, _ = proc.communicate(timeout=timeout_seconds)
        status = "passed" if proc.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        _stop_process_tree(proc)
        try:
            output, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            output = ""
        status = "timeout"
    return {
        "name": name,
        "status": status,
        "returnCode": proc.returncode,
        "durationSeconds": round(time.monotonic() - started, 3),
        "command": command,
        "outputTail": (output or "")[-4000:],
    }


def _python_and_json_syntax() -> dict[str, Any]:
    errors: list[str] = []
    python_count = 0
    json_count = 0
    for source_root in (ROOT / "LocalGenerator" / "infini_local", ROOT / "LocalGenerator" / "tests", ROOT / "tools"):
        for path in sorted(source_root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            python_count += 1
            try:
                ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            except (OSError, SyntaxError, UnicodeError) as exc:
                errors.append(f"{path.relative_to(ROOT)}: {exc}")
    for data_root in (ROOT / "contracts", ROOT / ".agent"):
        for path in sorted(data_root.rglob("*.json")):
            json_count += 1
            try:
                json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError, UnicodeError) as exc:
                errors.append(f"{path.relative_to(ROOT)}: {exc}")
    return {
        "name": "syntax_and_json",
        "status": "passed" if not errors else "failed",
        "pythonFiles": python_count,
        "jsonFiles": json_count,
        "errors": errors[:100],
    }


def _is_os_environ(value: ast.AST) -> bool:
    return (
        isinstance(value, ast.Attribute)
        and isinstance(value.value, ast.Name)
        and value.value.id == "os"
        and value.attr == "environ"
    )


def _test_process_safety() -> dict[str, Any]:
    errors: list[str] = []
    subprocess_count = 0
    tests_root = ROOT / "LocalGenerator" / "tests"
    for path in sorted(tests_root.glob("test_*.py")):
        text = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(text, filename=str(path))
        parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                owner = node.func.value
                if (
                    isinstance(owner, ast.Name)
                    and owner.id == "subprocess"
                    and node.func.attr in {"run", "check_call", "check_output"}
                ):
                    subprocess_count += 1
                    if not any(keyword.arg == "timeout" for keyword in node.keywords):
                        errors.append(f"{path.relative_to(ROOT)}:{node.lineno}: unbounded subprocess.{node.func.attr}")
                if _is_os_environ(owner) and node.func.attr in {"clear", "pop", "setdefault", "update"}:
                    current: ast.AST | None = node
                    while current in parents and not isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        current = parents[current]
                    if not isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        errors.append(f"{path.relative_to(ROOT)}:{node.lineno}: import-time os.environ mutation")
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if isinstance(target, ast.Subscript) and _is_os_environ(target.value):
                        current = node
                        while current in parents and not isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            current = parents[current]
                        if not isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            errors.append(f"{path.relative_to(ROOT)}:{node.lineno}: import-time os.environ assignment")
    return {
        "name": "test_process_safety",
        "status": "passed" if not errors else "failed",
        "boundedSubprocessCalls": subprocess_count,
        "errors": errors[:100],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--require-full-deps", action="store_true")
    args = parser.parse_args()
    timeout_seconds = max(5, min(300, int(args.timeout_seconds)))

    dependencies = {label: _module_available(import_name) for label, import_name in FULL_SUITE_MODULES.items()}
    missing = [label for label, available in dependencies.items() if not available]
    checks = [_python_and_json_syntax(), _test_process_safety()]
    checks.extend(_run_static_command(name, command, timeout_seconds) for name, command in STATIC_COMMANDS)
    failed = [check["name"] for check in checks if check["status"] != "passed"]
    full_available = not missing
    ok = not failed and (full_available or not args.require_full_deps)
    report = {
        "schema": "infini.sandbox-validation.v1",
        "ok": ok,
        "coverage": "portable-static",
        "releaseReady": False,
        "fullSuiteAvailable": full_available,
        "fullSuiteDependencies": dependencies,
        "missingFullSuiteDependencies": missing,
        "failed": failed,
        "timeoutSeconds": timeout_seconds,
        "checks": checks,
        "nextCommand": (
            f"{sys.executable} tools/validate_release.py --skip-build"
            if full_available
            else "Do not run full pytest here; install LocalGenerator/requirements-dev.txt in a capable environment."
        ),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        out = args.json_out if args.json_out.is_absolute() else ROOT / args.json_out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
