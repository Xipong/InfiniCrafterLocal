"""Boundary regressions for the PR339 structural interner (no model calls)."""
from __future__ import annotations

import copy
import json

import pytest

from infini_local.pipelines.context.parent_stage import share_exact_native_parent_facts
from tests.generator.context.native_sharing_oracle import share_native_facts_reference


@pytest.mark.parametrize("key", ["tooltipLines", "tooltipSource", "generatedParent"])
def test_foreign_mapping_cannot_intern_nested_literal_source(key):
    protected = {7: {key: ["Literal source is not a shared native fact. " * 12]}}
    parents = {"A": {"packet": {"raw": {"first": protected, "second": copy.deepcopy(protected)}}}}
    before = copy.deepcopy(parents)
    actual = share_exact_native_parent_facts(parents)
    assert actual == share_native_facts_reference(parents)
    assert "nativeSourceFacts" not in actual
    assert parents == before


def test_literal_exclusion_precedes_foreign_mixed_key_serialization():
    protected = {"tooltipLines": [{"opaque": {1, 2, 3}}], 7: "small native value"}
    parents = {"A": {"packet": {"raw": {"first": protected, "second": copy.deepcopy(protected)}}}}
    assert share_exact_native_parent_facts(parents) == share_native_facts_reference(parents)


@pytest.mark.parametrize("length", [125, 126, 127, 128, 129, 130])
@pytest.mark.parametrize("text", ["x", "Призма", "\t\n\"\\", "🛰️", "\u0000"])
def test_exact_escaped_character_thresholds_remain_legacy_equal(length, text):
    value = text * length
    parents = {"A": {"packet": {"raw": {"one": {"code": value}, "two": {"code": value}}}}}
    actual = share_exact_native_parent_facts(parents)
    expected = share_native_facts_reference(parents)
    assert json.dumps(actual, ensure_ascii=False) == json.dumps(expected, ensure_ascii=False)


@pytest.mark.parametrize("value", [False, True, 0, 1, 0.0, -0.0, 1.0, float("inf"), float("-inf"), float("nan")])
def test_scalar_json_spelling_not_python_numeric_equality(value):
    raw = {"first": [value] * 100, "second": [value] * 100,
           "integer": [0] * 100, "boolean": [False] * 100, "float": [0.0] * 100}
    parents = {"A": {"packet": {"raw": raw}}}
    actual = share_exact_native_parent_facts(parents)
    expected = share_native_facts_reference(parents)
    assert json.dumps(actual, ensure_ascii=False) == json.dumps(expected, ensure_ascii=False)
