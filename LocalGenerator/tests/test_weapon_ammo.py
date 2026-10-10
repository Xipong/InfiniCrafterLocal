"""Weapon ammo is an explicit native consumer, independent of generated ammo stacks."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, apply_repair_patch, build_runtime_repair_scope,
    compile_runtime_program, filter_repair_patch_scope, validate_runtime_program,
    validate_runtime_wire,
)
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.qa import primitive_loss_audit


def _weapon(category="arrow", speed="authored_spawn"):
    doc = build_capability_witness("configure_weapon_ammo")
    _ammo_call(doc)["params"].update(ammoCategory=category, speedBasis=speed)
    return doc


def _ammo_call(doc):
    return next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "configure_weapon_ammo")


@pytest.mark.parametrize("category", CAPABILITY_REGISTRY["configure_weapon_ammo"].params["ammoCategory"].enum)
@pytest.mark.parametrize("speed", ["authored_spawn", "native_shot"])
def test_each_exact_native_category_and_real_speed_choice_survives_vertical_slice(category, speed):
    doc = _weapon(category, speed)
    before = deepcopy(doc)
    assert validate_runtime_program(doc)["ok"]
    final = compile_runtime_program(doc)
    assert validate_runtime_wire(final)["ok"]
    assert doc == before
    assert final["runtimeProgram"]["weaponAmmo"] == {"ammoCategory": category, "speedBasis": speed}
    assert not final["gameplay"].get("ammoCategory")
    assert len(final["runtimeProgram"]["entities"]) == len(doc["runtimeProgram"]["entities"])
    rows = final["runtimeContract"]["finalWireReceipts"]
    selected = [row for row in rows if row.get("fn") == "configure_weapon_ammo"]
    assert len(selected) == 3
    assert next(row for row in selected if row["finalPath"] == "runtimeProgram.weaponAmmo")["authoredPath"].endswith(".fn")
    assert audit_compiler_receipts(rows, authored_document=doc, final_document=final)["ok"]


@pytest.mark.parametrize("field,value", [
    ("ammoCategory", "arrows"), ("ammoCategory", "bow"), ("ammoCategory", "sand"),
    ("ammoCategory", ""), ("ammoCategory", None), ("ammoCategory", 1),
    ("speedBasis", "native"), ("speedBasis", ""), ("speedBasis", None),
    ("speedBasis", True), ("speedBasis", {}),
])
def test_invalid_presence_is_rejected_without_guessing_ammo_or_speed(field, value):
    doc = _weapon()
    _ammo_call(doc)["params"][field] = value
    assert not validate_runtime_program(doc)["ok"]
    final = compile_runtime_program(_weapon())
    final.pop("runtimeContract")
    final["runtimeProgram"]["weaponAmmo"][field] = value
    assert not validate_runtime_wire(final)["ok"]


@pytest.mark.parametrize("missing", ["ammoCategory", "speedBasis"])
def test_choices_are_required_and_never_backend_defaults(missing):
    doc = _weapon()
    del _ammo_call(doc)["params"][missing]
    assert not validate_runtime_program(doc)["ok"]
    final = compile_runtime_program(_weapon())
    final.pop("runtimeContract")
    del final["runtimeProgram"]["weaponAmmo"][missing]
    assert not validate_runtime_wire(final)["ok"]


def test_existing_projectile_and_ammo_items_do_not_become_ammo_consumers():
    for fn in ("move_straight", "configure_vanilla_ammo_item", "restore_resources_on_use"):
        final = compile_runtime_program(build_capability_witness(fn))
        assert "weaponAmmo" not in final["runtimeProgram"]
        assert not any(row.get("fn") == "configure_weapon_ammo" for row in final["runtimeContract"]["finalWireReceipts"])


@pytest.mark.parametrize("invalid_input", [[], {}, ["primary_use"]])
def test_malformed_binding_input_is_a_structured_refusal_not_an_exception(invalid_input):
    final = compile_runtime_program(_weapon())
    final.pop("runtimeContract")
    final["runtimeProgram"]["bindings"][0]["input"] = invalid_input
    report = validate_runtime_wire(final)
    assert not report["ok"]
    assert any(row["code"] == "missing_weapon_ammo_consumer" for row in report["errors"])


def test_legacy_complete_wire_changes_only_declared_audit_and_alias_deltas():
    from tests.captured_projectile_author import without_captured_projectile_alias_delta
    from sentry_contract_checks import without_declared_targeting_neutrals

    # Keep frozen base627 hashes; reverse only the proven test-local alias
    # projection and two native-ammo inventory diagnostics. No omitted field
    # is materialized, and every other gameplay/provenance byte stays pinned.
    baseline = json.loads((Path(__file__).parent / "fixtures/weapon_ammo_legacy_wire_sha256.json").read_text())
    from sentry_contract_checks import without_declared_targeting_neutrals
    from beam_contract_checks import without_declared_beam_neutrals
    from captured_parent_combat_author import historical_child_combat_wire
    from captured_item_alias_wire import historical_item_alias_wire

    for name, expected_hash in baseline.items():
        final = without_declared_targeting_neutrals(without_declared_beam_neutrals(
            without_captured_projectile_alias_delta(historical_child_combat_wire(compile_runtime_program(build_runtime_fixture(name))))))
        checks = final["runtimeContract"]["validation"]["stats"]["registryDrivenChecks"]
        assert checks["exclusiveGroups"] == ["ammo_role", "controller", "movement"]
        added_modifier_caps = (
            "set_projectile_hitbox_curve", "set_projectile_turn_modifier", "set_projectile_speed_modifier",
            "set_projectile_homing_modifier", "set_projectile_visual_scale_curve", "orient_whip_to_owner_gravity",
        )
        assert checks["requirements"] == 29 + sum(len(CAPABILITY_REGISTRY[fn].requirements) for fn in added_modifier_caps)
        checks["exclusiveGroups"] = ["controller", "movement"]
        checks["requirements"] = 28
        actual = hashlib.sha256(json.dumps(final, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        assert actual == expected_hash, name


def test_ammo_stack_and_weapon_consumer_are_an_explicit_unsupported_composition():
    doc = _weapon()
    ammo = next(row for row in build_capability_witness("configure_vanilla_ammo_item")["runtimeProgram"]["calls"]
                if row["fn"] == "configure_vanilla_ammo_item")
    ammo["id"] = "ammo_stack"
    doc["runtimeProgram"]["calls"].append(ammo)
    report = validate_runtime_program(doc)
    assert any(row["code"] == "exclusive_component_conflict" for row in report["errors"])
    final = compile_runtime_program(_weapon())
    final.pop("runtimeContract")
    final["gameplay"].update(ammoCategory="arrow", ammoProjectileId=1, ammoShootSpeedPxPerTick=1, notAmmo=False)
    assert any(row["code"] == "ammo_role_conflict" for row in validate_runtime_wire(final)["errors"])


def test_hold_only_spawner_is_not_a_native_ammo_consumer_and_repair_uses_existing_entity():
    doc = _weapon()
    doc["runtimeProgram"]["bindings"][0]["input"] = "hold"
    report = validate_runtime_program(doc)
    assert any(row["code"] == "missing_binding_dependency" for row in report["errors"])
    scope = build_runtime_repair_scope(doc, report["errors"])
    choices = scope["create"]["bindings"]["allowedTransactions"]
    assert choices and all(row["input"] in ("primary_use", "alternate_use")
                           and row["usePolicy"]["action"]["kind"] == "spawn_entity" for row in choices)
    candidate = {"id": "active_ammo_use", **deepcopy(choices[0])}
    filtered, audit = filter_repair_patch_scope(doc, {"note": "Attach explicit active consumer", "bindingsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(doc, filtered)
    assert validate_runtime_program(repaired)["ok"]
    assert repaired["runtimeProgram"]["calls"] == doc["runtimeProgram"]["calls"]
    assert repaired["runtimeProgram"]["entities"] == doc["runtimeProgram"]["entities"]


def test_ammo_reference_repair_cannot_change_valid_speed_or_projectile_design():
    doc = _weapon()
    call = _ammo_call(doc)
    call["params"]["ammoCategory"] = "invalid"
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params.ammoCategory"]}]
    candidate = deepcopy(call)
    candidate["params"].update(ammoCategory="bullet", speedBasis="native_shot")
    filtered, audit = filter_repair_patch_scope(doc, {"note": "Correct category only", "callsUpsert": [candidate]}, scope)
    assert audit["ok"]
    repaired = apply_repair_patch(doc, filtered)
    assert _ammo_call(repaired)["params"] == {"ammoCategory": "bullet", "speedBasis": "authored_spawn"}
    assert validate_runtime_program(repaired)["ok"]


@pytest.mark.parametrize("mutation", ["drop_semantics", "drop_choice", "wrong_source", "duplicate_semantics", "unknown_field", "null_component"])
def test_wire_and_receipts_require_exact_native_ammo_capability_selection(mutation):
    doc = _weapon()
    final = compile_runtime_program(doc)
    rows = final["runtimeContract"]["finalWireReceipts"]
    selection = next(row for row in rows if row.get("finalPath") == "runtimeProgram.weaponAmmo")
    if mutation == "drop_semantics":
        rows.remove(selection)
    elif mutation == "drop_choice":
        rows[:] = [row for row in rows if row.get("finalPath") != "runtimeProgram.weaponAmmo.speedBasis"]
    elif mutation == "wrong_source":
        selection["authoredPath"] = "runtimeProgram.calls[0].fn"
    elif mutation == "duplicate_semantics":
        rows.append(deepcopy(selection))
    elif mutation == "unknown_field":
        final["runtimeProgram"]["weaponAmmo"]["projectilePolicy"] = "native_ammo"
    else:
        final["runtimeProgram"]["weaponAmmo"] = None
    assert not validate_runtime_wire(final)["ok"]
    assert not audit_compiler_receipts(rows, authored_document=doc, final_document=final)["ok"]


def test_new_ammo_dto_cannot_silently_gain_a_weapon_family_field():
    source = (primitive_loss_audit._MODEL_ROOT / "Common/Models/RuntimeWeaponAmmoSpec.cs").read_bytes()
    assert primitive_loss_audit.weapon_ammo_surface_audit(source)["ok"]
    anchor = b'public string AmmoCategory { get; set; } = "";'
    assert anchor in source
    mutated = source.replace(anchor, b'public string WeaponFamily { get; set; } = "";\n' + anchor)
    assert primitive_loss_audit.weapon_ammo_surface_audit(mutated)["unclassifiedDtoFields"] == ["WeaponFamily"]
