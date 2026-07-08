from __future__ import annotations

import json
from typing import Any

from infini_local.core.result_models import RuntimeCompileResult
from infini_local.core.runtime_authoring.common import ENGINE_RUNTIME_API_VERSION, _enum, _norm_name, _num
from infini_local.core.runtime_authoring.compiler import compile_runtime_plan_to_genome_patch
from infini_local.core.runtime_authoring.normalize import normalize_runtime_plan_inplace, runtime_plan
from infini_local.core.runtime_authoring.schema import RUNTIME_FAMILIES
from infini_local.core.runtime_authoring.structural import all_calls, find_call
from infini_local.core.runtime_contracts import validate_runtime_contract
from infini_local.core.runtime_promise_truth import validate_runtime_promises

def runtime_plan_quality_report(data: dict[str, Any]) -> dict[str, Any]:
    rp = runtime_plan(data)
    calls = rp.get("engineCalls") if isinstance(rp.get("engineCalls"), list) else []
    fns = [str(c.get("fn")) for c in calls if isinstance(c, dict)]
    counts = {fn: fns.count(fn) for fn in sorted(set(fns))}
    return {
        "hasRuntimePlan": bool(rp),
        "callCount": len(fns),
        "functions": fns,
        "functionCounts": counts,
        "hasStats": "set_item_stats" in fns,
        "hasPrimaryAction": "shoot_projectile" in fns,
        "hasPureVfx": "spawn_contact_particles" in fns,
        "hasRealChildren": "spawn_secondary_projectiles" in fns,
        "multiCallAware": True,
    }




def runtime_plan_validation_report(data: dict[str, Any]) -> dict[str, Any]:
    """Validate authoring plan as an interface contract, not as a game-design judge."""
    normalize_runtime_plan_inplace(data)
    rp = runtime_plan(data)
    q = runtime_plan_quality_report(data)
    calls = rp.get("engineCalls") if isinstance(rp.get("engineCalls"), list) else []
    errors: list[str] = []
    warnings: list[str] = []
    fns = q.get("functions") or []
    counts = q.get("functionCounts") if isinstance(q.get("functionCounts"), dict) else {}
    if counts.get("shoot_projectile", 0) > 1:
        warnings.append("multiple compatible shoot_projectile calls supplied; current adapter aggregates compatible calls and rejects incompatible extras")
    if counts.get("set_item_stats", 0) > 1:
        warnings.append("multiple set_item_stats calls supplied; current adapter merges later non-empty stat fields over earlier ones")
    if not rp:
        errors.append("missing runtimePlan")
    elif not calls:
        errors.append("runtimePlan.engineCalls has no accepted executable calls")
    norm = rp.get("_normalization") if isinstance(rp.get("_normalization"), dict) else {}
    if norm.get("droppedCalls"):
        warnings.append("some engineCalls were dropped as unknown/non-object")
    if norm.get("rejectedEngineCalls"):
        warnings.append("some engineCalls were hard-rejected by safety policy")
    if "state_meter" in fns or "triggered_action" in fns:
        warnings.append("state_meter/triggered_action are preserved as authored runtime state intent; current gameplay requires concrete executable calls too")
    combatish = str(data.get("category") or data.get("gameplay", {}).get("kind") or "").lower() in {"weapon", "summon"} or bool((data.get("attack") or {}).get("enabled") if isinstance(data.get("attack"), dict) else False)
    if combatish:
        if "set_item_stats" not in fns:
            errors.append("combat result lacks set_item_stats")
        if "shoot_projectile" not in fns:
            errors.append("combat result lacks a primary executable action; visual trail is not executable combat")
        else:
            compiled_patch = compile_runtime_plan_to_genome_patch(data)
            runtime_error = _norm_name(compiled_patch.get("runtimeContractError"))
            if runtime_error:
                errors.append("primary executable action did not compile: " + runtime_error)
            if runtime_error == "primary_attack_requires_runtimefamily" or not _norm_name(compiled_patch.get("runtimeFamily")) or _norm_name(compiled_patch.get("runtimeFamily")) == "none":
                errors.append("combat primary action lacks an executable runtimeFamily")
    for secondary in all_calls(rp, "spawn_secondary_projectiles"):
        count = _num(secondary.get("count"), 0) or 0
        trigger = _norm_name(secondary.get("trigger"))
        if count <= 0:
            warnings.append("spawn_secondary_projectiles present with count<=0")
        if count > 8:
            warnings.append("secondary projectile count exceeds executable adapter range; runtime will clamp")
        if trigger not in {"on_hit", "hit", ""}:
            warnings.append("secondary projectile trigger is not executable in v0.4.13 adapter; use on_hit or it will be rejected")
    stats = find_call(rp, "set_item_stats")
    result_kind = _norm_name(stats.get("resultKind"))
    max_stack = _num(stats.get("maxStack"), 0) or 0
    craft_yield = _num(stats.get("craftYield"), 0) or 0
    if result_kind == "ammo" and max(max_stack, craft_yield) < 25:
        warnings.append("ammo output has low stack/yield; playable ammo should usually output 25+")
    hit = find_call(rp, "apply_on_hit_effect")
    if hit:
        onhit = _norm_name(hit.get("onHit"))
        aoe = _num(hit.get("aoeRadiusTiles"), 0) or 0
        if onhit in {"burst", "starburst", "blackhole", "radial_beams", "mini_missiles", "vortex_spawn"} and aoe > 10:
            warnings.append("impact AoE exceeds executable range; runtime will clamp")
    contract_validation = validate_runtime_contract(data, compile_runtime_plan_to_genome_patch(data) if rp else {})
    warnings.extend(contract_validation.get("warnings") or [])
    return {
        "api": ENGINE_RUNTIME_API_VERSION,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "quality": q,
        "normalization": norm,
    }


def _authored_field_map(data_or_plan: dict[str, Any]) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Map compiled field names to the engine call that explicitly authored them."""
    rp = data_or_plan if isinstance(data_or_plan.get("engineCalls"), list) else runtime_plan(data_or_plan)
    authored: dict[str, str] = {}
    authored_by_fn: dict[str, list[str]] = {}
    maps: dict[str, dict[str, str]] = {
        "set_item_stats": {
            "resultKind": "resultKind",
            "damageClass": "damageClass",
            "damage": "damage",
            "useTimeTicks": "useTimeTicks",
            "maxStack": "maxStack",
            "consumable": "consumable",
            "rarity": "rarity",
            "value": "value",
            "manaCost": "manaCost",
            "craftYield": "craftYield",
            "defense": "defense",
        },
        "shoot_projectile": {
            "runtimeFamily": "runtimeFamily",
            "delivery": "delivery",
            "movement": "movement",
            "useStyleCode": "useStyleCode",
            "hideUseGraphic": "hideUseGraphic",
            "disableItemMeleeHitbox": "disableItemMeleeHitbox",
            "ownerHitCheck": "ownerHitCheck",
            "channelUse": "channelUse",
            "speed": "speed",
            "rangeTiles": "rangeTiles",
            "range": "rangeTiles",
            "lifetimeTicks": "lifetimeTicks",
            "lifetime": "lifetimeTicks",
            "shotCount": "shotCount",
            "spreadRadians": "spreadRadians",
            "pierce": "pierce",
            "extraUpdates": "extraUpdates",
            "homingStrength": "homingStrength",
            "reliability": "reliability",
        },
        "spawn_secondary_projectiles": {
            "splitCount": ("splitCount", "count"),
            "maxChildProjectiles": "maxChildProjectiles",
            "secondarySpreadRadians": "secondarySpreadRadians",
            "secondaryDamageMultiplier": "secondaryDamageMultiplier",
            "secondaryLifetimeTicks": "secondaryLifetimeTicks",
            "sameTargetBias": "sameTargetBias",
            "secondaryMaterial": "secondaryMaterial",
            "secondaryProjectileShape": "secondaryProjectileShape",
            "primaryColorName": "primaryColorName",
        },
        "apply_on_hit_effect": {
            "onHit": "onHit",
            "aoeRadiusTiles": "aoeRadiusTiles",
            "chainCount": "chainCount",
            "pullStrength": "pullStrength",
            "debuffHint": "debuffHint",
            "debuffTime": "debuffTime",
        },
        "spawn_contact_particles": {
            "effect": "effect",
            "burstDustCap": "burstDustCap",
            "vfxParticleScale": "vfxParticleScale",
            "vfxMaterial": "vfxMaterial",
            "primaryColorName": "primaryColorName",
        },
        "leave_trail_or_field": {
            "trailLength": "trailLength",
            "vfxFieldLifetimeTicks": "fieldLifetimeTicks",
            "vfxFieldRadiusTiles": ("fieldRadiusTiles", "fieldRadius"),
            "fieldRadius": ("fieldRadiusTiles", "fieldRadius"),
        },
        "visual_effect_cue": {"vfxCues": "cue", "vfxCueCount": "cue"},
        "state_meter": {"runtimeState": "kind"},
        "triggered_action": {"runtimeState": "trigger"},
        "use_affordance": {
            "itemScale": "itemScale",
            "holdoutOffsetX": "holdoutOffsetX",
            "holdoutOffsetY": "holdoutOffsetY",
            "autoReuse": "autoReuse",
            "useTurn": "useTurn",
            "channelUse": "channelUse",
            "useFantasy": "useFantasy",
            "heldVisibility": "heldVisibility",
            "releaseTiming": "releaseTiming",
            "handPose": "handPose",
            "spawnStyle": "spawnStyle",
            "rotationMode": "rotationMode",
            "initialOffsetPx": "initialOffsetPx",
            "drawDuringUse": "drawDuringUse",
            "trailMode": "trailMode",
            "projectileSizePolicy": "projectileSizePolicy",
        },
    }
    calls = rp.get("engineCalls") if isinstance(rp.get("engineCalls"), list) else []
    for raw in calls:
        if not isinstance(raw, dict):
            continue
        fn = _norm_name(raw.get("fn"))
        param_obj = raw.get("params") if isinstance(raw.get("params"), dict) else raw
        if not isinstance(param_obj, dict):
            continue
        authored_keys = {str(k) for k, v in param_obj.items() if not str(k).startswith("_") and v not in (None, "", [], {})}
        for compiled_field, authored_param in maps.get(fn, {}).items():
            params = authored_param if isinstance(authored_param, tuple) else (authored_param,)
            if any(param in authored_keys for param in params):
                authored[compiled_field] = fn
                authored_by_fn.setdefault(fn, []).append(compiled_field)
    authored_by_fn = {fn: sorted(set(fields)) for fn, fields in authored_by_fn.items()}
    return authored, authored_by_fn


def runtime_plan_provenance_report(data: dict[str, Any], patch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Explain authored-vs-applied runtime fields so VFX is not confused with gameplay."""
    normalize_runtime_plan_inplace(data)
    rp = runtime_plan(data)
    patch = patch or compile_runtime_plan_to_genome_patch(data)
    calls = rp.get("engineCalls") if isinstance(rp.get("engineCalls"), list) else []
    fns = [str(c.get("fn") or "") for c in calls if isinstance(c, dict)]
    authored_sources, authored_by_fn = _authored_field_map(rp)

    field_sources: dict[str, str] = {}
    authored_fields: dict[str, bool] = {}
    for field in (patch or {}):
        if field in authored_sources:
            field_sources[field] = authored_sources[field]
            authored_fields[field] = True
        else:
            field_sources[field] = "runtime_compiler_default"
            authored_fields[field] = False
    for field, source in authored_sources.items():
        field_sources.setdefault(field, source)
        authored_fields.setdefault(field, True)

    # Alias view requested by the debug contract: both compiled names and compact names
    # point to the same authoring fn when present.
    alias_pairs = {
        "range": "rangeTiles",
        "lifetime": "lifetimeTicks",
        "fieldRadius": "vfxFieldRadiusTiles",
    }
    for alias, compiled_field in alias_pairs.items():
        if compiled_field in field_sources:
            field_sources.setdefault(alias, field_sources[compiled_field])
            authored_fields.setdefault(alias, authored_fields.get(compiled_field, False))

    split = int(_num((patch or {}).get("splitCount"), 0) or 0)
    max_child = int(_num((patch or {}).get("maxChildProjectiles"), 0) or 0)
    burst_cap = int(_num((patch or {}).get("burstDustCap"), 0) or 0)
    secondary_calls = all_calls(rp, "spawn_secondary_projectiles")
    particle_calls = all_calls(rp, "spawn_contact_particles")
    trail_calls = all_calls(rp, "leave_trail_or_field")
    normalized_calls = [
        {"index": c.get("_index"), "fn": c.get("fn"), "paramKeys": sorted(list((c.get("params") or {}).keys())) if isinstance(c.get("params"), dict) else []}
        for c in calls if isinstance(c, dict)
    ]
    child_onhits = {"chain", "lightning_arc", "mini_missiles", "vortex_spawn", "radial_beams", "starburst", "starfall", "spore_cloud"}
    onhit = _norm_name((patch or {}).get("onHit"))
    effect_child_count = 0
    if onhit in {"chain", "lightning_arc"}:
        effect_child_count = int(_num((patch or {}).get("chainCount"), 0) or 0)
    elif onhit in child_onhits:
        effect_child_count = split if split > 0 else int(_num((patch or {}).get("maxChildProjectiles"), 0) or 0)
    norm = rp.get("_normalization", {}) if isinstance(rp.get("_normalization"), dict) else {}
    unsupported: list[Any] = []
    for key in ("rejectedEngineCalls", "rejectedPrimaryCalls", "rejectedSecondaryCalls", "rejectedTrailCalls"):
        values = norm.get(key) if key in norm else (patch or {}).get(key)
        if isinstance(values, list):
            unsupported.extend(values)
    future_disabled = []
    if (patch or {}).get("runtimeState"):
        future_disabled.append({"field": "runtimeState", "reason": "preserved_authored_intent_not_executed"})
    return {
        "api": ENGINE_RUNTIME_API_VERSION,
        "engineFunctions": fns,
        "normalizedCalls": normalized_calls,
        "authoredFields": authored_fields,
        "authoredByFunction": authored_by_fn,
        "gameplayChildren": {
            "enabled": (split > 0 and max_child > 0) or effect_child_count > 0,
            "source": "spawn_secondary_projectiles" if split > 0 else ("apply_on_hit_effect" if effect_child_count > 0 else "none"),
            "authoredCallCount": len(secondary_calls),
            "compiledFromCallIndices": (patch or {}).get("secondaryCallIndices", []),
            "splitCount": split,
            "onHit": onhit,
            "onHitChildEstimate": effect_child_count,
            "maxChildProjectiles": max_child,
            "rejectedSecondaryCalls": (patch or {}).get("rejectedSecondaryCalls", []),
            "note": "Real gameplay child projectiles come from spawn_secondary_projectiles or child-producing apply_on_hit_effect values. VFX motes are separate renderer slots."
        },
        "pureVfx": {
            "enabled": "spawn_contact_particles" in fns or "leave_trail_or_field" in fns or burst_cap > 0,
            "source": "spawn_contact_particles" if "spawn_contact_particles" in fns else ("leave_trail_or_field" if "leave_trail_or_field" in fns else "runtime_compiler_default"),
            "authoredCallCount": len(particle_calls) + len(trail_calls),
            "burstDustCap": burst_cap,
            "trailLength": (patch or {}).get("trailLength", 0),
            "fieldRadius": (patch or {}).get("vfxFieldRadiusTiles", 0),
            "material": (patch or {}).get("vfxMaterial", ""),
            "note": "Pure VFX/dust/trails do not imply damaging child projectiles."
        },
        "unsupported": unsupported[:24],
        "futureDisabled": future_disabled,
        "fieldSources": field_sources,
        "normalization": norm,
    }

def compiled_runtime_contract(data: dict[str, Any], patch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compact executable output for server/debug: this is what the runtime receives."""
    normalize_runtime_plan_inplace(data)
    patch = patch or compile_runtime_plan_to_genome_patch(data)
    rp = runtime_plan(data)
    q = runtime_plan_quality_report(data)
    out = {
        "api": ENGINE_RUNTIME_API_VERSION,
        "compiler": "runtime_plan_to_attack_spec",
        "executableFields": dict(patch),
        "functionCounts": q.get("functionCounts", {}),
        "primaryCall": (rp.get("engineCalls") or [{}])[0] if isinstance(rp.get("engineCalls"), list) and rp.get("engineCalls") else {},
        "notes": [
            "runtimeFamily is required for executable attacks; only tiny unambiguous family-field repair is allowed",
            "splitCount/maxChildProjectiles represent gameplay children only, not VFX motes",
            "state_meter/triggered_action are preserved as explicit authored intent; they do not spawn bosses/NPCs/mobs and do not execute unsupported gameplay by prose",
            "runtimeArchetype/runtimeContract are data contracts; unsupported families are preserved as intent, not executed magically",
        ],
    }
    if isinstance(data.get("runtimeArchetype"), dict):
        out["runtimeArchetype"] = data.get("runtimeArchetype")
    if isinstance(data.get("runtimeContract"), dict):
        out["runtimeContract"] = data.get("runtimeContract")
    if isinstance(patch.get("archetypeCompiler"), dict):
        out["archetypeCompiler"] = patch.get("archetypeCompiler")
    debug = data.get("debug") if isinstance(data.get("debug"), dict) else {}
    promise_truth = debug.get("runtimePromiseTruth") if isinstance(debug, dict) else None
    if isinstance(promise_truth, str) and promise_truth.strip().startswith("{"):
        try:
            out["runtimePromiseTruth"] = json.loads(promise_truth)
        except (json.JSONDecodeError, TypeError):
            pass
    return out


def compile_runtime_plan_to_genome_result(data: dict[str, Any]) -> dict[str, Any]:
    patch = compile_runtime_plan_to_genome_patch(data)
    contract_validation = validate_runtime_contract(data, patch)
    promise_truth = validate_runtime_promises(data, patch)
    validation = runtime_plan_validation_report(data)
    validation["warnings"] = list(dict.fromkeys((validation.get("warnings") or []) + (contract_validation.get("warnings") or []) + (promise_truth.get("warnings") or [])))
    provenance = runtime_plan_provenance_report(data, patch)
    model = RuntimeCompileResult(
        patch=patch,
        provenance=provenance,
        clamps=[],
        errors=list(validation.get("errors") or []),
    )
    result = model.to_dict()
    # Backwards-compatible debug payload used by older tests/tools.
    result.update({
        "compiled": compiled_runtime_contract(data, patch),
        "validation": validation,
        "quality": runtime_plan_quality_report(data),
        "runtimeContractValidation": contract_validation,
        "runtimePromiseTruth": promise_truth,
    })
    return result


def infer_attack_pattern_from_runtime(genome: dict[str, Any], damage_class: str = "generic") -> str:
    delivery = _norm_name(genome.get("delivery"))
    runtime_family = _enum(_norm_name(genome.get("runtimeFamily")), RUNTIME_FAMILIES, "none")
    movement = _norm_name(genome.get("movement"))
    onhit = _norm_name(genome.get("onHit"))
    damage_class = _norm_name(damage_class)
    if movement in {"orbit", "vortex_orb", "blackhole_pull"}:
        return "orbiting_projectile"
    if movement == "expanding_wave" or onhit in {"aura_pulse", "spore_cloud", "blackhole"}:
        return "field_trap"
    if movement == "gravity_arc" and runtime_family in {"cast", "summon"}:
        return "falling_projectile"
    if runtime_family == "thrust":
        return "spear_thrust"
    if runtime_family == "flail" or movement == "flail_tether":
        return "flail_tether"
    if runtime_family == "yoyo" or movement == "yoyo_hover":
        return "yoyo_hover"
    if runtime_family == "whip" or movement == "whip_lash":
        return "whip_lash"
    if runtime_family == "swing":
        return "beam_slash" if movement in {"phase", "expanding_wave"} else "slash_holdout"
    if movement in {"phase", "accelerate"} and runtime_family in {"cast", "shoot"}:
        return "laser_beam" if damage_class == "magic" or runtime_family == "cast" else "thrown_simple"
    # Child-producing onHit values are executed by OnHitCode. They must not force the
    # animation archetype to thrown_simple; runtime family/source identity wins.
    if runtime_family == "cast" or damage_class == "magic":
        return "magic_projectile"
    if runtime_family == "summon" or damage_class == "summon":
        return "summon_projectile"
    if runtime_family == "shoot" or damage_class == "ranged":
        return "ranged_projectile"
    if runtime_family in {"throw", "returning"}:
        return "thrown_simple"
    return "thrown_simple"

__all__ = ['runtime_plan_quality_report', 'runtime_plan_validation_report', '_authored_field_map', 'runtime_plan_provenance_report', 'compiled_runtime_contract', 'compile_runtime_plan_to_genome_result', 'infer_attack_pattern_from_runtime']
