"""Source sharing preserves evidence and reduces the delivered packet."""
from __future__ import annotations

import copy
import json
import random

import pytest

from infini_local.pipelines.context.parent_stage import share_exact_native_parent_facts
from tests.generator.context.native_sharing_oracle import expanded_native_parents


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


@pytest.mark.parametrize("seed", [0, 3, 7, 11, 18, 23])
def test_nested_shared_evidence_survives_wire_projection(seed):
    parents = _parents(seed)
    original = copy.deepcopy(parents)
    actual = share_exact_native_parent_facts(parents)
    # Compare decoded JSON to the original data, not to another encoder.
    assert json.dumps(expanded_native_parents(actual), ensure_ascii=False, sort_keys=True) == json.dumps(
        original, ensure_ascii=False, sort_keys=True)
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
        parents, sort_keys=True)


def test_deep_repeated_evidence_reduces_wire_size_without_loss():
    value = {"text": "nested shared literal" * 12}
    for _ in range(90):
        value = {"next": [value], "source": "static"}
    parents = {"A": {"packet": {"raw": {"one": value, "two": copy.deepcopy(value)}}}}
    actual = share_exact_native_parent_facts(parents)
    encode = lambda row: json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert expanded_native_parents(actual) == parents
    assert len(encode(actual)) < len(encode({"parents": parents}))


def test_literal_tooltips_generated_parents_and_existing_reference_markers_remain_exact():
    source = {"kind": "proof", "code": "x" * 180}
    parents = {"A": {"packet": {"raw": {
        "a": {"tooltipSource": {"native": source}, "facts": source},
        "b": {"sourceSameAs": 0, "facts": source},
        "c": {"sameAs": 2, "facts": source},
        "d": [source, copy.deepcopy(source)],
    }}}}
    assert share_exact_native_parent_facts(parents) == {"parents": parents}
