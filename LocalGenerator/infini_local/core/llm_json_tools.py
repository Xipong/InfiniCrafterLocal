from __future__ import annotations

"""LLM JSON extraction helpers.

Local models often return fenced JSON, prose around JSON, or duplicate objects like
`{...}{...}`.  These helpers are intentionally pure and side-effect free so the
HTTP/LLM transport code in server.py can import them without pulling in gameplay
state.
"""

import json
import re
from typing import Any


def _visible_model_output(text: str) -> str:
    """Remove model-private thought channels before scanning authored JSON."""
    visible = text or ""
    for tag in ("thought", "analysis"):
        visible = re.sub(
            rf"<{tag}\b[^>]*>.*?</{tag}\s*>",
            "",
            visible,
            flags=re.IGNORECASE | re.DOTALL,
        )
        # A truncated private channel has no authored answer. Dropping its tail is
        # safer than parsing a JSON example embedded in unfinished reasoning.
        visible = re.sub(
            rf"<{tag}\b[^>]*>.*\Z",
            "",
            visible,
            flags=re.IGNORECASE | re.DOTALL,
        )
    return visible


def json_object_candidates(text: str) -> list[str]:
    """Return complete top-level JSON object substrings from arbitrary LLM text.

    A greedy regex is unsafe for `{...}{...}` responses. This scanner tracks
    braces, strings, and escapes, then returns each complete object independently.
    """
    text = _visible_model_output(text).strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    out: list[str] = []
    start: int | None = None
    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if start is None:
            if ch == "{":
                start = i
                depth = 1
                in_string = False
                escape = False
            continue
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                out.append(text[start:i + 1])
                start = None
    return out


def extract_json(text: str) -> str:
    candidates = json_object_candidates(text)
    return candidates[0] if candidates else (text or "").strip()


def _candidate_with_one_missing_root_closer(text: str) -> str | None:
    """Close only an otherwise complete outer object ending at a nested `}`."""
    visible = _visible_model_output(text).strip()
    visible = re.sub(r"^```(?:json)?", "", visible).strip()
    visible = re.sub(r"```$", "", visible).strip()
    if not visible.startswith("{") or not visible.endswith("}"):
        return None
    containers: list[str] = []
    in_string = False
    escaped = False
    for char in visible:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "{[":
            containers.append(char)
        elif char in "}]":
            if not containers or containers.pop() != ("{" if char == "}" else "["):
                return None
    return visible + "}" if not in_string and containers == ["{"] else None


def recover_object_with_syntax_only_repairs(text: str) -> dict[str, Any] | None:
    """Repair bounded punctuation/key quotes without changing any authored value.

    Only duplicate/trailing commas, bare ASCII object keys followed by a
    colon, and one missing outer brace after a complete nested object are
    eligible. Strings and scalar tokens are copied byte-for-byte; missing
    values, array holes, duplicate keys, and non-JSON constants fail.
    The caller must compare the recovered object with Format Repair's answer.
    """
    candidates = json_object_candidates(text)
    if not candidates:
        closed = _candidate_with_one_missing_root_closer(text)
        if closed is not None:
            candidates = [closed]
    for candidate in candidates:
        output: list[str] = []
        containers: list[str] = []
        in_string = False
        escaped = False
        edits = 0
        index = 0
        while index < len(candidate):
            char = candidate[index]
            if in_string:
                output.append(char)
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                index += 1
                continue
            if char == '"':
                in_string = True
            elif char in "{[":
                containers.append(char)
            elif char in "}]":
                if not containers or containers.pop() != ("{" if char == "}" else "["):
                    break
            elif char == ",":
                previous_index = next((position for position in range(len(output) - 1, -1, -1)
                                       if not output[position].isspace()), -1)
                previous = output[previous_index] if previous_index >= 0 else ""
                next_index = index + 1
                while next_index < len(candidate) and candidate[next_index].isspace():
                    next_index += 1
                following = candidate[next_index:next_index + 1]
                if previous == "," and containers and containers[-1] == "{":
                    if following == "}":
                        del output[previous_index]  # Both object commas are redundant.
                        edits += 1
                    edits += 1
                    index += 1
                    continue
                if following in ("]", "}") and previous not in ("[", "{", ",", ":"):
                    edits += 1
                    index += 1
                    continue
            elif char.isascii() and (char.isalpha() or char == "_") and containers and containers[-1] == "{":
                previous = next((value for value in reversed(output) if not value.isspace()), "")
                if previous in ("{", ","):
                    bare_key = re.match(r"[A-Za-z_][A-Za-z0-9_]*", candidate[index:])
                    if bare_key is not None:
                        end = index + len(bare_key.group())
                        next_index = end
                        while next_index < len(candidate) and candidate[next_index].isspace():
                            next_index += 1
                        if candidate[next_index:next_index + 1] == ":":
                            output.extend(('"', bare_key.group(), '"'))
                            edits += 1
                            index = end
                            continue
            output.append(char)
            index += 1
        if containers or in_string or edits > 64:
            continue

        def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate JSON key")
                result[key] = value
            return result

        def reject_constant(value: str) -> None:
            raise ValueError(f"non-JSON constant {value}")

        try:
            recovered = json.loads("".join(output), object_pairs_hook=unique_object, parse_constant=reject_constant)
        except (TypeError, ValueError):
            continue
        if isinstance(recovered, dict):
            return recovered
    return None


def parse_first_valid_llm_json(text: str) -> dict[str, Any]:
    last_error: Exception | None = None
    for cand in json_object_candidates(text):
        try:
            parsed = json.loads(cand)
            if isinstance(parsed, dict):
                return parsed
        except Exception as e:
            last_error = e
            continue
    if last_error:
        raise last_error
    parsed = json.loads(extract_json(text))
    if not isinstance(parsed, dict):
        raise ValueError("LLM JSON root is not an object")
    return parsed
