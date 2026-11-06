"""Bounded source slices for native spawn arguments, never a game/IL executor.

Reaching definitions are alternatives on explicit normal-flow paths. Field and
call reads retain observation offsets; branch-entry locals are unknown inputs,
not item defaults. No predicate, hook, helper or constructor is evaluated.
"""
from __future__ import annotations

import math

from native_ammo_control_flow import branch_targets, COMPARISONS, CONDITIONALS, TRANSFERS
from native_attack_fact_analysis import Unrecognized


_LIMITS = {"instructions": 1024, "expressionNodes": 1024, "predicateNodes": 256,
           "definitionAlternatives": 8, "expressionDepth": 40, "localDefinitionDepth": 24}
_BINARY = {"add", "sub", "mul", "div", "rem"}


def _unknown(reason, **site):
    return {"kind": "unknown", "reason": reason, **site}


def _bounded_tree(value, limit):
    pending, size = [(value, 0)], 0
    while pending:
        node, depth = pending.pop()
        if isinstance(node, (dict, list)):
            size += 1
            if size > limit:
                raise Unrecognized("source_expression_output_bound")
            if depth > _LIMITS["expressionDepth"]:
                raise Unrecognized("source_expression_depth_bound")
            pending.extend((child, depth + 1) for child in (node.values() if isinstance(node, dict) else node))


def _coverage(value, path):
    unresolved, pending = [], [(value, path)]
    while pending:
        node, location = pending.pop()
        if isinstance(node, dict):
            if node.get("kind") == "unknown":
                unresolved.append({"path": location, **{k: v for k, v in node.items() if k != "kind"}})
            elif node.get("kind") == "call":
                unresolved.append({"path": location, "reason": "helper_output_not_evaluated",
                                   "member": node["member"], "sourceIlOffset": node["sourceIlOffset"]})
            pending.extend((v, location + "." + k) for k, v in reversed(list(node.items())) if k != "provenance")
        elif isinstance(node, list):
            pending.extend((v, f"{location}[{n}]") for n, v in reversed(list(enumerate(node))))
    status = "unknown" if isinstance(value, dict) and value.get("kind") == "unknown" else (
        "partial_source_expression" if unresolved else "source_expression")
    return {"status": status, "unresolved": unresolved}


class _SourceSlice:
    def __init__(self, code, guard, block, provenance):
        self.code, self.block, self.provenance = code, block, provenance or {}
        self.positions = {ins.offset: n for n, ins in enumerate(block)}
        self.targets = {t for ins in code for t in branch_targets(ins)}
        self.budget = _LIMITS["expressionNodes"]
        self.active = set()
        self.edges, self.predecessors = [], [[] for _ in block]
        guard_index = next(n for n, ins in enumerate(code) if ins.offset == guard)
        header = code[guard_index - 3].offset
        if any(header < t <= guard for t in self.targets):
            raise Unrecognized("foreign_entry_into_item_header")
        if len(block) > _LIMITS["instructions"] or len(self.positions) != len(block):
            raise Unrecognized("source_instruction_bound")
        offsets = {ins.offset for ins in code}
        for n, ins in enumerate(block):
            targets = branch_targets(ins)
            if any(t not in offsets for t in targets):
                raise Unrecognized("invalid_control_flow_target")
            if ins.op in TRANSFERS or ins.op.startswith("b") and ins.op not in CONDITIONALS | {"br", "break"}:
                raise Unrecognized("unsupported_control_flow_transfer")
            next_ = n + 1 if n + 1 < len(block) else None
            jumps = [self.positions.get(t) for t in targets]
            edges = [] if ins.op == "ret" else jumps if ins.op == "br" else (
                [*jumps, next_] if ins.op in CONDITIONALS | {"switch"} else [next_])
            self.edges.append(edges)
            for target in edges:
                if target is not None:
                    self.predecessors[target].append(n)
        self.reachable, pending = set(), [0]
        while pending:
            n = pending.pop()
            if n is None or n in self.reachable:
                continue
            self.reachable.add(n)
            pending.extend(self.edges[n])

    def read(self, end, depth=0):
        """Read syntax only. Local values and calls are not executed."""
        if end < 0 or depth > 48:
            raise Unrecognized("source_stack_expression_bound")
        ins = self.block[end]
        op, arg, site = ins.op, ins.arg, {"sourceIlOffset": ins.offset}
        if op == "const" and isinstance(arg, (int, float)) and math.isfinite(arg):
            return {"kind": "constant", "value": arg, **site}, end - 1
        if op in {"ldarg", "ldloc", "ldsfld"}:
            kind, key = {"ldarg": ("argument", "index"), "ldloc": ("local_read", "local"),
                         "ldsfld": ("static_field", "member")}[op]
            return {"kind": kind, key: arg, **site}, end - 1
        if op in {"conv", "ldfld", "neg"}:
            value, before = self.read(end - 1, depth + 1)
            if op == "ldfld":
                return {"kind": "field", "member": arg, "receiver": value, **site}, before
            return {"kind": "conversion" if op == "conv" else "unary",
                    "operator": arg if op == "conv" else op, "value": value, **site}, before
        if op in _BINARY:
            right, before = self.read(end - 1, depth + 1)
            left, before = self.read(before, depth + 1)
            return {"kind": "binary", "operator": op, "left": left, "right": right, **site}, before
        if op == "newobj" and arg == ("Microsoft.Xna.Framework.Vector2..ctor", "2002010c0c"):
            node, count = {"kind": "data_constructor", "member": arg[0], "signature": arg[1], **site}, 2
        elif op == "call" and arg[3]:
            node, count = {"kind": "call", "member": arg[0], **site,
                           "evaluation": "unresolved_helper_or_hook_output",
                           "provenance": self.provenance.get(arg[0], {"status": "unknown", "reason": "method_certificate_unavailable"})}, arg[1] + int(arg[2])
        else:
            raise Unrecognized("address_expression" if op in {"ldloca", "ldarga", "ldflda"} else "unsupported_stack_operation")
        values, before = [], end - 1
        for _ in range(count):
            value, before = self.read(before, depth + 1)
            values.append(value)
        node["arguments"] = list(reversed(values))
        return node, before

    def no_expression_entry(self, first, last):
        if any(self.block[first].offset < t <= self.block[last].offset for t in self.targets):
            raise Unrecognized("foreign_entry_into_source_expression")

    def expand(self, node):
        self.budget -= 1
        if self.budget < 0:
            return _unknown("source_expression_node_bound", sourceIlOffset=node.get("sourceIlOffset"))
        if node.get("kind") == "local_read":
            try:
                return self.local(node["local"], self.positions[node["sourceIlOffset"]])
            except Unrecognized as error:
                return _unknown(str(error), local=node["local"], sourceIlOffset=node["sourceIlOffset"])
        return {key: self.expand(value) if isinstance(value, dict) and "kind" in value else
                [self.expand(child) if isinstance(child, dict) and "kind" in child else child for child in value]
                if isinstance(value, list) else value for key, value in node.items()}

    def predicate(self, n, taken):
        ins = self.block[n]
        result = {"kind": "branch", "opcode": ins.op, "taken": taken, "sourceBranchIlOffset": ins.offset}
        try:
            right, before = self.read(n - 1)
            if ins.op in COMPARISONS:
                left, before = self.read(before)
                result.update(left=self.expand(left), right=self.expand(right))
            else:
                result["value"] = self.expand(right)
            self.no_expression_entry(before + 1, n)
        except Unrecognized as error:
            result = {"kind": "branch", "opcode": ins.op, "taken": taken, "sourceBranchIlOffset": ins.offset,
                      "operands": _unknown(str(error), sourceIlOffset=ins.offset)}
        return result

    def relevant(self, target):
        relevant, pending = set(), [target]
        while pending:
            n = pending.pop()
            if n not in self.reachable or n in relevant:
                continue
            relevant.add(n)
            pending.extend(self.predecessors[n])
        if any(s is not None and s in relevant and s <= n for n in relevant if n != target for s in self.edges[n]):
            raise Unrecognized("cyclic_source_path")
        return relevant

    def condition(self, target, local=None, wanted=None):
        """Normal-flow formula for reaching target with the requested last store.

        This finite two-state source walk tracks only write-site identity, never
        local values. Matching branch formulas collapse structurally, not by
        evaluating predicates or assuming stable fields across observations.
        """
        relevant = self.relevant(target)
        if 0 not in relevant:
            return False
        formulas = {(target, seen): seen or local is None for seen in (False, True)}
        for n in sorted(relevant - {target}, reverse=True):
            ins = self.block[n]
            for incoming in (False, True):
                seen = n == wanted if local is not None and ins.op == "stloc" and ins.arg == local else incoming
                values = [formulas.get((s, seen), False) for s in self.edges[n]]
                if not values:
                    result = False
                elif all(v == values[0] for v in values):
                    result = values[0]
                elif ins.op in CONDITIONALS:
                    taken, fallthrough = values
                    if taken is True and fallthrough is False:
                        result = self.predicate(n, True)
                    elif taken is False and fallthrough is True:
                        result = self.predicate(n, False)
                    else:
                        result = {"kind": "if", "condition": self.predicate(n, True), "then": taken, "else": fallthrough}
                else:
                    raise Unrecognized("unsupported_controlling_transfer")
                _bounded_tree(result, _LIMITS["predicateNodes"])
                formulas[n, incoming] = result
        return formulas[0, wanted is None]

    def local(self, local, use):
        site = {"local": local, "sourceIlOffset": self.block[use].offset}
        addresses = [ins.offset for ins in self.block if ins.op == "ldloca" and ins.arg == local]
        if addresses:
            return _unknown("address_exposed_local", **site, sourceAddressIlOffsets=addresses)
        if (local, use) in self.active:
            raise Unrecognized("cyclic_local_definition")
        if len(self.active) >= _LIMITS["localDefinitionDepth"]:
            raise Unrecognized("source_local_definition_depth_bound")
        relevant = self.relevant(use)
        definitions, seen, pending = set(), set(), list(self.predecessors[use])
        if use == 0:
            definitions.add(None)
        while pending:
            n = pending.pop()
            if n in seen or n not in relevant:
                continue
            seen.add(n)
            ins = self.block[n]
            if ins.op == "stloc" and ins.arg == local:
                definitions.add(n)
            else:
                if n == 0:
                    definitions.add(None)
                pending.extend(self.predecessors[n])
        if not definitions:
            raise Unrecognized("unreachable_local_observation")
        if len(definitions) > _LIMITS["definitionAlternatives"]:
            raise Unrecognized("reaching_definition_alternative_bound")
        self.active.add((local, use))
        try:
            alternatives = []
            for store in sorted(definitions, key=lambda n: -1 if n is None else n):
                condition = self.condition(use, local, store) if len(definitions) > 1 else True
                if condition is False:
                    continue
                if store is None:
                    value = _unknown("branch_entry_value_unknown", **site)
                else:
                    try:
                        rhs, before = self.read(store - 1)
                        self.no_expression_entry(before + 1, store)
                        value = self.expand(rhs)
                    except Unrecognized as error:
                        value = _unknown(str(error), sourceIlOffset=self.block[store].offset)
                    value = {"kind": "local_definition", **site, "sourceStoreIlOffset": self.block[store].offset,
                             "scope": "value_at_store", "value": value}
                alternatives.append({"whenSourceCondition": condition, "value": value})
            if len(alternatives) == 1:
                return alternatives[0]["value"]
            return {"kind": "source_alternatives", **site,
                    "scope": "last_local_definition_on_source_path_to_read; predicates_not_evaluated",
                    "alternatives": alternatives}
        finally:
            self.active.remove((local, use))


def spawn_argument_facts(code, guard, block, call_index, provenance=None):
    """Add source evidence to an existing certified spawn site, not identity rules."""
    count = block[call_index].arg[1]
    names = (("source", "position", "velocity") if count == 10 else
             ("source", "positionX", "positionY", "velocityX", "velocityY")) + (
                 "type", "damage", "knockback", "owner", "ai0", "ai1", "ai2")
    try:
        source = _SourceSlice(code, guard, block, provenance)
    except Unrecognized as error:
        source, failure = None, str(error)
    inputs, before = {}, call_index - 1
    for name in reversed(names):
        if source is None:
            inputs[name] = _unknown(failure, sourceIlOffset=block[call_index].offset)
            continue
        source.budget = _LIMITS["expressionNodes"]
        try:
            syntax, previous = source.read(before)
            source.no_expression_entry(previous + 1, call_index)
        except Unrecognized as error:
            inputs[name] = _unknown(str(error), sourceIlOffset=block[before].offset if before >= 0 else block[call_index].offset)
            # If syntax cannot be consumed, preceding argument boundaries are
            # unknown too. Never shift their role labels onto different values.
            source, failure = None, "argument_stack_boundary_unproved"
            continue
        before = previous
        try:
            inputs[name] = source.expand(syntax)
            _bounded_tree(inputs[name], _LIMITS["expressionNodes"])
        except Unrecognized as error:
            inputs[name] = _unknown(str(error), sourceIlOffset=syntax["sourceIlOffset"])
    if source is not None:
        source.budget = _LIMITS["expressionNodes"]
        try:
            condition = source.condition(call_index)
        except Unrecognized as error:
            condition = _unknown(str(error), sourceIlOffset=block[call_index].offset)
    else:
        condition = _unknown(failure, sourceIlOffset=block[call_index].offset)
    inputs = {name: inputs[name] for name in names}
    return {"spawnInputs": inputs, "whenSourceCondition": condition,
            "spawnInputCoverage": {
                "scope": "source_call_arguments_only; not_final_values_or_guaranteed_execution",
                "localValues": "guarded_reaching_definitions; branch_entry_values_unknown_not_item_defaults",
                "controlFlow": "normal_flow_from_item_branch_entry; external_gates_hooks_and_player_state_not_evaluated",
                "calls": "symbolic_source_only; helpers_hooks_getters_and_constructors_not_executed",
                "limits": dict(_LIMITS),
                "condition": _coverage(condition, "whenSourceCondition"),
                "fields": {name: _coverage(value, "spawnInputs." + name) for name, value in inputs.items()}}}
