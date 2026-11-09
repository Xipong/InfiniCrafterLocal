"""Lossless, local reading notation for repeated Author source diagnostics.

This is a presentation-only normalization after the stage view is complete.
Native captures, code, coverage decisions and the authored runtime are unchanged.
Recognized diagnostics, source locations and repeated code blocks are projected.
Every source record retains its metadata and its exact reconstructed code.
"""
from __future__ import annotations

import copy
import json
import os
from collections import defaultdict
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
    source references retain their indices and scopes. Shared code blocks have
    a separate, explicitly named table and never change nativeSourceFacts indices.
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
    selected = result if _size(result) < _size(context) else context
    return compact_author_source_text(selected)


_SOURCE_TEXT_READING = (
    "sourceTextParts concatenates literal strings and nativeSourceText[sourceText] entries in order "
    "to recover the record's exact C# code, including all line endings. Source-line mappings refer to "
    "that reconstructed code. Each record keeps its own identity, guards, coverage and provenance; "
    "shared text does not make records or their execution equivalent."
)
_SOURCE_TEXT_KEYS = {"sourceTextParts", "nativeSourceText", "sourceTextNotation", "sourceText"}
_SOURCE_CODE_COVERAGE = {
    "approximate_identity_ast_regions", "approximate_identity_ast_method",
    "conditional_ast_regions", "identity_specialized_method", "whole_method",
}


def compact_author_source_text(context: dict[str, Any]) -> dict[str, Any]:
    """Share exact line-aligned source blocks, never infer equivalent records.

    This declared read-only normalization uses at most three sequential pieces:
    shared prefix, literal distinct middle, shared suffix. Method and coverage
    only group comparisons; actual character equality establishes sharing.
    No deltas, source offsets, graph pruning or source-reference renumbering.
    """
    def records(value: Any):
        if isinstance(value, dict):
            yield value
            for key, child in value.items():
                if key not in _LITERAL_KEYS:
                    yield from records(child)
        elif isinstance(value, list):
            for child in value:
                yield from records(child)

    # Future literal fields must not become ambiguous with this notation.
    if any(_SOURCE_TEXT_KEYS.intersection(row) for row in records(context)):
        return copy.deepcopy(context)
    result = copy.deepcopy(context)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in records(result):
        method, coverage = row.get("method"), row.get("coverage")
        if (isinstance(method, str) and isinstance(coverage, str)
                and coverage in _SOURCE_CODE_COVERAGE and isinstance(row.get("code"), str)):
            groups[method, coverage].append(row)
    shared: list[str] = []
    for rows in groups.values():
        if len(rows) < 2:
            continue
        codes = [row["code"] for row in rows]
        prefix = os.path.commonprefix(codes)
        prefix = prefix[:prefix.rfind("\n") + 1]
        suffix = os.path.commonprefix([code[len(prefix):][::-1] for code in codes])[::-1]
        suffix = suffix[suffix.find("\n") + 1:] if "\n" in suffix else ""
        # Share substantial readable bodies, not boilerplate headers or short lines.
        # This is an encoding threshold, never an evidence truncation/budget.
        prefix = prefix if len(prefix) >= 1024 and prefix.count("\n") >= 2 else ""
        suffix = suffix if len(suffix) >= 1024 and suffix.count("\n") >= 2 else ""
        if not prefix and not suffix:
            continue
        index = len(shared)
        blocks = [part for part in (prefix, suffix) if part]
        replacements = []
        for row, code in zip(rows, codes):
            middle = code[len(prefix):len(code) - len(suffix)] if suffix else code[len(prefix):]
            pieces: list[Any] = []
            if prefix:
                pieces.append({"sourceText": index})
            if middle:
                pieces.append(middle)
            if suffix:
                pieces.append({"sourceText": index + bool(prefix)})
            replacements.append({("sourceTextParts" if key == "code" else key):
                                 (pieces if key == "code" else value) for key, value in row.items()})
        if _size(replacements) + _size(blocks) >= _size(rows):
            continue
        shared.extend(blocks)
        for row, replacement in zip(rows, replacements):
            row.clear()
            row.update(replacement)
    if not shared:
        return copy.deepcopy(context)
    result["nativeSourceText"] = shared
    result["sourceTextNotation"] = _SOURCE_TEXT_READING
    return result if _size(result) < _size(context) else copy.deepcopy(context)
