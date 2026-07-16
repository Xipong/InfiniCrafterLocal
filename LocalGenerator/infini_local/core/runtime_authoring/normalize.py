from __future__ import annotations

import re
from typing import Any

from infini_local.core.runtime_authoring.common import ENGINE_RUNTIME_API_VERSION, _clamp, _norm_name
from infini_local.core.runtime_authoring.schema import (
    ENGINE_FN_CATALOG_V2,
    FORBIDDEN_WORLD_ENTITY_FAMILIES,
    FORBIDDEN_WORLD_ENTITY_FN_NAMES,
    SAFE_SUMMON_FAMILIES,
    TRIGGERED_ACTION_KINDS,
    TRIGGERED_ACTION_TRIGGERS,
)
from infini_local.core.runtime_authoring.semantics import _expand_semantic_runtime_call

def _forbidden_world_entity_rejection(raw: dict[str, Any], fn: str, params: dict[str, Any], index: int) -> dict[str, Any] | None:
    """Hard safety boundary: generated items may not spawn bosses/NPCs/mobs.

    Minions/sentries/light pets are projectile-owned runtime concepts; world NPC/boss/mob
    creation is not part of UnlimitedCraft authoring and is rejected rather than downgraded.
    """
    norm_fn = _norm_name(fn)
    if norm_fn in FORBIDDEN_WORLD_ENTITY_FN_NAMES:
        return {"index": index, "fn": fn, "reason": "forbidden_world_entity_spawn", "policy": "boss_npc_mob_spawn_disabled"}
    if norm_fn == "spawn_temporary_helper_projectile":
        family = _norm_name(params.get("family") or params.get("entity") or params.get("kind") or params.get("mob") or params.get("npc"))
        if family and family not in SAFE_SUMMON_FAMILIES:
            if family in FORBIDDEN_WORLD_ENTITY_FAMILIES or any(x in family for x in ("boss", "npc", "mob", "enemy", "monster")):
                return {"index": index, "fn": fn, "family": family, "reason": "forbidden_world_entity_spawn", "policy": "temporary_helper_projectiles_only"}
    if norm_fn == "triggered_action":
        action = _norm_name(params.get("action") or params.get("fn") or params.get("effect"))
        if action in FORBIDDEN_WORLD_ENTITY_FN_NAMES or any(x in action for x in ("boss", "npc", "mob", "enemy", "monster")):
            return {"index": index, "fn": fn, "action": action, "reason": "forbidden_world_entity_spawn", "policy": "triggered_actions_cannot_spawn_world_entities"}
    return None


def _compile_state_meter_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, call in enumerate(calls):
        raw_id = _norm_name(call.get("id") or call.get("meterId") or call.get("name") or f"meter_{i+1}")
        meter_id = re.sub(r"[^a-z0-9_]+", "_", raw_id)[:32].strip("_") or f"meter_{i+1}"
        if meter_id in seen:
            meter_id = f"{meter_id}_{i+1}"[:32]
        seen.add(meter_id)
        row = {
            "id": meter_id,
            "label": str(call.get("label") or call.get("name") or meter_id)[:48],
            "maxValue": int(_clamp(call.get("maxValue"), "maxValue", 3) or 3),
            "initialValue": int(_clamp(call.get("initialValue"), "initialValue", 0) or 0),
            "gainOnUse": int(_clamp(call.get("gainOnUse"), "gainOnUse", 0) or 0),
            "gainOnHit": int(_clamp(call.get("gainOnHit"), "gainOnHit", 0) or 0),
            "gainOnKill": int(_clamp(call.get("gainOnKill"), "gainOnKill", 0) or 0),
            "spendOnUse": int(_clamp(call.get("spendOnUse"), "spendOnUse", 0) or 0),
            "spendOnAltUse": int(_clamp(call.get("spendOnAltUse"), "spendOnAltUse", 0) or 0),
            "decayPerSecond": round(_clamp(call.get("decayPerSecond"), "decayPerSecond", 0) or 0, 3),
            "cooldownTicks": int(_clamp(call.get("cooldownTicks"), "cooldownTicks", 0) or 0),
            "modeCount": int(_clamp(call.get("modeCount"), "modeCount", 0) or 0),
        }
        if row["initialValue"] > row["maxValue"]:
            row["initialValue"] = row["maxValue"]
        out.append(row)
        if len(out) >= 4:
            break
    return out


def _compile_triggered_action_calls(calls: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    out: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for call in calls:
        trigger = _norm_name(call.get("trigger"))
        action = _norm_name(call.get("action") or call.get("kind") or call.get("effect"))
        idx = call.get("_index")
        if trigger not in TRIGGERED_ACTION_TRIGGERS:
            rejected.append({"index": idx, "fn": "triggered_action", "trigger": trigger, "reason": "unsupported_trigger_intent"})
            continue
        if action not in TRIGGERED_ACTION_KINDS:
            rejected.append({"index": idx, "fn": "triggered_action", "action": action, "reason": "unsupported_action_intent"})
            continue
        if any(x in action for x in ("boss", "npc", "mob", "enemy", "monster")):
            rejected.append({"index": idx, "fn": "triggered_action", "action": action, "reason": "forbidden_world_entity_spawn"})
            continue
        row = {
            "trigger": trigger,
            "action": action,
            "meterId": re.sub(r"[^a-z0-9_]+", "_", _norm_name(call.get("meterId") or call.get("id")))[:32],
            "requiredValue": int(_clamp(call.get("requiredValue"), "requiredValue", 0) or 0),
            "spendValue": int(_clamp(call.get("spendValue"), "spendValue", 0) or 0),
            "cooldownTicks": int(_clamp(call.get("cooldownTicks"), "cooldownTicks", 0) or 0),
            "note": str(call.get("note") or "")[:80],
        }
        out.append(row)
        if len(out) >= 8:
            break
    return out, rejected


def normalize_runtime_plan_inplace(data: dict[str, Any]) -> dict[str, Any]:
    """Canonicalize runtimePlan shape without making design choices."""
    rp = data.get("runtimePlan") if isinstance(data.get("runtimePlan"), dict) else {}
    if not rp:
        for key in ("enginePlan", "runtimeAuthoring", "engineRuntimePlan"):
            val = data.get(key)
            if isinstance(val, dict):
                rp = val
                data["runtimePlan"] = rp
                break
    if not isinstance(rp, dict):
        return data
    calls = rp.get("engineCalls") if isinstance(rp.get("engineCalls"), list) else []
    prev_norm = rp.get("_normalization") if isinstance(rp.get("_normalization"), dict) else {}
    prev_dropped = prev_norm.get("droppedCalls") if isinstance(prev_norm.get("droppedCalls"), list) else []
    out = []
    dropped = list(prev_dropped)
    prev_rejected = prev_norm.get("rejectedEngineCalls") if isinstance(prev_norm.get("rejectedEngineCalls"), list) else []
    rejected = list(prev_rejected)
    for i, raw in enumerate(calls):
        if not isinstance(raw, dict):
            dropped.append({"index": i, "reason": "not_object", "rawType": type(raw).__name__})
            continue
        current_fn = str(raw.get("fn") or "").strip()
        call_id = str(raw.get("callId") or "").strip()
        original_fn = str(raw.get("_rawFn") or current_fn).strip()
        prior_semantic_fn = str(raw.get("_semanticFn") or "").strip()
        fn = _norm_name(current_fn)
        params = raw.get("params") if isinstance(raw.get("params"), dict) else {}
        hard_reject = _forbidden_world_entity_rejection(raw, fn or original_fn, params, i)
        if hard_reject:
            rejected.append(hard_reject)
            continue
        if fn not in ENGINE_FN_CATALOG_V2:
            dropped.append({"index": i, "reason": "unknown_fn", "fn": original_fn})
            continue
        for expanded_fn, expanded_params in _expand_semantic_runtime_call(fn, params):
            hard_reject = _forbidden_world_entity_rejection(raw, expanded_fn, expanded_params, i)
            if hard_reject:
                rejected.append(hard_reject)
                continue
            if expanded_fn not in ENGINE_FN_CATALOG_V2:
                dropped.append({"index": i, "reason": "semantic_expand_unknown_fn", "fn": expanded_fn, "from": original_fn})
                continue
            row = {"fn": expanded_fn, "params": expanded_params, "_index": i, "_rawFn": original_fn}
            if call_id:
                row["callId"] = call_id
            if prior_semantic_fn:
                row["_semanticFn"] = prior_semantic_fn
            elif expanded_fn != fn:
                row["_semanticFn"] = fn
            out.append(row)
    rp["engineCalls"] = out
    rp["_normalization"] = {"api": ENGINE_RUNTIME_API_VERSION, "inputCallCount": len(calls), "acceptedCallCount": len(out), "droppedCalls": dropped[:12], "rejectedEngineCalls": rejected[:16]}
    data["runtimePlan"] = rp
    return data


def runtime_plan(data: dict[str, Any]) -> dict[str, Any]:
    rp = data.get("runtimePlan") if isinstance(data.get("runtimePlan"), dict) else {}
    return rp if isinstance(rp, dict) else {}

__all__ = ['_forbidden_world_entity_rejection', '_compile_state_meter_calls', '_compile_triggered_action_calls', 'normalize_runtime_plan_inplace', 'runtime_plan']
