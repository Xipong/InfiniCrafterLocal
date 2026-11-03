"""Independent signed acceleration preserves tiny values, target clocks and frozen Repair."""
from copy import deepcopy

import pytest
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.registry_views import capability_provider_union, compact_capability_catalog
from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness

FN = "accelerate_y"
PARAM = "accelY"


def selected(document, fn=FN):
    return next(call for call in document["runtimeProgram"]["calls"] if call["fn"] == fn)


@pytest.mark.parametrize("value", [-2, -0.1875, -0.001, -1e-40, 0, 1e-40, 0.001, 0.1875, 2])
@pytest.mark.parametrize("updates", [1, 2, 6])
def test_signed_values_reach_the_same_wire_and_exact_receipts(value, updates):
    document = build_capability_witness(FN)
    call = selected(document)
    call["params"][PARAM] = CAPABILITY_REGISTRY[FN].params[PARAM].from_wire(value, updates_per_tick=updates)
    selected(document, "projectile_collision")["params"]["updatesPerTick"] = updates
    assert validate_runtime_program(document)["ok"]
    wire = compile_runtime_program(document)
    entity = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == call["target"])
    assert entity["verticalAcceleration"] == {"accelerationYPerUpdate": value}
    assert entity["movement"] == {"name": "move_straight", "code": 0, "params": {}}
    assert entity["collision"]["extraUpdates"] == updates - 1
    assert validate_runtime_wire(wire)["ok"]
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    delivered = [row for row in receipts if row.get("callId") == call["id"]
                 and row["authoredPath"].endswith(".params." + PARAM)]
    assert len(delivered) == 1
    assert delivered[0]["status"] == "delivered" and delivered[0]["value"] == value
    assert delivered[0]["finalPath"].endswith(".verticalAcceleration.accelerationYPerUpdate")
    for source in (None, document):
        assert audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
    damaged = deepcopy(wire)
    output = next(row for row in damaged["runtimeProgram"]["entities"] if row["id"] == call["target"])
    output["verticalAcceleration"]["accelerationYPerUpdate"] = 0.5 if value != 0.5 else -0.5
    assert not validate_runtime_wire(damaged)["ok"]


@pytest.mark.parametrize("value", [-16200.00001, 16200.00001, True, None, "-1", [], {}, float("inf"), float("nan"), -1e-300, 1e-300])
def test_bad_present_acceleration_is_rejected_without_rounding_or_clamping(value):
    document = build_capability_witness(FN)
    selected(document)["params"][PARAM] = value
    assert not validate_runtime_program(document)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(document)


def test_zero_is_explicit_and_schema_prompt_advertise_the_same_signed_domain():
    spec = CAPABILITY_REGISTRY[FN].params[PARAM]
    assert spec.minimum == -16200 and spec.maximum == 16200
    assert (spec.wire_minimum, spec.wire_maximum) == (-2, 2)
    assert spec.default is None and spec.required
    variant = next(row for row in capability_provider_union() if row["properties"]["fn"]["const"] == FN)
    shape = variant["properties"]["params"]
    assert PARAM in shape["required"]
    assert shape["properties"][PARAM]["minimum"] == spec.minimum
    assert shape["properties"][PARAM]["maximum"] == spec.maximum
    assert shape["properties"][PARAM]["x-infini-consumerConstraint"]["storage"] == "float32"
    card = next(row for row in compact_capability_catalog() if row["fn"] == FN)
    assert card["params"][PARAM]["min"] == spec.minimum and card["params"][PARAM]["max"] == spec.maximum
    assert card["params"][PARAM]["units"] == "blocks/second^2"
    document = build_capability_witness(FN)
    del selected(document)["params"][PARAM]
    assert not validate_runtime_program(document)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(document)


def test_repair_changes_only_bad_acceleration_and_keeps_valid_negative_frozen():
    document = build_capability_witness(FN)
    call = selected(document)
    call["params"][PARAM] = CAPABILITY_REGISTRY[FN].params[PARAM].minimum - 1
    scope = build_runtime_repair_scope(document, validate_runtime_program(document)["errors"])
    assert next(row["paths"] for row in scope["fieldPermissions"]["calls"] if row["id"] == call["id"]) == ["params." + PARAM]
    candidate = deepcopy(call)
    candidate["target"] = "other_entity"
    candidate["params"][PARAM] = -42.1875
    filtered, audit = filter_repair_patch_scope(document, {"note": "repair signed leaf", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    fixed = apply_repair_patch(document, filtered)
    assert selected(fixed)["params"][PARAM] == -42.1875
    assert selected(fixed)["target"] == call["target"]
    assert validate_runtime_program(fixed)["ok"]
    # A later unrelated invalid collision leaf cannot rewrite accepted acceleration.
    collision = selected(fixed, "projectile_collision")
    collision["params"]["pierce"] = 101
    scope = build_runtime_repair_scope(fixed, validate_runtime_program(fixed)["errors"])
    hostile = deepcopy(selected(fixed))
    hostile["params"][PARAM] = 2
    corrected = deepcopy(collision)
    corrected["params"]["pierce"] = 3
    filtered, audit = filter_repair_patch_scope(fixed, {"note": "keep accepted motion", "callsUpsert": [hostile, corrected]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(fixed, filtered)
    assert selected(repaired)["params"][PARAM] == -42.1875
    assert selected(repaired, "projectile_collision")["params"]["pierce"] == 3
    assert validate_runtime_program(repaired)["ok"]


@pytest.mark.parametrize("retired", ["move_gravity_arc", "move_orbit", "move_spiral", "move_expanding_wave",
    "move_whip_lash", "channel_beam", "charge_then_release", "orient_whip_to_owner_gravity"])
def test_retired_compound_names_are_not_fresh_author_aliases(retired):
    document = build_capability_witness(FN)
    selected(document)["fn"] = retired
    before = deepcopy(document)
    assert not validate_runtime_program(document)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(document)
    assert document == before


def test_retained_metadata_envelopes_and_obsolete_bounce_retirement():
    assert "move_bounce" not in CAPABILITY_REGISTRY
    assert CAPABILITY_REGISTRY["move_expanding_wave"].params["scaleGrowthPerUpdate"].minimum == 0.001
    assert CAPABILITY_REGISTRY["move_expanding_wave"].params["maxScale"].maximum == 4
    for fn, speed in (("move_boomerang", "returnSpeedBlocksPerSecond"), ("move_returning_glaive", "returnSpeedBlocksPerSecond"),
                      ("move_flail_tether", "returnSpeedBlocksPerSecond"), ("move_yoyo_hover", "speedBlocksPerSecond")):
        assert CAPABILITY_REGISTRY[fn].params[speed].wire_minimum == 1
        assert CAPABILITY_REGISTRY[fn].params[speed].wire_maximum == 80
