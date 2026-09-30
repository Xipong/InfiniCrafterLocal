"""Exact frozen-first additive VFX repair through the actual bounded stage."""
from __future__ import annotations

# Contract observers intentionally exercise the private request/scope/merge seams.
# pyright: reportPrivateUsage=false

import copy
import json
from typing import Any

import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.core.runtime_authoring import strict_schema_errors
from tests.test_vfx_material_contract import _asset, _data, _legacy, _sent, _sprite, _with_asset


def _patch(**edits: Any) -> dict[str, Any]:
    return {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "repair exact diagnosed leaves only", **edits}


def test_sparse_profile_repair_keeps_frozen_knots_absences_and_typed_correction() -> None:
    data = _data()
    raw = _sprite(data)
    raw["slots"][0]["element"]["widthProfile"]["middle"] = True
    before = copy.deepcopy(raw)
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["element"]["widthProfile"].update(start=4.0, middle=1.0, end=4.0)
    candidate["element"]["texture"] = {"source": "entity", "assetId": ""}
    replies = iter([raw, _patch(slotsUpsert=[candidate], assetsUpsert=[_asset()])])
    packets: list[dict[str, Any]] = []

    def respond(_system: str, user: dict[str, Any], *_args: Any, **kwargs: Any) -> Any:
        if kwargs.get("messages"):
            packets.append(json.loads(kwargs["messages"][1]["content"]))
        return next(replies)

    result = vfx.attach_hybrid_vfx_manifest(data, "profile_leaf", llm_director=respond)
    assert packets[0]["repairScope"]["fieldPermissions"]["slots"] == [{"slotId": "ingredient_element", "paths": ["element.widthProfile.middle"]}]
    expected = copy.deepcopy(before["slots"][0]["element"])
    expected["widthProfile"]["middle"] = 1.0
    assert result["vfxManifest"]["slots"][0]["element"] == expected
    assert type(result["vfxManifest"]["slots"][0]["element"]["widthProfile"]["middle"]) is float
    assert "assets" not in result["vfxManifest"]
    assert raw == before
    assert next(replies, None) is None


def test_asset_leaf_repair_transports_exact_scope_and_freezes_prompt_layout_references() -> None:
    data = _data()
    raw = _with_asset(data)
    raw["assets"][0]["canvasSize"] = True
    before = copy.deepcopy(raw)
    candidate = {**_asset(), "prompt": "unrequested redesign", "negativePrompt": "rewrite", "layout": "strip"}
    report = vfx.validate_vfx_director_output(raw, data)
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    assert scope["fieldPermissions"]["assets"] == [{"assetId": "Glow_A-1", "paths": ["canvasSize"]}]
    repaired, audit = vfx._apply_vfx_repair_patch(data, raw, _patch(assetsUpsert=[candidate]), scope, return_audit=True)
    expected = copy.deepcopy(before)
    expected["assets"][0]["canvasSize"] = 32
    assert repaired == expected
    assert audit["ok"]
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]
    assert any(row["path"].endswith(".prompt") for row in audit["ignoredChanges"])
    packet = vfx._prompt_packet(data, None, None)
    sent: list[dict[str, Any]] = []
    def capture(_system: str, user: dict[str, Any], *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        sent.append(user)
        return {}

    vfx._request(capture, packet, repair_errors=report["errors"], previous=raw, repair_scope=scope)
    assert sent[0]["brokenFragments"]["assets"] == before["assets"]
    assert sent[0]["outputSchema"]["properties"]["assetsUpsert"]["items"] == packet["outputSchema"]["properties"]["assets"]["items"]
    assert raw == before


def test_dangling_reference_repair_cannot_create_compensating_asset() -> None:
    data = _data()
    raw = _with_asset(data)
    raw["slots"][0]["element"]["texture"]["assetId"] = "missing"
    before = copy.deepcopy(raw)
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["element"]["texture"] = {"source": "item", "assetId": "Glow_A-1"}  # Invalid until frozen source wins.
    scope = vfx._build_vfx_repair_scope(raw, vfx.validate_vfx_director_output(raw, data)["errors"])
    assert not scope.get("allowCreateAssets")
    patch = _patch(slotsUpsert=[candidate], assetsUpsert=[_asset("missing")], assetIdsDelete=["Glow_A-1"])
    repaired, audit = vfx._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    expected = copy.deepcopy(before)
    expected["slots"][0]["element"]["texture"]["assetId"] = "Glow_A-1"
    assert repaired == expected
    assert audit["ok"] and vfx.validate_vfx_director_output(repaired, data)["ok"]
    assert scope["fieldPermissions"]["slots"] == [{"slotId": "ingredient_element", "paths": ["element.texture.assetId"]}]


@pytest.mark.parametrize("duplicate", [False, True])
def test_asset_delete_permissions_preserve_first_valid_request(duplicate: bool) -> None:
    data = _data()
    raw = _with_asset(data)
    raw["assets"].append(_asset() if duplicate else _asset("unused"))
    report = vfx.validate_vfx_director_output(raw, data)
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    patch = _patch(assetIndicesDelete=[1]) if duplicate else _patch(assetIdsDelete=["unused"])
    repaired = vfx._apply_vfx_repair_patch(data, raw, patch, scope)
    assert repaired["assets"] == [_asset()]
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]


def test_foreign_payload_can_be_removed_without_changing_valid_legacy_renderer() -> None:
    data = _data()
    raw = _legacy(data)
    raw["slots"][0]["element"] = _sprite(data)["slots"][0]["element"]
    candidate = copy.deepcopy(raw["slots"][0])
    candidate.pop("element")
    candidate["alpha"] = 0.1
    scope = vfx._build_vfx_repair_scope(raw, vfx.validate_vfx_director_output(raw, data)["errors"])
    repaired = vfx._apply_vfx_repair_patch(data, raw, _patch(slotsUpsert=[candidate]), scope)
    assert repaired == _legacy(data)
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]


@pytest.mark.parametrize("field", ["slotsUpsert", "slotIdsDelete", "slotIndicesDelete", "assetsUpsert", "assetIdsDelete", "assetIndicesDelete"])
def test_optional_repair_edits_are_noop_when_absent_but_null_invalid(field: str) -> None:
    data = _data()
    schema = _sent(data, True)["outputSchema"]
    assert not strict_schema_errors(_patch(), schema)
    assert strict_schema_errors(_patch(**{field: None}), schema)
