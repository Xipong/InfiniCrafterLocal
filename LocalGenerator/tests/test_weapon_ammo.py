"""Weapon ammo is an explicit native consumer, independent of generated ammo stacks."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from repair_test_helpers import DELETE, edit_fields, frozen_call_repair, frozen_gameplay_repair


def _weapon(category="arrow", speed="authored_spawn"):
    doc = build_capability_witness("weapon_ammo")
    _ammo_call(doc)["params"].update(ammoCategory=category, speedBasis=speed)
    return doc


def _ammo_call(doc):
    return next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "weapon_ammo")


@pytest.mark.parametrize("category", [
    "arrow", "bullet", "candy_corn", "coin", "dart", "fallen_star", "flare", "gel",
    "jack_o_lantern", "nail_friendly", "rocket", "snowball", "solution", "stake", "stynger_bolt",
])
@pytest.mark.parametrize("speed", ["authored_spawn", "native_shot"])
def test_each_exact_native_category_and_real_speed_choice_survives_vertical_slice(category, speed):
    doc = _weapon(category, speed)
    before = deepcopy(doc)
    final = compile_runtime_program(doc)
    assert validate_runtime_wire(final)["ok"]
    assert doc == before
    assert final["runtimeProgram"]["weaponAmmo"] == {"ammoCategory": category, "speedBasis": speed}
    assert not final["gameplay"].get("ammoCategory")
    assert len(final["runtimeProgram"]["entities"]) == len(doc["runtimeProgram"]["entities"])
    rows = final["runtimeContract"]["finalWireReceipts"]
    selected = [row for row in rows if row.get("fn") == "weapon_ammo"]
    assert len(selected) == 3
    assert next(row for row in selected if row["finalPath"] == "runtimeProgram.weaponAmmo")["authoredPath"].endswith(".fn")


@pytest.mark.parametrize("field,value", [
    pytest.param(field, value, id=f"{field}-{kind}")
    for field, kind, value in (
        ("ammoCategory", "plural", "arrows"), ("ammoCategory", "family", "bow"),
        ("ammoCategory", "unsupported", "sand"), ("ammoCategory", "empty", ""),
        ("ammoCategory", "null", None), ("ammoCategory", "integer", 1),
        ("speedBasis", "alias", "native"), ("speedBasis", "empty", ""),
        ("speedBasis", "null", None), ("speedBasis", "boolean", True),
        ("speedBasis", "object", {}),
        ("ammoCategory", "missing", DELETE), ("speedBasis", "missing", DELETE),
    )
])
def test_invalid_presence_is_rejected_without_guessing_ammo_or_speed(field, value):
    doc = _weapon()
    final = compile_runtime_program(doc)
    final.pop("runtimeContract")
    edit_fields(_ammo_call(doc)["params"], {field: value})
    edit_fields(final["runtimeProgram"]["weaponAmmo"], {field: value})
    for source, validator, suffix in (
        (doc, validate_runtime_program, ".params." + field),
        (final, validate_runtime_wire, ".weaponAmmo." + field),
    ):
        report = validator(source)
        assert not report["ok"]
        assert any(row["path"].endswith(suffix) for row in report["errors"]), report


@pytest.mark.parametrize("fn", ["move_straight", "ammo_item", "restore_resources_on_use"])
def test_existing_projectile_and_ammo_items_do_not_become_ammo_consumers(fn):
    final = compile_runtime_program(build_capability_witness(fn))
    assert "weaponAmmo" not in final["runtimeProgram"]
    assert not any(row.get("fn") == "weapon_ammo" for row in final["runtimeContract"]["finalWireReceipts"])


@pytest.mark.parametrize("invalid_input", [[], {}, ["primary_use"]])
def test_malformed_binding_input_is_a_structured_refusal_not_an_exception(invalid_input):
    final = compile_runtime_program(_weapon())
    final.pop("runtimeContract")
    final["runtimeProgram"]["bindings"][0]["input"] = invalid_input
    report = validate_runtime_wire(final)
    assert not report["ok"]
    assert any(row["code"] == "missing_weapon_ammo_consumer" for row in report["errors"])


def test_current_fixture_compositions_compile_and_deliver_without_implicit_weapon_ammo():
    # Frozen archive selects the retained corpus, not an obsolete metadata hash
    # contract. Retired compatibility receipts must not be restored for byte parity.
    baseline = json.loads((Path(__file__).parent / "fixtures/weapon_ammo_legacy_wire_sha256.json").read_text())
    for name in baseline:
        authored = build_runtime_fixture(name)
        before = deepcopy(authored)
        compiled = compile_runtime_program(authored)
        assert validate_runtime_wire(compiled)["ok"], name
        assert audit_compiler_receipts(compiled["runtimeContract"]["finalWireReceipts"],
                                       authored_document=authored, final_document=compiled)["ok"], name
        assert authored == before, name
        assert "weaponAmmo" not in compiled["runtimeProgram"], name
        delivered = deepcopy(compiled)
        delivered.pop("runtimeContract")
        assert validate_runtime_wire(delivered)["ok"], name


def test_ammo_stack_and_weapon_consumer_are_an_explicit_unsupported_composition():
    doc = _weapon()
    ammo = next(row for row in build_capability_witness("ammo_item")["runtimeProgram"]["calls"]
                if row["fn"] == "ammo_item")
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
    binding = doc["runtimeProgram"]["bindings"][0]
    doc["runtimeProgram"]["bindings"][0] = {"id": binding["id"], "input": "hold", "action": {"targetId": binding["action"]["targetId"]}}
    report = validate_runtime_program(doc)
    assert any(row["code"] == "missing_binding_dependency" for row in report["errors"])
    scope = build_runtime_repair_scope(doc, report["errors"])
    choices = scope["create"]["bindings"]["allowedTransactions"]
    assert choices and all(row["input"] in ("primary_use", "alternate_use")
                           and row["action"]["kind"] == "spawn_entity" for row in choices)
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
    expected = deepcopy(doc)
    _ammo_call(expected)["params"]["ammoCategory"] = "bullet"
    candidate = deepcopy(call)
    candidate["params"].update(ammoCategory="bullet", speedBasis="native_shot")
    repaired, final = frozen_call_repair(doc, [candidate],
        [{"id": call["id"], "paths": ["params.ammoCategory"]}], expected,
        note="Correct category only")
    assert final["runtimeProgram"]["weaponAmmo"] == {"ammoCategory": "bullet", "speedBasis": "authored_spawn"}


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




@pytest.mark.parametrize("response_mode", ["json_object", "json_schema"])
def test_native_ammo_sampled_active_root_has_exact_frozen_repair(response_mode, monkeypatch):
    doc = _weapon(speed="native_shot")
    binding = next(row for row in doc["runtimeProgram"]["bindings"]
                   if row["input"] in ("primary_use", "alternate_use")
                   and row["action"]["kind"] == "spawn_entity")
    spawn = next(row for row in doc["runtimeProgram"]["calls"]
                 if row["fn"] == "spawn" and row["target"] == binding["action"]["targetId"])
    spawn["params"]["velocity"] = {"fanSpeed": {'minSpeed': (2.0) * 60 / 16, 'maxSpeed': (8.0) * 60 / 16}}
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert not report["ok"]
    index = doc["runtimeProgram"]["calls"].index(spawn)
    expected_path = f"$.runtimeProgram.calls[{index}].params.velocity"
    assert [(row["path"], row["code"]) for row in report["errors"]] == [(expected_path, "incompatible_param_variant")]
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": spawn["id"], "paths": ["params.velocity"]}]
    correction = deepcopy(spawn)
    correction["params"]["velocity"] = {'speed': (8.0) * 60 / 16}
    correction["params"]["count"] = 4  # hostile valid frozen sibling
    patch = {"note": "exact root velocity replacement", "realizationReplacement": doc["realization"],
             "callsUpsert": [correction]}
    expected = deepcopy(before)
    expected["runtimeProgram"]["calls"][index]["params"]["velocity"] = {'speed': (8.0) * 60 / 16}
    repaired, dossier, final = frozen_gameplay_repair(monkeypatch, doc, patch, response_mode,
        {"calls": scope["fieldPermissions"]["calls"]}, expected)
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
                   and row["action"]["kind"] == "spawn_entity")
    spawn = next(row for row in doc["runtimeProgram"]["calls"]
                 if row["fn"] == "spawn" and row["target"] == binding["action"]["targetId"])
    if sampled:
        spawn["params"]["velocity"] = {"fanSpeed": {'minSpeed': (2.0) * 60 / 16, 'maxSpeed': (8.0) * 60 / 16}}
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
                  if row["input"] == "primary_use" and row["action"]["kind"] == "spawn_entity")
    root_id = active["action"]["targetId"]
    entity = deepcopy(next(row for row in doc["runtimeProgram"]["entities"] if row["id"] == root_id))
    entity["id"] = "sampled_side"
    doc["runtimeProgram"]["entities"].append(entity)
    copied = []
    for row in list(doc["runtimeProgram"]["calls"]):
        if row.get("target") == root_id:
            copy = deepcopy(row)
            copy["id"] = "side_" + copy["id"]
            copy["target"] = "sampled_side"
            if copy["fn"] == "spawn":
                copy["params"]["velocity"] = {"fanSpeed": {'minSpeed': (2.0) * 60 / 16, 'maxSpeed': (8.0) * 60 / 16}}
            copied.append(copy)
    doc["runtimeProgram"]["calls"].extend(copied)
    binding = deepcopy(active)
    binding.update(id="side_binding", input=input_name)
    binding["action"]["targetId"] = "sampled_side"
    if input_name == "hold":
        binding["action"].pop("kind")
        binding.pop("stackCost")
        binding.pop("contactDamage")
    else:
        binding.update(stackCost=0, contactDamage=False)
    doc["runtimeProgram"]["bindings"].append(binding)
    report = validate_runtime_program(doc)
    assert report["ok"] is accepted, report
    if accepted:
        assert validate_runtime_wire(compile_runtime_program(doc))["ok"]
    else:
        side_spawn = next(row for row in copied if row["fn"] == "spawn")
        index = doc["runtimeProgram"]["calls"].index(side_spawn)
        assert [row["path"] for row in report["errors"]] == [f"$.runtimeProgram.calls[{index}].params.velocity"]
        scope = build_runtime_repair_scope(doc, report["errors"])
        assert scope["fieldPermissions"]["calls"] == [{"id": side_spawn["id"], "paths": ["params.velocity"]}]


@pytest.mark.parametrize("basis", ["native_shot", "authored_spawn"])
@pytest.mark.parametrize("delay", [1, 600])
def test_weapon_ammo_constant_speed_and_activation_delay_are_an_accepted_composition(basis, delay):
    doc = _weapon(speed=basis)
    spawn = next(call for call in doc["runtimeProgram"]["calls"] if call["fn"] == "spawn")
    spawn["params"]["position"] = {"above": "activation_origin", "heightTiles": 2, 'activationDelay': (delay) / 60}
    before = deepcopy(doc)
    final = compile_runtime_program(doc)
    assert validate_runtime_wire(final)["ok"]
    entity = next(row for row in final["runtimeProgram"]["entities"] if row["id"] == spawn["target"])
    assert entity["spawn"]["overTarget"]["delayTicks"] == delay
    assert entity["spawn"]["speedPxPerTick"] == 8.0
    assert final["runtimeProgram"]["weaponAmmo"]["speedBasis"] == basis
    assert doc == before
