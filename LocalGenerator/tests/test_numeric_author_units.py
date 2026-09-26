"""Lossless numeric Author vocabulary and exact periodic event dependency."""
import copy
import json
from pathlib import Path

import pytest

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, build_runtime_repair_scope, capability_provider_union,
    compact_capability_catalog, compile_runtime_program, validate_runtime_program,
    validate_runtime_wire,
)
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.core.runtime_authoring.capability_registry import runtime_authoring_prompt_field_guide
from infini_local.core.runtime_authoring.program_schema import strict_author_shape_report


def _tool(value):
    doc = build_runtime_fixture("fishing_platform_tool")
    next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "configure_tool")["params"]["axePowerTooltipPercent"] = value
    return doc


def _regen(value):
    doc = build_runtime_fixture("workbench_blade")
    doc["runtimeProgram"]["bindings"].append({"id": "alternate_buff", "input": "alternate_use",
        "usePolicy": {"action": {"kind": "apply_item_effects", "targetId": "item"},
                      "stackCost": 0, "contactDamage": False}})
    doc["runtimeProgram"]["calls"].append({
        "id": "regen_effect", "fn": "apply_generated_buff_on_use", "target": "item",
        "params": {"durationTicks": 120, "miningSpeedMultiplier": 1,
                   "lightStrength": 0.1, "lightColor": "white", "oreSenseEnabled": False,
                   "movementSpeed": 0, "jumpBoost": 0, "manaRegen": 0,
                   "lifeRegenHpPerSecond": value},
    })
    return doc


@pytest.mark.parametrize("old", range(101))
def test_axe_tooltip_percent_reconstructs_every_legacy_integer(old):
    doc = _tool(old * 5)
    # Compilation validates the authored program before projecting its wire.
    wire = compile_runtime_program(doc)
    assert wire["gameplay"]["axePower"] == old
    assert isinstance(wire["gameplay"]["axePower"], int)
    assert validate_runtime_wire(wire)["ok"]
    assert any(r.get("authoredPath", "").endswith(".params.axePowerTooltipPercent")
               and r["finalPath"] == "gameplay.axePower" and r["value"] == old
               for r in wire["runtimeContract"]["finalWireReceipts"])


@pytest.mark.parametrize("old", range(121))
def test_regen_hp_per_second_reconstructs_every_legacy_integer(old):
    doc = _regen(old / 2)
    wire = compile_runtime_program(doc)
    assert wire["gameplay"]["generatedBuff"]["lifeRegen"] == old
    assert isinstance(wire["gameplay"]["generatedBuff"]["lifeRegen"], int)
    assert validate_runtime_wire(wire)["ok"]
    assert any(r.get("authoredPath", "").endswith(".params.lifeRegenHpPerSecond")
               and r["finalPath"] == "gameplay.generatedBuff.lifeRegen" and r["value"] == old
               for r in wire["runtimeContract"]["finalWireReceipts"])


@pytest.mark.parametrize("factory,bad", [(_tool, 1), (_tool, 501), (_regen, .25), (_regen, 60.5)])
def test_converted_author_bounds_and_steps_reject_invalid(factory, bad):
    doc = factory(bad)
    assert not validate_runtime_program(doc)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(doc)


def test_legacy_names_are_not_author_aliases_and_schema_keeps_steps():
    schemas = {s["properties"]["fn"]["const"]: s["properties"]["params"] for s in capability_provider_union()}
    for name, new, old, step in (("configure_tool", "axePowerTooltipPercent", "axePower", 5),
                                 ("apply_generated_buff_on_use", "lifeRegenHpPerSecond", "lifeRegen", .5)):
        params = schemas[name]
        assert new in params["properties"] and old not in params["properties"]
        assert params["properties"][new]["multipleOf"] == step
        assert new in params["required"]
        document = _tool(0) if name == "configure_tool" else _regen(0)
        target = next(c for c in document["runtimeProgram"]["calls"] if c["fn"] == name)
        target["params"][old] = target["params"].pop(new)
        assert not validate_runtime_program(document)["ok"]
    cards = {c["fn"]: c for c in compact_capability_catalog()}
    assert "axePowerTooltipPercent" in cards["configure_tool"]["params"]
    assert "lifeRegenHpPerSecond" in cards["apply_generated_buff_on_use"]["params"]


@pytest.mark.parametrize("fn", ["spawn_entity_on_event", "pull_on_event"])
def test_periodic_requires_explicit_period_ticks_and_repair_leaf(fn):
    doc = build_runtime_fixture("workbench_blade")
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "spawn_entity_on_event")
    if fn == "pull_on_event":
        call = {"id": "pull_periodic", "fn": fn, "target": call["target"], "params": {
            "event": "periodic", "mode": "target_to_entity", "strength": 1, "radiusTiles": 8,
        }}
        doc["runtimeProgram"]["calls"].append(call)
    else:
        call["params"].update(event="periodic")
    params = call["params"]
    params.pop("periodTicks", None)
    assert not strict_author_shape_report(doc)["ok"]
    report = validate_runtime_program(doc)
    assert not report["ok"]
    assert any(r["path"].endswith(".params.periodTicks") for r in report["errors"])
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params.periodTicks"]}]
    assert "periodTicks" in json.dumps(scope)
    with pytest.raises(ValueError):
        compile_runtime_program(doc)
    params["periodTicks"] = 6
    assert validate_runtime_program(doc)["ok"], validate_runtime_program(doc)["errors"]
    params["event"] = "on_hit"
    params.pop("periodTicks")
    assert validate_runtime_program(doc)["ok"], validate_runtime_program(doc)["errors"]


def test_model_cards_explain_ambiguous_engine_magnitudes_without_invented_units():
    cards = {c["fn"]: c["params"] for c in compact_capability_catalog()}
    expected = {
        "configure_item_stats": {"knockback": "Item.knockBack", "scale": "1 unchanged"},
        "configure_item_contact_hitbox": {"contactForgivenessPx": "each side"},
        "apply_generated_buff_on_use": {"movementSpeed": "Player.moveSpeed", "jumpBoost": "pixels/tick", "manaRegen": "Player.manaRegen", "miningSpeedMultiplier": "pickSpeed", "lightStrength": "RGB"},
        "configure_tool": {"pickPower": "tooltip", "hammerPower": "tooltip", "miningSpeedScale": "pickSpeed"},
        "configure_placeable": {"placeStyle": "style index"},
        "require_use_condition": {"minLife": "statLife >=", "minMana": "statMana >="},
        "add_hold_light": {"strength": "RGB"},
        "emit_light_while_active": {"strength": "RGB"},
        "configure_accessory": {"manaRegenBonusPoints": "Player.manaRegenBonus", "aggroPoints": "Player.aggro", "genericArmorPenetrationPoints": "armor", "lightStrength": "RGB"},
        "configure_armor": {"manaRegenBonusPoints": "Player.manaRegenBonus", "aggroPoints": "Player.aggro", "genericArmorPenetrationPoints": "armor", "lightStrength": "RGB"},
        "configure_spawn": {"speedPxPerTick": "extraUpdates", "count": "root binding"},
        "set_projectile_hitbox": {"drawScale": "visual scale"},
        "set_projectile_damage": {"knockback": "Projectile.knockBack"},
        "set_projectile_collision": {"extraUpdates": "per world tick", "localNpcHitCooldownTicks": "engine"},
        "move_gravity_arc": {"gravityPerTick": "per projectile update"},
        "move_bounce": {"gravityPerTick": "per projectile update"},
        "move_sine_homing": {"waveAmplitude": "0.03"},
        "move_accelerate": {"acceleration": "per projectile update"},
        "move_spiral": {"turnRadiansPerTick": "per projectile update"},
        "move_expanding_wave": {"scalePerTick": "per projectile update"},
        "target_and_fire": {"sameTargetBias": "0.9", "rangeTiles": "Soft"},
        "pull_on_event": {"strength": "velocity", "radiusTiles": "no directTarget"},
        "heal_owner_on_event": {"damageFraction": "0.15 = 15%"},
    }
    for capability, params in expected.items():
        for name, phrase in params.items():
            card = cards[capability][name]
            meaning = card.get("meaning") or cards["configure_accessory"].get(name, {}).get("meaning", "")
            assert phrase in meaning, (capability, name, card)
    guide = runtime_authoring_prompt_field_guide()["paramNotation"]
    assert "per projectile update" in guide and "extraUpdates" in guide
    for fn, name in (("configure_spawn", "speedPxPerTick"), ("move_boomerang", "returnSpeed"),
                     ("move_returning_glaive", "returnSpeed"), ("move_accelerate", "maxSpeed"),
                     ("move_flail_tether", "returnSpeed"), ("move_yoyo_hover", "returnSpeed")):
        assert cards[fn][name]["units"] == "pixels/projectile update"


def test_numeric_prompt_distinguishes_authored_damage_update_rate_and_raw_cooldown():
    cards = {c["fn"]: c for c in compact_capability_catalog()}
    for fn in ("damage_area_on_event", "chain_damage_on_event"):
        meaning = cards[fn]["params"]["damageMultiplier"]["meaning"]
        assert "item_body" in meaning and "configure_item_stats.damage" in meaning
        assert "set_projectile_damage.damage" in meaning and "damageDone" in meaning
        assert "at least 1" in meaning and "before target defense" in meaning
    drift = cards["move_drift"]
    assert "per projectile update" in drift["does"]
    assert "1 + extraUpdates" in drift["params"]["velocityRetention"]["meaning"]
    assert "10" in cards["configure_spawn"]["params"]["speedPxPerTick"]["meaning"]
    cooldown = cards["set_projectile_collision"]["params"]["localNpcHitCooldownTicks"]
    assert cooldown["min"] == -1 and cooldown["max"] == 600
    for phrase in ("unscaled", "-1", "once", "0..600", "owner", "extraUpdates"):
        assert phrase in cooldown["meaning"]
    guide = runtime_authoring_prompt_field_guide()["paramNotation"]
    assert "world ticks" in guide and "1 + extraUpdates" in guide
    assert "localNpcHitCooldownTicks" in guide


def test_numeric_prompt_keeps_distinct_factors_percentages_and_sentinels():
    cards = {c["fn"]: c["params"] for c in compact_capability_catalog()}
    guide = runtime_authoring_prompt_field_guide()["paramNotation"]
    for phrase in ("15", "0.15", "bonusPercent", "CritChancePercentagePoints",
                   "manaCostReductionPercentagePoints", "damageReductionPercentagePoints",
                   "ammoSaveChancePercent", "damageMultiplier=1", "AoE/chain floor at 1",
                   "damageFraction=0.15", "homingStrength=0.15", "pierce=-1",
                   "tileId/wallId=-1", "Default receives no Generic", "Summon crit is nonstandard"):
        assert phrase in guide
    for phrase in ("+2", "+1 HP/s", "-2", "-1 HP/s"):
        assert phrase in cards["configure_accessory"]["lifeRegenHalfHpPerSecond"]["meaning"]
    assert "not mana/s" in cards["configure_accessory"]["manaRegenBonusPoints"]["meaning"]
    assert "independent" in cards["configure_item_stats"]["useAnimationTicks"]["meaning"]
    assert "interval" in cards["configure_item_stats"]["useTimeTicks"]["meaning"]
    assert "1 unchanged" in cards["set_projectile_hitbox"]["hitboxScale"]["meaning"]
    assert "1 unchanged" in cards["move_accelerate"]["acceleration"]["meaning"]
    assert "1 unchanged" in cards["charge_then_release"]["powerMultiplier"]["meaning"]


def test_periodic_missing_fields_are_reported_once_by_canonical_shape():
    from infini_local.core.runtime_authoring.program_schema import strict_schema_errors

    cap = CAPABILITY_REGISTRY["spawn_entity_on_event"]
    schema = cap.provider_variant_schema()["properties"]["params"]
    assert schema["then"]["required"] == ["periodTicks"]
    doc = build_runtime_fixture("workbench_blade")
    params = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == cap.name)["params"]
    params["event"] = "periodic"
    params.pop("periodTicks", None)
    params.pop("count")
    errors = strict_schema_errors(params, schema)
    paths = [row["path"] for row in errors if row["kind"] == "required"]
    assert paths.count("$.count") == 1
    assert paths.count("$.periodTicks") == 1


def test_all_numeric_prompt_cards_reconstruct_meaning_bounds_units_and_dependencies():
    cards = {c["fn"]: c for c in compact_capability_catalog()}
    assert set(cards) == set(CAPABILITY_REGISTRY)
    guide = runtime_authoring_prompt_field_guide()
    assert "configure_accessory" in guide["armorParamInheritance"]
    assert "Matching armor set" in guide["setBonusParamPrefix"]
    for fn, cap in CAPABILITY_REGISTRY.items():
        card = cards[fn]
        assert set(card["params"]) == set(cap.params)
        assert card.get("requires", []) == [r.card() for r in cap.requirements]
        for name, spec in cap.params.items():
            if spec.kind not in ("integer", "number"):
                continue
            row = card["params"][name]
            meaning = row.get("meaning", "")
            if fn == "configure_armor" and name.startswith("setBonus"):
                meaning = guide["setBonusParamPrefix"] + meaning
            elif fn == "configure_armor" and not meaning:
                meaning = cards["configure_accessory"]["params"][name]["meaning"]
            assert meaning == spec.description, (fn, name)
            assert row["type"] == spec.kind
            assert row.get("min") == spec.minimum and row.get("max") == spec.maximum
            assert row.get("multipleOf") == spec.multiple_of
            assert row.get("optional", False) == (not spec.required)
            if "units" not in row:
                assert any(name.endswith(suffix) and spec.units == unit
                           for suffix, unit in (("Ticks", "ticks"), ("Tiles", "tiles"),
                                                ("Px", "pixels"), ("Radians", "radians"))) or not spec.units
            else:
                assert row["units"] == spec.units
