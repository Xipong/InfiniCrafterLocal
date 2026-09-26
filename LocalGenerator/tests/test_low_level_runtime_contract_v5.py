from __future__ import annotations

import copy
import json
from pathlib import Path

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY,
    INPUT_KIND_REGISTRY,
    audit_compiler_receipts,
    build_runtime_repair_scope,
    capability_provider_union,
    compile_runtime_program,
    compact_capability_catalog,
    validate_runtime_program,
    validate_runtime_wire,
)
from infini_local.core.runtime_authoring.terraria_vocabulary import DAMAGE_CLASS_TOKENS
from infini_local.pipelines.llm_authoring_prompt import (
    PLANNER_PROMPT_LIMIT_CHARS,
    PLANNER_PROMPT_MIN_HEADROOM_CHARS,
    build_llm_author_payload,
    planner_prompt_usability_report,
)
from infini_local.pipelines.author_item_contract import (
    author_item_provider_response_schema,
    author_item_prompt_shape_card,
    author_item_repair_prompt_shape_card,
    author_item_repair_response_schema,
    author_item_response_schema,
)
from infini_local.pipelines.generated_parent_summary import generated_parent_summary_from_data
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
from infini_local.pipelines.parent_context_pipeline import _generated_runtime_primary_projectile
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.storage.world_storage import sanitize_recipe_for_delivery


def _codes(report: dict) -> set[str]:
    return {str(row.get("code")) for row in report.get("errors") or []}


def test_generated_parent_projectile_projection_follows_canonical_primary_binding() -> None:
    generated = {
        "runtimeProgram": {
            "entities": [
                {"id": "body", "kind": "item_body"},
                {"id": "support_first", "kind": "projectile"},
                {"id": "authored_primary", "kind": "projectile"},
            ],
            "bindings": [{
                "id": "primary",
                "input": "primary_use",
                "usePolicy": {
                    "action": {"kind": "spawn_entity", "targetId": "authored_primary"},
                    "stackCost": 0,
                    "contactDamage": False,
                },
            }],
        },
    }
    projected = _generated_runtime_primary_projectile(generated)
    assert projected["id"] == "authored_primary"


def test_generated_parent_summary_uses_late_report_and_behavior_checks() -> None:
    authored = build_runtime_fixture("workbench_blade")
    authored["id"] = "generated_summary_fixture"
    authored["concept"]["coreMechanic"] = "EARLY CONCEPT MUST NOT LEAK"
    authored["realization"].update({
        "description": "Late accepted blade realization.",
        "playerExperience": "Late accepted player experience.",
    })
    authored["realization"]["selfEvaluation"]["programVsReport"] = {
        "verdict": "aligned",
        "summary": "The report covers both executable lanes.",
        "behaviorChecks": [
            {
                "runtimeRefs": ["primary_workbench"],
                "programBehavior": "Primary use launches the authored workbench projectile.",
                "reportedBehavior": "Primary use launches the authored workbench projectile.",
                "result": "aligned",
                "reason": "The final report names the exact primary lane.",
            },
            {
                "runtimeRefs": ["shed_nails"],
                "programBehavior": "A hit releases five nails.",
                "reportedBehavior": "A hit releases ten nails.",
                "result": "mismatch",
                "reason": "The final report overstates the exact event count.",
            },
        ],
    }
    summary = generated_parent_summary_from_data(authored)
    assert summary["identity"] == "generated:generated_summary_fixture"
    assert summary["description"] == "Late accepted blade realization."
    assert summary["playerExperience"] == "Late accepted player experience."
    assert "EARLY CONCEPT MUST NOT LEAK" not in json.dumps(summary)
    assert summary["notableEffects"] == [
        "Primary use launches the authored workbench projectile.",
        "A hit releases five nails.",
    ]
    assert "ten nails" not in json.dumps(summary)
    assert "backedByClaims" not in summary
    assert "parentComposition" not in summary

    authored["generatedParentSummary"] = summary
    delivered = sanitize_recipe_for_delivery(authored)
    delivered_summary = delivered["generatedParentSummary"]
    assert delivered_summary["description"] == "Late accepted blade realization."
    assert delivered_summary["playerExperience"] == "Late accepted player experience."
    recursive = raw_parent_card_for_llm({"name": authored["name"], "generatedData": delivered})
    recursive_summary = recursive["raw"]["generatedParent"]["summary"]
    assert recursive_summary["description"] == "Late accepted blade realization."
    assert recursive_summary["playerExperience"] == "Late accepted player experience."
    assert recursive_summary["notableEffects"] == summary["notableEffects"]
    assert recursive_summary["schema"] == "infini.generated-parent-summary.v2"
    assert recursive_summary["identity"] == summary["identity"]
    assert "fantasy" not in recursive_summary


def test_registry_provider_prompt_and_vertical_wire_are_one_inventory() -> None:
    names = set(CAPABILITY_REGISTRY)
    assert {row["fn"] for row in compact_capability_catalog()} == names
    assert len(capability_provider_union()) == len(names)
    heal_capability = CAPABILITY_REGISTRY["heal_owner_on_event"]
    assert heal_capability.network_authority == "owner_execute_sync"
    parent_a = {"name": "Workbench", "id": "a", "damage": 0, "useTime": 20, "tags": ["furniture"]}
    parent_b = {"name": "Blade", "id": "b", "damage": 18, "useTime": 24, "tags": ["metal"]}
    payload = build_llm_author_payload(parent_a, parent_b, parent_a, parent_b, "a+b")
    invariants = payload["runtimeProgramInvariants"]
    assert invariants["primaryEntityOwnership"]["authoredField"] == "runtimeProgram.primaryEntityId"
    assert invariants["primaryEntityOwnership"]["exactlyOnePrimaryEntity"] is True
    assert "do not carry role" in invariants["primaryEntityOwnership"]["preEmissionCheck"]
    assert invariants["exclusiveInputs"]["inputs"] == sorted(
        name for name, spec in INPUT_KIND_REGISTRY.items() if spec.exclusive
    )
    assert invariants["damageClass"]["builtInTokens"] == list(DAMAGE_CLASS_TOKENS)
    assert invariants["damageClass"]["otherTokensAllowed"] is False
    assert "does not require a use_item_body binding" in invariants["exclusiveInputs"]["configureItemUseRule"]
    use_item_body_card = next(
        row for row in payload["runtimeCapabilityContract"]["catalog"]["bindingActions"]
        if row["action"] == "use_item_body"
    )
    assert "never pair it with spawn_entity" in use_item_body_card["does"]
    self_check = " ".join(payload["selfCheck"])
    assert "set runtimeProgram.primaryEntityId" in self_check
    assert "never emit role in Author bindings or calls" in self_check
    assert "parent sentinel none is forbidden" in self_check
    assert "every damageClass" in self_check
    truth = invariants["realizationExecutionTruth"]
    assert "realization.selfEvaluation" in truth["authority"]
    assert "runtimeContract.selfEvaluation" not in truth["authority"]
    assert "does not emit item_body.on_use" in truth["placementUse"]
    assert "natural lifetime expiry" in truth["terminationEvents"]
    assert "whole generated item" in truth["stackCost"]
    assert "returned" in truth["placementEscrow"]
    assert "target_and_fire" in truth["entityTopology"]
    assert "free_projectile" in truth["entityTopology"]
    report = planner_prompt_usability_report(parent_a, parent_b, parent_a, parent_b, "a+b")
    assert report["ok"] is True
    assert PLANNER_PROMPT_LIMIT_CHARS == 96_000
    assert report["limit"] == PLANNER_PROMPT_LIMIT_CHARS
    assert report["headroom"] >= PLANNER_PROMPT_MIN_HEADROOM_CHARS
    assert report["visibleCapabilities"] == len(names)
    assert report["missingCapabilities"] == []
    assert report["extraCapabilities"] == []
    assert report["containsWeaponMacro"] is False
    assert report["containsFamilyRouter"] is False

    rich_parent = build_runtime_fixture("held_and_deployed")
    rich_report = planner_prompt_usability_report(
        rich_parent, rich_parent, rich_parent, rich_parent, "rich+rich"
    )
    assert rich_report["ok"] is True
    assert rich_report["headroom"] >= PLANNER_PROMPT_MIN_HEADROOM_CHARS
    assert rich_report["visibleCapabilities"] == len(names)
    assert rich_report["missingCapabilities"] == []


def test_author_prompt_shape_card_matches_root_object_cardinality_without_provider_schema() -> None:
    card = author_item_prompt_shape_card()
    expected_model_order = ["name", "category", "concept", "runtimeProgram", "realization"]
    assert card["root"] == expected_model_order
    assert list(author_item_response_schema()["properties"]) == expected_model_order

    exported = json.loads(
        (Path(__file__).resolve().parents[2] / "contracts/schemas/author_item_response.schema.json")
        .read_text(encoding="utf-8")
    )
    assert list(exported["properties"]) == expected_model_order
    assert list(author_item_provider_response_schema()["properties"]) == expected_model_order
    assert isinstance(card["concept"], dict)
    assert set(card["concept"]) == {
        "literalSynthesis", "coreMechanic", "parentAContribution", "parentBContribution",
        "playerExperience", "plannedPlayerActions",
    }
    planned_action = card["concept"]["plannedPlayerActions"][0]
    assert set(planned_action) == {"input", "intent"}
    assert "runtimeContract" not in card
    assert set(card["realization"]) == {
        "description", "playerExperience", "selfEvaluation",
    }
    evaluation = card["realization"]["selfEvaluation"]
    assert set(evaluation) == {"planVsProgram", "programVsReport"}
    assert set(evaluation["planVsProgram"]) == {"verdict", "summary", "actionChecks"}
    assert set(evaluation["programVsReport"]) == {"verdict", "summary", "behaviorChecks"}
    assert set(evaluation["planVsProgram"]["actionChecks"][0]) == {
        "plannedIntent", "implementedBehavior", "runtimeRefs", "result", "intentionality", "reason",
    }
    assert set(evaluation["programVsReport"]["behaviorChecks"][0]) == {
        "runtimeRefs", "programBehavior", "reportedBehavior", "result", "reason",
    }
    assert card["runtimeProgram"]["apiVersion"] == "infini.runtime-program.v5"
    assert card["runtimeProgram"]["schema"] == "infini.runtime-program.authoring.v4"
    assert card["runtimeProgram"]["primaryEntityId"] == "exact existing entity id chosen once by the model"
    author_binding = card["runtimeProgram"]["bindings"][0]
    assert set(author_binding) == {"id", "input", "usePolicy"}
    assert set(author_binding["usePolicy"]) == {"action", "stackCost", "contactDamage"}
    assert set(author_binding["usePolicy"]["action"]) == {"kind", "targetId", "placementCallId"}
    assert "role" not in author_binding
    assert "role" not in card["runtimeProgram"]["calls"][0]
    assert isinstance(card["runtimeProgram"]["calls"][0]["params"], dict)
    prompt_payload = build_llm_author_payload({}, {}, {}, {}, "binding-card")
    binding_guide = prompt_payload["runtimeCapabilityContract"]["catalog"]["fieldGuide"]["bindingTarget"]
    assert "bindings[].usePolicy.action.targetId" in binding_guide
    assert "bindings[].target" not in binding_guide

    repair_card = author_item_repair_prompt_shape_card()
    repair_schema = author_item_repair_response_schema()
    repair_binding = repair_card["bindingsUpsert"][0]
    assert set(repair_binding) == {"id", "input", "usePolicy"}
    assert repair_binding["usePolicy"] == author_binding["usePolicy"]
    assert set(repair_card) == set(repair_schema["properties"])
    assert all(isinstance(repair_card[key], list) for key in (
        "entitiesUpsert", "entityIdsDelete", "bindingsUpsert", "bindingIdsDelete",
        "callsUpsert", "callIdsDelete",
    ))
    assert "claimsUpsert" not in repair_card
    assert "claimIdsDelete" not in repair_card
    assert isinstance(repair_card["metadataPatch"], dict)
    assert isinstance(repair_card["realizationReplacement"], dict)
    assert isinstance(repair_card["note"], str)


def test_gameplay_author_stages_are_plain_and_one_pass() -> None:
    payload = build_llm_author_payload({}, {}, {}, {}, "one-pass-stage-guide")
    stages = payload["gameplayAuthoringStages"]
    assert [row["name"] for row in stages] == [
        "initial_design_draft",
        "executable_gameplay_program",
        "final_gameplay_report",
        "same_pass_self_evaluation",
    ]
    assert [row["field"] for row in stages] == [
        "concept",
        "runtimeProgram",
        "realization.description + realization.playerExperience",
        "realization.selfEvaluation",
    ]
    encoded = json.dumps(stages, ensure_ascii=False).casefold()
    assert "non-binding" in encoded
    assert "never rejects the craft" in encoded
    assert "only executable gameplay authority" in encoded
    assert "program_evidence_claims" not in encoded
    assert "same model response" in encoded


def test_concept_drift_and_report_mismatch_are_diagnostic_not_rejection() -> None:
    authored = build_runtime_fixture("workbench_blade")
    authored["concept"]["plannedPlayerActions"] = [{
        "input": "primary_use",
        "intent": "Teleport the player, although the executable draft later chooses a melee swing.",
    }]
    authored["realization"]["selfEvaluation"] = {
        "planVsProgram": {
            "verdict": "changed",
            "summary": "The initial teleport sketch became a melee swing.",
            "actionChecks": [{
                "plannedIntent": "Teleport on primary use.",
                "implementedBehavior": "Primary use swings the item body.",
                "runtimeRefs": ["primary_workbench"],
                "result": "changed",
                "intentionality": "intentional",
                "reason": "The executable program selected the supported melee composition.",
            }],
        },
        "programVsReport": {
            "verdict": "mismatch",
            "summary": "The report intentionally demonstrates a detectable mismatch.",
            "behaviorChecks": [{
                "runtimeRefs": ["primary_workbench"],
                "programBehavior": "Primary use swings the item body.",
                "reportedBehavior": "Primary use teleports the player.",
                "result": "mismatch",
                "reason": "Diagnostic mismatch; it is not a semantic craft gate.",
            }],
        },
    }
    report = validate_runtime_program(authored)
    assert report["ok"] is True, report


def test_planned_player_actions_are_requested_but_never_a_craft_gate() -> None:
    authored = build_runtime_fixture("workbench_blade")
    authored["concept"].pop("plannedPlayerActions")
    report = validate_runtime_program(authored)
    assert report["ok"] is True, report


def test_author_context_contains_only_source_backed_parent_packets_and_numeric_balance() -> None:
    parent = {
        "name": "GlowingMushroom",
        "internalName": "GlowingMushroom",
        "sourceMod": "Terraria",
        "damage": 0,
        "useTime": 20,
        "rare": 3,
        "value": 1000,
        "tags": ["wings", "accessory"],
    }
    generated_parent = copy.deepcopy(parent)
    generated_parent["generatedData"] = {"recipeMeta": {"generationDepth": 9}}
    payload = build_llm_author_payload(generated_parent, parent, {"headNoun": "wings"}, {"headNoun": "ore"}, "facts-only")
    encoded_parents = json.dumps(payload["parents"], ensure_ascii=False).casefold()
    assert "canonical" not in encoded_parents
    assert "headnoun" not in encoded_parents
    assert '"tags"' not in encoded_parents
    assert "primarycategory" not in encoded_parents
    corridor = payload["balanceCorridor"]
    assert corridor["authority"] == "source_numeric_facts_only"
    assert corridor["parentProgressionFacts"] == [{
        "parent": "A",
        "path": "generatedData.recipeMeta.generationDepth",
        "value": 9,
    }]
    assert "stage" not in corridor
    assert "parentNumericTiers" not in corridor
    assert "recipeCoherence" not in corridor
    assert "knowledgeTiers" not in corridor

    ammo_parent = {
        "name": "Raw Ammo Parent",
        "useAmmo": 1,
        "ammoRaw": {
            "ammoId": 1,
            "projectileRaw": {
                "ownerHitCheck": True,
                "tileCollide": False,
                "timeLeft": 60,
                "width": 12,
                "height": 12,
                "setsRaw": {
                    "classifier": "weapon",
                    "canonical": {"headNoun": "sword", "hardTags": ["sword"]},
                    "tags": ["sword"],
                    "primaryCategory": "combat",
                },
            },
        },
    }
    ammo_payload = build_llm_author_payload(ammo_parent, parent, {}, {}, "nested-ammo-facts-only")
    encoded_ammo = json.dumps(ammo_payload["parents"], ensure_ascii=False)
    assert "behaviorDigest" not in encoded_ammo
    assert "mechanicalHint" not in encoded_ammo
    assert '"semantics"' not in encoded_ammo
    assert '"canonical"' not in encoded_ammo
    assert '"tags"' not in encoded_ammo
    assert '"headNoun"' not in encoded_ammo
    assert '"primaryCategory"' not in encoded_ammo
    assert '"classifier"' not in encoded_ammo


def test_generated_parent_packet_never_synthesizes_a_primary_projectile() -> None:
    generated = {
        "id": "g_parent",
        "name": "Generated Parent",
        "generatedData": {
            "runtimeProgram": {
                "apiVersion": "infini.runtime-program.v5",
                "schema": "infini.runtime-program.wire.v3",
                "itemEntityId": "item",
                "entities": [
                    {"id": "item", "kind": "item_body"},
                    {"id": "ornament", "kind": "free_projectile", "spawn": {"speedPxPerTick": 1}},
                    {"id": "actual", "kind": "free_projectile", "spawn": {"speedPxPerTick": 20}},
                ],
                "bindings": [{
                    "input": "primary_use",
                    "usePolicy": {
                        "action": {"kind": "spawn_entity", "targetId": "actual"},
                        "stackCost": 0,
                        "contactDamage": False,
                    },
                }],
            },
        },
    }
    card = raw_parent_card_for_llm(generated)
    assert "directProjectile" not in card["raw"]
    assert "effectiveProjectile" not in card["raw"]
    assert "semantics" not in card
    runtime = card["raw"]["generatedParent"]["runtimeProgram"]
    assert [row["id"] for row in runtime["entities"]] == ["item", "ornament", "actual"]
    assert runtime["bindings"][0]["usePolicy"]["action"]["targetId"] == "actual"


def test_all_non_archetypal_fixtures_compile_to_strict_wire() -> None:
    for name in (
        "workbench_blade", "umbrella_grenade", "door_on_chain", "returning_potion",
        "fishing_platform_tool", "shield_and_disc", "held_and_deployed", "equipment_tool_combat",
    ):
        authored = build_runtime_fixture(name)
        assert "runtimeContract" not in authored
        assert "backedByClaims" not in authored["realization"]
        assert validate_runtime_program(authored)["ok"], name
        compiled = compile_runtime_program(authored)
        assert set(compiled["runtimeContract"]) == {
            "compiledSchema", "runtimeApiVersion", "finalWireReceipts", "validation", "technicalLoweringAudit",
        }
        wire = validate_runtime_wire(compiled)
        assert "promiseParityWarnings" not in wire
        assert wire["ok"], (name, wire["errors"])
        encoded = json.dumps(compiled, ensure_ascii=False)
        assert "runtimeFamily" not in encoded
        assert "weaponFamily" not in encoded
        assert compiled["runtimeProgram"]["schema"] == "infini.runtime-program.wire.v3"
        assert "calls" not in compiled["runtimeProgram"]


def test_final_wire_accepts_runtime_entity_impact_visual_fields_declared_by_csharp() -> None:
    compiled = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    visual = compiled["runtimeProgram"]["entities"][0]["visual"]
    visual.update({
        "impactPrompt": "literal wooden impact",
        "impactNegativePrompt": "text, watermark",
        "impactSpritePath": "impact_wood.png",
        "impactSpriteUrl": "/get_asset?file=impact_wood.png",
        "impactSpriteStatus": "ready",
        "impactSpriteTechnicalScore": 0.93,
    })

    report = validate_runtime_wire(compiled)
    assert report["ok"], report["errors"]


def test_wrong_target_kind_duplicate_input_missing_reference_and_unknown_capability_fail_closed() -> None:
    wrong = build_runtime_fixture("workbench_blade")
    next(row for row in wrong["runtimeProgram"]["calls"] if row["id"] == "workbench_blade_motion")["target"] = "item"
    assert "wrong_target_kind" in _codes(validate_runtime_program(wrong))

    duplicate = build_runtime_fixture("workbench_blade")
    duplicate_binding = copy.deepcopy(duplicate["runtimeProgram"]["bindings"][0])
    duplicate_binding["id"] = "duplicate_primary"
    duplicate_binding["usePolicy"]["action"]["targetId"] = "nail"
    duplicate["runtimeProgram"]["bindings"].append(duplicate_binding)
    assert "duplicate_exclusive_input" in _codes(validate_runtime_program(duplicate))

    missing = build_runtime_fixture("workbench_blade")
    next(row for row in missing["runtimeProgram"]["bindings"] if row["id"] == "primary_workbench")["usePolicy"]["action"]["targetId"] = "absent"
    assert "missing_entity_reference" in _codes(validate_runtime_program(missing))

    unknown = build_runtime_fixture("workbench_blade")
    next(row for row in unknown["runtimeProgram"]["calls"] if row["id"] == "workbench_blade_motion")["fn"] = "unknown_runtime_magic"
    report = validate_runtime_program(unknown)
    assert report["ok"] is False
    assert any(code.startswith("shape_") or code == "unknown_capability" for code in _codes(report))


def test_event_cycles_child_budget_and_omitted_design_fields_are_rejected_not_repaired_in_code() -> None:
    cycle = build_runtime_fixture("workbench_blade")
    cycle["runtimeProgram"]["calls"].append({
        "id": "nail_returns_blade", "fn": "spawn_entity_on_event", "role": "secondary", "target": "nail",
        "params": {"event": "on_hit", "entity": "workbench_blade", "count": 1, "spreadRadians": 0.0, "damageMultiplier": 1.0, "delayTicks": 0},
    })
    assert "illegal_event_cycle" in _codes(validate_runtime_program(cycle))

    budget = build_runtime_fixture("workbench_blade")
    for index in range(3):
        budget["runtimeProgram"]["calls"].append({
            "id": f"extra_spawn_{index}", "fn": "spawn_entity_on_event", "role": "secondary", "target": "workbench_blade",
            "params": {"event": "on_hit", "entity": "nail", "count": 12, "spreadRadians": 0.0, "damageMultiplier": 0.2, "delayTicks": index},
        })
    assert "event_spawn_budget" in _codes(validate_runtime_program(budget))

    missing_motion = build_runtime_fixture("workbench_blade")
    missing_motion["runtimeProgram"]["calls"] = [row for row in missing_motion["runtimeProgram"]["calls"] if row["id"] != "workbench_blade_motion"]
    report = validate_runtime_program(missing_motion)
    assert "missing_movement_component" in _codes(report)
    assert all(row.get("fn") != "move_forward_then_retract" for row in missing_motion["runtimeProgram"]["calls"])


def test_technical_lowering_may_write_only_declared_paths() -> None:
    compiled = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    audit = compiled["runtimeContract"]["technicalLoweringAudit"]
    assert audit["ok"] is True
    fake = copy.deepcopy(compiled["runtimeContract"]["finalWireReceipts"])
    fake.append({
        "callId": "item_stats", "fn": "configure_item_stats",
        "authoredPath": "$.runtimeProgram.calls[0].params.damage",
        "finalPath": "runtimeProgram.entities[0].movement.code",
        "value": 7, "status": "technical_projection",
    })
    rejected = audit_compiler_receipts(fake)
    assert rejected["ok"] is False
    assert rejected["violations"]


def test_entity_kind_visual_role_and_sorted_event_receipts_remain_exact() -> None:
    authored = build_runtime_fixture("returning_potion")
    calls = authored["runtimeProgram"]["calls"]
    healer_index = next(index for index, row in enumerate(calls) if row["id"] == "tonic_heal")
    splash_index = next(index for index, row in enumerate(calls) if row["id"] == "tonic_splash")
    calls[healer_index], calls[splash_index] = calls[splash_index], calls[healer_index]

    compiled = compile_runtime_program(authored)
    assert validate_runtime_wire(compiled)["ok"] is True
    runtime = compiled["runtimeProgram"]
    visual_receipts = [
        row for row in compiled["runtimeContract"]["finalWireReceipts"]
        if row.get("lowererId") == "entity_kind_to_visual_role"
    ]
    assert len(visual_receipts) == len(runtime["entities"]) * 2
    assert audit_compiler_receipts(visual_receipts)["ok"] is True

    for receipt in compiled["runtimeContract"]["finalWireReceipts"]:
        path = str(receipt.get("finalPath") or "")
        if ".events[" not in path:
            continue
        entity_index = int(path.split("entities[")[1].split("]", 1)[0])
        event_index = int(path.split(".events[")[1].split("]", 1)[0])
        assert runtime["entities"][entity_index]["events"][event_index]["id"] == receipt["callId"]

    mismatched_role = copy.deepcopy(compiled)
    mismatched_role["runtimeProgram"]["entities"][0]["visualRole"] = "projectile"
    assert "visual_role_mismatch" in _codes(validate_runtime_wire(mismatched_role))
    missing_visual = copy.deepcopy(compiled)
    missing_visual["runtimeProgram"]["entities"][0].pop("visual")
    assert "required_object" in _codes(validate_runtime_wire(missing_visual))


def test_explicit_primary_entity_projects_to_wire_and_gates_csharp_item_and_held_ownership() -> None:
    item_primary = build_runtime_fixture("workbench_blade")
    assert validate_runtime_program(item_primary)["stats"]["primaryEntityId"] == "item"
    item_wire = compile_runtime_program(item_primary)
    assert item_wire["runtimeProgram"]["primaryEntityId"] == "item"
    assert item_wire["runtimeProgram"]["primaryOwner"] == "item_body"
    assert item_wire["runtimeProgram"]["bindings"][0]["role"] == "secondary"

    projectile_primary = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    assert projectile_primary["runtimeProgram"]["primaryEntityId"] == "chained_door"
    assert projectile_primary["runtimeProgram"]["primaryOwner"] == "projectile"
    assert projectile_primary["runtimeProgram"]["bindings"][0]["role"] == "primary"

    authored_receipts = item_wire["runtimeContract"]["finalWireReceipts"]
    binding_receipts = [
        row for row in authored_receipts
        if row.get("lowererId") == "primary_entity_to_binding_role"
    ]
    assert len(binding_receipts) == len(item_wire["runtimeProgram"]["bindings"])
    assert all(row["status"] == "technical_projection" for row in binding_receipts)
    assert audit_compiler_receipts(binding_receipts)["ok"] is True

    undeclared_input = copy.deepcopy(binding_receipts)
    undeclared_input[0]["authoredPaths"][0] = "runtimeProgram.entities[0].kind"
    assert audit_compiler_receipts(undeclared_input)["ok"] is False

    reordered = build_runtime_fixture("umbrella_grenade")
    reordered["runtimeProgram"]["bindings"].reverse()
    reordered_wire = compile_runtime_program(reordered)
    reordered_receipts = [
        row for row in reordered_wire["runtimeContract"]["finalWireReceipts"]
        if row.get("lowererId") == "primary_entity_to_binding_role"
    ]
    for receipt in reordered_receipts:
        target_path = receipt["authoredPaths"][1]
        source_index = int(target_path.split("[")[1].split("]")[0])
        final_index = int(receipt["finalPath"].split("[")[1].split("]")[0])
        source_binding = reordered["runtimeProgram"]["bindings"][source_index]
        wire_binding = reordered_wire["runtimeProgram"]["bindings"][final_index]
        expected_role = (
            "primary"
            if source_binding["usePolicy"]["action"]["targetId"] == reordered["runtimeProgram"]["primaryEntityId"]
            else "secondary"
        )
        assert wire_binding["id"] == source_binding["id"]
        assert receipt["value"] == wire_binding["role"] == expected_role

    stale_role = build_runtime_fixture("workbench_blade")
    stale_role["runtimeProgram"]["calls"][0]["role"] = "primary"
    assert "shape_additional_property" in _codes(validate_runtime_program(stale_role))

    tampered = copy.deepcopy(item_wire)
    tampered["runtimeProgram"]["primaryOwner"] = "projectile"
    assert "primary_owner_mismatch" in _codes(validate_runtime_wire(tampered))
    tampered = copy.deepcopy(item_wire)
    tampered["runtimeProgram"]["bindings"][0]["role"] = "primary"
    assert "binding_primary_role_mismatch" in _codes(validate_runtime_wire(tampered))

    mod = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal"
    apply_source = (mod / "Common" / "Models" / "GeneratedItemData.Apply.cs").read_text("utf-8")
    item_source = (mod / "Content" / "Items" / "GeneratedItem.cs").read_text("utf-8")
    projectile_source = (mod / "Content" / "Projectiles" / "GeneratedProjectile.cs").read_text("utf-8")
    executor_source = (mod / "Content" / "Projectiles" / "GeneratedProjectile.Executors.cs").read_text("utf-8")
    assert "RuntimeProgram.PrimaryOwner != RuntimeProgramSpec.ItemBodyOwner" in apply_source
    assert "BindingUsesItemBodyContact(binding)" in item_source
    assert "UsePolicy.ContactDamage" in item_source
    assert "_data?.RuntimeProgram.PrimaryOwner == RuntimeProgramSpec.ProjectileOwner" in projectile_source
    assert "PrimaryEntityId" in projectile_source
    assert "owner.heldProj = Projectile.whoAmI;" in projectile_source
    assert "owner.heldProj = Projectile.whoAmI;" not in executor_source


def test_body_contact_and_projectile_are_independent_lanes_without_held_owner_inference() -> None:
    star_sword = build_runtime_fixture("workbench_blade")
    star_binding = star_sword["runtimeProgram"]["bindings"][0]
    assert star_binding["usePolicy"]["action"]["kind"] == "spawn_entity"
    star_binding["usePolicy"]["contactDamage"] = True

    report = validate_runtime_program(star_sword)
    assert report["ok"], report
    star_wire = compile_runtime_program(star_sword)
    runtime = star_wire["runtimeProgram"]
    assert runtime["primaryEntityId"] == runtime["itemEntityId"] == "item"
    assert runtime["primaryOwner"] == "item_body"
    assert runtime["bindings"][0]["role"] == "secondary"
    assert runtime["bindings"][0]["usePolicy"] == {
        "action": {"kind": "spawn_entity", "targetId": "workbench_blade"},
        "stackCost": 0,
        "contactDamage": True,
    }

    tool_with_shard = copy.deepcopy(star_sword)
    tool_with_shard["runtimeProgram"]["calls"].append({
        "id": "tool_heads",
        "fn": "configure_tool",
        "target": "item",
        "params": {
            "pickPower": 35,
            "axePowerTooltipPercent": 0,
            "hammerPower": 20,
            "miningSpeedScale": 0.9,
        },
    })
    tool_report = validate_runtime_program(tool_with_shard)
    assert tool_report["ok"], tool_report

    flail_wire = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    flail_binding = flail_wire["runtimeProgram"]["bindings"][0]
    assert flail_wire["runtimeProgram"]["primaryOwner"] == "projectile"
    assert flail_binding["usePolicy"]["contactDamage"] is False
    assert flail_binding["role"] == "primary"

    mod = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal"
    item_source = (mod / "Content" / "Items" / "GeneratedItem.cs").read_text("utf-8")
    contact_method = item_source.split("private bool BindingUsesItemBodyContact", 1)[1].split(
        "private bool BaseNoMeleeFor", 1
    )[0]
    assert "UsePolicy.ContactDamage == true" in contact_method
    assert "Action.Kind" not in contact_method
    assert "TargetId" not in contact_method

    runtime_spec = (mod / "Common" / "Models" / "RuntimeProgramSpec.cs").read_text("utf-8")
    assert "contactDamage=true requires use_item_body" not in runtime_spec

    invalid_place = build_runtime_fixture("fishing_platform_tool")
    invalid_place["runtimeProgram"]["bindings"][1]["usePolicy"]["contactDamage"] = True
    assert not validate_runtime_program(invalid_place)["ok"]

    invalid_hold = copy.deepcopy(star_sword)
    invalid_hold["runtimeProgram"]["bindings"][0]["input"] = "hold"
    assert not validate_runtime_program(invalid_hold)["ok"]


def test_active_equipment_keeps_authored_use_projection_in_csharp_defaults() -> None:
    mod = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal"
    apply_source = (mod / "Common" / "Models" / "GeneratedItemData.Apply.cs").read_text("utf-8")
    assert "bool hasActiveUse = primary is not null || alternate is not null;" in apply_source
    assert apply_source.count("if (!hasActiveUse)") == 2
    assert apply_source.count("item.maxStack = 1;") >= 2
    assert "Gameplay.Category" not in apply_source


def test_hidden_item_body_without_contact_requires_exact_spawn_target_ownership() -> None:
    hidden_projectile_form = build_runtime_fixture("door_on_chain")
    program = hidden_projectile_form["runtimeProgram"]
    item_id = next(row["id"] for row in program["entities"] if row["kind"] == "item_body")
    spawn_target = program["bindings"][0]["usePolicy"]["action"]["targetId"]
    item_use = next(
        row for row in program["calls"]
        if row["fn"] == "configure_item_use" and row["target"] == item_id
    )
    item_use["params"]["hideUseGraphic"] = True
    program["primaryEntityId"] = item_id

    report = validate_runtime_program(hidden_projectile_form)
    error = next(
        row for row in report["errors"]
        if row["code"] == "hidden_item_primary_requires_spawn_target"
    )
    assert error["path"] == "$.runtimeProgram.primaryEntityId"
    assert error["allowed"] == [spawn_target]

    scope = build_runtime_repair_scope(hidden_projectile_form, [error])
    transaction = scope["repairTransactions"]["primaryEntitySelection"]
    assert transaction["candidateEntityIds"] == [spawn_target]
    assert transaction["mustSelectExactlyOne"] is True

    program["primaryEntityId"] = spawn_target
    assert validate_runtime_program(hidden_projectile_form)["ok"]


def test_active_source_has_no_old_compiler_or_parallel_schema() -> None:
    root = Path(__file__).resolve().parents[1] / "infini_local"
    forbidden_files = {
        "root_lowering.py", "function_contract_registry.py", "combine_genome.py",
        "runtime_authored_composition.py", "presentation_sound.py",
    }
    assert not any(path.name in forbidden_files for path in root.rglob("*.py"))
    active = "\n".join(
        path.read_text("utf-8", errors="ignore")
        for path in (
            root / "pipelines" / "combine_pipeline.py",
            root / "pipelines" / "combine_gameplay.py",
            root / "pipelines" / "llm_authoring_prompt.py",
            root / "core" / "runtime_authoring" / "compiler.py",
        )
    )
    for token in ("perform_melee_attack", "fire_ranged_weapon", "cast_magic_weapon", "deploy_sentry"):
        assert token not in active


def test_delayed_item_events_have_a_bounded_runtime_consumer_and_keep_activation_budget() -> None:
    mod = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal"
    item_source = (mod / "Content" / "Items" / "GeneratedItem.cs").read_text("utf-8")
    projectile_source = (
        mod / "Content" / "Projectiles" / "GeneratedProjectile.RuntimeEvents.cs"
    ).read_text("utf-8")
    limits_source = (mod / "Common" / "InfiniRuntimeLimits.cs").read_text("utf-8")
    executor_source = (
        mod / "Common" / "Runtime" / "RuntimeProgramExecutor.cs"
    ).read_text("utf-8")
    scheduler_source = (
        mod / "Common" / "Runtime" / "RuntimeDelayedActionScheduler.cs"
    ).read_text("utf-8")

    run_item_event = item_source.split("private void RunItemEvent", 1)[1].split(
        "private void QueueOrExecuteItemAction", 1
    )[0]
    queue_method = item_source.split("private void QueueOrExecuteItemAction", 1)[1].split(
        "public override bool Shoot", 1
    )[0]

    assert "action.DelayTicks > 0" in queue_method
    assert "RuntimeDelayedActionScheduler.TrySchedule" in queue_method
    assert "_pendingItemActions" not in item_source
    assert "_pendingActions" not in projectile_source
    assert "RuntimeDelayedActionScheduler.TrySchedule" in projectile_source
    assert "RuntimeProgramExecutor.ExecuteAction" in scheduler_source
    assert "PostUpdateEverything" in scheduler_source
    assert "reservedSpawnBudget = budget.Reserve(action.Count)" in scheduler_source
    assert "pending.Budget.Return(pending.ReservedSpawnBudget)" in scheduler_source
    assert "new ItemEventBudgetState" not in run_item_event
    assert "MaxPendingRuntimeActions = 256" in limits_source
    assert "MaxRuntimeDelayedActionsPerTick = 64" in limits_source
    assert "InfiniRuntimeLimits.MaxPendingRuntimeActions" in scheduler_source
    assert "InfiniRuntimeLimits.MaxRuntimeDelayedActionsPerTick" in scheduler_source
    assert "for (int i = 0; i < Pending.Count;)" in scheduler_source
    assert "for (int i = Pending.Count - 1" not in scheduler_source
    assert "Pending[i] = pending with { Ticks = 1 }" in scheduler_source
    assert "includeDelayed" not in executor_source


def test_csharp_runtime_preserves_authored_tick_units_and_enforces_spawn_chokepoint_limits() -> None:
    mod = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal"
    projectile = (mod / "Content" / "Projectiles" / "GeneratedProjectile.cs").read_text("utf-8")
    executors = (
        mod / "Content" / "Projectiles" / "GeneratedProjectile.Executors.cs"
    ).read_text("utf-8")
    events = (
        mod / "Content" / "Projectiles" / "GeneratedProjectile.RuntimeEvents.cs"
    ).read_text("utf-8")
    vfx = (mod / "Common" / "VFX" / "InfiniVfxRuntime.cs").read_text("utf-8")

    assert "AuthoredTicksToProjectileUpdates" in projectile
    assert "AuthoredTicksToProjectileUpdates(entity.LifetimeTicks)" in projectile
    for temporal_use in (
        "AuthoredTicksToProjectileUpdates(_entity!.Controller.Params.WarmupTicks)",
        "AuthoredTicksToProjectileUpdates(p.ChargeTicks)",
        "AuthoredTicksToProjectileUpdates(returnAfterTicks)",
        "AuthoredTicksToProjectileUpdates(p.DurationTicks)",
    ):
        assert temporal_use in executors
    assert "AuthoredTicksToProjectileUpdates(Math.Max(6, action.PeriodTicks))" in events
    assert "state.LastGameUpdate == Main.GameUpdateCount" in vfx
    assert "record struct InfiniVfxSlotEmissionKey" in vfx
    assert "string SlotId" in vfx
    assert "new InfiniVfxSlotEmissionKey(projectile.identity, entityId, eventName, slot.Id)" in vfx
    on_event = vfx.split(" OnEvent(", 1)[1].split(
        "private static void BeginWorldTick", 1
    )[0]
    assert "foreach (VfxSlotSpec slot in manifest.Slots)" in on_event
    assert "TryMarkSlotEmission(projectile, entityId, eventName, slot" in on_event
    assert "EmitSlot(data, entityId, center, projectile.velocity, slot" in on_event
    run_event = events.split("private void RunRuntimeEvent", 1)[1].split(
        "private void RunPeriodicActions", 1
    )[0]
    assert "foreach (RuntimeEventActionSpec action" in run_event
    assert "RuntimeProgramExecutor.ExecuteAction" in run_event

    spawn = projectile.split("internal static int SpawnRuntimeEntity", 1)[1].split(
        "private static int CountActiveGeneratedProjectiles", 1
    )[0]
    assert "remainingSpawnBudget <= 0" in spawn
    assert "MaxRuntimeActiveProjectilesPerOwner" in spawn
    assert "CountActiveGeneratedProjectiles(owner.whoAmI)" in spawn
