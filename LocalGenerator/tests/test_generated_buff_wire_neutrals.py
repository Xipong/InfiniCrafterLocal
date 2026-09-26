"""Generated-buff binding dependency follows executable stats, not generic truthiness."""
from __future__ import annotations

import pytest

from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness


_NEUTRAL_PARAMS = {
    "miningSpeedMultiplier": 1,
    "lightStrength": 0,
    "lightColor": "white",
    "oreSenseEnabled": False,
    "moveSpeedBonusFactor": 0,
    "jumpSpeedBonusPxPerTick": 0,
    "manaRegenBonusPoints": 0,
    "lifeRegenHpPerSecond": 0,
}
_OPTIONAL = (
    "miningSpeedMultiplier", "oreSenseEnabled", "moveSpeedBonusFactor",
    "jumpSpeedBonusPxPerTick", "manaRegenBonusPoints", "lifeRegenHpPerSecond",
)


def _author(effect: str, value: object, *, sparse: bool):
    source = build_capability_witness("apply_generated_buff_on_use")
    params = next(call["params"] for call in source["runtimeProgram"]["calls"]
                  if call["fn"] == "apply_generated_buff_on_use")
    params.update(_NEUTRAL_PARAMS)
    params[effect] = value
    if sparse:
        for key in _OPTIONAL:
            if key != effect:
                params.pop(key)
    return source


@pytest.mark.parametrize("effect,value,wire_key,wire_value", [
    ("miningSpeedMultiplier", 1.5, "miningSpeedMultiplier", 1.5),
    ("lightStrength", 0.25, "emitLightStrength", 0.25),
    ("oreSenseEnabled", True, "oreSenseRadiusTiles", 1),
    ("moveSpeedBonusFactor", 0.2, "movementSpeed", 0.2),
    ("jumpSpeedBonusPxPerTick", 1, "jumpBoost", 1),
    ("manaRegenBonusPoints", 1, "manaRegen", 1),
    ("lifeRegenHpPerSecond", 0.5, "lifeRegen", 1),
])
@pytest.mark.parametrize("sparse", [False, True], ids=["explicit_neutrals", "omitted_neutrals"])
def test_sole_executable_generated_buff_stat_keeps_effect_binding(effect, value, wire_key, wire_value, sparse):
    wire = compile_runtime_program(_author(effect, value, sparse=sparse))
    assert wire["gameplay"]["generatedBuff"][wire_key] == wire_value
    report = validate_runtime_wire(wire)
    assert report["ok"], report["errors"]


@pytest.mark.parametrize("color", ["white", "red"])
def test_color_without_light_or_other_stats_is_not_effect(color):
    wire = compile_runtime_program(_author("lightStrength", 0.25, sparse=False))
    buff = wire["gameplay"]["generatedBuff"]
    buff["emitLightStrength"] = 0
    buff["lightColorName"] = color
    report = validate_runtime_wire(wire)
    assert any(error["code"] == "binding_dependency" for error in report["errors"])


def test_executable_stat_without_duration_cannot_enable_binding():
    wire = compile_runtime_program(_author("oreSenseEnabled", True, sparse=True))
    wire["gameplay"]["generatedBuff"]["durationTicks"] = 0
    report = validate_runtime_wire(wire)
    assert any(error["code"] == "binding_dependency" for error in report["errors"])


@pytest.mark.parametrize("key,bad", [
    ("oreSenseRadiusTiles", "true"),
    ("jumpBoost", "1"),
    ("miningSpeedMultiplier", float("nan")),
    ("emitLightStrength", float("nan")),
    ("lifeRegen", True),
    ("lifeRegen", 1.5),
    ("lifeRegen", 10 ** 1000),
    ("miningSpeedMultiplier", 0),
    ("emitLightStrength", -0.25),
    ("jumpBoost", -1),
])
def test_malformed_buff_stat_does_not_forge_effect(key, bad):
    wire = compile_runtime_program(_author("lightStrength", 0.25, sparse=False))
    buff = wire["gameplay"]["generatedBuff"]
    buff["emitLightStrength"] = 0
    buff[key] = bad
    report = validate_runtime_wire(wire)
    assert any(error["code"] == "binding_dependency" for error in report["errors"])
