"""Author-only unit corrections preserve the exact saved runtime domain."""
import copy
import json
import runpy
from pathlib import Path

import pytest

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, compile_runtime_program, validate_runtime_program,
    validate_runtime_wire,
)
from infini_local.qa.capability_witnesses import build_capability_witness


@pytest.mark.parametrize("capability,param,wire_name", [
    ("configure_accessory", "lifeRegenHpPerSecond", "lifeRegen"),
    ("configure_armor", "lifeRegenHpPerSecond", "lifeRegen"),
    ("configure_armor", "setBonusLifeRegenHpPerSecond", "setBonusLifeRegen"),
])
def test_equipment_regen_human_units_bijectively_preserve_signed_engine_domain(capability, param, wire_name):
    spec = CAPABILITY_REGISTRY[capability].params[param]
    assert (spec.minimum, spec.maximum, spec.multiple_of) == (-50, 100, 0.5)
    # Exhaust the old integer domain, rather than sampling only positive values.
    for old in range(-100, 201):
        human = old / 2
        assert spec.to_wire(human) == old
        assert isinstance(spec.to_wire(human), int)
        assert spec.to_wire(human) / 2 == human
    for old in (-100, -1, 0, 1, 200):
        doc = build_capability_witness(capability)
        call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == capability)
        call["params"][param] = old / 2
        wire = compile_runtime_program(doc)
        prefix = "armor" if capability == "configure_armor" else "accessory"
        assert wire[prefix][wire_name] == old
        assert isinstance(wire[prefix][wire_name], int)
        assert validate_runtime_wire(wire)["ok"]
        assert any(r.get("authoredPath", "").endswith(".params." + param)
                   and r["finalPath"] == prefix + "." + wire_name and r["value"] == old
                   for r in wire["runtimeContract"]["finalWireReceipts"])
    for bad in (-50.5, 100.5, 0.25):
        broken = copy.deepcopy(doc)
        next(c for c in broken["runtimeProgram"]["calls"] if c["fn"] == capability)["params"][param] = bad
        assert not validate_runtime_program(broken)["ok"]
    old_name = param.replace("HpPerSecond", "HalfHpPerSecond")
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == capability)["params"][old_name] = 2
    assert not validate_runtime_program(doc)["ok"], "old Author name is not an alias"


def test_fractional_author_unit_keeps_integer_saved_equipment_clamps():
    root = Path(__file__).resolve().parents[2]
    render = runpy.run_path(str(root / "tools/generate_equipment_bounds.py"))["render"]
    assert render() == (root / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedEquipmentBounds.g.cs").read_text()


AUTHOR_RENAMES = (
    ("configure_spawn", "speedPxPerTick", "speedPxPerUpdate"),
    ("set_projectile_collision", "localNpcHitCooldownTicks", "localNpcHitCooldownEngineUnits"),
    ("move_gravity_arc", "gravityPerTick", "gravityVelocityPerUpdate"),
    ("move_bounce", "gravityPerTick", "gravityVelocityPerUpdate"),
    ("move_spiral", "turnRadiansPerTick", "turnRadiansPerUpdate"),
    ("move_expanding_wave", "scalePerTick", "scaleGrowthPerUpdate"),
    ("move_accelerate", "acceleration", "speedMultiplierPerUpdate"),
    ("move_sine_homing", "waveAmplitude", "waveVelocityCoefficient"),
    ("configure_item_use", "releaseTiming", "heldSpriteVisibilityHint"),
    ("configure_vanilla_ammo_item", "shootSpeedPxPerTick", "shootSpeedContributionPxPerUpdate"),
    ("restore_resources_on_use", "potionSickness", "usesPotionRules"),
    ("apply_generated_buff_on_use", "movementSpeed", "moveSpeedBonusFactor"),
    ("apply_generated_buff_on_use", "jumpBoost", "jumpSpeedBonusPxPerTick"),
    ("apply_generated_buff_on_use", "manaRegen", "manaRegenBonusPoints"),
)


def test_actual_author_packet_exposes_correct_names_without_old_aliases():
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
    _, user, _ = build_initial_author_request({}, {}, {}, {}, "unit-proof", model_name="test-model")
    cards = {c["fn"]: c for c in json.loads(user)["runtimeCapabilityContract"]["catalog"]["capabilities"]}
    for fn, old, new in AUTHOR_RENAMES:
        assert new in cards[fn]["params"], (fn, old, new)
        assert old not in cards[fn]["params"]
        spec = CAPABILITY_REGISTRY[fn].params[new]
        assert any(path.endswith("." + spec.wire_name)
                   for path in CAPABILITY_REGISTRY[fn].final_wire_paths), (fn, spec.wire_name)
        # Rename is an identity projection, including floating-point values.
        for value in (spec.minimum, spec.maximum, spec.neutral):
            if value is not None:
                assert spec.to_wire(value) == value
    assert len(cards) == 52


def test_raw_coefficients_explicitly_keep_engine_units_and_no_percent_rounding():
    raw = {
        "configure_item_stats": ("knockback",),
        "set_projectile_damage": ("knockback",),
        "configure_tool": ("miningSpeedScale",),
        "apply_generated_buff_on_use": ("miningSpeedMultiplier", "lightStrength", "moveSpeedBonusFactor", "manaRegenBonusPoints"),
        "configure_accessory": ("manaRegenBonusPoints", "aggroPoints", "lightStrength"),
        "configure_armor": ("manaRegenBonusPoints", "aggroPoints", "lightStrength", "setBonusManaRegenBonusPoints", "setBonusAggroPoints"),
        "add_hold_light": ("strength",), "emit_light_while_active": ("strength",),
        "move_slow_homing": ("homingStrength",),
        "move_sine_homing": ("homingStrength", "waveVelocityCoefficient"),
        "move_proximity_missile": ("homingStrength",),
        "move_drift": ("velocityRetention",), "move_phase": ("phaseStrength",),
        "move_vortex_orb": ("pullStrength",), "move_blackhole_pull": ("pullStrength",),
        "move_accelerate": ("speedMultiplierPerUpdate",),
        "target_and_fire": ("sameTargetBias",), "pull_on_event": ("strength",),
    }
    for fn, names in raw.items():
        for name in names:
            spec = CAPABILITY_REGISTRY[fn].params[name]
            assert "engine units" in spec.units.lower(), (fn, name, spec.units)
            assert spec.wire_divisor == spec.wire_multiplier == 1
    # This admitted binary64 value has no percent double which /100 maps back
    # exactly; do not silently round or narrow the accepted old wire domain.
    value = 1.770282212988338
    assert value * 100 / 100 != value
    spec = CAPABILITY_REGISTRY["apply_generated_buff_on_use"].params["moveSpeedBonusFactor"]
    assert spec.to_wire(value).hex() == value.hex()


def test_prompt_discloses_coupled_controls_and_nonphysical_meaning():
    from infini_local.core.runtime_authoring import compact_capability_catalog
    cards = {c["fn"]: c["params"] for c in compact_capability_catalog()}
    for fn, param, text in (
        ("charge_then_release", "powerMultiplier", "release velocity"),
        ("move_phase", "phaseStrength", "alpha"),
        ("move_player_on_use", "safeTileOnly", "ignored for recall_home"),
        ("move_owner_on_event", "safeTileOnly", "not a general hazard check"),
        ("configure_item_stats", "manaCost", "Base Item.mana"),
        ("configure_item_stats", "craftYield", "maxStack"),
        ("restore_resources_on_use", "usesPotionRules", "Quick Heal"),
        ("configure_item_use", "heldSpriteVisibilityHint", "not gameplay release timing"),
    ):
        assert text in cards[fn][param]["meaning"], (fn, param)
