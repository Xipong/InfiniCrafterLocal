"""Exact native sharing stays byte-identical to the canonical JSON oracle."""
from __future__ import annotations

import copy
import json
import random

import pytest

from infini_local.pipelines.context.parent_stage import share_exact_native_parent_facts


def _canonical_sharing(parents):
    """Deliberately slow, independent pre-optimization implementation."""
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
            return {name: copy.deepcopy(child) if name in literal_keys else visit(child) for name, child in value.items()}
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


def _json(value):
    # Unsorted output checks reference numbering and first-occurrence key order,
    # as well as scalar kinds that Python's == would consider interchangeable.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _check(raw_a, raw_b=None):
    parents = {"A": {"packet": {"raw": raw_a}}, "B": {"packet": {"raw": copy.deepcopy(raw_a) if raw_b is None else raw_b}}}
    before = _json(parents)
    expected = _canonical_sharing(parents)
    actual = share_exact_native_parent_facts(parents)
    assert _json(actual) == _json(expected)
    assert _json(parents) == before
    return parents, actual


@pytest.mark.parametrize("text", ["x" * 125, "x" * 126, "Ж" * 125, "Ж" * 126, "😀" * 126,
                                  "\n" * 62 + "x", "\n" * 63, '\\"' * 32])
def test_character_threshold_includes_json_escapes_without_utf8_byte_estimates(text):
    _check({"left": text, "right": text})


def test_nested_facts_preserve_scalar_kinds_order_literals_and_unknown_shapes():
    values = [None, False, True, 0, 1, 0.0, -0.0, 1.0, "0", "true", "Ж😀\n\\\"" * 16]
    facts = [{"value": value, "unknown": "future-source-expression" * 8} for value in values]
    literal = {"tooltipLines": ["literal tooltip" * 16], "facts": copy.deepcopy(facts)}
    raw = {
        "forward": facts,
        "reversed": list(reversed(facts)),
        "multiplicity": [facts[0], facts[0], facts[1]],
        "literal": literal,
        "literalSource": {"tooltipSource": {"nested": facts}},
        "sameAs": {"sameAs": "native.profile", "facts": facts},
        "sourceSameAs": {"sourceSameAs": 0, "futureFields": facts},
        "unknown": {"futureSchema": [False, 0, 0.0], "payload": facts},
    }
    original, actual = _check(raw)
    actual["parents"]["A"]["packet"]["raw"]["literal"]["tooltipLines"].append("new output value")
    assert original["A"]["packet"]["raw"]["literal"]["tooltipLines"] == literal["tooltipLines"]


def test_equal_dicts_keep_first_encounter_order_and_generated_packets_stay_literal():
    fact = {"expression": "unknown runtime expression" * 10, "guards": ["p1", "p2"], "zero": -0.0}
    reverse = dict(reversed(list(fact.items())))
    raw = {"first": fact, "second": reverse}
    _check(raw)
    _check(raw, {"generatedParent": {"completeAcceptedPacket": raw}, "unchangedSibling": fact})
    # A native raw section map is counted but stays inline; this affects counts
    # when the same value is also nested in another parent's raw section.
    _check(fact, {"nested": fact})


def test_structural_interning_matches_canonical_json_on_varied_repeated_trees():
    rng = random.Random(333)
    pool = [None, False, True, 0, 1, 0.0, -0.0, 1.0, "", "future-native-value" * 12,
            "escaped\nvalue\\\"" * 8, "Ж" * 126]
    for index in range(80):
        children = [copy.deepcopy(rng.choice(pool)) for _ in range(rng.randrange(1, 5))]
        value = children if index % 3 == 0 else {f"field{key}": child for key, child in enumerate(children)}
        if isinstance(value, dict) and index % 13 == 0:
            value["tooltipLines"] = ["literal" * 30]
        if isinstance(value, dict) and index % 17 == 0:
            value["sameAs"] = "uninterpreted native reference"
        # Keep fixture depth bounded while varying shared and copied instances.
        pool.append(value)
        if len(pool) > 30:
            pool.pop(12)
        _check({"first": value, "copy": copy.deepcopy(value), "other": rng.choice(pool)})


@pytest.mark.parametrize("literal_key", ["tooltipLines", "tooltipSource"])
def test_top_level_literal_named_section_keeps_legacy_exact_lookup(literal_key):
    fact = {"scope": "read_only_native_source", "values": ["source detail " * 40, {"unknown": False}]}
    raw = {"first": copy.deepcopy(fact), "second": copy.deepcopy(fact), literal_key: copy.deepcopy(fact)}
    _check(raw)
