"""Adversarial final-wire checks derived from the strict-boundary audit."""
from __future__ import annotations

import copy

import pytest

from infini_local.core.runtime_authoring import validate_runtime_wire
from infini_local.web.vfx_debug_routes import _sample_data


@pytest.fixture
def wire():
    data = _sample_data()
    assert validate_runtime_wire(data)["ok"] is True
    return data


@pytest.mark.parametrize("row", [None, False, 0, "broken", [], ["broken"]])
def test_wire_rejects_non_object_entity_at_original_index(wire, row):
    wire["runtimeProgram"]["entities"].insert(0, row)
    original = copy.deepcopy(wire)

    report = validate_runtime_wire(wire)

    assert report["ok"] is False
    assert any(error["path"] == "$.runtimeProgram.entities[0]" and error["code"] == "required_object"
               for error in report["errors"])
    assert wire == original


def test_entity_error_paths_do_not_shift_after_invalid_rows(wire):
    wire["runtimeProgram"]["entities"].insert(0, None)
    wire["runtimeProgram"]["entities"][2]["movement"]["code"] = -1

    report = validate_runtime_wire(wire)

    assert any(error["path"] == "$.runtimeProgram.entities[2].movement.code"
               and error["code"] == "unsupported_opcode" for error in report["errors"])


def test_wire_rejects_multiple_item_bodies_like_csharp(wire):
    extra_body = copy.deepcopy(wire["runtimeProgram"]["entities"][0])
    extra_body["id"] = "extra_item"
    wire["runtimeProgram"]["entities"].append(extra_body)

    report = validate_runtime_wire(wire)

    assert report["ok"] is False
    assert any(error["path"] == "$.runtimeProgram.entities" and error["code"] == "item_body_count"
               for error in report["errors"])


@pytest.mark.parametrize("binding_id", [None, "", "   ", 7, []])
def test_wire_rejects_invalid_binding_id(wire, binding_id):
    wire["runtimeProgram"]["bindings"][0]["id"] = binding_id

    report = validate_runtime_wire(wire)

    assert report["ok"] is False
    assert any(error["path"] == "$.runtimeProgram.bindings[0].id" and error["code"] == "required_id"
               for error in report["errors"])


def test_wire_rejects_duplicate_ids_across_distinct_binding_inputs(wire):
    duplicate = copy.deepcopy(wire["runtimeProgram"]["bindings"][0])
    duplicate["input"] = "alternate_use"
    wire["runtimeProgram"]["bindings"].append(duplicate)

    report = validate_runtime_wire(wire)

    assert report["ok"] is False
    assert any(error["path"] == "$.runtimeProgram.bindings[1].id" and error["code"] == "duplicate_id"
               for error in report["errors"])


@pytest.mark.parametrize("code", [[], {}, [1]])
def test_invalid_controller_opcode_is_reported_without_crashing(wire, code):
    wire["runtimeProgram"]["entities"][1]["controller"]["code"] = code
    original = copy.deepcopy(wire)

    report = validate_runtime_wire(wire)

    assert report["ok"] is False
    assert any(error["path"] == "$.runtimeProgram.entities[1].controller.code"
               and error["code"] == "unsupported_opcode" for error in report["errors"])
    assert wire == original


@pytest.mark.parametrize("field", ["healLife", "healMana", "durationTicks"])
@pytest.mark.parametrize("value", [None, False, True, 1.5, "3", "broken", {}, []])
def test_wire_reports_invalid_effect_integer_without_coercion(wire, field, value):
    gameplay = wire.setdefault("gameplay", {})
    if field == "healMana":
        gameplay["healLife"] = 20  # A valid first effect must not hide invalid mana.
    target = gameplay.setdefault("generatedBuff", {}) if field == "durationTicks" else gameplay
    target[field] = value
    original = copy.deepcopy(wire)
    prefix = "$.gameplay.generatedBuff" if field == "durationTicks" else "$.gameplay"

    report = validate_runtime_wire(wire)

    assert report["ok"] is False
    assert any(error["path"] == f"{prefix}.{field}" and error["code"] == "invalid_integer"
               for error in report["errors"])
    assert wire == original


@pytest.mark.parametrize("mutation", ["entity_row", "extra_body", "binding_id", "controller_code", "heal_value", "buff_duration"])
def test_rejected_wire_is_quarantined_by_real_cache_lookup(tmp_path, monkeypatch, wire, mutation):
    from infini_local.core.vfx_manifest import VFX_MANIFEST_SCHEMA
    from infini_local.pipelines.combine_pipeline import combine_cache_lookup
    from infini_local.storage import world_recipe_runtime, world_storage

    monkeypatch.setattr(world_recipe_runtime, "WORLD_RECIPES_DIR", tmp_path)
    payload = {"worldId": "audit-world", "itemA": {"type": 1}, "itemB": {"type": 2}}
    key, cached = combine_cache_lookup(payload)
    assert cached is None
    wire["vfxManifest"] = {"schema": VFX_MANIFEST_SCHEMA, "slots": []}
    runtime = wire["runtimeProgram"]
    if mutation == "entity_row":
        runtime["entities"].insert(0, None)
    elif mutation == "extra_body":
        extra = copy.deepcopy(runtime["entities"][0])
        extra["id"] = "extra_item"
        runtime["entities"].append(extra)
    elif mutation == "binding_id":
        runtime["bindings"][0]["id"] = ""
    elif mutation == "heal_value":
        wire.setdefault("gameplay", {})["healLife"] = "broken"
    elif mutation == "buff_duration":
        wire.setdefault("gameplay", {})["generatedBuff"] = {"durationTicks": "broken"}
    else:
        runtime["entities"][1]["controller"]["code"] = []
    path = world_storage.world_recipe_file(tmp_path, "audit-world", key)
    world_storage.atomic_write_json(path, wire)
    original = path.read_bytes()

    assert combine_cache_lookup(payload) == (key, None)
    assert not path.exists()
    reasons = list((path.parent.parent / "invalid").glob("*.reason.json"))
    assert len(reasons) == 1
    reason = world_storage.read_json_file(reasons[0])
    assert isinstance(reason, dict)
    assert reason["reason"] == "low_level_runtime_contract_invalid"
    assert (reasons[0].parent / reason["payloadFile"]).read_bytes() == original
