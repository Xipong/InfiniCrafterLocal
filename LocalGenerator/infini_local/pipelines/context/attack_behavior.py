"""Model context: connected native behavior, not the provenance/audit dump.

This is an explicitly lossy *metadata* projection. It never executes expressions,
chooses branches, drops unknown mechanics, or truncates connected dependencies.
The original native capture remains the sole source/audit artifact.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import replace
from typing import Any

from infini_local.pipelines.context.attack_geometry import project_collision_behavior
from infini_local.pipelines.context.attack_draw import project_draw_layers
from infini_local.pipelines.context.attack_namespaces import (
    NATIVE_NAMESPACE_LEGEND, shorten_expression_names, shorten_symbol_name, shorten_symbol_signature,
)

from infini_local.pipelines.context.attack_expressions import (
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


def _map_expressions(program: dict, names: dict[str, str], *, preserve_unbound_opaque: bool = False,
                     short_namespaces: bool = False) -> bool:
    symbols = program["symbols"]
    namespace_changed = False

    def expression(text: str) -> str:
        nonlocal namespace_changed
        try:
            rendered = _expression_names(text, names,
                rgba_multiply=symbols.get("Color.op_Multiply") == "Xna.Color.op_Multiply(Xna.Color,float)",
                rgba_white=symbols.get("Color.get_White") == "Xna.Color.get_White()")
        except (ValueError, IndexError, RecursionError):
            # An opaque expression without any renamed dependency can stay
            # literal. If it may refer to one, retain the complete namespace.
            atom = r"A-Za-z0-9_@.#`"
            if not preserve_unbound_opaque or any(re.search(r"(?<![" + atom + r"])" + re.escape(name) + r"(?![" + atom + r"])", text)
                   for name in names):
                raise
            rendered = text
        if short_namespaces:
            shortened = shorten_expression_names(rendered)
            namespace_changed |= shortened != rendered
            return shortened
        return rendered

    def row(value: dict) -> None:
        nonlocal namespace_changed
        for key in ("expression", "receiver"):
            if isinstance(value.get(key), str):
                value[key] = expression(value[key])
        if short_namespaces and isinstance(value.get("call"), str):
            call = shorten_symbol_name(value["call"])
            namespace_changed |= call != value["call"]
            value["call"] = call
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
    if short_namespaces:
        shortened = {shorten_symbol_name(name): shorten_symbol_signature(value)
                     for name, value in symbols.items()}
        namespace_changed |= shortened != symbols
        program["symbols"] = shortened
        if isinstance(program.get("method"), str):
            method = shorten_symbol_signature(program["method"])
            namespace_changed |= method != program["method"]
            program["method"] = method
    return namespace_changed


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
    original_text = str(out)
    if not any(re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", original_text)
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


def _known_identity_receipt_fields(receipt: Any) -> bool:
    if not isinstance(receipt, dict):
        return False
    required = {"source", "version", "identityPredicates", "scope", "selectedEdges"}
    if set(receipt) == required:
        return True
    if set(receipt) != required | {"blockedIdentityReads", "blockedIdentityReadsOmitted"}:
        return False
    # Optional native refusal evidence is dump-only metadata, not authority to
    # choose an edge. Admit its exact bounded schema; future data stays literal.
    rows, omitted = receipt["blockedIdentityReads"], receipt["blockedIdentityReadsOmitted"]
    if (not isinstance(rows, list) or len(rows) > 32 or type(omitted) is not int or omitted < 0):
        return False
    for row in rows:
        if (not isinstance(row, dict)
                or set(row) != {"branchAt", "readAt", "field", "hazardAt", "hazardOp", "hazardMember", "hazardReason"}
                or any(type(row[key]) is not int or row[key] < 0 for key in ("branchAt", "readAt", "hazardAt"))
                or not isinstance(row["field"], str) or row["field"] not in {"Projectile.type", "Projectile.aiStyle"}
                or any(not isinstance(row[key], str) or not row[key] for key in ("hazardOp", "hazardMember"))
                or not isinstance(row["hazardReason"], str)
                or row["hazardReason"] not in {"direct_identity_write", "identity_address_exposed",
                    "actor_passing_call_uncertified", "actor_reference_stored"}):
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
    if (not _known_identity_receipt_fields(receipt)
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
    """Present known source programs in one ordered stream with literal links.

    This is not CFG reconstruction: branch opcodes, both successors, source blocks
    and reached-branch guards remain explicit. Addressed locals retain each source
    use/store and explicit alias uncertainty, without inferring their values.
    """
    converted = False
    branch_tests: dict[str, str] = {}
    has_addressed = False
    has_namespaces = False

    def source_row(row: Any) -> bool:
        if (not isinstance(row, dict) or not set(row) <= _ROW_FIELDS | {"step"}
                or type(row.get("step")) is not int or "at" in row or "orderedSourceUses" in row):
            return False
        if any(key in row and not isinstance(row[key], str)
               for key in ("expression", "receiver", "call", "kind", "scope", "id", "op")):
            return False
        if "block" in row and type(row["block"]) is not int:
            return False
        if any(key in row and (not isinstance(row[key], list) or any(not isinstance(value, str) for value in row[key]))
               for key in ("requiredPredicates", "inputs")):
            return False
        return ("arguments" not in row or isinstance(row["arguments"], dict)
                and all(isinstance(key, str) and isinstance(value, str) for key, value in row["arguments"].items()))

    def visit(value: Any) -> Any:
        nonlocal converted, has_addressed, has_namespaces
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
        if (not isinstance(definitions, dict) or not isinstance(value["observations"], list)
                or not isinstance(value["predicates"], list) or not isinstance(value["symbols"], dict)
                or any(not isinstance(name, str) or not isinstance(row, dict) for name, row in definitions.items())):
            return out
        addressed, scalars = {}, {}
        for name, row in definitions.items():
            if "orderedSourceUses" in row:
                if (set(row) != {"scope", "orderedSourceUses"} or not isinstance(row["scope"], str)
                        or not isinstance(row["orderedSourceUses"], list)
                        or any(not source_row(use) or not isinstance(use.get("expression"), str)
                               for use in row["orderedSourceUses"])):
                    return out
                addressed[name] = row
            elif source_row(row) and isinstance(row.get("expression"), str):
                scalars[name] = row
            else:
                return out
        # Block.Next is indexed switch targets followed by fallthrough.
        for predicate in value["predicates"]:
            opcode = predicate.get("op", "") if isinstance(predicate, dict) else ""
            if not isinstance(opcode, str) or not isinstance(predicate.get("successors"), list):
                return out
            base = opcode[:-2] if opcode.endswith(".s") else opcode
            successors = predicate["successors"]
            if (any(type(block) is not int for block in successors)
                    or (base == "switch" and (not successors or not isinstance(predicate.get("inputs"), list)
                                              or len(predicate["inputs"]) != 1))
                    or (base != "switch" and (base not in _BRANCH_TESTS or len(successors) != 2))):
                return out
        rows = [*value["observations"], *scalars.values(), *value["predicates"]]
        if any(not source_row(row) for row in rows):
            return out
        # Bind and address roles are explicit fields; local names carry no
        # inferred gameplay label and remain compact in large methods too.
        names = {name: ("a" if name in addressed else "v") + str(index)
                 for index, name in enumerate(definitions)}
        # A producer-owned identifier collision must not acquire our meaning.
        original_text = str(value)
        def collides(candidate: dict[str, str]) -> bool:
            return len(set(candidate.values())) != len(candidate) or any(
                re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", original_text)
                for name in candidate.values())
        if collides(names):
            for padding in range(1, 17):
                names = {name: ("a" if name in addressed else "v") + "_" * padding + str(index)
                         for index, name in enumerate(definitions)}
                if not collides(names):
                    break
        if collides(names):
            return out
        mapped = copy.deepcopy(value)
        try:
            names_shortened = _map_expressions(mapped, names, preserve_unbound_opaque=True, short_namespaces=True)
        except (ValueError, IndexError, TypeError, AttributeError, RecursionError):
            # Ordering never needs expression interpretation. If an opaque
            # expression might reference a renamed dependency, keep every name.
            mapped = copy.deepcopy(value)
            names = {name: name for name in definitions}
            names_shortened = False
        if names_shortened:
            mapped["nativeNames"] = 1
            has_namespaces = True
        operations, local_metadata, source_uses = [], {}, {}
        for name, row in mapped.pop("dependencies").items():
            if name not in addressed:
                operations.append(dict(row, bind=names[name]))
                continue
            local_metadata[names[name]] = {"scope": row["scope"]}
            for use in row["orderedSourceUses"]:
                # Equal instruction records can belong to several locals.
                # The membership list retains duplicates within each local too.
                key = json.dumps(use, ensure_ascii=False, separators=(",", ":"))
                if key not in source_uses:
                    source_uses[key] = dict(use, localUses=[])
                source_uses[key]["localUses"].append(names[name])
        operations.extend(source_uses.values())
        operations.extend(mapped.pop("observations"))
        operations.extend(mapped.pop("predicates"))
        if local_metadata:
            mapped["addressedLocals"] = local_metadata
            has_addressed = True
            # Hoist only a literal unanimous list from all records of a block.
            block_guards, conflicting = {}, set()
            for row in operations:
                if "block" not in row:
                    continue
                block, guards = row["block"], row.get("requiredPredicates")
                if (type(block) is not int or not isinstance(guards, list)
                        or any(not isinstance(guard, str) for guard in guards)):
                    conflicting.add(str(block))
                    continue
                key = str(block)
                if key in block_guards and block_guards[key] != guards:
                    conflicting.add(key)
                else:
                    block_guards[key] = guards
            block_guards = {key: guards for key, guards in block_guards.items() if key not in conflicting}
            if block_guards:
                mapped["blockGuards"] = block_guards
                for row in operations:
                    if str(row.get("block")) in block_guards:
                        row.pop("requiredPredicates", None)
        # Equal steps remain equal: list ordering does not invent an ordering for
        # multiple records of the same source instruction.
        mapped["operations"] = sorted(operations, key=lambda row: row["step"])
        for predicate in mapped["operations"]:
            if "op" in predicate:
                opcode = predicate["op"]
                base = opcode[:-2] if opcode.endswith(".s") else opcode
                if base == "switch":
                    branch_tests[opcode] = ("inputs[0] selects zero-based indexed successors; last successor is "
                                            "fallthrough for any other index; duplicate targets stay literal")
                elif base in _BRANCH_TESTS:
                    branch_tests[opcode] = _BRANCH_TESTS[base]
        converted = True
        return {key: visit(child) if key != "operations" else child for key, child in mapped.items()}

    result = visit(reference)
    if converted:
        reading = (
            "Read-only connected source, not executed gameplay. Read operations in step order; equal steps "
            "describe the same instruction and do not establish execution order. "
            "bind names a value captured at that step, not a live expression. requiredPredicates lists "
            "reached branches, NOT necessarily true conditions. branchTests explains the used opcodes; "
            "conditional successors are [taken,fallthrough] source blocks. Do not assume all listed operations execute. "
            "Fields/calls/aliases remain symbolic; alternatives are reaching definitions, not independent rolls. "
            "Unknown programs retain their original lists."
        )
        if has_addressed:
            reading += (" addressedLocals retains alias uncertainty; localUses links a source use/store to each "
                        "affected local, including duplicate memberships, without claiming its value. "
                        "blockGuards[block] supplies the exact reached-branch list for operations of that block; "
                        "other blocks retain requiredPredicates.")
        if has_namespaces:
            reading += " " + NATIVE_NAMESPACE_LEGEND
        if isinstance(result.get("behaviorView"), dict):
            old_scope = result["behaviorView"].get("scope", "")
            result["behaviorView"]["scope"] = reading if old_scope == _GUIDE else old_scope + " " + reading
        else:
            result["operationReading"] = reading
        if branch_tests:
            result["branchTests"] = branch_tests
    return result
