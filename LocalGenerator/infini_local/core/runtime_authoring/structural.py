from __future__ import annotations

import json
import math
import re
from typing import Any

from infini_local.core.runtime_authoring.common import _clamp, _enum, _intish, _norm_name, _num
from infini_local.core.runtime_authoring.normalize import runtime_plan
from infini_local.core.runtime_authoring.schema import DELIVERIES, ENGINE_FN_CATALOG_V2, FN_ALIASES, INT_FIELDS, MOVEMENTS, RUNTIME_FAMILIES

STRUCTURAL_RUNTIME_CALL_KEYS = {"fn", "function", "name", "op", "type", "kind", "call"}
STRUCTURAL_PARAM_CONTAINER_KEYS = {"params", "args", "arguments", "payload", "values"}
STRUCTURAL_NUMERIC_PARAM_ALIASES = {
    "use_time": "useTimeTicks", "usetime": "useTimeTicks", "use_ticks": "useTimeTicks", "use_time_ticks": "useTimeTicks",
    "animation_time": "useAnimationTicks", "use_animation": "useAnimation",
    "shot_count": "shotCount", "shots": "shotCount", "projectile_count": "shotCount", "projectiles": "shotCount",
    "homing": "homingStrength", "homing_strength": "homingStrength",
    "projectile_speed": "speed", "projectilespeed": "speed", "velocity": "speed",
    "range": "rangeTiles", "range_tiles": "rangeTiles",
    "lifetime": "lifetimeTicks", "time_left": "lifetimeTicks", "timeleft": "lifetimeTicks", "duration": "lifetimeTicks",
    "aoe": "aoeRadiusTiles", "aoe_radius": "aoeRadiusTiles", "radius": "aoeRadiusTiles", "radius_tiles": "aoeRadiusTiles",
    "spread": "spreadRadians", "spread_radians": "spreadRadians",
    "extra_updates": "extraUpdates",
    "damage_class": "damageClass", "result_kind": "resultKind", "max_stack": "maxStack", "craft_yield": "craftYield",
    "buff_time": "buffTime", "buff_type": "buffType", "pick_power": "pickPower", "axe_power": "axePower", "hammer_power": "hammerPower",
    "ammo_for": "ammoFor", "armor_slot": "armorSlot",
    "runtime_family": "runtimeFamily", "weapon_family": "weaponFamily", "projectile_family": "projectileFamily",
    "self_lock": "selfLockTicks", "self_lock_ticks": "selfLockTicks", "miss_punish": "missPunish",
    "damage_multiplier": "damageMultiplier", "pull_strength": "pullStrength", "debuff_hint": "debuffHint",
    "light_strength": "lightStrength", "light_color": "lightColorName", "color": "lightColorName",
    "safe_tile_only": "safeTileOnly", "cooldown": "cooldownTicks", "cooldown_ticks": "cooldownTicks",
    "consume_chance": "consumeChancePercent", "consume_chance_percent": "consumeChancePercent",
}
STRUCTURAL_INTISH_PARAM_FIELDS = INT_FIELDS | {"damage", "useAnimation", "maxStack", "defense", "rarity", "value", "chainCount", "count"}


def _try_parse_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return value


def _canonical_structural_key(key: Any) -> str:
    raw = str(key or "").strip()
    if not raw:
        return raw
    norm = _norm_name(raw)
    return STRUCTURAL_NUMERIC_PARAM_ALIASES.get(norm, raw)


def _structural_scalar(value: Any, key: str = "") -> Any:
    if isinstance(value, str):
        text = value.strip()
        lower = text.lower()
        if lower in {"true", "yes", "y", "on"}:
            return True
        if lower in {"false", "no", "n", "off"}:
            return False
        # Code-only repair for obvious numeric strings such as "24", "24 ticks",
        # "3 shots", "0.35". This preserves authored numbers instead of asking
        # the LLM to rewrite an otherwise good item.
        m = re.match(r"^[+\-]?(?:\d+(?:\.\d*)?|\.\d+)", text.replace(",", "."))
        if m and (key in STRUCTURAL_INTISH_PARAM_FIELDS or key.endswith("Ticks") or any(ch.isdigit() for ch in text)):
            try:
                x = float(m.group(0))
                if math.isfinite(x):
                    if key in STRUCTURAL_INTISH_PARAM_FIELDS or key.endswith("Ticks"):
                        return int(round(x))
                    return x
            except ValueError:
                pass
    return value


def _structural_params(raw_params: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fixes: list[dict[str, Any]] = []
    raw_params = _try_parse_jsonish(raw_params)
    if not isinstance(raw_params, dict):
        return {}, fixes
    out: dict[str, Any] = {}
    for k, v in raw_params.items():
        new_key = _canonical_structural_key(k)
        if new_key != k:
            fixes.append({"kind": "param_alias", "from": str(k), "to": new_key})
        v2 = _try_parse_jsonish(v)
        if isinstance(v2, dict):
            nested, nested_fixes = _structural_params(v2)
            v2 = nested
            fixes.extend(nested_fixes[:8])
        elif isinstance(v2, list):
            v2 = [_structural_scalar(_try_parse_jsonish(x), new_key) for x in v2]
        else:
            scalar = _structural_scalar(v2, new_key)
            if scalar is not v2 and scalar != v2:
                fixes.append({"kind": "scalar_parse", "field": new_key, "from": str(v2)[:48], "to": scalar})
            v2 = scalar
        out[new_key] = v2
    return out, fixes


def _structural_call_from_mapping_key(fn: str, value: Any) -> dict[str, Any] | None:
    norm = FN_ALIASES.get(_norm_name(fn), _norm_name(fn))
    if norm not in ENGINE_FN_CATALOG_V2:
        return None
    params, _fixes = _structural_params(value if isinstance(value, dict) else {})
    return {"fn": norm, "params": params}


def _structural_normalize_call(raw: Any, index: int) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    fixes: list[dict[str, Any]] = []
    raw = _try_parse_jsonish(raw)
    if not isinstance(raw, dict):
        return None, fixes
    # Common wrapper shapes: {"call": {...}}, {"engineCall": {...}}.
    for wrapper_key in ("call", "engineCall", "engine_call"):
        wrapped = raw.get(wrapper_key)
        if isinstance(wrapped, dict):
            inner, inner_fixes = _structural_normalize_call(wrapped, index)
            if inner is not None:
                fixes.append({"kind": "call_wrapper_unwrap", "field": wrapper_key, "index": index})
                fixes.extend(inner_fixes[:12])
                return inner, fixes
    # Mapping shorthand: {"shoot_projectile": {"shot_count": 3}}.
    if not any(k in raw for k in STRUCTURAL_RUNTIME_CALL_KEYS):
        for k, v in raw.items():
            mapped = _structural_call_from_mapping_key(str(k), v)
            if mapped is not None:
                fixes.append({"kind": "mapping_call", "from": str(k), "to": mapped["fn"], "index": index})
                return mapped, fixes
    original_fn = raw.get("fn") or raw.get("function") or raw.get("name") or raw.get("op") or raw.get("type") or raw.get("kind")
    fn = FN_ALIASES.get(_norm_name(original_fn), _norm_name(original_fn))
    if original_fn and fn != _norm_name(original_fn):
        fixes.append({"kind": "fn_alias", "from": str(original_fn), "to": fn, "index": index})
    params_raw = None
    for pk in STRUCTURAL_PARAM_CONTAINER_KEYS:
        if isinstance(raw.get(pk), dict) or isinstance(raw.get(pk), str):
            params_raw = raw.get(pk)
            if pk != "params":
                fixes.append({"kind": "params_alias", "from": pk, "to": "params", "index": index})
            break
    if params_raw is None:
        params_raw = {k: v for k, v in raw.items() if k not in STRUCTURAL_RUNTIME_CALL_KEYS | STRUCTURAL_PARAM_CONTAINER_KEYS}
    params, param_fixes = _structural_params(params_raw)
    fixes.extend(param_fixes[:20])
    return {"fn": fn, "params": params}, fixes


def structural_repair_runtime_plan_inplace(data: dict[str, Any]) -> dict[str, Any]:
    """Code-only repair for crooked runtimePlan shape when authored data is present.

    This is not a design/balance layer and never reads prose to invent mechanics. It only
    preserves obvious authored parameters that were placed in old/loose shapes, so the
    LLM is not called again when numbers and abilities are already concrete.
    """
    report: dict[str, Any] = {"schema": "infini.runtime-structural-repair.v1", "applied": False, "fixes": []}
    rp = data.get("runtimePlan")
    rp = _try_parse_jsonish(rp)
    if not isinstance(rp, dict):
        for key in ("enginePlan", "runtimeAuthoring", "engineRuntimePlan", "runtime_plan", "runtime"):
            val = _try_parse_jsonish(data.get(key))
            if isinstance(val, dict):
                rp = val
                data["runtimePlan"] = rp
                report["fixes"].append({"kind": "runtime_plan_alias", "from": key, "to": "runtimePlan"})
                break
    if not isinstance(rp, dict):
        return report
    calls_raw = None
    for key in ("engineCalls", "engine_calls", "calls", "actions", "action", "call"):
        if key in rp:
            calls_raw = _try_parse_jsonish(rp.get(key))
            if key != "engineCalls":
                report["fixes"].append({"kind": "engine_calls_alias", "from": key, "to": "engineCalls"})
            break
    if calls_raw is None:
        # Mapping shorthand at runtimePlan level: {"shoot_projectile": {...}}.
        mapped_calls = []
        for k, v in list(rp.items()):
            mapped = _structural_call_from_mapping_key(str(k), v)
            if mapped is not None:
                mapped_calls.append(mapped)
                report["fixes"].append({"kind": "runtime_plan_mapping_call", "from": str(k), "to": mapped["fn"]})
        calls_raw = mapped_calls if mapped_calls else rp.get("engineCalls")
    if isinstance(calls_raw, dict):
        mapped = []
        if any(k in calls_raw for k in STRUCTURAL_RUNTIME_CALL_KEYS):
            mapped = [calls_raw]
            report["fixes"].append({"kind": "single_call_object_to_list"})
        else:
            for k, v in calls_raw.items():
                call = _structural_call_from_mapping_key(str(k), v)
                if call is not None:
                    mapped.append(call)
            if mapped:
                report["fixes"].append({"kind": "engine_calls_mapping_to_list", "count": len(mapped)})
        calls_raw = mapped
    if not isinstance(calls_raw, list):
        return report
    out = []
    for i, raw in enumerate(calls_raw):
        call, fixes = _structural_normalize_call(raw, i)
        if call is not None:
            out.append(call)
        report["fixes"].extend(fixes[:24])
    if out:
        rp["engineCalls"] = out
        data["runtimePlan"] = rp
    # De-duplicate noisy identical fixes for compact debug.
    compact = []
    seen = set()
    for row in report["fixes"]:
        key = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        if key not in seen:
            compact.append(row)
            seen.add(key)
    report["fixes"] = compact[:48]
    report["applied"] = bool(report["fixes"])
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
    "STRUCTURAL_RUNTIME_CALL_KEYS",
    "STRUCTURAL_PARAM_CONTAINER_KEYS",
    "STRUCTURAL_NUMERIC_PARAM_ALIASES",
    "STRUCTURAL_INTISH_PARAM_FIELDS",
    *['_try_parse_jsonish', '_canonical_structural_key', '_structural_scalar', '_structural_params', '_structural_call_from_mapping_key', '_structural_normalize_call', 'structural_repair_runtime_plan_inplace', 'find_call', 'all_calls', '_first_non_empty', '_merged_params', '_select_primary_shoot_call', '_call_by_index', '_recover_rejected_primary_as_swing_secondary'],
]
