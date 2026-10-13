from prompt_packet_helpers import request_dossier, dossier_text
"""Independent explicit placed-light vertical slice; offline, no inference."""
import copy
import json
import pytest

from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_program, validate_runtime_wire, build_runtime_repair_scope, filter_repair_patch_scope, apply_repair_patch
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from test_dual_use_placeable_contract import _dual_use_placeable
from test_placed_body_capability import placement

FN = "add_placed_light"
LIGHT = {"strength": 0.625, "color": "cyan"}


def lit():
    document = _dual_use_placeable()
    document["runtimeProgram"]["calls"].append({"id": "station_light", "fn": FN,
        "params": {"placementCallId": "install_tile", **LIGHT}})
    return document


def test_explicit_independent_light_compiles_exact_reference_and_receipts():
    document = lit()
    before = json.dumps(document, sort_keys=True)
    report = validate_runtime_program(document)
    assert report["ok"], report
    cap = CAPABILITY_REGISTRY[FN]
    assert set(cap.provider_variant_schema()["properties"]["params"]["required"]) == {"placementCallId", *LIGHT}
    assert cap.prompt_card()["params"]["placementCallId"]["reference"]["namespace"] == "call"
    wire = compile_runtime_program(document)
    assert placement(wire) == {"tileId": 19, "wallId": -1, "placeStyle": 0, "placedLight": LIGHT}
    assert validate_runtime_wire(wire)["ok"], validate_runtime_wire(wire)
    receipts = [r for r in wire["runtimeContract"]["finalWireReceipts"] if r.get("fn") == FN]
    assert len(receipts) == 3
    assert {r["authoredPath"].rsplit(".", 1)[-1] for r in receipts} == {"placementCallId", *LIGHT}
    assert audit_compiler_receipts(receipts=wire["runtimeContract"]["finalWireReceipts"], authored_document=document, final_document=wire)["ok"]
    assert json.dumps(document, sort_keys=True) == before
    plain = compile_runtime_program(_dual_use_placeable())
    assert "placedLight" not in placement(plain)
    assert "holdLightStrength" not in wire["gameplay"]
    assert all("light" not in e for e in wire["runtimeProgram"]["entities"])


@pytest.mark.parametrize("fault", ["unknown", "wrong-fn", "unused", "wall", "duplicate"])
def test_exact_placement_reference_is_model_choice_not_inferred(fault):
    document = lit()
    light = document["runtimeProgram"]["calls"][-1]
    if fault == "unknown": light["params"]["placementCallId"] = "SoulOfLight"
    elif fault == "wrong-fn": light["params"]["placementCallId"] = "item_stats"
    elif fault == "unused": document["runtimeProgram"]["bindings"] = [b for b in document["runtimeProgram"]["bindings"] if b["id"] != "alternate_install"]
    elif fault == "wall": next(c for c in document["runtimeProgram"]["calls"] if c["id"] == "install_tile").update(fn="configure_wall_placement", params={"wallId": 1, "placeStyle": 0})
    else: document["runtimeProgram"]["calls"].append({**copy.deepcopy(light), "id": "duplicate_light"})
    before = json.dumps(document, sort_keys=True)
    assert not validate_runtime_program(document)["ok"]
    with pytest.raises(ValueError): compile_runtime_program(document)
    assert json.dumps(document, sort_keys=True) == before


@pytest.mark.parametrize("bad", [None, {}, [], {"strength": 0.5}, {"color": "cyan"},
    {"strength": 0, "color": "cyan"}, {"strength": 1.51, "color": "cyan"},
    {"strength": True, "color": "cyan"}, {"strength": 0.5, "color": " Cyan "},
    {"strength": 0.5, "color": "unknown"}, {"strength": 0.5, "color": "cyan", "foreign": 1}])
def test_present_light_is_strict_without_defaults(bad):
    wire = compile_runtime_program(lit()); wire.pop("runtimeContract")
    placement(wire)["placedLight"] = bad
    assert not validate_runtime_wire(wire)["ok"]
    document = lit()
    document["runtimeProgram"]["calls"][-1]["params"] = ({"placementCallId": "install_tile", **bad} if isinstance(bad, dict) else bad)
    assert not validate_runtime_program(document)["ok"]


@pytest.mark.parametrize("attack", ["all-receipts", "association", "color", "duplicate", "path", "target-source", "status"])
def test_light_receipts_cannot_be_removed_or_forged(attack):
    document = lit(); wire = compile_runtime_program(document)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    association = next(r for r in rows if r.get("fn") == FN and r["status"] == "technical_projection")
    scalar = next(r for r in rows if r.get("fn") == FN and r["authoredPath"].endswith(".color"))
    if attack == "all-receipts": rows[:] = [r for r in rows if r.get("fn") != FN]
    elif attack == "association": rows.remove(association)
    elif attack == "color": rows.remove(scalar)
    elif attack == "duplicate": rows.append(copy.deepcopy(association))
    elif attack == "path": association["finalPath"] = "runtimeProgram.bindings[1].usePolicy.action.placement.placedLight"
    elif attack == "target-source": association["authoredPaths"][-1] = "runtimeProgram.entities[1].kind"
    else: scalar["status"] = "technical_projection"
    assert not audit_compiler_receipts(rows, authored_document=document, final_document=wire)["ok"]
    assert not validate_runtime_wire(wire)["ok"]


def test_placed_sprite_and_light_compose_without_overwriting_each_other():
    from test_placed_body_capability import placed, TRANSFORM
    document = placed(); document["runtimeProgram"]["calls"].append(lit()["runtimeProgram"]["calls"][-1])
    wire = compile_runtime_program(document)
    assert placement(wire)["placedBody"] == TRANSFORM
    assert placement(wire)["placedLight"] == LIGHT
    assert validate_runtime_wire(wire)["ok"]


def test_repair_changes_only_explicit_light_reference():
    document = lit(); document["runtimeProgram"]["calls"][-1]["params"]["placementCallId"] = "wrong"
    scope = build_runtime_repair_scope(document, validate_runtime_program(document)["errors"])
    assert scope["nonRepairableErrors"] == []
    permission = next(p for p in scope["fieldPermissions"]["calls"] if p["id"] == "station_light")
    assert permission["paths"] == ["params.placementCallId"]
    incoming = copy.deepcopy(document["runtimeProgram"]["calls"][-1])
    incoming["params"].update(placementCallId="install_tile", strength=1.5, color="red")
    filtered, audit = filter_repair_patch_scope(document, {"note": "exact dependency", "callsUpsert": [incoming]}, scope)
    assert audit["ok"]
    repaired = apply_repair_patch(document, filtered)
    expected = copy.deepcopy(document); expected["runtimeProgram"]["calls"][-1]["params"]["placementCallId"] = "install_tile"
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]


def test_registry_witness_executes_dependency_and_native_surface_audit():
    from infini_local.qa.capability_witnesses import build_capability_witness
    document = build_capability_witness(FN)
    assert validate_runtime_program(document)["ok"], validate_runtime_program(document)
    assert validate_runtime_wire(compile_runtime_program(document))["ok"]




from test_low_level_three_stage_pipeline import wire_transport


def test_real_serialized_author_repair_carries_independent_placed_light(wire_transport):
    from infini_local.pipelines import llm_authoring_pipeline as gameplay
    responses, requests = wire_transport
    document = lit(); responses.append(document)
    accepted = gameplay.try_llm_plan({"name": "A"}, {"name": "B"}, {}, {}, "offline-placed-light")
    assert accepted is not None
    payload = request_dossier(requests[-1])
    card = next(c for c in payload["runtimeCapabilityContract"]["catalog"]["capabilities"] if c["fn"] == FN)
    assert set(card["params"]) == {"placementCallId", *LIGHT}
    assert "footprint" in card["does"]
    assert "256 cells" in card["constructionMeaning"]
    assert "independent" in card["constructionMeaning"].lower()
    document["runtimeProgram"]["calls"][-1]["params"]["placementCallId"] = "wrong"
    incoming = copy.deepcopy(document["runtimeProgram"]["calls"][-1])
    incoming["params"].update(placementCallId="install_tile", strength=1.5, color="red")
    responses.append({"note": "exact reference", "realizationReplacement": copy.deepcopy(document["realization"]), "callsUpsert": [incoming]})
    repaired = gameplay.repair_author_item_after_failure(document, {}, {}, {}, {}, "offline-placed-light-repair", failure_report=validate_runtime_program(document))
    dossier = request_dossier(requests[-1])
    permission = next(p for p in dossier["repairScope"]["fieldPermissions"]["calls"] if p["id"] == "station_light")
    assert permission["paths"] == ["params.placementCallId"]
    assert dossier["repairScope"]["create"]["calls"]["allowedFns"] == []
    assert placement(compile_runtime_program(repaired))["placedLight"] == LIGHT
