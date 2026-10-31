from prompt_packet_helpers import request_dossier
"""Opt-in live concurrency is independent of per-activation spawn count."""

import copy
import hashlib
import json
from pathlib import Path

import pytest


from infini_local.core.runtime_authoring.capability_registry import (
    CAPABILITY_REGISTRY,
    ENTITY_KIND_REGISTRY,
    PROJECTILE_ENTITY_KINDS,
    capability_provider_union,
)
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.capability_library_audit import _runtime_param_bound_rows
from infini_local.pipelines.author import request as gameplay
from test_low_level_three_stage_pipeline import wire_transport


CAPABILITY = "projectile_limit"


def _with_concurrency(value=1):
    document = build_runtime_fixture("returning_potion")
    document["runtimeProgram"]["calls"].append({
        "id": "tonic_concurrency", "fn": CAPABILITY, "target": "tonic_flask",
        "params": {"maxActive": value},
    })
    return document


def test_explicit_concurrency_projects_only_exact_spawn_leaf_with_receipt():
    old = compile_runtime_program(build_runtime_fixture("returning_potion"))
    document = _with_concurrency()
    report = validate_runtime_program(document)
    assert report["ok"], report["errors"]
    compiled = compile_runtime_program(document)
    expected = copy.deepcopy(old["runtimeProgram"])
    entity_index = next(i for i, row in enumerate(expected["entities"]) if row["id"] == "tonic_flask")
    expected["entities"][entity_index]["spawn"]["maxActive"] = 1
    assert compiled["runtimeProgram"] == expected
    receipts = [row for row in compiled["runtimeContract"]["finalWireReceipts"] if row.get("fn") == CAPABILITY]
    assert receipts == [{
        "callId": "tonic_concurrency", "fn": CAPABILITY,
        "authoredPath": f"runtimeProgram.calls[{len(document['runtimeProgram']['calls']) - 1}].params.maxActive",
        "finalPath": f"runtimeProgram.entities[{entity_index}].spawn.maxActive",
        "value": 1, "status": "delivered",
    }]
    assert compiled["runtimeContract"]["technicalLoweringAudit"]["ok"]
    wire_report = validate_runtime_wire(compiled)
    assert wire_report["ok"], wire_report["errors"]


@pytest.mark.parametrize("value", [None, False, True, 0, 97, 1.0, "1", [], {}])
def test_present_malformed_concurrency_is_refused_at_author_and_saved_wire(value):
    document = _with_concurrency(value)
    before = copy.deepcopy(document)
    report = validate_runtime_program(document)
    assert not report["ok"]
    assert any(row["path"].endswith(".params.maxActive") for row in report["errors"])
    with pytest.raises(ValueError):
        compile_runtime_program(document)
    assert document == before

    compiled = compile_runtime_program(build_runtime_fixture("returning_potion"))
    compiled.pop("runtimeContract")  # Saved/delivery wire has no Author provenance.
    entity_index = next(i for i, row in enumerate(compiled["runtimeProgram"]["entities"]) if row["id"] == "tonic_flask")
    compiled["runtimeProgram"]["entities"][entity_index]["spawn"]["maxActive"] = value
    before = copy.deepcopy(compiled)
    report = validate_runtime_wire(compiled)
    assert not report["ok"], report
    assert any(row["path"] == f"$.runtimeProgram.entities[{entity_index}].spawn.maxActive" for row in report["errors"])
    assert compiled == before


def test_independent_return_motion_keeps_explicit_values_and_concurrency_absence():
    document = build_runtime_fixture("returning_potion")
    before = copy.deepcopy(document)
    compiled = compile_runtime_program(document)
    assert document == before
    projectile = next(row for row in compiled["runtimeProgram"]["entities"] if row["id"] == "tonic_flask")
    assert projectile["spawn"]["speedPxPerTick"] == 12
    assert projectile["spawn"]["overTarget"] == {"heightTiles": 0, "delayTicks": 0}
    assert projectile["collision"]["bounceSpeedRetention"] == 1
    assert projectile["movement"] == {"name": "move_straight", "code": 0, "params": {}}
    assert projectile["returnTrigger"] == {"afterTicks": 36, "onOwnerRelease": False,
                                            "onTileCollision": False, "disableTileCollisionOnReturn": True}
    assert projectile["seek"] == [{"target": "owner_center", "maxSpeed": 15,
                                    "velocityLerpPerUpdate": 0.2, "limitSpeedToDistance": False,
                                    "window": {"phase": "returning"}}]
    assert projectile["arrival"] == {"target": "owner_center", "radiusPx": 24,
                                      "window": {"phase": "returning"}, "action": "kill"}
    assert all("maxActive" not in row.get("spawn", {}) for row in compiled["runtimeProgram"]["entities"])
    assert not any(row.get("fn") == CAPABILITY for row in compiled["runtimeContract"]["finalWireReceipts"])
    assert audit_compiler_receipts(compiled["runtimeContract"]["finalWireReceipts"],
                                   authored_document=document, final_document=compiled)["ok"]
    assert validate_runtime_wire(compiled)["ok"]
    compiled.pop("runtimeContract")
    saved_before = copy.deepcopy(compiled)
    assert validate_runtime_wire(compiled)["ok"]
    assert compiled == saved_before
    assert all(CAPABILITY not in kind.required_components for kind in ENTITY_KIND_REGISTRY.values())
    assert "maxActive" not in CAPABILITY_REGISTRY["spawn"].params


@pytest.mark.parametrize("fn,accepted", [("set_projectile_collision", True), ("move_bounce", False)])
def test_immutable_old_wire_preserves_concurrency_absence_and_current_admission(fn, accepted):
    # Genuine archived wire, never an inverse projection of a fresh composition.
    path = Path(__file__).with_name("fixtures") / "projectile_retained_wire.json"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "9bee5ef3ff732f5b0c2aa625efd6ac487e1e645cfdfeb0cf94f40a41ecb83fea"
    archive = json.loads(raw)
    assert archive["sourceHead"] == "a3d5950"
    wire = next(row["wire"] for row in archive["cases"] if row["fn"] == fn)
    before = copy.deepcopy(wire)
    # Old diagnostic receipts remain retired even when the stripped wire is valid.
    assert not validate_runtime_wire(wire)["ok"]
    assert wire == before
    saved = copy.deepcopy(wire)
    saved.pop("runtimeContract")
    saved_before = copy.deepcopy(saved)
    report = validate_runtime_wire(saved)
    assert report["ok"] is accepted, report
    if not accepted:
        assert any(row["code"] == "unsupported_opcode" and row["path"].endswith(".movement.code")
                   for row in report["errors"])
    assert all("maxActive" not in row.get("spawn", {}) for row in saved["runtimeProgram"]["entities"])
    assert saved == saved_before
    assert path.read_bytes() == raw


def test_schema_registry_has_required_positive_param_but_optional_capability():
    cap = CAPABILITY_REGISTRY[CAPABILITY]
    variant = next(row for row in capability_provider_union() if row["properties"]["fn"]["const"] == CAPABILITY)
    params = variant["properties"]["params"]
    assert params["required"] == ["maxActive"]
    assert params["properties"]["maxActive"] == cap.params["maxActive"].schema()
    assert cap.params["maxActive"].default is None
    assert cap.params["maxActive"].neutral is None
    assert cap.component_slot == "spawn"
    assert cap.multiplicity == "single_per_target"
    assert not cap.exclusive_group
    assert cap.final_wire_paths == ("runtimeProgram.entities[].spawn.maxActive",)


# Identity projection has no value-dependent branch: cover cap below/equal/above
# the batch count, an interior value and both domain endpoints, not 96 repeats.
@pytest.mark.parametrize("value", [
    pytest.param(1, id="minimum-below-batch"),
    pytest.param(2, id="below-batch"),
    pytest.param(3, id="equal-batch"),
    pytest.param(4, id="above-batch"),
    pytest.param(48, id="interior"),
    pytest.param(96, id="maximum"),
])
def test_positive_concurrency_projection_is_exact_and_count_is_independent(value):
    document = _with_concurrency(value)
    spawn = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "spawn")
    spawn["params"]["count"] = 3  # Even count > cap is an explicit, potentially refused batch, not a rewrite.
    document["runtimeProgram"]["calls"].insert(0, document["runtimeProgram"]["calls"].pop())
    compiled = compile_runtime_program(document)
    projectile = next(row for row in compiled["runtimeProgram"]["entities"] if row["id"] == "tonic_flask")
    assert projectile["spawn"]["maxActive"] == value
    assert projectile["spawn"]["count"] == 3
    assert validate_runtime_wire(compiled)["ok"]
    compiled.pop("runtimeContract")
    assert validate_runtime_wire(compiled)["ok"]


@pytest.mark.parametrize("kind", sorted(PROJECTILE_ENTITY_KINDS))
def test_same_optional_capability_compiles_for_every_projectile_kind(kind):
    if kind == "child_projectile":
        document = build_runtime_fixture("workbench_blade")
        target = "nail"
    else:
        document = build_runtime_fixture("returning_potion")
        target = "tonic_flask"
        next(row for row in document["runtimeProgram"]["entities"] if row["id"] == target)["kind"] = kind
    document["runtimeProgram"]["calls"].append({"id": "kind_concurrency", "fn": CAPABILITY, "target": target, "params": {"maxActive": 2}})
    report = validate_runtime_program(document)
    assert report["ok"], report["errors"]
    compiled = compile_runtime_program(document)
    assert next(row for row in compiled["runtimeProgram"]["entities"] if row["id"] == target)["spawn"]["maxActive"] == 2
    assert validate_runtime_wire(compiled)["ok"]


def test_duplicate_writer_refused_while_other_entity_cap_remains_independent():
    document = _with_concurrency(3)
    duplicate = copy.deepcopy(document["runtimeProgram"]["calls"][-1])
    duplicate["id"] = "second_concurrency"
    document["runtimeProgram"]["calls"].append(duplicate)
    report = validate_runtime_program(document)
    assert any(row["code"] == "duplicate_single_component" for row in report["errors"])
    with pytest.raises(ValueError):
        compile_runtime_program(document)
    document = build_runtime_fixture("shield_and_disc")
    for target, value in (("shield_body", 1), ("shield_disc", 6)):
        document["runtimeProgram"]["calls"].append({"id": target + "_cap", "fn": CAPABILITY, "target": target, "params": {"maxActive": value}})
    compiled = compile_runtime_program(document)
    assert {row["id"]: row["spawn"]["maxActive"] for row in compiled["runtimeProgram"]["entities"] if "spawn" in row} == {"shield_body": 1, "shield_disc": 6}


def test_concurrency_rejects_item_target_and_missing_value_without_neutral_fill():
    document = _with_concurrency()
    document["runtimeProgram"]["calls"][-1]["target"] = "item"
    assert any(row["code"] == "wrong_target_kind" for row in validate_runtime_program(document)["errors"])
    document = _with_concurrency()
    document["runtimeProgram"]["calls"][-1]["params"] = {}
    report = validate_runtime_program(document)
    assert not report["ok"]
    assert any(row["path"].endswith(".params.maxActive") for row in report["errors"])


def test_automatic_vertical_witness_has_exact_opt_in_wire_receipt():
    document = build_capability_witness(CAPABILITY)
    report = validate_runtime_program(document)
    assert report["ok"], report["errors"]
    compiled = compile_runtime_program(document)
    assert validate_runtime_wire(compiled)["ok"]
    receipts = [row for row in compiled["runtimeContract"]["finalWireReceipts"] if row.get("fn") == CAPABILITY]
    assert len(receipts) == 1
    assert receipts[0]["finalPath"].endswith(".spawn.maxActive")


@pytest.mark.parametrize("mutation", ["wrong_path", "wrong_value", "wrong_status", "omitted"])
def test_exact_concurrency_receipt_proof_refuses_forgery(mutation):
    document = _with_concurrency(3)
    compiled = compile_runtime_program(document)
    receipts = compiled["runtimeContract"]["finalWireReceipts"]
    receipt = next(row for row in receipts if row.get("fn") == CAPABILITY)
    if mutation == "wrong_path":
        receipt["finalPath"] = receipt["finalPath"].replace(".maxActive", ".count")
    elif mutation == "wrong_value":
        receipt["value"] = 2
    elif mutation == "wrong_status":
        receipt["status"] = "technical_projection"
    else:
        receipts.remove(receipt)
    assert not audit_compiler_receipts(receipts, authored_document=document, final_document=compiled)["ok"]
    if mutation != "omitted":  # Wire-only cannot reconstruct absent Author calls.
        assert not validate_runtime_wire(compiled)["ok"]


def test_frozen_repair_can_change_only_invalid_concurrency_leaf():
    good = _with_concurrency(6)
    broken = copy.deepcopy(good)
    broken["runtimeProgram"]["calls"][-1]["params"]["maxActive"] = 0
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": "tonic_concurrency", "paths": ["params.maxActive"]}]
    assert scope["capabilitySubset"] == [CAPABILITY]
    assert not scope["create"]["calls"]["allowed"]
    fixed_call = copy.deepcopy(good["runtimeProgram"]["calls"][-1])
    hostile_spawn = copy.deepcopy(next(row for row in good["runtimeProgram"]["calls"] if row["fn"] == "spawn"))
    hostile_spawn["params"]["count"] = 12
    patch = {"callsUpsert": [fixed_call, hostile_spawn], "note": "Fix only invalid maxActive"}
    filtered, audit = filter_repair_patch_scope(broken, patch, scope)
    assert audit["ok"], audit
    assert audit["ignoredChanges"]
    fixed = apply_repair_patch(broken, filtered)
    assert fixed == good
    assert compile_runtime_program(fixed)["runtimeProgram"] == compile_runtime_program(good)["runtimeProgram"]


def test_unrequested_repair_cannot_add_concurrency_to_old_absent_wire():
    good = build_runtime_fixture("returning_potion")
    broken = copy.deepcopy(good)
    next(row for row in broken["runtimeProgram"]["calls"] if row["fn"] == "spawn")["params"]["count"] = 0
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    fixed_spawn = copy.deepcopy(next(row for row in good["runtimeProgram"]["calls"] if row["fn"] == "spawn"))
    unsolicited_cap = _with_concurrency()["runtimeProgram"]["calls"][-1]
    filtered, audit = filter_repair_patch_scope(broken, {"callsUpsert": [fixed_spawn, unsolicited_cap], "note": "Count only"}, scope)
    assert audit["ok"], audit
    assert audit["ignoredChanges"]
    fixed = apply_repair_patch(broken, filtered)
    assert fixed == good
    assert all("maxActive" not in row.get("spawn", {}) for row in compile_runtime_program(fixed)["runtimeProgram"]["entities"])


def test_qa_tracks_nullable_reject_bounds_instead_of_omitting_new_cap():
    rows = [row for row in _runtime_param_bound_rows() if row["capability"] == CAPABILITY]
    assert len(rows) == 1
    assert rows[0]["authorBounds"] == [1, 96]
    assert rows[0]["csharpBounds"] == [1, 96]
    assert rows[0]["csharpClass"] == "RuntimeSpawnSpec"
    assert rows[0]["admission"] == "reject_without_clamp"
    assert rows[0]["preserved"]




@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("fn,leaf,bad", [
    pytest.param("accelerate_y", "accelY", -16201, id="signed-gravity"),
    pytest.param("seek", "maxSpeed", -3.75, id="return-motion"),
    pytest.param("projectile_collision", "pierce", -2, id="pierce"),
    pytest.param(CAPABILITY, "maxActive", 0, id="concurrency"),
])
def test_contact_and_return_repairs_preserve_independent_collision_and_concurrency(wire_transport, monkeypatch, mode, fn, leaf, bad):
    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', mode)
    parent = {"id": "literal", "name": "Literal object", "damage": 7, "useTime": 20}
    if fn == "seek":
        good = _with_concurrency(6)
        # Wall return and collision disabling are separate authored choices;
        # steering and arrival must survive leaf-local speed Repair unchanged.
        trigger = next(row for row in good["runtimeProgram"]["calls"] if row["fn"] == "return_when")
        trigger["params"]["onTileCollision"] = True
    else:
        good = build_capability_witness(fn) if fn == "accelerate_y" else _with_concurrency(6)
    broken = copy.deepcopy(good)
    call = next(row for row in broken["runtimeProgram"]["calls"] if row["fn"] == fn)
    call["params"][leaf] = bad
    report = validate_runtime_program(broken)
    assert not report["ok"]
    response = copy.deepcopy(next(row for row in good["runtimeProgram"]["calls"] if row["fn"] == fn))
    responses, requests = wire_transport
    responses.append({"callsUpsert": [response], "realizationReplacement": good["realization"], "note": "Exact contact leaf"})
    fixed = gameplay.repair_author_item_after_failure(broken, parent, parent, "contact-facts", failure_report={"stage": "validation", "errors": report["errors"]})
    packet = request_dossier(requests[-1])
    repair_card = next(row for row in packet["existingBrokenCapabilityCards"] if row["fn"] == fn)
    assert repair_card == CAPABILITY_REGISTRY[fn].prompt_card()
    assert packet["repairScope"]["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params." + leaf]}]
    compiled = compile_runtime_program(fixed)
    assert compiled["runtimeProgram"] == compile_runtime_program(good)["runtimeProgram"]
    assert validate_runtime_wire(compiled)["ok"]
    if fn == "seek":
        projectile = next(row for row in compiled["runtimeProgram"]["entities"] if row["id"] == "tonic_flask")
        assert projectile["returnTrigger"]["onTileCollision"] is True
        assert projectile["returnTrigger"]["disableTileCollisionOnReturn"] is True
        assert projectile["seek"][0]["maxSpeed"] == 15
        assert projectile["seek"][0]["window"] == {"phase": "returning"}
        assert projectile["arrival"]["window"] == {"phase": "returning"}
        assert projectile["spawn"]["maxActive"] == 6
