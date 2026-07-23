from __future__ import annotations

import json
from typing import Any
from infini_local.core.balance_report import attach_balance_report

from infini_local.core.balance_mode import should_apply_soft_normalization

from infini_local.core.category_policy import COMBAT_CATEGORIES, NON_WEAPON_CATEGORIES

from infini_local.core.item_identity_tools import item_field, item_num
from infini_local.core.runtime_authoring.normalize import normalize_runtime_plan_inplace, runtime_plan
from infini_local.core.runtime_authoring.compiler import (
    project_aoe_radius_tiles_to_damage_pixels,
    project_authored_pierce_to_runtime_hit_budget,
)
from infini_local.core.runtime_authoring.final_projection import (
    apply_runtime_final_sections,
    compile_runtime_plan_to_final_result,
)
from infini_local.core.runtime_authoring.structural import find_call
from infini_local.pipelines.runtime_presentation_policy import runtime_presentation_defaults
from infini_local.pipelines.result_identity_policy import (
    choose_result_category,
    coerce_category_by_policy,
    normalize_category,
)
from infini_local.pipelines.equipment_stats import (
    accessory_stats_for,
    apply_accessory_soft_budget,
    apply_armor_soft_budget,
    armor_slot_from_authoring,
    armor_stats_for,
)
from infini_local.pipelines.engine_pressure_metrics import estimate_engine_metrics
from infini_local.pipelines.item_power_knowledge import tags_of
from infini_local.pipelines.pipeline_runtime_constants import LLM_RUNTIME_AUTHORING
from infini_local.pipelines.projectile_affordance import apply_parent_projectile_affordance
from infini_local.pipelines.combine_genome_contract import is_llm_planner
from infini_local.pipelines.llm_authoring_prompt import (
    authored_int,
    authored_num,
    authored_weapon_damage,
    llm_category_without_router,
)
from infini_local.pipelines.combine_balance import size_profile_for, stat_profile_for
from infini_local.pipelines.combine_genome import _bounded_parent_potion_stats, _parent_tool_power, normalize_authored_attack_pattern, weapon_genome_for, weapon_numbers_from_genome


def _authored_float_or_default(values: dict[str, Any], key: str, default: float | int) -> float:
    raw = values.get(key)
    return float(default if raw in (None, "") else raw)


def attach_gameplay_and_attack(
    data: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    ca: dict[str, Any],
    cb: dict[str, Any],
) -> dict[str, Any]:
    runtime_authored = bool(LLM_RUNTIME_AUTHORING and runtime_plan(data))
    runtime_compile_result: dict[str, Any] = {}
    if runtime_authored:
        normalize_runtime_plan_inplace(data)
        runtime_compile_result = compile_runtime_plan_to_final_result(data)
    tags = set(data.get("tags", [])) | tags_of(a) | tags_of(b)
    gp = data.setdefault("gameplay", {})
    attack = data.setdefault("attack", {})
    if runtime_authored:
        apply_runtime_final_sections(data, runtime_compile_result)
    final_sections = runtime_compile_result.get("finalSections")
    final_sections = final_sections if isinstance(final_sections, dict) else {}
    projected_fields = {
        section: set(values)
        for section, values in final_sections.items()
        if isinstance(values, dict)
    }

    def update_composition(section: str, target: dict[str, Any], values: dict[str, Any]) -> None:
        if runtime_authored:
            owned = projected_fields.get(section, set())
            values = {key: value for key, value in values.items() if key not in owned}
        target.update(values)
    requested_kind = gp.get("kind") or data.get("category") or choose_result_category(tags, a, b, data.get("recipeKey"))
    if runtime_authored:
        kind = str(gp.get("kind") or "generic")
        policy = {
            "source": "runtime_final_projection",
            "resultKind": kind,
        }
    elif is_llm_planner(data):
        kind, policy = llm_category_without_router(data, requested_kind, tags, a, b, data.get("recipeKey"))
    else:
        kind, policy = coerce_category_by_policy(requested_kind, tags, a, b, data.get("recipeKey"))
    data["category"] = kind
    if not runtime_authored:
        gp["kind"] = kind
    data.setdefault("debug", {})["categoryPolicyFinal"] = json.dumps(policy, ensure_ascii=False)
    max_parent_damage = max(int(a.get("damage") or 0), int(b.get("damage") or 0))
    stage = stat_profile_for(a, b, tags)
    stage_name = stage["name"]
    gp["powerTransfer"] = stage.get("powerTransfer", {})

    # v0.4.8: disambiguate three stack modes before category routing disables attack.
    # - weapon: normal generated weapon, stack 1
    # - consumable_weapon: stackable thrown/shot item using GeneratedProjectile
    # - actual_ammo: Terraria ammo skin/stat mode via item.ammo, reduced custom runtime support
    runtime_stats = find_call(data, "set_item_stats") if LLM_RUNTIME_AUTHORING else {}
    runtime_patch_candidate = runtime_compile_result.get("patch")
    runtime_patch: dict[str, Any] = (
        runtime_patch_candidate if isinstance(runtime_patch_candidate, dict) else {}
    )
    runtime_identity = runtime_compile_result.get("identity")
    runtime_identity = runtime_identity if isinstance(runtime_identity, dict) else {}
    runtime_ammo_for = str(runtime_identity.get("finalAmmoFor") or "")
    runtime_actual_ammo = bool(
        runtime_authored
        and runtime_identity.get("runtimeOutputKind") == "actual_ammo"
    )
    if runtime_actual_ammo:
        gp.setdefault(
            "actualAmmoMode",
            "vanilla_projectile_basic; generated split/onHit runtime is not used by bow/gun ammo yet",
        )

    explicit_non_weapon = kind in NON_WEAPON_CATEGORIES and kind != "generic"
    runtime_tool_family = str(runtime_patch.get("runtimeFamily") or "").strip().lower()
    runtime_tool_has_root_executor = kind == "tool" and runtime_tool_family not in {"", "none"}
    is_weapon = ((kind in COMBAT_CATEGORIES) or runtime_tool_has_root_executor) if runtime_authored else (
        (kind in COMBAT_CATEGORIES) or (not explicit_non_weapon and ("weapon" in tags or max_parent_damage > 0))
    )
    if runtime_authored:
        # Physics-neutral compiler defaults. Runtime-authored projectile geometry must
        # never be selected from item names, parent tags, or prose.
        size = {
            "oversized": 0,
            "itemScale": 1.0,
            "holdoutOffsetX": 0,
            "holdoutOffsetY": 0,
            "projectileWidth": 16,
            "projectileHeight": 16,
            "projectileScale": 1.0,
            "hitboxScale": 1.0,
            "explosionRadius": 0,
        }
    else:
        size = size_profile_for(str(data.get("name", "generated item")), tags, "weapon" if is_weapon else kind, stage)

    if runtime_actual_ammo:
        data["category"] = "ammo"
        ammo_for = "arrow" if runtime_ammo_for in {"arrow", "arrows"} else "bullet"
        update_composition("gameplay", gp, {
            "kind": "ammo",
            "runtimeOutputKind": "actual_ammo",
            "actualAmmoMode": "vanilla_projectile_basic; generated split/onHit runtime is not used by bow/gun ammo yet",
            "stage": stage_name,
            "powerBudget": stage["powerBudget"],
            "damageClass": str(gp.get("damageClass") or "generic"),
            "damage": authored_int(gp, "damage", 0, 0, 9999),
            "knockback": round(authored_num(gp, "knockback", 0.0, 0.0, 12.0), 2),
            "useTime": 10,
            "useAnimation": 10,
            "useStyle": 0,
            "autoReuse": False,
            "consumable": True,
            "manaCost": 0,
            "rarity": authored_int(gp, "rarity", 0, -1, 12),
            "value": authored_int(gp, "value", 0, 0, 999999999),
            "maxStack": authored_int(gp, "maxStack", 1, 1, 9999),
            "craftYield": authored_int(gp, "craftYield", 1, 1, 9999),
            "ammoFor": ammo_for,
            "width": authored_int(gp, "width", 20, 8, 64),
            "height": authored_int(gp, "height", 20, 8, 64),
            "itemScale": authored_num(gp, "itemScale", 1.0, 0.55, 1.55),
        })
        update_composition("attack", attack, {"enabled": False})
        data.setdefault("accessory", {"enabled": False})
    elif kind == "armor" or data.get("category") == "armor":
        data["category"] = "armor"
        if runtime_authored:
            projected_armor = data.get("armor")
            armor: dict[str, Any] = projected_armor if isinstance(projected_armor, dict) else {}
            slot = str(armor.get("slot") or "")
            armor_budget_report = {"mode": "runtime_final_projection", "applied": False}
        else:
            slot = armor_slot_from_authoring(data, runtime_stats, default="body")
            armor = armor_stats_for(tags, stage, slot)
            armor.update(data.get("armor") or {})
            authored_armor_candidate = runtime_patch.get("armor")
            authored_armor = dict(authored_armor_candidate) if isinstance(authored_armor_candidate, dict) else {}
            armor.update(authored_armor)
            armor["enabled"] = True
            armor["slot"] = armor.get("slot") if armor.get("slot") in {"head", "body", "legs"} else slot
            armor, armor_budget_report = apply_armor_soft_budget(
                armor,
                stage,
                str(armor.get("slot") or slot),
                apply_clamps=should_apply_soft_normalization(),
            )
            data["armor"] = armor
        data.setdefault("debug", {})["armorBudgetReport"] = json.dumps(armor_budget_report, ensure_ascii=False)
        update_composition("gameplay", gp, {
            "kind": "armor", "stage": stage_name, "powerBudget": stage["powerBudget"], "damageClass": "generic", "damage": 0,
            "knockback": 0, "useTime": 10, "useAnimation": 10, "useStyle": 0, "autoReuse": False,
            "consumable": False, "manaCost": 0,
            "rarity": authored_int(gp, "rarity", 0 if runtime_authored else max(int(a.get("rare") or 0), int(b.get("rare") or 0), min(8, int(stage["rarity"])),), -1, 12),
            "value": authored_int(gp, "value", 0 if runtime_authored else max(max(int(a.get("value") or 0), int(b.get("value") or 0)) + 100, int(stage["value"] * 0.72)), 0, 999999999),
            "maxStack": 1, "width": 24, "height": 24, "itemScale": authored_num(gp, "itemScale", 1.0, 0.55, 1.55)
        })
        update_composition("attack", attack, {"enabled": False})
        data.setdefault("debug", {})["armorGeneration"] = json.dumps({"slot": armor.get("slot"), "setKey": armor.get("setKey", ""), "rule": "Generated armor uses dedicated Head/Body/Legs proxy ModItem types; C# writes Item.defense and UpdateEquip modifiers."}, ensure_ascii=False)
    elif kind == "accessory" or data.get("category") == "accessory":
        data["category"] = "accessory"
        if runtime_authored:
            projected_accessory = data.get("accessory")
            acc: dict[str, Any] = projected_accessory if isinstance(projected_accessory, dict) else {}
            accessory_budget_report = {"mode": "runtime_final_projection", "applied": False}
        else:
            acc = accessory_stats_for(tags, stage)
            acc.update(data.get("accessory") or {})
            authored_accessory_candidate = runtime_patch.get("accessory")
            authored_accessory = dict(authored_accessory_candidate) if isinstance(authored_accessory_candidate, dict) else {}
            acc.update(authored_accessory)
            acc["enabled"] = True
            acc, accessory_budget_report = apply_accessory_soft_budget(
                acc,
                stage,
                apply_clamps=should_apply_soft_normalization(),
            )
            data["accessory"] = acc
        data.setdefault("debug", {})["accessoryBudgetReport"] = json.dumps(accessory_budget_report, ensure_ascii=False)
        update_composition("gameplay", gp, {
            "kind": "accessory", "stage": stage_name, "powerBudget": stage["powerBudget"], "damageClass": "generic", "damage": 0,
            "knockback": 0, "useTime": 10, "useAnimation": 10, "useStyle": 0, "autoReuse": False,
            "consumable": False, "manaCost": 0,
            "rarity": authored_int(gp, "rarity", 0 if runtime_authored else max(int(a.get("rare") or 0), int(b.get("rare") or 0), min(8, int(stage["rarity"])),), -1, 12),
            "value": authored_int(gp, "value", 0 if runtime_authored else max(max(int(a.get("value") or 0), int(b.get("value") or 0)) + 100, int(stage["value"] * 0.65)), 0, 999999999),
            "maxStack": 1, "width": 24, "height": 24, "itemScale": authored_num(gp, "itemScale", 1.0, 0.55, 1.55)
        })
        update_composition("attack", attack, {"enabled": False})
    elif is_weapon:
        # Combat-capable tools keep their authored item identity while sharing the
        # explicit attack DTO/executor path with weapons.
        combat_output_kind = "tool" if runtime_tool_has_root_executor else "weapon"
        data["category"] = combat_output_kind
        requested_dc = str(gp.get("damageClass") or "").strip()
        if runtime_authored:
            damage_class = requested_dc or ("summon" if kind == "summon" else "generic")
        elif kind == "summon" or requested_dc.lower() == "summon":
            damage_class = "summon"
        elif requested_dc.lower() in {"melee", "melee_no_speed", "ranged", "magic", "summon", "summon_melee_speed", "generic"}:
            damage_class = requested_dc.lower()
        else:
            parent_candidates = sorted([a, b], key=lambda it: int(item_num(it, "damage", 0)), reverse=True)
            parent_dc = str(item_field(parent_candidates[0], "damageClass", "") or "").lower() if parent_candidates else ""
            damage_class = parent_dc if parent_dc in {"melee", "ranged", "magic", "summon", "generic"} else "generic"
        genome = weapon_genome_for(data, a, b, tags, stage, damage_class)
        numbers = weapon_numbers_from_genome(max_parent_damage, tags, stage, genome)
        delivery = str(genome.get("delivery") or "swing")
        runtime_authored = bool(LLM_RUNTIME_AUTHORING and runtime_plan(data))
        pattern, pattern_source = normalize_authored_attack_pattern(genome, attack, damage_class, allow_fallback=not runtime_authored)
        genome["attackPattern"] = pattern
        genome["attackPatternSource"] = pattern_source
        if not runtime_authored:
            genome = apply_parent_projectile_affordance(genome, a, b, tags, data, damage_class)
        delivery = str(genome.get("delivery") or delivery)
        runtime_family = str(genome.get("runtimeFamily") or "none")

        presentation_defaults = runtime_presentation_defaults(runtime_family, damage_class, delivery)

        use_style = int(presentation_defaults["useStyle"])
        update_composition("gameplay", gp, {
            "kind": combat_output_kind,
            "categoryIntent": kind,
            "stage": stage_name,
            "powerBudget": stage["powerBudget"],
            "damageClass": damage_class,
            "damage": authored_weapon_damage(
                gp,
                int(numbers["damage"]),
                max_parent_damage,
                stage,
                genome,
                data.setdefault("debug", {}).setdefault("authorPreservingValidation", {}),
                runtime_authored=runtime_authored,
            ),
            "knockback": round(authored_num(gp, "knockback", 2.0 + min(stage["powerBudget"], 3.8) * 0.42 + (0.8 if int(numbers["useTime"]) >= 60 else 0.0), 0.0, 12.0), 2),
            "useTime": authored_int(gp, "useTime", int(numbers["useTime"]), 6, 150),
            "useAnimation": authored_int(gp, "useAnimation", int(float(genome.get("useAnimationTicks") or numbers["useAnimation"])), 6, 150),
            "useStyle": authored_int(gp, "useStyle", use_style, 0, 5),
            "autoReuse": bool(gp.get("autoReuse", False if runtime_authored else stage["derivedPower"] > 12 and int(numbers["useTime"]) <= 45)),
            "manaCost": authored_int(gp, "manaCost", int(stage["mana"]) if damage_class == "magic" else 0, 0, 80),
            "rarity": authored_int(gp, "rarity", 0 if runtime_authored else max(int(a.get("rare") or 0), int(b.get("rare") or 0), int(stage["rarity"])), -1, 12),
            "value": authored_int(gp, "value", 0 if runtime_authored else max(max(int(a.get("value") or 0), int(b.get("value") or 0)) + 150, int(stage["value"])), 0, 999999999),
            "consumable": bool(gp.get("consumable", False)) if gp.get("runtimeOutputKind") == "consumable_weapon" else False,
            "maxStack": authored_int(gp, "maxStack", 50 if gp.get("runtimeOutputKind") == "consumable_weapon" else 1, 1, 999) if gp.get("runtimeOutputKind") == "consumable_weapon" else 1,
            "craftYield": authored_int(gp, "craftYield", 50 if gp.get("runtimeOutputKind") == "consumable_weapon" else 1, 1, 999),
            "width": authored_int(gp, "width", 24 if runtime_authored else 28 + size["oversized"] * 4, 10, 96),
            "height": authored_int(gp, "height", 24 if runtime_authored else 28 + size["oversized"] * 4, 10, 96),
            "itemScale": authored_num(gp, "itemScale", 1.0 if runtime_authored else size["itemScale"], 0.55, 1.55),
            "holdoutOffsetX": authored_int(gp, "holdoutOffsetX", 0 if runtime_authored else size["holdoutOffsetX"], -256, 256),
            "holdoutOffsetY": authored_int(gp, "holdoutOffsetY", 0 if runtime_authored else size["holdoutOffsetY"], -256, 256),
        })
        if not str(gp.get("heldVisibility") or "").strip():
            gp["heldVisibility"] = presentation_defaults["heldVisibility"]
        if not str(gp.get("releaseTiming") or "").strip():
            gp["releaseTiming"] = presentation_defaults["releaseTiming"]
        if not str(gp.get("handPose") or "").strip():
            gp["handPose"] = presentation_defaults["handPose"]
        aoe_damage_radius_px = (
            int(genome["aoeDamageRadiusPx"])
            if runtime_authored
            else project_aoe_radius_tiles_to_damage_pixels(genome.get("aoeRadiusTiles"))
        )
        impact_vfx_radius_px = int(_authored_float_or_default(
            genome,
            "impactVfxRadiusPx",
            0 if runtime_authored else max(size.get("explosionRadius", 0), aoe_damage_radius_px),
        ))
        contact_forgiveness_px = int(_authored_float_or_default(
            genome,
            "contactForgivenessPx",
            0 if runtime_authored else (min(14, max(0, aoe_damage_radius_px // 6)) if str(genome.get("onHit") or "") in {"burst", "starburst", "aura_pulse"} else 0),
        ))
        update_composition("attack", attack, {
            "enabled": True,
            "stage": stage_name,
            "powerBudget": stage["powerBudget"],
            "damageClass": damage_class,
            "runtimeFamily": runtime_family,
            "delivery": delivery,
            "useStyleCode": int(float(genome.get("useStyleCode") or use_style)),
            "hideUseGraphic": bool(genome.get("hideUseGraphic", False)),
            "disableItemMeleeHitbox": bool(genome.get("disableItemMeleeHitbox", False)),
            "ownerHitCheck": bool(genome.get("ownerHitCheck", False)),
            "channelUse": bool(genome.get("channelUse", False)),
            "weaponFamily": str(genome.get("weaponFamily") or ""),
            "projectileFamily": str(genome.get("projectileFamily") or ""),
            "ammoKind": str(genome.get("ammoFor") or genome.get("ammoKind") or gp.get("ammoFor") or ""),
            "pattern": pattern,
            "patternSource": str(genome.get("attackPatternSource") or pattern_source),
            "runtimePlanAuthored": bool(LLM_RUNTIME_AUTHORING and runtime_plan(data)),
            "movement": genome["movement"], "movementCode": int(genome["movementCode"]),
            "effect": genome["effect"], "effectCode": int(genome["effectCode"]),
            "onHit": genome["onHit"], "onHitCode": int(genome["onHitCode"]),
            "shotCount": int(genome["shotCount"]),
            "spreadRadians": float(genome["spreadRadians"]),
            "procMode": 1 if genome["movementCode"] == 13 else 2 if genome["movementCode"] == 11 else 3 if genome["movementCode"] == 12 else 0,
            "splitCount": max(0, min(8, int(float(genome.get("splitCount") or 0)))),
            "secondaryTrigger": str(genome.get("secondaryTrigger") or "on_hit"),
            "chainCount": max(0, min(6, int(float(genome.get("chainCount") or (2 if genome["onHit"] in {"chain", "lightning_arc"} else 0))))),
            "pullStrength": round(max(0.0, min(1.0, float(genome.get("pullStrength") or 0.0))), 3),
            "pullMode": str(genome.get("pullMode") or "none"),
            "bounceCount": 2 if genome["movement"] in {"bounce", "boomerang"} else 0,
            "genome": genome,
            "speed": round(float(genome.get("speed") or stage["speed"]), 2),
            "rangeTiles": round(max(4.0, min(120.0, float(genome.get("rangeTiles") or 35.0))), 2),
            "homingStrength": round(max(0.0, min(1.0, float(genome.get("homingStrength") or 0.0))), 3),
            "beamWidthPx": round(max(2.0, min(96.0, float(genome.get("beamWidthPx") or 14.0))), 2),
            "beamChargeTicks": max(0, min(300, int(float(genome.get("beamChargeTicks") or 0)))),
            "chargeTicks": max(1, min(300, int(float(genome.get("chargeTicks") or 45)))),
            "chargePowerMultiplier": round(max(1.0, min(3.0, float(genome.get("chargePowerMultiplier") or 1.6))), 3),
            "delayTicks": max(0, min(300, int(float(genome.get("delayTicks") or 0)))),
            "sentryPlacement": str(genome.get("sentryPlacement") or "grounded"),
            "sentryAttackIntervalTicks": max(12, min(180, int(float(genome.get("sentryAttackIntervalTicks") or 45)))),
            "sentryTargetRangeTiles": round(max(8.0, min(60.0, float(genome.get("sentryTargetRangeTiles") or 30.0))), 2),
            "sentryLifetimeTicks": max(120, min(36000, int(float(genome.get("sentryLifetimeTicks") or 3600)))),
            "lifetime": int(genome["lifetimeTicks"]),
            # Runtime C# treats this as total projectile hit budget.
            # 0/1 = one hit; -1 = explicitly infinite/persistent. Older builds added +1,
            # which made ordinary authored pierce=1 shots hit twice.
            "pierce": (
                int(genome["projectileHitBudget"])
                if runtime_authored
                else project_authored_pierce_to_runtime_hit_budget(genome["pierce"])
            ),
            "scale": 1.0,
            "projectileWidth": int(float(genome.get("projectileWidth") or size["projectileWidth"])),
            "projectileHeight": int(float(genome.get("projectileHeight") or size["projectileHeight"])),
            "projectileScale": float(genome.get("projectileScale") or size.get("projectileScale") or 1.0),
            "hitboxScale": float(genome.get("hitboxScale") if genome.get("hitboxScale") is not None else (1.0 if runtime_authored else size["hitboxScale"])),
            "explosionRadius": int(genome.get("explosionRadius") or 0) if runtime_authored else max(size["explosionRadius"], impact_vfx_radius_px),
            "impactVfxRadiusPx": max(0, min(192, impact_vfx_radius_px)),
            "aoeDamageRadiusPx": max(0, min(160, aoe_damage_radius_px)),
            "contactForgivenessPx": max(0, min(32, contact_forgiveness_px)),
            "extraUpdates": int(genome["extraUpdates"]),
            "tileCollide": False if int(genome["movementCode"]) in {8, 11, 12, 13, 15, 16, 17, 18} else True,
            # Local immunity must never default to -1 for generated damaging projectiles;
            # with finite pierce this could re-hit the same NPC while still overlapping.
            "immunityCooldown": max(4, min(60, int(float(genome.get("immunityCooldown") or 0)))) if int(float(genome.get("immunityCooldown") or 0)) > 0 else max(10, int(10 + float(genome.get("aoeRadiusTiles") or 0) * 2)),
            "trailLength": int(float(genome.get("trailLength") if genome.get("trailLength") is not None else (10 if genome["effect"] in {"star", "shadow", "electric", "flame", "lunar"} else 4))),
            "maxChildProjectiles": int(genome.get("maxChildProjectiles") or 0),
            "maxChildDepth": int(genome.get("maxChildDepth") or 0),
            "dustSpawnDenom": int(genome.get("dustSpawnDenom") if genome.get("dustSpawnDenom") is not None else (0 if bool(LLM_RUNTIME_AUTHORING and runtime_plan(data)) else 3)),
            "burstDustCap": int(genome.get("burstDustCap") if genome.get("burstDustCap") is not None else (0 if bool(LLM_RUNTIME_AUTHORING and runtime_plan(data)) else 20)),
            "vfxParticleScale": round(float(genome.get("vfxParticleScale") or 0.0), 3),
            "vfxMaterial": str(genome.get("vfxMaterial") or ""),
            "vfxParticleDurationTicks": int(float(genome.get("vfxParticleDurationTicks") or 0)),
            "vfxFieldLifetimeTicks": int(float(genome.get("vfxFieldLifetimeTicks") or 0)),
            "vfxFieldRadiusTiles": round(float(genome.get("vfxFieldRadiusTiles") or 0.0), 3),
            "vfxFieldTickRate": int(float(genome.get("vfxFieldTickRate") or 0)),
            "debuffHint": str(genome.get("debuffHint") or ""),
            "debuffTime": int(float(genome.get("debuffTime") or 0)),
            "secondaryMaterial": str(genome.get("secondaryMaterial") or ""),
            "secondaryProjectileShape": str(genome.get("secondaryProjectileShape") or ""),
            "secondaryDamageMultiplier": round(max(0.0, min(1.0, float(genome.get("secondaryDamageMultiplier") if genome.get("secondaryDamageMultiplier") is not None else 0.0))), 3),
            "secondarySpreadRadians": round(max(0.0, min(1.2, float(genome.get("secondarySpreadRadians") if genome.get("secondarySpreadRadians") is not None else 0.0))), 3),
            "secondaryLifetimeTicks": max(5, min(180, int(float(genome.get("secondaryLifetimeTicks") if genome.get("secondaryLifetimeTicks") is not None else 5)))),
            "sameTargetBias": round(max(0.0, min(1.0, float(genome.get("sameTargetBias") if genome.get("sameTargetBias") is not None else 0.0))), 3),
            "engineMetrics": genome.get("engineMetrics") or estimate_engine_metrics(genome, stage),
            "projectileShape": genome.get("projectileShape") or attack.get("projectileShape") or (data.get("projectileGenome") if isinstance(data.get("projectileGenome"), dict) else {}).get("shape", ""),
            "projectileMotion": genome.get("projectileMotion") or attack.get("projectileMotion") or (data.get("projectileGenome") if isinstance(data.get("projectileGenome"), dict) else {}).get("motionFeel", ""),
            "projectileTrail": genome.get("projectileTrail") or attack.get("projectileTrail") or (data.get("projectileGenome") if isinstance(data.get("projectileGenome"), dict) else {}).get("trail", ""),
            "projectileImpact": genome.get("projectileImpact") or attack.get("projectileImpact") or (data.get("projectileGenome") if isinstance(data.get("projectileGenome"), dict) else {}).get("impact", ""),
            "primaryColorName": str(genome.get("primaryColorName") or attack.get("primaryColorName") or ""),
            "runtimeLightStrength": round(float(genome.get("runtimeLightStrength") or 0.0), 3),
            "runtimeLightDurationTicks": int(float(genome.get("runtimeLightDurationTicks") or 0)),
            "mobilityMode": str(gp.get("mobilityMode") or genome.get("mobilityMode") or ""),
            "mobilityRangeTiles": int(float(gp.get("mobilityRangeTiles") or genome.get("mobilityRangeTiles") or 0)),
            "mobilityCooldownTicks": int(float(gp.get("mobilityCooldownTicks") or genome.get("mobilityCooldownTicks") or 0)),
            "mobilitySafeTileOnly": bool(gp.get("mobilitySafeTileOnly", genome.get("mobilitySafeTileOnly", True))),
            "soundUseCatalogId": str(genome.get("soundUseCatalogId") or ""),
            "soundImpactCatalogId": str(genome.get("soundImpactCatalogId") or ""),
            "soundCatalogSource": str(genome.get("soundCatalogSource") or ""),
            "soundVolume": round(float(genome.get("soundVolume") or 0.85), 3),
            "soundPitch": round(float(genome.get("soundPitch") or 0.0), 3),
            "soundPitchVariance": round(float(genome.get("soundPitchVariance") if genome.get("soundPitchVariance") is not None else 0.18), 3),
        })
        data.setdefault("accessory", {"enabled": False})
    elif kind == "tool":
        data["category"] = "tool"
        tool_power = max(35, min(230, int(28 + stage["derivedPower"] * 4 + max_parent_damage * 1.2)))
        authored_tool = gp if runtime_authored else {}
        authored_pick = int(authored_tool.get("pickPower") or 0)
        authored_axe = int(authored_tool.get("axePower") or 0)
        authored_hammer = int(authored_tool.get("hammerPower") or 0)
        parent_pick_signal = "pickaxe" in tags or "drill" in tags or _parent_tool_power(a, "pickPower", "pick") > 0 or _parent_tool_power(b, "pickPower", "pick") > 0
        parent_axe_signal = "axe" in tags or "chainsaw" in tags or _parent_tool_power(a, "axePower", "axe") > 0 or _parent_tool_power(b, "axePower", "axe") > 0
        parent_hammer_signal = "hammer" in tags or _parent_tool_power(a, "hammerPower", "hammer") > 0 or _parent_tool_power(b, "hammerPower", "hammer") > 0
        inferred_pick = tool_power if parent_pick_signal else 0
        inferred_axe = max(8, tool_power // 5) if parent_axe_signal else 0
        inferred_hammer = max(20, min(120, tool_power)) if parent_hammer_signal else 0
        if runtime_authored:
            pick = max(0, min(1000, authored_pick))
            axe = max(0, min(200, authored_axe))
            hammer = max(0, min(1000, authored_hammer))
        else:
            pick = authored_int(gp, "pickPower", inferred_pick, 0, 230) if parent_pick_signal else 0
            axe = authored_int(gp, "axePower", inferred_axe, 0, 50) if parent_axe_signal else 0
            hammer = authored_int(gp, "hammerPower", inferred_hammer, 0, 120) if parent_hammer_signal else 0
        genome = (attack.get("genome") if isinstance(attack.get("genome"), dict) else {}) or {}
        # emit_light on a non-projectile tool is executable held-item light.
        # Keep it in the existing Gameplay.HoldLight* contract instead of
        # inventing Python-only Gameplay.RuntimeLight* wire fields.
        light_strength = gp.get("holdLightStrength")
        if light_strength in (None, ""):
            light_strength = genome.get("runtimeLightStrength")
        light_color = gp.get("holdLightColorName")
        if light_color in (None, ""):
            light_color = genome.get("runtimeLightColorName") or genome.get("primaryColorName")
        mining_speed = gp.get("miningSpeedScale")
        if mining_speed in (None, ""):
            mining_speed = genome.get("miningSpeedScale")
        data.setdefault("debug", {})["toolMerge"] = json.dumps({
            "parentSignals": {"pick": parent_pick_signal, "axe": parent_axe_signal, "hammer": parent_hammer_signal},
            "runtimeAuthoredSignals": {"pick": authored_pick > 0, "axe": authored_axe > 0, "hammer": authored_hammer > 0},
            "inferred": {"pickPower": inferred_pick, "axePower": inferred_axe, "hammerPower": inferred_hammer},
            "final": {"pickPower": pick, "axePower": axe, "hammerPower": hammer},
            "rule": "tool tile-edit powers come from parent tool signals or explicit runtimePlan tool_capability; weapons/projectiles do not invent them",
        }, ensure_ascii=False)
        damage_class = str(gp.get("damageClass") or ("generic" if runtime_authored else "melee"))
        update_composition("gameplay", gp, {
            "kind": "tool", "stage": stage_name, "powerBudget": stage["powerBudget"], "damageClass": damage_class,
            "damage": authored_int(gp, "damage", 0 if runtime_authored else max(4, int(max_parent_damage * 0.75 + max(1, int(stage.get("derivedDamage") or max_parent_damage or 4)) * 0.25)), 0, 9999),
            "knockback": round(authored_num(gp, "knockback", 0.0 if runtime_authored else 2.0 + min(stage["powerBudget"], 3.0) * 0.35, 0.0, 12.0), 2),
            "useTime": authored_int(gp, "useTime", 20 if runtime_authored else max(12, int(stage["useTime"] + 2)), 10, 150),
            "useAnimation": authored_int(gp, "useAnimation", 20 if runtime_authored else max(12, int(stage["useTime"] + 2)), 6, 150),
            "useStyle": 1, "autoReuse": bool(gp.get("autoReuse", False if runtime_authored else True)), "manaCost": 0,
            "rarity": authored_int(gp, "rarity", 0 if runtime_authored else max(int(a.get("rare") or 0), int(b.get("rare") or 0), int(stage["rarity"])), -1, 12),
            "value": authored_int(gp, "value", 0 if runtime_authored else max(max(int(a.get("value") or 0), int(b.get("value") or 0)) + 100, int(stage["value"] * 0.85)), 0, 999999999),
            "maxStack": 1, "width": 28, "height": 28, "itemScale": authored_num(gp, "itemScale", 1.0 if runtime_authored else size["itemScale"], 0.55, 1.55),
            "pickPower": pick, "axePower": axe, "hammerPower": hammer,
        })
        if not runtime_authored:
            if mining_speed not in (None, ""):
                try:
                    gp["miningSpeedScale"] = max(0.25, min(3.0, float(mining_speed)))
                except Exception as exc:
                    data.setdefault("debug", {})["ignoredInvalidMiningSpeedScale"] = json.dumps({"value": mining_speed, "error": repr(exc)}, ensure_ascii=False)
            if light_strength not in (None, ""):
                try:
                    gp["holdLightStrength"] = max(0.0, min(1.5, float(light_strength)))
                except Exception as exc:
                    data.setdefault("debug", {})["ignoredInvalidHoldLightStrength"] = json.dumps({"value": light_strength, "error": repr(exc)}, ensure_ascii=False)
            if light_color not in (None, ""):
                gp["holdLightColorName"] = str(light_color)
        update_composition("attack", attack, {"enabled": False})
        data.setdefault("accessory", {"enabled": False})
    elif kind == "potion" or (not runtime_authored and ("potion" in tags or "consumable" in tags)):
        data["category"] = "potion"
        potion_profile = {} if runtime_authored else _bounded_parent_potion_stats(a, b)
        heal_life = authored_int(gp, "healLife", int(potion_profile.get("healLife") or 0), 0, 500)
        heal_mana = authored_int(gp, "healMana", int(potion_profile.get("healMana") or 0), 0, 500)
        buff_code = authored_int(gp, "buffCode", int(potion_profile.get("buffCode") or 0), 0, 2147483647)
        buff_time = authored_int(gp, "buffTime", int(potion_profile.get("buffTime") or 0), 0, 60 * 60 * 6)
        extra_buffs = gp.get("extraBuffs") if isinstance(gp.get("extraBuffs"), list) else ([] if runtime_authored else potion_profile.get("extraBuffs", []))
        if not isinstance(extra_buffs, list):
            extra_buffs = []
        if buff_code > 0 and buff_time > 0 and not any(isinstance(entry, dict) and int(float(entry.get("buffCode") or entry.get("buffType") or 0)) == buff_code for entry in extra_buffs):
            extra_buffs = [{"buffCode": buff_code, "buffTime": buff_time}] + list(extra_buffs)
        generated_use_buff = (
            dict(gp.get("generatedBuff") or {})
            if not runtime_authored and isinstance(gp.get("generatedBuff"), dict)
            else {}
        )
        data.setdefault("debug", {})["potionMerge"] = json.dumps(potion_profile.get("debug", {}), ensure_ascii=False)
        update_composition("gameplay", gp, {
            "kind": "potion", "stage": stage_name, "powerBudget": stage["powerBudget"], "damageClass": "generic", "damage": 0, "useStyle": 2,
            "consumable": True,
            "maxStack": authored_int(gp, "maxStack", 30, 1, 999),
            "rarity": authored_int(gp, "rarity", 0 if runtime_authored else min(3, max(1, int(stage["rarity"]))), -1, 12),
            "value": authored_int(gp, "value", 0 if runtime_authored else max(80, int(stage["value"] * 0.18)), 0, 999999999),
            "useTime": authored_int(gp, "useTime", 17, 10, 60), "useAnimation": authored_int(gp, "useAnimation", 17, 6, 60),
            "width": authored_int(gp, "width", 20, 8, 64), "height": authored_int(gp, "height", 26, 8, 64), "healLife": heal_life, "healMana": heal_mana, "buffCode": buff_code, "buffTime": buff_time, "extraBuffs": extra_buffs[:4], "itemScale": authored_num(gp, "itemScale", 1.0, 0.55, 1.55)
        })
        if not runtime_authored:
            if generated_use_buff:
                gp["generatedBuff"] = generated_use_buff
            else:
                gp.pop("generatedBuff", None)
        update_composition("attack", attack, {"enabled": False})
        data.setdefault("accessory", {"enabled": False})
    else:
        generic_kind = kind if kind != "generic" else data.get("category", "generic")
        generic_kind = normalize_category(generic_kind)
        data["category"] = generic_kind
        if not runtime_authored:
            size = size_profile_for(
                str(data.get("name", "generated item")),
                tags,
                generic_kind,
                stage,
            )
        update_composition("gameplay", gp, {
            "kind": generic_kind, "stage": stage_name, "powerBudget": stage["powerBudget"], "damageClass": "generic", "damage": 0, "useStyle": 1,
            "maxStack": authored_int(gp, "maxStack", 1 if runtime_authored else (99 if generic_kind in ["material", "generic", "ammo"] else 1), 1, 9999),
            "rarity": authored_int(gp, "rarity", 0 if runtime_authored else max(int(a.get("rare") or 0), int(b.get("rare") or 0), min(4, int(stage["rarity"]))), -1, 12),
            "value": authored_int(gp, "value", 0 if runtime_authored else max(int(a.get("value") or 0), int(b.get("value") or 0)) + 50, 0, 999999999),
            "width": 24, "height": 24, "itemScale": authored_num(gp, "itemScale", 1.0 if runtime_authored else size["itemScale"], 0.55, 1.55)
        })
        update_composition("attack", attack, {"enabled": False})
        data.setdefault("accessory", {"enabled": False})

    data.setdefault("debug", {})["statProfile"] = json.dumps(stage, ensure_ascii=False)
    data.setdefault("debug", {})["sizeProfile"] = json.dumps(size, ensure_ascii=False)
    data.setdefault("debug", {})["finalCategory"] = data.get("category", "generic")
    attach_balance_report(data, stage)
    return data

__all__ = ["attach_gameplay_and_attack"]
