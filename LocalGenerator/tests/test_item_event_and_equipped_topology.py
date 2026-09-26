from __future__ import annotations

import copy

import pytest

from infini_local.core.runtime_authoring import (
    compile_runtime_program,
    runtime_event_inventory,
    validate_runtime_program,
    validate_runtime_wire,
)
from infini_local.core.runtime_authoring.capability_registry import (
    EVENT_KIND_REGISTRY,
    INPUT_KIND_REGISTRY,
    event_dependency_alternatives,
)
from infini_local.core.runtime_authoring.program_schema import strict_author_shape_report
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring import apply_repair_patch, filter_repair_patch_scope
from infini_local.pipelines.llm_authoring_pipeline import build_gameplay_repair_dossier
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.qa.capability_witnesses import build_capability_witness


def _body_event(document: dict, event: str) -> None:
    document["runtimeProgram"]["calls"].append({
        "id": "body_status", "fn": "apply_status_on_event", "target": "item",
        "params": {"event": event, "buffId": 20, "durationTicks": 60},
    })


def test_spawn_target_item_contact_event_is_valid_and_compiles() -> None:
    authored = build_runtime_fixture("workbench_blade")
    _body_event(authored, "on_hit")
    assert strict_author_shape_report(authored)["ok"]
    report = validate_runtime_program(authored)
    assert report["ok"], report["errors"]
    compiled = compile_runtime_program(authored)
    assert validate_runtime_wire(compiled)["ok"]
    assert any(e["entityId"] == "item" and e["event"] == "on_hit" for e in runtime_event_inventory(compiled))
    assert any(e["event"] == "on_hit" for e in next(x for x in compiled["runtimeProgram"]["entities"] if x["id"] == "item")["events"])


def test_spawn_binding_emits_item_body_on_use_even_with_projectile_target() -> None:
    authored = build_runtime_fixture("workbench_blade")
    authored["runtimeProgram"]["calls"].append({
        "id": "body_use_child", "fn": "spawn_entity_on_event", "target": "item",
        "params": {"event": "on_use", "entity": "nail", "count": 1,
                   "spreadRadians": 0.0, "damageMultiplier": 1.0, "delayTicks": 0},
    })
    assert strict_author_shape_report(authored)["ok"]
    assert validate_runtime_program(authored)["ok"]
    compiled = compile_runtime_program(authored)
    assert validate_runtime_wire(compiled)["ok"]
    assert any(e["event"] == "on_use" for e in next(x for x in compiled["runtimeProgram"]["entities"] if x["id"] == "item")["events"])


def test_apply_item_effects_emits_item_use_without_contact() -> None:
    authored = build_capability_witness("restore_resources_on_use")
    assert validate_runtime_program(authored)["ok"]
    compiled = compile_runtime_program(authored)
    assert ("item", "on_use") in {(row["entityId"], row["event"]) for row in runtime_event_inventory(compiled)}


def test_apply_item_effects_contact_has_same_body_event_producer() -> None:
    authored = build_capability_witness("restore_resources_on_use")
    authored["runtimeProgram"]["bindings"][0]["usePolicy"]["contactDamage"] = True
    next(c for c in authored["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"]["disableMeleeHitbox"] = False
    _body_event(authored, "on_crit")
    assert strict_author_shape_report(authored)["ok"]
    report = validate_runtime_program(authored)
    assert report["ok"], report["errors"]
    compiled = compile_runtime_program(authored)
    assert validate_runtime_wire(compiled)["ok"]
    assert ("item", "on_crit") in {(e["entityId"], e["event"]) for e in runtime_event_inventory(compiled)}


def test_disabled_contact_does_not_claim_body_hit_producer() -> None:
    authored = build_runtime_fixture("workbench_blade")
    authored["runtimeProgram"]["bindings"][0]["usePolicy"]["contactDamage"] = False
    _body_event(authored, "on_hit")
    assert "event_not_emitted" in {e["code"] for e in validate_runtime_program(authored)["errors"]}


def test_disabled_melee_hitbox_cannot_produce_body_contact_event() -> None:
    authored = build_runtime_fixture("workbench_blade")
    next(c for c in authored["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"]["disableMeleeHitbox"] = True
    _body_event(authored, "on_hit")
    assert "event_not_emitted" in {e["code"] for e in validate_runtime_program(authored)["errors"]}
    compiled_without_event = copy.deepcopy(authored)
    compiled_without_event["runtimeProgram"]["calls"].pop()
    compiled = compile_runtime_program(compiled_without_event)
    assert ("item", "on_hit") not in {(e["entityId"], e["event"]) for e in runtime_event_inventory(compiled)}


def test_contact_producer_alternatives_include_actual_item_effects_root() -> None:
    for event in ("on_hit", "on_crit"):
        spec = EVENT_KIND_REGISTRY[event]
        alternatives = event_dependency_alternatives(event, "item_body")
        assert spec.producer_binding_actions == (
            "spawn_entity", "use_item_body", "apply_item_effects"
        )
        assert len(alternatives) == 1
        assert alternatives[0].required_bindings[0].any_of_actions == spec.producer_binding_actions
        assert alternatives[0].required_bindings[0].required_contact_damage is True


def test_repair_can_offer_contact_on_item_effects_root_without_replacing_it() -> None:
    authored = build_capability_witness("restore_resources_on_use")
    next(call for call in authored["runtimeProgram"]["calls"] if call["fn"] == "configure_item_use")["params"]["disableMeleeHitbox"] = False
    _body_event(authored, "on_hit")
    errors = validate_runtime_program(authored)["errors"]
    assert "event_not_emitted" in {row["code"] for row in errors}
    scope = build_runtime_repair_scope(authored, errors)
    alternatives = next(row for row in scope["eventAlternatives"] if row["callId"] == "body_status")
    assert any("apply_item_effects" in binding["anyOfActions"] and binding["requiredContactDamage"] is True
               for option in alternatives["allowed"] for binding in option["requiredBindings"])
    assert any(row["id"] == authored["runtimeProgram"]["bindings"][0]["id"] and "usePolicy" in row["paths"]
               for row in scope["fieldPermissions"]["bindings"])
    repaired = copy.deepcopy(authored)
    repaired["runtimeProgram"]["bindings"][0]["usePolicy"]["contactDamage"] = True
    assert validate_runtime_program(repaired)["ok"]
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]

def test_spawn_item_hit_repair_names_projectile_action_target_not_event_source() -> None:
    authored = build_runtime_fixture("workbench_blade")
    binding = authored["runtimeProgram"]["bindings"][0]
    binding["usePolicy"]["contactDamage"] = False
    _body_event(authored, "on_hit")
    report = validate_runtime_program(authored)
    assert [row["code"] for row in report["errors"]] == ["event_not_emitted"]
    dossier = build_gameplay_repair_dossier(authored, {}, {}, {}, {}, failure_report=report)
    scope = dossier["repairScope"]
    alternative = next(row for row in scope["eventAlternatives"] if row["callId"] == "body_status")
    assert alternative["targetId"] == "item"
    assert any(b["targetId"] == "workbench_blade" and "spawn_entity" in b["anyOfActions"]
               for option in alternative["allowed"] for b in option["requiredBindings"])
    assert not any(b["targetId"] == "item" and "spawn_entity" in b["anyOfActions"]
                   for option in alternative["allowed"] for b in option["requiredBindings"])
    update = next(row for row in scope["repairRequirements"] if row["code"] == "event_not_emitted")
    assert binding["id"] in update["allowedExistingBindingIds"]
    fixed = copy.deepcopy(binding)
    fixed["usePolicy"]["contactDamage"] = True
    patch = {"note": "repair contact on existing spawn binding", "bindingsUpsert": [fixed]}
    filtered, audit = filter_repair_patch_scope(authored, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(authored, filtered)
    assert validate_runtime_program(repaired)["ok"]
    compiled = compile_runtime_program(repaired)
    assert validate_runtime_wire(compiled)["ok"]
    assert ("item", "on_hit") in {(e["entityId"], e["event"]) for e in runtime_event_inventory(compiled)}


@pytest.mark.parametrize("suppressor", ["hitbox", "ammo"])
def test_frozen_contact_suppression_repair_never_offers_unexecutable_contact(suppressor: str) -> None:
    authored = build_runtime_fixture("workbench_blade")
    if suppressor == "hitbox":
        next(c for c in authored["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"]["disableMeleeHitbox"] = True
    else:
        # Ammo is a distinct, frozen engine suppression of item contact.
        authored = build_capability_witness("configure_vanilla_ammo_item")
        next(c for c in authored["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"]["disableMeleeHitbox"] = False
    _body_event(authored, "on_hit")
    report = validate_runtime_program(authored)
    assert "event_not_emitted" in {row["code"] for row in report["errors"]}
    dossier = build_gameplay_repair_dossier(authored, {}, {}, {}, {}, failure_report=report)
    scope = dossier["repairScope"]
    assert not any(row["callId"] == "body_status" for row in scope["eventAlternatives"])
    assert "body_status" in scope["deletable"]["callIds"]
    assert not next(row for row in scope["repairRequirements"] if row["code"] == "event_not_emitted")["allowedValues"]
    assert not any(row["usePolicy"]["contactDamage"] is True
                   for row in scope["create"]["bindings"]["allowedTransactions"])
    filtered, audit = filter_repair_patch_scope(authored, {"note": "drop impossible event call", "callIdsDelete": ["body_status"]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(authored, filtered)
    assert validate_runtime_program(repaired)["ok"]
    wire = compile_runtime_program(repaired)
    assert validate_runtime_wire(wire)["ok"]


def test_incompatible_event_projection_respects_frozen_contact_and_action_target() -> None:
    authored = build_runtime_fixture("workbench_blade")
    next(c for c in authored["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"]["disableMeleeHitbox"] = True
    authored["runtimeProgram"]["calls"].append({
        "id": "body_child", "fn": "spawn_entity_on_event", "target": "item",
        "params": {"event": "on_use", "entity": "nail", "count": 1,
                   "spreadRadians": 0.0, "damageMultiplier": 1.0, "delayTicks": 0},
    })
    index = len(authored["runtimeProgram"]["calls"]) - 1
    scope = build_runtime_repair_scope(authored, [{
        "path": f"$.runtimeProgram.calls[{index}].params.event",
        "code": "capability_event_incompatible", "allowed": ["on_use", "on_hit", "on_crit"],
        "relatedIds": ["item"], "message": "synthetic incompatible event selection",
    }])
    alternatives = next(row for row in scope["eventAlternatives"] if row["callId"] == "body_child")
    assert all(option["event"] not in {"on_hit", "on_crit"} for option in alternatives["allowed"])
    assert any(option["event"] == "on_use" and any(
        b["targetId"] == "workbench_blade" and "spawn_entity" in b["anyOfActions"]
        for b in option["requiredBindings"]
    ) for option in alternatives["allowed"])


def test_incompatible_event_with_no_executable_event_can_remove_only_invalid_call() -> None:
    authored = build_runtime_fixture("workbench_blade")
    next(c for c in authored["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"]["disableMeleeHitbox"] = True
    _body_event(authored, "on_hit")
    broken = next(c for c in authored["runtimeProgram"]["calls"] if c["id"] == "body_status")
    broken["params"]["event"] = "on_use"
    report = validate_runtime_program(authored)
    assert "capability_event_incompatible" in {row["code"] for row in report["errors"]}
    scope = build_runtime_repair_scope(authored, report["errors"])
    assert not any(row["callId"] == "body_status" for row in scope["eventAlternatives"])
    assert "body_status" in scope["deletable"]["callIds"]
    filtered, audit = filter_repair_patch_scope(authored, {
        "note": "remove invalid event call", "callIdsDelete": ["body_status"],
    }, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(authored, filtered)
    assert validate_runtime_program(repaired)["ok"]
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]


def test_incompatible_event_repair_can_update_existing_contact_without_changing_target() -> None:
    authored = build_runtime_fixture("workbench_blade")
    binding = authored["runtimeProgram"]["bindings"][0]
    binding["usePolicy"]["action"] = {"kind": "use_item_body", "targetId": "item"}
    binding["usePolicy"]["contactDamage"] = False
    authored["runtimeProgram"]["calls"].append({
        "id": "body_child", "fn": "spawn_entity_on_event", "target": "item",
        "params": {"event": "on_use", "entity": "nail", "count": 1,
                   "spreadRadians": 0.0, "damageMultiplier": 1.0, "delayTicks": 0},
    })
    index = len(authored["runtimeProgram"]["calls"]) - 1
    scope = build_runtime_repair_scope(authored, [{
        "path": f"$.runtimeProgram.calls[{index}].params.event",
        "code": "capability_event_incompatible", "allowed": ["on_hit"],
        "relatedIds": ["item"], "message": "synthetic event choice",
    }])
    allowed = next(row for row in scope["bindingAlternatives"] if row["bindingId"] == binding["id"])["allowed"]
    assert any(row["usePolicy"]["contactDamage"] is True
               and row["usePolicy"]["action"]["targetId"] == "item" for row in allowed)
    # Occupy the other exclusive use input: a new spawn binding is impossible,
    # but the existing contact-policy edit remains a complete alternative.
    other = copy.deepcopy(binding)
    other["id"] = "alternate_body"
    other["input"] = "alternate_use"
    authored["runtimeProgram"]["bindings"].append(other)
    closed = build_runtime_repair_scope(authored, [{
        "path": f"$.runtimeProgram.calls[{index}].params.event",
        "code": "capability_event_incompatible", "allowed": ["on_hit"],
        "relatedIds": ["item"], "message": "synthetic event choice",
    }])
    alternatives = next(row for row in closed["eventAlternatives"] if row["callId"] == "body_child")
    assert any(row["event"] == "on_hit" and row["requiredBindings"][0]["targetId"] == "item"
               for row in alternatives["allowed"])
    assert not any(row["event"] == "on_hit" and row["requiredBindings"]
                   and row["requiredBindings"][0]["targetId"] == "workbench_blade"
                   for row in alternatives["allowed"])


def test_placement_input_does_not_emit_item_use() -> None:
    authored = build_runtime_fixture("fishing_platform_tool")
    compiled = compile_runtime_program(authored)
    inputs = {row["input"] for row in runtime_event_inventory(compiled)
              if row["entityId"] == "item" and row["event"] == "on_use"}
    assert inputs == {"primary_use"}


def test_equipped_second_binding_is_rejected_before_and_after_compilation() -> None:
    assert INPUT_KIND_REGISTRY["equipped"].exclusive is True
    authored = build_runtime_fixture("equipment_tool_combat")
    extra = copy.deepcopy(next(b for b in authored["runtimeProgram"]["bindings"] if b["input"] == "equipped"))
    extra["id"] = "second_equipped"
    authored["runtimeProgram"]["bindings"].append(extra)
    assert strict_author_shape_report(authored)["ok"]
    issues = validate_runtime_program(authored)["errors"]
    assert "duplicate_exclusive_input" in {e["code"] for e in issues}
    scope = build_runtime_repair_scope(authored, issues)
    assert any(t["input"] == "equipped" and t["mustKeepExactlyOne"] for t in scope["repairTransactions"]["exclusiveInputSelections"])
    with pytest.raises(ValueError):
        compile_runtime_program(authored)
    valid = build_runtime_fixture("equipment_tool_combat")
    assert validate_runtime_program(valid)["ok"]
    wire = compile_runtime_program(valid)
    wire["runtimeProgram"]["bindings"].append({**copy.deepcopy(next(b for b in wire["runtimeProgram"]["bindings"] if b["input"] == "equipped")), "id": "second_equipped"})
    assert "duplicate_exclusive_input" in {e["code"] for e in validate_runtime_wire(wire)["errors"]}
