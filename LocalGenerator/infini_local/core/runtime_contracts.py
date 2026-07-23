from __future__ import annotations

import re
import copy
from typing import Any

from infini_local.core.runtime_tooltip import compiled_runtime_tooltip
from infini_local.core.runtime_authoring.function_contract_registry import engine_param_wire_obligation
from infini_local.core.runtime_authoring.function_contract_types import WireObligation

STRUCTURAL_RUNTIME_CONTRACT_SCHEMA = "infini.runtime-contract.v3"
STRUCTURAL_ID_MAX_CHARS = 64
STRUCTURAL_ID_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
_STRUCTURAL_ID_RE = re.compile(STRUCTURAL_ID_PATTERN)
_FINAL_WIRE_ROOTS = {"gameplay", "attack", "accessory", "armor"}
CONTROL_STYLES = {"", "tap", "hold-to-channel", "right-click-alt", "combo", "passive", "toggle", "automatic", "on-hit-trigger"}
EXECUTION_STATUSES = {"", "executable", "partial", "visual_only", "unsupported"}
_FINAL_WIRE_RECEIPT_REQUIRED_KEYS = frozenset({
    "callId", "authoredParam", "authoredValue", "compiledField",
    "finalPath", "compiledValue", "status",
})
_FINAL_WIRE_RECEIPT_ALLOWED_KEYS = _FINAL_WIRE_RECEIPT_REQUIRED_KEYS | {"finalActual"}
_FINAL_WIRE_RECEIPT_STATUSES = frozenset({
    "active", "clamped", "normalized", "dropped", "mismatched",
})

def authored_param_requires_final_wire_provenance(fn: Any, authored_param: Any) -> bool:
    normalized_fn = str(fn or "").strip().lower().replace("-", "_").replace(" ", "_")
    param = str(authored_param or "").strip()
    if not normalized_fn or not param:
        return False
    obligation = engine_param_wire_obligation(normalized_fn, param)
    # Unknown surface is fail-closed; canonical non/future-wire obligations are
    # deliberately not required to manufacture a gameplay/attack DTO receipt.
    return obligation is None or obligation is WireObligation.FINAL_WIRE



def _text(value: Any, max_len: int = 160) -> str:
    if value in (None, ""):
        return ""
    return str(value).replace("\0", " ").strip()[:max_len]


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-").replace(" ", "-")


def _valid_receipt_value(value: Any, *, depth: int = 0) -> bool:
    if value is None or isinstance(value, (str, bool, int, float)):
        return True
    if depth >= 8:
        return False
    if isinstance(value, list):
        return len(value) <= 96 and all(
            _valid_receipt_value(child, depth=depth + 1)
            for child in value
        )
    if isinstance(value, dict):
        return len(value) <= 96 and all(
            isinstance(key, str)
            and _valid_receipt_value(child, depth=depth + 1)
            for key, child in value.items()
        )
    return False


def _valid_final_wire_receipt_shape(receipt: Any) -> bool:
    if not isinstance(receipt, dict):
        return False
    keys = frozenset(receipt)
    if not _FINAL_WIRE_RECEIPT_REQUIRED_KEYS.issubset(keys) or not keys.issubset(_FINAL_WIRE_RECEIPT_ALLOWED_KEYS):
        return False
    if not isinstance(receipt.get("callId"), str) or not _STRUCTURAL_ID_RE.fullmatch(receipt["callId"]):
        return False
    if not isinstance(receipt.get("authoredParam"), str) or not receipt["authoredParam"]:
        return False
    if not isinstance(receipt.get("compiledField"), str) or not receipt["compiledField"]:
        return False
    if not isinstance(receipt.get("finalPath"), str):
        return False
    if receipt.get("status") not in _FINAL_WIRE_RECEIPT_STATUSES:
        return False
    receipt_values = [receipt.get("authoredValue"), receipt.get("compiledValue")]
    if "finalActual" in receipt:
        receipt_values.append(receipt.get("finalActual"))
    return all(_valid_receipt_value(value) for value in receipt_values)


def _normalize_structural_timeline_step(raw: Any) -> dict[str, Any]:
    obj: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    return {
        "phase": _text(obj.get("phase"), 48),
        "description": _text(obj.get("description"), 240),
    }


def _normalize_structural_runtime_contract(obj: dict[str, Any]) -> dict[str, Any]:
    timeline_candidate = obj.get("playerViewTimeline")
    timeline_raw: list[Any] = timeline_candidate if isinstance(timeline_candidate, list) else []
    receipts_candidate = obj.get("finalWireReceipts")
    receipts_raw: list[Any] = receipts_candidate if isinstance(receipts_candidate, list) else []
    execution = _norm(obj.get("executionStatus")).replace("-", "_")
    if execution not in EXECUTION_STATUSES:
        execution = ""
    return {
        "schema": STRUCTURAL_RUNTIME_CONTRACT_SCHEMA,
        "primaryVerb": _text(obj.get("primaryVerb"), 120),
        "controlStyle": _norm(obj.get("controlStyle")),
        "playerViewTimeline": [_normalize_structural_timeline_step(step) for step in timeline_raw][:8],
        "finalWireReceipts": [
            dict(row)
            for row in receipts_raw
            if isinstance(row, dict)
        ][:96],
        "executionStatus": execution,
    }


def _backing_values_match(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return abs(float(actual) - float(expected)) <= 1e-6
    return actual == expected


def _nested_path_value(data: dict[str, Any], path: str) -> tuple[bool, Any]:
    parts = str(path or "").split(".")
    if not parts or any(not part for part in parts):
        return False, None
    current: Any = data
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _valid_final_wire_path(path: str) -> bool:
    parts = str(path or "").split(".")
    return (
        len(parts) >= 2
        and parts[0] in _FINAL_WIRE_ROOTS
        and all(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,95}", part) is not None for part in parts[1:])
    )


def _final_wire_value(data: dict[str, Any], path: str) -> tuple[bool, Any]:
    if not _valid_final_wire_path(path):
        return False, None
    return _nested_path_value(data, path)


def _authored_scalar_param_identities(calls: list[Any]) -> set[tuple[str, str]]:
    identities: set[tuple[str, str]] = set()
    for raw_call in calls:
        if not isinstance(raw_call, dict):
            continue
        call_id = str(raw_call.get("callId") or "").strip()
        fn = str(raw_call.get("fn") or "")
        params_candidate = raw_call.get("params")
        params: dict[str, Any] = params_candidate if isinstance(params_candidate, dict) else {}
        pending: list[tuple[str, Any]] = [(str(key), value) for key, value in params.items()]
        while pending:
            path, value = pending.pop(0)
            if isinstance(value, dict):
                pending[0:0] = [(f"{path}.{key}", child) for key, child in value.items()]
            elif isinstance(value, list):
                if value and authored_param_requires_final_wire_provenance(fn, path):
                    identities.add((call_id, path))
            elif (
                isinstance(value, (str, bool, int, float))
                and (not isinstance(value, str) or bool(value.strip()))
                and authored_param_requires_final_wire_provenance(fn, path)
            ):
                identities.add((call_id, path))
    return identities


def validate_structural_planner_contract(data: dict[str, Any]) -> dict[str, Any]:
    """Validate compact author metadata and structural engine-call identity.

    This is a source boundary, not a compiler stage.  It must therefore be pure:
    callers may run it more than once without turning an accepted AuthorItem into
    one that appears to contain model-authored compiler fields.
    """
    raw_candidate = data.get("runtimeContract")
    raw_contract: dict[str, Any] = dict(raw_candidate) if isinstance(raw_candidate, dict) else {}
    errors: list[dict[str, Any]] = []

    compiler_owned = {
        "schema", "mechanicClaims", "signatureMode", "signatureClaimId",
        "tooltipClaimIds", "unsupportedPromises", "executionStatus", "finalWireReceipts",
        "stateFields", "syncFields", "visualStateFields",
    }
    authored_compiler_fields = sorted(compiler_owned.intersection(raw_contract))
    if authored_compiler_fields:
        errors.append({"kind": "model_authored_compiler_fields", "fields": authored_compiler_fields})

    contract = _normalize_structural_runtime_contract(raw_contract)

    if not contract.get("primaryVerb"):
        errors.append({"kind": "missing_primary_verb"})
    control_style = str(contract.get("controlStyle") or "")
    if not control_style or control_style not in CONTROL_STYLES:
        errors.append({"kind": "invalid_control_style", "controlStyle": control_style})

    raw_timeline = raw_contract.get("playerViewTimeline")
    if raw_timeline is not None and not isinstance(raw_timeline, list):
        errors.append({"kind": "player_view_timeline_not_array"})
    elif isinstance(raw_timeline, list):
        if len(raw_timeline) > 8:
            errors.append({"kind": "player_view_timeline_too_long", "count": len(raw_timeline)})
        for step_index, step in enumerate(raw_timeline):
            if not isinstance(step, dict):
                errors.append({"kind": "timeline_step_not_object", "stepIndex": step_index})
                continue
            if not str(step.get("phase") or "").strip():
                errors.append({"kind": "timeline_step_missing_phase", "stepIndex": step_index})
            if not str(step.get("description") or "").strip():
                errors.append({"kind": "timeline_step_missing_description", "stepIndex": step_index})

    runtime_candidate = data.get("runtimePlan")
    runtime: dict[str, Any] = runtime_candidate if isinstance(runtime_candidate, dict) else {}
    calls_candidate = runtime.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    call_ids: set[str] = set()
    for index, raw_call in enumerate(calls):
        if not isinstance(raw_call, dict):
            errors.append({"kind": "engine_call_not_object", "callIndex": index})
            continue
        call_id = str(raw_call.get("callId") or "").strip()
        if not _STRUCTURAL_ID_RE.fullmatch(call_id):
            errors.append({"kind": "invalid_or_missing_call_id", "callIndex": index, "callId": call_id})
            continue
        if call_id in call_ids:
            errors.append({"kind": "duplicate_call_id", "callId": call_id})
            continue
        call_ids.add(call_id)

    return {
        "schema": "infini.structural-planner-contract-report.v2",
        "ok": not errors,
        "blockingClaims": errors,
        "unsupportedPromises": [],
    }


def structural_final_wire_report(data: dict[str, Any]) -> dict[str, Any]:
    """Pure report for compiler-owned authored-param receipts against the final DTO."""
    raw_candidate = data.get("runtimeContract")
    raw_contract: dict[str, Any] = dict(raw_candidate) if isinstance(raw_candidate, dict) else {}
    raw_receipts = raw_contract.get("finalWireReceipts")
    errors: list[dict[str, Any]] = []
    component_errors: dict[str, list[dict[str, Any]]] = {
        "receiptShape": [],
        "sourceIdentity": [],
        "finalProjection": [],
        "mechanic": [],
    }

    def reject(component: str, claim: dict[str, Any]) -> None:
        errors.append(claim)
        component_errors[component].append(claim)

    if not isinstance(raw_receipts, list):
        reject("receiptShape", {"kind": "malformed_final_wire_receipts"})
        raw_receipts = []
    elif any(not _valid_final_wire_receipt_shape(row) for row in raw_receipts):
        reject("receiptShape", {"kind": "malformed_final_wire_receipts"})

    contract = _normalize_structural_runtime_contract(raw_contract)
    runtime_candidate = data.get("runtimePlan")
    runtime: dict[str, Any] = runtime_candidate if isinstance(runtime_candidate, dict) else {}
    calls_candidate = runtime.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    calls_by_id: dict[str, dict[str, Any]] = {}
    for index, raw_call in enumerate(calls):
        if not isinstance(raw_call, dict):
            continue
        call_id = str(raw_call.get("callId") or "").strip()
        authored_index = raw_call.get("_index") if isinstance(raw_call.get("_index"), int) else index
        if not _STRUCTURAL_ID_RE.fullmatch(call_id):
            reject("sourceIdentity", {"kind": "invalid_or_missing_call_id", "callIndex": authored_index, "callId": call_id})
            continue
        if call_id in calls_by_id:
            reject("sourceIdentity", {"kind": "duplicate_call_id", "callId": call_id})
            continue
        calls_by_id[call_id] = raw_call

    receipt_identities = {
        (str(row.get("callId") or ""), str(row.get("authoredParam") or ""))
        for row in raw_receipts
        if _valid_final_wire_receipt_shape(row)
    }
    missing_receipts = sorted(_authored_scalar_param_identities(calls) - receipt_identities)
    for call_id, authored_param in missing_receipts:
        reject("sourceIdentity", {
            "kind": "compiler_provenance_receipt_missing",
            "callId": call_id,
            "authoredParam": authored_param,
        })

    verified_receipts: list[dict[str, Any]] = []
    for raw_receipt in raw_receipts:
        if not _valid_final_wire_receipt_shape(raw_receipt):
            continue
        receipt = dict(raw_receipt)
        call_id = str(receipt.get("callId") or "")
        authored_param = str(receipt.get("authoredParam") or "")
        authored_value = receipt.get("authoredValue")
        source_call = calls_by_id.get(call_id)
        params_candidate = source_call.get("params") if isinstance(source_call, dict) else None
        params: dict[str, Any] = params_candidate if isinstance(params_candidate, dict) else {}
        source_present, source_actual = _nested_path_value(params, authored_param)
        if not source_present or not _backing_values_match(source_actual, authored_value):
            reject("sourceIdentity", {"kind": "compiler_provenance_source_mismatch", **receipt})

        status = str(receipt.get("status") or "")
        final_path = str(receipt.get("finalPath") or "")
        if status == "dropped" or not final_path:
            receipt["finalActual"] = None
            reject("finalProjection", {"kind": "compiler_provenance_dropped", **receipt})
            verified_receipts.append(receipt)
            continue
        final_present, final_actual = _final_wire_value(data, final_path)
        receipt["finalActual"] = final_actual if final_present else None
        if not final_present:
            receipt["status"] = "dropped"
            reject("finalProjection", {"kind": "compiler_provenance_dropped", **receipt})
        elif not _backing_values_match(final_actual, receipt.get("compiledValue")):
            receipt["status"] = "mismatched"
            reject("finalProjection", {"kind": "compiler_provenance_mismatched", **receipt})
        elif status not in {"active", "clamped", "normalized"}:
            reject("finalProjection", {"kind": "compiler_provenance_invalid_status", **receipt})
        verified_receipts.append(receipt)

    concept_candidate = data.get("concept")
    concept: dict[str, Any] = concept_candidate if isinstance(concept_candidate, dict) else {}
    core_mechanic = str(concept.get("coreMechanic") or "").strip()
    if not core_mechanic:
        reject("mechanic", {"kind": "missing_core_mechanic"})
    contract["executionStatus"] = "executable" if not errors else "partial"
    contract["finalWireReceipts"] = verified_receipts
    return {
        "schema": "infini.final-wire-contract-report.v2",
        "ok": not errors,
        "blockingClaims": errors,
        "componentGates": {
            name: {"ok": not claims, "blockingClaims": claims}
            for name, claims in component_errors.items()
        },
        "finalWireReceipts": verified_receipts,
        "executionStatus": contract["executionStatus"],
        "contract": contract,
        "tooltip": compiled_runtime_tooltip(data) if not errors else "",
    }


def apply_structural_final_wire_contract(
    data: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    """Explicitly commit a previously computed structural final-wire report."""
    if str(report.get("schema") or "") != "infini.final-wire-contract-report.v2":
        raise ValueError("invalid structural final-wire report schema")
    contract = report.get("contract")
    if not isinstance(contract, dict):
        raise ValueError("structural final-wire report lacks contract")
    data["runtimeContract"] = copy.deepcopy(contract)
    if report.get("ok"):
        tooltip = str(report.get("tooltip") or "").strip()
        if not tooltip:
            raise ValueError("executable structural final-wire report lacks tooltip")
        data["tooltip"] = tooltip
    return report
