"""Exact event naming and fresh-vs-retained targeting domains share one owner."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY, EVENT_ACTION_OPCODE, EVENT_CAPABILITIES
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.registry_views import (
    capability_inventory_rows,
    capability_provider_union,
    compact_capability_catalog,
)
from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness

NEW = "damage_nearby_on_event"
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
        document = build_capability_witness("item_hitbox")
        witness(document)["id"] = "contact"
        next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "item_use")["params"]["disableMeleeHitbox"] = False
        call["target"] = "item"
        document["runtimeProgram"]["calls"].append(call)
    call["params"].update(when=when, maxTargets=count, radius=7.125, damageMultiplier=0.625, delay=(37) / 60)
    wire, entity = compile_and_check(document)
    assert entity["events"][0] == {
        "id": "witness_call", "action": NEW, "actionCode": 10, "event": when,
        "maxTargets": count, "radiusPx": 114, "damageMultiplier": 0.625, "delayTicks": 37,
    }
    cap = CAPABILITY_REGISTRY[NEW]
    assert cap.network_authority == "server_execute"
    assert cap.authority_by_effect[when] == "owner_execute_sync"
    receipts = [row for row in wire["runtimeContract"]["finalWireReceipts"] if row.get("callId") == "witness_call"]
    for field in ("action", "actionCode"):
        row = next(row for row in receipts if row["finalPath"].endswith("." + field))
        assert row["authoredPath"].endswith(".fn") and row["status"] == "technical_projection"
    count_row = next(row for row in receipts if row["finalPath"].endswith(".maxTargets"))
    assert count_row["authoredPath"].endswith(".params.maxTargets")
    assert count_row["value"] == count and count_row["status"] == "delivered"


@pytest.mark.parametrize("name,value", [
    ("maxTargets", 0), ("maxTargets", 17), ("maxTargets", 1.5), ("maxTargets", True),
    ("maxTargets", None), ("count", 2), ("radius", 0.49), ("radius", 61),
    ("damageMultiplier", 0.049), ("damageMultiplier", 4.01),
    ("when", "periodic"), ("when", {"everySeconds": 1}), ("event", "on_hit"),
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
        row = next(row for row in receipts if row.get("callId") == "witness_call" and row["finalPath"].endswith(".maxTargets"))
        row["authoredPath"] = row["authoredPath"].removesuffix(".maxTargets") + ".count"
    else:
        row = next(row for row in receipts if row.get("callId") == "witness_call" and row["finalPath"].endswith(".maxTargets"))
        row["value"] = entity["events"][0]["maxTargets"] = 17
    for source in (None, document):
        assert not audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
    assert not validate_runtime_wire(wire)["ok"]


def test_old_receipt_owner_is_retired_but_current_action_four_remains():
    public = {row["fn"]: row for row in compact_capability_catalog()}
    variants = {row["properties"]["fn"]["const"]: row for row in capability_provider_union()}
    assert NEW in public and NEW in variants and OLD not in public and OLD not in variants
    assert "maxTargets" in public[NEW]["params"] and "count" not in public[NEW]["params"]
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


@pytest.mark.parametrize("fn,leaf,bad,good", [(NEW, "maxTargets", 17, 3), ("target_and_fire", "sameTargetBias", 0.95, 0.4)])
def test_leaf_repair_keeps_valid_neighbors_and_accepts_only_current_domain(fn, leaf, bad, good):
    document = build_capability_witness(fn)
    call = witness(document)
    call["params"][leaf] = bad
    scope = build_runtime_repair_scope(document, validate_runtime_program(document)["errors"])
    assert next(row["paths"] for row in scope["fieldPermissions"]["calls"] if row["id"] == call["id"]) == ["params." + leaf]
    candidate = deepcopy(call)
    neighbor = "radius" if fn == NEW else "range"
    candidate["params"].update({leaf: good, neighbor: 999})
    patch, audit = filter_repair_patch_scope(document, {"note": "correct one domain leaf", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(document, patch)
    assert witness(repaired)["params"][neighbor] == call["params"][neighbor]
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


@pytest.mark.parametrize("mode,impulses", [
    ("target_to_owner", {"impulseBlocksPerSecond": 8, "radius": 10}),
    ("target_to_entity", {"impulseBlocksPerSecond": 14, "radius": 10}),
    ("owner_to_target", {"impulseBlocksPerSecond": 8}),
    ("both", {"ownerImpulseBlocksPerSecond": 8, "targetImpulseBlocksPerSecond": 14}),
])
def test_unified_pull_compiles_only_explicit_selected_branch(mode, impulses):
    document = build_capability_witness("pull_on_event")
    witness(document)["params"] = {"when": "on_crit", "mode": mode, **impulses}
    wire, entity = compile_and_check(document)
    action = entity["events"][0]
    assert action["action"] == "pull_on_event" and action["actionCode"] == 5
    assert action["mode"] == mode
    if mode == "both":
        assert action["ownerStrength"] == 8 * 16 / 60
        assert action["targetStrength"] == 14 * 16 / 60
        assert "strength" not in action and "radius" not in action
    else:
        assert action["strength"] == impulses["impulseBlocksPerSecond"] * 16 / 60
        assert "ownerStrength" not in action and "targetStrength" not in action
    delivery = deepcopy(wire); delivery.pop("runtimeContract")
    assert validate_runtime_wire(delivery)["ok"]


@pytest.mark.parametrize("change", [
    {"targetImpulseBlocksPerSecond": None}, {"targetImpulseBlocksPerSecond": True},
    {"targetImpulseBlocksPerSecond": 0}, {"targetImpulseBlocksPerSecond": 15.01},
    {"radius": 5}, {"impulseBlocksPerSecond": 2},
    {"when": {"everySeconds": 1}}, {"when": "on_expire"},
])
def test_both_pull_rejects_missing_wrong_branch_or_targetless_events(change):
    document = build_capability_witness("pull_on_event")
    witness(document)["params"] = {"when": "on_hit", "mode": "both",
        "ownerImpulseBlocksPerSecond": 8, "targetImpulseBlocksPerSecond": 14, **change}
    assert not validate_runtime_program(document)["ok"]
    with pytest.raises(ValueError): compile_runtime_program(document)


def test_both_pull_missing_impulse_repair_preserves_other_strength_and_mode():
    document = build_capability_witness("pull_on_event")
    call = witness(document)
    call["params"] = {"when": "on_hit", "mode": "both", "ownerImpulseBlocksPerSecond": 8}
    report = validate_runtime_program(document)
    assert not report["ok"]
    scope = build_runtime_repair_scope(document, report["errors"])
    candidate = deepcopy(call)
    candidate["params"].update(ownerImpulseBlocksPerSecond=12, targetImpulseBlocksPerSecond=14)
    patch, audit = filter_repair_patch_scope(document, {"note": "supply missing target impulse", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(document, patch)
    assert witness(repaired)["params"]["ownerImpulseBlocksPerSecond"] == 8
    assert witness(repaired)["params"]["mode"] == "both"
    assert witness(repaired)["params"]["targetImpulseBlocksPerSecond"] == 14
    compile_and_check(repaired)


def test_nearby_omission_is_explicit_cap_receipt_not_unlimited_damage():
    source = build_capability_witness(NEW)
    witness(source)["params"].pop("maxTargets")
    wire, entity = compile_and_check(source)
    assert entity["events"][0]["maxTargets"] == 16
    receipt = next(r for r in wire["runtimeContract"]["finalWireReceipts"]
                   if r.get("callId") == "witness_call" and r["finalPath"].endswith(".maxTargets"))
    assert receipt["status"] == "declared_neutral_omission" and receipt["value"] == 16


@pytest.mark.parametrize("field,value", [("maxTargets", 17), ("maxTargets", True), ("radiusPx", 961),
    ("radiusPx", 7), ("damageMultiplier", 4.01), ("damageMultiplier", None), ("mode", "both")])
def test_nearby_delivery_strict_native_domain_without_diagnostics(field, value):
    wire = compile_runtime_program(build_capability_witness(NEW)); wire.pop("runtimeContract")
    event = next(e["events"][0] for e in wire["runtimeProgram"]["entities"] if e["events"])
    event[field] = value
    assert not validate_runtime_wire(wire)["ok"]


def test_saved_event_facts_survive_in_current_envelope_without_accepting_retired_item_fields():
    corpus = json.loads(FIXTURE.with_name("event_api_pre_simplification.json").read_text())
    assert corpus["sourceHead"] == "723f0e1b07a79b3621f40e61c4d9ee30690ced8a"
    for case in corpus["cases"]:
        wire = case["wire"]
        before = deepcopy(wire)
        report = validate_runtime_wire(wire)
        assert not report["ok"] and any(
            e["path"] == "$.runtimeProgram.itemUse.releaseTiming" for e in report["errors"])
        assert not audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"],
            final_document=wire)["ok"], case["fn"]
        # Saved receipts remain readable; historical Author syntax is not a
        # second authenticated input grammar for new v7 compilation.
        assert not audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"],
            authored_document=case["source"], final_document=wire)["ok"], case["fn"]
        assert not validate_runtime_program(case["source"])["ok"]
        assert wire == before
        # Current envelope; only the archived event is transplanted, with no
        # old item presentation or authentication receipts silently migrated.
        delivery = compile_runtime_program(build_capability_witness(NEW))
        delivery.pop("runtimeContract")
        target = next(e for e in delivery["runtimeProgram"]["entities"] if e.get("events"))
        saved_events = next(e["events"] for e in wire["runtimeProgram"]["entities"] if e.get("events"))
        target["events"] = deepcopy(saved_events)
        assert validate_runtime_wire(delivery)["ok"]
        assert target["events"] == saved_events
        if case["fn"] != "pull_on_event":
            assert not validate_runtime_program(case["source"])["ok"]
            assert not CAPABILITY_REGISTRY[case["fn"]].author_visible


def test_both_pull_foreign_radius_repair_deletes_only_invalid_leaf():
    source = build_capability_witness("pull_on_event")
    call = witness(source)
    call["params"] = {"when": "on_hit", "mode": "both", "ownerImpulseBlocksPerSecond": 8,
                      "targetImpulseBlocksPerSecond": 14, "radius": 8}
    scope = build_runtime_repair_scope(source, validate_runtime_program(source)["errors"])
    assert next(row["paths"] for row in scope["fieldPermissions"]["calls"]
                if row["id"] == call["id"]) == ["params.radius"]
    candidate = deepcopy(call)
    candidate["params"].pop("radius")
    candidate["params"]["ownerImpulseBlocksPerSecond"] = 12
    patch, audit = filter_repair_patch_scope(source, {"note": "delete foreign radius", "callsUpsert": [candidate],
        "callParamKeysDelete": [{"callId": call["id"], "key": name}
                               for name in ("radius", "ownerImpulseBlocksPerSecond")]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(source, patch)
    assert witness(repaired)["params"] == {"when": "on_hit", "mode": "both",
        "ownerImpulseBlocksPerSecond": 8, "targetImpulseBlocksPerSecond": 14}
    compile_and_check(repaired)
    assert audit["ignoredChanges"]
    # A valid different branch is not an alternate permission to change mode.
    hostile = deepcopy(call)
    hostile["params"] = {"when": "on_hit", "mode": "owner_to_target", "impulseBlocksPerSecond": 2}
    patch, audit = filter_repair_patch_scope(source, {"note": "try replacing branch", "callsUpsert": [hostile]}, scope)
    if audit["ok"]:
        actual = witness(apply_repair_patch(source, patch))["params"]
        assert actual == {key: value for key, value in call["params"].items() if key != "radius"}


@pytest.mark.parametrize("invalid_selector", ["oops", None, 7, {}])
def test_pull_undecided_mode_repair_freezes_present_strengths(invalid_selector):
    source = build_capability_witness("pull_on_event")
    call = witness(source)
    call["params"] = {"when": "on_hit", "ownerImpulseBlocksPerSecond": 8,
                      "targetImpulseBlocksPerSecond": 14}
    if invalid_selector is not None:
        call["params"]["mode"] = invalid_selector
    report = validate_runtime_program(source)
    assert not report["ok"]
    scope = build_runtime_repair_scope(source, report["errors"])
    candidate = deepcopy(call)
    candidate["params"].update(mode="both", when="on_crit", ownerImpulseBlocksPerSecond=1,
                               targetImpulseBlocksPerSecond=2)
    patch, audit = filter_repair_patch_scope(source, {"note": "choose mode", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(source, patch)
    assert witness(repaired)["params"] == {"when": "on_hit", "mode": "both",
        "ownerImpulseBlocksPerSecond": 8, "targetImpulseBlocksPerSecond": 14}
    compile_and_check(repaired)


@pytest.mark.parametrize("invalid_when", ["oops", None, 7, {}])
def test_pull_invalid_when_repair_freezes_mode_and_strengths(invalid_when):
    source = build_capability_witness("pull_on_event")
    call = witness(source)
    call["params"] = {"mode": "both", "ownerImpulseBlocksPerSecond": 8,
                      "targetImpulseBlocksPerSecond": 14}
    if invalid_when is not None:
        call["params"]["when"] = invalid_when
    scope = build_runtime_repair_scope(source, validate_runtime_program(source)["errors"])
    candidate = deepcopy(call)
    candidate["params"].update(when="on_hit", ownerImpulseBlocksPerSecond=1,
                               targetImpulseBlocksPerSecond=2)
    patch, audit = filter_repair_patch_scope(source, {"note": "choose event", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(source, patch)
    assert witness(repaired)["params"] == {"when": "on_hit", "mode": "both",
        "ownerImpulseBlocksPerSecond": 8, "targetImpulseBlocksPerSecond": 14}
    compile_and_check(repaired)


@pytest.mark.parametrize("field,value", [
    ("count", 2), ("damageMultiplier", 2), ("entityId", "foreign"), ("spreadRadians", 1),
    ("periodTicks", 1), ("buffId", 1), ("durationTicks", 1), ("radiusPx", 16), ("rangeTiles", 1),
    ("strength", 1), ("radiusTiles", 1), ("damageFraction", .5), ("maxHeal", 1),
    ("cooldownTicks", 1), ("safeTileOnly", False), ("delayTicks", 601), ("delayTicks", -1), ("delayTicks", 1.5),
])
def test_both_delivery_rejects_foreign_native_fields_without_receipts(field, value):
    source = build_capability_witness("pull_on_event")
    witness(source)["params"] = {"when": "on_hit", "mode": "both",
        "ownerImpulseBlocksPerSecond": 8, "targetImpulseBlocksPerSecond": 14}
    wire = compile_runtime_program(source)
    wire.pop("runtimeContract")
    assert validate_runtime_wire(wire)["ok"]
    event = next(e["events"][0] for e in wire["runtimeProgram"]["entities"] if e["events"])
    event[field] = value
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(error["path"].endswith("." + field) for error in report["errors"]), report


@pytest.mark.parametrize("mode", ["target_to_owner", "target_to_entity", "owner_to_target"])
@pytest.mark.parametrize("field,value", [("count", 2), ("damageMultiplier", 2), ("spreadRadians", 1),
    ("durationTicks", 1), ("delayTicks", 601)])
def test_legacy_pull_delivery_keeps_existing_unused_field_acceptance(mode, field, value):
    wire = compile_runtime_program(build_capability_witness("pull_on_event"))
    wire.pop("runtimeContract")
    event = next(e["events"][0] for e in wire["runtimeProgram"]["entities"] if e["events"])
    event.update(mode=mode)
    event[field] = value
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("delay", [-1, 601, 1.5, True])
def test_nearby_delivery_rejects_invalid_delay_without_receipts(delay):
    wire = compile_runtime_program(build_capability_witness(NEW))
    wire.pop("runtimeContract")
    event = next(e["events"][0] for e in wire["runtimeProgram"]["entities"] if e["events"])
    event["delayTicks"] = delay
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(error["path"].endswith(".delayTicks") for error in report["errors"])


def test_both_delivery_reads_native_dto_neutrals_without_receipts():
    source = build_capability_witness("pull_on_event")
    witness(source)["params"] = {"when": "on_hit", "mode": "both",
        "ownerImpulseBlocksPerSecond": 8, "targetImpulseBlocksPerSecond": 14}
    wire = compile_runtime_program(source); wire.pop("runtimeContract")
    event = next(e["events"][0] for e in wire["runtimeProgram"]["entities"] if e["events"])
    event.update(count=1, damageMultiplier=1, entityId="", spreadRadians=0, periodTicks=0,
                 buffId=-1, durationTicks=0, radiusPx=0, rangeTiles=0, strength=0, radiusTiles=0,
                 damageFraction=0, maxHeal=0, cooldownTicks=0, safeTileOnly=True, delayTicks=600)
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("fn", ["pull_on_event", NEW])
@pytest.mark.parametrize("field,value", [("safeTileOnly", 1), ("safeTileOnly", 1.0), ("count", 1.0),
    ("count", True), ("durationTicks", 0.0), ("buffId", -1.0), ("periodTicks", 0.0),
    ("maxHeal", 0.0), ("cooldownTicks", 0.0), ("spreadRadians", False), ("strength", False)])
def test_new_event_unused_native_neutrals_require_exact_json_types(fn, field, value):
    source = build_capability_witness(fn)
    if fn == "pull_on_event":
        witness(source)["params"] = {"when": "on_hit", "mode": "both",
            "ownerImpulseBlocksPerSecond": 8, "targetImpulseBlocksPerSecond": 14}
    wire = compile_runtime_program(source); wire.pop("runtimeContract")
    event = next(e["events"][0] for e in wire["runtimeProgram"]["entities"] if e["events"])
    event[field] = value
    assert not validate_runtime_wire(wire)["ok"]
