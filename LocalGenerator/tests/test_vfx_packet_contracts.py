"""VFX presentation choices survive compilation and leaf-local Repair."""
from __future__ import annotations

import copy

import pytest

from prompt_packet_helpers import request_dossier
from infini_local.core import vfx_manifest as vfx
from infini_local.pipelines import vfx_generation_pipeline as stage
from infini_local.storage.world_storage import sanitize_recipe_for_delivery
from test_low_level_three_stage_pipeline import _accepted_visual_data, wire_transport
from vfx_material_fixtures import _legacy, _sprite


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
