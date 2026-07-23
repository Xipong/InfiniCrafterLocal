from __future__ import annotations

import math
import re
from typing import Any

from infini_local.core.runtime_authoring.common import _clamp, _enum, _norm_name
from infini_local.core.runtime_authoring.function_contract_registry import ENGINE_FUNCTION_CATALOG
from infini_local.core.runtime_authoring.normalize import runtime_plan
from infini_local.core.runtime_authoring.schema import INT_FIELDS
from infini_local.core.runtime_authoring.vocabulary import DELIVERIES
from infini_local.core.runtime_executor_vocabulary import MOVEMENTS


STRUCTURAL_INTISH_PARAM_FIELDS = INT_FIELDS | {"damage", "useAnimation", "maxStack", "defense", "rarity", "value", "chainCount", "count"}


def _structural_scalar(value: Any, key: str = "") -> Any:
    """Coerce only scalar type mistakes inside exact canonical fields."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    lower = text.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    m = re.match(r"^[+\-]?(?:\d+(?:\.\d*)?|\.\d+)", text.replace(",", "."))
    if not m:
        return value
    try:
        x = float(m.group(0))
    except ValueError:
        return value
    if not math.isfinite(x):
        return value
    if key in STRUCTURAL_INTISH_PARAM_FIELDS or key.endswith("Ticks"):
        return int(round(x))
    return x


def _structural_params(raw_params: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(raw_params, dict):
        return {}, []
    out: dict[str, Any] = {}
    fixes: list[dict[str, Any]] = []
    for key, value in raw_params.items():
        if isinstance(value, dict):
            normalized, nested = _structural_params(value)
            out[key] = normalized
            fixes.extend(nested[:8])
        elif isinstance(value, list):
            normalized_list = [_structural_scalar(item, key) for item in value]
            out[key] = normalized_list
            if normalized_list != value:
                fixes.append({"kind": "scalar_list_parse", "field": key})
        else:
            normalized = _structural_scalar(value, key)
            out[key] = normalized
            if normalized != value:
                fixes.append({"kind": "scalar_parse", "field": key, "from": str(value)[:48], "to": normalized})
    return out, fixes


def structural_repair_runtime_plan_inplace(data: dict[str, Any]) -> dict[str, Any]:
    """Repair scalar types inside the one current runtimePlan shape.

    No aliases, wrapper unwrapping, alternative keys or mapping shorthand are accepted.
    Invalid structure is left for validation/LLM repair instead of being guessed here.
    """
    report: dict[str, Any] = {"schema": "infini.runtime-structural-repair.v2", "applied": False, "fixes": []}
    rp = data.get("runtimePlan")
    if not isinstance(rp, dict):
        return report
    calls = rp.get("engineCalls")
    if not isinstance(calls, list):
        return report
    out: list[dict[str, Any]] = []
    for index, raw in enumerate(calls):
        if not isinstance(raw, dict):
            continue
        fn = _norm_name(raw.get("fn"))
        params = raw.get("params")
        if fn not in ENGINE_FUNCTION_CATALOG or not isinstance(params, dict):
            out.append(raw)
            continue
        normalized, fixes = _structural_params(params)
        row = {"fn": fn, "params": normalized}
        call_id = str(raw.get("callId") or "").strip()
        if call_id:
            row["callId"] = call_id
        out.append(row)
        for fix in fixes:
            report["fixes"].append({"index": index, **fix})
    if report["fixes"]:
        rp["engineCalls"] = out
        data["runtimePlan"] = rp
        report["applied"] = True
    report["fixes"] = report["fixes"][:48]
    return report


def find_call(data_or_plan: dict[str, Any], fn: str) -> dict[str, Any]:
    rp = data_or_plan if isinstance(data_or_plan.get("engineCalls"), list) else runtime_plan(data_or_plan)
    for raw in rp.get("engineCalls") or []:
        if isinstance(raw, dict) and _norm_name(raw.get("fn")) == fn:
            params = raw.get("params") if isinstance(raw.get("params"), dict) else raw
            return params if isinstance(params, dict) else {}
    return {}


def all_calls(data_or_plan: dict[str, Any], fn: str) -> list[dict[str, Any]]:
    """Return every call of a function. Multi-shot belongs in one root call; extra root calls are rejected by the compiler."""
    rp = data_or_plan if isinstance(data_or_plan.get("engineCalls"), list) else runtime_plan(data_or_plan)
    out: list[dict[str, Any]] = []
    want = _norm_name(fn)
    for raw in rp.get("engineCalls") or []:
        if isinstance(raw, dict) and _norm_name(raw.get("fn")) == want:
            params = raw.get("params") if isinstance(raw.get("params"), dict) else raw
            if isinstance(params, dict):
                row = dict(params)
                if "_index" in raw: row["_index"] = raw.get("_index")
                if "_rawFn" in raw: row["_rawFn"] = raw.get("_rawFn")
                if "callId" in raw: row["_callId"] = raw.get("callId")
                out.append(row)
    return out


def _first_non_empty(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return default


def _merged_params(calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge multiple calls of the same fn: later explicit params override earlier ones.

    This keeps Gemma free to split a design into several set_item_stats/on_hit calls
    without the runtime compiler silently discarding all but the first.
    """
    out: dict[str, Any] = {}
    for call in calls:
        if not isinstance(call, dict):
            continue
        for k, v in call.items():
            if k.startswith("_"):
                continue
            if v not in (None, "", [], {}):
                out[k] = v
    return out


def _select_root_executor_call(calls: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Choose exactly one root executor; every additional controller is rejected.

    Multi-shot/spread/pierce belong to that one call. Body damage is a lane of
    ``shoot+swing`` rather than a second executor. This keeps the boundary finite
    and prevents later calls from silently replacing runtimeFamily or lifecycle.
    """
    if not calls:
        return {}, []
    primary = calls[0] if isinstance(calls[0], dict) else {}
    rejected: list[dict[str, Any]] = []
    for sc in calls[1:]:
        if not isinstance(sc, dict):
            continue
        rejected.append({
            "index": sc.get("_index"),
            "callId": sc.get("_callId"),
            "fn": sc.get("_rawFn") or "shoot_projectile",
            "runtimeFamily": sc.get("runtimeFamily"),
            "delivery": sc.get("delivery"),
            "movement": sc.get("movement"),
            "reason": "runtime_one_root_executor",
        })
    return dict(primary), rejected


__all__ = [
    "STRUCTURAL_INTISH_PARAM_FIELDS",
    "_structural_scalar",
    "_structural_params",
    "structural_repair_runtime_plan_inplace",
    "find_call",
    "all_calls",
    "_first_non_empty",
    "_merged_params",
    "_select_root_executor_call",
]
