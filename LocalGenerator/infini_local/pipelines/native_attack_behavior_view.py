"""Model context: connected native behavior, not the provenance/audit dump.

This is an explicitly lossy *metadata* projection. It never executes expressions,
chooses branches, drops unknown mechanics, or truncates connected dependencies.
The original native capture remains the sole source/audit artifact.
"""
from __future__ import annotations

import copy
import re
from dataclasses import replace
from typing import Any

from infini_local.pipelines.native_attack_geometry_view import project_collision_behavior
from infini_local.pipelines.native_attack_draw_view import project_draw_layers

from infini_local.pipelines.native_attack_expression_view import (
    _Parser, _Term, _render, compact_attack_expressions,
)

_PROGRAM_COVERAGE = "connected_source_slice; opaque_fields_calls_and_address_aliases_are_symbolic"
_GUIDE = (
    "Read-only connected source, not executed gameplay. Raw dump retains omitted certificates/offsets. "
    "Rows stay ordered; step ordinals preserve cross-list source order; blocks/successors retain control flow. requiredPredicates names "
    "reached branches, not necessarily true arms. dN are local definitions. Fields/calls/aliases "
    "remain symbolic; alternatives are reaching definitions, not independent rolls."
)
_NOTATION = (
    "Fully parenthesized arithmetic preserves order, without evaluation. (r).Owner.field reads "
    "a live field; @Owner.field reads static state; set(field,v) writes it. f32_at/ref_at/i32_at "
    "read indexed array values. Vector2.add/sub/mul/div and Color.mul are native operators. "
    "T=Terraria, Xna=Microsoft.Xna.Framework, XnaGfx=Xna.Graphics, Content=ReLogic.Content; "
    "primitive type names are shortened. rgba.white and color * scalar denote certified native Color "
    "operations on all RGBA channels, including native rounding/clamping, not alpha alone. Calls retain signatures. "
    "readFloat(array,index) reads a System.Single element. writeFloat(array,index,value) resolves/checks "
    "the element address BEFORE evaluating value, then writes it; it is source notation, not an ordinary "
    "helper call. Both preserve native array/address checks and re-read live state."
)


def _expression_names(text: str, names: dict[str, str], *, rgba_multiply: bool = False, rgba_white: bool = False) -> str:
    """Rename only parsed identifier atoms, never string literals or numeric lexemes."""
    def visit(term: _Term) -> _Term:
        if term.args is None:
            return replace(term, name=names.get(term.name, term.name))
        return replace(term, args=tuple(visit(arg) for arg in term.args))
    tree = _Parser(text, compact=True).parse()
    # Unknown syntax remains literal at the program boundary, including its names.
    if _render(tree, compact=True) != text:
        raise ValueError("noncanonical expression")
    def readable(term: _Term) -> _Term:
        if term.args is None:
            return term
        args = tuple(readable(arg) for arg in term.args)
        # Only the exact typed array-address idiom; unknown aliases stay literal.
        if term.name in {"ldind.r4", "stind.r4"} and args:
            address = args[0]
            if (address.name == "ldelema" and address.args is not None
                    and len(address.args) == 3 and address.args[2] == _Term('"System.Single"')
                    and address.separators == (",", ";")
                    and len(args) == (1 if term.name == "ldind.r4" else 2)):
                values = (*address.args[:2], *args[1:])
                return _Term("readFloat" if len(args) == 1 else "writeFloat", values,
                             separators=(",",) * (len(values) - 1))
        if rgba_white and term.name == "Color.get_White" and not args:
            return _Term("rgba.white")
        if rgba_multiply and term.name == "Color.op_Multiply" and len(args) == 2:
            return _Term("(" + _render(args[0], compact=True) + "*" + _render(args[1], compact=True) + ")")
        return replace(term, args=args)

    return _render(readable(visit(tree)), compact=True)


def _map_expressions(program: dict, names: dict[str, str]) -> None:
    symbols = program["symbols"]

    def expression(text: str) -> str:
        return _expression_names(text, names,
            rgba_multiply=symbols.get("Color.op_Multiply") == "Xna.Color.op_Multiply(Xna.Color,float)",
            rgba_white=symbols.get("Color.get_White") == "Xna.Color.get_White()")

    def row(value: dict) -> None:
        for key in ("expression", "receiver"):
            if isinstance(value.get(key), str):
                value[key] = expression(value[key])
    for observation in program["observations"]:
        row(observation)
        if isinstance(observation.get("arguments"), dict):
            observation["arguments"] = {key: expression(value) if isinstance(value, str) else value
                                        for key, value in observation["arguments"].items()}
    for dependency in program["dependencies"].values():
        if isinstance(dependency, dict):
            row(dependency)
            for use in dependency.get("orderedSourceUses", []):
                row(use)
    for predicate in program["predicates"]:
        if isinstance(predicate.get("inputs"), list):
            predicate["inputs"] = [expression(value) if isinstance(value, str) else value
                                   for value in predicate["inputs"]]


def _program(value: dict) -> dict:
    out = copy.deepcopy(value)
    # Unknown program/row schemas retain their complete reference namespace.
    out.pop("sourceModuleVersionId", None)
    out.pop("sourceMethodSha256", None)
    if not (isinstance(out.get("observations"), list) and isinstance(out.get("dependencies"), dict)
            and isinstance(out.get("predicates"), list) and isinstance(out.get("symbols"), dict)):
        return copy.deepcopy(value)
    names = {name: f"d{index}" for index, name in enumerate(out["dependencies"])}
    # Reserved identifier collision / unsupported expression: retain the complete
    # original names. There is no partial renaming and no guessed syntax.
    known_program = {"method", "observations", "dependencies", "predicates", "symbols", "coverage",
                     "unresolved", "identityWindows", "predicateSources", "identitySelection", "identityAlternatives"}
    known_row = _ROW_FIELDS
    rows = [*out["observations"], *out["dependencies"].values(), *out["predicates"]]
    if (not set(out) <= known_program or any(not isinstance(row, dict) or not set(row) <= known_row
            or not isinstance(row.get("orderedSourceUses", []), list) for row in rows)):
        return copy.deepcopy(value)
    rows += [use for row in rows for use in row.get("orderedSourceUses", [])]
    if any(not isinstance(row, dict) or not set(row) <= known_row for row in rows):
        return copy.deepcopy(value)
    removed_literals = set()
    if not any(re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", str(out))
                         for name in names.values()):
        renamed = copy.deepcopy(out)
        try:
            literals = {
                name: row["expression"] for name, row in out["dependencies"].items()
                if set(row) <= {"expression", "at", "block", "requiredPredicates"}
                and row.get("requiredPredicates") == []
                and isinstance(row.get("expression"), str)
                and re.fullmatch(r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", row["expression"])
            }
            # Never inline live/guarded/addressed definitions across their reads.
            _map_expressions(renamed, names | literals)
        except (ValueError, IndexError, TypeError, AttributeError, RecursionError):
            pass
        else:
            renamed["dependencies"] = {names[key]: child for key, child in renamed["dependencies"].items()}
            removed_literals = {names[key] for key in literals}
            out = renamed
    # A shared step order preserves interleaving between dependencies, predicates,
    # observations and addressed-local uses. Removing offsets outright would lose
    # whether a live read precedes a write when both are in the same block.
    rows = [*out["observations"], *out["dependencies"].values(), *out["predicates"]]
    rows += [use for row in rows if isinstance(row, dict)
             for use in row.get("orderedSourceUses", [])]
    offsets = sorted({row["at"] for row in rows if isinstance(row, dict) and type(row.get("at")) is int})
    steps = {offset: index for index, offset in enumerate(offsets)}
    # Unknown future step fields cannot be overwritten by this projection.
    if not any(isinstance(row, dict) and "step" in row for row in rows):
        for row in rows:
            if isinstance(row, dict) and type(row.get("at")) is int:
                row["step"] = steps[row.pop("at")]
    out["dependencies"] = {key: row for key, row in out["dependencies"].items() if key not in removed_literals}
    # Field qualification duplicates the already-written owner.field. Method
    # overloads/signatures and unfamiliar symbols are deliberately retained.
    out["symbols"] = {key: re.sub(r", Version=[^,\]]+, Culture=[^,\]]+, PublicKeyToken=[^,\]]+", "", symbol)
                      if isinstance(symbol, str) else symbol for key, symbol in out["symbols"].items()
                      if symbol not in ("T." + key, "Xna." + key, "XnaGfx." + key)}
    if out.get("coverage") == _PROGRAM_COVERAGE:
        del out["coverage"]
    return out


_ROW_FIELDS = {"kind", "at", "block", "requiredPredicates", "expression", "call", "receiver", "arguments",
                 "scope", "orderedSourceUses", "id", "op", "inputs", "successors"}

_PROGRAM_FIELDS = {"method", "sourceModuleVersionId", "sourceMethodSha256", "observations", "dependencies",
                   "predicates", "symbols", "coverage", "unresolved", "identityWindows", "predicateSources", "identityAlternatives"}


def _identity_alternatives(value: Any) -> Any:
    """Readable disclosure of producer-proved discarded paths, never activation.

    Merge only equalities differing in the literal on the same identity field,
    with identical remaining conditions/effect. Unknown syntax stays untouched.
    """
    if (not isinstance(value, dict) or set(value) != {"source", "version", "scope", "cases"}
            or value["source"] != "excluded_identity_edges" or type(value["version"]) is not int or value["version"] != 1
            or not isinstance(value["scope"], str) or not isinstance(value["cases"], list)):
        return copy.deepcopy(value)
    groups = []
    for case in value["cases"]:
        if (not isinstance(case, dict) or set(case) != {"allConditions", "effect"}
                or not isinstance(case["effect"], str)
                or case["effect"] not in {"returns_without_method_state_changes", "discarded_path_effect_unresolved"}
                or not isinstance(case["allConditions"], list) or not case["allConditions"]):
            return copy.deepcopy(value)
        conditions = []
        source_path = []
        for condition in case["allConditions"]:
            if (not isinstance(condition, dict) or set(condition) != {"at", "op", "inputs", "successors", "chosenSuccessor"}
                    or type(condition["at"]) is not int or type(condition["chosenSuccessor"]) is not int
                    or not isinstance(condition["successors"], list) or len(condition["successors"]) != 2
                    or any(type(n) is not int for n in condition["successors"])
                    or condition["successors"][0] == condition["successors"][1]
                    or condition["chosenSuccessor"] not in condition["successors"]
                    or not isinstance(condition["inputs"], list) or len(condition["inputs"]) != 2
                    or any(not isinstance(x, str) for x in condition["inputs"])):
                return copy.deepcopy(value)
            source_path.append(condition["at"])
            left, right = condition["inputs"]
            field = re.fullmatch(r"ldfld\(Projectile\.(type|aiStyle),this\)", left)
            state = re.fullmatch(r"ldelem\.r4\(ldfld\(Projectile\.ai,this\),(\d+)\)", left)
            if not (field or state) or not re.fullmatch(r"-?\d+", right):
                return copy.deepcopy(value)
            taken = condition["chosenSuccessor"] == condition["successors"][0]
            op = condition["op"]
            if not isinstance(op, str):
                return copy.deepcopy(value)
            op = op[:-2] if op.endswith(".s") else op
            if op not in {"beq", "bne.un", "blt"}:
                return copy.deepcopy(value)
            relation = ("equals" if taken else "notEquals") if op == "beq" else ("notEquals" if taken else "equals") if op == "bne.un" else ("orderedLessThan" if taken else "notOrderedLessThan")
            conditions.append({"field": "Projectile." + field[1] if field else "Projectile.ai[" + state[1] + "]",
                               "test": relation, "value": int(right)})
        head, *tail = conditions
        # Integer identity equality has no NaN/range ambiguity. Do not merge
        # mutable AI comparisons or arbitrary formulas into identity sets.
        mergeable = head["field"] in {"Projectile.type", "Projectile.aiStyle"} and head["test"] == "equals"
        existing = next((group for group in groups if mergeable and group["effect"] == case["effect"]
                         and group["whenAll"][1:] == tail and group["whenAll"][0].get("field") == head["field"]
                         and group["whenAll"][0].get("test") == "oneOf"), None)
        if existing is not None:
            existing["sourcePaths"].append(source_path)
            if head["value"] not in existing["whenAll"][0]["values"]:
                existing["whenAll"][0]["values"].append(head["value"])
        else:
            if mergeable:
                head = {"field": head["field"], "test": "oneOf", "values": [head["value"]]}
            groups.append({"whenAll": [head, *tail], "effect": case["effect"], "sourcePaths": [source_path]})
    return {"scope": value["scope"], "comparisonSemantics": "equals/notEquals use ordinary numeric equality; orderedLessThan is false for NaN; notOrderedLessThan includes NaN.",
            "meaning": "A proved return skips this method's remaining position/velocity integration, not necessarily movement elsewhere. Other native identity/controller choices are source clues, not imported Author options; capability equivalence is unproved.",
            "cases": groups}


def known_identity_alternatives(value: Any) -> bool:
    """Admission for the exact projected disclosure; future fields stay opaque."""
    if (not isinstance(value, dict) or set(value) != {"scope", "comparisonSemantics", "meaning", "cases"}
            or any(not isinstance(value[key], str) for key in ("scope", "comparisonSemantics", "meaning"))
            or not isinstance(value["cases"], list)):
        return False
    for case in value["cases"]:
        if (not isinstance(case, dict) or set(case) != {"whenAll", "effect", "sourcePaths"}
                or not isinstance(case["effect"], str)
                or case["effect"] not in {"returns_without_method_state_changes", "discarded_path_effect_unresolved"}
                or not isinstance(case["whenAll"], list) or not case["whenAll"]
                or not isinstance(case["sourcePaths"], list) or not case["sourcePaths"]
                or any(not isinstance(path, list) or len(path) != len(case["whenAll"])
                       or any(type(offset) is not int for offset in path) for path in case["sourcePaths"])):
            return False
        for condition in case["whenAll"]:
            if not isinstance(condition, dict) or not isinstance(condition.get("field"), str) or not isinstance(condition.get("test"), str):
                return False
            if condition.get("test") == "oneOf":
                if (set(condition) != {"field", "test", "values"} or condition["field"] not in {"Projectile.type", "Projectile.aiStyle"}
                        or not isinstance(condition["values"], list) or not condition["values"]
                        or any(type(n) is not int for n in condition["values"])):
                    return False
            elif (set(condition) != {"field", "test", "value"} or condition.get("test") not in {"equals", "notEquals", "orderedLessThan", "notOrderedLessThan"}
                    or type(condition.get("value")) is not int
                    or not re.fullmatch(r"Projectile\.(?:type|aiStyle|ai\[\d+\])", condition["field"])):
                return False
    return True


def _selected_program(value: dict, identity: Any) -> dict:
    """Consume only the native producer's same-method, same-identity CFG slice.

    Python never decides a branch. The untouched original and edge proof remain
    in the native dump; a recognized selection supplies the model behavior graph.
    """
    selected = value.get("identitySelected")
    if not isinstance(selected, dict) or not set(value) <= _PROGRAM_FIELDS | {"identitySelected"}:
        return value
    receipt = selected.get("identitySelection")
    if (not isinstance(receipt, dict) or set(receipt) != {"source", "version", "identityPredicates", "scope", "selectedEdges"}
            or receipt["source"] != "certified_receiver_identity_cfg"
            or type(receipt["version"]) is not int or receipt["version"] != 1
            or not isinstance(identity, dict) or set(identity) != {"Projectile.type", "Projectile.aiStyle"}
            or any(type(item) is not int for item in identity.values())
            or not isinstance(receipt["identityPredicates"], dict)
            or any(type(item) is not int for item in receipt["identityPredicates"].values())
            or receipt["identityPredicates"] != identity or not isinstance(receipt["scope"], str)
            or not isinstance(receipt["selectedEdges"], list)):
        return value
    for edge in receipt["selectedEdges"]:
        if (not isinstance(edge, dict) or set(edge) != {"at", "block", "op", "successor"}
                or any(type(edge[key]) is not int for key in ("at", "block", "successor"))
                or not isinstance(edge["op"], str)):
            return value
    if (not set(selected) <= _PROGRAM_FIELDS | {"identitySelection"}
            or any(type(value.get(key)) is not str or selected.get(key) != value[key]
                   for key in ("method", "sourceModuleVersionId", "sourceMethodSha256"))
            or not isinstance(selected.get("observations"), list)
            or not isinstance(selected.get("dependencies"), dict)
            or not isinstance(selected.get("predicates"), list)
            or not isinstance(selected.get("symbols"), dict)):
        return value
    unavailable_full_method = (
        set(value) == {"method", "sourceModuleVersionId", "sourceMethodSha256", "coverage", "unresolved", "identitySelected"}
        and value.get("coverage") == "unknown" and isinstance(value.get("unresolved"), str) and bool(value["unresolved"])
    )
    # A producer may certify the captured-identity slice even when the complete
    # all-identity method exceeds its extraction work bound. Never fabricate an
    # empty original graph; retain its explicit failure beside the selected one.
    for graph in (selected,) if unavailable_full_method else (value, selected):
        if (not isinstance(graph.get("observations"), list) or not isinstance(graph.get("dependencies"), dict)
                or not isinstance(graph.get("predicates"), list) or not isinstance(graph.get("symbols"), dict)):
            return value
        rows = [*graph["observations"], *graph["dependencies"].values(), *graph["predicates"]]
        if any(not isinstance(row, dict) or not set(row) <= _ROW_FIELDS
               or not isinstance(row.get("orderedSourceUses", []), list) for row in rows):
            return value
        if any(not isinstance(use, dict) or not set(use) <= _ROW_FIELDS for row in rows for use in row.get("orderedSourceUses", [])):
            return value
    # Keep unfamiliar original data instead of allowing a new producer version
    # to silently make this reader discard it. Known graph fields come from the
    # selected source; selectedEdges is dump-only provenance, not an LLM decision.
    out = copy.deepcopy(selected)
    if "identityAlternatives" in out:
        out["identityAlternatives"] = _identity_alternatives(out["identityAlternatives"])
    out["identitySelection"] = {
        "forCapturedIdentity": True,
        "scope": receipt["scope"],
    }
    if unavailable_full_method:
        out["identitySelection"]["fullMethodCapture"] = {
            "coverage": value["coverage"], "unresolved": value["unresolved"],
        }
    return out


def project_attack_behavior(reference: dict[str, Any]) -> dict[str, Any]:
    """Detach native-v1 behavior from dump-only provenance, with explicit scope.

    Unknown schema/refusal/future projections are literal passthroughs. Unknown
    fields survive. This projection is not advertised as an audit roundtrip.
    """
    if (reference.get("source") != "read_only_native_attack_source"
            or type(reference.get("version")) is not int or reference["version"] != 1
            or "behaviorView" in reference or "expressionNotation" in reference):
        return copy.deepcopy(reference)
    unrecognized_selection = False

    def select(value: Any) -> Any:
        nonlocal unrecognized_selection
        if isinstance(value, list):
            return [select(child) for child in value]
        if isinstance(value, dict):
            chosen = _selected_program(value, reference.get("identityPredicates"))
            if "identitySelected" in value and chosen is value:
                unrecognized_selection = True
            value = chosen
            return {key: select(child) for key, child in value.items()}
        return copy.deepcopy(value)

    selected = select(reference)
    if unrecognized_selection:
        return copy.deepcopy(reference)
    out = compact_attack_expressions(project_collision_behavior(selected))
    certificates = out.get("sourceMethods", [])

    def visit(value: Any) -> Any:
        if isinstance(value, list):
            return [visit(child) for child in value]
        if not isinstance(value, dict):
            return value
        if isinstance(value.get("method"), str) and (
                "sourceMethodSha256" in value or all(key in value for key in ("observations", "dependencies", "predicates", "symbols"))):
            behavior = _program(value)
            value = project_draw_layers(value, behavior, certificates) or behavior
        return {key: visit(child) for key, child in value.items()}

    # This roster exists solely to certify the capture, not to describe behavior.
    out.pop("sourceMethods", None)
    out = visit(out)
    if "expressionNotation" in out:
        out["expressionNotation"] = _NOTATION
    out["behaviorView"] = {"version": 1, "scope": _GUIDE}
    return out


def _snapshot_source_name(expression: str) -> str | None:
    """Names expose syntax only: ai slots are not guessed to mean age/direction."""
    def name(term: _Term) -> str | None:
        args = term.args or ()
        if term.name in {"ldelem.r4", "ldelem.ref", "ldelem.i4"} and len(args) == 2:
            array = name(args[0])
            index = args[1].name if args[1].args is None else ""
            return array + index if array and re.fullmatch(r"[0-9]+", index) else array
        if term.name in {"ldfld", "ldsfld"} and args and args[0].args is None:
            return args[0].name.rsplit(".", 1)[-1]
        if term.name == "div" and len(args) == 2:
            left, right = name(args[0]), name(args[1])
            return left + "Over" + right if left and right else None
        if term.opener == "[" and term.name not in {"alternatives", "source_block"}:
            return term.name.rsplit(".", 1)[-1]
        return None
    try:
        result = name(_Parser(expression, compact=True).parse())
    except (ValueError, IndexError, RecursionError):
        return None
    return result if result and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", result) else None


_BRANCH_TESTS = {
    "brfalse": "take branch when input is zero or null; otherwise fall through",
    "brtrue": "take branch when input is nonzero or non-null; otherwise fall through",
    "beq": "take branch when inputs[0] equals inputs[1]; unordered floating-point inputs do not compare equal",
    "bne.un": "take branch when inputs differ, including unordered floating-point inputs (NaN)",
    "blt": "take branch when inputs[0] < inputs[1]; integers signed, floating-point comparison ordered (NaN is false)",
    "ble": "take branch when inputs[0] <= inputs[1]; integers signed, floating-point comparison ordered (NaN is false)",
    "bgt": "take branch when inputs[0] > inputs[1]; integers signed, floating-point comparison ordered (NaN is false)",
    "bge": "take branch when inputs[0] >= inputs[1]; integers signed, floating-point comparison ordered (NaN is false)",
    "blt.un": "take branch when inputs[0] < inputs[1]; integers unsigned; floating-point comparison also takes branch if unordered (NaN)",
    "ble.un": "take branch when inputs[0] <= inputs[1]; integers unsigned; floating-point comparison also takes branch if unordered (NaN)",
    "bgt.un": "take branch when inputs[0] > inputs[1]; integers unsigned; floating-point comparison also takes branch if unordered (NaN)",
    "bge.un": "take branch when inputs[0] >= inputs[1]; integers unsigned; floating-point comparison also takes branch if unordered (NaN)",
}


def ordered_attack_context(reference: dict[str, Any]) -> dict[str, Any]:
    """Present known scalar source programs in one ordered stream, not three lists.

    This is not CFG reconstruction: branch opcodes, both successors, source blocks
    and reached-branch guards remain explicit. Addressed/multi-use snapshots stay
    in their existing representation until a faithful ordering can be supplied.
    """
    converted = False
    branch_tests: dict[str, str] = {}

    def visit(value: Any) -> Any:
        nonlocal converted
        if isinstance(value, list):
            return [visit(child) for child in value]
        if not isinstance(value, dict):
            return copy.deepcopy(value)
        out = {key: visit(child) for key, child in value.items()}
        if not all(key in value for key in ("observations", "dependencies", "predicates", "symbols")):
            return out
        if not set(value) <= _PROGRAM_FIELDS | {"identitySelection"}:
            return out
        definitions = value["dependencies"]
        if (not isinstance(definitions, dict)
                or any(not isinstance(row, dict) or not isinstance(row.get("expression"), str)
                       or "orderedSourceUses" in row for row in definitions.values())):
            return out
        # A switch has indexed successors (possibly duplicates), not the
        # conditional [taken,fallthrough] shape. Keep it and unfamiliar opcodes
        # literal until their ordering/legend is explicitly supported.
        for predicate in value["predicates"]:
            opcode = predicate.get("op", "") if isinstance(predicate, dict) else ""
            if (not isinstance(opcode, str) or (opcode[:-2] if opcode.endswith(".s") else opcode) not in _BRANCH_TESTS
                    or not isinstance(predicate.get("successors"), list) or len(predicate["successors"]) != 2):
                return out
        rows = [*value["observations"], *definitions.values(), *value["predicates"]]
        if any(not isinstance(row, dict) or not set(row) <= _ROW_FIELDS | {"step"}
               or type(row.get("step")) is not int or "at" in row for row in rows):
            return out
        # Names describe proven source use, not inferred gameplay roles.
        roles: dict[str, set[str]] = {name: set() for name in definitions}
        for row in value["observations"]:
            for argument, expression in row.get("arguments", {}).items():
                if expression in roles:
                    roles[expression].add(argument)
            if isinstance(row.get("expression"), str):
                try:
                    term = _Parser(row["expression"], compact=True).parse()
                except (ValueError, IndexError, RecursionError):
                    continue
                if term.name == "stfld" and term.args and len(term.args) == 3 and term.args[2].args is None:
                    if term.args[2].name in roles:
                        roles[term.args[2].name].add(term.args[0].name.rsplit(".", 1)[-1])
        names = {}
        for name, role in roles.items():
            label = next(iter(role)) if len(role) == 1 else _snapshot_source_name(definitions[name]["expression"])
            if label and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", label):
                label = None
            names[name] = (label + "Snapshot_" if label else "snapshot_") + name
        # A producer-owned identifier collision must not acquire our meaning.
        if any(re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", str(value))
               for name in names.values()):
            return out
        mapped = copy.deepcopy(value)
        try:
            _map_expressions(mapped, names)
        except (ValueError, IndexError, TypeError, AttributeError, RecursionError):
            return out
        operations = [dict(row, bind=names[name]) for name, row in mapped.pop("dependencies").items()]
        operations.extend(mapped.pop("observations"))
        operations.extend(mapped.pop("predicates"))
        # Equal steps remain equal: list ordering does not invent an ordering for
        # multiple records of the same source instruction.
        mapped["operations"] = sorted(operations, key=lambda row: row["step"])
        for predicate in mapped["operations"]:
            if "op" in predicate:
                opcode = predicate["op"]
                base = opcode[:-2] if opcode.endswith(".s") else opcode
                if base in _BRANCH_TESTS:
                    branch_tests[opcode] = _BRANCH_TESTS[base]
        converted = True
        return {key: visit(child) if key != "operations" else child for key, child in mapped.items()}

    result = visit(reference)
    if converted:
        reading = (
            "Read-only connected source, not executed gameplay. Scalar programs use one operations stream; "
            "addressed/unsupported programs retain observations/dependencies/predicates and their source steps. "
            "Read operations in step order; equal steps describe the same source instruction. "
            "bind names a value captured at that step, not a live expression. requiredPredicates lists "
            "reached branches, NOT necessarily true conditions. branchTests explains the used opcodes; "
            "successors are [taken,fallthrough] source blocks. Do not assume all listed operations execute. "
            "Fields/calls/aliases remain symbolic; alternatives are reaching definitions, not independent rolls."
        )
        if isinstance(result.get("behaviorView"), dict):
            old_scope = result["behaviorView"].get("scope", "")
            result["behaviorView"]["scope"] = reading if old_scope == _GUIDE else old_scope + " " + reading
        else:
            result["operationReading"] = reading
        if branch_tests:
            result["branchTests"] = branch_tests
    return result
