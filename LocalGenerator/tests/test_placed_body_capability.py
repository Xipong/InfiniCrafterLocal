"""Explicit placed-body Author -> compiler -> wire tracer bullets (offline)."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import pytest
from infini_local.core.runtime_authoring import (
    validate_runtime_program, compile_runtime_program, validate_runtime_wire,
    build_runtime_repair_scope, filter_repair_patch_scope, apply_repair_patch,
)
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from test_dual_use_placeable_contract import _dual_use_placeable
from test_low_level_three_stage_pipeline import wire_transport

FN = "present_placed_item_sprite"
TRANSFORM = dict(renderSizePx=96, footprintAnchorX=0.25, footprintAnchorY=1,
                 imagePivotX=0.75, imagePivotY=1, offsetXPx=-13, offsetYPx=7,
                 rotationDegrees=-30.5, flipX=True, flipY=False)

def placed():
    document = _dual_use_placeable()
    document["runtimeProgram"]["calls"].append(dict(
        id="placed_body", fn=FN, target="item",
        params={"placementCallId": "install_tile", **TRANSFORM}))
    return document

def placement(wire):
    return next(b for b in wire["runtimeProgram"]["bindings"]
                if b["id"] == "alternate_install")["usePolicy"]["action"]["placement"]

def test_explicit_capability_has_required_schema_and_exact_compiler_projection():
    document = placed()
    before = json.dumps(document, sort_keys=True)
    report = validate_runtime_program(document)
    assert report["ok"], report["errors"]
    cap = CAPABILITY_REGISTRY[FN]
    schema = cap.provider_variant_schema()["properties"]["params"]
    assert set(schema["required"]) == {"placementCallId", *TRANSFORM}
    assert set(cap.prompt_card()["params"]) == {"placementCallId", *TRANSFORM}
    wire = compile_runtime_program(document)
    assert placement(wire) == {"tileId":19, "wallId":-1, "placeStyle":0, "placedBody":TRANSFORM}
    assert wire["runtimeContract"]["technicalLoweringAudit"]["ok"]
    assert validate_runtime_wire(wire)["ok"], validate_runtime_wire(wire)
    receipts = [r for r in wire["runtimeContract"]["finalWireReceipts"] if r.get("fn") == FN]
    assert len(receipts) == len(TRANSFORM) + 1
    assert {r["authoredPath"].rsplit(".",1)[-1] for r in receipts} == {"placementCallId", *TRANSFORM}
    association = next(r for r in receipts if r["authoredPath"].endswith(".placementCallId"))
    assert any(p.endswith(".target") for p in association["authoredPaths"])
    assert any(p.endswith(".usePolicy.action.placementCallId") for p in association["authoredPaths"])
    assert json.dumps(document, sort_keys=True) == before

@pytest.mark.parametrize("fault", ["unknown", "wrong-fn", "cross-item", "wall", "tile-and-wall", "unused", "duplicate"])
def test_bad_placement_association_rejects_without_rewriting(fault):
    document = placed()
    body = document["runtimeProgram"]["calls"][-1]
    native = next(c for c in document["runtimeProgram"]["calls"] if c["id"] == "install_tile")
    if fault == "unknown": body["params"]["placementCallId"] = "not_declared"
    elif fault == "wrong-fn": body["params"]["placementCallId"] = "item_stats"
    elif fault == "cross-item": native["target"] = "head"
    elif fault == "wall": native["params"].update(tileId=-1, wallId=1)
    elif fault == "tile-and-wall": native["params"]["wallId"] = 1
    elif fault == "unused": document["runtimeProgram"]["bindings"] = [b for b in document["runtimeProgram"]["bindings"] if b["id"] != "alternate_install"]
    elif fault == "duplicate": document["runtimeProgram"]["calls"].append({**copy.deepcopy(body), "id":"duplicate_body"})
    before = json.dumps(document, sort_keys=True)
    report = validate_runtime_program(document)
    code = "duplicate_placed_body_reference" if fault == "duplicate" else "placed_body_placement_reference"
    assert code in {r["code"] for r in report["errors"]}, report
    with pytest.raises(ValueError): compile_runtime_program(document)
    assert json.dumps(document, sort_keys=True) == before

def test_real_author_and_visual_requests_carry_capability_readonly(wire_transport):
    from infini_local.pipelines import llm_authoring_pipeline as gameplay
    from infini_local.pipelines import visual_generation_pipeline as visual
    from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
    from test_low_level_three_stage_pipeline import _visual_kit
    responses, requests = wire_transport
    document = placed()
    responses.append(document)
    accepted = gameplay.try_llm_plan({"name":"A"}, {"name":"B"}, {}, {}, "placed-body-offline")
    assert accepted is not None
    payload = json.loads(requests[-1]["messages"][1]["content"])
    cards = payload["runtimeCapabilityContract"]["catalog"]["capabilities"]
    card = next(c for c in cards if c["fn"] == FN)
    assert set(card["params"]) == {"placementCallId", *TRANSFORM}
    assert "call id" in card["constructionMeaning"] and "native" in card["constructionMeaning"]
    assert all(term in card["constructionMeaning"].lower() for term in ("certified", "16x16", "256 cells", "callbacks", "before mutation"))
    wire = compile_runtime_program(document)
    before = json.dumps(wire, sort_keys=True)
    kit = _visual_kit(wire)
    for repair in (False, True):
        responses.append(kit if not repair else {"schema":visual.VISUAL_REPAIR_PATCH_SCHEMA, "note":"offline no-op"})
        visual._request_visual_kit(wire, {}, {}, {}, {}, **({"repair_errors":[], "previous":kit, "repair_scope":{}} if repair else {}))
        packet = json.loads(requests[-1]["messages"][1]["content"])
        assert packet["acceptedPresentationMechanicsReadOnly"]["bindings"] == wire["runtimeProgram"]["bindings"]
        guidance = packet["spritePresentationReadOnly"]["placedBody"]
        assert guidance["operation"] == FN
        assert set(guidance["params"]) == {"placementCallId", *TRANSFORM}
        assert "existing" in guidance["meaning"] and "light" in guidance["meaning"]
        packet["acceptedPresentationMechanicsReadOnly"]["bindings"].clear()
    assert json.dumps(wire, sort_keys=True) == before
    with_body = visual._apply_kit(wire, kit)
    without_body = copy.deepcopy(with_body)
    placement(without_body).pop("placedBody")
    assert build_visual_asset_plan(with_body) == build_visual_asset_plan(without_body)
    assert placement(with_body)["placedBody"] == TRANSFORM


def test_explicit_placed_png_is_required_even_with_legacy_optional_policy(monkeypatch):
    from infini_local.pipelines import visual_delivery_gate as gate
    from infini_local.storage.world_storage import _cache_assets_ready
    wire = compile_runtime_program(placed())
    monkeypatch.setattr(gate, "VISUAL_REQUIRE_ITEM_SPRITE", False)
    assert not _cache_assets_ready(wire)
    report = gate.visual_delivery_report(wire, check_backend_config=False)
    assert "required_placed_body_sprite_missing" in {p["code"] for p in report["problems"]}
    assert report["requiredItemSprite"] is True
    assert next(slot for slot in report["slots"] if slot["role"] == "item")["required"] is True


def test_registry_witness_includes_executed_native_dependency():
    from infini_local.qa.capability_witnesses import build_capability_witness
    authored = build_capability_witness(FN)
    report = validate_runtime_program(authored)
    assert report["ok"], report
    wire = compile_runtime_program(authored)
    assert validate_runtime_wire(wire)["ok"]
    assert any("placedBody" in b["usePolicy"]["action"].get("placement", {}) for b in wire["runtimeProgram"]["bindings"])


@pytest.mark.parametrize("attack", ["missing-association", "wrong-target-input", "wrong-binding-path", "duplicate-association", "missing-transform", "wire-value-type"])
def test_receipt_audit_rejects_missing_or_forged_exact_association(attack):
    document = placed()
    wire = compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    association = next(r for r in receipts if r.get("fn") == FN and r["authoredPath"].endswith(".placementCallId"))
    transform = next(r for r in receipts if r.get("fn") == FN and r["authoredPath"].endswith(".flipX"))
    if attack == "missing-association": receipts.remove(association)
    elif attack == "wrong-target-input": association["authoredPaths"][1] = "runtimeProgram.calls[0].target"
    elif attack == "wrong-binding-path":
        association["finalPath"] = "runtimeProgram.bindings[1].usePolicy.action.placement.placedBody"
        wire["runtimeProgram"]["bindings"][1]["usePolicy"]["action"]["placement"] = copy.deepcopy(placement(wire))
    elif attack == "duplicate-association": receipts.append(copy.deepcopy(association))
    elif attack == "missing-transform": receipts.remove(transform)
    elif attack == "wire-value-type": placement(wire)["placedBody"]["flipX"] = 1
    assert not audit_compiler_receipts(receipts, authored_document=document, final_document=wire)["ok"]
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("fault", ["source-params", "final-binding"])
def test_malformed_receipt_context_declines_without_exception(fault):
    document = placed(); wire = compile_runtime_program(document)
    if fault == "source-params": document["runtimeProgram"]["calls"][-1]["params"] = None
    else: wire["runtimeProgram"]["bindings"][1] = None
    report = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=document, final_document=wire)
    assert not report["ok"]


def test_double_storage_metadata_preserves_tiny_present_numbers():
    document = placed()
    document["runtimeProgram"]["calls"][-1]["params"]["imagePivotX"] = 1e-100
    cap = CAPABILITY_REGISTRY[FN]
    assert cap.params["imagePivotX"].consumer_storage == "float64"
    assert cap.params["imagePivotX"].consumer_value_error(1e-100) is None
    assert validate_runtime_program(document)["ok"]
    wire = compile_runtime_program(document)
    assert placement(wire)["placedBody"]["imagePivotX"] == 1e-100
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("fault,repair", [("reference", "leaf"), ("transform", "leaf"), ("duplicate", "delete")])
def test_frozen_repair_closes_only_causal_leaf_or_duplicate_index(fault, repair):
    document = placed()
    row = document["runtimeProgram"]["calls"][-1]
    if fault == "reference": row["params"]["placementCallId"] = "wrong"
    elif fault == "transform": row["params"]["imagePivotY"] = 2
    else: document["runtimeProgram"]["calls"].append({**copy.deepcopy(row), "id":"second_presentation"})
    report = validate_runtime_program(document)
    assert not report["ok"]
    scope = build_runtime_repair_scope(document, report["errors"])
    assert scope["nonRepairableErrors"] == []
    expected = copy.deepcopy(document)
    if repair == "leaf":
        leaf = "placementCallId" if fault == "reference" else "imagePivotY"
        permission = next(p for p in scope["fieldPermissions"]["calls"] if p["id"] == "placed_body")
        assert permission["paths"] == [f"params.{leaf}"]
        incoming = copy.deepcopy(row)
        incoming["params"].update({leaf: "install_tile" if fault == "reference" else 1, "renderSizePx":512, "flipY":True})
        incoming["target"] = "arbitrary"
        patch = {"note":"exact leaf", "callsUpsert":[incoming]}
        expected["runtimeProgram"]["calls"][-1]["params"][leaf] = incoming["params"][leaf]
    else:
        index = len(document["runtimeProgram"]["calls"])-1
        assert scope["deletable"]["callIndices"] == [index]
        incoming = copy.deepcopy(row); incoming["params"]["renderSizePx"] = 512
        patch = {"note":"later duplicate", "callIndicesDelete":[index], "callsUpsert":[incoming]}
        expected["runtimeProgram"]["calls"].pop()
    filtered, audit = filter_repair_patch_scope(document, patch, scope)
    assert audit["ok"], audit
    result = apply_repair_patch(document, filtered)
    assert json.dumps(result, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert validate_runtime_program(result)["ok"]
    assert validate_runtime_wire(compile_runtime_program(result))["ok"]


def test_new_reference_requirements_and_bounds_are_in_canonical_audit():
    from infini_local.qa.capability_library_audit import capability_library_audit
    report = capability_library_audit()
    assert report["metrics"]["typedEntityReferences"] == sum(1 for c in CAPABILITY_REGISTRY.values() for p in c.params.values() if p.reference is not None and p.reference.namespace == "entity")
    assert report["metrics"]["typedCallReferences"] == 1
    relevant = [row for row in report["issues"] if FN in row.get("path", "")]
    assert not [r for r in relevant if r["code"] in {"unknown_requirement_kind", "incomplete_typed_reference"}], relevant
    from infini_local.qa.primitive_loss_audit import placed_body_surface_audit
    dto = (Path(__file__).parent / "fixtures/placed_body_parent_dto_observed.txt").read_bytes()
    observed = placed_body_surface_audit(dto)
    assert observed["boundsByField"]["RotationDegrees"] == [-180, 180]
    assert observed["boundsByField"]["ImagePivotX"] == [0, 1]
    assert not placed_body_surface_audit(dto.replace(b"RenderSizePx is < 1 or > 512", b"RenderSizePx is < 1 or > 64"))["ok"]


def test_observed_parent_dto_classification_detects_float_storage_mutant():
    from infini_local.qa import primitive_loss_audit as audit
    check = getattr(audit, "placed_body_surface_audit", None)
    assert callable(check), "new nested placed DTO requires canonical surface/storage classification"
    dto = (Path(__file__).parent / "fixtures/placed_body_parent_dto_observed.txt").read_bytes()
    report = check(dto)
    assert report["ok"], report
    assert report["storageByField"]["ImagePivotX"] == "double"
    assert not check(dto.replace(b"double ImagePivotX", b"float ImagePivotX"))["ok"]
    assert not check(dto.replace(b"public bool FlipY", b"public bool ForeignFlag"))["ok"]


@pytest.mark.parametrize("field,bad", [
    ("renderSizePx", 0), ("renderSizePx", 513), ("renderSizePx", True), ("renderSizePx", 2.5),
    ("footprintAnchorX", -0.1), ("footprintAnchorY", 1.1), ("imagePivotX", float("nan")),
    ("imagePivotY", float("inf")), ("rotationDegrees", -181), ("rotationDegrees", 181),
    ("offsetXPx", -513), ("offsetYPx", 513), ("offsetXPx", 1.5),
    ("flipX", 1), ("flipY", "false"), ("source", "foreign"),
])
def test_invalid_transform_is_rejected_at_author_and_standalone_wire(field, bad):
    document = placed()
    document["runtimeProgram"]["calls"][-1]["params"][field] = bad
    before = json.dumps(document, sort_keys=True)
    report = validate_runtime_program(document)
    assert not report["ok"] and any(r["path"].endswith(f".params.{field}") for r in report["errors"])
    with pytest.raises(ValueError): compile_runtime_program(document)
    assert json.dumps(document, sort_keys=True) == before
    wire = compile_runtime_program(placed()); wire.pop("runtimeContract")
    placement(wire)["placedBody"][field] = bad
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("field", list(TRANSFORM))
def test_each_transform_is_required_without_default_at_both_boundaries(field):
    document = placed(); document["runtimeProgram"]["calls"][-1]["params"].pop(field)
    assert not validate_runtime_program(document)["ok"]
    wire = compile_runtime_program(placed()); wire.pop("runtimeContract")
    placement(wire)["placedBody"].pop(field)
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("body", [None, [], {}, "native"])
def test_present_bad_container_is_not_absence(body):
    wire = compile_runtime_program(placed()); wire.pop("runtimeContract")
    placement(wire)["placedBody"] = body
    assert not validate_runtime_wire(wire)["ok"]


def test_real_gameplay_repair_request_retains_frozen_transform_and_native_call(wire_transport):
    from infini_local.pipelines import llm_authoring_pipeline as gameplay
    responses, requests = wire_transport
    document = placed()
    document["runtimeProgram"]["calls"][-1]["params"]["placementCallId"] = "wrong"
    broken = copy.deepcopy(document["runtimeProgram"]["calls"][-1])
    broken["params"].update(placementCallId="install_tile", renderSizePx=512, rotationDegrees=150)
    patch = {"note":"explicit exact call reference", "realizationReplacement":copy.deepcopy(document["realization"]), "callsUpsert":[broken]}
    responses.append(patch)
    result = gameplay.repair_author_item_after_failure(document, {}, {}, {}, {}, "offline-placed-repair",
                                                      failure_report=validate_runtime_program(document))
    dossier = json.loads(requests[-1]["messages"][1]["content"])
    permission = next(p for p in dossier["repairScope"]["fieldPermissions"]["calls"] if p["id"] == "placed_body")
    assert permission["paths"] == ["params.placementCallId"]
    assert dossier["repairScope"]["create"]["calls"]["allowedFns"] == []
    wire = compile_runtime_program(result)
    assert placement(wire)["placedBody"] == TRANSFORM
    assert placement(wire)["tileId"] == 19
    assert len(requests) == 1


def test_healthy_existing_root_png_delivers_and_bad_body_is_not_admitted(tmp_path, monkeypatch):
    from PIL import Image
    from infini_local.pipelines import visual_generation_pipeline as visual
    from infini_local.pipelines import visual_delivery_gate as gate
    from infini_local.storage.world_storage import is_deliverable_recipe_payload, sanitize_recipe_for_delivery
    from test_low_level_three_stage_pipeline import _visual_kit
    png = tmp_path / "placed.png"
    Image.new("RGBA", (32,32), (240,90,20,255)).save(png)
    wire = compile_runtime_program(placed())
    wire = visual._apply_kit(wire, _visual_kit(wire))
    from infini_local.core.vfx_manifest import attach_hybrid_vfx_manifest
    from test_low_level_three_stage_pipeline import _vfx_output
    wire = attach_hybrid_vfx_manifest(wire, "offline-placed-delivery", llm_director=lambda *_args, **_kwargs: _vfx_output(wire))
    wire.update(id="explicit_placed_fixture", sourceMode="llm", schemaVersion=5, runtimeApiVersion="infini.runtime-program.v5")
    wire["visual"].update(spritePath="placed.png", spriteStatus="generated")
    for entity in wire["runtimeProgram"]["entities"]:
        entity["visual"].update(spritePath="placed.png", spriteStatus="generated")
    monkeypatch.setattr(gate, "_resolved_asset_path", lambda value: png if value and Path(str(value)).name == "placed.png" else None)
    monkeypatch.setattr(gate, "VISUAL_REQUIRE_ITEM_SPRITE", False)
    report = gate.visual_delivery_report(wire, check_backend_config=False)
    assert report["ok"], report["problems"]
    assert validate_runtime_wire(wire)["ok"], validate_runtime_wire(wire)["errors"]
    from infini_local.core.vfx_manifest import validate_vfx_manifest_wire
    assert validate_vfx_manifest_wire(wire)["ok"], validate_vfx_manifest_wire(wire)
    assert is_deliverable_recipe_payload(wire)
    sanitized = sanitize_recipe_for_delivery(wire)
    assert placement(sanitized)["placedBody"] == TRANSFORM
    for mutate in (lambda p:p.update(placedBody=None), lambda p:p["placedBody"].update(offsetXPx=513)):
        bad = copy.deepcopy(wire); mutate(placement(bad))
        assert not is_deliverable_recipe_payload(bad)
    missing = copy.deepcopy(wire); missing["visual"]["spritePath"] = ""
    assert not is_deliverable_recipe_payload(missing)
    assert placement(missing)["placedBody"] == TRANSFORM


def test_absent_member_keeps_complete_legacy_compiled_bytes():
    from captured_parent_combat_author import historical_child_combat_wire
    baseline = json.loads((Path(__file__).parent / "fixtures/placed_body_legacy_wire_sha256.json").read_text())
    actual = {name:hashlib.sha256(json.dumps(historical_child_combat_wire(compile_runtime_program(build_runtime_fixture(name))), ensure_ascii=False, sort_keys=True).encode()).hexdigest() for name in baseline}
    assert actual == baseline
