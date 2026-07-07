from __future__ import annotations

from typing import Any

RUNTIME_CONTRACT_SCHEMA = "infini.runtime-contract.v1"
CONTROL_STYLES = {"", "tap", "hold-to-channel", "right-click-alt", "combo", "passive", "on-hit-trigger"}
EXECUTION_STATUSES = {"", "executable", "partial", "visual_only", "unsupported"}


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


def normalize_mechanic_claim(raw: Any) -> dict[str, str]:
    obj = raw if isinstance(raw, dict) else {"claim": raw}
    status = _norm(obj.get("status")).replace("-", "_")
    if status not in {"", "executable", "partial", "visual_only", "unsupported", "ambiguous"}:
        status = ""
    return {
        "claim": _text(obj.get("claim"), 220),
        "backing": _text(obj.get("backing"), 160),
        "status": status,
    }


def normalize_runtime_contract(raw: Any) -> dict[str, Any]:
    obj = raw if isinstance(raw, dict) else {}
    control = _norm(obj.get("controlStyle"))
    if control not in CONTROL_STYLES:
        control = ""
    execution = _norm(obj.get("executionStatus")).replace("-", "_")
    if execution not in EXECUTION_STATUSES:
        execution = ""
    claims_raw = obj.get("mechanicClaims") if isinstance(obj.get("mechanicClaims"), list) else []
    claims = [normalize_mechanic_claim(x) for x in claims_raw]
    claims = [x for x in claims if x.get("claim")]
    return {
        "schema": _text(obj.get("schema"), 64) or RUNTIME_CONTRACT_SCHEMA,
        "primaryVerb": _text(obj.get("primaryVerb"), 120),
        "controlStyle": control,
        "mustFeelLike": _list_text(obj.get("mustFeelLike"), max_items=8, max_len=80),
        "mustNotFeelLike": _list_text(obj.get("mustNotFeelLike"), max_items=8, max_len=80),
        "stateFields": _list_text(obj.get("stateFields"), max_items=16, max_len=48),
        "syncFields": _list_text(obj.get("syncFields"), max_items=16, max_len=48),
        "visualStateFields": _list_text(obj.get("visualStateFields"), max_items=16, max_len=48),
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
        channel_ok = bool(patch.get("channelUse")) and runtime_family in {"yoyo"}
        beam_ok = family == "channel_beam" and patch.get("runtimeFamily") == "cast" and bool(patch.get("channelUse"))
        if not (channel_ok or beam_ok):
            warnings.append("hold_to_channel_contract_preserved_without_channel_executor")
            unsupported.append("unsupported:hold_to_channel")

    if contract.get("syncFields"):
        warnings.append("sync_contract_preserved_not_active")

    if family in {"channel_beam", "delayed_starfall", "secondary_attack", "unsupported"}:
        unsupported.append(f"unsupported:{family}")

    # Mechanic claims are debug/truth contracts. They do not create gameplay.
    for claim in contract.get("mechanicClaims") or []:
        backing = str(claim.get("backing") or "").lower()
        status = str(claim.get("status") or "")
        if "visual_only" in backing:
            claim["status"] = "visual_only"
        elif "unsupported" in backing:
            claim["status"] = "unsupported"
            unsupported.append("unsupported:" + (claim.get("claim") or "mechanic")[:48])
        elif "runtimearchetype.family=boomerang" in backing and family == "boomerang":
            claim["status"] = "executable"
        elif "enginecall" in backing or "runtimearchetype" in backing:
            claim["status"] = status or "partial"
        elif not status:
            claim["status"] = "ambiguous"

    if raw_present:
        statuses = {str(c.get("status") or "") for c in contract.get("mechanicClaims") or []}
        if unsupported:
            contract["executionStatus"] = "unsupported" if not any(s == "executable" for s in statuses) else "partial"
        elif statuses and statuses <= {"executable"}:
            contract["executionStatus"] = "executable"
        elif statuses and "visual_only" in statuses:
            contract["executionStatus"] = "visual_only"
        elif statuses:
            contract["executionStatus"] = "partial"
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
