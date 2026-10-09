"""Internal prompt-prefix boundary marker. Never forwarded to a model as-is."""
from __future__ import annotations

from typing import Any
from collections.abc import Mapping, Sequence
import json

PROMPT_CACHE_METADATA_KEY = "_infini_prompt_cache"


def static_instruction_prefix_parts(payload: Mapping[str, Any]) -> tuple[int, str, str] | None:
    """Validate explicit builder authority; return lossless JSON member framing.

    Cacheability alone never grants instruction authority. Text is sliced, not
    reserialized: only the shared object's comma/braces change on Codex wire.
    """
    if PROMPT_CACHE_METADATA_KEY not in payload:
        return None
    marker = payload[PROMPT_CACHE_METADATA_KEY]
    if not isinstance(marker, dict):
        raise ValueError("static instruction prefix requires an object marker")
    if "staticInstructionPrefix" not in marker:
        return None
    if set(marker) != {"messageIndex", "prefixChars", "staticInstructionPrefix"}:
        raise ValueError("static instruction prefix has unsupported marker fields")
    if marker["staticInstructionPrefix"] is not True:
        raise ValueError("static instruction prefix authority must be true")
    index, chars = marker.get("messageIndex"), marker.get("prefixChars")
    messages = payload.get("messages")
    if (type(index) is not int or type(chars) is not int or not isinstance(messages, list)
            or index < 0 or index >= len(messages)):
        raise ValueError("static instruction prefix requires an existing user message")
    message = messages[index]
    if (not isinstance(message, dict) or message.get("role") != "user"
            or not isinstance(message.get("content"), str)
            or not 0 < chars < len(message["content"])):
        raise ValueError("static instruction prefix requires a bounded user text prefix and tail")
    prefix, suffix = message["content"][:chars], message["content"][chars:]
    if not prefix.endswith(","):
        raise ValueError("static instruction prefix must end at a JSON member comma")
    static_text, dynamic_text = prefix[:-1] + "}", "{" + suffix

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("static instruction prefix contains duplicate JSON members")
            obj[key] = value
        return obj

    def reject_constant(_value: str) -> Any:
        raise ValueError("static instruction prefix requires strict JSON values")

    static, dynamic = (json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)
                       for text in (static_text, dynamic_text))
    if (not isinstance(static, dict) or not static or not isinstance(dynamic, dict)
            or not dynamic or static.keys() & dynamic.keys()):
        raise ValueError("static instruction prefix requires two disjoint nonempty JSON objects")
    return index, static_text, dynamic_text


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
    payload: dict[str, Any], *, message_index: int, prefix_chars: int,
    static_instruction_prefix: bool = False,
) -> dict[str, Any]:
    """Mark an exact authored user-text prefix, preserving all message bytes.

    The builder owns the static/dynamic boundary. This helper does not infer a
    boundary from prose. The optional authority flag declares that the prefix
    consists only of app-owned instructions, never user/parent/recipe data. It
    permits Codex-only developer framing of two disjoint JSON member groups;
    ordinary cache boundaries confer no such permission.
    """
    if type(static_instruction_prefix) is not bool:
        raise ValueError("static instruction prefix authority must be boolean")
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
    marker = {"messageIndex": message_index, "prefixChars": prefix_chars}
    if static_instruction_prefix:
        marker["staticInstructionPrefix"] = True
    out = {**payload, PROMPT_CACHE_METADATA_KEY: marker}
    static_instruction_prefix_parts(out)
    return out
