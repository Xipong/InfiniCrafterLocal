"""Boundary regressions for the PR339 structural interner (no model calls)."""
from __future__ import annotations

import copy
import json

import pytest

from infini_local.pipelines.context.parent_stage import share_exact_native_parent_facts
from tests.generator.context.native_sharing_oracle import expanded_native_parents, share_native_facts_reference


@pytest.mark.parametrize("key", ["tooltipLines", "tooltipSource", "generatedParent"])
@pytest.mark.parametrize("nested", [False, True], ids=["root", "nested"])
def test_literal_fields_preserve_opaque_markers_without_disabling_native_sharing(key, nested):
    body = {"code": "literal native fact; " * 20, "values": [False, 0, 0.0, -0.0]}
    literal = [copy.deepcopy(body), {"sourceSameAs": 0, "opaque": {1, 2, 3}}]
    raw = {key: literal, "native": copy.deepcopy(body)}
    if nested:
        raw = {"wrapper": raw}
    parents = {"A": {"packet": {"raw": raw}},
               "B": {"packet": {"raw": {"one": body, "two": copy.deepcopy(body)}}}}
    before = copy.deepcopy(parents)
    actual = share_exact_native_parent_facts(parents)
    assert actual["nativeSourceFacts"] == [body]
    assert expanded_native_parents(actual) == before
    delivered = actual["parents"]["A"]["packet"]["raw"]
    if nested:
        delivered = delivered["wrapper"]
    assert delivered[key] == literal
    if key == "generatedParent" and not nested:
        assert actual["parents"]["A"] == before["A"]
    delivered[key][1]["opaque"].add(4)
    actual["nativeSourceFacts"][0]["values"].append(1)
    assert parents == before


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


@pytest.mark.parametrize("encoded_length", [127, 128, 129])
@pytest.mark.parametrize("text", ["x", "Призма", "\t\n\"\\", "🛰️", "\u0000"])
def test_exact_escaped_character_thresholds_remain_legacy_equal(encoded_length, text):
    # The threshold counts canonical JSON characters, including quotes and
    # escapes, not input characters or UTF-8 bytes.
    prefix_length = len(json.dumps(text, ensure_ascii=False))
    value = text + "x" * (encoded_length - prefix_length)
    assert len(json.dumps(value, ensure_ascii=False)) == encoded_length
    parents = {"A": {"packet": {"raw": {"one": value, "two": value}}}}
    actual = share_exact_native_parent_facts(parents)
    expected = share_native_facts_reference(parents)
    assert json.dumps(actual, ensure_ascii=False) == json.dumps(expected, ensure_ascii=False)
    if encoded_length < 128:
        assert "nativeSourceFacts" not in actual
    else:
        assert actual["nativeSourceFacts"] == [value]
        assert actual["parents"]["A"]["packet"]["raw"] == {
            "one": {"sourceSameAs": 0}, "two": {"sourceSameAs": 0},
        }


@pytest.mark.parametrize("value", [False, True, 0, 1, 0.0, -0.0, 1.0, float("inf"), float("-inf"), float("nan")])
def test_scalar_json_spelling_not_python_numeric_equality(value):
    raw = {"first": [value] * 100, "second": [value] * 100,
           "integer": [0] * 100, "boolean": [False] * 100, "float": [0.0] * 100}
    parents = {"A": {"packet": {"raw": raw}}}
    actual = share_exact_native_parent_facts(parents)
    expected = share_native_facts_reference(parents)
    assert json.dumps(actual, ensure_ascii=False) == json.dumps(expected, ensure_ascii=False)
