"""Numeric units, neutral common fields and bounded wire admission for new branches."""
from __future__ import annotations

# Contract observers intentionally exercise the private request/scope/merge seams.
# pyright: reportPrivateUsage=false

import copy

import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.core.runtime_authoring import strict_schema_errors
from tests.test_vfx_material_contract import _data, _path, _sent, _sprite, _with_asset
from tests.test_vfx_material_repair import _patch


@pytest.mark.parametrize("renderer", ["spriteElement", "texturedPath"])
def test_new_branch_channels_lanes_and_common_neutrals_match_sent_schema(renderer: str) -> None:
    data = _data()
    raw = _sprite(data) if renderer == "spriteElement" else _path(data)
    slot = raw["slots"][0]
    surface = vfx.vfx_director_surface(data)
    schema = _sent(data, False)["outputSchema"]["properties"]["slots"]["items"]
    for channel in surface["channel"]:
        for lane in surface["lane"]:
            slot.update(channel=channel, lane=lane)
            expected = channel not in {"light", "sound"}
            assert (not strict_schema_errors(slot, schema)) is expected
            assert vfx.validate_vfx_director_output(raw, data)["ok"] is expected
    slot.update(channel="coreGlow", lane="accent")
    for field, neutral in surface["rendererRequirements"][renderer].items():
        broken = copy.deepcopy(slot)
        broken[field] = "Auto" if field == "backend" else ("item" if isinstance(neutral, str) else neutral + 1)
        errors = strict_schema_errors(broken, schema)
        assert "$." + field in {row["path"] for row in errors}, (field, errors)


@pytest.mark.parametrize("repair", [False, True])
def test_sent_new_payload_numeric_descriptions_do_not_repeat_legacy_consumption(repair: bool) -> None:
    data = _data()
    packet = _sent(data, repair)
    props = packet["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]["properties"]
    for field in ("duration", "startTick", "repeatEvery", "alpha", "backend", "textureRole"):
        assert "spriteElement" in props[field]["description"], field
        assert "texturedPath" in props[field]["description"], field
    if repair:
        assert any("deletePaths" in rule and "omissions" in rule for rule in packet["rules"])
    else:
        assert all(rule.startswith("Legacy ") for rule in packet["rules"] if "Procedural phase" in rule or "Sprite renderers require" in rule)
        assert any("spriteElement and texturedPath" in rule and "nested texture" in rule for rule in packet["rules"])
    for payload in ("element", "path"):
        for field, schema in props[payload]["properties"].items():
            if schema.get("type") in ("integer", "number"):
                assert schema.get("description"), (payload, field)
            if field.endswith("Profile"):
                assert "profile coordinate" in schema["description"]
                for knot in ("start", "middle", "end"):
                    assert schema["properties"][knot].get("description")


@pytest.mark.parametrize("repair", [False, True])
def test_inherited_velocity_units_are_explicit_in_actual_sent_payload(repair: bool) -> None:
    packet = _sent(_data(), repair)
    slots = packet["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]
    description = slots["items"]["properties"]["element"]["properties"]["inheritVelocity"]["description"]
    assert "world tick" in description
    assert "extraUpdates" in description
    assert "Player.velocity" in description
    assert "not measured anchor displacement" in description


@pytest.mark.parametrize("field", ["duration", "startTick", "repeatEvery"])
def test_nonfinite_common_integer_diagnosis_is_indexed_not_a_validator_crash(field: str) -> None:
    data = _data()
    raw = _sprite(data)
    raw["slots"][0][field] = float("nan")
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert f"$.slots[0].{field}" in {r["path"] for r in report["errors"]}


def test_wire_slot_ceiling_is_not_bypassed_by_canonical_shape_gate() -> None:
    data = _data()
    raw = _sprite(data)
    vfx.attach_hybrid_vfx_manifest(data, "bounded_wire", llm_director=lambda *_a, **_kw: raw)
    slot = data["vfxManifest"]["slots"][0]
    data["vfxManifest"]["slots"] = [{**copy.deepcopy(slot), "id": f"row_{index}"} for index in range(13)]
    report = vfx.validate_vfx_manifest_wire(data)
    assert not report["ok"]
    assert "$.vfxManifest.slots" in {r["path"] for r in report["errors"]}


def test_optional_malformed_asset_container_requires_explicit_empty_repair_not_omission() -> None:
    data = _data()
    raw = _sprite(data)
    raw["assets"] = None
    scope = vfx._build_vfx_repair_scope(raw, vfx.validate_vfx_director_output(raw, data)["errors"])
    untouched = vfx._apply_vfx_repair_patch(data, raw, _patch(), scope)
    assert untouched["assets"] is None
    repaired = vfx._apply_vfx_repair_patch(data, raw, _patch(assetsUpsert=[]), scope)
    assert repaired["assets"] == []
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]


def test_exact_missing_named_knot_permission_adds_only_that_leaf() -> None:
    data = _data()
    raw = _with_asset(data)
    raw["slots"][0]["element"]["heightProfile"].pop("middle")
    report = vfx.validate_vfx_director_output(raw, data)
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    assert scope["fieldPermissions"]["slots"] == [{"slotId": "ingredient_element", "paths": ["element.heightProfile.middle"]}]
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["element"]["heightProfile"].update(start=4.0, middle=0.5)
    repaired = vfx._apply_vfx_repair_patch(data, raw, _patch(slotsUpsert=[candidate]), scope)
    assert repaired["slots"][0]["element"]["heightProfile"] == {"start": 2.0, "middle": 0.5, "end": 0.0, "curve": "easeOut"}
    assert repaired["assets"] == raw["assets"]
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]
