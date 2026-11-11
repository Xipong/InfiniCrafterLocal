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
    return _share_local_entry_condition(compact_author_source_text(selected))


_SOURCE_TEXT_READING = (
    "sourceTextParts concatenates literal strings and nativeSourceText[sourceText] entries in order "
    "to recover the record's exact C# code, including all line endings. Source-line mappings refer to "
    "that reconstructed code. Each record keeps its own identity, guards, coverage and provenance; "
    "shared text does not make records or their execution equivalent."
)
_SOURCE_TEXT_VALUE_READING = (
    " A nativeSourceFacts entry {sourceTextValueParts:[...]} uses the same concatenation to represent "
    "a string, not an object. Every sourceSameAs reference to that entry still resolves to the exact "
    "original string, including references outside code; existing indices are unchanged."
)
_SOURCE_TEXT_KEYS = {"sourceTextParts", "sourceTextValueParts", "nativeSourceText", "sourceTextNotation", "sourceText"}
_SOURCE_CODE_COVERAGE = {
    "approximate_identity_ast_regions", "approximate_identity_ast_method",
    "conditional_ast_regions", "identity_specialized_method", "whole_method",
}


def compact_author_source_text(context: dict[str, Any]) -> dict[str, Any]:
    """Keep the smaller complete presentation, including its reading guide.

    Adding a pooled body to an inline comparison group can shorten that group's
    common blocks. Retain the existing inline-only result when that happens.
    """
    inline = _compact_author_source_text(context, include_pooled=False)
    if not isinstance(context.get("nativeSourceFacts"), list):
        return inline
    pooled = _compact_author_source_text(context, include_pooled=True)
    return pooled if _size(pooled) < _size(inline) else inline


def _compact_author_source_text(context: dict[str, Any], *, include_pooled: bool) -> dict[str, Any]:
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
    facts = result.get("nativeSourceFacts", [])
    if not include_pooled or not isinstance(facts, list):
        facts = []

    def code_value(value: Any) -> tuple[str, int | None] | None:
        """Follow only exact existing references, retaining the terminal string's slot."""
        index = None
        seen: set[int] = set()
        while isinstance(value, dict) and set(value) == {"sourceSameAs"}:
            index = value["sourceSameAs"]
            if type(index) is not int or not 0 <= index < len(facts) or index in seen:
                return None
            seen.add(index)
            value = facts[index]
        return (value, index) if isinstance(value, str) else None

    groups: dict[tuple[str, str], list[tuple[dict[str, Any], str, int | None]]] = defaultdict(list)
    for row in records(result):
        method, coverage = row.get("method"), row.get("coverage")
        if (isinstance(method, str) and isinstance(coverage, str)
                and coverage in _SOURCE_CODE_COVERAGE):
            resolved = code_value(row.get("code"))
            if resolved is not None:
                groups[method, coverage].append((row, *resolved))
    shared: list[str] = []
    changed_facts: set[int] = set()
    for entries in groups.values():
        if len(entries) < 2 or any(slot in changed_facts for _, _, slot in entries if slot is not None):
            continue
        codes = [code for _, code, _ in entries]
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
        pooled: dict[int, dict[str, Any]] = {}
        originals = []
        for row, code, slot in entries:
            middle = code[len(prefix):len(code) - len(suffix)] if suffix else code[len(prefix):]
            pieces: list[Any] = []
            if prefix:
                pieces.append({"sourceText": index})
            if middle:
                pieces.append(middle)
            if suffix:
                pieces.append({"sourceText": index + bool(prefix)})
            if slot is None:
                originals.append(row)
                replacements.append((row, {("sourceTextParts" if key == "code" else key):
                                          (pieces if key == "code" else value) for key, value in row.items()}))
            elif slot not in pooled:
                # One physical string may have many code and non-code readers.
                # Replace its value once, without inlining or renumbering aliases.
                originals.append(facts[slot])
                pooled[slot] = {"sourceTextValueParts": pieces}
        projected = [replacement for _, replacement in replacements] + list(pooled.values())
        if _size(projected) + _size(blocks) >= _size(originals):
            continue
        shared.extend(blocks)
        for row, replacement in replacements:
            row.clear()
            row.update(replacement)
        for slot, replacement in pooled.items():
            facts[slot] = replacement
        changed_facts.update(pooled)
    if not shared:
        # No accepted group modified this already-detached copy.
        return result
    result["nativeSourceText"] = shared
    result["sourceTextNotation"] = _SOURCE_TEXT_READING + (_SOURCE_TEXT_VALUE_READING if changed_facts else "")
    return result if _size(result) < _size(context) else copy.deepcopy(context)


_ENTRY_CONDITION_READING = (
    "In sourceTextParts, {entryCondition:true} inserts this same record's complete entryCondition string. "
    "Concatenate the pieces in order to reconstruct the exact code; it does not evaluate or waive the guard. "
    "Source paths and snippets remain conditional static evidence, not observed gameplay."
)


def _share_local_entry_condition(context: dict[str, Any]) -> dict[str, Any]:
    """Reference one long, verbatim sibling guard instead of repeating its text.

    No source is parsed or inferred. Each changed record retains the full
    readable condition locally and two literal surrounding code fragments.
    Existing tables, scopes, conditions and dependencies are untouched.
    """
    def collision(value: Any) -> bool:
        if isinstance(value, dict):
            if set(value) == {"entryCondition"} and value["entryCondition"] is True:
                return True
            return any(collision(v) for k, v in value.items() if k not in _LITERAL_KEYS)
        return isinstance(value, list) and any(collision(v) for v in value)

    if collision(context):
        return copy.deepcopy(context)
    changed = False

    def visit(value: Any) -> Any:
        nonlocal changed
        if isinstance(value, list):
            return [visit(v) for v in value]
        if not isinstance(value, dict):
            return copy.deepcopy(value)
        result = {k: copy.deepcopy(v) if k in _LITERAL_KEYS else visit(v) for k, v in value.items()}
        code, condition = result.get("code"), result.get("entryCondition")
        if (isinstance(code, str) and isinstance(condition, str) and len(condition) >= 512
                and "sourceTextParts" not in result
                and result.get("coverage") == "conditional_source_region; external_inputs_explicit"
                and code.count(condition) == 1):
            prefix, suffix = code.split(condition)
            candidate = {k: v for k, v in result.items() if k != "code"}
            candidate["sourceTextParts"] = [prefix, {"entryCondition": True}, suffix]
            if _size(candidate) < _size(result):
                result = candidate
                changed = True
        return result

    result = visit(context)
    if not changed:
        return result
    old_reading = result.get("sourceTextNotation")
    if old_reading is not None and not isinstance(old_reading, str):
        return copy.deepcopy(context)
    result["sourceTextNotation"] = ((old_reading + " ") if old_reading else "") + _ENTRY_CONDITION_READING
    return result if _size(result) < _size(context) else copy.deepcopy(context)
