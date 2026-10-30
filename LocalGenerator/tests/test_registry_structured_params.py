"""Structured Author parameters keep strict shape and exact wire provenance."""
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys

import pytest
from hypothesis import example, given, settings, strategies as st
from jsonschema import Draft202012Validator

import infini_local.core.runtime_authoring.capability_registry as registry
import infini_local.core.runtime_authoring.compiler as compiler
import infini_local.core.runtime_authoring.technical_lowering as technical_lowering
from infini_local.core.runtime_authoring.capability_registry import ParamSpec
from infini_local.core.runtime_authoring.program_schema import strict_schema_errors
from infini_local.qa.capability_witnesses import build_capability_witness


JSON_VALUES = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(max_size=12),
    lambda children: st.lists(children, max_size=4)
    | st.dictionaries(st.text(max_size=8), children, max_size=4),
    max_leaves=12,
)


@pytest.mark.parametrize("keyword", ["const", "enum"])
@settings(max_examples=64, derandomize=True, deadline=None)
@example(value=True, literal=1)
@example(value=False, literal=0)
@example(value={"flag": True}, literal={"flag": 1})
@example(value=[False], literal=[0])
@example(value=1.0, literal=1)
@example(value={"a": [1.0], "b": False}, literal={"b": False, "a": [1]})
@given(value=JSON_VALUES, literal=JSON_VALUES)
def test_literal_admission_agrees_with_independent_json_schema(keyword, value, literal):
    # The JSON Schema implementation is an independent oracle. Generated nested
    # values cover key order, scalar/container distinctions and bool/int aliases;
    # checking the literal itself prevents an always-reject validator from passing.
    schema = {keyword: [literal] if keyword == "enum" else literal}
    before = deepcopy((value, schema))
    assert (not strict_schema_errors(value, schema)) == Draft202012Validator(schema).is_valid(value)
    assert not strict_schema_errors(deepcopy(literal), schema)
    assert (value, schema) == before


def test_boolean_and_numeric_const_union_selects_exactly_one_branch():
    schema = {"oneOf": [{"const": True}, {"const": 1}]}
    assert not strict_schema_errors(True, schema)
    assert not strict_schema_errors(1, schema)
    assert strict_schema_errors(False, schema)


@pytest.mark.parametrize("reverse_properties", [False, True], ids=["declared-order", "reversed-order"])
def test_object_keeps_exact_leaf_units_and_rejects_empty_group(reverse_properties):
    properties = {
        "radius": ParamSpec("number", "Radius on the exact pixel lattice", minimum=0.5,
                                 maximum=48, multiple_of=1 / 16, wire_multiplier=16, wire_name="radiusPx"),
        "updatesPerTick": ParamSpec("integer", "Updates", minimum=1, maximum=6, wire_offset=-1,
                                    wire_name="extraUpdates", required=False),
    }
    if reverse_properties:
        properties = dict(reversed(list(properties.items())))
    spec = ParamSpec("object", "Explicit grouped stats", min_properties=1, properties=properties)
    assert not strict_schema_errors({"radius": 8.0625, "updatesPerTick": 6}, spec.schema())
    rows = spec.projected_fields({"radius": 8.0625, "updatesPerTick": 6}, "group")
    # Independent DTO destinations have no execution order. Keep provenance,
    # values and multiplicity exact rather than pinning registry insertion order.
    assert Counter((r.authored_path, r.wire_path, r.value) for r in rows) == Counter([
        ("group.radius", "radiusPx", 129), ("group.updatesPerTick", "extraUpdates", 5),
    ])
    assert strict_schema_errors({}, spec.schema())
    assert strict_schema_errors({"radius": 0.6}, spec.schema())


@pytest.mark.parametrize("mutation", ["old-primary-path", "old-group-path", "six-inputs", "six-use-policy-inputs"])
def test_retired_global_source_paths_are_refused(mutation):
    document = build_capability_witness("placed_sprite" if mutation != "old-group-path" else "generated_buff_on_use")
    if mutation == "old-group-path":
        next(c for c in document["runtimeProgram"]["calls"] if c["id"] == "witness_call")["params"]["effectGroupId"] = "utility"
        document["runtimeProgram"]["bindings"][0]["action"]["effectGroupId"] = "utility"
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    assert technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]
    if mutation == "old-primary-path":
        row = next(r for r in receipts if r.get("lowererId") == "primary_entity_to_binding_role")
        row["authoredPaths"] = [row["authoredPaths"][0], "runtimeProgram.bindings[0].usePolicy.action.targetId"]
    elif mutation == "old-group-path":
        row = next(r for r in receipts if r.get("lowererId") == "binding_effect_group_identity")
        row["authoredPaths"] = [p.replace(".action.", ".usePolicy.action.") for p in row["authoredPaths"]]
    else:
        row = next(r for r in receipts if r.get("fn") == "placed_sprite" and r["status"] == "technical_projection")
        paths = row["authoredPaths"]
        binding = paths[3].removesuffix(".id")
        row["authoredPaths"] = paths[:3] + [binding + ".action.kind", binding + ".action.targetId", binding + ".action.placementCallId"]
        if mutation == "six-use-policy-inputs":
            row["authoredPaths"] = [p.replace(".action.", ".usePolicy.action.") for p in row["authoredPaths"]]
    assert not technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]


def test_ambiguous_union_fails_closed():
    spec = ParamSpec("union", "Invalid duplicate branches", alternatives=(
        ParamSpec("string", "One", enum=("x",), wire_literals={"field": 1}),
        ParamSpec("string", "Two", enum=("x",), wire_literals={"field": 2}),
    ))
    with pytest.raises(ValueError, match="exactly one"):
        spec.projected_fields("x", "choice")


def test_retired_provenance_refuses_old_wire_and_old_author():
    old_author = build_capability_witness("projectile_collision")
    corpus = json.loads((Path(__file__).with_name("fixtures") / "projectile_retained_wire.json").read_text())
    old_wire = next(row["wire"] for row in corpus["cases"] if row["fn"] == "set_projectile_collision")
    old_call = next(c for c in old_author["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    old_call["params"].pop("immunity")
    old_call["params"].pop("updatesPerTick")
    old_call["params"].update(npcImmunityMode="owner", localNpcHitCooldownEngineUnits=37, extraUpdates=5)
    old_receipts = deepcopy(old_wire["runtimeContract"]["finalWireReceipts"])
    assert not technical_lowering.audit_compiler_receipts(old_receipts, final_document=old_wire)["ok"]
    assert not technical_lowering.audit_compiler_receipts(
        old_receipts, authored_document=old_author, final_document=old_wire,
    )["ok"]
    with pytest.raises(ValueError):
        compiler.compile_runtime_program(old_author)
    changed = deepcopy(old_receipts)
    row = next(r for r in changed if r.get("authoredPath", "").endswith(".localNpcHitCooldownEngineUnits"))
    row["value"] = 10.5
    assert not technical_lowering.audit_compiler_receipts(changed)["ok"]
    row["value"] = 10
    row["authoredPath"] = row["authoredPath"].replace("localNpcHitCooldownEngineUnits", "unregisteredOldName")
    assert not technical_lowering.audit_compiler_receipts(changed)["ok"]


def _two_collision_calls():
    document = build_capability_witness("spawn_on_event")
    calls = [c for c in document["runtimeProgram"]["calls"] if c["fn"] == "projectile_collision"]
    assert len(calls) == 2
    for i, call in enumerate(calls):
        call["params"]["immunity"] = {"localCooldown": 10 + i}
    return document, calls


@pytest.mark.parametrize("attack", ["source-targets", "final-owners"])
def test_call_projection_authenticates_exact_entity_owner(attack):
    from infini_local.core.runtime_authoring.validator import validate_runtime_program
    document, calls = _two_collision_calls()
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    assert technical_lowering.audit_compiler_receipts(receipts, authored_document=document, final_document=wire)["ok"]
    if attack == "source-targets":
        calls[0]["target"], calls[1]["target"] = calls[1]["target"], calls[0]["target"]
        assert validate_runtime_program(document)["ok"]  # valid new Author, stale proof
    else:
        entities = wire["runtimeProgram"]["entities"]
        indices = [next(i for i, e in enumerate(entities) if e["id"] == c["target"]) for c in calls]
        entities[indices[0]]["collision"], entities[indices[1]]["collision"] = (
            entities[indices[1]]["collision"], entities[indices[0]]["collision"])
        for row in receipts:
            if row.get("fn") == "projectile_collision":
                old = next(i for i in indices if row["finalPath"].startswith(f"runtimeProgram.entities[{i}]."))
                new = indices[1] if old == indices[0] else indices[0]
                row["finalPath"] = row["finalPath"].replace(f"entities[{old}]", f"entities[{new}]")
    standalone = technical_lowering.audit_compiler_receipts(receipts, final_document=wire)
    assert standalone["ok"] and standalone["authoredSourceChecked"] is False
    assert not technical_lowering.audit_compiler_receipts(
        receipts, authored_document=document, final_document=wire,
    )["ok"]


@pytest.mark.parametrize("attack", ["id-only", "coordinated-events"])
def test_event_projection_authenticates_exact_call_identity(attack):
    document = build_capability_witness("damage_nearby_on_event")
    call = next(c for c in document["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    another = deepcopy(call)
    another.update(id="another_nearest")
    another["params"]["maxTargets"] = 7
    document["runtimeProgram"]["calls"].append(another)
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    checked_source = document
    assert technical_lowering.audit_compiler_receipts(receipts, authored_document=checked_source, final_document=wire)["ok"]
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == call["target"])
    events = entity["events"]
    assert len(events) == 2
    if attack == "id-only":
        events[0]["id"], events[1]["id"] = events[1]["id"], events[0]["id"]
    else:
        ids = [e["id"] for e in events]
        events.reverse()
        for event, identity in zip(events, ids):
            event["id"] = identity
        for row in receipts:
            if row.get("callId") in {call["id"], another["id"]}:
                row["finalPath"] = row["finalPath"].replace("events[0]", "events[x]").replace("events[1]", "events[0]").replace("events[x]", "events[1]")
    for source in (None, checked_source):
        assert not technical_lowering.audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]


@pytest.mark.parametrize("attack", ["duplicate", "missing-all", "source-index"])
def test_projection_coverage_is_unique_and_complete(attack):
    document, calls = _two_collision_calls()
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    source_tail = ".params.immunity"
    relevant = [r for r in receipts if r.get("callId") == calls[0]["id"]
                and source_tail in r.get("authoredPath", "")]
    if attack == "duplicate":
        receipts.append(deepcopy(relevant[-1]))
    elif attack == "missing-all":
        receipts[:] = [r for r in receipts if r not in relevant]
    else:
        # Different source coordinates cannot claim one wire owner's output.
        for r in relevant:
            r["authoredPath"] = r["authoredPath"].replace("calls[", "calls[9")
    for source in (None, document):
        assert not technical_lowering.audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]


@pytest.mark.parametrize("malformed", ["boolean", "above-maximum", "float", "null"])
@pytest.mark.parametrize("source_available", [False, True])
def test_structured_scalar_domain_is_not_authenticated_by_coherent_receipts(malformed, source_available):
    immunity = registry.CAPABILITY_REGISTRY["projectile_collision"].params["immunity"]
    cooldown = next(branch.properties["localCooldown"] for branch in immunity.alternatives if branch.kind == "object")
    bad = {"boolean": True, "above-maximum": cooldown.maximum + 1, "float": 1.0, "null": None}[malformed]
    document = build_capability_witness("projectile_collision")
    call = next(c for c in document["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    call["params"]["immunity"] = {"localCooldown": 19}
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    source = document if source_available else None
    assert technical_lowering.audit_compiler_receipts(
        receipts, authored_document=source, final_document=wire,
    )["ok"]
    # Corrupt the current authored leaf, not a retired unknown parameter that
    # would fail regardless of whether the cooldown domain was checked.
    call["params"]["immunity"]["localCooldown"] = bad
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == call["target"])
    entity["collision"]["localNpcHitCooldownTicks"] = bad
    next(r for r in receipts if r.get("callId") == call["id"] and r["finalPath"].endswith(".localNpcHitCooldownTicks"))["value"] = bad
    assert not technical_lowering.audit_compiler_receipts(
        receipts, authored_document=source, final_document=wire,
    )["ok"]


def test_wire_claim_cannot_split_one_call_across_entity_owners():
    document, calls = _two_collision_calls()
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    entities = wire["runtimeProgram"]["entities"]
    indices = [next(i for i, e in enumerate(entities) if e["id"] == c["target"]) for c in calls]
    # Equal-valued scalar fields still belong to one exact call/component.
    row = next(r for r in receipts if r.get("callId") == calls[0]["id"] and r["finalPath"].endswith(".tileCollide"))
    row["finalPath"] = row["finalPath"].replace(f"entities[{indices[0]}]", f"entities[{indices[1]}]")
    assert not technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]


@pytest.mark.parametrize("missing", ["npcImmunityMode", "localNpcHitCooldownTicks"])
def test_typed_variant_outputs_require_complete_coverage(missing):
    document = build_capability_witness("projectile_collision")
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    receipts[:] = [r for r in receipts if not (r.get("callId") == "witness_call"
                                             and r["finalPath"].endswith("." + missing))]
    assert not technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]


def test_wire_output_cannot_be_claimed_by_two_distinct_calls():
    document = build_capability_witness("projectile_collision")
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    duplicates = [deepcopy(r) for r in receipts if r.get("callId") == "witness_call"]
    for row in duplicates:
        row["callId"] = "another_collision"
        row["authoredPath"] = row["authoredPath"].replace("calls[", "calls[9")
    receipts.extend(duplicates)
    assert not technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]


def test_fn_literal_provenance_requires_value_source_and_complete_coverage(monkeypatch):
    document = build_capability_witness("spawn")
    changed = dict(registry.CAPABILITY_REGISTRY)
    changed["spawn"] = replace(changed["spawn"], fixed_wire_literals={"enabled": True})
    for name, module in tuple(sys.modules.items()):
        if name.startswith("infini_local.") and hasattr(module, "CAPABILITY_REGISTRY"):
            monkeypatch.setattr(module, "CAPABILITY_REGISTRY", changed)
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    literal = next(r for r in receipts if r.get("fn") == "spawn" and r["finalPath"].endswith(".enabled"))
    assert technical_lowering.audit_compiler_receipts(receipts, authored_document=document, final_document=wire)["ok"]
    for key, value in (("value", False), ("status", "delivered"), ("authoredPath", "runtimeProgram.calls[0].fn")):
        forged = deepcopy(receipts)
        forged[receipts.index(literal)][key] = value
        assert not technical_lowering.audit_compiler_receipts(forged, authored_document=document, final_document=wire)["ok"]
    assert not technical_lowering.audit_compiler_receipts([r for r in receipts if r is not literal], final_document=wire)["ok"]


@pytest.mark.parametrize("key,value", [("shotEntity", "shot"), ("intervalSeconds", 1), ("sameTargetBias", 0.5)])
def test_obsolete_controller_bag_fields_are_refused_without_provenance(key, value):
    from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
    wire = compiler.compile_runtime_program(build_capability_witness("target_and_fire"))
    wire.pop("runtimeContract")
    controller = next(e["controller"] for e in wire["runtimeProgram"]["entities"] if "controller" in e)
    controller.setdefault("params", {})[key] = value
    assert not validate_runtime_wire(wire)["ok"]
