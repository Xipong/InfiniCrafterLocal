"""Own-stack RNG is an explicit binding policy; placement and ammo stay separate."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring import (
    compile_runtime_program, validate_runtime_program, validate_runtime_wire,
    apply_repair_patch, build_runtime_repair_scope, filter_repair_patch_scope,
)
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts, STACK_CHANCE_LOWERER_ID
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def _fixture(chance=35):
    doc = build_runtime_fixture("workbench_blade")
    policy = doc["runtimeProgram"]["bindings"][0]["usePolicy"]
    policy.update(stackCost=1, stackConsumeChancePercent=chance)
    return doc


@pytest.mark.parametrize("chance", [0, 1, 35, 99, 100])
def test_stack_probability_is_literal_in_full_compile_and_receipts(chance):
    authored = _fixture(chance)
    before = deepcopy(authored)
    final = compile_runtime_program(authored)
    assert authored == before
    assert validate_runtime_wire(final)["ok"]
    assert final["runtimeProgram"]["bindings"][0]["usePolicy"]["stackConsumeChancePercent"] == chance
    receipts = final["runtimeContract"]["finalWireReceipts"]
    rows = [r for r in receipts if r.get("lowererId") == STACK_CHANCE_LOWERER_ID]
    assert len(rows) == 1 and rows[0]["value"] == chance
    assert audit_compiler_receipts(receipts, authored_document=authored, final_document=final)["ok"]


@pytest.mark.parametrize("chance", [-1, 101, 0.5, True, None, "35"])
def test_author_and_wire_reject_invalid_probabilities(chance):
    assert not validate_runtime_program(_fixture(chance))["ok"]
    final = compile_runtime_program(_fixture())
    final.pop("runtimeContract")
    final["runtimeProgram"]["bindings"][0]["usePolicy"]["stackConsumeChancePercent"] = chance
    assert not validate_runtime_wire(final)["ok"]


def test_absence_keeps_existing_wire_and_does_not_create_probability_receipt():
    authored = build_runtime_fixture("workbench_blade")
    final = compile_runtime_program(authored)
    assert "stackConsumeChancePercent" not in final["runtimeProgram"]["bindings"][0]["usePolicy"]
    assert not any(r.get("lowererId") == STACK_CHANCE_LOWERER_ID for r in final["runtimeContract"]["finalWireReceipts"])


@pytest.mark.parametrize("fixture_name,input_name", [("workbench_blade", "primary_use"), ("fishing_platform_tool", "alternate_use"), ("equipment_tool_combat", "equipped")])
def test_free_passive_or_placement_bindings_cannot_borrow_stack_rng(fixture_name, input_name):
    authored = build_runtime_fixture(fixture_name)
    bindings = authored["runtimeProgram"]["bindings"]
    candidate = next(b for b in bindings if b["input"] == input_name)
    if candidate["usePolicy"]["action"]["kind"] != "place_item":
        candidate["usePolicy"]["stackCost"] = 0
    candidate["usePolicy"]["stackConsumeChancePercent"] = 100
    assert not validate_runtime_program(authored)["ok"]


def test_saving_stack_on_reusable_placement_hybrid_keeps_one_physical_unit():
    authored = build_runtime_fixture("fishing_platform_tool")
    binding = next(b for b in authored["runtimeProgram"]["bindings"] if b["input"] == "primary_use")
    binding["usePolicy"].update(stackCost=1, stackConsumeChancePercent=35)
    assert validate_runtime_program(authored)["ok"]
    final = compile_runtime_program(authored)
    stats = next(c for c in authored["runtimeProgram"]["calls"] if c["fn"] == "configure_item_stats")
    stats["params"]["maxStack"] = 2
    assert any(e["code"] == "hybrid_placeable_max_stack" for e in validate_runtime_program(authored)["errors"])
    final.pop("runtimeContract")
    final["gameplay"]["maxStack"] = 2
    assert any(e["code"] == "hybrid_placeable_max_stack" for e in validate_runtime_wire(final)["errors"])


@pytest.mark.parametrize("stack_cost", [True, False, 0.5, 2])
def test_probability_requires_literal_integer_one_stack_cost(stack_cost):
    authored = _fixture()
    authored["runtimeProgram"]["bindings"][0]["usePolicy"]["stackCost"] = stack_cost
    assert not validate_runtime_program(authored)["ok"]


@pytest.mark.parametrize("mutation", ["drop", "value", "identity", "source"])
def test_probability_receipt_cannot_be_forged(mutation):
    authored = _fixture()
    final = compile_runtime_program(authored)
    receipts = deepcopy(final["runtimeContract"]["finalWireReceipts"])
    receipt = next(r for r in receipts if r.get("lowererId") == STACK_CHANCE_LOWERER_ID)
    if mutation == "drop":
        receipts.remove(receipt)
    elif mutation == "value":
        receipt["value"] = 99
        final["runtimeProgram"]["bindings"][0]["usePolicy"]["stackConsumeChancePercent"] = 99
    elif mutation == "identity":
        final["runtimeProgram"]["bindings"][0]["id"] = "other_binding"
    else:
        receipt["authoredPaths"][1] = "runtimeProgram.bindings[0].usePolicy.stackCost"
    assert not audit_compiler_receipts(receipts, authored_document=authored, final_document=final)["ok"]


def test_probability_repair_changes_only_invalid_leaf_and_omission_does_not_default():
    authored = _fixture(101)
    report = validate_runtime_program(authored)
    scope = build_runtime_repair_scope(authored, report["errors"])
    binding = deepcopy(authored["runtimeProgram"]["bindings"][0])
    binding["usePolicy"]["stackConsumeChancePercent"] = 35
    binding["usePolicy"]["contactDamage"] = False
    patch = {"bindingsUpsert": [binding], "note": "Repair exact invalid probability."}
    filtered, audit = filter_repair_patch_scope(authored, patch, scope)
    repaired = apply_repair_patch(authored, filtered)
    assert repaired["runtimeProgram"]["bindings"][0]["usePolicy"]["stackConsumeChancePercent"] == 35
    assert repaired["runtimeProgram"]["bindings"][0]["usePolicy"]["contactDamage"] is True
    assert validate_runtime_program(repaired)["ok"]
    omitted = deepcopy(binding)
    del omitted["usePolicy"]["stackConsumeChancePercent"]
    filtered, _ = filter_repair_patch_scope(authored, {"bindingsUpsert": [omitted], "note": "No probability patch."}, scope)
    assert apply_repair_patch(authored, filtered)["runtimeProgram"]["bindings"][0]["usePolicy"]["stackConsumeChancePercent"] == 101
