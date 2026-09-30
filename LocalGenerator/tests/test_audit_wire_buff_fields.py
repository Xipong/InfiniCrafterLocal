"""A7: active effects cannot mask malformed delivery buff neighbours."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION
from infini_local.core.vfx_manifest import _compile_manifest
from infini_local.storage.world_storage import sanitize_recipe_for_delivery, is_deliverable_recipe_payload


def _wire():
    source = build_capability_witness("apply_generated_buff_on_use")
    wire = compile_runtime_program(source)
    wire.pop("runtimeContract")
    wire["gameplay"]["generatedBuff"]["emitLightStrength"] = 0.25
    return wire


@pytest.mark.parametrize("field,value", [
    ("jumpBoost", "broken"), ("lifeRegen", True),
    ("miningSpeedMultiplier", 0), ("oreSenseRadiusTiles", 2),
])
def test_a7_storage_delivery_gate_rejects_malformed_neighbour(field, value):
    delivery = sanitize_recipe_for_delivery(_wire())
    delivery.update(id="receipt_probe", name="Receipt probe", schemaVersion=5,
                    runtimeApiVersion=RUNTIME_PROGRAM_API_VERSION)
    # The positive control is a complete compiled empty VFX manifest, not only
    # a schema marker. This observer isolates the malformed buff neighbour.
    delivery["vfxManifest"] = _compile_manifest(delivery, {
        "effectMagnitude": 0.0, "visualBudgetClass": "tiny",
        "motif": {"element": "neutral", "shapeLanguage": "none", "motionLanguage": "none",
                  "paletteRole": "primary", "rhythm": 1.0, "chaos": 0.0},
        "slots": [],
    }, "receipt_probe")
    assert is_deliverable_recipe_payload(delivery)
    delivery["gameplay"]["generatedBuff"][field] = value
    assert not is_deliverable_recipe_payload(delivery)


@pytest.mark.parametrize("field,value", [
    ("jumpBoost", "broken"), ("lifeRegen", True),
    ("miningSpeedMultiplier", 0), ("oreSenseRadiusTiles", 2),
    ("durationTicks", 21601), ("durationTicks", 1.0),
    ("manaRegen", 1.0), ("lifeRegen", 1.0), ("oreSenseRadiusTiles", True),
    ("movementSpeed", -0.6), ("jumpBoost", 9), ("manaRegen", 121),
    ("lifeRegen", 121), ("emitLightStrength", 2),
    ("lightColorName", "broken"), ("lightColorName", None),
    ("jumpBoost", float("inf")), ("jumpBoost", 10 ** 1000),
    ("miningSpeedMultiplier", None), ("extra", 1),
    ("jumpBoost", 1e-50), ("miningSpeedMultiplier", 1.000000001),
])
def test_active_light_does_not_hide_invalid_wire_field(field, value):
    wire = _wire()
    wire["gameplay"]["generatedBuff"][field] = value
    before = deepcopy(wire)
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(e["path"] == f"$.gameplay.generatedBuff.{field}" for e in report["errors"])
    assert wire == before


@pytest.mark.parametrize("field,value", [
    ("miningSpeedMultiplier", 1), ("jumpBoost", 1), ("movementSpeed", 1),
    ("emitLightStrength", 1), ("lifeRegen", 1), ("oreSenseRadiusTiles", 1),
])
def test_numeric_json_integers_accepted_for_float_dto_fields(field, value):
    wire = _wire()
    wire["gameplay"]["generatedBuff"][field] = value
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("bad", [None, [], 0, "buff"])
def test_present_malformed_buff_object_is_not_hidden_by_healing(bad):
    wire = _wire()
    wire["gameplay"]["healLife"] = 10
    wire["gameplay"]["generatedBuff"] = bad
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(e["path"] == "$.gameplay.generatedBuff" for e in report["errors"])


@pytest.mark.parametrize("color_present", [False, True])
def test_empty_or_missing_color_is_invalid_for_active_light(color_present):
    wire = _wire()
    if color_present:
        wire["gameplay"]["generatedBuff"]["lightColorName"] = ""
    else:
        del wire["gameplay"]["generatedBuff"]["lightColorName"]
    assert not validate_runtime_wire(wire)["ok"]


def test_sparse_legacy_buff_uses_dto_defaults_without_materializing():
    wire = _wire()
    wire["gameplay"]["generatedBuff"] = {"durationTicks": 60, "jumpBoost": 1}
    before = deepcopy(wire)
    assert validate_runtime_wire(wire)["ok"]
    assert wire == before
