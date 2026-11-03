"""Small source-shape recognizers, not an IL executor or weapon-family mapper.

Recognize explicit type guards and the arguments of direct native spawn calls.
Unknown expression/control-flow shapes decline a fact. Calls are never executed.
"""
from __future__ import annotations


class Unrecognized(ValueError):
    pass


def expression(code, index, depth=0):
    """Read one straight-line stack expression backwards, bounded and literal."""
    if index < 0 or depth > 32:
        raise Unrecognized("expression bound")
    ins = code[index]
    op, arg = ins.op, ins.arg
    if op in ("ldloc", "ldloca", "ldarg", "const", "ldsfld"):
        return (op, arg), index - 1
    if op in ("conv", "ldfld", "ldflda"):
        value, before = expression(code, index - 1, depth + 1)
        return (op, arg, value), before
    if op in ("mul", "add", "sub", "div"):
        right, before = expression(code, index - 1, depth + 1)
        left, before = expression(code, before, depth + 1)
        return (op, left, right), before
    if op == "newobj":
        # Metadata includes the complete signature, not just a name/arity.
        # This is a symbolic data value, never a constructor invocation.
        if arg != ("Microsoft.Xna.Framework.Vector2..ctor", "2002010c0c"):
            raise Unrecognized("not a known typed data constructor")
        args, before = arguments(code, index, 2, depth + 1)
        return ("newobj", arg, *args), before
    if op == "call":
        name, count, has_this, returns = arg
        if not returns:
            raise Unrecognized("void call is not an expression")
        args, before = arguments(code, index, count + int(has_this), depth + 1)
        return ("call", name, *args), before
    raise Unrecognized("unsupported stack expression: " + op)


def arguments(code, call_index, count, depth=0):
    args, index = [], call_index - 1
    for _ in range(count):
        value, index = expression(code, index, depth + 1)
        args.append(value)
    return tuple(reversed(args)), index


def straight_line_arguments(block, call_index, count):
    args, before = arguments(block, call_index, count)
    start, finish = block[before + 1].offset, block[call_index].offset
    for ins in block:
        targets = ins.arg if ins.op == "switch" else [ins.arg] if ins.op.startswith("b") and isinstance(ins.arg, int) else []
        if any(start < target <= finish for target in targets):
            raise Unrecognized("control-flow entry into argument expression")
    return args


def type_blocks(instructions, field, argument):
    code = [i for i in instructions if i.op != "nop"]
    # No fallthrough proof is valid in the presence of an unmodeled transfer,
    # including transfers outside the candidate that could enter its interior.
    if any(i.op in ("throw", "rethrow", "jmp", "leave", "endfinally", "endfilter") for i in code):
        return
    for index in range(len(code) - 4):
        a, b, c, guard = code[index:index + 4]
        if (a.op, a.arg, b.op, b.arg, c.op, guard.op) != ("ldarg", argument, "ldfld", field, "const", "bne"):
            continue
        if not isinstance(c.arg, int) or guard.arg <= guard.offset:
            continue
        block = [i for i in code[index + 4:] if i.offset < guard.arg]
        if block and len(block) <= 1024:
            start, end = block[0].offset, guard.arg
            external_entry = False
            for ins in code:
                if start <= ins.offset < end:
                    continue
                targets = ins.arg if ins.op == "switch" else [ins.arg] if ins.op.startswith("b") and isinstance(ins.arg, int) else []
                if any(start <= target < end for target in targets):
                    external_entry = True
                    break
            if not external_entry:
                yield c.arg, guard.offset, block


def direct_call_count(block, call_offset):
    """Prove one explicit spawn on every terminating path, including setup loops.

    This finite CFG walk tracks only whether the call was visited, never game
    values. A cycle that can revisit the spawn is refused for counted-loop proof.
    """
    positions = {i.offset: n for n, i in enumerate(block)}
    pending, seen, exits = [(block[0].offset, 0)], set(), set()
    while pending:
        offset, count = pending.pop()
        if (offset, count) in seen:
            continue
        seen.add((offset, count))
        if offset not in positions:
            exits.add(count)
            continue
        index = positions[offset]
        ins = block[index]
        count += int(ins.offset == call_offset)
        if count > 1:
            raise Unrecognized("spawn may repeat")
        if ins.op == "ret":
            exits.add(count)
            continue
        next_ = block[index + 1].offset if index + 1 < len(block) else None
        if ins.op == "br":
            targets = [ins.arg]
        elif ins.op in ("brtrue", "brfalse", "beq", "bne", "bgt", "blt", "ble", "bge", "bge.un", "ble.un", "blt.un", "bgt.un"):
            targets = [ins.arg, next_]
        elif ins.op == "switch":
            targets = [*ins.arg, next_]
        else:
            targets = [next_]
        pending.extend((target, count) for target in targets)
    if exits != {1}:
        raise Unrecognized("spawn is not once on all terminating branch paths")
    return {"minimum": 1, "maximum": 1, "distribution": "fixed"}


def counted_spawn(block, call_offset):
    """Recognize bounded i=0; i<literal/local; i++ with one direct spawn."""
    jumps = [(n, i) for n, i in enumerate(block) if i.op.startswith("b") and isinstance(i.arg, int) and i.arg < i.offset]
    if len(jumps) != 1:
        raise Unrecognized("not one counted loop")
    end, branch = jumps[0]
    if branch.op != "blt":
        raise Unrecognized("not strict upper bound")
    left, right = block[end - 2:end]
    if left.op != "ldloc" or right.op not in ("ldloc", "const"):
        raise Unrecognized("nonlocal loop bounds")
    counter, limit = left.arg, right.arg if right.op == "ldloc" else None
    if counter == limit:
        raise Unrecognized("aliased loop locals")
    if any(i.op == "ldloca" and i.arg in (counter, limit) for i in block):
        raise Unrecognized("address mutation of loop locals")
    start = next(n for n, i in enumerate(block) if i.offset == branch.arg)
    if any(i.op in ("ret", "switch") for i in block[:start]) or [i.op for i in block[end + 1:]] != ["ret"]:
        raise Unrecognized("noncanonical loop entry or exit")
    body = block[start:end - 2]
    if any(i.op.startswith("b") or i.op in ("switch", "ret") for i in body):
        raise Unrecognized("conditional loop body")
    if [i.offset for i in body if i.op == "call" and i.arg[0] == "Terraria.Projectile.NewProjectile"] != [call_offset]:
        raise Unrecognized("not one spawn per iteration")
    if [(i.op, i.arg) for i in body[-4:]] != [("ldloc", counter), ("const", 1), ("add", None), ("stloc", counter)]:
        raise Unrecognized("nonunit increment")
    stores = [(n, i) for n, i in enumerate(block) if i.op == "stloc" and i.arg in (counter, limit)]
    if len(stores) != (3 if limit is not None else 2):
        raise Unrecognized("loop local reassignment")
    initial = [n for n, i in stores if i.arg == counter and n < start]
    bounds = [n for n, i in stores if i.arg == limit and n < start]
    if len(initial) != 1 or len(bounds) != int(limit is not None) or (block[initial[0] - 1].op, block[initial[0] - 1].arg) != ("const", 0):
        raise Unrecognized("nonzero loop start")
    value, _ = expression(block, bounds[0] - 1) if bounds else (("const", right.arg), None)
    if value[0] == "const":
        low = high = value[1]
        distribution = "fixed"
    elif len(value) == 5 and value[:2] == ("call", "Terraria.Utilities.UnifiedRandom.Next") and value[2] == ("call", "Terraria.Main.get_rand") and all(v[0] == "const" for v in value[3:]):
        low, high = value[3][1], value[4][1] - 1
        distribution = "uniform_integer_inclusive"
    else:
        raise Unrecognized("nonuniform loop bound")
    if not all(isinstance(v, int) for v in (low, high)) or not 0 < low <= high <= 64:
        raise Unrecognized("unbounded loop")
    # The only forward jump skips the loop body for the first condition test.
    forwards = [i for i in block if i.op.startswith("b") and isinstance(i.arg, int) and i.arg > i.offset]
    if len(forwards) != 1 or forwards[0].op != "br" or forwards[0].arg != left.offset:
        raise Unrecognized("additional loop entry/exit condition")
    if forwards[0].offset != block[start - 1].offset or any(block[n].offset >= forwards[0].offset for n in initial + bounds):
        raise Unrecognized("loop setup does not dominate first condition")
    return {"minimum": low, "maximum": high, "distribution": distribution}


def definition_dominates(block, store, use):
    """Can the use be reached from branch entry without the unique store?"""
    positions = {ins.offset: n for n, ins in enumerate(block)}
    pending, seen = [0], set()
    while pending:
        n = pending.pop()
        if n == store or n in seen or not 0 <= n < len(block):
            continue
        if n == use:
            return False
        seen.add(n)
        ins = block[n]
        if ins.op == "ret":
            continue
        targets = ins.arg if ins.op == "switch" else [ins.arg] if ins.op.startswith("b") and isinstance(ins.arg, int) else []
        pending.extend(positions[t] for t in targets if t in positions)
        if ins.op != "br":
            pending.append(n + 1)
    return True


def spawn_inputs(block, call_index, args, method_provenance=None):
    """Serialize source values; only branch-local, unique dominating defs expand.

    A definition retains its store offset and snapshot scope: reads in its RHS
    happened at the store, not necessarily at the subsequent projectile call.
    Current shot locals deliberately do not borrow method-entry/base values.
    """
    provenance = method_provenance or {}
    budget = [512]

    def value(expr, use, trail=()):
        budget[0] -= 1
        op = expr[0]
        if budget[0] < 0 or len(trail) > 16:
            return {"kind": "unknown", "reason": "source_expression_bound"}
        if op == "ldloc":
            local = expr[1]
            unknown = {"kind": "unknown", "local": local}
            stores = [n for n, ins in enumerate(block) if ins.op == "stloc" and ins.arg == local]
            if any(ins.op == "ldloca" and ins.arg == local for ins in block):
                return {**unknown, "reason": "address_exposed_local"}
            if len(stores) != 1:
                return {**unknown, "reason": "multiple_branch_local_definitions" if stores else "no_branch_local_definition"}
            store = stores[0]
            if store >= use or not definition_dominates(block, store, use):
                return {**unknown, "reason": "definition_does_not_dominate_use"}
            if local in trail:
                return {**unknown, "reason": "cyclic_local_definition"}
            try:
                rhs = straight_line_arguments(block, store, 1)[0]
            except (Unrecognized, IndexError):
                return {**unknown, "reason": "unsupported_definition_expression"}
            return {"kind": "local_definition", "local": local,
                    "sourceStoreIlOffset": block[store].offset, "scope": "value_at_store",
                    "value": value(rhs, store, (*trail, local))}
        if op == "const":
            return {"kind": "constant", "value": expr[1]}
        if op == "ldarg":
            return {"kind": "argument", "index": expr[1]}
        if op in ("ldloca", "ldflda"):
            return {"kind": "unknown", "reason": "address_expression", "sourceOperation": op}
        if op == "ldsfld":
            return {"kind": "static_field", "member": expr[1]}
        if op == "ldfld":
            return {"kind": "field", "member": expr[1], "receiver": value(expr[2], use, trail)}
        if op == "conv":
            return {"kind": "conversion", "operator": expr[1], "value": value(expr[2], use, trail)}
        if op in ("mul", "add", "sub", "div"):
            return {"kind": "binary", "operator": op, "left": value(expr[1], use, trail), "right": value(expr[2], use, trail)}
        if op == "newobj":
            return {"kind": "data_constructor", "member": expr[1][0], "signature": expr[1][1],
                    "arguments": [value(v, use, trail) for v in expr[2:]]}
        if op == "call":
            return {"kind": "call", "member": expr[1],
                    "arguments": [value(v, use, trail) for v in expr[2:]],
                    "evaluation": "unresolved_helper_or_hook_output",
                    "provenance": provenance.get(expr[1], {"status": "unknown", "reason": "method_certificate_unavailable"})}
        return {"kind": "unknown", "reason": "unsupported_source_expression", "sourceOperation": op}

    names = (("source", "position", "velocity") if len(args) == 10 else
             ("source", "positionX", "positionY", "velocityX", "velocityY")) + ("type", "damage", "knockback", "owner", "ai0", "ai1", "ai2")
    result = {name: value(expr, call_index) for name, expr in zip(names, args)}
    for name, role in (("type", "current_native_shot_type"), ("damage", "current_native_shot_damage"), ("knockback", "current_native_knockback")):
        result[name]["role"] = role
    return result


def shoot_facts(instructions):
    # Native ItemCheck_Shoot receives damage as argument 3 and initializes a
    # local before ammo and mod hooks. The multiplier below is relative to the
    # current value of that local at the spawn, NOT the original/base damage.
    code = [i for i in instructions if i.op != "nop"]
    damage_locals = {b.arg for a, b in zip(code, code[1:]) if (a.op, a.arg, b.op) == ("ldarg", 3, "stloc")}
    if len(damage_locals) != 1:
        return []
    damage_local = next(iter(damage_locals))
    records = []
    blocks = list(type_blocks(instructions, "Terraria.Item.type", 2))
    for item_id, guard, block in blocks:
        if sum(other_id == item_id for other_id, _, _ in blocks) != 1:
            continue
        spawns = [(n, i) for n, i in enumerate(block) if i.op == "call" and i.arg[0] == "Terraria.Projectile.NewProjectile"]
        if len(spawns) != 1:
            continue
        n, call = spawns[0]
        try:
            count = call.arg[1]
            if count not in (10, 12) or call.arg[2]:
                continue
            args = straight_line_arguments(block, n, count)
            damage = args[4 if count == 10 else 6]
            multiplier = 1.0
            if damage != ("ldloc", damage_local):
                if damage[:2] != ("conv", "conv.i4") or damage[2][0] != "mul":
                    continue
                left, right = damage[2][1:]
                if left not in (("conv", "conv.r8", ("ldloc", damage_local)), ("conv", "conv.r4", ("ldloc", damage_local))):
                    continue
                if right[0] != "const" or not isinstance(right[1], (float, int)) or not 0 < right[1] <= 16:
                    continue
                multiplier = right[1]
            try:
                spawn_count = direct_call_count(block, call.offset)
            except Unrecognized:
                spawn_count = counted_spawn(block, call.offset)
            records.append({"itemId": item_id, "sourceGuardIlOffset": guard,
                "sourceSpawnIlOffset": call.offset, "damageMultiplierAtSpawn": multiplier,
                "damageIntegerConversion": "native_truncate_toward_zero" if damage[0] == "conv" else "none",
                "shotDamageLocalMayBeModifiedInBranch": any(i.op in ("stloc", "ldloca") and i.arg == damage_local for i in block),
                "explicitSpawnCount": spawn_count,
                "sourcePredicates": [{"field": "Terraria.Item.type", "argument": 2,
                    "operator": "equals", "literal": item_id, "sourceIlOffset": guard}],
                "spawnInputs": spawn_inputs(block, n, args, getattr(instructions, "method_provenance", None)),
                "spawnInputCoverage": {
                    "scope": "native_call_arguments_only_not_final_attack",
                    "localDefinitions": "branch_local_single_assignment_dominating_use_only",
                    "calls": "symbolic_unresolved_helper_and_mod_contributions_not_executed",
                    "multiplicity": "existing_branch_count_proof_only_not_global_use_count",
                    "unresolved": "unknown_nodes_retain_current_locals_not_item_base_values"}})
        except (Unrecognized, IndexError, StopIteration):
            continue
    # Duplicate guards are ambiguous; never overwrite one branch with another.
    key = "itemId" if records and "itemId" in records[0] else "projectileId"
    return [r for r in records if sum(other[key] == r[key] for other in records) == 1]


def line_collision_facts(instructions):
    records = []
    center = ("call", "Terraria.Entity.get_Center", ("ldarg", 0))
    scale = ("ldfld", "Terraria.Projectile.scale", ("ldarg", 0))
    blocks = list(type_blocks(instructions, "Terraria.Projectile.type", 0))
    for projectile_id, guard, block in blocks:
        if sum(other_id == projectile_id for other_id, _, _ in blocks) != 1:
            continue
        calls = [(n, i) for n, i in enumerate(block) if i.op == "call" and i.arg[0] == "Terraria.Collision.CheckAABBvLineCollision"]
        if len(calls) != 1:
            continue
        n, call = calls[0]
        allowed_calls = {
            "Terraria.Utils.ToRotationVector2", "Terraria.Entity.get_Hitbox", "Terraria.Entity.get_Center",
            "Microsoft.Xna.Framework.Rectangle.Inflate", "Microsoft.Xna.Framework.Rectangle.Intersects",
            "Terraria.Utils.TopLeft", "Terraria.Utils.Size", "Microsoft.Xna.Framework.Vector2.op_Multiply",
            "Microsoft.Xna.Framework.Vector2.op_Subtraction", "Microsoft.Xna.Framework.Vector2.op_Addition",
            "Terraria.Collision.CheckAABBvLineCollision",
        }
        if any(i.op == "call" and i.arg[0] not in allowed_calls for i in block):
            continue
        # The proof relates all reads to one live scale/rotation. Writes (also
        # indirect writes via aliases) invalidate that relation, even if the
        # final expression still has the familiar spelling.
        if any(i.op in ("ldarga", "starg") or i.op.startswith(("stfld", "stsfld", "stind", "stobj", "cpobj", "initobj")) for i in block):
            continue
        if call.arg != ("Terraria.Collision.CheckAABBvLineCollision", 6, False, True):
            continue
        try:
            if any(i.op == "ret" for i in block[:n]):
                continue
            args = straight_line_arguments(block, n, 6)
            if args[:2] != (("call", "Terraria.Utils.TopLeft", ("ldarg", 2)),
                            ("call", "Terraria.Utils.Size", ("ldarg", 2))):
                continue
            start, end, thickness = args[2:5]
            if start[:3] != ("call", "Microsoft.Xna.Framework.Vector2.op_Subtraction", center):
                continue
            delta = start[3]
            if end != ("call", "Microsoft.Xna.Framework.Vector2.op_Addition", center, delta):
                continue
            if delta[:2] != ("call", "Microsoft.Xna.Framework.Vector2.op_Multiply") or any(v[0] != "ldloc" for v in delta[2:]):
                continue
            direction, half = delta[2:]
            if thickness[0] != "mul" or thickness[2] != scale or thickness[1][0] != "ldloc":
                continue
            width = thickness[1]
            # Recognized stack-preserving native setup: rotation is retained on
            # stack while the intersection accumulator, half-length and width
            # locals are initialized, then converted to a unit direction.
            setups = []
            # Setup must be the branch entry, so no CFG edge can bypass it.
            for k in (0,) if len(block) >= 14 else ():
                seq = block[k:k + 14]
                pattern = [("ldarg", 0), ("ldfld", "Terraria.Projectile.rotation"),
                    ("const", 0.0), ("stloc", args[5][1]),
                    ("const", seq[4].arg), ("ldarg", 0), ("ldfld", "Terraria.Projectile.scale"),
                    ("mul", None), ("stloc", half[1]), ("const", seq[9].arg), ("stloc", width[1]),
                    ("call", ("Terraria.Utils.ToRotationVector2", 1, False, True)), ("stloc", direction[1])]
                if [(i.op, i.arg) for i in seq[:13]] == pattern:
                    setups.append((seq[4].arg, seq[9].arg))
            if len(setups) != 1 or args[5][0] != "ldloca":
                continue
            if any(i.op == "ldloca" and i.arg in (direction[1], half[1], width[1]) for i in block):
                continue
            if any(sum(i.op == "stloc" and i.arg == v[1] for i in block) != 1 for v in (direction, half, width)):
                continue
            half_length, line_width = setups[0]
            if not all(isinstance(v, (float, int)) and 0 < v <= 4096 for v in setups[0]):
                continue
            records.append({"projectileId": projectile_id, "sourceGuardIlOffset": guard,
                "sourceCollisionCallIlOffset": call.offset, "halfLengthTimesProjectileScale": half_length,
                "lineWidthTimesProjectileScale": line_width,
                "center": "projectile.Center", "direction": "projectile.rotation",
                "scope": "Arguments of the native line-collision test; native broadphase and mod hooks still gate collision. Scale is live AI state, not necessarily SetDefaults scale."})
        except (Unrecognized, IndexError):
            continue
    # Duplicate guards are ambiguous; never overwrite one branch with another.
    key = "itemId" if records and "itemId" in records[0] else "projectileId"
    return [r for r in records if sum(other[key] == r[key] for other in records) == 1]
