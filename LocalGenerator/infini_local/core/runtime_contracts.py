from __future__ import annotations

import re
from typing import Any

RUNTIME_CONTRACT_SCHEMA = "infini.runtime-contract.v2"
STRUCTURAL_RUNTIME_CONTRACT_SCHEMA = "infini.runtime-contract.v3"
_STRUCTURAL_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FINAL_WIRE_ROOTS = {"gameplay", "attack", "accessory", "armor"}
CONTROL_STYLES = {"", "tap", "hold-to-channel", "right-click-alt", "combo", "passive", "on-hit-trigger"}
EXECUTION_STATUSES = {"", "executable", "partial", "visual_only", "unsupported"}
EXECUTABLE_STATUS_ALIASES = {"active", "supported", "stable", "applied", "implemented", "complete", "completed"}
UNSUPPORTED_STATUS_ALIASES = {"future_disabled", "disabled", "not_supported"}


def _text(value: Any, max_len: int = 160) -> str:
    if value in (None, ""):
        return ""
    return str(value).replace("\0", " ").strip()[:max_len]


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-").replace(" ", "-")


def _list_text(value: Any, *, max_items: int = 16, max_len: int = 80) -> list[str]:
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    out = [_text(x, max_len) for x in raw]
    return list(dict.fromkeys(x for x in out if x))[:max_items]


def _backing_expected(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return _text(value, 120)


def _normalize_structural_backing_ref(raw: Any) -> dict[str, Any]:
    obj: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    if str(obj.get("source") or "").strip() != "engineCall":
        return {}
    field = _text(obj.get("field"), 64)
    call_id = _text(obj.get("callId"), 64)
    if not field or not call_id:
        return {}
    return {
        "source": "engineCall",
        "callId": call_id,
        "field": field,
        "expected": _backing_expected(obj.get("expected")),
    }


def _normalize_structural_claim(raw: Any) -> dict[str, Any]:
    obj: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    status = _norm(obj.get("status")).replace("-", "_")
    if status not in {"executable", "visual_only"}:
        status = ""
    refs_candidate = obj.get("backingRefs")
    refs_raw: list[Any] = refs_candidate if isinstance(refs_candidate, list) else []
    refs = [_normalize_structural_backing_ref(ref) for ref in refs_raw]
    return {
        "claimId": _text(obj.get("claimId"), 64),
        "playerText": _text(obj.get("playerText"), 220),
        "backingRefs": [ref for ref in refs if ref][:12],
        "status": status,
    }


def _normalize_structural_timeline_step(raw: Any) -> dict[str, Any]:
    obj: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    return {
        "phase": _text(obj.get("phase"), 48),
        "text": _text(obj.get("text"), 180),
        "claimIds": _list_text(obj.get("claimIds"), max_items=8, max_len=64),
        "presentationOnly": obj.get("presentationOnly") is True,
    }


def _normalize_structural_runtime_contract(obj: dict[str, Any]) -> dict[str, Any]:
    claims_candidate = obj.get("mechanicClaims")
    claims_raw: list[Any] = claims_candidate if isinstance(claims_candidate, list) else []
    timeline_candidate = obj.get("playerViewTimeline")
    timeline_raw: list[Any] = timeline_candidate if isinstance(timeline_candidate, list) else []
    execution = _norm(obj.get("executionStatus")).replace("-", "_")
    if execution not in EXECUTION_STATUSES:
        execution = ""
    signature_mode = _norm(obj.get("signatureMode")).replace("-", "_")
    if signature_mode not in {"mechanic", "visual"}:
        signature_mode = ""
    return {
        "schema": STRUCTURAL_RUNTIME_CONTRACT_SCHEMA,
        "primaryVerb": _text(obj.get("primaryVerb"), 120),
        "controlStyle": _norm(obj.get("controlStyle")),
        "signatureMode": signature_mode,
        "signatureClaimId": _text(obj.get("signatureClaimId"), 64),
        "tooltipClaimIds": _list_text(obj.get("tooltipClaimIds"), max_items=16, max_len=64),
        "stateFields": _list_text(obj.get("stateFields"), max_items=16, max_len=48),
        "syncFields": _list_text(obj.get("syncFields"), max_items=16, max_len=48),
        "visualStateFields": _list_text(obj.get("visualStateFields"), max_items=16, max_len=48),
        "playerViewTimeline": [_normalize_structural_timeline_step(step) for step in timeline_raw][:8],
        "mechanicClaims": [_normalize_structural_claim(claim) for claim in claims_raw][:16],
        "unsupportedPromises": _list_text(obj.get("unsupportedPromises"), max_items=24, max_len=120),
        "finalWireReceipts": [
            dict(row)
            for row in (obj.get("finalWireReceipts") or [])
            if isinstance(row, dict)
        ][:96],
        "executionStatus": execution,
    }


def normalize_backing_ref(raw: Any) -> dict[str, Any]:
    obj: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    source = str(obj.get("source") or "").strip()
    if source not in {"compiledAttack", "runtimeArchetype", "engineCall"}:
        return {}
    ref: dict[str, Any] = {
        "source": source,
        "field": _text(obj.get("field"), 64),
        "expected": _backing_expected(obj.get("expected")),
    }
    if source == "engineCall":
        call_index_raw = obj.get("callIndex")
        try:
            ref["callIndex"] = int(call_index_raw) if call_index_raw is not None else -1
        except (TypeError, ValueError, OverflowError):
            ref["callIndex"] = -1
        ref["fn"] = _text(obj.get("fn"), 64).lower()
    return ref if ref["field"] else {}


def normalize_mechanic_claim(raw: Any) -> dict[str, Any]:
    obj: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {"claim": raw}
    status = _norm(obj.get("status")).replace("-", "_")
    if status in EXECUTABLE_STATUS_ALIASES:
        status = "executable"
    elif status in UNSUPPORTED_STATUS_ALIASES:
        status = "unsupported"
    if status not in {"", "executable", "partial", "visual_only", "unsupported", "ambiguous"}:
        status = ""
    refs_candidate = obj.get("backingRefs")
    refs_raw: list[Any] = refs_candidate if isinstance(refs_candidate, list) else []
    refs = [normalize_backing_ref(ref) for ref in refs_raw]
    refs = [ref for ref in refs if ref]
    return {
        "claim": _text(obj.get("claim"), 220),
        "backing": _text(obj.get("backing"), 160),
        "backingRefs": refs[:12],
        "status": status,
    }


def _backing_values_match(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return abs(float(actual) - float(expected)) <= 1e-6
    return actual == expected


_EVIDENCE_GENERIC_TOKENS = {
    "action", "apply", "behavior", "call", "effect", "engine", "field", "get", "item",
    "mode", "param", "runtime", "set", "stat", "stats", "use", "value",
}
_EVIDENCE_CLAIM_STOPWORDS = {
    "a", "an", "and", "as", "at", "be", "by", "can", "for", "from", "in", "into",
    "is", "it", "of", "on", "or", "that", "the", "then", "this", "to", "up", "while",
    "with", "within", "you", "your",
}


def _evidence_tokens(value: Any) -> set[str]:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value or ""))
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9]*", text.replace("_", " ").replace("-", " ").lower())
    return {word[:-1] if len(word) > 4 and word.endswith("s") else word for word in words}


def _evidence_token_matches(left: str, right: str) -> bool:
    if left == right:
        return True
    if min(len(left), len(right)) >= 5 and (left in right or right in left):
        return True
    prefix = 0
    for a, b in zip(left, right):
        if a != b:
            break
        prefix += 1
    return prefix >= 5


def mechanic_claim_backing_relevant(claim: dict[str, Any]) -> tuple[bool, list[str]]:
    """Check that machine refs are lexical evidence for the claim they purport to prove.

    This is deliberately executor-agnostic: identifiers, enum values, booleans, and
    numbers supply evidence. It prevents an active but unrelated field (for example an
    alt-use mode) from proving arbitrary prose without introducing item-name routing.
    """
    claim_text = str(claim.get("claim") or "")
    claim_tokens = _evidence_tokens(claim_text) - _EVIDENCE_CLAIM_STOPWORDS
    claim_numbers = {float(value.rstrip("%")) for value in re.findall(r"\d+(?:\.\d+)?%?", claim_text)}
    refs_candidate = claim.get("backingRefs")
    refs_raw: list[Any] = refs_candidate if isinstance(refs_candidate, list) else []
    refs = [normalize_backing_ref(ref) for ref in refs_raw]
    refs = [ref for ref in refs if ref]
    if not refs:
        return False, ["missing_backing_refs"]

    score = 0
    evidence_numbers: set[float] = set()
    evidence_tokens: set[str] = set()
    for ref in refs:
        field = str(ref.get("field") or "")
        field_tokens = _evidence_tokens(field) - _EVIDENCE_GENERIC_TOKENS
        expected_tokens = _evidence_tokens(ref.get("expected")) - _EVIDENCE_GENERIC_TOKENS
        fn_tokens = _evidence_tokens(ref.get("fn")) - _EVIDENCE_GENERIC_TOKENS
        for token in field_tokens:
            if any(_evidence_token_matches(token, claim_token) for claim_token in claim_tokens):
                score += 2
                evidence_tokens.add(token)
        for token in expected_tokens:
            if any(_evidence_token_matches(token, claim_token) for claim_token in claim_tokens):
                score += 1
                evidence_tokens.add(token)
        for token in fn_tokens:
            if any(_evidence_token_matches(token, claim_token) for claim_token in claim_tokens):
                score += 2
                evidence_tokens.add(token)
        expected = ref.get("expected")
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            numeric = float(expected)
            evidence_numbers.add(numeric)
            if field.lower().endswith("ticks"):
                evidence_numbers.add(numeric / 60.0)

    if claim_numbers and not claim_numbers.issubset(evidence_numbers):
        return False, ["claim_numbers_not_proven_by_backing_refs"]
    if score < 2:
        return False, ["claim_text_not_relevant_to_backing_refs"]
    return True, []


def resolve_mechanic_backing_refs(
    data: dict[str, Any],
    patch: dict[str, Any],
    claim: dict[str, Any],
) -> tuple[bool, list[str]]:
    refs_candidate = claim.get("backingRefs")
    refs_raw: list[Any] = refs_candidate if isinstance(refs_candidate, list) else []
    refs = [normalize_backing_ref(ref) for ref in refs_raw]
    refs = [ref for ref in refs if ref]
    if not refs:
        return False, ["missing_backing_refs"]

    runtime_plan_candidate = data.get("runtimePlan")
    runtime_plan: dict[str, Any] = dict(runtime_plan_candidate) if isinstance(runtime_plan_candidate, dict) else {}
    calls_candidate = runtime_plan.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    archetype_candidate = data.get("runtimeArchetype")
    archetype: dict[str, Any] = dict(archetype_candidate) if isinstance(archetype_candidate, dict) else {}
    failures: list[str] = []
    for index, ref in enumerate(refs):
        source = ref["source"]
        field = ref["field"]
        actual: Any = None
        present = False
        if source == "compiledAttack":
            present = field in patch
            actual = patch.get(field)
        elif source == "runtimeArchetype":
            present = field in archetype
            actual = archetype.get(field)
        elif source == "engineCall":
            call_index_raw = ref.get("callIndex", -1)
            try:
                call_index = int(call_index_raw) if isinstance(call_index_raw, (int, str)) else -1
            except (TypeError, ValueError, OverflowError):
                call_index = -1
            if 0 <= call_index < len(calls) and isinstance(calls[call_index], dict):
                call: dict[str, Any] = calls[call_index]
                fn_candidates = {
                    str(call.get(key) or "").strip().lower()
                    for key in ("fn", "_rawFn")
                    if str(call.get(key) or "").strip()
                }
                params = call.get("params") if isinstance(call.get("params"), dict) else call
                if str(ref.get("fn") or "") in fn_candidates and isinstance(params, dict):
                    present = field in params
                    actual = params.get(field)
                    if (
                        present
                        and _backing_values_match(actual, ref.get("expected"))
                        and field in patch
                        and not _backing_values_match(patch.get(field), ref.get("expected"))
                    ):
                        failures.append(f"ref[{index}]_inactive_compiled_field:{field}")
                        continue
        if not present or not _backing_values_match(actual, ref.get("expected")):
            failures.append(f"ref[{index}]_unresolved:{source}.{field}")
    return not failures, failures


def normalize_runtime_contract(raw: Any) -> dict[str, Any]:
    obj: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    if str(obj.get("schema") or "").strip() == STRUCTURAL_RUNTIME_CONTRACT_SCHEMA:
        return _normalize_structural_runtime_contract(obj)
    control = _norm(obj.get("controlStyle"))
    if control not in CONTROL_STYLES:
        control = ""
    execution = _norm(obj.get("executionStatus")).replace("-", "_")
    if execution in EXECUTABLE_STATUS_ALIASES:
        execution = "executable"
    elif execution in {"degraded", "mixed"}:
        execution = "partial"
    elif execution in UNSUPPORTED_STATUS_ALIASES:
        execution = "unsupported"
    if execution not in EXECUTION_STATUSES:
        execution = ""
    claims_candidate = obj.get("mechanicClaims")
    claims_raw: list[Any] = claims_candidate if isinstance(claims_candidate, list) else []
    claims = [normalize_mechanic_claim(x) for x in claims_raw]
    claims = [x for x in claims if x.get("claim")]
    return {
        "schema": RUNTIME_CONTRACT_SCHEMA,
        "primaryVerb": _text(obj.get("primaryVerb"), 120),
        "controlStyle": control,
        "mustFeelLike": _list_text(obj.get("mustFeelLike"), max_items=8, max_len=80),
        "mustNotFeelLike": _list_text(obj.get("mustNotFeelLike"), max_items=8, max_len=80),
        "stateFields": _list_text(obj.get("stateFields"), max_items=16, max_len=48),
        "syncFields": _list_text(obj.get("syncFields"), max_items=16, max_len=48),
        "visualStateFields": _list_text(obj.get("visualStateFields"), max_items=16, max_len=48),
        "playerViewTimeline": _list_text(obj.get("playerViewTimeline"), max_items=8, max_len=180),
        "mechanicClaims": claims[:16],
        "unsupportedPromises": _list_text(obj.get("unsupportedPromises"), max_items=24, max_len=120),
        "executionStatus": execution,
    }


def _append_unique_list(data: dict[str, Any], key: str, values: list[str]) -> None:
    current = data.get(key) if isinstance(data.get(key), list) else []
    merged = list(dict.fromkeys([str(x) for x in current if x] + [str(x) for x in values if x]))
    data[key] = merged[:32]


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


def validate_structural_planner_contract(data: dict[str, Any]) -> dict[str, Any]:
    """Validate v3 authorship links before final DTO projection, without prose semantics."""
    raw_contract_candidate = data.get("runtimeContract")
    raw_contract: dict[str, Any] = dict(raw_contract_candidate) if isinstance(raw_contract_candidate, dict) else {}
    model_authored_receipts = bool(raw_contract.get("finalWireReceipts"))
    raw_claims_candidate = raw_contract.get("mechanicClaims")
    raw_claims: list[Any] = raw_claims_candidate if isinstance(raw_claims_candidate, list) else []
    model_authored_final_fields = False
    for raw_claim in raw_claims:
        if not isinstance(raw_claim, dict):
            continue
        raw_refs_candidate = raw_claim.get("backingRefs")
        raw_refs: list[Any] = raw_refs_candidate if isinstance(raw_refs_candidate, list) else []
        if any(isinstance(ref, dict) and ("finalPath" in ref or "finalExpected" in ref) for ref in raw_refs):
            model_authored_final_fields = True
            break
    contract = normalize_runtime_contract(raw_contract)
    contract["finalWireReceipts"] = []
    data["runtimeContract"] = contract
    errors: list[dict[str, Any]] = []
    if model_authored_receipts:
        errors.append({"kind": "model_authored_final_wire_receipts"})
    if model_authored_final_fields:
        errors.append({"kind": "model_authored_final_wire_fields"})
    runtime = data.get("runtimePlan") if isinstance(data.get("runtimePlan"), dict) else {}
    calls_candidate = runtime.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    calls_by_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(calls):
        if not isinstance(raw, dict):
            errors.append({"kind": "engine_call_not_object", "callIndex": index})
            continue
        call_id = str(raw.get("callId") or "").strip()
        if not _STRUCTURAL_ID_RE.fullmatch(call_id):
            errors.append({"kind": "invalid_or_missing_call_id", "callIndex": index, "callId": call_id})
            continue
        if call_id in calls_by_id:
            errors.append({"kind": "duplicate_call_id", "callId": call_id})
            continue
        calls_by_id[call_id] = raw

    claims_candidate = contract.get("mechanicClaims")
    claims: list[dict[str, Any]] = [claim for claim in claims_candidate if isinstance(claim, dict)] if isinstance(claims_candidate, list) else []
    claims_by_id: dict[str, dict[str, Any]] = {}
    executable_claim_ids: set[str] = set()
    visual_claim_ids: set[str] = set()
    for claim_index, claim in enumerate(claims):
        claim_id = str(claim.get("claimId") or "").strip()
        if not _STRUCTURAL_ID_RE.fullmatch(claim_id):
            errors.append({"kind": "invalid_or_missing_claim_id", "claimIndex": claim_index, "claimId": claim_id})
            continue
        if claim_id in claims_by_id:
            errors.append({"kind": "duplicate_claim_id", "claimId": claim_id})
            continue
        claims_by_id[claim_id] = claim
        if not str(claim.get("playerText") or "").strip():
            errors.append({"kind": "missing_player_text", "claimId": claim_id})
        status = str(claim.get("status") or "")
        refs_candidate = claim.get("backingRefs")
        refs: list[dict[str, Any]] = [ref for ref in refs_candidate if isinstance(ref, dict)] if isinstance(refs_candidate, list) else []
        if status == "visual_only":
            visual_claim_ids.add(claim_id)
            if refs:
                errors.append({"kind": "visual_claim_has_execution_refs", "claimId": claim_id})
            continue
        if status != "executable":
            errors.append({"kind": "invalid_claim_status", "claimId": claim_id, "status": status})
            continue
        if not refs:
            errors.append({"kind": "missing_final_wire_refs", "claimId": claim_id})
            continue
        claim_resolved = True
        for ref_index, ref in enumerate(refs):
            call_id = str(ref.get("callId") or "")
            call = calls_by_id.get(call_id)
            field = str(ref.get("field") or "")
            params_candidate = call.get("params") if isinstance(call, dict) else None
            params: dict[str, Any] = dict(params_candidate) if isinstance(params_candidate, dict) else {}
            authored_present, authored_actual = _nested_path_value(params, field)
            if not authored_present or not _backing_values_match(authored_actual, ref.get("expected")):
                claim_resolved = False
                errors.append({
                    "kind": "authored_ref_unresolved",
                    "claimId": claim_id,
                    "refIndex": ref_index,
                    "callId": call_id,
                    "field": field,
                })
        if claim_resolved:
            executable_claim_ids.add(claim_id)

    signature_mode = str(contract.get("signatureMode") or "")
    signature_claim_id = str(contract.get("signatureClaimId") or "")
    if signature_mode == "mechanic":
        if signature_claim_id not in executable_claim_ids:
            errors.append({"kind": "signature_claim_not_executable", "claimId": signature_claim_id})
    elif signature_mode == "visual":
        if signature_claim_id not in visual_claim_ids:
            errors.append({"kind": "signature_claim_not_visual", "claimId": signature_claim_id})
    else:
        errors.append({"kind": "missing_signature_mode", "claimId": signature_claim_id})

    tooltip_ids = [str(value) for value in contract.get("tooltipClaimIds") or []]
    if not tooltip_ids:
        errors.append({"kind": "missing_tooltip_claim_ids"})
    for claim_id in tooltip_ids:
        if claim_id not in claims_by_id:
            errors.append({"kind": "unknown_tooltip_claim_id", "claimId": claim_id})
    if signature_mode == "mechanic" and signature_claim_id not in tooltip_ids:
        errors.append({"kind": "signature_missing_from_tooltip", "claimId": signature_claim_id})

    timeline_candidate = contract.get("playerViewTimeline")
    timeline: list[dict[str, Any]] = [step for step in timeline_candidate if isinstance(step, dict)] if isinstance(timeline_candidate, list) else []
    if len(timeline) < 4:
        errors.append({"kind": "missing_player_view_timeline"})
    timeline_claim_ids: set[str] = set()
    for step_index, step in enumerate(timeline):
        claim_ids = [str(value) for value in step.get("claimIds") or []]
        if step.get("presentationOnly") is True:
            if claim_ids:
                errors.append({"kind": "presentation_step_has_claim_ids", "stepIndex": step_index})
            continue
        if not claim_ids:
            errors.append({"kind": "timeline_step_missing_claim_ids", "stepIndex": step_index})
            continue
        for claim_id in claim_ids:
            timeline_claim_ids.add(claim_id)
            if claim_id not in claims_by_id:
                errors.append({"kind": "unknown_timeline_claim_id", "stepIndex": step_index, "claimId": claim_id})
    if signature_claim_id and signature_claim_id not in timeline_claim_ids:
        errors.append({"kind": "signature_missing_from_timeline", "claimId": signature_claim_id})

    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    weird_twist = concept.get("weirdTwist") if isinstance(concept.get("weirdTwist"), dict) else {}
    twist_claim_ids = [str(value) for value in weird_twist.get("claimIds") or []]
    if signature_claim_id and signature_claim_id not in twist_claim_ids:
        errors.append({"kind": "signature_missing_from_weird_twist", "claimId": signature_claim_id})
    if not executable_claim_ids:
        errors.append({"kind": "missing_executable_mechanic_claim"})
    if contract.get("unsupportedPromises"):
        errors.append({"kind": "unsupported_promises_present"})

    return {
        "schema": "infini.structural-planner-contract-report.v1",
        "ok": not errors,
        "blockingClaims": errors[:32],
        "unsupportedPromises": list(contract.get("unsupportedPromises") or []),
    }


def validate_structural_final_wire_contract(data: dict[str, Any]) -> dict[str, Any]:
    """Validate v3 authorship using compiler-owned final DTO provenance only.

    This function does not interpret prose, infer item mechanics, or map semantic
    categories.  It proves that authored call scalars survived to the final wire.
    """
    contract = normalize_runtime_contract(data.get("runtimeContract"))
    data["runtimeContract"] = contract
    errors: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []

    runtime = data.get("runtimePlan") if isinstance(data.get("runtimePlan"), dict) else {}
    calls_candidate = runtime.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    calls_by_id: dict[str, list[dict[str, Any]]] = {}
    call_indices_by_id: dict[str, set[int]] = {}
    for index, raw in enumerate(calls):
        if not isinstance(raw, dict):
            continue
        call_id = str(raw.get("callId") or "").strip()
        authored_index = raw.get("_index") if isinstance(raw.get("_index"), int) else index
        if not _STRUCTURAL_ID_RE.fullmatch(call_id):
            errors.append({"kind": "invalid_or_missing_call_id", "callIndex": authored_index, "callId": call_id})
            continue
        calls_by_id.setdefault(call_id, []).append(raw)
        call_indices_by_id.setdefault(call_id, set()).add(authored_index)
    for call_id, indices in call_indices_by_id.items():
        if len(indices) > 1:
            errors.append({"kind": "duplicate_call_id", "callId": call_id})

    claims_candidate = contract.get("mechanicClaims")
    claims: list[dict[str, Any]] = [claim for claim in claims_candidate if isinstance(claim, dict)] if isinstance(claims_candidate, list) else []
    claims_by_id: dict[str, dict[str, Any]] = {}
    executable_claim_ids: set[str] = set()
    visual_claim_ids: set[str] = set()
    for claim_index, claim in enumerate(claims):
        claim_id = str(claim.get("claimId") or "").strip()
        if not _STRUCTURAL_ID_RE.fullmatch(claim_id):
            errors.append({"kind": "invalid_or_missing_claim_id", "claimIndex": claim_index, "claimId": claim_id})
            continue
        if claim_id in claims_by_id:
            errors.append({"kind": "duplicate_claim_id", "claimId": claim_id})
            continue
        claims_by_id[claim_id] = claim
        if not str(claim.get("playerText") or "").strip():
            errors.append({"kind": "missing_player_text", "claimId": claim_id})
        status = str(claim.get("status") or "")
        if status == "visual_only":
            visual_claim_ids.add(claim_id)
            if claim.get("backingRefs"):
                errors.append({"kind": "visual_claim_has_execution_refs", "claimId": claim_id})
            continue
        if status != "executable":
            errors.append({"kind": "invalid_claim_status", "claimId": claim_id, "status": status})
            continue
        refs_candidate = claim.get("backingRefs")
        refs: list[dict[str, Any]] = [ref for ref in refs_candidate if isinstance(ref, dict)] if isinstance(refs_candidate, list) else []
        if not refs:
            errors.append({"kind": "missing_final_wire_refs", "claimId": claim_id})
            continue
        claim_active = True
        for ref_index, ref in enumerate(refs):
            call_id = str(ref.get("callId") or "")
            field = str(ref.get("field") or "")
            expected = ref.get("expected")
            source_calls = calls_by_id.get(call_id) or []
            authored_present = False
            for call in source_calls:
                params_candidate = call.get("params")
                params: dict[str, Any] = dict(params_candidate) if isinstance(params_candidate, dict) else {}
                source_present, source_actual = _nested_path_value(params, field)
                if source_present and _backing_values_match(source_actual, expected):
                    authored_present = True
                    break
            matching_receipts = [
                row
                for row in contract.get("finalWireReceipts") or []
                if isinstance(row, dict)
                and str(row.get("claimId") or "") == claim_id
                and row.get("refIndex") == ref_index
                and str(row.get("callId") or "") == call_id
                and str(row.get("field") or "") == field
                and _backing_values_match(row.get("authoredExpected"), expected)
            ]
            if not authored_present:
                receipt = {
                    "claimId": claim_id, "refIndex": ref_index, "callId": call_id,
                    "field": field, "authoredExpected": expected, "finalPath": "",
                    "compiledValue": None, "finalActual": None, "status": "authored_unresolved",
                }
                receipts.append(receipt)
                claim_active = False
                errors.append({"kind": "final_wire_ref_authored_unresolved", **receipt})
                continue
            if not matching_receipts:
                receipt = {
                    "claimId": claim_id, "refIndex": ref_index, "callId": call_id,
                    "field": field, "authoredExpected": expected, "finalPath": "",
                    "compiledValue": None, "finalActual": None, "status": "missing_compiler_receipt",
                }
                receipts.append(receipt)
                claim_active = False
                errors.append({"kind": "final_wire_ref_missing_compiler_receipt", **receipt})
                continue
            for compiler_receipt in matching_receipts:
                final_path = str(compiler_receipt.get("finalPath") or "")
                compiled_value = compiler_receipt.get("compiledValue")
                compiler_status = str(compiler_receipt.get("status") or "")
                final_present, final_actual = _final_wire_value(data, final_path)
                if compiler_status not in {"active", "normalized", "clamped"}:
                    receipt_status = compiler_status or "unsupported"
                elif not final_present:
                    receipt_status = "dropped"
                elif not _backing_values_match(final_actual, compiled_value):
                    receipt_status = "mismatched"
                else:
                    receipt_status = compiler_status
                receipt = {
                    "claimId": claim_id,
                    "refIndex": ref_index,
                    "callId": call_id,
                    "field": field,
                    "authoredExpected": expected,
                    "finalPath": final_path,
                    "compiledValue": compiled_value,
                    "finalActual": final_actual if final_present else None,
                    "status": receipt_status,
                }
                receipts.append(receipt)
                if receipt_status not in {"active", "normalized", "clamped"}:
                    claim_active = False
                    errors.append({"kind": "final_wire_ref_" + receipt_status, **receipt})
        if claim_active:
            executable_claim_ids.add(claim_id)

    signature_mode = str(contract.get("signatureMode") or "")
    signature_claim_id = str(contract.get("signatureClaimId") or "")
    if signature_mode == "mechanic":
        if signature_claim_id not in executable_claim_ids:
            errors.append({"kind": "signature_claim_not_executable", "claimId": signature_claim_id})
    elif signature_mode == "visual":
        if signature_claim_id not in visual_claim_ids:
            errors.append({"kind": "signature_claim_not_visual", "claimId": signature_claim_id})
    else:
        errors.append({"kind": "missing_signature_mode", "claimId": signature_claim_id})

    tooltip_ids = [str(value) for value in contract.get("tooltipClaimIds") or []]
    if not tooltip_ids:
        errors.append({"kind": "missing_tooltip_claim_ids"})
    for claim_id in tooltip_ids:
        if claim_id not in claims_by_id:
            errors.append({"kind": "unknown_tooltip_claim_id", "claimId": claim_id})
    if signature_mode == "mechanic" and signature_claim_id not in tooltip_ids:
        errors.append({"kind": "signature_missing_from_tooltip", "claimId": signature_claim_id})

    timeline_candidate = contract.get("playerViewTimeline")
    timeline: list[dict[str, Any]] = [step for step in timeline_candidate if isinstance(step, dict)] if isinstance(timeline_candidate, list) else []
    if len(timeline) < 4:
        errors.append({"kind": "missing_player_view_timeline"})
    timeline_claim_ids: set[str] = set()
    for step_index, step in enumerate(timeline):
        claim_ids = [str(value) for value in step.get("claimIds") or []]
        if step.get("presentationOnly") is True:
            if claim_ids:
                errors.append({"kind": "presentation_step_has_claim_ids", "stepIndex": step_index})
            continue
        if not claim_ids:
            errors.append({"kind": "timeline_step_missing_claim_ids", "stepIndex": step_index})
            continue
        for claim_id in claim_ids:
            timeline_claim_ids.add(claim_id)
            if claim_id not in claims_by_id:
                errors.append({"kind": "unknown_timeline_claim_id", "stepIndex": step_index, "claimId": claim_id})
    if signature_claim_id and signature_claim_id not in timeline_claim_ids:
        errors.append({"kind": "signature_missing_from_timeline", "claimId": signature_claim_id})

    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    weird_twist = concept.get("weirdTwist") if isinstance(concept.get("weirdTwist"), dict) else {}
    twist_claim_ids = [str(value) for value in weird_twist.get("claimIds") or []]
    if signature_claim_id and signature_claim_id not in twist_claim_ids:
        errors.append({"kind": "signature_missing_from_weird_twist", "claimId": signature_claim_id})

    if not executable_claim_ids:
        errors.append({"kind": "missing_executable_mechanic_claim"})
    if contract.get("unsupportedPromises"):
        errors.append({"kind": "unsupported_promises_present"})

    tooltip_parts = [
        str(claims_by_id[claim_id].get("playerText") or "").strip().rstrip(" .;")
        for claim_id in tooltip_ids
        if claim_id in claims_by_id and str(claims_by_id[claim_id].get("playerText") or "").strip()
    ]
    if not errors:
        data["tooltip"] = "; ".join(tooltip_parts)
        contract["executionStatus"] = "executable"
    else:
        contract["executionStatus"] = "partial"
    contract["finalWireReceipts"] = receipts[:96]
    data["runtimeContract"] = contract
    return {
        "schema": "infini.final-wire-contract-report.v1",
        "ok": not errors,
        "blockingClaims": errors[:32],
        "finalWireReceipts": receipts[:96],
        "executionStatus": contract["executionStatus"],
        "contract": contract,
    }


def validate_runtime_contract(data: dict[str, Any], patch: dict[str, Any] | None = None) -> dict[str, Any]:
    patch = patch or {}
    raw_present = isinstance(data.get("runtimeContract"), dict)
    contract = normalize_runtime_contract(data.get("runtimeContract") if raw_present else {})
    if raw_present:
        data["runtimeContract"] = contract
    if contract.get("schema") == STRUCTURAL_RUNTIME_CONTRACT_SCHEMA:
        return {
            "schema": "infini.runtime-contract-validation.v2",
            "warnings": [],
            "unsupportedPromises": list(contract.get("unsupportedPromises") or []),
            "executionStatus": contract.get("executionStatus", ""),
            "contract": contract,
        }

    warnings: list[str] = []
    unsupported: list[str] = list(contract.get("unsupportedPromises") or [])
    runtime_family = str(patch.get("runtimeFamily") or "")
    family = ""
    arch = data.get("runtimeArchetype") if isinstance(data.get("runtimeArchetype"), dict) else {}
    if isinstance(arch, dict):
        family = str(arch.get("family") or "")

    if contract.get("controlStyle") == "hold-to-channel":
        channel_ok = bool(patch.get("channelUse")) and runtime_family in {"yoyo", "charge_release"}
        beam_ok = family == "channel_beam" and patch.get("runtimeFamily") == "beam" and bool(patch.get("channelUse"))
        if not (channel_ok or beam_ok):
            warnings.append("hold_to_channel_contract_preserved_without_channel_executor")
            unsupported.append("unsupported:hold_to_channel")

    sync_fields = {str(x or "").strip() for x in contract.get("syncFields") or [] if str(x or "").strip()}
    if sync_fields:
        active_sync_fields: set[str] = set()
        if family == "channel_beam" and runtime_family == "beam":
            active_sync_fields = {"owner", "beamRotation", "beamDirection", "beamLength", "chargeTicks"}
        elif family == "charge_release" and runtime_family == "charge_release":
            active_sync_fields = {"owner", "chargeTicks", "chargePowerMultiplier", "releaseDirection", "shotCount"}
        elif family == "sentry" and runtime_family == "sentry":
            active_sync_fields = {"owner", "sentryPlacement", "sentryAttackIntervalTicks", "sentryTargetRangeTiles", "sentryLifetimeTicks"}
        elif family == "overhead_barrage" and runtime_family == "overhead_barrage":
            active_sync_fields = {"owner", "targetPosition", "delayTicks", "shotCount"}
        unsupported_sync = sorted(sync_fields - active_sync_fields)
        if unsupported_sync:
            warnings.append("sync_contract_fields_not_active:" + ",".join(unsupported_sync[:8]))
            unsupported.extend("unsupported:sync:" + x for x in unsupported_sync[:8])

    if family in {"secondary_attack", "unsupported"}:
        unsupported.append(f"unsupported:{family}")


    # Mechanic claims are debug/truth contracts. They do not create gameplay.
    # Free-text `backing` is descriptive only; executable status requires exact
    # machine-resolvable backingRefs.
    for claim in contract.get("mechanicClaims") or []:
        backing = str(claim.get("backing") or "").lower()
        status = str(claim.get("status") or "")
        machine_backed, backing_failures = resolve_mechanic_backing_refs(data, patch, claim)
        has_refs = bool(claim.get("backingRefs"))
        if status == "visual_only" or "visual_only" in backing:
            claim["status"] = "visual_only"
        elif status == "unsupported" or "unsupported" in backing:
            claim["status"] = "unsupported"
            unsupported.append("unsupported:" + (claim.get("claim") or "mechanic")[:48])
        elif machine_backed:
            claim["status"] = "executable"
        elif has_refs or status == "executable":
            claim["status"] = "partial"
            warnings.append("machine_backing_refs_missing_or_unresolved")
            warnings.extend(backing_failures[:4])
        elif not status:
            claim["status"] = "ambiguous"

    if raw_present:
        statuses = {str(c.get("status") or "") for c in contract.get("mechanicClaims") or []}
        if unsupported:
            runtime_executable = runtime_family not in {"", "none", "unsupported"}
            contract["executionStatus"] = "partial" if runtime_executable or any(s == "executable" for s in statuses) else "unsupported"
        elif statuses and statuses <= {"executable", "visual_only"} and "executable" in statuses:
            contract["executionStatus"] = "executable"
        elif statuses == {"visual_only"}:
            contract["executionStatus"] = "visual_only"
        elif statuses:
            contract["executionStatus"] = "partial"
        elif warnings:
            contract["executionStatus"] = "partial"
        elif runtime_family not in {"", "none", "unsupported"}:
            contract["executionStatus"] = "executable"
        data["runtimeContract"] = contract

    if unsupported:
        _append_unique_list(data, "unsupportedPromises", list(dict.fromkeys(unsupported)))

    return {
        "schema": "infini.runtime-contract-validation.v1",
        "warnings": list(dict.fromkeys(warnings))[:16],
        "unsupportedPromises": list(dict.fromkeys(unsupported))[:24],
        "executionStatus": contract.get("executionStatus", ""),
        "contract": contract,
    }
