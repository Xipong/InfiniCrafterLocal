from __future__ import annotations

import math
import re
from typing import Any

from infini_local.core.runtime_authoring.common import _clamp, _enum, _norm_name, _num
from infini_local.core.runtime_authoring.normalize import runtime_plan
from infini_local.core.runtime_authoring.schema import ENGINE_FN_CATALOG_V2, INT_FIELDS
from infini_local.core.runtime_authoring.vocabulary import DELIVERIES
from infini_local.core.runtime_executor_vocabulary import MOVEMENTS
from infini_local.core.runtime_family_policy import CANONICAL_RUNTIME_FAMILIES as RUNTIME_FAMILIES

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
        if fn not in ENGINE_FN_CATALOG_V2 or not isinstance(params, dict):
            out.append(raw)
            continue
        normalized, fixes = _structural_params(params)
        row = {"fn": fn, "params": normalized}
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
    """Return every call of a function. The author can stack compatible calls; compiler aggregates only executable-compatible shapes."""
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


def _select_primary_shoot_call(calls: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Choose one executable primary family and reject incompatible extras.

    The first authored projectile/held executor is the primary. Compatible extra
    calls may only aggregate multi-shot/spread/pierce pressure. Incompatible
    calls must not leak back into executableFields through a later-call merge.
    This is the anti-spaghetti boundary: it is based only on normalized engineCall
    fields, never on item names or prose.
    """
    if not calls:
        return {}, []
    primary = calls[0] if isinstance(calls[0], dict) else {}
    primary_delivery = _enum(primary.get("delivery"), DELIVERIES, "shoot")
    primary_movement = _enum(primary.get("movement"), MOVEMENTS, "straight")
    compatible: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    total_shots = 0
    max_spread = 0.0
    max_pierce: float = 0.0
    for sc in calls:
        if not isinstance(sc, dict):
            continue
        d = _enum(sc.get("delivery"), DELIVERIES, primary_delivery)
        m = _enum(sc.get("movement"), MOVEMENTS, primary_movement)
        same_primary = d == primary_delivery and m == primary_movement
        if same_primary:
            compatible.append(sc)
            total_shots += int(_clamp(sc.get("shotCount"), "shotCount", 1) or 1)
            max_spread = max(max_spread, float(_clamp(sc.get("spreadRadians"), "spreadRadians", 0) or 0))
            pv = _clamp(sc.get("pierce"), "pierce", 0)
            if pv == -1:
                max_pierce = -1
            elif max_pierce != -1:
                max_pierce = max(max_pierce, float(pv or 0))
        else:
            rejected.append({"index": sc.get("_index"), "delivery": d, "movement": m, "reason": "runtime_one_primary_family"})
    selected = _merged_params(compatible) if compatible else dict(primary)
    if total_shots > 0:
        selected["shotCount"] = min(8, total_shots)
        selected["spreadRadians"] = max(float(selected.get("spreadRadians") or 0), max_spread)
        selected["pierce"] = max(float(selected.get("pierce") or 0), max_pierce)
    return selected, rejected


def _call_by_index(calls: list[dict[str, Any]], index: Any) -> dict[str, Any]:
    for call in calls:
        if isinstance(call, dict) and call.get("_index") == index:
            return call
    return {}


def _recover_rejected_primary_as_swing_secondary(
    primary: dict[str, Any],
    rejected: list[dict[str, Any]],
    all_shoot_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    """Recover a second authored attack as an explicit swing secondary.

    This is not prompt/prose inference and it is not a new category router.  It only
    handles a structural ambiguity the LLM can produce today: a melee primary plus
    a second incompatible projectile primary.  Current C# has real on-hit swing
    secondary projectiles, so preserving the extra call there is safer than either
    letting it override the primary or deleting it.
    """
    if not rejected:
        return {}
    primary_delivery = _enum(primary.get("delivery"), DELIVERIES, "")
    primary_family = _enum(primary.get("runtimeFamily"), RUNTIME_FAMILIES, primary_delivery)
    if primary_delivery not in {"swing", "thrust"} and primary_family not in {"swing", "thrust"}:
        return {}

    for row in rejected:
        src = _call_by_index(all_shoot_calls, row.get("index"))
        if not src:
            continue
        delivery = _enum(src.get("delivery"), DELIVERIES, "")
        family = _enum(src.get("runtimeFamily"), RUNTIME_FAMILIES, delivery)
        if delivery not in {"shoot", "throw", "cast"} and family not in {"shoot", "throw", "cast"}:
            continue
        shape = str(src.get("projectileShape") or src.get("projectileFamily") or src.get("projectileTrail") or "shard").strip()[:80]
        material = str(src.get("material") or src.get("projectileTrail") or src.get("projectileFamily") or shape or "shard").strip()[:40]
        count = int(max(1, min(3, _clamp(src.get("shotCount"), "shotCount", 1) or 1)))
        life = int(max(6, min(120, _num(src.get("lifetimeTicks"), 24) or 24)))
        spread = float(_clamp(src.get("spreadRadians"), "secondarySpreadRadians", 0.18) or 0.18)
        dmg = float(_clamp(src.get("damageMultiplier"), "secondaryDamageMultiplier", 0.25) or 0.25)
        return {
            "_index": src.get("_index"),
            "_rawFn": "recovered_rejected_primary",
            "_recoveredFromRejectedPrimary": True,
            "trigger": "on_hit",
            "count": count,
            "damageMultiplier": round(max(0.08, min(0.35, dmg)), 3),
            "spreadRadians": round(max(0.0, min(1.2, spread)), 3),
            "lifetimeTicks": life,
            "projectileShape": shape or "shard",
            "material": material or "shard",
        }
    return {}

__all__ = [
    "STRUCTURAL_INTISH_PARAM_FIELDS",
    "_structural_scalar",
    "_structural_params",
    "structural_repair_runtime_plan_inplace",
    "find_call",
    "all_calls",
    "_first_non_empty",
    "_merged_params",
    "_select_primary_shoot_call",
    "_call_by_index",
    "_recover_rejected_primary_as_swing_secondary",
]
