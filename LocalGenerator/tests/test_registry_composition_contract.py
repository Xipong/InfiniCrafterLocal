"""Authored composition ownership, non-archetypal runtime programs and engine seams."""

from __future__ import annotations
import copy
from copy import deepcopy
import json
import pytest
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.pipelines.generated_parent_summary import generated_parent_summary_from_data
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
from infini_local.pipelines.parent_context_pipeline import projectile_profile_of, effective_projectile_profile_of
from infini_local.pipelines.llm_authoring_prompt import build_llm_author_payload
from infini_local.qa.runtime_program_fixtures import NON_ARCHETYPAL_FIXTURES, build_runtime_fixture
from infini_local.storage.world_storage import sanitize_recipe_for_delivery


def _codes(report):
    return {str(e.get("code")) for e in report.get("errors") or []}


def test_generated_parent_retains_complete_graph_instead_of_fabricating_primary_projectile() -> None:
    generated = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    parent = {"name": generated["name"], "generatedData": generated,
              "directProjectileRaw": {"type": 1}, "effectiveProjectileRaw": {"type": 2}}
    before = copy.deepcopy(parent)
    assert projectile_profile_of(parent) == effective_projectile_profile_of(parent) == {}
    card = raw_parent_card_for_llm(parent)
    expected = copy.deepcopy(generated["runtimeProgram"])
    for entity in expected["entities"]:
        entity.pop("visual", None)
    assert card["raw"]["generatedParent"]["runtimeProgram"] == expected
    assert "directProjectile" not in card["raw"] and "effectiveProjectile" not in card["raw"]
    assert parent == before


def test_generated_parent_summary_uses_late_report_and_behavior_checks() -> None:
    authored = build_runtime_fixture("workbench_blade")
    authored["id"] = "generated_summary_fixture"
    authored["concept"]["coreMechanic"] = "EARLY CONCEPT MUST NOT LEAK"
    authored["realization"].update(
        {
            "description": "Late accepted blade realization.",
            "playerExperience": "Late accepted player experience.",
        }
    )
    authored["realization"]["selfEvaluation"] = {"programVsReport": {
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
    }}
    summary = generated_parent_summary_from_data(authored)
    assert summary["identity"] == "generated:generated_summary_fixture"
    assert summary["description"] == "Late accepted blade realization."
    assert summary["playerExperience"] == "Late accepted player experience."
    assert "EARLY CONCEPT MUST NOT LEAK" not in json.dumps(summary)
    assert "notableEffects" not in summary
    assert "runtimePrimaryEntityId" not in summary and "runtimeEntityIds" not in summary
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
    assert "notableEffects" not in recursive_summary
    assert recursive_summary["schema"] == "infini.generated-parent-summary.v2"
    assert recursive_summary["identity"] == summary["identity"]
    assert "fantasy" not in recursive_summary


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
    payload = build_llm_author_payload(generated_parent, parent, "facts-only")
    encoded_parents = json.dumps(payload["parents"], ensure_ascii=False).casefold()
    assert "canonical" not in encoded_parents
    assert "headnoun" not in encoded_parents
    assert '"tags"' not in encoded_parents
    assert "primarycategory" not in encoded_parents
    corridor = payload["balanceCorridor"]
    assert corridor["authority"] == "source_numeric_facts_only"
    assert corridor["parentProgressionFacts"] == [
        {
            "parent": "A",
            "path": "generatedData.recipeMeta.generationDepth",
            "value": 9,
        }
    ]
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
    ammo_payload = build_llm_author_payload(ammo_parent, parent, "nested-ammo-facts-only")
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
                "bindings": [
                    {
                        "input": "primary_use",
                        "usePolicy": {
                            "action": {"kind": "spawn_entity", "targetId": "actual"},
                            "stackCost": 0,
                            "contactDamage": False,
                        },
                    }
                ],
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


def test_concept_drift_and_report_mismatch_are_diagnostic_not_rejection() -> None:
    authored = build_runtime_fixture("workbench_blade")
    authored["concept"]["plannedPlayerActions"] = [
        {
            "input": "primary_use",
            "intent": "Teleport the player, although the executable draft later chooses a melee swing.",
        }
    ]
    authored["realization"]["selfEvaluation"] = {
        "planVsProgram": {
            "verdict": "changed",
            "summary": "The initial teleport sketch became a melee swing.",
            "actionChecks": [
                {
                    "plannedIntent": "Teleport on primary use.",
                    "implementedBehavior": "Primary use swings the item body.",
                    "runtimeRefs": ["primary_workbench"],
                    "result": "changed",
                    "intentionality": "intentional",
                    "reason": "The executable program selected the supported melee composition.",
                }
            ],
        },
        "programVsReport": {
            "verdict": "mismatch",
            "summary": "The report intentionally demonstrates a detectable mismatch.",
            "behaviorChecks": [
                {
                    "runtimeRefs": ["primary_workbench"],
                    "programBehavior": "Primary use swings the item body.",
                    "reportedBehavior": "Primary use teleports the player.",
                    "result": "mismatch",
                    "reason": "Diagnostic mismatch; it is not a semantic craft gate.",
                }
            ],
        },
    }
    report = validate_runtime_program(authored)
    assert report["ok"] is True, report


def test_planned_player_actions_are_requested_but_never_a_craft_gate() -> None:
    authored = build_runtime_fixture("workbench_blade")
    authored["concept"].pop("plannedPlayerActions")
    report = validate_runtime_program(authored)
    assert report["ok"] is True, report


def test_final_wire_accepts_runtime_entity_impact_visual_fields_declared_by_csharp() -> None:
    compiled = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    visual = compiled["runtimeProgram"]["entities"][0]["visual"]
    visual.update(
        {
            "impactPrompt": "literal wooden impact",
            "impactNegativePrompt": "text, watermark",
            "impactSpritePath": "impact_wood.png",
            "impactSpriteUrl": "/get_asset?file=impact_wood.png",
            "impactSpriteStatus": "ready",
            "impactSpriteTechnicalScore": 0.93,
        }
    )

    report = validate_runtime_wire(compiled)
    assert report["ok"], report["errors"]


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
        row for row in compiled["runtimeContract"]["finalWireReceipts"] if row.get("lowererId") == "entity_kind_to_visual_role"
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


def test_hidden_item_body_without_contact_requires_exact_spawn_target_ownership() -> None:
    hidden_projectile_form = build_runtime_fixture("door_on_chain")
    program = hidden_projectile_form["runtimeProgram"]
    item_id = next(row["id"] for row in program["entities"] if row["kind"] == "item_body")
    spawn_target = program["bindings"][0]["action"]["targetId"]
    item_use = next(row for row in program["calls"] if row["fn"] == "configure_item_use")
    item_use["params"]["hideUseGraphic"] = True
    program["primaryEntityId"] = item_id

    report = validate_runtime_program(hidden_projectile_form)
    error = next(row for row in report["errors"] if row["code"] == "hidden_item_primary_requires_spawn_target")
    assert error["path"] == "$.runtimeProgram.primaryEntityId"
    assert error["allowed"] == [spawn_target]

    scope = build_runtime_repair_scope(hidden_projectile_form, [error])
    transaction = scope["repairTransactions"]["primaryEntitySelection"]
    assert transaction["candidateEntityIds"] == [spawn_target]
    assert transaction["mustSelectExactlyOne"] is True

    program["primaryEntityId"] = spawn_target
    assert validate_runtime_program(hidden_projectile_form)["ok"]


@pytest.mark.parametrize(
    "mutation,code",
    [
        pytest.param("target-kind", "wrong_target_kind", id="movement-on-item"),
        pytest.param("exclusive-input", "duplicate_exclusive_input", id="distinct-ids-same-primary-input"),
        pytest.param("missing-reference", "missing_entity_reference", id="absent-binding-target"),
        pytest.param("unknown-capability", None, id="unknown-capability"),
        pytest.param("cycle", "illegal_event_cycle", id="child-returns-to-root"),
        pytest.param("spawn-budget", "event_spawn_budget", id="aggregate-child-budget"),
        pytest.param("missing-movement", "missing_movement_component", id="no-guessed-movement"),
    ],
)
def test_invalid_composition_is_rejected_without_synthesis(mutation, code):
    doc = build_runtime_fixture("workbench_blade")
    program = doc["runtimeProgram"]
    calls = program["calls"]
    motion = next(c for c in calls if c["id"] == "workbench_blade_motion")
    if mutation == "target-kind":
        motion["target"] = "item"
    elif mutation == "exclusive-input":
        binding = deepcopy(program["bindings"][0])
        binding["id"] = "duplicate_primary"
        binding["action"]["targetId"] = "nail"
        program["bindings"].append(binding)
    elif mutation == "missing-reference":
        program["bindings"][0]["action"]["targetId"] = "absent"
    elif mutation == "unknown-capability":
        motion["fn"] = "unknown_runtime_magic"
    elif mutation in {"cycle", "spawn-budget"}:
        calls.extend(
            {
                "id": "nail_returns_blade" if mutation == "cycle" else f"extra_spawn_{i}",
                "fn": "spawn_entity_on_event",
                "role": "secondary",
                "target": "nail" if mutation == "cycle" else "workbench_blade",
                "params": {
                    "when": "on_hit",
                    "entity": "workbench_blade" if mutation == "cycle" else "nail",
                    "count": 1 if mutation == "cycle" else 12,
                    "spreadRadians": 0.0,
                    "damageMultiplier": 1.0 if mutation == "cycle" else 0.2,
                    'delaySeconds': (i) / 60,
                 "damageBasis": "authored_child", "knockbackBasis": "authored_child"},
            }
            for i in range(1 if mutation == "cycle" else 3)
        )
    else:
        program["calls"].remove(motion)
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert not report["ok"] and doc == before
    if code:
        assert code in _codes(report)
    else:
        assert any(c.startswith("shape_") or c == "unknown_capability" for c in _codes(report))
    if mutation == "missing-movement":
        assert all(c.get("fn") != "move_forward_then_retract" for c in program["calls"])


@pytest.mark.parametrize(
    "fixture,primary,owner,role",
    [
        pytest.param("workbench_blade", "item", "item_body", "secondary", id="item-body"),
        pytest.param("door_on_chain", "chained_door", "projectile", "primary", id="projectile"),
    ],
)
def test_primary_owner_and_binding_role_are_exact_receipted_projection(fixture, primary, owner, role):
    doc = build_runtime_fixture(fixture)
    assert validate_runtime_program(doc)["stats"]["primaryEntityId"] == primary
    wire = compile_runtime_program(doc)
    program = wire["runtimeProgram"]
    assert (program["primaryEntityId"], program["primaryOwner"], program["bindings"][0]["role"]) == (primary, owner, role)
    rows = [r for r in wire["runtimeContract"]["finalWireReceipts"] if r.get("lowererId") == "primary_entity_to_binding_role"]
    assert len(rows) == len(program["bindings"])
    assert all(r["status"] == "technical_projection" for r in rows) and audit_compiler_receipts(rows)["ok"] is True
    rows[0]["authoredPaths"][0] = "runtimeProgram.entities[0].kind"
    assert audit_compiler_receipts(rows)["ok"] is False
    stale = deepcopy(doc)
    stale["runtimeProgram"]["calls"][0]["role"] = "primary"
    assert "shape_additional_property" in _codes(validate_runtime_program(stale))
    for path, value, code in (
        ("primaryOwner", "projectile" if owner == "item_body" else "item_body", "primary_owner_mismatch"),
        ("role", "primary" if role == "secondary" else "secondary", "binding_primary_role_mismatch"),
    ):
        bad = deepcopy(wire)
        (bad["runtimeProgram"] if path == "primaryOwner" else bad["runtimeProgram"]["bindings"][0])[path] = value
        assert code in _codes(validate_runtime_wire(bad))


def test_item_contact_and_spawn_lane_do_not_infer_held_ownership():
    doc = build_runtime_fixture("workbench_blade")
    binding = doc["runtimeProgram"]["bindings"][0]
    assert binding["action"]["kind"] == "spawn_entity"
    binding["contactDamage"] = True
    wire = compile_runtime_program(doc)
    program = wire["runtimeProgram"]
    assert program["primaryEntityId"] == program["itemEntityId"] == "item" and program["primaryOwner"] == "item_body"
    assert program["bindings"][0]["role"] == "secondary"
    assert program["bindings"][0]["usePolicy"] == {
        "action": {"kind": "spawn_entity", "targetId": "workbench_blade"},
        "stackCost": 0,
        "contactDamage": True,
    }
    tool = deepcopy(doc)
    tool["runtimeProgram"]["calls"].append(
        {
            "id": "tool_heads",
            "fn": "configure_tool",
            "params": {"pickPower": 35, "axePowerTooltipPercent": 0, "hammerPower": 20, "miningSpeedMultiplier": 0.9},
        }
    )
    assert validate_runtime_program(tool)["ok"]
    flail = compile_runtime_program(build_runtime_fixture("door_on_chain"))["runtimeProgram"]
    assert (
        flail["primaryOwner"] == "projectile"
        and flail["bindings"][0]["role"] == "primary"
        and flail["bindings"][0]["usePolicy"]["contactDamage"] is False
    )
    place = build_runtime_fixture("fishing_platform_tool")
    place["runtimeProgram"]["bindings"][1]["contactDamage"] = True
    assert not validate_runtime_program(place)["ok"]
    binding["input"] = "hold"
    assert not validate_runtime_program(doc)["ok"]
