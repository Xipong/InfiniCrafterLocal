"""VFX presentation choices survive compilation and leaf-local Repair."""
from __future__ import annotations

import copy

import pytest

from prompt_packet_helpers import request_dossier
from infini_local.core import vfx_manifest as vfx
from infini_local.pipelines import llm_authoring_pipeline as stage
from infini_local.storage.world_storage import sanitize_recipe_for_delivery
from test_low_level_three_stage_pipeline import _accepted_visual_data, wire_transport
from vfx_material_fixtures import _legacy, _sprite


@pytest.mark.parametrize("audio", [pytest.param(False, id="deliberate-silence"), pytest.param(True, id="explicit-sound")])
def test_magnitude_repair_does_not_create_delete_or_redesign_audio(wire_transport, audio):
    data = _accepted_visual_data("workbench_blade")
    before = copy.deepcopy(data)
    accepted = _legacy(data)
    accepted.update(effectMagnitude=0.2, visualBudgetClass="tiny")
    sound = dict(accepted["slots"][0], id="authored_sound", rendererKind="soundCue", channel="sound", lane="cue",
                 emissionMode="none", soundId="Tink", sound={"volume": 0.37, "pitch": -0.2, "pitchVariance": 0.12})
    accepted["slots"] = [sound] if audio else []
    raw = dict(accepted, effectMagnitude=2)
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "effectMagnitude": 0.2,
             "slotsUpsert": [dict(sound, soundId="Item14"), dict(sound, id="unrequested_sound")],
             "slotIdsDelete": ["authored_sound"], "note": "magnitude only"}
    responses, sent = wire_transport
    responses.extend([raw, patch])
    final = vfx.attach_hybrid_vfx_manifest(data, "audio-ownership", llm_director=stage.call_llm_vfx_director)
    assert final["debug"]["vfxDirectorRaw"] == accepted
    slots = sanitize_recipe_for_delivery(final)["vfxManifest"]["slots"]
    if audio:
        sound_slot, = slots
        assert (sound_slot["id"], sound_slot["entityId"], sound_slot["event"], sound_slot["soundId"]) == ("authored_sound", "item", "on_use", "Tink")
        assert sound_slot["sound"] == {"volume": 0.37, "pitch": -0.2, "pitchVariance": 0.12}
    else:
        assert slots == []
    packet = request_dossier(sent[1])
    assert packet["repairScope"]["fieldPermissions"] == {"globals": {"effectMagnitude": [""]}, "slots": [], "assets": []}
    assert final["gameplay"] == before["gameplay"] and final["runtimeProgram"] == before["runtimeProgram"]
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert [request["_infini_stage"] for request in sent] == ["vfx_director", "vfx_repair"] and not responses


def test_alpha_repair_preserves_effect_color_profiles_and_dedicated_impact(wire_transport):
    data = _accepted_visual_data("workbench_blade")
    data["visual"]["effectColor"] = data["visualKit"]["item"]["effectColor"] = "cyan"
    data["visual"]["palette"] = data["visualKit"]["item"]["palette"] = ["copper and red fire prose"]
    before = copy.deepcopy(data)
    accepted = _sprite(data)
    accepted["slots"][0]["element"]["opacityProfile"]["middle"] = 0.25
    impact = dict(_legacy(data)["slots"][0], id="dedicated_impact", rendererKind="impactSprite", textureRole="impact",
                  spritePrompt="one dedicated cyan impact sprite", spriteNegativePrompt="no atlas")
    accepted["slots"].append(impact)
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["alpha"] = 2
    candidate = copy.deepcopy(accepted["slots"][0])
    candidate["element"]["opacityProfile"]["middle"] = 0
    candidate["element"]["colorProfile"]["middle"] = "pink"
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [candidate, dict(impact, spritePrompt="unrequested replacement")], "note": "alpha only"}
    responses, sent = wire_transport
    responses.extend([raw, patch])
    final = vfx.attach_hybrid_vfx_manifest(data, "frozen-presentation", llm_director=stage.call_llm_vfx_director)
    assert final["debug"]["vfxDirectorRaw"] == accepted
    element = final["vfxManifest"]["slots"][0]["element"]
    assert element["colorProfile"] == {"start": "white", "middle": "effect", "end": "tan", "curve": "linear"}
    assert element["opacityProfile"] == {"start": 0, "middle": 0.25, "end": 0, "curve": "smoothStep"}
    assert final["visual"]["effectColor"] == "cyan" and final["visual"]["palette"] == ["copper and red fire prose"]
    item = next(row for row in final["runtimeProgram"]["entities"] if row["id"] == "item")
    assert item["visual"]["impactPrompt"] == "one dedicated cyan impact sprite"
    assert final["gameplay"] == before["gameplay"]
    packet = request_dossier(sent[1])
    assert packet["repairScope"]["fieldPermissions"] == {"globals": {}, "slots": [{"slotId": "ingredient_element", "paths": ["alpha"]}], "assets": []}
    assert packet["validGeneratedContext"]["slots"] == [impact]
    assert packet["acceptedVisualKitReadOnly"] == before["visualKit"]
    assert all("sound" not in slot and "soundId" not in slot for slot in final["vfxManifest"]["slots"])
    assert vfx.validate_vfx_manifest_wire(sanitize_recipe_for_delivery(final))["ok"] and not responses
