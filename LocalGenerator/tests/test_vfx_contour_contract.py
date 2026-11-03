"""Actual admission, projection, references, texture dependencies and frozen Repair."""

from __future__ import annotations
import copy
import math
import pytest
import infini_local.core.vfx.contract as vfx_contract
import infini_local.core.vfx.projection as vfx_projection
import infini_local.core.vfx.repair as vfx_repair
import infini_local.core.vfx.validation as vfx_validation
from infini_local.core.vfx.contours import resolve_contours
from tests.vfx_material_fixtures import _data


def geometry():
    affine = {"translate": [0, 0], "scale": [1, 1], "rotationRadians": 0}
    material = {
        "texture": {"source": "library", "assetId": "solidPixel", "uv": {"quarterTurns": 0, "mirrorU": False, "mirrorV": False}},
        "sampling": "linear",
        "colorStart": {"r": 50, "g": 100, "b": 200},
        "colorEnd": {"r": 0, "g": 10, "b": 50},
        "opacityStart": 0.8,
        "opacityEnd": 0,
    }
    return {
        "attachment": "world",
        "rotationFrame": "source",
        "transformStart": copy.deepcopy(affine),
        "transformEnd": copy.deepcopy(affine),
        "contours": [
            {
                "id": "rim",
                "kind": "ellipseArc",
                "center": [0, 0],
                "radiusX": 32,
                "radiusY": 32,
                "startRadians": 0,
                "sweepRadians": math.tau,
                "segments": 16,
            },
            {"id": "inner", "kind": "transform", "source": "rim", "translate": [0, 0], "scale": [0.5, 0.5], "rotationRadians": 0},
        ],
        "draws": [
            {
                "opacityProfile": {"start": 1, "middle": 1, "end": 1, "curve": "linear"},
                "op": "band",
                "first": "inner",
                "second": "rim",
                "mapping": {"mode": "stretch", "repeatLengthPx": 1, "scrollPxPerTick": 0},
                "material": material,
            }
        ],
    }


def authored(data):
    return {
        "schema": vfx_contract.VFX_DIRECTOR_SCHEMA,
        "slots": [
            {
                "id": "contour_accent",
                "entityId": data["runtimeProgram"]["itemEntityId"],
                "event": "on_use",
                "rendererKind": "contour",
                "anchor": "self",
                "blend": "additive",
                "layer": "AfterProjectiles",
                "startTick": 0,
                "repeatEvery": 0,
                "duration": 20,
                "geometry": geometry(),
            }
        ],
    }


def test_contour_real_compile_preserves_dag_material_and_has_no_png_job():
    data = _data()
    raw = authored(data)
    before = copy.deepcopy(raw)
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"] == before
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "contour")
    assert data["vfxManifest"]["slots"][0]["geometry"] == before["slots"][0]["geometry"]
    assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]
    assert not vfx_validation.vfx_png_dependencies(data, raw)["dependencies"]
    assert raw == before


def test_forward_references_resolve_same_geometry_and_are_not_reordered():
    value = geometry()
    expected, errors = resolve_contours(value)
    assert not errors
    value["contours"].reverse()
    actual, errors = resolve_contours(value)
    assert not errors and actual == expected
    assert value["contours"][0]["id"] == "inner"


@pytest.mark.parametrize("mutation", ["cycle", "missing", "duplicate", "unknown", "null", "fold", "cross", "budget"])
def test_rejects_invalid_graph_or_topology_without_throwing(mutation):
    data = _data()
    raw = authored(data)
    g = raw["slots"][0]["geometry"]
    if mutation == "cycle":
        g["contours"][1]["source"] = "inner"
    if mutation == "missing":
        g["draws"][0]["first"] = "absent"
    if mutation == "duplicate":
        g["contours"][1]["id"] = "rim"
    if mutation == "unknown":
        g["contours"][0]["kind"] = "weapon_magic"
    if mutation == "null":
        g["contours"][0]["id"] = None
    if mutation == "fold":
        g["contours"][1]["scale"] = [-0.5, 0.5]
    if mutation == "cross":
        g["contours"][1]["translate"] = [25, 0]
    if mutation == "budget":
        g["contours"] = [
            {
                "id": f"rim{i}",
                "kind": "ellipseArc",
                "center": [0, 0],
                "radiusX": 32,
                "radiusY": 32,
                "startRadians": 0,
                "sweepRadians": math.tau,
                "segments": 64,
            }
            for i in range(9)
        ]
        g["draws"][0].update(first="rim0", second="rim1")
    assert not vfx_validation.validate_vfx_director_output(raw, data)["ok"]


def test_concave_fill_and_wedge_close_preserve_authored_vertices():
    data = _data()
    raw = authored(data)
    g = raw["slots"][0]["geometry"]
    g["contours"] = [
        {"id": "edge", "kind": "polyline", "points": [[0, 0], [20, 0], [8, 8], [20, 20], [0, 20]]},
        {"id": "face", "kind": "close", "source": "edge", "via": []},
    ]
    material = g["draws"][0]["material"]
    g["draws"] = [
        {"op": "fill", "contour": "face", "material": material, "mapping": {"origin": [0, 0], "size": [20, 20], "addressMode": "clamp"}}
    ]
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    points, _ = resolve_contours(g)
    assert points["face"] == [(0, 0), (20, 0), (8, 8), (20, 20), (0, 20), (0, 0)]
    g["contours"][0]["points"] = [[0, 0], [20, 20], [20, 0], [0, 20]]
    assert not vfx_validation.validate_vfx_director_output(raw, data)["ok"]


def test_stroke_controls_required_no_fill_path_mapping_guess():
    data = _data()
    raw = authored(data)
    g = raw["slots"][0]["geometry"]
    material = g["draws"][0]["material"]
    g["draws"] = [
        {
            "opacityProfile": {"start": 1, "middle": 1, "end": 1, "curve": "linear"},
            "op": "stroke",
            "contour": "rim",
            "widthPx": 2,
            "join": "miter",
            "cap": "butt",
            "miterLimit": 2,
            "material": material,
            "mapping": {"mode": "repeat", "repeatLengthPx": 20, "scrollPxPerTick": 2},
        }
    ]
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    del g["draws"][0]["join"]
    assert not vfx_validation.validate_vfx_director_output(raw, data)["ok"]


def test_nested_texture_dependency_has_exact_selector_not_fake_renderer():
    data = _data()
    raw = authored(data)
    texture = raw["slots"][0]["geometry"]["draws"][0]["material"]["texture"]
    texture.update(source="item", assetId="")
    deps = vfx_validation.vfx_png_dependencies(data, raw)
    assert len(deps["dependencies"]) == 1
    assert deps["dependencies"][0]["selectorPath"] == "$.slots[0].geometry.draws[0].material.texture.source"
    texture.update(source="asset", assetId="missing")
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert not report["ok"] and any(e["path"].endswith("draws[0].material.texture.assetId") for e in report["errors"])


def test_array_leaf_repair_preserves_other_draw_and_geometry_fields():
    data = _data()
    raw = authored(data)
    raw["slots"][0]["geometry"]["draws"][0]["material"]["opacityEnd"] = 2
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    scope = vfx_repair._build_vfx_repair_scope(raw, report["errors"])
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["geometry"]["draws"][0]["material"]["opacityEnd"] = 0
    candidate["geometry"]["contours"][0]["radiusX"] = 100
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [candidate], "note": "only invalid opacity"}
    repaired, audit = vfx_repair._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    assert vfx_validation.validate_vfx_director_output(repaired, data)["ok"]
    assert repaired["slots"][0]["geometry"]["contours"][0]["radiusX"] == 32
    assert audit["ignoredChanges"]


@pytest.mark.parametrize("bad", [None, [], {}, True, float("nan"), 10**400])
def test_malformed_numeric_graph_leaf_refused_without_native_projection(bad):
    data = _data()
    raw = authored(data)
    raw["slots"][0]["geometry"]["contours"][0]["radiusX"] = bad
    assert not vfx_validation.validate_vfx_director_output(raw, data)["ok"]


def test_per_operation_mapping_stays_precise_after_schema_deduplication():
    from jsonschema import Draft202012Validator
    from infini_local.core.vfx.contours import contour_schema

    value = geometry()
    schema = contour_schema()
    assert Draft202012Validator(schema).is_valid(value)
    value["draws"][0]["mapping"] = {"origin": [0, 0], "size": [20, 20], "addressMode": "repeat"}
    assert not Draft202012Validator(schema).is_valid(value)
    value["draws"][0] = {
        "op": "fill",
        "contour": "rim",
        "material": value["draws"][0]["material"],
        "mapping": {"mode": "stretch", "repeatLengthPx": 1, "scrollPxPerTick": 0},
    }
    assert not Draft202012Validator(schema).is_valid(value)


def test_repeated_texture_uses_retain_multiplicity_and_exact_draw_provenance():
    data = _data()
    raw = authored(data)
    value = raw["slots"][0]["geometry"]
    value["draws"][0]["material"]["texture"].update(source="item", assetId="")
    value["draws"].append(copy.deepcopy(value["draws"][0]))
    dependencies = vfx_validation.vfx_png_dependencies(data, raw)["dependencies"]
    assert len(dependencies) == 2
    assert [row["selectorPath"] for row in dependencies] == [f"$.slots[0].geometry.draws[{i}].material.texture.source" for i in range(2)]


def test_indexed_repair_cannot_expand_or_truncate_other_valid_draws():
    from infini_local.core.repair_merge import merge_frozen_subtree

    old = {"draws": [{"opacity": 2, "width": 7}, {"opacity": 0.5, "width": 4}]}
    for candidate in (
        {"draws": [{"opacity": 0, "width": 100}]},
        {"draws": [{"opacity": 0, "width": 100}, {"opacity": 1, "width": 100}, {"opacity": 1}]},
    ):
        merged, ignored, _ = merge_frozen_subtree(
            old, candidate, mutable_paths=["draws[0].opacity"], audit_path="$", array_leaves=True, allow_additions=False
        )
        assert merged == {"draws": [{"opacity": 0, "width": 7}, {"opacity": 0.5, "width": 4}]}
        assert ignored


def test_compiler_budgets_complete_multilayer_scene_without_dummy_slots():
    data = _data()
    raw = authored(data)
    value = raw["slots"][0]["geometry"]
    value["contours"][0]["segments"] = 64
    value["draws"] *= 3
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "multi-layer")
    assert len(data["vfxManifest"]["slots"]) == 1
    assert 192 <= data["vfxManifest"]["budget"]["maxDrawCalls"] <= 512
    assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]
    data["vfxManifest"]["budget"]["maxDrawCalls"] = 100
    assert not vfx_validation.validate_vfx_manifest_wire(data)["ok"]


def test_overcapacity_is_not_silently_clamped_or_permission_for_unrelated_slot():
    data = _data()
    raw = authored(data)
    value = raw["slots"][0]["geometry"]
    value["contours"][0]["segments"] = 64
    value["draws"] *= 16
    raw["slots"] = [copy.deepcopy(raw["slots"][0]) for _ in range(3)]
    for index, slot in enumerate(raw["slots"]):
        slot["id"] = f"contour_layer_{index}"
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    errors = [error for error in report["errors"] if "shared draw budget" in error["message"]]
    assert len(errors) == 16 and all("$.slots[2].geometry.draws[" in error["path"] for error in errors)
    scope = vfx_repair._build_vfx_repair_scope(raw, errors)
    assert not scope["allowCreateSlots"]
    assert not scope["deletableSlotIds"]


@pytest.mark.parametrize("scale,shift", [([0.5, 0.5], [10, 0]), ([4, 4], [0, 0])])
def test_float32_band_slivers_preserve_corners_without_false_overlap(scale, shift):
    value = geometry()
    value["contours"][1]["scale"] = scale
    value["contours"][1]["translate"] = shift
    resolved, errors = resolve_contours(value)
    assert not errors
    assert len(resolved["inner"]) == 17


def test_trim_preserves_all_corners_and_explicit_reverse_without_new_bridge():
    value = geometry()
    value["contours"] = [
        {"id": "middle", "kind": "trim", "source": "edge", "start": 0.25, "end": 0.75},
        {"id": "backward", "kind": "trim", "source": "edge", "start": 1, "end": 0},
        {"id": "edge", "kind": "polyline", "points": [[0, 0], [10, 0], [10, 10], [20, 10]]},
    ]
    value["draws"] = []
    points, errors = resolve_contours(value)
    assert not errors
    assert points["middle"][1:3] == [(10, 0), (10, 10)]
    assert points["middle"][0] == pytest.approx((7.5, 0), abs=1e-5)
    assert points["middle"][-1] == pytest.approx((12.5, 10), abs=1e-5)
    assert points["backward"] == list(reversed(points["edge"]))


@pytest.mark.parametrize("failure", [None, "gap", "cycle", "expansion"])
def test_concat_keeps_order_requires_coincidence_and_bounds_dag(failure):
    value = geometry()
    value["contours"] = [
        {"id": "joined", "kind": "concat", "sources": ["first", "second"]},
        {"id": "first", "kind": "line", "from": [0, 0], "to": [10, 0]},
        {"id": "second", "kind": "line", "from": [10, 0], "to": [10, 10]},
    ]
    value["draws"] = []
    if failure == "gap":
        value["contours"][2]["from"] = [11, 0]
    if failure == "cycle":
        value["contours"][0]["sources"][0] = "joined"
    if failure == "expansion":
        value["contours"][1] = {
            "id": "first",
            "kind": "ellipseArc",
            "center": [0, 0],
            "radiusX": 32,
            "radiusY": 32,
            "startRadians": 0,
            "sweepRadians": math.tau,
            "segments": 64,
        }
        value["contours"][0]["sources"] = ["first"] * 3
    points, errors = resolve_contours(value)
    assert bool(errors) is (failure is not None)
    if failure is None:
        assert points["joined"] == [(0, 0), (10, 0), (10, 10)]


def test_one_circle_reused_for_ring_outline_and_closed_quarter_fill():
    data = _data()
    raw = authored(data)
    value = raw["slots"][0]["geometry"]
    value["contours"].extend(
        [
            {"id": "quarter", "kind": "trim", "source": "rim", "start": 0, "end": 0.25},
            {"id": "wedge", "kind": "close", "source": "quarter", "via": [[0, 0]]},
        ]
    )
    value["draws"].append(
        {
            "op": "fill",
            "contour": "wedge",
            "material": copy.deepcopy(value["draws"][0]["material"]),
            "mapping": {"origin": [-32, -32], "size": [64, 64], "addressMode": "clamp"},
        }
    )
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"] == raw


def test_expanded_work_ceiling_uses_derived_576_not_blanket_2048():
    data = _data()
    raw = authored(data)
    value = raw["slots"][0]["geometry"]
    value["contours"][0]["segments"] = 64
    value["draws"] *= 9
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "expanded-derived-budget")
    assert data["vfxManifest"]["budget"]["maxDrawCalls"] == 576
    assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]


@pytest.mark.parametrize("explicit_budget", [256, 512])
def test_expansion_does_not_rewrite_existing_serialized_allowance(explicit_budget):
    data = _data()
    data["vfxManifest"] = vfx_projection._compile_manifest(data, authored(data), "saved-explicit-budget")
    data["vfxManifest"]["budget"]["maxDrawCalls"] = explicit_budget
    before = copy.deepcopy(data["vfxManifest"])
    assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]
    assert data["vfxManifest"] == before


def test_one_frozen_repair_simplifies_all_excess_draws_not_earlier_valid_layers():
    data = _data()
    raw = authored(data)
    first = raw["slots"][0]
    first["geometry"]["contours"][0]["segments"] = 64
    prototype = copy.deepcopy(first["geometry"]["draws"][0])
    stroke = {
        "op": "stroke",
        "contour": "rim",
        "widthPx": 2,
        "join": "bevel",
        "cap": "butt",
        "miterLimit": 2,
        "material": prototype["material"],
        "mapping": prototype["mapping"],
        "opacityProfile": prototype["opacityProfile"],
    }
    first["geometry"]["draws"] = [copy.deepcopy(stroke) for _ in range(16)]
    first["id"] = "valid_scene"
    second = copy.deepcopy(first)
    second["id"] = "partly_excessive_scene"
    second["geometry"]["draws"] = [copy.deepcopy(prototype) for _ in range(16)]
    second["geometry"]["contours"].extend(
        [
            {"id": "small_outer", "kind": "polyline", "points": [[0, 0], [2, 0], [0, 2], [0, 0]]},
            {
                "id": "small_inner",
                "kind": "transform",
                "source": "small_outer",
                "scale": [0.5, 0.5],
                "rotationRadians": 0,
                "translate": [0.25, 0.25],
            },
        ]
    )
    raw["slots"].append(second)
    report = vfx_validation.validate_vfx_director_output(raw, data)
    errors = [error for error in report["errors"] if "shared draw budget" in error["message"]]
    assert len(errors) == 9
    scope = vfx_repair._build_vfx_repair_scope(raw, errors)
    assert scope["mutableSlotIds"] == ["partly_excessive_scene"]
    assert not scope["deletableSlotIds"]
    candidate = copy.deepcopy(raw["slots"])
    candidate[0]["geometry"]["draws"][0]["widthPx"] = 100
    candidate[1]["geometry"]["draws"][0]["material"]["opacityStart"] = 0.01
    for draw in candidate[1]["geometry"]["draws"][7:]:
        draw.update(first="small_inner", second="small_outer")
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": candidate, "note": "simplify only diagnosed excessive layers"}
    repaired, audit = vfx_repair._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    result = vfx_validation.validate_vfx_director_output(repaired, data)
    assert result["ok"], result["errors"]
    assert repaired["slots"][0] == raw["slots"][0]
    assert repaired["slots"][1]["geometry"]["draws"][:7] == raw["slots"][1]["geometry"]["draws"][:7]
    assert len(audit["ignoredChanges"]) >= 2


def test_one_repair_can_explicitly_silence_all_excess_strokes_without_widening():
    data = _data()
    raw = authored(data)
    slot = raw["slots"][0]
    slot["geometry"]["contours"][0]["segments"] = 64
    band = slot["geometry"]["draws"][0]
    stroke = {
        "op": "stroke",
        "contour": "rim",
        "widthPx": 2,
        "join": "bevel",
        "cap": "butt",
        "miterLimit": 2,
        "material": band["material"],
        "mapping": band["mapping"],
        "opacityProfile": band["opacityProfile"],
    }
    slot["geometry"]["draws"] = [copy.deepcopy(stroke) for _ in range(16)]
    raw["slots"].append(copy.deepcopy(slot))
    raw["slots"][1]["id"] = "overflow_strokes"
    report = vfx_validation.validate_vfx_director_output(raw, data)
    errors = [error for error in report["errors"] if "shared draw budget" in error["message"]]
    assert len(errors) == 11
    scope = vfx_repair._build_vfx_repair_scope(raw, errors)
    assert not scope["deletableSlotIds"]
    candidate = copy.deepcopy(raw["slots"])
    candidate[0]["geometry"]["draws"][0]["widthPx"] = 100
    candidate[1]["geometry"]["draws"][0]["material"]["opacityStart"] = 0.01
    for draw in candidate[1]["geometry"]["draws"][5:]:
        draw["widthPx"] = 0
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": candidate, "note": "explicit zero width only on excessive strokes"}
    repaired, audit = vfx_repair._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    result = vfx_validation.validate_vfx_director_output(repaired, data)
    assert result["ok"], result["errors"]
    assert repaired["slots"][0] == raw["slots"][0]
    assert repaired["slots"][1]["geometry"]["draws"][:5] == raw["slots"][1]["geometry"]["draws"][:5]
    assert all(draw["widthPx"] == 0 for draw in repaired["slots"][1]["geometry"]["draws"][5:])
    assert len(audit["ignoredChanges"]) >= 2


def test_silent_draw_after_overflow_is_not_granted_repair_authority():
    from infini_local.core.vfx.contours import contour_budget_errors

    data = _data()
    raw = authored(data)
    value = raw["slots"][0]["geometry"]
    band = value["draws"][0]
    silent = {
        "op": "stroke",
        "contour": "rim",
        "widthPx": 0,
        "join": "bevel",
        "cap": "butt",
        "miterLimit": 2,
        "material": copy.deepcopy(band["material"]),
        "mapping": copy.deepcopy(band["mapping"]),
        "opacityProfile": copy.deepcopy(band["opacityProfile"]),
    }
    value["draws"].append(silent)
    errors = contour_budget_errors(raw["slots"], available=1)
    assert [row["path"] for row in errors] == ["$.slots[0].geometry.draws[0]"]
    scope = vfx_repair._build_vfx_repair_scope(raw, errors)
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["geometry"]["draws"][1]["widthPx"] = 8
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [candidate], "note": "attempt to rewrite silent sibling"}
    repaired, audit = vfx_repair._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    assert repaired == raw
    assert any(row["path"].endswith("draws[1].widthPx") for row in audit["ignoredChanges"])
