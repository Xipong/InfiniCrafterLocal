"""Bounded, fail-closed analysis of native NPC-hit source facts, never game execution.

Only acyclic IL in the explicitly listed subset is accepted. Unknown state is
merged, not sampled. A fact must occur on every reachable return path. This is
not an arbitrary IL VM: it cannot call methods, access game state or run loops.
"""
from __future__ import annotations

from dataclasses import dataclass

UNKNOWN = ("unknown",)
THIS = ("this",)
TARGET_INDEX = ("target_index",)
TARGET = ("target_npc",)
RANDOM = ("random",)


@dataclass(frozen=True)
class Instruction:
    offset: int
    op: str
    arg: object = None


@dataclass(frozen=True)
class State:
    stack: tuple = ()
    locals: tuple = (UNKNOWN,) * 8
    must: frozenset = frozenset()


def integer(value):
    return value[1] if value[0] == "int" else None


def merge(a, b):
    if len(a.stack) != len(b.stack):
        raise ValueError("inconsistent evaluation stack")
    same = lambda x, y: x if x == y else UNKNOWN
    return State(tuple(map(same, a.stack, b.stack)), tuple(map(same, a.locals, b.locals)), a.must & b.must)


def analyze(instructions, projectile_type):
    """Return only proved unconditional target-NPC requests and exclusion reasons."""
    if not instructions or len(instructions) > 8192:
        raise ValueError("empty/oversized native method")
    positions = {i.offset: n for n, i in enumerate(instructions)}
    if len(positions) != len(instructions):
        raise ValueError("duplicate instruction offsets")
    states = {instructions[0].offset: State()}
    exits = []
    calls = {}
    reasons = {}
    all_sites = {i.offset for i in instructions if i.op == "call" and i.arg[0] == "Terraria.NPC.AddBuff"}
    for index, ins in enumerate(instructions):
        if ins.offset not in states:
            continue
        state = states[ins.offset]
        stack, locals_, must = list(state.stack), list(state.locals), state.must
        op, arg = ins.op, ins.arg
        next_offset = instructions[index + 1].offset if index + 1 < len(instructions) else None
        successors = [next_offset]
        pop = stack.pop
        if op == "ldarg":
            stack.append(THIS if arg == 0 else TARGET_INDEX if arg == 1 else UNKNOWN)
        elif op == "const":
            stack.append(("int", arg) if isinstance(arg, int) else UNKNOWN)
        elif op == "ldloc":
            stack.append(locals_[arg])
        elif op == "stloc":
            locals_[arg] = pop()
        elif op == "dup":
            stack.append(stack[-1])
        elif op == "ldsfld":
            stack.append(("npc_array",) if arg == "Terraria.Main.npc" else UNKNOWN)
        elif op == "ldfld":
            receiver = pop()
            stack.append(("int", projectile_type) if receiver == THIS and arg == "Terraria.Projectile.type" else UNKNOWN)
        elif op == "ldelem":
            subscript, receiver = pop(), pop()
            stack.append(TARGET if receiver == ("npc_array",) and subscript == TARGET_INDEX else UNKNOWN)
        elif op == "conv":
            pop(); stack.append(UNKNOWN)
        elif op in ("mul", "sub"):
            right, left = pop(), pop()
            a, b = integer(left), integer(right)
            if a is not None and b is not None:
                value = a * b if op == "mul" else a - b
                if not -2147483648 <= value <= 2147483647:
                    raise ValueError("integer overflow outside supported subset")
                stack.append(("int", value))
            elif op == "mul" and ((left[0] == "range" and b is not None) or (right[0] == "range" and a is not None)):
                distribution, factor = (left, b) if left[0] == "range" else (right, a)
                if factor <= 0 or distribution[2] * factor > 2147483647:
                    stack.append(UNKNOWN)
                else:
                    stack.append(("range", distribution[1] * factor, distribution[2] * factor, distribution[3] * factor))
            else:
                stack.append(UNKNOWN)
        elif op == "call":
            name, count, has_this, returns = arg
            arguments = [pop() for _ in range(count)][::-1]
            receiver = pop() if has_this else None
            result = UNKNOWN
            if name == "Terraria.Main.get_rand" and not has_this and count == 0:
                result = RANDOM
            elif name == "Terraria.Utilities.UnifiedRandom.Next" and receiver == RANDOM and count in (1, 2):
                values = [integer(a) for a in arguments]
                if all(v is not None for v in values):
                    low, high = (0, values[0]) if count == 1 else values
                    if 0 <= low < high:
                        result = ("range", low, high - 1, 1)
            elif name == "Terraria.NPC.AddBuff" and receiver == TARGET and count == 3:
                buff, duration, quiet = arguments
                buff_id = integer(buff)
                duration_value = integer(duration)
                if duration_value is not None:
                    duration = ("range", duration_value, duration_value, 1)
                if buff_id is not None and buff_id > 0 and duration[0] == "range" and duration[1] > 0 and integer(quiet) == 0:
                    calls[ins.offset] = (buff_id, duration[1], duration[2], duration[3])
                    must = must | {ins.offset}
                else:
                    reasons[ins.offset] = "dynamic_buff_or_duration_or_flags"
            elif name not in ("Terraria.Projectile.get_melee", "Terraria.Projectile.get_ranged"):
                # Unknown calls could mutate this.type or invoke extra statuses.
                raise ValueError("unsupported call: " + name)
            if returns:
                stack.append(result)
        elif op == "br":
            successors = [arg]
        elif op in ("brtrue", "brfalse"):
            value = integer(pop())
            condition = None if value is None else bool(value)
            if condition is not None and op == "brfalse":
                condition = not condition
            successors = [arg, next_offset] if condition is None else [arg if condition else next_offset]
        elif op in ("beq", "bne", "bgt", "blt", "ble", "bge"):
            b, a = integer(pop()), integer(pop())
            condition = None if a is None or b is None else {
                "beq": a == b, "bne": a != b, "bgt": a > b,
                "blt": a < b, "ble": a <= b, "bge": a >= b,
            }[op]
            successors = [arg, next_offset] if condition is None else [arg if condition else next_offset]
        elif op == "switch":
            value = integer(pop())
            successors = [*arg, next_offset] if value is None else [arg[value] if 0 <= value < len(arg) else next_offset]
        elif op == "ret":
            if stack:
                raise ValueError("nonempty stack at void return")
            exits.append(must)
            continue
        else:
            raise ValueError("unsupported opcode: " + op)
        after = State(tuple(stack), tuple(locals_), frozenset(must))
        for target in set(successors):
            if target not in positions or target <= ins.offset:
                raise ValueError("non-forward or invalid control flow")
            states[target] = merge(states[target], after) if target in states else after
    if not exits:
        raise ValueError("no reachable return")
    guaranteed = frozenset.intersection(*exits)
    for offset in calls.keys() - guaranteed:
        reasons[offset] = "conditional_player_world_ai_or_random_path"
    return {
        "effects": [{"ilOffset": offset, "buffId": calls[offset][0], "durationTicksMin": calls[offset][1],
                     "durationTicksMax": calls[offset][2], "durationTicksStep": calls[offset][3]}
                    for offset in sorted(guaranteed)],
        "excludedSites": [{"ilOffset": offset, "reason": reason} for offset, reason in sorted(reasons.items())],
        "totalMethodAddBuffSites": len(all_sites),
    }
