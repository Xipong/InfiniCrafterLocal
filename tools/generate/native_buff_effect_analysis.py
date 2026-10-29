"""Read-only, bounded IL source-shape recognizers for buff operation fragments.

No BuffID/name routing, native execution, IL evaluation, or capability naming.
A fragment states what a certified branch writes *when control reaches it*, not
that the entire native update, downstream AI, or another mod has been decoded.
"""
from __future__ import annotations

import math


def pairs(code):
    return [(i.op, i.arg) for i in code]


def targets(ins):
    if ins.op == "switch":
        return ins.arg
    if ins.op.startswith("b") and isinstance(ins.arg, int):
        return [ins.arg]
    return []


def literal(ins):
    return ins.op == "const" and type(ins.arg) in (int, float) and math.isfinite(ins.arg)


def scalar_writes(block, owner, field_types):
    """Consume the entire straight-line block, or decline all its writes."""
    writes, n = [], 0
    while n < len(block):
        part = block[n:]
        if len(part) >= 5:
            a, b, index, value, store = part[:5]
            if ((a.op, a.arg) == ("ldarg", 0) and b.op == "ldfld"
                    and isinstance(b.arg, str) and b.arg.startswith("Terraria." + owner + ".")
                    and field_types.get(b.arg) == "boolean_array"
                    and index.op == "const" and type(index.arg) is int and index.arg >= 0
                    and value.op == "const" and type(value.arg) is int and value.arg in (0, 1)
                    and store.op == "stelem.i1"):
                writes.append({"nativeMember": b.arg, "arrayIndex": index.arg,
                               "operation": "assign", "value": bool(value.arg),
                               "units": "boolean_flag_only", "storageType": "boolean_array_element",
                               "sourceIlOffset": store.offset})
                n += 5
                continue
        if len(part) >= 3:
            a, b, c = part[:3]
            if ((a.op, a.arg) == ("ldarg", 0) and literal(b) and c.op == "stfld"
                    and isinstance(c.arg, str) and c.arg.startswith("Terraria." + owner + ".")
                    and field_types.get(c.arg) == "boolean" and b.arg in (0, 1)):
                writes.append({"nativeMember": c.arg, "operation": "assign", "value": bool(b.arg),
                               "units": "boolean_flag_only", "storageType": "boolean", "sourceIlOffset": c.offset})
                n += 3
                continue
        if len(part) >= 6:
            a, b, c, d, e, f = part[:6]
            storage = field_types.get(c.arg) if c.op == "ldfld" else None
            if (pairs([a, b]) == [("ldarg", 0), ("ldarg", 0)]
                    and isinstance(c.arg, str) and c.arg.startswith("Terraria." + owner + ".")
                    and storage == "value_type" and literal(d) and e.op == "call"
                    and e.arg[1:] == (2, False, True)
                    and e.arg[0].endswith((".op_Addition", ".op_Subtraction", ".op_Multiply"))
                    and (f.op, f.arg) == ("stfld", c.arg)):
                writes.append({"nativeMember": c.arg, "operation": "operator_call_and_assign",
                               "nativeOperator": e.arg[0], "value": d.arg,
                               "units": "native_operator_argument", "storageType": storage,
                               "sourceIlOffset": f.offset})
                n += 6
                continue
            if (pairs([a, b]) == [("ldarg", 0), ("ldarg", 0)]
                    and isinstance(c.arg, str) and c.arg.startswith("Terraria." + owner + ".")
                    and storage in ("int32", "float32", "float64") and literal(d)
                    and e.op in ("add", "sub", "mul") and (f.op, f.arg) == ("stfld", c.arg)):
                writes.append({"nativeMember": c.arg, "operation": "multiply" if e.op == "mul" else "add",
                               "value": -d.arg if e.op == "sub" else d.arg,
                               "units": "dimensionless_factor" if e.op == "mul" else "native_member_units",
                               "storageType": storage, "sourceIlOffset": f.offset})
                n += 6
                continue
        if len(part) >= 7:
            a, getter, dup, read, value, op, store = part[:7]
            if ((a.op, a.arg) == ("ldarg", 0) and getter.op == "call"
                    and getter.arg[0].startswith("Terraria." + owner + ".")
                    and getter.arg[1:] == (0, True, True) and dup.op == "dup" and literal(value)):
                if (read.op in ("ldind.r4", "ldind.i4") and op.op in ("add", "sub", "mul")
                        and store.op == {"ldind.r4": "stind.r4", "ldind.i4": "stind.i4"}[read.op]):
                    writes.append({"nativeMember": getter.arg[0], "operation": "multiply" if op.op == "mul" else "add",
                                   "value": -value.arg if op.op == "sub" else value.arg,
                                   "units": "dimensionless_factor" if op.op == "mul" else "native_member_units",
                                   "storageType": "ref_float32" if read.op == "ldind.r4" else "ref_int32",
                                   "sourceIlOffset": store.offset})
                    n += 7
                    continue
                if (read.op == "ldobj" and store.op == "stobj"
                        and getattr(read.arg, "value", read.arg) == getattr(store.arg, "value", store.arg)
                        and op.op == "call" and op.arg[1:] == (2, False, True)
                        and op.arg[0].endswith((".op_Addition", ".op_Subtraction", ".op_Multiply"))):
                    writes.append({"nativeMember": getter.arg[0], "operation": "operator_call_and_assign",
                                   "nativeOperator": op.arg[0], "value": value.arg,
                                   "units": "native_operator_argument", "storageType": "ref_value_type",
                                   "sourceIlOffset": store.offset})
                    n += 7
                    continue
        return None
    return writes or None


def buff_type_branches(code, owner, field_types):
    """Recognize equality tests and entire straight-line fallthrough bodies.

    Never erase unresolved enclosing guards: reaching the literal test remains
    an explicit precondition. Reject foreign edges into the test/body interior.
    This deliberately does not claim all effects of any buff have been found.
    """
    positions = {i.offset: n for n, i in enumerate(code)}
    rows = []
    for start in range(len(code) - 6):
        a, b, slot, elem, value, branch = code[start:start + 6]
        if (pairs([a, b]) != [("ldarg", 0), ("ldfld", "Terraria." + owner + ".buffType")]
                or slot.op != "ldloc" or elem.op != "ldelem" or value.op != "const"
                or type(value.arg) is not int or value.arg <= 0 or branch.op != "bne"
                or branch.arg not in positions or branch.arg <= branch.offset):
            continue
        stop = positions[branch.arg]
        block = code[start + 6:stop]
        if block and block[-1].op == "br" and block[-1].arg >= branch.arg:
            block = block[:-1]
        unsafe = any(a.offset < t < branch.arg for ins in code
                     if not a.offset <= ins.offset < branch.arg for t in targets(ins))
        writes = None if unsafe else scalar_writes(block, owner, field_types)
        rows.append({"buffId": value.arg, "condition": {
            "buffTypeEquals": value.arg, "slotLocal": slot.arg,
            "nativeControlFlowMustReachTest": a.offset, "testBranchIlOffset": branch.offset,
            "conditionScope": "literal_test_and_straight_line_body_only; enclosing native guards remain required"},
            "operations": writes or [],
            "completeness": "partial_native_statement_fragment" if writes else "unsupported",
            "unsupported": (["enclosing_path_and_downstream_consumers_not_fully_analyzed", "other_native_and_mod_effects_unknown"]
                            if writes else ["foreign_control_entry" if unsafe else "body_outside_scalar_write_subset"])})
    return rows


def npc_defense_fragments(code, field_types):
    """Read only literal HitModifiers.Defense.Flat writes under arg3's gate.

    The generator checks arg3's metadata name/signature separately. This is a
    hit-local defense contribution, NOT a persistent write to NPC.defense.
    """
    p, rows = pairs(code), []
    for start in range(len(code) - 12):
        if p[start] != ("ldarg", 3) or code[start + 1].op != "brtrue":
            continue
        end = next((k for k in range(start + 2, len(code)) if code[k].offset == code[start + 1].arg), None)
        if end is None:
            continue
        n, found = start + 2, []
        while n < end:
            if n + 11 > end:
                break
            a, b, branch = code[n:n + 3]
            q = p[n + 3:n + 11]
            if ((a.op, a.arg) != ("ldarg", 0) or b.op != "ldfld"
                    or field_types.get(b.arg) != "boolean" or branch.op != "brfalse"
                    or branch.arg != code[n + 11].offset
                    or q[:5] != [("ldloca", 0), ("ldflda", ".HitModifiers.Defense"),
                                   ("ldflda", "Terraria.ModLoader.StatModifier.Flat"), ("dup", None), ("ldind.r4", None)]
                    or not literal(code[n + 8]) or q[6:] != [("sub", None), ("stind.r4", None)]):
                break
            found.append({"flagMember": b.arg, "condition": {"ignoreArmorDebuffs": False, "flagEquals": True,
                          "nativeControlFlowMustReachTest": code[start].offset},
                          "sourceFlagTestIlOffset": branch.offset,
                          "operations": [{"nativeMember": "NPC.HitModifiers.Defense.Flat", "operation": "add",
                                          "value": -code[n + 8].arg, "units": "defense_points", "storageType": "float32",
                                          "sourceIlOffset": code[n + 10].offset}]})
            n += 11
        foreign = any(code[start].offset < t < code[end].offset for ins in code
                      if not start <= code.index(ins) < end for t in targets(ins))
        if n == end and not foreign:
            rows.extend(found)
    return rows


def npc_dot_fragments(code, field_types):
    """Only the flat prefix after the exact damageability early-return guard.

    Recognize flag -> clear positive regen -> subtract literal, optionally a
    display-damage lower bound. Stop before any complex condition/call/loop;
    do not resume scanning inside unknown outer control flow.
    """
    p = pairs(code)
    if len(code) < 7 or p[:3] != [("ldarg", 0), ("ldfld", "Terraria.NPC.dontTakeDamage"), ("brfalse", code[4].offset)] or p[3] != ("ret", None):
        return []
    if p[4:7] != [("ldarg", 0), ("ldfld", "Terraria.NPC.lifeRegenExpectedLossPerSecond"), ("stloc", 0)]:
        return []
    rows, n = [], 7
    while n + 16 <= len(code):
        a, b, branch = code[n:n + 3]
        if ((a.op, a.arg) != ("ldarg", 0) or b.op != "ldfld"
                or field_types.get(b.arg) != "boolean" or branch.op != "brfalse"):
            break
        end = next((k for k in range(n + 3, len(code)) if code[k].offset == branch.arg), None)
        if end is None:
            break
        q = p[n + 3:end]
        clear = [("ldarg", 0), ("ldfld", "Terraria.NPC.lifeRegen"), ("const", 0),
                 ("ble", code[n + 10].offset), ("ldarg", 0), ("const", 0), ("stfld", "Terraria.NPC.lifeRegen")]
        if (len(q) not in (13, 18) or q[:7] != clear
                or q[7:10] != [("ldarg", 0), ("ldarg", 0), ("ldfld", "Terraria.NPC.lifeRegen")]
                or not literal(code[n + 13]) or type(code[n + 13].arg) is not int or code[n + 13].arg <= 0
                or q[11:13] != [("sub", None), ("stfld", "Terraria.NPC.lifeRegen")]):
            break
        display = None
        if len(q) == 18:
            low = code[n + 17]
            if (q[13] != ("ldloc", 0) or not literal(low) or type(low.arg) is not int or low.arg < 0
                    or q[15:] != [("bge", branch.arg), ("const", low.arg), ("stloc", 0)]):
                break
            display = low.arg
        op = {"nativeMember": "Terraria.NPC.lifeRegen", "operation": "add", "value": -code[n + 13].arg,
              "units": "native_lifeRegen_units", "storageType": "int32", "clampPositiveToZeroFirst": True,
              "sourceIlOffset": code[n + 15].offset}
        row = {"flagMember": b.arg, "condition": {"Terraria.NPC.dontTakeDamage": False, "flagEquals": True},
               "operations": [op], "sourceFlagTestIlOffset": branch.offset}
        if display is not None:
            row["displayDamageLowerBound"] = display
        rows.append(row)
        n = end
    # A tail jump into this prefix could bypass the preserved entry guards.
    if any(code[0].offset < t < code[n].offset for ins in code[n:] for t in targets(ins)):
        return []
    return rows


def npc_regen_unit_evidence(code):
    """Prove local negative-regen accumulator/one-HP source-unit relation.

    Do not claim final damage: resolved target immortality, segmented-NPC
    routing, other contributions/hooks and actual update scheduling still apply.
    """
    p = pairs(code)
    accumulate = [("ldarg", 0), ("ldarg", 0), ("ldfld", "Terraria.NPC.lifeRegenCount"),
                  ("ldarg", 0), ("ldfld", "Terraria.NPC.lifeRegen"), ("add", None), ("stfld", "Terraria.NPC.lifeRegenCount")]
    sites = [n for n in range(len(p) - 6) if p[n:n + 7] == accumulate]
    if len(sites) != 1 or len(code) < 5 or p[-5:-3] != [("ldarg", 0), ("ldfld", "Terraria.NPC.lifeRegenCount")]:
        return None
    threshold, repeat, ret = code[-3:]
    if threshold.op != "const" or type(threshold.arg) is not int or threshold.arg >= 0 or repeat.op != "ble" or ret.op != "ret":
        return None
    start = next((n for n, i in enumerate(code) if i.offset == repeat.arg), None)
    if start is None or start + 29 >= len(code):
        return None
    q = p[start:]
    step = -threshold.arg
    if (q[:6] != [("ldarg", 0), ("ldarg", 0), ("ldfld", "Terraria.NPC.lifeRegenCount"), ("const", step), ("add", None), ("stfld", "Terraria.NPC.lifeRegenCount")]
            or q[6:8] != [("ldarg", 0), ("ldfld", "Terraria.Entity.whoAmI")] or q[8][0] != "stloc"):
        return None
    slot = q[8][1]
    if (q[9:16] != [("ldarg", 0), ("ldfld", "Terraria.NPC.realLife"), ("const", 0), ("blt", code[start + 16].offset),
                     ("ldarg", 0), ("ldfld", "Terraria.NPC.realLife"), ("stloc", slot)]
            or q[16:20] != [("ldsfld", "Terraria.Main.npc"), ("ldloc", slot), ("ldelem", None), ("ldfld", "Terraria.NPC.immortal")]
            or q[20] != ("brtrue", code[start + 29].offset)
            or q[21:29] != [("ldsfld", "Terraria.Main.npc"), ("ldloc", slot), ("ldelem", None), ("dup", None),
                            ("ldfld", "Terraria.NPC.life"), ("const", 1), ("sub", None), ("stfld", "Terraria.NPC.life")]):
        return None
    return {"accumulatorUnitsPerHealthPoint": step, "healthPointsPerLoopBody": 1,
            "accumulatorAddIlOffset": code[sites[0] + 6].offset,
            "negativeAccumulatorStepIlOffset": code[start + 5].offset,
            "healthStoreIlOffset": code[start + 28].offset, "loopCheckIlOffset": repeat.offset,
            "targetRouting": "realLife_if_nonnegative_else_whoAmI", "damageCondition": "resolved_target.immortal == false",
            "scope": "Local accumulator and one-HP decrement source relation only; actual cadence, other contributions, hooks, grouping and final HP loss are not guaranteed."}
