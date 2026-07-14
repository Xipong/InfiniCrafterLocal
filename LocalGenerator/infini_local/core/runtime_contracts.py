from __future__ import annotations

from typing import Any

RUNTIME_CONTRACT_SCHEMA = "infini.runtime-contract.v2"
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
            call_index = int(call_index_raw) if isinstance(call_index_raw, (int, str)) else -1
            if 0 <= call_index < len(calls) and isinstance(calls[call_index], dict):
                call: dict[str, Any] = calls[call_index]
                fn = str(call.get("fn") or "").strip().lower()
                params = call.get("params") if isinstance(call.get("params"), dict) else call
                if fn == str(ref.get("fn") or "") and isinstance(params, dict):
                    present = field in params
                    actual = params.get(field)
        if not present or not _backing_values_match(actual, ref.get("expected")):
            failures.append(f"ref[{index}]_unresolved:{source}.{field}")
    return not failures, failures


def normalize_runtime_contract(raw: Any) -> dict[str, Any]:
    obj: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
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


def validate_runtime_contract(data: dict[str, Any], patch: dict[str, Any] | None = None) -> dict[str, Any]:
    patch = patch or {}
    raw_present = isinstance(data.get("runtimeContract"), dict)
    contract = normalize_runtime_contract(data.get("runtimeContract") if raw_present else {})
    if raw_present:
        data["runtimeContract"] = contract

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
        elif statuses and statuses <= {"executable"}:
            contract["executionStatus"] = "executable"
        elif statuses and "visual_only" in statuses:
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
