from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from infini_local.pipelines import (
    author_item_repair,
    author_item_repair_delta,
    author_item_repair_scope,
    combine_pipeline,
    llm_authoring_pipeline,
)
from infini_local.core.runtime_authoring import (
    compile_runtime_plan_to_genome_patch,
    runtime_plan_validation_report,
)
from infini_local.core.runtime_authoring.compiler import project_aoe_radius_tiles_to_damage_pixels
from infini_local.pipelines import combine_gameplay
from infini_local.pipelines.llm_transport import LLM_MODEL_OVERRIDE_KEY
from infini_local.pipelines.combine_gameplay import attach_gameplay_and_attack
from infini_local.pipelines.equipment_stats import armor_slot_from_authoring
from infini_local.pipelines.final_normalize import final_normalize
from infini_local.pipelines.item_power_knowledge import canonicalize
from infini_local.pipelines.combine_balance import stat_profile_for
from infini_local.pipelines.result_identity_policy import parent_primary_category
from infini_local.pipelines.llm_authoring_prompt import build_llm_author_payload, normalize_runtime_authoring_fields
from infini_local.pipelines.llm_authoring_pipeline import (
    final_runtime_promise_report,
    planner_runtime_promise_gate,
    validate_final_runtime_promise_boundary,
)
from infini_local.pipelines.combine_genome import genome_defects
from infini_local.pipelines.engine_pressure_metrics import estimate_engine_metrics

from infini_local.core.errors import PlannerUnavailable
from infini_local.core.boundary_models import runtime_plan_boundary_report
from infini_local.core.runtime_contracts import structural_final_wire_report
from infini_local.core.runtime_authoring.function_contract_registry import accepted_engine_param_names
from infini_local.core.runtime_authoring.reports import compiled_fields_for_authored_call
from infini_local.core.vfx_runtime_slots import _vfx_runtime_plan_direct_manifest
from infini_local.core.contract_versions import PLANNER_PROMPT_PROFILE_VERSION, RUNTIME_CONTRACT_SCHEMA_VERSION
from infini_local.storage import world_storage


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


def _contract_check_armor_slot_never_routes_from_name_or_tags() -> None:
    semantic_noise = {"name": "Nebula Helmet Boots", "armor": {}}
    assert armor_slot_from_authoring(semantic_noise, {}, default="") == ""
    assert armor_slot_from_authoring(semantic_noise, {}, default="body") == "body"
    assert armor_slot_from_authoring(
        semantic_noise,
        {"armorSlot": "head"},
        default="body",
    ) == "head"


def _contract_check_parent_role_and_power_ignore_fantasy_tokens() -> None:
    quiet = _parent("Plain Object", maxStack=1, rare=2, value=5000)
    loud = deepcopy(quiet)
    loud.update({
        "name": "Zenith Lunar Helmet Drill Potion",
        "tags": ["weapon", "armor", "tool", "potion", "material"],
        "nameTokens": ["zenith", "lunar", "helmet", "drill", "potion"],
    })
    assert parent_primary_category(quiet) == "generic"
    assert parent_primary_category(loud) == "generic"
    quiet_stage = stat_profile_for(quiet, quiet, set())
    loud_stage = stat_profile_for(loud, loud, set())
    assert loud_stage["derivedPower"] == quiet_stage["derivedPower"]
    assert loud_stage["powerBudget"] == quiet_stage["powerBudget"]


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


def _attach(
    plan: dict,
    a: dict | None = None,
    b: dict | None = None,
    *,
    name: str = "Authored Result",
    tooltip: str = "Exact runtime contract.",
) -> dict:
    a = a or _parent("Parent A")
    b = b or _parent("Parent B")
    data = {
        "name": name,
        "tooltip": tooltip,
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
            "acceptedAuthorItem": {"name": "Literal Workbench Blade"},
            "debug": {"planner": "stale_debug_must_not_route"},
            "gameplay": {"kind": "generic"},
        })


def _contract_check_compiler_provenance_proves_authored_values_against_final_wire() -> None:
    parent_a = _parent("Wooden Sword", damage=7, damage_class="melee")
    parent_b = _parent("Fallen Star")
    authored = {
        "name": "Star-Splinter Blade",
        "category": "weapon",
        "concept": {
            "fantasy": "A wooden blade that launches a compact star-splinter volley.",
            "mergeLogic": "The sword supplies the blade while the star supplies the projectile core.",
            "coreMechanic": "Fires three straight star splinters per swing.",
        },
        "runtimeContract": {
            "primaryVerb": "swing and fire",
            "controlStyle": "tap",
            "playerViewTimeline": [
                {"phase": "use", "description": "The blade releases three star splinters."},
                {"phase": "travel", "description": "The splinters travel in a narrow spread."},
            ],
        },
        "runtimePlan": {
            "resultKind": "weapon",
            "sourceRolePreservation": {"itemA": "wooden blade", "itemB": "star projectile core"},
            "engineCalls": [
                {
                    "callId": "stats",
                    "fn": "set_item_stats",
                    "params": {
                        "resultKind": "weapon", "damageClass": "melee", "damage": 21,
                        "useTimeTicks": 24, "useAnimationTicks": 24, "knockback": 4,
                    },
                },
                {
                    "callId": "shot",
                    "fn": "shoot_projectile",
                    "params": {
                        "runtimeFamily": "shoot", "delivery": "swing", "movement": "straight",
                        "speed": 9, "rangeTiles": 42, "lifetimeTicks": 90,
                        "shotCount": 3, "spreadRadians": 0.12, "pierce": 1,
                        "projectileShape": "small star splinter",
                    },
                },
            ],
            "runtimeStateIntent": "No persistent state.",
            "visualIntent": {
                "item": "Wooden sword with a compact fallen-star core at the guard.",
                "projectile": "Small sharp star splinter.",
                "impact": "Brief star fragments.",
                "vfxIntent": "Short gold star trail.",
                "vfxAvoid": "No beam or full-screen glow.",
                "topology": "connected",
                "parts": ["wooden sword", "fallen-star core"],
                "arrangement": "star core set into the sword guard",
            },
            "sourceReading": "Sword supplies melee form; star supplies the finite projectile.",
            "balanceIntent": "Three low-pierce splinters at a normal melee cadence.",
            "anomalyFlags": [],
        },
    }

    planner_gate = planner_runtime_promise_gate(authored)
    assert planner_gate["ok"] is True
    final_item = _attach(deepcopy(authored), parent_a, parent_b)
    report = validate_final_runtime_promise_boundary(final_item)

    assert report["ok"] is True
    assert final_item["gameplay"]["damage"] == 21
    assert final_item["attack"]["runtimeFamily"] == "shoot"
    assert final_item["attack"]["shotCount"] == 3
    receipts = report["finalWireReceipts"]
    assert any(
        row["callId"] == "stats" and row["authoredParam"] == "damage"
        and row["finalPath"] == "gameplay.damage" and row["compiledValue"] == 21
        for row in receipts
    )
    assert any(
        row["callId"] == "shot" and row["authoredParam"] == "shotCount"
        and row["finalPath"] == "attack.shotCount" and row["compiledValue"] == 3
        for row in receipts
    )

    corrupted = deepcopy(final_item)
    corrupted["attack"]["shotCount"] = 2
    corrupted_report = final_runtime_promise_report(corrupted)
    assert corrupted_report["ok"] is False
    assert any(
        row["kind"] == "compiler_provenance_mismatched"
        and row["authoredParam"] == "shotCount"
        for row in corrupted_report["blockingClaims"]
    )

    missing_receipts = deepcopy(final_item)
    missing_receipts["runtimeContract"]["finalWireReceipts"] = []
    missing_report = final_runtime_promise_report(missing_receipts)
    assert missing_report["ok"] is False
    assert any(
        row["kind"] == "compiler_provenance_receipt_missing"
        for row in missing_report["blockingClaims"]
    )

    consumable = deepcopy(authored)
    consumable["name"] = "Star-Bound Mirror"
    consumable["runtimePlan"]["resultKind"] = "consumable_weapon"
    consumable["runtimePlan"]["engineCalls"][0]["params"].update({
        "resultKind": "consumable_weapon",
        "damageClass": "magic",
        "damage": 50,
        "maxStack": 9999,
        "craftYield": 1,
        "consumable": True,
    })
    clamped_item = _attach(
        consumable,
        _parent("Magic Mirror"),
        _parent("Fallen Star"),
    )
    clamped_report = validate_final_runtime_promise_boundary(clamped_item)
    assert clamped_item["gameplay"]["damage"] == 50
    assert clamped_item["gameplay"]["maxStack"] == 999
    assert any(
        row["callId"] == "stats"
        and row["authoredParam"] == "damage"
        and row["compiledValue"] == 50
        and row["status"] == "active"
        for row in clamped_report["finalWireReceipts"]
    )
    assert any(
        row["callId"] == "stats"
        and row["authoredParam"] == "maxStack"
        and row["compiledValue"] == 999
        and row["status"] == "clamped"
        for row in clamped_report["finalWireReceipts"]
    )
    corrupted_clamp = deepcopy(clamped_item)
    corrupted_clamp["gameplay"]["maxStack"] = 998
    assert any(
        row["kind"] == "compiler_provenance_mismatched"
        and row["authoredParam"] == "maxStack"
        for row in final_runtime_promise_report(corrupted_clamp)["blockingClaims"]
    )

    family_owned_fields = compiled_fields_for_authored_call(
        "fire_ranged_weapon",
        {
            "family": "bow", "ammoFor": "arrow", "projectileFamily": "wooden_arrow",
            "movement": "straight", "speed": 10, "lifetimeTicks": 90,
        },
        "family",
    )
    assert family_owned_fields

    item_runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs").read_text(encoding="utf-8")
    dto_source = (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Model.cs").read_text(encoding="utf-8")
    assert "Data.Attack.ShotCount" in item_runtime
    assert "data.Attack.RuntimeFamily" in item_runtime
    assert "public int ShotCount" in dto_source
    assert "public string RuntimeFamily" in dto_source





def _contract_check_planner_prompt_uses_compact_author_item_contract() -> None:
    a = _parent("Prompt Parent A", damage=12, damage_class="melee")
    b = _parent("Prompt Parent B", tags=["material"])
    payload = build_llm_author_payload(a, b, canonicalize(a), canonicalize(b), "structural-v3-contract")
    required = payload["requiredJsonShape"]
    contract = required["runtimeContract"]
    assert set(contract) == {"primaryVerb", "controlStyle", "playerViewTimeline"}
    timeline_card = str(contract["playerViewTimeline"])
    assert "phase" in timeline_card and "description" in timeline_card
    assert "backingRefRules" not in payload
    assert "mechanicClaims" not in str(required)
    assert "signatureClaimId" not in str(required)
    assert "tooltipClaimIds" not in str(required)
    assert required["runtimePlan"]["engineCalls"] == (
        "array<{callId:[a-z][a-z0-9_]{0,63},fn,params}>"
    )
    assert "availableFunctions" in payload["engineRuntimeContract"]
    visual_intent_keys = set(required["runtimePlan"]["visualIntent"])
    assert {
        "item", "projectile", "impact", "vfxIntent", "vfxAvoid",
        "topology", "parts", "arrangement",
    } <= visual_intent_keys
    assert {
        "partCountMin", "partCountMax", "palette", "preferredCanvasSize",
        "projectileCanvasSize", "projectileVisualFamily", "projectileOrientation",
        "animeReference",
    } <= visual_intent_keys
    assert "visual" not in required
    assert RUNTIME_CONTRACT_SCHEMA_VERSION == "infini.runtime-contract.v3"
    assert "planner_prompt" in PLANNER_PROMPT_PROFILE_VERSION


def _contract_check_any_domain_rejection_gets_one_same_author_scoped_repair_before_images(monkeypatch) -> None:
    from contract_checks import (
        assert_pipeline_phase_order,
        assert_pipeline_terminal_phase,
        pipeline_phase_count,
    )

    stages: list[str] = []
    repairs: list[dict] = []

    def run_stage(label, fn, *args, **kwargs):
        stages.append(label)
        return fn(*args, **kwargs)

    def strict_validate(data, *_args):
        if data.get("variant") == "bad":
            raise PlannerUnavailable("runtimePlan engineCalls[1].params.runtimeFamily: field required")
        return data

    def validate(data, *_args):
        return data

    monkeypatch.setattr(combine_pipeline, "strict_validate_authored_item", strict_validate)
    monkeypatch.setattr(combine_pipeline, "validate_and_repair", validate)
    monkeypatch.setattr(combine_pipeline, "apply_item_knowledge", lambda data, *_args: data)
    monkeypatch.setattr(combine_pipeline, "attach_gameplay_and_attack", lambda data, *_args: {**data, "compiled": True})
    monkeypatch.setattr(combine_pipeline, "project_attack_presentation_fields", lambda data, **_kwargs: data)
    monkeypatch.setattr(combine_pipeline, "validate_executable_item_boundary", lambda data: data)
    monkeypatch.setattr(combine_pipeline, "validate_final_runtime_promise_boundary", lambda data: {"ok": True})

    def same_author_repair(data, *_args, failure_report=None, **_kwargs):
        repairs.append({"data": deepcopy(data), "report": deepcopy(failure_report)})
        return {"variant": "good", "debug": {"planner": "llm_author_first"}}

    monkeypatch.setattr(combine_pipeline, "repair_author_item_after_failure", same_author_repair)

    result = combine_pipeline.compile_and_validate_authored_runtime(
        {
            "variant": "bad",
            "debug": {
                "planner": "llm_author_first",
                "authorItemV3LocalStrictBoundary": json.dumps({"ok": False, "errors": [{"path": "$.runtimePlan"}]}),
            },
        },
        {}, {}, {}, {}, "recipe-key",
        run_stage=run_stage,
    )

    assert result["variant"] == "good"
    assert len(repairs) == 1
    assert repairs[0]["report"]["stage"] == "strict_author_validation"
    assert repairs[0]["report"]["errorType"] == "PlannerUnavailable"
    assert repairs[0]["report"]["authorItemV3LocalStrictBoundary"] == {
        "ok": False,
        "errors": [{"path": "$.runtimePlan"}],
    }
    assert "runtimeFamily" in repairs[0]["report"]["error"]
    assert pipeline_phase_count(stages, "runtime_compile") == 1
    assert_pipeline_phase_order(
        stages,
        "author_validation",
        "author_recovery",
        "recovered_final_wire",
    )
    assert_pipeline_terminal_phase(stages, "recovered_final_wire")


def _contract_check_targeted_repair_delta_is_leaf_typed_and_scope_bounded() -> None:
    from infini_local.pipelines.author_item_contract import (
        strict_author_item_targeted_repair_delta_report,
    )

    current = {
        "name": "Stable Yoyo",
        "category": "weapon",
        "concept": {"fantasy": "Keep me.", "mergeLogic": "Keep fusion.", "coreMechanic": "Keep mechanic."},
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {
                    "callId": "stats",
                    "fn": "set_item_stats",
                    "params": {"resultKind": "weapon", "damage": 22, "useTimeTicks": 25},
                },
                {
                    "callId": "primary",
                    "fn": "perform_melee_attack",
                    "params": {"family": "yoyo", "lifetimeTicks": 900, "useTimeTicks": 25, "speed": 16},
                },
                {
                    "callId": "on_hit",
                    "fn": "apply_on_hit_effect",
                    "params": {"onHit": "shadowflame", "debuffTime": 120},
                },
            ],
        },
    }
    delta = {
        "engineCallParamPatches": [
            {"callId": "stats", "fn": "set_item_stats", "params": {"useTimeTicks": 30}},
            {
                "callId": "primary",
                "fn": "perform_melee_attack",
                "params": {"lifetimeTicks": 600, "useTimeTicks": 30},
            },
        ],
    }
    assert strict_author_item_targeted_repair_delta_report(delta)["ok"] is True
    invalid_param = {
        "engineCallParamPatches": [{
            "callId": "primary",
            "fn": "perform_melee_attack",
            "params": {"inventedParam": 123},
        }],
    }
    assert strict_author_item_targeted_repair_delta_report(invalid_param)["ok"] is False

    exact_pressure_failure = {
        "authorRepairTargets": [
            {
                "path": "$.runtimePlan.engineCalls[0]",
                "callId": "stats",
                "fn": "set_item_stats",
                "repairParamNames": ["useTimeTicks"],
                "reason": "cross-call pressure",
            },
            {
                "path": "$.runtimePlan.engineCalls[1]",
                "callId": "primary",
                "fn": "perform_melee_attack",
                "repairParamNames": ["lifetimeTicks", "useTimeTicks"],
                "reason": "cross-call pressure",
            },
        ],
    }
    repaired = author_item_repair_delta._apply_targeted_repair_delta(
        current,
        delta,
        exact_pressure_failure,
    )
    assert repaired["runtimePlan"]["engineCalls"][0]["params"] == {
        "resultKind": "weapon", "damage": 22, "useTimeTicks": 30,
    }
    assert repaired["runtimePlan"]["engineCalls"][1]["params"] == {
        "family": "yoyo", "lifetimeTicks": 600, "useTimeTicks": 30, "speed": 16,
    }
    assert repaired["runtimePlan"]["engineCalls"][2] == current["runtimePlan"]["engineCalls"][2]
    assert repaired["concept"] == current["concept"]

    role_current = deepcopy(current)
    role_current["runtimePlan"]["sourceRolePreservation"] = {
        "itemA": "accepted blade",
        "itemB": "accepted crystal",
    }
    role_failure = {"authorRepairTargets": [{
        "path": "$.runtimePlan.sourceRolePreservation.itemA",
        "repairParamNames": ["sourceRolePreservation.itemA"],
        "reason": "itemA role is incomplete",
    }]}
    role_delta = {"authorFields": {
        "sourceRolePreservation": {"itemA": "repaired blade"},
    }}
    assert strict_author_item_targeted_repair_delta_report(role_delta)["ok"] is True
    role_repaired = author_item_repair_delta._apply_targeted_repair_delta(
        role_current, role_delta, role_failure,
    )
    assert role_repaired["runtimePlan"]["sourceRolePreservation"] == {
        "itemA": "repaired blade",
        "itemB": "accepted crystal",
    }
    with pytest.raises(PlannerUnavailable, match="out_of_scope_author_field_leaf"):
        author_item_repair_delta._apply_targeted_repair_delta(
            role_current,
            {"authorFields": {"sourceRolePreservation": {
                "itemA": "repaired blade",
                "itemB": "unauthorized crystal mutation",
            }}},
            role_failure,
        )

    targeted_stats_failure = {
        "errors": [{"callId": "stats", "path": "$.runtimePlan.engineCalls[0].params.damage", "kind": "range"}],
    }
    with pytest.raises(PlannerUnavailable, match="out_of_scope_runtime_metadata_leaf:balanceIntent"):
        author_item_repair_delta._apply_targeted_repair_delta(
            current,
            {"runtimeMetadata": {"balanceIntent": "unrelated rewrite"}},
            targeted_stats_failure,
        )

    metadata_current = deepcopy(current)
    metadata_current["runtimePlan"].update({
        "balanceIntent": "accepted balance",
        "sourceReading": "accepted source reading",
    })
    metadata_failure = {"authorRepairTargets": [{
        "path": "$.runtimePlan.balanceIntent",
        "repairParamNames": ["balanceIntent"],
        "reason": "bounded metadata leaf rejected",
    }]}
    metadata_repaired = author_item_repair_delta._apply_targeted_repair_delta(
        metadata_current,
        {"runtimeMetadata": {"balanceIntent": "repaired balance"}},
        metadata_failure,
    )
    assert metadata_repaired["runtimePlan"]["balanceIntent"] == "repaired balance"
    assert metadata_repaired["runtimePlan"]["sourceReading"] == "accepted source reading"
    with pytest.raises(PlannerUnavailable, match="out_of_scope_runtime_metadata_leaf:sourceReading"):
        author_item_repair_delta._apply_targeted_repair_delta(
            metadata_current,
            {"runtimeMetadata": {"sourceReading": "unauthorized rewrite"}},
            metadata_failure,
        )

    with pytest.raises(PlannerUnavailable, match="out_of_scope_engine_call_param_patch"):
        author_item_repair_delta._apply_targeted_repair_delta(
            current,
            {"engineCallParamPatches": [{
                "callId": "primary",
                "fn": "perform_melee_attack",
                "params": {"speed": 12},
            }]},
            targeted_stats_failure,
        )
    with pytest.raises(PlannerUnavailable, match="out_of_scope_engine_call_param"):
        author_item_repair_delta._apply_targeted_repair_delta(
            current,
            {"engineCallParamPatches": [{
                "callId": "stats",
                "fn": "set_item_stats",
                "params": {"damage": 24, "useTimeTicks": 12},
            }]},
            targeted_stats_failure,
        )
    with pytest.raises(PlannerUnavailable, match="out_of_scope_engine_call_replacement"):
        author_item_repair_delta._apply_targeted_repair_delta(
            current,
            {"engineCallReplacements": [{
                "callId": "stats", "fn": "set_item_stats",
                "params": {"resultKind": "weapon", "damage": 24, "useTimeTicks": 25},
            }]},
            targeted_stats_failure,
        )

    combat_current = deepcopy(current)
    combat_current["runtimePlan"]["resultKind"] = "consumable_weapon"
    combat_current["runtimePlan"]["engineCalls"][0]["params"].update({
        "resultKind": "consumable_weapon",
        "damage": 0,
        "maxStack": 25,
        "craftYield": 1,
        "consumable": True,
    })
    combat_delta = {
        "engineCallParamPatches": [{
            "callId": "stats",
            "fn": "set_item_stats",
            "params": {"damage": 12},
        }],
    }
    combat_failure = {
        "errors": [{
            "callId": "stats",
            "path": "$.runtimePlan.engineCalls[0].params.damage",
            "reason": "combat set_item_stats requires positive damage; use a non-combat resultKind",
            "repairParamNames": ["damage"],
        }],
    }
    repaired_combat = author_item_repair_delta._apply_targeted_repair_delta(
        combat_current,
        combat_delta,
        combat_failure,
    )
    assert repaired_combat["category"] == "weapon"
    assert repaired_combat["runtimePlan"]["resultKind"] == "consumable_weapon"
    assert repaired_combat["runtimePlan"]["engineCalls"][0]["params"]["resultKind"] == "consumable_weapon"
    assert repaired_combat["runtimePlan"]["engineCalls"][0]["params"]["damage"] == 12

    nested_current = deepcopy(current)
    nested_current["runtimePlan"]["engineCalls"].append({
        "callId": "accessory",
        "fn": "accessory_effect",
        "params": {"stats": {
            "movementSpeed": 0.1,
            "lightStrength": 1.2,
        }},
    })
    nested_failure = {"authorRepairTargets": [{
        "path": "$.runtimePlan.engineCalls[3].params.stats.lightColorName",
        "callId": "accessory",
        "fn": "accessory_effect",
        "repairParamNames": ["stats.lightColorName"],
        "reason": "lightStrength requires lightColorName",
    }]}
    nested_delta = {"engineCallParamPatches": [{
        "callId": "accessory",
        "fn": "accessory_effect",
        "params": {"stats": {"lightColorName": "blue"}},
    }]}
    assert strict_author_item_targeted_repair_delta_report(nested_delta)["ok"] is True
    nested = author_item_repair_delta._apply_targeted_repair_delta(
        nested_current,
        nested_delta,
        nested_failure,
    )
    assert nested["runtimePlan"]["engineCalls"][3]["params"]["stats"] == {
        "movementSpeed": 0.1,
        "lightStrength": 1.2,
        "lightColorName": "blue",
    }

    mixed_sources = author_item_repair_scope._failure_rejection_sources({
        "error": "actual stage failure",
        "compilerFinalWirePreview": {"errors": ["preview failure"]},
    })
    assert "actual stage failure" in mixed_sources
    assert ["preview failure"] in mixed_sources

    assert author_item_repair_scope._targeted_repair_function_cards(
        current["runtimePlan"],
        [{"path": "$.runtimePlan.engineCalls", "reason": "ownerless"}],
        {
            "set_item_stats": {"params": {"damage": "number"}},
            "perform_melee_attack": {"params": {"speed": "number"}},
        },
    ) == {}
    _, fallback_user, _, fallback_targeted, _ = (
        author_item_repair.build_same_author_repair_request(
            current,
            {},
            {},
            {"errors": [{
                "path": "$.runtimePlan.engineCalls",
                "reason": "ownerless",
            }]},
        )
    )
    assert fallback_targeted is False
    assert json.loads(fallback_user)["repairMode"] == "full_redesign"

    overhead_item = {
        "category": "weapon",
        "runtimePlan": {
        "resultKind": "consumable_weapon",
        "engineCalls": [{
            "callId": "stats",
            "fn": "set_item_stats",
            "params": {
                "resultKind": "consumable_weapon",
                "damageClass": "magic",
                "damage": 45,
                "useTimeTicks": 90,
                "maxStack": 99,
                "craftYield": 1,
                "consumable": True,
            },
        }, {
            "callId": "stars",
            "fn": "shoot_projectile",
            "params": {
                "delivery": "cast",
                "movement": "gravity_arc",
                "speed": 8,
                "rangeTiles": 20,
                "lifetimeTicks": 60,
                "shotCount": 5,
                "spreadRadians": 0.5,
                "pierce": 2,
                "runtimeFamily": "overhead_barrage",
            },
        }, {
            "callId": "starburst",
            "fn": "apply_on_hit_effect",
            "params": {
                "onHit": "starburst",
                "count": 3,
                "secondaryDamageMultiplier": 0.5,
                "secondaryLifetimeTicks": 30,
            },
        }],
    }}
    overhead_report = runtime_plan_validation_report(overhead_item)
    delay_detail = next(
        row for row in overhead_report["errorDetails"]
        if row.get("reason") == (
            "combat runtimeFamily=overhead_barrage requires explicit delayTicks"
        )
    )
    assert delay_detail["path"] == "$.runtimePlan.engineCalls[1].params.delayTicks"
    assert delay_detail["callId"] == "stars"
    assert delay_detail["fn"] == "shoot_projectile"

    armor_combat_item = deepcopy(overhead_item)
    armor_combat_item["category"] = "armor"
    armor_combat_item["runtimePlan"]["resultKind"] = "armor"
    armor_stats = armor_combat_item["runtimePlan"]["engineCalls"][0]["params"]
    armor_stats.update({"resultKind": "armor", "armorSlot": "head", "defense": 3})
    armor_combat_report = runtime_plan_validation_report(armor_combat_item)
    assert any(
        error.startswith(
            "executor_not_representable: resultKind=armor cannot execute combat engine calls"
        )
        for error in armor_combat_report["errors"]
    )

    indexed_targets = author_item_repair_scope._resolve_indexed_target_call_owners(
        [{
            "path": "$.runtimePlan.engineCalls[1].params.speed",
            "kind": "type",
            "reason": "expected number",
        }],
        current["runtimePlan"],
    )
    assert indexed_targets == [{
        "path": "$.runtimePlan.engineCalls[1].params.speed",
        "kind": "type",
        "reason": "expected number",
        "callId": "primary",
        "fn": "perform_melee_attack",
    }]
    with pytest.raises(PlannerUnavailable, match="indexed_target_owner_mismatch"):
        author_item_repair_scope._resolve_indexed_target_call_owners(
            [{
                "path": "$.runtimePlan.engineCalls[0].params.damage",
                "callId": "primary",
                "fn": "perform_melee_attack",
            }],
            current["runtimePlan"],
        )

    from infini_local.pipelines.llm_authoring_prompt import (
        engine_runtime_capability_contract_for_llm,
    )
    capability = engine_runtime_capability_contract_for_llm({}, {})["availableFunctions"]
    nested_cards = author_item_repair_scope._targeted_repair_function_cards(
        nested_current["runtimePlan"],
        nested_failure["authorRepairTargets"],
        capability,
    )
    nested_stats_schema = nested_cards["accessory"]["params"]["stats"]
    assert set(nested_stats_schema["properties"]) == {"lightColorName"}
    assert "lightStrength" not in json.dumps(nested_stats_schema)
    assert "movementSpeed" not in json.dumps(nested_stats_schema)

    visual_current = deepcopy(current)
    visual_current["runtimePlan"]["visualIntent"] = {
        "topology": "connected",
        "partCountMin": 1,
        "partCountMax": 1,
        "parts": ["one continuous body"],
        "palette": ["violet", "black"],
        "preferredCanvasSize": 32,
    }
    visual_failure = {"authorRepairTargets": [{
        "path": "$.runtimePlan.visualIntent.preferredCanvasSize",
        "kind": "maximum",
        "reason": "must be <= 64",
    }]}
    visual_delta = {"authorFields": {"visualIntent": {"preferredCanvasSize": 64}}}
    assert strict_author_item_targeted_repair_delta_report(visual_delta)["ok"] is True
    visual_repaired = author_item_repair_delta._apply_targeted_repair_delta(
        visual_current,
        visual_delta,
        visual_failure,
    )
    assert visual_repaired["runtimePlan"]["visualIntent"] == {
        **visual_current["runtimePlan"]["visualIntent"],
        "preferredCanvasSize": 64,
    }
    with pytest.raises(PlannerUnavailable, match="out_of_scope_visual_intent_leaf:topology"):
        author_item_repair_delta._apply_targeted_repair_delta(
            visual_current,
            {"authorFields": {"visualIntent": {
                "preferredCanvasSize": 64,
                "topology": "multipart_separated",
            }}},
            visual_failure,
        )


def test_required_targeted_visual_leaves_are_non_nullable_in_provider_schema() -> None:
    from infini_local.pipelines.author_item_contract import (
        author_item_provider_targeted_repair_delta_schema,
    )

    current = {
        "runtimePlan": {
            "visualIntent": {
                "item": "winged boots",
                "vfxIntent": "speed dust",
            },
        },
    }
    invalid_targets = [
        {
            "path": "$.runtimePlan.visualIntent.projectile",
            "kind": "required",
            "reason": "required",
        },
        {
            "path": "$.runtimePlan.visualIntent.impact",
            "kind": "required",
            "reason": "required",
        },
    ]
    author_schemas, metadata_fields, identity_schemas = (
        author_item_repair_scope._targeted_provider_delta_scope(
            current,
            invalid_targets,
            ["visualIntent"],
        )
    )
    provider = author_item_provider_targeted_repair_delta_schema(
        allowed_author_field_schemas=author_schemas,
        allowed_runtime_metadata_fields=metadata_fields,
        identity_field_schemas=identity_schemas,
    )
    author_fields_schema = author_item_repair_scope._resolve_local_schema_ref(
        provider["properties"]["authorFields"],
        provider,
    )
    visual_schema = author_item_repair_scope._resolve_local_schema_ref(
        author_fields_schema["properties"]["visualIntent"],
        provider,
    )
    assert set(visual_schema["properties"]) == {"projectile", "impact"}
    assert set(visual_schema["required"]) == {"projectile", "impact"}
    for field in ("projectile", "impact"):
        assert '"null"' not in json.dumps(visual_schema["properties"][field])


def _contract_check_same_author_repair_uses_source_validated_snapshot_not_lowered_dto(monkeypatch) -> None:
    repair_inputs: list[dict] = []
    repair_reports: list[dict] = []

    def strict_validate(data, *_args):
        return deepcopy(data)

    def lower_for_runtime(data, *_args):
        call = data["runtimePlan"]["engineCalls"][1]
        call["fn"] = "shoot_projectile"
        call["_rawFn"] = "fire_ranged_weapon"
        call["_index"] = 1
        return data

    def final_wire(data):
        if not data.get("repaired"):
            error = PlannerUnavailable(
                "compiler provenance mismatch after lowering",
                author_repair_rejected_domains=[{
                    "path": "$.runtimePlan.engineCalls",
                    "kind": "genome_non_executable",
                }],
            )
            raise error
        return data

    def same_author_repair(data, *_args, failure_report=None, **_kwargs):
        repair_inputs.append(deepcopy(data))
        assert isinstance(failure_report, dict)
        repair_reports.append(deepcopy(failure_report))
        repaired = deepcopy(data)
        repaired["repaired"] = True
        return repaired

    monkeypatch.setattr(combine_pipeline, "strict_validate_authored_item", strict_validate)
    monkeypatch.setattr(combine_pipeline, "validate_and_repair", lower_for_runtime)
    monkeypatch.setattr(combine_pipeline, "apply_item_knowledge", lambda data, *_args: data)
    monkeypatch.setattr(combine_pipeline, "attach_gameplay_and_attack", lambda data, *_args: data)
    monkeypatch.setattr(combine_pipeline, "project_attack_presentation_fields", lambda data, **_kwargs: data)
    monkeypatch.setattr(combine_pipeline, "validate_executable_item_boundary", lambda data: data)
    monkeypatch.setattr(combine_pipeline, "validate_final_runtime_promise_boundary", final_wire)
    monkeypatch.setattr(combine_pipeline, "repair_author_item_after_failure", same_author_repair)

    result = combine_pipeline.compile_and_validate_authored_runtime(
        {
            "runtimePlan": {
                "engineCalls": [
                    {"callId": "stats", "fn": "set_item_stats", "params": {"resultKind": "weapon"}},
                    {
                        "callId": "primary",
                        "fn": "fire_ranged_weapon",
                        "params": {"family": "gun", "ammoFor": "bullet"},
                    },
                ],
            },
        },
        {}, {}, {}, {}, "recipe-key",
        run_stage=lambda _label, fn, *args, **kwargs: fn(*args, **kwargs),
    )

    assert result["repaired"] is True
    assert len(repair_inputs) == 1
    assert repair_reports[0]["authorRepairRejectedDomains"] == [{
        "path": "$.runtimePlan.engineCalls",
        "kind": "genome_non_executable",
    }]
    repaired_call = repair_inputs[0]["runtimePlan"]["engineCalls"][1]
    assert repaired_call == {
        "callId": "primary",
        "fn": "fire_ranged_weapon",
        "params": {"family": "gun", "ammoFor": "bullet"},
    }


def _contract_check_internal_pipeline_exceptions_never_invoke_author_repair(monkeypatch) -> None:
    repair_calls: list[type[Exception]] = []

    def fake_repair(data, *_args, **_kwargs):
        repair_calls.append(type(data.get("internalError")))
        return data

    monkeypatch.setattr(combine_pipeline, "repair_author_item_after_failure", fake_repair)
    for error_type in (TypeError, ValueError):
        error = error_type("deterministic compiler regression")

        def fail_internal(_data, *_args, _error=error):
            raise _error

        monkeypatch.setattr(combine_pipeline, "strict_validate_authored_item", fail_internal)
        with pytest.raises(error_type, match="deterministic compiler regression"):
            combine_pipeline.compile_and_validate_authored_runtime(
                {"internalError": error}, {}, {}, {}, {}, "recipe-key",
                run_stage=lambda _label, fn, *args, **kwargs: fn(*args, **kwargs),
            )
        assert repair_calls == []


def _contract_check_final_normalize_cannot_mutate_executable_dto() -> None:
    item = {
        "name": "Immutable Executable",
        "category": "weapon",
        "gameplay": {"kind": "weapon", "damage": 17, "autoReuse": False},
        "attack": {"enabled": True, "runtimeFamily": "shoot", "damage": 17},
        "_llmHistory": {"kind": "internal"},
    }
    before = {field: deepcopy(item[field]) for field in ("category", "gameplay", "attack")}
    normalized = final_normalize(item)
    assert {field: normalized[field] for field in before} == before



def _contract_check_post_author_visual_stages_cannot_mutate_executable_dto() -> None:
    item = {
        "category": "weapon",
        "gameplay": {"kind": "weapon", "damage": 17, "categoryIntent": "weapon"},
        "accessory": {"enabled": False},
        "armor": {"enabled": False},
        "attack": {
            "enabled": True,
            "runtimeFamily": "shoot",
            "speed": 9.0,
            "runtimeAuthoringProvenance": {"source": "compiler"},
        },
    }
    frozen = combine_pipeline._post_author_executable_projection(item)

    presentation_only = deepcopy(item)
    presentation_only["attack"].update({
        "projectileSpritePath": "/generated/projectile.png",
        "projectileSpriteScore": 0.9,
        "vfxManifestJson": "{}",
    })
    assert combine_pipeline._assert_post_author_executable_unchanged(frozen, presentation_only) is presentation_only

    changed_gameplay = deepcopy(presentation_only)
    changed_gameplay["gameplay"]["damage"] = 99
    with pytest.raises(PlannerUnavailable, match="gameplay"):
        combine_pipeline._assert_post_author_executable_unchanged(frozen, changed_gameplay)

    changed_executor = deepcopy(presentation_only)
    changed_executor["attack"]["runtimeFamily"] = "beam"
    with pytest.raises(PlannerUnavailable, match="attack"):
        combine_pipeline._assert_post_author_executable_unchanged(frozen, changed_executor)


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
    assert project_aoe_radius_tiles_to_damage_pixels(4) == 64
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
    assert "writer.Write((byte)3); // state version" in multiplayer
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

    ambiguous_custom_ammo = {"runtimePlan": {"resultKind": "ammo", "engineCalls": [
        {"fn": "set_item_stats", "params": {
            "resultKind": "ammo", "damageClass": "ranged", "damage": 7,
            "maxStack": 99, "craftYield": 25, "ammoFor": "",
        }},
        _primary("throw", "throw", "gravity_arc", 60),
    ]}}
    ambiguous_report = runtime_plan_validation_report(ambiguous_custom_ammo)
    assert ambiguous_report["ok"] is False
    assert any("ammo result requires vanilla arrow or bullet identity" in error for error in ambiguous_report["errors"])
    assert any("actual ammo cannot author a generated root executor" in error for error in ambiguous_report["errors"])

    plural_alias = deepcopy(ambiguous_custom_ammo)
    plural_alias["runtimePlan"]["engineCalls"] = [deepcopy(ambiguous_custom_ammo["runtimePlan"]["engineCalls"][0])]
    plural_alias["runtimePlan"]["engineCalls"][0]["params"]["ammoFor"] = "arrows"
    plural_report = runtime_plan_validation_report(plural_alias)
    assert plural_report["ok"] is False
    assert any("ammo result requires vanilla arrow or bullet identity" in error for error in plural_report["errors"])

    stack_consumed_weapon = {"category": "weapon", "runtimePlan": {"resultKind": "weapon", "engineCalls": [
        {"callId": "stats", "fn": "set_item_stats", "params": {
            "resultKind": "weapon", "damageClass": "melee", "damage": 12,
            "useTimeTicks": 25, "useAnimationTicks": 25,
            "maxStack": 99, "craftYield": 25, "consumable": True,
        }},
        _primary("swing", "swing", "straight", 15),
        {"callId": "consume", "fn": "consumption_behavior", "params": {"consumeChancePercent": 100}},
    ]}}
    stack_report = runtime_plan_validation_report(stack_consumed_weapon)
    assert stack_report["ok"] is False
    assert any("invalid_result_kind" in error for error in stack_report["errors"])
    stats_repair_paths = {
        detail.get("path")
        for detail in stack_report["errorDetails"]
        if detail.get("callId") == "stats"
    }
    assert stats_repair_paths == {
        "$.runtimePlan.engineCalls[0].params.consumable",
        "$.runtimePlan.engineCalls[0].params.maxStack",
        "$.runtimePlan.engineCalls[0].params.craftYield",
    }, stack_report["errorDetails"]
    assert any(
        detail.get("callId") == "consume"
        and detail.get("path") == "$.runtimePlan.engineCalls[2].params.consumeChancePercent"
        for detail in stack_report["errorDetails"]
    ), stack_report["errorDetails"]

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
    child_policy = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedChildSpecPolicy.cs").read_text(encoding="utf-8")
    projectile_runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    charge_runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.ChargeRelease.cs").read_text(encoding="utf-8")
    sentry_runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Sentry.cs").read_text(encoding="utf-8")
    assert "parent.Speed > 0f ? parent.Speed : 11f" not in overhead_policy
    assert "authoredSpreadRadians <= 0f ? 0.44f" not in overhead_policy
    assert "SecondaryDamageMultiplier <= 0f ? 0.55f" not in overhead_runtime
    assert "Math.Max(0.12f, attack.SecondaryDamageMultiplier)" not in item_runtime
    assert "GeneratedChildSpecPolicy.CreateSwingSecondary(parent)" in item_runtime
    swing_policy = child_policy.split("public static AttackSpec CreateSwingSecondary", 1)[1].split("private static bool HasExplicitSecondaryBody", 1)[0]
    assert "Lifetime = Math.Clamp(parent.SecondaryLifetimeTicks, 5, 180)" in swing_policy
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


def _contract_check_runtime_validation_errors_always_publish_structured_targets() -> None:
    report = runtime_plan_validation_report({
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "consumable_weapon",
            "engineCalls": [
                {"callId": "stats", "fn": "set_item_stats", "params": {
                    "resultKind": "consumable_weapon", "damageClass": "ranged",
                    "damage": 12, "useTimeTicks": 15, "useAnimationTicks": 15,
                    "consumable": True, "maxStack": 9999, "craftYield": 0,
                }},
                {"callId": "primary", "fn": "shoot_projectile", "params": {
                    "runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight",
                    "speed": 10, "rangeTiles": 40, "lifetimeTicks": 60,
                    "shotCount": 1, "spreadRadians": 0, "pierce": 1,
                }},
            ],
        },
    })
    assert report["ok"] is False
    details = report["errorDetails"]
    assert set(report["errors"]) <= {str(row.get("reason") or "") for row in details}
    craft_targets = [row for row in details if str(row.get("path") or "").endswith(".params.craftYield")]
    assert craft_targets == [{
        "kind": "runtime_validation",
        "path": "$.runtimePlan.engineCalls[0].params.craftYield",
        "callId": "stats",
        "fn": "set_item_stats",
        "reason": "consumable_weapon result requires explicit positive maxStack and craftYield",
        "repairParamNames": ["craftYield"],
    }]

    armor_report = runtime_plan_validation_report({
        "category": "armor",
        "runtimePlan": {
            "resultKind": "armor",
            "engineCalls": [
                {"callId": "stats", "fn": "set_item_stats", "params": {
                    "resultKind": "armor", "armorSlot": "head", "defense": 4,
                }},
                {"callId": "armor", "fn": "armor_effect", "params": {
                    "armorSlot": "head", "defense": 4,
                    "stats": {"movementSpeed": 0.05, "lightStrength": 1.2},
                }},
            ],
        },
    })
    light_targets = [
        row
        for row in armor_report["errorDetails"]
        if str(row.get("path") or "").endswith(".params.stats.lightColorName")
    ]
    assert light_targets == [{
        "kind": "runtime_validation",
        "path": "$.runtimePlan.engineCalls[1].params.stats.lightColorName",
        "callId": "armor",
        "fn": "armor_effect",
        "reason": "armor_effect stats.lightStrength requires explicit lightColorName",
        "repairParamNames": ["stats.lightColorName"],
    }]
    cards = author_item_repair_scope._targeted_repair_function_cards(
        armor_report.get("runtimePlan") or {
            "engineCalls": [
                {"callId": "stats", "fn": "set_item_stats", "params": {}},
                {"callId": "armor", "fn": "armor_effect", "params": {
                    "stats": {"movementSpeed": 0.05, "lightStrength": 1.2},
                }},
            ],
        },
        light_targets,
        {"armor_effect": {"params": {"stats": {"type": "object"}, "defense": "number"}}},
    )
    assert set(cards) == {"armor"}
    assert cards["armor"]["fn"] == "armor_effect"
    assert set(cards["armor"]["params"]) == {"stats"}


def _contract_check_global_genome_defect_routes_back_to_the_same_author_domain() -> None:
    from infini_local.pipelines import combine_genome

    current_plan = {
        "engineCalls": [
            {"callId": "stats", "fn": "set_item_stats", "params": {"useTimeTicks": 10}},
            {"callId": "primary", "fn": "shoot_projectile", "params": {"lifetimeTicks": 900}},
        ],
    }
    data = {"runtimePlan": deepcopy(current_plan)}
    targets = combine_genome._genome_author_repair_targets(
        data,
        [{
            "kind": "genome_non_executable",
            "reason": "composite projectile pressure exceeds runtime safety envelope",
            "compiledFields": ["aggregateProjectilePressure"],
        }],
    )
    assert targets == [{
        "kind": "genome_non_executable",
        "path": "$.runtimePlan.engineCalls",
        "reason": "composite projectile pressure exceeds runtime safety envelope",
        "compiledFields": ["aggregateProjectilePressure"],
    }]

    failure_report = {"authorRepairTargets": targets}
    rejected = author_item_repair_scope._rejected_call_ids(failure_report, current_plan)
    assert rejected == {"stats", "primary"}

    replacement = {
        "engineCalls": [
            {"callId": "stats", "fn": "set_item_stats", "params": {"useTimeTicks": 30}},
            {"callId": "primary", "fn": "shoot_projectile", "params": {"lifetimeTicks": 120}},
        ],
    }
    author_item_repair_delta._preserve_accepted_engine_calls(
        replacement,
        current_plan,
        rejected,
    )
    assert replacement["engineCalls"][0]["params"]["useTimeTicks"] == 30
    assert replacement["engineCalls"][1]["params"]["lifetimeTicks"] == 120

    # Keep one production-path integration assertion: the compiled-genome boundary
    # must publish the same structured targets consumed by the single Author repair.
    pressure_data = {
        "gameplay": {"powerBudget": 1.0},
        "runtimePlan": {"engineCalls": [
            {"callId": "stats", "fn": "set_item_stats", "params": {
                "resultKind": "weapon", "damageClass": "ranged", "damage": 20,
                "useTimeTicks": 10, "useAnimationTicks": 10,
            }},
            {"callId": "primary", "fn": "shoot_projectile", "params": {
                "delivery": "shoot", "runtimeFamily": "shoot", "movement": "straight",
                "useTimeTicks": 10, "shotCount": 8, "pierce": 1,
                "rangeTiles": 60, "lifetimeTicks": 900, "speed": 12,
                "spreadRadians": 0, "extraUpdates": 3,
            }},
            {"callId": "onhit", "fn": "apply_on_hit_effect", "params": {
                "onHit": "none",
            }},
        ]},
        "attack": {"genome": {
            "delivery": "shoot", "runtimeFamily": "shoot", "movement": "straight",
            "effect": "dust", "onHit": "none", "pullMode": "none", "pullStrength": 0,
            "useTimeTicks": 10, "shotCount": 8, "pierce": 1, "aoeRadiusTiles": 0,
            "rangeTiles": 60, "lifetimeTicks": 900, "speed": 12, "spreadRadians": 0,
            "extraUpdates": 3, "reliability": 1.0, "selfLockTicks": 0, "missPunish": 0,
        }},
    }
    with pytest.raises(PlannerUnavailable) as raised:
        combine_genome.llm_authored_weapon_genome(pressure_data, {}, {}, {})
    published_targets = raised.value.author_repair_targets
    assert {str(target.get("callId") or "") for target in published_targets} == {
        "stats", "primary",
    }
    assert all(
        "composite projectile pressure" in str(target.get("reason") or "")
        for target in published_targets
    )
    compiled_by_call = {
        str(target.get("callId") or ""): set(target.get("compiledFields") or [])
        for target in published_targets
    }
    assert compiled_by_call["stats"] == {"useTimeTicks"}
    assert compiled_by_call["primary"] == {
        "extraUpdates", "lifetimeTicks", "shotCount", "useTimeTicks",
    }


def _contract_check_compiled_genome_surface_has_one_executable_owner() -> None:
    from infini_local.core.runtime_authoring.compiler import (
        COMPILED_COMBAT_GENOME_OPTIONAL_DEFAULTS,
        COMPILED_COMBAT_GENOME_REQUIRED_FIELDS,
    )
    from infini_local.core.runtime_authoring.function_contract_registry import (
        NORMALIZED_ROOT_REQUIRED_PARAM_NAMES,
    )
    from infini_local.core.runtime_authoring.schema import NUMERIC_LIMITS
    from infini_local.pipelines import pipeline_runtime_constants

    root_count = len(NORMALIZED_ROOT_REQUIRED_PARAM_NAMES)
    assert tuple(COMPILED_COMBAT_GENOME_REQUIRED_FIELDS[:root_count]) == tuple(
        NORMALIZED_ROOT_REQUIRED_PARAM_NAMES
    )
    assert {"useTimeTicks", "aoeRadiusTiles"} <= set(
        COMPILED_COMBAT_GENOME_REQUIRED_FIELDS
    )
    assert set(COMPILED_COMBAT_GENOME_OPTIONAL_DEFAULTS) <= set(NUMERIC_LIMITS)
    assert not hasattr(pipeline_runtime_constants, "LLM_REQUIRED_GENOME_FIELDS")
    assert not hasattr(pipeline_runtime_constants, "LLM_OPTIONAL_GENOME_DEFAULTS")
    assert not hasattr(pipeline_runtime_constants, "LLM_NUMERIC_GENOME_LIMITS")


def _contract_check_active_engine_cards_execute_authored_visual_and_summon_fields() -> None:
    assert "durationTicks" in accepted_engine_param_names("emit_light")
    assert "durationTicks" in accepted_engine_param_names("spawn_contact_particles")
    assert {"fieldLifetimeTicks", "fieldRadiusTiles", "tickRate"} <= accepted_engine_param_names("leave_trail_or_field")
    from infini_local.core.runtime_authoring.engine_call_contracts import validate_engine_call_params

    for fn in ("accessory_effect", "armor_effect"):
        parsed, errors = validate_engine_call_params(fn, {"stats": {"whipRange": 0.2, "summonTagDamage": 0.15}})
        assert not errors
        assert parsed and parsed["stats"] == {"whipRange": 0.2, "summonTagDamage": 0.15}

    visual_plan = {
        "concept": {"coreMechanic": "One finite authored projectile with bounded visual cues."},
        "runtimeContract": {"primaryVerb": "shoot once", "controlStyle": "tap"},
        "runtimePlan": {"resultKind": "weapon", "engineCalls": [
            {"callId": "stats", "fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 12, "useTimeTicks": 20, "useAnimationTicks": 20}},
            {"callId": "shot", "fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "speed": 8, "rangeTiles": 30, "lifetimeTicks": 90, "shotCount": 1, "spreadRadians": 0, "pierce": 1}},
            {"callId": "light", "fn": "emit_light", "params": {"strength": 0.7, "color": "blue", "durationTicks": 41}},
            {"callId": "particles", "fn": "spawn_contact_particles", "params": {"effect": "electric", "amount": 8, "scale": 1.2, "durationTicks": 23}},
            {"callId": "trail", "fn": "leave_trail_or_field", "params": {"trailLength": 6, "fieldLifetimeTicks": 80, "fieldRadiusTiles": 3.5, "tickRate": 9, "visualOnly": True}},
        ]},
    }
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
    final_wire = structural_final_wire_report(item)
    assert final_wire["ok"] is True, final_wire["blockingClaims"]
    assert any(
        row["callId"] == "trail"
        and row["authoredParam"] == "fieldLifetimeTicks"
        and row["finalPath"] == "attack.vfxFieldLifetimeTicks"
        for row in final_wire["finalWireReceipts"]
    )

    from infini_local.core.runtime_authoring.function_contract_registry import ENGINE_FUNCTION_CATALOG
    assert ENGINE_FUNCTION_CATALOG["leave_trail_or_field"]["requiresRootExecutor"] is True
    assert ENGINE_FUNCTION_CATALOG["spawn_contact_particles"]["requiresRootExecutor"] is True
    for fn in ("set_item_stats", "apply_player_effect_on_use"):
        buff_type_card = str(ENGINE_FUNCTION_CATALOG[fn]["params"]["buffType"]).casefold()
        assert "integer" in buff_type_card and "id" in buff_type_card
    trail_card = str(ENGINE_FUNCTION_CATALOG["leave_trail_or_field"]["meaning"]).casefold()
    assert "requires" in trail_card and "root" in trail_card
    non_projectile_field = {
        "category": "potion",
        "runtimePlan": {
            "resultKind": "potion",
            "engineCalls": [
                {
                    "callId": "stats",
                    "fn": "set_item_stats",
                    "params": {
                        "resultKind": "potion", "damage": 0, "healLife": 50,
                        "useTimeTicks": 20, "useAnimationTicks": 20,
                        "consumable": True, "maxStack": 30, "craftYield": 1,
                    },
                },
                {
                    "callId": "trail",
                    "fn": "leave_trail_or_field",
                    "params": {
                        "fieldLifetimeTicks": 80, "fieldRadiusTiles": 3,
                        "tickRate": 10, "visualOnly": True,
                    },
                },
            ],
        },
    }
    non_projectile_report = runtime_plan_validation_report(non_projectile_field)
    assert non_projectile_report["ok"] is False
    assert any(
        row.get("kind") == "structural_call_rejected"
        and row.get("callId") == "trail"
        and "root executor" in str(row.get("reason") or "")
        for row in non_projectile_report["errorDetails"]
    )

    projectile_visuals = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Visuals.cs").read_text(encoding="utf-8")
    projectile_runtime = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Runtime.cs").read_text(encoding="utf-8")
    generated_item = (ROOT / "ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs").read_text(encoding="utf-8")
    net_sync = (ROOT / "ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.NetSync.cs").read_text(encoding="utf-8")
    tag_runtime = (ROOT / "ModSources/InfiniCrafterLocal/Common/Players/GeneratedWhipTagGlobalNPC.cs").read_text(encoding="utf-8")
    assert "RuntimeLightDurationTicks" in projectile_visuals
    assert "VfxParticleDurationTicks" in projectile_visuals
    assert "EmitAuthoredVisualField" in projectile_visuals
    send_extra_ai = net_sync.split("public override void SendExtraAI", 1)[1].split("public override void ReceiveExtraAI", 1)[0]
    assert "_spec." not in send_extra_ai
    assert "TryGetAttack(_generatedItemId)" in net_sync
    assert "GeneratedChildSpecPolicy.TryCreateRuntimeVariant" in net_sync
    for field in (
        "VfxParticleScale", "VfxMaterial", "VfxParticleDurationTicks",
        "VfxFieldLifetimeTicks", "VfxFieldRadiusTiles", "VfxFieldTickRate",
        "RuntimeLightDurationTicks",
    ):
        assert f"_spec.{field}" in projectile_visuals
    assert "owner.whipRangeMultiplier" in projectile_runtime
    assert "AddGeneratedSummonTagDamage" in generated_item
    assert "ModifyHitByProjectile" in tag_runtime


def _contract_check_compiler_provenance_covers_active_noncombat_and_downstream_vfx_cards() -> None:
    common = {
        "concept": {"coreMechanic": "Every authored executable scalar reaches its compiler-owned destination."},
        "runtimeContract": {"primaryVerb": "use the authored finite effect", "controlStyle": "tap"},
    }
    cases = {
        "potion": {
            "category": "potion",
            **common,
            "runtimePlan": {"resultKind": "potion", "engineCalls": [
                {"callId": "stats", "fn": "set_item_stats", "params": {"resultKind": "potion", "maxStack": 30, "consumable": True, "healLife": 50, "buffType": 5, "buffTime": 600}},
                {"callId": "use", "fn": "apply_player_effect_on_use", "params": {"healLife": 50, "buffType": 5, "buffTime": 600, "generatedBuff": {"durationTicks": 600, "movementSpeed": 0.1}}},
            ]},
        },
        "tool": {
            "category": "tool",
            **common,
            "runtimePlan": {"resultKind": "tool", "engineCalls": [
                {"callId": "stats", "fn": "set_item_stats", "params": {"resultKind": "tool", "maxStack": 1, "pickPower": 55}},
                {"callId": "tool", "fn": "tool_capability", "params": {"pickPower": 55, "miningSpeedScale": 1.0}},
            ]},
        },
        "armor": {
            "category": "armor",
            **common,
            "runtimePlan": {"resultKind": "armor", "engineCalls": [
                {"callId": "stats", "fn": "set_item_stats", "params": {"resultKind": "armor", "maxStack": 1, "armorSlot": "head", "defense": 8}},
                {"callId": "armor", "fn": "armor_effect", "params": {"armorSlot": "head", "setKey": "test_set", "archetype": "magic", "defense": 8, "stats": {"maxMana": 20}, "setBonus": {"text": "Finite bonus.", "magicDamage": 0.1}}},
            ]},
        },
        "utility": {
            "category": "material",
            **common,
            "runtimePlan": {"resultKind": "material", "engineCalls": [
                {"callId": "stats", "fn": "set_item_stats", "params": {"resultKind": "material", "maxStack": 99}},
                {"callId": "consume", "fn": "consumption_behavior", "params": {"consumeChancePercent": 50}},
                {"callId": "condition", "fn": "use_condition", "params": {"mode": "grounded", "minLife": 10, "minMana": 5}},
            ]},
        },
    }
    for label, plan in cases.items():
        item = _attach(deepcopy(plan))
        report = structural_final_wire_report(item)
        assert report["ok"] is True, {label: report["blockingClaims"]}

    cue_plan = {
        "category": "weapon",
        **common,
        "runtimePlan": {"resultKind": "weapon", "engineCalls": [
            {"callId": "stats", "fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 11, "useTimeTicks": 30}},
            {"callId": "shot", "fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "speed": 8, "rangeTiles": 30, "lifetimeTicks": 90, "shotCount": 1, "spreadRadians": 0, "pierce": 1}},
            {"callId": "cue", "fn": "visual_effect_cue", "params": {"event": "hit", "rendererKind": "impactRing", "channel": "impactShape", "lane": "primary", "textureRole": "impact", "particleRole": "impact", "emissionMode": "ring", "particleSystemId": "pl:spark", "duration": 12, "importance": "core"}},
        ]},
    }
    cue_item = _attach(cue_plan)
    cue_report = structural_final_wire_report(cue_item)
    assert cue_report["ok"] is True, cue_report["blockingClaims"]
    assert cue_item["vfxCues"][0]["source"] == "runtimePlan.visual_effect_cue"
    manifest = _vfx_runtime_plan_direct_manifest(cue_item, "test-recipe")
    assert manifest is not None
    assert manifest["debug"]["composition"]["authoredCueSlots"]

    from infini_local.core.vfx_manifest import attach_hybrid_vfx_manifest

    equipped_plan = {
        "category": "accessory",
        **deepcopy(common),
        "runtimePlan": {"resultKind": "accessory", "engineCalls": [
            {"callId": "stats", "fn": "set_item_stats", "params": {"resultKind": "accessory", "maxStack": 1}},
            {"callId": "effect", "fn": "accessory_effect", "params": {"archetype": "mobility", "stats": {"movementSpeed": 0.1}}},
            {"callId": "cue", "fn": "visual_effect_cue", "params": {"event": "while_equipped", "rendererKind": "orbitingMotes", "channel": "ambientParticles", "lane": "support", "textureRole": "item", "particleRole": "item", "emissionMode": "orbit", "particleSystemId": "pl:glow", "duration": 24, "importance": "secondary"}},
        ]},
    }
    equipped_item = _attach(equipped_plan)
    assert equipped_item["attack"]["enabled"] is False
    attach_hybrid_vfx_manifest(equipped_item, "equipped-recipe")
    assert equipped_item["vfxManifest"]["slots"]
    assert equipped_item["vfxManifest"]["debug"]["composition"]["authoredCueSlots"]


def _contract_check_every_active_engine_param_has_a_provenance_policy() -> None:
    from infini_local.core.runtime_authoring.engine_call_contracts import engine_params_model
    from infini_local.core.runtime_authoring.function_contract_registry import (
        ENGINE_FUNCTION_CATALOG,
        ENGINE_FUNCTION_CONTRACT_BY_NAME,
        compiled_fields_for_authored_path,
    )
    from infini_local.core.runtime_authoring.schema import PLANNER_HIDDEN_ENGINE_FUNCTIONS
    from infini_local.core.runtime_contracts import authored_param_requires_final_wire_provenance

    failures: dict[str, list[str]] = {}
    for fn in ENGINE_FUNCTION_CATALOG:
        if fn in PLANNER_HIDDEN_ENGINE_FUNCTIONS:
            continue
        spec = ENGINE_FUNCTION_CONTRACT_BY_NAME[fn]
        contracts = {param.name: param for param in spec.params}
        missing: list[str] = []
        for name in engine_params_model(fn).model_fields:
            if not authored_param_requires_final_wire_provenance(fn, name):
                continue
            param = contracts[name]
            paths = (name, *(f"{name}.{row.path}" for row in param.nested_wire_paths))
            if not any(compiled_fields_for_authored_path(fn, path) for path in paths):
                missing.append(name)
        if missing:
            failures[fn] = sorted(missing)
    assert failures == {}


def _contract_check_scoped_repair_is_targeted_and_transport_failure_propagates(monkeypatch) -> None:
    captured: list[dict] = []

    def fake_chat(request_payload: dict, timeout: int) -> dict:
        captured.append(request_payload)
        return {
            "choices": [{"message": {"content": json.dumps({
                "engineCallParamPatches": [{
                    "callId": "primary",
                    "fn": "shoot_projectile",
                    "params": {"speed": 20},
                }],
            })}}],
            "_debug": {"transportFootprint": {"repairChars": 321}},
        }

    def mutating_source_gate(value: dict) -> dict:
        value.setdefault("runtimeContract", {})["schema"] = "compiler-owned-preflight"
        return {"ok": True, "blockingClaims": []}

    monkeypatch.setattr(llm_authoring_pipeline, "USE_LLM", True)
    monkeypatch.setenv("INFINI_LLM_REAUTHOR_MODEL", "replacement-model")
    monkeypatch.setattr(llm_authoring_pipeline, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(author_item_repair, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(llm_authoring_pipeline, "llm_chat_json", fake_chat)
    monkeypatch.setattr(llm_authoring_pipeline, "trace_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(llm_authoring_pipeline, "_prepare_parsed_author_item", lambda value: value)
    monkeypatch.setattr(llm_authoring_pipeline, "planner_runtime_promise_gate", mutating_source_gate)

    authored = {
        "name": "Accepted Identity",
        "category": "weapon",
        "concept": {
            "fantasy": "Accepted fantasy.",
            "mergeLogic": "Accepted fusion.",
            "coreMechanic": "Accepted mechanism.",
        },
        "runtimeContract": {
            "primaryVerb": "throw",
            "controlStyle": "tap",
            "playerViewTimeline": [{"phase": "release", "description": "Throw once."}],
        },
        "runtimePlan": {
            "resultKind": "weapon",
            "runtimeStateIntent": "No persistent state.",
            "sourceReading": "Shaft and crystal remain visible.",
            "balanceIntent": "One finite projectile per use.",
            "anomalyFlags": [],
            "sourceRolePreservation": {"itemA": "shaft", "itemB": "crystal"},
            "visualIntent": {
                "item": "accepted visual",
                "topology": "connected",
                "parts": ["crystal spear"],
                "arrangement": "one continuous spear silhouette",
                "preferredCanvasSize": 32,
            },
            "engineCalls": [{
                "callId": "primary",
                "fn": "shoot_projectile",
                "params": {"speed": 12},
            }, {
                "callId": "accepted_stats",
                "fn": "set_item_stats",
                "params": {"damage": 31, "useTimeTicks": 24},
            }],
        },
    }
    diagnostic = runtime_plan_validation_report(deepcopy(authored))
    assert any(
        row.get("callId") == "primary"
        and row.get("path") == "$.runtimePlan.engineCalls[0].params.spreadRadians"
        for row in diagnostic["errorDetails"]
    )
    assert "primary" in author_item_repair_scope._rejected_call_ids(
        {"runtimePlanValidationBeforeRepair": diagnostic},
        authored["runtimePlan"],
    )
    dotted_only_failure = {
        "errors": ["runtimePlan.engineCalls.0.fn: unknown engine function"],
    }
    assert author_item_repair_scope._rejected_call_ids(
        dotted_only_failure,
        authored["runtimePlan"],
    ) == {"primary"}
    assert author_item_repair_scope._repair_targets(dotted_only_failure) == [{
        "path": "$.runtimePlan.engineCalls[0].fn",
        "reason": "runtimePlan.engineCalls.0.fn: unknown engine function",
    }]
    dotted_replacement = author_item_repair_delta._preserve_accepted_authoring(
        {
            "runtimePlan": {
                "engineCalls": [{
                    "callId": "primary",
                    "fn": "shoot_projectile",
                    "params": {"speed": 20},
                }],
            },
        },
        authored,
        dotted_only_failure,
    )
    assert dotted_replacement["runtimePlan"]["engineCalls"][0]["params"]["speed"] == 20
    assert dotted_replacement["runtimePlan"]["engineCalls"][1] == authored["runtimePlan"]["engineCalls"][1]

    potion_identity_failure = {
        "errors": [{
            "path": "$.runtimePlan.engineCalls[0]",
            "callId": "stats",
            "reason": "combat set_item_stats requires positive damage; use a non-combat resultKind for pure utility",
        }],
    }
    potion_replacement = author_item_repair_delta._preserve_accepted_authoring(
        {
            "category": "potion",
            "runtimePlan": {
                "resultKind": "potion",
                "engineCalls": [{
                    "callId": "stats",
                    "fn": "set_item_stats",
                    "params": {"resultKind": "potion", "damage": 0, "healLife": 50},
                }],
            },
        },
        {
            "category": "weapon",
            "runtimePlan": {
                "resultKind": "consumable_weapon",
                "engineCalls": [{
                    "callId": "stats",
                    "fn": "set_item_stats",
                    "params": {"resultKind": "consumable_weapon", "damage": 0},
                }],
            },
        },
        potion_identity_failure,
    )
    assert potion_replacement["category"] == "potion"
    assert potion_replacement["runtimePlan"]["resultKind"] == "potion"

    rejected = deepcopy(authored)
    rejected["runtimeContract"].update({
        "schema": "compiler-owned",
        "executionStatus": "compiler-owned",
        "finalWireReceipts": [{"compiler": True}],
    })
    failure_report = {
        "stage": "compiler",
        # The real wrapper also carries a giant serialized candidate. Its accepted
        # field names are context, not rejection markers; only structured diagnostics
        # below may open a repair domain.
        "error": "strict authoring rejected: " + json.dumps({
            "runtimeContract": authored["runtimeContract"],
            "runtimePlan": {
                "sourceReading": authored["runtimePlan"]["sourceReading"],
                "visualIntent": authored["runtimePlan"]["visualIntent"],
            },
        }),
        "runtimePlanValidationBeforeRepair": {"errors": [{
            "kind": "range",
            "path": "$.runtimePlan.engineCalls[0].params.speed",
            "callId": "primary",
            "fn": "shoot_projectile",
            "reason": "speed must stay inside the executable range",
        }]},
    }
    parent = {"name": "Wood", "internalName": "Wood", "sourceMod": "Terraria", "type": 9}
    result = llm_authoring_pipeline.repair_author_item_after_failure(
        rejected, parent, parent, {}, {}, "recipe-key", failure_report=failure_report,
    )

    assert len(captured) == 1
    assert result["name"] == authored["name"]
    assert result["category"] == authored["category"]
    assert result["concept"] == authored["concept"]
    assert result["runtimeContract"] == authored["runtimeContract"]
    for field in ("runtimeStateIntent", "sourceReading", "balanceIntent", "anomalyFlags"):
        assert result["runtimePlan"][field] == authored["runtimePlan"][field]
    assert result["runtimePlan"]["sourceRolePreservation"] == authored["runtimePlan"]["sourceRolePreservation"]
    assert result["runtimePlan"]["visualIntent"] == authored["runtimePlan"]["visualIntent"]
    assert result["runtimePlan"]["engineCalls"][0]["params"]["speed"] == 20
    assert result["runtimePlan"]["engineCalls"][1] == authored["runtimePlan"]["engineCalls"][1]
    assert result["debug"]["model"] == "test-model"
    assert result["debug"]["authorRepair"] == "same_author_role_targeted_leaf_delta"
    assert "repairModelMayDiffer" not in result["debug"]
    assert result["debug"]["authorRepairTransport"]["transportFootprint"]["repairChars"] == 321
    assert captured[0]["model"] == "test-model"
    production_repair_schema = captured[0]["response_format"]["json_schema"]["schema"]
    assert set(production_repair_schema["properties"]) == {"engineCallParamPatches"}
    assert LLM_MODEL_OVERRIDE_KEY not in captured[0]
    dossier = json.loads(captured[0]["messages"][-1]["content"])
    assert dossier["repairMode"] == "targeted_leaf_delta"
    assert dossier["acceptedAuthorItem"]["runtimePlan"]["engineCalls"] == authored["runtimePlan"]["engineCalls"]
    assert dossier["acceptedAuthorItem"]["concept"] == authored["concept"]
    assert dossier["allowedAuthorDomains"] == ["runtimePlan"]
    assert dossier["rejectedCallIds"] == ["primary"]
    assert dossier["agentHandoff"]["currentSpeaker"] == "item_planner"
    assert dossier["agentHandoff"]["artifactSource"] == "acceptedAuthorItem"
    assert dossier["targetedRepairDeltaShape"]["engineCallParamPatches"][0]["params"] == {
        "changedParamOnly": "new typed value",
    }
    assert dossier["deltaRules"][0] == "Return the smallest sufficient delta; omit every unchanged top-level key."
    assert set(dossier["repairFunctionCards"]) == {"primary"}
    assert dossier["repairFunctionCards"]["primary"]["fn"] == "shoot_projectile"
    assert set(dossier["repairFunctionCards"]["primary"]["params"]) == {"speed"}
    from infini_local.pipelines.author_item_contract import (
        author_item_provider_targeted_repair_delta_schema,
        strict_author_item_targeted_repair_delta_report,
    )
    exact_provider_schema = author_item_provider_targeted_repair_delta_schema({
        "set_item_stats": {
            "callId": "set_item_stats",
            "fn": "set_item_stats",
            "params": {"useTimeTicks": {"type": "integer"}},
        },
    })
    patch_array = exact_provider_schema["properties"]["engineCallParamPatches"]
    assert patch_array["type"] == "array"
    patch_branch = patch_array["items"]["anyOf"][0]
    assert patch_branch["properties"]["callId"]["const"] == "set_item_stats"
    assert patch_branch["properties"]["fn"]["const"] == "set_item_stats"
    exact_params = patch_branch["properties"]["params"]
    assert set(exact_params["properties"]) == {"useTimeTicks"}
    assert exact_params["additionalProperties"] is False
    assert "useAnimationTicks" not in exact_params["properties"]
    assert set(exact_provider_schema["properties"]) == {"engineCallParamPatches"}
    assert strict_author_item_targeted_repair_delta_report({
        "engineCallReplacements": [{
            "callId": "set_item_stats",
            "fn": "set_item_stats",
            "params": {"useTimeTicks": 10},
        }],
    })["ok"] is False

    visual_provider_schema = author_item_provider_targeted_repair_delta_schema(
        {},
        allowed_author_field_schemas={
            "visualIntent": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"preferredCanvasSize": {"type": "integer"}},
                "required": [],
            },
        },
    )
    assert set(visual_provider_schema["properties"]) == {"authorFields"}
    visual_author = visual_provider_schema["properties"]["authorFields"]
    assert visual_author["type"] == "object"
    visual_intent = visual_author["properties"]["visualIntent"]
    assert visual_intent["type"] == "object"
    assert set(visual_intent["properties"]) == {"preferredCanvasSize"}
    assert "topology" not in visual_intent["properties"]
    assert "parents" not in dossier
    assert dossier["invalidTargets"] == [{
        "path": "$.runtimePlan.engineCalls[0].params.speed",
        "callId": "primary",
        "fn": "shoot_projectile",
        "reason": "speed must stay inside the executable range",
        "kind": "range",
    }]
    assert "parentAuthoringPacket" not in dossier
    assert "failureReport" not in dossier
    duplicate_fn_cards = author_item_repair_scope._targeted_repair_function_cards(
        {
            "engineCalls": [
                {"callId": "primary", "fn": "shoot_projectile", "params": {}},
                {"callId": "secondary", "fn": "shoot_projectile", "params": {}},
            ],
        },
        [
            {
                "path": "$.runtimePlan.engineCalls[0].params.speed",
                "callId": "primary",
                "fn": "shoot_projectile",
            },
            {
                "path": "$.runtimePlan.engineCalls[1].params.spreadRadians",
                "callId": "secondary",
                "fn": "shoot_projectile",
            },
        ],
        {"shoot_projectile": {"description": "finite projectile call"}},
    )
    assert set(duplicate_fn_cards) == {"primary", "secondary"}
    assert set(duplicate_fn_cards["primary"]["params"]) == {"speed"}
    assert set(duplicate_fn_cards["secondary"]["params"]) == {"spreadRadians"}
    provenance_failure = {
        "finalWireReport": {"blockingClaims": [{
            "kind": "compiler_provenance_mismatched",
            "callId": "accepted_stats",
            "authoredParam": "useAnimationTicks",
            "authoredValue": 0,
            "compiledField": "useAnimationTicks",
            "compiledValue": 10,
            "finalPath": "gameplay.useAnimation",
            "finalActual": 12,
        }]},
    }
    assert author_item_repair_scope._repair_targets(provenance_failure) == [{
        "callId": "accepted_stats",
        "reason": "compiler_provenance_mismatched",
        "kind": "compiler_provenance_mismatched",
        "authoredParam": "useAnimationTicks",
        "authoredValue": 0,
        "compiledField": "useAnimationTicks",
        "compiledValue": 10,
        "finalPath": "gameplay.useAnimation",
        "finalActual": 12,
    }]
    visual_and_call_failure = {
        "finalWireReport": {"blockingClaims": [{
            "kind": "compiler_provenance_mismatched", "callId": "accepted_stats",
        }]},
        "authorItemV3": {"errors": [{
            "path": "$.runtimePlan.visualIntent",
            "kind": "connected_topology_requires_one_significant_body",
        }]},
    }
    assert author_item_repair_scope._repair_allowed_patch_keys(
        visual_and_call_failure, True,
    ) == ["runtimePlan", "visualIntent"]
    assert author_item_repair_scope._repair_allowed_patch_keys(
        {"errors": [{"kind": "invalid_item_name"}]},
        True,
    ) == ["name"]
    assert author_item_repair_scope._repair_allowed_patch_keys(
        {"errors": [
            {"path": "$.runtimePlan.engineCalls[0].params.speed", "kind": "range"},
            {"path": "$.runtimeContract.playerViewTimeline", "kind": "timeline_runtime_conflict"},
        ]},
        True,
    ) == ["runtimePlan", "playerViewTimeline"]

    bad_category_only = deepcopy(authored)
    bad_category_only["category"] = "not-a-category"
    bad_category_only["runtimePlan"]["resultKind"] = "weapon"
    category_fixed = author_item_repair_delta._preserve_accepted_authoring(
        {"category": "weapon"},
        bad_category_only,
        {"errors": [{"path": "$.category", "kind": "invalid_category"}]},
    )
    assert category_fixed["category"] == "weapon"
    assert category_fixed["runtimePlan"]["resultKind"] == "weapon"

    bad_result_kind_only = deepcopy(authored)
    bad_result_kind_only["runtimePlan"]["resultKind"] = "not-a-kind"
    result_kind_fixed = author_item_repair_delta._preserve_accepted_authoring(
        {"runtimePlan": {"resultKind": "weapon"}},
        bad_result_kind_only,
        {"errors": [{
            "path": "$.runtimePlan.resultKind",
            "kind": "invalid_result_kind",
        }]},
    )
    assert result_kind_fixed["category"] == "weapon"
    assert result_kind_fixed["runtimePlan"]["resultKind"] == "weapon"

    invalid_visual = deepcopy(authored)
    invalid_visual["runtimePlan"]["visualIntent"]["preferredCanvasSize"] = "32"
    repaired_visual = author_item_repair_delta._preserve_accepted_authoring(
        {
            "runtimePlan": {
                "visualIntent": {
                    "item": "unwanted redesigned morphology",
                    "preferredCanvasSize": 48,
                },
            },
        },
        invalid_visual,
        {
            "authorItemV3": {
                "errors": [{
                    "kind": "enum",
                    "path": "$.runtimePlan.visualIntent.preferredCanvasSize",
                }],
            },
        },
    )
    assert repaired_visual["runtimePlan"]["visualIntent"]["preferredCanvasSize"] == 48
    assert repaired_visual["runtimePlan"]["visualIntent"]["item"] == "accepted visual"
    assert repaired_visual["runtimePlan"]["visualIntent"]["topology"] == "connected"
    assert repaired_visual["runtimePlan"]["visualIntent"]["parts"] == ["crystal spear"]

    duplicate_current = deepcopy(authored)
    duplicate_current["runtimePlan"]["engineCalls"].append(
        deepcopy(duplicate_current["runtimePlan"]["engineCalls"][0])
    )
    repaired_calls = deepcopy(authored["runtimePlan"]["engineCalls"])
    repaired_calls.append({
        "callId": "secondary",
        "fn": "shoot_projectile",
        "params": {"movement": "straight", "speed": 7},
    })
    deduplicated = author_item_repair_delta._preserve_accepted_authoring(
        {"runtimePlan": {"engineCalls": repaired_calls}},
        duplicate_current,
        {"errors": [{
            "path": "$.runtimePlan.engineCalls[1].callId",
            "kind": "duplicate_call_id",
            "callId": "primary",
        }]},
    )
    assert [call["callId"] for call in deduplicated["runtimePlan"]["engineCalls"]] == [
        "primary", "accepted_stats", "secondary",
    ]

    redesigned_visual_intent = deepcopy(authored["runtimePlan"]["visualIntent"])
    redesigned_visual_intent.update({
        "item": "two separated authored crystal bodies",
        "topology": "multipart_separated",
        "parts": ["crystal point", "shaft body"],
        "arrangement": "the point floats just ahead of the shaft",
    })
    whole_visual_repair = author_item_repair_delta._preserve_accepted_authoring(
        {"runtimePlan": {"visualIntent": redesigned_visual_intent}},
        authored,
        {"errors": [{"path": "$.runtimePlan.visualIntent", "kind": "topology_contract"}]},
    )
    assert whole_visual_repair["runtimePlan"]["visualIntent"] == redesigned_visual_intent
    assert whole_visual_repair["runtimePlan"]["engineCalls"] == authored["runtimePlan"]["engineCalls"]

    full_redesign = author_item_repair_delta._preserve_accepted_authoring(
        {
            "category": "weapon",
            "concept": {"coreMechanic": "A newly authored executable attack."},
            "runtimeContract": {"primaryVerb": "shoot", "controlStyle": "tap"},
            "runtimePlan": {
                "resultKind": "weapon",
                "runtimeStateIntent": "No persistent state.",
                "sourceReading": "The accepted literal source parts remain visible.",
                "balanceIntent": "One finite projectile per use.",
                "anomalyFlags": [],
                "engineCalls": authored["runtimePlan"]["engineCalls"],
            },
        },
        authored,
        {"kind": "unrepresentable_mechanic"},
    )
    assert full_redesign["name"] == authored["name"]
    assert full_redesign["concept"] == {
        "fantasy": authored["concept"]["fantasy"],
        "mergeLogic": authored["concept"]["mergeLogic"],
        "coreMechanic": "A newly authored executable attack.",
    }
    assert full_redesign["runtimePlan"]["sourceRolePreservation"] == authored["runtimePlan"]["sourceRolePreservation"]
    assert full_redesign["runtimePlan"]["visualIntent"] == authored["runtimePlan"]["visualIntent"]
    assert full_redesign["runtimePlan"]["runtimeStateIntent"] == "No persistent state."

    retained_equipment = {
        "name": "Accepted Helm",
        "category": "armor",
        "runtimePlan": {
            "resultKind": "armor",
            "engineCalls": [
                {
                    "callId": "stats",
                    "fn": "set_item_stats",
                    "params": {"resultKind": "armor", "armorSlot": "head", "defense": 3},
                },
                {
                    "callId": "armor",
                    "fn": "armor_effect",
                    "params": {
                        "armorSlot": "head",
                        "stats": {"lightStrength": 0.8, "lightColorName": "orange"},
                    },
                },
                {
                    "callId": "removed_combat",
                    "fn": "shoot_projectile",
                    "params": {"runtimeFamily": "shoot", "speed": 8},
                },
            ],
        },
    }
    equipment_redesign = author_item_repair_delta._preserve_accepted_authoring(
        {
            "category": "armor",
            "runtimePlan": {
                "resultKind": "armor",
                "engineCalls": [
                    {
                        "callId": "stats",
                        "fn": "set_item_stats",
                        "params": {"resultKind": "armor", "armorSlot": "head", "defense": 4},
                    },
                    {
                        "callId": "armor",
                        "fn": "armor_effect",
                        "params": {"armorSlot": "head", "stats": {"lightStrength": 0.8}},
                    },
                ],
            },
        },
        retained_equipment,
        {"kind": "executor_not_representable"},
    )
    equipment_calls = {
        call["callId"]: call
        for call in equipment_redesign["runtimePlan"]["engineCalls"]
    }
    assert equipment_calls["stats"]["params"]["defense"] == 4
    assert equipment_calls["armor"]["params"]["stats"] == {
        "lightStrength": 0.8,
        "lightColorName": "orange",
    }
    assert "removed_combat" not in equipment_calls

    _, redesign_dossier_json, *_ = author_item_repair.build_same_author_repair_request(
        rejected,
        parent,
        parent,
        {"kind": "unrepresentable_mechanic"},
    )
    redesign_dossier = json.loads(redesign_dossier_json)
    assert redesign_dossier["repairMode"] == "full_redesign"
    assert redesign_dossier["allowedPatchKeys"][0] == "category"
    from infini_local.core.runtime_authoring.function_contract_registry import (
        NORMALIZED_ROOT_REQUIRED_PARAM_NAMES,
    )
    from infini_local.core.runtime_authoring.schema import COMBAT_EXECUTOR_RESULT_KINDS
    assert redesign_dossier["normalizedRootRequiredFields"] == list(
        NORMALIZED_ROOT_REQUIRED_PARAM_NAMES
    )
    assert redesign_dossier["combatExecutorResultKinds"] == sorted(
        COMBAT_EXECUTOR_RESULT_KINDS
    )
    assert any(
        all(field in rule for field in NORMALIZED_ROOT_REQUIRED_PARAM_NAMES)
        and "must compile to" in rule.lower()
        for rule in redesign_dossier["redesignRules"]
    )
    assert any(
        "passive armor/accessory light" in rule
        and "set_alt_use_mode" in rule
        for rule in redesign_dossier["redesignRules"]
    )
    with pytest.raises(PlannerUnavailable, match="incomplete_gameplay_redesign_patch"):
        llm_authoring_pipeline.repair_author_item_after_failure(
            rejected,
            parent,
            parent,
            {},
            {},
            "recipe-key",
            failure_report={"kind": "unrepresentable_mechanic"},
        )

    attempts = 0

    def second_author_transport_failure(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("second author transport failed")

    monkeypatch.setattr(llm_authoring_pipeline, "llm_chat_json", second_author_transport_failure)
    with pytest.raises(RuntimeError, match="second author transport failed"):
        llm_authoring_pipeline.repair_author_item_after_failure(
            rejected, parent, parent, {}, {}, "recipe-key", failure_report=failure_report,
        )
    assert attempts == 1


def _contract_check_multiple_root_executors_fail_before_final_wire() -> None:
    authored = {
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {
                    "callId": "stats",
                    "fn": "set_item_stats",
                    "params": {
                        "resultKind": "weapon",
                        "damageClass": "ranged",
                        "damage": 20,
                        "useTimeTicks": 20,
                    },
                },
                {
                    "callId": "shot",
                    "fn": "shoot_projectile",
                    "params": {
                        "runtimeFamily": "shoot",
                        "delivery": "shoot",
                        "movement": "straight",
                        "speed": 9,
                        "rangeTiles": 45,
                        "lifetimeTicks": 90,
                        "shotCount": 1,
                        "spreadRadians": 0,
                        "pierce": 0,
                    },
                },
                {
                    "callId": "alternate_throw",
                    "fn": "shoot_projectile",
                    "params": {
                        "runtimeFamily": "throw",
                        "delivery": "throw",
                        "movement": "gravity_arc",
                        "speed": 8,
                        "rangeTiles": 30,
                        "lifetimeTicks": 75,
                        "shotCount": 1,
                        "spreadRadians": 0,
                        "pierce": 0,
                    },
                },
            ],
        },
    }
    report = runtime_plan_validation_report(authored)
    assert report["ok"] is False
    detail = next(
        row
        for row in report["errorDetails"]
        if row.get("callId") == "alternate_throw"
    )
    assert detail["path"] == "$.runtimePlan.engineCalls[2]"
    assert "one root executor" in detail["reason"]
    targets = author_item_repair_scope._repair_targets(
        {"runtimePlanValidationBeforeRepair": report}
    )
    assert any(
        row.get("callId") == "alternate_throw"
        and row.get("path") == "$.runtimePlan.engineCalls[2]"
        and "one root executor" in row.get("reason", "")
        for row in targets
    )


def _contract_check_runtime_authored_projectile_geometry_ignores_names_and_parent_tags() -> None:
    plan = {
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "weapon",
            "engineCalls": [
                {
                    "callId": "item_stats",
                    "fn": "set_item_stats",
                    "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 12, "useTimeTicks": 20},
                },
                {"callId": "primary", **_primary("shoot", "shoot", "straight", 60)},
            ],
        },
    }
    plain = _attach(
        deepcopy(plan),
        _parent("Copper", tags=["dagger", "knife"]),
        _parent("Copper", tags=["dagger"]),
        name="Copper Dagger",
        tooltip="A small ordinary blade.",
    )
    loud = _attach(
        deepcopy(plan),
        _parent("Zenith", tags=["zenith", "oversized", "explosive"]),
        _parent("Cataclysm", tags=["legendary", "boss"]),
        name="Zenith Cataclysm Knife",
        tooltip="Legendary colossal explosive nova.",
    )
    fields = ("projectileWidth", "projectileHeight", "projectileScale", "hitboxScale", "explosionRadius")
    assert {field: plain["attack"][field] for field in fields} == {
        field: loud["attack"][field] for field in fields
    } == {
        "projectileWidth": 16,
        "projectileHeight": 16,
        "projectileScale": 1.0,
        "hitboxScale": 1.0,
        "explosionRadius": 0,
    }

def _contract_check_equipment_light_and_fixed_item_timing_have_one_executable_owner() -> None:
    authored = {
        "category": "armor",
        "concept": {
            "fantasy": "A finite authored equipment light.",
            "mergeLogic": "The equipment body carries the authored lamp.",
            "coreMechanic": "Emits the authored light while equipped.",
        },
        "runtimeContract": {"primaryVerb": "equip", "controlStyle": "passive"},
        "runtimePlan": {
            "resultKind": "armor",
            "sourceRolePreservation": {"itemA": "equipment body", "itemB": "lamp"},
            "runtimeStateIntent": "No mutable runtime state.",
            "sourceReading": "One armor body with one lamp.",
            "balanceIntent": "A small passive equipment light.",
            "anomalyFlags": [],
            "visualIntent": {
                "item": "one connected helmet",
                "topology": "connected",
                "partCountMin": 1,
                "partCountMax": 1,
                "parts": ["helmet with attached lamp"],
                "arrangement": "one connected body",
                "preferredCanvasSize": 32,
            },
            "engineCalls": [{
                "callId": "stats",
                "fn": "set_item_stats",
                "params": {
                    "resultKind": "armor", "armorSlot": "head", "defense": 2,
                    "useTimeTicks": 0, "useAnimationTicks": 0,
                },
            }, {
                "callId": "armor",
                "fn": "armor_effect",
                "params": {
                    "armorSlot": "head", "archetype": "defense", "defense": 2,
                    "stats": {"lightStrength": 1.2},
                },
            }, {
                "callId": "light",
                "fn": "emit_light",
                "params": {"strength": 1.2, "color": "orange", "durationTicks": 240},
            }],
        },
    }
    invalid = runtime_plan_validation_report(deepcopy(authored))
    assert any("emit_light" in error and "armor_effect.stats" in error for error in invalid["errors"])
    assert any("lightColorName" in error for error in invalid["errors"])
    assert {row.get("callId") for row in invalid["errorDetails"]} >= {"armor", "light"}

    valid = deepcopy(authored)
    valid["runtimePlan"]["engineCalls"] = valid["runtimePlan"]["engineCalls"][:2]
    valid["runtimePlan"]["engineCalls"][1]["params"]["stats"]["lightColorName"] = "orange"
    patch = compile_runtime_plan_to_genome_patch(deepcopy(valid))
    assert patch["useTimeTicks"] == 10
    assert patch["useAnimationTicks"] == 10
    final_item = _attach(valid)
    assert final_item["gameplay"]["useTime"] == 10
    assert final_item["gameplay"]["useAnimation"] == 10
    assert final_item["armor"]["lightStrength"] == 1.2
    assert final_item["armor"]["lightColorName"] == "orange"
    assert final_runtime_promise_report(final_item)["ok"] is True


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_gameplay_authority_authorship_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(globals(), request)
