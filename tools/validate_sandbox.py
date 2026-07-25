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
    ("targeted_repair", ("tools/audit_targeted_repair.py", "--check")),
    ("terraria_standardization", ("tools/audit_terraria_standardization.py", "--check")),
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


def _subprocess_call_error(node: ast.Call) -> str | None:
    if not isinstance(node.func, ast.Attribute) or not isinstance(node.func.value, ast.Name) or node.func.value.id != "subprocess":
        return None
    name = node.func.attr
    if name == "Popen":
        return "subprocess.Popen is not permitted in tests; use a bounded subprocess.run"
    if name not in {"run", "check_call", "check_output"}:
        return None
    timeout = next((keyword.value for keyword in node.keywords if keyword.arg == "timeout"), None)
    if not isinstance(timeout, ast.Constant) or isinstance(timeout.value, bool) or not isinstance(timeout.value, (int, float)):
        return f"subprocess.{name} timeout must be a finite numeric literal"
    if not 0 < float(timeout.value) <= 300:
        return f"subprocess.{name} timeout must be within 0..300 seconds"
    return None


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


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
                if isinstance(owner, ast.Name) and owner.id == "subprocess" and node.func.attr in {"run", "check_call", "check_output", "Popen"}:
                    subprocess_count += 1
                    process_error = _subprocess_call_error(node)
                    if process_error:
                        errors.append(f"{path.relative_to(ROOT)}:{node.lineno}: {process_error}")
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
    probes = {
        "subprocess.run([], timeout=30)": None,
        "subprocess.run([], timeout=None)": "error",
        "subprocess.run([], timeout=301)": "error",
        "subprocess.Popen([])": "error",
    }
    for source, expected in probes.items():
        probe = ast.parse(source).body[0]
        call = probe.value if isinstance(probe, ast.Expr) and isinstance(probe.value, ast.Call) else None
        actual = _subprocess_call_error(call) if call is not None else "invalid probe"
        if (actual is None) != (expected is None):
            errors.append(f"internal subprocess scanner probe failed: {source}")
    return {
        "name": "test_process_safety",
        "status": "passed" if not errors else "failed",
        "scope": "LocalGenerator/tests/test_*.py",
        "boundedSubprocessCalls": subprocess_count,
        "errors": errors[:100],
    }


def _pytest_bootstrap_policy() -> dict[str, Any]:
    """Make the one sanctioned import-time test bootstrap explicit and finite."""
    path = ROOT / "LocalGenerator" / "tests" / "conftest.py"
    allowed_keys = {
        "INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK",
        "INFINI_CACHE_DIR",
        "INFINI_IMAGE_BACKEND",
        "INFINI_SDCPP_SERVER_AUTOSTART",
        "INFINI_SKIP_CONFIG_FILE",
        "INFINI_USE_LLM",
        "INFINI_WORLD_RECIPES_DIR",
    }
    errors: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    bootstrap = functions.get("_configure_deterministic_sandbox")
    calls = [
        node
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "_configure_deterministic_sandbox"
    ]
    if bootstrap is None:
        errors.append("conftest.py lacks _configure_deterministic_sandbox")
    if len(calls) != 1:
        errors.append(f"conftest.py must invoke deterministic sandbox exactly once, got {len(calls)}")

    observed_keys: set[str] = set()
    environment_updates = 0
    if bootstrap is not None:
        allowed_calls = {
            "_truthy", "Path", "tempfile.mkdtemp", "cache_dir.mkdir", "world_dir.mkdir",
            "os.environ.update", "str", "atexit.register",
        }
        for node in ast.walk(bootstrap):
            if isinstance(node, ast.Call):
                call_name = _call_name(node.func)
                if call_name not in allowed_calls:
                    errors.append(f"conftest.py:{node.lineno}: unapproved bootstrap call {call_name or '<dynamic>'}")
                if not (isinstance(node.func, ast.Attribute) and _is_os_environ(node.func.value)):
                    continue
                if node.func.attr != "update":
                    errors.append(f"conftest.py:{node.lineno}: unapproved os.environ.{node.func.attr} mutation")
                    continue
                environment_updates += 1
                if len(node.args) != 1 or not isinstance(node.args[0], ast.Dict):
                    errors.append(f"conftest.py:{node.lineno}: sandbox environment update must be a literal dict")
                    continue
                for key in node.args[0].keys:
                    if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                        errors.append(f"conftest.py:{node.lineno}: sandbox environment key must be a string literal")
                        continue
                    observed_keys.add(key.value)
                continue
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(target, ast.Subscript) and _is_os_environ(target.value) for target in targets):
                    errors.append(f"conftest.py:{node.lineno}: direct os.environ assignment is not approved")
    if environment_updates != 1:
        errors.append(f"conftest.py must perform exactly one literal os.environ.update, got {environment_updates}")
    if observed_keys != allowed_keys:
        errors.append(
            "conftest.py sandbox keys differ from policy: "
            f"missing={sorted(allowed_keys - observed_keys)} extra={sorted(observed_keys - allowed_keys)}"
        )
    return {
        "name": "pytest_bootstrap_policy",
        "status": "passed" if not errors else "failed",
        "importTimeBootstrap": "_configure_deterministic_sandbox",
        "allowedEnvironmentKeys": sorted(allowed_keys),
        "errors": errors,
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
    checks = [_python_and_json_syntax(), _test_process_safety(), _pytest_bootstrap_policy()]
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
