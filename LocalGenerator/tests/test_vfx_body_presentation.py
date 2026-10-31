"""Actual Director/Repair delivery of selected body coverage, not prose snapshots."""
from copy import deepcopy

import pytest

import infini_local.core.vfx.surface as vfx_surface
from tests.test_director_example_neutrality import _accepted_data, _capture_vfx


@pytest.mark.parametrize("repair", [False, True])
@pytest.mark.parametrize("mode", ["runtime_geometry", "no_asset", "baked_sprite", "reuse_item_icon"])
def test_selected_body_coverage_reaches_director_and_repair(monkeypatch, mode, repair):
    data = _accepted_data()
    entity = next(row for row in data["runtimeProgram"]["entities"] if "lashGeometry" in row)
    entity["visual"] = {"assetMode": mode, "renderSizePx": 26,
                        "forwardAngleDegrees": -90, "spritePath": "/private/not-model-context.png"}
    entity["hitbox"] = {"widthPx": 16, "heightPx": 16, "hitboxScale": 1}
    data["visual"] = {"renderSizePx": 44, "forwardAngleDegrees": 0, "spritePath": "/private/root.png"}
    data["visualKit"] = {"animationPlan": "A tapered material follows the accepted curve.", "item": {"palette": ["gold"]}}
    frozen = deepcopy(data)
    _, packet = _capture_vfx(monkeypatch, data, repair=repair)
    surface = packet["runtimeSurfaceReadOnly" if repair else "runtimeSurface"]
    row = next(row for row in surface["bodyPresentation"] if row["entityId"] == entity["id"])
    assert row["assetMode"] == mode
    frame = {"aim": {"source": "initial", "turnOwner": False},
             "units": {"distance": "native_world_pixels", "duration": "world_ticks"}}
    assert row["frame"] == frame
    if mode == "runtime_geometry":
        assert row == {"entityId": entity["id"], "assetMode": mode, "frame": frame,
                       "coverage": "collision_curve", "material": "solid_untextured", "widthPx": 8}
    elif mode == "no_asset":
        assert row == {"entityId": entity["id"], "assetMode": mode, "frame": frame, "coverage": "no_body"}
    else:
        assert row["coverage"] == "single_sprite_at_curve_tip"
        assert row["image"] == ({"renderSizePx": 44, "forwardAngleDegrees": 0} if mode == "reuse_item_icon"
                                else {"renderSizePx": 26, "forwardAngleDegrees": -90})
    assert packet["acceptedVisualKitReadOnly" if repair else "acceptedVisualKit"] == data["visualKit"]
    if repair:
        assert packet["repairScope"] == {}
    assert data == frozen
    row["coverage"] = "tampered"
    assert data == frozen


def test_geometry_facts_follow_selected_data_not_name_or_missing_defaults():
    data = _accepted_data()
    entity = next(row for row in data["runtimeProgram"]["entities"] if "lashGeometry" in row)
    entity["visual"] = {"assetMode": "runtime_geometry"}
    entity["hitbox"] = {"widthPx": 2, "hitboxScale": 0.1}
    first = vfx_surface._body_presentation(data)
    row = next(row for row in first if row["entityId"] == entity["id"])
    assert row["widthPx"] == 4  # same actual native collision/render minimum
    data["name"] = "invisible rigid sword"
    assert vfx_surface._body_presentation(data) == first
    entity["hitbox"].pop("hitboxScale")
    assert "widthPx" not in next(row for row in vfx_surface._body_presentation(data) if row["entityId"] == entity["id"])
    entity.pop("lashGeometry")
    row = next(row for row in vfx_surface._body_presentation(data) if row["entityId"] == entity["id"])
    assert row["coverage"] == "body_segment"
    assert "widthPx" not in row


def test_item_body_uses_root_image_and_preserves_explicit_hidden_use():
    data = _accepted_data()
    body = next(row for row in data["runtimeProgram"]["entities"] if row["kind"] == "item_body")
    body["visual"] = {"assetMode": "baked_sprite"}
    data["visual"] = {"renderSizePx": 48, "forwardAngleDegrees": 0}
    data["runtimeProgram"]["itemUse"] = {"hideUseGraphic": True, "releaseTiming": "immediate"}
    row = next(row for row in vfx_surface._body_presentation(data) if row["entityId"] == body["id"])
    assert row["image"] == {"renderSizePx": 48, "forwardAngleDegrees": 0}
    assert row["coverage"] == "inventory_and_item_use"
    assert row["itemUse"] == {"hideUseGraphic": True, "releaseTiming": "immediate"}


@pytest.mark.parametrize("driver,source", [
    ({"movement": {"name": "move_whip_lash", "code": 18}}, "whip"),
    ({"controller": {"name": "channel_beam", "code": 1}}, "beam"),
    ({"lashGeometry": {}, "controller": {"name": "channel_beam", "code": 1}}, "beam"),
    ({"beamGeometry": {}, "movement": {"name": "move_whip_lash", "code": 18}}, "beam"),
])
def test_saved_wire_geometry_coverage_matches_path_source_without_recompiling(driver, source):
    data = _accepted_data()
    entity = next(row for row in data["runtimeProgram"]["entities"] if "lashGeometry" in row)
    for key in ("lashGeometry", "beamGeometry", "controller", "movement"):
        entity.pop(key, None)
    entity.update(deepcopy(driver))
    entity["visual"] = {"assetMode": "runtime_geometry"}
    frozen = deepcopy(data)
    surface = vfx_surface.vfx_director_surface(data)
    paths = next(row for row in surface["texturedPathSources"] if row["entityId"] == entity["id"])
    body = next(row for row in surface["bodyPresentation"] if row["entityId"] == entity["id"])
    assert paths["sources"] == ["anchorHistory", source, "ownerLink"]
    assert body["coverage"] == ("collision_beam" if source == "beam" else "collision_curve")
    assert data == frozen
