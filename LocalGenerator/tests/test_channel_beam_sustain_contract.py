"""Beam choices through production Author, exact receipts, strict wire and Repair."""

from copy import deepcopy
from itertools import product
import json
from pathlib import Path

import pytest

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, apply_repair_patch, build_runtime_repair_scope,
    compile_runtime_program, filter_repair_patch_scope,
    validate_runtime_program, validate_runtime_wire,
)
from infini_local.pipelines.author_item_contract import project_provider_author_item_to_local
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.qa.capability_library_audit import _runtime_param_bound_rows
from infini_local.qa.capability_witnesses import build_capability_witness


OPTIONS = {"manaPayment": "each_use_time", "initialDamageMultiplier": 0.35,
           "initialWidthMultiplier": 0.22, "damageStartProgress": 0.08, "raycastTiles": True}
NEUTRALS = {"manaPayment": "initial_use_only", "initialDamageMultiplier": 1.0,
            "initialWidthMultiplier": 1.0, "damageStartProgress": 1.0, "raycastTiles": False}


def _fixture(**options):
    doc = build_capability_witness("channel_beam")
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "channel_beam")
    call["params"].update(options)
    return doc, call


def _beam(wire):
    return next(e for e in wire["runtimeProgram"]["entities"] if e.get("controller", {}).get("name") == "channel_beam")


@pytest.mark.parametrize("choices", list(product((False, True), repeat=len(OPTIONS))))
def test_all_joint_beam_choices_project_exactly_with_independent_collision_and_receipts(choices):
    values = {k: OPTIONS[k] if selected else NEUTRALS[k] for k, selected in zip(OPTIONS, choices)}
    doc, call = _fixture(**values)
    before = deepcopy(doc)
    wire = compile_runtime_program(doc)
    assert doc == before and validate_runtime_program(doc)["ok"] and validate_runtime_wire(wire)["ok"]
    entity = _beam(wire)
    assert {k: entity["controller"]["params"][k] for k in OPTIONS} == values
    for fn, component in (("set_projectile_collision", "collision"), ("set_projectile_damage", "damage")):
        source = next(c["params"] for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)
        assert entity[component]["tileCollide" if component == "collision" else "ownerHitCheck"] == source["tileCollide" if component == "collision" else "ownerHitCheck"]
    assert wire["runtimeContract"]["technicalLoweringAudit"]["ok"]
    for key, value in values.items():
        rows = [r for r in wire["runtimeContract"]["finalWireReceipts"]
                if r.get("callId") == call["id"] and r["authoredPath"].endswith(".params." + key)]
        assert len(rows) == 1 and rows[0]["value"] == value and rows[0]["status"] == "delivered"
        assert rows[0]["finalPath"].endswith(".controller.params." + key)


@pytest.mark.parametrize("present", list(product((False, True), repeat=len(NEUTRALS))))
def test_joint_omissions_are_exact_neutrals_with_own_provenance(present):
    doc, call = _fixture(**NEUTRALS)
    explicit = compile_runtime_program(doc)
    for name, keep in zip(NEUTRALS, present):
        if not keep:
            call["params"].pop(name)
    sparse = compile_runtime_program(doc)
    for component in ("runtimeProgram", "gameplay", "accessory", "armor"):
        assert sparse[component] == explicit[component]
    rows = sparse["runtimeContract"]["finalWireReceipts"]
    for name, keep in zip(NEUTRALS, present):
        row = next(r for r in rows if r.get("callId") == call["id"] and r["authoredPath"].endswith(".params." + name))
        assert row["value"] == NEUTRALS[name]
        assert row["status"] == ("delivered" if keep else "declared_neutral_omission")
    assert validate_runtime_wire(sparse)["ok"]


@pytest.mark.parametrize("key,value", [
    ("manaPayment", None), ("manaPayment", True), ("manaPayment", "on_tick"),
    ("manaPayment", " each_use_time "), ("manaPayment", "EACH_USE_TIME"),
    *((k, v) for k in ("initialDamageMultiplier", "initialWidthMultiplier")
      for v in (None, False, "0.35", 0, 0.0099, 1.001, 0.9999999999, float("inf"), float("nan"))),
    *(("damageStartProgress", v) for v in (None, True, "0.08", -0.1, 1.001, float("nan"))),
    ("raycastTiles", None), ("raycastTiles", 0), ("raycastTiles", "true"),
])
def test_bad_present_values_stay_red_in_author_and_wire_without_receipts(key, value):
    doc, call = _fixture(**OPTIONS)
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    call["params"][key] = value
    _beam(wire)["controller"]["params"][key] = value
    for obj, validator in ((doc, validate_runtime_program), (wire, validate_runtime_wire)):
        before = deepcopy(obj)
        report = validator(obj)
        assert not report["ok"] and any(r["path"].endswith(".params." + key) for r in report["errors"])
        assert obj == before


def test_retained_wire_absence_stays_absent_and_does_not_enable_sustain_or_raycast():
    doc, _ = _fixture()
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    for key in OPTIONS:
        _beam(wire)["controller"]["params"].pop(key)
    before = deepcopy(wire)
    assert validate_runtime_wire(wire)["ok"] and wire == before


@pytest.mark.parametrize("component,code,name", (("controller", 0, ""), ("controller", 2, "charge_then_release"),
                                                 ("movement", 1, "move_homing")))
def test_extension_cannot_be_smuggled_into_another_driver(component, code, name):
    doc, _ = _fixture(**OPTIONS)
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    entity = _beam(wire)
    values = entity.pop("controller")["params"]
    entity[component] = {"code": code, "name": name, "params": values}
    report = validate_runtime_wire(wire)
    rejected = {r["path"].rsplit(".", 1)[-1] for r in report["errors"] if r["code"] == "invalid_channel_beam_param"}
    assert rejected == set(OPTIONS)


@pytest.mark.parametrize("mode", ("json_object", "json_schema"))
def test_real_production_packet_and_nullable_inverse_expose_all_choices(monkeypatch, mode):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    request, user, _ = build_initial_author_request({}, {}, {}, {}, "beam", model_name="test-model")
    packet = json.loads(user)
    card = next(c for c in packet["runtimeCapabilityContract"]["catalog"]["capabilities"] if c["fn"] == "channel_beam")
    profiles = packet["runtimeCapabilityContract"]["catalog"]["fieldGuide"]["consumerConstraints"]
    for param in card["params"].values():
        if isinstance(param.get("consumerConstraint"), str):
            param["consumerConstraint"] = deepcopy(profiles[param["consumerConstraint"]])
    assert card == CAPABILITY_REGISTRY["channel_beam"].author_prompt_card()
    for term in ("CheckMana", "useTime", "LaserScan", "ownerHitCheck", "ModifyHitNPC", "three rays", "shortest"):
        assert term in json.dumps(card)
    doc, call = _fixture(**OPTIONS)
    assert project_provider_author_item_to_local(doc, response_format=request["response_format"]) == doc
    call["params"]["raycastTiles"] = None
    local = project_provider_author_item_to_local(doc, response_format=request["response_format"])
    params = next(c["params"] for c in local["runtimeProgram"]["calls"] if c["fn"] == "channel_beam")
    assert ("raycastTiles" not in params) == (mode == "json_schema")
    call["params"]["raycastTiles"] = "true"
    malformed = project_provider_author_item_to_local(doc, response_format=request["response_format"])
    assert not validate_runtime_program(malformed)["ok"]


def test_frozen_repair_fixes_only_invalid_width_and_keeps_accepted_omissions():
    good, good_call = _fixture(initialWidthMultiplier=0.22)
    for key in OPTIONS.keys() - {"initialWidthMultiplier"}:
        good_call["params"].pop(key, None)
    broken = deepcopy(good)
    bad_call = next(c for c in broken["runtimeProgram"]["calls"] if c["fn"] == "channel_beam")
    bad_call["params"]["initialWidthMultiplier"] = 0
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": bad_call["id"], "paths": ["params.initialWidthMultiplier"]}]
    hostile = deepcopy(good_call)
    hostile["params"].update(OPTIONS)
    hostile["params"]["warmupTicks"] += 10
    filtered, audit = filter_repair_patch_scope(broken, {"callsUpsert": [hostile], "note": "width only"}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    assert apply_repair_patch(broken, filtered) == good


def test_new_nullable_numeric_reject_guards_cannot_escape_bound_audit():
    rows = {r["param"]: r for r in _runtime_param_bound_rows() if r["capability"] == "channel_beam"}
    for key in ("initialDamageMultiplier", "initialWidthMultiplier", "damageStartProgress"):
        assert rows[key]["preserved"] and rows[key]["admission"] == "reject_without_clamp"


@pytest.mark.parametrize("old,new", [("value < 0.01 || value > 1", "value < 0 || value > 1"),
                                     ("value < 0 || value > 1)", "value < 0 || value > 2)"),
                                     ("|| value != 1 && (float)value.Value == 1f", "")])
def test_numeric_guard_mutations_turn_the_authority_report_red(monkeypatch, old, new):
    original = Path.read_text
    def read(path, *args, **kwargs):
        source = original(path, *args, **kwargs)
        return source.replace(old, new) if path.name == "RuntimeProgramSpec.cs" else source
    monkeypatch.setattr(Path, "read_text", read)
    assert any(not r["preserved"] for r in _runtime_param_bound_rows() if r["capability"] == "channel_beam")
