"""Composed native equipment contracts through Author, delivery and frozen Repair."""
from copy import deepcopy
import pytest
from prompt_packet_helpers import request_dossier
from test_equipment_native_utilities import fixture
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch

CASES = []
CASES.append({'gravityControl': True, 'featherFall': True, 'extraFallTiles': 2})
CASES.append({'autoPaint': True, 'rulerGrid': True, 'buildRangeTiles': 2, 'tileSpeedBonusPercent': 2, 'wallSpeedBonusPercent': 2})
CASES.append({'autoJump': True, 'frogJump': True, 'wallGrip': 2})
CASES.append({'swimFlipper': True, 'divingHelm': True, 'underwaterBreathing': True, 'waterFloat': True})
CASES.append({'jumpCloud': True, 'jumpBlizzard': True, 'jumpSandstorm': True, 'jumpFart': True, 'jumpTsunami': True})

@pytest.mark.parametrize("params", CASES)
@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_native_composition_delivery_and_frozen_repair(params, format_mode, monkeypatch):
    from test_source_unit_guidance import _author_request, _source, _offline
    getattr(_offline, "__wrapped__")(monkeypatch)
    request, _ = _author_request(monkeypatch, format_mode, _source())
    packet = request_dossier(request)
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


@pytest.mark.parametrize("field,value", [(field, value) for group in CASES for field, value in group.items()])
def test_each_traversal_leaf_has_independent_strict_delivery(field, value):
    doc, _ = fixture({field: value})
    assert validate_runtime_program(doc)["ok"]
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    delivered = deepcopy(wire)
    delivered.pop("runtimeContract")
    assert validate_runtime_wire(delivered)["ok"]
    # Neutral explicit choices coexist with unrelated equipment stats, without
    # granting any of the other traversal abilities.
    neutral, _ = fixture({field: False if isinstance(value, bool) else 0, "defensePoints": 1})
    neutral_wire = compile_runtime_program(neutral)
    assert neutral_wire["accessory"][field] == (False if isinstance(value, bool) else 0)
    leaves = {name for group in CASES for name in group}
    assert (leaves - {field}).isdisjoint(neutral_wire["accessory"])
    for malformed in (None, "true" if isinstance(value, bool) else "2", 1 if isinstance(value, bool) else True):
        rejected = deepcopy(delivered)
        rejected["accessory"][field] = malformed
        assert not validate_runtime_wire(rejected)["ok"]
