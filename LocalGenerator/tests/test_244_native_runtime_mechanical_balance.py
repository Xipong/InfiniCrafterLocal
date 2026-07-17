from __future__ import annotations

from pathlib import Path

from infini_local.core.runtime_authoring.compiler import compile_runtime_plan_to_genome_patch
from infini_local.core.runtime_executor_vocabulary import MOVEMENT_CODE
from infini_local.core.runtime_family_policy import CANONICAL_RUNTIME_FAMILIES
from infini_local.pipelines.combine_balance import item_power_score, stat_profile_for
from infini_local.pipelines.combine_genome import genome_defects, llm_authored_weapon_genome
from infini_local.pipelines.engine_pressure_metrics import behavior_cost_multiplier
from infini_local.pipelines.item_power_knowledge import infer_item_card
from infini_local.pipelines.item_rarity_baseline import rarity_tier_estimate


ROOT = Path(__file__).resolve().parents[2]


def _raw_weapon(name: str, tags: list[str] | None = None) -> dict:
    return {
        "name": name,
        "sourceMod": "Terraria",
        "damage": 31,
        "damageClass": "melee",
        "useTime": 24,
        "useAnimation": 24,
        "knockback": 4.0,
        "rare": 3,
        "value": 18000,
        "tags": tags or [],
    }


def _contract_check_balance_power_ignores_fantasy_words_when_runtime_facts_match() -> None:
    plain = _raw_weapon("Plain Implement")
    bait = _raw_weapon(
        "True Zenith Lunar Solar Stardust Night Vortex Nebula",
        ["cosmic", "lunar", "solar", "vortex", "nebula", "stardust", "shadow", "void", "technology"],
    )
    assert item_power_score(plain) == item_power_score(bait)

    anchor = {
        "name": "Mechanical Anchor",
        "sourceMod": "Terraria",
        "damage": 18,
        "damageClass": "ranged",
        "useTime": 30,
        "useAnimation": 30,
        "rare": 2,
        "value": 9000,
    }
    plain_stage = stat_profile_for(plain, anchor, {"weapon", "melee", "ranged"})
    bait_stage = stat_profile_for(
        bait,
        anchor,
        {"weapon", "melee", "ranged", "cosmic", "lunar", "solar", "vortex", "nebula", "stardust", "shadow", "void", "technology"},
    )
    for key in ("derivedPower", "derivedDamage", "powerBudget", "name"):
        assert bait_stage[key] == plain_stage[key]


def _contract_check_unknown_mod_rarity_numeric_id_is_not_treated_as_progression_ordinal() -> None:
    low_id = rarity_tier_estimate(12, {"name": "UnknownA", "mod": "ExampleMod"})
    huge_id = rarity_tier_estimate(999, {"name": "UnknownB", "mod": "ExampleMod"})
    assert low_id["tierScore"] == 0
    assert huge_id["tierScore"] == 0
    assert low_id["role"] == huge_id["role"] == "unknown_modded_rarity"


def _contract_check_non_executable_metadata_cannot_buy_damage_budget() -> None:
    executable = {
        "runtimeFamily": "shoot", "shotCount": 1, "pierce": 1,
        "aoeRadiusTiles": 0, "homingStrength": 0, "lifetimeTicks": 90,
        "rangeTiles": 30, "useTimeTicks": 24,
    }
    honest = behavior_cost_multiplier(executable)
    bait = behavior_cost_multiplier({
        **executable,
        "reliability": 0.01,
        "selfLockTicks": 9999,
        "missPunish": 1,
    })
    assert bait == honest


def _contract_check_executable_pull_mode_survives_compile_and_costs_budget() -> None:
    plan = {
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {
                    "fn": "shoot_projectile",
                    "params": {
                        "runtimeFamily": "returning",
                        "delivery": "throw",
                        "movement": "returning_glaive",
                        "rangeTiles": 18,
                        "lifetimeTicks": 90,
                    },
                },
                {
                    "fn": "apply_on_hit_effect",
                    "params": {
                        "onHit": "none",
                        "pullStrength": 0.6,
                        "pullMode": "owner_to_target",
                    },
                },
            ],
        }
    }
    attack = compile_runtime_plan_to_genome_patch(plan)
    assert attack["pullStrength"] == 0.6
    assert attack["pullMode"] == "owner_to_target"

    base = {
        "runtimeFamily": "returning",
        "shotCount": 1,
        "pierce": -1,
        "aoeRadiusTiles": 0,
        "homingStrength": 0,
        "lifetimeTicks": 90,
        "rangeTiles": 18,
        "useTimeTicks": 24,
    }
    assert behavior_cost_multiplier({**base, "pullStrength": 0.6, "pullMode": "owner_to_target"}) > behavior_cost_multiplier(base)


def _contract_check_pull_mode_has_typed_networked_csharp_executor_lifecycle() -> None:
    boundary = (ROOT / "LocalGenerator/infini_local/core/boundary_models.py").read_text(encoding="utf-8")
    model = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Model.cs").read_text(encoding="utf-8")
    normalize = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize.cs").read_text(encoding="utf-8")
    net_sync = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.NetSync.cs").read_text(encoding="utf-8")
    impact = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Impact.cs").read_text(encoding="utf-8")

    assert 'pullMode: Literal["none", "target_to_owner", "owner_to_target", "target_to_projectile"]' in boundary
    assert "public string PullMode" in model
    assert "NormalizePullMode(Attack.PullMode, Attack.PullStrength)" in normalize
    assert 'if (Attack.PullMode == "none") Attack.PullStrength = 0f;' in normalize
    send_extra_ai = net_sync.split("public override void SendExtraAI", 1)[1].split("public override void ReceiveExtraAI", 1)[0]
    assert "_spec." not in send_extra_ai
    assert "TryGetAttack(_generatedItemId)" in net_sync
    assert "GeneratedChildSpecPolicy.TryCreateRuntimeVariant" in net_sync
    assert "_spec.PullMode" in impact
    assert 'case "target_to_owner"' in impact
    assert 'case "owner_to_target"' in impact
    assert 'case "target_to_projectile"' in impact


def _contract_check_blackhole_pull_requires_explicit_target_to_projectile_mode() -> None:
    plan = {
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "shoot_projectile", "params": {
                    "runtimeFamily": "cast", "delivery": "cast", "movement": "blackhole_pull",
                    "rangeTiles": 20, "lifetimeTicks": 90,
                }},
                {"fn": "apply_on_hit_effect", "params": {
                    "onHit": "none", "pullStrength": 0.55, "pullMode": "target_to_projectile",
                }},
            ],
        }
    }
    attack = compile_runtime_plan_to_genome_patch(plan)
    assert attack["pullMode"] == "target_to_projectile"
    assert attack["pullStrength"] == 0.55
    assert behavior_cost_multiplier(attack) > behavior_cost_multiplier({**attack, "pullStrength": 0.0, "pullMode": "none"})

    runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    blackhole = runtime[runtime.index("private void BlackholePull"):runtime.index("private void ProximityMissile")]
    assert '_spec.PullMode != "target_to_projectile"' in blackhole
    assert "npc.DirectionTo(Projectile.Center)" in blackhole


def _contract_check_native_held_family_lifecycles_follow_tmodloader_patterns() -> None:
    runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    impact = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Impact.cs").read_text(encoding="utf-8")

    flail = runtime[runtime.index("private bool ApplyFlailTetherAI"):runtime.index("private bool ApplyYoyoHoverAI")]
    assert "owner.noItems" in flail and "owner.CCed" in flail
    assert "!owner.channel" in flail and "BeginReturningPhase()" in flail
    assert "owner.heldProj = Projectile.whoAmI" in flail
    tile_collision_assignment = next(line for line in runtime.splitlines() if "Projectile.tileCollide = !heldLike" in line)
    assert "!flailLike" not in tile_collision_assignment
    assert "movement != 16" not in tile_collision_assignment
    assert "if (_spec.MovementCode is 5 or 14 || IsFlailDelivery())" in runtime

    yoyo = runtime[runtime.index("private bool ApplyYoyoHoverAI"):runtime.index("private void FillGeneratedWhipControlPoints")]
    assert "Projectile.ai[0]" in yoyo and "Projectile.ai[1]" in yoyo
    assert "aim.Length()" in yoyo and "Math.Min" in yoyo
    assert "BeginReturningPhase()" in yoyo and "Projectile.netUpdate = true" in yoyo
    assert "owner.noItems" in yoyo and "owner.CCed" in yoyo

    whip_collision = impact[impact.index("public override bool? Colliding"):impact.index("private int ProjectileHitboxRadiusBonus")]
    assert "FillGeneratedWhipControlPoints" in whip_collision
    assert "for (int i = 1; i < _whipControlPoints.Count; i++)" in whip_collision


def _contract_check_runtime_family_matrix_covers_every_canonical_family_and_movement() -> None:
    matrix = ROOT / "docs/TERRARIA_RUNTIME_FAMILY_MATRIX_RU.md"
    assert matrix.exists(), "native lifecycle matrix must be checked into docs"
    text = matrix.read_text(encoding="utf-8")
    for family in sorted(CANONICAL_RUNTIME_FAMILIES):
        assert f"| `{family}` |" in text
    for movement, code in MOVEMENT_CODE.items():
        assert f"| {code} | `{movement}` |" in text
    for source_pin in (
        "tModLoader/tModLoader",
        "codingwatching/terraria-1.4.4.5-source-code",
        "CalamityTeam/CalamityModPublic",
        "Fargowilta/FargowiltasSouls",
    ):
        assert source_pin in text


def _contract_check_remaining_finite_families_keep_structural_native_boundaries() -> None:
    runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    impact = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Impact.cs").read_text(encoding="utf-8")
    sentry = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Sentry.cs").read_text(encoding="utf-8")
    sentry_item = (ROOT / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.Sentry.cs").read_text(encoding="utf-8")
    overhead = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.OverheadBarrage.cs").read_text(encoding="utf-8")
    schema = (ROOT / "LocalGenerator/infini_local/core/runtime_authoring/schema.py").read_text(encoding="utf-8")

    orbit = runtime[runtime.index("private void Orbitish"):runtime.index("private void SpiralOut")]
    assert "_spec.RangeTiles * 16f" in orbit and "owner.MountedCenter" in orbit
    blackhole = runtime[runtime.index("private void BlackholePull"):runtime.index("private void ProximityMissile")]
    assert '_spec.PullMode != "target_to_projectile"' in blackhole
    assert "ShouldRunNpcGameplay()" in blackhole and "npc.netUpdate = true" in blackhole
    assert "MovementCode == 15" in impact and "Projectile.scale / _spec.ProjectileScale" in impact
    assert "UpdateMaxTurrets()" in sentry_item
    assert "GeneratedChildSpecPolicy.ConfigureSentryShot" in sentry
    assert "RuntimeFamily = GeneratedRuntimeFamilyPolicy.Shoot" in (
        ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedChildSpecPolicy.cs"
    ).read_text(encoding="utf-8")
    assert "ShouldRunProjectileGameplay" in overhead and "Projectile.Kill()" in overhead
    assert "not a persistent terraria minion" in schema.lower()


def _contract_check_python_v3_author_contract_does_not_cross_csharp_wire() -> None:
    model = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Model.cs").read_text(encoding="utf-8")
    assert "RuntimeContractSpec" not in model
    assert "MechanicBackingRefSpec" not in model
    assert "PlayerViewTimeline" not in model


def _contract_check_executor_specific_movement_mismatches_are_rejected() -> None:
    base = {
        "runtimeFamily": "flail",
        "delivery": "flail",
        "movement": "straight",
        "effect": "none",
        "onHit": "none",
        "useTimeTicks": 24,
        "shotCount": 1,
        "pierce": 1,
        "aoeRadiusTiles": 0,
        "lifetimeTicks": 90,
        "rangeTiles": 20,
    }
    defects = genome_defects({"attack": {"genome": base}})
    assert any("runtimeFamily=flail requires movement=flail_tether" in defect for defect in defects)

    base["runtimeFamily"] = "shoot"
    base["delivery"] = "shoot"
    base["movement"] = "whip_lash"
    defects = genome_defects({"attack": {"genome": base}})
    assert any("movement=whip_lash requires runtimeFamily=whip" in defect for defect in defects)


def _contract_check_starfury_style_affordance_survives_actual_genome_sanitizer() -> None:
    data = {
        "name": "Astral Edge",
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 34, "useTimeTicks": 22}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "overhead_barrage", "delivery": "swing", "movement": "phase", "weaponFamily": "broadsword", "projectileFamily": "star", "speed": 10, "shotCount": 1, "spreadRadians": 0, "pierce": 1, "rangeTiles": 50, "lifetimeTicks": 90}},
            ],
        },
    }
    data["attack"] = {"enabled": True, "genome": compile_runtime_plan_to_genome_patch(data)}
    stage = {"name": "pre_boss", "powerBudget": 1.5, "derivedDamage": 34}
    genome = llm_authored_weapon_genome(data, _raw_weapon("Gold Broadsword"), {"name": "Fallen Star", "rare": 1, "value": 500}, stage)
    assert genome["useStyleCode"] == 1
    assert genome["hideUseGraphic"] is False
    assert genome["disableItemMeleeHitbox"] is False


def _contract_check_csharp_native_family_guards_are_behavioral_not_prose() -> None:
    family = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedRuntimeFamilyPolicy.cs").read_text(encoding="utf-8")
    runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    impact = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Impact.cs").read_text(encoding="utf-8")

    assert "HasCompatibleMovement" in family
    assert "BeginReturningPhase" in runtime
    assert "MovementCode is 5 or 14" in impact
    assert "IsFlailDelivery()" in runtime and "BeginReturningPhase" in runtime
    assert "whipLike" in runtime and "? -1" in runtime
    assert "ShouldRunNpcGameplay()" in runtime.split("private void BlackholePull()", 1)[1]
    assert "return base.CanHitNPC(target);" in impact


def _contract_check_returning_hit_starts_return_without_disabling_return_path_damage() -> None:
    projectile = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.cs").read_text(encoding="utf-8")
    runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    impact = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Impact.cs").read_text(encoding="utf-8")
    net_sync = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.NetSync.cs").read_text(encoding="utf-8")

    # Terraria 1.4.4.5 aiStyle 3: the first outbound hit flips ai[0] to the
    # returning state, but penetrate remains -1 and return-path hits stay live.
    combined = projectile + runtime + impact + net_sync
    assert "_remainingHitBudget" not in combined
    returning_hit = impact.split("if (_spec.MovementCode is 5 or 14)", 1)[1].split("// If an overlay carrier", 1)[0]
    assert "if (!_returningPhase)" in returning_hit
    assert "BeginReturningPhase();" in returning_hit
    can_hit = impact.split("public override bool? CanHitNPC", 1)[1].split("public override void OnHitNPC", 1)[0]
    assert "MovementCode is 5 or 14" not in can_hit


def _contract_check_parent_progression_ignores_ammo_placeholder_and_persistent_root_spawn_stats() -> None:
    technical_root = {
        "type": 10,
        "penetrate": -1,
        "maxPenetrate": -1,
        "timeLeft": 3600,
        "extraUpdates": 0,
        "tileCollide": False,
        "ownerHitCheck": False,
        "usesLocalNPCImmunity": False,
        "usesIDStaticNPCImmunity": False,
        "aiStyle": 6,
        "friendly": True,
        "fromLiveWireRaw": True,
    }
    weak_material = {"name": "Weak Catalyst", "sourceMod": "Terraria", "damage": 0, "rare": 0, "value": 100, "maxStack": 999, "material": True}
    ammo_user = {
        "name": "Rapid Ammo User", "sourceMod": "Terraria", "damage": 6, "damageClass": "ranged",
        "useTime": 8, "useAnimation": 8, "shoot": 10, "shootSpeed": 7, "useAmmo": 1,
        "rare": 2, "value": 350000, "maxStack": 1, "noMelee": True,
        "directProjectileRaw": technical_root,
    }
    disposable = {
        "name": "Stacked Throwable", "sourceMod": "Terraria", "damage": 60, "damageClass": "ranged",
        "useTime": 45, "useAnimation": 45, "shoot": 30, "shootSpeed": 5.5,
        "rare": 0, "value": 75, "maxStack": 999, "consumable": True,
        "directProjectileRaw": {**technical_root, "tileCollide": True, "aiStyle": 16},
    }
    persistent_root = {
        "name": "Persistent Root Spawner", "sourceMod": "Terraria", "damage": 8, "damageClass": "summon",
        "useTime": 28, "useAnimation": 28, "shoot": 266, "shootSpeed": 10,
        "rare": 4, "value": 100000, "maxStack": 1,
        "directProjectileRaw": {**technical_root, "tileCollide": True, "aiStyle": 26, "minion": True, "timeLeft": 18000},
    }
    rank = {name: index for index, name in enumerate(("wood", "early", "pre_boss", "pre_hardmode_late", "hardmode_early", "mech", "plantera", "lunar", "endgame"))}
    ammo_stage = stat_profile_for(ammo_user, weak_material, {"weapon", "ranged", "ammo"})
    disposable_stage = stat_profile_for(disposable, weak_material, {"weapon", "ranged", "consumable"})
    persistent_stage = stat_profile_for(persistent_root, weak_material, {"weapon", "summon", "minion"})
    assert rank[ammo_stage["name"]] <= rank["pre_boss"]
    assert rank[disposable_stage["name"]] <= rank["pre_boss"]
    assert rank[persistent_stage["name"]] <= rank["pre_hardmode_late"]


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_244_native_runtime_mechanical_balance_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_balance_power_ignores_fantasy_words_when_runtime_facts_match',
            '_contract_check_unknown_mod_rarity_numeric_id_is_not_treated_as_progression_ordinal',
            '_contract_check_non_executable_metadata_cannot_buy_damage_budget',
            '_contract_check_executable_pull_mode_survives_compile_and_costs_budget',
            '_contract_check_pull_mode_has_typed_networked_csharp_executor_lifecycle',
            '_contract_check_blackhole_pull_requires_explicit_target_to_projectile_mode',
            '_contract_check_native_held_family_lifecycles_follow_tmodloader_patterns',
            '_contract_check_runtime_family_matrix_covers_every_canonical_family_and_movement',
            '_contract_check_remaining_finite_families_keep_structural_native_boundaries',
            '_contract_check_python_v3_author_contract_does_not_cross_csharp_wire',
            '_contract_check_executor_specific_movement_mismatches_are_rejected',
            '_contract_check_starfury_style_affordance_survives_actual_genome_sanitizer',
            '_contract_check_csharp_native_family_guards_are_behavioral_not_prose',
            '_contract_check_returning_hit_starts_return_without_disabling_return_path_damage',
            '_contract_check_parent_progression_ignores_ammo_placeholder_and_persistent_root_spawn_stats',
        ),
    )
