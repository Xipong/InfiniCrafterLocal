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


def test_beam_axial_origin_offset_projects_actual_author_to_wire_and_receipts():
    doc, call = _fixture()
    call["params"].update(length=4, startOffsetBlocks=-2)
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert report["ok"], report["errors"]
    wire = compile_runtime_program(doc)
    assert _beam(wire)["beamGeometry"] == {
        "lengthPx": 64, "widthPx": 8, "raycastTiles": False, "startOffsetPx": -32}
    assert doc == before
    report = validate_runtime_wire(wire)
    assert report["ok"], report["errors"]
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    for source in (doc, None):
        report = audit_compiler_receipts(receipts, authored_document=source, final_document=wire)
        assert report["ok"], report
    rows = [r for r in receipts if r.get("callId") == call["id"]
            and r["authoredPath"].endswith(".params.startOffsetBlocks")]
    assert len(rows) == 1 and rows[0]["status"] == "delivered"
    assert rows[0]["value"] == -32
    assert rows[0]["finalPath"].endswith(".beamGeometry.startOffsetPx")
    wire.pop("runtimeContract")
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("with_receipts", [False, True])
def test_historical_beam_offset_absence_is_preserved_without_retroactive_receipt(with_receipts):
    doc, _ = _fixture()
    wire = compile_runtime_program(doc)
    _beam(wire)["beamGeometry"].pop("startOffsetPx")
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    receipts[:] = [r for r in receipts if not r["finalPath"].endswith(".beamGeometry.startOffsetPx")]
    if not with_receipts:
        wire.pop("runtimeContract")
    before = deepcopy(wire)
    report = validate_runtime_wire(wire)
    assert report["ok"], report["errors"]
    if with_receipts:
        for source in (doc, None):
            report = audit_compiler_receipts(receipts, authored_document=source, final_document=wire)
            assert report["ok"], report
    assert wire == before and "startOffsetPx" not in _beam(wire)["beamGeometry"]


@pytest.mark.parametrize("offset", [-1920, -2, -0.125, 0, 1.5, 1920, "omitted"])
def test_beam_offset_boundaries_and_declared_neutral_are_lossless(offset):
    doc, call = _fixture()
    if offset != "omitted":
        call["params"]["startOffsetBlocks"] = offset
    before = deepcopy(doc)
    assert validate_runtime_program(doc)["ok"]
    wire = compile_runtime_program(doc)
    expected = 0 if offset == "omitted" else offset * 16
    assert _beam(wire)["beamGeometry"]["startOffsetPx"] == expected
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    rows = [r for r in receipts if r["finalPath"].endswith(".beamGeometry.startOffsetPx")]
    assert len(rows) == 1
    assert rows[0]["status"] == ("declared_neutral_omission" if offset == "omitted" else "delivered")
    assert rows[0]["value"] == expected
    for source in (doc, None):
        report = audit_compiler_receipts(receipts, authored_document=source, final_document=wire)
        assert report["ok"], report
    assert validate_runtime_wire(wire)["ok"] and doc == before
    wire.pop("runtimeContract")
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("value", [None, True, "-2", {}, [], -1920.001, 1920.001,
                                  float("inf"), float("-inf"), float("nan")])
def test_present_beam_offset_rejects_wrong_type_and_outside_author_or_native_domain(value):
    doc, call = _fixture()
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    call["params"]["startOffsetBlocks"] = value
    _beam(wire)["beamGeometry"]["startOffsetPx"] = value * 16 if type(value) in (int, float) else value
    for obj, validator, field in ((doc, validate_runtime_program, "startOffsetBlocks"),
                                   (wire, validate_runtime_wire, "startOffsetPx")):
        before = deepcopy(obj)
        report = validator(obj)
        assert not report["ok"], report
        assert any(row["path"].endswith("." + field) for row in report["errors"]), report
        assert obj == before


@pytest.mark.parametrize("key", ["startOffsetPx", "futureOrigin"])
def test_beam_author_refuses_wire_spelling_and_unknown_offset_fields(key):
    doc, call = _fixture()
    call["params"][key] = -32
    report = validate_runtime_program(doc)
    assert not report["ok"] and any(row["path"].endswith("." + key) for row in report["errors"])


@pytest.mark.parametrize("key", ["startOffsetBlocks", "futureOrigin"])
def test_beam_stripped_wire_refuses_author_spelling_and_unknown_offset_fields(key):
    wire = compile_runtime_program(_fixture()[0])
    wire.pop("runtimeContract")
    _beam(wire)["beamGeometry"][key] = -2
    report = validate_runtime_wire(wire)
    assert not report["ok"] and any(row["path"].endswith("." + key) for row in report["errors"])


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong_source", "wrong_owner", "wrong_value", "neutral_lie"])
@pytest.mark.parametrize("source_backed", [False, True])
def test_present_beam_offset_requires_exact_scoped_provenance(mutation, source_backed):
    doc, call = _fixture()
    call["params"]["startOffsetBlocks"] = -2
    wire = compile_runtime_program(doc)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    row = next(r for r in receipts if r["finalPath"].endswith(".beamGeometry.startOffsetPx"))
    if mutation == "missing":
        receipts.remove(row)
    elif mutation == "duplicate":
        receipts.append(deepcopy(row))
    elif mutation == "wrong_source":
        row["authoredPath"] = row["authoredPath"].replace("startOffsetBlocks", "startOffsetPx")
    elif mutation == "wrong_owner":
        row["callId"] = "foreign_call"
    elif mutation == "wrong_value":
        row["value"] = -16
    else:
        row["status"] = "declared_neutral_omission"
    report = audit_compiler_receipts(receipts, authored_document=doc if source_backed else None, final_document=wire)
    assert not report["ok"], report
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("source_backed", [False, True])
def test_present_neutral_beam_offset_cannot_lose_its_omission_receipt(source_backed):
    doc, _ = _fixture()
    wire = compile_runtime_program(doc)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    receipts[:] = [row for row in receipts if not row["finalPath"].endswith(".beamGeometry.startOffsetPx")]
    assert _beam(wire)["beamGeometry"]["startOffsetPx"] == 0
    report = audit_compiler_receipts(receipts, authored_document=doc if source_backed else None, final_document=wire)
    assert not report["ok"], report
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_beam_offset_real_author_and_repair_packets_explain_shifted_origin(monkeypatch, mode):
    from infini_local.core import llm_config
    from test_front_hand_generation_packets import _http_packet
    from prompt_packet_helpers import request_dossier
    from repair_test_helpers import provider_roundtrip, repair_with_response

    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    initial, _, _ = build_initial_author_request({}, {}, "beam-offset", model_name="offline")
    doc, call = _fixture()
    doc.pop("concept")
    doc.pop("realization")
    call["params"]["startOffsetBlocks"] = -2
    restored = provider_roundtrip(doc, initial["response_format"])
    assert validate_runtime_program(restored)["ok"]
    baseline = compile_runtime_program(restored)
    assert _beam(baseline)["beamGeometry"]["startOffsetPx"] == -32

    broken = deepcopy(doc)
    _call(broken, "beam_geometry")["params"]["startOffsetBlocks"] = None
    correction = deepcopy(call)
    correction["params"].update(length=8, widthBlocks=1, raycastTiles=True)
    repaired, repair = repair_with_response(monkeypatch, broken,
        {"callsUpsert": [correction], "note": "only invalid origin offset"}, mode)
    assert compile_runtime_program(repaired)["runtimeProgram"] == baseline["runtimeProgram"]
    assert request_dossier(repair)["repairScope"]["fieldPermissions"]["calls"] == [
        {"id": call["id"], "paths": ["params.startOffsetBlocks"]}]
    for request in (initial, repair):
        packet = _http_packet(monkeypatch, request)
        prose = " ".join(m["content"] for m in packet["messages"])
        assert "startOffsetBlocks" in prose and "MotionAxis" in prose
        assert "beam_geometry starts at body center, not at an inventory grip" not in prose
        assert "start=body center+axis*startOffsetBlocks" in prose
    card = next(row for row in request_dossier(initial)["runtimeCapabilityContract"]["catalog"]["capabilities"]
                if row["fn"] == "beam_geometry")
    field = card["params"]["startOffsetBlocks"]
    assert field["optional"] is True and field["default"] == field["neutral"] == 0
    assert field["min"] == -1920 and field["max"] == 1920


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
    _add(doc, "set_aim", {"source": "velocity", "turnOwner": False})
    beam = _add(doc, "beam_geometry", {"length": 20, "widthBlocks": 0.5,
                                              "raycastTiles": values["raycastTiles"]})
    beam["params"]["ramp"] = {"warmupSeconds": 0.5,
        **{k: values[k] for k in ("initialDamageMultiplier", "initialWidthMultiplier", "damageStartProgress")}}
    if values["manaPayment"] == "each_use_time":
        # Explicit test composition, never a gameplay default inferred from beam.
        _call(doc, "item_use")["params"]["channel"] = True
        _add(doc, "set_owner_control", {"requireHeldItem": True, "requireChannel": True,
            "requireItemAnimation": False, "claimHeldProjectile": False, "animation": "none", "lifetime": "authored"})
        _add(doc, "sustain_mana", {})
    return doc, beam


def _beam(wire):
    return next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == wire["runtimeProgram"]["primaryEntityId"])


def _retained_wire(**options):
    """Valid program control with the exact old controller shape, not old Author."""
    doc = build_capability_witness("move_straight")
    _call(doc, "item_use")["params"]["channel"] = True
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
    assert entity["beamGeometry"] == {"lengthPx": 320, "widthPx": 8, "raycastTiles": values["raycastTiles"], "startOffsetPx": 0}
    assert entity["beamRamp"] == {"warmupTicks": 30, **{k: values[k] for k in
        ("initialDamageMultiplier", "initialWidthMultiplier", "damageStartProgress")}}
    assert ("manaSustain" in entity) is choices[0]
    assert ("ownerControl" in entity) is choices[0]
    assert wire["runtimeProgram"]["itemUse"]["channel"] is choices[0]
    assert "controller" not in entity and "attachment" not in entity
    for fn, component in (("projectile_collision", "collision"), ("projectile_damage", "damage")):
        source = _call(doc, fn)["params"]
        key = "tileCollide" if component == "collision" else "ownerHitCheck"
        assert entity[component][key] == source[key]
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    for source in (doc, None):
        assert audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
    call = _call(doc, "beam_geometry")
    for parameter, spec in CAPABILITY_REGISTRY[call["fn"]].params.items():
        if parameter not in call["params"]:
            continue
        member = "beamRamp" if parameter == "ramp" else "beamGeometry"
        for projection in spec.projected_fields(call["params"][parameter], parameter):
            rows = [r for r in receipts if r.get("callId") == call["id"]
                    and r["authoredPath"].endswith(".params." + projection.authored_path)]
            assert len(rows) == 1 and rows[0]["status"] == "delivered"
            assert rows[0]["value"] == projection.value
            assert rows[0]["finalPath"].endswith("." + member + "." + projection.wire_path)
    if choices[0]:
        cadence = [r for r in receipts if r.get("callId") == "sustain_mana"]
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
    call = _call(doc, "beam_geometry") if key == "raycastTiles" else ramp
    params = call["params"] if key == "raycastTiles" else call["params"]["ramp"]
    params[key] = value
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
    _call(doc, "beam_geometry")["params"]["raycastTiles"] = None
    local = project_provider_author_item_to_local(doc, response_format=request["response_format"])
    assert not validate_runtime_program(local)["ok"]
    import json
    offered = {row["fn"] for row in json.loads(user)["runtimeCapabilityContract"]["catalog"]["capabilities"]}
    assert {"beam_geometry", "sustain_mana", "set_owner_control"} <= offered
    assert "channel_beam" not in offered


def test_frozen_repair_fixes_only_invalid_width_and_keeps_absent_independent_components():
    good, good_call = _fixture(initialWidthMultiplier=0.22)
    broken = deepcopy(good)
    bad_call = _call(broken, "beam_geometry")
    bad_call["params"]["ramp"]["initialWidthMultiplier"] = 0
    before = deepcopy(broken)
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": bad_call["id"], "paths": ["params.ramp.initialWidthMultiplier"]}]
    hostile = deepcopy(good_call)
    hostile["params"]["ramp"]["warmupSeconds"] += 10 / 60
    filtered, audit = filter_repair_patch_scope(broken, {"callsUpsert": [hostile], "note": "width only"}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    repaired = apply_repair_patch(broken, filtered)
    assert repaired == good and broken == before
    wire = compile_runtime_program(repaired)
    assert validate_runtime_wire(wire)["ok"]
    assert "manaSustain" not in _beam(wire) and "ownerControl" not in _beam(wire)
