"""Boundary regressions for the PR339 structural interner (no model calls)."""
from __future__ import annotations

import copy
import json

import pytest

from infini_local.pipelines.context.parent_stage import share_exact_native_parent_facts


def _legacy_share(parents):
    """Independent pre-PR339 JSON-key oracle; never used by production."""
    counts, indices, shared = {}, {}, []
    literal_keys = {"tooltipLines", "tooltipSource", "generatedParent"}

    def contains_literal(value):
        if isinstance(value, dict):
            return bool(literal_keys.intersection(value)) or any(contains_literal(child) for child in value.values())
        return isinstance(value, list) and any(contains_literal(child) for child in value)

    def candidate(value):
        if not isinstance(value, (dict, list, str)) or contains_literal(value):
            return None
        if isinstance(value, dict) and ("sameAs" in value or "sourceSameAs" in value):
            return None
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return encoded if len(encoded) >= 128 else None

    def count(value):
        key = candidate(value)
        if key is not None:
            counts[key] = counts.get(key, 0) + 1
        if isinstance(value, dict):
            for name, child in value.items():
                if name not in literal_keys:
                    count(child)
        elif isinstance(value, list):
            for child in value:
                count(child)

    def children(value):
        if isinstance(value, dict):
            return {name: copy.deepcopy(child) if name in literal_keys else visit(child)
                    for name, child in value.items()}
        if isinstance(value, list):
            return [visit(child) for child in value]
        return copy.deepcopy(value)

    def visit(value):
        key = candidate(value)
        if key is not None and counts[key] > 1:
            if key not in indices:
                index = indices[key] = len(shared)
                shared.append(None)
                shared[index] = children(value)
            return {"sourceSameAs": indices[key]}
        return children(value)

    for row in parents.values():
        raw = row.get("packet", {}).get("raw", {})
        if "generatedParent" not in raw:
            count(raw)
    result = copy.deepcopy(parents)
    for row in result.values():
        raw = row.get("packet", {}).get("raw", {})
        if "generatedParent" not in raw:
            row["packet"]["raw"] = {name: visit(value) for name, value in raw.items()}
    return {"parents": result, **({"nativeSourceFacts": shared} if shared else {})}


@pytest.mark.parametrize("key", ["tooltipLines", "tooltipSource", "generatedParent"])
def test_foreign_mapping_cannot_intern_nested_literal_source(key):
    protected = {7: {key: ["Literal source is not a shared native fact. " * 12]}}
    parents = {"A": {"packet": {"raw": {"first": protected, "second": copy.deepcopy(protected)}}}}
    before = copy.deepcopy(parents)
    actual = share_exact_native_parent_facts(parents)
    assert actual == _legacy_share(parents)
    assert "nativeSourceFacts" not in actual
    assert parents == before


def test_literal_exclusion_precedes_foreign_mixed_key_serialization():
    protected = {"tooltipLines": [{"opaque": {1, 2, 3}}], 7: "small native value"}
    parents = {"A": {"packet": {"raw": {"first": protected, "second": copy.deepcopy(protected)}}}}
    assert share_exact_native_parent_facts(parents) == _legacy_share(parents)


@pytest.mark.parametrize("length", [125, 126, 127, 128, 129, 130])
@pytest.mark.parametrize("text", ["x", "Призма", "\t\n\"\\", "🛰️", "\u0000"])
def test_exact_escaped_character_thresholds_remain_legacy_equal(length, text):
    value = text * length
    parents = {"A": {"packet": {"raw": {"one": {"code": value}, "two": {"code": value}}}}}
    actual = share_exact_native_parent_facts(parents)
    expected = _legacy_share(parents)
    assert json.dumps(actual, ensure_ascii=False) == json.dumps(expected, ensure_ascii=False)


@pytest.mark.parametrize("value", [False, True, 0, 1, 0.0, -0.0, 1.0, float("inf"), float("-inf"), float("nan")])
def test_scalar_json_spelling_not_python_numeric_equality(value):
    raw = {"first": [value] * 100, "second": [value] * 100,
           "integer": [0] * 100, "boolean": [False] * 100, "float": [0.0] * 100}
    parents = {"A": {"packet": {"raw": raw}}}
    actual = share_exact_native_parent_facts(parents)
    expected = _legacy_share(parents)
    assert json.dumps(actual, ensure_ascii=False) == json.dumps(expected, ensure_ascii=False)
