"""Bounded source certificates for conditional arithmetic shot-local updates.

No game code is executed. Item-field snapshots used for identity projection are
explicit conditions, not claims that hooks preserve those fields or the shot.
"""
from native_attack_fact_analysis import definition_dominates
from native_ammo_control_flow import branch_targets, CONDITIONALS, TRANSFERS


def _snapshot_input(code, guard, target, item_id):
    """Prove Item.shoot reaches the guard under stated item snapshot conditions.

    Prune only explicit Item.type comparisons and useAmmo <= 0. Every other
    normal-flow edge remains possible. A reachable write/byref or cycle refuses
    projection; no effect summary or gameplay condition is guessed.
    """
    positions = {i.offset: n for n, i in enumerate(code)}
    end = positions[guard]
    definitions = [n for n in range(2, end) if [(i.op, i.arg) for i in code[n-2:n+1]] ==
                   [("ldarg", 2), ("ldfld", "Terraria.Item.shoot"), ("stloc", target)]]
    if len(definitions) != 1 or not definition_dominates(code, definitions[0], end):
        return None
    start = definitions[0]
    all_targets = {t for ins in code for t in branch_targets(ins)}
    if any(code[start-2].offset < t <= code[start].offset for t in all_targets):
        return None
    reached = False
    pending, seen = [start + 1], set()
    while pending:
        n = pending.pop()
        if n == end:
            reached = True
            continue
        if n in seen:
            continue
        if not start < n < end:
            return None
        seen.add(n)
        ins = code[n]
        if ins.op in TRANSFERS or ins.op == "switch":
            return None
        if ins.op in ("stloc", "ldloca") and ins.arg == target:
            return None
        if ins.op == "ret":
            continue
        destinations = branch_targets(ins)
        if any(t not in positions or positions[t] <= n for t in destinations):
            return None
        selected = None
        if n >= 3 and not any(code[n-3].offset < t <= ins.offset for t in all_targets):
            a, b, c = code[n-3:n]
            if (a.op, a.arg, b.op, c.op) == ("ldarg", 2, "ldfld", "const"):
                if b.arg == "Terraria.Item.type" and ins.op in ("beq", "bne"):
                    selected = (item_id == c.arg) == (ins.op == "beq")
                elif b.arg == "Terraria.Item.useAmmo" and c.arg == 0 and ins.op == "ble":
                    selected = True
        if ins.op == "br" or selected is True:
            pending.extend(positions[t] for t in destinations)
        elif selected is False:
            pending.append(n + 1)
        elif ins.op in CONDITIONALS:
            pending.extend([n + 1, *(positions[t] for t in destinations)])
        elif destinations or ins.op.startswith("b") and ins.op != "break":
            return None
        else:
            pending.append(n + 1)
    if not reached:
        return None
    return {"basis": "item_shoot_snapshot", "sourceInitializationIlOffset": code[start].offset,
            "requiredUseAmmoMaximum": 0,
            "conditions": ["Item.type equals catalog item identity at every tested read",
                           "Item.useAmmo is nonpositive at the source read",
                           "Item.shoot at initialization equals the captured item.shoot"],
            "scope": "Conditional source input binding only; hooks may mutate item fields before reads or projectile locals after this site"}


def _initialization_provenance(code, guard, local):
    """Name a dominating initial field/argument, never the later current value."""
    end = next(n for n, ins in enumerate(code) if ins.offset == guard)
    stores = [n for n, ins in enumerate(code[:end]) if ins.op == "stloc" and ins.arg == local]
    if not stores:
        return None
    store = stores[0]
    if store >= 2 and code[store-2].op == "ldarg" and code[store-1].op == "ldfld":
        first = store-2
        source = {"kind": "argument_field", "argument": code[first].arg, "field": code[store-1].arg}
    elif store >= 1 and code[store-1].op == "ldarg":
        first = store-1
        source = {"kind": "argument", "argument": code[first].arg}
    else:
        return None
    if (not definition_dominates(code, store, end)
            or any(code[first].offset < t <= code[store].offset for ins in code for t in branch_targets(ins))):
        return None
    return {"source": source, "sourceStoreIlOffset": code[store].offset,
            "interveningWriteOrAddressOffsets": [ins.offset for ins in code[store+1:end]
                                                 if ins.op in ("stloc", "ldloca") and ins.arg == local],
            "scope": "Dominating initialization only; intervening transformations and byrefs are not evaluated. This does not equate the branch-entry value with the initial field or argument."}


def conditional_arithmetic_variants(code, guard, block, target, item_id):
    """A complete random comparison with two straight-line arithmetic arms.

    Parameters and IDs come only from IL. Restrict probability semantics to the
    engine's integer RNG API and keep probability conditional on reaching this
    branch, not a final gameplay shot frequency.
    """
    if target[0] != "local" or len(block) < 11:
        return []
    index = next(n for n, i in enumerate(code) if i.offset == guard)
    first, end = code[index-3].offset, code[index].arg
    if any(first < t < end for ins in code if not first <= ins.offset < end for t in branch_targets(ins)):
        return []
    a, maximum, call, threshold, branch = block[:5]
    if ((a.op, a.arg) != ("call", ("Terraria.Main.get_rand", 0, False, True))
            or (call.op, call.arg) != ("call", ("Terraria.Utilities.UnifiedRandom.Next", 1, True, True))
            or maximum.op != "const" or threshold.op != "const" or branch.op != "bge"
            or not isinstance(maximum.arg, int) or not isinstance(threshold.arg, int)
            or not 0 <= threshold.arg <= maximum.arg or maximum.arg <= 0):
        return []
    split = next((n for n, ins in enumerate(block) if ins.offset == branch.arg), -1)
    if split < 6 or (block[split-1].op, block[split-1].arg) != ("br", end):
        return []
    # Only the two certified branch edges may enter either expression sequence.
    if any(branch_targets(ins) for ins in block if ins not in (branch, block[split-1])):
        return []
    arms = [block[5:split-1], block[split:]]
    updates = []
    for arm in arms:
        if len(arm) % 4:
            return []
        arm_updates = []
        for n in range(0, len(arm), 4):
            read, constant, op, store = arm[n:n+4]
            if (read.op != "ldloc" or constant.op != "const" or op.op not in ("add", "sub", "mul")
                    or store.op != "stloc" or store.arg != read.arg
                    or not isinstance(constant.arg, (int, float))
                    or any(u["local"] == read.arg for u in arm_updates)):
                return []
            arm_updates.append({"local": read.arg, "operator": op.op, "operand": constant.arg,
                                "sourceReadIlOffset": read.offset, "sourceStoreIlOffset": store.offset,
                                "basis": "local_value_at_branch_entry", "numericSemantics": "original_IL_arithmetic_not_evaluated",
                                "initializationProvenance": _initialization_provenance(code, guard, read.arg)})
        updates.append(arm_updates)
    if not any(u["local"] == target[1] for arm in updates for u in arm):
        return []
    binding = _snapshot_input(code, guard, target[1], item_id)
    result = []
    for arm_index, arm in enumerate(updates):
        projectile = next((u for u in arm if u["local"] == target[1]), None)
        if projectile and (projectile["operator"] not in ("add", "sub") or not isinstance(projectile["operand"], int)):
            return []
        offset = 0 if projectile is None else projectile["operand"] * (1 if projectile["operator"] == "add" else -1)
        result.append({"sourceGuardIlOffset": guard, "sourceBranchIlOffset": branch.offset,
                       "sourceRandomCallIlOffset": call.offset, "branchTaken": bool(arm_index),
                       "whenSourceCondition": {"operation": "uniform_integer_less_than" if arm_index == 0 else "uniform_integer_greater_equal",
                                               "minimumInclusive": 0, "maximumExclusive": maximum.arg, "threshold": threshold.arg},
                       "conditionalProbability": {"numerator": threshold.arg if arm_index == 0 else maximum.arg-threshold.arg,
                                                  "denominator": maximum.arg, "scope": "Conditional on reaching this RNG call; not final shot frequency"},
                       "projectileLocal": target[1], "projectileOffset": offset, "localUpdates": arm,
                       "inputBinding": binding,
                       "scope": "Arithmetic source alternative at this stage only; source conditions, later writes, hooks and shooting admission are not evaluated"})
    return result
