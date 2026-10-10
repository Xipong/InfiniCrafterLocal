"""Frozen-first structure validation must tolerate overlapping relaxed values."""
from __future__ import annotations

import copy

import pytest

from infini_local.core.runtime_authoring.program_schema import (
    _repair_structure_schema,
    strict_schema_errors,
)


def _cost_union() -> dict:
    return {"oneOf": [{
        "type": "object", "additionalProperties": False,
        "properties": {"kind": {"const": "use"}, "cost": {"const": cost}},
        "required": ["kind", "cost"],
    } for cost in (0, 1)]}


@pytest.mark.parametrize("cost", [0, 1, 50])
def test_relaxed_numeric_discriminators_accept_structure_before_freezing(cost):
    schema = _cost_union()
    original = copy.deepcopy(schema)
    assert not strict_schema_errors({"kind": "use", "cost": cost}, _repair_structure_schema(schema))
    assert bool(strict_schema_errors({"kind": "use", "cost": cost}, schema)) is (cost == 50)
    assert schema == original


@pytest.mark.parametrize("candidate", [
    {"kind": "other", "cost": 0}, {"kind": "use", "cost": True},
    {"kind": "use", "cost": "0"}, {"kind": "use"},
    {"kind": "use", "cost": 0, "unknown": 3},
])
def test_relaxed_union_keeps_registered_identity_types_and_shape(candidate):
    assert strict_schema_errors(candidate, _repair_structure_schema(_cost_union()))


def test_relaxed_union_preserves_exact_common_error_locations():
    errors = strict_schema_errors({"kind": "use", "cost": 0, "unknown": 3}, _repair_structure_schema(_cost_union()))
    assert any(row["kind"] == "additional_property" and row["path"] == "$.unknown" for row in errors)


def test_structural_union_preserves_parallel_anyof_and_allof_constraints():
    schema = {
        **_cost_union(),
        "anyOf": [{"required": ["tag"]}],
        "allOf": [{"properties": {"tag": {"type": "string"}}}],
    }
    for branch in schema["oneOf"]:
        branch["properties"]["tag"] = {"type": "string"}
    projected = _repair_structure_schema(schema)
    assert not strict_schema_errors({"kind": "use", "cost": 0, "tag": "kept"}, projected)
    assert strict_schema_errors({"kind": "use", "cost": 0}, projected)
    assert strict_schema_errors({"kind": "use", "cost": 0, "tag": 7}, projected)
