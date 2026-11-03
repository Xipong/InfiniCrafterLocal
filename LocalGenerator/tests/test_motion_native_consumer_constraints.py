"""Absolute-position tile policies must name an actual reachable native consumer."""
from copy import deepcopy

import pytest
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from test_composable_motion_primitives import add, base_document


def absolute_body(lash=False, window=None):
    doc = base_document()
    add(doc, "set_aim", {"source": "initial"})
    if lash:
        add(doc, "lash_geometry", {"clock": "active", "duration": 1,
            "anchor": "owner_center", "reach": 8, "segments": 12,
            "sweepStartRadians": -1, "sweepEndRadians": 1, "bendRatio": 0.2,
            "useOwnerGravity": False, "useWhipRange": False})
    else:
        add(doc, "attach", {"anchor": "owner_center", **({"window": window} if window is not None else {})})
    collision = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "projectile_collision")
    collision["params"]["tileCollide"] = True
    return doc, collision


@pytest.mark.parametrize("lash,window", [(False, None), (False, {"phase": "always"}), (True, None)])
def test_always_absolute_position_refuses_unexecuted_tile_policy(lash, window):
    doc, collision = absolute_body(lash, window)
    frozen = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert not report["ok"]
    path = f"$.runtimeProgram.calls[{doc['runtimeProgram']['calls'].index(collision)}].params.tileCollide"
    assert any(e["path"] == path and e["code"] == "incompatible_param_variant" for e in report["errors"])
    assert doc == frozen
    collision["params"]["tileCollide"] = False
    assert validate_runtime_program(doc)["ok"]


def test_finite_attachment_keeps_explicit_tile_policy_for_free_flight():
    doc, _ = absolute_body(window={"phase": "always", "clock": "active", "startDelay": 0, "duration": 1})
    assert validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("lash", [False, True])
def test_stripped_wire_checks_the_same_absolute_tile_consumer(lash):
    doc, collision = absolute_body(lash)
    collision["params"]["tileCollide"] = False
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    assert validate_runtime_wire(wire)["ok"]
    body = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == doc["runtimeProgram"]["primaryEntityId"])
    body["collision"]["tileCollide"] = True
    assert not validate_runtime_wire(wire)["ok"]


def test_collision_refusal_repair_does_not_open_other_valid_body_choices():
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
    from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
    from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
    doc, collision = absolute_body()
    frozen = deepcopy(doc)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    proposal = deepcopy(collision)
    proposal["params"].update(tileCollide=False, pierce=99)
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [proposal], "note": "supported collision only"}, scope)
    assert audit["ok"], audit
    result = apply_repair_patch(doc, patch)
    wanted = deepcopy(frozen)
    next(c for c in wanted["runtimeProgram"]["calls"] if c["id"] == collision["id"])["params"]["tileCollide"] = False
    assert result == wanted
    assert doc == frozen
    assert validate_runtime_program(result)["ok"]
