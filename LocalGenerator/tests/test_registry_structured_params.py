"""Structured Author parameters keep strict shape and exact wire provenance."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys

import pytest

from infini_local.core.runtime_authoring import capability_registry as registry
from infini_local.core.runtime_authoring import compiler, technical_lowering
from infini_local.core.runtime_authoring.capability_registry import ParamSpec
from infini_local.core.runtime_authoring.program_schema import strict_schema_errors
from infini_local.qa.capability_witnesses import build_capability_witness


def test_object_keeps_exact_leaf_units_and_rejects_empty_group():
    spec = ParamSpec("object", "Explicit grouped stats", min_properties=1, properties={
        "radiusTiles": ParamSpec("number", "Radius on the exact pixel lattice", minimum=0.5,
                                 maximum=48, multiple_of=1 / 16, wire_multiplier=16, wire_name="radiusPx"),
        "updatesPerTick": ParamSpec("integer", "Updates", minimum=1, maximum=6, wire_offset=-1,
                                    wire_name="extraUpdates", required=False),
    })
    assert not strict_schema_errors({"radiusTiles": 8.0625, "updatesPerTick": 6}, spec.schema())
    rows = spec.projected_fields({"radiusTiles": 8.0625, "updatesPerTick": 6}, "group")
    assert [(r.authored_path, r.wire_path, r.value) for r in rows] == [
        ("group.radiusTiles", "radiusPx", 129), ("group.updatesPerTick", "extraUpdates", 5),
    ]
    assert strict_schema_errors({}, spec.schema())
    assert strict_schema_errors({"radiusTiles": 0.6}, spec.schema())


def test_ambiguous_union_fails_closed():
    spec = ParamSpec("union", "Invalid duplicate branches", alternatives=(
        ParamSpec("string", "One", enum=("x",), wire_literals={"field": 1}),
        ParamSpec("string", "Two", enum=("x",), wire_literals={"field": 2}),
    ))
    with pytest.raises(ValueError, match="exactly one"):
        spec.projected_fields("x", "choice")


def test_retained_provenance_preserves_old_wire_without_accepting_old_author():
    old_author = build_capability_witness("set_projectile_collision")
    corpus = json.loads((Path(__file__).with_name("fixtures") / "projectile_retained_wire.json").read_text())
    old_wire = next(row["wire"] for row in corpus["cases"] if row["fn"] == "set_projectile_collision")
    old_call = next(c for c in old_author["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    old_call["params"].pop("immunity")
    old_call["params"].pop("updatesPerTick")
    old_call["params"].update(npcImmunityMode="owner", localNpcHitCooldownEngineUnits=37, extraUpdates=5)
    old_receipts = deepcopy(old_wire["runtimeContract"]["finalWireReceipts"])
    assert technical_lowering.audit_compiler_receipts(old_receipts, final_document=old_wire)["ok"]
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


def _scalar_collision(monkeypatch):
    """Isolated prior scalar contract, not a production grammar/importer."""
    import infini_local.qa.capability_witnesses as witnesses
    monkeypatch.setattr(witnesses, "_COLLISION", {
        "tileCollide": True, "ignoreWater": False, "bounceCount": 0, "pierce": 1,
        "extraUpdates": 0, "npcImmunityMode": "local", "localNpcHitCooldownEngineUnits": 10,
    })
    cap = registry.CAPABILITY_REGISTRY["set_projectile_collision"]
    params = dict(cap.params)
    params.pop("immunity")
    params.pop("updatesPerTick")
    params.update(cap.retained_receipt_params)
    changed = replace(cap, params=params, retained_receipt_params={})
    modified = dict(registry.CAPABILITY_REGISTRY)
    modified[cap.name] = replace(changed, final_wire_paths=registry._exact_wire_paths(changed))
    for name, module in tuple(sys.modules.items()):
        if name.startswith("infini_local.") and hasattr(module, "CAPABILITY_REGISTRY"):
            monkeypatch.setattr(module, "CAPABILITY_REGISTRY", modified)


def _two_collision_calls(monkeypatch, typed):
    if not typed:
        _scalar_collision(monkeypatch)
    document = build_capability_witness("spawn_entity_on_event")
    calls = [c for c in document["runtimeProgram"]["calls"] if c["fn"] == "set_projectile_collision"]
    assert len(calls) == 2
    for i, call in enumerate(calls):
        call["params"]["immunity" if typed else "localNpcHitCooldownEngineUnits"] = {"localCooldown": 10 + i} if typed else 10 + i
    return document, calls


@pytest.mark.parametrize("typed", [False, True], ids=["legacy-scalar", "typed-immunity"])
@pytest.mark.parametrize("attack", ["source-targets", "final-owners"])
def test_call_projection_authenticates_exact_entity_owner(monkeypatch, typed, attack):
    from infini_local.core.runtime_authoring import validate_runtime_program
    document, calls = _two_collision_calls(monkeypatch, typed)
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
            if row.get("fn") == "set_projectile_collision":
                old = next(i for i in indices if row["finalPath"].startswith(f"runtimeProgram.entities[{i}]."))
                new = indices[1] if old == indices[0] else indices[0]
                row["finalPath"] = row["finalPath"].replace(f"entities[{old}]", f"entities[{new}]")
    standalone = technical_lowering.audit_compiler_receipts(receipts, final_document=wire)
    assert standalone["ok"] and standalone["authoredSourceChecked"] is False
    assert not technical_lowering.audit_compiler_receipts(
        receipts, authored_document=document, final_document=wire,
    )["ok"]


@pytest.mark.parametrize("alias", [False, True], ids=["legacy-chain", "pr26-nearest"])
@pytest.mark.parametrize("attack", ["id-only", "coordinated-events"])
def test_event_projection_authenticates_exact_call_identity(monkeypatch, alias, attack):
    document = build_capability_witness("damage_nearest_on_event")
    call = next(c for c in document["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    another = deepcopy(call)
    another.update(id="another_nearest")
    another["params"]["maxTargets"] = 7
    document["runtimeProgram"]["calls"].append(another)
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    if not alias:
        # The same action-4 wire retains old scalar provenance without accepting
        # that retired grammar as a fresh Author or inventing a source.
        for row in receipts:
            if row.get("fn") == "damage_nearest_on_event":
                row["fn"] = "chain_damage_on_event"
                row["authoredPath"] = row["authoredPath"].replace(".params.maxTargets", ".params.count").replace(".params.when", ".params.event")
    checked_source = document if alias else None
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


@pytest.mark.parametrize("typed", [False, True], ids=["legacy-scalar", "typed-immunity"])
@pytest.mark.parametrize("attack", ["duplicate", "missing-all", "source-index"])
def test_projection_coverage_is_unique_and_complete(monkeypatch, typed, attack):
    document, calls = _two_collision_calls(monkeypatch, typed)
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    source_tail = ".params.immunity" if typed else ".params.localNpcHitCooldownEngineUnits"
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


@pytest.mark.parametrize("bad", [True, 601, 1.0, None])
@pytest.mark.parametrize("source_available", [False, True])
def test_legacy_scalar_domain_is_not_authenticated_by_coherent_receipts(bad, source_available):
    document = build_capability_witness("set_projectile_collision")
    call = next(c for c in document["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    call["params"]["localNpcHitCooldownEngineUnits"] = bad
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == call["target"])
    entity["collision"]["localNpcHitCooldownTicks"] = bad
    next(r for r in receipts if r.get("callId") == call["id"] and r["finalPath"].endswith(".localNpcHitCooldownTicks"))["value"] = bad
    assert not technical_lowering.audit_compiler_receipts(
        receipts, authored_document=document if source_available else None, final_document=wire,
    )["ok"]


@pytest.mark.parametrize("typed", [False, True], ids=["legacy-scalar", "typed-immunity"])
def test_wire_claim_cannot_split_one_call_across_entity_owners(monkeypatch, typed):
    document, calls = _two_collision_calls(monkeypatch, typed)
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    entities = wire["runtimeProgram"]["entities"]
    indices = [next(i for i, e in enumerate(entities) if e["id"] == c["target"]) for c in calls]
    # Equal-valued scalar fields still belong to one exact call/component.
    row = next(r for r in receipts if r.get("callId") == calls[0]["id"] and r["finalPath"].endswith(".tileCollide"))
    row["finalPath"] = row["finalPath"].replace(f"entities[{indices[0]}]", f"entities[{indices[1]}]")
    assert not technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]


def test_unrelated_retained_parameter_cannot_excuse_missing_typed_outputs(monkeypatch):
    document = build_capability_witness("set_projectile_collision")
    call = next(c for c in document["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    call["params"]["immunity"] = {"localCooldown": 19}
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    cap = technical_lowering.CAPABILITY_REGISTRY["set_projectile_collision"]
    retained = dict(cap.retained_receipt_params)
    retained["extraUpdates"] = cap.retained_receipt_params["extraUpdates"]
    modified = dict(technical_lowering.CAPABILITY_REGISTRY)
    modified[cap.name] = replace(cap, retained_receipt_params=retained)
    monkeypatch.setattr(technical_lowering, "CAPABILITY_REGISTRY", modified)
    receipts[:] = [r for r in receipts if ".params.immunity" not in r.get("authoredPath", "")]
    assert not technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]


@pytest.mark.parametrize("missing", ["npcImmunityMode", "localNpcHitCooldownEngineUnits"])
def test_retained_scalar_variant_outputs_still_require_complete_coverage(monkeypatch, missing):
    _scalar_collision(monkeypatch)
    document = build_capability_witness("set_projectile_collision")
    wire = compiler.compile_runtime_program(document)
    monkeypatch.undo()  # Restore the current typed registry; old receipts are wire-only.
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    receipts[:] = [r for r in receipts if not (r.get("callId") == "witness_call"
                                             and r["authoredPath"].endswith(".params." + missing))]
    assert not technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]


def test_wire_output_cannot_be_claimed_by_two_distinct_calls():
    document = build_capability_witness("set_projectile_collision")
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    duplicates = [deepcopy(r) for r in receipts if r.get("callId") == "witness_call"]
    for row in duplicates:
        row["callId"] = "another_collision"
        row["authoredPath"] = row["authoredPath"].replace("calls[", "calls[9")
    receipts.extend(duplicates)
    assert not technical_lowering.audit_compiler_receipts(receipts, final_document=wire)["ok"]


def test_fn_literal_provenance_requires_value_source_and_complete_coverage(monkeypatch):
    document = build_capability_witness("configure_spawn")
    changed = dict(registry.CAPABILITY_REGISTRY)
    changed["configure_spawn"] = replace(changed["configure_spawn"], fixed_wire_literals={"enabled": True})
    for name, module in tuple(sys.modules.items()):
        if name.startswith("infini_local.") and hasattr(module, "CAPABILITY_REGISTRY"):
            monkeypatch.setattr(module, "CAPABILITY_REGISTRY", changed)
    wire = compiler.compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    literal = next(r for r in receipts if r.get("fn") == "configure_spawn" and r["finalPath"].endswith(".enabled"))
    assert technical_lowering.audit_compiler_receipts(receipts, authored_document=document, final_document=wire)["ok"]
    for key, value in (("value", False), ("status", "delivered"), ("authoredPath", "runtimeProgram.calls[0].fn")):
        forged = deepcopy(receipts)
        forged[receipts.index(literal)][key] = value
        assert not technical_lowering.audit_compiler_receipts(forged, authored_document=document, final_document=wire)["ok"]
    assert not technical_lowering.audit_compiler_receipts([r for r in receipts if r is not literal], final_document=wire)["ok"]
