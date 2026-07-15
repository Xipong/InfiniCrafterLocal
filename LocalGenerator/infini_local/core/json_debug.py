from __future__ import annotations

"""Bounded, parseable JSON diagnostics.

Debug payloads used to be truncated by slicing the serialized string, producing
invalid JSON exactly when diagnostics became large.  This owner recursively
sanitizes unusual values and emits a bounded preview envelope when needed.
"""

from collections.abc import Mapping, Sequence
import math
from typing import Any

from infini_local.core import strict_json

_CIRCULAR = "<circular>"


def _json_safe(value: Any, seen: set[int]) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        if math.isnan(value):
            return "nan"
        return "inf" if value > 0 else "-inf"
    if isinstance(value, Mapping):
        marker = id(value)
        if marker in seen:
            return _CIRCULAR
        seen.add(marker)
        try:
            return {str(key): _json_safe(item, seen) for key, item in value.items()}
        finally:
            seen.remove(marker)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        marker = id(value)
        if marker in seen:
            return _CIRCULAR
        seen.add(marker)
        try:
            return [_json_safe(item, seen) for item in value]
        finally:
            seen.remove(marker)
    return str(value)


def _encoded(value: Any) -> str:
    return strict_json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def bounded_json_dumps(value: Any, max_chars: int = 6000) -> str:
    """Return valid JSON no longer than ``max_chars`` for diagnostic storage."""
    limit = max(2, int(max_chars))
    safe = _json_safe(value, set())
    text = _encoded(safe)
    if len(text) <= limit:
        return text

    # Debug strings are not executable contracts.  Once the full structure no
    # longer fits, preserve a bounded textual preview inside a valid JSON
    # envelope instead of slicing the JSON document mid-token.
    preview = text
    envelope: dict[str, Any] = {"truncated": True, "preview": preview}
    encoded = _encoded(envelope)
    if len(encoded) <= limit:
        return encoded

    low, high = 0, len(preview)
    best = "{}"
    while low <= high:
        middle = (low + high) // 2
        candidate = _encoded({"truncated": True, "preview": preview[:middle]})
        if len(candidate) <= limit:
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    return best


__all__ = ["bounded_json_dumps"]
