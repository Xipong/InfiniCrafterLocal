from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring.binding_use_policy import (
    action_kind, authored_transaction, contact_damage, project_to_wire,
    stack_cost, target_id, wire_action_kind, wire_contact_damage,
    wire_placeable_input_contract, wire_stack_cost, wire_target_id,
)
from infini_local.core.runtime_authoring.capability_registry import (
    CAPABILITY_REGISTRY, RUNTIME_PROGRAM_SCHEMA, authored_call_target_id,
    unique_item_body_id,
)
from infini_local.core.runtime_authoring.program_schema import (
    author_item_repair_schema, author_item_response_schema, binding_schema,
    strict_schema_errors,
)
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


@pytest.mark.parametrize(("source", "kind", "target", "cost", "contact"), [
    ({"id": "equip", "input": "equipped"}, "equip_passive", "item", 0, False),
    ({"id": "hold", "input": "hold", "action": {"targetId": "bolt"}}, "spawn_entity", "bolt", 0, False),
    ({"id": "use", "input": "primary_use", "action": {"kind": "use_item_body"}, "stackCost": 0, "contactDamage": True}, "use_item_body", "item", 0, True),
    ({"id": "effects", "input": "alternate_use", "action": {"kind": "apply_item_effects"}, "stackCost": 1, "contactDamage": False}, "apply_item_effects", "item", 1, False),
    ({"id": "place", "input": "primary_use", "action": {"kind": "place_item", "placementCallId": "tile"}}, "place_item", "item", 1, False),
])
def test_native_binding_variants_project_to_existing_wire(source, kind, target, cost, contact):
    before = deepcopy(source)
    assert not strict_schema_errors(source, binding_schema())
    assert (action_kind(source), target_id(source, item_entity_id="item"), stack_cost(source), contact_damage(source)) == (kind, target, cost, contact)
    wire = project_to_wire(source, item_entity_id="item", placement_calls_by_id={
        "tile": {"params": {"tileId": 18, "wallId": -1, "placeStyle": 0}},
    })
    assert (wire_action_kind(wire), wire_target_id(wire), wire_stack_cost(wire), wire_contact_damage(wire)) == (kind, target, cost, contact)
    assert source == before
    assert "usePolicy" in wire and "usePolicy" not in source
    if kind == "place_item":
        assert wire["usePolicy"]["action"]["placement"] == {"tileId": 18, "wallId": -1, "placeStyle": 0}
        assert wire_placeable_input_contract([wire])[0]


@pytest.mark.parametrize("source", [
    {"id": "equip", "input": "equipped", "action": {}},
    {"id": "equip", "input": "equipped", "stackCost": 0},
    {"id": "equip", "input": "equipped", "contactDamage": False},
    {"id": "hold", "input": "hold", "action": {"kind": "spawn_entity", "targetId": "bolt"}},
    {"id": "use", "input": "primary_use", "action": {"kind": "use_item_body", "targetId": "item"}, "stackCost": 0, "contactDamage": True},
    {"id": "place", "input": "primary_use", "action": {"kind": "place_item", "placementCallId": "tile"}, "stackCost": 1},
    {"id": "place", "input": "primary_use", "action": {"kind": "place_item", "placementCallId": "tile"}, "contactDamage": False},
    {"id": "old", "input": "primary_use", "usePolicy": {"action": {"kind": "use_item_body", "targetId": "item"}, "stackCost": 0, "contactDamage": True}},
])
def test_obsolete_explicit_binding_fields_are_rejected_even_when_values_match(source):
    assert strict_schema_errors(source, binding_schema())
    assert strict_schema_errors({"bindingsUpsert": [source], "note": "obsolete syntax"}, author_item_repair_schema())


def test_item_targets_and_zero_argument_calls_have_one_source_spelling():
    item = build_runtime_fixture("workbench_blade")
    entities = item["runtimeProgram"]["entities"]
    stats = next(row for row in item["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats")
    assert "target" not in stats
    assert authored_call_target_id(stats, entities) == "item"
    assert strict_schema_errors({**stats, "target": "item"}, CAPABILITY_REGISTRY[stats["fn"]].provider_variant_schema())
    movement = {"id": "travel", "fn": "move_straight", "target": "bolt"}
    schema = CAPABILITY_REGISTRY["move_straight"].provider_variant_schema()
    assert not strict_schema_errors(movement, schema)
    assert strict_schema_errors({**movement, "params": {}}, schema)
    assert strict_schema_errors({"id": "travel", "fn": "move_straight"}, schema)
    # An event that can also target projectiles never inherits the body target.
    event = {"id": "event", "fn": "heal_owner_on_event"}
    assert authored_call_target_id(event, entities) == ""


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "malformed_id"])
def test_implicit_target_ambiguity_stays_on_authored_entity_declarations(mutation):
    item = build_runtime_fixture("workbench_blade")
    entities = item["runtimeProgram"]["entities"]
    if mutation == "missing":
        entities[:] = [row for row in entities if row["kind"] != "item_body"]
    elif mutation == "duplicate":
        entities.append({"id": "other_body", "kind": "item_body"})
    else:
        next(row for row in entities if row["kind"] == "item_body")["id"] = 42
    before = deepcopy(item)
    assert unique_item_body_id(entities) == ""
    report = validate_runtime_program(item)
    assert not report["ok"]
    paths = {row["path"] for row in report["errors"]}
    assert any(path.startswith("$.runtimeProgram.entities") for path in paths)
    for index, call in enumerate(item["runtimeProgram"]["calls"]):
        if CAPABILITY_REGISTRY[call["fn"]].target_kinds == ("item_body",):
            assert f"$.runtimeProgram.calls[{index}].target" not in paths
    assert item == before


@pytest.mark.parametrize("concept", [None, {}, "not a gameplay authority", ["malformed sketch"]])
def test_nonbinding_concept_does_not_block_native_author(concept):
    item = build_runtime_fixture("workbench_blade")
    item["concept"] = concept
    before = deepcopy(item)
    assert validate_runtime_program(item)["ok"]
    assert item == before


def test_absent_concept_and_explicit_report_indices_do_not_generate_prose():
    item = build_runtime_fixture("workbench_blade")
    item.pop("concept")
    row = item["realization"]["selfEvaluation"]["planVsProgram"]["actionChecks"][0]
    row["plannedActionIndex"] = None
    before = deepcopy(item)
    assert validate_runtime_program(item)["ok"]
    assert item == before and "plannedIntent" not in row


@pytest.mark.parametrize("invalid_index", [True, -1, 8, 0.5, "0"])
def test_report_index_type_and_bounds_are_strict(invalid_index):
    item = build_runtime_fixture("workbench_blade")
    item["realization"]["selfEvaluation"]["planVsProgram"]["actionChecks"][0]["plannedActionIndex"] = invalid_index
    assert not validate_runtime_program(item)["ok"]


def test_old_author_version_and_group_notation_have_no_admission_path():
    item = build_runtime_fixture("workbench_blade")
    assert RUNTIME_PROGRAM_SCHEMA == "infini.runtime-program.authoring.v5"
    item["runtimeProgram"]["schema"] = "infini.runtime-program.authoring.v4"
    assert not validate_runtime_program(item)["ok"]
    item["runtimeProgram"]["schema"] = RUNTIME_PROGRAM_SCHEMA
    item["runtimeProgram"]["callGroups"] = [{"calls": item["runtimeProgram"].pop("calls")}]
    assert not validate_runtime_program(item)["ok"]
    assert "callGroups" not in author_item_response_schema()["properties"]["runtimeProgram"]["properties"]


def test_sparse_authored_transaction_extraction_preserves_omissions():
    source = {"id": "use", "input": "primary_use", "action": {"kind": "use_item_body"}}
    transaction = authored_transaction(source)
    assert transaction == {"input": "primary_use", "action": {"kind": "use_item_body"}}
    transaction["action"]["kind"] = "apply_item_effects"
    assert source["action"]["kind"] == "use_item_body"


@pytest.mark.parametrize(("binding", "path", "kind"), [
    ({"id": "use", "action": {"kind": "use_item_body"}, "stackCost": 0, "contactDamage": True}, "$.input", "required"),
    ({"id": "use", "input": "primary_use", "action": {"kind": "unknown_kind"}, "stackCost": 0, "contactDamage": True}, "$.action.kind", "one_of"),
    ({"id": "place", "input": "primary_use", "action": {"kind": "place_item", "placementCallId": "tile"}, "stackCost": 0}, "$.stackCost", "additional_property"),
    ({"id": "use", "input": "primary_use", "action": "spawn_entity", "target": "bolt", "stackCost": 0, "contactDamage": False}, "$.action", "type"),
])
def test_invalid_binding_discriminators_and_constants_keep_exact_error_paths(binding, path, kind):
    errors = strict_schema_errors(binding, binding_schema())
    assert any(row["path"] == path and row["kind"] == kind for row in errors), errors
