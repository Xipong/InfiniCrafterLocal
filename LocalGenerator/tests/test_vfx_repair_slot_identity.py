"""Repair malformed VFX slot containers/identities without touching valid cues."""
from __future__ import annotations

import copy

import pytest

from infini_local.core.vfx.contract import VFX_REPAIR_PATCH_SCHEMA
from infini_local.core.schema_validation import strict_schema_errors
from infini_local.core.vfx.materials import vfx_model_payload
from infini_local.core.vfx.repair import _apply_vfx_repair_patch, _build_vfx_repair_scope
from infini_local.core.vfx.validation import validate_vfx_director_output, validate_vfx_manifest_wire
from infini_local.pipelines.vfx.stage import attach_vfx_manifest
from tests.vfx_material_fixtures import _asset, _data, _native, _with_asset


def _repair(data, previous, **changes):
    report = validate_vfx_director_output(previous, data)
    assert not report["ok"]
    scope = _build_vfx_repair_scope(previous, report["errors"])
    patch = {"schema": VFX_REPAIR_PATCH_SCHEMA, "note": "Correct only the diagnosed slots", **changes}
    return _apply_vfx_repair_patch(data, previous, patch, scope, return_audit=True)


def test_duplicate_slot_can_be_deleted_by_occurrence_without_changing_first_cue():
    data = _data()
    raw = _native(data)
    raw["slots"].append({**copy.deepcopy(raw["slots"][0]), "color": {"r": 220, "g": 30, "b": 10}})
    before = copy.deepcopy(raw)
    repaired, audit = _repair(data, raw, slotIndicesDelete=[1], slotIdsDelete=["native_cue"])
    assert repaired["slots"] == before["slots"][:1]
    assert validate_vfx_director_output(repaired, data)["ok"]
    assert audit["filteredPatch"]["slotIdsDelete"] == []
    assert raw == before


def test_duplicate_slot_diagnostics_do_not_grant_edits_to_first_valid_cue():
    data = _data()
    raw = _native(data)
    duplicate = copy.deepcopy(raw["slots"][0])
    duplicate["dust"]["count"] = -1
    raw["slots"].append(duplicate)
    attempted = copy.deepcopy(raw["slots"][0])
    attempted["dust"]["count"] = 30
    repaired, audit = _repair(data, raw, slotIndicesDelete=[1], slotsUpsert=[attempted])
    assert repaired["slots"] == raw["slots"][:1]
    assert validate_vfx_director_output(repaired, data)["ok"]
    assert audit["filteredPatch"]["slotsUpsert"] == []


def test_first_slot_leaf_repair_uses_first_occurrence_when_later_duplicate_is_deleted():
    data = _data()
    raw = _native(data)
    first = copy.deepcopy(raw["slots"][0])
    duplicate = copy.deepcopy(first)
    duplicate["color"] = {"r": 220, "g": 30, "b": 10}
    raw["slots"][0]["dust"]["count"] = -1
    raw["slots"].append(duplicate)
    repaired, _ = _repair(data, raw, slotIndicesDelete=[1], slotsUpsert=[first])
    assert repaired["slots"] == [first]
    assert validate_vfx_director_output(repaired, data)["ok"]


@pytest.mark.parametrize("value", [None, "mistyped slot list", {}])
def test_explicit_empty_slot_upsert_repairs_invalid_container(value):
    data = _data()
    raw = _native(data)
    raw["slots"] = value
    repaired, audit = _repair(data, raw, slotsUpsert=[])
    assert repaired["slots"] == []
    assert "$.slots" in audit["acceptedPaths"]
    assert validate_vfx_director_output(repaired, data)["ok"]


def test_explicit_empty_slot_upsert_repairs_missing_container_but_omission_does_not():
    data = _data()
    raw = _native(data)
    del raw["slots"]
    omitted, audit = _repair(data, raw)
    assert "slots" not in omitted
    assert "$.slots" not in audit["acceptedPaths"]
    repaired, audit = _repair(data, raw, slotsUpsert=[])
    assert repaired["slots"] == []
    assert "$.slots" in audit["acceptedPaths"]
    assert validate_vfx_director_output(repaired, data)["ok"]


def test_empty_upsert_cannot_remove_valid_slots_during_an_unrelated_leaf_repair():
    data = _data()
    raw = _native(data)
    raw["slots"][0]["dust"]["count"] = -1
    repaired, audit = _repair(data, raw, slotsUpsert=[])
    assert repaired == raw
    assert "$.slots" not in audit["acceptedPaths"]


@pytest.mark.parametrize("fault", ["duplicate", "duplicate_and_first_leaf", "empty_container"])
def test_real_vfx_stage_repair_request_can_express_correction_and_deliver_valid_wire(fault):
    data = _data()
    expected = _native(data)
    raw = copy.deepcopy(expected)
    patch = {"schema": VFX_REPAIR_PATCH_SCHEMA, "note": "Use the exact permitted correction"}
    if fault == "empty_container":
        raw["slots"] = None
        expected["slots"] = []
        patch["slotsUpsert"] = []
    else:
        duplicate = copy.deepcopy(raw["slots"][0])
        duplicate["color"] = {"r": 220, "g": 30, "b": 10}
        raw["slots"].append(duplicate)
        patch["slotIndicesDelete"] = [1]
        if fault == "duplicate_and_first_leaf":
            raw["slots"][0]["dust"]["count"] = -1
            patch["slotsUpsert"] = copy.deepcopy(expected["slots"])
    requests = []

    def director(_system, packet, *_args, **_kwargs):
        requests.append(packet)
        if len(requests) == 1:
            return raw
        assert not strict_schema_errors(vfx_model_payload(patch), packet["outputSchema"])
        return patch

    result = attach_vfx_manifest(data, "slot-repair-regression", llm_director=director)
    assert len(requests) == 2
    assert result["debug"]["vfxDirectorRaw"] == expected
    assert validate_vfx_manifest_wire(result)["ok"]
    assert result["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 1


@pytest.mark.parametrize("asset_use", ["duplicate_only", "first_and_duplicate", "sibling_and_duplicate"])
def test_duplicate_slot_asset_deletion_preserves_every_surviving_consumer(asset_use):
    data = _data()
    raw = _with_asset(data)
    first_asset_id = raw["assets"][0]["id"]
    duplicate = copy.deepcopy(raw["slots"][0])
    if asset_use == "first_and_duplicate":
        duplicate_asset_id = first_asset_id
    else:
        duplicate_asset_id = "DuplicateTexture"
        raw["assets"].append(_asset(duplicate_asset_id))
        duplicate["element"]["texture"]["assetId"] = duplicate_asset_id
    raw["slots"].append(duplicate)
    if asset_use == "sibling_and_duplicate":
        sibling = copy.deepcopy(duplicate)
        sibling["id"] = "independent_sibling"
        raw["slots"].append(sibling)
    before = copy.deepcopy(raw)
    repaired, audit = _repair(data, raw, slotIndicesDelete=[1], assetIdsDelete=list({first_asset_id, duplicate_asset_id}))
    assert repaired["slots"] == [row for index, row in enumerate(before["slots"]) if index != 1]
    expected_assets = before["assets"][:1] if asset_use == "duplicate_only" else before["assets"]
    assert repaired["assets"] == expected_assets
    assert audit["filteredPatch"]["assetIdsDelete"] == ([duplicate_asset_id] if asset_use == "duplicate_only" else [])
    assert validate_vfx_director_output(repaired, data)["ok"]
    assert raw == before


def test_real_vfx_repair_can_delete_duplicate_and_its_exclusive_asset_in_one_request():
    data = _data()
    expected = _with_asset(data)
    sibling = copy.deepcopy(expected["slots"][0])
    sibling["id"] = "independent_sibling"
    sibling["element"]["texture"]["assetId"] = "SiblingTexture"
    expected["slots"].append(sibling)
    expected["assets"].append(_asset("SiblingTexture"))
    raw = copy.deepcopy(expected)
    duplicate = copy.deepcopy(raw["slots"][0])
    duplicate["element"]["texture"]["assetId"] = "DuplicateTexture"
    raw["slots"].insert(1, duplicate)
    raw["assets"].append(_asset("DuplicateTexture"))
    patch = {"schema": VFX_REPAIR_PATCH_SCHEMA, "note": "Delete only the duplicate and its exclusively used texture",
             "slotIndicesDelete": [1], "assetIdsDelete": ["DuplicateTexture"]}
    requests = []

    def director(_system, packet, *_args, **_kwargs):
        requests.append(packet)
        if len(requests) == 1:
            return raw
        assert not strict_schema_errors(vfx_model_payload(patch), packet["outputSchema"])
        assert packet["repairScope"]["deletableAssetIds"] == ["DuplicateTexture"]
        assert not packet["repairScope"]["mutableAssetIds"]
        assert not packet["repairScope"]["allowCreateAssets"]
        assert "assetsUpsert" not in packet["outputSchema"]["properties"]
        assert packet["brokenFragments"]["assets"] == [_asset("DuplicateTexture")]
        assert packet["validGeneratedContext"]["assets"] == expected["assets"]
        return patch

    result = attach_vfx_manifest(data, "duplicate-dependent-asset", llm_director=director)
    assert len(requests) == 2
    assert result["debug"]["vfxDirectorRaw"] == expected
    assert validate_vfx_manifest_wire(result)["ok"]
    assert result["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 1
