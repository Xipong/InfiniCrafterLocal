"""Placement facts must survive the real parent-card and Author serialization path."""

import json

import pytest

from infini_local.pipelines.llm_authoring_prompt import build_llm_author_payload
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm


def _author_packet(item):
    payload = build_llm_author_payload(item, {"name": "Other"}, {}, {}, "placement_fact_probe")
    return json.loads(json.dumps(payload, ensure_ascii=False))["parents"]["A"]["packet"]


@pytest.mark.parametrize("style", [0, 7])
def test_raw_vanilla_placement_style_survives_to_serialized_author(style):
    item = {"name": "Workbench", "sourceMod": "Terraria", "createTile": 18,
            "createWall": -1, "placeStyle": style, "consumable": True}
    packet = _author_packet(item)
    assert packet["raw"]["item"]["createTile"] == 18
    assert packet["raw"]["item"]["placeStyle"] == style
    assert packet["raw"]["vanillaFlags"]["placeStyle"] == style


def test_missing_vanilla_placement_style_is_not_guessed():
    item = {"name": "Old dump", "createTile": 18, "createWall": -1,
            "consumable": True}
    packet = _author_packet(item)
    assert "placeStyle" not in packet["raw"]["item"]
    assert "placeStyle" not in packet["raw"].get("vanillaFlags", {})


def test_old_wire_fingerprint_style_remains_source_backed():
    packet = _author_packet({"name": "Older dump", "fingerprint": {
        "createTile": 18, "createWall": -1, "placeStyle": 7,
    }})
    assert packet["raw"]["item"]["placeStyle"] == 7


@pytest.mark.parametrize("style", [0, 7])
def test_generated_parent_uses_exact_canonical_place_binding_not_projected_item(style):
    placement = {"tileId": 18, "wallId": -1, "placeStyle": style}
    item = {
        "name": "Generated workbench", "sourceMod": "InfiniCrafterLocal",
        "createTile": -1, "createWall": -1, "placeStyle": 0,
        "generatedData": {"runtimeProgram": {"bindings": [
            {"input": "primary_use", "usePolicy": {"action": {
                "kind": "place_item", "placement": placement}, "stackCost": 1}},
        ]}},
    }
    packet = _author_packet(item)
    assert packet["raw"]["item"]["createTile"] == 18
    assert packet["raw"]["item"]["createWall"] == -1
    assert packet["raw"]["item"]["placeStyle"] == style
    assert packet["raw"]["generatedParent"]["runtimeProgram"]["bindings"][0]["usePolicy"]["action"]["placement"] == placement
    assert packet == raw_parent_card_for_llm(item)


def test_generated_missing_placement_does_not_inherit_projected_zero():
    item = {"name": "Generated nonplacer", "createTile": -1,
            "createWall": -1, "placeStyle": 0,
            "generatedData": {"runtimeProgram": {"bindings": [
                {"input": "primary_use", "usePolicy": {"action": {"kind": "use_item_body"}}},
            ]}}}
    packet = _author_packet(item)
    assert "placeStyle" not in packet["raw"]["item"]
    assert "placeStyle" not in packet["raw"].get("vanillaFlags", {})


def test_generated_placement_missing_style_does_not_inherit_projected_zero():
    item = {"name": "Partial authored placement", "createTile": -1, "placeStyle": 0,
            "generatedData": {"runtimeProgram": {"bindings": [
                {"input": "primary_use", "usePolicy": {"action": {
                    "kind": "place_item", "placement": {"tileId": 18, "wallId": -1}}}},
            ]}}}
    packet = _author_packet(item)
    assert packet["raw"]["item"]["createTile"] == 18
    assert "placeStyle" not in packet["raw"]["item"]
    assert "placeStyle" not in packet["raw"].get("vanillaFlags", {})


def test_two_distinct_generated_place_bindings_stay_separate_not_a_guessed_item_style():
    placements = [
        {"tileId": 18, "wallId": -1, "placeStyle": 0},
        {"tileId": 19, "wallId": -1, "placeStyle": 7},
    ]
    item = {"name": "Dual placer", "createTile": -1, "placeStyle": 0,
            "generatedData": {"runtimeProgram": {"bindings": [
                {"input": input_name, "usePolicy": {"action": {
                    "kind": "place_item", "placement": placement}}}
                for input_name, placement in zip(("primary_use", "alternate_use"), placements)
            ]}}}
    packet = _author_packet(item)
    assert "placeStyle" not in packet["raw"]["item"]
    assert "placeStyle" not in packet["raw"].get("vanillaFlags", {})
    bindings = packet["raw"]["generatedParent"]["runtimeProgram"]["bindings"]
    assert [row["usePolicy"]["action"]["placement"] for row in bindings] == placements
