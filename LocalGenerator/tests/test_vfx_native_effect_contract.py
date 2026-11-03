"""Stock effects remain explicit, bounded and separate from gameplay and image jobs."""

from __future__ import annotations
import copy
import pytest
import infini_local.core.vfx.contract as vfx_contract
import infini_local.core.vfx.projection as vfx_projection
import infini_local.core.vfx.repair as vfx_repair
import infini_local.core.vfx.validation as vfx_validation
from infini_local.core.vfx.native_effects import NATIVE_EFFECT_TYPES, MOVING_NATIVE_EFFECTS
from tests.vfx_material_fixtures import _data


def effect(kind="goldCrossBurst", data=None):
    payload = {"type": kind}
    if kind in MOVING_NATIVE_EFFECTS:
        payload["movement"] = {"x": -4.25, "y": 2}
    return {
        "schema": vfx_contract.VFX_DIRECTOR_SCHEMA,
        "slots": [
            {
                "id": "native_effect",
                "entityId": (data or _data())["runtimeProgram"]["itemEntityId"],
                "event": "on_use",
                "rendererKind": "nativeEffect",
                "anchor": "hitPoint",
                "startTick": 3,
                "repeatEvery": 0,
                "nativeEffect": payload,
            }
        ],
    }


@pytest.mark.parametrize("kind", NATIVE_EFFECT_TYPES)
def test_stock_effect_identity_through_director_compile_saved_wire(kind):
    data = _data()
    raw = effect(kind)
    before = copy.deepcopy(raw)
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"] == before
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "stock-effects")
    assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]
    delivered = data["vfxManifest"]["slots"][0]
    assert {k: v for k, v in delivered.items() if k != "slotSeed"} == before["slots"][0]
    assert vfx_validation.vfx_png_dependencies(data, raw)["dependencies"] == []
    assert raw == before


@pytest.mark.parametrize("kind", NATIVE_EFFECT_TYPES)
def test_movement_is_required_only_when_native_reads_it(kind):
    raw = effect(kind)
    payload = raw["slots"][0]["nativeEffect"]
    if kind in MOVING_NATIVE_EFFECTS:
        payload.pop("movement")
    else:
        payload["movement"] = {"x": 0, "y": 0}
    assert not vfx_validation.validate_vfx_director_output(raw, _data())["ok"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("type", "ItemTransfer"),
        ("type", "GasTrap"),
        ("type", []),
        ("type", None),
        ("type", "goldCrossBurst "),
        ("tint", "#FFFFFF"),
        ("count", 4),
        ("playerIndex", 0),
        ("uniqueInfoPiece", 1),
    ],
)
def test_unlisted_native_routes_or_ignored_controls_rejected(field, value):
    raw = effect()
    raw["slots"][0]["nativeEffect"][field] = value
    assert not vfx_validation.validate_vfx_director_output(raw, _data())["ok"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("color", {"r": 1, "g": 2, "b": 3}),
        ("duration", 30),
        ("scale", 1),
        ("density", 0.5),
        ("spread", 1),
        ("alpha", 1),
        ("blend", "alpha"),
        ("layer", "front"),
        ("particleSystemId", "Smoke"),
        ("textureRole", "item"),
    ],
)
def test_common_ignored_art_controls_rejected(field, value):
    raw = effect()
    raw["slots"][0][field] = value
    assert not vfx_validation.validate_vfx_director_output(raw, _data())["ok"]


@pytest.mark.parametrize("value", [-24.01, 24.01, True, None, [], float("inf"), float("nan")])
def test_invalid_native_movement_never_clamped(value):
    raw = effect("shimmerStar")
    raw["slots"][0]["nativeEffect"]["movement"]["x"] = value
    assert not vfx_validation.validate_vfx_director_output(raw, _data())["ok"]


def test_periodic_item_gate_and_exact_cadence():
    raw = effect()
    slot = raw["slots"][0]
    slot.update(event="periodic", startTick=0, repeatEvery=1)
    assert vfx_validation.validate_vfx_director_output(raw, _data())["ok"]
    slot["repeatEvery"] = 0
    assert not vfx_validation.validate_vfx_director_output(raw, _data())["ok"]
    slot.update(repeatEvery=1, startTick=1)
    assert not vfx_validation.validate_vfx_director_output(raw, _data())["ok"]


def test_repair_invalid_movement_x_cannot_change_y_or_effect():
    data = _data()
    raw = effect("rainbowBurst")
    raw["slots"][0]["nativeEffect"]["movement"]["x"] = 25
    report = vfx_validation.validate_vfx_director_output(raw, data)
    scope = vfx_repair._build_vfx_repair_scope(raw, report["errors"])
    fixed = copy.deepcopy(raw["slots"][0])
    fixed["nativeEffect"].update(type="shimmerStar", movement={"x": 10, "y": 20})
    result = vfx_repair._apply_vfx_repair_patch(
        data, raw, {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [fixed], "note": "x only"}, scope
    )
    expected = copy.deepcopy(raw)
    expected["slots"][0]["nativeEffect"]["movement"]["x"] = 10
    assert result == expected
    assert vfx_validation.validate_vfx_director_output(result, data)["ok"]


def test_missing_movement_repair_cannot_change_valid_type_or_timing():
    data = _data()
    raw = effect("shimmerStar")
    raw["slots"][0]["nativeEffect"].pop("movement")
    report = vfx_validation.validate_vfx_director_output(raw, data)
    scope = vfx_repair._build_vfx_repair_scope(raw, report["errors"])
    fixed = copy.deepcopy(raw["slots"][0])
    fixed.update(startTick=60)
    fixed["nativeEffect"].update(type="rainbowBurst", movement={"x": 0, "y": 0})
    result = vfx_repair._apply_vfx_repair_patch(
        data, raw, {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [fixed], "note": "missing movement"}, scope
    )
    expected = copy.deepcopy(raw)
    expected["slots"][0]["nativeEffect"]["movement"] = {"x": 0, "y": 0}
    assert result == expected
    assert vfx_validation.validate_vfx_director_output(result, data)["ok"]


@pytest.mark.parametrize("kind,cost", [("goldCrossBurst", 16), ("rainbowBurst", 36), ("darkLightningBurst", 8), ("shimmerStar", 1)])
@pytest.mark.parametrize("field", ["maxParticlesPerTick", "maxParticlesTotal"])
def test_impossible_saved_budget_rejected_but_exact_burst_admitted(kind, cost, field):
    data = _data()
    data["vfxManifest"] = vfx_projection._compile_manifest(data, effect(kind), "budget")
    assert data["vfxManifest"]["budget"][field] >= cost
    data["vfxManifest"]["budget"][field] = cost - 1
    report = vfx_validation.validate_vfx_manifest_wire(data)
    assert not report["ok"]
    assert any(e["path"] == "$.vfxManifest.budget." + field for e in report["errors"])
    assert data["vfxManifest"]["budget"][field] == cost - 1
    data["vfxManifest"]["budget"][field] = cost
    assert vfx_validation.validate_vfx_manifest_wire(data)["ok"]
