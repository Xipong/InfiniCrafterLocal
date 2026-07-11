from __future__ import annotations

import json
from pathlib import Path

from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_patch
from infini_local.core.runtime_authoring.schema import (
    ENGINE_FN_CATALOG_V2,
    PLANNER_HIDDEN_ENGINE_FUNCTIONS,
)
from infini_local.pipelines.llm_authoring_prompt import build_llm_author_payload

ROOT = Path(__file__).resolve().parents[2]


def _plan(*calls: dict) -> dict:
    return {"runtimePlan": {"resultKind": "weapon", "engineCalls": list(calls)}}


def test_preserved_only_functions_stay_readable_but_out_of_active_prompt() -> None:
    payload = build_llm_author_payload(
        {"name": "Wooden Sword", "type": 24, "damage": 7},
        {"name": "Torch", "type": 8},
        {},
        {},
        "v10_hidden_functions",
    )
    functions = payload["engineRuntimeContract"]["availableFunctions"]
    assert set(PLANNER_HIDDEN_ENGINE_FUNCTIONS) == {"state_meter", "triggered_action"}
    assert set(PLANNER_HIDDEN_ENGINE_FUNCTIONS).issubset(ENGINE_FN_CATALOG_V2)
    assert not (set(functions) & set(PLANNER_HIDDEN_ENGINE_FUNCTIONS))

    # Old/debug payloads remain inspectable and inert instead of becoming an input migration layer.
    patch = compile_runtime_plan_to_genome_patch(_plan(
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 10}},
        {"fn": "cast_magic_weapon", "params": {"family": "staff"}},
        {"fn": "state_meter", "params": {"id": "charge", "maxValue": 3}},
    ))
    assert patch["runtimeFamily"] == "cast"
    assert patch["runtimeState"]["stateMeters"][0]["id"] == "charge"


def test_on_expire_is_one_exact_bounded_secondary_trigger() -> None:
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


def test_overhead_barrage_is_exact_generic_and_does_not_classify_staff_names() -> None:
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


def test_on_expire_does_not_create_an_implicit_second_child_lifecycle() -> None:
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


def test_overhead_barrage_report_names_its_real_child_source() -> None:
    from infini_local.core.runtime_authoring.reports import runtime_plan_provenance_report

    data = _plan(
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 28}},
        {"fn": "cast_magic_weapon", "params": {"family": "overhead_barrage", "delayTicks": 24, "shotCount": 3}},
    )
    patch = compile_runtime_plan_to_genome_patch(data)
    report = runtime_plan_provenance_report(data, patch)
    assert report["gameplayChildren"]["enabled"] is True
    assert report["gameplayChildren"]["source"] == "overhead_barrage"
    assert report["gameplayChildren"]["overheadBarrageChildEstimate"] == 3
