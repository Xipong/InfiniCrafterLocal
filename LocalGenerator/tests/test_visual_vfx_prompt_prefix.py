"""Outgoing provider roles, stable instructions and changing accepted recipe facts."""
from __future__ import annotations

import copy

import pytest

from prompt_packet_helpers import request_dossier
from infini_local.core import llm_config, vfx_manifest as vfx
from infini_local.core.runtime_authoring import compile_runtime_program
from infini_local.pipelines import llm_authoring_pipeline as stage
from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from test_low_level_three_stage_pipeline import _accepted_visual_data, _visual_kit, _vfx_output, wire_transport


@pytest.mark.parametrize("director,repair,mode", [
    pytest.param("visual", False, "json_schema", id="visual-director-schema"),
    pytest.param("visual", True, "json_object", id="visual-scoped-repair-object"),
    pytest.param("vfx", False, "json_object", id="vfx-director-object"),
    pytest.param("vfx", True, "json_schema", id="vfx-scoped-repair-schema"),
])
def test_provider_instructions_stay_static_while_recipe_and_parent_facts_change(wire_transport, monkeypatch, director, repair, mode):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    responses, sent = wire_transport
    packets = []
    for fixture, width in (("workbench_blade", 40), ("door_on_chain", 73)):
        data = _accepted_visual_data(fixture)
        data["name"] = fixture
        parent = {"id": 1, "name": fixture, "damage": 17, "spriteReferenceRaw": {
            "source": "TextureAssets.Item", "textureWidthPx": width, "textureHeightPx": 68,
            "currentFrame": {"source": "draw_animation", "xPx": 0, "yPx": 34, "widthPx": width, "heightPx": 32}}}
        frozen = copy.deepcopy((data, parent))
        responses.append({})
        if director == "visual":
            kwargs = {} if not repair else {
                "repair_errors": [{"path": "$.item.inventoryScale", "message": "invalid"}],
                "previous": {"schema": visual.VISUAL_KIT_SCHEMA, "item": {"inventoryScale": 99}, "entities": []},
                "repair_scope": {"fieldPermissions": {"itemPaths": ["inventoryScale"]}},
            }
            visual._request_visual_kit(data, parent, {}, {}, {}, **kwargs)
        else:
            kwargs = {} if not repair else {
                "repair_errors": [{"path": "$.slots[0].alpha", "message": "invalid"}],
                "previous": _vfx_output(data),
                "repair_scope": {"fieldPermissions": {"slots": [{"slotId": "slot_0", "paths": ["alpha"]}]}},
            }
            vfx._request(stage.call_llm_vfx_director, vfx._prompt_packet(data, parent, {}), **kwargs)
        request = sent[-1]
        assert [row["role"] for row in request["messages"]] == ["system", "developer", "user"]
        assert request["_infini_prompt_cache"] == {"instructionMessageIndex": 1}
        assert request["response_format"]["type"] == mode
        packet = request_dossier(request)
        schema = packet["responseSchema" if director == "visual" else "outputSchema"]
        if mode == "json_schema":
            assert request["response_format"]["json_schema"]["strict"] is True
            assert request["response_format"]["json_schema"]["schema"] == schema
        if director == "visual":
            parents = packet["parentFactsReadOnly" if repair else "parents"]
            assert parents["parentA"]["packet"]["raw"]["spriteReference"] == {
                "source": "TextureAssets.Item", "textureWidthPx": width, "textureHeightPx": 68,
                "currentFrame": {"source": "draw_animation", "xPx": 0, "yPx": 34, "widthPx": width, "heightPx": 32}}
            context = packet["acceptedPresentationMechanicsReadOnly"]
            assert context["gameplay"]["useTime"] == 24
            assert context["itemUse"] == data["runtimeProgram"]["itemUse"]
            assert packet["spritePresentationReadOnly"]["formulas"]["q"] == "R / max(actual final PNG frame width, height)"
        else:
            assert packet["acceptedGameplayReadOnly"] == data["gameplay"]
            mechanics = copy.deepcopy(data["runtimeProgram"])
            for row in mechanics["entities"]:
                row.pop("visual", None)
            assert packet["acceptedRuntimeProgramReadOnly"] == mechanics
            assert packet["acceptedVisualKitReadOnly" if repair else "acceptedVisualKit"] == data["visualKit"]
            surface = packet["runtimeSurfaceReadOnly" if repair else "runtimeSurface"]
            assert {("item", "on_use"), ("item", "periodic")}.issubset({(row["entityId"], row["event"]) for row in surface["runtimePairs"]})
        if repair:
            assert packet["repairScope"] == kwargs["repair_scope"]
            assert packet["exactErrors"] == kwargs["repair_errors"]
        assert (data, parent) == frozen
        packets.append(packet)
    assert sent[0]["messages"][1]["content"] == sent[1]["messages"][1]["content"]
    assert sent[0]["messages"][2]["content"] != sent[1]["messages"][2]["content"]
    assert packets[0]["responseSchema" if director == "visual" else "outputSchema"] != packets[1]["responseSchema" if director == "visual" else "outputSchema"]
    assert not responses


def test_catalog_revision_reaches_outgoing_instruction_not_recipe_tail(wire_transport, monkeypatch):
    responses, sent = wire_transport
    data = _accepted_visual_data("door_on_chain")
    responses.extend([{}, {}])
    visual._request_visual_kit(data, {}, {}, {}, {})
    catalog = copy.deepcopy(visual.visual_asset_mode_catalog())
    catalog[0]["runtimeEffect"] += " Explicit catalog revision."
    monkeypatch.setattr(visual, "visual_asset_mode_catalog", lambda: catalog)
    visual._request_visual_kit(data, {}, {}, {}, {})
    assert sent[0]["messages"][1]["content"] != sent[1]["messages"][1]["content"]
    assert sent[0]["messages"][2]["content"] == sent[1]["messages"][2]["content"]
    assert request_dossier(sent[1])["assetModeCatalog"] == catalog


@pytest.mark.parametrize("mirror", [pytest.param(False, id="independent-hitbox"), pytest.param(True, id="explicit-mirroring")])
def test_visual_receives_authored_hitbox_curve_without_selecting_sprite_scale(wire_transport, mirror):
    source = build_capability_witness("set_projectile_hitbox_curve")
    call = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "set_projectile_hitbox_curve")
    call["params"].update(startScale=0.25, endScale=8, mirrorToSprite=mirror)
    data = compile_runtime_program(source)
    before = copy.deepcopy(data)
    responses, sent = wire_transport
    responses.append({})
    visual._request_visual_kit(data, {}, {}, {}, {})
    packet = request_dossier(sent[0])
    entity = next(row for row in packet["runtimeEntities"] if "hitboxCurve" in row)
    assert entity["hitboxCurve"]["startScale"] == 0.25
    assert entity["hitboxCurve"]["endScale"] == 8
    assert entity["hitboxCurve"]["mirrorToSprite"] is mirror
    assert "q_selected * P" in packet["spritePresentationReadOnly"]["formulas"]["body"]
    assert data == before


def test_physical_geometry_is_read_only_guidance_and_can_have_no_vfx_slots(wire_transport):
    beam = compile_runtime_program(build_capability_witness("channel_beam"))
    before = copy.deepcopy(beam)
    raw = _visual_kit(beam)
    body = next(row for row in raw["entities"] if row["entityId"] == "witness_entity")
    body.update(assetMode="runtime_geometry", visualProjectRef="none")
    authored = _vfx_output(beam)
    authored["slots"] = []
    responses, sent = wire_transport
    responses.extend([raw, authored])
    projected = visual.apply_visual_director(beam, {}, {}, {}, {})
    packet = request_dossier(sent[0])
    entity = next(row for row in packet["runtimeEntities"] if row["controller"].get("name") == "channel_beam")
    assert entity["controller"]["params"]["rangeTiles"] == 1.0
    assert "collision" in entity["driverMeaningReadOnly"]["controller"]
    final = vfx.attach_hybrid_vfx_manifest(projected, "beam-geometry", llm_director=stage.call_llm_vfx_director)
    surface = request_dossier(sent[1])["runtimeSurface"]
    assert "beam" in next(row["sources"] for row in surface["texturedPathSources"] if row["entityId"] == "witness_entity")
    assert final["vfxManifest"]["slots"] == []
    assert final["runtimeProgram"]["entities"][1]["visual"]["assetMode"] == "runtime_geometry"
    assert final["runtimeProgram"]["entities"][1]["controller"] == before["runtimeProgram"]["entities"][1]["controller"]
    assert final["gameplay"] == before["gameplay"]
    assert not responses


def test_visual_style_changes_advisory_system_only(wire_transport, monkeypatch):
    data = _accepted_visual_data("door_on_chain")
    responses, sent = wire_transport
    responses.extend([{}, {}])
    monkeypatch.setattr(llm_config, "PROMPT_STYLE", "Default", raising=False)
    visual._request_visual_kit(data, {}, {}, {}, {})
    monkeypatch.setattr(llm_config, "PROMPT_STYLE", "Terraria Like", raising=False)
    visual._request_visual_kit(data, {}, {}, {}, {})
    assert "Terraria Like art direction" in sent[1]["messages"][0]["content"]
    assert sent[0]["messages"][1:] == sent[1]["messages"][1:]
    assert sent[0]["response_format"] == sent[1]["response_format"]


def test_invalid_prompt_style_is_not_silently_defaulted(monkeypatch):
    monkeypatch.setattr(llm_config, "PROMPT_STYLE", "Unknown", raising=False)
    with pytest.raises(ValueError, match="INFINI_PROMPT_STYLE"):
        stage.build_initial_author_request({}, {}, {}, {}, "invalid-style", model_name="test-model")


def test_generated_parent_visual_calibration_stays_in_visual_tail_not_gameplay(wire_transport):
    parent = {"id": 1, "name": "same proxy", "width": 999, "height": 888,
              "generatedData": {"id": "exact-definition", "gameplay": {"damage": 19},
                                "visual": {"renderSizePx": 47, "preferredCanvasSize": 32, "spritePath": "private.png"},
                                "runtimeProgram": {"entities": [], "bindings": []}}}
    before = copy.deepcopy(parent)
    data = _accepted_visual_data("door_on_chain")
    responses, sent = wire_transport
    responses.extend([{}, {}])
    visual._request_visual_kit(data, parent, {}, {}, {})
    parent["generatedData"]["visual"]["renderSizePx"] = 48
    visual._request_visual_kit(data, parent, {}, {}, {})
    packets = [request_dossier(request)["parents"]["parentA"]["packet"] for request in sent]
    assert packets[0]["raw"]["generatedParent"]["visual"] == {"renderSizePx": 47, "preferredCanvasSize": 32}
    assert packets[1]["raw"]["generatedParent"]["visual"]["renderSizePx"] == 48
    assert sent[0]["messages"][1]["content"] == sent[1]["messages"][1]["content"]
    assert sent[0]["messages"][2]["content"] != sent[1]["messages"][2]["content"]
    request, _, _ = stage.build_initial_author_request(before, {}, {}, {}, "parent-control", model_name="test-model")
    gameplay = request_dossier(request)["parents"]["A"]["packet"]
    assert gameplay["raw"]["generatedParent"]["gameplay"] == {"damage": 19}
    assert "visual" not in gameplay["raw"]["generatedParent"]
    older = copy.deepcopy(before)
    older["generatedData"]["visual"].pop("renderSizePx")
    assert "renderSizePx" not in raw_parent_card_for_llm(older, include_visual_reference=True)["raw"]["generatedParent"]["visual"]


@pytest.mark.parametrize("defect", ["texture-type", "frame-outside", "unobserved-location"])
def test_parent_reference_never_invents_pixels_from_gameplay_bounds(defect):
    observation = {"source": "TextureAssets.Item", "textureWidthPx": 40, "textureHeightPx": 68,
                   "currentFrame": {"source": "draw_animation", "xPx": 0, "yPx": 34, "widthPx": 40, "heightPx": 32}}
    parent = {"id": 1, "name": "literal", "width": 999, "height": 888}
    if defect == "texture-type":
        observation["textureWidthPx"] = True
    elif defect == "frame-outside":
        observation["currentFrame"]["heightPx"] = 69
    if defect == "unobserved-location":
        parent["fingerprint"] = {"spriteReferenceRaw": observation}
    else:
        parent["spriteReferenceRaw"] = observation
    before = copy.deepcopy(parent)
    raw = raw_parent_card_for_llm(parent, include_visual_reference=True)["raw"]
    if defect == "frame-outside":
        assert raw["spriteReference"] == {"source": "TextureAssets.Item", "textureWidthPx": 40, "textureHeightPx": 68}
    else:
        assert "spriteReference" not in raw
    assert parent == before


def test_public_visual_schemas_share_owner_catalogs_without_per_token_cases():
    director = visual.visual_response_schema(["item", "body"], True, item_body_id="item")["properties"]
    repair = visual.visual_repair_schema(["item", "body"], True, item_body_id="item")["properties"]
    assert director["item"]["properties"]["effectColor"]["enum"] == repair["itemPatch"]["anyOf"][0]["properties"]["effectColor"]["enum"]
    assert director["equipOverlay"]["properties"]["accessoryMount"]["enum"] == repair["equipOverlayPatch"]["anyOf"][0]["properties"]["accessoryMount"]["enum"]
    modes = {branch["properties"]["assetMode"]["const"] for branch in director["entities"]["items"]["oneOf"]}
    assert modes == {row["mode"] for row in visual.visual_asset_mode_catalog()}
