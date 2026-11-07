"""Differential and complexity tests for native exact-source sharing."""
from __future__ import annotations

import copy
import json
import random

import pytest

from infini_local.pipelines.context import parent_stage
from infini_local.pipelines.context.parent_stage import share_exact_native_parent_facts


def _legacy_share(parents):
    """Reference JSON-key algorithm retained only as an equivalence oracle."""
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
    expected = _legacy_share(parents)
    actual = share_exact_native_parent_facts(parents)
    assert actual == expected
    assert json.dumps(actual, ensure_ascii=False, separators=(",", ":")) == json.dumps(
        expected, ensure_ascii=False, separators=(",", ":"))
    assert parents == original
    actual["parents"]["A"]["packet"]["raw"]["values"].append(99)
    assert parents == original


def test_structural_keys_preserve_object_order_independence_and_scalar_kinds():
    large = {"kind": "proof", "text": "abc" * 55}
    same_reordered = {"text": large["text"], "kind": "proof"}
    raw = {"a": large, "b": same_reordered, "bool": [True] * 70,
           "int": [1] * 70, "float": [1.0] * 70, "negative_zero": [-0.0] * 70}
    parents = {"A": {"packet": {"raw": raw}}}
    assert share_exact_native_parent_facts(parents) == _legacy_share(parents)


def test_deep_exact_sharing_does_not_json_serialize_every_ancestor(monkeypatch):
    value = {"text": "nested shared literal" * 12}
    for _ in range(90):
        value = {"next": [value], "source": "static"}
    parents = {"A": {"packet": {"raw": {"one": value, "two": copy.deepcopy(value)}}}}
    expected = _legacy_share(parents)
    calls = 0
    original_dumps = json.dumps

    def instrumented(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_dumps(*args, **kwargs)

    monkeypatch.setattr(parent_stage.json, "dumps", instrumented)
    actual = share_exact_native_parent_facts(parents)
    assert actual == expected
    assert calls < 30, "structural IDs should encode distinct scalar strings, not every ancestor"


def test_literal_tooltips_generated_parents_and_existing_reference_markers_remain_exact():
    source = {"kind": "proof", "code": "x" * 180}
    parents = {"A": {"packet": {"raw": {
        "a": {"tooltipSource": {"native": source}, "facts": source},
        "b": {"sourceSameAs": 0, "facts": source},
        "c": {"sameAs": 2, "facts": source},
        "d": [source, copy.deepcopy(source)],
    }}}
    assert share_exact_native_parent_facts(parents) == _legacy_share(parents)
