"""Fn-selected wire outputs must authenticate the executor, not a self-consistent lie."""
from copy import deepcopy
import re
from typing import Any

import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness


def test_source_selected_movement_cannot_be_retargeted_by_equal_receipt_edits():
    source = build_capability_witness("move_straight")
    original_source = deepcopy(source)
    wire = compile_runtime_program(source)
    assert validate_runtime_wire(wire)["ok"]
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e.get("movement", {}).get("name") == "move_straight")
    entity["movement"].update(name="move_slow_homing", code=1, params={"homingStrength": 0.15})
    rows = wire["runtimeContract"]["finalWireReceipts"]
    for row in rows:
        if row.get("fn") == "move_straight":
            row["value"] = "move_slow_homing" if row["finalPath"].endswith(".name") else 1
    report = audit_compiler_receipts(rows, authored_document=source, final_document=wire)
    assert not report["ok"], "unchanged Author must bind the actual selected executor"
    assert any("fn-selected" in v["reason"] for v in report["violations"]), report
    assert not validate_runtime_wire(wire)["ok"], "saved proof must bind its claimed fn too"
    assert source == original_source


@pytest.mark.parametrize("fn,component", [("move_straight", "movement"), ("target_and_fire", "controller")])
@pytest.mark.parametrize("leaves", [("name",), ("code",), ("name", "code")])
@pytest.mark.parametrize("source_backed", [True, False])
def test_selected_executor_requires_each_fixed_output_receipt(fn, component, leaves, source_backed):
    source = build_capability_witness(fn)
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    rows[:] = [row for row in rows if not (row.get("fn") == fn
               and any(row["finalPath"].endswith(f".{component}.{leaf}") for leaf in leaves))]
    report = audit_compiler_receipts(rows, authored_document=source if source_backed else None, final_document=wire)
    assert not report["ok"], "each selected fixed output requires unique originating coverage"
    assert any("fixed wire literal has no unique" in v["reason"] for v in report["violations"]), report
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("named", [False, True])
def test_fixed_output_coverage_uses_only_the_selected_effect_group(named):
    source = build_capability_witness("recall_home_on_use")
    if named:
        call = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "recall_home_on_use")
        call["params"]["effectGroupId"] = "chosen"
        for binding in source["runtimeProgram"]["bindings"]:
            if binding.get("action", {}).get("kind") == "apply_item_effects":
                binding["action"]["effectGroupId"] = "chosen"
    wire = compile_runtime_program(source)
    assert validate_runtime_wire(wire)["ok"]
    for authored in (source, None):
        report = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"],
                                         authored_document=authored, final_document=wire)
        assert report["ok"], report


@pytest.mark.parametrize("mutation", ["remove", "change"])
def test_selected_owner_teleport_has_one_fixed_destination_mode(mutation):
    source = build_capability_witness("move_owner_on_event")
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    selected = next(r for r in rows if r.get("fn") == "move_owner_on_event" and r["finalPath"].endswith(".mode"))
    if mutation == "remove":
        rows.remove(selected)
    else:
        event = next(event for entity in wire["runtimeProgram"]["entities"] for event in entity.get("events", [])
                     if event["id"] == selected["callId"])
        event["mode"] = selected["value"] = "owner_to_target"
    for authored in (source, None):
        report = audit_compiler_receipts(rows, authored_document=authored, final_document=wire)
        assert not report["ok"], "teleport capability selects exactly blink_to_event_position"
        assert any("fixed wire literal" in v["reason"] for v in report["violations"]), report
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("fn,tail", [
    ("set_projectile_damage", ".damage.enabled"),
    ("configure_spawn", ".spawn.enabled"),
    ("configure_item_use", ".itemUse.configured"),
    ("configure_accessory", "accessory.enabled"),
    ("configure_armor", "armor.enabled"),
])
@pytest.mark.parametrize("mutation", ["false_with_matching_receipt", "remove_receipt"])
def test_selected_configuration_flag_is_fixed_and_covered(fn, tail, mutation):
    source = build_capability_witness(fn)
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    selected = next(row for row in rows if row.get("fn") == fn and row["finalPath"].endswith(tail))
    if mutation == "remove_receipt":
        rows.remove(selected)
    else:
        value: Any = wire
        segments = re.findall(r"[A-Za-z][A-Za-z0-9_]*|\d+", selected["finalPath"])
        for segment in segments[:-1]:
            value = value[int(segment)] if isinstance(value, list) else value[segment]
        value[segments[-1]] = selected["value"] = False
    for authored in (source, None):
        report = audit_compiler_receipts(rows, authored_document=authored, final_document=wire)
        assert not report["ok"], (fn, mutation, "a selected configuration cannot disable itself")
        assert any("fixed wire literal" in v["reason"] for v in report["violations"]), report
    assert not validate_runtime_wire(wire)["ok"]
