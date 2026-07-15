from __future__ import annotations

"""Strict JSON parsing/serialization shared by machine boundaries.

Python's :mod:`json` accepts non-finite JavaScript constants by default and
silently resolves duplicate object members with last-write-wins semantics.
This module defines one finite, unambiguous policy for HTTP, durable cache files,
and release gates before values reach strict typed DTO binding.
"""

import json
import math
from typing import Any, Callable


class StrictJsonError(ValueError):
    """Raised when a value is syntactically JSON but violates strict policy."""


def _reject_constant(token: str) -> Any:
    raise StrictJsonError(f"non-finite JSON number is not allowed: {token}")


def _finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise StrictJsonError(f"JSON number is outside finite float range: {token}")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def loads(
    value: str | bytes | bytearray,
    *,
    object_hook: Callable[[dict[str, Any]], Any] | None = None,
) -> Any:
    """Parse strict RFC-style JSON with finite numbers and unique keys."""
    return json.loads(
        value,
        parse_constant=_reject_constant,
        parse_float=_finite_float,
        object_pairs_hook=(
            (lambda pairs: object_hook(_unique_object(pairs)))
            if object_hook is not None
            else _unique_object
        ),
    )


def loads_object(value: str | bytes | bytearray) -> dict[str, Any]:
    parsed = loads(value)
    if not isinstance(parsed, dict):
        kind = "null" if parsed is None else type(parsed).__name__
        raise StrictJsonError(f"JSON root must be an object, got {kind}")
    return parsed


def dumps(value: Any, **kwargs: Any) -> str:
    """Serialize strict JSON; callers cannot opt back into NaN/Infinity."""
    kwargs["allow_nan"] = False
    return json.dumps(value, **kwargs)


__all__ = ["StrictJsonError", "loads", "loads_object", "dumps"]
