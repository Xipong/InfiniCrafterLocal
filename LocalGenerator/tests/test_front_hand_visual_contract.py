"""Offline Visual handoffs; incoming mechanics are read-only stage fixtures."""
from __future__ import annotations

import copy
import json

import pytest

from prompt_packet_helpers import request_dossier
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.storage.world_storage import sanitize_recipe_for_delivery
from test_low_level_three_stage_pipeline import _visual_kit, wire_transport

ROOT_GRIP = {"normalizedX": 0.125, "normalizedY": 0.875}
ENTITY_GRIP = {"normalizedX": 0.23456789, "normalizedY": 0.67890123}


def _visual_input(mode="baked_sprite"):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    raw = _visual_kit(data)
    body = next(row for row in raw["entities"] if row["entityId"] == "chained_door")
    body.update(assetMode=mode, visualProjectRef="entity" if mode == "baked_sprite" else "item" if mode == "reuse_item_icon" else "none")
    if mode == "baked_sprite":
        body.update(prompt="independent handle, brass rim and three oak panels", silhouette="three panels with rim and handle",
                    visualIdentity="brass rim, oak and red handle", preferredCanvasSize=64,
                    renderSizePx=53, forwardAngleDegrees=-35, grip=copy.deepcopy(ENTITY_GRIP))
    return data, raw


def test_distinct_grip_survives_fresh_director_and_delivery(wire_transport):
    data, raw = _visual_input()
    before = copy.deepcopy(data)
    responses, requests = wire_transport
    responses.append(raw)
    projected = visual.apply_visual_director(data, {}, {})
    delivered = sanitize_recipe_for_delivery(projected)
    entity = next(row for row in delivered["runtimeProgram"]["entities"] if row["id"] == "chained_door")
    assert entity["visual"]["grip"] == ENTITY_GRIP
    assert "grip" not in delivered["visual"]
    assert delivered["gameplay"] == before["gameplay"]
    assert entity["movement"] == before["runtimeProgram"]["entities"][1]["movement"]
    assert len(requests) == 1 and not responses
    assert projected["debug"]["llmStageAccounting"]["visualRepairCalls"] == 0


def _hand_input(mode="reuse_item_icon"):
    data, raw = _visual_input(mode)
    # Explicit accepted-input fixture at the Visual boundary, not a compiler or
    # gameplay admission assertion. The mechanical lane owns that vertical slice.
    data["runtimeProgram"]["entities"][1]["movement"] = {
        "name": "move_front_hand", "code": 20,
        "params": {"aimMode": "cursor", "durationTicks": 13, "startStretch": "quarter",
                   "peakStretch": "full", "hitboxOffsetPx": 11},
    }
    return data, raw


@pytest.mark.parametrize("mode", ["reuse_item_icon", "baked_sprite"])
def test_missing_selected_grip_repairs_only_that_owner(wire_transport, mode):
    data, raw = _hand_input(mode)
    body = raw["entities"][1]
    owner = raw["item"] if mode == "reuse_item_icon" else body
    owner.pop("grip", None)
    before = copy.deepcopy(raw)
    mechanics = copy.deepcopy(data["runtimeProgram"])
    corrected: dict = dict(body, scale=4)
    if mode == "baked_sprite":
        corrected["grip"] = copy.deepcopy(ENTITY_GRIP)
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA,
                 itemPatch={"grip": ROOT_GRIP, "prompt": "hostile root rewrite"},
                 entitiesUpsert=[corrected], entityIdsDelete=[], entityIndicesDelete=[],
                 animationPlan="hostile animation", note="only selected grip")
    responses, requests = wire_transport
    responses.extend([raw, patch])
    result = visual.apply_visual_director(data, {}, {})
    assert len(requests) == 2 and not responses
    scope = request_dossier(requests[1])["repairScope"]
    expected = copy.deepcopy(before)
    if mode == "reuse_item_icon":
        expected["item"]["grip"] = ROOT_GRIP
        assert scope["fieldPermissions"]["itemPaths"] == ["grip"]
        assert scope["fieldPermissions"]["entities"] == []
        assert "grip" not in result["runtimeProgram"]["entities"][1]["visual"]
    else:
        expected["entities"][1]["grip"] = ENTITY_GRIP
        assert scope["fieldPermissions"]["itemPaths"] == []
        assert scope["fieldPermissions"]["entities"] == [{"entityId": "chained_door", "paths": ["grip"]}]
    assert result["visualKit"] == expected
    assert result["runtimeProgram"]["entities"][1]["movement"] == mechanics["entities"][1]["movement"]
    assert result["debug"]["visualRepairFilterAudit"]["ignoredChanges"]


@pytest.mark.parametrize("mode", ["reuse_item_icon", "baked_sprite"])
@pytest.mark.parametrize("field", ["grip", "renderSizePx", "forwardAngleDegrees"])
def test_delivery_and_director_reject_the_same_missing_selected_metadata(monkeypatch, mode, field):
    from infini_local.pipelines import visual_delivery_gate as gate
    data, raw = _hand_input(mode)
    if mode == "reuse_item_icon":
        raw["item"]["grip"] = copy.deepcopy(ROOT_GRIP)
    owner = raw["item"] if mode == "reuse_item_icon" else raw["entities"][1]
    owner.pop(field)
    accepted, errors = visual._validate_kit(raw, ["item", "chained_door"], "item", accepted_data=data)
    path = "$.item." + field if mode == "reuse_item_icon" else "$.entities[1]." + field
    assert accepted is None and path in {row["path"] for row in errors}
    projected = visual._apply_kit(data, raw)
    # Isolate metadata from disk/PNG health without writing image assets.
    monkeypatch.setattr(gate, "VISUAL_REQUIRE_ITEM_SPRITE", False)
    report = gate.visual_delivery_report(projected, check_backend_config=False)
    delivery_path = "$.visual." + field if mode == "reuse_item_icon" else "$.runtimeProgram.entities[1].visual." + field
    assert any(row.get("path") == delivery_path and row.get("code") == "front_hand_sprite_metadata_required"
               for row in report["problems"])


@pytest.mark.parametrize("format_name", ["json_object", "json_schema"])
def test_director_and_frozen_repair_packets_explain_exact_hand_dependencies(wire_transport, monkeypatch, format_name):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", format_name)
    data, raw = _hand_input("reuse_item_icon")
    responses, requests = wire_transport
    responses.extend([raw, dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA,
                               itemPatch={"grip": ROOT_GRIP}, entitiesUpsert=[], entityIdsDelete=[],
                               entityIndicesDelete=[], note="missing root grip")])
    visual.apply_visual_director(data, {}, {})
    for request, key in zip(requests, ("runtimeEntities", "runtimeEntitiesReadOnly")):
        assert request["response_format"]["type"] == format_name
        packet = request_dossier(request)
        row = next(row for row in packet[key] if row["id"] == "chained_door")
        assert row["movement"] == data["runtimeProgram"]["entities"][1]["movement"]
        dependency = row["spriteDependenciesReadOnly"]
        assert dependency["requiredFields"] == ["renderSizePx", "forwardAngleDegrees", "grip"]
        assert dependency["selectedOwnerByAssetMode"] == {"reuse_item_icon": "item", "baked_sprite": "entity",
                                                         "no_asset": None, "runtime_geometry": None}
        guidance = packet["spritePresentationReadOnly"]["frontHand"]
        assert "H + aimedAxis * hitboxOffsetPx" in guidance
        assert "no duplicate" in guidance
        assert "never" in guidance
    assert not responses


def test_distinct_image_request_forwards_exact_grip_without_truncating_art(monkeypatch):
    from infini_local.pipelines import visual_sprite_generation as images
    from infini_local.pipelines.visual_prompt_contracts import image_final_frame_prompt_clause
    data, raw = _hand_input("baked_sprite")
    raw["item"]["grip"] = ROOT_GRIP
    raw["entities"][1]["prompt"] = ("independent brass handle with three oak panels; " + "literal engraving " * 100)[:1400]
    data = visual._apply_kit(data, raw)
    monkeypatch.setattr(images, "IMAGE_BACKEND", "off")
    # Exercise the real image request adapter, with prompt-only policy: no PNG,
    # backend, GPU, image workspace or provider calls.
    outcome = images.generate_visual_asset(data, "runtime:held_body", raw["entities"][1]["prompt"], "",
                                          "hand_body", 64, entity_id="chained_door")
    assert outcome[3] == "prompt_only"
    prompt = data["debug"]["runtime:held_bodyFinalPrompt"]
    facts = json.JSONDecoder().raw_decode(prompt.split("Read-only final-frame facts: ", 1)[1])[0]
    assert facts["grip"] == ENTITY_GRIP
    assert facts["grip"] != ROOT_GRIP
    assert raw["entities"][1]["prompt"] in prompt
    assert "visible handle/hand-contact region must contain the declared final-space grip" in prompt
    assert facts["movementReadOnly"] == data["runtimeProgram"]["entities"][1]["movement"]
    assert not image_final_frame_prompt_clause(data, "impact", 32, entity_id="chained_door")


@pytest.mark.parametrize("mode", ["no_asset", "runtime_geometry"])
def test_non_png_hand_modes_do_not_require_grip(wire_transport, mode):
    from infini_local.core.visual_contract_schema import front_hand_sprite_errors
    data, raw = _hand_input(mode)
    responses, requests = wire_transport
    responses.append(raw)
    result = visual.apply_visual_director(data, {}, {})
    assert not front_hand_sprite_errors(result)
    assert "grip" not in result["visual"]
    assert "grip" not in result["runtimeProgram"]["entities"][1]["visual"]
    assert len(requests) == 1 and not responses


@pytest.mark.parametrize("fault", ["entity", "project", "duplicate", "opcode", "name"])
def test_unresolved_identity_or_unselected_driver_never_diagnoses_grip(fault):
    from infini_local.core.visual_contract_schema import front_hand_sprite_errors
    data, raw = _hand_input("reuse_item_icon")
    if fault == "entity":
        raw["entities"][1]["entityId"] = "unknown"
    elif fault == "project":
        raw["entities"][1]["visualProjectRef"] = "unknown"
    elif fault == "duplicate":
        raw["entities"].append(copy.deepcopy(raw["entities"][1]))
    else:
        data["runtimeProgram"]["entities"][1]["movement"]["code" if fault == "opcode" else "name"] = 19 if fault == "opcode" else "move_forward_then_retract"
    assert not front_hand_sprite_errors(data, kit=raw)


@pytest.mark.parametrize("bad_grip,leaf", [
    (None, "grip"), ({"normalizedX": 0.2}, "grip.normalizedY"),
    ({"normalizedX": True, "normalizedY": 0.7}, "grip.normalizedX"),
    ({"normalizedX": 0.2, "normalizedY": float("nan")}, "grip.normalizedY"),
    ({"normalizedX": 0.2, "normalizedY": 1.1}, "grip.normalizedY"),
])
def test_distinct_atomic_grip_rejects_invalid_presence_at_exact_leaf(bad_grip, leaf):
    from infini_local.core.visual_contract_schema import front_hand_sprite_errors
    data, raw = _hand_input("baked_sprite")
    raw["entities"][1]["grip"] = bad_grip
    accepted, errors = visual._validate_kit(raw, ["item", "chained_door"], "item", accepted_data=data)
    assert accepted is None and "$.entities[1]." + leaf in {row["path"] for row in errors}
    projected = visual._apply_kit(data, raw)
    assert "$.runtimeProgram.entities[1].visual." + leaf in {row["path"] for row in front_hand_sprite_errors(projected)}


def test_partial_distinct_grip_repair_preserves_valid_coordinate(wire_transport):
    data, raw = _hand_input("baked_sprite")
    raw["entities"][1]["grip"]["normalizedY"] = 2
    corrected = copy.deepcopy(raw["entities"][1])
    corrected["grip"] = {"normalizedX": 0.9, "normalizedY": ENTITY_GRIP["normalizedY"]}
    responses, requests = wire_transport
    responses.extend([raw, dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA,
                               itemPatch=None, entitiesUpsert=[corrected], entityIdsDelete=[],
                               entityIndicesDelete=[], note="Y only")])
    result = visual.apply_visual_director(data, {}, {})
    assert result["visualKit"]["entities"][1]["grip"] == ENTITY_GRIP
    assert request_dossier(requests[1])["repairScope"]["fieldPermissions"]["entities"] == [
        {"entityId": "chained_door", "paths": ["grip.normalizedY"]}]
    assert result["debug"]["visualRepairFilterAudit"]["ignoredChanges"]


def test_delivery_missing_root_owner_reports_exact_missing_metadata():
    from infini_local.core.visual_contract_schema import front_hand_sprite_errors
    data, raw = _hand_input("reuse_item_icon")
    projected = visual._apply_kit(data, raw)
    projected.pop("visual")
    assert {row["path"] for row in front_hand_sprite_errors(projected)} == {
        "$.visual.renderSizePx", "$.visual.forwardAngleDegrees", "$.visual.grip"}


def test_delivery_rejects_duplicate_reuse_grip_even_with_valid_root():
    from infini_local.core.visual_contract_schema import front_hand_sprite_errors
    data, raw = _hand_input("reuse_item_icon")
    raw["item"]["grip"] = ROOT_GRIP
    projected = visual._apply_kit(data, raw)
    projected["runtimeProgram"]["entities"][1]["visual"]["grip"] = ROOT_GRIP
    errors = front_hand_sprite_errors(projected)
    assert {row["path"] for row in errors} == {"$.runtimeProgram.entities[1].visual.grip"}
    assert errors[0]["code"] == "nonowning_sprite_presentation"


@pytest.mark.parametrize("mode", ["reuse_item_icon", "baked_sprite"])
def test_real_image_retry_keeps_selected_owner_grip_without_png_or_provider_calls(monkeypatch, tmp_path, mode):
    from infini_local.pipelines import visual_sprite_generation as images
    data, raw = _hand_input(mode)
    raw["item"]["grip"] = ROOT_GRIP
    projected = visual._apply_kit(data, raw)
    monkeypatch.setattr(images, "IMAGE_BACKEND", "openai_codex")
    monkeypatch.setattr(images, "IMAGE_BACKEND_CONFIG_ERROR", "")
    monkeypatch.setattr(images, "SPRITE_RETRIES", 1)
    monkeypatch.setattr(images, "_new_image_workspace", lambda: tmp_path)
    calls = []

    def offline_no_image(prompt, negative, asset_id, canvas, *, output_dir=None):
        calls.append(prompt)
        return []  # Explicit offline failed image response, no PNG writes.

    monkeypatch.setattr(images, "generate_openai_codex", offline_no_image)
    if mode == "reuse_item_icon":
        role, entity_id, canvas, authored = "item", "", 32, raw["item"]["prompt"]
    else:
        role, entity_id, canvas, authored = "runtime:held_body", "chained_door", 64, raw["entities"][1]["prompt"]
    images.generate_visual_asset(projected, role, authored, "", "retry_hand", canvas, entity_id=entity_id)
    assert len(calls) == 2
    frames = [json.JSONDecoder().raw_decode(prompt.split("Read-only final-frame facts: ", 1)[1])[0] for prompt in calls]
    assert frames[0] == frames[1]
    assert frames[0]["grip"] == (ROOT_GRIP if mode == "reuse_item_icon" else ENTITY_GRIP)
    if mode == "reuse_item_icon":
        assert frames[0]["sharedEntityMultipliers"][0]["movementReadOnly"] == data["runtimeProgram"]["entities"][1]["movement"]
    assert not list(tmp_path.rglob("*.png"))


def test_legacy_driver_omission_and_absent_grip_remain_unchanged(wire_transport):
    from infini_local.core.visual_contract_schema import front_hand_sprite_errors
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    raw = _visual_kit(data)
    responses, requests = wire_transport
    responses.append(raw)
    result = visual.apply_visual_director(data, {}, {})
    assert not front_hand_sprite_errors(result)
    assert "grip" not in result["visual"]
    assert all("grip" not in row["visual"] for row in result["runtimeProgram"]["entities"])
    assert len(requests) == 1


def test_valid_selected_metadata_has_no_dependency_errors_in_either_stage():
    from infini_local.core.visual_contract_schema import front_hand_sprite_errors
    for mode in ("reuse_item_icon", "baked_sprite"):
        data, raw = _hand_input(mode)
        raw["item"]["grip"] = ROOT_GRIP
        accepted, errors = visual._validate_kit(raw, ["item", "chained_door"], "item", accepted_data=data)
        assert accepted is not None and not errors
        delivered = sanitize_recipe_for_delivery(visual._apply_kit(data, accepted))
        assert not front_hand_sprite_errors(delivered)
