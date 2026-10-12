"""Internal prompt-prefix boundary marker. Never forwarded to a model as-is."""
from __future__ import annotations

from typing import Any
from collections.abc import Mapping, Sequence
import json
import math
import copy

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
    if "instructionMessageIndex" in marker:
        instruction_segment_index(payload)
        return None
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


def instruction_segment_index(payload: Mapping[str, Any]) -> int | None:
    """Validate complete builder-owned instructions, with disjoint USER data."""
    marker = payload.get(PROMPT_CACHE_METADATA_KEY)
    if isinstance(marker, dict) and "staticDataMessageIndex" in marker:
        raise ValueError("retired static schema data declaration is unsupported")
    if not isinstance(marker, dict) or "instructionMessageIndex" not in marker:
        return None
    index = marker["instructionMessageIndex"]
    messages = payload.get("messages")
    if (set(marker) != {"instructionMessageIndex"} or type(index) is not int
            or not isinstance(messages, list) or not 0 <= index < len(messages) - 1):
        raise ValueError("instruction segments require an existing developer/user pair")
    segment_rows = messages[index:index + 2]
    static, dynamic = segment_rows[:2]
    if (not isinstance(static, dict) or not isinstance(dynamic, dict)
            or any(not isinstance(row, dict) or row.get("role") not in {"system", "developer"} for row in messages[:index])
            or static.get("role") != "developer" or dynamic.get("role") != "user"
            or not isinstance(static.get("content"), str) or not isinstance(dynamic.get("content"), str)):
        raise ValueError("instruction segments require complete developer/user text objects")
    def unique_object(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("instruction segments contain duplicate JSON members")
            obj[key] = value
        return obj

    def reject_constant(value):
        raise ValueError("instruction segments require strict JSON values")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("instruction segments require finite JSON numbers")
        return number

    if any(not isinstance(row, dict) or row.get("role") != "user"
           or not isinstance(row.get("content"), str) for row in segment_rows[1:]):
        raise ValueError("schema data and case facts must remain complete user text objects")
    objects = [json.loads(message["content"], object_pairs_hook=unique_object,
                          parse_constant=reject_constant, parse_float=finite_float)
               for message in segment_rows]
    keys = set()
    for obj in objects:
        if not isinstance(obj, dict) or not obj or keys & obj.keys():
            raise ValueError("instruction segments require disjoint nonempty objects")
        keys.update(obj)
    if "schemaDefinitions" in objects[0]:
        definitions = objects[0]["schemaDefinitions"]
        if (not isinstance(definitions, dict) or set(definitions) != {"$defs"}
                or not isinstance(definitions["$defs"], dict) or not definitions["$defs"]
                or any(not isinstance(value, dict) or not value for value in definitions["$defs"].values())):
            raise ValueError("static schema definitions must be a nonempty schema object")
    return index


def with_instruction_segments(
    payload: dict[str, Any], dossier: Mapping[str, Any], instruction_keys: Sequence[str], *, message_index: int = 1,
) -> dict[str, Any]:
    """Builder declaration, not a cacheability-to-authority promotion.

    The caller owns every listed member as application instructions. Unlisted
    facts and case-specific output schemas remain USER data; the combined dossier is
    only a derived compatibility view for traces and syntax Repair.
    """
    if not instruction_keys or isinstance(instruction_keys, (str, bytes)):
        raise ValueError("instruction keys must be explicit")
    static = {key: dossier[key] for key in instruction_keys}
    dynamic = {key: value for key, value in dossier.items() if key not in static}
    messages = list(payload["messages"])
    source = messages[message_index]
    encode = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    messages[message_index:message_index + 1] = [
        {**source, "role": "developer", "content": encode(static)},
        {**source, "role": "user", "content": encode(dynamic)},
    ]
    out = {**payload, "messages": messages, PROMPT_CACHE_METADATA_KEY: {"instructionMessageIndex": message_index}}
    instruction_segment_index(out)
    return out


def with_schema_instruction_definitions(
    payload: dict[str, Any], schema_key: str, definition_paths: Mapping[str, tuple[str | int, ...]],
) -> dict[str, Any]:
    """Extract explicit owner-selected nodes, not inferred invariant subtrees.

    The response_format keeps its complete provider-compatible schema. Only the
    model-facing dossier uses root $defs references to canonical application-owned
    output grammar in the existing DEVELOPER contract. The caller explicitly owns
    these nodes; runtime enums, facts and Repair permissions stay in USER.
    """
    index = instruction_segment_index(payload)
    if index is None or "schemaDefinitions" in json.loads(payload["messages"][index]["content"]):
        raise ValueError("schema data requires an existing instruction/case pair")
    messages = copy.deepcopy(payload["messages"])
    dynamic = json.loads(messages[index + 1]["content"])
    schema = dynamic[schema_key]
    if "$defs" in schema or not definition_paths:
        raise ValueError("schema data requires explicit inline canonical nodes")
    definitions = {}
    for name, path in definition_paths.items():
        node = schema
        for key in path[:-1]:
            node = node[key]
        definitions[name] = node[path[-1]]
        node[path[-1]] = {"$ref": "#/$defs/" + name}
    encode = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    instructions = json.loads(messages[index]["content"])
    instructions["rules"].append(
        "The output schema's #/$defs/ references resolve against DEVELOPER schemaDefinitions.$defs; "
        "together they are the complete output contract, not additional output fields. Repair permissions remain unchanged."
    )
    instructions["schemaDefinitions"] = {"$defs": definitions}
    messages[index]["content"] = encode(instructions)
    messages[index + 1]["content"] = encode(dynamic)
    out = {**payload, "messages": messages}
    instruction_segment_index(out)
    return out


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
