"""Internal prompt-prefix boundary marker. Never forwarded to a model as-is."""
from __future__ import annotations

from typing import Any
from collections.abc import Mapping, Sequence
import json

PROMPT_CACHE_METADATA_KEY = "_infini_prompt_cache"


def json_prefix_chars(payload: Mapping[str, Any], static_keys: Sequence[str]) -> int:
    """Length of the exact compact JSON prefix through initial static fields.

    With a dynamic tail the delimiter comma replaces the temporary closing
    brace. The caller must serialize the complete payload with the same compact
    separators and ensure_ascii=False; this routine does not reorder values.
    """
    keys = list(payload)
    if (not static_keys or isinstance(static_keys, (str, bytes))
            or list(static_keys) != keys[:len(static_keys)]):
        raise ValueError("static keys must be the nonempty initial JSON fields")
    encoded = json.dumps({key: payload[key] for key in static_keys},
                         ensure_ascii=False, separators=(",", ":"))
    return len(encoded) if len(static_keys) == len(keys) else len(encoded[:-1] + ",")


def with_prompt_cache_prefix(
    payload: dict[str, Any], *, message_index: int, prefix_chars: int
) -> dict[str, Any]:
    """Mark an exact authored user-text prefix, preserving all message bytes.

    The builder owns the static/dynamic boundary. This helper does not infer a
    boundary from prose or require the partial prefix to parse as JSON.
    """
    messages = payload.get("messages")
    if (
        type(message_index) is not int or type(prefix_chars) is not int
        or not isinstance(messages, list) or message_index < 0
        or message_index >= len(messages)
    ):
        raise ValueError("prompt cache boundary requires an existing user message")
    message = messages[message_index]
    if (
        not isinstance(message, dict) or message.get("role") != "user"
        or not isinstance(message.get("content"), str)
        or prefix_chars <= 0 or prefix_chars > len(message["content"])
    ):
        raise ValueError("prompt cache boundary requires a bounded user text prefix")
    return {**payload, PROMPT_CACHE_METADATA_KEY: {"messageIndex": message_index, "prefixChars": prefix_chars}}
