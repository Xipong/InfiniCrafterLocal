from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from infini_local.core.runtime_authoring import (
    compile_runtime_plan_to_genome_patch,
    runtime_plan_validation_report,
)
from infini_local.pipelines.combine_gameplay import attach_gameplay_and_attack
from infini_local.pipelines.item_power_knowledge import canonicalize
from infini_local.pipelines.llm_authoring_prompt import normalize_runtime_authoring_fields
from infini_local.pipelines.combine_genome import genome_defects
from infini_local.pipelines.engine_pressure_metrics import estimate_engine_metrics
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.boundary_models import runtime_plan_boundary_report


ROOT = Path(__file__).resolve().parents[2]


def _parent(name: str, *, damage: int = 0, damage_class: str = "generic", tags: list[str] | None = None, **extra) -> dict:
    item = {
        "name": name,
        "internalName": name.replace(" ", ""),
        "sourceMod": "Terraria",
        "damage": damage,
        "damageClass": damage_class,
        "useTime": 24,
        "useAnimation": 24,
        "knockback": 3.0,
        "rare": 2,
        "value": 5000,
        "maxStack": 1,
        "consumable": False,
        "material": False,
        "tags": tags or [],
    }
    item.update(extra)
    return item


def _primary(
    runtime_family: str,
    delivery: str,
    movement: str,
    lifetime_ticks: int,
    *,
    speed: float = 8.0,
    range_tiles: float = 45.0,
    shot_count: int = 1,
    spread_radians: float = 0.0,
    pierce: int = 0,
) -> dict:
    return {
        "fn": "shoot_projectile",
        "params": {
            "runtimeFamily": runtime_family,
            "delivery": delivery,
            "movement": movement,
            "lifetimeTicks": lifetime_ticks,
            "speed": speed,
            "rangeTiles": range_tiles,
            "shotCount": shot_count,
            "spreadRadians": spread_radians,
            "pierce": pierce,
        },
    }


def _attach(plan: dict, a: dict | None = None, b: dict | None = None) -> dict:
    a = a or _parent("Parent A")
    b = b or _parent("Parent B")
    data = {
        "name": "Authored Result",
        "tooltip": "Exact runtime contract.",
        "debug": {"planner": "llm_author_first"},
        **plan,
    }
    normalize_runtime_authoring_fields(data)
    return attach_gameplay_and_attack(data, a, b, canonicalize(a), canonicalize(b))


def _contract_check_llm_output_without_runtime_plan_never_falls_back_to_semantic_router() -> None:
    with pytest.raises(PlannerUnavailable, match="runtimePlan"):
        normalize_runtime_authoring_fields({
            "name": "Literal Workbench Blade",
            "category": "generic",
            "debug": {"planner": "llm_author_first"},
            "gameplay": {"kind": "generic"},
        })


def _contract_check_parent_tags_and_damage_do_not_reclassify_explicit_generic() -> None:
    data = _attach(
        {
            "category": "generic",
            "runtimePlan": {
                "resultKind": "generic",
                "engineCalls": [
                    {"fn": "set_item_stats", "params": {"resultKind": "generic", "maxStack": 1}},
                ],
            },
        },
        _parent("Flaming Sword", damage=80, damage_class="melee", tags=["weapon", "flaming"]),
        _parent("Workbench", tags=["crafting_station"]),
    )
    assert data["category"] == "generic"
    assert data["gameplay"]["kind"] == "generic"
    assert data["attack"]["enabled"] is False


def _contract_check_compiler_never_inherits_parent_burn_or_default_debuff_duration() -> None:
    data = {
        "parentA": {"tags": ["flaming"]},
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 20, "useTimeTicks": 25}},
                _primary("swing", "swing", "straight", 30),
            ],
        },
    }
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["onHit"] == "none"
    assert "parentMechanicPreserved" not in patch
    assert "debuffTime" not in patch

    missing_duration = {
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 20, "useTimeTicks": 25}},
                _primary("shoot", "shoot", "straight", 60),
                {"fn": "apply_on_hit_effect", "params": {"onHit": "burn"}},
            ],
        },
    }
    report = runtime_plan_validation_report(missing_duration)
    assert report["ok"] is False
    assert any("debuffTime" in error for error in report["errors"])


def _contract_check_generated_buffs_require_authored_duration_and_zero_consume_is_preserved() -> None:
    missing_duration = {
        "runtimePlan": {
            "resultKind": "potion",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "potion", "maxStack": 30, "consumable": True}},
                {"fn": "apply_player_effect_on_use", "params": {"generatedBuff": {"movementSpeed": 0.15}}},
            ],
        },
    }
    report = runtime_plan_validation_report(missing_duration)
    assert report["ok"] is False
    assert any("durationTicks" in error for error in report["errors"])
    assert "generatedBuff" not in compile_runtime_plan_to_genome_patch(missing_duration)

    zero = {
        "runtimePlan": {
            "resultKind": "potion",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "potion", "maxStack": 30, "consumable": True, "healLife": 10}},
                {"fn": "consumption_behavior", "params": {"consumeChancePercent": 0}},
            ],
        },
    }
    assert compile_runtime_plan_to_genome_patch(zero)["consumeChancePercent"] == 0


def _contract_check_nested_accessory_and_armor_stats_are_the_only_equipment_authority() -> None:
    accessory = compile_runtime_plan_to_genome_patch({
        "runtimePlan": {
            "resultKind": "accessory",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "accessory", "maxStack": 1}},
                {"fn": "accessory_effect", "params": {"archetype": "utility", "defense": 10, "stats": {"movementSpeed": 0.12, "ammoSaveChance": 0.13, "fallDamageImmune": True}}},
            ],
        },
    })["accessory"]
    assert accessory["movementSpeed"] == 0.12
    assert accessory["defense"] == 10
    assert accessory["ammoSaveChance"] == 0.13
    assert accessory["fallDamageImmune"] is True
    assert "rangedDamage" not in accessory

    armor = compile_runtime_plan_to_genome_patch({
        "runtimePlan": {
            "resultKind": "armor",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "armor", "armorSlot": "head", "defense": 12}},
                {"fn": "armor_effect", "params": {
                    "armorSlot": "head",
                    "stats": {"magicDamage": 0.09, "manaRegen": 2},
                    "setBonus": {"text": "Focused circuitry", "magicDamage": 0.05, "manaRegen": 1},
                }},
            ],
        },
    })["armor"]
    assert armor["slot"] == "head"
    assert armor["magicDamage"] == 0.09
    assert armor["manaRegen"] == 2
    assert armor["setBonusText"] == "Focused circuitry"
    assert armor["setBonusMagicDamage"] == 0.05
    assert armor["setBonusManaRegen"] == 1


def _contract_check_tool_power_is_explicit_and_modded_ranges_are_not_vanilla_capped() -> None:
    data = _attach({
        "category": "tool",
        "runtimePlan": {
            "resultKind": "tool",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "tool", "useTimeTicks": 12, "useAnimationTicks": 12}},
                {"fn": "tool_capability", "params": {"pickPower": 420, "axePower": 95, "hammerPower": 350}},
            ],
        },
    })
    gp = data["gameplay"]
    assert (gp["pickPower"], gp["axePower"], gp["hammerPower"]) == (420, 95, 350)

    no_tool_call = _attach({
        "category": "tool",
        "runtimePlan": {
            "resultKind": "tool",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "tool", "useTimeTicks": 12, "useAnimationTicks": 12}},
            ],
        },
    }, _parent("Pickaxe Parent", tags=["pickaxe"], pickPower=200), _parent("Other"))
    assert no_tool_call["gameplay"]["pickPower"] == 0


def _contract_check_secondary_fields_and_primary_debuff_survive_final_projection() -> None:
    data = _attach({
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 35, "useTimeTicks": 24, "useAnimationTicks": 24}},
                _primary("shoot", "shoot", "straight", 90, speed=10),
                {"fn": "apply_on_hit_effect", "params": {"onHit": "frostburn", "debuffTime": 137}},
                {"fn": "spawn_secondary_projectiles", "params": {"trigger": "on_hit", "count": 3, "damageMultiplier": 0.17, "spreadRadians": 0.31, "lifetimeTicks": 37, "sameTargetBias": 0.73, "projectileShape": "ice splinters"}},
            ],
        },
    })
    attack = data["attack"]
    assert attack["onHit"] == "frostburn"
    assert attack["debuffTime"] == 137
    assert attack["secondaryTrigger"] == "on_hit"
    assert attack["splitCount"] == 3
    assert attack["secondaryDamageMultiplier"] == 0.17
    assert attack["secondarySpreadRadians"] == 0.31
    assert attack["secondaryLifetimeTicks"] == 37
    assert attack["sameTargetBias"] == 0.73


def _contract_check_aoe_visual_and_contact_radii_are_independent() -> None:
    data = _attach({
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 25, "useTimeTicks": 24}},
                _primary("cast", "cast", "straight", 90),
                {"fn": "apply_on_hit_effect", "params": {"onHit": "burst", "aoeRadiusTiles": 4}},
            ],
        },
    })
    attack = data["attack"]
    assert attack["aoeDamageRadiusPx"] == 64
    assert attack["impactVfxRadiusPx"] == 0
    assert attack["contactForgivenessPx"] == 0
    assert attack["hitboxScale"] == 1.0

    normalize = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize.cs").read_text(encoding="utf-8")
    projectile_runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    impact = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Impact.cs").read_text(encoding="utf-8")
    visuals = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Visuals.cs").read_text(encoding="utf-8")
    item = (ROOT / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs").read_text(encoding="utf-8")
    assert "Attack.ImpactVfxRadiusPx = Attack.ExplosionRadius" not in normalize
    assert "spec.ImpactVfxRadiusPx <= 0 ? spec.ExplosionRadius" not in projectile_runtime
    assert "return Math.Clamp(_spec.AoeDamageRadiusPx / 4" not in impact
    assert "_spec.AoeDamageRadiusPx > 0 ? _spec.AoeDamageRadiusPx : _spec.ImpactVfxRadiusPx" not in impact
    assert "OnHitUsesBurstDustFallback" not in visuals
    assert "return Math.Clamp(attack.AoeDamageRadiusPx / 6" not in item


def _contract_check_csharp_accepts_loaded_mod_damage_classes_and_content_ids() -> None:
    policy = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedDamageClassPolicy.cs").read_text(encoding="utf-8")
    normalize = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize.cs").read_text(encoding="utf-8")
    impact = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Impact.cs").read_text(encoding="utf-8")
    assert "ModContent.TryFind<DamageClass>" in policy
    assert "BuffLoader.BuffCount" in normalize or "BuffLoader.BuffCount" in impact
    assert "ExtractinatorOutputItemType" not in normalize
    assert "Gameplay.PickPower, 0, 1000" in normalize
    assert "Gameplay.AxePower, 0, 200" in normalize
    assert "Gameplay.HammerPower, 0, 1000" in normalize


def _contract_check_csharp_runtime_preserves_exact_equipment_network_and_buff_authority() -> None:
    item = (ROOT / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs").read_text(encoding="utf-8")
    player = (ROOT / "ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.cs").read_text(encoding="utf-8")
    craft_state = (ROOT / "ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.CraftState.cs").read_text(encoding="utf-8")
    mobility = (ROOT / "ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.Mobility.cs").read_text(encoding="utf-8")
    multiplayer = (ROOT / "ModSources/InfiniCrafterLocal/Common/Players/InfiniCraftPlayer.Multiplayer.cs").read_text(encoding="utf-8")
    mod_root = (ROOT / "ModSources/InfiniCrafterLocal/InfiniCrafterLocal.cs").read_text(encoding="utf-8")
    projectile_impact = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Impact.cs").read_text(encoding="utf-8")
    registry = (ROOT / "ModSources/InfiniCrafterLocal/Common/Services/GeneratedItemRegistryService.cs").read_text(encoding="utf-8")

    assert "AddGeneratedAmmoSaveChance" in player
    assert "override bool CanConsumeAmmo" in player
    assert "ammoCost75" not in item
    assert "ammoCost80" not in item

    item_net_send = item[item.index("public override void NetSend"):item.index("public override void NetReceive")]
    assert "ToPlayerSaveJson" in item_net_send and "ToNetworkJson" not in item_net_send
    assert "registerLocal: false" in item[item.index("public override void NetReceive"):item.index("public override bool CanStack")]
    assert not (ROOT / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedExtractinatorMaterial.cs").exists()

    assert "private readonly List<ActiveGeneratedUtilityBuff>" in player
    assert "SameEffect" in mobility
    assert "RebuildGeneratedUtilityBuffAggregate" in mobility
    assert "ReadGeneratedBuffState(reader);" in multiplayer
    assert "writer.Write((byte)2); // state version" in multiplayer
    assert "WriteGeneratedUtilityBuffEntry" in multiplayer
    assert "ReadGeneratedUtilityBuffEntry" in multiplayer
    assert "RehydrateOwnedGeneratedUtilityBuffFromNetwork" not in multiplayer + mobility
    assert "GeneratedUtilitySummary" in item
    assert "mining time x" in item
    assert "DiscardGeneratedBuffState(reader)" in multiplayer
    assert "Clients may request a resync" in multiplayer
    assert "RequestGeneratedAltUse" in mod_root
    assert "HandleGeneratedAltUseRequestPacket" in multiplayer
    assert "RequestGeneratedAltUseFromServer" in multiplayer
    assert "TryRunGeneratedMobilityFromServerIntent" in mobility
    assert "GeneratedItem.UseBlockedReason(Player, gp)" in multiplayer
    assert "Math.Clamp(gp.UseTime, 6, 150)" in multiplayer
    assert "Player.itemAnimation <= 0 && Player.itemTime <= 0" in multiplayer
    assert "ProcessPendingGeneratedUseIntent();" in craft_state
    assert "if (Main.netMode == NetmodeID.Server)\n                return true;" in item
    assert "ApplyGeneratedUtilityBuffEffects();" in craft_state
    tick_buff = mobility[mobility.index("private void TickGeneratedUtilityBuff"):mobility.index("private void RebuildGeneratedUtilityBuffAggregate")]
    assert "Player.moveSpeed" not in tick_buff
    assert "Player.lifeRegen" not in tick_buff

    assert 'mode == "buff"' not in item
    assert "8 * 60" not in item[item.index("public override bool? UseItem"):item.index("public override void HoldItem")]
    assert "ShouldRunPlayerGameplay(player)" in item

    assert "player.Heal(heal);" in item
    assert "owner.Heal(heal);" in projectile_impact
    assert "damageDone / 4" not in projectile_impact

    assert "FileMode.CreateNew" in registry
    assert "stream.Flush(flushToDisk: true)" in registry
    assert "File.Move(tempPath, path, overwrite: true)" in registry

    assert "cooldownTicks <= 0 ? 60" not in mobility
    assert "MobilityRangeTiles <= 0 ? 18" not in mobility
    assert "MobilityRangeTiles <= 0 ? 24" not in projectile_impact
    assert "if (sameTarget)\n            if (sameTarget)" not in projectile_impact


def _contract_check_runtime_item_stats_survive_category_projection_without_parent_economy_or_stack_rewrites() -> None:
    consumable = _attach({
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "consumable_weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "consumable_weapon", "damageClass": "ranged", "damage": 17, "useTimeTicks": 19, "useAnimationTicks": 19, "maxStack": 7, "craftYield": 3, "rarity": 1, "value": 42, "consumable": True}},
                _primary("throw", "throw", "gravity_arc", 75, speed=8),
            ],
        },
    }, _parent("Expensive Parent", damage=90, tags=["weapon"], rare=9, value=900000), _parent("Other", rare=8, value=800000))
    gp = consumable["gameplay"]
    assert (gp["maxStack"], gp["craftYield"], gp["rarity"], gp["value"]) == (7, 3, 1, 42)

    accessory = _attach({
        "category": "accessory",
        "runtimePlan": {
            "resultKind": "accessory",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "accessory", "rarity": 0, "value": 11}},
                {"fn": "accessory_effect", "params": {"stats": {"movementSpeed": 0.05}}},
            ],
        },
    }, _parent("Expensive Parent", rare=10, value=999999), _parent("Other", rare=9, value=888888))
    assert (accessory["gameplay"]["rarity"], accessory["gameplay"]["value"]) == (0, 11)

    tool = _attach({
        "category": "tool",
        "runtimePlan": {
            "resultKind": "tool",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "tool", "damageClass": "CalamityMod/RogueDamageClass", "damage": 9, "useTimeTicks": 16, "useAnimationTicks": 16, "rarity": 2, "value": 77}},
                {"fn": "tool_capability", "params": {"pickPower": 260}},
            ],
        },
    }, _parent("Expensive Pick", rare=10, value=999999, tags=["pickaxe"]), _parent("Other"))
    tool_gp = tool["gameplay"]
    assert tool_gp["damageClass"] == "CalamityMod/RogueDamageClass"
    assert (tool_gp["rarity"], tool_gp["value"], tool_gp["pickPower"]) == (2, 77, 260)

    missing_stack = runtime_plan_validation_report({
        "runtimePlan": {
            "resultKind": "consumable_weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "consumable_weapon", "damageClass": "ranged", "damage": 10, "useTimeTicks": 20}},
                _primary("throw", "throw", "gravity_arc", 60),
            ],
        },
    })
    assert missing_stack["ok"] is False
    assert any("maxStack" in error and "craftYield" in error for error in missing_stack["errors"])



def _contract_check_actual_ammo_preserves_authored_stats_and_presentation() -> None:
    data = _attach({
        "category": "ammo",
        "runtimePlan": {
            "resultKind": "ammo",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {
                    "resultKind": "ammo",
                    "damageClass": "ranged",
                    "damage": 17,
                    "knockback": 1.75,
                    "maxStack": 999,
                    "craftYield": 50,
                    "ammoFor": "arrow",
                    "rarity": 3,
                    "value": 12,
                }},
                {"fn": "use_affordance", "params": {"itemScale": 1.2}},
            ],
        },
    })
    gp = data["gameplay"]
    assert gp["runtimeOutputKind"] == "actual_ammo"
    assert gp["damageClass"] == "ranged"
    assert gp["damage"] == 17
    assert gp["knockback"] == 1.75
    assert (gp["maxStack"], gp["craftYield"], gp["ammoFor"]) == (999, 50, "arrow")
    assert (gp["rarity"], gp["value"], gp["itemScale"]) == (3, 12, 1.2)
    assert data["attack"]["enabled"] is False

    bypass = {"category": "ammo", "runtimePlan": {"resultKind": "ammo", "engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "ammo", "maxStack": 999, "craftYield": 50}},
        {"fn": "ammo_behavior", "params": {"ammoFor": "arrow"}},
    ]}}
    bypass_report = runtime_plan_validation_report(bypass)
    assert bypass_report["ok"] is False
    assert any("actual ammo requires explicit damageClass" in error for error in bypass_report["errors"])
    assert any("actual ammo requires explicit non-negative damage" in error for error in bypass_report["errors"])

    zero_weapon = {"category": "weapon", "runtimePlan": {"resultKind": "weapon", "engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 0, "useTimeTicks": 24, "maxStack": 1}},
        {"fn": "shoot_projectile", "params": {
            "runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight",
            "speed": 8, "rangeTiles": 20, "lifetimeTicks": 90, "shotCount": 1,
            "spreadRadians": 0, "pierce": 1,
        }},
    ]}}
    zero_report = runtime_plan_validation_report(zero_weapon)
    assert any("combat set_item_stats requires positive damage" in error for error in zero_report["errors"])

    light = {"category": "generic", "runtimePlan": {"resultKind": "generic", "engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "generic", "maxStack": 1}},
        {"fn": "emit_light", "params": {"strength": 1.0, "color": "cyan"}},
        {"fn": "set_alt_use_mode", "params": {"mode": "light", "durationTicks": 90}},
    ]}}
    light_report = runtime_plan_validation_report(light)
    assert light_report["ok"] is True, light_report["errors"]
    assert compile_runtime_plan_to_genome_patch(light)["altGeneratedBuff"]["durationTicks"] == 90


def _contract_check_armor_has_no_slot_datatable_budget() -> None:
    patch = compile_runtime_plan_to_genome_patch({
        "runtimePlan": {
            "resultKind": "armor",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "armor", "armorSlot": "head", "defense": 80}},
                {"fn": "armor_effect", "params": {
                    "armorSlot": "head",
                    "stats": {"movementSpeed": 0.8, "endurance": 0.2},
                }},
            ],
        },
    })
    armor = patch["armor"]
    assert armor["slot"] == "head"
    assert armor["defense"] == 80
    assert armor["movementSpeed"] == 0.8
    assert armor["endurance"] == 0.2
    assert "slotBudgetClamps" not in armor


def _contract_check_use_affordance_is_only_the_executable_surface() -> None:
    accepted = {
        "runtimePlan": {
            "resultKind": "generic",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "generic", "maxStack": 1}},
                {"fn": "use_affordance", "params": {
                    "autoReuse": False,
                    "useTurn": True,
                    "channelUse": True,
                    "itemScale": 1.25,
                    "holdoutOffsetX": 14,
                    "holdoutOffsetY": -6,
                    "heldVisibility": "show_item",
                    "releaseTiming": "on_release",
                    "handPose": "held_out",
                    "initialOffsetPx": 9,
                }},
            ],
        },
    }
    report = runtime_plan_boundary_report(accepted)
    assert report["ok"] is True, report["errors"]
    patch = compile_runtime_plan_to_genome_patch(accepted)
    for field, expected in {
        "autoReuse": False,
        "useTurn": True,
        "channelUse": True,
        "itemScale": 1.25,
        "holdoutOffsetX": 14,
        "holdoutOffsetY": -6,
        "heldVisibility": "show_item",
        "releaseTiming": "on_release",
        "handPose": "held_out",
        "initialOffsetPx": 9,
    }.items():
        assert patch[field] == expected

    rejected = {
        "runtimePlan": {
            "resultKind": "generic",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "generic", "maxStack": 1}},
                {"fn": "use_affordance", "params": {"projectileSizePolicy": "inherit_parent_floor"}},
            ],
        },
    }
    rejected_report = runtime_plan_boundary_report(rejected)
    assert rejected_report["ok"] is False
    assert any("projectileSizePolicy" in error for error in rejected_report["errors"])

    boundary = (ROOT / "LocalGenerator/infini_local/core/boundary_models.py").read_text(encoding="utf-8")
    model = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Model.cs").read_text(encoding="utf-8")
    for dead in ("useFantasy", "spawnStyle", "rotationMode", "trailMode", "projectileSizePolicy", "drawDuringUse"):
        assert dead not in boundary
    for dead in ("UseFantasy", "SpawnStyle", "RotationMode", "TrailMode", "ProjectileSizePolicy", "DrawDuringUse"):
        assert dead not in model


def _contract_check_primary_projectile_fields_are_authored_not_defaulted() -> None:
    incomplete = {
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 20, "useTimeTicks": 24}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot"}},
            ],
        },
    }
    report = runtime_plan_validation_report(incomplete)
    assert report["ok"] is False
    for field in ("delivery", "movement", "speed", "rangeTiles", "lifetimeTicks", "shotCount", "spreadRadians", "pierce"):
        assert any(field in error for error in report["errors"]), (field, report["errors"])
    patch = compile_runtime_plan_to_genome_patch(incomplete)
    for field in ("delivery", "movement", "speed", "rangeTiles", "lifetimeTicks", "shotCount", "spreadRadians", "pierce"):
        assert field not in patch

    complete = {
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 20, "useTimeTicks": 24}},
                {"fn": "shoot_projectile", "params": {
                    "runtimeFamily": "shoot",
                    "delivery": "shoot",
                    "movement": "straight",
                    "speed": 9.25,
                    "rangeTiles": 47,
                    "lifetimeTicks": 113,
                    "shotCount": 2,
                    "spreadRadians": 0.14,
                    "pierce": 3,
                }},
            ],
        },
    }
    complete_report = runtime_plan_validation_report(complete)
    assert complete_report["ok"] is True, complete_report["errors"]
    complete_patch = compile_runtime_plan_to_genome_patch(complete)
    assert {field: complete_patch[field] for field in ("delivery", "movement", "speed", "rangeTiles", "lifetimeTicks", "shotCount", "spreadRadians", "pierce")} == {
        "delivery": "shoot", "movement": "straight", "speed": 9.25, "rangeTiles": 47,
        "lifetimeTicks": 113, "shotCount": 2, "spreadRadians": 0.14, "pierce": 3,
    }


def _contract_check_family_specific_numbers_are_authored_not_defaulted() -> None:
    base_stats = {"fn": "set_item_stats", "params": {
        "resultKind": "weapon", "damageClass": "ranged", "damage": 20,
        "useTimeTicks": 24, "useAnimationTicks": 24,
    }}
    base_primary = {
        "movement": "straight", "speed": 9.0, "rangeTiles": 48,
        "lifetimeTicks": 120, "shotCount": 1, "spreadRadians": 0.0, "pierce": 1,
    }

    charge = {"category": "weapon", "runtimePlan": {"resultKind": "weapon", "engineCalls": [
        base_stats,
        {"fn": "fire_ranged_weapon", "params": {"family": "charge_release", **base_primary}},
    ]}}
    charge_report = runtime_plan_validation_report(charge)
    assert charge_report["ok"] is False
    assert any("chargeTicks" in error for error in charge_report["errors"])
    assert any("chargePowerMultiplier" in error for error in charge_report["errors"])
    charge_patch = compile_runtime_plan_to_genome_patch(charge)
    assert "chargeTicks" not in charge_patch
    assert "chargePowerMultiplier" not in charge_patch

    beam_stats = {"fn": "set_item_stats", "params": {
        "resultKind": "weapon", "damageClass": "magic", "damage": 20,
        "useTimeTicks": 24, "useAnimationTicks": 24,
    }}
    beam = {"category": "weapon", "runtimePlan": {"resultKind": "weapon", "engineCalls": [
        beam_stats,
        {"fn": "cast_magic_weapon", "params": {"family": "channelled_beam", **base_primary}},
    ]}}
    beam_report = runtime_plan_validation_report(beam)
    assert beam_report["ok"] is False
    for field in ("beamWidthPx", "beamChargeTicks", "immunityCooldown"):
        assert any(field in error for error in beam_report["errors"]), beam_report["errors"]

    overhead_params = {
        "family": "overhead_barrage", "movement": "phase", "speed": 7.0,
        "rangeTiles": 24, "lifetimeTicks": 240, "shotCount": 3,
        "spreadRadians": 0.0, "pierce": 1, "delayTicks": 0,
        "secondaryDamageMultiplier": 0.42, "secondaryLifetimeTicks": 77,
    }
    overhead = {"category": "weapon", "runtimePlan": {"resultKind": "weapon", "engineCalls": [
        base_stats,
        {"fn": "fire_ranged_weapon", "params": overhead_params},
    ]}}
    overhead_report = runtime_plan_validation_report(overhead)
    assert overhead_report["ok"] is True, overhead_report["errors"]
    overhead_patch = compile_runtime_plan_to_genome_patch(overhead)
    assert overhead_patch["delayTicks"] == 0
    assert overhead_patch["secondaryDamageMultiplier"] == 0.42
    assert overhead_patch["secondaryLifetimeTicks"] == 77

    hit_primary = {"fn": "fire_ranged_weapon", "params": {"family": "bow", **base_primary}}
    missing_hit_children = {"category": "weapon", "runtimePlan": {"resultKind": "weapon", "engineCalls": [
        base_stats,
        hit_primary,
        {"fn": "apply_on_hit_effect", "params": {"onHit": "overhead_barrage", "count": 3}},
    ]}}
    missing_hit_report = runtime_plan_validation_report(missing_hit_children)
    assert missing_hit_report["ok"] is False
    for field in ("secondaryDamageMultiplier", "secondaryLifetimeTicks"):
        assert any(field in error for error in missing_hit_report["errors"]), missing_hit_report["errors"]

    authored_hit_children = deepcopy(missing_hit_children)
    authored_hit_children["runtimePlan"]["engineCalls"][-1]["params"].update({
        "secondaryDamageMultiplier": 0.23,
        "secondaryLifetimeTicks": 131,
    })
    authored_hit_report = runtime_plan_validation_report(authored_hit_children)
    assert authored_hit_report["ok"] is True, authored_hit_report["errors"]
    authored_hit_patch = compile_runtime_plan_to_genome_patch(authored_hit_children)
    assert authored_hit_patch["secondaryDamageMultiplier"] == 0.23
    assert authored_hit_patch["secondaryLifetimeTicks"] == 131

    overhead_policy = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedOverheadBarragePolicy.cs").read_text(encoding="utf-8")
    overhead_runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.OverheadBarrage.cs").read_text(encoding="utf-8")
    impact_runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Impact.cs").read_text(encoding="utf-8")
    item_runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs").read_text(encoding="utf-8")
    projectile_runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    charge_runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.ChargeRelease.cs").read_text(encoding="utf-8")
    sentry_runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Sentry.cs").read_text(encoding="utf-8")
    assert "parent.Speed > 0f ? parent.Speed : 11f" not in overhead_policy
    assert "authoredSpreadRadians <= 0f ? 0.44f" not in overhead_policy
    assert "SecondaryDamageMultiplier <= 0f ? 0.55f" not in overhead_runtime
    assert "Math.Max(0.12f, attack.SecondaryDamageMultiplier)" not in item_runtime
    assert "Lifetime = Math.Clamp(parent.SecondaryLifetimeTicks, 5, 180)" in item_runtime
    assert "Math.Max(0.05f, _spec.SecondaryDamageMultiplier)" not in impact_runtime
    assert "Math.Clamp(_spec.SecondaryLifetimeTicks, 5, 180)" in projectile_runtime
    assert "Math.Max(1, Projectile.originalDamage)" not in charge_runtime
    assert "Math.Max(1, Projectile.damage)" not in projectile_runtime
    assert "Math.Max(1, Projectile.damage)" not in sentry_runtime


def _contract_check_csharp_timing_bounds_and_axe_display_are_consistent() -> None:
    normalize = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize.cs").read_text(encoding="utf-8")
    apply = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Apply.cs").read_text(encoding="utf-8")
    item = (ROOT / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs").read_text(encoding="utf-8")
    assert "Gameplay.UseTime = ClampInt(Gameplay.UseTime, 10, 3600);" in normalize
    assert "Gameplay.UseAnimation = ClampInt(Gameplay.UseAnimation, 6, 3600);" in normalize
    assert "item.useAnimation = Math.Max(6, Gameplay.UseAnimation);" in apply
    assert "data.Gameplay.AxePower * 5" in item

def _contract_check_blink_mobility_requires_authored_range_instead_of_runtime_defaults() -> None:
    primary = runtime_plan_validation_report({
        "runtimePlan": {
            "resultKind": "generic",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "generic", "maxStack": 1}},
                {"fn": "mobility_effect", "params": {"mode": "blink_to_cursor", "cooldownTicks": 0}},
            ],
        },
    })
    assert primary["ok"] is False
    assert any("rangeTiles" in error for error in primary["errors"])

    alt = runtime_plan_validation_report({
        "runtimePlan": {
            "resultKind": "generic",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "generic", "maxStack": 1}},
                {"fn": "set_alt_use_mode", "params": {"mode": "mobility", "mobilityMode": "blink_to_cursor", "cooldownTicks": 0}},
            ],
        },
    })
    assert alt["ok"] is False
    assert any("rangeTiles" in error for error in alt["errors"])


def _contract_check_composite_projectile_pressure_requires_llm_repair() -> None:
    defects = genome_defects({
        "gameplay": {"powerBudget": 1.0},
        "attack": {"genome": {
            "delivery": "shoot", "runtimeFamily": "straight_shot", "movement": "straight",
            "effect": "dust", "onHit": "none", "pullMode": "none", "pullStrength": 0,
            "useTimeTicks": 10, "shotCount": 8, "pierce": 1, "aoeRadiusTiles": 0,
            "rangeTiles": 60, "lifetimeTicks": 900, "speed": 12, "spreadRadians": 0,
            "extraUpdates": 3, "reliability": 1.0, "selfLockTicks": 0, "missPunish": 0,
        }},
    })
    assert any("composite projectile pressure" in defect for defect in defects)

    charge = {
        "delivery": "shoot", "runtimeFamily": "charge_release", "movement": "straight",
        "effect": "dust", "onHit": "none", "pullMode": "none", "pullStrength": 0,
        "useTimeTicks": 10, "chargeTicks": 10, "shotCount": 8, "pierce": 1, "aoeRadiusTiles": 0,
        "rangeTiles": 60, "lifetimeTicks": 900, "speed": 12, "spreadRadians": 0,
        "extraUpdates": 3, "reliability": 1.0, "selfLockTicks": 0, "missPunish": 0,
    }
    charge_metrics = estimate_engine_metrics(charge, {"powerBudget": 1.0})
    assert charge_metrics["activePrimaryProjectiles"] > 100
    charge_defects = genome_defects({"gameplay": {"powerBudget": 1.0}, "attack": {"genome": charge}})
    assert any("composite projectile pressure" in defect for defect in charge_defects)


def test_gameplay_authority_authorship_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            "_contract_check_llm_output_without_runtime_plan_never_falls_back_to_semantic_router",
            "_contract_check_parent_tags_and_damage_do_not_reclassify_explicit_generic",
            "_contract_check_compiler_never_inherits_parent_burn_or_default_debuff_duration",
            "_contract_check_generated_buffs_require_authored_duration_and_zero_consume_is_preserved",
            "_contract_check_nested_accessory_and_armor_stats_are_the_only_equipment_authority",
            "_contract_check_tool_power_is_explicit_and_modded_ranges_are_not_vanilla_capped",
            "_contract_check_secondary_fields_and_primary_debuff_survive_final_projection",
            "_contract_check_aoe_visual_and_contact_radii_are_independent",
            "_contract_check_csharp_accepts_loaded_mod_damage_classes_and_content_ids",
            "_contract_check_csharp_runtime_preserves_exact_equipment_network_and_buff_authority",
            "_contract_check_runtime_item_stats_survive_category_projection_without_parent_economy_or_stack_rewrites",
            "_contract_check_actual_ammo_preserves_authored_stats_and_presentation",
            "_contract_check_armor_has_no_slot_datatable_budget",
            "_contract_check_use_affordance_is_only_the_executable_surface",
            "_contract_check_primary_projectile_fields_are_authored_not_defaulted",
            "_contract_check_family_specific_numbers_are_authored_not_defaulted",
            "_contract_check_csharp_timing_bounds_and_axe_display_are_consistent",
            "_contract_check_blink_mobility_requires_authored_range_instead_of_runtime_defaults",
            "_contract_check_composite_projectile_pressure_requires_llm_repair",
        ),
    )
