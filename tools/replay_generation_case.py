#!/usr/bin/env python3
"""Replay harness for InfiniCrafterLocal generation cases.

A case stores JSON artifacts for one craft so it can be inspected, diffed and
replayed without turning multipass into the main generation path.

Compatibility modes:
  python tools/replay_generation_case.py <case_id> [--cases-root ...] [--json]
      Summarize an existing case directory. This is the compatibility summary form.

  python tools/replay_generation_case.py save <case_id> --itemA a.json --itemB b.json
  python tools/replay_generation_case.py replay <case_id>
  python tools/replay_generation_case.py list
  python tools/replay_generation_case.py show <case_id> final_item.json
      Case management/debug commands. They do not apply multipass output.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_LOCAL_GEN = _HERE.parent / "LocalGenerator"
if str(_LOCAL_GEN) not in sys.path:
    sys.path.insert(0, str(_LOCAL_GEN))

from infini_local.core.env_utils import env_str  # noqa: E402

REPLAY_DIR_NAME = "replay_cases"
CASE_FILES = [
    "parents.json",
    "llm_raw.json",
    "structural_repair.json",
    "targeted_retry.json",
    "compiled_runtime.json",
    "balance_report.json",
    "final_item.json",
]

_multipass_mode = env_str("INFINI_MULTIPASS_AUTHORING", "").strip().lower()
MULTIPASS_DEBUG = _multipass_mode in {"debug_only", "1", "true", "yes"}


def _replay_root() -> Path:
    """Root directory for replay case storage.

    Uses LocalGenerator/cache by default so ad-hoc replay artifacts do not become
    release source files. Tests may monkeypatch this function.
    """
    return _LOCAL_GEN / "cache" / REPLAY_DIR_NAME


def _slugify(text: str) -> str:
    import re

    return re.sub(r"[^a-zA-Z0-9_-]+", "_", text).strip("_") or "case"


def _case_dir(case_id: str, create: bool = False) -> Path:
    p = _replay_root() / _slugify(case_id)
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def _load_json(path: Path) -> tuple[bool, Any, str]:
    if not path.exists():
        return False, None, "missing"
    try:
        return True, json.loads(path.read_text(encoding="utf-8")), "ok"
    except json.JSONDecodeError as exc:
        return True, None, f"invalid_json:{exc.lineno}:{exc.colno}"
    except OSError as exc:
        return True, None, f"read_error:{exc}"


def _load_json_required(path: Path) -> Any:
    exists, payload, status = _load_json(path)
    if not exists:
        raise FileNotFoundError(path)
    if status != "ok":
        raise ValueError(f"{path}: {status}")
    return payload


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def summarize_case(case_dir: Path) -> dict[str, Any]:
    files: dict[str, Any] = {}
    loaded: dict[str, Any] = {}
    for name in CASE_FILES:
        exists, payload, status = _load_json(case_dir / name)
        files[name] = {"exists": exists, "status": status, "path": str(case_dir / name)}
        if status == "ok":
            loaded[name] = payload
    raw_final_item = loaded.get("final_item.json")
    final_item: dict[str, Any] = raw_final_item if isinstance(raw_final_item, dict) else {}
    raw_compiled = loaded.get("compiled_runtime.json")
    compiled: dict[str, Any] = raw_compiled if isinstance(raw_compiled, dict) else {}
    raw_provenance = compiled.get("provenance")
    provenance: dict[str, Any] = raw_provenance if isinstance(raw_provenance, dict) else {}
    raw_balance = loaded.get("balance_report.json")
    balance: dict[str, Any] = raw_balance if isinstance(raw_balance, dict) else {}
    return {
        "schema": "infini.replay-case-summary.v1",
        "caseDir": str(case_dir),
        "ok": bool(final_item) and all(row["status"] in {"ok", "missing"} for row in files.values()),
        "files": files,
        "finalItem": {
            "name": final_item.get("name", ""),
            "category": final_item.get("category", ""),
            "id": final_item.get("id", ""),
            "recipeKey": final_item.get("recipeKey", ""),
        },
        "compiledRuntime": {
            "hasPatch": isinstance(compiled.get("patch"), dict),
            "provenanceKeys": sorted(provenance.keys()),
            "fieldSourceCount": len(provenance.get("fieldSources") or {}) if isinstance(provenance.get("fieldSources"), dict) else 0,
        },
        "balanceReport": {
            "schema": balance.get("schema", ""),
            "powerBand": balance.get("powerBand", ""),
            "hasClamps": bool(balance.get("clamps")),
        },
        "dryRun": True,
        "note": "Replay harness audits persisted artifacts and can recompile final_item runtime state; it never applies multipass output to the main generator.",
    }


def resolve_case(case_id: str, cases_root: Path) -> Path:
    candidate = Path(case_id)
    if candidate.exists():
        return candidate
    return cases_root / case_id


def summary_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("case_id", help="Case id or path to a saved generation case directory")
    ap.add_argument("--cases-root", default=str(_replay_root()), help="Root used when case_id is not a path")
    ap.add_argument("--json", action="store_true", help="Emit pretty JSON summary")
    args = ap.parse_args(argv)

    case_dir = resolve_case(args.case_id, Path(args.cases_root))
    summary = summarize_case(case_dir)
    text = json.dumps(summary, ensure_ascii=False, indent=2 if args.json else None, default=str)
    print(text)
    return 0 if summary["ok"] else 2


def save_case(args: argparse.Namespace) -> int:
    """Save a generation case as a set of replay artifacts."""
    case_id = _slugify(args.case_id)
    cdir = _case_dir(case_id, create=True)

    if args.parents_json:
        parents = _load_json_required(Path(args.parents_json))
    else:
        if not args.itemA or not args.itemB:
            print("ERROR: either --parents-json or both --itemA and --itemB are required")
            return 2
        parents = {
            "itemA": _load_json_required(Path(args.itemA)),
            "itemB": _load_json_required(Path(args.itemB)),
        }
        if args.world_id:
            parents["worldId"] = args.world_id

    _save_json(cdir / "parents.json", parents)
    print(f"[saved] {cdir / 'parents.json'}")

    try:
        from infini_local.pipelines.combine_pipeline import combine
    except Exception as exc:
        print(f"WARN: could not import combine pipeline: {exc}")
        print("[partial] parents.json saved; run replay later when imports resolve.")
        return 0

    try:
        t0 = time.time()
        result = combine(parents)
        elapsed = int((time.time() - t0) * 1000)
        print(f"[combine] {elapsed}ms")
    except Exception as exc:
        print(f"ERROR: combine failed: {exc}")
        _save_json(cdir / "combine_error.json", {"error": repr(exc), "type": type(exc).__name__})
        return 1

    _save_json(cdir / "final_item.json", result)
    print(f"[saved] {cdir / 'final_item.json'}")
    raw_debug = result.get("debug")
    debug: dict[str, Any] = raw_debug if isinstance(raw_debug, dict) else {}
    artifact_keys = {
            "llmRaw": "llm_raw.json",
            "structuralRepair": "structural_repair.json",
            "targetedRetry": "targeted_retry.json",
        }
    for key, filename in artifact_keys.items():
        if key in debug:
            _save_json(cdir / filename, debug[key])
            print(f"[saved] {cdir / filename}")
    try:
        from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_result

        compiled = compile_runtime_plan_to_genome_result(result)
        _save_json(cdir / "compiled_runtime.json", compiled)
        print(f"[saved] {cdir / 'compiled_runtime.json'}")
    except Exception as exc:
        print(f"WARN: compile_runtime_plan_to_genome_result failed: {exc}")
    try:
        from infini_local.core.balance_report import build_balance_report

        report = build_balance_report(result)
        _save_json(cdir / "balance_report.json", report)
        print(f"[saved] {cdir / 'balance_report.json'}")
    except Exception as exc:
        print(f"WARN: build_balance_report failed: {exc}")

    if MULTIPASS_DEBUG:
        _write_multipass_debug_report(case_id, parents, result)

    print(f"\nCase '{case_id}' saved with {len(list(cdir.glob('*.json')))} artifacts.")
    return 0


def _write_multipass_debug_report(case_id: str, parents: dict[str, Any], single_pass_result: dict[str, Any] | None) -> None:
    """Write a disabled multipass comparison report without pretending to author fragments."""
    cdir = _case_dir(case_id)
    final_debug = single_pass_result.get("debug", {}) if isinstance(single_pass_result, dict) and isinstance(single_pass_result.get("debug"), dict) else {}
    comparison = {
        "mode": "debug_only",
        "applied": False,
        "reason": "INFINI_MULTIPASS_AUTHORING=debug_only records diagnostics only; single-pass remains the only item applied.",
        "singlePass": {
            "hasResult": single_pass_result is not None,
            "name": single_pass_result.get("name") if isinstance(single_pass_result, dict) else None,
            "category": single_pass_result.get("category") if isinstance(single_pass_result, dict) else None,
            "hasRuntimePlan": bool(single_pass_result.get("runtimePlan")) if isinstance(single_pass_result, dict) else False,
            "debugKeys": sorted(final_debug.keys()),
        },
        "multipass": {
            "enabledAsMainPath": False,
            "fragmentsAuthored": [],
            "fragmentsValidated": [],
            "resultApplied": False,
        },
        "parentsPresent": bool(parents),
    }
    _save_json(cdir / "multipass_comparison.json", comparison)
    print(f"[saved] {cdir / 'multipass_comparison.json'} (debug-only report)")

def _semantic_diff(path: str, expected: Any, actual: Any, out: list[dict[str, Any]]) -> None:
    """Collect a deterministic structural diff suitable for machine gates."""
    if type(expected) is not type(actual):
        out.append({"path": path or "$", "expected": expected, "actual": actual})
        return
    if isinstance(expected, dict):
        for key in sorted(set(expected) | set(actual)):
            child = f"{path}.{key}" if path else key
            if key not in expected:
                out.append({"path": child, "expected": "<missing>", "actual": actual[key]})
            elif key not in actual:
                out.append({"path": child, "expected": expected[key], "actual": "<missing>"})
            else:
                _semantic_diff(child, expected[key], actual[key], out)
        return
    if isinstance(expected, list):
        if len(expected) != len(actual):
            out.append({"path": f"{path}.length", "expected": len(expected), "actual": len(actual)})
        for index, (left, right) in enumerate(zip(expected, actual)):
            _semantic_diff(f"{path}[{index}]", left, right, out)
        return
    if expected != actual:
        out.append({"path": path or "$", "expected": expected, "actual": actual})


def _canonical_compiled_runtime(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep deterministic semantic compiler output and drop diagnostic decoration."""
    raw_compiled = payload.get("compiled")
    compiled: dict[str, Any] = raw_compiled if isinstance(raw_compiled, dict) else {}
    raw_provenance = payload.get("provenance")
    provenance: dict[str, Any] = raw_provenance if isinstance(raw_provenance, dict) else {}
    raw_validation = payload.get("validation")
    validation: dict[str, Any] = raw_validation if isinstance(raw_validation, dict) else {}
    return {
        "patch": payload.get("patch") if isinstance(payload.get("patch"), dict) else {},
        "clamps": payload.get("clamps") if isinstance(payload.get("clamps"), list) else [],
        "errors": payload.get("errors") if isinstance(payload.get("errors"), list) else [],
        "compiled": {
            "api": compiled.get("api"),
            "compiler": compiled.get("compiler"),
            "executableFields": compiled.get("executableFields") if isinstance(compiled.get("executableFields"), dict) else {},
            "functionCounts": compiled.get("functionCounts") if isinstance(compiled.get("functionCounts"), dict) else {},
            "runtimePromiseTruth": compiled.get("runtimePromiseTruth") if isinstance(compiled.get("runtimePromiseTruth"), dict) else {},
        },
        "provenance": {
            "api": provenance.get("api"),
            "engineFunctions": provenance.get("engineFunctions") if isinstance(provenance.get("engineFunctions"), list) else [],
            "authoredFields": provenance.get("authoredFields") if isinstance(provenance.get("authoredFields"), dict) else {},
            "authoredByFunction": provenance.get("authoredByFunction") if isinstance(provenance.get("authoredByFunction"), dict) else {},
            "gameplayChildren": provenance.get("gameplayChildren") if isinstance(provenance.get("gameplayChildren"), dict) else {},
            "pureVfx": provenance.get("pureVfx") if isinstance(provenance.get("pureVfx"), dict) else {},
            "unsupported": provenance.get("unsupported") if isinstance(provenance.get("unsupported"), list) else [],
            "futureDisabled": provenance.get("futureDisabled") if isinstance(provenance.get("futureDisabled"), list) else [],
            "fieldSources": provenance.get("fieldSources") if isinstance(provenance.get("fieldSources"), dict) else {},
            "normalization": provenance.get("normalization") if isinstance(provenance.get("normalization"), dict) else {},
        },
        "validation": {
            "api": validation.get("api"),
            "ok": validation.get("ok"),
            "errors": validation.get("errors") if isinstance(validation.get("errors"), list) else [],
            "warnings": validation.get("warnings") if isinstance(validation.get("warnings"), list) else [],
            "quality": validation.get("quality") if isinstance(validation.get("quality"), dict) else {},
            "normalization": validation.get("normalization") if isinstance(validation.get("normalization"), dict) else {},
        },
    }


def _canonical_final_runtime(payload: dict[str, Any]) -> dict[str, Any]:
    """Select the executable result, excluding assets, cache paths and traces."""
    keys = ("category", "gameplay", "attack", "accessory", "armor", "visualKit", "vfxManifest")
    return {key: payload.get(key) for key in keys if key in payload}


def _strict_recompile(cdir: Path) -> dict[str, Any]:
    """Revalidate and recompile a persisted final item without external services."""
    from infini_local.core.boundary_models import validate_executable_item_boundary
    from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_result

    item = _load_json_required(cdir / "final_item.json")
    if not isinstance(item, dict):
        raise TypeError("final_item.json must contain an object")
    boundary = validate_executable_item_boundary(item)
    compiled = compile_runtime_plan_to_genome_result(item)
    return {"item": item, "boundary": boundary, "compiled": compiled}


def _rerun_case(cdir: Path, replay_raw: str | None) -> dict[str, Any]:
    """Run the real combine pipeline in isolated cache directories.

    A saved raw LLM response is used when available.  The replay path is explicit:
    it never silently contacts a configured remote model when no replay fixture was
    supplied.
    """
    parents = _load_json_required(cdir / "parents.json")
    if not isinstance(parents, dict):
        raise TypeError("parents.json must contain an object accepted by combine()")
    raw_path = Path(replay_raw) if replay_raw else cdir / "llm_raw.json"
    if not raw_path.exists():
        raise FileNotFoundError("strict rerun requires --replay-raw or llm_raw.json")

    old_env = dict(os.environ)
    try:
        with tempfile.TemporaryDirectory(prefix="infini-replay-") as temp_root:
            os.environ["INFINI_LLM_REPLAY_RAW"] = str(raw_path.resolve())
            os.environ["INFINI_CACHE_DIR"] = str(Path(temp_root) / "cache")
            os.environ["INFINI_WORLD_RECIPES_DIR"] = str(Path(temp_root) / "world_recipes")
            os.environ["INFINI_TRACE_PROMPTS"] = "0"
            from infini_local.pipelines.combine_pipeline import combine

            result = combine(parents)
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    return result


def build_replay_report(
    cdir: Path,
    *,
    compare: bool,
    rerun: bool,
    replay_raw: str | None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    differences: list[dict[str, Any]] = []
    try:
        strict = _strict_recompile(cdir)
        checks.append({"name": "strict_boundary", "status": "passed"})
        checks.append({"name": "runtime_recompile", "status": "passed"})
    except Exception as exc:
        return {
            "schema": "infini.replay-result.v2",
            "caseDir": str(cdir),
            "ok": False,
            "checks": [{"name": "strict_recompile", "status": "failed", "error": repr(exc)}],
            "differences": [],
        }

    if compare:
        expected_path = cdir / "compiled_runtime.json"
        if not expected_path.exists():
            checks.append({"name": "compiled_runtime_compare", "status": "failed", "error": "compiled_runtime.json missing"})
        else:
            expected = _load_json_required(expected_path)
            if not isinstance(expected, dict):
                checks.append({"name": "compiled_runtime_compare", "status": "failed", "error": "compiled_runtime.json must contain an object"})
            else:
                _semantic_diff(
                    "compiledRuntime",
                    _canonical_compiled_runtime(expected),
                    _canonical_compiled_runtime(strict["compiled"]),
                    differences,
                )
                checks.append({
                    "name": "compiled_runtime_compare",
                    "status": "passed" if not differences else "failed",
                    "differenceCount": len(differences),
                })

    if rerun:
        try:
            rerun_item = _rerun_case(cdir, replay_raw)
            rerun_differences: list[dict[str, Any]] = []
            _semantic_diff(
                "finalRuntime",
                _canonical_final_runtime(strict["item"]),
                _canonical_final_runtime(rerun_item),
                rerun_differences,
            )
            differences.extend(rerun_differences)
            checks.append({
                "name": "full_pipeline_rerun",
                "status": "passed" if not rerun_differences else "failed",
                "differenceCount": len(rerun_differences),
            })
        except Exception as exc:
            checks.append({"name": "full_pipeline_rerun", "status": "failed", "error": repr(exc)})

    ok = all(row.get("status") == "passed" for row in checks)
    return {
        "schema": "infini.replay-result.v2",
        "caseDir": str(cdir),
        "ok": ok,
        "checks": checks,
        "differences": differences[:200],
        "strict": True,
        "compare": compare,
        "rerun": rerun,
    }


def replay_case(args: argparse.Namespace) -> int:
    """Replay a saved case; strict mode is a real non-zero verification gate."""
    case_id = _slugify(args.case_id)
    cdir = _case_dir(case_id)
    if not cdir.exists():
        print(f"ERROR: case '{case_id}' not found at {cdir}")
        return 1

    if args.strict or args.compare or args.rerun:
        report = build_replay_report(
            cdir,
            compare=bool(args.compare or args.strict),
            rerun=bool(args.rerun),
            replay_raw=args.replay_raw,
        )
        text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
        if args.out:
            Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0 if report["ok"] else 1

    print(f"=== Replay case: {case_id} ===")
    print(f"  path: {cdir}")
    for artifact in CASE_FILES:
        p = cdir / artifact
        if p.exists():
            _, data, status = _load_json(p)
            if status == "ok" and isinstance(data, dict):
                keys = list(data.keys())[:8]
                print(f"  {artifact}: OK ({len(data)} keys: {', '.join(keys)}...)")
            elif status == "ok":
                print(f"  {artifact}: OK (type={type(data).__name__})")
            else:
                print(f"  {artifact}: {status}")
        else:
            print(f"  {artifact}: MISSING")

    try:
        strict = _strict_recompile(cdir)
        provenance = strict["compiled"].get("provenance", {})
        print(f"\n  [replay] compile OK; provenance keys: {list(provenance.keys())}")
        return 0
    except Exception as exc:
        print(f"\n  [replay] compile FAILED: {exc}")
        return 0


def list_cases(_: argparse.Namespace) -> int:
    root = _replay_root()
    if not root.exists():
        print("No replay cases saved yet.")
        return 0
    cases = sorted(root.iterdir())
    if not cases:
        print("No replay cases found.")
        return 0
    print(f"Replay cases in {root}:")
    for c in cases:
        if c.is_dir():
            artifacts = list(c.glob("*.json"))
            print(f"  {c.name}  ({len(artifacts)} artifacts)")
    return 0


def show_case(args: argparse.Namespace) -> int:
    case_id = _slugify(args.case_id)
    artifact = args.artifact
    cdir = _case_dir(case_id)
    if not cdir.exists():
        print(f"ERROR: case '{case_id}' not found")
        return 1
    p = cdir / artifact
    if not p.exists():
        print(f"ERROR: artifact '{artifact}' not found in case '{case_id}'")
        print(f"Available: {', '.join(sorted(f.name for f in cdir.glob('*.json')))}")
        return 1
    print(json.dumps(_load_json_required(p), ensure_ascii=False, indent=2, default=str))
    return 0


def command_main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Replay harness case management")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp_save = sub.add_parser("save", help="Save a generation case")
    sp_save.add_argument("case_id")
    sp_save.add_argument("--itemA", help="Path to itemA JSON")
    sp_save.add_argument("--itemB", help="Path to itemB JSON")
    sp_save.add_argument("--parents-json", help="Path to combined parents JSON")
    sp_save.add_argument("--world-id", default="")
    sp_save.set_defaults(func=save_case)

    sp_replay = sub.add_parser("replay", help="Replay or strictly verify a saved case")
    sp_replay.add_argument("case_id")
    sp_replay.add_argument("--strict", action="store_true", help="Fail on strict boundary, compile, or saved-runtime drift")
    sp_replay.add_argument("--compare", action="store_true", help="Compare recompiled runtime with compiled_runtime.json")
    sp_replay.add_argument("--rerun", action="store_true", help="Run the full combine pipeline with a saved raw LLM response")
    sp_replay.add_argument("--replay-raw", help="Raw/stage-keyed LLM replay fixture used by --rerun")
    sp_replay.add_argument("--out", help="Write machine-readable replay report")
    sp_replay.set_defaults(func=replay_case)

    sp_list = sub.add_parser("list", help="List all saved cases")
    sp_list.set_defaults(func=list_cases)

    sp_show = sub.add_parser("show", help="Show a specific artifact")
    sp_show.add_argument("case_id")
    sp_show.add_argument("artifact", help="Artifact filename (e.g. final_item.json)")
    sp_show.set_defaults(func=show_case)

    args = ap.parse_args(argv)
    return args.func(args)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return command_main(["--help"])
    if argv[0] in {"save", "replay", "list", "show"}:
        return command_main(argv)
    if argv[0] == "summary":
        return summary_main(argv[1:])
    return summary_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
