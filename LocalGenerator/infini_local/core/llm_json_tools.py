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
