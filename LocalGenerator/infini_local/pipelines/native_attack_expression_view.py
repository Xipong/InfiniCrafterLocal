"""Lossless, non-executing notation for certified native attack source expressions.

The dump stays authoritative. This view changes syntax, never folds arithmetic,
chooses a branch, samples state or invents a geometry description.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import Any, Callable

_BINARY = {"add": "+", "sub": "-", "mul": "*", "div": "/"}
_ALIASES = {"f32_at": "ldelem.r4", "ref_at": "ldelem.ref", "i32_at": "ldelem.i4",
            "Vector2.add": "Vector2.op_Addition", "Vector2.sub": "Vector2.op_Subtraction",
            "Vector2.mul": "Vector2.op_Multiply", "Vector2.div": "Vector2.op_Division",
            "Color.mul": "Color.op_Multiply"}
_SHORT = {value: key for key, value in _ALIASES.items()}
_SYMBOL_ALIASES = {"XnaGfx.": "Microsoft.Xna.Framework.Graphics.", "Xna.": "Microsoft.Xna.Framework.",
    "T.": "Terraria.", "Content.": "ReLogic.Content.", "float": "System.Single", "double": "System.Double",
    "int": "System.Int32", "uint": "System.UInt32", "bool": "System.Boolean", "string": "System.String",
    "void": "System.Void", "byte": "System.Byte"}


def _symbol_pattern(mapping: dict[str, str]) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9_])(?:" + "|".join(
        re.escape(key) + ("" if key.endswith(".") else r"(?![A-Za-z0-9_])")
        for key in sorted(mapping, key=len, reverse=True)) + ")")


_SYMBOL_SHORT = {value: key for key, value in _SYMBOL_ALIASES.items()}
_SYMBOL_SHORT_PATTERN = _symbol_pattern(_SYMBOL_SHORT)
_SYMBOL_LONG_PATTERN = _symbol_pattern(_SYMBOL_ALIASES)


def _symbol_view(text: str) -> str:
    return _SYMBOL_SHORT_PATTERN.sub(lambda match: _SYMBOL_SHORT[match.group()], text)


def _symbol_restore(text: str) -> str:
    return _SYMBOL_LONG_PATTERN.sub(lambda match: _SYMBOL_ALIASES[match.group()], text)


_GUIDE = {"format": "native-source-expressions-v1",
    "math": "Parenthesized + - * / = IL add sub mul div, exact order/grouping, no folding or evaluation.",
    "fields": "(r).Owner.f = ldfld(Owner.f,r); @Owner.f = ldsfld; set(field,v) = stfld. Each use re-reads live state.",
    "calls": _ALIASES, "symbolTypeAliases": _SYMBOL_ALIASES}
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_@.#`]*")
_NUMBER = re.compile(r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_JSON = json.JSONDecoder()


@dataclass(frozen=True)
class _Term:
    name: str
    args: tuple[_Term, ...] | None = None
    opener: str = "("
    separators: tuple[str, ...] = ()


def _call(name: str, *args: _Term) -> _Term:
    return _Term(name, args, separators=(",",) * max(0, len(args) - 1))


class _Parser:
    def __init__(self, text: str, compact: bool):
        self.text, self.compact, self.at = text, compact, 0

    def term(self, depth: int = 0) -> _Term:
        if depth > 80 or self.at >= len(self.text):
            raise ValueError("unsupported source expression")
        start = self.at
        lead = self.text[self.at]
        if self.compact and lead == "(":
            self.at += 1
            left = self.term(depth + 1)
            if self.text[self.at:self.at + 1] == ")":
                self.at += 1
                self.take(".")
                field = self.name()
                return _call("ldfld", _Term(field), left)
            op = self.text[self.at:self.at + 1]
            if op not in _BINARY.values():
                raise ValueError("unsupported infix operation")
            self.at += 1
            right = self.term(depth + 1)
            self.take(")")
            return _call(next(key for key, value in _BINARY.items() if value == op), left, right)
        if self.compact and lead == "@":
            self.at += 1
            return _call("ldsfld", _Term(self.name()))
        if lead in '\"[{':
            _, end = _JSON.raw_decode(self.text, self.at)
            self.at = end
            return _Term(self.text[start:end])
        number = _NUMBER.match(self.text, self.at)
        if number:
            self.at = number.end()
            return _Term(number.group())
        name = self.name()
        opener = self.text[self.at:self.at + 1]
        if opener == "=":
            self.at += 1
            return _Term(name, (self.term(depth + 1),), "=")
        if opener not in ("(", "["):
            return _Term(name)
        self.at += 1
        close = ")" if opener == "(" else "]"
        args: list[_Term] = []
        separators: list[str] = []
        if self.text[self.at:self.at + 1] != close:
            while True:
                args.append(self.term(depth + 1))
                delimiter = self.text[self.at:self.at + 1]
                if delimiter == close:
                    break
                if delimiter not in (",", ";"):
                    raise ValueError("unsupported argument delimiter")
                separators.append(delimiter)
                self.at += 1
        self.take(close)
        if self.compact and name == "set" and len(args) == 2 and args[0].name == "ldfld" and args[0].args is not None:
            return _call("stfld", *args[0].args, args[1])
        return _Term(_ALIASES.get(name, name) if self.compact else name, tuple(args), opener, tuple(separators))

    def name(self) -> str:
        match = _NAME.match(self.text, self.at)
        if match is None:
            raise ValueError("unsupported source atom")
        self.at = match.end()
        return match.group()

    def take(self, value: str) -> None:
        if not self.text.startswith(value, self.at):
            raise ValueError("unsupported source delimiter")
        self.at += len(value)

    def parse(self) -> _Term:
        term = self.term()
        if self.at != len(self.text):
            raise ValueError("unconsumed source expression")
        return term


def _render(term: _Term, compact: bool) -> str:
    if term.args is None:
        return term.name
    args = [_render(arg, compact) for arg in term.args]
    if term.opener == "=":
        return term.name + "=" + args[0]
    ordinary = term.opener == "(" and all(separator == "," for separator in term.separators)
    if compact and ordinary:
        if term.name in _BINARY and len(args) == 2:
            return "(" + args[0] + _BINARY[term.name] + args[1] + ")"
        if term.name == "ldfld" and len(args) == 2 and term.args[0].args is None:
            return "(" + args[1] + ")." + args[0]
        if term.name == "ldsfld" and len(args) == 1 and term.args[0].args is None:
            return "@" + args[0]
        if term.name == "stfld" and len(args) == 3 and term.args[0].args is None:
            return "set((" + args[1] + ")." + args[0] + "," + args[2] + ")"
    name = _SHORT.get(term.name, term.name) if compact else term.name
    joined = "".join((term.separators[index - 1] if index else "") + arg for index, arg in enumerate(args))
    return name + term.opener + joined + (")" if term.opener == "(" else "]")


def _restore(text: str) -> str:
    try:
        return _render(_Parser(text, compact=True).parse(), compact=False)
    except (ValueError, IndexError, RecursionError):
        return text


def _pretty(text: str) -> str:
    try:
        tree = _Parser(text, compact=False).parse()
        if _render(tree, compact=False) != text:
            return text
        result = _render(tree, compact=True)
        if _restore(result) != text:
            raise ValueError("non-reversible source syntax")
        return result
    except (IndexError, RecursionError):
        return text


def _map_program_expressions(value: Any, convert: Callable[[str], str], symbols: Callable[[str], str]) -> None:
    def expression(row: dict[str, Any]) -> None:
        for key in ("expression", "receiver"):
            if isinstance(row.get(key), str):
                row[key] = convert(row[key])

    if isinstance(value, list):
        for child in value:
            _map_program_expressions(child, convert, symbols)
    elif isinstance(value, dict):
        if isinstance(value.get("method"), str) and "sourceMethodSha256" in value:
            value["method"] = symbols(value["method"])
        if isinstance(value.get("method"), str) and all(key in value for key in ("observations", "dependencies", "predicates", "symbols")):
            value["symbols"] = {key: symbols(item) if isinstance(item, str) else item for key, item in value["symbols"].items()}
            for row in value["observations"]:
                if not isinstance(row, dict):
                    continue
                expression(row)
                if isinstance(row.get("arguments"), dict):
                    row["arguments"] = {key: convert(item) if isinstance(item, str) else item for key, item in row["arguments"].items()}
            for row in value["dependencies"].values():
                if isinstance(row, dict):
                    expression(row)
                    for use in row.get("orderedSourceUses", []):
                        if isinstance(use, dict):
                            expression(use)
            for row in value["predicates"]:
                if isinstance(row, dict) and isinstance(row.get("inputs"), list):
                    row["inputs"] = [convert(item) if isinstance(item, str) else item for item in row["inputs"]]
        for child in value.values():
            _map_program_expressions(child, convert, symbols)


def compact_attack_expressions(reference: dict[str, Any]) -> dict[str, Any]:
    """Return a detached model view; unrecognized source syntax remains literal."""
    out = copy.deepcopy(reference)
    if reference.get("source") != "read_only_native_attack_source" or type(reference.get("version")) is not int or reference["version"] != 1 or "expressionNotation" in reference:
        return out
    changed = False

    def convert(text: str) -> str:
        nonlocal changed
        try:
            result = _pretty(text)
        except ValueError:
            result = text
        if _restore(result) != text:
            # Reserved notation collision: preserve the whole observation instead
            # of letting a future source atom acquire a different meaning.
            raise ValueError("source notation collision")
        changed |= result != text
        return result

    def symbol(text: str) -> str:
        nonlocal changed
        result = _symbol_view(text)
        if _symbol_restore(result) != text:
            raise ValueError("source symbol alias collision")
        changed |= result != text
        return result

    try:
        _map_program_expressions(out, convert, symbol)
    except (ValueError, TypeError, AttributeError):
        return copy.deepcopy(reference)
    if changed:
        out["expressionNotation"] = copy.deepcopy(_GUIDE)
    return out


def expand_attack_expressions(reference: dict[str, Any]) -> dict[str, Any]:
    """Decode notation for auditing; never execute the source or edit gameplay."""
    out = copy.deepcopy(reference)
    if out.get("expressionNotation") != _GUIDE:
        return out
    del out["expressionNotation"]
    _map_program_expressions(out, _restore, _symbol_restore)
    return out
