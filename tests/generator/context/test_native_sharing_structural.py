"""Differential and complexity tests for native exact-source sharing."""
from __future__ import annotations

import copy
import json
import random

import pytest

from infini_local.pipelines.context import parent_stage
from infini_local.pipelines.context.parent_stage import share_exact_native_parent_facts
from tests.generator.context.native_sharing_oracle import expanded_native_parents, share_native_facts_reference


def _parents(seed):
    randomizer = random.Random(seed)
    long = "Призма\\n\\t🛰️" * 22
    leaves = [None, True, False, 0, 1, 0.0, 1.0, -0.0, 1.5, long,
              "quotes:\" and backslash:\\", "text", 234567891]

    def make(depth):
        if depth == 0 or randomizer.random() < 0.22:
            return copy.deepcopy(randomizer.choice(leaves))
        if randomizer.random() < 0.55:
            return [make(depth - 1) for _ in range(randomizer.randint(0, 3))]
        return {name: make(depth - 1) for name in randomizer.sample(
            ["source", "coverage", "proof", "data", "code"], randomizer.randint(0, 4))}

    shared = {"source": "verified_native", "records": [make(3) for _ in range(5)],
              "sameAs": 0, "name": long}
    packet = {"native": shared, "related": copy.deepcopy(shared),
              "path": [make(4), make(4)], "values": [True, 1, 1.0, -0.0],
              "excluded": {"tooltipLines": [long, long], "node": copy.deepcopy(shared)},
              "unresolved": long}
    return {
        "A": {"packet": {"raw": copy.deepcopy(packet)}, "role": "first"},
        "B": {"packet": {"raw": copy.deepcopy(packet)}, "role": "second"},
        "C": {"packet": {"raw": {"generatedParent": {"source": long, "native": shared}}}},
    }


@pytest.mark.parametrize("seed", range(24))
def test_structural_interning_matches_canonical_json_oracle(seed):
    parents = _parents(seed)
    original = copy.deepcopy(parents)
    expected = share_native_facts_reference(parents)
    actual = share_exact_native_parent_facts(parents)
    # Pool layout can change; decoded order, multiplicity, payload and scalar
    # JSON types must still match the independent legacy interner.
    assert json.dumps(expanded_native_parents(actual), ensure_ascii=False, sort_keys=True) == json.dumps(
        expanded_native_parents(expected), ensure_ascii=False, sort_keys=True)
    assert parents == original
    actual["parents"]["A"]["packet"]["raw"]["values"].append(99)
    assert parents == original


def test_structural_keys_preserve_object_order_independence_and_scalar_kinds():
    large = {"kind": "proof", "text": "abc" * 55}
    same_reordered = {"text": large["text"], "kind": "proof"}
    raw = {"a": large, "b": same_reordered, "bool": [True] * 70,
           "int": [1] * 70, "float": [1.0] * 70, "negative_zero": [-0.0] * 70}
    parents = {"A": {"packet": {"raw": raw}}}
    assert json.dumps(expanded_native_parents(share_exact_native_parent_facts(parents)), sort_keys=True) == json.dumps(
        expanded_native_parents(share_native_facts_reference(parents)), sort_keys=True)


def test_deep_exact_sharing_does_not_json_serialize_every_ancestor(monkeypatch):
    value = {"text": "nested shared literal" * 12}
    for _ in range(90):
        value = {"next": [value], "source": "static"}
    parents = {"A": {"packet": {"raw": {"one": value, "two": copy.deepcopy(value)}}}}
    expected = share_native_facts_reference(parents)
    calls = 0
    original_dumps = json.dumps

    def instrumented(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_dumps(*args, **kwargs)

    monkeypatch.setattr(parent_stage.json, "dumps", instrumented)
    actual = share_exact_native_parent_facts(parents)
    assert expanded_native_parents(actual) == expanded_native_parents(expected)
    assert len(actual["nativeSourceFacts"]) == 1
    assert calls < 30, "structural IDs should encode distinct scalar strings, not every ancestor"


def test_literal_tooltips_generated_parents_and_existing_reference_markers_remain_exact():
    source = {"kind": "proof", "code": "x" * 180}
    parents = {"A": {"packet": {"raw": {
        "a": {"tooltipSource": {"native": source}, "facts": source},
        "b": {"sourceSameAs": 0, "facts": source},
        "c": {"sameAs": 2, "facts": source},
        "d": [source, copy.deepcopy(source)],
    }}}}
    assert share_exact_native_parent_facts(parents) == share_native_facts_reference(parents)
