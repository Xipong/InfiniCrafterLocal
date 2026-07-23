from __future__ import annotations

from typing import Any

from infini_local.core.runtime_authoring.common import ENGINE_RUNTIME_API_VERSION, _clamp, _norm_name
from infini_local.core.runtime_authoring.function_contract_registry import ENGINE_FUNCTION_CATALOG
from infini_local.core.runtime_authoring.schema import (
    FORBIDDEN_WORLD_ENTITY_FAMILIES,
    FORBIDDEN_WORLD_ENTITY_FN_NAMES,
    SAFE_SUMMON_FAMILIES,
)
from infini_local.core.runtime_authoring.semantics import _lower_typed_engine_call

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
    return None

def normalize_runtime_plan_inplace(data: dict[str, Any]) -> dict[str, Any]:
    """Canonicalize runtimePlan shape without making design choices."""
    rp = data.get("runtimePlan") if isinstance(data.get("runtimePlan"), dict) else {}
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
        fn = _norm_name(current_fn)
        params: dict[str, Any] = dict(raw.get("params") or {}) if isinstance(raw.get("params"), dict) else {}
        hard_reject = _forbidden_world_entity_rejection(raw, fn or original_fn, params, i)
        if hard_reject:
            rejected.append(hard_reject)
            continue
        if fn not in ENGINE_FUNCTION_CATALOG:
            dropped.append({"index": i, "reason": "unknown_fn", "fn": original_fn})
            continue
        for expanded_fn, expanded_params in _lower_typed_engine_call(fn, params):
            hard_reject = _forbidden_world_entity_rejection(raw, expanded_fn, expanded_params, i)
            if hard_reject:
                rejected.append(hard_reject)
                continue
            if expanded_fn not in ENGINE_FUNCTION_CATALOG:
                dropped.append({"index": i, "reason": "typed_lowering_unknown_fn", "fn": expanded_fn, "from": original_fn})
                continue
            row = {"fn": expanded_fn, "params": expanded_params, "_index": i, "_rawFn": original_fn}
            if call_id:
                row["callId"] = call_id
            out.append(row)
    rp["engineCalls"] = out
    rp["_normalization"] = {"api": ENGINE_RUNTIME_API_VERSION, "inputCallCount": len(calls), "acceptedCallCount": len(out), "droppedCalls": dropped[:12], "rejectedEngineCalls": rejected[:16]}
    data["runtimePlan"] = rp
    return data


def runtime_plan(data: dict[str, Any]) -> dict[str, Any]:
    rp = data.get("runtimePlan") if isinstance(data.get("runtimePlan"), dict) else {}
    return rp if isinstance(rp, dict) else {}

__all__ = ['_forbidden_world_entity_rejection', 'normalize_runtime_plan_inplace', 'runtime_plan']
