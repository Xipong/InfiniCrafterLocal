"""Explicit solid-body authorship survives delivery and exact scoped Repair."""
import copy

import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.storage.world_storage import sanitize_recipe_for_delivery
from test_low_level_three_stage_pipeline import _visual_kit


def case():
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    kit = _visual_kit(data)
    row = next(row for row in kit["entities"] if row["entityId"] != "item")
    row.update(assetMode="runtime_geometry", visualProjectRef="none", geometry={
        "schema": "infini.body-geometry.v1", "source": "body_segment", "widthPx": 3.5,
        "lengthPx": 73, "axis": "rotation", "color": "#28aAbF", "opacity": 0.41,
    })
    return data, kit, row


def validate(data, kit):
    runtime = data["runtimeProgram"]
    return visual._validate_kit(kit, [e["id"] for e in runtime["entities"]], runtime["itemEntityId"], accepted_data=data)


def test_geometry_is_literal_through_visual_and_delivered_wire():
    data, kit, row = case()
    before = copy.deepcopy(data["runtimeProgram"])
    accepted, errors = validate(data, kit)
    assert accepted is not None, errors
    result = sanitize_recipe_for_delivery(visual._apply_kit(data, accepted))
    entity = next(e for e in result["runtimeProgram"]["entities"] if e["id"] == row["entityId"])
    assert entity["visual"]["geometry"] == row["geometry"]
    assert validate_runtime_wire(result)["ok"]
    for e, original in zip(result["runtimeProgram"]["entities"], before["entities"]):
        assert {k: v for k, v in e.items() if k != "visual"} == {k: v for k, v in original.items() if k != "visual"}


@pytest.mark.parametrize("change", [
    lambda r: r.pop("geometry"),
    lambda r: r["geometry"].update(widthPx=0),
    lambda r: r["geometry"].update(color="gold"),
    lambda r: r["geometry"].update(opacity=2),
    lambda r: r["geometry"].update(widthPx=float("nan")),
    lambda r: r["geometry"].update(axis="aim"),
    lambda r: r.update(assetMode="no_asset"),
])
def test_fresh_geometry_requires_authored_valid_choices(change):
    data, kit, row = case()
    change(row)
    accepted, errors = validate(data, kit)
    assert accepted is None and errors


def test_collision_path_requires_real_accepted_geometry_not_a_visual_role():
    data, kit, row = case()
    row["geometry"].update(source="collision_path")
    row["geometry"].pop("lengthPx")
    row["geometry"].pop("axis")
    entity = next(e for e in data["runtimeProgram"]["entities"] if e["id"] == row["entityId"])
    entity.pop("lashGeometry", None)
    entity.pop("beamGeometry", None)
    entity["movement"] = {"name": "move_linear", "code": 1, "params": {}}
    entity["visualRole"] = "whip"
    assert validate(data, kit)[0] is None
    entity["lashGeometry"] = {}
    assert validate(data, kit)[0] is not None
    entity.pop("lashGeometry")
    entity["movement"] = {"name": "move_whip_lash", "code": 18, "params": {}}
    assert validate(data, kit)[0] is not None


def test_geometry_repair_keeps_other_valid_leaves_frozen():
    data, kit, row = case()
    row["geometry"]["opacity"] = 2
    _, errors = validate(data, kit)
    runtime = data["runtimeProgram"]
    ids = [e["id"] for e in runtime["entities"]]
    scope = visual._build_visual_repair_scope(kit, errors, ids, runtime["itemEntityId"])
    changed = copy.deepcopy(row)
    changed["geometry"].update(opacity=0.25, color="#ffffff", widthPx=99)
    patch = {"schema": visual.VISUAL_REPAIR_PATCH_SCHEMA, "itemPatch": None,
             "entitiesUpsert": [changed], "entityIdsDelete": [], "entityIndicesDelete": [], "note": "repair opacity"}
    repaired, audit = visual._apply_visual_repair_patch(kit, patch, scope, ids, return_audit=True)
    accepted, errors = validate(data, repaired)
    assert accepted is not None, errors
    geometry = next(r["geometry"] for r in accepted["entities"] if r["entityId"] == row["entityId"])
    assert geometry == {**row["geometry"], "opacity": 0.25}
    assert audit


def test_scoped_geometry_repair_requests_only_invalid_leaf():
    data, kit, row = case()
    row["geometry"]["opacity"] = 2
    _, errors = validate(data, kit)
    runtime = data["runtimeProgram"]
    ids = [e["id"] for e in runtime["entities"]]
    scope = visual._build_visual_repair_scope(kit, errors, ids, runtime["itemEntityId"])
    schema = visual._scoped_visual_repair_schema(ids, False, runtime["itemEntityId"], scope, kit)
    entity_schema = schema["properties"]["entitiesUpsert"]["items"]
    assert set(entity_schema["properties"]) == {"entityId", "geometry"}
    assert set(entity_schema["properties"]["geometry"]["properties"]) == {"opacity"}


def test_saved_missing_geometry_preserves_wire_but_invalid_present_fails():
    data, kit, row = case()
    projected = visual._apply_kit(data, kit)
    entity = next(e for e in projected["runtimeProgram"]["entities"] if e["id"] == row["entityId"])
    entity["visual"].pop("geometry")
    assert validate_runtime_wire(projected)["ok"]
    entity["visual"]["geometry"] = {**row["geometry"], "color": "garbage"}
    assert not validate_runtime_wire(projected)["ok"]


def test_geometry_repair_removes_only_unknown_nested_field():
    data, kit, row = case()
    row["geometry"]["inventedGlow"] = 8
    _, errors = validate(data, kit)
    runtime = data["runtimeProgram"]
    ids = [e["id"] for e in runtime["entities"]]
    scope = visual._build_visual_repair_scope(kit, errors, ids, runtime["itemEntityId"])
    changed = copy.deepcopy(row)
    changed["geometry"].pop("inventedGlow")
    changed["geometry"]["color"] = "#ffffff"
    patch = {"schema": visual.VISUAL_REPAIR_PATCH_SCHEMA, "itemPatch": None,
             "entitiesUpsert": [changed], "entityIdsDelete": [], "entityIndicesDelete": [], "note": "remove unknown field"}
    repaired, _ = visual._apply_visual_repair_patch(kit, patch, scope, ids, return_audit=True)
    accepted, errors = validate(data, repaired)
    assert accepted is not None, errors
    geometry = next(r["geometry"] for r in accepted["entities"] if r["entityId"] == row["entityId"])
    assert geometry == {k: v for k, v in row["geometry"].items() if k != "inventedGlow"}


def test_vfx_receives_explicit_body_shape_not_collision_shape_or_light():
    from infini_local.core.vfx_manifest import _body_presentation
    data, kit, row = case()
    projected = visual._apply_kit(data, kit)
    entity = next(e for e in projected["runtimeProgram"]["entities"] if e["id"] == row["entityId"])
    entity["lashGeometry"] = {}
    entity["light"] = {"color": "#ff0000"}
    presentation = next(r for r in _body_presentation(projected) if r["entityId"] == row["entityId"])
    assert presentation["coverage"] == "body_segment"
    assert presentation["geometry"] == row["geometry"]
    entity["visual"]["geometry"] = {k: v for k, v in row["geometry"].items() if k not in ("axis", "lengthPx")}
    entity["visual"]["geometry"]["source"] = "collision_path"
    presentation = next(r for r in _body_presentation(projected) if r["entityId"] == row["entityId"])
    assert presentation["coverage"] == "collision_curve"
    assert presentation["widthPx"] == row["geometry"]["widthPx"]


def test_previous_visual_kit_version_is_not_replayed_as_fresh_authorship():
    data, kit, _ = case()
    kit["schema"] = "infini.visual-kit.runtime-entities.v2"
    accepted, errors = validate(data, kit)
    assert accepted is None
    assert any(error["path"] == "$.schema" for error in errors)
