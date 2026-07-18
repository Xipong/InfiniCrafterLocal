from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from infini_local.core.errors import PlannerUnavailable
from infini_local.pipelines.author_item_contract import (
    author_item_provider_response_schema,
    author_item_prompt_shape_card,
    author_item_repair_response_schema,
    author_item_response_schema,
    project_provider_author_item_to_local,
    strict_author_item_repair_report,
    strict_author_item_v3_report,
)
from infini_local.pipelines import llm_transport
from infini_local.pipelines.combine_gameplay import attach_gameplay_and_attack
from infini_local.pipelines.combine_validation import strict_validate_authored_item, validate_and_repair
from infini_local.pipelines.llm_authoring_pipeline import (
    _prepare_parsed_author_item,
    build_initial_author_request,
    planner_runtime_promise_gate,
)


ROOT = Path(__file__).resolve().parents[2]


def _valid_author_item() -> dict:
    return {
        "name": "Workbench Edge",

        "category": "material",
        "concept": {
            "fantasy": "A portable carpenter's edge.",
            "mergeLogic": "Wood supplies the body while the bench supplies the bracing.",
            "coreMechanic": "The material stacks to ninety-nine.",
        },
        "runtimeContract": {
            "primaryVerb": "carry as a crafting material",
            "controlStyle": "passive",
            "playerViewTimeline": [],
        },
        "runtimePlan": {
            "resultKind": "material",
            "sourceRolePreservation": {"itemA": "wood body", "itemB": "bench brace"},
            "engineCalls": [{
                "callId": "item_stats",
                "fn": "set_item_stats",
                "params": {"resultKind": "material", "maxStack": 99},
            }],
            "runtimeStateIntent": "No runtime state.",
            "visualIntent": {
                "item": "A wood blade blank with folded bench braces.",
                "projectile": "None.",
                "impact": "None.",
                "vfxIntent": "Subtle sawdust motes only.",
                "vfxAvoid": "No combat effects.",
                "topology": "connected",
                "parts": ["wooden edge blank", "folded bench braces"],
                "arrangement": "braces folded tightly around the single edge blank",
            },
            "sourceReading": "Wood is the body; the bench is the brace.",
            "balanceIntent": "A stackable crafting material with no combat power.",
            "anomalyFlags": [],
        },

    }


def test_author_item_v3_design_metadata_is_compact_and_proof_is_compiler_owned() -> None:
    schema = author_item_response_schema()
    card = author_item_prompt_shape_card()
    assert set(card) == set(schema["required"])
    assert "visual" not in schema["properties"]
    assert "visual" not in card
    assert set(card["concept"]) == {"fantasy", "mergeLogic", "coreMechanic"}
    assert set(card["runtimeContract"]) == {
        "primaryVerb", "controlStyle", "playerViewTimeline",
    }
    assert "backingRefs" not in str(card)
    assert "signatureClaimId" not in str(card)
    concept = schema["properties"]["concept"]
    assert set(concept["required"]) == {"fantasy", "mergeLogic", "coreMechanic"}
    assert "weirdTwist" not in concept["properties"]
    visual_intent = schema["properties"]["runtimePlan"]["properties"]["visualIntent"]
    assert {
        "topology", "partCountMin", "partCountMax", "palette",
        "preferredCanvasSize", "projectileCanvasSize",
        "projectileVisualFamily", "projectileOrientation", "animeReference",
    } <= set(visual_intent["properties"])
    visual_card = card["runtimePlan"]["visualIntent"]
    for field in (
        "partCountMin", "partCountMax", "palette", "preferredCanvasSize",
        "projectileCanvasSize", "projectileVisualFamily", "projectileOrientation",
    ):
        assert field in visual_card
    assert visual_card["preferredCanvasSize"] == 32
    assert visual_card["projectileCanvasSize"] == 32
    assert isinstance(visual_card["preferredCanvasSize"], int)
    assert isinstance(visual_card["projectileCanvasSize"], int)

    runtime = schema["properties"]["runtimeContract"]
    assert set(runtime["required"]) == {"primaryVerb", "controlStyle"}
    assert set(runtime["properties"]) == {
        "primaryVerb",
        "controlStyle",
        "playerViewTimeline",
    }
    timeline = runtime["properties"]["playerViewTimeline"]
    assert timeline.get("minItems", 0) == 0
    assert timeline["maxItems"] == 8
    assert set(timeline["items"]["required"]) == {"phase", "description"}
    assert set(timeline["items"]["properties"]) == {"phase", "description"}
    assert {
        "tap",
        "hold-to-channel",
        "passive",
        "toggle",
        "automatic",
        "right-click-alt",
        "combo",
        "on-hit-trigger",
    } == set(runtime["properties"]["controlStyle"]["enum"])
    visual_intent = schema["properties"]["runtimePlan"]["properties"]["visualIntent"]
    assert {"topology", "parts", "arrangement"}.isdisjoint(visual_intent["required"])

    repair_calls = author_item_repair_response_schema()["properties"]["runtimePlan"]["properties"]["engineCalls"]
    assert all(
        {"callId", "fn"}.issubset(branch["required"])
        for branch in repair_calls["items"]["oneOf"]
    )
    partial_visual_repair = strict_author_item_repair_report({
        "visualIntent": {"preferredCanvasSize": 48},
    })
    assert partial_visual_repair["ok"] is True, partial_visual_repair["errors"]
    quoted_visual_repair = strict_author_item_repair_report({
        "visualIntent": {"preferredCanvasSize": "48"},
    })
    assert quoted_visual_repair["ok"] is False
    assert any(
        row.get("path") == "$.visualIntent.preferredCanvasSize"
        and row.get("kind") == "enum"
        for row in quoted_visual_repair["errors"]
    )

    candidate = _valid_author_item()
    candidate["concept"] = {
        "fantasy": "A portable carpenter's edge.",
        "mergeLogic": "Wood supplies the body while the bench supplies the bracing.",
        "coreMechanic": "A stackable crafting material with no active use.",
    }
    candidate["runtimeContract"] = {
        "primaryVerb": "carry as a crafting material",
        "controlStyle": "passive",
        "playerViewTimeline": [],
    }
    report = strict_author_item_v3_report(candidate)
    assert report["ok"] is True, report["errors"]
    topology_unspecified = deepcopy(candidate)
    for field in ("topology", "parts", "arrangement"):
        topology_unspecified["runtimePlan"]["visualIntent"].pop(field)
    unspecified_report = strict_author_item_v3_report(topology_unspecified)
    assert unspecified_report["ok"] is True, unspecified_report["errors"]
    timeline_unspecified = deepcopy(candidate)
    timeline_unspecified["runtimeContract"].pop("playerViewTimeline")
    timeline_unspecified_report = strict_author_item_v3_report(timeline_unspecified)
    assert timeline_unspecified_report["ok"] is True, timeline_unspecified_report["errors"]
    prepared = _prepare_parsed_author_item(deepcopy(candidate))
    authored_contract = deepcopy(prepared["runtimeContract"])
    assert planner_runtime_promise_gate(prepared)["ok"] is True
    assert prepared["runtimeContract"] == authored_contract
    strict_validate_authored_item(prepared, {"name": "Wood"}, {"name": "Work Bench"})
    assert prepared["runtimeContract"] == authored_contract
    assert "schema" not in prepared["runtimeContract"]
    assert "finalWireReceipts" not in prepared["runtimeContract"]
    assert "mechanicClaims" not in prepared["runtimeContract"]
    assert "signatureClaimId" not in prepared["runtimeContract"]
    projected = validate_and_repair(
        prepared, {"name": "Wood"}, {"name": "Work Bench"}, {}, {}, "visual_owner",
    )
    assert projected["visual"]["topology"] == "connected"
    assert projected["visual"]["parts"] == ["wooden edge blank", "folded bench braces"]
    assert projected["visual"]["arrangement"] == "braces folded tightly around the single edge blank"
    compiled = attach_gameplay_and_attack(
        projected,
        {"name": "Wood"},
        {"name": "Work Bench"},
        {},
        {},
    )
    assert compiled["runtimeContract"]["schema"] == "infini.runtime-contract.v3"
    assert compiled["runtimeContract"]["finalWireReceipts"]


def test_author_item_auto_response_format_stays_light_even_for_local_provider(monkeypatch) -> None:
    parent = {"name": "Wood", "internalName": "Wood", "sourceMod": "Terraria", "type": 9}
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", "auto")
    request, _, _ = build_initial_author_request(
        parent,
        {"name": "Work Bench", "internalName": "WorkBench", "sourceMod": "Terraria", "type": 36},
        {},
        {},
        "format-contract",
        model_name="local-test-model",
    )
    assert request["response_format"] == {"type": "json_object"}

    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", "json_schema")
    explicit, _, _ = build_initial_author_request(
        parent,
        {"name": "Work Bench", "internalName": "WorkBench", "sourceMod": "Terraria", "type": 36},
        {},
        {},
        "format-contract",
        model_name="local-test-model",
    )
    assert explicit["response_format"]["type"] == "json_schema"


def test_author_item_v3_is_fully_strict_locally_and_has_no_name_repair_hop() -> None:
    valid = _valid_author_item()
    assert strict_author_item_v3_report(valid)["ok"] is True

    provider_shaped = deepcopy(valid)
    provider_shaped["runtimeContract"]["playerViewTimeline"] = None
    provider_shaped["runtimePlan"]["visualIntent"].update({
        "palette": None,
        "partCountMin": None,
        "projectileCanvasSize": None,
    })
    projected = project_provider_author_item_to_local(provider_shaped)
    assert "playerViewTimeline" not in projected["runtimeContract"]
    assert "palette" not in projected["runtimePlan"]["visualIntent"]
    assert "partCountMin" not in projected["runtimePlan"]["visualIntent"]
    assert "projectileCanvasSize" not in projected["runtimePlan"]["visualIntent"]
    assert strict_author_item_v3_report(projected)["ok"] is True

    required_null = deepcopy(provider_shaped)
    required_null["concept"]["fantasy"] = None
    required_null["unexpectedProviderField"] = None
    required_projection = project_provider_author_item_to_local(required_null)
    assert required_projection["concept"]["fantasy"] is None
    assert "unexpectedProviderField" in required_projection
    assert strict_author_item_v3_report(required_projection)["ok"] is False

    prepared = _prepare_parsed_author_item(deepcopy(valid))
    raw_snapshot = prepared["_authorItemRaw"]
    assert raw_snapshot == valid
    assert raw_snapshot is not valid
    assert strict_author_item_v3_report(raw_snapshot)["ok"] is True
    strict_validate_authored_item(prepared, {"name": "Wood"}, {"name": "Work Bench"})
    assert "attack" not in raw_snapshot
    assert "visual" not in raw_snapshot

    legacy_proof = deepcopy(valid)
    legacy_proof["runtimeContract"]["signatureMode"] = "mechanic"
    assert strict_author_item_v3_report(legacy_proof)["ok"] is False

    plan_kind_mismatch = deepcopy(valid)
    plan_kind_mismatch["runtimePlan"]["resultKind"] = "weapon"
    with pytest.raises(PlannerUnavailable, match="runtimePlan.resultKind=weapon disagrees"):
        strict_validate_authored_item(
            _prepare_parsed_author_item(plan_kind_mismatch),
            {"name": "Wood"},
            {"name": "Work Bench"},
        )

    category_mismatch = deepcopy(valid)
    category_mismatch["category"] = "accessory"
    with pytest.raises(PlannerUnavailable, match="category=accessory disagrees"):
        strict_validate_authored_item(
            _prepare_parsed_author_item(category_mismatch),
            {"name": "Wood"},
            {"name": "Work Bench"},
        )

    noncanonical_consumable = deepcopy(valid)
    noncanonical_consumable["category"] = "consumable_weapon"
    assert strict_author_item_v3_report(noncanonical_consumable)["ok"] is False

    duplicate_tooltip = deepcopy(valid)
    duplicate_tooltip["tooltip"] = "Duplicate model-owned mirror."
    tooltip_report = strict_author_item_v3_report(duplicate_tooltip)
    assert tooltip_report["ok"] is False
    assert any(row["path"] == "$.tooltip" and row["kind"] == "additional_property" for row in tooltip_report["errors"])

    extra = deepcopy(valid)
    extra["attackPattern"] = "legacy semantic field"
    extra_report = strict_author_item_v3_report(extra)
    assert extra_report["ok"] is False
    assert any(row["path"] == "$.attackPattern" and row["kind"] == "additional_property" for row in extra_report["errors"])

    missing = deepcopy(valid)
    missing["runtimePlan"].pop("visualIntent")
    missing_report = strict_author_item_v3_report(missing)
    assert missing_report["ok"] is False
    assert any(row["path"] == "$.runtimePlan.visualIntent" and row["kind"] == "required" for row in missing_report["errors"])

    unknown_param = deepcopy(valid)
    unknown_param["runtimePlan"]["engineCalls"][0]["params"]["madeUp"] = 7
    param_report = strict_author_item_v3_report(unknown_param)
    assert param_report["ok"] is False
    assert any("madeUp" in row["path"] for row in param_report["errors"])

    unknown_function = deepcopy(valid)
    unknown_function["runtimePlan"]["engineCalls"][0] = {
        "callId": "unknown",
        "fn": "invent_gameplay_at_runtime",
        "params": {},
    }
    assert strict_author_item_v3_report(unknown_function)["ok"] is False

    wrong_type = deepcopy(valid)
    wrong_type["runtimePlan"]["engineCalls"][0]["params"]["damage"] = "12"
    assert strict_author_item_v3_report(wrong_type)["ok"] is False

    nonfinite = deepcopy(valid)
    nonfinite["runtimePlan"]["engineCalls"][0]["params"]["damage"] = float("inf")
    assert strict_author_item_v3_report(nonfinite)["ok"] is False

    duplicate_call_id = deepcopy(valid)
    duplicate_call_id["runtimePlan"]["engineCalls"].append(deepcopy(duplicate_call_id["runtimePlan"]["engineCalls"][0]))
    duplicate_report = strict_author_item_v3_report(duplicate_call_id)
    assert duplicate_report["ok"] is False
    assert any(row["kind"] == "duplicate_call_id" for row in duplicate_report["errors"])

    throw_without_authored_movement = deepcopy(valid)
    throw_without_authored_movement["runtimePlan"]["engineCalls"].append({
        "callId": "primary_throw",
        "fn": "shoot_projectile",
        "params": {"delivery": "throw", "runtimeFamily": "throw", "speed": 9},
    })
    omitted_movement_report = strict_author_item_v3_report(throw_without_authored_movement)
    assert omitted_movement_report["ok"] is False
    assert any(
        row["path"] == "$.runtimePlan.engineCalls[1].params.movement"
        and row["kind"] == "required_for_physical_throw"
        for row in omitted_movement_report["errors"]
    )
    throw_without_authored_movement["runtimePlan"]["engineCalls"][1]["params"]["movement"] = "straight"
    assert strict_author_item_v3_report(throw_without_authored_movement)["ok"] is True

    bad_name = deepcopy(valid)
    bad_name["name"] = "Generated Item"
    wrapped = {**deepcopy(bad_name), "_authorItemRaw": deepcopy(bad_name), "debug": {"planner": "llm_author_first"}}
    with pytest.raises(PlannerUnavailable, match="invalid_item_name"):
        strict_validate_authored_item(wrapped, {"name": "Wood"}, {"name": "Work Bench"})

    identity_source = (ROOT / "LocalGenerator/infini_local/pipelines/result_identity_policy.py").read_text(encoding="utf-8")
    stage_source = (ROOT / "LocalGenerator/infini_local/core/llm_stage_messages.py").read_text(encoding="utf-8")
    assert "try_llm_name_repair" not in identity_source
    assert "name_repair_contract" not in stage_source
    assert "name_repairer" not in stage_source

    assert not (ROOT / "LocalGenerator/infini_local/core/runtime_archetypes.py").exists()
    for source_path in (
        "LocalGenerator/infini_local/pipelines/author_item_contract.py",
        "LocalGenerator/infini_local/pipelines/llm_authoring_prompt.py",
        "LocalGenerator/infini_local/core/runtime_authoring/compiler.py",
        "LocalGenerator/infini_local/core/runtime_authoring/reports.py",
        "LocalGenerator/infini_local/core/contract_versions.py",
        "LocalGenerator/infini_local/core/boundary_models.py",
    ):
        assert "runtimeArchetype" not in (ROOT / source_path).read_text(encoding="utf-8")
    world_source = (ROOT / "LocalGenerator/infini_local/storage/world_storage.py").read_text(encoding="utf-8")
    assert "_project_runtime_archetype_for_delivery" not in world_source
    assert '"runtimeArchetype"' in world_source
    for source_path in (
        "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Model.cs",
        "ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize.cs",
    ):
        assert "RuntimeArchetype" not in (ROOT / source_path).read_text(encoding="utf-8")

    assert not (ROOT / "LocalGenerator/infini_local/core/runtime_promise_truth.py").exists()
    runtime_contract_source = (ROOT / "LocalGenerator/infini_local/core/runtime_contracts.py").read_text(encoding="utf-8")
    reports_source = (ROOT / "LocalGenerator/infini_local/core/runtime_authoring/reports.py").read_text(encoding="utf-8")
    for removed_symbol in (
        'RUNTIME_CONTRACT_SCHEMA = "infini.runtime-contract.v2"',
        "def normalize_runtime_contract(",
        "def validate_runtime_contract(",
        "def mechanic_claim_backing_relevant(",
    ):
        assert removed_symbol not in runtime_contract_source
    assert "validate_runtime_contract" not in reports_source

    provider_schema = author_item_provider_response_schema()
    forbidden_provider_keywords: list[str] = []
    strict_object_mismatches: list[str] = []

    def walk_provider_schema(value, path: str = "$") -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                properties = value.get("properties") if isinstance(value.get("properties"), dict) else {}
                if properties and set(value.get("required") or []) != set(properties):
                    strict_object_mismatches.append(path)
                if value.get("additionalProperties") is not False:
                    strict_object_mismatches.append(path + ".additionalProperties")
            for key, child in value.items():
                if key in {"default", "oneOf", "contains", "minContains", "maxContains"}:
                    forbidden_provider_keywords.append(path + "." + key)
                walk_provider_schema(child, path + "." + key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk_provider_schema(child, f"{path}[{index}]")

    walk_provider_schema(provider_schema)
    assert strict_object_mismatches == []
    assert forbidden_provider_keywords == []
    # Provider projection is grammar-only; the sparse local semantic owner remains separate.
    assert author_item_response_schema() != provider_schema
