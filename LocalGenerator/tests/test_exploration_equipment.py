"""Independent exploration equipment: real Author/wire/Repair delivery."""
from copy import deepcopy
import pytest
from jsonschema import Draft202012Validator
from test_equipment_native_utilities import fixture
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.pipelines.author_item_contract import author_item_response_schema

SYSTEMS = [
    {'treasureVision': True, 'dangerVision': True, 'creatureVision': True, 'nightVision': True},
    {'lifePickup': True, 'manaPickup': True, 'coinPickup': True, 'treasurePickup': True},
    {"fishingPower": 25, "fishingLine": True, "lavaFishing": True, "fishingSonar": True, "fishingCrates": True},
]

@pytest.mark.parametrize("params", SYSTEMS)
def test_exploration_system_exact_delivery_and_frozen_repair(params):
    doc, call = fixture(deepcopy(params))
    assert Draft202012Validator(author_item_response_schema()).is_valid(doc)
    assert validate_runtime_program(doc)["ok"]
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(receipts, authored_document=doc, final_document=wire)["ok"]
    for field, value in params.items():
        assert wire["accessory"][field] == value
        matching = [r for r in receipts if r.get("callId") == call["id"] and r.get("finalPath") == "accessory." + field]
        assert len(matching) == 1 and matching[0]["value"] == value
        corrupt = deepcopy(wire)
        corrupt["runtimeContract"]["finalWireReceipts"].remove(matching[0])
        assert not validate_runtime_wire(corrupt)["ok"]
        delivered = deepcopy(wire); delivered.pop("runtimeContract"); delivered["accessory"][field] = None
        assert not validate_runtime_wire(delivered)["ok"]
    field = next(iter(params))
    call["params"][field] = None
    errors = validate_runtime_program(doc)["errors"]
    scope = build_runtime_repair_scope(doc, errors)
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params." + field]}]
    changed = deepcopy(call); changed["params"] = {**params, "defensePoints": 99}
    patch = {"note": "repair exact invalid leaf", "callsUpsert": [changed]}
    filtered, audit = filter_repair_patch_scope(doc, patch, scope)
    assert audit["ok"] and audit["ignoredChanges"], audit
    # All unauthorized sibling additions remain absent after the real frozen merge.
    repaired = apply_repair_patch(doc, filtered)
    assert validate_runtime_program(repaired)["ok"]
    repaired_call = next(c for c in repaired["runtimeProgram"]["calls"] if c["id"] == call["id"])
    assert repaired_call["params"] == params

@pytest.mark.parametrize("params", SYSTEMS)
@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_exploration_actual_author_packet_and_omission(monkeypatch, params, mode):
    from test_source_unit_guidance import _author_request, _repair_request, _source, _offline
    getattr(_offline, "__wrapped__")(monkeypatch)
    _, packet = _author_request(monkeypatch, mode, _source())
    card = next(c for c in packet["runtimeCapabilityContract"]["catalog"]["capabilities"] if c["fn"] == "configure_accessory")
    assert all(field in card["params"] for field in params)
    doc, _ = fixture({"defensePoints": 1})
    wire = compile_runtime_program(doc)
    assert set(params).isdisjoint(wire["accessory"])
    doc["name"] = "Fishing Magnet of Survival"
    assert compile_runtime_program(doc)["accessory"] == wire["accessory"]

    broken, broken_call = fixture(deepcopy(params))
    bad_field = next(iter(params))
    broken_call["params"][bad_field] = None
    _, repair = _repair_request(monkeypatch, mode, _source(), broken)
    assert repair["repairScope"]["fieldPermissions"]["calls"] == [{"id": broken_call["id"], "paths": ["params." + bad_field]}]
    repair_card = next(c for c in repair["existingBrokenCapabilityCards"] if c["fn"] == "configure_accessory")
    assert all(field in repair_card["params"] for field in params)
    from test_codex_subscription_contract import _encode_nullable_fixture
    from infini_local.pipelines import author_item_contract as contract
    schema = contract.author_item_response_schema()
    provider = contract.author_item_provider_response_schema()
    encoded = _encode_nullable_fixture(doc, schema)
    assert Draft202012Validator(provider).is_valid(encoded)
    restored = contract.project_provider_author_item_to_local(encoded, response_format={"type": "json_schema", "json_schema": {"schema": provider}})
    assert restored == doc
