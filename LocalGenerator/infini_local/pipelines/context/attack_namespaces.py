"""Reversible lexical aliases for native-source identifier components."""
from __future__ import annotations

import json
from dataclasses import replace

from infini_local.pipelines.context.attack_expressions import (
    _ALIASES, _NAME, _Parser, _SHORT, _Term, _render,
)

_SHORT_NAMES = {"Projectile": "P", "Entity": "E", "Vector2": "Vec"}
_LONG_NAMES = {short: long for long, short in _SHORT_NAMES.items()}
NATIVE_NAMESPACE_LEGEND = (
    "Within programs marked nativeNames=1, identifier components P=Projectile, E=Entity, Vec=Vector2 "
    "in expressions and symbol signatures retain namespace prefixes and overloads. Other programs "
    "keep their original namespace. Quoted literals are unchanged."
)


def _identifier(name: str, *, restore: bool) -> str:
    if _NAME.fullmatch(name) is None:
        return name
    parts = name.split(".")
    if not restore and any(part in _LONG_NAMES for part in parts):
        raise ValueError("native namespace alias collides with a source identifier")
    aliases = _LONG_NAMES if restore else _SHORT_NAMES
    return ".".join(aliases.get(part, part) for part in parts)


def _symbol_tokens(text: str, *, restore: bool) -> str:
    """Keep signature punctuation, numeric lexemes and quoted strings verbatim."""
    result, at = [], 0
    while at < len(text):
        if text[at] == '"':
            _, end = json.JSONDecoder().raw_decode(text, at)
            result.append(text[at:end])
            at = end
            continue
        # A receiver field starts after '.' and a static field after '@'. A
        # complete dotted/addressed identifier was already consumed as one token.
        boundary = at == 0 or not (text[at - 1].isalnum() or text[at - 1] in "_#`")
        token = _NAME.match(text, at) if boundary else None
        if token is not None:
            result.append(_identifier(token[0], restore=restore))
            at = token.end()
        else:
            result.append(text[at])
            at += 1
    return "".join(result)


def _expression_tree_names(term: _Term, *, restore: bool) -> _Term:
    # Parser expands Vector2.add. Keep its compact spelling before shortening
    # the owner; the inverse restores the same native operator.
    name = term.name if restore else _SHORT.get(term.name, term.name)
    name = _identifier(name, restore=restore)
    if restore:
        name = _ALIASES.get(name, name)
    args = tuple(_expression_tree_names(arg, restore=restore) for arg in term.args) if term.args is not None else None
    return replace(term, name=name, args=args)


def shorten_expression_names(text: str) -> str:
    """Abbreviate canonical parsed expressions; opaque syntax stays literal.

    A reserved source alias raises so the caller can retain the whole program
    namespace. No branch, arithmetic or string-literal value is evaluated.
    """
    _symbol_tokens(text, restore=False)  # Check collisions in opaque syntax too.
    try:
        tree = _Parser(text, compact=True).parse()
        if _render(tree, compact=True) != text:
            return text
    except (ValueError, IndexError, RecursionError):
        return text
    result = _render(_expression_tree_names(tree, restore=False), compact=True)
    restored = _render(_expression_tree_names(_Parser(result, compact=True).parse(), restore=True), compact=True)
    if restored != text:
        raise ValueError("native namespace expression is not reversible")
    return result


def shorten_symbol_name(name: str) -> str:
    """Keep exact symbol identity and overload suffixes under the aliases."""
    if _NAME.fullmatch(name) is None:
        _symbol_tokens(name, restore=False)
        return name
    result = _identifier(name, restore=False)
    if _identifier(result, restore=True) != name:
        raise ValueError("native namespace symbol is not reversible")
    return result


def shorten_symbol_signature(signature: str) -> str:
    """Keep the complete signature under lexical component aliases."""
    result = _symbol_tokens(signature, restore=False)
    if _symbol_tokens(result, restore=True) != signature:
        raise ValueError("native namespace signature is not reversible")
    return result
