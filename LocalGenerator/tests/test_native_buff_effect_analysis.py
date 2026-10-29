"""Source-only recognizer contracts. No native hooks or game runtime are executed."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/generate"))
from native_hit_status_analysis import Instruction as I


def code(ops):
    labels, clean = {}, []
    for op in ops:
        if op[0] == "label":
            labels[op[1]] = len(clean)
        else:
            clean.append(op)
    return [I(n, op[0], labels.get(op[1], op[1]) if len(op) == 2 else None)
            for n, op in enumerate(clean)]


def buff_clause(body, buff_id=917):
    return code([
        ("ldarg", 0), ("ldfld", "Terraria.Player.buffType"), ("ldloc", 0),
        ("ldelem",), ("const", buff_id), ("bne", "end"),
        *body, ("br", "end"), ("label", "end"), ("ret",),
    ])


def test_arbitrary_buff_id_derives_raw_scalar_and_boolean_operations_not_names():
    from native_buff_effect_analysis import buff_type_branches
    body = [("ldarg", 0), ("ldarg", 0), ("ldfld", "Terraria.Player.pickSpeed"),
            ("const", 0.25), ("sub",), ("stfld", "Terraria.Player.pickSpeed"),
            ("ldarg", 0), ("const", 1), ("stfld", "Terraria.Player.findTreasure")]
    rows = buff_type_branches(buff_clause(body), "Player", {
        "Terraria.Player.pickSpeed": "float32", "Terraria.Player.findTreasure": "boolean"})
    assert len(rows) == 1
    row = rows[0]
    assert row["buffId"] == 917
    assert row["condition"]["buffTypeEquals"] == 917
    assert row["condition"]["nativeControlFlowMustReachTest"] == 0
    assert row["operations"] == [
        {"nativeMember": "Terraria.Player.pickSpeed", "operation": "add", "value": -0.25,
         "units": "native_member_units", "storageType": "float32", "sourceIlOffset": 11},
        {"nativeMember": "Terraria.Player.findTreasure", "operation": "assign", "value": True,
         "units": "boolean_flag_only", "storageType": "boolean", "sourceIlOffset": 14},
    ]
    assert row["completeness"] == "partial_native_statement_fragment"
    assert row["unsupported"]


def test_npc_flag_to_dot_is_derived_and_keeps_clamp_and_damageability_guard():
    from native_buff_effect_analysis import npc_dot_fragments
    dot = code([
        ("ldarg", 0), ("ldfld", "Terraria.NPC.dontTakeDamage"), ("brfalse", "start"), ("ret",),
        ("label", "start"), ("ldarg", 0), ("ldfld", "Terraria.NPC.lifeRegenExpectedLossPerSecond"), ("stloc", 0),
        ("ldarg", 0), ("ldfld", "Terraria.NPC.arbitraryFlag"), ("brfalse", "end"),
        ("ldarg", 0), ("ldfld", "Terraria.NPC.lifeRegen"), ("const", 0), ("ble", "subtract"),
        ("ldarg", 0), ("const", 0), ("stfld", "Terraria.NPC.lifeRegen"),
        ("label", "subtract"), ("ldarg", 0), ("ldarg", 0), ("ldfld", "Terraria.NPC.lifeRegen"),
        ("const", 12), ("sub",), ("stfld", "Terraria.NPC.lifeRegen"), ("label", "end"), ("ret",),
    ])
    rows = npc_dot_fragments(dot, {"Terraria.NPC.arbitraryFlag": "boolean"})
    assert len(rows) == 1
    fact = rows[0]
    assert fact["flagMember"] == "Terraria.NPC.arbitraryFlag"
    assert fact["condition"] == {"Terraria.NPC.dontTakeDamage": False, "flagEquals": True}
    assert fact["operations"][0]["value"] == -12
    assert fact["operations"][0]["clampPositiveToZeroFirst"] is True
    assert fact["operations"][0]["units"] == "native_lifeRegen_units"
    assert npc_dot_fragments(dot, {}) == []
    # Unknown outer guard cannot silently disappear from the condition.
    broken = [I(i.offset, "ldsfld", "unknown") if i.offset == 0 else i for i in dot]
    assert npc_dot_fragments(broken, {"Terraria.NPC.arbitraryFlag": "boolean"}) == []


def test_npc_defense_flat_addition_retains_ignore_armor_debuffs_gate():
    from native_buff_effect_analysis import npc_defense_fragments
    native = code([
        ("ldarg", 3), ("brtrue", "end"),
        ("ldarg", 0), ("ldfld", "Terraria.NPC.testFlag"), ("brfalse", "end"),
        ("ldloca", 0), ("ldflda", ".HitModifiers.Defense"),
        ("ldflda", "Terraria.ModLoader.StatModifier.Flat"), ("dup",),
        ("ldind.r4",), ("const", 15.0), ("sub",), ("stind.r4",),
        ("label", "end"), ("ret",),
    ])
    result = npc_defense_fragments(native, {"Terraria.NPC.testFlag": "boolean"})
    assert len(result) == 1
    assert result[0]["condition"]["ignoreArmorDebuffs"] is False
    assert result[0]["condition"]["nativeControlFlowMustReachTest"] == 0
    assert result[0]["operations"][0]["value"] == -15
    assert result[0]["operations"][0]["units"] == "defense_points"
    assert result[0]["operations"][0]["nativeMember"] == "NPC.HitModifiers.Defense.Flat"
    assert "NPC.defense" != result[0]["operations"][0]["nativeMember"]
    assert npc_defense_fragments([I(i.offset, i.op, 2 if i.offset == 0 else i.arg) for i in native],
                                 {"Terraria.NPC.testFlag": "boolean"}) == []


def test_generated_report_regressions_are_source_derived_not_behavior_presets():
    import json
    report_path = ROOT / "contracts/reports/native_buff_effect_sources.generated.json"
    assert report_path.exists(), "source effect generator/report not implemented"
    report = json.loads(report_path.read_text())
    installed = next(s for s in report["sources"] if s["assemblySha256"] ==
                     "fcc6a9624b12191be4a15d714a3675440911feb8c1d374642ab1fd686f0da0a5")
    assert installed["sourceModuleVersionId"] == "033e87cd-cefe-4dc6-a1fb-e14aa938bbb2"
    def row(receiver, name):
        return next(r for r in installed["records"] if r["receiver"] == receiver and r["buffFullName"] == "Terraria/" + name)
    def operations(r):
        return [o for f in r["fragments"] for o in f["operations"]]
    assert any(o["nativeMember"] == "Terraria.Player.pickSpeed" and o["value"] == -0.25 for o in operations(row("player", "Mining")))
    assert any(o["nativeMember"] == "Terraria.Player.findTreasure" and o["value"] is True for o in operations(row("player", "Spelunker")))
    poisoned = row("npc", "Poisoned")
    assert poisoned["buffId"] == 20
    poison_op = next(o for o in operations(poisoned) if o["nativeMember"] == "Terraria.NPC.lifeRegen")
    assert poison_op["value"] == -12
    assert poison_op["unitEvidence"]["accumulatorUnitsPerHealthPoint"] == 120
    assert poison_op["nominalHpLossPerSecondAt60Updates"] == 6
    ichor = row("npc", "Ichor")
    assert any(o["nativeMember"] == "NPC.HitModifiers.Defense.Flat" and o["value"] == -15 for o in operations(ichor))
    assert all(r["completeness"] != "complete" and r["unsupported"] for r in installed["records"])
    assert len(installed["methods"]) >= 5


def test_regen_unit_evidence_requires_accumulator_threshold_and_guarded_one_hp_store():
    from native_buff_effect_analysis import npc_regen_unit_evidence
    unit = code([
        ("ldarg", 0), ("ldarg", 0), ("ldfld", "Terraria.NPC.lifeRegenCount"),
        ("ldarg", 0), ("ldfld", "Terraria.NPC.lifeRegen"), ("add",), ("stfld", "Terraria.NPC.lifeRegenCount"),
        ("br", "check"), ("label", "loop"),
        ("ldarg", 0), ("ldarg", 0), ("ldfld", "Terraria.NPC.lifeRegenCount"), ("const", 120),
        ("add",), ("stfld", "Terraria.NPC.lifeRegenCount"),
        ("ldarg", 0), ("ldfld", "Terraria.Entity.whoAmI"), ("stloc", 19),
        ("ldarg", 0), ("ldfld", "Terraria.NPC.realLife"), ("const", 0), ("blt", "target"),
        ("ldarg", 0), ("ldfld", "Terraria.NPC.realLife"), ("stloc", 19),
        ("label", "target"), ("ldsfld", "Terraria.Main.npc"), ("ldloc", 19), ("ldelem",),
        ("ldfld", "Terraria.NPC.immortal"), ("brtrue", "check"),
        ("ldsfld", "Terraria.Main.npc"), ("ldloc", 19), ("ldelem",), ("dup",),
        ("ldfld", "Terraria.NPC.life"), ("const", 1), ("sub",), ("stfld", "Terraria.NPC.life"),
        ("label", "check"), ("ldarg", 0), ("ldfld", "Terraria.NPC.lifeRegenCount"), ("const", -120), ("ble", "loop"), ("ret",),
    ])
    proof = npc_regen_unit_evidence(unit)
    assert proof["accumulatorUnitsPerHealthPoint"] == 120
    assert proof["healthPointsPerLoopBody"] == 1
    assert proof["targetRouting"] == "realLife_if_nonnegative_else_whoAmI"
    assert proof["damageCondition"] == "resolved_target.immortal == false"
    corrupt = [I(i.offset, i.op, -119 if i.op == "const" and i.arg == -120 else i.arg) for i in unit]
    assert npc_regen_unit_evidence(corrupt) is None


def test_boolean_zero_is_preserved_and_integer_one_is_not_claimed_as_boolean():
    from native_buff_effect_analysis import buff_type_branches
    body = [("ldarg", 0), ("const", 0), ("stfld", "Terraria.Player.testFlag")]
    result = buff_type_branches(buff_clause(body), "Player", {"Terraria.Player.testFlag": "boolean"})
    assert result[0]["operations"][0]["value"] is False
    assert buff_type_branches(buff_clause(body), "Player", {"Terraria.Player.testFlag": "int32"})[0]["operations"] == []


def test_full_scalar_body_declines_unknown_calls_branches_and_foreign_entries():
    from native_buff_effect_analysis import buff_type_branches
    body = [("ldarg", 0), ("ldarg", 0), ("ldfld", "Terraria.Player.testScalar"),
            ("const", 1.125), ("mul",), ("stfld", "Terraria.Player.testScalar")]
    types = {"Terraria.Player.testScalar": "float32"}
    result = buff_type_branches(buff_clause(body), "Player", types)
    assert result[0]["operations"][0]["operation"] == "multiply"
    assert result[0]["operations"][0]["units"] == "dimensionless_factor"
    for extra in [[("call", ("Unknown.Hook", 0, False, False))], [("ldsfld", "unknown"), ("brtrue", "end")]]:
        refused = buff_type_branches(buff_clause(body + extra), "Player", types)
        assert refused[0]["operations"] == []
        assert refused[0]["completeness"] == "unsupported"
    inject = [I(-1, "br", 6), *buff_clause(body)]
    assert buff_type_branches(inject, "Player", types)[0]["operations"] == []


def test_npc_reset_must_not_claim_a_flag_cleared_if_later_set_true():
    from generate_native_buff_effects import cleared_flags
    reset = code([("ldarg", 0), ("const", 0), ("stfld", "Terraria.NPC.testFlag"),
                  ("ldarg", 0), ("const", 1), ("stfld", "Terraria.NPC.testFlag"), ("ret",)])
    assert cleared_flags(reset, {"Terraria.NPC.testFlag": "boolean"}) == set()
    assert cleared_flags(code([("call", ("Unknown.Hook", 0, False, False)), ("ret",)]), {}) == set()


def test_catalog_render_is_reproducible_from_committed_source_report():
    import json
    from generate_native_buff_effects import render, OUTPUT, REPORT
    report = json.loads(REPORT.read_text())
    assert OUTPUT.read_text() == render(report["sources"])


def test_typed_array_write_keeps_index_without_inventing_buff_semantics():
    from native_buff_effect_analysis import buff_type_branches
    body = [("ldarg", 0), ("const", 1), ("stfld", "Terraria.Player.testFlag"),
            ("ldarg", 0), ("ldfld", "Terraria.Player.testArray"), ("const", 812),
            ("const", 0), ("stelem.i1",)]
    types = {"Terraria.Player.testFlag": "boolean", "Terraria.Player.testArray": "boolean_array"}
    rows = buff_type_branches(buff_clause(body), "Player", types)
    ops = rows[0]["operations"]
    assert len(ops) == 2 and ops[0]["value"] is True
    assert ops[1]["arrayIndex"] == 812 and ops[1]["value"] is False
    assert ops[1]["storageType"] == "boolean_array_element"
    # Same storage opcode may write signed bytes; only metadata proves bool[].
    assert buff_type_branches(buff_clause(body), "Player", {**types, "Terraria.Player.testArray": "int8_array"})[0]["operations"] == []
    dynamic = [*body[:5], ("ldloc", 7), *body[6:]]
    assert buff_type_branches(buff_clause(dynamic), "Player", types)[0]["operations"] == []


def test_struct_operator_is_preserved_as_a_call_not_guessed_final_stats():
    from native_buff_effect_analysis import buff_type_branches
    body = [("ldarg", 0), ("ldarg", 0), ("ldfld", "Terraria.Player.testStruct"),
            ("const", 8), ("call", ("Example.Counter.op_Addition", 2, False, True)),
            ("stfld", "Terraria.Player.testStruct")]
    types = {"Terraria.Player.testStruct": "value_type"}
    row = buff_type_branches(buff_clause(body), "Player", types)[0]
    op = row["operations"][0]
    assert op["operation"] == "operator_call_and_assign" and op["value"] == 8
    assert op["nativeOperator"] == "Example.Counter.op_Addition"
    assert op["units"] == "native_operator_argument"
    assert buff_type_branches(buff_clause(body), "Player", {})[0]["operations"] == []
    other_target = [*body[:-1], ("stfld", "Terraria.Player.other")]
    assert buff_type_branches(buff_clause(other_target), "Player", types)[0]["operations"] == []


def test_ref_getter_requires_matching_read_write_storage_and_operator_shape():
    from native_buff_effect_analysis import buff_type_branches
    body = [("ldarg", 0), ("call", ("Terraria.Player.get_example", 0, True, True)),
            ("dup",), ("ldobj", 1234), ("const", 0.2),
            ("call", ("Terraria.ModLoader.StatModifier.op_Addition", 2, False, True)), ("stobj", 1234)]
    ops = buff_type_branches(buff_clause(body), "Player", {})[0]["operations"]
    assert ops[0]["nativeMember"] == "Terraria.Player.get_example"
    assert ops[0]["operation"] == "operator_call_and_assign"
    assert buff_type_branches(buff_clause([*body[:-1], ("stobj", 5678)]), "Player", {})[0]["operations"] == []
    numeric = [*body[:3], ("ldind.r4",), ("const", 10.0), ("add",), ("stind.r4",)]
    op = buff_type_branches(buff_clause(numeric), "Player", {})[0]["operations"][0]
    assert op["operation"] == "add" and op["storageType"] == "ref_float32"
    assert buff_type_branches(buff_clause([*numeric[:-1], ("stind.i4",)]), "Player", {})[0]["operations"] == []
