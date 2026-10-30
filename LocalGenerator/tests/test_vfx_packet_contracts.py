"""VFX presentation choices survive compilation and leaf-local Repair."""
from __future__ import annotations

import copy

import pytest

from prompt_packet_helpers import request_dossier
from infini_local.core import vfx_manifest as vfx
from infini_local.pipelines import vfx_generation_pipeline as stage
from infini_local.storage.world_storage import sanitize_recipe_for_delivery
from test_low_level_three_stage_pipeline import _accepted_visual_data, _visual_kit, wire_transport
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.pipelines import visual_generation_pipeline as visual
from vfx_material_fixtures import _legacy, _sprite
from test_provider_transport_contract import loopback_transport  # noqa: F401


@pytest.mark.parametrize("format_name", ["json_object", "json_schema"])
def test_material_and_body_facts_survive_final_http_serialization(monkeypatch, loopback_transport, format_name):
    import json
    from infini_local.core import llm_config
    from infini_local.core.vfx_material_contract import vfx_model_payload
    from test_vfx_material_admission_contracts import _library_particle

    endpoint, _events = loopback_transport
    data = compile_runtime_program(build_capability_witness("beam_geometry"))
    body = data["runtimeProgram"]["entities"][1]
    body["attachment"] = {"anchor": "owner_mounted", "axisOffsetPx": 8, "normalOffsetPx": 0}
    body["reach"] = {"durationTicks": 12, "startOffsetPx": 0, "peakOffsetPx": 32,
                     "endOffsetPx": 0, "peakProgress": 0.5}
    kit = _visual_kit(data)
    kit["entities"][1].update(assetMode="no_asset", visualProjectRef="none")
    data = visual._apply_kit(data, kit)
    before = copy.deepcopy(data)
    accepted = _library_particle(data)
    accepted["slots"][0]["particle"]["count"] = 5
    invalid = copy.deepcopy(accepted)
    invalid["slots"][0]["alpha"] = 2
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": accepted["slots"], "note": "alpha only"}
    replies = [{"body": {"choices": [{"finish_reason": "stop", "message": {
        "content": json.dumps(vfx_model_payload(row))}}]}} for row in (invalid, patch)]
    base, observed = endpoint(replies)
    monkeypatch.setattr(llm_config, "OPENROUTER_BASE_URL", base)
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", format_name)
    monkeypatch.setattr(stage, "USE_LLM", True)
    final = vfx.attach_vfx_manifest(data, "http_frame_facts", llm_director=stage.call_llm_vfx_director)
    assert len(observed) == 2
    for (method, path, request, _authorization), surface_key, vocabulary_key in zip(
        observed, ("runtimeSurface", "runtimeSurfaceReadOnly"), ("runtimeVocabulary", "runtimeVocabularyReadOnly"),
    ):
        assert method == "POST" and path.endswith("/chat/completions")
        assert all(not key.startswith("_infini_") for key in request)
        assert request["response_format"]["type"] == format_name
        # Inspect the actual JSON decoded from HTTP bytes, not a stage-template mirror.
        instructions, facts = [json.loads(row["content"]) for row in request["messages"][1:]]
        semantics = instructions[vocabulary_key]["rendererSemantics"]["libraryParticle"]
        assert all(concept in semantics for concept in ("soft circular radial glow", "same captured anchor", "saturate", "white"))
        row = next(row for row in facts[surface_key]["bodyPresentation"] if row["entityId"] == body["id"])
        assert row["coverage"] == "no_body" and "image" not in row
        assert row["frame"]["attachment"] == body["attachment"]
        assert row["frame"]["reach"] == body["reach"]
        assert row["frame"]["beamStart"] == {"anchor": "projectile.Center"}
        if surface_key == "runtimeSurfaceReadOnly":
            assert facts["repairScope"]["fieldPermissions"]["slots"] == [{"slotId": accepted["slots"][0]["id"], "paths": ["alpha"]}]
    assert final["runtimeProgram"] == before["runtimeProgram"]
    assert final["debug"]["vfxDirectorRaw"] == accepted


@pytest.mark.parametrize("format_name", ["json_object", "json_schema"])
def test_actual_body_attachment_reach_and_beam_frame_reach_both_requests(wire_transport, monkeypatch, format_name):
    monkeypatch.setattr("infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE", format_name)
    data = compile_runtime_program(build_capability_witness("beam_geometry"))
    body = data["runtimeProgram"]["entities"][1]
    # Explicit final-wire presentation controls, not a new Author/compiler contract.
    body["beamGeometry"] = {"lengthPx": 64, "widthPx": 10, "raycastTiles": False}
    body["beamRamp"] = {"warmupTicks": 4, "initialWidthMultiplier": 0.5,
                        "initialDamageMultiplier": 0.7, "damageStartProgress": 0.2}
    body["attachment"] = {"anchor": "owner_mounted", "axisOffsetPx": 8, "normalOffsetPx": -2,
                          "window": {"phase": "always", "clock": "active", "startDelayTicks": 0, "durationTicks": 50}}
    body["reach"] = {"durationTicks": 12, "startOffsetPx": 0, "peakOffsetPx": 32,
                     "endOffsetPx": 0, "peakProgress": 0.5, "window": {"phase": "always"}}
    body["armPose"] = {"durationTicks": 12, "startStretch": "quarter", "peakStretch": "full",
                       "endStretch": "quarter", "peakProgress": 0.5}
    kit = _visual_kit(data)
    kit["entities"][1].update(assetMode="no_asset", visualProjectRef="none")
    data = visual._apply_kit(data, kit)
    before = copy.deepcopy(data)
    accepted = _legacy(data)
    invalid = copy.deepcopy(accepted)
    invalid["slots"][0]["alpha"] = 2
    responses, sent = wire_transport
    responses.extend([invalid, {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": accepted["slots"],
                               "note": "only alpha"}])
    final = vfx.attach_vfx_manifest(data, "body_frame", llm_director=stage.call_llm_vfx_director)
    assert len(sent) == 2 and not responses
    for request, key in zip(sent, ("runtimeSurface", "runtimeSurfaceReadOnly")):
        assert request["response_format"]["type"] == format_name
        surface = request_dossier(request)[key]
        row = next(row for row in surface["bodyPresentation"] if row["entityId"] == body["id"])
        assert row["coverage"] == "no_body" and "image" not in row
        frame = row["frame"]
        assert frame["units"] == {"distance": "native_world_pixels", "duration": "world_ticks"}
        for component in ("aim", "attachment", "reach", "armPose", "beamGeometry"):
            assert frame[component] == before["runtimeProgram"]["entities"][1][component]
        assert frame["attachmentAnchor"] == "owner.MountedCenter"
        assert frame["beamStart"] == {"anchor": "projectile.Center"}
        assert frame["beamAxis"] == "motion_axis"
        assert frame["beamRamp"] == {"warmupTicks": 4, "initialWidthMultiplier": 0.5}
        assert "grip" not in frame and "movement" not in frame and "events" not in frame
        assert "material" not in row
        assert next(row["sources"] for row in surface["texturedPathSources"] if row["entityId"] == body["id"]) == ["anchorHistory", "beam", "ownerLink"]
    assert request_dossier(sent[1])["repairScope"]["fieldPermissions"] == {
        "globals": {}, "slots": [{"slotId": accepted["slots"][0]["id"], "paths": ["alpha"]}], "assets": []}
    assert final["runtimeProgram"] == before["runtimeProgram"]
    assert final["gameplay"] == before["gameplay"] and final["visualKit"] == before["visualKit"]
    assert final["debug"]["vfxDirectorRaw"] == accepted


@pytest.mark.parametrize("format_name", ["json_object", "json_schema"])
@pytest.mark.parametrize("case", ["free_named_hand", "pose_only", "offset_hand", "hidden_main", "legacy_beam_priority"])
def test_body_frame_projection_preserves_absence_offsets_and_selected_image(wire_transport, monkeypatch, format_name, case):
    monkeypatch.setattr("infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE", format_name)
    data = compile_runtime_program(build_capability_witness("move_straight"))
    body = data["runtimeProgram"]["entities"][1]
    data["name"] = "Held front-hand sword"  # Never selects an attachment or beam.
    kit = _visual_kit(data)
    kit["item"]["grip"] = {"normalizedX": 0.1, "normalizedY": 0.8}
    kit["item"]["forwardAngleDegrees"] = -35
    if case in {"pose_only", "offset_hand"}:
        body["armPose"] = {"durationTicks": 20, "startStretch": "quarter", "peakStretch": "full",
                           "endStretch": "none", "peakProgress": 0.3}
    if case == "offset_hand":
        body["aim"] = {"source": "cursor", "turnOwner": False}
        body["attachment"] = {"anchor": "front_hand", "axisOffsetPx": 13, "normalOffsetPx": -4}
        body["reach"] = {"durationTicks": 16, "startOffsetPx": -5, "peakOffsetPx": 20,
                         "endOffsetPx": 7, "peakProgress": 0.7}
        body["rotation"] = {"mode": "aim", "offsetRadians": 0.25, "radiansPerUpdate": 0}
    if case == "hidden_main":
        kit["entities"][1].update(assetMode="no_asset", visualProjectRef="none")
        data["runtimeProgram"]["itemUse"]["hideUseGraphic"] = True
    if case == "legacy_beam_priority":
        kit["entities"][1].update(assetMode="runtime_geometry", visualProjectRef="none")
        body["controller"] = {"name": "channel_beam", "code": 1, "params": {"range": 4, "widthPx": 10}}
        body["movement"] = {"name": "move_whip_lash", "code": 18, "params": {"range": 2, "segments": 8}}
    data = visual._apply_kit(data, kit)
    before = copy.deepcopy(data)
    accepted = _legacy(data)
    invalid = copy.deepcopy(accepted)
    invalid["slots"][0]["alpha"] = 2
    responses, sent = wire_transport
    responses.extend([invalid, {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": accepted["slots"], "note": "alpha only"}])
    final = vfx.attach_vfx_manifest(data, "frame_controls", llm_director=stage.call_llm_vfx_director)
    assert len(sent) == 2 and not responses
    for request, key in zip(sent, ("runtimeSurface", "runtimeSurfaceReadOnly")):
        assert request["response_format"]["type"] == format_name
        surface = request_dossier(request)[key]
        row = next(row for row in surface["bodyPresentation"] if row["entityId"] == body["id"])
        frame = row.get("frame", {})
        for component in ("attachment", "reach", "armPose", "aim", "rotation"):
            assert (component in frame) == (component in body)
            if component in body:
                assert frame[component] == body[component]
        assert ("attachmentAnchor" in frame) == (case == "offset_hand")
        if case == "offset_hand":
            assert frame["attachmentAnchor"] == "owner.current_composite_front_hand"
        assert "grip" not in frame  # PNG-space grip is not a body/beam anchor.
        if case in {"free_named_hand", "pose_only", "offset_hand"}:
            assert row["coverage"] == "single_sprite_at_body"
            assert row["image"]["grip"] == kit["item"]["grip"]
            assert row["image"]["forwardAngleDegrees"] == -35
            assert row["image"]["renderSizePx"] == kit["item"]["renderSizePx"]
        elif case == "hidden_main":
            assert row["coverage"] == "no_body" and "image" not in row
            root_row = next(row for row in surface["bodyPresentation"] if row["entityId"] == "item")
            assert root_row["itemUse"]["hideUseGraphic"] is True
        else:
            assert row["coverage"] == "collision_beam" and row["material"] == "solid_untextured"
            assert frame["beamStart"] == {"anchor": "owner.MountedCenter", "forwardOffsetPx": 18}
            assert frame["beamAxis"] == "velocity_or_initial_direction"
            assert "lashGeometry" not in frame
            assert next(row["sources"] for row in surface["texturedPathSources"] if row["entityId"] == body["id"]) == ["anchorHistory", "beam", "ownerLink"]
        assert ("beamStart" in frame) == (case == "legacy_beam_priority")
    assert final["runtimeProgram"] == before["runtimeProgram"]
    assert final["visual"] == before["visual"] and final["visualKit"] == before["visualKit"]
    assert final["debug"]["vfxDirectorRaw"] == accepted


@pytest.mark.parametrize("audio", [False, True])
def test_executable_leaf_repair_does_not_create_delete_or_redesign_audio(wire_transport, audio):
    data = _accepted_visual_data("workbench_blade")
    before = copy.deepcopy(data)
    accepted = _legacy(data)
    visual = dict(accepted["slots"][0], id="visible")
    sound = dict(visual, id="authored_sound", rendererKind="soundCue", soundId="Tink",
                 sound={"volume": 0.37, "pitch": -0.2, "pitchVariance": 0.12})
    for field in ("color", "scale", "spread", "particleSystemId", "textureRole", "duration", "alpha", "blend", "layer", "density", "startTick", "repeatEvery"):
        sound.pop(field, None)
    accepted["slots"] = [visual, sound] if audio else [visual]
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["alpha"] = 2
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA,
             "slotsUpsert": [dict(visual, alpha=visual["alpha"]), dict(sound, soundId="Item14"), dict(sound, id="unrequested_sound")],
             "slotIdsDelete": ["authored_sound"], "note": "alpha only"}
    responses, sent = wire_transport
    responses.extend([raw, patch])
    final = vfx.attach_vfx_manifest(data, "audio-ownership", llm_director=stage.call_llm_vfx_director)
    assert final["debug"]["vfxDirectorRaw"] == accepted
    slots = final["vfxManifest"]["slots"]
    assert len(slots) == 1 + int(audio)
    if audio:
        assert slots[1]["soundId"] == "Tink"
        assert slots[1]["sound"] == {"volume": 0.37, "pitch": -0.2, "pitchVariance": 0.12}
    else:
        assert all("soundId" not in slot for slot in slots)
    packet = request_dossier(sent[1])
    assert packet["repairScope"]["fieldPermissions"] == {"globals": {}, "slots": [{"slotId": "visible", "paths": ["alpha"]}], "assets": []}
    assert final["gameplay"] == before["gameplay"] and final["runtimeProgram"] == before["runtimeProgram"]
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert [request["_infini_stage"] for request in sent] == ["vfx_director", "vfx_repair"] and not responses


def test_alpha_repair_preserves_effect_color_profiles_and_dedicated_impact(wire_transport):
    data = _accepted_visual_data("workbench_blade")
    data["visual"]["palette"] = data["visualKit"]["item"]["palette"] = ["copper and red fire prose"]
    before = copy.deepcopy(data)
    accepted = _sprite(data)
    accepted["slots"][0]["element"]["opacityProfile"]["middle"] = 0.25
    impact = dict(_legacy(data)["slots"][0], id="dedicated_impact", rendererKind="impactSprite", textureRole="impact", spriteCanvasSize=32,
                  spritePrompt="one dedicated cyan impact sprite", spriteNegativePrompt="no atlas")
    for field in ("spread", "particleSystemId", "startTick", "repeatEvery", "density"):
        impact.pop(field)
    accepted["slots"].append(impact)
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["alpha"] = 2
    candidate = copy.deepcopy(accepted["slots"][0])
    candidate["element"]["opacityProfile"]["middle"] = 0
    candidate["element"]["colorProfile"]["middle"] = {"r": 255, "g": 192, "b": 203}
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [candidate, dict(impact, spritePrompt="unrequested replacement")], "note": "alpha only"}
    responses, sent = wire_transport
    responses.extend([raw, patch])
    final = vfx.attach_vfx_manifest(data, "frozen-presentation", llm_director=stage.call_llm_vfx_director)
    assert final["debug"]["vfxDirectorRaw"] == accepted
    element = final["vfxManifest"]["slots"][0]["element"]
    assert element["colorProfile"] == {"start": {"r": 255, "g": 255, "b": 255}, "middle": {"r": 17, "g": 93, "b": 241}, "end": {"r": 210, "g": 180, "b": 140}, "curve": "linear"}
    assert element["opacityProfile"] == {"start": 0, "middle": 0.25, "end": 0, "curve": "smoothStep"}
    assert final["visual"]["palette"] == ["copper and red fire prose"]
    item = next(row for row in final["runtimeProgram"]["entities"] if row["id"] == "item")
    assert item["visual"]["impactPrompt"] == "one dedicated cyan impact sprite"
    assert final["gameplay"] == before["gameplay"]
    packet = request_dossier(sent[1])
    assert packet["repairScope"]["fieldPermissions"] == {"globals": {}, "slots": [{"slotId": "ingredient_element", "paths": ["alpha"]}], "assets": []}
    assert packet["validGeneratedContext"]["slots"] == [impact]
    assert packet["acceptedVisualKitReadOnly"] == before["visualKit"]
    assert all("sound" not in slot and "soundId" not in slot for slot in final["vfxManifest"]["slots"])
    assert vfx.validate_vfx_manifest_wire(sanitize_recipe_for_delivery(final))["ok"] and not responses
