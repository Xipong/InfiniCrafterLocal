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


@pytest.mark.parametrize("response_mode", ["json_object", "json_schema"])
def test_native_ammo_sampled_active_root_has_exact_frozen_repair(response_mode, monkeypatch):
    from test_repair_gameplay_contract import _offline_gameplay_repair

    doc = _weapon(speed="native_shot")
    binding = next(row for row in doc["runtimeProgram"]["bindings"]
                   if row["input"] in ("primary_use", "alternate_use")
                   and row["usePolicy"]["action"]["kind"] == "spawn_entity")
    spawn = next(row for row in doc["runtimeProgram"]["calls"]
                 if row["fn"] == "configure_spawn" and row["target"] == binding["usePolicy"]["action"]["targetId"])
    spawn["params"]["velocity"] = {"fanSpeed": {"minSpeedPxPerUpdate": 2.0, "maxSpeedPxPerUpdate": 8.0}}
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert not report["ok"]
    index = doc["runtimeProgram"]["calls"].index(spawn)
    expected_path = f"$.runtimeProgram.calls[{index}].params.velocity"
    assert [(row["path"], row["code"]) for row in report["errors"]] == [(expected_path, "incompatible_param_variant")]
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": spawn["id"], "paths": ["params.velocity"]}]
    correction = deepcopy(spawn)
    correction["params"]["velocity"] = {"constantSpeedPxPerUpdate": 8.0}
    correction["params"]["count"] = 4  # hostile valid frozen sibling
    patch = {"note": "exact root velocity replacement", "realizationReplacement": doc["realization"],
             "callsUpsert": [correction]}
    repaired, dossier = _offline_gameplay_repair(monkeypatch, doc, patch, response_mode)
    audit = repaired["debug"]["gameplayRepairFilterAudit"]
    repaired.pop("debug")
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == scope["fieldPermissions"]["calls"]
    expected = deepcopy(before)
    expected["runtimeProgram"]["calls"][index]["params"]["velocity"] = {"constantSpeedPxPerUpdate": 8.0}
    assert repaired == expected and doc == before
    assert audit["ignoredChanges"]
    assert validate_runtime_program(repaired)["ok"]
    final = compile_runtime_program(repaired)
    assert validate_runtime_wire(final)["ok"]
    assert _ammo_call(repaired)["params"]["speedBasis"] == "native_shot"


@pytest.mark.parametrize("speed,sampled,accepted", [
    ("authored_spawn", True, True),
    ("native_shot", False, True),
    ("native_shot", True, False),
])
def test_native_ammo_and_velocity_keep_one_selected_root_speed_owner(speed, sampled, accepted):
    doc = _weapon(speed=speed)
    binding = next(row for row in doc["runtimeProgram"]["bindings"]
                   if row["input"] in ("primary_use", "alternate_use")
                   and row["usePolicy"]["action"]["kind"] == "spawn_entity")
    spawn = next(row for row in doc["runtimeProgram"]["calls"]
                 if row["fn"] == "configure_spawn" and row["target"] == binding["usePolicy"]["action"]["targetId"])
    if sampled:
        spawn["params"]["velocity"] = {"fanSpeed": {"minSpeedPxPerUpdate": 2.0, "maxSpeedPxPerUpdate": 8.0}}
    assert validate_runtime_program(doc)["ok"] is accepted
    if accepted:
        final = compile_runtime_program(doc)
        assert validate_runtime_wire(final)["ok"]
        if speed == "authored_spawn":
            final.pop("runtimeContract")
            final["runtimeProgram"]["weaponAmmo"]["speedBasis"] = "native_shot"
            report = validate_runtime_wire(final)
            assert not report["ok"]
            assert any(row["code"] == "incompatible_param_variant" for row in report["errors"])


@pytest.mark.parametrize("input_name,accepted", [("hold", True), ("alternate_use", False)])
def test_native_ammo_speed_owner_checks_only_exact_active_binding_targets(input_name, accepted):
    doc = _weapon(speed="native_shot")
    active = next(row for row in doc["runtimeProgram"]["bindings"]
                  if row["input"] == "primary_use" and row["usePolicy"]["action"]["kind"] == "spawn_entity")
    root_id = active["usePolicy"]["action"]["targetId"]
    entity = deepcopy(next(row for row in doc["runtimeProgram"]["entities"] if row["id"] == root_id))
    entity["id"] = "sampled_side"
    doc["runtimeProgram"]["entities"].append(entity)
    copied = []
    for row in list(doc["runtimeProgram"]["calls"]):
        if row["target"] == root_id:
            copy = deepcopy(row)
            copy["id"] = "side_" + copy["id"]
            copy["target"] = "sampled_side"
            if copy["fn"] == "configure_spawn":
                copy["params"]["velocity"] = {"fanSpeed": {"minSpeedPxPerUpdate": 2.0, "maxSpeedPxPerUpdate": 8.0}}
            copied.append(copy)
    doc["runtimeProgram"]["calls"].extend(copied)
    binding = deepcopy(active)
    binding.update(id="side_binding", input=input_name)
    binding["usePolicy"]["action"]["targetId"] = "sampled_side"
    binding["usePolicy"].update(stackCost=0, contactDamage=False)
    doc["runtimeProgram"]["bindings"].append(binding)
    report = validate_runtime_program(doc)
    assert report["ok"] is accepted, report
    if accepted:
        assert validate_runtime_wire(compile_runtime_program(doc))["ok"]
    else:
        side_spawn = next(row for row in copied if row["fn"] == "configure_spawn")
        index = doc["runtimeProgram"]["calls"].index(side_spawn)
        assert [row["path"] for row in report["errors"]] == [f"$.runtimeProgram.calls[{index}].params.velocity"]
        scope = build_runtime_repair_scope(doc, report["errors"])
        assert scope["fieldPermissions"]["calls"] == [{"id": side_spawn["id"], "paths": ["params.velocity"]}]
