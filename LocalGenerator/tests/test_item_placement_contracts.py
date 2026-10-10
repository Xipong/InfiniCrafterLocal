"""Canonical placement provenance and durable-hybrid stack/Repair contracts."""
from __future__ import annotations

import copy
import json

import pytest

from infini_local.core.runtime_authoring import (
    apply_repair_patch, build_runtime_repair_scope, compile_runtime_program,
    filter_repair_patch_scope, validate_runtime_program, validate_runtime_wire,
)
from infini_local.pipelines.llm_authoring_prompt import build_llm_author_payload
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
from test_dual_use_placeable_contract import _dual_use_placeable


PLACEMENT_FACT_CASES = [
    *[pytest.param(
        {"name": "Workbench", "sourceMod": "Terraria", "createTile": 18,
         "createWall": -1, "placeStyle": style, "consumable": True},
        {"createTile": 18, "placeStyle": style}, {"placeStyle": style}, (),
        id=f"vanilla-style-{style}",
    ) for style in (0, 7)],
    pytest.param({"name": "Old dump", "createTile": 18, "createWall": -1, "consumable": True},
                 {}, {}, ("placeStyle",), id="vanilla-style-missing"),
    pytest.param({"name": "Older dump", "fingerprint": {"createTile": 18, "createWall": -1, "placeStyle": 7}},
                 {"placeStyle": 7}, {}, (), id="fingerprint-style"),
    *[pytest.param(
        {"name": "Generated workbench", "sourceMod": "InfiniCrafterLocal",
         "createTile": -1, "createWall": -1, "placeStyle": 0,
         "generatedData": {"runtimeProgram": {"bindings": [
             {"input": "primary_use", "usePolicy": {"action": {
                 "kind": "place_item", "placement": {"tileId": 18, "wallId": -1, "placeStyle": style}}, "stackCost": 1}},
         ]}}},
        {"createTile": 18, "createWall": -1, "placeStyle": style}, {}, (),
        id=f"generated-canonical-style-{style}",
    ) for style in (0, 7)],
    pytest.param(
        {"name": "Generated nonplacer", "createTile": -1, "createWall": -1, "placeStyle": 0,
         "generatedData": {"runtimeProgram": {"bindings": [
             {"input": "primary_use", "usePolicy": {"action": {"kind": "use_item_body"}}},
         ]}}}, {}, {}, ("placeStyle",), id="generated-nonplacer"),
    pytest.param(
        {"name": "Partial authored placement", "createTile": -1, "placeStyle": 0,
         "generatedData": {"runtimeProgram": {"bindings": [
             {"input": "primary_use", "usePolicy": {"action": {
                 "kind": "place_item", "placement": {"tileId": 18, "wallId": -1}}}},
         ]}}}, {"createTile": 18}, {}, ("placeStyle",), id="generated-style-missing"),
    pytest.param(
        {"name": "Dual placer", "createTile": -1, "placeStyle": 0,
         "generatedData": {"runtimeProgram": {"bindings": [
             {"input": input_name, "usePolicy": {"action": {"kind": "place_item", "placement": placement}}}
             for input_name, placement in zip(("primary_use", "alternate_use"), [
                 {"tileId": 18, "wallId": -1, "placeStyle": 0},
                 {"tileId": 19, "wallId": -1, "placeStyle": 7},
             ])
         ]}}}, {}, {}, ("placeStyle",), id="distinct-placement-bindings"),
]


@pytest.mark.parametrize("item,expected_item,expected_flags,absent", PLACEMENT_FACT_CASES)
def test_placement_facts_survive_serialized_author(item, expected_item, expected_flags, absent):
    source = copy.deepcopy(item)
    payload = build_llm_author_payload(item, {"name": "Other"}, {}, {}, "placement_fact_probe")
    packet = json.loads(json.dumps(payload, ensure_ascii=False))["parents"]["A"]["packet"]
    raw = packet["raw"]
    for field, value in expected_item.items():
        assert field in raw["item"] and raw["item"][field] == value, f"item.{field} provenance"
    for field, value in expected_flags.items():
        assert raw.get("vanillaFlags", {}).get(field) == value, f"vanillaFlags.{field} provenance"
    for field in absent:
        assert field not in raw["item"], f"invented item.{field}"
        assert field not in raw.get("vanillaFlags", {}), f"invented vanillaFlags.{field}"
    if "generatedData" in item:
        assert raw["generatedParent"]["runtimeProgram"]["bindings"] == item["generatedData"]["runtimeProgram"]["bindings"]
        assert packet == raw_parent_card_for_llm(item)
    assert item == source


@pytest.mark.parametrize("max_stack,invalid", [(1, False), (9999, True)], ids=["single-unit", "stacked-durable"])
@pytest.mark.parametrize("tile_id", [18, 19], ids=["historical-workbench", "dual-use-platform"])
def test_durable_hybrid_stack_contract(max_stack, invalid, tile_id):
    document = _dual_use_placeable()
    next(c for c in document["runtimeProgram"]["calls"] if c["fn"] == "configure_tile_placement")["params"]["tileId"] = tile_id
    next(c for c in document["runtimeProgram"]["calls"] if c["fn"] == "configure_item_stats")["params"]["maxStack"] = max_stack
    report = validate_runtime_program(document)
    assert ("hybrid_placeable_max_stack" in {row["code"] for row in report["errors"]}) is invalid
    if not invalid:
        assert report["ok"], report["errors"]
        assert validate_runtime_wire(compile_runtime_program(document))["ok"]


def test_hybrid_stack_repair_changes_only_authorized_leaf():
    document = _dual_use_placeable()
    stats = next(c for c in document["runtimeProgram"]["calls"] if c["fn"] == "configure_item_stats")
    stats["params"]["maxStack"] = 9999
    errors = [r for r in validate_runtime_program(document)["errors"] if r["code"] == "hybrid_placeable_max_stack"]
    assert errors
    scope = build_runtime_repair_scope(document, errors)
    assert scope["nonRepairableErrors"] == []
    permission = next(row for row in scope["fieldPermissions"]["calls"] if row["id"] == stats["id"])
    assert permission["paths"] == ["params.maxStack"]
    candidate = copy.deepcopy(stats)
    candidate["params"].update(maxStack=1, damage=9876)
    filtered, audit = filter_repair_patch_scope(document, {"note": "cap durable hybrid to one unit", "callsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(document, filtered)
    expected = copy.deepcopy(document)
    next(c for c in expected["runtimeProgram"]["calls"] if c["id"] == stats["id"])["params"]["maxStack"] = 1
    assert repaired == expected
    assert validate_runtime_program(repaired)["ok"]
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
