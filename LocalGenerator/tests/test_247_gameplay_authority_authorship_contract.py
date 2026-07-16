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
from infini_local.pipelines.llm_authoring_prompt import build_llm_author_payload, normalize_runtime_authoring_fields
from infini_local.pipelines.llm_authoring_pipeline import (
    _public_clause_matches_claim,
    planner_runtime_promise_gate,
    validate_final_runtime_promise_boundary,
)
from infini_local.pipelines.combine_genome import genome_defects
from infini_local.pipelines.engine_pressure_metrics import estimate_engine_metrics
from infini_local.core.runtime_contracts import resolve_mechanic_backing_refs
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.boundary_models import runtime_plan_boundary_report
from infini_local.core.runtime_authoring.schema import accepted_engine_param_names
from infini_local.core.contract_versions import PLANNER_PROMPT_PROFILE_VERSION, RUNTIME_CONTRACT_SCHEMA_VERSION


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

    incomplete_public_contract = {
        "name": "Structured Result",
        "category": "weapon",
        "tooltip": "Launches one authored projectile; grants an unrelated public bonus.",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 20, "useTimeTicks": 24}},
                _primary("cast", "cast", "straight", 60),
            ],
        },
        "runtimeContract": {
            "playerViewTimeline": ["press use", "projectile spawns", "projectile travels", "projectile expires"],
            "mechanicClaims": [{
                "claim": "Launches one authored projectile.",
                "status": "executable",
                "backingRefs": [{"source": "engineCall", "callIndex": 1, "fn": "shoot_projectile", "field": "shotCount", "expected": 1}],
            }],
        },
    }
    promise_gate = planner_runtime_promise_gate(incomplete_public_contract, enforce_public_contract=True)
    assert promise_gate["ok"] is False
    assert any(row.get("kind") == "tooltip_clause_missing_mechanic_claim" for row in promise_gate["blockingClaims"])
    assert _public_clause_matches_claim(
        "Hold to channel starlight, then release to teleport to cursor within 45 tiles.",
        "Hold to charge starlight; release teleports to the cursor within 45 tiles.",
    ) is True
    assert _public_clause_matches_claim("Does not consume arrows.", "Consumes arrows.") is False
    assert _public_clause_matches_claim("Teleports up to 45 tiles.", "Teleports up to 40 tiles.") is False
    assert _public_clause_matches_claim("Grants an unrelated public bonus.", "Launches one authored projectile.") is False

    lowered_alias_contract = {
        "name": "Stationary Helper",
        "category": "weapon",
        "tooltip": "Deploys a stationary helper.",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "summon", "damage": 12, "useTimeTicks": 30}},
                {"fn": "deploy_sentry", "params": {"placement": "grounded", "attackIntervalTicks": 60, "targetRangeTiles": 10, "helperLifetimeTicks": 600, "shotCount": 1, "speed": 3, "spreadRadians": 0, "pierce": 1, "movement": "straight", "projectileShape": "helper"}},
            ],
        },
        "runtimeContract": {
            "playerViewTimeline": ["press use", "helper appears", "helper attacks", "helper expires"],
            "mechanicClaims": [{
                "claim": "Deploys a stationary helper.",
                "status": "executable",
                "backingRefs": [{"source": "engineCall", "callIndex": 1, "fn": "deploy_sentry", "field": "helperLifetimeTicks", "expected": 600}],
            }],
        },
    }
    assert planner_runtime_promise_gate(lowered_alias_contract, enforce_public_contract=True)["ok"] is True

    unrelated_active_ref = {
        "name": "False Proof",
        "category": "weapon",
        "tooltip": "Can be placed as a temporary crafting tile that lasts 30 seconds.",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "melee", "damage": 12, "useTimeTicks": 20}},
                {"fn": "set_alt_use_mode", "params": {"mode": "generated_buff", "generatedBuff": {"durationTicks": 1800, "emitLightStrength": 0.5}}},
            ],
        },
        "runtimeContract": {
            "playerViewTimeline": ["press alt", "buff starts", "light is visible", "buff expires"],
            "mechanicClaims": [{
                "claim": "Can be placed as a temporary crafting tile that lasts 30 seconds.",
                "status": "executable",
                "backingRefs": [{"source": "engineCall", "callIndex": 1, "fn": "set_alt_use_mode", "field": "mode", "expected": "generated_buff"}],
            }],
        },
    }
    irrelevant_gate = planner_runtime_promise_gate(unrelated_active_ref, enforce_public_contract=True)
    assert irrelevant_gate["ok"] is False
    assert any(row.get("kind") == "mechanic_claim_backing_irrelevant" for row in irrelevant_gate["blockingClaims"])

    mixed_surface = deepcopy(unrelated_active_ref)
    mixed_surface["tooltip"] = "Deals 12 melee damage; Can be placed as a temporary crafting tile that lasts 30 seconds."
    mixed_surface["runtimeContract"]["mechanicClaims"].insert(0, {
        "claim": "Deals 12 melee damage.",
        "status": "executable",
        "backingRefs": [{"source": "engineCall", "callIndex": 0, "fn": "set_item_stats", "field": "damage", "expected": 12}],
    })
    mixed_surface["runtimeContract"]["syncFields"] = ["fictionalMeter"]
    assert planner_runtime_promise_gate(mixed_surface, enforce_public_contract=True)["ok"] is False
    with pytest.raises(PlannerUnavailable):
        validate_final_runtime_promise_boundary(mixed_surface)
    with pytest.raises(PlannerUnavailable):
        validate_final_runtime_promise_boundary(unrelated_active_ref)


def _contract_check_structural_v3_proves_signature_against_final_wire() -> None:
    authored = {
        "category": "weapon",
        "concept": {
            "fantasy": "A tethered projectile.",
            "mergeLogic": "The parents provide the projectile and tether roles.",
            "weirdTwist": {
                "text": "A hit pulls the target toward the owner.",
                "claimIds": ["signature_pull"],
            },
        },
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {
                    "callId": "item_stats",
                    "fn": "set_item_stats",
                    "params": {
                        "resultKind": "weapon",
                        "damageClass": "melee",
                        "damage": 18,
                        "useTimeTicks": 24,
                    },
                },
                {
                    "callId": "primary_projectile",
                    **_primary("thrust", "thrust", "straight", 45),
                },
                {
                    "callId": "signature_pull_call",
                    "fn": "apply_on_hit_effect",
                    "params": {
                        "pullMode": "target_to_owner",
                        "pullStrength": 0.4,
                    },
                },
                {
                    "callId": "secondary_burst_call",
                    "fn": "spawn_secondary_projectiles",
                    "params": {
                        "trigger": "on_hit",
                        "count": 3,
                        "damageMultiplier": 0.35,
                        "projectileShape": "tether spark",
                        "material": "rope",
                    },
                },
            ],
        },
        "runtimeContract": {
            "schema": "infini.runtime-contract.v3",
            "signatureMode": "mechanic",
            "signatureClaimId": "signature_pull",
            "tooltipClaimIds": ["primary_attack", "signature_pull", "secondary_burst"],
            "mechanicClaims": [
                {
                    "claimId": "primary_attack",
                    "playerText": "Launches one tethered projectile.",
                    "status": "executable",
                    "backingRefs": [{
                        "source": "engineCall",
                        "callId": "primary_projectile",
                        "field": "runtimeFamily",
                        "expected": "thrust",
                    }],
                },
                {
                    "claimId": "signature_pull",
                    "playerText": "A hit pulls the target toward the owner.",
                    "status": "executable",
                    "backingRefs": [
                        {
                            "source": "engineCall",
                            "callId": "signature_pull_call",
                            "field": "pullMode",
                            "expected": "target_to_owner",
                        },
                        {
                            "source": "engineCall",
                            "callId": "signature_pull_call",
                            "field": "pullStrength",
                            "expected": 0.4,
                        },
                    ],
                },
                {
                    "claimId": "secondary_burst",
                    "playerText": "A hit releases three tether sparks.",
                    "status": "executable",
                    "backingRefs": [{
                        "source": "engineCall",
                        "callId": "secondary_burst_call",
                        "field": "count",
                        "expected": 3,
                    }],
                },
            ],
            "playerViewTimeline": [
                {"phase": "use", "text": "The projectile launches.", "claimIds": ["primary_attack"]},
                {"phase": "travel", "text": "The tether remains visible.", "presentationOnly": True},
                {"phase": "hit", "text": "The target is pulled and sparks release.", "claimIds": ["signature_pull", "secondary_burst"]},
                {"phase": "expiry", "text": "The projectile expires.", "claimIds": ["primary_attack"]},
            ],
            "unsupportedPromises": [],
            "executionStatus": "executable",
        },
    }

    planner_gate = planner_runtime_promise_gate(deepcopy(authored), enforce_public_contract=True)
    assert planner_gate["ok"] is True
    assert planner_gate["schema"] == "infini.structural-planner-contract-report.v1"

    final_item = _attach(authored)
    report = validate_final_runtime_promise_boundary(final_item)

    assert report["ok"] is True
    assert final_item["runtimeContract"]["schema"] == "infini.runtime-contract.v3"
    assert final_item["runtimeContract"]["signatureClaimId"] == "signature_pull"
    assert final_item["tooltip"] == "Launches one tethered projectile; A hit pulls the target toward the owner; A hit releases three tether sparks"
    receipts = report["finalWireReceipts"]
    assert final_item["debug"]["finalWireExecutionReceipts"] == receipts
    assert {(row["finalPath"], row["status"]) for row in receipts} == {
        ("attack.runtimeFamily", "active"),
        ("attack.pullMode", "active"),
        ("attack.pullStrength", "active"),
        ("attack.maxChildProjectiles", "active"),
        ("attack.splitCount", "active"),
    }

    redundant = deepcopy(authored)
    redundant["runtimePlan"]["engineCalls"][0]["params"]["consumable"] = False
    redundant["runtimeContract"]["tooltipClaimIds"].append("no_op_identity")
    redundant["runtimeContract"]["mechanicClaims"].append({
        "claimId": "no_op_identity",
        "playerText": "The ordinary weapon is not consumed.",
        "status": "executable",
        "backingRefs": [{
            "source": "engineCall",
            "callId": "item_stats",
            "field": "consumable",
            "expected": False,
        }],
    })
    redundant["runtimeContract"]["playerViewTimeline"][0]["claimIds"].append("no_op_identity")
    assert planner_runtime_promise_gate(redundant, enforce_public_contract=True)["ok"] is True
    redundant_final = _attach(redundant)
    redundant_receipts = redundant_final["runtimeContract"]["finalWireReceipts"]
    assert any(row["claimId"] == "no_op_identity" and row["status"] == "dropped" for row in redundant_receipts)
    with pytest.raises(PlannerUnavailable, match="final_wire_ref_dropped"):
        validate_final_runtime_promise_boundary(redundant_final)

    drifted = deepcopy(final_item)
    drifted["attack"]["pullStrength"] = 0.2
    with pytest.raises(PlannerUnavailable, match="final_wire_ref_mismatched"):
        validate_final_runtime_promise_boundary(drifted)
    assert any(
        row.get("finalPath") == "attack.pullStrength" and row.get("status") == "mismatched"
        for row in drifted["debug"]["finalWireExecutionReceipts"]
    )

    unlinked = deepcopy(authored)
    unlinked["runtimeContract"]["playerViewTimeline"][2]["claimIds"] = ["primary_attack"]
    unlinked_gate = planner_runtime_promise_gate(unlinked, enforce_public_contract=True)
    assert unlinked_gate["ok"] is False
    assert any(row.get("kind") == "signature_missing_from_timeline" for row in unlinked_gate["blockingClaims"])

    nested_source = deepcopy(authored)
    nested_source["runtimePlan"]["engineCalls"].append({
        "callId": "accessory_stats",
        "fn": "accessory_effect",
        "params": {"archetype": "mobility", "stats": {"movementSpeed": 0.3}},
    })
    nested_source["runtimeContract"]["mechanicClaims"][1]["backingRefs"] = [{
        "source": "engineCall",
        "callId": "accessory_stats",
        "field": "stats.movementSpeed",
        "expected": 0.3,
    }]
    assert planner_runtime_promise_gate(nested_source, enforce_public_contract=True)["ok"] is True

    forged_receipts = deepcopy(authored)
    forged_receipts["runtimeContract"]["finalWireReceipts"] = [{
        "callId": "signature_pull_call",
        "field": "pullStrength",
        "finalPath": "attack.pullStrength",
        "status": "active",
    }]
    forged_gate = planner_runtime_promise_gate(forged_receipts, enforce_public_contract=True)
    assert forged_gate["ok"] is False
    assert any(row.get("kind") == "model_authored_final_wire_receipts" for row in forged_gate["blockingClaims"])

    forged_final_path = deepcopy(authored)
    forged_final_path["runtimeContract"]["mechanicClaims"][1]["backingRefs"][0]["finalPath"] = "attack.pullMode"
    forged_path_gate = planner_runtime_promise_gate(forged_final_path, enforce_public_contract=True)
    assert forged_path_gate["ok"] is False
    assert any(row.get("kind") == "model_authored_final_wire_fields" for row in forged_path_gate["blockingClaims"])

    precompiled = deepcopy(final_item)
    precompiled["runtimeContract"]["finalWireReceipts"] = []
    precompiled = _attach(precompiled)
    precompiled_report = validate_final_runtime_promise_boundary(precompiled)
    assert precompiled_report["ok"] is True
    assert all(
        row["status"] in {"active", "normalized", "clamped"}
        for row in precompiled_report["finalWireReceipts"]
    )

    from infini_local.pipelines.combine_pipeline import _cached_payload_passes_executable_boundary

    cache_parent_a = _parent("Parent A")
    cache_parent_b = _parent("Parent B")
    cache_parent_args = {
        "parent_a": cache_parent_a,
        "parent_b": cache_parent_b,
        "canonical_a": canonicalize(cache_parent_a),
        "canonical_b": canonicalize(cache_parent_b),
    }
    cached_v3 = deepcopy(final_item)
    assert _cached_payload_passes_executable_boundary(
        cached_v3,
        recipe_key_value="v3",
        source="test",
        **cache_parent_args,
    ) is True

    cached_failed = deepcopy(final_item)
    cached_failed["sourceMode"] = "failed"
    assert _cached_payload_passes_executable_boundary(
        cached_failed,
        recipe_key_value="failed-v3",
        source="test",
        **cache_parent_args,
    ) is False

    forged_cache = deepcopy(final_item)
    forged_receipt = forged_cache["runtimeContract"]["finalWireReceipts"][0]
    forged_receipt["finalPath"] = "gameplay.damage"
    forged_receipt["compiledValue"] = forged_cache["gameplay"]["damage"]
    forged_receipt["status"] = "active"
    assert _cached_payload_passes_executable_boundary(
        forged_cache,
        recipe_key_value="forged-v3",
        source="test",
        **cache_parent_args,
    ) is False

    cached_v2 = deepcopy(final_item)
    cached_v2["runtimeContract"]["schema"] = "infini.runtime-contract.v2"
    assert _cached_payload_passes_executable_boundary(
        cached_v2,
        recipe_key_value="v2",
        source="test",
        **cache_parent_args,
    ) is False


def _contract_check_planner_prompt_requires_structural_v3() -> None:
    a = _parent("Prompt Parent A", damage=12, damage_class="melee")
    b = _parent("Prompt Parent B", tags=["material"])
    payload = build_llm_author_payload(a, b, canonicalize(a), canonicalize(b), "structural-v3-contract")
    required = payload["requiredJsonShape"]
    contract = required["runtimeContract"]
    assert contract["schema"] == "infini.runtime-contract.v3"
    assert contract["signatureMode"] == "mechanic|visual"
    assert contract["signatureClaimId"] == "model-selected stable claimId"
    assert contract["tooltipClaimIds"] == ["ordered claimIds"]
    claim_shape = contract["mechanicClaims"][0]
    assert set(claim_shape) == {"claimId", "playerText", "backingRefs", "status"}
    assert set(claim_shape["backingRefs"][0]) == {"source", "callId", "field", "expected"}
    assert required["runtimePlan"]["engineCalls"] == "array of {callId, fn, params}"
    timeline_shape = contract["playerViewTimeline"][0]
    assert set(timeline_shape) == {"phase", "text", "claimIds", "presentationOnly"}
    assert RUNTIME_CONTRACT_SCHEMA_VERSION == "infini.runtime-contract.v3"
    assert "structural_final_wire_v3" in PLANNER_PROMPT_PROFILE_VERSION


def _contract_check_final_wire_gate_runs_before_images_and_after_final_clamps() -> None:
    source = (ROOT / "LocalGenerator/infini_local/pipelines/combine_pipeline.py").read_text(encoding="utf-8")
    gameplay_compile = source.index('step("04_author_gameplay_to_runtime_envelope"')
    structural_preflight = source.index('step("04d_structural_final_wire_preflight"')
    image_generation = source.index('step("09_visual_asset_generation"')
    final_normalize_stage = source.index('step("12_final_normalize"')
    post_clamp_gate = source.index('step("12a_final_runtime_promise_boundary"')
    assert gameplay_compile < structural_preflight < image_generation
    assert final_normalize_stage < post_clamp_gate


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

    child_effect_without_count = {
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 20, "useTimeTicks": 25}},
                _primary("shoot", "shoot", "straight", 60),
                {"fn": "apply_on_hit_effect", "params": {
                    "onHit": "starburst",
                    "secondaryDamageMultiplier": 0.5,
                    "secondaryLifetimeTicks": 20,
                }},
            ],
        },
    }
    child_report = runtime_plan_validation_report(child_effect_without_count)
    assert child_report["ok"] is False
    assert any("onHit=starburst" in error and "count" in error for error in child_report["errors"])

    machine_backed, failures = resolve_mechanic_backing_refs(
        child_effect_without_count,
        compile_runtime_plan_to_genome_patch(child_effect_without_count),
        {"backingRefs": [{"source": "engineCall", "callIndex": 2, "fn": "apply_on_hit_effect", "field": "onHit", "expected": "starburst"}]},
    )
    assert machine_backed is False
    assert any("inactive_compiled_field" in failure for failure in failures)


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

    one_tick_hold = {
        "runtimePlan": {
            "resultKind": "generic",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "generic", "maxStack": 1}},
                {"fn": "hold_item_effect", "params": {"generatedBuff": {"durationTicks": 1, "movementSpeed": 0.15}}},
            ],
        },
    }
    hold_report = runtime_plan_validation_report(one_tick_hold)
    assert hold_report["ok"] is False
    assert any("at least 2 ticks" in error for error in hold_report["errors"])

    duration_only = deepcopy(missing_duration)
    duration_only["runtimePlan"]["engineCalls"][-1]["params"]["generatedBuff"] = {"durationTicks": 60}
    duration_only_report = runtime_plan_validation_report(duration_only)
    assert duration_only_report["ok"] is False
    assert any("executable effect" in error for error in duration_only_report["errors"])

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

    potion_light = _attach({
        "category": "potion",
        "runtimePlan": {
            "resultKind": "potion",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "potion", "maxStack": 30, "consumable": True, "healLife": 150}},
                {"fn": "emit_light", "params": {"strength": 0.6, "color": "cyan", "durationTicks": 600}},
            ],
        },
    })
    use_buff = potion_light["gameplay"]["generatedBuff"]
    assert use_buff["durationTicks"] == 600
    assert use_buff["emitLightStrength"] == 0.6
    assert use_buff["lightColorName"] == "cyan"


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
    alt_capability = item[item.index("private static bool HasExecutableAltUse"):item.index("private string AltUseSummary")]
    assert 'mobilityMode == "recall_home"' in alt_capability
    assert 'mobilityMode == "blink_to_cursor" && gp.AltMobilityRangeTiles > 0' in alt_capability
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
    debuff_body = projectile_impact[
        projectile_impact.index("private void ApplyValidatedDebuff"):
        projectile_impact.index("private void ApplyAuthoredPull")
    ]
    heal_body = projectile_impact[
        projectile_impact.index("private void HealOwner"):
        projectile_impact.index("private int RemainingGameplayChildBudget")
    ]
    assert "ShouldRunNpcGameplay()" in debuff_body
    assert "ShouldRunLocalPlayerAction(owner)" in heal_body

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

    zero_damage_child = deepcopy(authored_hit_children)
    zero_damage_child["runtimePlan"]["engineCalls"][0]["params"]["damage"] = 1
    zero_damage_child["runtimePlan"]["engineCalls"][-1]["params"]["secondaryDamageMultiplier"] = 0.23
    zero_child_report = runtime_plan_validation_report(zero_damage_child)
    assert zero_child_report["ok"] is False
    assert any("rounds to zero damage" in error for error in zero_child_report["errors"])

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
    beam_mana = projectile_runtime[projectile_runtime.index("private bool CanPayChannelBeamMana"):projectile_runtime.index("private bool ApplyChannelBeamAI")]
    assert "activeTick != 1" not in beam_mana
    assert "activeTick % cadenceTicks != 0" in beam_mana


def _contract_check_csharp_timing_bounds_and_axe_display_are_consistent() -> None:
    normalize = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize.cs").read_text(encoding="utf-8")
    apply = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Apply.cs").read_text(encoding="utf-8")
    item = (ROOT / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs").read_text(encoding="utf-8")
    projectile = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    assert "Gameplay.UseTime = ClampInt(Gameplay.UseTime, 10, 3600);" in normalize
    assert "Gameplay.UseAnimation = ClampInt(Gameplay.UseAnimation, 6, 3600);" in normalize
    assert "item.useAnimation = Math.Max(6, Gameplay.UseAnimation);" in apply
    assert "int lifetimeUpdates = Projectile.extraUpdates + 1;" in projectile
    assert "_spec.Lifetime * lifetimeUpdates" in projectile
    assert "data.Gameplay.AxePower * 5" in item

def _contract_check_blink_mobility_requires_authored_range_instead_of_runtime_defaults() -> None:
    primary_missing_mode = runtime_plan_validation_report({
        "runtimePlan": {
            "resultKind": "generic",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "generic", "maxStack": 1}},
                {"fn": "mobility_effect", "params": {"rangeTiles": 10, "cooldownTicks": 30}},
            ],
        },
    })
    assert primary_missing_mode["ok"] is False
    assert any("mobility mode" in error for error in primary_missing_mode["errors"])

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

    alt_missing_mode = runtime_plan_validation_report({
        "runtimePlan": {
            "resultKind": "generic",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "generic", "maxStack": 1}},
                {"fn": "set_alt_use_mode", "params": {"mode": "mobility", "rangeTiles": 10, "cooldownTicks": 30}},
            ],
        },
    })
    assert alt_missing_mode["ok"] is False
    assert any("mobilityMode" in error for error in alt_missing_mode["errors"])

    alt_empty_buff = runtime_plan_validation_report({
        "runtimePlan": {
            "resultKind": "generic",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "generic", "maxStack": 1}},
                {"fn": "set_alt_use_mode", "params": {"mode": "generated_buff", "generatedBuff": {"durationTicks": 60}}},
            ],
        },
    })
    assert alt_empty_buff["ok"] is False
    assert any("executable generatedBuff effect" in error for error in alt_empty_buff["errors"])

    alt_dark_light = runtime_plan_validation_report({
        "runtimePlan": {
            "resultKind": "generic",
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "generic", "maxStack": 1}},
                {"fn": "set_alt_use_mode", "params": {"mode": "light", "durationTicks": 60}},
                {"fn": "emit_light", "params": {"strength": 0, "color": "blue"}},
            ],
        },
    })
    assert alt_dark_light["ok"] is False
    assert any("positive emit_light strength" in error for error in alt_dark_light["errors"])


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


def _contract_check_active_engine_cards_execute_authored_visual_and_summon_fields() -> None:
    assert "durationTicks" in accepted_engine_param_names("emit_light")
    assert "durationTicks" in accepted_engine_param_names("spawn_contact_particles")
    assert {"fieldLifetimeTicks", "fieldRadiusTiles", "tickRate"} <= accepted_engine_param_names("leave_trail_or_field")
    from infini_local.core.runtime_authoring.engine_call_contracts import validate_engine_call_params

    for fn in ("accessory_effect", "armor_effect"):
        parsed, errors = validate_engine_call_params(fn, {"stats": {"whipRange": 0.2, "summonTagDamage": 0.15}})
        assert not errors
        assert parsed and parsed["stats"] == {"whipRange": 0.2, "summonTagDamage": 0.15}

    visual_plan = {"runtimePlan": {"resultKind": "weapon", "engineCalls": [
        {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 12, "useTimeTicks": 20, "useAnimationTicks": 20}},
        {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "speed": 8, "rangeTiles": 30, "lifetimeTicks": 90, "shotCount": 1, "spreadRadians": 0, "pierce": 1}},
        {"fn": "emit_light", "params": {"strength": 0.7, "color": "blue", "durationTicks": 41}},
        {"fn": "spawn_contact_particles", "params": {"effect": "electric", "amount": 8, "scale": 1.2, "durationTicks": 23}},
        {"fn": "leave_trail_or_field", "params": {"trailLength": 6, "fieldLifetimeTicks": 80, "fieldRadiusTiles": 3.5, "tickRate": 9, "visualOnly": True}},
    ]}}
    patch = compile_runtime_plan_to_genome_patch(visual_plan)
    assert patch["runtimeLightDurationTicks"] == 41
    assert patch["vfxParticleDurationTicks"] == 23
    assert patch["vfxFieldLifetimeTicks"] == 80
    assert patch["vfxFieldRadiusTiles"] == 3.5
    assert patch["vfxFieldTickRate"] == 9
    item = _attach({"category": "weapon", **visual_plan})
    assert item["attack"]["runtimeLightDurationTicks"] == 41
    assert item["attack"]["vfxParticleDurationTicks"] == 23
    assert item["attack"]["vfxFieldLifetimeTicks"] == 80
    assert item["attack"]["vfxFieldRadiusTiles"] == 3.5
    assert item["attack"]["vfxFieldTickRate"] == 9

    projectile_visuals = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Visuals.cs").read_text(encoding="utf-8")
    projectile_runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    generated_item = (ROOT / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs").read_text(encoding="utf-8")
    net_sync = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.NetSync.cs").read_text(encoding="utf-8")
    tag_runtime = (ROOT / "ModSources/InfiniCrafterLocal/Common/Players/GeneratedWhipTagGlobalNPC.cs").read_text(encoding="utf-8")
    assert "RuntimeLightDurationTicks" in projectile_visuals
    assert "VfxParticleDurationTicks" in projectile_visuals
    assert "EmitAuthoredVisualField" in projectile_visuals
    for field in (
        "VfxParticleScale", "VfxMaterial", "VfxParticleDurationTicks",
        "VfxFieldLifetimeTicks", "VfxFieldRadiusTiles", "VfxFieldTickRate",
        "RuntimeLightDurationTicks",
    ):
        assert f"writer.Write(_spec.{field})" in net_sync or f"ShortNet(_spec.{field}" in net_sync
        assert f"_spec.{field} = reader." in net_sync
    assert "owner.whipRangeMultiplier" in projectile_runtime
    assert "AddGeneratedSummonTagDamage" in generated_item
    assert "ModifyHitByProjectile" in tag_runtime


def test_gameplay_authority_authorship_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            "_contract_check_llm_output_without_runtime_plan_never_falls_back_to_semantic_router",
            "_contract_check_structural_v3_proves_signature_against_final_wire",
            "_contract_check_planner_prompt_requires_structural_v3",
            "_contract_check_final_wire_gate_runs_before_images_and_after_final_clamps",
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
            "_contract_check_active_engine_cards_execute_authored_visual_and_summon_fields",
        ),
    )
