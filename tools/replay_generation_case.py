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
import sys
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
    final_item = loaded.get("final_item.json") if isinstance(loaded.get("final_item.json"), dict) else {}
    compiled = loaded.get("compiled_runtime.json") if isinstance(loaded.get("compiled_runtime.json"), dict) else {}
    provenance = compiled.get("provenance") if isinstance(compiled.get("provenance"), dict) else {}
    balance = loaded.get("balance_report.json") if isinstance(loaded.get("balance_report.json"), dict) else {}
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

    if isinstance(result, dict):
        _save_json(cdir / "final_item.json", result)
        print(f"[saved] {cdir / 'final_item.json'}")
        debug = result.get("debug", {}) if isinstance(result.get("debug"), dict) else {}
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
        _write_multipass_debug_report(case_id, parents, result if isinstance(result, dict) else None)

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

def replay_case(args: argparse.Namespace) -> int:
    """Replay a saved case: load artifacts, recompile runtime state and print a summary."""
    case_id = _slugify(args.case_id)
    cdir = _case_dir(case_id)
    if not cdir.exists():
        print(f"ERROR: case '{case_id}' not found at {cdir}")
        return 1

    print(f"=== Replay case: {case_id} ===")
    print(f"  path: {cdir}")
    for artifact in CASE_FILES:
        p = cdir / artifact
        if p.exists():
            exists, data, status = _load_json(p)
            if status == "ok" and isinstance(data, dict):
                keys = list(data.keys())[:8]
                print(f"  {artifact}: OK ({len(data)} keys: {', '.join(keys)}...)")
            elif status == "ok":
                print(f"  {artifact}: OK (type={type(data).__name__})")
            else:
                print(f"  {artifact}: {status}")
        else:
            print(f"  {artifact}: MISSING")

    final_path = cdir / "final_item.json"
    if final_path.exists():
        try:
            from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_result

            item = _load_json_required(final_path)
            compiled = compile_runtime_plan_to_genome_result(item)
            provenance = compiled.get("provenance", {}) if isinstance(compiled, dict) else {}
            print(f"\n  [replay] compile OK; provenance keys: {list(provenance.keys())}")
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

    sp_replay = sub.add_parser("replay", help="Replay a saved case audit")
    sp_replay.add_argument("case_id")
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
