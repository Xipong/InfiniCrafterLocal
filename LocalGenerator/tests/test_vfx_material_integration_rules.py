"""Binding review rules at transported schema, frozen merge and persisted admission."""
from __future__ import annotations

# Contract observers intentionally exercise the private request/scope/merge seams.
# pyright: reportPrivateUsage=false

import copy
import json
from typing import Any

import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring import strict_schema_errors
from tests.test_vfx_material_contract import _asset, _data, _legacy, _path, _sent, _sprite, _with_asset
from tests.test_vfx_material_repair import _patch


@pytest.mark.parametrize("mode,valid", [("baked_sprite", True), ("reuse_item_icon", True), ("no_asset", False), ("runtime_geometry", False), ("", False)])
def test_entity_texture_requires_that_exact_accepted_image_tuple(mode: str, valid: bool) -> None:
    data = _data()
    row = next(row for row in data["runtimeProgram"]["entities"] if row["kind"] != "item_body")
    row["visual"]["assetMode"] = mode
    raw = _sprite(data)
    raw["slots"][0].update(entityId=row["id"], event="on_spawn")
    raw["slots"][0]["element"]["texture"] = {"source": "entity", "assetId": ""}
    before = copy.deepcopy(data)
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"] is valid, report["errors"]
    for repair in (False, True):
        packet = _sent(data, repair)
        surface = packet["runtimeSurfaceReadOnly"] if repair else packet["runtimeSurface"]
        assert surface["textureDependencyTuples"]
        schema = packet["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]
        assert bool(strict_schema_errors(raw["slots"][0], schema)) is not valid
    if not valid:
        assert {r["path"] for r in report["errors"]} == {"$.slots[0].element.texture.source"}
        candidate = copy.deepcopy(raw["slots"][0])
        candidate["element"]["texture"]["source"] = "item"
        candidate["element"]["widthPx"] = 40
        scope = vfx._build_vfx_repair_scope(raw, report["errors"])
        repaired = vfx._apply_vfx_repair_patch(data, raw, _patch(slotsUpsert=[candidate]), scope)
        assert repaired["slots"][0]["element"]["widthPx"] == 12.0
        assert vfx.validate_vfx_director_output(repaired, data)["ok"]
    assert data == before


@pytest.mark.parametrize("renderer", ["spriteElement", "texturedPath"])
def test_nested_impact_requires_same_entity_existing_image_producer(renderer: str) -> None:
    data = _data()
    raw = _sprite(data) if renderer == "spriteElement" else _path(data)
    name = "element" if renderer == "spriteElement" else "path"
    raw["slots"][0][name]["texture"] = {"source": "impact", "assetId": ""}
    unpaired = vfx.validate_vfx_director_output(raw, data)
    assert not unpaired["ok"]
    assert {r["path"] for r in unpaired["errors"]} == {f"$.slots[0].{name}.texture.source"}
    producer = _legacy(data)["slots"][0]
    producer.update(id="exact_impact", entityId=raw["slots"][0]["entityId"], event=raw["slots"][0]["event"], rendererKind="impactSprite", backend="Sprite", textureRole="impact", spritePrompt="one impact ingredient")
    raw["slots"].append(producer)
    assert vfx.validate_vfx_director_output(raw, data)["ok"]
    final = vfx.attach_hybrid_vfx_manifest(data, "nested_impact", llm_director=lambda *_a, **_kw: raw)
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    final["vfxManifest"]["slots"].pop()
    report = vfx.validate_vfx_manifest_wire(final)
    assert not report["ok"]
    assert f"$.vfxManifest.slots[0].{name}.texture.source" in {r["path"] for r in report["errors"]}


@pytest.mark.parametrize("capability,source", [("channel_beam", "beam"), ("move_whip_lash", "whip")])
def test_current_geometry_anchor_is_neutral_self_in_both_sent_schemas(capability: str, source: str) -> None:
    data = _data(capability)
    raw = _path(data, source)
    raw["slots"][0]["anchor"] = "owner"
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert {r["path"] for r in report["errors"]} == {"$.slots[0].anchor"}
    for repair in (False, True):
        schema = _sent(data, repair)["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]
        assert strict_schema_errors(raw["slots"][0], schema)


def test_beam_collision_precedence_does_not_advertise_dormant_whip() -> None:
    data = _data("channel_beam")
    entity = next(row for row in data["runtimeProgram"]["entities"] if row["kind"] != "item_body")
    entity["movement"] = {"name": "move_whip_lash", "code": 18, "params": {"rangeTiles": 4, "segments": 10}}
    assert vfx.vfx_director_surface(data)["texturedPathSources"] == [{"entityId": entity["id"], "sources": ["anchorHistory", "beam"]}]
    entity["controller"]["name"] = "not_accepted_beam"
    assert vfx.vfx_director_surface(data)["texturedPathSources"] == [{"entityId": entity["id"], "sources": ["anchorHistory"]}]


@pytest.mark.parametrize("field", ["spritePath", "spriteUrl", "spriteStatus", "spriteTechnicalScore"])
def test_asset_authored_metadata_is_deleted_only_at_diagnosed_leaf(field: str) -> None:
    data = _data()
    raw = _with_asset(data)
    raw["assets"][0][field] = 0.5 if field == "spriteTechnicalScore" else "injected"
    report = vfx.validate_vfx_director_output(raw, data)
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    assert scope["fieldPermissions"]["assets"][0]["deletePaths"] == [field]
    candidate = _asset()
    candidate["prompt"] = "rewrite frozen prompt"
    repaired = vfx._apply_vfx_repair_patch(data, raw, _patch(assetsUpsert=[candidate]), scope)
    assert repaired == _with_asset(data)
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]


def test_duplicate_bad_later_row_cannot_grant_first_valid_asset_prompt_permission() -> None:
    data = _data()
    raw = _with_asset(data)
    bad_twin = _asset()
    bad_twin["prompt"] = ""
    raw["assets"].append(bad_twin)
    scope = vfx._build_vfx_repair_scope(raw, vfx.validate_vfx_director_output(raw, data)["errors"])
    assert scope["fieldPermissions"]["assets"] == []
    repaired = vfx._apply_vfx_repair_patch(data, raw, _patch(assetIndicesDelete=[1], assetsUpsert=[{**_asset(), "prompt": "replaced good twin"}]), scope)
    assert repaired == _with_asset(data)
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]


def test_duplicate_index_deletion_and_first_row_leaf_correction_do_not_alias_merge_ownership() -> None:
    data = _data()
    raw = _with_asset(data)
    raw["assets"][0]["prompt"] = ""
    raw["assets"].append(_asset())
    before = copy.deepcopy(raw)
    scope = vfx._build_vfx_repair_scope(raw, vfx.validate_vfx_director_output(raw, data)["errors"])
    assert scope["fieldPermissions"]["assets"] == [{"assetId": "Glow_A-1", "paths": ["prompt"]}]
    assert scope["deletableAssetIndices"] == [1] and scope["deletableAssetIds"] == []
    candidate = {**_asset(), "canvasSize": 64, "layout": "strip"}
    repaired = vfx._apply_vfx_repair_patch(data, raw, _patch(assetIndicesDelete=[1], assetIdsDelete=["Glow_A-1"], assetsUpsert=[candidate]), scope)
    assert repaired == _with_asset(data)
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]
    assert raw == before


def test_numeric_material_leaf_diagnosis_does_not_allow_whole_slot_deletion() -> None:
    data = _data()
    raw = _sprite(data)
    raw["slots"][0]["element"]["opacityProfile"]["middle"] = 2.0
    scope = vfx._build_vfx_repair_scope(raw, vfx.validate_vfx_director_output(raw, data)["errors"])
    assert scope["deletableSlotIds"] == []
    repaired = vfx._apply_vfx_repair_patch(data, raw, _patch(slotIdsDelete=["ingredient_element"]), scope)
    assert repaired == raw
    assert not vfx.validate_vfx_director_output(repaired, data)["ok"]


def test_nonforeign_omissions_are_nochange_even_with_a_broken_descendant() -> None:
    data = _data()
    raw = _sprite(data)
    raw["slots"][0]["element"]["widthProfile"]["middle"] = 9.0
    scope = vfx._build_vfx_repair_scope(raw, vfx.validate_vfx_director_output(raw, data)["errors"])
    assert "deletePaths" not in scope["fieldPermissions"]["slots"][0]


@pytest.mark.parametrize("kind,relative", [("legacy", "element"), ("sprite", "path"), ("path", "element"), ("nested", "element.shaderCode")])
def test_foreign_leaf_deletion_does_not_authorize_slot_loss_and_reaches_actual_bounded_stage(kind: str, relative: str) -> None:
    data = _data()
    clean = _legacy(data) if kind == "legacy" else (_path(data) if kind == "path" else _sprite(data))
    raw = copy.deepcopy(clean)
    target = raw["slots"][0]["element"] if kind == "nested" else raw["slots"][0]
    target[relative.rsplit(".", 1)[-1]] = "forbidden" if kind == "nested" else None
    before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    assert scope["fieldPermissions"]["slots"][0]["deletePaths"] == [relative]
    assert scope["deletableSlotIds"] == []
    denied = vfx._apply_vfx_repair_patch(data, raw, _patch(slotIdsDelete=[raw["slots"][0]["id"]]), scope)
    assert denied == raw
    assert not vfx.validate_vfx_director_output(denied, data)["ok"]
    replies = iter([raw, _patch(slotIdsDelete=[raw["slots"][0]["id"]])])
    with pytest.raises(PlannerUnavailable, match="VFX Repair did not produce"):
        vfx.attach_hybrid_vfx_manifest(_data(), "foreign_denied", llm_director=lambda *_a, **_kw: next(replies))
    candidate = copy.deepcopy(clean["slots"][0])
    candidate["alpha"] = 0.1
    replies = iter([raw, _patch(slotsUpsert=[candidate])])
    packets: list[dict[str, Any]] = []

    def respond(_system: str, _user: Any, *_args: Any, **kwargs: Any) -> Any:
        if kwargs.get("messages"):
            packets.append(json.loads(kwargs["messages"][1]["content"]))
        return next(replies)

    final = vfx.attach_hybrid_vfx_manifest(data, "foreign_positive", llm_director=respond)
    expected = clean["slots"][0].get("element") if kind != "path" else clean["slots"][0]["path"]
    assert final["vfxManifest"]["slots"][0].get("element" if kind != "path" else "path") == expected
    assert final["vfxManifest"]["slots"][0]["alpha"] == clean["slots"][0]["alpha"]
    assert relative.rsplit(".", 1)[-1] not in (final["vfxManifest"]["slots"][0]["element"] if kind == "nested" else final["vfxManifest"]["slots"][0])
    assert packets[0]["repairScope"] == scope
    assert final["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 1
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert raw == before
