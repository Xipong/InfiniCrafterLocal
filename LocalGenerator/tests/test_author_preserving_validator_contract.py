from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server
from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_patch


def _check_authored_damage_is_preserved_inside_broad_safety_envelope() -> None:
    debug: dict = {}
    stage = {"derivedDamage": 18, "powerBudget": 1.4}
    genome = {"shotCount": 1, "pierce": 0, "lifetimeTicks": 90}
    gp = {"damage": 42}
    assert server.authored_weapon_damage(gp, fallback=21, max_parent_damage=10, stage=stage, genome=genome, debug=debug) == 42
    assert debug["damageSource"] == "llm_authored_preserved"
    assert debug["referenceNumbersDamage"] == 21


def _check_authored_damage_only_clamps_absurd_outliers() -> None:
    debug: dict = {}
    stage = {"derivedDamage": 18, "powerBudget": 1.4}
    genome = {"shotCount": 5, "pierce": 6, "lifetimeTicks": 240}
    gp = {"damage": 9999}
    value = server.authored_weapon_damage(gp, fallback=14, max_parent_damage=10, stage=stage, genome=genome, debug=debug)
    assert value < 9999
    assert debug["authoredDamageClamp"]["reason"] == "hard_safety_cap"


def _check_non_explosive_magic_aoe_is_not_zeroed_by_family_lock() -> None:
    data: dict = {"tags": ["magic", "holy"]}
    stage = {"powerBudget": 1.5}
    g = {
        "delivery": "cast",
        "movement": "straight",
        "movementCode": server.MOVEMENT_CODE["straight"],
        "effect": "holy",
        "effectCode": server.EFFECT_CODE["holy"],
        "onHit": "aura_pulse",
        "onHitCode": server.ONHIT_CODE["aura_pulse"],
        "shotCount": 1,
        "pierce": 0,
        "aoeRadiusTiles": 1.4,
        "lifetimeTicks": 90,
        "rangeTiles": 40,
        "extraUpdates": 0,
        "homingStrength": 0,
    }
    out = server.apply_family_locks_to_genome(g, {"name": "A", "damage": 5}, {"name": "B", "damage": 5}, data, stage)
    assert out["effect"] == "holy"
    assert out["onHit"] == "aura_pulse"
    assert out["aoeRadiusTiles"] == 1.4


def _check_secondary_children_preserve_simple_debuff_intent() -> None:
    data = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damage": 12, "useTimeTicks": 24}},
        {"fn": "shoot_projectile", "params": {"delivery": "shoot", "movement": "straight"}},
        {"fn": "apply_on_hit_effect", "params": {"onHit": "frostburn"}},
        {"fn": "spawn_secondary_projectiles", "params": {"trigger": "on_hit", "count": 2, "damageMultiplier": 0.25}},
    ]}}
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["onHit"] == "split"
    assert patch["splitCount"] == 2
    assert patch["debuffHint"] == "frostburn"
    assert patch["secondaryPreservedDebuffOnHit"] == "frostburn"


def _check_secondary_children_do_not_replace_lifesteal_identity() -> None:
    data = {"runtimePlan": {"engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damage": 12, "useTimeTicks": 24}},
        {"fn": "shoot_projectile", "params": {"delivery": "shoot", "movement": "straight"}},
        {"fn": "apply_on_hit_effect", "params": {"onHit": "lifesteal"}},
        {"fn": "spawn_secondary_projectiles", "params": {"trigger": "on_hit", "count": 3, "damageMultiplier": 0.25}},
    ]}}
    patch = compile_runtime_plan_to_genome_patch(data)
    assert patch["onHit"] == "lifesteal"
    assert patch["splitCount"] == 0
    assert patch["maxChildProjectiles"] == 0
    assert patch["secondarySuppressedByPrimaryOnHit"] == "lifesteal"



def _check_behavior_digest_stays_raw_flag_based_for_owner_checked_projectiles() -> None:
    digest = server.projectile_behavior_digest_for_llm({
        "internalName": "Spear",
        "source": "item.shoot",
        "aiStyle": 19,
        "ownerHitCheck": True,
        "tileCollide": False,
        "penetrate": -1,
        "timeLeft": 3600,
        "width": 21,
        "height": 21,
    })
    assert digest["mechanicalHint"] == "owner_checked_close_or_held_hitbox"
    blob = str(digest).lower()
    assert "darklance" not in blob
    assert "trident" not in blob
    assert "vanilla" not in blob
    assert "long-lived projectile/effect" not in blob
    assert "not evidence of long free flight" in blob

def _check_behavior_policy_has_no_item_family_exception_table() -> None:
    bomb_parent = {"name": "Bomb", "tags": ["bomb", "explosive"], "damage": 0}
    flower_parent = {"name": "Sunflower", "tags": ["sunflower", "flower"], "damage": 0}
    a = server.behavior_policy_for_prompt(bomb_parent, flower_parent)
    b = server.behavior_policy_for_prompt(flower_parent, bomb_parent)
    assert a["family"] == "runtime_authored"
    assert b["family"] == "runtime_authored"
    assert "prefer" not in a and "forbid" not in a


def _check_projectile_name_does_not_infer_shuriken_family() -> None:
    data = {}
    parent = {"directProjectileRaw": {"internalName": "Shuriken", "width": 14, "height": 14, "aiStyle": 2}}
    assert server.infer_projectile_visual_family(data, parent, {}) == "generic_projectile"


def _check_parent_projectile_affordance_does_not_rewrite_motion_or_shape() -> None:
    genome = {
        "delivery": "shoot",
        "movement": "straight",
        "movementCode": server.MOVEMENT_CODE["straight"],
        "projectileShape": "authored weird seed-disc",
        "projectileWidth": 8,
        "projectileHeight": 8,
        "projectileScale": 1.0,
    }
    parent = {"directProjectileRaw": {"internalName": "WoodenArrowFriendly", "width": 10, "height": 28, "scale": 1.0, "aiStyle": 1, "arrow": True}}
    data = {"debug": {}}
    out = server.apply_parent_projectile_affordance(genome, parent, {}, set(), data, "ranged")
    assert out["movement"] == "straight"
    assert out["movementCode"] == server.MOVEMENT_CODE["straight"]
    assert out["projectileShape"] == "authored weird seed-disc"
    assert out["projectileWidth"] == 8
    assert out["projectileHeight"] == 8
    assert "reference only" in data["debug"]["parentProjectileRef"]

    opt_in = dict(genome)
    opt_in["projectileSizePolicy"] = "inherit_parent_floor"
    out2 = server.apply_parent_projectile_affordance(opt_in, parent, {}, set(), {}, "ranged")
    assert out2["projectileWidth"] >= 10
    assert out2["projectileHeight"] >= 28


if __name__ == "__main__":
    test_authored_damage_is_preserved_inside_broad_safety_envelope()
    test_authored_damage_only_clamps_absurd_outliers()
    test_non_explosive_magic_aoe_is_not_zeroed_by_family_lock()
    test_secondary_children_preserve_simple_debuff_intent()
    test_secondary_children_do_not_replace_lifesteal_identity()
    test_behavior_digest_stays_raw_flag_based_for_owner_checked_projectiles()
    test_behavior_policy_has_no_item_family_exception_table()
    test_projectile_name_does_not_infer_shuriken_family()
    test_parent_projectile_affordance_does_not_rewrite_motion_or_shape()
    print("OK author-preserving validator contract")

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_authored_damage_is_preserved_inside_broad_safety_envelope',
    '_check_authored_damage_only_clamps_absurd_outliers',
    '_check_non_explosive_magic_aoe_is_not_zeroed_by_family_lock',
    '_check_secondary_children_preserve_simple_debuff_intent',
    '_check_secondary_children_do_not_replace_lifesteal_identity',
    '_check_behavior_digest_stays_raw_flag_based_for_owner_checked_projectiles',
    '_check_behavior_policy_has_no_item_family_exception_table',
    '_check_projectile_name_does_not_infer_shuriken_family',
    '_check_parent_projectile_affordance_does_not_rewrite_motion_or_shape'
    ]:
        _fn = globals()[_name]
        _sig = _inspect.signature(_fn)
        _kwargs = {}
        if "tmp_path" in _sig.parameters:
            _case_dir = tmp_path / _name
            _case_dir.mkdir(parents=True, exist_ok=True)
            _kwargs["tmp_path"] = _case_dir
        if "monkeypatch" in _sig.parameters:
            with _pytest.MonkeyPatch.context() as _mp:
                _kwargs["monkeypatch"] = _mp
                _fn(**_kwargs)
        else:
            _fn(**_kwargs)


def test_author_preserving_validator_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)



def test_parent_projectile_reference_is_size_only_not_family_router(monkeypatch):
    from infini_local.pipelines import combine_pipeline as cp
    from infini_local.pipelines import projectile_affordance as pa

    profiles = {
        "small_arrow": {"internalName": "SmallArrow", "width": 8, "height": 28, "scale": 1.4, "arrow": True, "aiStyle": 1},
        "large_held": {"internalName": "LargeHeld", "width": 40, "height": 12, "scale": 1.0, "ownerHitCheck": True, "aiStyle": 19},
    }

    def fake_effective_projectile_profile_of(item):
        return profiles.get(item["id"], {})

    monkeypatch.setattr(pa, "effective_projectile_profile_of", fake_effective_projectile_profile_of)
    chosen = cp.choose_parent_projectile_size_reference({"id": "small_arrow"}, {"id": "large_held"})
    assert chosen["__parent"] == "max"
    assert chosen["width"] == 40
    assert chosen["height"] == 28
    assert chosen["scale"] == 1.4
    assert chosen["__sources"] == {"width": "B", "height": "A", "scale": "A", "primary": "B"}

    genome = {"delivery": "shoot", "projectileWidth": 4, "projectileHeight": 4, "projectileScale": 1.0}
    data = {"debug": {}}
    out = cp.apply_parent_projectile_affordance(genome, {"id": "small_arrow"}, {"id": "large_held"}, set(), data, "ranged")
    assert out["projectileWidth"] == 4
    assert out["projectileHeight"] == 4
    assert out["projectileScale"] == 1.0
    assert "delivery" in out and out["delivery"] == "shoot"
    assert "runtimeFamily" not in out
    assert "max raw parent projectile width/height/scale" in data["debug"]["parentProjectileRef"]
    assert "candidates" in data["debug"]["parentProjectileRef"]
    assert "reference only" in data["debug"]["parentProjectileRef"]

    opt_in = {**genome, "projectileSizePolicy": "inherit_parent_floor"}
    data2 = {"debug": {}}
    out2 = cp.apply_parent_projectile_affordance(opt_in, {"id": "small_arrow"}, {"id": "large_held"}, set(), data2, "ranged")
    assert out2["projectileWidth"] == 40
    assert out2["projectileHeight"] == 28
    assert out2["projectileScale"] == 1.4
    assert "\"appliedToGenome\": true" in data2["debug"]["parentProjectileRef"]
