"""Exact volley/target choices, omission provenance, strict wire and frozen Repair."""

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


OPTIONS = {"count": 4, "spreadRadians": 0.6, "targetPolicy": "player_assigned_first",
           "requireLineOfSight": True, "hardRange": True}


def _fixture(**options):
    doc = build_capability_witness("target_and_fire")
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "target_and_fire")
    call["params"].update(options)
    return doc, call


def _targeting(wire):
    return next(e["targeting"] for e in wire["runtimeProgram"]["entities"] if e.get("targeting"))


@pytest.mark.parametrize("count,spread,policy,los,hard", list(product(
    (1, 4), (0.0, 0.75), ("distance_score", "player_assigned_first"), (False, True), (False, True))))
def test_all_joint_targeting_choices_deliver_exact_fields_and_receipts(count, spread, policy, los, hard):
    values = dict(zip(OPTIONS, (count, spread, policy, los, hard)))
    doc, call = _fixture(**values)
    before = deepcopy(doc)
    wire = compile_runtime_program(doc)
    assert doc == before
    assert validate_runtime_program(doc)["ok"]
    assert validate_runtime_wire(wire)["ok"]
    assert {k: _targeting(wire)[k] for k in OPTIONS} == values
    assert wire["runtimeContract"]["technicalLoweringAudit"]["ok"]
    receipts = [r for r in wire["runtimeContract"]["finalWireReceipts"] if r.get("callId") == call["id"]]
    for key, value in values.items():
        rows = [r for r in receipts if r["authoredPath"].endswith(".params." + key)]
        assert len(rows) == 1 and rows[0]["value"] == value
        assert rows[0]["status"] == "delivered"
        assert rows[0]["finalPath"].endswith(".targeting." + key)


@pytest.mark.parametrize("key,value", [
    ("count", None), ("count", True), ("count", 1.0), ("count", 0), ("count", 5),
    ("spreadRadians", None), ("spreadRadians", False), ("spreadRadians", -0.1),
    ("spreadRadians", 0.7501), ("spreadRadians", 1e-50),
    ("targetPolicy", None), ("targetPolicy", "nearest"), ("targetPolicy", 0),
    ("requireLineOfSight", None), ("requireLineOfSight", 0), ("hardRange", None), ("hardRange", "true"),
])
def test_invalid_present_choices_stay_red_in_author_and_wire_without_provenance(key, value):
    doc, call = _fixture(**OPTIONS)
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    call["params"][key] = value
    _targeting(wire)[key] = value
    for obj, validator, suffix in ((doc, validate_runtime_program, ".params."), (wire, validate_runtime_wire, ".targeting.")):
        before = deepcopy(obj)
        report = validator(obj)
        assert not report["ok"]
        assert any(r["path"].endswith(suffix + key) for r in report["errors"])
        assert obj == before


def test_retained_wire_absence_is_accepted_without_inventing_choices():
    doc, _ = _fixture()
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    for key in OPTIONS:
        _targeting(wire).pop(key)
    before = deepcopy(wire)
    assert validate_runtime_wire(wire)["ok"]
    assert wire == before


@pytest.mark.parametrize("mode", ("json_object", "json_schema"))
def test_real_author_packet_and_nullable_inverse_preserve_every_explicit_choice(monkeypatch, mode):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    request, user, _ = build_initial_author_request({}, {}, {}, {}, "targeting", model_name="test-model")
    card = next(c for c in json.loads(user)["runtimeCapabilityContract"]["catalog"]["capabilities"] if c["fn"] == "target_and_fire")
    assert card == CAPABILITY_REGISTRY["target_and_fire"].author_prompt_card()
    for term in ("Collision.CanHit", "hard geometric", "assigned NPC", "aim=velocity", "placement=item_use_origin"):
        assert term in json.dumps(card)
    doc, call = _fixture(**OPTIONS)
    assert project_provider_author_item_to_local(doc, response_format=request["response_format"]) == doc
    # Only schema-owned optional nulls are removed; json_object null stays RED.
    call["params"]["hardRange"] = None
    local = project_provider_author_item_to_local(doc, response_format=request["response_format"])
    params = next(c["params"] for c in local["runtimeProgram"]["calls"] if c["fn"] == "target_and_fire")
    assert ("hardRange" not in params) == (mode == "json_schema")


def test_frozen_repair_repairs_one_invalid_choice_and_preserves_absent_and_valid_neighbors():
    good, good_call = _fixture(count=4)
    for key in OPTIONS.keys() - {"count"}:
        good_call["params"].pop(key, None)
    broken = deepcopy(good)
    bad_call = next(c for c in broken["runtimeProgram"]["calls"] if c["fn"] == "target_and_fire")
    bad_call["params"]["count"] = 5
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": bad_call["id"], "paths": ["params.count"]}]
    hostile = deepcopy(good_call)
    hostile["params"].update(OPTIONS)
    hostile["params"]["sameTargetBias"] = 0.9
    filtered, audit = filter_repair_patch_scope(broken, {"callsUpsert": [hostile], "note": "count"}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    assert apply_repair_patch(broken, filtered) == good


def test_targeting_numeric_reject_guards_are_audited():
    rows = {r["param"]: r for r in _runtime_param_bound_rows() if r["capability"] == "target_and_fire"}
    for key in ("count", "spreadRadians"):
        assert rows[key]["preserved"]
        assert rows[key]["admission"] == "reject_without_clamp"


@pytest.mark.parametrize("old,new", [("Count is < 1 or > 4", "Count is < 0 or > 4"),
                                      ("SpreadRadians is < 0d or > 0.75d", "SpreadRadians is < 0d or > 1d")])
def test_numeric_guard_mutations_cannot_disappear_from_quality_report(monkeypatch, old, new):
    original = Path.read_text
    def read(path, *args, **kwargs):
        text = original(path, *args, **kwargs)
        return text.replace(old, new) if path.name == "RuntimeProgramSpec.cs" else text
    monkeypatch.setattr(Path, "read_text", read)
    rows = [r for r in _runtime_param_bound_rows() if r["capability"] == "target_and_fire"]
    assert any(not r["preserved"] for r in rows)
