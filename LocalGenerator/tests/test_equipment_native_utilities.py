"""Independent equipment flags, not source-item presets."""
from copy import deepcopy
from infini_local.core.runtime_authoring import apply_repair_patch, filter_repair_patch_scope
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope
import pytest
from infini_local.core.runtime_authoring import (
    compile_runtime_program, validate_runtime_program, validate_runtime_wire,
)
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness


@pytest.mark.parametrize("field,valid,invalid", [
    ("rocketBoots", [0, 1, 2, 3, 4, 5], [-1, 6, 1.5, True, None]),
    ("accRunSpeedPxPerTick", [0, 3, 6.75, 20], [-1, 20.00001, True, None]),
])
def test_bounded_native_number(field, valid, invalid):
    for value in valid:
        doc, _ = fixture({field: value, "defensePoints": 1})
        assert validate_runtime_program(doc)["ok"], "bounded native number must be authorable"
        wire = compile_runtime_program(doc)
        wire_field = "accRunSpeed" if field == "accRunSpeedPxPerTick" else field
        assert wire["accessory"][wire_field] == value
        assert validate_runtime_wire(wire)["ok"]
        delivered = deepcopy(wire)
        delivered.pop("runtimeContract")
        assert validate_runtime_wire(delivered)["ok"]
        invalid_wire = deepcopy(delivered)
        invalid_wire["accessory"][wire_field] = invalid[0]
        assert not validate_runtime_wire(invalid_wire)["ok"], "delivery must reject present invalid fields without receipts"
        receipts = wire["runtimeContract"]["finalWireReceipts"]
        assert audit_compiler_receipts(receipts, authored_document=doc, final_document=wire)["ok"]
        corrupt = deepcopy(wire)
        corrupt["accessory"][wire_field] = invalid[0]
        assert not validate_runtime_wire(corrupt)["ok"]
    for value in invalid:
        doc, _ = fixture({field: value, "defensePoints": 1})
        assert not validate_runtime_program(doc)["ok"]
        with pytest.raises(ValueError):
            compile_runtime_program(doc)


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_serialized_author_and_frozen_leaf_repair(monkeypatch, mode):
    from test_source_unit_guidance import _author_request, _repair_request, _source, _offline
    getattr(_offline, "__wrapped__")(monkeypatch)
    params = {"wireVision": True, "iceSkate": True, "noKnockback": True, "fireWalk": True,
              "rocketBoots": 3, "accRunSpeedPxPerTick": 6.75, "moveSpeedBonusPercent": 8,
              "defensePoints": 2}
    doc, call = fixture(params)
    from jsonschema import Draft202012Validator
    from test_codex_subscription_contract import _encode_nullable_fixture
    from infini_local.pipelines import author_item_contract as contract
    schema = contract.author_item_response_schema()
    provider = contract.author_item_provider_response_schema()
    encoded = _encode_nullable_fixture(doc, schema)
    assert Draft202012Validator(provider).is_valid(encoded)
    restored = contract.project_provider_author_item_to_local(encoded, response_format={"type": "json_schema", "json_schema": {"schema": provider}})
    assert restored == doc
    _, packet = _author_request(monkeypatch, mode, _source())
    card = next(c for c in packet["runtimeCapabilityContract"]["catalog"]["capabilities"] if c["fn"] == "configure_accessory")
    for field in params:
        assert field in card["params"]
    assert "NOT lava" in card["params"]["fireWalk"]["meaning"]
    assert "does not choose vanityRocketBoots" in card["params"]["rocketBoots"]["meaning"]
    call["params"]["rocketBoots"] = 6
    before = deepcopy(doc)
    _, repair_packet = _repair_request(monkeypatch, mode, _source(), doc)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params.rocketBoots"]}]
    assert repair_packet["repairScope"] == scope
    repair_card = next(c for c in repair_packet["existingBrokenCapabilityCards"] if c["fn"] == "configure_accessory")
    assert repair_card["params"]["rocketBoots"]["max"] == 5
    candidate = deepcopy(call)
    candidate["params"].update(rocketBoots=3, wireVision=False, defensePoints=200)
    candidate["params"]["lavaImmune"] = True
    filtered, audit = filter_repair_patch_scope(doc, {"note": "correct only rocket mode", "callsUpsert": [candidate]}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    repaired = apply_repair_patch(doc, filtered)
    expected = deepcopy(before)
    next(c for c in expected["runtimeProgram"]["calls"] if c["id"] == call["id"])["params"]["rocketBoots"] = 3
    assert repaired == expected and doc == before
    wire = compile_runtime_program(repaired)
    assert validate_runtime_wire(wire)["ok"]
    assert "lavaImmune" not in wire["accessory"]
    rows = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(rows, authored_document=repaired, final_document=wire)["ok"]


def test_omitted_utilities_and_names_do_not_author_mechanics():
    new_fields = {"wireVision", "iceSkate", "noKnockback", "fireWalk", "rocketBoots", "accRunSpeed"}
    doc, _ = fixture({"defensePoints": 1})
    wire = compile_runtime_program(doc)
    assert new_fields.isdisjoint(wire["accessory"])
    assert validate_runtime_wire(wire)["ok"]
    for name in ("Mechanical Lens", "Frostspark Boots", "Obsidian Shield"):
        named = deepcopy(doc)
        named["name"] = name
        compiled = compile_runtime_program(named)
        assert compiled["accessory"] == wire["accessory"]


def fixture(params):
    doc = build_capability_witness("configure_accessory")
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_accessory")
    call["params"] = params
    return doc, call


@pytest.mark.parametrize("field", ["wireVision", "iceSkate", "noKnockback", "fireWalk"])
def test_independent_native_flag(field):
    doc, call = fixture({field: True})
    assert validate_runtime_program(doc)["ok"], "native equipment flag must be authorable alone"
    wire = compile_runtime_program(doc)
    assert wire["accessory"][field] is True
    assert validate_runtime_wire(wire)["ok"]
    rows = wire["runtimeContract"]["finalWireReceipts"]
    receipt = next(r for r in rows if r.get("callId") == call["id"] and r.get("finalPath") == "accessory." + field)
    assert receipt["authoredPath"].endswith(".params." + field) and receipt["value"] is True
    assert audit_compiler_receipts(rows, authored_document=doc, final_document=wire)["ok"]
    wrong_owner = deepcopy(doc)
    next(c for c in wrong_owner["runtimeProgram"]["calls"] if c["id"] == call["id"])["target"] = "not_the_item"
    assert not audit_compiler_receipts(rows, authored_document=wrong_owner, final_document=wire)["ok"]
    missing_owner = deepcopy(wire)
    missing_owner["runtimeContract"]["finalWireReceipts"] = [r for r in rows if not (
        r.get("callId") == call["id"] and r.get("finalPath") == "accessory.enabled")]
    assert not validate_runtime_wire(missing_owner)["ok"]
    bad = deepcopy(wire)
    bad["runtimeContract"]["finalWireReceipts"].remove(receipt)
    assert not validate_runtime_wire(bad)["ok"]
    doc, _ = fixture({field: False, "defensePoints": 1})
    assert compile_runtime_program(doc)["accessory"][field] is False
    doc, _ = fixture({field: 1, "defensePoints": 1})
    assert not validate_runtime_program(doc)["ok"]
    delivered = deepcopy(wire)
    delivered.pop("runtimeContract")
    assert validate_runtime_wire(delivered)["ok"]
    delivered["accessory"][field] = 1
    assert not validate_runtime_wire(delivered)["ok"]
