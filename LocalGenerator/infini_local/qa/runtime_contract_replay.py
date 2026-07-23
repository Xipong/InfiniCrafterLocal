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
from infini_local.core.runtime_authoring.function_contract_registry import (
    ENGINE_FUNCTION_CONTRACT_BY_NAME,
    engine_function_form_impacts,
    engine_function_impact_names,
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


def _normalize_function_name(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


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
        fn = _normalize_function_name(call.get("fn"))
        if fn:
            out.add(fn)
    return frozenset(out)


def authored_functions_from_runtime_plan(
    runtime_plan: Mapping[str, Any] | None,
) -> frozenset[str]:
    """Recover typed Author function provenance when a dump preserved it."""

    if not isinstance(runtime_plan, Mapping):
        return frozenset()
    calls = runtime_plan.get("engineCalls")
    if not isinstance(calls, list):
        return frozenset()
    out: set[str] = set()
    for call in calls:
        if not isinstance(call, Mapping):
            continue
        authored = _normalize_function_name(call.get("_rawFn") or call.get("authoredFn"))
        if authored:
            out.add(authored)
    return frozenset(out)


def _iter_param_paths(params: Mapping[str, Any]) -> frozenset[str]:
    """Return top-level and nested object paths present in one call."""

    out: set[str] = set()
    pending: list[tuple[str, Any]] = [
        (str(key), value) for key, value in params.items() if not str(key).startswith("_")
    ]
    while pending:
        path, value = pending.pop(0)
        out.add(path)
        if isinstance(value, Mapping):
            pending[0:0] = [
                (f"{path}.{child}", child_value)
                for child, child_value in value.items()
                if not str(child).startswith("_")
            ]
    return frozenset(out)


def function_forms_from_runtime_plan(
    runtime_plan: Mapping[str, Any] | None,
) -> frozenset[tuple[str, str]]:
    """Return normalized function identity and exact present parameter forms."""

    if not isinstance(runtime_plan, Mapping):
        return frozenset()
    calls = runtime_plan.get("engineCalls")
    if not isinstance(calls, list):
        return frozenset()
    out: set[tuple[str, str]] = set()
    for call in calls:
        if not isinstance(call, Mapping):
            continue
        fn = _normalize_function_name(call.get("fn"))
        if not fn:
            continue
        out.add((fn, "$function"))
        params = call.get("params")
        if isinstance(params, Mapping):
            out.update((fn, path) for path in _iter_param_paths(params))
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


def case_authored_function_set(case: Mapping[str, Any]) -> frozenset[str]:
    """Typed Author function inventory, if retained by the corpus builder."""

    plan = case.get("runtimePlan") if isinstance(case.get("runtimePlan"), Mapping) else {}
    from_plan = authored_functions_from_runtime_plan(plan if isinstance(plan, Mapping) else {})
    listed = case.get("authoredFunctions")
    listed_set = (
        frozenset(_normalize_function_name(fn) for fn in listed if _normalize_function_name(fn))
        if isinstance(listed, list)
        else frozenset()
    )
    return from_plan or listed_set


def case_impact_function_set(case: Mapping[str, Any]) -> frozenset[str]:
    """All normalized and authored function identities represented by a case."""

    return case_function_set(case) | case_authored_function_set(case)


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
    - a provenance-aware corpus selects specialized typed lowerers by exact
      ``authoredFunctions`` identity
    - a legacy corpus without authored provenance conservatively maps a typed
      lowerer to its canonical normalized executor
    - unknown or uncovered functions raise instead of returning false-green empty
      selections
    - each case appears at most once; order is deterministic by caseId
    """
    cases_raw = corpus.get("cases")
    cases: list[dict[str, Any]] = [
        dict(case) for case in cases_raw if isinstance(case, Mapping)
    ] if isinstance(cases_raw, list) else []

    if changed_functions is None:
        selected = cases
    else:
        changed = {
            _normalize_function_name(fn)
            for fn in changed_functions
            if _normalize_function_name(fn)
        }
        if not changed:
            selected = cases
        else:
            unknown = sorted(fn for fn in changed if fn not in ENGINE_FUNCTION_CONTRACT_BY_NAME)
            if unknown:
                raise ValueError(f"unknown changed engine functions: {unknown}")

            coverage = corpus.get("coverage")
            coverage = coverage if isinstance(coverage, Mapping) else {}
            authored_inventory_available = bool(
                coverage.get("authoredFunctionInventoryAvailable")
            )
            selected_by_id: dict[str, dict[str, Any]] = {}
            uncovered: list[str] = []
            for fn in sorted(changed):
                spec = ENGINE_FUNCTION_CONTRACT_BY_NAME[fn]
                if spec.lowerers and authored_inventory_available:
                    # New corpora retain exact typed Author identity.  Falling back
                    # to every normalized shoot_projectile case here would hide a
                    # missing typed-family fixture behind unrelated executor cases.
                    matches = [
                        case for case in cases
                        if fn in case_authored_function_set(case)
                    ]
                else:
                    impacted = engine_function_impact_names(fn)
                    matches = [
                        case for case in cases
                        if case_impact_function_set(case).intersection(impacted)
                    ]
                if not matches:
                    uncovered.append(fn)
                    continue
                for case in matches:
                    case_id = str(case.get("caseId") or "")
                    selected_by_id[case_id] = case

            if uncovered:
                raise ValueError(
                    "historical replay corpus has no coverage for changed engine functions: "
                    f"{uncovered}"
                )
            selected = list(selected_by_id.values())

    selected.sort(key=lambda case: str(case.get("caseId") or ""))
    return selected


def select_cases_by_changed_forms(
    corpus: Mapping[str, Any],
    changed_forms: Iterable[str] | None,
) -> list[dict[str, Any]]:
    """Select exact ``function:param.path`` impacts and fail closed on gaps.

    Typed source forms are lowered through ``engine_function_form_impacts``.  Legacy
    corpus rows therefore remain selectable without a hand-written source/target map.
    Empty/None forms mean full replay, matching the changed-function selector.
    """

    cases_raw = corpus.get("cases")
    cases: list[dict[str, Any]] = [
        dict(case) for case in cases_raw if isinstance(case, Mapping)
    ] if isinstance(cases_raw, list) else []
    if changed_forms is None:
        return sorted(cases, key=lambda case: str(case.get("caseId") or ""))

    raw_forms = [str(form or "").strip() for form in changed_forms if str(form or "").strip()]
    if not raw_forms:
        return sorted(cases, key=lambda case: str(case.get("caseId") or ""))

    case_forms = {
        str(case.get("caseId") or ""): function_forms_from_runtime_plan(
            case.get("runtimePlan") if isinstance(case.get("runtimePlan"), Mapping) else {}
        )
        for case in cases
    }
    selected_by_id: dict[str, dict[str, Any]] = {}
    uncovered: list[str] = []
    for raw_form in sorted(set(raw_forms)):
        if ":" not in raw_form:
            raise ValueError(
                f"changed form must use 'function:param.path' syntax: {raw_form!r}"
            )
        raw_fn, raw_path = raw_form.split(":", 1)
        fn = _normalize_function_name(raw_fn)
        path = raw_path.strip()
        if fn not in ENGINE_FUNCTION_CONTRACT_BY_NAME:
            raise ValueError(f"unknown changed engine function in form: {fn!r}")
        impacts = engine_function_form_impacts(fn, path)
        if not impacts:
            raise ValueError(f"unknown or unbound changed engine form: {fn}:{path}")
        matches = [
            case
            for case in cases
            if case_forms[str(case.get("caseId") or "")].intersection(impacts)
        ]
        if not matches:
            uncovered.append(f"{fn}:{path}")
            continue
        for case in matches:
            selected_by_id[str(case.get("caseId") or "")] = case

    if uncovered:
        raise ValueError(
            "historical replay corpus has no coverage for changed engine forms: "
            f"{uncovered}"
        )
    return sorted(selected_by_id.values(), key=lambda case: str(case.get("caseId") or ""))


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
    "case_authored_function_set",
    "case_function_set",
    "case_impact_function_set",
    "compile_input_from_case",
    "corpus_function_set",
    "default_corpus_path",
    "executable_runtime_plan_from_dump",
    "authored_functions_from_runtime_plan",
    "functions_from_runtime_plan",
    "function_forms_from_runtime_plan",
    "load_corpus",
    "make_case_id",
    "replay_case",
    "replay_cases",
    "select_cases_by_changed_functions",
    "select_cases_by_changed_forms",
    "stable_final_sections_fingerprint",
]
