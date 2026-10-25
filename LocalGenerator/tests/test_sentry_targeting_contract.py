"""Exact volley/target choices, omission provenance, strict wire and frozen Repair."""

from copy import deepcopy
from itertools import product
import json

import pytest

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
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
    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', mode)
    request, user, _ = build_initial_author_request({}, {}, "targeting", model_name="test-model")
    catalog = json.loads(user)["runtimeCapabilityContract"]["catalog"]
    card = next(c for c in catalog["capabilities"] if c["fn"] == "target_and_fire")
    from test_author_request_compaction import _expand_constraint_references
    card = _expand_constraint_references(card, catalog["fieldGuide"]["consumerConstraints"])
    expected = CAPABILITY_REGISTRY["target_and_fire"].author_prompt_card()
    expected["constructionMeaning"] = (
        "For projectile descendant production, see fieldGuide.descendantSpawnBudget: "
        "interval and entity lifetime do not guarantee sustained output."
    )
    assert card == expected
    for term in (
        "native line-of-sight check from this projectile hitbox to the candidate NPC hitbox",
        "both assigned and scanned targets", "hard geometric", "assigned NPC", "aim=velocity",
        "position={at:activation_origin}",
    ):
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


@pytest.mark.parametrize("with_provenance", [False, True])
@pytest.mark.parametrize("kind", ["item_body", "noncontroller_projectile"])
def test_targeting_extensions_require_the_executable_owner(kind, with_provenance):
    doc, _ = _fixture(**OPTIONS)
    wire = compile_runtime_program(doc)
    target = next(row for row in wire["runtimeProgram"]["entities"]
                  if row["kind"] == "item_body" if kind == "item_body") if kind == "item_body" else next(
                      row for row in wire["runtimeProgram"]["entities"]
                      if row["kind"] != "item_body" and not row.get("controller", {}).get("code"))
    target["targeting"] = dict(OPTIONS)
    if not with_provenance:
        wire.pop("runtimeContract")
    before = deepcopy(wire)
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(row.get("code") == "targeting_extension_owner" for row in report["errors"])
    assert wire == before


def test_targeting_extension_requires_a_receipt_when_contract_is_present():
    doc, _ = _fixture(**OPTIONS)
    wire = compile_runtime_program(doc)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    wire["runtimeContract"]["finalWireReceipts"] = [row for row in rows if not row["finalPath"].endswith(".targeting.count")]
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(row.get("code") == "targeting_extension_provenance" for row in report["errors"])


def test_targeting_numeric_reject_guards_are_audited():
    rows = {r["param"]: r for r in _runtime_param_bound_rows() if r["capability"] == "target_and_fire"}
    for key in ("count", "spreadRadians"):
        assert rows[key]["preserved"]
        assert rows[key]["admission"] == "reject_without_clamp"


@pytest.mark.parametrize("kind", ["temporary_helper", "stationary_projectile"])
@pytest.mark.parametrize("movement", [None, "move_straight", "orbit_projectile"])
def test_firing_controller_preserves_explicit_same_entity_movement_and_stationary_omission(kind, movement):
    doc, controller = _fixture()
    next(e for e in doc["runtimeProgram"]["entities"] if e["id"] == controller["target"])["kind"] = kind
    if movement is not None:
        motion = deepcopy(next(c for c in build_capability_witness(movement)["runtimeProgram"]["calls"] if c["fn"] == movement))
        motion.update(id="controller_motion", target=controller["target"])
        doc["runtimeProgram"]["calls"].append(motion)
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert report["ok"], report
    wire = compile_runtime_program(doc)
    assert doc == before  # No inferred movement or rewritten stationary substitute.
    target = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == controller["target"])
    assert target["controller"]["name"] == "target_and_fire"
    if movement is None:
        assert "movement" not in target
    else:
        if movement == "orbit_projectile":
            assert target["orbit"] == {"anchor": "owner_center", "radiusPx": .1, "radiansPerUpdate": .1,
                "phaseRadians": .1, "identityPhaseRadians": .1}
            assert "movement" not in target
        else:
            assert target["movement"]["name"] == movement
    shot = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == controller["params"]["shotEntity"])
    assert shot["movement"]["name"] == "move_straight"
    assert validate_runtime_wire(wire)["ok"]
    wire.pop("runtimeContract")
    assert validate_runtime_wire(wire)["ok"]


def test_firing_controller_does_not_infer_a_movement_from_unknown_wire_driver():
    doc, call = _fixture()
    wire = compile_runtime_program(doc)
    wire.pop("runtimeContract")
    controller = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == call["target"])
    controller["movement"] = {"name": "invented_orbit", "code": 999, "params": {}}
    assert not validate_runtime_wire(wire)["ok"]


def test_moving_firing_helper_velocity_modifier_obeys_declared_kinds_and_position_exclusion():
    doc, controller = _fixture()
    next(e for e in doc["runtimeProgram"]["entities"] if e["id"] == controller["target"])["kind"] = "temporary_helper"
    motion = deepcopy(next(c for c in build_capability_witness("move_straight")["runtimeProgram"]["calls"] if c["fn"] == "move_straight"))
    motion.update(id="controller_motion", target=controller["target"])
    doc["runtimeProgram"]["calls"].append(motion)
    modifier_fn = next(name for name, cap in CAPABILITY_REGISTRY.items() if cap.category == "motion_modifier")
    modifier = deepcopy(next(c for c in build_capability_witness(modifier_fn)["runtimeProgram"]["calls"] if c["fn"] == modifier_fn))
    modifier.update(id="wrong_kind_modifier", target=controller["target"])
    doc["runtimeProgram"]["calls"].append(modifier)
    assert "temporary_helper" in CAPABILITY_REGISTRY[modifier_fn].target_kinds
    assert validate_runtime_wire(compile_runtime_program(doc))["ok"]
    modifier["target"] = next(e["id"] for e in doc["runtimeProgram"]["entities"] if e["kind"] == "item_body")
    report = validate_runtime_program(doc)
    assert not report["ok"]
    assert any(e["code"] == "wrong_target_kind" for e in report["errors"])
    modifier["target"] = controller["target"]
    orbit = deepcopy(next(c for c in build_capability_witness("orbit_projectile")["runtimeProgram"]["calls"] if c["fn"] == "orbit_projectile"))
    orbit.update(id="absolute_orbit", target=controller["target"])
    doc["runtimeProgram"]["calls"].append(orbit)
    assert any(e["code"] == "exclusive_component_conflict" for e in validate_runtime_program(doc)["errors"])
