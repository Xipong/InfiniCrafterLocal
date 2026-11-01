"""Canonical gameplay names keep old wire and provenance readable, not Author aliases."""
from collections import Counter
from copy import deepcopy
import gzip
import json
from pathlib import Path

import pytest

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY, capability_for_saved_receipt
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire

_CAPTURE = json.loads(gzip.decompress((Path(__file__).parent / "fixtures" / "gameplay_vocabulary_wire_baseline.json.gz").read_bytes()))
# Public capability cohort at the documented df29f582 capture boundary. New
# operations have no pre-migration wire and must not be backfilled into it.
_MIGRATION_CAPABILITIES = frozenset("""
accelerate_projectile_vertical accumulate_projectile_charge add_equipment_damage_bonus
add_hold_light add_placed_light add_projectile_visual_scale apply_generated_buff_on_event
apply_generated_buff_on_use apply_npc_effect_on_event apply_status_on_event apply_vanilla_buff_on_use
attach_projectile attract_npcs_while_active collect_seeds_from_grass configure_accessory configure_armor
configure_item_contact_hitbox configure_item_stats configure_item_use configure_spawn configure_tile_placement
configure_tool configure_vanilla_ammo_item configure_wall_placement configure_weapon_ammo damage_nearby_on_event
emit_light_while_active enable_placed_vfx gate_projectile_contact heal_owner_on_event move_owner_on_event
move_player_on_use move_straight orbit_projectile oscillate_projectile_velocity present_placed_item_sprite
pull_on_event recall_home_on_use refresh_generated_effect_group_while_held require_use_condition
restore_resources_on_use scale_projectile_velocity seek_projectile select_targets_and_emit_on_event
set_descendant_concurrency set_front_arm_pose set_projectile_aim set_projectile_arrival set_projectile_beam_geometry
set_projectile_collision set_projectile_concurrency set_projectile_damage set_projectile_hitbox set_projectile_hitbox_curve
set_projectile_homing_modifier set_projectile_lash_geometry set_projectile_lifetime set_projectile_opacity
set_projectile_owner_control set_projectile_proximity_action set_projectile_return_trigger set_projectile_rotation
set_projectile_sentry set_projectile_turn_modifier set_projectile_visual_scale_curve spawn_entity_from_hit_target
spawn_entity_on_event sustain_projectile_mana target_and_fire
""".split())


def executable_wire(document):
    result = deepcopy(document)
    result.pop("runtimeContract")  # Source names change; executable DTO does not.
    return result


@pytest.mark.parametrize("case", _CAPTURE["cases"], ids=lambda row: row["previousFn"])
def test_canonical_choices_preserve_prechange_execution_and_old_wire_still_loads(case):
    before = deepcopy(case)
    source = case["author"]
    assert validate_runtime_program(source)["ok"]
    wire = compile_runtime_program(source)
    actual = executable_wire(wire)
    expected = executable_wire(case["wire"])
    if case["previousFn"] == "set_projectile_beam_geometry":
        # New fresh compilation declares one neutral origin leaf. Keep the
        # frozen old capture byte-for-byte; compare every retained field exactly.
        call = next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "beam_geometry")
        assert "startOffsetBlocks" not in call["params"]
        fresh = next(row for row in actual["runtimeProgram"]["entities"] if row["id"] == call["target"])
        old = next(row for row in expected["runtimeProgram"]["entities"] if row["id"] == call["target"])
        assert "startOffsetPx" not in old["beamGeometry"]
        neutral = fresh["beamGeometry"].pop("startOffsetPx")
        assert type(neutral) in (int, float) and neutral == 0
    assert actual == expected
    assert validate_runtime_wire(wire)["ok"]
    assert validate_runtime_wire(case["wire"])["ok"]
    assert audit_compiler_receipts(case["wire"]["runtimeContract"]["finalWireReceipts"], final_document=case["wire"])["ok"]
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=source, final_document=wire)["ok"]
    assert case == before


def test_capture_preserves_migration_cohort_and_old_identity_is_not_an_author_alias():
    assert Counter(row["previousFn"] for row in _CAPTURE["cases"]) == Counter(_MIGRATION_CAPABILITIES)
    for row in _CAPTURE["cases"]:
        cap = capability_for_saved_receipt(row["previousFn"])
        assert cap is not None and cap.author_visible
        if cap.name == row["previousFn"]:
            continue
        source = deepcopy(row["author"])
        call = next(call for call in source["runtimeProgram"]["calls"] if call["fn"] == cap.name)
        call["fn"] = row["previousFn"]
        assert not validate_runtime_program(source)["ok"]
        assert row["previousFn"] not in CAPABILITY_REGISTRY


@pytest.mark.parametrize("value", [0, 1, 128, 255])
def test_transparency_byte_is_exact_existing_native_domain(value):
    case = next(row for row in _CAPTURE["cases"] if row["previousFn"] == "set_projectile_opacity")
    source = deepcopy(case["author"])
    call = next(call for call in source["runtimeProgram"]["calls"] if call["fn"] == "set_opacity")
    call["params"]["transparencyByte"] = value
    wire = compile_runtime_program(source)
    entity = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == call["target"])
    assert entity["opacity"]["alpha"] == value
    call["params"]["alpha"] = call["params"].pop("transparencyByte")
    assert not validate_runtime_program(source)["ok"]


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("previous_fn", ["apply_generated_buff_on_use", "spawn_entity_on_event", "seek_projectile"])
def test_saved_generated_parent_keeps_old_wire_in_next_craft_with_current_unit_guide(monkeypatch, mode, previous_fn):
    from infini_local.core import llm_config
    from infini_local.pipelines.author.request import build_initial_author_request
    from prompt_packet_helpers import request_dossier
    case = next(row for row in _CAPTURE["cases"] if row["previousFn"] == previous_fn)
    parent = {"name": "accepted saved craft", "generatedData": deepcopy(case["wire"])}
    before = deepcopy(parent)
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    request, _, _ = build_initial_author_request(parent, parent, "old-wire-next-craft", model_name="offline")
    packet = request_dossier(request)
    for side in ("A", "B"):
        source = packet["parents"][side]["packet"]["raw"]["generatedParent"]
        assert source["gameplay"] == case["wire"]["gameplay"]
        expected = deepcopy(case["wire"]["runtimeProgram"])
        for entity in expected["entities"]:
            entity.pop("visual", None)
        assert source["runtimeProgram"] == expected
    assert request["response_format"]["type"] == mode
    assert packet["runtimeCapabilityContract"]["catalog"]["authoringSchema"] == "infini.runtime-program.authoring.v7"
    assert parent == before


@pytest.mark.parametrize("case", _CAPTURE["combatCases"], ids=lambda row: row["activation"])
def test_equipment_aligned_combat_names_keep_scoped_wire_and_old_receipts(case):
    before = deepcopy(case)
    source = case["author"]
    assert validate_runtime_program(source)["ok"]
    wire = compile_runtime_program(source)
    assert executable_wire(wire) == executable_wire(case["wire"])
    assert validate_runtime_wire(case["wire"])["ok"]
    assert audit_compiler_receipts(case["wire"]["runtimeContract"]["finalWireReceipts"], final_document=case["wire"])["ok"]
    assert not validate_runtime_program(case["previousAuthor"])["ok"]
    assert not audit_compiler_receipts(case["wire"]["runtimeContract"]["finalWireReceipts"], authored_document=source, final_document=case["wire"])["ok"]
    assert case == before


def test_common_combat_names_have_explicit_units_without_changing_numeric_projection():
    cap = CAPABILITY_REGISTRY["generated_buff_on_use"]
    card = cap.author_prompt_card()["params"]["combat"]["properties"]
    for key, units, old in (("attackSpeedBonus", "additive_percent", "attackSpeedPercent"),
                            ("critChance", "percentage_points", "critChancePoints"),
                            ("damageBonus", "additive_percent", "damagePercent")):
        spec = cap.params["combat"].properties[key]
        assert card[key]["units"] == units
        assert spec.wire_name == "combat." + old
        for value in (spec.minimum, 0, spec.maximum):
            assert spec.to_wire(value) == value
        assert old not in card
