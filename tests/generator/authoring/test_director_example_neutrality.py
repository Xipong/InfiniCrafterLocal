"""Offline production packets: fewer build anecdotes, unchanged expressive contracts."""
from __future__ import annotations

from infini_local.core import llm_config
from infini_local.pipelines.vfx import request as vfx_transport

from copy import deepcopy
import json

import pytest

from prompt_packet_helpers import request_dossier
import infini_local.core.vfx.contract as vfx_contract
import infini_local.core.vfx.validation as vfx_validation
import infini_local.pipelines.vfx.prompt as vfx_prompt
import infini_local.pipelines.vfx.stage as vfx_stage
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
import infini_local.pipelines.visual.request as visual_request
from infini_local.qa.capability_witnesses import build_capability_witness


def _accepted_data():
    # The independent curve needs no retired movement/controller. Keep the
    # actual compiler and Director readers in the absent-driver path.
    source = build_capability_witness("lash_geometry")
    source["runtimeProgram"]["calls"] = [call for call in source["runtimeProgram"]["calls"] if call["fn"] != "move_straight"]
    return compile_runtime_program(source)


def _capture_visual(monkeypatch, data, *, repair=False):
    sent = []

    def offline_response(request, **_kwargs):
        sent.append(deepcopy(request))
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", "json_object")
    monkeypatch.setattr(visual_request, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(visual_request, "llm_chat_json", offline_response)
    kwargs = {"repair_errors": [], "previous": {}, "repair_scope": {}} if repair else {}
    visual_request._request_visual_kit(data, {}, {}, **kwargs)
    assert len(sent) == 1
    return sent[0], request_dossier(sent[0])


def _assert_visual_geometry_facts(data, rows):
    lash_id = next(row["id"] for row in data["runtimeProgram"]["entities"] if "lashGeometry" in row)
    matching = [row for row in rows if row["id"] == lash_id]
    assert len(matching) == 1
    assert matching[0]["bodyGeometrySourcesReadOnly"]["collision_path"] == "whip"


def test_visual_packet_exposes_accepted_lash_geometry_without_a_movement_driver(monkeypatch):
    data = _accepted_data()
    frozen = deepcopy(data)
    _, packet = _capture_visual(monkeypatch, data)
    assert packet["acceptedPresentationMechanicsReadOnly"]["bindings"] == data["runtimeProgram"]["bindings"]
    _assert_visual_geometry_facts(data, packet["runtimeEntities"])
    assert data == frozen


def _capture_vfx(monkeypatch, data, *, repair=False):
    sent = []

    def offline_response(request, **_kwargs):
        sent.append(deepcopy(request))
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", "json_object")
    monkeypatch.setattr(vfx_transport, "USE_LLM", True)
    monkeypatch.setattr(vfx_transport, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(vfx_transport, "llm_chat_json", offline_response)
    kwargs = {"repair_errors": [], "previous": {}, "repair_scope": {}} if repair else {}
    vfx_stage._request(vfx_transport.call_llm_vfx_director, vfx_prompt._prompt_packet(data, {}, {}), **kwargs)
    assert len(sent) == 1
    return sent[0], request_dossier(sent[0])


def test_vfx_packet_preserves_geometry_choices_without_adding_effects(monkeypatch):
    data = _accepted_data()
    frozen = deepcopy(data)
    _, packet = _capture_vfx(monkeypatch, data)
    mechanics = deepcopy(data["runtimeProgram"])
    for row in mechanics["entities"]:
        row.pop("visual", None)
    assert packet["acceptedRuntimeProgramReadOnly"] == mechanics
    entity = next(row for row in mechanics["entities"] if "lashGeometry" in row)
    offered = next(row for row in packet["runtimeSurface"]["texturedPathSources"]
                   if row["entityId"] == entity["id"])
    assert offered["sources"] == ["anchorHistory", "whip", "ownerLink"]
    assert packet["outputSchema"]["properties"]["slots"]["minItems"] == 0
    assert vfx_validation.validate_vfx_director_output({"schema": vfx_contract.VFX_DIRECTOR_SCHEMA, "slots": []}, data)["ok"]
    assert "vfxManifest" not in data and data == frozen

    # Geometry availability follows accepted runtime facts, not names or prose.
    without_geometry = deepcopy(data)
    next(row for row in without_geometry["runtimeProgram"]["entities"]
         if row["id"] == entity["id"]).pop("lashGeometry")
    _, without_packet = _capture_vfx(monkeypatch, without_geometry)
    without_sources = next(row["sources"] for row in without_packet["runtimeSurface"]["texturedPathSources"]
                           if row["entityId"] == entity["id"])
    assert without_sources == ["anchorHistory", "ownerLink"]
    assert without_packet["item"] == packet["item"]
    assert without_packet["runtimeSurface"]["runtimePairs"] == packet["runtimeSurface"]["runtimePairs"]


@pytest.mark.parametrize("director", ["visual", "vfx"])
def test_shared_geometry_guidance_remains_neutral_in_serialized_repair(monkeypatch, director):
    data = _accepted_data()
    capture = _capture_visual if director == "visual" else _capture_vfx
    request, packet = capture(monkeypatch, data, repair=True)
    scope = packet["repairScope"]
    assert scope == {}  # Shared presentation facts do not expand permissions.
    if director == "visual":
        _assert_visual_geometry_facts(data, packet["runtimeEntitiesReadOnly"])
    else:
        assert packet["acceptedRuntimeProgramReadOnly"]["bindings"] == data["runtimeProgram"]["bindings"]



def test_image_packet_preserves_literal_art_and_selected_facts_without_build_examples(monkeypatch):
    from infini_local.pipelines.images import backends as image
    from infini_local.core.images import config
    from infini_local.pipelines.images.prompts import normalize_asset_prompt

    monkeypatch.setattr(config, "BG_COLOR", "transparent")
    monkeypatch.setattr(image, "SDCPP_LORA_PROMPT_TAGS", "")
    monkeypatch.setattr(image, "SDCPP_LORA_FILE", "")
    data = _accepted_data()
    data["visual"] = {
        "renderSizePx": 48, "forwardAngleDegrees": 25,
        "silhouette": "two separate curved plates", "visualIdentity": "three offset inset marks",
        "grip": {"normalizedX": 0.2, "normalizedY": 0.7},
    }
    frozen = deepcopy(data)
    authored = "Two separate curved plates with three offset inset marks and a visible hand-contact region."
    prompt = normalize_asset_prompt(data, "item", authored, 64)
    # Serialize the actual adapter payload, without starting an image backend.
    payload = json.loads(json.dumps(image.sdcpp_server_payload(prompt, "no text", 64, 64, 7, "a1111")))
    text = payload["prompt"]
    assert text.startswith(authored)
    facts = json.JSONDecoder().raw_decode(text.split("Read-only final-frame facts: ", 1)[1])[0]
    for key, value in data["visual"].items():
        assert facts[key] == value
    assert facts["canvasSizePx"] == 64
    assert data == frozen
