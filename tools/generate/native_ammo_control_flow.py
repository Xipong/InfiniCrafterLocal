"""Bounded normal-flow source predicates for literal projectile writes.

No IL execution or item routing: slice explicit CFG edges and retain the exact
observation sites. Refused sites stay with the caller's unknown-write evidence.
"""
from __future__ import annotations

from native_attack_fact_analysis import Unrecognized, definition_dominates


COMPARISONS = {"beq", "bne", "bgt", "blt", "ble", "bge", "bgt.un", "blt.un", "ble.un", "bge.un"}
CONDITIONALS = COMPARISONS | {"brtrue", "brfalse"}
TRANSFERS = {"throw", "rethrow", "jmp", "leave", "endfinally", "endfilter"}


def branch_targets(ins):
    if ins.op == "switch":
        return ins.arg if isinstance(ins.arg, (list, tuple)) else []
    return [ins.arg] if ins.op.startswith("b") and isinstance(ins.arg, int) else []


def literal_store_predicates(code, guard_offset, block, target):
    """Certify local literals, relative to reaching the proven item branch.

    The existing recognizer owns contiguous enclosing projectile predicates.
    This extension refuses enclosing spans and byrefs rather than losing them.
    Only acyclic explicit normal-flow paths and fully known predicate operands
    are admitted; unrelated trajectory branches disappear by CFG equivalence.
    """
    if target[0] != "local" or not block or len(block) > 1024:
        return []
    slot = target[1]
    if any(i.op == "ldloca" and i.arg == slot for i in block):
        return []
    guard_index = next(n for n, i in enumerate(code) if i.offset == guard_offset)
    item_start = code[guard_index - 3].offset
    # type_blocks protects the body, not the stack expression of its header.
    # An entry at the constant/comparison could forge the tested item identity.
    if any(item_start < destination <= guard_offset for ins in code for destination in branch_targets(ins)):
        return []
    # Linear IL spans are not enclosing CFG regions. A jump from a completed
    # sibling dispatcher arm may span this item's code while neither successor
    # can ever reach it. Discard only such structurally disconnected spans.
    offsets = {i.offset for i in code}
    predecessors = {offset: [] for offset in offsets}
    for n, ins in enumerate(code):
        destinations = branch_targets(ins)
        if any(t not in offsets for t in destinations):
            return []
        if ins.op not in {"br", "ret"} and n + 1 < len(code):
            destinations = [*destinations, code[n + 1].offset]
        for destination in destinations:
            predecessors[destination].append(ins.offset)
    ancestors, pending = {item_start}, [item_start]
    while pending:
        for source in predecessors[pending.pop()]:
            if source not in ancestors:
                ancestors.add(source)
                pending.append(source)
    if any(ins.offset in ancestors and destination > item_start
           for ins in code[:guard_index - 3] for destination in branch_targets(ins)):
        return []
    # The decoder keeps unsupported transfers distinct, including EH metadata
    # checked by the caller. Unknown call signatures are not CFG branches.
    if any(i.op in TRANSFERS or (i.op.startswith("b") and i.op not in CONDITIONALS | {"br", "break"}) for i in block):
        return []
    positions = {i.offset: n for n, i in enumerate(block)}
    code_offsets = {i.offset for i in code}
    if len(positions) != len(block) or any(t not in code_offsets for i in block for t in branch_targets(i)):
        return []
    edges = []
    for n, ins in enumerate(block):
        next_ = n + 1 if n + 1 < len(block) else None
        targets = [positions.get(t) for t in branch_targets(ins)]
        edges.append([] if ins.op == "ret" else targets if ins.op == "br" else
                     [*targets, next_] if ins.op in CONDITIONALS | {"switch"} else [next_])

    def source_expression(end, budget, trail=()):
        budget[0] -= 1
        if end < 0 or budget[0] < 0 or len(trail) > 16:
            raise Unrecognized("source expression bound")
        ins = block[end]
        op, arg = ins.op, ins.arg
        site = {"sourceIlOffset": ins.offset}
        if op == "const" and isinstance(arg, int):
            return {"kind": "constant", "value": arg, **site}, end - 1
        if op == "ldarg":
            return {"kind": "argument", "index": arg, **site}, end - 1
        if op == "ldfld":
            receiver, before = source_expression(end - 1, budget, trail)
            return {"kind": "field", "member": arg, "receiver": receiver, **site}, before
        if op in {"add", "sub", "mul", "div"}:
            right, before = source_expression(end - 1, budget, trail)
            left, before = source_expression(before, budget, trail)
            return {"kind": "binary", "operator": op, "left": left, "right": right, **site}, before
        if op == "ldloc":
            stores = [n for n, i in enumerate(block) if i.op == "stloc" and i.arg == arg]
            if (arg == slot or arg in trail or len(stores) != 1
                    or any(i.op == "ldloca" and i.arg == arg for i in code)):
                raise Unrecognized("ambiguous or address-exposed local")
            store = stores[0]
            if store >= end or not definition_dominates(block, store, end):
                raise Unrecognized("local definition does not dominate observation")
            value, before = source_expression(store - 1, budget, (*trail, arg))
            no_foreign_expression_entry(before + 1, store)
            return {"kind": "local_definition", "local": arg, **site,
                    "sourceStoreIlOffset": block[store].offset, "scope": "value_at_store", "value": value}, end - 1
        raise Unrecognized("unsupported controlling expression")

    def no_foreign_expression_entry(start, end):
        low, high = block[start].offset, block[end].offset
        if any(low < t <= high for ins in code for t in branch_targets(ins)):
            raise Unrecognized("control-flow entry into expression")

    def branch_predicate(n, taken):
        ins = block[n]
        budget = [96]
        right, before = source_expression(n - 1, budget)
        node = {"kind": "branch", "opcode": ins.op, "taken": taken,
                "sourceBranchIlOffset": ins.offset}
        if ins.op in COMPARISONS:
            left, before = source_expression(before, budget)
            node.update(left=left, right=right)
        else:
            node["value"] = right
        no_foreign_expression_entry(before + 1, n)
        return node

    def validate_formula(formula):
        # Bound the serialized tree, not only unique CFG nodes: reconvergent
        # branches can otherwise duplicate large shared suffixes in JSON.
        pending, size = [formula], 0
        while pending:
            node = pending.pop()
            size += 1
            if size > 256:
                raise Unrecognized("source predicate output bound")
            if isinstance(node, dict):
                pending.extend(node.values())
        # A local snapshot has one defining store even at multiple loads. Refuse
        # contradictory literal equalities on that same snapshot; separate
        # field-load offsets are intentionally never treated as one observation.
        def equality(node, outcome):
            if node.get("kind") != "branch" or node["opcode"] not in {"beq", "bne"}:
                return None
            taken = node["taken"] if outcome else not node["taken"]
            if taken != (node["opcode"] == "beq"):
                return None
            left, right = node["left"], node["right"]
            if right.get("kind") == "local_definition":
                left, right = right, left
            if left.get("kind") == "local_definition" and right.get("kind") == "constant":
                return left["sourceStoreIlOffset"], right["value"]
            return None
        paths = [(formula, {})]
        while paths:
            node, known = paths.pop()
            if isinstance(node, bool):
                continue
            choices = [(node, True, True)] if node["kind"] == "branch" else [
                (node["condition"], True, node["then"]), (node["condition"], False, node["else"])]
            for predicate, outcome, child in choices:
                if child is False:
                    continue
                updated = dict(known)
                pair = equality(predicate, outcome)
                if pair:
                    key, value = pair
                    if key in updated and updated[key] != value:
                        raise Unrecognized("contradictory snapshot equalities")
                    updated[key] = value
                if child is not True:
                    paths.append((child, updated))

    rules = []
    for store, ins in enumerate(block):
        if (ins.op != "stloc" or ins.arg != slot or store == 0 or block[store - 1].op != "const"
                or not isinstance(block[store - 1].arg, int) or block[store - 1].arg <= 0):
            continue
        try:
            no_foreign_expression_entry(store - 1, store)
            # Reverse reachability excludes paths that cannot hit this store.
            relevant = {store}
            changed = True
            while changed:
                changed = False
                for n, successors in enumerate(edges):
                    if n not in relevant and any(s in relevant for s in successors):
                        relevant.add(n)
                        changed = True
            if 0 not in relevant:
                continue
            # Explore only the prefix ending at the store. A back-edge there
            # would require loop semantics, even if its condition later cancels.
            pending, visited = [0], set()
            while pending:
                n = pending.pop()
                if n in visited or n not in relevant or n == store:
                    continue
                visited.add(n)
                if any(s is not None and s in relevant and s <= n for s in edges[n]):
                    raise Unrecognized("cyclic controlling path")
                pending.extend(s for s in edges[n] if s is not None)
            formulas = {store: True, None: False}
            for n in sorted(visited, reverse=True):
                successors = edges[n]
                values = [formulas.get(s, False) for s in successors]
                if not values:
                    result = False
                elif all(v == values[0] for v in values):
                    result = values[0]
                elif block[n].op in CONDITIONALS:
                    taken, fallthrough = values
                    if taken is True and fallthrough is False:
                        result = branch_predicate(n, True)
                    elif taken is False and fallthrough is True:
                        result = branch_predicate(n, False)
                    else:
                        result = {"kind": "if", "condition": branch_predicate(n, True),
                                  "then": taken, "else": fallthrough}
                else:
                    raise Unrecognized("unsupported controlling transfer")
                validate_formula(result)
                formulas[n] = result
            condition = formulas[0]
            if condition is False:
                continue
            validate_formula(condition)
            rule = {"outputProjectileId": block[store - 1].arg, "sourceStoreIlOffset": ins.offset,
                    "sourceScope": "normal_flow_from_item_branch_entry; exact_source_observations_not_final_shot"}
            if condition is not True:
                rule["whenSourceCondition"] = condition
            rules.append(rule)
        except (Unrecognized, IndexError):
            continue
    return rules
