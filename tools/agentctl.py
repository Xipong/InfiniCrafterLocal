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
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / ".agent"
MANIFEST_PATH = AGENT_DIR / "manifest.json"
RULES_PATH = AGENT_DIR / "impact_rules.json"
ARTIFACTS = ROOT / "artifacts" / "agent"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def _base_revision() -> str:
    proc = run_git("rev-parse", "HEAD")
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


def changed_files(base: str | None = None) -> list[str]:
    """Committed branch diff plus staged, unstaged and untracked paths.

    --base is a merge-base comparison, so unrelated upstream commits are not
    attributed to this task. --no-renames retains both sides of moves.
    """
    if run_git("rev-parse", "--show-toplevel").returncode != 0:
        if base:
            raise ValueError("--base requires a Git checkout")
        return _source_index_changes()
    commands: list[tuple[str, ...]] = [("diff", "--name-only", "-z", "--no-renames", "HEAD"),
                                      ("ls-files", "--others", "--exclude-standard", "-z")]
    if base:
        revision = run_git("rev-parse", "--verify", "--end-of-options", base + "^{commit}")
        if revision.returncode:
            raise ValueError(f"invalid --base revision: {base}")
        ancestor = run_git("merge-base", revision.stdout.strip(), "HEAD")
        if ancestor.returncode:
            raise ValueError(f"no merge base with {base}")
        commands.insert(0, ("diff", "--name-only", "-z", "--no-renames", ancestor.stdout.strip(), "HEAD"))
    rows: set[str] = set()
    for command in commands:
        proc = run_git(*command)
        if proc.returncode:
            raise ValueError(proc.stderr.strip() or "git change discovery failed")
        rows.update(path for path in proc.stdout.split("\0") if path and not _ignored_repository_path(path))
    return sorted(rows)


def _matches(path: str, pattern: str) -> bool:
    # fnmatch treats ** adequately for the repository paths used here; also test
    # a collapsed form so patterns such as ModSources/**/*.cs match direct files.
    return fnmatch(path, pattern) or fnmatch(path, pattern.replace("**/", ""))


def impacted(files: list[str], *, areas: list[str] | None = None) -> tuple[list[dict[str, Any]], list[str], bool]:
    rules = _load(RULES_PATH).get("rules", [])
    unknown_areas = set(areas or []) - {rule["area"] for rule in rules}
    if unknown_areas:
        raise ValueError("unknown areas: " + ", ".join(sorted(unknown_areas)))
    matched = [rule for rule in rules if rule["area"] in (areas or []) or any(
        _matches(path, pattern) for path in files for pattern in rule.get("patterns", []))]
    checks = {check for rule in matched for check in rule.get("checks", [])}
    requires_build = any(path.startswith("ModSources/") and path.endswith((".cs", ".csproj")) for path in files)
    requires_build = requires_build or any(bool(rule.get("requiresBuild")) for rule in matched)
    return matched, sorted(checks), requires_build


def repository_paths(paths: list[str], *, require_files: bool = False) -> list[str]:
    selected: list[str] = []
    root = ROOT.resolve()
    for path in paths:
        target = (ROOT / path).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"path must stay inside checkout: {path}")
        if require_files and not target.is_file():
            raise ValueError(f"path must name an existing file: {path}")
        selected.append(target.relative_to(root).as_posix())
    return list(dict.fromkeys(selected))


def _test_module(path: str) -> bool:
    candidate = ROOT / path
    return any(path.startswith(prefix) and candidate.name.startswith("test_") and candidate.suffix == ".py"
               and candidate.is_file() and candidate.resolve().is_relative_to((ROOT / prefix).resolve())
               for prefix in ("LocalGenerator/tests/", "toolbox/tests/"))


def verification_plan(files: list[str], *, final: bool = False, areas: list[str] | None = None) -> dict[str, Any]:
    """Small owner-area map for iteration; unknown surfaces require final gates."""
    manifest = _load(MANIFEST_PATH)
    rules, checks, requires_build = impacted(files, areas=areas)
    unknown = [path for path in files if not _test_module(path) and not any(
        _matches(path, pattern) for rule in rules for pattern in rule.get("patterns", []))]
    tests = {path for path in files if _test_module(path)}
    for rule in rules:
        for pattern in rule.get("tests", []):
            matches = [path.relative_to(ROOT).as_posix() for path in ROOT.glob(pattern)
                       if _test_module(path.relative_to(ROOT).as_posix())]
            if not matches:
                raise ValueError(f"test selection pattern has no modules: {pattern}")
            tests.update(matches)
    full = final or bool(unknown)
    if full:
        checks = list(manifest["fullChecks"])
        tests = set()
    return {
        "mode": "final" if final else "final_fallback" if unknown else "iteration",
        "changedFiles": files,
        "impactedRules": [rule["id"] for rule in rules],
        "checks": checks,
        "tests": sorted(tests),
        "requiresBuild": requires_build,
        "unmappedPaths": unknown,
        "releaseScope": full,
    }


def _environment() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "LocalGenerator")
    env["PYTHONUTF8"] = "1"
    env["INFINI_SKIP_CONFIG_FILE"] = "1"
    env["INFINI_TEST_USE_PROJECT_CONFIG"] = "0"
    return env


def _run_check(name: str, command: list[str]) -> dict[str, Any]:
    from validate_release import run_check
    return run_check(name, command, root=ROOT, env=_environment())


def _dotnet_executable() -> str | None:
    """Find .NET in native shells and in the project's WSL/Windows workflow."""
    return shutil.which("dotnet") or shutil.which("dotnet.exe")



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
    paths = getattr(args, "path", None) or []
    areas = getattr(args, "area", None) or []
    explicit = bool(paths or areas)
    if explicit and (args.changed or args.base):
        raise ValueError("--path/--area select an explicit scope; use --changed/--base separately for the branch diff")
    files = repository_paths(paths, require_files=True) if explicit else changed_files(args.base)
    plan = verification_plan(files, final=not (args.changed or explicit), areas=areas)
    plan["scope"] = "paths" if paths else "areas" if areas else "changes"
    plan["areas"] = sorted(set(areas))
    if explicit:
        plan["paths"] = plan.pop("changedFiles")
    if args.require_build and "tml_build" not in plan["checks"]:
        plan["checks"].append("tml_build")
    if args.plan:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    checks = [_run_check(name, list(manifest["checks"][name])) for name in plan["checks"]]
    if plan["tests"]:
        checks.append(_run_check("focused_pytest", ["python", "tools/run_focused_pytests.py", *plan["tests"]]))
    passed = bool(checks) and all(row["status"] == "passed" for row in checks)
    report = {
        "schema": "infini.agent-run-result.v3",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        **plan,
        "ok": passed,
        "status": "not_selected" if not checks else "passed" if passed else "incomplete" if all(
            row["status"] in {"passed", "unavailable", "notRun"} for row in checks) else "failed",
        "releaseReady": passed and plan["releaseScope"],
        "baseRevision": _base_revision(),
        "comparisonBase": args.base,
        "checks": checks,
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else ARTIFACTS / "last_verify.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if passed else 2 if report["status"] in {"not_selected", "incomplete"} else 1


def _read_context_file(path: str, remaining: int, *, start_line: int = 1) -> tuple[dict[str, Any], int]:
    target = ROOT / path
    if not target.is_file() or remaining <= 0:
        return {"path": path, "available": False}, remaining
    lines = target.read_text(encoding="utf-8-sig", errors="replace").splitlines(keepends=True)
    if start_line < 1 or start_line > max(1, len(lines)):
        raise ValueError(f"context line is outside {path}: {start_line}")
    text = "".join(lines[start_line - 1:])
    chunk = text[:remaining]
    return {
        "path": path, "available": True, "startLine": start_line if chunk else None,
        "endLine": start_line + len(chunk.splitlines()) - 1 if chunk else None, "totalLines": len(lines),
        "truncated": start_line > 1 or len(chunk) < len(text), "content": chunk,
    }, remaining - len(chunk)


def command_context(args: argparse.Namespace) -> int:
    # A source lookup must not scan or repeat an unrelated branch diff. The
    # verify/diff commands own changed-file reports; context owns this request.
    scope = "paths" if args.path else "areas" if args.area else "changes"
    selected = args.path or ([] if args.area else changed_files(args.base))
    paths = repository_paths(selected, require_files=bool(args.path))
    start_line = getattr(args, "line", None)
    if start_line is not None and (not args.path or len(paths) != 1 or start_line < 1):
        raise ValueError("--line requires one --path and a positive line number")
    all_rules = _load(RULES_PATH)["rules"]
    areas = args.area or []
    rules, _, _ = impacted(paths, areas=areas)
    # Exact source first. Broader owner documentation remains opt-in via --area.
    requested = [path for path in paths if (ROOT / path).is_file()] if args.path else []
    requested.extend(path for rule in rules for path in rule.get("entrypoints", []))
    if not args.path:
        requested.extend(path for path in paths if (ROOT / path).is_file())
        requested.extend(path for rule in rules for path in rule.get("context", []))
    requested.extend(["docs/development/CODE_MAP_RU.md", "AGENTS.md"])
    remaining = int(args.budget)
    if remaining < 1:
        raise ValueError("--budget must be positive")
    docs: list[dict[str, Any]] = []
    for path in dict.fromkeys(requested):
        limit = remaining if start_line is not None and path == paths[0] else min(remaining, 3000)
        row, unused = _read_context_file(path, limit, start_line=start_line if start_line is not None and path == paths[0] else 1)
        remaining -= limit - unused
        docs.append(row)
        if remaining <= 0:
            break
    plan = verification_plan(paths, areas=areas)
    plan["paths"] = plan.pop("changedFiles")
    report = {
        "schema": "infini.agent-context.v3",
        "task": args.task,
        "baseRevision": _base_revision(),
        "comparisonBase": args.base,
        "scope": scope,
        "paths": paths,
        "areas": sorted({rule["area"] for rule in rules}),
        "availableAreas": sorted({rule["area"] for rule in all_rules}),
        "entrypoints": list(dict.fromkeys(path for rule in rules for path in rule.get("entrypoints", []))),
        "suggestedVerification": plan,
        "validationRun": False,
        "releaseReady": False,
        "hint": "Read the selected owner and its callers. Use verify --path/--area for this scope; verify --changed checks the branch diff.",
        "documents": docs,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def command_diff(args: argparse.Namespace) -> int:
    files = changed_files(args.base)
    scopes = {"workingTree": ["HEAD"]}
    if args.base:
        scopes["committed"] = [args.base + "...HEAD"]
    diffs = {name: {"stat": run_git("diff", "--stat", *scope),
                    "nameStatus": run_git("diff", "--name-status", *scope)}
             for name, scope in scopes.items()}
    ok = all(row.returncode == 0 for result in diffs.values() for row in result.values())
    report = {
        "schema": "infini.agent-source-diff.v1",
        "ok": ok,
        "baseRevision": _base_revision(),
        "comparisonBase": args.base,
        "changedFiles": files,
        "diffs": {name: {key: row.stdout if row.returncode == 0 else row.stderr
                          for key, row in result.items()} for name, result in diffs.items()},
        "validationRun": False,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if ok else 1



def command_handoff(args: argparse.Namespace) -> int:
    verify_path = ARTIFACTS / "last_verify.json"
    verification = _load(verify_path) if verify_path.exists() else None
    files = changed_files(args.base)
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
    verify = sub.add_parser("verify", help="Run owner checks for paths/areas, the changed diff, or full acceptance")
    verify.add_argument("--changed", action="store_true")
    verify.add_argument("--path", action="append", help="Check an existing repository file without scanning the diff (repeatable)")
    verify.add_argument("--area", action="append", help="Check a declared owner area without scanning the diff (repeatable)")
    verify.add_argument("--base")
    verify.add_argument("--plan", action="store_true")
    verify.add_argument("--require-build", action="store_true")
    verify.add_argument("--out")
    verify.set_defaults(func=command_verify)
    context = sub.add_parser("context"); context.add_argument("--task", default=""); context.add_argument("--area", action="append"); context.add_argument("--path", action="append"); context.add_argument("--line", type=int, help="Start the selected source excerpt at this 1-based line (one --path)"); context.add_argument("--base"); context.add_argument("--budget", type=int, default=5000); context.add_argument("--out"); context.set_defaults(func=command_context)
    diff = sub.add_parser("diff"); diff.add_argument("--base"); diff.set_defaults(func=command_diff)
    handoff = sub.add_parser("handoff"); handoff.add_argument("--out"); handoff.add_argument("--base"); handoff.set_defaults(func=command_handoff)
    task_check = sub.add_parser("task-check"); task_check.add_argument("--task-file", required=True); task_check.set_defaults(func=command_task_check)
    bootstrap = sub.add_parser("bootstrap-snapshot"); bootstrap.add_argument("--message", default="Baseline imported source snapshot"); bootstrap.add_argument("--allow-dirty", action="store_true"); bootstrap.set_defaults(func=command_bootstrap)
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
