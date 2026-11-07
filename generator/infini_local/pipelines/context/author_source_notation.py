"""Lossless, local reading notation for repeated Author source diagnostics.

This is a presentation-only normalization after the stage view is complete.
Native captures, code, coverage decisions and the authored runtime are unchanged.
Only two fully recognized shapes are projected; future shapes stay literal.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any

_EFFECT_SITE = re.compile(
    r"(?P<context>motion_source|motion_dispatch_effect):"
    r"(?P<method>[A-Za-z0-9_.]+):effect_source_site@"
    r"(?P<offset>0|[1-9][0-9]*):(?P<reason>effect_source_site_count_bound)\Z"
)
_LITERAL_KEYS = {"tooltipLines", "tooltipSource", "generatedParent"}
_DIAGNOSTIC_READING = (
    "An unresolved row with context, method, reason and ilOffsets records the same extraction failure "
    "at every listed native IL offset, in order, including repetitions. Its exact diagnostic strings are "
    "context + ':' + method + ':effect_source_site@' + offset + ':' + reason. "
    "These are unknown source effects, not proved absence or executed behavior. Other entries remain literal."
)
_LOCATION_READING = (
    "Predicate ilSites are the original native IL sites, not evaluated conditions. Each site gives its "
    "ilOffset and sourceLines: inclusive [first,last] line ranges in the enclosing sourceRecord's C# code, "
    "or null when source mapping is unavailable. Order and repeated ranges/sites are retained. "
    "A mapped site expands to mapping=source_lines with locations containing that same ilOffset, "
    "startLine and endLine; null expands to mapping=unavailable. "
    "An ilSites predicate expands to sourceSites plus mapping=raw_predicate_sites."
)


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _effect_site(row: Any) -> re.Match[str] | None:
    match = _EFFECT_SITE.fullmatch(row) if isinstance(row, str) else None
    if match is None:
        return None
    offset = match["offset"]
    # Native IL offsets are nonnegative Int32 values. Unknown/future values
    # remain literal, before int() can reject an arbitrarily long digit string.
    if len(offset) > 10 or (len(offset) == 10 and offset > "2147483647"):
        return None
    return match


def _diagnostic_runs(rows: list[Any]) -> list[Any]:
    """Group adjacent exact diagnostic patterns, never reorder or deduplicate."""
    result: list[Any] = []
    index = 0
    while index < len(rows):
        match = _effect_site(rows[index])
        if match is None:
            result.append(copy.deepcopy(rows[index]))
            index += 1
            continue
        group = {key: match[key] for key in ("context", "method", "reason")}
        offsets = [int(match["offset"])]
        end = index + 1
        while end < len(rows):
            following = _effect_site(rows[end])
            if following is None or any(following[key] != group[key] for key in group):
                break
            offsets.append(int(following["offset"]))
            end += 1
        grouped = {**group, "ilOffsets": offsets}
        original = rows[index:end]
        result.extend([grouped] if _size(grouped) < _size(original) else copy.deepcopy(original))
        index = end
    return result


def _source_sites(value: dict[str, Any]) -> dict[str, Any] | None:
    """Name IL sites and line ranges directly, without nested repeated offsets."""
    if (set(value) != {"id", "sourceSites", "mapping"}
            or not isinstance(value["id"], str) or not value["id"]
            or value["mapping"] != "raw_predicate_sites"
            or not isinstance(value["sourceSites"], list) or not value["sourceSites"]):
        return None
    sites = []
    for site in value["sourceSites"]:
        if (not isinstance(site, dict) or type(site.get("ilOffset")) is not int
                or site["ilOffset"] < 0):
            return None
        if set(site) == {"mapping", "ilOffset"} and site["mapping"] == "unavailable":
            sites.append({"ilOffset": site["ilOffset"], "sourceLines": None})
            continue
        if (set(site) != {"mapping", "ilOffset", "locations"} or site["mapping"] != "source_lines"
                or not isinstance(site["locations"], list) or not site["locations"]):
            return None
        lines = []
        for row in site["locations"]:
            if (not isinstance(row, dict) or set(row) != {"ilOffset", "startLine", "endLine"}
                    or type(row["ilOffset"]) is not int or row["ilOffset"] != site["ilOffset"]
                    or type(row["startLine"]) is not int or type(row["endLine"]) is not int
                    or not 1 <= row["startLine"] <= row["endLine"]):
                return None
            lines.append([row["startLine"], row["endLine"]])
        sites.append({"ilOffset": site["ilOffset"], "sourceLines": lines})
    result = {"id": value["id"], "ilSites": sites}
    return result if _size(result) < _size(value) else None


def compact_author_parent_context(context: dict[str, Any]) -> dict[str, Any]:
    """Keep all current-stage facts with a self-contained, reversible notation.

    No provider/runtime schema or additional model action is involved. Existing
    source references retain their indices and scopes; no new references arise.
    Literal/generated data and unrecognized rows are never interpreted.
    """
    def collision(value: Any) -> bool:
        if isinstance(value, dict):
            if ("parentContextNotation" in value or set(value) == {"id", "ilSites"}
                    or set(value) == {"context", "method", "reason", "ilOffsets"}):
                return True
            return any(collision(child) for key, child in value.items() if key not in _LITERAL_KEYS)
        return isinstance(value, list) and any(collision(child) for child in value)

    # A future literal using our output notation cannot be distinguished from
    # a projected row by the reader. Keep the complete context literal instead.
    if collision(context):
        return copy.deepcopy(context)
    used: set[str] = set()

    def visit(value: Any) -> Any:
        if isinstance(value, list):
            return [visit(child) for child in value]
        if not isinstance(value, dict):
            return copy.deepcopy(value)
        sites = _source_sites(value)
        if sites is not None:
            used.add("sourceLocations")
            return sites
        result = {}
        for key, child in value.items():
            if key in _LITERAL_KEYS:
                result[key] = copy.deepcopy(child)
            elif key == "unresolved" and isinstance(child, list):
                grouped = _diagnostic_runs(child)
                if grouped != child:
                    used.add("unresolvedDiagnostics")
                result[key] = grouped
            else:
                result[key] = visit(child)
        return result

    result = visit(context)
    guides = {"unresolvedDiagnostics": _DIAGNOSTIC_READING, "sourceLocations": _LOCATION_READING}
    if used:
        result = {"parentContextNotation": {key: text for key, text in guides.items() if key in used}, **result}
    return result if _size(result) < _size(context) else copy.deepcopy(context)
