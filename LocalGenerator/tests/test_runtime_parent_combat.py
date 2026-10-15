"""Live-parent combat is an explicit producer choice with exact retained provenance."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
from repair_test_helpers import frozen_call_repair, provider_roundtrip

from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.repair_scope import filter_repair_patch_scope
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.program_schema import strict_author_shape_report
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.pipelines import author_item_contract as contract
from infini_local.qa.capability_witnesses import build_capability_witness


_PRODUCERS = ("spawn_entity_on_event", "target_and_fire")
_RETAINED = Path(__file__).with_name("fixtures") / "parent_combat_retained_wire.json"


def _accepted_main_combat_composition(damage_basis="live_parent", knockback_basis="authored_child", multiplier=0.5):
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture

    document = build_runtime_fixture("held_and_deployed")
    calls = document["runtimeProgram"]["calls"]
    held = next(row for row in calls if row.get("target") == "held_lantern_pike" and row["fn"] == "move_forward_then_retract")
    held.update(fn="channel_beam", params={
        "rangeTiles": 20, "widthPx": 12, "warmupTicks": 12, "manaPayment": "each_use_time",
        "initialDamageMultiplier": 0.35, "initialWidthMultiplier": 0.22,
        "damageStartProgress": 0.08, "raycastTiles": True,
    })
    _call(document, "configure_item_use")["params"]["channel"] = True
    _call(document, "target_and_fire")["params"].update(
        damageBasis=damage_basis, knockbackBasis=knockback_basis, damageMultiplier=multiplier,
        count=4, spreadRadians=0.6, targetPolicy="player_assigned_first", requireLineOfSight=True, hardRange=True,
    )
    calls.extend([
        {"id": "ammo", "fn": "configure_weapon_ammo",
         "params": {"ammoCategory": "arrow", "speedBasis": "native_shot"}},
        {"id": "native", "fn": "set_projectile_sentry", "target": "deployed_lantern", "params": {"enabled": True}},
        {"id": "pool", "fn": "set_descendant_concurrency", "target": "deployed_lantern", "params": {"maxActive": 12}},
        {"id": "shot_event", "fn": "spawn_entity_on_event", "target": "deployed_lantern", "params": {
            "when": {"everyTicks": 90}, "entity": "lantern_bolt", "count": 2, "spreadRadians": 0.5,
            "damageBasis": damage_basis, "knockbackBasis": knockback_basis,
            "damageMultiplier": multiplier, "delayTicks": 3,
        }},
    ])
    return document


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("damage_basis,knockback_basis,multiplier", [
    ("authored_child", "authored_child", 0), ("authored_child", "live_parent", 0.5),
    ("live_parent", "authored_child", 1), ("live_parent", "live_parent", 4),
])
def test_parent_combat_composes_with_accepted_volley_ammo_lifecycle_beam_through_serialized_provider(
    monkeypatch, mode, damage_basis, knockback_basis, multiplier,
):
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request

    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    request, user, _ = build_initial_author_request({}, {}, {}, {}, "combined-combat", model_name="test-model")
    packet = json.loads(user)
    names = {card["fn"] for card in packet["runtimeCapabilityContract"]["catalog"]["capabilities"]}
    source = _accepted_main_combat_composition(damage_basis, knockback_basis, multiplier)
    assert {"target_and_fire", "configure_weapon_ammo", "set_projectile_sentry", "set_descendant_concurrency", "channel_beam"} <= names
    before = deepcopy(source)
    restored = provider_roundtrip(source, request["response_format"])
    wire = compile_runtime_program(restored)
    assert validate_runtime_wire(wire)["ok"]
    assert wire["runtimeProgram"]["weaponAmmo"] == {"ammoCategory": "arrow", "speedBasis": "native_shot"}
    turret = next(entity for entity in wire["runtimeProgram"]["entities"] if entity["id"] == "deployed_lantern")
    assert turret["nativeSentry"] is True and turret["spawn"]["descendantMaxActive"] == 12
    assert turret["targeting"]["count"] == 4 and turret["targeting"]["spreadRadians"] == 0.6
    for fn in _PRODUCERS:
        call = _call(source, fn)
        component = _wire_component(wire, call)
        assert {name: component[name] for name in ("damageBasis", "knockbackBasis", "damageMultiplier")} == {
            "damageBasis": damage_basis, "knockbackBasis": knockback_basis, "damageMultiplier": multiplier,
        }
    beam = next(entity for entity in wire["runtimeProgram"]["entities"] if entity["id"] == "held_lantern_pike")
    assert beam["controller"]["params"]["manaPayment"] == "each_use_time"
    assert beam["controller"]["params"]["raycastTiles"] is True
    rows = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(rows, final_document=wire)["ok"]
    assert source == before


@pytest.mark.parametrize("mutation", ["source_pool_target", "source_event_target", "final_event_id", "drop_combat_receipt", "drop_all_targeting_receipts"])
def test_combined_combat_keeps_source_identity_and_exact_present_wire_receipt_guards(mutation):
    source = _accepted_main_combat_composition()
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    if mutation == "source_pool_target":
        _call(source, "set_descendant_concurrency")["target"] = "lantern_bolt"
        assert validate_runtime_program(source)["ok"]
    elif mutation == "source_event_target":
        _call(source, "spawn_entity_on_event")["target"] = "held_lantern_pike"
        assert validate_runtime_program(source)["ok"]
    elif mutation == "final_event_id":
        _wire_component(wire, _call(source, "spawn_entity_on_event"))["id"] = "different_valid_event_id"
    elif mutation == "drop_combat_receipt":
        rows[:] = [row for row in rows if not (row.get("fn") == "target_and_fire"
                   and row.get("authoredPath", "").endswith(".params.damageBasis"))]
    else:
        rows[:] = [row for row in rows if row.get("fn") != "target_and_fire"]
    assert not audit_compiler_receipts(rows, authored_document=source, final_document=wire)["ok"]
    if not mutation.startswith("source_"):
        assert not audit_compiler_receipts(rows, final_document=wire)["ok"]
        assert not validate_runtime_wire(wire)["ok"]


def _call(document, fn):
    return next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == fn)


def _wire_component(wire, call):
    entity = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == call["target"])
    return (next(row for row in entity["events"] if row["id"] == call["id"])
            if call["fn"] == "spawn_entity_on_event" else entity["targeting"])


# Both producers share the scalar owner. RuntimeChildCombat.TryResolve selects
# damage and knockback independently; retain all four basis pairs for EACH
# producer, plus 0/interior/identity/upper-bound multiplier wiring for each.
@pytest.mark.parametrize("fn", _PRODUCERS)
@pytest.mark.parametrize("damage_basis,knockback_basis,multiplier", [
    pytest.param("authored_child", "authored_child", 0, id="authored-zero"),
    pytest.param("authored_child", "live_parent", 0.5, id="parent-knockback-half"),
    pytest.param("live_parent", "authored_child", 1, id="parent-damage-identity"),
    pytest.param("live_parent", "live_parent", 4, id="both-parent-maximum"),
    pytest.param("live_parent", "live_parent", 0, id="parent-zero-is-not-authored-fallback"),
])
def test_combat_choices_reach_exact_component_provider_inverse_and_receipts(fn, damage_basis, knockback_basis, multiplier):
    authored = build_capability_witness(fn)
    call = _call(authored, fn)
    call["params"].update(damageBasis=damage_basis, knockbackBasis=knockback_basis, damageMultiplier=multiplier)
    before = deepcopy(authored)
    assert strict_author_shape_report(authored)["ok"]
    restored = provider_roundtrip(authored, {
        "type": "json_schema", "json_schema": {"schema": contract.author_item_provider_response_schema()},
    })
    compiled = compile_runtime_program(restored)
    assert validate_runtime_wire(compiled)["ok"]
    component = _wire_component(compiled, call)
    for name, expected in (("damageBasis", damage_basis), ("knockbackBasis", knockback_basis), ("damageMultiplier", multiplier)):
        assert component[name] == expected
        receipts = [row for row in compiled["runtimeContract"]["finalWireReceipts"]
                    if row.get("callId") == call["id"] and row.get("authoredPath", "").endswith(".params." + name)]
        assert len(receipts) == 1 and receipts[0]["status"] == "delivered"
        assert receipts[0]["value"] == expected and receipts[0]["finalPath"].endswith("." + name)
    assert audit_compiler_receipts(compiled["runtimeContract"]["finalWireReceipts"],
                                   authored_document=authored, final_document=compiled)["ok"]
    assert authored == before


# Both independent producer consumers and both scalar destinations, without a
# producer x field x JSON-type product owned by the shared enum validator.
@pytest.mark.parametrize("fn,name,invalid", [
    ("spawn_entity_on_event", "damageBasis", None),
    ("spawn_entity_on_event", "knockbackBasis", True),
    ("target_and_fire", "damageBasis", "Live_Parent"),
    ("target_and_fire", "knockbackBasis", " live_parent"),
    ("target_and_fire", "damageBasis", {}),
])
def test_present_basis_is_exact_in_author_and_saved_wire(fn, name, invalid):
    authored = build_capability_witness(fn)
    call = _call(authored, fn)
    wire = compile_runtime_program(authored)
    call["params"][name] = deepcopy(invalid)
    assert not strict_author_shape_report(authored)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(authored)
    _wire_component(wire, call)[name] = deepcopy(invalid)
    # Even an amended receipt cannot make an invalid typed value admissible.
    for row in wire["runtimeContract"]["finalWireReceipts"]:
        if row.get("callId") == call["id"] and row.get("finalPath", "").endswith("." + name):
            row["value"] = deepcopy(invalid)
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("fn,name", [(fn, name) for fn in _PRODUCERS for name in ("damageBasis", "knockbackBasis")]
                         + [("target_and_fire", "damageMultiplier")])
def test_fresh_missing_choice_requires_leaf_repair_without_reauthoring_valid_siblings(fn, name):
    document = build_capability_witness(fn)
    call = _call(document, fn)
    expected = deepcopy(document)
    value = call["params"].pop(name)
    with pytest.raises(ValueError):
        compile_runtime_program(document)
    candidate = deepcopy(call)
    candidate["target"] = "item"
    candidate["params"][name] = value
    candidate["params"]["damageMultiplier" if name != "damageMultiplier" else "intervalTicks"] = 3
    repaired, final = frozen_call_repair(document, [candidate],
        [{"id": call["id"], "paths": ["params." + name]}], expected, note="fill exact missing choice")
    assert _wire_component(final, call)[name] == value


@pytest.mark.parametrize("name", ["damageBasis", "knockbackBasis"])
def test_item_body_live_parent_reports_and_repairs_only_the_selected_basis(name):
    document = build_capability_witness("spawn_entity_on_event")
    call = _call(document, "spawn_entity_on_event")
    call["target"] = "item"
    call["params"].update(when="on_use", **{name: "live_parent"})
    report = validate_runtime_program(document)
    errors = [row for row in report["errors"] if row["code"] == "unsupported_param_target_kind"]
    assert len(errors) == 1 and errors[0]["path"].endswith(".params." + name)
    assert errors[0]["allowed"] == ["authored_child"]
    scope = build_runtime_repair_scope(document, report["errors"])
    assert next(row["paths"] for row in scope["fieldPermissions"]["calls"] if row["id"] == call["id"]) == ["params." + name]
    candidate = deepcopy(call)
    candidate["params"][name] = "authored_child"
    candidate["params"]["count"] = 11
    patch, audit = filter_repair_patch_scope(document, {"note": "explicit item source", "callsUpsert": [candidate]}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    repaired = apply_repair_patch(document, patch)
    assert _call(repaired, "spawn_entity_on_event")["params"]["count"] == call["params"]["count"]
    assert validate_runtime_program(repaired)["ok"]
    wire = compile_runtime_program(repaired)
    assert validate_runtime_wire(wire)["ok"]
    _wire_component(wire, call)[name] = "live_parent"
    assert any(row["code"] == "unsupported_param_target_kind" for row in validate_runtime_wire(wire)["errors"])


@pytest.mark.parametrize("fn,name,mutation", [
    ("spawn_entity_on_event", "damageBasis", "drop"),
    ("spawn_entity_on_event", "knockbackBasis", "duplicate"),
    ("target_and_fire", "damageMultiplier", "wrong-call"),
    ("target_and_fire", "damageBasis", "wrong-source"),
    ("target_and_fire", "knockbackBasis", "swap-equal-bases"),
    ("target_and_fire", "damageMultiplier", "swap-equal-bases"),
])
def test_new_wire_presence_requires_exact_unique_owned_provenance(fn, name, mutation):
    document = build_capability_witness(fn)
    call = _call(document, fn)
    wire = compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    selected = next(row for row in receipts if row.get("callId") == call["id"] and row.get("authoredPath", "").endswith(".params." + name))
    if mutation == "drop":
        receipts.remove(selected)
    elif mutation == "duplicate":
        receipts.append(deepcopy(selected))
    elif mutation == "wrong-call":
        selected["callId"] = "some_other_call"
    elif mutation == "wrong-source":
        selected["authoredPath"] = selected["authoredPath"].rsplit(".", 1)[0] + ".count"
    else:
        if name == "damageMultiplier":
            selected["finalPath"] = selected["finalPath"].rsplit(".", 1)[0] + ".intervalTicks"
        else:
            other_name = "damageBasis" if name == "knockbackBasis" else "knockbackBasis"
            other = next(row for row in receipts if row.get("callId") == call["id"] and row.get("authoredPath", "").endswith(".params." + other_name))
            selected["finalPath"], other["finalPath"] = other["finalPath"], selected["finalPath"]
    for source in (None, document):
        report = audit_compiler_receipts(receipts, authored_document=source, final_document=wire)
        assert not report["ok"], report
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("fn", _PRODUCERS)
@pytest.mark.parametrize("mutation", ["name-only", "code-only", "both", "boolean-code"])
def test_present_combat_selector_requires_the_exact_runtime_consumer_even_with_amended_receipts(fn, mutation):
    document = build_capability_witness(fn)
    call = _call(document, fn)
    wire = compile_runtime_program(document)
    entity = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == call["target"])
    if fn == "spawn_entity_on_event":
        consumer = _wire_component(wire, call)
        name_key, code_key, other_name, other_code = "action", "actionCode", "chain_damage_on_event", 4
    else:
        consumer = entity["controller"]
        name_key, code_key, other_name, other_code = "name", "code", "charge_then_release", 2
    if mutation in {"name-only", "both"}:
        consumer[name_key] = other_name
    if mutation in {"code-only", "both", "boolean-code"}:
        consumer[code_key] = True if mutation == "boolean-code" else other_code
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    for receipt in receipts:
        if receipt.get("callId") == call["id"] and receipt.get("authoredPath", "").endswith(".fn"):
            for key in (name_key, code_key):
                if receipt["finalPath"].endswith("." + key):
                    receipt["value"] = consumer[key]
    for source in (None, document):
        assert not audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
    assert not validate_runtime_wire(wire)["ok"]
    # Delivery omits diagnostic receipts; the strict wire consumer guard remains.
    wire.pop("runtimeContract")
    assert not validate_runtime_wire(wire)["ok"]


def test_archived_old_receipts_refuse_without_mutating_frozen_saved_wire():
    raw = _RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "cfddf2ae287f30d5bbe6dfb2a30f3c5db4fec72e65e304315e811905912e3ced"
    archive = json.loads(raw)
    assert archive["capturedBase"] == "9a9ebd520212dd902640029836f897c5a502b2e7"
    for case in archive["cases"]:
        wire = case["wire"]
        before = deepcopy(wire)
        report = validate_runtime_wire(wire)
        assert not report["ok"]
        assert any(row["code"] == "undeclared_technical_lowering" for row in report["errors"])
        assert not audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)["ok"]
        assert wire == before
        for entity in wire["runtimeProgram"]["entities"]:
            assert "damageBasis" not in entity.get("targeting", {})
            for event in entity["events"]:
                assert "damageBasis" not in event and "knockbackBasis" not in event
        # Current equivalents still compile with accepted provenance; a live-parent
        # selector cannot be injected without its own modern receipt.
        authored = build_capability_witness(case["capability"])
        current = compile_runtime_program(authored)
        assert validate_runtime_wire(current)["ok"]
        assert audit_compiler_receipts(current["runtimeContract"]["finalWireReceipts"],
                                       authored_document=authored, final_document=current)["ok"]
        if case["capability"] == "target_and_fire":
            component = next(entity["targeting"] for entity in current["runtimeProgram"]["entities"] if entity.get("targeting"))
        else:
            component = next(event for entity in current["runtimeProgram"]["entities"] for event in entity["events"] if event["action"] == "spawn_entity_on_event")
        component["damageBasis"] = "live_parent"
        assert not validate_runtime_wire(current)["ok"]
    assert hashlib.sha256(_RETAINED.read_bytes()).digest() == hashlib.sha256(raw).digest()
