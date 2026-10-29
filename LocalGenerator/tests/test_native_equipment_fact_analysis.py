"""Behavioral proof boundaries for native equipment source references."""

import copy
import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/generate"))
from native_hit_status_analysis import Instruction as I
from native_equipment_fact_analysis import equipment_facts, armor_set_facts
from infini_local.pipelines.parent_context_pipeline import compact_item_raw_for_llm


def program(ops):
    labels, clean = {}, []
    for op in ops:
        if op[0] == "label":
            labels[op[1]] = len(clean)
        else:
            clean.append(op)
    return [
        I(n, op[0], labels.get(op[1], op[1]) if len(op) == 2 and isinstance(op[1], str) else op[1] if len(op) == 2 else None)
        for n, op in enumerate(clean)
    ]


def crit():
    return [
        ("ldarg", 0),
        ("call", ("Terraria.Player.get_allCrit", 0, True, True)),
        ("dup",),
        ("ldind.r4",),
        ("const", 5),
        ("add",),
        ("stind.r4",),
    ]


def item(body, ids=(10, 11)):
    guards = []
    for value in ids[:-1]:
        guards += [("ldarg", 1), ("ldfld", "Terraria.Item.type"), ("const", value), ("beq", "body")]
    guards += [("ldarg", 1), ("ldfld", "Terraria.Item.type"), ("const", ids[-1]), ("bne", "outside"), ("label", "body")]
    return guards + body + [("label", "outside"), ("ret",)]


def set_ops():
    ops = []
    for field, values in [("head", [5, 74]), ("body", [5, 48]), ("legs", [5, 44])]:
        for value in values[:-1]:
            ops += [("ldarg", 0), ("ldfld", "Terraria.Player." + field), ("const", value), ("beq", "after_" + field)]
        ops += [("ldarg", 0), ("ldfld", "Terraria.Player." + field), ("const", values[-1]), ("bne", "outside"), ("label", "after_" + field)]
    return ops + [
        ("ldarg", 0),
        ("ldstr", "ArmorSetBonus.ShadowScale"),
        ("call", ("Terraria.Localization.Language.GetTextValue", 1, False, True)),
        ("stfld", "Terraria.Player.setBonus"),
        ("ldarg", 0),
        ("const", 1),
        ("stfld", "Terraria.Player.shadowArmor:bool"),
        ("label", "outside"),
        ("ret",),
    ]


def test_or_item_guards_preserve_exact_numeric_scope_without_double_counting():
    rows = equipment_facts(program(item(crit())))
    assert [r["itemId"] for r in rows] == [10, 11]
    assert all(len(r["branches"]) == 1 for r in rows)
    effect = rows[0]["branches"][0]["effects"][0]
    assert (effect["stat"], effect["damageClass"], effect["value"], effect["units"]) == ("critChance", "generic", 5, "percentage_points")


@pytest.mark.parametrize(
    "body",
    [
        crit() + [("call", ("Unknown.Apply", 0, False, False))],
        [("ldsfld", "unknown"), ("brtrue", "outside")] + crit(),
        crit() + [("br", "body")],
    ],
)
def test_unknown_calls_branches_and_loops_refuse_the_whole_equipment_block(body):
    assert equipment_facts(program(item(body))) == []


@pytest.mark.parametrize("prefix", [[("ldsfld", "unknown"), ("brfalse", "outside")], [("br", "body")]])
def test_enclosing_context_and_external_body_entry_cannot_become_unconditional(prefix):
    assert equipment_facts(program(prefix + item(crit()))) == []
    assert armor_set_facts(program([("ldsfld", "unknown"), ("brfalse", "outside")] + set_ops())) == []


def test_full_set_keeps_all_slots_and_mixed_variants_not_item_ids():
    rows = armor_set_facts(program(set_ops()))
    assert len(rows) == 1
    assert rows[0]["condition"] == {
        "functionalEquipSlots": {"head": [5, 74], "body": [5, 48], "legs": [5, 44]},
        "allSlotsRequired": True,
        "vanitySatisfies": False,
    }
    assert rows[0]["effects"][0]["nativeMember"] == "Terraria.Player.shadowArmor"
    assert rows[0]["effects"][0]["value"] is True
    assert "movementSpeed" not in json.dumps(rows)
    broken = set_ops()
    broken[1] = ("ldfld", "Terraria.Player.unknown")
    assert armor_set_facts(program(broken)) == []


@pytest.mark.parametrize("key", ["nativeEquipmentReference", "nativeEnvironmentReference"])
@pytest.mark.parametrize("envelope", ["root", "runtimeFacts", "fingerprint"])
def test_compact_packet_keeps_complete_conditional_proof_and_independent_copy(key, envelope):
    ref = {
        "effects": [{"value": 0}],
        "condition": {"allSlotsRequired": True, "vanitySatisfies": False, "anyOf": []},
        "certificate": "exact",
        "unsupported": [],
    }
    item_ = {key: ref} if envelope == "root" else {envelope: {key: ref}}
    compact = compact_item_raw_for_llm(item_)
    assert compact[key] == ref
    compact[key]["condition"]["vanitySatisfies"] = True
    assert ref["condition"]["vanitySatisfies"] is False


def test_packet_root_precedence_and_generated_parent_host_exclusion():
    item_ = {
        "nativeEquipmentReference": {"value": 0},
        "runtimeFacts": {"nativeEquipmentReference": {"value": 1}},
        "fingerprint": {"nativeEquipmentReference": {"value": 2}},
    }
    assert compact_item_raw_for_llm(item_)["nativeEquipmentReference"] == {"value": 0}
    item_["generatedData"] = {"id": "g_test", "name": "authored"}
    assert "nativeEquipmentReference" not in compact_item_raw_for_llm(item_)


def test_generated_catalog_is_exact_report_projection():
    from generate_native_equipment_facts import render

    report = json.loads((ROOT / "contracts/reports/native_equipment_sources.generated.json").read_text())
    assert (
        render(report["sources"])
        == (ROOT / "ModSources/InfiniCrafterLocal/Common/Services/Generation/NativeEquipmentFactsCatalog.g.cs").read_text()
    )
    for source in report["sources"]:
        assert source["sourceModuleVersionId"] and len(source["sourceMethodSha256"]) == 64


def test_unreachable_or_repeated_whole_equipment_branch_is_refused():
    assert equipment_facts(program([("ret",)] + item(crit()))) == []
    repeated = [("label", "loop")] + item(crit())[:-1] + [("br", "loop"), ("ret",)]
    assert equipment_facts(program(repeated)) == []


def test_boolean_context_keeps_base_addition_and_conditional_contribution_separate():
    body = crit() + [("ldsfld", "Terraria.Main.tenthAnniversaryWorld:bool"), ("brfalse", "outside")] + [
        ("ldarg", 0), ("ldarg", 0), ("ldfld", "Terraria.Player.maxMinions"), ("const", 1), ("add",), ("stfld", "Terraria.Player.maxMinions")]
    rows = equipment_facts(program(item(body, (238,))))
    assert len(rows) == 1
    branch = rows[0]["branches"][0]
    assert branch["effects"][0]["value"] == 5
    conditional = branch["conditionalEffects"][0]
    assert conditional["condition"] == {"nativeMember": "Terraria.Main.tenthAnniversaryWorld", "equals": True, "observed": False}
    assert conditional["effects"][0]["stat"] == "maximumMinions"
    assert conditional["effects"][0]["value"] == 1
    false_body = list(body); false_body[8] = ("brtrue", "outside")
    assert equipment_facts(program(item(false_body, (238,))))[0]["branches"][0]["conditionalEffects"][0]["condition"]["equals"] is False
    for gate in ["unknown", "Terraria.Main.tenthAnniversaryWorld"]:
        unknown = list(body); unknown[7] = ("ldsfld", gate)
        assert equipment_facts(program(item(unknown, (238,)))) == []
    nested = body[:9] + [("ldsfld", "Terraria.Main.other:bool"), ("brfalse", "outside")] + body[9:]
    assert equipment_facts(program(item(nested, (238,)))) == []


def test_bounded_literal_item_id_range_preserves_each_item_and_declines_bypass():
    guarded = [("ldarg", 1), ("ldfld", "Terraria.Item.type"), ("const", 1158), ("blt", "outside"),
        ("ldarg", 1), ("ldfld", "Terraria.Item.type"), ("const", 1161), ("bgt", "outside")] + crit() + [("label", "outside"), ("ret",)]
    rows = equipment_facts(program(guarded))
    assert [r["itemId"] for r in rows] == [1158, 1159, 1160, 1161]
    assert all(len(r["branches"]) == 1 and r["branches"][0]["effects"][0]["value"] == 5 for r in rows)
    for at, replacement in [(3, ("blt", "outside_wrong")), (7, ("bge", "outside")), (6, ("const", 2000))]:
        changed = guarded.copy(); changed[at] = replacement
        assert equipment_facts(program(changed + [("label", "outside_wrong"), ("ret",)])) == []
    assert equipment_facts(program([("ldsfld", "unknown"), ("brfalse", "outside")] + guarded)) == []
    bypass = program(guarded)
    assert equipment_facts([I(-1, "br", 8), *bypass]) == []


def test_native_mining_whip_and_fishing_additions_keep_component_units():
    for field, value, expected, units in [("pickSpeed", -0.1, "pickUseTimeMultiplier", "additive_fraction"),
            ("whipRangeMultiplier", 0.15, "whipRangeMultiplier", "additive_fraction"),
            ("fishingSkill", 5, "fishingPower", "points")]:
        body = [("ldarg", 0), ("ldarg", 0), ("ldfld", "Terraria.Player." + field), ("const", value), ("add",), ("stfld", "Terraria.Player." + field)]
        rows = equipment_facts(program(item(body, (10,))))
        assert len(rows) == 1
        effect = rows[0]["branches"][0]["effects"][0]
        assert (effect["stat"], effect["value"], effect["units"]) == (expected, value, units)
