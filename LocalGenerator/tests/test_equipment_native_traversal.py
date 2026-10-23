"""Composed native equipment contracts through Author, delivery and frozen Repair."""
from copy import deepcopy
import pytest
from test_equipment_native_utilities import fixture
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch

CASES = []
CASES.append({'jumpCloud': True, 'jumpBlizzard': True, 'jumpSandstorm': True, 'jumpFart': True, 'jumpTsunami': True})

@pytest.mark.parametrize("params", CASES)
def test_native_composition_delivery_and_frozen_repair(params, monkeypatch):
    from test_source_unit_guidance import _author_request, _source, _offline
    getattr(_offline, "__wrapped__")(monkeypatch)
    _, packet = _author_request(monkeypatch, "json_schema", _source())
    card = next(c for c in packet["runtimeCapabilityContract"]["catalog"]["capabilities"] if c["fn"] == "configure_accessory")
    assert params.keys() <= card["params"].keys()
    doc, call = fixture(deepcopy(params))
    assert validate_runtime_program(doc)["ok"]
    wire = compile_runtime_program(doc)
    assert all(wire["accessory"][k] == v for k,v in params.items())
    assert validate_runtime_wire(wire)["ok"]
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=doc, final_document=wire)["ok"]
    absent, _ = fixture({"defensePoints": 1})
    assert params.keys().isdisjoint(compile_runtime_program(absent)["accessory"])
    delivered = deepcopy(wire); delivered.pop("runtimeContract")
    field = next(iter(params)); delivered["accessory"][field] = None
    assert not validate_runtime_wire(delivered)["ok"]
    call["params"][field] = None
    errors = validate_runtime_program(doc)["errors"]
    assert errors
    scope = build_runtime_repair_scope(doc, errors)
    candidate = deepcopy(call); candidate["params"][field] = params[field]
    candidate["params"]["lavaImmune"] = True
    patch, audit = filter_repair_patch_scope(doc, {"note": "repair one invalid traversal leaf", "callsUpsert": [candidate]}, scope)
    repaired = apply_repair_patch(doc, patch)
    assert audit["ok"] and audit["ignoredChanges"]
    assert validate_runtime_program(repaired)["ok"]
    assert "lavaImmune" not in compile_runtime_program(repaired)["accessory"]
