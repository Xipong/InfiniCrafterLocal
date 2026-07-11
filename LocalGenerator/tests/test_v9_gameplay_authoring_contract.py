from __future__ import annotations

from pathlib import Path

from infini_local.core.runtime_authoring import (
    compile_runtime_plan_to_genome_patch,
    compile_runtime_plan_to_genome_result,
)
from infini_local.pipelines.combine_gameplay import attach_gameplay_and_attack
from infini_local.pipelines.combine_validation import validate_and_repair
from infini_local.pipelines.engine_pressure_metrics import (
    effective_hit_cadence_ticks,
    estimate_engine_metrics,
)
from infini_local.pipelines.item_power_knowledge import apply_item_knowledge, canonicalize


ROOT = Path(__file__).resolve().parents[2]


def _magic_parent(name: str, damage: int, use_time: int) -> dict:
    return {
        "name": name,
        "internalName": name.replace(" ", ""),
        "sourceMod": "Terraria",
        "damage": damage,
        "damageClass": "magic",
        "useStyle": 5,
        "useTime": use_time,
        "useAnimation": use_time,
        "mana": 8,
        "rare": 3,
        "value": 12000,
        "maxStack": 1,
        "consumable": False,
        "material": False,
        "shoot": 1,
        "shootSpeed": 9.0,
    }


def _attach(plan: dict) -> dict:
    a = _magic_parent("Magic Missile", 35, 22)
    b = _magic_parent("Crystal Storm", 32, 20)
    ca = canonicalize(a)
    cb = canonicalize(b)
    data = validate_and_repair(plan, a, b, ca, cb, "v9_channel_beam_contract")
    data = apply_item_knowledge(data, a, b, ca, cb)
    return attach_gameplay_and_attack(data, a, b, ca, cb)


def test_exact_channelled_beam_reaches_final_attack_without_prose_inference() -> None:
    plan = {
        "name": "Totally Ordinary Stick",
        "tooltip": "This prose says sword, gun, prism and laser; none of it selects gameplay.",
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {
                    "fn": "set_item_stats",
                    "params": {
                        "resultKind": "weapon",
                        "damageClass": "magic",
                        "damage": 82,
                        "useTimeTicks": 31,
                        "useAnimationTicks": 39,
                        "knockback": 4.25,
                        "manaCost": 11,
                        "autoReuse": False,
                    },
                },
                {
                    "fn": "cast_magic_weapon",
                    "params": {
                        "family": "channelled_beam",
                        "rangeTiles": 62,
                        "beamWidthPx": 19,
                        "chargeTicks": 45,
                        "immunityCooldown": 8,
                        "effect": "electric",
                        "soundUseCatalogId": "laser_machine",
                        "soundImpactCatalogId": "impact_electric",
                    },
                },
            ],
        },
        "visual": {"itemPrompt": "A plain dark rod with a cyan emitter."},
    }

    data = _attach(plan)
    gp = data["gameplay"]
    attack = data["attack"]
    genome = attack["genome"]

    assert attack["runtimeFamily"] == "beam"
    assert attack["channelUse"] is True
    assert attack["rangeTiles"] == 62.0
    assert attack["beamWidthPx"] == 19.0
    assert attack["beamChargeTicks"] == 45
    assert attack["immunityCooldown"] == 8
    assert attack["soundUseCatalogId"] == "laser_machine"
    assert attack["soundImpactCatalogId"] == "impact_electric"
    assert gp["useTime"] == 31
    assert gp["useAnimation"] == 39
    assert gp["knockback"] == 4.25
    assert gp["manaCost"] == 11
    assert gp["autoReuse"] is False
    assert genome["runtimeFamily"] == "beam"
    assert genome["movement"] == "phase"
    assert "attackPatternTags" not in genome

    provenance = attack["runtimeAuthoringProvenance"]
    for field in ("useAnimationTicks", "knockback", "beamWidthPx", "beamChargeTicks", "immunityCooldown"):
        assert provenance["authoredFields"][field] is True
        assert provenance["fieldSources"][field] in {"set_item_stats", "shoot_projectile", "cast_magic_weapon"}


def test_beam_like_names_and_visual_prose_do_not_select_channel_beam() -> None:
    data = {
        "name": "Channelled Laser Prism Staff",
        "tooltip": "Hold to fire an endless wall-piercing beam.",
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 30, "useTimeTicks": 25}},
                {
                    "fn": "cast_magic_weapon",
                    "params": {
                        "family": "beam_staff",
                        "movement": "phase",
                        "projectileShape": "a continuous prism laser beam",
                    },
                },
            ]
        },
    }
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["runtimeFamily"] == "cast"
    assert not bool(patch.get("channelUse", False))
    assert patch["weaponFamily"] == "beam_staff"


def test_regular_homing_range_and_strength_are_not_dead_fields() -> None:
    data = {
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 28, "useTimeTicks": 24}},
                {
                    "fn": "shoot_projectile",
                    "params": {
                        "runtimeFamily": "cast",
                        "delivery": "cast",
                        "movement": "slow_homing",
                        "rangeTiles": 74,
                        "homingStrength": 0.83,
                    },
                },
            ]
        }
    }
    result = compile_runtime_plan_to_genome_result(data)
    assert result["patch"]["rangeTiles"] == 74.0
    assert result["patch"]["homingStrength"] == 0.83
    assert result["provenance"]["authoredFields"]["rangeTiles"] is True
    assert result["provenance"]["authoredFields"]["homingStrength"] is True


def test_beam_balance_uses_local_immunity_cadence_and_one_active_primary() -> None:
    beam = {
        "runtimeFamily": "beam",
        "useTimeTicks": 40,
        "immunityCooldown": 8,
        "shotCount": 1,
        "lifetimeTicks": 90,
        "beamWidthPx": 18,
        "reliability": 1.0,
    }
    normal = dict(beam, runtimeFamily="cast")
    assert effective_hit_cadence_ticks(beam, 40) == 8
    assert effective_hit_cadence_ticks(normal, 40) == 40
    metrics = estimate_engine_metrics(beam)
    assert metrics["activePrimaryProjectiles"] == 1.0
    assert metrics["effectiveHitCadenceTicks"] == 8.0
    assert metrics["hitEventsPerSecond"] == 7.5


def test_no_wiki_weapon_alias_router_and_csharp_beam_contract_is_exact() -> None:
    semantics = (ROOT / "LocalGenerator/infini_local/core/runtime_authoring/semantics.py").read_text(encoding="utf-8")
    assert "_WEAPON_SUBFAMILY_ALIASES" not in semantics
    assert "_material_effect_hint" not in semantics
    assert "_weapon_subfamily_from_fields" not in semantics
    assert "_attack_pattern_tags_from_patch" not in semantics

    item_source = (ROOT / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs").read_text(encoding="utf-8")
    projectile_source = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    net_source = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.NetSync.cs").read_text(encoding="utf-8")
    model_source = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Model.cs").read_text(encoding="utf-8")

    assert "generated.IsActiveBeamFor(Data?.Id)" in item_source
    assert "generated.IsActiveChargeFor(Data?.Id)" in item_source
    active_guard = item_source.split("string runtimeFamily = AttackRuntimeFamily(Data?.Attack);", 1)[1].split("string blocked", 1)[0]
    assert "GeneratedRuntimeFamilyPolicy.Beam" in active_guard
    assert "GeneratedRuntimeFamilyPolicy.ChargeRelease" in active_guard
    assert "ownedProjectileCounts" not in active_guard
    assert "Collision.LaserScan" in projectile_source
    assert "effective_hit_cadence_ticks" in (ROOT / "LocalGenerator/infini_local/pipelines/engine_pressure_metrics.py").read_text(encoding="utf-8")
    assert "ProjectileSyncVersion = 14" in net_source
    for field in ("RangeTiles", "HomingStrength", "BeamWidthPx", "BeamChargeTicks"):
        assert f"public" in model_source and field in model_source
        assert f"_spec.{field}" in net_source


def test_channel_beam_pays_authored_mana_and_respects_player_lockout() -> None:
    source = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    assert "private bool CanPayChannelBeamMana(Player owner)" in source
    assert "owner.HeldItem.mana" in source
    assert "owner.HeldItem.useTime" in source
    assert "owner.CheckMana(manaCost, true, false)" in source
    assert "owner.noItems || owner.CCed || !CanPayChannelBeamMana(owner)" in source
    assert "Projectile.owner != Main.myPlayer" in source
