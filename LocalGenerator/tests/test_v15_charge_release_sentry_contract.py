from __future__ import annotations

from pathlib import Path

import pytest

from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_patch

ROOT = Path(__file__).resolve().parents[2]


def _plan(*calls: dict) -> dict:
    return {"runtimePlan": {"engineCalls": list(calls)}}


def _contract_check_charge_release_compiles_as_exact_held_root() -> None:
    patch = compile_runtime_plan_to_genome_patch(_plan(
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged"}},
        {"fn": "fire_ranged_weapon", "params": {
            "family": "charge_release", "projectileFamily": "crystal_bolt",
            "chargeTicks": 72, "chargePowerMultiplier": 1.85,
            "shotCount": 3, "spreadRadians": 0.22,
        }},
        {"fn": "apply_on_hit_effect", "params": {"onHit": "burn"}},
    ))
    assert patch["runtimeFamily"] == "charge_release"
    assert patch["delivery"] == "shoot"
    assert patch["chargeTicks"] == 72
    assert patch["chargePowerMultiplier"] == 1.85
    assert patch["channelUse"] is True
    assert patch["onHit"] == "burn"
    assert patch["shotCount"] == 3


def _contract_check_charge_release_rejects_vanilla_ammo() -> None:
    with pytest.raises(ValueError, match="charge_release_does_not_support_vanilla_ammo"):
        compile_runtime_plan_to_genome_patch(_plan(
            {"fn": "fire_ranged_weapon", "params": {"family": "charge_release", "ammoFor": "arrow"}},
        ))


def _contract_check_sentry_compiles_bounded_lifetime_budget() -> None:
    patch = compile_runtime_plan_to_genome_patch(_plan(
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "summon"}},
        {"fn": "deploy_sentry", "params": {
            "placement": "floating", "attackIntervalTicks": 40,
            "targetRangeTiles": 28, "helperLifetimeTicks": 600,
            "shotCount": 2, "projectileShape": "crystal turret",
            "secondaryProjectileShape": "crystal bolt",
        }},
    ))
    assert patch["runtimeFamily"] == "sentry"
    assert patch["delivery"] == "summon"
    assert patch["damageClass"] == "summon"
    assert patch["sentryPlacement"] == "floating"
    assert patch["sentryAttackIntervalTicks"] == 40
    assert patch["sentryTargetRangeTiles"] == 28
    assert patch["sentryLifetimeTicks"] == 600
    assert patch["maxChildProjectiles"] == 30
    assert patch["maxChildDepth"] == 1
    assert patch["secondaryProjectileShape"] == "crystal bolt"


def _contract_check_sentry_rejects_recursive_child_mechanics() -> None:
    with pytest.raises(ValueError, match="sentry_does_not_support_child_producing_onhit"):
        compile_runtime_plan_to_genome_patch(_plan(
            {"fn": "deploy_sentry", "params": {"onHit": "mini_missiles", "shotCount": 1}},
        ))
    with pytest.raises(ValueError, match="sentry_does_not_support_secondary_projectile_triggers"):
        compile_runtime_plan_to_genome_patch(_plan(
            {"fn": "deploy_sentry", "params": {}},
            {"fn": "spawn_secondary_projectiles", "params": {"trigger": "on_hit", "count": 2}},
        ))


def _contract_check_sentry_flags_are_applied_only_after_runtime_spec_hydration() -> None:
    source = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    defaults = source.split("public override void SetDefaults()", 1)[1].split("private void DisableUnsupportedProjectile", 1)[0]
    configured = source.split("private void ApplyConfiguredStats()", 1)[1].split("public override void AI()", 1)[0]
    assert "Projectile.sentry = false;" in defaults
    assert "Projectile.netImportant = false;" in defaults
    assert "sentryLike" not in defaults
    assert "Projectile.sentry = sentryLike;" in configured
    assert "Projectile.netImportant = sentryLike;" in configured


def _contract_check_item_and_projectile_share_one_damage_class_policy() -> None:
    policy = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedDamageClassPolicy.cs").read_text(encoding="utf-8")
    item = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Apply.cs").read_text(encoding="utf-8")
    projectile = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    assert "public static DamageClass Resolve(string? raw)" in policy
    assert "GeneratedDamageClassPolicy.Resolve(Gameplay.DamageClass)" in item
    assert "GeneratedDamageClassPolicy.Resolve(_spec.DamageClass)" in projectile
    assert "private static DamageClass ResolveDamageClass" not in item
    assert "Projectile.DamageType = DamageClass.Generic;" in projectile  # safe pre-hydration default only


def _contract_check_charge_and_sentry_provenance_keeps_authored_family_call_owner() -> None:
    from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_result

    charged = compile_runtime_plan_to_genome_result({
        "runtimePlan": {"engineCalls": [{
            "fn": "fire_ranged_weapon",
            "params": {"family": "charge_release", "chargeTicks": 64, "chargePowerMultiplier": 1.9},
        }]}
    })
    assert charged["provenance"]["fieldSources"]["chargeTicks"] == "fire_ranged_weapon"
    assert charged["provenance"]["fieldSources"]["chargePowerMultiplier"] == "fire_ranged_weapon"

    sentry = compile_runtime_plan_to_genome_result({
        "runtimePlan": {"engineCalls": [{
            "fn": "deploy_sentry",
            "params": {
                "placement": "floating",
                "attackIntervalTicks": 36,
                "targetRangeTiles": 26,
                "helperLifetimeTicks": 900,
                "secondaryProjectileShape": "single crystal bolt",
                "onHit": "poison",
            },
        }]}
    })
    sources = sentry["provenance"]["fieldSources"]
    for field in (
        "sentryPlacement", "sentryAttackIntervalTicks", "sentryTargetRangeTiles",
        "sentryLifetimeTicks", "secondaryProjectileShape", "onHit",
    ):
        assert sources[field] == "deploy_sentry"


def _contract_check_runtime_plan_normalization_preserves_raw_function_owner_across_repeated_passes() -> None:
    from infini_local.core.runtime_authoring import normalize_runtime_plan_inplace

    payload = {"runtimePlan": {"engineCalls": [{
        "fn": "deploy_sentry",
        "params": {"placement": "grounded", "attackIntervalTicks": 40},
    }]}}
    normalize_runtime_plan_inplace(payload)
    normalize_runtime_plan_inplace(payload)
    call = payload["runtimePlan"]["engineCalls"][0]
    assert call["fn"] == "shoot_projectile"
    assert call["_rawFn"] == "deploy_sentry"
    assert call["_semanticFn"] == "deploy_sentry"


def _v15_parent(name: str, damage_class: str) -> dict:
    return {
        "name": name,
        "internalName": name.replace(" ", ""),
        "sourceMod": "Terraria",
        "damage": 30,
        "damageClass": damage_class,
        "useStyle": 5,
        "useTime": 25,
        "useAnimation": 25,
        "mana": 8 if damage_class == "magic" else 0,
        "rare": 3,
        "value": 10000,
        "maxStack": 1,
        "consumable": False,
        "material": False,
        "shoot": 1,
        "shootSpeed": 9.0,
    }


def _attach_v15(plan: dict, a: dict, b: dict) -> dict:
    from infini_local.pipelines.combine_gameplay import attach_gameplay_and_attack
    from infini_local.pipelines.combine_validation import validate_and_repair
    from infini_local.pipelines.item_power_knowledge import apply_item_knowledge, canonicalize

    ca, cb = canonicalize(a), canonicalize(b)
    data = validate_and_repair(plan, a, b, ca, cb, "v15_full_projection")
    data = apply_item_knowledge(data, a, b, ca, cb)
    return attach_gameplay_and_attack(data, a, b, ca, cb)


def _contract_check_charge_release_survives_full_gameplay_projection_for_ranged_and_magic() -> None:
    cases = [
        ("ranged", "fire_ranged_weapon", 50, 1.8),
        ("magic", "cast_magic_weapon", 40, 2.0),
    ]
    for damage_class, fn, charge_ticks, multiplier in cases:
        plan = {
            "name": f"Charged {damage_class}",
            "category": "weapon",
            "runtimePlan": {"resultKind": "weapon", "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": damage_class, "damage": 42, "useTimeTicks": 28, "manaCost": 9 if damage_class == "magic" else 0}},
                {"fn": fn, "params": {"family": "charge_release", "chargeTicks": charge_ticks, "chargePowerMultiplier": multiplier, "projectileFamily": "orb" if damage_class == "magic" else "arrow", "movement": "straight", "speed": 10, "rangeTiles": 55, "lifetimeTicks": 120, "shotCount": 1, "spreadRadians": 0, "pierce": 1, "projectileShape": "one charged projectile"}},
            ]},
        }
        data = _attach_v15(plan, _v15_parent("Parent A", damage_class), _v15_parent("Parent B", damage_class))
        assert data["gameplay"]["damageClass"] == damage_class
        assert data["attack"]["damageClass"] == damage_class
        assert data["attack"]["runtimeFamily"] == "charge_release"
        assert data["attack"]["chargeTicks"] == charge_ticks
        assert data["attack"]["chargePowerMultiplier"] == multiplier
        assert data["attack"]["genome"]["damageClass"] == damage_class


def _contract_check_sentry_survives_full_gameplay_projection_with_live_child_budget() -> None:
    plan = {
        "name": "Crystal Sentry",
        "category": "weapon",
        "runtimePlan": {"resultKind": "weapon", "engineCalls": [
            {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "summon", "damage": 30, "manaCost": 10, "useTimeTicks": 30}},
            {"fn": "deploy_sentry", "params": {"placement": "floating", "attackIntervalTicks": 36, "targetRangeTiles": 26, "helperLifetimeTicks": 900, "shotCount": 2, "speed": 11, "spreadRadians": 0.2, "pierce": 1, "movement": "straight", "effect": "poison", "onHit": "poison", "projectileShape": "crystal sentry core", "secondaryProjectileShape": "single crystal bolt", "secondaryLifetimeTicks": 50}},
        ]},
    }
    data = _attach_v15(plan, _v15_parent("Summon A", "summon"), _v15_parent("Summon B", "summon"))
    attack = data["attack"]
    assert data["gameplay"]["damageClass"] == "summon"
    assert attack["damageClass"] == "summon"
    assert attack["runtimeFamily"] == "sentry"
    assert attack["sentryPlacement"] == "floating"
    assert attack["sentryAttackIntervalTicks"] == 36
    assert attack["sentryTargetRangeTiles"] == 26.0
    assert attack["sentryLifetimeTicks"] == 900
    assert attack["secondaryLifetimeTicks"] == 50
    assert attack["secondaryProjectileShape"] == "single crystal bolt"
    assert attack["maxChildProjectiles"] == 48
    assert attack["maxChildDepth"] == 1


def _contract_check_charge_release_sound_occurs_on_release_not_item_press() -> None:
    apply = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Apply.cs").read_text(encoding="utf-8")
    charge = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.ChargeRelease.cs").read_text(encoding="utf-8")
    branch = apply.split("else if (chargeReleaseLike)", 1)[1].split("else if (sentryLike)", 1)[0]
    assert "item.UseSound = null;" in branch
    assert "InfiniSoundLibrary.ForUse" in charge
    assert "SoundEngine.PlaySound(releaseSound, Projectile.Center)" in charge


def _contract_check_invalid_charge_or_sentry_runtime_contract_is_inert_in_csharp() -> None:
    policy = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedRuntimeFamilyPolicy.cs").read_text(encoding="utf-8")
    normalize = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize.cs").read_text(encoding="utf-8")
    runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    assert "HasValidExecutorContract(AttackSpec? spec)" in policy
    assert 'return delivery is "shoot" or "cast" or "throw";' in policy
    assert 'return delivery == "summon" && spec.SentryPlacement is "grounded" or "floating";' in policy
    assert "Attack.Enabled = false;" in normalize
    assert "GeneratedRuntimeFamilyPolicy.HasValidExecutorContract(_spec)" in runtime


def _contract_check_sentry_reuses_concurrent_shot_budget_until_authored_lifetime_expires() -> None:
    source = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Sentry.cs").read_text(encoding="utf-8")
    block = source.split("int count = RuntimeChildCount", 1)[1].split("float spread", 1)[0]
    impact = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Impact.cs").read_text(encoding="utf-8")
    policy = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedChildSpecPolicy.cs").read_text(encoding="utf-8")
    budget = impact.split("private int RemainingGameplayChildBudget", 1)[1].split("private bool CanRunChildEffect", 1)[0]
    assert "Projectile.Kill();" not in block
    assert "return true;" in block
    assert "IsSentryDelivery()" in budget
    assert "CountOwnedGeneratedProjectiles(rootId)" in budget
    assert "sentry_shot" not in source
    assert "sentry_shot" not in policy


def _contract_check_child_image_prompt_is_generic_secondary_body_not_forced_mote() -> None:
    from infini_local.pipelines.visual_prompt_contracts import build_child_image_prompt

    prompt = build_child_image_prompt({
        "name": "Crystal Sentry",
        "attack": {
            "runtimeFamily": "sentry",
            "secondaryProjectileShape": "single crystal bolt",
            "primaryColorName": "cyan",
        },
    }).lower()
    assert "single crystal bolt" in prompt
    assert "one authored child-projectile texture/composition" in prompt
    assert "preserve explicitly authored connected parts" in prompt
    assert "tiny echo spark/mote" not in prompt


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_v15_charge_release_sentry_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_charge_release_compiles_as_exact_held_root',
            '_contract_check_charge_release_rejects_vanilla_ammo',
            '_contract_check_sentry_compiles_bounded_lifetime_budget',
            '_contract_check_sentry_rejects_recursive_child_mechanics',
            '_contract_check_sentry_flags_are_applied_only_after_runtime_spec_hydration',
            '_contract_check_item_and_projectile_share_one_damage_class_policy',
            '_contract_check_charge_and_sentry_provenance_keeps_authored_family_call_owner',
            '_contract_check_runtime_plan_normalization_preserves_raw_function_owner_across_repeated_passes',
            '_contract_check_charge_release_survives_full_gameplay_projection_for_ranged_and_magic',
            '_contract_check_sentry_survives_full_gameplay_projection_with_live_child_budget',
            '_contract_check_charge_release_sound_occurs_on_release_not_item_press',
            '_contract_check_invalid_charge_or_sentry_runtime_contract_is_inert_in_csharp',
            '_contract_check_sentry_reuses_concurrent_shot_budget_until_authored_lifetime_expires',
            '_contract_check_child_image_prompt_is_generic_secondary_body_not_forced_mote',
        ),
    )
