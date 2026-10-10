"""Signed acceleration is an explicit Author choice over the existing native opcode."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, apply_repair_patch, build_runtime_repair_scope,
    capability_provider_union, compact_capability_catalog, compile_runtime_program,
    filter_repair_patch_scope, validate_runtime_program, validate_runtime_wire,
)
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness


FN = "move_gravity_arc"
PARAM = "gravityVelocityPerUpdate"


def selected(document, fn=FN):
    return next(call for call in document["runtimeProgram"]["calls"] if call["fn"] == fn)


@pytest.mark.parametrize("value", [-2, -0.1875, -0.001, -1e-40, 0, 1e-40, 0.001, 0.1875, 2])
@pytest.mark.parametrize("updates", [1, 2, 6])
def test_signed_values_reach_the_same_wire_and_exact_receipts(value, updates):
    document = build_capability_witness(FN)
    call = selected(document)
    call["params"][PARAM] = value
    selected(document, "set_projectile_collision")["params"]["updatesPerTick"] = updates
    assert validate_runtime_program(document)["ok"]
    wire = compile_runtime_program(document)
    entity = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == call["target"])
    assert entity["movement"] == {"name": FN, "code": 2, "params": {"gravityPerTick": value}}
    assert entity["collision"]["extraUpdates"] == updates - 1
    assert validate_runtime_wire(wire)["ok"]
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    delivered = [row for row in receipts if row.get("callId") == call["id"]
                 and row["authoredPath"].endswith(".params." + PARAM)]
    assert len(delivered) == 1
    assert delivered[0]["status"] == "delivered" and delivered[0]["value"] == value
    assert delivered[0]["finalPath"].endswith(".movement.params.gravityPerTick")
    for source in (None, document):
        assert audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
    damaged = deepcopy(wire)
    output = next(row for row in damaged["runtimeProgram"]["entities"] if row["id"] == call["target"])
    output["movement"]["params"]["gravityPerTick"] = 0.5 if value != 0.5 else -0.5
    assert not validate_runtime_wire(damaged)["ok"]


@pytest.mark.parametrize("value", [-2.00001, 2.00001, True, None, "-1", [], {}, float("inf"), float("nan"), -1e-300, 1e-300])
def test_bad_present_acceleration_is_rejected_without_rounding_or_clamping(value):
    document = build_capability_witness(FN)
    selected(document)["params"][PARAM] = value
    assert not validate_runtime_program(document)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(document)


def test_zero_is_explicit_and_schema_prompt_advertise_the_same_signed_domain():
    spec = CAPABILITY_REGISTRY[FN].params[PARAM]
    assert spec.minimum == -2 and spec.maximum == 2
    assert spec.neutral == 0 and spec.default is None and spec.required
    variant = next(row for row in capability_provider_union() if row["properties"]["fn"]["const"] == FN)
    shape = variant["properties"]["params"]
    assert PARAM in shape["required"]
    assert shape["properties"][PARAM]["minimum"] == -2
    assert shape["properties"][PARAM]["maximum"] == 2
    assert shape["properties"][PARAM]["x-infini-consumerConstraint"]["storage"] == "float32"
    card = next(row for row in compact_capability_catalog() if row["fn"] == FN)
    assert card["params"][PARAM]["min"] == -2 and card["params"][PARAM]["max"] == 2
    assert "negative accelerates upward" in card["does"]
    assert "updatesPerTick=N" in card["params"][PARAM]["meaning"]
    document = build_capability_witness(FN)
    del selected(document)["params"][PARAM]
    assert not validate_runtime_program(document)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(document)


def test_repair_changes_only_bad_acceleration_and_keeps_valid_negative_frozen():
    document = build_capability_witness(FN)
    call = selected(document)
    call["params"][PARAM] = -3
    scope = build_runtime_repair_scope(document, validate_runtime_program(document)["errors"])
    assert next(row["paths"] for row in scope["fieldPermissions"]["calls"] if row["id"] == call["id"]) == ["params." + PARAM]
    candidate = deepcopy(call)
    candidate["target"] = "other_entity"
    candidate["params"][PARAM] = -0.1875
    filtered, audit = filter_repair_patch_scope(document, {"note": "repair signed leaf", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    fixed = apply_repair_patch(document, filtered)
    assert selected(fixed)["params"][PARAM] == -0.1875
    assert selected(fixed)["target"] == call["target"]
    assert validate_runtime_program(fixed)["ok"]
    # A later unrelated invalid collision leaf cannot rewrite accepted acceleration.
    collision = selected(fixed, "set_projectile_collision")
    collision["params"]["pierce"] = 101
    scope = build_runtime_repair_scope(fixed, validate_runtime_program(fixed)["errors"])
    hostile = deepcopy(selected(fixed))
    hostile["params"][PARAM] = 2
    corrected = deepcopy(collision)
    corrected["params"]["pierce"] = 3
    filtered, audit = filter_repair_patch_scope(fixed, {"note": "keep accepted motion", "callsUpsert": [hostile, corrected]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(fixed, filtered)
    assert selected(repaired)["params"][PARAM] == -0.1875
    assert selected(repaired, "set_projectile_collision")["params"]["pierce"] == 3
    assert validate_runtime_program(repaired)["ok"]


def test_only_gravity_arc_domain_expands_and_retained_bounce_stays_hidden():
    assert CAPABILITY_REGISTRY["move_bounce"].decision == "internal"
    assert CAPABILITY_REGISTRY["move_bounce"].params[PARAM].minimum == 0.001
    assert CAPABILITY_REGISTRY["move_expanding_wave"].params["scaleGrowthPerUpdate"].minimum == 0.001
    assert CAPABILITY_REGISTRY["move_expanding_wave"].params["maxScale"].maximum == 4
    for fn in ("move_boomerang", "move_returning_glaive", "move_flail_tether", "move_yoyo_hover"):
        assert CAPABILITY_REGISTRY[fn].params["returnSpeed"].minimum == 1
        assert CAPABILITY_REGISTRY[fn].params["returnSpeed"].maximum == 80
