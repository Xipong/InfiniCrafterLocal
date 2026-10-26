"""Recognize straight-line native equipment additions under literal item guards.

This is a source-shape recognizer, not an interpreter. Unknown branches, calls,
control-flow entries, nested context or numeric transformations refuse a record.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import chain

PLAYER = ("ldarg", 0)
# Names identify native state, not generated capabilities or inheritance rules.
GETTERS = {
    "allCrit": ("critChance", "generic", "percentage_points"),
    "meleeCrit": ("critChance", "melee", "percentage_points"),
    "rangedCrit": ("critChance", "ranged", "percentage_points"),
    "magicCrit": ("critChance", "magic", "percentage_points"),
    "meleeSpeed": ("attackSpeed", "melee", "additive_fraction"),
    "armorPenetration": ("armorPenetration", "generic", "points"),
    "allDamage": ("damage", "generic", "additive_fraction"),
    "meleeDamage": ("damage", "melee", "additive_fraction"),
    "rangedDamage": ("damage", "ranged", "additive_fraction"),
    "magicDamage": ("damage", "magic", "additive_fraction"),
    "minionDamage": ("damage", "summon", "additive_fraction"),
}
FIELDS = {
    "pickSpeed": ("pickUseTimeMultiplier", "additive_fraction"),
    "whipRangeMultiplier": ("whipRangeMultiplier", "additive_fraction"),
    "fishingSkill": ("fishingPower", "points"),
    "moveSpeed": ("movementSpeed", "additive_fraction"),
    "statManaMax2": ("maximumMana", "points"),
    "maxMinions": ("maximumMinions", "slots"),
    "maxTurrets": ("maximumSentries", "slots"),
    "lifeRegen": ("lifeRegeneration", "native_half_hp_per_second_units"),
    "manaCost": ("manaCostMultiplier", "additive_fraction"),
    "manaRegenBonus": ("manaRegenerationBonus", "native_units"),
    "aggro": ("aggro", "native_units"),
    "endurance": ("damageReduction", "additive_fraction"),
}


def _targets(ins):
    if ins.op == "switch":
        return ins.arg
    if ins.op.startswith("b") and isinstance(ins.arg, int):
        return [ins.arg]
    return []


def guarded_blocks(code):
    """Flat (type==A || type==B) blocks, declining enclosing context guards."""
    code = [i for i in code if i.op != "nop"]
    for start in range(len(code) - 4):
        if any(ins.op == "ret" for ins in code[:start]):
            continue
        cursor, ids, joins = start, [], []
        while cursor + 4 <= len(code):
            a, b, c, d = code[cursor : cursor + 4]
            if ((a.op, a.arg), (b.op, b.arg), c.op) != (("ldarg", 1), ("ldfld", "Terraria.Item.type"), "const") or not isinstance(
                c.arg, int
            ):
                break
            ids.append(c.arg)
            if d.op == "beq":
                joins.append(d.arg)
                cursor += 4
                continue
            if d.op != "bne" or d.arg <= d.offset:
                break
            body_start = cursor + 4
            if body_start >= len(code) or any(t != code[body_start].offset for t in joins):
                break
            end = d.arg
            body = [i for i in code[body_start:] if i.offset < end]
            if not body:
                break
            # A guard may not be nested under an earlier unknown condition, or
            # entered in its middle by another dispatch/branch.
            first = code[start].offset
            unsafe = False
            for n, ins in enumerate(code):
                if start <= n < body_start:
                    continue
                for target in _targets(ins):
                    if ins.offset < first and target > first and target >= end:
                        unsafe = True
                    if target <= first and ins.offset >= end:
                        unsafe = True
                    if not first <= ins.offset < end and first < target < end:
                        unsafe = True
            if not unsafe:
                yield tuple(ids), d.offset, body
            break


def guarded_range_blocks(code):
    """Two signed inclusive Item.type comparisons, not a name-derived family."""
    code = [i for i in code if i.op != "nop"]
    for start in range(len(code) - 8):
        if any(i.op == "ret" for i in code[:start]):
            continue
        a, b, lo, lower, e, f, hi, upper = code[start:start + 8]
        if ((a.op, a.arg), (b.op, b.arg), (e.op, e.arg), (f.op, f.arg)) != (
                ("ldarg", 1), ("ldfld", "Terraria.Item.type"), ("ldarg", 1), ("ldfld", "Terraria.Item.type")):
            continue
        if (lo.op != "const" or hi.op != "const" or not isinstance(lo.arg, int) or not isinstance(hi.arg, int)
                or not 0 < lo.arg <= hi.arg < 10000 or hi.arg - lo.arg >= 32
                or lower.op != "blt" or upper.op != "bgt" or lower.arg != upper.arg
                or not isinstance(upper.arg, int) or upper.arg <= upper.offset):
            continue
        first, end = a.offset, upper.arg
        body = [i for i in code[start + 8:] if i.offset < end]
        if not body:
            continue
        unsafe = False
        for n, ins in enumerate(code):
            if start <= n < start + 8:
                continue
            for target in _targets(ins):
                if (ins.offset < first and target > first and target >= end
                        or target <= first and ins.offset >= end
                        or not first <= ins.offset < end and first < target < end):
                    unsafe = True
        if not unsafe:
            yield tuple(range(lo.arg, hi.arg + 1)), upper.offset, body


def _constant(ins):
    return ins.op == "const" and isinstance(ins.arg, (float, int)) and abs(ins.arg) <= 10000


def _rounded(value):
    return round(float(value), 7) if isinstance(value, float) else value


def additions(block):
    """Consume the WHOLE block: no unrelated side effects or hidden gates."""
    result, n = [], 0
    while n < len(block):
        tail = block[n:]
        # player.field += constant / -= constant
        if len(tail) >= 6:
            a, b, c, d, e, f = tail[:6]
            field = c.arg.removeprefix("Terraria.Player.") if c.op == "ldfld" and isinstance(c.arg, str) else ""
            if (
                ((a.op, a.arg), (b.op, b.arg)) == (PLAYER, PLAYER)
                and field in FIELDS
                and _constant(d)
                and e.op in ("add", "sub")
                and (f.op, f.arg) == ("stfld", c.arg)
            ):
                name, units = FIELDS[field]
                result.append(
                    {
                        "stat": name,
                        "nativeMember": c.arg,
                        "operation": "add",
                        "value": _rounded(d.arg * (-1 if e.op == "sub" else 1)),
                        "units": units,
                        "ilOffset": f.offset,
                    }
                )
                n += 6
                continue
        # ref float getter: player.allCrit += 5
        if len(tail) >= 7:
            a, b, c, d, e, f, g = tail[:7]
            getter = b.arg[0].removeprefix("Terraria.Player.get_") if b.op == "call" else ""
            if (
                (a.op, a.arg) == PLAYER
                and getter in GETTERS
                and b.arg[1:] == (0, True, True)
                and c.op == "dup"
                and d.op in ("ldind.r4", "ldind.i4")
                and _constant(e)
                and f.op in ("add", "sub")
                and g.op in ("stind.r4", "stind.i4")
            ):
                stat, cls, units = GETTERS[getter]
                result.append(
                    {
                        "stat": stat,
                        "damageClass": cls,
                        "nativeMember": b.arg[0],
                        "operation": "add",
                        "value": _rounded(e.arg * (-1 if f.op == "sub" else 1)),
                        "units": units,
                        "ilOffset": g.offset,
                    }
                )
                n += 7
                continue
            # StatModifier getter + constant is its Additive component, not multiplication.
            if (
                (a.op, a.arg) == PLAYER
                and getter in GETTERS
                and b.arg[1:] == (0, True, True)
                and c.op == "dup"
                and d.op == "ldobj"
                and _constant(e)
                and f.op == "call"
                and f.arg == ("Terraria.ModLoader.StatModifier.op_Addition", 2, False, True)
                and g.op == "stobj"
            ):
                stat, cls, units = GETTERS[getter]
                result.append(
                    {
                        "stat": stat,
                        "damageClass": cls,
                        "nativeMember": b.arg[0],
                        "operation": "add",
                        "value": _rounded(e.arg),
                        "units": units,
                        "ilOffset": g.offset,
                    }
                )
                n += 7
                continue
        # Literal field true/false assignment is a state flag, not invented mechanics.
        if len(tail) >= 3:
            a, b, c = tail[:3]
            if (
                (a.op, a.arg) == PLAYER
                and b.op == "const"
                and b.arg in (0, 1)
                and c.op == "stfld"
                and isinstance(c.arg, str)
                and c.arg.startswith("Terraria.Player.")
            ):
                # Preserve only known Boolean metadata supplied by the decoder.
                if c.arg.endswith(":bool"):
                    result.append(
                        {
                            "nativeMember": c.arg[:-5],
                            "operation": "set",
                            "value": bool(b.arg),
                            "units": "boolean_state",
                            "ilOffset": c.offset,
                        }
                    )
                    n += 3
                    continue
        return []
    return result


def conditioned_additions(block, end):
    """One literal Boolean gate, retaining independent straight-line additions.

    Entire branch consumption is still mandatory. This does not evaluate world
    or player state, split opaque calls, or flatten nested conditions.
    """
    gates = []
    for n, ins in enumerate(block):
        if ins.op == "ldsfld" and isinstance(ins.arg, str) and ins.arg.startswith("Terraria.Main.") and ins.arg.endswith(":bool"):
            gates.append((n, n + 1, ins.arg))
        elif (ins.op, ins.arg) == PLAYER and n + 1 < len(block):
            field = block[n + 1]
            if field.op == "ldfld" and isinstance(field.arg, str) and field.arg.startswith("Terraria.Player.") and field.arg.endswith(":bool"):
                gates.append((n, n + 2, field.arg))
    if not gates:
        effects = additions(block)
        return {"effects": effects} if effects else None
    if len(gates) != 1:
        return None
    start, at, member = gates[0]
    if at >= len(block) or block[at].op not in ("brfalse", "brtrue"):
        return None
    branch = block[at]
    # The gate must enclose a complete nonempty suffix of the item branch.
    # Decline short-circuit chains, inner joins, loops and unknown control flow.
    if branch.arg != end:
        return None
    before, conditional = additions(block[:start]), additions(block[at + 1:])
    if (start and not before) or not conditional:
        return None
    return {"effects": before, "conditionalEffects": [{
        "condition": {"nativeMember": member[:-5], "equals": branch.op == "brfalse", "observed": False},
        "guardIlOffset": branch.offset, "effects": conditional}]}


def equipment_facts(code):
    records = defaultdict(list)
    for ids, guard, block in chain(guarded_blocks(code), guarded_range_blocks(code)):
        end = next((i.offset for i in code if i.offset > block[-1].offset), None)
        contributions = conditioned_additions(block, end)
        if contributions is not None:
            for identity in ids:
                records[identity].append({"guardIlOffset": guard, **contributions})
    return [
        {"itemId": identity, "condition": "equipped_functional_item_during_GrantArmorBenefits", "branches": branches}
        for identity, branches in sorted(records.items())
    ]


def armor_set_facts(code):
    """Recognize conjunctions of three literal equip-slot equality groups.

    Slot identifiers are deliberately not ItemIDs. OR alternatives allow mixed
    matching variants; no set identity or bonus is inferred from item names.
    """
    code = [i for i in code if i.op != "nop"]
    result = []
    for start in range(len(code) - 12):
        if any(ins.op == "ret" for ins in code[:start]):
            continue
        cursor, groups, exits = start, {}, []
        for _ in range(3):
            choices, joins, field = [], [], None
            while cursor + 4 <= len(code):
                a, b, c, d = code[cursor : cursor + 4]
                if (
                    (a.op, a.arg) != PLAYER
                    or b.op != "ldfld"
                    or b.arg not in ("Terraria.Player.head", "Terraria.Player.body", "Terraria.Player.legs")
                    or not _constant(c)
                    or not isinstance(c.arg, int)
                    or c.arg < 0
                ):
                    break
                if field is not None and b.arg != field:
                    break
                field = b.arg
                choices.append(c.arg)
                if d.op == "beq":
                    joins.append(d.arg)
                    cursor += 4
                    continue
                if d.op != "bne" or d.arg <= d.offset:
                    break
                cursor += 4
                if cursor >= len(code) or any(t != code[cursor].offset for t in joins):
                    break
                if field in groups:
                    break
                groups[field] = choices
                exits.append(d.arg)
                break
            else:
                break
            if len(groups) != _ + 1:
                break
        if len(groups) != 3 or len(set(exits)) != 1:
            continue
        end = exits[0]
        if end <= code[cursor].offset:
            continue
        body = [i for i in code[cursor:] if i.offset < end]
        first = code[start].offset
        unsafe = False
        for n, ins in enumerate(code):
            if start <= n < cursor:
                continue
            for target in _targets(ins):
                if ins.offset < first and target > first and target >= end:
                    unsafe = True
                if target <= first and ins.offset >= end:
                    unsafe = True
                if not first <= ins.offset < end and first < target < end:
                    unsafe = True
        if unsafe:
            continue
        key = None
        if len(body) >= 4:
            a, b, c, d = body[:4]
            if (
                (a.op, a.arg) == PLAYER
                and b.op == "ldstr"
                and isinstance(b.arg, str)
                and b.arg.startswith("ArmorSetBonus.")
                and c.op == "call"
                and c.arg == ("Terraria.Localization.Language.GetTextValue", 1, False, True)
                and (d.op, d.arg) == ("stfld", "Terraria.Player.setBonus")
            ):
                key = b.arg
                body = body[4:]
        effects = additions(body)
        if not effects or key is None:
            continue
        result.append(
            {
                "condition": {
                    "functionalEquipSlots": {field.rsplit(".", 1)[1]: choices for field, choices in groups.items()},
                    "allSlotsRequired": True,
                    "vanitySatisfies": False,
                },
                "setBonusLocalizationKey": key,
                "effects": effects,
                "guardIlOffset": code[start].offset,
            }
        )
    return result
