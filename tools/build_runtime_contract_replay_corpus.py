#!/usr/bin/env python3
"""Build a compact historical finalContract runtimePlan replay corpus.

Scans image_boundary.ndjson dumps, keeps executable runtimePlan wire only
(no names/tooltips/concept/prose), retains typed Author function provenance
separately, dedupes by canonical plan + authored inventory, selects a
representative set covering every observed function and distinct call-shape,
and stores expected final-sections fingerprints via production compile.

No LLM, no HTTP. Mechanical accepted-wire corpus only.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCAL_GENERATOR = ROOT / "LocalGenerator"
if str(LOCAL_GENERATOR) not in sys.path:
    sys.path.insert(0, str(LOCAL_GENERATOR))

from infini_local.qa.runtime_contract_replay import (  # noqa: E402
    CORPUS_SCHEMA,
    authored_function_forms_from_runtime_plan,
    authored_functions_from_runtime_plan,
    call_shapes_from_plan,
    canonical_json,
    default_corpus_path,
    deterministic_contract_witness_candidates,
    executable_runtime_plan_from_dump,
    functions_from_runtime_plan,
    make_case_id,
    normalized_functions_from_runtime_plan,
    replay_case,
    stable_final_sections_fingerprint,
)
from infini_local.core.runtime_authoring.function_contract_registry import (  # noqa: E402
    ENGINE_FUNCTION_CONTRACT_BY_NAME,
)
from infini_local.core.runtime_authoring.final_projection import (  # noqa: E402
    compile_runtime_plan_to_final_result,
)
from infini_local.qa.runtime_contract_replay import compile_input_from_case  # noqa: E402

DEFAULT_DUMP_ROOT = ROOT.parent / "artifacts" / "tool-runs"


def _iter_image_boundary_rows(dump_root: Path) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    if not dump_root.is_dir():
        return rows
    paths = sorted(dump_root.rglob("image_boundary.ndjson"))
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not text.strip():
            continue
        # sourceRun = immediate tool-run folder name (or nested leaf parent).
        try:
            rel = path.relative_to(dump_root)
            source_run = rel.parts[0] if rel.parts else path.parent.name
        except ValueError:
            source_run = path.parent.name
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            rows.append((source_run, row))
    return rows


def _extract_candidate(
    source_run: str,
    row: dict[str, Any],
) -> dict[str, Any] | None:
    final_contract = row.get("finalContract")
    if not isinstance(final_contract, dict):
        return None
    runtime_plan = final_contract.get("runtimePlan")
    if not isinstance(runtime_plan, dict):
        return None
    engine_calls = runtime_plan.get("engineCalls")
    if not isinstance(engine_calls, list) or not engine_calls:
        return None

    plan = executable_runtime_plan_from_dump(runtime_plan)
    if not plan.get("engineCalls"):
        return None
    functions = sorted(functions_from_runtime_plan(plan))
    if not functions:
        return None
    authored_functions = sorted(authored_functions_from_runtime_plan(runtime_plan))
    authored_forms = sorted(
        f"{fn}:{path}"
        for fn, path in authored_function_forms_from_runtime_plan(runtime_plan)
    )

    case_name = row.get("case")
    if case_name is None or case_name == "":
        case_name = row.get("itemId") or "unknown"
    category = row.get("category") or final_contract.get("category") or plan.get("resultKind")
    result_kind = plan.get("resultKind") or final_contract.get("category") or category
    plan_key = canonical_json(
        {
            "runtimePlan": plan,
            "authoredFunctions": authored_functions,
            "authoredForms": authored_forms,
        }
    )
    case_id = make_case_id(str(source_run), str(case_name), plan_key)

    return {
        "caseId": case_id,
        "sourceRun": str(source_run),
        "case": str(case_name),
        "category": str(category) if category is not None else None,
        "resultKind": str(result_kind) if result_kind is not None else None,
        "functions": functions,
        "authoredFunctions": authored_functions,
        "authoredForms": authored_forms,
        "runtimePlan": plan,
        "_planKey": plan_key,
        "_shapes": call_shapes_from_plan(plan),
    }


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep first occurrence per canonical executable runtimePlan (sorted inputs)."""
    ordered = sorted(
        candidates,
        key=lambda c: (
            str(c.get("sourceRun") or ""),
            str(c.get("case") or ""),
            str(c.get("_planKey") or ""),
        ),
    )
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for cand in ordered:
        key = str(cand.get("_planKey") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(cand)
    return unique


def _select_representative(
    unique: list[dict[str, Any]],
    *,
    max_cases: int | None,
) -> list[dict[str, Any]]:
    """Greedy cover: every observed function/form + call-shape + kind."""
    all_fns: set[str] = set()
    all_shapes: set[tuple[str, tuple[str, ...]]] = set()
    all_authored_forms: set[str] = set()
    all_kinds: set[str] = set()
    for cand in unique:
        all_fns.update(cand["functions"])
        all_fns.update(cand.get("authoredFunctions") or [])
        all_shapes.update(cand["_shapes"])
        all_authored_forms.update(cand.get("authoredForms") or [])
        rk = str(cand.get("resultKind") or "")
        if rk:
            all_kinds.add(rk)

    remaining = list(unique)
    selected: list[dict[str, Any]] = []
    cov_fn: set[str] = set()
    cov_shape: set[tuple[str, tuple[str, ...]]] = set()
    cov_authored_form: set[str] = set()
    cov_kind: set[str] = set()

    def novelty(cand: dict[str, Any]) -> tuple[int, int, str]:
        candidate_functions = set(cand["functions"]) | set(cand.get("authoredFunctions") or [])
        new_fn = len(candidate_functions - cov_fn)
        new_shape = len(set(cand["_shapes"]) - cov_shape)
        new_authored_form = len(set(cand.get("authoredForms") or []) - cov_authored_form)
        rk = str(cand.get("resultKind") or "")
        new_kind = 1 if rk and rk not in cov_kind else 0
        # Prefer higher novelty; tie-break by shorter plan then stable key.
        plan_len = len(cand.get("runtimePlan", {}).get("engineCalls") or [])
        return (
            new_fn * 1000 + new_authored_form * 100 + new_shape * 10 + new_kind,
            -plan_len,
            str(cand.get("_planKey") or ""),
        )

    # Pass 1: cover until no more novelty (or max).
    while remaining:
        if max_cases is not None and len(selected) >= max_cases:
            break
        scored = sorted(
            ((novelty(c), i, c) for i, c in enumerate(remaining)),
            key=lambda row: (-row[0][0], row[0][1], row[0][2], row[2]["caseId"]),
        )
        score, index, cand = scored[0]
        if score[0] <= 0:
            break
        selected.append(cand)
        remaining.pop(index)
        cov_fn.update(cand["functions"])
        cov_fn.update(cand.get("authoredFunctions") or [])
        cov_shape.update(cand["_shapes"])
        cov_authored_form.update(cand.get("authoredForms") or [])
        rk = str(cand.get("resultKind") or "")
        if rk:
            cov_kind.add(rk)
        if (
            cov_fn == all_fns
            and cov_authored_form == all_authored_forms
            and cov_shape == all_shapes
            and cov_kind == all_kinds
        ):
            break

    # If max_cases is None or generous, keep full unique when small enough.
    if max_cases is None:
        # Prefer full unique when it is not huge; still ensure cover is included.
        if len(unique) <= 120:
            selected = list(unique)
        else:
            # Keep cover only when full set is large.
            pass
    elif max_cases >= len(unique):
        selected = list(unique)

    # Deterministic final order by caseId.
    selected_by_id = {c["caseId"]: c for c in selected}
    return [selected_by_id[k] for k in sorted(selected_by_id)]


def _attach_fingerprints(cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    compiled = 0
    failed = 0
    errors: Counter[str] = Counter()
    out: list[dict[str, Any]] = []
    for cand in cases:
        case = {
            "caseId": cand["caseId"],
            "sourceRun": cand["sourceRun"],
            "case": cand["case"],
            "category": cand.get("category"),
            "resultKind": cand.get("resultKind"),
            "functions": list(cand["functions"]),
            "runtimePlan": cand["runtimePlan"],
        }
        if cand.get("authoredFunctions"):
            case["authoredFunctions"] = list(cand["authoredFunctions"])
        if cand.get("authoredForms"):
            case["authoredForms"] = list(cand["authoredForms"])
        try:
            data = compile_input_from_case(case)
            result = compile_runtime_plan_to_final_result(data)
            fp = stable_final_sections_fingerprint(result)
            case["expectedFinalSectionsFingerprint"] = fp
            # Sanity: replay_case agrees.
            report = replay_case(case)
            if not report.get("ok"):
                failed += 1
                errors[str(report.get("error") or "replay_not_ok")] += 1
            else:
                compiled += 1
            out.append(case)
        except Exception as exc:  # noqa: BLE001 - builder must continue
            failed += 1
            errors[f"{type(exc).__name__}: {exc}"] += 1
            # Still keep case without fingerprint only if we want — tests require fingerprint
            # for cases that compile. Skip non-compiling cases from committed corpus.
            continue
    stats = {
        "compiled": compiled,
        "failed": failed,
        "errors": dict(errors),
    }
    return out, stats


def build_corpus(
    dump_root: Path,
    *,
    max_cases: int | None = 96,
) -> dict[str, Any]:
    raw_rows = _iter_image_boundary_rows(dump_root)
    candidates: list[dict[str, Any]] = []
    for source_run, row in raw_rows:
        cand = _extract_candidate(source_run, row)
        if cand is not None:
            candidates.append(cand)

    historical_candidate_count = len(candidates)
    witnesses = deterministic_contract_witness_candidates()
    candidates.extend(witnesses)

    unique = _dedupe_candidates(candidates)
    selected = _select_representative(unique, max_cases=max_cases)
    cases, compile_stats = _attach_fingerprints(selected)

    stored_fns = sorted({fn for case in cases for fn in case["functions"]})
    normalized_fns = sorted(
        {
            fn
            for case in cases
            for fn in normalized_functions_from_runtime_plan(case["runtimePlan"])
        }
    )
    authored_fns = sorted(
        {
            fn
            for case in cases
            for fn in (case.get("authoredFunctions") or [])
        }
    )
    authored_forms = sorted(
        {
            form
            for case in cases
            for form in (case.get("authoredForms") or [])
        }
    )
    effective_fns = sorted(set(stored_fns) | set(normalized_fns) | set(authored_fns))
    registry_fns = sorted(ENGINE_FUNCTION_CONTRACT_BY_NAME)
    all_shapes: set[str] = set()
    for case in cases:
        for fn, keys in call_shapes_from_plan(case["runtimePlan"]):
            all_shapes.add(f"{fn}::{','.join(keys)}")

    lowerer_functions = {
        name
        for name, spec in ENGINE_FUNCTION_CONTRACT_BY_NAME.items()
        if spec.lowerers
    }
    coverage = {
        "caseCount": len(cases),
        "uniquePlanCount": len(unique),
        "rawRowCount": historical_candidate_count,
        "deterministicWitnessCount": len(witnesses),
        # Legacy keys remain normalized-runtime coverage for v1 readers.
        "functions": stored_fns,
        "functionCount": len(stored_fns),
        "normalizedFunctions": normalized_fns,
        "normalizedFunctionCount": len(normalized_fns),
        "authoredFunctions": authored_fns,
        "authoredFunctionCount": len(authored_fns),
        "authoredForms": authored_forms,
        "authoredFormCount": len(authored_forms),
        "authoredFunctionInventoryAvailable": lowerer_functions <= set(authored_fns),
        "effectiveFunctions": effective_fns,
        "effectiveFunctionCount": len(effective_fns),
        "registryFunctions": registry_fns,
        "registryFunctionCount": len(registry_fns),
        "missingRegistryFunctions": sorted(set(registry_fns) - set(effective_fns)),
        "callShapeCount": len(all_shapes),
        "resultKinds": sorted(
            {str(case.get("resultKind") or "") for case in cases if case.get("resultKind")}
        ),
        "compile": compile_stats,
    }

    try:
        dump_root_label = dump_root.resolve().relative_to(ROOT.parent.resolve()).as_posix()
    except ValueError:
        # External rebuilds commonly use a random temporary directory.  Persisting
        # that basename makes a byte-identical corpus dirty on every rebuild.
        dump_root_label = "external-tool-runs"
    corpus = {
        "schema": CORPUS_SCHEMA,
        "source": {
            "dumpRoot": dump_root_label,
            "glob": "**/image_boundary.ndjson",
            "selector": (
                "function+authoredForm+callShape+resultKind cover; "
                "dedupe by canonical runtimePlan+authored provenance"
            ),
        },
        "coverage": coverage,
        "cases": sorted(cases, key=lambda c: str(c["caseId"])),
    }
    return corpus


def write_corpus(corpus: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(corpus, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    out_path.write_text(text, encoding="utf-8")
    # Sidecar coverage report for humans / CI logs.
    coverage_path = out_path.parent / "coverage.json"
    coverage_path.write_text(
        json.dumps(corpus.get("coverage") or {}, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dump-root",
        type=Path,
        default=DEFAULT_DUMP_ROOT,
        help="Root directory containing **/image_boundary.ndjson dumps",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=default_corpus_path(),
        help="Output corpus.json path",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=96,
        help="Max cases in committed corpus (cover-first). 0 = all unique if <=120 else cover-only",
    )
    args = parser.parse_args(argv)

    max_cases: int | None
    if args.max_cases == 0:
        max_cases = None
    else:
        max_cases = int(args.max_cases)

    corpus = build_corpus(args.dump_root, max_cases=max_cases)
    write_corpus(corpus, args.out)
    coverage = corpus.get("coverage") or {}
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "caseCount": coverage.get("caseCount"),
                "functionCount": coverage.get("functionCount"),
                "functions": coverage.get("functions"),
                "callShapeCount": coverage.get("callShapeCount"),
                "uniquePlanCount": coverage.get("uniquePlanCount"),
                "compile": coverage.get("compile"),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
