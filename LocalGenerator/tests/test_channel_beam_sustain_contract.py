"""Independent beam composition and retained-controller readback; no legacy Author."""

from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.pipelines.author_item_contract import project_provider_author_item_to_local
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.qa.capability_witnesses import build_capability_witness


OPTIONS = {"manaPayment": "each_use_time", "initialDamageMultiplier": 0.35,
           "initialWidthMultiplier": 0.22, "damageStartProgress": 0.08, "raycastTiles": True}
NEUTRALS = {"manaPayment": "initial_use_only", "initialDamageMultiplier": 1.0,
            "initialWidthMultiplier": 1.0, "damageStartProgress": 1.0, "raycastTiles": False}


def _call(doc, fn):
    return next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)


def _add(doc, fn, params):
    row = {"id": fn, "fn": fn, "target": doc["runtimeProgram"]["primaryEntityId"], "params": params}
    doc["runtimeProgram"]["calls"].append(row)
    return row


def _fixture(**options):
    values = {**NEUTRALS, **options}
    doc = build_capability_witness("move_straight")
    _add(doc, "set_projectile_aim", {"source": "velocity", "turnOwner": False})
    _add(doc, "set_projectile_beam_geometry", {"lengthBlocks": 20, "widthBlocks": 0.5,
                                              "raycastTiles": values["raycastTiles"]})
    ramp = _add(doc, "set_projectile_beam_ramp", {"warmupSeconds": 0.5,
        **{k: values[k] for k in ("initialDamageMultiplier", "initialWidthMultiplier", "damageStartProgress")}})
    if values["manaPayment"] == "each_use_time":
        # Explicit test composition, never a gameplay default inferred from beam.
        _call(doc, "configure_item_use")["params"]["channel"] = True
        _add(doc, "set_projectile_owner_control", {"requireHeldItem": True, "requireChannel": True,
            "requireItemAnimation": False, "claimHeldProjectile": False, "animation": "none", "lifetime": "authored"})
        _add(doc, "sustain_projectile_mana", {})
    return doc, ramp


def _beam(wire):
    return next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == wire["runtimeProgram"]["primaryEntityId"])


def _retained_wire(**options):
    """Valid program control with the exact old controller shape, not old Author."""
    doc = build_capability_witness("move_straight")
    _call(doc, "configure_item_use")["params"]["channel"] = True
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    entity = _beam(wire)
    entity["kind"] = "owner_attached_projectile"
    entity["controller"] = {"code": 1, "name": "channel_beam", "params": {
        "rangeTiles": 20, "widthPx": 8, "warmupTicks": 30, **options}}
    return wire


@pytest.mark.parametrize("choices", [
    (False, False, False, False, False), (True, True, True, True, True),
    (True, False, True, False, True), (False, True, False, True, False),
])
def test_representative_joint_beam_choices_project_exactly_with_independent_collision_and_receipts(choices):
    values = {k: OPTIONS[k] if selected else NEUTRALS[k] for k, selected in zip(OPTIONS, choices)}
    doc, _ = _fixture(**values)
    before = deepcopy(doc)
    wire = compile_runtime_program(doc)
    assert doc == before and validate_runtime_program(doc)["ok"] and validate_runtime_wire(wire)["ok"]
    entity = _beam(wire)
    assert entity["beamGeometry"] == {"lengthPx": 320, "widthPx": 8, "raycastTiles": values["raycastTiles"]}
    assert entity["beamRamp"] == {"warmupTicks": 30, **{k: values[k] for k in
        ("initialDamageMultiplier", "initialWidthMultiplier", "damageStartProgress")}}
    assert ("manaSustain" in entity) is choices[0]
    assert ("ownerControl" in entity) is choices[0]
    assert wire["runtimeProgram"]["itemUse"]["channel"] is choices[0]
    assert "controller" not in entity and "attachment" not in entity
    for fn, component in (("set_projectile_collision", "collision"), ("set_projectile_damage", "damage")):
        source = _call(doc, fn)["params"]
        key = "tileCollide" if component == "collision" else "ownerHitCheck"
        assert entity[component][key] == source[key]
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    for source in (doc, None):
        assert audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
    for fn, member in (("set_projectile_beam_geometry", "beamGeometry"), ("set_projectile_beam_ramp", "beamRamp")):
        call = _call(doc, fn)
        for key, value in call["params"].items():
            rows = [r for r in receipts if r.get("callId") == call["id"] and r["authoredPath"].endswith(".params." + key)]
            assert len(rows) == 1 and rows[0]["status"] == "delivered"
            spec = CAPABILITY_REGISTRY[fn].params[key]
            assert rows[0]["value"] == spec.to_wire(value)
            assert rows[0]["finalPath"].endswith("." + member + "." + (spec.wire_name or key))
    if choices[0]:
        cadence = [r for r in receipts if r.get("callId") == "sustain_projectile_mana"]
        assert len(cadence) == 1
        assert cadence[0]["value"] == "held_item_use_time" and cadence[0]["finalPath"].endswith(".manaSustain.cadence")


@pytest.mark.parametrize("present", [
    (False, False, False, False, False),
    (True, False, True, False, True), (False, True, False, True, False),
])
def test_retained_joint_omissions_stay_absent_without_enabling_sustain_or_raycast(present):
    wire = _retained_wire(**{k: NEUTRALS[k] for k, keep in zip(NEUTRALS, present) if keep})
    before = deepcopy(wire)
    assert validate_runtime_wire(wire)["ok"] and wire == before
    params = _beam(wire)["controller"]["params"]
    for key, keep in zip(NEUTRALS, present):
        assert (key in params) is keep
    assert "manaSustain" not in _beam(wire) and "beamGeometry" not in _beam(wire)


@pytest.mark.parametrize("key,value", [
    ("manaPayment", None), ("manaPayment", True), ("manaPayment", "on_tick"),
    ("manaPayment", " each_use_time "), ("manaPayment", "EACH_USE_TIME"),
    *((k, v) for k in ("initialDamageMultiplier", "initialWidthMultiplier")
      for v in (None, False, "0.35", 0, 0.0099, 1.001, 0.9999999999, float("inf"), float("nan"))),
    *(("damageStartProgress", v) for v in (None, True, "0.08", -0.1, 1.001, float("nan"))),
    ("raycastTiles", None), ("raycastTiles", 0), ("raycastTiles", "true"),
])
def test_bad_present_retained_values_stay_red_without_mutation(key, value):
    wire = _retained_wire(**{**OPTIONS, key: value})
    before = deepcopy(wire)
    report = validate_runtime_wire(wire)
    assert not report["ok"] and any(r["path"].endswith(".params." + key) for r in report["errors"])
    assert wire == before


@pytest.mark.parametrize("key,value", [
    *((k, v) for k in ("initialDamageMultiplier", "initialWidthMultiplier")
      for v in (None, False, "0.35", 0, 0.0099, 1.001, float("inf"), float("nan"))),
    *(("damageStartProgress", v) for v in (None, True, "0.08", -0.1, 1.001, float("nan"))),
    ("raycastTiles", None), ("raycastTiles", 0), ("raycastTiles", "true"),
])
def test_bad_present_independent_values_stay_red_in_author_and_stripped_wire(key, value):
    doc, ramp = _fixture(**OPTIONS)
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    call = _call(doc, "set_projectile_beam_geometry") if key == "raycastTiles" else ramp
    call["params"][key] = value
    member = "beamGeometry" if key == "raycastTiles" else "beamRamp"
    _beam(wire)[member][key] = value
    for obj, validator in ((doc, validate_runtime_program), (wire, validate_runtime_wire)):
        before = deepcopy(obj)
        report = validator(obj)
        assert not report["ok"] and any(r["path"].endswith("." + key) for r in report["errors"])
        assert obj == before


@pytest.mark.parametrize("component,code,name", (("controller", 0, ""), ("controller", 2, "charge_then_release"),
                                                 ("movement", 1, "move_homing")))
def test_extension_cannot_be_smuggled_into_another_driver(component, code, name):
    wire = _retained_wire(**OPTIONS)
    entity = _beam(wire)
    values = entity.pop("controller")["params"]
    entity[component] = {"code": code, "name": name, "params": values}
    before = deepcopy(wire)
    report = validate_runtime_wire(wire)
    rejected = {r["path"].rsplit(".", 1)[-1] for r in report["errors"] if r["code"] == "invalid_channel_beam_param"}
    assert rejected == set(OPTIONS) and wire == before


@pytest.mark.parametrize("mode", ("json_object", "json_schema"))
def test_real_production_packet_and_nullable_inverse_expose_independent_choices(monkeypatch, mode):
    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', mode)
    request, user, _ = build_initial_author_request({}, {}, "beam", model_name="test-model")
    doc, _ = _fixture(**OPTIONS)
    assert project_provider_author_item_to_local(doc, response_format=request["response_format"]) == doc
    # New raycast is required, not the old controller's optional neutral leaf.
    _call(doc, "set_projectile_beam_geometry")["params"]["raycastTiles"] = None
    local = project_provider_author_item_to_local(doc, response_format=request["response_format"])
    assert not validate_runtime_program(local)["ok"]
    import json
    offered = {row["fn"] for row in json.loads(user)["runtimeCapabilityContract"]["catalog"]["capabilities"]}
    assert {"set_projectile_beam_geometry", "set_projectile_beam_ramp", "sustain_projectile_mana", "set_projectile_owner_control"} <= offered
    assert "channel_beam" not in offered


def test_frozen_repair_fixes_only_invalid_width_and_keeps_absent_independent_components():
    good, good_call = _fixture(initialWidthMultiplier=0.22)
    broken = deepcopy(good)
    bad_call = _call(broken, "set_projectile_beam_ramp")
    bad_call["params"]["initialWidthMultiplier"] = 0
    before = deepcopy(broken)
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": bad_call["id"], "paths": ["params.initialWidthMultiplier"]}]
    hostile = deepcopy(good_call)
    hostile["params"]["warmupSeconds"] += 10 / 60
    filtered, audit = filter_repair_patch_scope(broken, {"callsUpsert": [hostile], "note": "width only"}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    repaired = apply_repair_patch(broken, filtered)
    assert repaired == good and broken == before
    wire = compile_runtime_program(repaired)
    assert validate_runtime_wire(wire)["ok"]
    assert "manaSustain" not in _beam(wire) and "ownerControl" not in _beam(wire)
