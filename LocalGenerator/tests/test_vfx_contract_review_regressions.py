"""Independent-review counterexamples through canonical validation and Repair.

Offline hand-authored replies exercise real scope/filter/merge/compile functions;
these are required-behavior assertions, not defect-presence probes.
"""
from __future__ import annotations

# pyright: reportPrivateUsage=false

import copy
import json
from typing import Any

import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.core.errors import PlannerUnavailable
from tests.test_vfx_material_contract import _data, _sprite, _with_asset
from tests.test_vfx_material_repair import _patch


@pytest.mark.parametrize("parent,key", [
    ("slot", "element.widthPx"),
    ("slot", 'element["widthPx"]'),
    ("slot", ""),
    ("element", "widthProfile.middle"),
    ("element", 'quote"\\\n.widthPx'),
])
def test_literal_foreign_key_deletion_keeps_valid_nested_values_frozen(parent: str, key: str) -> None:
    data = _data()
    raw = _sprite(data)
    slot = raw["slots"][0]
    container = slot if parent == "slot" else slot["element"]
    container[key] = "foreign literal JSON member"
    before = copy.deepcopy(raw)
    candidate = _sprite(data)["slots"][0]
    candidate["element"]["widthPx"] = 64.0
    candidate["element"]["widthProfile"]["middle"] = 4.0
    prefix = "" if parent == "slot" else "element"
    relative = prefix + "[" + json.dumps(key) + "]"
    absolute = "$.slots[0]" + ("." if prefix else "") + relative
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert {row["path"] for row in report["errors"]} == {absolute}
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    assert scope["fieldPermissions"]["slots"] == [{
        "slotId": slot["id"], "paths": [relative], "deletePaths": [relative],
    }]
    patch = _patch(slotsUpsert=[candidate])
    repaired, audit = vfx._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    assert repaired == _sprite(data)
    assert audit["acceptedPaths"] == ["$.slotsUpsert[0]" + ("." if prefix else "") + relative]
    assert {row["path"] for row in audit["ignoredChanges"]} == {
        "$.slotsUpsert[0].element.widthPx", "$.slotsUpsert[0].element.widthProfile.middle",
    }
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]
    replies = iter([raw, patch])
    gameplay_before = copy.deepcopy(data["runtimeProgram"])
    final = vfx.attach_hybrid_vfx_manifest(data, "literal_foreign_key", llm_director=lambda *_a, **_kw: next(replies))
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert final["vfxManifest"]["slots"][0]["element"] == _sprite(data)["slots"][0]["element"]
    assert raw == before
    assert data["runtimeProgram"] == gameplay_before
    assert next(replies, None) is None


@pytest.mark.parametrize("invalid_minimum", [25.0, float("inf")])
def test_speed_relation_with_invalid_operand_keeps_valid_maximum_frozen(invalid_minimum: float) -> None:
    data = _data()
    raw = _sprite(data)
    raw["slots"][0]["element"]["speedMinPxPerTick"] = invalid_minimum
    before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert {row["path"] for row in report["errors"]} == {"$.slots[0].element.speedMinPxPerTick"}
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    assert scope["fieldPermissions"]["slots"] == [{
        "slotId": raw["slots"][0]["id"], "paths": ["element.speedMinPxPerTick"],
    }]
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["element"].update(speedMinPxPerTick=1.0, speedMaxPxPerTick=24.0)
    patch = _patch(slotsUpsert=[candidate])
    repaired, audit = vfx._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    assert repaired == _sprite(data)
    assert audit["acceptedPaths"] == ["$.slotsUpsert[0].element.speedMinPxPerTick"]
    assert [row["path"] for row in audit["ignoredChanges"]] == ["$.slotsUpsert[0].element.speedMaxPxPerTick"]
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]
    replies = iter([raw, patch])
    gameplay_before = copy.deepcopy(data["runtimeProgram"])
    final = vfx.attach_hybrid_vfx_manifest(data, "invalid_speed_operand", llm_director=lambda *_a, **_kw: next(replies))
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert final["vfxManifest"]["slots"][0]["element"]["speedMaxPxPerTick"] == 2.0
    assert raw == before
    assert data["runtimeProgram"] == gameplay_before
    assert next(replies, None) is None


@pytest.mark.parametrize("malformation", ["empty_id", "missing_id", "non_object"])
def test_sparse_noop_retains_malformed_slot_for_explicit_repair(malformation: str) -> None:
    data = _data()
    raw = _sprite(data)
    if malformation == "empty_id":
        raw["slots"][0]["id"] = ""
    elif malformation == "missing_id":
        raw["slots"][0].pop("id")
    else:
        raw["slots"][0] = None
    before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    assert scope["deletableSlotIndices"] == [0]
    repaired, audit = vfx._apply_vfx_repair_patch(data, raw, _patch(), scope, return_audit=True)
    assert audit["acceptedPaths"] == []
    assert repaired == before
    assert not vfx.validate_vfx_director_output(repaired, data)["ok"]
    replies = iter([raw, _patch()])
    with pytest.raises(PlannerUnavailable, match="VFX Repair did not produce"):
        vfx.attach_hybrid_vfx_manifest(data, "sparse_noop", llm_director=lambda *_a, **_kw: next(replies))
    assert "vfxManifest" not in data
    assert raw == before
    assert next(replies, None) is None


def test_unrelated_slot_upsert_does_not_implicitly_delete_idless_row() -> None:
    data = _data()
    raw = _sprite(data)
    raw["slots"][0]["id"] = ""
    sibling = copy.deepcopy(raw["slots"][0])
    sibling.update(id="sibling", alpha=2.0)
    raw["slots"].append(sibling)
    before = copy.deepcopy(raw)
    candidate = copy.deepcopy(sibling)
    candidate["alpha"] = 0.5
    scope = vfx._build_vfx_repair_scope(raw, vfx.validate_vfx_director_output(raw, data)["errors"])
    repaired, audit = vfx._apply_vfx_repair_patch(data, raw, _patch(slotsUpsert=[candidate]), scope, return_audit=True)
    assert repaired["slots"] == [before["slots"][0], candidate]
    assert audit["acceptedPaths"] == ["$.slotsUpsert[0].alpha"]
    assert not vfx.validate_vfx_director_output(repaired, data)["ok"]
    assert raw == before


def test_explicit_permitted_slot_index_delete_removes_only_malformed_row() -> None:
    data = _data()
    raw = _sprite(data)
    valid_slot = copy.deepcopy(raw["slots"][0])
    raw["slots"].insert(0, {**valid_slot, "id": ""})
    before = copy.deepcopy(raw)
    scope = vfx._build_vfx_repair_scope(raw, vfx.validate_vfx_director_output(raw, data)["errors"])
    patch = _patch(slotIndicesDelete=[0, 1])
    repaired, audit = vfx._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    assert repaired["slots"] == [valid_slot]
    assert audit["acceptedPaths"] == ["$.slotIndicesDelete[0]"]
    assert [row["path"] for row in audit["ignoredChanges"]] == ["$.slotIndicesDelete[1]"]
    replies = iter([raw, patch])
    final = vfx.attach_hybrid_vfx_manifest(data, "explicit_index_delete", llm_director=lambda *_a, **_kw: next(replies))
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert len(final["vfxManifest"]["slots"]) == 1
    assert final["vfxManifest"]["slots"][0]["element"] == valid_slot["element"]
    assert raw == before


@pytest.mark.parametrize("field", ["widthPx", "count", "speedMinPxPerTick"])
def test_large_json_integer_material_leaf_repair_keeps_valid_siblings_frozen(field: str) -> None:
    data = _data()
    raw = _sprite(data)
    valid = copy.deepcopy(raw["slots"][0])
    broken = copy.deepcopy(valid)
    broken["id"] = "later_material"
    broken["element"][field] = json.loads("1" + "0" * 400)
    raw["slots"].append(broken)
    before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert {row["path"] for row in report["errors"]} == {f"$.slots[1].element.{field}"}
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    assert scope["fieldPermissions"]["slots"] == [{
        "slotId": broken["id"], "paths": [f"element.{field}"],
    }]
    candidate = copy.deepcopy(broken)
    candidate["element"][field] = valid["element"][field]
    candidate["element"]["heightPx"] = 44.0
    patch = _patch(slotsUpsert=[candidate])
    repaired, audit = vfx._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    expected = copy.deepcopy(before)
    expected["slots"][1]["element"][field] = valid["element"][field]
    assert repaired == expected
    assert audit["acceptedPaths"] == [f"$.slotsUpsert[0].element.{field}"]
    assert [row["path"] for row in audit["ignoredChanges"]] == ["$.slotsUpsert[0].element.heightPx"]
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]
    gameplay_before = copy.deepcopy(data["runtimeProgram"])
    replies = iter([raw, patch])
    final = vfx.attach_hybrid_vfx_manifest(data, "large_integer_material", llm_director=lambda *_a, **_kw: next(replies))
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert [row["element"] for row in final["vfxManifest"]["slots"]] == [row["element"] for row in expected["slots"]]
    assert data["runtimeProgram"] == gameplay_before
    assert raw == before
    assert next(replies, None) is None


@pytest.mark.parametrize("location", ["element_width", "element_count", "asset_score"])
def test_large_json_integer_wire_rejection_keeps_original_later_index(location: str) -> None:
    data = _data()
    raw = _with_asset(data)
    later = copy.deepcopy(raw["slots"][0])
    later["id"] = "later_material"
    raw["slots"].append(later)
    final = vfx.attach_hybrid_vfx_manifest(data, "large_integer_wire", llm_director=lambda *_a, **_kw: raw)
    manifest = final["vfxManifest"]
    huge = json.loads("1" + "0" * 400)
    if location == "asset_score":
        asset = copy.deepcopy(manifest["assets"][0])
        asset.update(id="Later_A-2", spriteTechnicalScore=huge)
        manifest["assets"].append(asset)
        path = "$.vfxManifest.assets[1].spriteTechnicalScore"
    else:
        field = "widthPx" if location == "element_width" else "count"
        manifest["slots"][1]["element"][field] = huge
        path = f"$.vfxManifest.slots[1].element.{field}"
    before = copy.deepcopy(final)
    report = vfx.validate_vfx_manifest_wire(final)
    assert not report["ok"]
    assert {row["path"] for row in report["errors"]} == {path}
    assert final == before


@pytest.mark.parametrize("field", ["effectMagnitude", "alpha", "duration"])
def test_large_json_integer_common_numeric_repair_keeps_exact_scope(field: str) -> None:
    data = _data()
    raw = _sprite(data)
    valid = copy.deepcopy(raw["slots"][0])
    huge = json.loads(("-1" if field == "effectMagnitude" else "1") + "0" * 400)
    candidate = copy.deepcopy(valid)
    candidate["element"]["heightPx"] = 44.0
    if field == "effectMagnitude":
        raw[field] = huge
        path = f"$.{field}"
        patch = _patch(effectMagnitude=0.5, slotsUpsert=[candidate])
        accepted_path = path
        ignored_path = "$.slotsUpsert[0]"
    else:
        candidate["id"] = "later_material"
        broken = copy.deepcopy(valid)
        broken.update(id=candidate["id"], **{field: huge})
        raw["slots"].append(broken)
        path = f"$.slots[1].{field}"
        patch = _patch(slotsUpsert=[candidate])
        accepted_path = f"$.slotsUpsert[0].{field}"
        ignored_path = "$.slotsUpsert[0].element.heightPx"
    before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert {row["path"] for row in report["errors"]} == {path}
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    if field == "effectMagnitude":
        assert scope["fieldPermissions"]["globals"] == {field: [""]}
        assert scope["fieldPermissions"]["slots"] == []
    else:
        assert scope["fieldPermissions"]["globals"] == {}
        assert scope["fieldPermissions"]["slots"] == [{"slotId": candidate["id"], "paths": [field]}]
    expected = copy.deepcopy(before)
    if field == "effectMagnitude":
        expected[field] = 0.5
    else:
        expected["slots"][1][field] = valid[field]
    repaired, audit = vfx._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    assert repaired == expected
    assert audit["acceptedPaths"] == [accepted_path]
    assert [row["path"] for row in audit["ignoredChanges"]] == [ignored_path]
    gameplay_before = copy.deepcopy(data["runtimeProgram"])
    replies = iter([raw, patch])
    final = vfx.attach_hybrid_vfx_manifest(data, "large_integer_common", llm_director=lambda *_a, **_kw: next(replies))
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert data["runtimeProgram"] == gameplay_before
    assert raw == before
    assert next(replies, None) is None
