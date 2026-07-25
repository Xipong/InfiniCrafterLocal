#!/usr/bin/env python3
"""Saved-case validation and deterministic replay for runtimeProgram v5.

The harness stores one accepted final item plus a canonical delivery-wire snapshot.
It never migrates retired runtimePlan/genome contracts and never contacts an LLM
unless the operator explicitly invokes ``save`` or ``replay --rerun``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any

_HERE = Path(__file__).resolve().parent
_LOCAL_GEN = _HERE.parent / "LocalGenerator"
if str(_LOCAL_GEN) not in sys.path:
    sys.path.insert(0, str(_LOCAL_GEN))

from infini_local.core.env_utils import env_path  # noqa: E402
from infini_local.core.runtime_authoring import validate_runtime_wire  # noqa: E402
from infini_local.storage.world_storage import sanitize_recipe_for_delivery  # noqa: E402

REPLAY_DIR_NAME = "replay_cases"
SNAPSHOT_SCHEMA = "infini.runtime-program-replay-snapshot.v1"
REPORT_SCHEMA = "infini.runtime-program-replay-result.v1"
CASE_FILES = (
    "parents.json",
    "llm_raw.json",
    "gameplay_repair.json",
    "visual_repair.json",
    "vfx_repair.json",
    "compiled_runtime.json",
    "final_item.json",
)


def _replay_root() -> Path:
    cache_root = env_path("INFINI_CACHE_DIR", _LOCAL_GEN / "cache")
    return cache_root / REPLAY_DIR_NAME


def _slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", text).strip("_") or "case"


def _case_dir(case_id: str, *, create: bool = False) -> Path:
    path = _replay_root() / _slugify(case_id)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


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
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _canonical_delivery_wire(payload: dict[str, Any]) -> dict[str, Any]:
    projected = sanitize_recipe_for_delivery(payload)
    if not isinstance(projected, dict):
        raise TypeError("delivery projection must return an object")
    projected.pop("debug", None)
    return projected


def _snapshot_for(payload: dict[str, Any]) -> dict[str, Any]:
    wire = _canonical_delivery_wire(payload)
    encoded = json.dumps(
        wire,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return {
        "schema": SNAPSHOT_SCHEMA,
        "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "wire": wire,
    }


def _strict_wire(payload: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(payload, dict):
        raise TypeError("final_item.json must contain an object")
    report = validate_runtime_wire(payload)
    if not report.get("ok"):
        raise ValueError(
            "final v5 wire rejected: "
            + json.dumps((report.get("errors") or [])[:16], ensure_ascii=False)
        )
    delivery = _canonical_delivery_wire(payload)
    delivery_report = validate_runtime_wire(delivery)
    if not delivery_report.get("ok"):
        raise ValueError(
            "delivery v5 wire rejected: "
            + json.dumps((delivery_report.get("errors") or [])[:16], ensure_ascii=False)
        )
    return payload, delivery


def _semantic_diff(
    path: str,
    expected: Any,
    actual: Any,
    output: list[dict[str, Any]],
) -> None:
    if type(expected) is not type(actual):
        output.append({"path": path or "$", "expected": expected, "actual": actual})
        return
    if isinstance(expected, dict):
        for key in sorted(set(expected) | set(actual)):
            child = f"{path}.{key}" if path else key
            if key not in expected:
                output.append(
                    {"path": child, "expected": "<missing>", "actual": actual[key]}
                )
            elif key not in actual:
                output.append(
                    {"path": child, "expected": expected[key], "actual": "<missing>"}
                )
            else:
                _semantic_diff(child, expected[key], actual[key], output)
        return
    if isinstance(expected, list):
        if len(expected) != len(actual):
            output.append(
                {
                    "path": f"{path}.length",
                    "expected": len(expected),
                    "actual": len(actual),
                }
            )
        for index, (left, right) in enumerate(zip(expected, actual)):
            _semantic_diff(f"{path}[{index}]", left, right, output)
        return
    if expected != actual:
        output.append({"path": path or "$", "expected": expected, "actual": actual})


def summarize_case(case_dir: Path) -> dict[str, Any]:
    files: dict[str, Any] = {}
    loaded: dict[str, Any] = {}
    for name in CASE_FILES:
        exists, payload, status = _load_json(case_dir / name)
        files[name] = {
            "exists": exists,
            "status": status,
            "path": str(case_dir / name),
        }
        if status == "ok":
            loaded[name] = payload
    raw_final_item = loaded.get("final_item.json")
    final_item: dict[str, Any] = raw_final_item if isinstance(raw_final_item, dict) else {}
    raw_snapshot = loaded.get("compiled_runtime.json")
    snapshot: dict[str, Any] = raw_snapshot if isinstance(raw_snapshot, dict) else {}
    wire_report = validate_runtime_wire(final_item) if final_item else {"ok": False}
    raw_runtime = final_item.get("runtimeProgram")
    runtime: dict[str, Any] = raw_runtime if isinstance(raw_runtime, dict) else {}
    return {
        "schema": "infini.runtime-program-replay-summary.v1",
        "caseDir": str(case_dir),
        "ok": bool(final_item) and bool(wire_report.get("ok")),
        "files": files,
        "finalItem": {
            "name": final_item.get("name", ""),
            "category": final_item.get("category", ""),
            "id": final_item.get("id", ""),
            "recipeKey": final_item.get("recipeKey", ""),
        },
        "runtimeProgram": {
            "apiVersion": runtime.get("apiVersion"),
            "entityCount": len(runtime.get("entities") or []),
            "bindingCount": len(runtime.get("bindings") or []),
        },
        "snapshot": {
            "schema": snapshot.get("schema", ""),
            "sha256": snapshot.get("sha256", ""),
        },
        "dryRun": True,
    }


def resolve_case(case_id: str, cases_root: Path) -> Path:
    candidate = Path(case_id)
    return candidate if candidate.exists() else cases_root / case_id


def summary_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_id", help="Case id or saved generation case directory")
    parser.add_argument("--cases-root", default=str(_replay_root()))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    summary = summarize_case(resolve_case(args.case_id, Path(args.cases_root)))
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2 if args.json else None,
            default=str,
        )
    )
    return 0 if summary["ok"] else 2


def _save_debug_artifacts(case_dir: Path, result: dict[str, Any]) -> None:
    raw_debug = result.get("debug")
    debug: dict[str, Any] = raw_debug if isinstance(raw_debug, dict) else {}
    artifact_keys = {
        "llmRaw": "llm_raw.json",
        "gameplayRepairRawPatch": "gameplay_repair.json",
        "visualRepairRawPatch": "visual_repair.json",
        "vfxRepairRawPatch": "vfx_repair.json",
    }
    for key, filename in artifact_keys.items():
        if key in debug:
            _save_json(case_dir / filename, debug[key])


def save_case(args: argparse.Namespace) -> int:
    case_dir = _case_dir(str(args.case_id), create=True)
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
    _save_json(case_dir / "parents.json", parents)

    from infini_local.pipelines.combine_pipeline import combine

    started = time.monotonic()
    try:
        result = combine(parents)
        _strict_wire(result)
    except Exception as exc:
        _save_json(
            case_dir / "combine_error.json",
            {"error": repr(exc), "type": type(exc).__name__},
        )
        print(f"ERROR: combine failed: {exc}")
        return 1
    _save_json(case_dir / "final_item.json", result)
    _save_json(case_dir / "compiled_runtime.json", _snapshot_for(result))
    _save_debug_artifacts(case_dir, result)
    print(
        json.dumps(
            {
                "ok": True,
                "caseDir": str(case_dir),
                "elapsedMs": int((time.monotonic() - started) * 1000),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _rerun_case(case_dir: Path, replay_raw: str | None) -> dict[str, Any]:
    parents = _load_json_required(case_dir / "parents.json")
    if not isinstance(parents, dict):
        raise TypeError("parents.json must contain an object accepted by combine()")
    raw_path = Path(replay_raw) if replay_raw else case_dir / "llm_raw.json"
    if not raw_path.exists():
        raise FileNotFoundError("rerun requires --replay-raw or llm_raw.json")

    old_env = dict(os.environ)
    try:
        with tempfile.TemporaryDirectory(prefix="infini-v5-replay-") as temp_root:
            os.environ["INFINI_LLM_REPLAY_RAW"] = str(raw_path.resolve())
            os.environ["INFINI_CACHE_DIR"] = str(Path(temp_root) / "cache")
            os.environ["INFINI_WORLD_RECIPES_DIR"] = str(
                Path(temp_root) / "world_recipes"
            )
            os.environ["INFINI_TRACE_PROMPTS"] = "0"
            from infini_local.pipelines.combine_pipeline import combine

            result = combine(parents)
            _strict_wire(result)
            return result
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def build_replay_report(
    case_dir: Path,
    *,
    compare: bool,
    rerun: bool,
    replay_raw: str | None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    differences: list[dict[str, Any]] = []
    try:
        item = _load_json_required(case_dir / "final_item.json")
        item, _ = _strict_wire(item)
        current_snapshot = _snapshot_for(item)
        checks.extend(
            [
                {"name": "final_wire", "status": "passed"},
                {"name": "delivery_wire", "status": "passed"},
            ]
        )
    except Exception as exc:
        return {
            "schema": REPORT_SCHEMA,
            "caseDir": str(case_dir),
            "ok": False,
            "checks": [
                {"name": "strict_wire", "status": "failed", "error": repr(exc)}
            ],
            "differences": [],
        }

    if compare:
        try:
            expected = _load_json_required(case_dir / "compiled_runtime.json")
            if not isinstance(expected, dict) or expected.get("schema") != SNAPSHOT_SCHEMA:
                raise ValueError(f"compiled_runtime.json must use {SNAPSHOT_SCHEMA}")
            _semantic_diff("wire", expected.get("wire"), current_snapshot["wire"], differences)
            if expected.get("sha256") != current_snapshot["sha256"]:
                differences.append(
                    {
                        "path": "sha256",
                        "expected": expected.get("sha256"),
                        "actual": current_snapshot["sha256"],
                    }
                )
            checks.append(
                {
                    "name": "saved_snapshot",
                    "status": "passed" if not differences else "failed",
                    "differenceCount": len(differences),
                }
            )
        except Exception as exc:
            checks.append(
                {"name": "saved_snapshot", "status": "failed", "error": repr(exc)}
            )

    if rerun:
        try:
            rerun_item = _rerun_case(case_dir, replay_raw)
            rerun_differences: list[dict[str, Any]] = []
            _semantic_diff(
                "wire",
                current_snapshot["wire"],
                _snapshot_for(rerun_item)["wire"],
                rerun_differences,
            )
            differences.extend(rerun_differences)
            checks.append(
                {
                    "name": "full_pipeline_rerun",
                    "status": "passed" if not rerun_differences else "failed",
                    "differenceCount": len(rerun_differences),
                }
            )
        except Exception as exc:
            checks.append(
                {
                    "name": "full_pipeline_rerun",
                    "status": "failed",
                    "error": repr(exc),
                }
            )

    return {
        "schema": REPORT_SCHEMA,
        "caseDir": str(case_dir),
        "ok": all(row.get("status") == "passed" for row in checks),
        "checks": checks,
        "differences": differences[:200],
        "compare": compare,
        "rerun": rerun,
    }


def replay_case(args: argparse.Namespace) -> int:
    case_dir = _case_dir(str(args.case_id))
    if not case_dir.exists():
        print(f"ERROR: case not found at {case_dir}")
        return 1
    report = build_replay_report(
        case_dir,
        compare=bool(args.compare or args.strict),
        rerun=bool(args.rerun),
        replay_raw=args.replay_raw,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["ok"] else 1


def list_cases(_: argparse.Namespace) -> int:
    root = _replay_root()
    if not root.exists():
        print("No replay cases saved yet.")
        return 0
    cases = sorted(path for path in root.iterdir() if path.is_dir())
    if not cases:
        print("No replay cases found.")
        return 0
    for case in cases:
        print(f"{case.name}\t{len(list(case.glob('*.json')))} artifacts")
    return 0


def show_case(args: argparse.Namespace) -> int:
    path = _case_dir(str(args.case_id)) / str(args.artifact)
    if not path.exists():
        print(f"ERROR: artifact not found: {path}")
        return 1
    print(json.dumps(_load_json_required(path), ensure_ascii=False, indent=2, default=str))
    return 0


def command_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="runtimeProgram v5 replay harness")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    save_parser = subparsers.add_parser("save")
    save_parser.add_argument("case_id")
    save_parser.add_argument("--itemA")
    save_parser.add_argument("--itemB")
    save_parser.add_argument("--parents-json")
    save_parser.add_argument("--world-id", default="")
    save_parser.set_defaults(func=save_case)

    replay_parser = subparsers.add_parser("replay")
    replay_parser.add_argument("case_id")
    replay_parser.add_argument("--strict", action="store_true")
    replay_parser.add_argument("--compare", action="store_true")
    replay_parser.add_argument("--rerun", action="store_true")
    replay_parser.add_argument("--replay-raw")
    replay_parser.add_argument("--out")
    replay_parser.set_defaults(func=replay_case)

    list_parser = subparsers.add_parser("list")
    list_parser.set_defaults(func=list_cases)

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("case_id")
    show_parser.add_argument("artifact")
    show_parser.set_defaults(func=show_case)

    args = parser.parse_args(argv)
    return int(args.func(args))


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        return command_main(["--help"])
    if values[0] in {"save", "replay", "list", "show"}:
        return command_main(values)
    if values[0] == "summary":
        return summary_main(values[1:])
    return summary_main(values)


if __name__ == "__main__":
    raise SystemExit(main())
