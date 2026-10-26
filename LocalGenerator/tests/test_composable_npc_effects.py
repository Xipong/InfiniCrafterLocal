"""Composable timed NPC effects use authored quantities, not BuffID semantics."""
from copy import deepcopy
import json

import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.storage.world_storage import sanitize_recipe_for_delivery
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY, capability_provider_union
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope

FN = "apply_npc_effect_on_event"


def document(**params):
    doc = build_capability_witness("apply_status_on_event")
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    call.update(fn=FN, params={"when": "on_hit", "durationSeconds": 2, "damagePerSecond": 7.5, **params})
    return doc


def event(wire):
    return next(e["events"][0] for e in wire["runtimeProgram"]["entities"] if e.get("events"))


def check(doc):
    original = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert report["ok"], report
    wire = compile_runtime_program(doc)
    assert doc == original
    assert validate_runtime_wire(wire)["ok"], validate_runtime_wire(wire)
    for source in (doc, None):
        result = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=source, final_document=wire)
        assert result["ok"], result
    stripped = json.loads(json.dumps(sanitize_recipe_for_delivery(wire)))
    assert "runtimeContract" not in stripped
    assert validate_runtime_wire(stripped)["ok"], validate_runtime_wire(stripped)
    return wire


def test_composed_effect_reaches_final_wire_with_exact_native_units():
    wire = check(document(defenseDelta=-12, contactDamageMultiplier=0.75,
                          velocityRetentionPerTick=0.9, delaySeconds=0.5, chancePercent=25))
    assert event(wire) == {
        "id": "witness_call", "action": FN, "actionCode": 11, "event": "on_hit",
        "durationTicks": 120, "delayTicks": 30,
        "npcEffect": {"lifeRegenPenalty": 15, "defenseDelta": -12,
                      "contactDamageMultiplier": 0.75, "velocityRetentionPerTick": 0.9, "chance": 0.25},
    }


@pytest.mark.parametrize("chance", [0, 25, 100, 12.5])
def test_chance_is_independent_and_preserved_through_stripped_wire(chance):
    wire = check(document(chancePercent=chance))
    assert event(wire)["npcEffect"]["chance"] == chance / 100


@pytest.mark.parametrize("leaf,bad,good", [
    ("damagePerSecond", 0.25, 0.5), ("defenseDelta", -101, -100),
    ("contactDamageMultiplier", 0.09, 0.1), ("velocityRetentionPerTick", 1.01, 0.75),
    ("durationSeconds", 61, 1 / 60), ("chancePercent", 100.5, 25),
])
def test_invalid_leaf_repair_freezes_valid_siblings_and_absence(leaf, bad, good):
    doc = document(**{leaf: bad})
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    paths = next(r["paths"] for r in scope["fieldPermissions"]["calls"] if r["id"] == call["id"])
    assert paths == ["params." + leaf]
    candidate = deepcopy(call)
    candidate["params"].update({leaf: good, "when": "on_crit", "delaySeconds": 1})
    if leaf != "damagePerSecond":
        candidate["params"]["damagePerSecond"] = 100
    filtered, audit = filter_repair_patch_scope(doc, {"note": "correct leaf", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    assert audit["ignoredChanges"]
    repaired = apply_repair_patch(doc, filtered)
    actual = next(c for c in repaired["runtimeProgram"]["calls"] if c["id"] == call["id"])
    assert actual == {**call, "params": {**call["params"], leaf: good}}
    check(repaired)


@pytest.mark.parametrize("chance", [0, 25, 100])
def test_neutral_action_repair_opens_only_modifier_leaves(chance):
    doc = document(damagePerSecond=0, chancePercent=chance, delaySeconds=1)
    assert not CAPABILITY_REGISTRY[FN].has_non_neutral_effect({"chancePercent": chance, "delaySeconds": 1})
    report = validate_runtime_program(doc)
    assert not report["ok"]
    assert any(r["code"] == "inert_component" for r in report["errors"])
    scope = build_runtime_repair_scope(doc, report["errors"])
    paths = next(r["paths"] for r in scope["fieldPermissions"]["calls"] if r["id"] == "witness_call")
    assert set(paths) == {"params." + name for name in ("damagePerSecond", "defenseDelta", "contactDamageMultiplier", "velocityRetentionPerTick")}
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    candidate = deepcopy(call)
    candidate["params"].update(defenseDelta=-10, chancePercent=50, delaySeconds=2, durationSeconds=5, when="on_crit")
    filtered, audit = filter_repair_patch_scope(doc, {"note": "add one modifier", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(doc, filtered)
    actual = next(c for c in repaired["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    assert actual["params"] == {**call["params"], "defenseDelta": -10}
    check(repaired)


@pytest.mark.parametrize("leaf,value", [
    ("when", "periodic"), ("when", "on_expire"), ("chancePercent", True), ("chancePercent", None),
    ("chancePercent", "25"), ("chancePercent", -0.5), ("damagePerSecond", 200.5),
    ("damagePerSecond", True), ("defenseDelta", 1.5), ("defenseDelta", True),
    ("durationSeconds", 0), ("contactDamageMultiplier", 3.01),
    ("velocityRetentionPerTick", 0.09), ("buffId", 20),
])
def test_fresh_invalid_inputs_fail_without_normalization(leaf, value):
    doc = document(**{leaf: value})
    before = deepcopy(doc)
    assert not validate_runtime_program(doc)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(doc)
    assert doc == before


@pytest.mark.parametrize("mutation", ["missing_object", "null", "foreign_leaf", "wrong_owner", "neutral", "chance_range", "chance_type", "duration_float", "no_hit_producer"])
def test_stripped_wire_rejects_bad_shapes_and_wrong_owners(mutation):
    wire = check(document(chancePercent=25))
    wire.pop("runtimeContract")
    e = event(wire)
    if mutation == "missing_object":
        del e["npcEffect"]
    elif mutation == "null":
        e["npcEffect"] = None
    elif mutation == "foreign_leaf":
        e["npcEffect"]["buffId"] = 20
    elif mutation == "wrong_owner":
        e.update(action="apply_status_on_event", actionCode=2, buffId=20)
    elif mutation == "neutral":
        e["npcEffect"]["lifeRegenPenalty"] = 0
    elif mutation == "chance_range":
        e["npcEffect"]["chance"] = 1.01
    elif mutation == "chance_type":
        e["npcEffect"]["chance"] = True
    elif mutation == "duration_float":
        e["durationTicks"] = 1.5
    else:
        next(entity for entity in wire["runtimeProgram"]["entities"] if entity.get("events"))["damage"]["enabled"] = False
    before = deepcopy(wire)
    assert not validate_runtime_wire(wire)["ok"]
    assert wire == before


@pytest.mark.parametrize("mutation", ["remove", "duplicate", "wrong_source", "wrong_event", "forged_quantity"])
def test_source_free_receipts_authenticate_each_npc_modifier(mutation):
    wire = check(document(chancePercent=25))
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    row = next(r for r in receipts if r["finalPath"].endswith(".npcEffect.lifeRegenPenalty"))
    if mutation == "remove":
        receipts.remove(row)
    elif mutation == "duplicate":
        receipts.append(deepcopy(row))
    elif mutation == "wrong_source":
        row["authoredPath"] = row["authoredPath"].replace("damagePerSecond", "defenseDelta")
    elif mutation == "wrong_event":
        event(wire)["id"] = "not_the_call"
    else:
        row["value"] = event(wire)["npcEffect"]["lifeRegenPenalty"] = 401
    assert not audit_compiler_receipts(receipts, final_document=wire)["ok"]
    assert not validate_runtime_wire(wire)["ok"]


def test_native_id_wire_without_new_object_remains_readable():
    old = compile_runtime_program(build_capability_witness("apply_status_on_event"))
    assert "npcEffect" not in event(old)
    assert validate_runtime_wire(old)["ok"]
    old.pop("runtimeContract")
    assert validate_runtime_wire(old)["ok"]


def test_registry_provider_and_witness_cover_new_action():
    cap = CAPABILITY_REGISTRY[FN]
    assert cap.params["durationSeconds"].maximum == 60
    variant = next(r for r in capability_provider_union() if r["properties"]["fn"]["const"] == FN)
    assert variant["properties"]["params"]["properties"]["damagePerSecond"]["multipleOf"] == 0.5
    assert cap.wire_components == {"npcEffect": "RuntimeNpcEffectSpec"}
    check(build_capability_witness(FN))


@pytest.mark.parametrize("when,item", [("on_hit", False), ("on_crit", False), ("on_hit", True), ("on_crit", True)])
def test_real_hit_sources_admit_both_hit_events(when, item):
    doc = document(when=when)
    if item:
        call = deepcopy(next(c for c in doc["runtimeProgram"]["calls"] if c["id"] == "witness_call"))
        doc = build_capability_witness("configure_item_contact_hitbox")
        next(c for c in doc["runtimeProgram"]["calls"] if c["id"] == "witness_call")["id"] = "base_contact"
        next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"]["disableMeleeHitbox"] = False
        call["target"] = "item"
        doc["runtimeProgram"]["calls"].append(call)
    wire = check(doc)
    assert event(wire)["event"] == when


def test_omitted_neutrals_have_exact_receipts_and_no_input_mutation():
    doc = document()
    wire = check(doc)
    assert event(wire)["npcEffect"] == {"lifeRegenPenalty": 15, "defenseDelta": 0,
        "contactDamageMultiplier": 1, "velocityRetentionPerTick": 1, "chance": 1}
    receipts = [r for r in wire["runtimeContract"]["finalWireReceipts"] if r.get("callId") == "witness_call"]
    for field in ("defenseDelta", "contactDamageMultiplier", "velocityRetentionPerTick", "chance"):
        row = next(r for r in receipts if r["finalPath"].endswith(".npcEffect." + field))
        assert row["status"] == "declared_neutral_omission"
    assert "chancePercent" not in next(c for c in doc["runtimeProgram"]["calls"] if c["id"] == "witness_call")["params"]


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_actual_offline_author_request_transports_typed_composition(monkeypatch, mode):
    from repair_test_helpers import provider_roundtrip
    from infini_local.core import llm_config
    from infini_local.pipelines import llm_authoring_pipeline as author
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    request, user, _ = author.build_initial_author_request({}, {}, "numeric NPC effects", model_name="offline")
    request = json.loads(json.dumps(request))
    card = next(c for c in json.loads(user)["runtimeCapabilityContract"]["catalog"]["capabilities"] if c["fn"] == FN)
    assert card["params"]["damagePerSecond"]["max"] == 200
    assert card["params"]["chancePercent"]["max"] == 100
    assert "before" in card["params"]["chancePercent"]["meaning"].lower()
    parsed = provider_roundtrip(document(chancePercent=25), request["response_format"])
    assert event(check(parsed))["npcEffect"]["chance"] == 0.25
