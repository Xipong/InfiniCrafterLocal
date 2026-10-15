"""Exact event naming and fresh-vs-retained targeting domains share one owner."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from infini_local.core.runtime_authoring.capability_registry import (
    CAPABILITY_REGISTRY,
    capability_inventory_rows,
    capability_provider_union,
    compact_capability_catalog,
)
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.capability_registry import EVENT_ACTION_OPCODE, EVENT_CAPABILITIES
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness

NEW = "damage_nearest_on_event"
OLD = "chain_damage_on_event"
FIXTURE = Path(__file__).with_name("fixtures") / "event_domain_retained_wire.json"


def witness(document):
    return next(row for row in document["runtimeProgram"]["calls"] if row["id"] == "witness_call")


def compile_and_check(document):
    wire = compile_runtime_program(document)
    assert validate_runtime_wire(wire)["ok"]
    for source in (None, document):
        audit = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=source, final_document=wire)
        assert audit["ok"], audit
    call = witness(document)
    return wire, next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == call["target"])


# Owner routes and event discriminators each retain a witness; target-count
# bounds do not require a Cartesian product with both routing dimensions.
@pytest.mark.parametrize("when,count,item_body", [
    ("on_hit", 1, False),
    ("on_crit", 12, False),
    ("on_hit", 12, True),
    ("on_crit", 1, True),
])
def test_nearest_alias_preserves_exact_event_opcode_parameters_and_authority(when, count, item_body):
    document = build_capability_witness(NEW)
    call = witness(document)
    if item_body:
        document = build_capability_witness("configure_item_contact_hitbox")
        witness(document)["id"] = "contact"
        next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "configure_item_use")["params"]["disableMeleeHitbox"] = False
        call["target"] = "item"
        document["runtimeProgram"]["calls"].append(call)
    call["params"].update(when=when, maxTargets=count, rangeTiles=7.125, damageMultiplier=0.625, delayTicks=37)
    wire, entity = compile_and_check(document)
    assert entity["events"][0] == {
        "id": "witness_call", "action": OLD, "actionCode": 4, "event": when,
        "count": count, "rangeTiles": 7.125, "damageMultiplier": 0.625, "delayTicks": 37,
    }
    cap = CAPABILITY_REGISTRY[NEW]
    assert cap.network_authority == "owner_execute_sync"
    receipts = [row for row in wire["runtimeContract"]["finalWireReceipts"] if row.get("callId") == "witness_call"]
    for field in ("action", "actionCode"):
        row = next(row for row in receipts if row["finalPath"].endswith("." + field))
        assert row["authoredPath"].endswith(".fn") and row["status"] == "technical_projection"
    count_row = next(row for row in receipts if row["finalPath"].endswith(".count"))
    assert count_row["authoredPath"].endswith(".params.maxTargets")
    assert count_row["value"] == count and count_row["status"] == "delivered"


@pytest.mark.parametrize("name,value", [
    ("maxTargets", 0), ("maxTargets", 13), ("maxTargets", 1.5), ("maxTargets", True),
    ("maxTargets", None), ("count", 2), ("rangeTiles", 0.9), ("rangeTiles", 61),
    ("damageMultiplier", 0.049), ("damageMultiplier", 2.01),
    ("when", "periodic"), ("when", {"everyTicks": 60}), ("event", "on_hit"),
])
def test_nearest_alias_rejects_old_or_ambiguous_fresh_fields(name, value):
    document = build_capability_witness(NEW)
    witness(document)["params"][name] = value
    assert not validate_runtime_program(document)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(document)


@pytest.mark.parametrize("mutation", ["literal", "missing", "duplicate", "source", "count_path", "count_domain"])
def test_nearest_receipts_bind_exact_fixed_action_and_max_target_source(mutation):
    document = build_capability_witness(NEW)
    wire, entity = compile_and_check(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    action = next(row for row in receipts if row.get("callId") == "witness_call" and row["finalPath"].endswith(".action"))
    if mutation == "literal":
        entity["events"][0].update(action="damage_area_on_event", actionCode=3)
        action["value"] = "damage_area_on_event"
        next(row for row in receipts if row.get("callId") == "witness_call" and row["finalPath"].endswith(".actionCode"))["value"] = 3
    elif mutation == "missing":
        receipts.remove(action)
    elif mutation == "duplicate":
        receipts.append(deepcopy(action))
    elif mutation == "source":
        action["authoredPath"] = action["authoredPath"].removesuffix(".fn") + ".params.maxTargets"
    elif mutation == "count_path":
        row = next(row for row in receipts if row.get("callId") == "witness_call" and row["finalPath"].endswith(".count"))
        row["authoredPath"] = row["authoredPath"].removesuffix(".maxTargets") + ".count"
    else:
        row = next(row for row in receipts if row.get("callId") == "witness_call" and row["finalPath"].endswith(".count"))
        row["value"] = entity["events"][0]["count"] = 13
    for source in (None, document):
        assert not audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
    assert not validate_runtime_wire(wire)["ok"]


def test_old_receipt_owner_is_retired_but_current_action_four_remains():
    public = {row["fn"]: row for row in compact_capability_catalog()}
    variants = {row["properties"]["fn"]["const"]: row for row in capability_provider_union()}
    assert NEW in public and NEW in variants and OLD not in public and OLD not in variants
    assert "maxTargets" in public[NEW]["params"] and "count" not in public[NEW]["params"]
    assert "same center" in public[NEW]["does"] and "excluding" in public[NEW]["does"]
    assert "sequential hopping" in public[NEW]["does"]
    assert OLD not in CAPABILITY_REGISTRY and EVENT_ACTION_OPCODE[OLD] == 4
    assert NEW in EVENT_CAPABILITIES and OLD not in EVENT_CAPABILITIES
    document = deepcopy(json.loads(FIXTURE.read_text())["cases"][0]["source"])
    report = validate_runtime_program(document)
    assert not report["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(document)
    scope = build_runtime_repair_scope(document, report["errors"])
    assert OLD not in scope["create"]["calls"]["allowedFns"]


def test_stationary_diagnostics_and_repair_offer_only_fresh_event_capabilities():
    document = build_capability_witness("target_and_fire")
    target = witness(document)["target"]
    calls = document["runtimeProgram"]["calls"]
    document["runtimeProgram"]["calls"] = [
        row for row in calls if row.get("target") != target or not CAPABILITY_REGISTRY[row["fn"]].meaningful_for_stationary
    ]
    report = validate_runtime_program(document)
    issue = next(row for row in report["errors"] if row["code"] == "inert_stationary_entity")
    allowed = set(issue["allowed"])
    assert NEW in allowed and OLD not in allowed
    assert allowed <= {row["fn"] for row in compact_capability_catalog()}
    scope = build_runtime_repair_scope(document, report["errors"])
    assert OLD not in scope["create"]["calls"]["allowedFns"]
    assert NEW in scope["create"]["calls"]["allowedFns"]


def test_frozen_old_receipts_are_refused_without_rewriting_the_archive():
    corpus = json.loads(FIXTURE.read_text())
    assert corpus["sourceHead"] == "c0a8450"
    for row in corpus["cases"]:
        wire = row["wire"]
        encoded = json.dumps(wire, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        assert hashlib.sha256(encoded.encode()).hexdigest() == row["wireSha256"]
        assert not validate_runtime_wire(wire)["ok"]
        receipts = wire["runtimeContract"]["finalWireReceipts"]
        assert not audit_compiler_receipts(receipts, final_document=wire)["ok"]
        assert json.dumps(wire, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == encoded
        source_audit = audit_compiler_receipts(receipts, authored_document=row["source"], final_document=wire)
        assert not source_audit["ok"]


@pytest.mark.parametrize("bias", [0, 0.125, 0.5, 0.899999, 0.9])
def test_fresh_bias_is_exact_unclamped_and_bounded_at_point_nine(bias):
    document = build_capability_witness("target_and_fire")
    witness(document)["params"]["sameTargetBias"] = bias
    wire, entity = compile_and_check(document)
    assert entity["targeting"]["sameTargetBias"] == bias
    assert any(row.get("callId") == "witness_call" and row["authoredPath"].endswith(".sameTargetBias")
               and row["value"] == bias for row in wire["runtimeContract"]["finalWireReceipts"])


@pytest.mark.parametrize("bias", [-0.001, 0.900001, 0.95, 1, 1.001, True, None, "0.9", float("inf"), float("nan")])
def test_bad_fresh_bias_is_rejected_not_clamped_or_projected_to_retained_domain(bias):
    document = build_capability_witness("target_and_fire")
    witness(document)["params"]["sameTargetBias"] = bias
    assert not validate_runtime_program(document)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(document)


@pytest.mark.parametrize("bias", [0, 0.9, 0.95, 1, -0.001, 1.001, True, None, "0.95", float("inf"), float("nan")])
@pytest.mark.parametrize("provenance", [False, True])
def test_saved_bias_domain_is_strict_even_without_receipts(bias, provenance):
    wire = compile_runtime_program(build_capability_witness("target_and_fire"))
    target = next(row for row in wire["runtimeProgram"]["entities"] if "targeting" in row)
    target["targeting"]["sameTargetBias"] = bias
    if provenance:
        receipt = next(row for row in wire["runtimeContract"]["finalWireReceipts"] if row.get("callId") == "witness_call" and row["authoredPath"].endswith(".sameTargetBias"))
        receipt["value"] = bias
    else:
        wire.pop("runtimeContract")
    good = type(bias) in (int, float) and 0 <= bias <= 0.9
    assert validate_runtime_wire(wire)["ok"] == good
    assert target["targeting"]["sameTargetBias"] is bias  # no in-place normalization


@pytest.mark.parametrize("fn,leaf,bad,good", [(NEW, "maxTargets", 13, 3), ("target_and_fire", "sameTargetBias", 0.95, 0.4)])
def test_leaf_repair_keeps_valid_neighbors_and_accepts_only_current_domain(fn, leaf, bad, good):
    document = build_capability_witness(fn)
    call = witness(document)
    call["params"][leaf] = bad
    scope = build_runtime_repair_scope(document, validate_runtime_program(document)["errors"])
    assert next(row["paths"] for row in scope["fieldPermissions"]["calls"] if row["id"] == call["id"]) == ["params." + leaf]
    candidate = deepcopy(call)
    candidate["params"].update({leaf: good, "rangeTiles": 999})
    patch, audit = filter_repair_patch_scope(document, {"note": "correct one domain leaf", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(document, patch)
    assert witness(repaired)["params"]["rangeTiles"] == call["params"]["rangeTiles"]
    assert witness(repaired)["params"][leaf] == good
    assert audit["ignoredChanges"]
    compile_and_check(repaired)
    candidate["params"][leaf] = bad
    _, audit = filter_repair_patch_scope(document, {"note": "still bad", "callsUpsert": [candidate]}, scope)
    assert not audit["ok"]


def test_only_current_bias_domain_is_exported():
    cap = CAPABILITY_REGISTRY["target_and_fire"]
    assert cap.params["sameTargetBias"].maximum == 0.9
    assert cap.provider_variant_schema()["properties"]["params"]["properties"]["sameTargetBias"]["maximum"] == 0.9
    assert cap.prompt_card()["params"]["sameTargetBias"]["max"] == 0.9
    assert "retainedWireProvenance" not in cap.prompt_card()
    assert "retainedWireProvenance" not in cap.audit_card()
    inventory = next(row for row in capability_inventory_rows() if row["capability"] == cap.name)
    assert "retainedWireProvenance" not in inventory
    assert inventory["parameters"]["sameTargetBias"]["maximum"] == 0.9
    assert CAPABILITY_REGISTRY[NEW].params["maxTargets"].semantic_type == "spawn_or_target_count"

@pytest.mark.parametrize("equal", [False, True])
def test_nearest_alias_receipts_bind_final_event_identity_even_for_equal_values(equal):
    source = build_capability_witness(NEW)
    first = witness(source)
    first["params"]["maxTargets"] = 1
    second = deepcopy(first)
    second["id"] = "another_nearest"
    second["params"]["maxTargets"] = 1 if equal else 7
    source["runtimeProgram"]["calls"].append(second)
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == first["target"])
    assert audit_compiler_receipts(rows, authored_document=source, final_document=wire)["ok"]
    for row in rows:
        if row.get("callId") in {first["id"], second["id"]}:
            row["finalPath"] = row["finalPath"].replace("events[0]", "EVENT_SWAP").replace("events[1]", "events[0]").replace("EVENT_SWAP", "events[1]")
    a, b = entity["events"]
    a_id, b_id = a["id"], b["id"]
    entity["events"] = [{**b, "id": a_id}, {**a, "id": b_id}]
    for doc in (None, source):
        assert not audit_compiler_receipts(rows, authored_document=doc, final_document=wire)["ok"]
