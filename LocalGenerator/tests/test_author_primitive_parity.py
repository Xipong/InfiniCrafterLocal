"""Author primitives must retain exact source identity through final-wire lowering."""

from __future__ import annotations

from copy import deepcopy
import json
import pytest
from pathlib import Path

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request

def test_every_ordinary_authored_param_has_one_named_exact_wire_projection() -> None:
    # The class-damage selector is intentionally a three-parameter dynamic projection.
    for fn, cap in CAPABILITY_REGISTRY.items():
        if fn == "add_equipment_damage_bonus":
            continue
        for name, spec in cap.params.items():
            assert any(
                path.rsplit(".", 1)[-1] in {name, spec.wire_name}
                for path in cap.final_wire_paths
            ), f"{fn}.{name} has no declared one-to-one wire mapping"


@pytest.mark.parametrize("fn", ["configure_item_stats", "set_projectile_damage"])
def test_vanilla_item_fullname_is_not_a_registered_damage_class(fn: str) -> None:
    authored = build_runtime_fixture("workbench_blade")
    call = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == fn)
    assert validate_runtime_program(authored)["ok"]
    call["params"]["damageClass"] = "Terraria/ThornWhip"
    report = validate_runtime_program(authored)
    assert not report["ok"]
    assert any("damageClass" in row["path"] for row in report["errors"])

    # A registered mod's exact FullName shape remains representable; runtime
    # registration is checked by tML, not guessed from the token's spelling.
    call["params"]["damageClass"] = "ExampleMod/CustomDamage"
    assert validate_runtime_program(authored)["ok"]

def test_initial_author_request_separates_item_identity_from_damage_class() -> None:
    _, user_text, _ = build_initial_author_request(
        {"name": "Thorn Whip", "fullName": "Terraria/ThornWhip"},
        {"name": "Jungle Spores"}, {"name": "Thorn Whip"}, {"name": "Jungle Spores"},
        "whip+jungle", model_name="test-model",
    )
    catalog = json.loads(user_text)["runtimeCapabilityContract"]["catalog"]
    for fn in ("configure_item_stats", "set_projectile_damage"):
        meaning = next(row for row in catalog["capabilities"] if row["fn"] == fn)["params"]["damageClass"]["meaning"]
        assert "DamageClass.FullName" in meaning
        assert "not item FullName" in meaning


def test_generated_parity_table_shows_set_key_pattern_not_boolean_range() -> None:
    text = (Path(__file__).resolve().parents[2] / "docs/PRIMITIVE_PARITY_RU.md").read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| setKey |"))
    assert r"^[a-z0-9_]{0,48}$" in row
    assert "| bounded_text |  |" in row
    assert "| bool |" not in row


def test_initial_author_wire_explains_actual_stack_consumption() -> None:
    request, user_text, _ = build_initial_author_request(
        {"name": "Boomerang"}, {"name": "Hellstone Bar"},
        {"name": "Boomerang"}, {"name": "Hellstone Bar"}, "boomerang+hellstone", model_name="test-model",
    )
    system_text = str(request["messages"][0]["content"])
    guide = json.loads(user_text)["runtimeCapabilityContract"]["catalog"]["fieldGuide"]
    assert "place_item requires stackCost=1" in system_text
    assert "place_item requires stackCost=1" in guide["stackCost"]
    assert "projectile return does not refund" in guide["stackCost"]
    assert "stackCost=0" in guide["stackCost"]
    assert "remains in inventory for another activation" in guide["stackCost"]
    assert "not a projectile or separate ammo" in system_text
    assert "apply_item_effects is the only active binding" in system_text
    assert "item_body.on_use" in system_text
    assert "double-quoted JSON object keys" in system_text


def test_initial_author_wire_explains_exact_copper_and_percent_units() -> None:
    request, _, _ = build_initial_author_request(
        {"name": "Hermes Boots"}, {"name": "Aglet"},
        {"name": "Hermes Boots"}, {"name": "Aglet"}, "boots+aglet", model_name="test-model",
    )
    system_text = str(request["messages"][0]["content"])
    assert "valueCopper" in system_text and "never use params.value" in system_text
    assert "+15%" in system_text and "enter 15" in system_text and "not 0.15" in system_text



def test_item_stat_renaming_receipt_points_to_actual_authored_parameter() -> None:
    authored = build_runtime_fixture("workbench_blade")
    compiled = compile_runtime_program(authored)
    stat_call = next(call for call in authored["runtimeProgram"]["calls"] if call["fn"] == "configure_item_stats")
    index = authored["runtimeProgram"]["calls"].index(stat_call)
    receipt = next(
        row for row in compiled["runtimeContract"]["finalWireReceipts"]
        if row.get("callId") == stat_call["id"] and row.get("finalPath") == "gameplay.useTime"
    )
    assert receipt["authoredPath"] == f"runtimeProgram.calls[{index}].params.useTimeTicks"
    assert receipt["value"] == stat_call["params"]["useTimeTicks"]


def test_item_channel_writes_only_the_csharp_item_use_dto() -> None:
    authored = build_runtime_fixture("workbench_blade")
    compiled = compile_runtime_program(authored)
    assert compiled["runtimeProgram"]["itemUse"]["channel"] is False
    assert "channelUse" not in compiled["gameplay"]


def test_receipt_audit_rejects_a_nonexistent_authored_parameter() -> None:
    receipt = {
        "callId": "stats", "fn": "configure_item_stats", "status": "delivered",
        "authoredPath": "runtimeProgram.calls[0].params.useTime",
        "finalPath": "gameplay.useTime", "value": 24,
    }
    report = audit_compiler_receipts([receipt])
    assert report["ok"] is False
    assert report["violations"][0]["reason"] == "compiler receipt used an undeclared authored parameter"


def test_compiler_receipt_source_must_exist_in_the_exact_authored_call() -> None:
    authored = build_capability_witness("configure_accessory")
    compiled = compile_runtime_program(authored)
    original = next(row for row in compiled["runtimeContract"]["finalWireReceipts"]
                    if row.get("fn") == "configure_accessory" and row.get("status") == "delivered")
    forged = deepcopy(original)
    forged["authoredPath"] = forged["authoredPath"].rsplit(".", 1)[0] + ".maxManaPoints"
    report = audit_compiler_receipts([forged], authored_document=authored)
    assert not report["ok"]
    assert any("absent from originating call" in row["reason"] for row in report["violations"])


def test_receipt_value_must_equal_the_declared_one_to_one_projection() -> None:
    authored = build_capability_witness("configure_accessory")
    compiled = compile_runtime_program(authored)
    original = next(row for row in compiled["runtimeContract"]["finalWireReceipts"]
                    if row.get("fn") == "configure_accessory" and row.get("status") == "delivered")
    forged = deepcopy(original)
    forged["value"] = "not_the_authored_value"
    result = audit_compiler_receipts([forged], authored_document=authored)
    assert not result["ok"]
    assert any("not the declared projection" in row["reason"] for row in result["violations"])


def test_equipment_receipt_cannot_swap_equal_valued_class_outputs() -> None:
    authored = build_capability_witness("configure_accessory")
    call = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == "configure_accessory")
    call["params"] = {"defensePoints": 1}
    authored["runtimeProgram"]["calls"].extend([
        {"id": "melee_bonus", "fn": "add_equipment_damage_bonus", "target": "item",
         "params": {"phase": "equipped", "damageClass": "melee", "bonusPercent": 15}},
        {"id": "ranged_bonus", "fn": "add_equipment_damage_bonus", "target": "item",
         "params": {"phase": "equipped", "damageClass": "ranged", "bonusPercent": 15}},
    ])
    receipts = compile_runtime_program(authored)["runtimeContract"]["finalWireReceipts"]
    swapped = deepcopy(receipts)
    melee = next(row for row in swapped if row.get("callId") == "melee_bonus" and row.get("status") == "delivered")
    ranged = next(row for row in swapped if row.get("callId") == "ranged_bonus" and row.get("status") == "delivered")
    melee["finalPath"], ranged["finalPath"] = ranged["finalPath"], melee["finalPath"]
    report = audit_compiler_receipts(swapped, authored_document=authored)
    assert not report["ok"]
    assert any("wrong equipment output" in row["reason"] for row in report["violations"])


def test_equipment_receipts_must_cover_every_authored_parameter() -> None:
    authored = build_capability_witness("configure_accessory")
    call = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == "configure_accessory")
    call["params"] = {"defensePoints": 1, "moveSpeedBonusPercent": 5}
    receipts = compile_runtime_program(authored)["runtimeContract"]["finalWireReceipts"]
    omitted = [row for row in receipts if not str(row.get("authoredPath", "")).endswith(".params.defensePoints")]
    report = audit_compiler_receipts(omitted, authored_document=authored)
    assert not report["ok"]
    assert any("equipment parameter has no receipt" in row["reason"] for row in report["violations"])


def test_receipts_must_match_final_wire_value_when_supplied() -> None:
    authored = build_capability_witness("configure_accessory")
    call = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == "configure_accessory")
    call["params"] = {"defensePoints": 1}
    compiled = compile_runtime_program(authored)
    compiled["accessory"]["defense"] = 99
    report = audit_compiler_receipts(
        compiled["runtimeContract"]["finalWireReceipts"],
        authored_document=authored,
        final_document=compiled,
    )
    assert not report["ok"]
    assert any("final wire value differs" in row["reason"] for row in report["violations"])


def test_item_stat_receipts_cannot_swap_equal_valued_outputs() -> None:
    authored = build_capability_witness("configure_item_stats")
    compiled = compile_runtime_program(authored)
    receipts = deepcopy(compiled["runtimeContract"]["finalWireReceipts"])
    damage = next(row for row in receipts if row.get("finalPath") == "gameplay.damage")
    use_time = next(row for row in receipts if row.get("finalPath") == "gameplay.useTime")
    assert damage["value"] == use_time["value"] == 20
    damage["finalPath"], use_time["finalPath"] = use_time["finalPath"], damage["finalPath"]
    report = audit_compiler_receipts(receipts, authored_document=authored, final_document=compiled)
    assert not report["ok"]
    assert any("wrong item stat output" in row["reason"] for row in report["violations"])


def test_tool_receipts_cannot_swap_equal_valued_outputs() -> None:
    authored = build_capability_witness("configure_tool")
    tool = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == "configure_tool")
    tool["params"].update({"pickPower": 20, "axePowerTooltipPercent": 100})
    compiled = compile_runtime_program(authored)
    receipts = deepcopy(compiled["runtimeContract"]["finalWireReceipts"])
    pick = next(row for row in receipts if row.get("finalPath") == "gameplay.pickPower")
    axe = next(row for row in receipts if row.get("finalPath") == "gameplay.axePower")
    pick["finalPath"], axe["finalPath"] = axe["finalPath"], pick["finalPath"]
    report = audit_compiler_receipts(receipts, authored_document=authored, final_document=compiled)
    assert not report["ok"]
    assert any("wrong capability output" in row["reason"] for row in report["violations"])
    compiled["runtimeContract"]["finalWireReceipts"] = receipts
    assert not validate_runtime_wire(compiled)["ok"]


def test_tool_projection_status_cannot_bypass_param_to_wire_mapping() -> None:
    authored = build_capability_witness("configure_tool")
    tool = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == "configure_tool")
    tool["params"].update({"pickPower": 20, "axePowerTooltipPercent": 125})
    compiled = compile_runtime_program(authored)
    receipts = deepcopy(compiled["runtimeContract"]["finalWireReceipts"])
    pick = next(row for row in receipts if row.get("finalPath") == "gameplay.pickPower")
    axe = next(row for row in receipts if row.get("finalPath") == "gameplay.axePower")
    pick["finalPath"], axe["finalPath"] = axe["finalPath"], pick["finalPath"]
    pick["value"], axe["value"] = axe["value"], pick["value"]
    pick["status"] = axe["status"] = "technical_projection"
    report = audit_compiler_receipts(receipts, authored_document=authored, final_document=compiled)
    assert not report["ok"]
    assert any("wrong capability output" in row["reason"] for row in report["violations"])
    compiled["runtimeContract"]["finalWireReceipts"] = receipts
    assert not validate_runtime_wire(compiled)["ok"]


def test_no_ordinary_parameter_receipt_can_hide_as_technical_projection() -> None:
    for fn in CAPABILITY_REGISTRY:
        if not CAPABILITY_REGISTRY[fn].params:
            continue
        authored = build_capability_witness(fn)
        compiled = compile_runtime_program(authored)
        receipts = deepcopy(compiled["runtimeContract"]["finalWireReceipts"])
        direct = next((row for row in receipts if row.get("fn") == fn
                       and row.get("status") == "delivered"
                       and ".params." in str(row.get("authoredPath") or "")), None)
        if direct is None:
            assert fn == "apply_vanilla_buff_on_use", fn
            continue
        direct["status"] = "technical_projection"
        report = audit_compiler_receipts(receipts, authored_document=authored, final_document=compiled)
        assert not report["ok"], fn
        compiled["runtimeContract"]["finalWireReceipts"] = receipts
        assert not validate_runtime_wire(compiled)["ok"], fn


def test_buff_receipts_cannot_swap_equal_valued_outputs() -> None:
    authored = build_capability_witness("apply_vanilla_buff_on_use")
    buff = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == "apply_vanilla_buff_on_use")
    buff["params"].update({"buffId": 20, "durationTicks": 20})
    compiled = compile_runtime_program(authored)
    receipts = deepcopy(compiled["runtimeContract"]["finalWireReceipts"])
    code = next(row for row in receipts if row.get("finalPath") == "gameplay.extraBuffs[0].buffCode")
    duration = next(row for row in receipts if row.get("finalPath") == "gameplay.extraBuffs[0].buffTime")
    code["finalPath"], duration["finalPath"] = duration["finalPath"], code["finalPath"]
    report = audit_compiler_receipts(receipts, authored_document=authored, final_document=compiled)
    assert not report["ok"]
    assert any("wrong capability output" in row["reason"] for row in report["violations"])
    compiled["runtimeContract"]["finalWireReceipts"] = receipts
    assert not validate_runtime_wire(compiled)["ok"]


def test_wire_validator_detects_receipt_value_mismatch_without_author_document() -> None:
    authored = build_capability_witness("configure_accessory")
    compiled = compile_runtime_program(authored)
    compiled["accessory"]["defense"] = 99
    report = validate_runtime_wire(compiled)
    assert not report["ok"]
    assert any(row["code"] == "undeclared_technical_lowering" for row in report["errors"])


def test_receipts_cover_non_equipment_authored_parameter_too() -> None:
    authored = build_capability_witness("configure_item_stats")
    compiled = compile_runtime_program(authored)
    receipts = compiled["runtimeContract"]["finalWireReceipts"]
    omitted = [row for row in receipts if not str(row.get("authoredPath", "")).endswith(".params.valueCopper")]
    report = audit_compiler_receipts(omitted, authored_document=authored)
    assert not report["ok"]
    assert any("authored parameter has no compiler receipt" in row["reason"] for row in report["violations"])


@pytest.mark.parametrize("fn,values,expected", [
    ("configure_accessory", {
        "defensePoints": 4,
        "genericCritChancePercentagePoints": 3, "maxRunSpeedBonusPxPerTick": 1.5,
        "fallDamageImmune": True, "ammoSaveChancePercent": 25,
    }, {
        "defense": 4, "genericCrit": 3,
        "maxRunSpeed": 1.5, "fallDamageImmune": True, "ammoSaveChance": 0.25,
    }),
    ("configure_armor", {
        "slot": "head", "setKey": "tested_set", "defensePoints": 5,
        "setBonusManaCostReductionPercentagePoints": 10,
        "setBonusMinionSlotsBonus": 2,
    }, {
        "defense": 5, "setBonusManaCostReduction": 0.10,
        "setBonusMinionSlots": 2,
    }),
])
def test_equipment_primitives_reach_exact_tml_fields(fn: str, values: dict, expected: dict) -> None:
    authored = build_capability_witness(fn)
    call = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == fn)
    call["params"] = values
    assert validate_runtime_program(authored)["ok"]
    compiled = compile_runtime_program(authored)
    assert validate_runtime_wire(compiled)["ok"]
    key = "accessory" if fn == "configure_accessory" else "armor"
    for field, value in expected.items():
        assert compiled[key][field] == pytest.approx(value) if isinstance(value, float) else compiled[key][field] == value
    receipts = compiled["runtimeContract"]["finalWireReceipts"]
    for param in values:
        if param in {"slot", "setKey"}:
            continue
        assert any(row.get("callId") == call["id"] and row.get("authoredPath", "").endswith(".params." + param) for row in receipts)


@pytest.mark.parametrize("fn,old", [
    ("configure_accessory", "genericDamage"),
    ("configure_accessory", "meleeDamage"),
    ("configure_armor", "setBonusGenericDamage"),
])
def test_ambiguous_equipment_vocabulary_is_not_a_second_author_surface(fn: str, old: str) -> None:
    authored = build_capability_witness(fn)
    call = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == fn)
    call["params"] = {"slot": "head", "setKey": "checked"} if fn == "configure_armor" else {}
    call["params"][old] = 0.15
    assert validate_runtime_program(authored)["ok"] is False


@pytest.mark.parametrize("configure,slot,phase,damage_class,expected_path", [
    ("configure_accessory", None, "equipped", "melee", "accessory.meleeDamage"),
    ("configure_armor", "head", "equipped", "summon", "armor.summonDamage"),
    ("configure_armor", "head", "matching_armor_set", "magic", "armor.setBonusMagicDamage"),
])
def test_class_damage_is_one_parameterized_equipment_primitive(
    configure: str, slot: str | None, phase: str, damage_class: str, expected_path: str,
) -> None:
    authored = build_capability_witness(configure)
    equip = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == configure)
    equip["params"] = {"defensePoints": 4} if slot is None else {"slot": slot, "setKey": "coral_set", "defensePoints": 4}
    authored["runtimeProgram"]["calls"].append({
        "id": "class_bonus", "fn": "add_equipment_damage_bonus", "target": "item",
        "params": {"phase": phase, "damageClass": damage_class, "bonusPercent": 15},
    })
    assert validate_runtime_program(authored)["ok"]
    compiled = compile_runtime_program(authored)
    assert validate_runtime_wire(compiled)["ok"]
    namespace, field = expected_path.split(".")
    assert compiled[namespace][field] == pytest.approx(0.15)
    assert any(
        row.get("callId") == "class_bonus" and row.get("finalPath") == expected_path
        and row.get("value") == pytest.approx(0.15)
        for row in compiled["runtimeContract"]["finalWireReceipts"]
    )


def test_per_class_damage_aliases_are_not_a_second_author_vocabulary() -> None:
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY

    for fn in ("configure_accessory", "configure_armor"):
        assert not any(
            f"{damage_class}DamageBonusPercent" in CAPABILITY_REGISTRY[fn].params
            or f"setBonus{damage_class.title()}DamageBonusPercent" in CAPABILITY_REGISTRY[fn].params
            for damage_class in ("generic", "melee", "ranged", "magic", "summon")
        )
        authored = build_capability_witness(fn)
        equip = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == fn)
        equip["params"]["meleeDamageBonusPercent"] = 15
        assert not validate_runtime_program(authored)["ok"]


def test_equipment_damage_only_accessory_is_not_inert() -> None:
    authored = build_capability_witness("add_equipment_damage_bonus")
    accessory = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == "configure_accessory")
    accessory["params"] = {}
    assert validate_runtime_program(authored)["ok"]
    wire = compile_runtime_program(authored)
    assert wire["accessory"]["meleeDamage"] == pytest.approx(0.15)


@pytest.mark.parametrize("damage_class", ["generic", "melee", "ranged", "magic", "summon"])
def test_equipment_damage_class_selector_is_exact(damage_class: str) -> None:
    authored = build_capability_witness("add_equipment_damage_bonus")
    bonus = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == "add_equipment_damage_bonus")
    bonus["params"]["damageClass"] = damage_class
    assert validate_runtime_program(authored)["ok"]
    wire = compile_runtime_program(authored)
    assert wire["accessory"][f"{damage_class}Damage"] == pytest.approx(0.15)


@pytest.mark.parametrize("damage_class", ["melee_no_speed", "ExampleMod/CustomDamage", "Terraria/ThornWhip"])
def test_equipment_damage_class_does_not_claim_unimplemented_engine_classes(damage_class: str) -> None:
    authored = build_capability_witness("add_equipment_damage_bonus")
    bonus = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == "add_equipment_damage_bonus")
    bonus["params"]["damageClass"] = damage_class
    assert not validate_runtime_program(authored)["ok"]


def test_equipment_damage_duplicate_selector_is_rejected_without_implicit_addition() -> None:
    authored = build_capability_witness("add_equipment_damage_bonus")
    bonus = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == "add_equipment_damage_bonus")
    other = deepcopy(bonus)
    other["id"] = "same_class_again"
    authored["runtimeProgram"]["calls"].append(other)
    report = validate_runtime_program(authored)
    assert not report["ok"]
    assert any(row["code"] == "duplicate_equipment_damage_selector" for row in report["errors"])


def test_equipment_damage_needs_exactly_one_declared_equipment_kind() -> None:
    authored = build_capability_witness("add_equipment_damage_bonus")
    authored["runtimeProgram"]["calls"].append({
        "id": "also_armor", "fn": "configure_armor", "target": "item",
        "params": {"slot": "head", "setKey": "", "defensePoints": 2},
    })
    report = validate_runtime_program(authored)
    assert not report["ok"]
    assert any(row["code"] == "equipment_scope_conflict" for row in report["errors"])


def test_accessory_with_only_boolean_immunity_is_not_inert() -> None:
    authored = build_capability_witness("configure_accessory")
    call = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == "configure_accessory")
    call["params"] = {"fallDamageImmune": True}
    assert validate_runtime_program(authored)["ok"]
    compiled = compile_runtime_program(authored)
    assert compiled["accessory"]["fallDamageImmune"] is True


def test_armor_set_bonus_requires_an_actual_matching_set_key() -> None:
    authored = build_capability_witness("configure_armor")
    call = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == "configure_armor")
    call["params"] = {"slot": "head", "setKey": "", "defensePoints": 2}
    authored["runtimeProgram"]["calls"].append({
        "id": "set_damage", "fn": "add_equipment_damage_bonus", "target": "item",
        "params": {"phase": "matching_armor_set", "damageClass": "melee", "bonusPercent": 15},
    })
    invalid = validate_runtime_program(authored)
    assert not invalid["ok"]
    assert any(row["code"] == "missing_set_key" for row in invalid["errors"])
    call["params"]["setKey"] = "matching_set"
    assert validate_runtime_program(authored)["ok"]


def test_set_bonus_only_on_head_when_matching_three_piece_set_exists() -> None:
    authored = build_capability_witness("configure_armor")
    call = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == "configure_armor")
    call["params"] = {"slot": "body", "setKey": "matching_set", "defensePoints": 2}
    authored["runtimeProgram"]["calls"].append({
        "id": "set_damage", "fn": "add_equipment_damage_bonus", "target": "item",
        "params": {"phase": "matching_armor_set", "damageClass": "generic", "bonusPercent": 10},
    })
    result = validate_runtime_program(authored)
    assert not result["ok"]
    assert any(error["code"] == "set_bonus_head_only" for error in result["errors"])
    call["params"]["slot"] = "head"
    assert validate_runtime_program(authored)["ok"]


@pytest.mark.parametrize("fn", [
    "restore_resources_on_use", "apply_vanilla_buff_on_use",
    "apply_generated_buff_on_use", "move_player_on_use",
])
def test_item_use_effect_call_requires_an_executable_effect_binding(fn: str) -> None:
    authored = build_capability_witness(fn)
    binding = authored["runtimeProgram"]["bindings"][0]
    assert binding["usePolicy"]["action"]["kind"] == "apply_item_effects"
    assert validate_runtime_program(authored)["ok"]
    binding["usePolicy"]["action"]["kind"] = "use_item_body"
    report = validate_runtime_program(authored)
    assert not report["ok"]
    assert any(error["code"] == "missing_binding_dependency" for error in report["errors"])


def test_accessory_ammo_save_describes_player_wide_ammo_consumption() -> None:
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY

    description = CAPABILITY_REGISTRY["configure_accessory"].params["ammoSaveChancePercent"].description
    assert "any weapon" in description
    assert "CanConsumeAmmo" in description


@pytest.mark.parametrize("fn", ["configure_accessory", "configure_armor"])
def test_equipped_light_requires_explicit_color_before_csharp_normalization(fn: str) -> None:
    authored = build_capability_witness(fn)
    call = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == fn)
    call["params"] = {"lightStrength": 0.35}
    if fn == "configure_armor":
        call["params"].update({"slot": "head", "setKey": ""})
    rejected = validate_runtime_program(authored)
    assert not rejected["ok"]
    assert any(row["code"] == "missing_light_color" for row in rejected["errors"])
    call["params"]["lightColor"] = "yellow"
    assert validate_runtime_program(authored)["ok"]
    wire = compile_runtime_program(authored)
    assert wire["accessory" if fn == "configure_accessory" else "armor"]["lightColorName"] == "yellow"


@pytest.mark.parametrize("fn", [
    "apply_status_on_event", "damage_area_on_event", "chain_damage_on_event",
    "pull_on_event", "heal_owner_on_event", "move_owner_on_event",
])
def test_each_event_action_can_use_its_existing_bounded_delay(fn: str) -> None:
    authored = build_capability_witness(fn)
    call = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == fn)
    call["params"]["delayTicks"] = 30
    assert validate_runtime_program(authored)["ok"]
    compiled = compile_runtime_program(authored)
    assert validate_runtime_wire(compiled)["ok"]
    actions = [a for entity in compiled["runtimeProgram"]["entities"] for a in entity.get("events", [])]
    assert next(a for a in actions if a["id"] == call["id"])["delayTicks"] == 30


def test_machine_audit_detects_a_new_executable_csharp_field_without_author_primitive() -> None:
    from infini_local.qa.primitive_loss_audit import equipment_surface_audit

    root = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal"
    dto = (root / "Common/Models/GeneratedItemData.Model.cs").read_bytes()
    executor = (root / "Content/Items/GeneratedItem.cs").read_bytes()
    assert equipment_surface_audit(dto, executor)["ok"]
    new_dto = dto.replace(
        b"public float SummonTagDamage { get; set; } = 0f;",
        b"public float UncataloguedBonus { get; set; } = 0f;\n    public float SummonTagDamage { get; set; } = 0f;",
    )
    new_executor = executor.replace(
        b"AddGeneratedSummonTagDamage(a.SummonTagDamage)",
        b"AddGeneratedSummonTagDamage(a.UncataloguedBonus)",
    )
    assert new_dto != dto and new_executor != executor
    report = equipment_surface_audit(new_dto, new_executor)
    assert report["ok"] is False
    assert "UncataloguedBonus" in report["missingAuthorFields"]


def test_ast_dto_inventory_uses_property_name_not_initializer_symbol() -> None:
    from infini_local.qa.primitive_loss_audit import _class_properties

    root = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal"
    source = (root / "Common/Models/RuntimeProgramSpec.cs").read_bytes()
    names = _class_properties(source, "RuntimeProgramSpec")
    assert {"ApiVersion", "Schema", "Entities", "Bindings"} <= names
    assert "CurrentApiVersion" not in names and "CurrentWireSchema" not in names


def test_machine_audit_detects_an_unexposed_event_executor_field() -> None:
    from infini_local.qa.primitive_loss_audit import event_surface_audit

    root = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal"
    dto = (root / "Common/Models/RuntimeProgramSpec.cs").read_bytes()
    executor = (root / "Common/Runtime/RuntimeProgramExecutor.cs").read_bytes()
    assert event_surface_audit(dto, executor)["ok"]
    extra_dto = dto.replace(
        b"public float DamageMultiplier { get; set; } = 1f;",
        b"public float UncataloguedBlast { get; set; } = 1f;\n    public float DamageMultiplier { get; set; } = 1f;",
    )
    extra_executor = executor.replace(b"Math.Clamp(action.DamageMultiplier, 0f, 10f)",
                                      b"Math.Clamp(action.UncataloguedBlast, 0f, 10f)")
    assert extra_dto != dto and extra_executor != executor
    result = event_surface_audit(extra_dto, extra_executor)
    assert not result["ok"]
    assert "UncataloguedBlast" in result["missingAuthorFields"]
    init_dto = extra_dto.replace(b"UncataloguedBlast { get; set; }", b"UncataloguedBlast { get; init; }")
    assert "UncataloguedBlast" in event_surface_audit(init_dto, extra_executor)["missingAuthorFields"]


def test_event_ast_inventory_includes_delayed_and_periodic_consumers() -> None:
    from infini_local.qa.primitive_loss_audit import event_surface_audit

    result = event_surface_audit()
    assert result["ok"]
    assert {"DelayTicks", "PeriodTicks"} <= set(result["executableFields"])


def test_event_ast_detects_new_delayed_executor_field() -> None:
    from infini_local.qa.primitive_loss_audit import event_surface_audit

    root = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal"
    dto = (root / "Common/Models/RuntimeProgramSpec.cs").read_bytes()
    scheduler = (root / "Common/Runtime/RuntimeDelayedActionScheduler.cs").read_bytes()
    injected_dto = dto.replace(
        b"public int DelayTicks { get; set; }\n    public int PeriodTicks { get; set; }",
        b"public int UncataloguedDelay { get; init; }\n    public int DelayTicks { get; set; }\n    public int PeriodTicks { get; set; }",
    )
    injected_scheduler = scheduler.replace(b"action.DelayTicks", b"action.UncataloguedDelay", 1)
    assert injected_dto != dto and injected_scheduler != scheduler
    result = event_surface_audit(injected_dto, scheduler=injected_scheduler)
    assert not result["ok"]
    assert "UncataloguedDelay" in result["missingAuthorFields"]


def test_machine_audit_classifies_the_remaining_runtime_component_dto_fields() -> None:
    from infini_local.qa.primitive_loss_audit import runtime_component_surface_audit

    root = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal"
    dto = (root / "Common/Models/RuntimeProgramSpec.cs").read_bytes()
    assert runtime_component_surface_audit(dto)["ok"]
    changed = dto.replace(
        b"public float HomingStrength { get; set; }",
        b"public float UncataloguedMomentum { get; set; }\n    public float HomingStrength { get; set; }",
    )
    assert changed != dto
    result = runtime_component_surface_audit(changed)
    assert not result["ok"]
    assert "UncataloguedMomentum" in result["unclassifiedByClass"]["RuntimeParamsSpec"]


def test_machine_audit_covers_structural_runtime_and_visual_dtos() -> None:
    from infini_local.qa.primitive_loss_audit import structural_surface_audit

    root = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal"
    dto = (root / "Common/Models/RuntimeProgramSpec.cs").read_bytes()
    assert structural_surface_audit(dto)["ok"]
    surface = structural_surface_audit(dto)
    assert "ImpactPrompt" in surface["vfxDirectorFields"]
    assert "ImpactPrompt" not in surface["technicalVisualFields"]
    assert "SpritePath" in surface["technicalVisualFields"]
    changed = dto.replace(
        b"public string ItemEntityId { get; set; } = \"\";",
        b"public int UncataloguedRootBonus { get; set; }\n    public string ItemEntityId { get; set; } = \"\";",
    )
    assert changed != dto
    report = structural_surface_audit(changed)
    assert not report["ok"]
    assert "UncataloguedRootBonus" in report["unclassifiedByClass"]["RuntimeProgramSpec"]


def test_machine_audit_covers_item_gameplay_and_generated_buff_dtos() -> None:
    from infini_local.qa.primitive_loss_audit import item_gameplay_surface_audit

    root = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal"
    dto = (root / "Common/Models/GeneratedItemData.Model.cs").read_bytes()
    assert item_gameplay_surface_audit(dto)["ok"]
    changed = dto.replace(
        b"public int BuffTime { get; set; } = 0;",
        b"public int UncataloguedItemEffect { get; set; } = 0;\n    public int BuffTime { get; set; } = 0;",
    )
    assert changed != dto
    assert "UncataloguedItemEffect" in item_gameplay_surface_audit(changed)["unclassifiedByClass"]["GameplaySpec"]


@pytest.mark.parametrize("enabled,wire_value", [(True, 1), (False, 0)])
def test_generated_spelunker_is_a_boolean_capability_not_a_fake_radius(enabled: bool, wire_value: int) -> None:
    authored = build_capability_witness("apply_generated_buff_on_use")
    call = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == "apply_generated_buff_on_use")
    call["params"]["oreSenseEnabled"] = enabled
    assert validate_runtime_program(authored)["ok"]
    compiled = compile_runtime_program(authored)
    assert compiled["gameplay"]["generatedBuff"]["oreSenseRadiusTiles"] == wire_value
    assert validate_runtime_wire(compiled)["ok"]
    call["params"]["oreSenseRadiusTiles"] = 30
    assert validate_runtime_program(authored)["ok"] is False


def test_event_blink_only_exposes_the_destination_it_actually_executes() -> None:
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY

    authored = build_capability_witness("move_owner_on_event")
    call = next(row for row in authored["runtimeProgram"]["calls"] if row["fn"] == "move_owner_on_event")
    call["params"].pop("mode", None)
    assert "mode" not in CAPABILITY_REGISTRY["move_owner_on_event"].params
    assert validate_runtime_program(authored)["ok"]
    compiled = compile_runtime_program(authored)
    actions = [a for entity in compiled["runtimeProgram"]["entities"] for a in entity.get("events", [])]
    assert next(a for a in actions if a["id"] == call["id"])["mode"] == "blink_to_event_position"
    assert validate_runtime_wire(compiled)["ok"]
    call["params"]["mode"] = "blink_to_entity"
    assert validate_runtime_program(authored)["ok"] is False


def test_canonical_parity_document_contains_engine_units_and_loss_boundaries() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / "docs/PRIMITIVE_PARITY_RU.md").read_text(encoding="utf-8")
    assert "019ff01" in text and "25caddf" in text
    assert "add_equipment_damage_bonus" in text and "additive_percent" in text
    assert "armor.setBonusMagicDamage" in text and "matching_armor_set" in text
    assert "meleeDamageBonusPercent" not in text
    assert "extraUpdates > 0" in text
    assert "held generatedBuff" in text
    assert "OreSenseRadiusTiles" in text and "oreSenseEnabled" in text
    assert "RuntimeParamsSpec.IntervalTicks" in text
    inventory = (root / "docs/LOW_LEVEL_CAPABILITY_INVENTORY_RU.md").read_text(encoding="utf-8")
    assert "PRIMITIVE_PARITY_RU.md" in inventory
