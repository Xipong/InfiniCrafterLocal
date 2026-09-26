"""Numeric semantics must reach the actual Visual Director and Repair packets."""
from __future__ import annotations

import json

import pytest

from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


@pytest.fixture
def sent_packet(monkeypatch):
    requests = []
    monkeypatch.setattr(visual, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(visual, "llm_chat_json", lambda request, **_kwargs: requests.append(request) or {
        "choices": [{"message": {"content": "{}"}}]
    })
    # Exercise the required-overlay schema without substituting any schema builder.
    monkeypatch.setattr(visual, "equipment_overlay_requirement", lambda _data: {"required": True, "slot": "head"})
    # The request consumes accepted entity rows; compiling legacy fixture calls
    # is unrelated to this Visual packet contract and can drift independently.
    data = build_runtime_fixture("workbench_blade")

    def send(kind):
        kwargs = {}
        if kind == "scoped_repair":
            kwargs = {
                "repair_errors": [{"path": "$.item.inventoryScale", "message": "invalid"}],
                "previous": {"schema": visual.VISUAL_KIT_SCHEMA, "item": {"inventoryScale": "invalid"}, "entities": []},
                "repair_scope": {"itemMutable": True, "fieldPermissions": {"itemPaths": ["inventoryScale"]}},
            }
        elif kind == "malformed_repair":
            kwargs = {
                "repair_errors": [{"path": "$", "message": "malformed_json"}],
                "previous": visual.MalformedVisualDirectorOutput(raw_text="{broken", error="bad json"),
                "repair_scope": {"itemMutable": True, "fieldPermissions": {"itemPaths": [""]}},
            }
        visual._request_visual_kit(data, {}, {}, {}, {}, **kwargs)
        request = requests[-1]
        packet = json.loads(request["messages"][1]["content"])
        if request["response_format"] and request["response_format"]["type"] == "json_schema":
            assert request["response_format"]["json_schema"]["schema"] == packet["responseSchema"]
        return packet

    return send


@pytest.mark.parametrize("kind", ["director", "scoped_repair", "malformed_repair"])
def test_canvas_and_item_draw_factors_are_explained_on_wire(sent_packet, kind):
    packet = sent_packet(kind)
    props = packet["responseSchema"]["properties"]
    item = props["item"]["properties"] if kind == "director" else props["itemPatch"]["anyOf"][0]["properties"]
    overlay = props["equipOverlay"]["properties"] if kind == "director" else props["equipOverlayPatch"]["anyOf"][0]["properties"]
    assert item["preferredCanvasSize"]["enum"] == [24, 32, 48, 64, 96, 128]
    assert overlay["preferredCanvasSize"]["enum"] == [32, 48, 64, 96]
    for canvas in (item["preferredCanvasSize"], overlay["preferredCanvasSize"]):
        description = canvas["description"].lower()
        assert "square" in description and "canvas" in description and "pixels" in description
        assert "world size" in description or "display size" in description
    for name, label in (("inventoryScale", "inventory"), ("worldScale", "world")):
        field = item[name]
        assert field["minimum"] == 0.25 and field["maximum"] == 4.0
        description = field["description"].lower()
        assert label in description and "factor" in description and "1" in description
    assert "fit" in item["inventoryScale"]["description"].lower()
    assert "dropped" in item["worldScale"]["description"].lower()


@pytest.mark.parametrize("kind", ["director", "scoped_repair", "malformed_repair"])
def test_every_entity_asset_mode_explains_visual_factor_not_hitbox(sent_packet, kind):
    props = sent_packet(kind)["responseSchema"]["properties"]
    branches = (props["entities"] if kind == "director" else props["entitiesUpsert"])["items"]["oneOf"]
    assert {branch["properties"]["assetMode"]["const"] for branch in branches} == {
        "baked_sprite", "reuse_item_icon", "runtime_geometry", "no_asset"
    }
    descriptions = [branch["properties"]["scale"]["description"] for branch in branches]
    assert len(set(descriptions)) == 1
    assert all(branch["properties"]["scale"]["minimum"] == 0.25 and branch["properties"]["scale"]["maximum"] == 4.0 for branch in branches)
    description = descriptions[0].lower()
    assert "visual" in description and "factor" in description and "1" in description
    assert "hitbox" in description and "drawscale" in description
    assert "worldscale" in description


@pytest.mark.parametrize("kind", ["scoped_repair", "malformed_repair"])
def test_repair_delete_index_is_explicitly_zero_based(sent_packet, kind):
    schema = sent_packet(kind)["responseSchema"]["properties"]["entityIndicesDelete"]
    assert schema["items"]["type"] == "integer" and schema["items"]["minimum"] == 0
    description = (schema.get("description", "") + " " + schema["items"].get("description", "")).lower()
    assert "zero-based" in description and "index" in description
    assert "entities" in description
