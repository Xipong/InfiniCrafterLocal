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
    "operations on all RGBA channels, including native rounding/clamping, not alpha alone. Calls retain signatures."
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
                     "unresolved", "identityWindows", "predicateSources", "identitySelection"}
    known_row = _ROW_FIELDS
    rows = [*out["observations"], *out["dependencies"].values(), *out["predicates"]]
    if (not set(out) <= known_program or any(not isinstance(row, dict) or not set(row) <= known_row
            or not isinstance(row.get("orderedSourceUses", []), list) for row in rows)):
        return copy.deepcopy(value)
    rows += [use for row in rows for use in row.get("orderedSourceUses", [])]
    if any(not isinstance(row, dict) or not set(row) <= known_row for row in rows):
        return copy.deepcopy(value)
    if not any(re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", str(out))
                         for name in names.values()):
        renamed = copy.deepcopy(out)
        try:
            _map_expressions(renamed, names)
        except (ValueError, IndexError, TypeError, AttributeError, RecursionError):
            pass
        else:
            renamed["dependencies"] = {names[key]: child for key, child in renamed["dependencies"].items()}
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
                   "predicates", "symbols", "coverage", "unresolved", "identityWindows", "predicateSources"}


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
    for graph in (value, selected):
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
    out["identitySelection"] = {
        "forCapturedIdentity": True,
        "scope": "Only certified receiver identity branches selected; dynamic conditions and unknown alias/hook behavior remain symbolic.",
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
    out = compact_attack_expressions(selected)

    def visit(value: Any) -> Any:
        if isinstance(value, list):
            return [visit(child) for child in value]
        if not isinstance(value, dict):
            return value
        if isinstance(value.get("method"), str) and (
                "sourceMethodSha256" in value or all(key in value for key in ("observations", "dependencies", "predicates", "symbols"))):
            value = _program(value)
        return {key: visit(child) for key, child in value.items()}

    # This roster exists solely to certify the capture, not to describe behavior.
    out.pop("sourceMethods", None)
    out = visit(out)
    if "expressionNotation" in out:
        out["expressionNotation"] = _NOTATION
    out["behaviorView"] = {"version": 1, "scope": _GUIDE}
    return out
