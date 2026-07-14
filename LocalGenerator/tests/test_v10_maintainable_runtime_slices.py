from __future__ import annotations

from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_patch


def _plan(*calls: dict) -> dict:
    return {"runtimePlan": {"resultKind": "weapon", "engineCalls": list(calls)}}


def _contract_check_on_expire_is_one_exact_bounded_secondary_trigger() -> None:
    patch = compile_runtime_plan_to_genome_patch(_plan(
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 20}},
        {"fn": "cast_magic_weapon", "params": {"family": "staff", "projectileShape": "orb"}},
        {"fn": "spawn_secondary_projectiles", "params": {
            "trigger": "on_expire",
            "count": 3,
            "damageMultiplier": 0.3,
            "lifetimeTicks": 28,
            "projectileShape": "small shard",
        }},
    ))
    assert patch["secondaryTrigger"] == "on_expire"
    assert patch["splitCount"] == 3
    assert patch["maxChildProjectiles"] == 3
    assert patch["maxChildDepth"] == 1
    assert patch["onHit"] == "none"

    rejected = compile_runtime_plan_to_genome_patch(_plan(
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 20}},
        {"fn": "cast_magic_weapon", "params": {"family": "staff"}},
        {"fn": "spawn_secondary_projectiles", "params": {"trigger": "when_destroyed", "count": 3}},
    ))
    assert rejected["splitCount"] == 0
    assert rejected["rejectedSecondaryCalls"][0]["reason"] == "unsupported_secondary_trigger"


def _contract_check_overhead_barrage_is_exact_generic_and_does_not_classify_staff_names() -> None:
    barrage = compile_runtime_plan_to_genome_patch(_plan(
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 28}},
        {"fn": "cast_magic_weapon", "params": {
            "family": "overhead_barrage",
            "projectileFamily": "arrow",
            "projectileShape": "wooden arrow",
            "effect": "none",
            "delayTicks": 42,
            "shotCount": 4,
            "rangeTiles": 55,
        }},
    ))
    assert barrage["runtimeFamily"] == "overhead_barrage"
    assert barrage["delayTicks"] == 42
    assert barrage["shotCount"] == 4
    assert barrage["maxChildProjectiles"] == 4
    assert barrage["maxChildDepth"] == 1
    assert barrage["projectileFamily"] == "arrow"
    assert barrage["effect"] == "none"

    ordinary_staff = compile_runtime_plan_to_genome_patch(_plan(
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 28}},
        {"fn": "cast_magic_weapon", "params": {"family": "starfall_staff", "projectileFamily": "star"}},
    ))
    assert ordinary_staff["runtimeFamily"] == "cast"
    assert "delayTicks" not in ordinary_staff


def _contract_check_on_expire_does_not_create_an_implicit_second_child_lifecycle() -> None:
    patch = compile_runtime_plan_to_genome_patch(_plan(
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 20}},
        {"fn": "cast_magic_weapon", "params": {"family": "staff", "projectileShape": "orb"}},
        {"fn": "apply_on_hit_effect", "params": {"onHit": "overhead_barrage", "count": 4}},
        {"fn": "spawn_secondary_projectiles", "params": {
            "trigger": "on_expire",
            "count": 3,
            "projectileShape": "small shard",
        }},
    ))
    assert patch["onHit"] == "overhead_barrage"
    assert patch["splitCount"] == 4
    assert patch.get("secondaryTrigger", "on_hit") == "on_hit"
    assert patch["rejectedSecondaryCalls"][0]["reason"] == "on_expire_conflicts_with_child_producing_on_hit"


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_v10_maintainable_runtime_slices_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_on_expire_is_one_exact_bounded_secondary_trigger',
            '_contract_check_overhead_barrage_is_exact_generic_and_does_not_classify_staff_names',
            '_contract_check_on_expire_does_not_create_an_implicit_second_child_lifecycle',
        ),
    )
