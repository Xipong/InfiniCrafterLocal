"""Offline presentation boundary fixtures, not claimed model or native output."""
from __future__ import annotations

import copy

import pytest

from prompt_packet_helpers import request_dossier
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.qa.capability_witnesses import build_capability_witness
from test_low_level_three_stage_pipeline import _visual_kit, wire_transport

GRIP = {"normalizedX": 0.125, "normalizedY": 0.875}


def _presentation_input(mode="reuse_item_icon", *, attachment=True, pose=False):
    # The compiler owns the known baseline. The explicit final-wire additions
    # below are test controls at the presentation boundary, not compiler proof.
    data = compile_runtime_program(build_capability_witness("move_straight"))
    body = data["runtimeProgram"]["entities"][1]
    body["aim"] = {"source": "cursor", "turnOwner": False}
    if attachment:
        body["attachment"] = {"anchor": "front_hand", "axisOffsetPx": 11.5, "normalOffsetPx": -2.0}
    if pose:
        body["armPose"] = {"durationTicks": 20, "startStretch": "quarter", "peakStretch": "full",
                           "endStretch": "three_quarters", "peakProgress": 0.3}
    raw = _visual_kit(data)
    row = raw["entities"][1]
    row.update(assetMode=mode, visualProjectRef="item" if mode == "reuse_item_icon" else "entity" if mode == "baked_sprite" else "none")
    if mode == "baked_sprite":
        row.update(prompt="Three oak panels, brass rim and hand-contact handle",
                   silhouette="three panels with a handle", visualIdentity="oak and brass", preferredCanvasSize=64,
                   renderSizePx=53, forwardAngleDegrees=-35, grip=copy.deepcopy(GRIP))
    if mode == "reuse_item_icon":
        raw["item"]["grip"] = copy.deepcopy(GRIP)
    return data, raw


@pytest.mark.parametrize("mode", ["reuse_item_icon", "baked_sprite"])
@pytest.mark.parametrize("field", ["grip", "renderSizePx", "forwardAngleDegrees"])
def test_attachment_requires_exact_selected_png_owner_metadata(mode, field):
    from infini_local.core.visual_contract_schema import front_hand_sprite_errors
    data, raw = _presentation_input(mode)
    owner = raw["item"] if mode == "reuse_item_icon" else raw["entities"][1]
    owner.pop(field)
    frozen = copy.deepcopy((data, raw))
    accepted, errors = visual._validate_kit(raw, ["item", "witness_entity"], "item", accepted_data=data)
    path = ("$.item." if mode == "reuse_item_icon" else "$.entities[1].") + field
    assert accepted is None
    assert any(row["path"] == path for row in errors)
    assert any(row["path"] == path and row["code"] == "front_hand_sprite_metadata_required"
               for row in front_hand_sprite_errors(data, kit=raw))
    projected = visual._apply_kit(data, raw)
    delivery_path = ("$.visual." if mode == "reuse_item_icon" else "$.runtimeProgram.entities[1].visual.") + field
    assert any(row["path"] == delivery_path for row in front_hand_sprite_errors(projected))
    assert (data, raw) == frozen


@pytest.mark.parametrize("format_name", ["json_object", "json_schema"])
def test_visual_and_frozen_repair_expose_components_and_true_hand_semantics(wire_transport, monkeypatch, format_name):
    monkeypatch.setattr("infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE", format_name)
    data, raw = _presentation_input(pose=True)
    body = data["runtimeProgram"]["entities"][1]
    body["attachment"]["window"] = {"phase": "charging", "clock": "active", "startDelayTicks": 0, "durationTicks": 50}
    body["armPose"]["window"] = {"phase": "charging"}
    body["reach"] = {"durationTicks": 12, "startOffsetPx": -2.0, "peakOffsetPx": 35.5,
                     "endOffsetPx": 6.0, "peakProgress": 0.7, "window": {"phase": "charging"}}
    body["seek"] = [
        {"target": "cursor", "maxSpeed": 7.0, "lerpPerUpdate": 0.2, "limitSpeedToDistance": False,
         "window": {"phase": "outbound", "clock": "since_release", "startDelayTicks": 2, "durationTicks": 40}},
        {"target": "owner_center", "maxSpeed": 13.0, "lerpPerUpdate": 1.0, "limitSpeedToDistance": True,
         "window": {"phase": "returning"}},
    ]
    raw["item"].pop("grip")
    frozen = copy.deepcopy((data, raw))
    responses, requests = wire_transport
    responses.extend([raw, dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch={"grip": GRIP, "renderSizePx": 400},
                               entitiesUpsert=[], entityIdsDelete=[], entityIndicesDelete=[], note="grip only")])
    result = visual.apply_visual_director(data, {}, {})
    assert len(requests) == 2 and not responses
    for request, key in zip(requests, ("runtimeEntities", "runtimeEntitiesReadOnly")):
        assert request["response_format"]["type"] == format_name
        packet = request_dossier(request)
        row = next(row for row in packet[key] if row["id"] == "witness_entity")
        for field in ("aim", "attachment", "armPose", "reach", "seek"):
            assert row[field] == body[field]
        assert row["modifierMeaningReadOnly"]["attachment"]
        assert row["spriteDependenciesReadOnly"]["requiredFields"] == ["renderSizePx", "forwardAngleDegrees", "grip"]
        guidance = packet["spritePresentationReadOnly"]["frontHand"]
        assert "attachment.anchor=front_hand" in guidance
        assert "armPose alone" in guidance and "shared native hand" in guidance
        assert "since_release" in packet["spritePresentationReadOnly"]["motionWindows"]
    scope = request_dossier(requests[1])["repairScope"]
    assert scope["fieldPermissions"]["itemPaths"] == ["grip"]
    assert scope["fieldPermissions"]["entities"] == []
    assert result["visual"]["grip"] == GRIP
    assert result["visual"]["renderSizePx"] == frozen[1]["item"]["renderSizePx"]
    actual_mechanics = copy.deepcopy(result["runtimeProgram"])
    expected_mechanics = copy.deepcopy(frozen[0]["runtimeProgram"])
    for runtime in (actual_mechanics, expected_mechanics):
        for row in runtime["entities"]:
            row.pop("visual", None)
    assert actual_mechanics == expected_mechanics
    # Stage accounting legitimately updates diagnostics in the input; source
    # gameplay, accepted visuals and the supplied response stay immutable.
    assert {key: value for key, value in data.items() if key != "debug"} == {key: value for key, value in frozen[0].items() if key != "debug"}
    assert raw == frozen[1]


@pytest.mark.parametrize("format_name", ["json_object", "json_schema"])
@pytest.mark.parametrize("geometry,component,expected", [
    ("beam", "beamGeometry", {"lengthPx": 127.5, "widthPx": 6.25, "raycastTiles": False}),
    ("whip", "lashGeometry", {"clock": "active", "durationTicks": 35, "anchor": "owner_mounted",
                              "reachPx": 96.5, "segments": 9, "sweepStartRadians": -0.5, "sweepEndRadians": 0.7,
                              "bendRatio": 0.25, "useOwnerGravity": False, "useWhipRange": False}),
])
def test_vfx_and_frozen_repair_use_independent_collision_geometry(wire_transport, monkeypatch, format_name, geometry, component, expected):
    from infini_local.core import vfx_manifest as vfx
    from infini_local.pipelines import vfx_generation_pipeline as stage
    from test_low_level_three_stage_pipeline import _vfx_output
    monkeypatch.setattr("infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE", format_name)
    data, raw = _presentation_input("runtime_geometry", attachment=False)
    data["runtimeProgram"]["entities"][1][component] = copy.deepcopy(expected)
    data = visual._apply_kit(data, raw)
    before = copy.deepcopy(data)
    authored = _vfx_output(data)
    authored["slots"][0]["alpha"] = 2
    candidate = dict(authored["slots"][0], alpha=0.65, duration=500)
    responses, requests = wire_transport
    responses.extend([authored, {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "alpha only", "slotsUpsert": [candidate]}])
    result = vfx.attach_vfx_manifest(data, "independent-geometry", llm_director=stage.call_llm_vfx_director)
    assert len(requests) == 2 and not responses
    mechanics = copy.deepcopy(before["runtimeProgram"])
    for row in mechanics["entities"]:
        row.pop("visual", None)
    for request, surface_key, visual_key in zip(requests, ("runtimeSurface", "runtimeSurfaceReadOnly"), ("acceptedVisualKit", "acceptedVisualKitReadOnly")):
        packet = request_dossier(request)
        assert request["response_format"]["type"] == format_name
        assert packet["acceptedRuntimeProgramReadOnly"] == mechanics
        assert packet[visual_key] == before["visualKit"]
        guidance = " ".join(packet["rules"])
        assert "attachment" in guidance and "armPose" in guidance
        assert "since_release" in guidance and "since_return" in guidance
        row = next(row for row in packet[surface_key]["texturedPathSources"] if row["entityId"] == "witness_entity")
        assert row["sources"] == ["anchorHistory", geometry, "ownerLink"]
    scope = request_dossier(requests[1])["repairScope"]
    assert scope["fieldPermissions"]["slots"] == [{"slotId": "slot_0", "paths": ["alpha"]}]
    assert result["vfxManifest"]["slots"][0]["alpha"] == 0.65
    assert result["vfxManifest"]["slots"][0]["duration"] == authored["slots"][0]["duration"]
    assert {key: value for key, value in result.items() if key in before and key != "debug"} == {key: value for key, value in before.items() if key != "debug"}


@pytest.mark.parametrize("mode", ["reuse_item_icon", "baked_sprite", "no_asset", "runtime_geometry"])
@pytest.mark.parametrize("attachment,pose", [(True, False), (False, True)])
def test_hand_anchor_reader_and_pose_writer_keep_asset_choice_independent(wire_transport, mode, attachment, pose):
    from infini_local.core.visual_contract_schema import front_hand_sprite_errors, front_hand_sprite_requirement
    from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
    data, raw = _presentation_input(mode, attachment=attachment, pose=pose)
    if not attachment:
        raw["item"].pop("grip", None)
        raw["entities"][1].pop("grip", None)
    before = copy.deepcopy(data)
    responses, requests = wire_transport
    responses.append(raw)
    result = visual.apply_visual_director(data, {}, {})
    assert len(requests) == 1 and not responses
    body = result["runtimeProgram"]["entities"][1]
    assert bool(front_hand_sprite_requirement(body)) == attachment
    assert not front_hand_sprite_errors(result)
    assert body["visual"]["assetMode"] == mode
    assert body.get("attachment") == before["runtimeProgram"]["entities"][1].get("attachment")
    assert body.get("armPose") == before["runtimeProgram"]["entities"][1].get("armPose")
    plan = next(row for row in build_visual_asset_plan(result) if row["entityId"] == "witness_entity")
    if mode in {"reuse_item_icon", "baked_sprite"}:
        owner = result["visual"] if mode == "reuse_item_icon" else body["visual"]
        for field in ("renderSizePx", "forwardAngleDegrees", "grip"):
            if field in owner:
                assert plan[field] == owner[field]
        assert plan["presentationOwnerEntityId"] == ("item" if mode == "reuse_item_icon" else "witness_entity")
    else:
        assert not {"grip", "renderSizePx", "forwardAngleDegrees", "canvas"} & plan.keys()


@pytest.mark.parametrize("mode", ["reuse_item_icon", "baked_sprite"])
@pytest.mark.parametrize("with_base_flight", [True, False])
def test_real_no_image_request_carries_selected_grip_and_actual_components(monkeypatch, mode, with_base_flight):
    import json
    from infini_local.pipelines import visual_sprite_generation as images
    data, raw = _presentation_input(mode, pose=True)
    if not with_base_flight:
        data["runtimeProgram"]["entities"][1].pop("movement")
    projected = visual._apply_kit(data, raw)
    before = copy.deepcopy(projected)
    monkeypatch.setattr(images, "IMAGE_BACKEND", "off")
    role = "item" if mode == "reuse_item_icon" else "runtime:held_body"
    entity_id = "" if mode == "reuse_item_icon" else "witness_entity"
    prompt = raw["item"]["prompt"] if mode == "reuse_item_icon" else raw["entities"][1]["prompt"]
    outcome = images.generate_visual_asset(projected, role, prompt, "", "offline_hand", 64, entity_id=entity_id)
    assert outcome[3] == "prompt_only"
    final_prompt = projected["debug"][role + "FinalPrompt"]
    assert prompt in final_prompt
    facts = json.JSONDecoder().raw_decode(final_prompt.split("Read-only final-frame facts: ", 1)[1])[0]
    assert facts["grip"] == GRIP
    body_facts = facts["sharedEntityMultipliers"][0] if mode == "reuse_item_icon" else facts
    assert ("movementReadOnly" in body_facts) is with_base_flight
    if with_base_flight:
        assert body_facts["movementReadOnly"] == before["runtimeProgram"]["entities"][1]["movement"]
    for field in ("aim", "attachment", "armPose"):
        assert body_facts[field] == before["runtimeProgram"]["entities"][1][field]
    assert projected["runtimeProgram"] == before["runtimeProgram"]
    assert projected["visual"] == before["visual"]


@pytest.mark.parametrize("law,expected", [
    ("angular_sine", ["law.angular_sine.amplitudeRadiansPerSecond", "source * 60 * updatesPerTick", "radians/second"]),
    ("lateral_velocity_sine", ["law.lateral_velocity_sine.amplitudeBlocksPerSecond", "source * 60 * updatesPerTick / 16", "blocks/second"]),
    (None, None), ("unknown", None),
])
def test_source_units_preserve_explicit_sine_law_without_inferring_it(law, expected):
    from infini_local.pipelines.llm_authoring_prompt import source_wire_units_for_llm
    oscillator = {"amplitude": 0.125, **({"law": law} if law is not None else {})}
    source = {"raw": {"generatedParent": {"runtimeProgram": {"entities": [{"oscillation": oscillator}]}}}}
    before = copy.deepcopy(source)
    rows = [row for row in source_wire_units_for_llm([source])["scopes"] if row["fn"] == "oscillate_velocity"]
    if expected is not None:
        assert len(rows) == 1
        assert rows[0]["when"] == {"law": law}
        assert rows[0]["fields"] == {"amplitude": expected}
    else:
        assert rows == []
    assert source == before


def test_author_usability_reports_only_current_catalog_choices():
    from infini_local.pipelines.llm_authoring_prompt import planner_prompt_usability_report
    report = planner_prompt_usability_report({}, {}, "current-motion")
    assert report["ok"], report


@pytest.mark.parametrize("driver,source,needs_grip", [
    # Literal driver bags from the frozen baseline compiled witnesses; this is
    # a read-only presentation replay, not fresh admission of retired calls.
    ({"movement": {"name": "move_front_hand", "code": 20, "params": {"aimMode": "initial", "durationTicks": 2,
        "startStretch": "none", "peakStretch": "none", "hitboxOffsetPx": 0.1}}}, None, True),
    ({"movement": {"name": "move_whip_lash", "code": 18, "params": {"range": 2.0, "segments": 3}}}, "whip", False),
    ({"controller": {"name": "channel_beam", "code": 1, "params": {"range": 1.0, "widthPx": 2.0,
        "warmupTicks": 1, "manaPayment": "initial_use_only", "initialDamageMultiplier": 1.0,
        "initialWidthMultiplier": 1.0, "damageStartProgress": 1.0, "raycastTiles": False}}}, "beam", False),
])
def test_accepted_historical_wire_drivers_are_presented_without_recompilation(wire_transport, driver, source, needs_grip):
    from infini_local.core import vfx_manifest as vfx
    from infini_local.pipelines import vfx_generation_pipeline as stage
    data, _ = _presentation_input(attachment=False)
    body = data["runtimeProgram"]["entities"][1]
    body.update(copy.deepcopy(driver))
    before = copy.deepcopy(data)
    responses, requests = wire_transport
    responses.extend([{}, {}])
    visual._request_visual_kit(data, {}, {})
    vfx._request(stage.call_llm_vfx_director, vfx._prompt_packet(data, {}, {}))
    row = next(row for row in request_dossier(requests[0])["runtimeEntities"] if row["id"] == body["id"])
    for key, value in driver.items():
        assert row[key] == value
    assert ("spriteDependenciesReadOnly" in row) == needs_grip
    surface = request_dossier(requests[1])["runtimeSurface"]
    sources = next(row["sources"] for row in surface["texturedPathSources"] if row["entityId"] == body["id"])
    assert sources == ["anchorHistory", *([source] if source else []), "ownerLink"]
    assert len(requests) == 2 and not responses
    assert data == before


@pytest.mark.parametrize("format_name", ["json_object", "json_schema"])
@pytest.mark.parametrize("offset", [0.0, 1.57])
def test_visual_axis_repair_keeps_world_rotation_and_delivers_declared_pixels(wire_transport, monkeypatch, format_name, offset):
    """Visual cannot compensate accepted rotation by rewriting mechanics."""
    from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
    monkeypatch.setattr("infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE", format_name)
    data, raw = _presentation_input("baked_sprite", attachment=False)
    body = data["runtimeProgram"]["entities"][1]
    body["rotation"] = {"mode": "velocity", "offsetRadians": offset, "radiansPerUpdate": 0.0}
    source = copy.deepcopy(data)
    row = raw["entities"][1]
    row["forwardAngleDegrees"] = None
    row["prompt"] = "One narrow wooden object pointing vertically upward; tip at top."
    responses, requests = wire_transport
    responses.extend([raw, {"schema": visual.VISUAL_REPAIR_PATCH_SCHEMA,
                           "entitiesUpsert": [{"entityId": row["entityId"], "forwardAngleDegrees": -90,
                                               "renderSizePx": 300}], "note": "axis only"}])
    result = visual.apply_visual_director(data, {}, {})
    assert len(requests) == 2 and not responses
    for request, key in zip(requests, ("runtimeEntities", "runtimeEntitiesReadOnly")):
        packet = request_dossier(request)
        actual = next(value for value in packet[key] if value["id"] == body["id"])
        assert actual["rotation"] == body["rotation"]
        assert actual["aim"] == body["aim"]
        # The Repair must retain relevant transform guidance as well as facts.
        assert packet["spritePresentationReadOnly"]["rotation"]
    repaired = result["runtimeProgram"]["entities"][1]
    assert repaired["rotation"] == body["rotation"]
    assert repaired["visual"]["forwardAngleDegrees"] == -90
    assert repaired["visual"]["renderSizePx"] == row["renderSizePx"]
    assert repaired["visual"]["prompt"] == row["prompt"]
    plan = next(value for value in build_visual_asset_plan(result) if value["entityId"] == body["id"])
    assert plan["forwardAngleDegrees"] == -90 and plan["prompt"] == row["prompt"]
    assert {key: value for key, value in data.items() if key != "debug"} == source


@pytest.mark.parametrize("body_mode", ["runtime_geometry", "no_asset"])
def test_selected_curve_body_and_animation_intent_reach_actual_vfx_request(wire_transport, body_mode):
    from infini_local.core import vfx_manifest as vfx
    from infini_local.pipelines import vfx_generation_pipeline as transport
    data = compile_runtime_program(build_capability_witness("lash_geometry"))
    raw = _visual_kit(data)
    raw["entities"][1].update(assetMode=body_mode, visualProjectRef="none")
    raw["animationPlan"] = "A textured copper ribbon follows the existing curved path, with a narrow dark edge."
    responses, requests = wire_transport
    responses.extend([raw, {"schema": vfx.VFX_DIRECTOR_SCHEMA, "slots": []}])
    rendered = visual.apply_visual_director(data, {}, {})
    before = copy.deepcopy(rendered)
    final = vfx.attach_vfx_manifest(rendered, "curve-presentation", llm_director=transport.call_llm_vfx_director)
    packet = request_dossier(requests[1])
    assert packet["acceptedVisualKit"] == raw
    assert packet["acceptedVisualKit"]["entities"][1]["assetMode"] == body_mode
    runtime = copy.deepcopy(before["runtimeProgram"])
    for entity in runtime["entities"]:
        entity.pop("visual", None)
    assert packet["acceptedRuntimeProgramReadOnly"] == runtime
    assert final["runtimeProgram"] == before["runtimeProgram"]
    # An advisory plan does not secretly force a slot or a second model pass.
    assert final["vfxManifest"]["slots"] == []
    assert len(requests) == 2 and not responses
