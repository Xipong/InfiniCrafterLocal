#!/usr/bin/env python3
"""Single machine-readable control plane for repository coding agents."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fnmatch import fnmatch
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / ".agent"
MANIFEST_PATH = AGENT_DIR / "manifest.json"
RULES_PATH = AGENT_DIR / "impact_rules.json"
ARTIFACTS = ROOT / "artifacts" / "agent"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _base_revision() -> str:
    proc = _git("rev-parse", "HEAD")
    if proc.returncode == 0:
        return proc.stdout.strip()
    source_index = ROOT / "SOURCE_FILE_INDEX.txt"
    if source_index.is_file():
        digest = hashlib.sha256(source_index.read_bytes()).hexdigest()[:20]
        return f"source-index:{digest}"
    package = ROOT / "PACKAGE_METADATA.json"
    if package.is_file():
        digest = hashlib.sha256(package.read_bytes()).hexdigest()[:20]
        return f"source-package:{digest}"
    return "source-only:no-baseline-evidence"


def _ignored_repository_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.lstrip("/")
    parts = normalized.split("/")
    ignored_parts = {
        ".git", ".nuget", ".tml-build-cache", "__pycache__", ".pytest_cache",
        ".ruff_cache", ".hypothesis", "bin", "obj",
    }
    ignored_prefixes = (
        "artifacts/", "build_logs/", "LocalGenerator/cache/",
        "LocalGenerator/data/Runtime_dumps/",
    )
    return (
        not normalized
        or normalized == "SOURCE_FILE_INDEX.txt"
        or normalized in {"config.env", "WORKTREE_STATUS.txt"}
        or normalized.startswith(ignored_prefixes)
        or any(part in ignored_parts for part in parts)
    )


def _source_index_entries(root: Path = ROOT) -> dict[str, str]:
    source_index = root / "SOURCE_FILE_INDEX.txt"
    if not source_index.is_file():
        return {}
    rows: dict[str, str] = {}
    for line in source_index.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split(None, 2)
        if len(parts) != 3:
            continue
        digest, _size, relative = parts
        normalized = relative.replace("\\", "/")
        if not _ignored_repository_path(normalized):
            rows[normalized] = digest.lower()
    return rows


def _source_index_changes(root: Path = ROOT) -> list[str]:
    expected = _source_index_entries(root)
    if not expected:
        return []
    changed: set[str] = set()
    for relative, expected_digest in expected.items():
        path = root / relative
        if not path.is_file():
            changed.add(relative)
            continue
        actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_digest != expected_digest:
            changed.add(relative)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if _ignored_repository_path(relative):
            continue
        if relative not in expected:
            changed.add(relative)
    return sorted(changed)


def changed_files() -> list[str]:
    proc = _git("status", "--porcelain=v1", "--untracked-files=all")
    if proc.returncode != 0:
        return _source_index_changes()
    rows: list[str] = []
    for line in proc.stdout.splitlines():
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        normalized = path.replace("\\", "/")
        if _ignored_repository_path(normalized):
            continue
        rows.append(normalized)
    return sorted(set(rows))


def _matches(path: str, pattern: str) -> bool:
    # fnmatch treats ** adequately for the repository paths used here; also test
    # a collapsed form so patterns such as ModSources/**/*.cs match direct files.
    return fnmatch(path, pattern) or fnmatch(path, pattern.replace("**/", ""))


def impacted(files: list[str]) -> tuple[list[dict[str, Any]], list[str], bool]:
    rules = _load(RULES_PATH).get("rules", [])
    matched = [rule for rule in rules if any(_matches(path, pattern) for path in files for pattern in rule.get("patterns", []))]
    checks = set(_load(MANIFEST_PATH).get("alwaysChecks", []))
    checks.update(check for rule in matched for check in rule.get("checks", []))
    requires_build = any(bool(rule.get("requiresBuild")) for rule in matched)
    return matched, sorted(checks), requires_build


def _environment() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "LocalGenerator")
    env["PYTHONUTF8"] = "1"
    env["INFINI_SKIP_CONFIG_FILE"] = "1"
    return env


def _run_check(name: str, command: list[str]) -> dict[str, Any]:
    start = time.monotonic()
    command = list(command)
    if command and command[0] in {"python", "python3"}:
        command[0] = sys.executable
    executable = command[0] if command and Path(command[0]).is_file() else shutil.which(command[0])
    if executable is None and command:
        sibling_names = [command[0]]
        if not Path(command[0]).suffix:
            sibling_names.extend([f"{command[0]}.exe", f"{command[0]}.cmd"])
        for sibling_name in sibling_names:
            sibling = Path(sys.executable).with_name(sibling_name)
            if sibling.is_file():
                command[0] = str(sibling)
                executable = str(sibling)
                break
    if executable is None:
        return {"name": name, "status": "unavailable", "command": command, "durationSeconds": 0.0, "reason": f"{command[0]} not installed"}
    if name == "pyright" and "--pythonpath" not in command:
        command.extend(["--pythonpath", sys.executable])
    # All manifest commands are repository-root relative. The pytest shard
    # runner creates its own isolated LocalGenerator working directories.
    cwd = ROOT
    proc = subprocess.run(command, cwd=cwd, env=_environment(), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    return {
        "name": name,
        "status": "passed" if proc.returncode == 0 else "failed",
        "exitCode": proc.returncode,
        "command": command,
        "durationSeconds": round(time.monotonic() - start, 3),
        "outputTail": proc.stdout[-12000:],
    }


def _dotnet_executable() -> str | None:
    """Find .NET in native shells and in the project's WSL/Windows workflow."""
    return shutil.which("dotnet") or shutil.which("dotnet.exe")


def _dotnet_path(executable: str, path: Path) -> str:
    """Translate WSL paths only when invoking the Windows dotnet host."""
    if os.name != "nt" and executable.lower().endswith(".exe") and shutil.which("wslpath"):
        proc = subprocess.run(
            ["wslpath", "-w", str(path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    return str(path)


def command_doctor(_: argparse.Namespace) -> int:
    modules = {name: importlib.util.find_spec(name) is not None for name in ("pydantic", "hypothesis", "pytest")}
    project = ROOT / "ModSources/InfiniCrafterLocal/InfiniCrafterLocal.csproj"
    deps_root = os.environ.get("INFINI_TML_DEPS_SRC", "")
    report = {
        "schema": "infini.agent-doctor.v1",
        "ok": all(modules.values()) and MANIFEST_PATH.exists() and RULES_PATH.exists(),
        "python": sys.version.split()[0],
        "modules": modules,
        "executables": {
            "git": shutil.which("git"),
            "dotnet": _dotnet_executable(),
            "ruff": shutil.which("ruff"),
            "pyright": shutil.which("pyright"),
        },
        "gitBaseline": _base_revision(),
        "projectExists": project.exists(),
        "externalDepsRoot": deps_root,
        "externalDepsAvailable": bool(deps_root and Path(deps_root).exists()),
        "runtimeSelfTestReport": os.environ.get("INFINI_AGENT_SELFTEST_REPORT", ""),
        "runtimeSelfTestAvailable": bool(
            os.environ.get("INFINI_AGENT_SELFTEST_REPORT")
            and Path(os.environ["INFINI_AGENT_SELFTEST_REPORT"]).is_file()
        ),
        "changedFileCount": len(changed_files()),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


def command_verify(args: argparse.Namespace) -> int:
    manifest = _load(MANIFEST_PATH)
    files = changed_files()
    rules, selected, requires_build = impacted(files)
    if not args.changed:
        selected = list(manifest.get("fullChecks", []))
    checks: list[dict[str, Any]] = []
    for name in selected:
        command = manifest.get("checks", {}).get(name)
        if command:
            checks.append(_run_check(name, list(command)))
    blocked: list[str] = []
    build_status = "not-required"
    if requires_build or args.require_build:
        dotnet = _dotnet_executable()
        if dotnet is None:
            build_status = "blocked"
            blocked.append("C#-sensitive diff requires real tML build, but dotnet/dotnet.exe is unavailable")
        elif not os.environ.get("INFINI_TML_DEPS_SRC"):
            build_status = "blocked"
            blocked.append("C#-sensitive diff requires INFINI_TML_DEPS_SRC for real tML build")
        else:
            project = _dotnet_path(dotnet, ROOT / "ModSources/InfiniCrafterLocal/InfiniCrafterLocal.csproj")
            deps_root = _dotnet_path(dotnet, Path(os.environ["INFINI_TML_DEPS_SRC"]))
            command = [dotnet, "build", project, "-c", "Debug", "--nologo", "-v:minimal", "-warnaserror", f"/p:InfiniExternalDepsRoot={deps_root}"]
            row = _run_check("tml_build", command)
            checks.append(row)
            build_status = row["status"]
            if row["status"] == "passed":
                report_path = os.environ.get("INFINI_AGENT_SELFTEST_REPORT", "")
                if report_path and Path(report_path).is_file():
                    checks.append(_run_check("tml_runtime_selftest", ["python", "tools/check_tml_selftest_report.py", report_path]))
    failed = [row for row in checks if row["status"] == "failed"]
    unavailable = [row for row in checks if row["status"] == "unavailable"]
    report = {
        "schema": "infini.agent-run-result.v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "ok": not failed,
        "releaseReady": not failed and not blocked and not unavailable,
        "baseRevision": _base_revision(),
        "changedFiles": files,
        "impactedRules": [rule["id"] for rule in rules],
        "requiresBuild": requires_build,
        "buildStatus": build_status,
        "checks": checks,
        "blocked": blocked,
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else ARTIFACTS / "last_verify.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] and (not args.require_build or report["releaseReady"]) else 1


def _read_context_file(path: str, remaining: int) -> tuple[dict[str, Any], int]:
    target = ROOT / path
    if not target.is_file() or remaining <= 0:
        return {"path": path, "available": False}, remaining
    text = target.read_text(encoding="utf-8-sig", errors="replace")
    chunk = text[:remaining]
    return {"path": path, "available": True, "truncated": len(chunk) < len(text), "content": chunk}, remaining - len(chunk)


def command_context(args: argparse.Namespace) -> int:
    files = changed_files()
    rules, checks, requires_build = impacted(files)
    requested: list[str] = ["AGENTS.md", ".agent/manifest.json", ".agent/impact_rules.json"]
    for rule in rules:
        requested.extend(rule.get("context", []))
    requested.extend(files[:30])
    remaining = max(1000, int(args.budget))
    docs: list[dict[str, Any]] = []
    for path in dict.fromkeys(requested):
        row, remaining = _read_context_file(path, remaining)
        docs.append(row)
        if remaining <= 0:
            break
    report = {
        "schema": "infini.agent-context.v1",
        "task": args.task,
        "baseRevision": _base_revision(),
        "changedFiles": files,
        "impactedRules": [rule["id"] for rule in rules],
        "requiredChecks": checks,
        "requiresBuild": requires_build,
        "documents": docs,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def command_diff(_: argparse.Namespace) -> int:
    diff = _git("diff", "--stat", "HEAD")
    name_status = _git("diff", "--name-status", "HEAD")
    semantic = _run_check("semantic_runtime_diff", ["python", "tools/semantic_runtime_diff.py"])
    parity = _run_check("contract_parity", ["python", "tools/contract_parity.py", "--json"])
    report = {
        "schema": "infini.agent-semantic-diff.v1",
        "ok": semantic["status"] == "passed" and parity["status"] == "passed",
        "baseRevision": _base_revision(),
        "changedFiles": changed_files(),
        "gitStat": diff.stdout,
        "nameStatus": name_status.stdout,
        "semanticRuntime": semantic,
        "contractParity": parity,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


def command_handoff(args: argparse.Namespace) -> int:
    verify_path = ARTIFACTS / "last_verify.json"
    verification = _load(verify_path) if verify_path.exists() else None
    files = changed_files()
    rules, checks, requires_build = impacted(files)
    report = {
        "schema": "infini.agent-handoff.v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "baseRevision": _base_revision(),
        "changedFiles": files,
        "impactedRules": [rule["id"] for rule in rules],
        "requiredChecks": checks,
        "requiresBuild": requires_build,
        "verification": verification,
        "claimPolicy": "Do not claim runtime/build success when required checks are blocked or unavailable.",
    }
    out = Path(args.out) if args.out else AGENT_DIR / "current_state.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0



def _validate_task_payload(payload: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["task must be a JSON object"]
    allowed_keys = {"taskId", "goal", "baseRevision", "allowedBoundaries", "forbiddenChanges", "acceptance", "requiresBuild"}
    unknown = sorted(set(payload) - allowed_keys)
    if unknown:
        errors.append("unknown task fields: " + ", ".join(unknown))
    for key in ("taskId", "goal", "baseRevision"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            errors.append(f"{key} must be a non-empty string")
    for key in ("allowedBoundaries", "acceptance"):
        value = payload.get(key)
        if not isinstance(value, list) or not value or not all(isinstance(row, str) and row.strip() for row in value):
            errors.append(f"{key} must be a non-empty string array")
    forbidden = payload.get("forbiddenChanges", [])
    if not isinstance(forbidden, list) or not all(isinstance(row, str) and row.strip() for row in forbidden):
        errors.append("forbiddenChanges must be a string array")
    if "requiresBuild" in payload and not isinstance(payload["requiresBuild"], bool):
        errors.append("requiresBuild must be boolean")
    return errors


def command_task_check(args: argparse.Namespace) -> int:
    path = Path(args.task_file)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"schema": "infini.agent-task-check.v1", "ok": False, "errors": [repr(exc)]}, ensure_ascii=False, indent=2))
        return 1
    errors = _validate_task_payload(payload)
    current = _base_revision()
    if isinstance(payload, dict) and payload.get("baseRevision") != current:
        errors.append(f"baseRevision mismatch: task={payload.get('baseRevision')} current={current}")
    files = changed_files()
    allowed = payload.get("allowedBoundaries", []) if isinstance(payload, dict) else []
    forbidden = payload.get("forbiddenChanges", []) if isinstance(payload, dict) else []
    outside = [path for path in files if allowed and not any(_matches(path, pattern) for pattern in allowed)]
    prohibited = [path for path in files if any(_matches(path, pattern) for pattern in forbidden)]
    if outside:
        errors.append("changed files outside allowedBoundaries: " + ", ".join(outside))
    if prohibited:
        errors.append("changed files match forbiddenChanges: " + ", ".join(prohibited))
    _, _, impact_requires_build = impacted(files)
    if impact_requires_build and isinstance(payload, dict) and not payload.get("requiresBuild", False):
        errors.append("task must set requiresBuild=true for the current C#-sensitive diff")
    report = {
        "schema": "infini.agent-task-check.v1",
        "ok": not errors,
        "taskId": payload.get("taskId") if isinstance(payload, dict) else None,
        "baseRevision": current,
        "changedFiles": files,
        "outsideAllowed": outside,
        "forbiddenMatches": prohibited,
        "requiresBuild": impact_requires_build,
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1

def command_bootstrap(args: argparse.Namespace) -> int:
    if (ROOT / ".git").exists():
        print(json.dumps({"ok": True, "status": "already_git", "revision": _base_revision()}, indent=2))
        return 0
    source_changes = _source_index_changes()
    if source_changes and not args.allow_dirty:
        print(json.dumps({
            "ok": False,
            "status": "source_snapshot_differs_from_index",
            "changedFiles": source_changes,
            "hint": "re-extract the archive or pass --allow-dirty only when intentionally baselining the current tree",
        }, ensure_ascii=False, indent=2))
        return 1
    if shutil.which("git") is None:
        print(json.dumps({"ok": False, "status": "git_unavailable"}, indent=2))
        return 1
    subprocess.run(["git", "init"], cwd=ROOT, check=True)
    subprocess.run(["git", "config", "user.name", "Infini Snapshot Agent"], cwd=ROOT, check=True)
    subprocess.run(["git", "config", "user.email", "snapshot@local.invalid"], cwd=ROOT, check=True)
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-m", args.message], cwd=ROOT, check=True)
    print(json.dumps({"ok": True, "status": "baseline_created", "revision": _base_revision()}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="agentctl")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor"); doctor.set_defaults(func=command_doctor)
    verify = sub.add_parser("verify"); verify.add_argument("--changed", action="store_true"); verify.add_argument("--require-build", action="store_true"); verify.add_argument("--out"); verify.set_defaults(func=command_verify)
    context = sub.add_parser("context"); context.add_argument("--task", required=True); context.add_argument("--budget", type=int, default=14000); context.add_argument("--out"); context.set_defaults(func=command_context)
    diff = sub.add_parser("diff"); diff.add_argument("--semantic", action="store_true"); diff.set_defaults(func=command_diff)
    handoff = sub.add_parser("handoff"); handoff.add_argument("--out"); handoff.set_defaults(func=command_handoff)
    task_check = sub.add_parser("task-check"); task_check.add_argument("--task-file", required=True); task_check.set_defaults(func=command_task_check)
    bootstrap = sub.add_parser("bootstrap-snapshot"); bootstrap.add_argument("--message", default="Baseline imported source snapshot"); bootstrap.add_argument("--allow-dirty", action="store_true"); bootstrap.set_defaults(func=command_bootstrap)
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
