"""Live-parent combat is an explicit producer choice with exact retained provenance."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, apply_repair_patch, compile_runtime_program,
    filter_repair_patch_scope, validate_runtime_program, validate_runtime_wire,
)
from infini_local.core.runtime_authoring.program_schema import strict_author_shape_report
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.pipelines import author_item_contract as contract
from infini_local.qa.capability_witnesses import build_capability_witness
from test_codex_subscription_contract import _encode_nullable_fixture


_PRODUCERS = ("spawn_entity_on_event", "target_and_fire")
_BASES = ("authored_child", "live_parent")
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
    assert validate_runtime_program(source)["ok"]
    before = deepcopy(source)
    encoded = _encode_nullable_fixture(source, contract.author_item_response_schema()) if mode == "json_schema" else source
    serialized = json.dumps(encoded, ensure_ascii=False)
    restored = contract.project_provider_author_item_to_local(json.loads(serialized), response_format=request["response_format"])
    assert restored == source
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
    assert audit_compiler_receipts(rows, authored_document=source, final_document=wire)["ok"]
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


@pytest.mark.parametrize("fn,leaf,invalid", [
    ("target_and_fire", "damageBasis", "parent"), ("target_and_fire", "count", 5),
    ("spawn_entity_on_event", "damageMultiplier", True),
    ("channel_beam", "initialWidthMultiplier", 0), ("set_descendant_concurrency", "maxActive", 0),
])
def test_combined_combat_leaf_repair_keeps_all_accepted_main_and_parent_choices_frozen(fn, leaf, invalid):
    good = _accepted_main_combat_composition()
    broken = deepcopy(good)
    call = _call(broken, fn)
    call["params"][leaf] = invalid
    before = deepcopy(broken)
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params." + leaf]}]
    hostile = deepcopy(good["runtimeProgram"]["calls"])
    for row in hostile:
        for key, value in tuple(row["params"].items()):
            if row["id"] == call["id"] and key == leaf:
                continue
            spec = CAPABILITY_REGISTRY[row["fn"]].params[key]
            if type(value) is bool:
                row["params"][key] = not value
            elif spec.enum and len(spec.enum) > 1:
                row["params"][key] = next(option for option in spec.enum if option != value)
            elif type(value) in (int, float):
                alternate = spec.maximum if value == spec.minimum else spec.minimum
                if alternate is not None:
                    row["params"][key] = type(value)(alternate)
    filtered, audit = filter_repair_patch_scope(broken, {"note": "exact combined leaf", "callsUpsert": hostile}, scope)
    assert audit["ok"] and audit["ignoredChanges"], audit
    repaired = apply_repair_patch(broken, filtered)
    assert repaired == good and broken == before
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]


def _call(document, fn):
    return next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == fn)


def _wire_component(wire, call):
    entity = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == call["target"])
    return (next(row for row in entity["events"] if row["id"] == call["id"])
            if call["fn"] == "spawn_entity_on_event" else entity["targeting"])


@pytest.mark.parametrize("fn", _PRODUCERS)
@pytest.mark.parametrize("damage_basis", _BASES)
@pytest.mark.parametrize("knockback_basis", _BASES)
@pytest.mark.parametrize("multiplier", [0, 0.5, 1, 4])
def test_combat_choices_reach_exact_component_provider_inverse_and_receipts(fn, damage_basis, knockback_basis, multiplier):
    authored = build_capability_witness(fn)
    call = _call(authored, fn)
    call["params"].update(damageBasis=damage_basis, knockbackBasis=knockback_basis, damageMultiplier=multiplier)
    before = deepcopy(authored)
    assert strict_author_shape_report(authored)["ok"]
    assert validate_runtime_program(authored)["ok"]
    schema = contract.author_item_response_schema()
    provider = contract.author_item_provider_response_schema()
    encoded = _encode_nullable_fixture(authored, schema)
    assert Draft202012Validator(provider).is_valid(encoded)
    restored = contract.project_provider_author_item_to_local(encoded, response_format={
        "type": "json_schema", "json_schema": {"schema": provider},
    })
    assert restored == authored
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


@pytest.mark.parametrize("fn", _PRODUCERS)
@pytest.mark.parametrize("name", ["damageBasis", "knockbackBasis"])
@pytest.mark.parametrize("invalid", [None, True, 0, "Live_Parent", " live_parent", "parent", {}, []])
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
    expected = call["params"].pop(name)
    before = deepcopy(document)
    report = validate_runtime_program(document)
    assert not report["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(document)
    scope = build_runtime_repair_scope(document, report["errors"])
    permissions = next(row for row in scope["fieldPermissions"]["calls"] if row["id"] == call["id"])
    assert permissions["paths"] == ["params." + name]
    candidate = deepcopy(call)
    candidate["target"] = "item"
    candidate["params"][name] = expected
    candidate["params"]["damageMultiplier" if name != "damageMultiplier" else "intervalTicks"] = 3
    filtered, audit = filter_repair_patch_scope(document, {"note": "fill exact missing choice", "callsUpsert": [candidate]}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    repaired = apply_repair_patch(document, filtered)
    wanted = deepcopy(before)
    _call(wanted, fn)["params"][name] = expected
    assert repaired == wanted
    assert validate_runtime_program(repaired)["ok"]
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    assert document == before


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


@pytest.mark.parametrize("fn,name", [(fn, name) for fn in _PRODUCERS for name in ("damageBasis", "knockbackBasis")]
                         + [("target_and_fire", "damageMultiplier")])
@pytest.mark.parametrize("mutation", ["drop", "duplicate", "wrong-call", "wrong-source", "swap-equal-bases"])
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


def test_saved_wire_and_all_old_receipts_remain_exact_without_new_choices():
    raw = _RETAINED.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "cfddf2ae287f30d5bbe6dfb2a30f3c5db4fec72e65e304315e811905912e3ced"
    archive = json.loads(raw)
    assert archive["capturedBase"] == "9a9ebd520212dd902640029836f897c5a502b2e7"
    for case in archive["cases"]:
        wire = case["wire"]
        before = deepcopy(wire)
        assert validate_runtime_wire(wire)["ok"]
        assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)["ok"]
        assert wire == before
        for entity in wire["runtimeProgram"]["entities"]:
            assert "damageBasis" not in entity.get("targeting", {})
            for event in entity["events"]:
                assert "damageBasis" not in event and "knockbackBasis" not in event
        # An unreceipted live-parent selector is not a saved-wire default.
        if case["capability"] == "target_and_fire":
            component = next(entity["targeting"] for entity in wire["runtimeProgram"]["entities"] if entity.get("targeting"))
        else:
            component = next(event for entity in wire["runtimeProgram"]["entities"] for event in entity["events"] if event["action"] == "spawn_entity_on_event")
        component["damageBasis"] = "live_parent"
        assert not validate_runtime_wire(wire)["ok"]
    assert hashlib.sha256(_RETAINED.read_bytes()).digest() == hashlib.sha256(raw).digest()


def test_registry_and_prompt_explain_actual_parent_timing_without_hit_damage_or_class_reapplication():
    for fn in _PRODUCERS:
        cap = CAPABILITY_REGISTRY[fn]
        for name in ("damageBasis", "knockbackBasis"):
            assert cap.params[name].required and cap.params[name].default is None
            assert cap.params[name].wire_presence_requires_receipt
            assert cap.prompt_card()["params"][name]["enum"] == list(_BASES)
        assert "player/class modifiers" in cap.prompt_card()["does"]
    assert "snapshot" in CAPABILITY_REGISTRY["spawn_entity_on_event"].prompt_card()["does"]
    assert "authored" in CAPABILITY_REGISTRY["damage_area_on_event"].params["damageMultiplier"].description
    assert "authored" in CAPABILITY_REGISTRY["chain_damage_on_event"].params["damageMultiplier"].description


@pytest.mark.parametrize("mutation", ["valid", "comment-only", "null-allowed", "nonfinite-allowed", "wrong-storage", "changed-upper-bound"])
def test_targeting_multiplier_audit_reads_the_real_strict_nullable_setter(mutation):
    from infini_local.qa.primitive_loss_audit import nullable_number_rejection_bounds
    path = Path(__file__).resolve().parents[2] / "ModSources/InfiniCrafterLocal/Common/Models/RuntimeProgramSpec.cs"
    source = path.read_bytes()
    if mutation == "comment-only":
        source = source.replace(b"if (value is not float multiplier || !float.IsFinite(multiplier) || multiplier < 0f || multiplier > 4f)",
                                b"// if (value is not float multiplier || !float.IsFinite(multiplier) || multiplier < 0f || multiplier > 4f)\n if (false)")
    elif mutation == "null-allowed":
        source = source.replace(b"value is not float multiplier || ", b"")
    elif mutation == "nonfinite-allowed":
        source = source.replace(b"!float.IsFinite(multiplier) || ", b"")
    elif mutation == "wrong-storage":
        source = source.replace(b"_damageMultiplier = multiplier;", b"_damageMultiplier = 1f;")
    elif mutation == "changed-upper-bound":
        source = source.replace(b"multiplier > 4f", b"multiplier > 3f")
    result = nullable_number_rejection_bounds(source, "RuntimeTargetingSpec", "DamageMultiplier")
    if mutation == "valid":
        assert result == [0, 4]
    elif mutation == "changed-upper-bound":
        assert result == [0, 3] and result != [0, 4]
    else:
        assert result is None
