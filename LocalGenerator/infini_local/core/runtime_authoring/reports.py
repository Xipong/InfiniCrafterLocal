from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from infini_local.core.result_models import RuntimeCompileResult
from infini_local.core.runtime_authoring.common import ENGINE_RUNTIME_API_VERSION, _enum, _norm_name, _num
from infini_local.core.runtime_authoring.compiler import compile_runtime_plan_to_genome_patch
from infini_local.core.runtime_authoring.normalize import normalize_runtime_plan_inplace, runtime_plan
from infini_local.core.runtime_family_policy import (
    CANONICAL_RUNTIME_FAMILIES as RUNTIME_FAMILIES,
    HELD_PROJECTILE_RUNTIME_FAMILIES,
)
from infini_local.core.runtime_secondary_policy import normalize_secondary_trigger
from infini_local.core.runtime_authoring.structural import all_calls, find_call
from infini_local.core.boundary_models import runtime_plan_boundary_report



def _generated_buff_has_executable_effect(buff: dict[str, Any]) -> bool:
    mining = _num(buff.get("miningSpeedMultiplier"), 1.0)
    return bool(
        (mining is not None and abs(mining - 1.0) > 0.001)
        or (_num(buff.get("emitLightStrength"), 0) or 0) > 0
        or (_num(buff.get("oreSenseRadiusTiles"), 0) or 0) > 0
        or abs(_num(buff.get("movementSpeed"), 0) or 0) > 0.001
        or (_num(buff.get("jumpBoost"), 0) or 0) > 0
        or (_num(buff.get("manaRegen"), 0) or 0) > 0
        or (_num(buff.get("lifeRegen"), 0) or 0) > 0
    )


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


def _runtime_validation_error_details(
    errors: list[str],
    calls: list[Any],
) -> list[dict[str, Any]]:
    """Map validator-owned diagnostics back to authored calls without choosing a repair."""
    indexed_calls: list[tuple[int, dict[str, Any]]] = []
    for normalized_index, raw_call in enumerate(calls):
        if not isinstance(raw_call, dict):
            continue
        authored_index = raw_call.get("_index")
        index = authored_index if isinstance(authored_index, int) else normalized_index
        indexed_calls.append((index, raw_call))

    details: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for message in errors:
        text = str(message)
        indexed_match = re.search(r"engineCalls\.(\d+)(?:\.params\.([A-Za-z0-9_.]+))?", text)
        selected: tuple[int, dict[str, Any]] | None = None
        field = ""
        if indexed_match:
            wanted_index = int(indexed_match.group(1))
            selected = next((row for row in indexed_calls if row[0] == wanted_index), None)
            field = str(indexed_match.group(2) or "")
        if selected is None:
            named = [
                row
                for row in indexed_calls
                if str(row[1].get("fn") or "").strip()
                and str(row[1].get("fn") or "").strip() in text
            ]
            if len(named) == 1:
                selected = named[0]
        if selected is None and "primary action" in text:
            selected = next(
                (row for row in indexed_calls if str(row[1].get("fn") or "") == "shoot_projectile"),
                None,
            )
        if selected is None:
            continue
        if not field:
            explicit_match = re.search(r"requires explicit ([A-Za-z0-9_.]+)", text)
            field = str(explicit_match.group(1) or "") if explicit_match else ""
        index, call = selected
        call_id = str(call.get("_callId") or call.get("callId") or "").strip()
        fn = str(call.get("_rawFn") or call.get("fn") or "").strip()
        path = f"$.runtimePlan.engineCalls[{index}]"
        if field:
            path += f".params.{field}"
        identity = (call_id, path, text)
        if identity in seen:
            continue
        seen.add(identity)
        details.append({
            "kind": "runtime_validation",
            "path": path,
            "callId": call_id,
            "fn": fn,
            "reason": text,
        })
    return details


def runtime_plan_validation_report(data: dict[str, Any]) -> dict[str, Any]:
    """Validate authoring plan as an interface contract, not as a game-design judge.

    The strict per-function boundary applies to raw authoring calls.  Semantic
    normalization deliberately lowers high-level calls such as deploy_sentry to
    canonical shoot_projectile rows with compiler-owned fields; those rows must
    not be reinterpreted as raw model output on a second validation pass.
    """
    before = runtime_plan(data)
    already_canonical = isinstance(before.get("_normalization"), dict)
    boundary = (
        {"ok": True, "errors": [], "unknownParams": [], "typedCalls": [], "mode": "canonical_already_normalized"}
        if already_canonical
        else runtime_plan_boundary_report(data)
    )
    normalize_runtime_plan_inplace(data)
    rp = runtime_plan(data)
    q = runtime_plan_quality_report(data)
    calls_candidate = rp.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    errors: list[str] = list(boundary.get("errors") or [])
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
    stats_kind = _norm_name(find_call(rp, "set_item_stats").get("resultKind"))
    plan_kind = _norm_name(rp.get("resultKind"))
    authored_category = _norm_name(data.get("category"))
    if plan_kind and stats_kind and plan_kind != stats_kind:
        errors.append(f"runtimePlan.resultKind={plan_kind} disagrees with set_item_stats.resultKind={stats_kind}")
    runtime_kind = stats_kind or plan_kind
    projected_category = "weapon" if runtime_kind == "consumable_weapon" else runtime_kind
    if authored_category and projected_category and authored_category != projected_category:
        errors.append(
            f"category={authored_category} disagrees with canonical category={projected_category} for authored runtime resultKind={runtime_kind}"
        )
    plan_kind = runtime_kind
    combatish = (
        str(data.get("category") or data.get("gameplay", {}).get("kind") or plan_kind or "").lower() in {"weapon", "summon"}
        or bool((data.get("attack") or {}).get("enabled") if isinstance(data.get("attack"), dict) else False)
    )
    if combatish:
        if "set_item_stats" not in fns:
            errors.append("combat result lacks set_item_stats")
        if "shoot_projectile" not in fns:
            errors.append("combat result lacks a primary executable action; visual trail is not executable combat")
        else:
            compiled_patch = compile_runtime_plan_to_genome_patch(data)
            rejected_primary = compiled_patch.get("rejectedPrimaryCalls")
            if isinstance(rejected_primary, list):
                for rejection in rejected_primary:
                    if not isinstance(rejection, dict):
                        continue
                    index = rejection.get("index")
                    index_text = str(index) if isinstance(index, int) else "?"
                    delivery = str(rejection.get("delivery") or "unknown")
                    movement = str(rejection.get("movement") or "unknown")
                    errors.append(
                        "runtimePlan.engineCalls."
                        + index_text
                        + ": runtime supports one primary attack family; "
                        + f"incompatible extra primary uses delivery={delivery}, movement={movement}"
                    )
            runtime_error = _norm_name(compiled_patch.get("runtimeContractError"))
            if runtime_error:
                errors.append("primary executable action did not compile: " + runtime_error)
            if runtime_error == "primary_attack_requires_runtimefamily" or not _norm_name(compiled_patch.get("runtimeFamily")) or _norm_name(compiled_patch.get("runtimeFamily")) == "none":
                errors.append("combat primary action lacks an executable runtimeFamily")
            for field in ("delivery", "movement", "speed", "rangeTiles", "lifetimeTicks", "shotCount", "spreadRadians", "pierce"):
                if field not in compiled_patch:
                    errors.append(f"combat primary action requires explicit {field}")
            compiled_family = _norm_name(compiled_patch.get("runtimeFamily"))
            family_required: dict[str, tuple[str, ...]] = {
                "beam": ("beamWidthPx", "beamChargeTicks", "immunityCooldown"),
                "charge_release": ("chargeTicks", "chargePowerMultiplier"),
                "overhead_barrage": ("delayTicks", "secondaryDamageMultiplier", "secondaryLifetimeTicks"),
            }
            for field in family_required.get(compiled_family, ()):
                if field not in compiled_patch:
                    errors.append(f"combat runtimeFamily={compiled_family} requires explicit {field}")
            if compiled_family == "overhead_barrage" and (_num(compiled_patch.get("secondaryDamageMultiplier"), 0) or 0) <= 0:
                errors.append("combat runtimeFamily=overhead_barrage requires secondaryDamageMultiplier > 0")
            if compiled_family == "overhead_barrage":
                base_damage = _num(find_call(rp, "set_item_stats").get("damage"), 0) or 0
                child_multiplier = _num(compiled_patch.get("secondaryDamageMultiplier"), 0) or 0
                if base_damage > 0 and child_multiplier > 0 and int(base_damage * child_multiplier) < 1:
                    errors.append("combat runtimeFamily=overhead_barrage rounds to zero damage; increase damage or secondaryDamageMultiplier")
            single_runtime_families = set(HELD_PROJECTILE_RUNTIME_FAMILIES) - {"charge_release"}
            single_runtime_shots = _num(compiled_patch.get("shotCount"), None)
            if compiled_family in single_runtime_families and single_runtime_shots is not None and single_runtime_shots != 1:
                errors.append(f"combat runtimeFamily={compiled_family} requires shotCount=1; its executor owns one runtime root")
            if compiled_family in {"swing", "thrust"}:
                for secondary_call in all_calls(rp, "spawn_secondary_projectiles"):
                    if (_num(secondary_call.get("count"), 0) or 0) <= 0:
                        continue
                    has_child_body = bool(_norm_name(secondary_call.get("material")) or _norm_name(secondary_call.get("projectileShape")))
                    if not has_child_body:
                        errors.append(f"combat runtimeFamily={compiled_family} secondary projectiles require explicit material or projectileShape")
                    trigger = normalize_secondary_trigger(secondary_call.get("trigger"))
                    if compiled_family == "swing" and trigger == "on_expire":
                        errors.append("combat runtimeFamily=swing cannot execute secondary trigger=on_expire; use on_hit")
        stats_call = find_call(rp, "set_item_stats")
        for field in ("damageClass", "damage", "useTimeTicks"):
            if field not in stats_call:
                errors.append(f"combat set_item_stats requires explicit {field}")
        damage = _num(stats_call.get("damage"))
        if damage is not None and damage <= 0:
            errors.append("combat set_item_stats requires positive damage; use a non-combat resultKind for pure utility")
    for secondary in all_calls(rp, "spawn_secondary_projectiles"):
        count = _num(secondary.get("count"), 0) or 0
        trigger = normalize_secondary_trigger(secondary.get("trigger"))
        if count <= 0:
            warnings.append("spawn_secondary_projectiles present with count<=0")
        if count > 8:
            warnings.append("secondary projectile count exceeds executable adapter range; runtime will clamp")
        if not trigger:
            warnings.append("secondary projectile trigger is unsupported; use exact on_hit or on_expire")
        base_damage = _num(find_call(rp, "set_item_stats").get("damage"), 0) or 0
        child_multiplier = _num(secondary.get("damageMultiplier"), 0) or 0
        if combatish and count > 0 and base_damage > 0 and child_multiplier > 0 and int(base_damage * child_multiplier) < 1:
            errors.append("spawn_secondary_projectiles rounds to zero damage; increase damage or damageMultiplier")
    particle_materials = {
        _norm_name(call.get("material"))
        for call in all_calls(rp, "spawn_contact_particles")
        if (_num(call.get("amount"), 0) or 0) > 0 and _norm_name(call.get("material")) not in {"", "none"}
    }
    if len(particle_materials) > 1:
        errors.append("spawn_contact_particles requires one exact material per runtime plan")
    for particle_call in all_calls(rp, "spawn_contact_particles"):
        material = _norm_name(particle_call.get("material"))
        effect_name = _norm_name(particle_call.get("effect"))
        if (_num(particle_call.get("amount"), 0) or 0) > 0 and material not in {"", "none"} and effect_name not in {"", "none", "dust"}:
            errors.append("spawn_contact_particles material is executable only with effect=none|dust")
    stats = find_call(rp, "set_item_stats")
    result_kind = _norm_name(stats.get("resultKind"))
    max_stack = _num(stats.get("maxStack"), 0) or 0
    craft_yield = _num(stats.get("craftYield"), 0) or 0
    has_primary = bool(all_calls(rp, "shoot_projectile"))
    if result_kind in {"weapon", "consumable_weapon"} and not has_primary:
        errors.append(f"{result_kind} result requires a primary executable action")
    if result_kind == "accessory" and not all_calls(rp, "accessory_effect"):
        errors.append("accessory result requires accessory_effect")
    if result_kind == "armor" and not all_calls(rp, "armor_effect"):
        errors.append("armor result requires armor_effect")
    if result_kind in {"ammo", "consumable_weapon"}:
        if max_stack <= 0 or craft_yield <= 0:
            errors.append(f"{result_kind} result requires explicit positive maxStack and craftYield")
        elif max(max_stack, craft_yield) < 25:
            warnings.append("ammo output has low stack/yield; playable ammo should usually output 25+")
    ammo_behavior = find_call(rp, "ammo_behavior")
    ammo_for = _norm_name(stats.get("ammoFor") or ammo_behavior.get("ammoFor"))
    if result_kind == "ammo":
        if ammo_for not in {"arrow", "bullet"}:
            errors.append("ammo result requires vanilla arrow or bullet identity; custom projectile stacks use consumable_weapon")
        if has_primary:
            errors.append("actual ammo cannot author a generated primary action; use consumable_weapon or weapon")
        if "damageClass" not in stats or not str(stats.get("damageClass") or "").strip():
            errors.append("actual ammo requires explicit damageClass")
        if "damage" not in stats or (_num(stats.get("damage"), -1) or 0) < 0:
            errors.append("actual ammo requires explicit non-negative damage")
    hit = find_call(rp, "apply_on_hit_effect")
    if hit:
        onhit = _norm_name(hit.get("onHit"))
        aoe = _num(hit.get("aoeRadiusTiles"), 0) or 0
        if onhit in {"burst", "starburst", "blackhole", "radial_beams", "mini_missiles", "vortex_spawn"} and aoe > 10:
            warnings.append("impact AoE exceeds executable range; runtime will clamp")
        buff_onhits = {"chain", "burn", "frostburn", "poison", "shadowflame", "bleed", "spore_cloud", "lightning_arc", "slow"}
        if onhit in buff_onhits and (_num(hit.get("debuffTime"), 0) or 0) <= 0:
            errors.append(f"apply_on_hit_effect onHit={onhit} requires explicit debuffTime")
        child_projectile_onhits = {
            "split", "chain", "starburst", "spore_cloud", "mini_missiles",
            "vortex_spawn", "radial_beams", "lightning_arc", "overhead_barrage",
        }
        if onhit in child_projectile_onhits:
            authored_child_count = (
                _num(hit.get("chainCount"), 0) or _num(hit.get("count"), 0) or 0
                if onhit in {"chain", "lightning_arc"}
                else _num(hit.get("count"), 0) or 0
            )
            if authored_child_count <= 0:
                errors.append(f"apply_on_hit_effect onHit={onhit} requires explicit count > 0")
            child_multiplier = _num(hit.get("secondaryDamageMultiplier"), 0) or 0
            if child_multiplier <= 0:
                errors.append(f"apply_on_hit_effect onHit={onhit} requires explicit secondaryDamageMultiplier > 0")
            if (_num(hit.get("secondaryLifetimeTicks"), 0) or 0) <= 0:
                errors.append(f"apply_on_hit_effect onHit={onhit} requires explicit secondaryLifetimeTicks")
            base_damage = _num(stats.get("damage"), 0) or 0
            if base_damage > 0 and child_multiplier > 0 and int(base_damage * child_multiplier) < 1:
                errors.append(f"apply_on_hit_effect onHit={onhit} rounds to zero damage; increase damage or secondaryDamageMultiplier")

    for use_effect in all_calls(rp, "apply_player_effect_on_use"):
        raw_buffs = use_effect.get("buffs") if isinstance(use_effect.get("buffs"), list) else []
        if use_effect.get("buffType") not in (None, ""):
            raw_buffs = [*raw_buffs, {"buffType": use_effect.get("buffType"), "buffTime": use_effect.get("buffTime")}]
        for buff in raw_buffs:
            if isinstance(buff, dict) and (_num(buff.get("buffType"), 0) or 0) > 0 and (_num(buff.get("buffTime"), 0) or 0) <= 0:
                errors.append("apply_player_effect_on_use buffType requires explicit positive buffTime")
        generated = use_effect.get("generatedBuff") if isinstance(use_effect.get("generatedBuff"), dict) else {}
        if generated and (_num(generated.get("durationTicks") or use_effect.get("durationTicks"), 0) or 0) <= 0:
            errors.append("apply_player_effect_on_use generatedBuff requires explicit durationTicks")
        if generated and not _generated_buff_has_executable_effect(generated):
            errors.append("apply_player_effect_on_use generatedBuff requires at least one executable effect")

    for alt in all_calls(rp, "set_alt_use_mode"):
        mode = _norm_name(alt.get("mode"))
        mobility_mode = _norm_name(alt.get("mobilityMode"))
        generated = alt.get("generatedBuff") if isinstance(alt.get("generatedBuff"), dict) else {}
        duration = _num(generated.get("durationTicks") or alt.get("durationTicks"), 0) or 0
        if (generated or mode == "light") and duration <= 0:
            errors.append(f"set_alt_use_mode mode={mode or 'unknown'} requires explicit durationTicks")
        if mode == "generated_buff" and (not generated or not _generated_buff_has_executable_effect(generated)):
            errors.append("set_alt_use_mode mode=generated_buff requires an executable generatedBuff effect")
        if mode == "light":
            light_calls = all_calls(rp, "emit_light")
            light_strength = max((_num(call.get("strength"), 0) or 0) for call in light_calls) if light_calls else 0
            if light_strength <= 0:
                errors.append("set_alt_use_mode mode=light requires positive emit_light strength")
        if mode == "mobility" and mobility_mode not in {"recall_home", "blink_to_cursor"}:
            errors.append("set_alt_use_mode mode=mobility requires explicit mobilityMode=recall_home|blink_to_cursor")
        if mode == "mobility" and mobility_mode == "blink_to_cursor" and (_num(alt.get("rangeTiles"), 0) or 0) <= 0:
            errors.append("set_alt_use_mode blink_to_cursor requires explicit positive rangeTiles")

    for mobility in all_calls(rp, "mobility_effect"):
        mode = _norm_name(mobility.get("mode"))
        if mode not in {"recall_home", "blink_to_cursor", "blink_to_projectile_impact"}:
            errors.append("mobility_effect requires an explicit supported mobility mode")
        if mode in {"blink_to_cursor", "blink_to_projectile_impact"} and (_num(mobility.get("rangeTiles"), 0) or 0) <= 0:
            errors.append(f"mobility_effect mode={mode} requires explicit positive rangeTiles")

    for hold in all_calls(rp, "hold_item_effect"):
        generated = hold.get("generatedBuff") if isinstance(hold.get("generatedBuff"), dict) else {}
        if generated:
            hold_duration = _num(generated.get("durationTicks"), 0) or 0
            if hold_duration <= 0:
                errors.append("hold_item_effect generatedBuff requires explicit durationTicks")
            elif hold_duration < 2:
                errors.append("hold_item_effect generatedBuff durationTicks must be at least 2 ticks so the next effect phase can execute it")
            if not _generated_buff_has_executable_effect(generated):
                errors.append("hold_item_effect generatedBuff requires at least one executable effect")

    if result_kind == "tool":
        tool = find_call(rp, "tool_capability")
        if max((_num(tool.get(name), 0) or 0) for name in ("pickPower", "axePower", "hammerPower")) <= 0:
            errors.append("tool result lacks explicit executable tool_capability")
    elif result_kind == "accessory":
        accessory = find_call(rp, "accessory_effect")
        stats_obj = accessory.get("stats") if isinstance(accessory.get("stats"), dict) else {}
        if not any(value not in (None, "", 0, 0.0, False) for value in stats_obj.values()):
            errors.append("accessory result lacks explicit executable accessory_effect.stats")
    elif result_kind == "armor":
        armor = find_call(rp, "armor_effect")
        slot = _norm_name(armor.get("armorSlot") or stats.get("armorSlot"))
        armor_stats = armor.get("stats") if isinstance(armor.get("stats"), dict) else {}
        set_bonus = armor.get("setBonus") if isinstance(armor.get("setBonus"), dict) else {}
        defense = _num(armor.get("defense", stats.get("defense")), 0) or 0
        if slot not in {"head", "body", "legs"}:
            errors.append("armor result requires explicit armorSlot=head|body|legs")
        if defense <= 0 and not any(value not in (None, "", 0, 0.0, False) for value in [*armor_stats.values(), *set_bonus.values()]):
            errors.append("armor result lacks explicit defense/stat/set-bonus effect")
    elif result_kind == "potion":
        use_calls = all_calls(rp, "apply_player_effect_on_use")
        heal = max((_num(stats.get("healLife"), 0) or 0), (_num(stats.get("healMana"), 0) or 0))
        buff_type = _num(stats.get("buffType"), 0) or 0
        if heal <= 0 and buff_type <= 0 and not use_calls:
            errors.append("potion result lacks an explicit executable use effect")
    return {
        "api": ENGINE_RUNTIME_API_VERSION,
        "ok": not errors,
        "errors": errors,
        "errorDetails": _runtime_validation_error_details(errors, calls),
        "warnings": warnings,
        "quality": q,
        "normalization": norm,
        "strictBoundary": boundary,
    }


def _compiled_field_source_map() -> dict[str, dict[str, str | tuple[str, ...]]]:
    """Canonical compiled-field → authored-param provenance for engine functions."""
    return {
        "set_item_stats": {
            "resultKind": "resultKind",
            "damageClass": "damageClass",
            "damage": "damage",
            "useTimeTicks": "useTimeTicks",
            "useAnimationTicks": "useAnimationTicks",
            "knockback": "knockback",
            "autoReuse": "autoReuse",
            "maxStack": "maxStack",
            "consumable": "consumable",
            "rarity": "rarity",
            "value": "value",
            "manaCost": "manaCost",
            "craftYield": "craftYield",
            "defense": "defense",
            "healLife": "healLife",
            "healMana": "healMana",
            "buffType": "buffType",
            "buffTime": "buffTime",
            "pickPower": "pickPower",
            "axePower": "axePower",
            "hammerPower": "hammerPower",
            "ammoFor": "ammoFor",
            "slot": "armorSlot",
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
            "useTimeTicks": "useTimeTicks",
            "useAnimationTicks": "useAnimationTicks",
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
            "beamWidthPx": "beamWidthPx",
            "beamChargeTicks": "beamChargeTicks",
            "chargeTicks": "chargeTicks",
            "chargePowerMultiplier": "chargePowerMultiplier",
            "sentryPlacement": ("sentryPlacement", "placement"),
            "sentryAttackIntervalTicks": ("sentryAttackIntervalTicks", "attackIntervalTicks"),
            "sentryTargetRangeTiles": ("sentryTargetRangeTiles", "targetRangeTiles"),
            "sentryLifetimeTicks": ("sentryLifetimeTicks", "helperLifetimeTicks"),
            "secondaryProjectileShape": "secondaryProjectileShape",
            "onHit": "onHit",
            "delayTicks": "delayTicks",
            "immunityCooldown": "immunityCooldown",
            "projectileFamily": "projectileFamily",
            "weaponFamily": "weaponFamily",
            "ammoFor": "ammoFor",
            "effect": "effect",
            "projectileShape": "projectileShape",
            "projectileMotion": "projectileMotion",
            "projectileTrail": "projectileTrail",
            "projectileImpact": "projectileImpact",
            "soundUseCatalogId": "soundUseCatalogId",
            "soundImpactCatalogId": "soundImpactCatalogId",
            "soundVolume": "soundVolume",
            "soundPitch": "soundPitch",
            "soundPitchVariance": "soundPitchVariance",
            "secondaryDamageMultiplier": "secondaryDamageMultiplier",
            "secondaryLifetimeTicks": "secondaryLifetimeTicks",
        },
        "spawn_secondary_projectiles": {
            "secondaryTrigger": "trigger",
            "splitCount": ("splitCount", "count"),
            "maxChildProjectiles": ("maxChildProjectiles", "count"),
            "secondarySpreadRadians": ("secondarySpreadRadians", "spreadRadians"),
            "secondaryDamageMultiplier": ("secondaryDamageMultiplier", "damageMultiplier"),
            "secondaryLifetimeTicks": ("secondaryLifetimeTicks", "lifetimeTicks"),
            "sameTargetBias": "sameTargetBias",
            "secondaryMaterial": ("secondaryMaterial", "material"),
            "secondaryProjectileShape": ("secondaryProjectileShape", "projectileShape"),
            "primaryColorName": "primaryColorName",
        },
        "apply_on_hit_effect": {
            "onHit": "onHit",
            "aoeRadiusTiles": "aoeRadiusTiles",
            "aoeDamageRadiusPx": "aoeRadiusTiles",
            "immunityCooldown": "immunityCooldown",
            "splitCount": "count",
            "maxChildProjectiles": "count",
            "chainCount": "chainCount",
            "secondaryDamageMultiplier": "secondaryDamageMultiplier",
            "secondaryLifetimeTicks": "secondaryLifetimeTicks",
            "pullStrength": "pullStrength",
            "pullMode": "pullMode",
            "debuffHint": "debuffHint",
            "debuffTime": "debuffTime",
        },
        "tool_capability": {
            "pickPower": "pickPower",
            "axePower": "axePower",
            "hammerPower": "hammerPower",
            "miningSpeedScale": "miningSpeedScale",
        },
        "apply_player_effect_on_use": {
            "healLife": "healLife",
            "healMana": "healMana",
            "buffType": "buffType",
            "buffTime": "buffTime",
            "extraBuffs": "buffs",
            "generatedBuff.durationTicks": "generatedBuff.durationTicks",
            "generatedBuff.miningSpeedMultiplier": "generatedBuff.miningSpeedMultiplier",
            "generatedBuff.emitLightStrength": "generatedBuff.emitLightStrength",
            "generatedBuff.lightColorName": "generatedBuff.lightColorName",
            "generatedBuff.oreSenseRadiusTiles": "generatedBuff.oreSenseRadiusTiles",
            "generatedBuff.movementSpeed": "generatedBuff.movementSpeed",
            "generatedBuff.jumpBoost": "generatedBuff.jumpBoost",
            "generatedBuff.manaRegen": "generatedBuff.manaRegen",
            "generatedBuff.lifeRegen": "generatedBuff.lifeRegen",
        },
        "accessory_effect": {
            "archetype": "archetype",
            "defense": "defense",
            "maxLife": "stats.maxLife",
            "maxMana": "stats.maxMana",
            "lifeRegen": "stats.lifeRegen",
            "manaRegen": "stats.manaRegen",
            "movementSpeed": "stats.movementSpeed",
            "maxRunSpeed": "stats.maxRunSpeed",
            "jumpSpeed": "stats.jumpSpeed",
            "genericDamage": "stats.genericDamage",
            "meleeDamage": "stats.meleeDamage",
            "rangedDamage": "stats.rangedDamage",
            "magicDamage": "stats.magicDamage",
            "summonDamage": "stats.summonDamage",
            "genericCrit": "stats.genericCrit",
            "attackSpeed": "stats.attackSpeed",
            "knockback": "stats.knockback",
            "minionSlots": "stats.minionSlots",
            "sentrySlots": "stats.sentrySlots",
            "manaCostReduction": "stats.manaCostReduction",
            "ammoSaveChance": "stats.ammoSaveChance",
            "aggro": "stats.aggro",
            "endurance": "stats.endurance",
            "armorPenetration": "stats.armorPenetration",
            "whipRange": "stats.whipRange",
            "summonTagDamage": "stats.summonTagDamage",
            "lightStrength": "stats.lightStrength",
            "fallDamageImmune": "stats.fallDamageImmune",
            "lavaImmune": "stats.lavaImmune",
            "waterWalk": "stats.waterWalk",
            "lightColorName": "stats.lightColorName",
        },
        "armor_effect": {
            "slot": ("armorSlot", "slot"),
            "setKey": "setKey",
            "archetype": "archetype",
            "defense": "defense",
            "maxLife": "stats.maxLife",
            "maxMana": "stats.maxMana",
            "lifeRegen": "stats.lifeRegen",
            "manaRegen": "stats.manaRegen",
            "movementSpeed": "stats.movementSpeed",
            "maxRunSpeed": "stats.maxRunSpeed",
            "jumpSpeed": "stats.jumpSpeed",
            "genericDamage": "stats.genericDamage",
            "meleeDamage": "stats.meleeDamage",
            "rangedDamage": "stats.rangedDamage",
            "magicDamage": "stats.magicDamage",
            "summonDamage": "stats.summonDamage",
            "genericCrit": "stats.genericCrit",
            "attackSpeed": "stats.attackSpeed",
            "knockback": "stats.knockback",
            "minionSlots": "stats.minionSlots",
            "sentrySlots": "stats.sentrySlots",
            "manaCostReduction": "stats.manaCostReduction",
            "ammoSaveChance": "stats.ammoSaveChance",
            "aggro": "stats.aggro",
            "endurance": "stats.endurance",
            "armorPenetration": "stats.armorPenetration",
            "whipRange": "stats.whipRange",
            "summonTagDamage": "stats.summonTagDamage",
            "lightStrength": "stats.lightStrength",
            "fallDamageImmune": "stats.fallDamageImmune",
            "lavaImmune": "stats.lavaImmune",
            "waterWalk": "stats.waterWalk",
            "lightColorName": "stats.lightColorName",
            "setBonusText": "setBonus.text",
            "setBonusGenericDamage": "setBonus.genericDamage",
            "setBonusMeleeDamage": "setBonus.meleeDamage",
            "setBonusRangedDamage": "setBonus.rangedDamage",
            "setBonusMagicDamage": "setBonus.magicDamage",
            "setBonusSummonDamage": "setBonus.summonDamage",
            "setBonusGenericCrit": "setBonus.genericCrit",
            "setBonusMovementSpeed": "setBonus.movementSpeed",
            "setBonusLifeRegen": "setBonus.lifeRegen",
            "setBonusManaRegen": "setBonus.manaRegen",
            "setBonusMinionSlots": "setBonus.minionSlots",
            "setBonusSentrySlots": "setBonus.sentrySlots",
            "setBonusManaCostReduction": "setBonus.manaCostReduction",
            "setBonusAmmoSaveChance": "setBonus.ammoSaveChance",
            "setBonusAggro": "setBonus.aggro",
            "setBonusEndurance": "setBonus.endurance",
            "setBonusArmorPenetration": "setBonus.armorPenetration",
        },
        "set_alt_use_mode": {
            "altUseMode": "mode",
            "altMobilityMode": ("mobilityMode", "mode"),
            "altMobilityRangeTiles": "rangeTiles",
            "altMobilityCooldownTicks": "cooldownTicks",
            "altMobilitySafeTileOnly": "safeTileOnly",
            "altGeneratedBuff.durationTicks": ("generatedBuff.durationTicks", "durationTicks"),
            "altGeneratedBuff.miningSpeedMultiplier": "generatedBuff.miningSpeedMultiplier",
            "altGeneratedBuff.emitLightStrength": "generatedBuff.emitLightStrength",
            "altGeneratedBuff.lightColorName": "generatedBuff.lightColorName",
            "altGeneratedBuff.oreSenseRadiusTiles": "generatedBuff.oreSenseRadiusTiles",
            "altGeneratedBuff.movementSpeed": "generatedBuff.movementSpeed",
            "altGeneratedBuff.jumpBoost": "generatedBuff.jumpBoost",
            "altGeneratedBuff.manaRegen": "generatedBuff.manaRegen",
            "altGeneratedBuff.lifeRegen": "generatedBuff.lifeRegen",
        },
        "hold_item_effect": {
            "holdLightStrength": "lightStrength",
            "holdLightColorName": ("lightColorName", "color"),
            "holdGeneratedBuff.durationTicks": "generatedBuff.durationTicks",
            "holdGeneratedBuff.miningSpeedMultiplier": "generatedBuff.miningSpeedMultiplier",
            "holdGeneratedBuff.emitLightStrength": "generatedBuff.emitLightStrength",
            "holdGeneratedBuff.lightColorName": "generatedBuff.lightColorName",
            "holdGeneratedBuff.oreSenseRadiusTiles": "generatedBuff.oreSenseRadiusTiles",
            "holdGeneratedBuff.movementSpeed": "generatedBuff.movementSpeed",
            "holdGeneratedBuff.jumpBoost": "generatedBuff.jumpBoost",
            "holdGeneratedBuff.manaRegen": "generatedBuff.manaRegen",
            "holdGeneratedBuff.lifeRegen": "generatedBuff.lifeRegen",
        },
        "mobility_effect": {
            "mobilityMode": "mode",
            "mobilityRangeTiles": "rangeTiles",
            "mobilityCooldownTicks": "cooldownTicks",
            "mobilitySafeTileOnly": "safeTileOnly",
        },
        "spawn_contact_particles": {
            "effect": "effect",
            "burstDustCap": "amount",
            "dustSpawnDenom": "amount",
            "vfxParticleScale": "scale",
            "vfxMaterial": "material",
            "vfxParticleDurationTicks": "durationTicks",
        },
        "leave_trail_or_field": {
            "trailLength": "trailLength",
            "vfxFieldLifetimeTicks": "fieldLifetimeTicks",
            "vfxFieldRadiusTiles": ("fieldRadiusTiles", "fieldRadius"),
            "vfxFieldTickRate": "tickRate",
            "fieldRadius": ("fieldRadiusTiles", "fieldRadius"),
        },
        "emit_light": {
            "runtimeLightStrength": "strength",
            "runtimeLightDurationTicks": "durationTicks",
            "runtimeLightColorName": ("lightColorName", "color"),
            "primaryColorName": ("lightColorName", "color"),
        },
        "visual_effect_cue": {
            "vfxCues": (
                "event", "rendererKind", "channel", "lane", "textureRole", "particleRole",
                "emissionMode", "particleSystemId", "scale", "density", "duration", "alpha",
                "spread", "jitter", "startTick", "repeatEvery", "importance", "note",
            ),
        },
        "state_meter": {"runtimeState": "kind"},
        "triggered_action": {"runtimeState": "trigger"},
        "use_affordance": {
            "itemScale": "itemScale",
            "holdoutOffsetX": "holdoutOffsetX",
            "holdoutOffsetY": "holdoutOffsetY",
            "autoReuse": "autoReuse",
            "useTurn": "useTurn",
            "channelUse": "channelUse",
            "heldVisibility": "heldVisibility",
            "releaseTiming": "releaseTiming",
            "handPose": "handPose",
            "initialOffsetPx": "initialOffsetPx",
        },
        "consumption_behavior": {"consumeChancePercent": "consumeChancePercent"},
        "ammo_behavior": {"ammoFor": "ammoFor"},
        "use_condition": {
            "useConditionMode": "mode",
            "useConditionMinLife": "minLife",
            "useConditionMinMana": "minMana",
        },
    }


def compiled_fields_for_authored_param(fn: str, authored_param: str) -> frozenset[str]:
    """Return exact compiler fields structurally attributed to one authored param."""
    normalized_fn = _norm_name(fn)
    return frozenset(
        compiled_field
        for compiled_field, source_params in _compiled_field_source_map().get(normalized_fn, {}).items()
        if authored_param in (source_params if isinstance(source_params, tuple) else (source_params,))
    )


def compiled_fields_for_authored_call(
    fn: str,
    params: dict[str, Any],
    authored_param: str,
) -> frozenset[str]:
    """Resolve a raw typed call through canonical lowering before provenance lookup."""
    from infini_local.core.runtime_authoring.semantics import _lower_typed_engine_call

    def nested(value: dict[str, Any], path: str) -> tuple[bool, Any]:
        current: Any = value
        for part in str(path or "").split("."):
            if not part or not isinstance(current, dict) or part not in current:
                return False, None
            current = current[part]
        return True, current

    present, authored_value = nested(params, authored_param)
    if not present:
        return frozenset()
    resolved = set(compiled_fields_for_authored_param(fn, authored_param))
    baseline = _lower_typed_engine_call(fn, params)
    for canonical_fn, canonical_params in baseline:
        canonical_present, canonical_value = nested(canonical_params, authored_param)
        if canonical_present and canonical_value == authored_value:
            resolved.update(compiled_fields_for_authored_param(canonical_fn, authored_param))

    probe_params = deepcopy(params)
    probe_parent: Any = probe_params
    probe_parts = str(authored_param or "").split(".")
    for part in probe_parts[:-1]:
        if not isinstance(probe_parent, dict) or not isinstance(probe_parent.get(part), dict):
            return frozenset(resolved)
        probe_parent = probe_parent[part]
    if not isinstance(probe_parent, dict) or not probe_parts:
        return frozenset(resolved)
    if isinstance(authored_value, bool):
        probe_value: Any = not authored_value
    elif isinstance(authored_value, int):
        probe_value = authored_value + 1
    elif isinstance(authored_value, float):
        probe_value = authored_value + 0.5
    elif isinstance(authored_value, str):
        probe_value = authored_value + "__icl_provenance_probe__"
    else:
        probe_value = "__icl_provenance_probe__"
    probe_parent[probe_parts[-1]] = probe_value
    counterfactual = _lower_typed_engine_call(fn, probe_params)
    for index, (canonical_fn, canonical_params) in enumerate(baseline):
        if index >= len(counterfactual) or counterfactual[index][0] != canonical_fn:
            changed_fields = set(canonical_params)
        else:
            counterfactual_params = counterfactual[index][1]
            changed_fields = {
                field
                for field in set(canonical_params) | set(counterfactual_params)
                if canonical_params.get(field) != counterfactual_params.get(field)
            }
        for canonical_field in changed_fields:
            resolved.update(compiled_fields_for_authored_param(canonical_fn, canonical_field))
    return frozenset(resolved)


def _authored_field_map(data_or_plan: dict[str, Any]) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Map compiled field names to the engine call that explicitly authored them."""
    rp = data_or_plan if isinstance(data_or_plan.get("engineCalls"), list) else runtime_plan(data_or_plan)
    authored: dict[str, str] = {}
    authored_by_fn: dict[str, list[str]] = {}
    maps = _compiled_field_source_map()
    calls_candidate = rp.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    for raw in calls:
        if not isinstance(raw, dict):
            continue
        fn = _norm_name(raw.get("fn"))
        authored_fn = _norm_name(raw.get("_rawFn") or fn)
        param_obj = raw.get("params") if isinstance(raw.get("params"), dict) else raw
        if not isinstance(param_obj, dict):
            continue
        authored_keys = {str(k) for k, v in param_obj.items() if not str(k).startswith("_") and v not in (None, "", [], {})}
        for compiled_field, authored_param in maps.get(fn, {}).items():
            params = authored_param if isinstance(authored_param, tuple) else (authored_param,)
            if any(param in authored_keys for param in params):
                authored[compiled_field] = authored_fn
                authored_by_fn.setdefault(authored_fn, []).append(compiled_field)
    authored_by_fn = {fn: sorted(set(fields)) for fn, fields in authored_by_fn.items()}
    return authored, authored_by_fn


def runtime_plan_provenance_report(data: dict[str, Any], patch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Explain authored-vs-applied runtime fields so VFX is not confused with gameplay."""
    normalize_runtime_plan_inplace(data)
    rp = runtime_plan(data)
    patch = patch or compile_runtime_plan_to_genome_patch(data)
    calls_candidate = rp.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    fns = [str(c.get("fn") or "") for c in calls if isinstance(c, dict)]
    authored_sources, authored_by_fn = _authored_field_map(rp)
    authored_parameters: list[dict[str, Any]] = []
    for call_index, raw_call in enumerate(calls):
        if not isinstance(raw_call, dict):
            continue
        fn = _norm_name(raw_call.get("fn"))
        call_id = str(raw_call.get("callId") or f"call_{call_index}")
        params_candidate = raw_call.get("params")
        params: dict[str, Any] = params_candidate if isinstance(params_candidate, dict) else {}
        pending: list[tuple[str, Any]] = [(str(key), value) for key, value in params.items()]
        while pending:
            param_path, authored_value = pending.pop(0)
            if isinstance(authored_value, dict):
                pending[0:0] = [
                    (f"{param_path}.{child_key}", child_value)
                    for child_key, child_value in authored_value.items()
                ]
                continue
            if authored_value is not None and not isinstance(authored_value, (str, bool, int, float, list)):
                continue
            compiled_fields = sorted(compiled_fields_for_authored_call(fn, params, param_path))
            authored_parameters.append({
                "callId": call_id,
                "fn": fn,
                "param": param_path,
                "authoredValue": deepcopy(authored_value),
                "compiledFields": compiled_fields,
                "claimableFields": compiled_fields,
            })

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
    child_onhits = {"chain", "lightning_arc", "mini_missiles", "vortex_spawn", "radial_beams", "starburst", "overhead_barrage", "spore_cloud"}
    onhit = _norm_name((patch or {}).get("onHit"))
    runtime_family = _norm_name((patch or {}).get("runtimeFamily"))
    overhead_child_count = int(_num((patch or {}).get("shotCount"), 0) or 0) if runtime_family == "overhead_barrage" else 0
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
        "authoredParameters": authored_parameters,
        "authoredByFunction": authored_by_fn,
        "gameplayChildren": {
            "enabled": (split > 0 and max_child > 0) or effect_child_count > 0 or overhead_child_count > 0,
            "source": "overhead_barrage" if overhead_child_count > 0 else ("spawn_secondary_projectiles" if split > 0 else ("apply_on_hit_effect" if effect_child_count > 0 else "none")),
            "authoredCallCount": len(secondary_calls),
            "compiledFromCallIndices": (patch or {}).get("secondaryCallIndices", []),
            "splitCount": split,
            "onHit": onhit,
            "onHitChildEstimate": effect_child_count,
            "overheadBarrageChildEstimate": overhead_child_count,
            "maxChildProjectiles": max_child,
            "rejectedSecondaryCalls": (patch or {}).get("rejectedSecondaryCalls", []),
            "note": "Real gameplay child projectiles come from spawn_secondary_projectiles, overhead_barrage, or child-producing apply_on_hit_effect values. VFX motes are separate renderer slots."
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
            "runtimeFamily is explicit; missing or conflicting primary families fail validation",
            "splitCount/maxChildProjectiles represent gameplay children only, not VFX motes",
            "state_meter/triggered_action are preserved as explicit authored intent; they do not spawn bosses/NPCs/mobs and do not execute unsupported gameplay by prose",
            "runtimeContract is model-authored public meaning; unsupported engine calls remain explicit and inert",
        ],
    }
    if isinstance(data.get("runtimeContract"), dict):
        out["runtimeContract"] = data.get("runtimeContract")
    return out


def compile_runtime_plan_to_genome_result(data: dict[str, Any]) -> dict[str, Any]:
    patch = compile_runtime_plan_to_genome_patch(data)
    validation = runtime_plan_validation_report(data)
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
