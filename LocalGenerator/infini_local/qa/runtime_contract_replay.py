"""Historical finalContract runtimePlan replay + impact selector.

Load a dump-backed corpus of accepted executable runtimePlans, select cases by
changed engine functions, and replay production compile/final projection.

No LLM, no HTTP, no image backend. Mechanical accepted-wire replay only.
Does not duplicate semantic validation — production compile path owns that.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from infini_local.core.runtime_authoring.final_projection import (
    compile_runtime_plan_to_final_result,
)

CORPUS_SCHEMA = "infini.runtime-contract-replay-corpus.v1"
DEFAULT_CORPUS_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "runtime_contract_history"
    / "corpus.json"
)

# Presentation / free-text fields stripped from historical dumps.
PROSE_RUNTIME_PLAN_KEYS = frozenset(
    {
        "visualIntent",
        "sourceReading",
        "sourceRolePreservation",
        "balanceIntent",
        "runtimeStateIntent",
    }
)


def canonical_json(value: Any) -> str:
    """Deterministic JSON for fingerprints and dedupe keys."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _safe_token(value: object) -> str:
    raw = str(value or "").strip().lower()
    token = re.sub(r"[^a-z0-9_.-]+", "_", raw).strip("._-")
    return token or "unknown"


def default_corpus_path() -> Path:
    return DEFAULT_CORPUS_PATH


def load_corpus(path: str | Path | None = None) -> dict[str, Any]:
    """Load the committed historical replay corpus."""
    corpus_path = Path(path) if path is not None else DEFAULT_CORPUS_PATH
    payload = json.loads(corpus_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("corpus root must be an object")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("corpus.cases must be a list")
    return payload


def functions_from_runtime_plan(runtime_plan: Mapping[str, Any] | None) -> frozenset[str]:
    """Return the engine function set from an executable runtimePlan."""
    if not isinstance(runtime_plan, Mapping):
        return frozenset()
    calls = runtime_plan.get("engineCalls")
    if not isinstance(calls, list):
        return frozenset()
    out: set[str] = set()
    for call in calls:
        if not isinstance(call, Mapping):
            continue
        fn = str(call.get("fn") or "").strip()
        if fn:
            out.add(fn)
    return frozenset(out)


def case_function_set(case: Mapping[str, Any]) -> frozenset[str]:
    """Function inventory for one corpus case (authoritative: engineCalls)."""
    plan = case.get("runtimePlan") if isinstance(case.get("runtimePlan"), Mapping) else {}
    from_plan = functions_from_runtime_plan(plan if isinstance(plan, Mapping) else {})
    listed = case.get("functions")
    if isinstance(listed, list) and listed:
        listed_set = frozenset(str(fn).strip() for fn in listed if str(fn).strip())
        if listed_set != from_plan:
            # Prefer executable calls; listed field is a cache that must match.
            return from_plan
        return listed_set
    return from_plan


def corpus_function_set(corpus: Mapping[str, Any]) -> frozenset[str]:
    """Union of all engine functions present in the corpus."""
    cases = corpus.get("cases")
    if not isinstance(cases, list):
        return frozenset()
    out: set[str] = set()
    for case in cases:
        if isinstance(case, Mapping):
            out |= set(case_function_set(case))
    return frozenset(out)


def select_cases_by_changed_functions(
    corpus: Mapping[str, Any],
    changed_functions: Iterable[str] | None,
) -> list[dict[str, Any]]:
    """Select corpus cases impacted by changed engine functions.

    - empty / None changed set → all cases (full regression)
    - non-empty → union of cases whose function set intersects the changed set
    - each case appears at most once
    - order is deterministic by caseId
    """
    cases_raw = corpus.get("cases")
    cases: list[dict[str, Any]] = [
        dict(case) for case in cases_raw if isinstance(case, Mapping)
    ] if isinstance(cases_raw, list) else []

    if changed_functions is None:
        selected = cases
    else:
        changed = {str(fn).strip() for fn in changed_functions if str(fn).strip()}
        if not changed:
            selected = cases
        else:
            selected = [
                case
                for case in cases
                if case_function_set(case).intersection(changed)
            ]

    selected.sort(key=lambda case: str(case.get("caseId") or ""))
    return selected


def stable_final_sections_fingerprint(compile_result: Mapping[str, Any]) -> str:
    """Stable fingerprint of compiler-owned final sections (+ identity)."""
    payload = {
        "identity": compile_result.get("identity"),
        "finalSections": compile_result.get("finalSections"),
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return digest


def compile_input_from_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Build the minimal production compile input from a corpus case."""
    plan = case.get("runtimePlan")
    if not isinstance(plan, Mapping):
        raise ValueError("case.runtimePlan must be an object")
    runtime_plan = copy.deepcopy(dict(plan))
    # Defensive strip if an older dump leaked prose keys.
    for key in PROSE_RUNTIME_PLAN_KEYS:
        runtime_plan.pop(key, None)
    category = case.get("category") or case.get("resultKind") or runtime_plan.get("resultKind")
    data: dict[str, Any] = {
        "category": category,
        "runtimePlan": runtime_plan,
    }
    return data


def replay_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Replay one historical case through production final projection compile.

    Uses compile_runtime_plan_to_final_result (production path). No network.
    """
    case_id = str(case.get("caseId") or _safe_token(case.get("case")))
    report: dict[str, Any] = {
        "caseId": case_id,
        "ok": False,
        "error": None,
        "fingerprint": None,
        "expectedFingerprint": case.get("expectedFinalSectionsFingerprint"),
        "result": None,
        "functions": sorted(case_function_set(case)),
    }
    try:
        data = compile_input_from_case(case)
        result = compile_runtime_plan_to_final_result(data)
        if not isinstance(result, dict):
            raise TypeError("compile_runtime_plan_to_final_result returned non-object")
        rejected = result.get("rejectedEngineCalls") or []
        if rejected:
            raise ValueError(f"production compiler returned rejected engine calls: {rejected}")
        receipts = result.get("finalWireReceipts") or []
        dropped = [
            row
            for row in receipts
            if isinstance(row, Mapping) and str(row.get("status") or "") == "dropped"
        ]
        if dropped:
            raise ValueError(f"production compiler returned dropped final-wire receipts: {dropped}")
        validation = result.get("validation")
        if isinstance(validation, Mapping) and validation.get("ok") is False:
            raise ValueError(f"production compiler validation failed: {dict(validation)}")
        fingerprint = stable_final_sections_fingerprint(result)
        report["fingerprint"] = fingerprint
        report["result"] = {
            "schema": result.get("schema"),
            "identity": copy.deepcopy(result.get("identity")),
            "finalSections": copy.deepcopy(result.get("finalSections")),
            "rejectedEngineCalls": copy.deepcopy(result.get("rejectedEngineCalls") or []),
            "finalWireReceipts": copy.deepcopy(result.get("finalWireReceipts") or []),
            "validation": copy.deepcopy(result.get("validation") or {}),
        }
        expected = case.get("expectedFinalSectionsFingerprint")
        if expected and fingerprint != expected:
            report["error"] = (
                f"fingerprint mismatch: got {fingerprint}, expected {expected}"
            )
            report["ok"] = False
        else:
            report["ok"] = True
    except Exception as exc:  # surface compile crashes as failed reports
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["ok"] = False
    return report


def replay_cases(cases: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Replay many cases; preserves input order."""
    return [replay_case(case) for case in cases]


def executable_runtime_plan_from_dump(runtime_plan: Mapping[str, Any]) -> dict[str, Any]:
    """Strip prose and internal keys; keep engineCalls + structural resultKind."""
    calls_out: list[dict[str, Any]] = []
    raw_calls = runtime_plan.get("engineCalls")
    if isinstance(raw_calls, list):
        for raw in raw_calls:
            if not isinstance(raw, Mapping):
                continue
            fn = str(raw.get("fn") or "").strip()
            if not fn:
                continue
            params_in = raw.get("params") if isinstance(raw.get("params"), Mapping) else {}
            params = {
                str(key): copy.deepcopy(value)
                for key, value in dict(params_in or {}).items()
                if not str(key).startswith("_")
            }
            call_id = str(raw.get("callId") or "").strip()
            if not call_id:
                continue
            calls_out.append({"callId": call_id, "fn": fn, "params": params})
    plan: dict[str, Any] = {
        "resultKind": runtime_plan.get("resultKind"),
        "engineCalls": calls_out,
    }
    # Optional structural (non-prose) metadata.
    flags = runtime_plan.get("anomalyFlags")
    if isinstance(flags, list) and flags:
        plan["anomalyFlags"] = copy.deepcopy(flags)
    return plan


def call_shapes_from_plan(runtime_plan: Mapping[str, Any]) -> list[tuple[str, tuple[str, ...]]]:
    """Accepted call-shapes: (fn, sorted param keys)."""
    shapes: list[tuple[str, tuple[str, ...]]] = []
    calls = runtime_plan.get("engineCalls")
    if not isinstance(calls, list):
        return shapes
    for call in calls:
        if not isinstance(call, Mapping):
            continue
        fn = str(call.get("fn") or "").strip()
        if not fn:
            continue
        params = call.get("params") if isinstance(call.get("params"), Mapping) else {}
        shapes.append((fn, tuple(sorted(str(k) for k in dict(params or {}).keys()))))
    return shapes


def make_case_id(source_run: str, case_name: str, plan_key: str) -> str:
    short = hashlib.sha256(plan_key.encode("utf-8")).hexdigest()[:10]
    base = f"{_safe_token(source_run)}__{_safe_token(case_name)}"
    return f"{base}__{short}"


__all__ = [
    "CORPUS_SCHEMA",
    "DEFAULT_CORPUS_PATH",
    "PROSE_RUNTIME_PLAN_KEYS",
    "call_shapes_from_plan",
    "canonical_json",
    "case_function_set",
    "compile_input_from_case",
    "corpus_function_set",
    "default_corpus_path",
    "executable_runtime_plan_from_dump",
    "functions_from_runtime_plan",
    "load_corpus",
    "make_case_id",
    "replay_case",
    "replay_cases",
    "select_cases_by_changed_functions",
    "stable_final_sections_fingerprint",
]
