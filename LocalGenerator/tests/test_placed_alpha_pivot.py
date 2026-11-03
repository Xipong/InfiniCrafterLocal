"""Opt-in alpha-bounds pivot: real Author/compiler/final-wire boundaries, offline."""
import copy
import json

import pytest
from infini_local.core import llm_config
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.pipelines.visual import contract as visual_contract
from infini_local.pipelines.visual import request as visual_request
from infini_local.pipelines.visual import stage as visual_stage
from prompt_packet_helpers import request_dossier
from test_low_level_three_stage_pipeline import wire_transport
from test_placed_body_capability import FN, placed, placement


def test_explicit_alpha_pivot_compiles_losslessly_with_exact_receipt():
    document = placed()
    document["runtimeProgram"]["calls"][-1]["params"]["pivotSpace"] = "alpha_bounds"
    before = copy.deepcopy(document)
    report = validate_runtime_program(document)
    assert report["ok"], report["errors"]
    wire = compile_runtime_program(document)
    assert placement(wire)["placedBody"]["pivotSpace"] == "alpha_bounds"
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    receipt = next(r for r in receipts if r.get("fn") == FN and r["authoredPath"].endswith(".pivotSpace"))
    assert receipt["status"] == "delivered"
    assert receipt["value"] == "alpha_bounds"
    assert receipt["finalPath"].endswith(".placement.placedBody.pivotSpace")
    assert audit_compiler_receipts(receipts, authored_document=document, final_document=wire)["ok"]
    assert validate_runtime_wire(wire)["ok"]
    assert document == before
    # Delivery without source receipts retains this accepted low-level choice.
    final_wire = copy.deepcopy(wire)
    final_wire.pop("runtimeContract")
    assert validate_runtime_wire(json.loads(json.dumps(final_wire)))["ok"]


def test_neutral_omission_receipt_and_historical_wire_absence_preserve_frame():
    document = placed()
    before = copy.deepcopy(document)
    wire = compile_runtime_program(document)
    assert document == before
    assert placement(wire)["placedBody"]["pivotSpace"] == "frame"
    rows = wire["runtimeContract"]["finalWireReceipts"]
    receipt = next(r for r in rows if r.get("fn") == FN and r["authoredPath"].endswith(".pivotSpace"))
    assert receipt["status"] == "declared_neutral_omission" and receipt["value"] == "frame"
    assert audit_compiler_receipts(rows, authored_document=document, final_document=wire)["ok"]
    assert audit_compiler_receipts(rows, final_document=wire)["ok"]
    historical = copy.deepcopy(wire)
    historical.pop("runtimeContract")
    placement(historical)["placedBody"].pop("pivotSpace")
    assert validate_runtime_wire(historical)["ok"], validate_runtime_wire(historical)
    explicit = copy.deepcopy(document)
    explicit["runtimeProgram"]["calls"][-1]["params"]["pivotSpace"] = "frame"
    explicit_wire = compile_runtime_program(explicit)
    assert explicit_wire["runtimeProgram"] == wire["runtimeProgram"]
    assert next(r for r in explicit_wire["runtimeContract"]["finalWireReceipts"] if r.get("fn") == FN and r["authoredPath"].endswith(".pivotSpace"))["status"] == "delivered"


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_real_provider_and_visual_repair_describe_selected_basis_readonly(wire_transport, monkeypatch, mode):
    from infini_local.pipelines.author import item_contract as contract
    from infini_local.pipelines.author import request as author
    from infini_local.pipelines.visual.assets import build_visual_asset_plan
    from jsonschema import Draft202012Validator
    from test_codex_subscription_contract import _encode_nullable_fixture
    from test_low_level_three_stage_pipeline import _visual_kit

    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    document = {key: value for key, value in placed().items() if key in {"name", "category", "runtimeProgram"}}
    document["runtimeProgram"]["calls"][-1]["params"]["pivotSpace"] = "alpha_bounds"
    responses, requests = wire_transport
    local_schema = contract.author_item_response_schema()
    payload = _encode_nullable_fixture(document, local_schema) if mode == "json_schema" else document
    responses.append(payload)
    accepted = author.try_llm_plan({"name":"A"}, {"name":"B"}, "offline-alpha-pivot")
    assert accepted is not None
    request = requests[-1]
    assert request["response_format"]["type"] == mode
    if mode == "json_schema":
        Draft202012Validator(request["response_format"]["json_schema"]["schema"]).validate(payload)
    dossier = request_dossier(request)
    card = next(c for c in dossier["runtimeCapabilityContract"]["catalog"]["capabilities"] if c["fn"] == FN)
    assert set(card["params"]["pivotSpace"]["enum"]) == {"frame", "alpha_bounds"}
    wire = compile_runtime_program(accepted)
    before = copy.deepcopy(wire)
    kit = _visual_kit(wire)
    for repair in (False, True):
        responses.append(kit if not repair else {"schema":visual_contract.VISUAL_REPAIR_PATCH_SCHEMA,"note":"offline no-op"})
        visual_request._request_visual_kit(wire, {}, {}, **({"repair_errors":[],"previous":kit,"repair_scope":{}} if repair else {}))
        packet = request_dossier(requests[-1])
        guidance = packet["spritePresentationReadOnly"]["placedBody"]
        assert "pivotSpace" in guidance["ownership"]
        assert "alpha_bounds" in guidance["ownership"]
        assert "final" in guidance["ownership"]
        assert "uncropped" in guidance["ownership"]
        bindings = packet["acceptedPresentationMechanicsReadOnly"]["bindings"]
        assert bindings == wire["runtimeProgram"]["bindings"]
        assert placement({"runtimeProgram":{"bindings":bindings}})["placedBody"]["pivotSpace"] == "alpha_bounds"
    assert wire == before
    projected = visual_stage._apply_kit(wire, kit)
    frame = copy.deepcopy(projected)
    placement(frame)["placedBody"]["pivotSpace"] = "frame"
    assert build_visual_asset_plan(projected) == build_visual_asset_plan(frame)
    assert placement(projected)["placedBody"]["pivotSpace"] == "alpha_bounds"


def test_current_nested_dto_audit_classifies_optional_selector_not_hidden_storage():
    from infini_local.qa.primitive_loss_audit import placed_body_surface_audit
    report = placed_body_surface_audit()
    assert report["ok"], report
    assert report["storageByField"]["PivotSpace"] == "string?"


def test_outgoing_placement_cards_keep_native_containers_at_existing_placement(wire_transport):
    from infini_local.pipelines.author import request as author
    from test_dual_use_placeable_contract import _dual_use_placeable
    from test_placed_light_capability import lit
    responses, requests = wire_transport
    document = placed()
    document["runtimeProgram"]["calls"].append(lit()["runtimeProgram"]["calls"][-1])
    responses.append(document)
    accepted = author.try_llm_plan({"name":"A"}, {"name":"B"}, "offline-native-precondition")
    assert accepted is not None
    cards = request_dossier(requests[-1])["runtimeCapabilityContract"]["catalog"]["capabilities"]
    native = next(c for c in cards if c["fn"] == "place_tile")
    assert set(native["params"]) == {"tileId", "placeStyle"}  # No chest flag or new authored decision.
    summary = native["does"].lower()
    assert "native containers" in summary and "terraria" in summary
    assert "inventory" in summary and "return" in summary
    assert "unsupported" in summary and "callback" in summary
    for fn in (FN, "placed_light", "placed_vfx"):
        card = next(c for c in cards if c["fn"] == fn)
        summary = card["does"].lower()
        assert "footprint" in summary and "16x16/256 cells" in summary
        assert "place_tile" in card["params"]["placementCallId"]["meaning"]
        assert "waterchest" not in summary and "tile 21/style 17" not in summary
    wire = compile_runtime_program(accepted)
    assert {"placedBody", "placedLight"} <= placement(wire).keys()
    # Presentation opt-ins neither invent nor select a separate container mechanic.
    assert validate_runtime_program(lit())["ok"]
    assert validate_runtime_program(placed())["ok"]
    plain = compile_runtime_program(_dual_use_placeable())
    assert "placedBody" not in placement(plain) and "placedLight" not in placement(plain)


@pytest.mark.parametrize("bad", [None, "alpha", "FRAME", " alpha_bounds ", "", True, 0, {}, []])
def test_present_invalid_pivot_space_is_strict_without_mutation(bad):
    document = placed()
    document["runtimeProgram"]["calls"][-1]["params"]["pivotSpace"] = bad
    before = copy.deepcopy(document)
    report = validate_runtime_program(document)
    assert not report["ok"]
    assert any(e["path"].endswith(".params.pivotSpace") for e in report["errors"])
    with pytest.raises(ValueError):
        compile_runtime_program(document)
    assert document == before
    wire = compile_runtime_program(placed())
    wire.pop("runtimeContract")
    placement(wire)["placedBody"]["pivotSpace"] = bad
    before = copy.deepcopy(wire)
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(e["code"] == "invalid_placed_body" and e["path"].endswith(".pivotSpace") for e in report["errors"])
    assert wire == before


@pytest.mark.parametrize("attack", ["missing", "duplicate", "wrong-call", "wrong-path", "omission-for-alpha", "wire-value"])
def test_alpha_receipt_cannot_be_forged_or_dropped(attack):
    document = placed()
    document["runtimeProgram"]["calls"][-1]["params"]["pivotSpace"] = "alpha_bounds"
    wire = compile_runtime_program(document)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    row = next(r for r in rows if r.get("fn") == FN and r["authoredPath"].endswith(".pivotSpace"))
    if attack == "missing": rows.remove(row)
    elif attack == "duplicate": rows.append(copy.deepcopy(row))
    elif attack == "wrong-call": row["callId"] = "install_tile"
    elif attack == "wrong-path": row["finalPath"] = row["finalPath"].replace("bindings[0]", "bindings[1]")
    elif attack == "omission-for-alpha": row["status"] = "declared_neutral_omission"
    else: placement(wire)["placedBody"]["pivotSpace"] = "frame"
    for source in (None, document):
        assert not audit_compiler_receipts(rows, authored_document=source, final_document=wire)["ok"]
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("old", ["absent", "alpha_bounds", "frame", "invalid"])
def test_frozen_leaf_repair_preserves_basis_and_absence(old):
    from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
    from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
    from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
    document = placed()
    call = document["runtimeProgram"]["calls"][-1]
    if old != "absent": call["params"]["pivotSpace"] = old
    bad_leaf = "pivotSpace" if old == "invalid" else "offsetYPx"
    if old != "invalid": call["params"][bad_leaf] = 900
    report = validate_runtime_program(document)
    assert not report["ok"]
    scope = build_runtime_repair_scope(document, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id":"placed_body", "paths":[f"params.{bad_leaf}"]}]
    candidate = copy.deepcopy(call)
    candidate["params"].update(pivotSpace="alpha_bounds", offsetYPx=0, renderSizePx=512, flipY=True)
    filtered, audit = filter_repair_patch_scope(document, {"note":"leaf only", "callsUpsert":[candidate]}, scope)
    assert audit["ok"], audit
    result = apply_repair_patch(document, filtered)
    expected = copy.deepcopy(document)
    expected["runtimeProgram"]["calls"][-1]["params"][bad_leaf] = candidate["params"][bad_leaf]
    assert result == expected
    assert validate_runtime_wire(compile_runtime_program(result))["ok"]


def test_frozen_body_absence_survives_current_visibility_control_sanitizer(tmp_path, monkeypatch):
    import hashlib
    from pathlib import Path

    from infini_local.pipelines.visual import delivery as gate
    from infini_local.storage.world_storage import sanitize_recipe_for_delivery
    from PIL import Image
    path = Path(__file__).resolve().parents[2] / "tools/fixtures/placed-body-pre-alpha-delivered.json"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "90d1d3c16b4d6b0b5cf5ce69eaa25731bb3a9518b80bd8c8c896f09a585e7fa7"
    old = json.loads(raw)
    assert "pivotSpace" not in placement(old)["placedBody"]
    report = validate_runtime_wire(old)
    assert not report["ok"] and any(e["path"] == "$.runtimeProgram.itemUse.releaseTiming" for e in report["errors"])
    control = copy.deepcopy(old)
    assert control["gameplay"].pop("releaseTiming") == "immediate"
    assert control["runtimeProgram"]["itemUse"].pop("releaseTiming") == "immediate"
    control["runtimeProgram"]["itemUse"]["hideUseGraphic"] = True
    assert validate_runtime_wire(control)["ok"]
    assert placement(control) == placement(old)
    png = tmp_path / "placed.png"
    Image.new("RGBA", (32,32), (240,90,20,255)).save(png)
    monkeypatch.setattr(gate, "_resolved_asset_path", lambda p: png if p and Path(str(p)).name == "placed.png" else None)
    before = copy.deepcopy(control)
    final = sanitize_recipe_for_delivery(control)
    assert final == control == before
    assert json.loads(raw) == old and path.read_bytes() == raw
    assert "pivotSpace" not in placement(json.loads(json.dumps(final)))["placedBody"]


def test_real_final_delivery_sanitizer_keeps_alpha_choice_and_refuses_foreign_leaf(tmp_path, monkeypatch):
    from pathlib import Path

    import infini_local.pipelines.visual.stage as visual_stage
    from infini_local.pipelines.vfx.stage import attach_vfx_manifest
    from infini_local.pipelines.visual import delivery as gate
    from infini_local.storage.world_storage import is_deliverable_recipe_payload, sanitize_recipe_for_delivery
    from PIL import Image
    from test_low_level_three_stage_pipeline import _vfx_output, _visual_kit
    document = placed()
    document["runtimeProgram"]["calls"][-1]["params"]["pivotSpace"] = "alpha_bounds"
    wire = compile_runtime_program(document)
    wire = visual_stage._apply_kit(wire, _visual_kit(wire))
    wire = attach_vfx_manifest(wire, "offline-alpha-delivery", llm_director=lambda *_a, **_kw: _vfx_output(wire))
    wire.update(id="alpha_delivery_fixture", sourceMode="llm", schemaVersion=5, runtimeApiVersion="infini.runtime-program.v5")
    png = tmp_path / "alpha.png"
    image = Image.new("RGBA", (64,64)); image.paste((240,90,20,255), (7,9,49,48)); image.save(png)
    wire["visual"].update(spritePath="alpha.png", spriteStatus="generated")
    for entity in wire["runtimeProgram"]["entities"]: entity["visual"].update(spritePath="alpha.png", spriteStatus="generated")
    monkeypatch.setattr(gate, "_resolved_asset_path", lambda p: png if p and Path(str(p)).name == "alpha.png" else None)
    before = copy.deepcopy(wire)
    assert is_deliverable_recipe_payload(wire)
    final_wire = sanitize_recipe_for_delivery(wire)
    assert placement(final_wire)["placedBody"]["pivotSpace"] == "alpha_bounds"
    expected = json.loads((Path(__file__).resolve().parents[2] / "tools/fixtures/placed-alpha-pivot-delivered.json").read_text())
    # The retained native observer consumes placement/rendering, not unrelated
    # future item-stat defaults. Keep its bytes and validate both deliveries.
    report = validate_runtime_wire(expected)
    assert not report["ok"] and any(e["path"] == "$.runtimeProgram.itemUse.releaseTiming" for e in report["errors"])
    assert validate_runtime_wire(final_wire)["ok"]
    assert placement(final_wire) == placement(expected)
    # Fresh motion composition is independent of the retained native placement
    # witness. Keep complete sanitizer identity against the current input and
    # compare every retained presentation owner, including identity/multiplicity.
    from collections import Counter
    assert final_wire["runtimeProgram"] == before["runtimeProgram"]
    assert final_wire["visual"] == expected["visual"]
    assert final_wire["vfxManifest"] == before["vfxManifest"]
    def presentations(payload):
        return Counter((row["id"], row["kind"], json.dumps(row["visual"], sort_keys=True))
                       for row in payload["runtimeProgram"]["entities"])
    assert presentations(final_wire) == presentations(expected)
    assert validate_runtime_wire(json.loads(json.dumps(final_wire)))["ok"]
    assert wire == before
    for leaf, value in (("pivotSpace", None), ("foreignAlphaCrop", True)):
        bad = copy.deepcopy(wire)
        placement(bad)["placedBody"][leaf] = value
        assert not is_deliverable_recipe_payload(bad)
