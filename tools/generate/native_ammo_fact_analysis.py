"""Bounded IL source shapes for ammo projectile rewrites; never execute game code.

Only complete literal assignment blocks and equality-guarded literal assignments
are certificates. Spawn arguments are source references, not simulated gameplay.
"""
from __future__ import annotations

from native_attack_fact_analysis import Unrecognized, direct_call_count, straight_line_arguments, type_blocks


def adjusted_counted_spawn(block, call_offset):
    """One unit-step loop; literal initial bound with bounded +/- updates.

    Return conservative bounds, not probabilities or simulated branch choices.
    """
    back = [(n, i) for n, i in enumerate(block) if i.op.startswith("b") and isinstance(i.arg, int) and i.arg < i.offset]
    if len(back) != 1 or back[0][1].op != "blt":
        return None
    end, branch = back[0]
    left, right = block[end - 2:end]
    if left.op != "ldloc" or right.op != "ldloc" or left.arg == right.arg:
        return None
    start = next(n for n, i in enumerate(block) if i.offset == branch.arg)
    body = block[start:end - 2]
    if [(i.op, i.arg) for i in body[-4:]] != [("ldloc", left.arg), ("const", 1), ("add", None), ("stloc", left.arg)]:
        return None
    if any(i.op == "ldloca" and i.arg in (left.arg, right.arg) for i in block):
        return None
    counter_stores = [(n, i) for n, i in enumerate(block) if i.op == "stloc" and i.arg == left.arg]
    if len(counter_stores) != 2 or counter_stores[0][0] >= start or (block[counter_stores[0][0] - 1].op, block[counter_stores[0][0] - 1].arg) != ("const", 0):
        return None
    low = high = None
    for n, ins in enumerate(block):
        if ins.op != "stloc" or ins.arg != right.arg:
            continue
        if n >= start:
            return None
        if low is None and block[n - 1].op == "const":
            low = high = block[n - 1].arg
        elif low is not None and [(i.op, i.arg) for i in block[n - 3:n - 1]] == [("ldloc", right.arg), ("const", 1)] and block[n - 1].op in ("add", "sub"):
            if block[n - 1].op == "add": high += 1
            else: low -= 1
        else:
            return None
    if low is None or not 0 < low <= high <= 64:
        return None
    try:
        direct_call_count(body, call_offset)
    except Unrecognized:
        return None
    return {"minimum": low, "maximum": high,
            "distribution": "unmodeled_native_conditions_conservative_bounds",
            "scope": "Per reached native branch on terminating loop paths, not cadence, unconditional shot admission or a fixed count"}


def default_ammo_selection(instructions, categories):
    """Prove the complete table -> offsets -> positive-ammo/default decision chain.

    Matching isolated stores cannot prove which arm wins. Consume every arm,
    its fallthrough and common join; refuse foreign entries or extra branches.
    """
    code = [i for i in instructions if i.op != "nop"]
    calls = [n for n, i in enumerate(code) if i.op == "call"
             and i.arg == ("Terraria.Player.PickAmmo_TryFindingSpecificMatches", 3, True, True)]
    if len(calls) != 1:
        raise ValueError("unrecognized native ammo table lookup")
    at = calls[0]
    prefix = [("ldarg", 0), ("ldarg", 1), ("ldfld", "Terraria.Item.type"),
              ("ldloc", 0), ("ldfld", "Terraria.Item.type")]
    if (at < 6 or [(i.op, i.arg) for i in code[at - 6:at - 1]] != prefix
            or code[at - 1].op != "ldloca"):
        raise ValueError("unrecognized native ammo lookup arguments")
    start = at - 6
    out_local = code[at - 1].arg
    tail = code[at + 1:at + 6]
    if (len(tail) != 5 or tail[0].op != "brfalse"
            or [(i.op, i.arg) for i in tail[1:4]] != [("ldarg", 2), ("ldloc", out_local), ("stind.i4", None)]
            or tail[4].op != "br"):
        raise ValueError("unrecognized native ammo table arm")
    join, cursor = tail[4].arg, at + 6
    if cursor >= len(code) or code[cursor].offset != tail[0].arg:
        raise ValueError("native ammo table fallthrough")
    offsets = []
    while cursor < len(code) and code[cursor].offset < join:
        arm = code[cursor:cursor + 12]
        if len(arm) < 12 or [(i.op, i.arg) for i in arm[:2]] != [("ldarg", 1), ("ldfld", "Terraria.Item.useAmmo")]:
            break
        category, guard = arm[2:4]
        if (category.op != "ldsfld" or category.arg not in categories or guard.op != "bne"
                or [(i.op, i.arg) for i in arm[4:11]] != [
                    ("ldarg", 2), ("ldarg", 2), ("ldind.i4", None), ("ldloc", 0),
                    ("ldfld", "Terraria.Item.shoot"), ("add", None), ("stind.i4", None)]
                or (arm[11].op, arm[11].arg) != ("br", join)
                or cursor + 12 >= len(code) or code[cursor + 12].offset != guard.arg):
            raise ValueError("unrecognized native ammo category arm")
        offsets.append({"ammoCategoryId": categories[category.arg], "nativeCategoryField": category.arg,
                        "operation": "weapon_shoot_plus_ammo_shoot", "sourceStoreIlOffset": arm[10].offset})
        cursor += 12
    arm = code[cursor:cursor + 8]
    if (len(arm) != 8 or [(i.op, i.arg) for i in arm] != [
            ("ldloc", 0), ("ldfld", "Terraria.Item.shoot"), ("const", 0), ("ble", join),
            ("ldarg", 2), ("ldloc", 0), ("ldfld", "Terraria.Item.shoot"), ("stind.i4", None)]
            or cursor + 8 >= len(code) or code[cursor + 8].offset != join):
        raise ValueError("unrecognized native default ammo arm")
    first = code[start].offset
    for ins in code:
        targets = ins.arg if ins.op == "switch" else [ins.arg] if ins.op.startswith("b") and isinstance(ins.arg, int) else []
        if not first <= ins.offset < join and any(first < target < join for target in targets):
            raise ValueError("foreign entry into native ammo selection")
    return {"basis": "positive_selected_ammo_shoot", "ammoShootStoreIlOffset": arm[-1].offset,
            "specificMatchLookupFirst": True, "nonPositiveAmmoShoot": "retain_weapon_shoot",
            "categoryOffsetSelectors": offsets,
            "scope": "Complete source decision chain: current specific-match table, then category offsets, then positive ammo.shoot or retained weapon.shoot. Later native/player/ammo hooks remain separate."}


def item_type_mentions(instructions, item_argument):
    return sorted({c.arg for a, b, c in zip(instructions, instructions[1:], instructions[2:])
                   if (a.op, a.arg, b.op, b.arg, c.op) == ("ldarg", item_argument, "ldfld", "Terraria.Item.type", "const")
                   and isinstance(c.arg, int)})


def literal_rewrite(code, target):
    code = [i for i in code if i.op != "nop"]
    kind, slot = target
    read = [("ldarg", slot), ("ldind.i4", None)] if kind == "argument" else [("ldloc", slot)]
    write_prefix = [("ldarg", slot)] if kind == "argument" else []
    store = "stind.i4" if kind == "argument" else "stloc"
    pairs = [(i.op, i.arg) for i in code]
    condition = None
    cursor = 0
    if pairs[:len(read)] == read and len(code) > len(read) + 1 and code[len(read)].op == "const":
        branch = code[len(read) + 1]
        if branch.op != "bne" or branch.arg <= branch.offset:
            return None
        condition = code[len(read)].arg
        cursor = len(read) + 2
    body = code[cursor:]
    expected = len(write_prefix) + 2
    # A return/jump is allowed only after the assignment, never into its interior.
    if len(body) == expected + 1 and body[-1].op in ("ret", "br"):
        body = body[:-1]
    if len(body) != expected or [(i.op, i.arg) for i in body[:len(write_prefix)]] != write_prefix:
        return None
    literal, assignment = body[-2:]
    if literal.op != "const" or not isinstance(literal.arg, int) or literal.arg <= 0:
        return None
    if assignment.op != store or (kind == "local" and assignment.arg != slot):
        return None
    if condition is not None and code[len(read) + 1].arg <= assignment.offset:
        return None
    rule = {"outputProjectileId": literal.arg, "sourceStoreIlOffset": assignment.offset}
    if condition is not None:
        rule["whenInputProjectileId"] = condition
    return [rule]


def ammo_method_facts(instructions, method):
    code = [i for i in instructions if i.op != "nop"]
    pick = method == "PickAmmo"
    if pick:
        target, item_arg = ("argument", 2), 1
    else:
        locals_ = [c.arg for a, b, c in zip(code, code[1:], code[2:])
                   if (a.op, a.arg, b.op, b.arg, c.op) == ("ldarg", 2, "ldfld", "Terraria.Item.shoot", "stloc")]
        if len(locals_) != 1:
            raise ValueError("unknown native shot-projectile local")
        target, item_arg = ("local", locals_[0]), 2
    rows = {}
    for item_id, guard, block in type_blocks(code, "Terraria.Item.type", item_arg):
        row = rows.setdefault(item_id, {"itemId": item_id, "rules": [], "spawnSites": [], "spawnOriginSetups": [], "unrecognizedProjectileWriteOffsets": []})
        for n in range(5, len(block)):
            call = block[n]
            if call.op != "call" or call.arg[0] != "Microsoft.Xna.Framework.Vector2..ctor":
                continue
            prefix = block[n - 5:n]
            if ([(i.op, i.arg) for i in prefix[:3]] == [
                ("ldarg", 0), ("call", ("Terraria.Player.get_MountedCenter", 0, True, True)),
                ("ldfld", "Microsoft.Xna.Framework.Vector2.Y")]
                and prefix[3].op == "const" and prefix[4].op == "sub"):
                row["spawnOriginSetups"].append({"sourceConstructorIlOffset": call.offset,
                    "initialYRelativeToMountedCenterPx": -prefix[3].arg,
                    "scope": "Vector2 constructor Y argument inside this native spawn branch; later origin mutations, X coordinate and final spawn position not modeled"})
        rules = literal_rewrite(block, target)
        if rules:
            row["rules"].extend(dict(r, sourceGuardIlOffset=guard) for r in rules)
        elif target[0] == "local":
            row["unrecognizedProjectileWriteOffsets"].extend(i.offset for i in block if i.op in ("stloc", "ldloca") and i.arg == target[1])
        else:
            # In the source PickAmmo subset, passing this byref elsewhere is
            # not a proof of a constant rewrite.
            row["unrecognizedProjectileWriteOffsets"].extend(i.offset for i in block if i.op == "ldarg" and i.arg == target[1])
        for n, call in enumerate(block):
            if call.op != "call" or call.arg[0] != "Terraria.Projectile.NewProjectile":
                continue
            try:
                count = call.arg[1]
                if count not in (10, 12) or call.arg[2]:
                    continue
                args = straight_line_arguments(block, n, count)
                projectile = args[3 if count == 10 else 5]
                basis = "current_shot_projectile" if projectile == ("ldloc", target[1]) else "fixed_projectile" if projectile[0] == "const" else "unknown_expression"
                spawn = {"sourceSpawnIlOffset": call.offset, "sourceGuardIlOffset": guard,
                         "projectileBasis": basis, "nativeItemSpecificDelivery": True,
                         "scope": "Explicit native branch spawn site; not ordinary direct-ammo delivery, spawn count or guaranteed execution"}
                count_bounds = adjusted_counted_spawn(block, call.offset)
                if count_bounds is not None:
                    spawn["spawnCountBounds"] = count_bounds
                spawn["trajectoryReference"] = {"status": "native_branch_aim_and_spread_not_fully_modeled",
                                                "scope": "Retained projectile does not imply direct origin, authored straight movement, fixed spread or an inherited native attack"}
                if basis == "fixed_projectile":
                    spawn["projectileId"] = projectile[1]
                row["spawnSites"].append(spawn)
            except (Unrecognized, IndexError):
                continue
    return [rows[k] for k in sorted(rows) if any(rows[k][f] for f in ("rules", "spawnSites", "unrecognizedProjectileWriteOffsets"))]
