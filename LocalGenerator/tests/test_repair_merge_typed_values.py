"""Type-aware frozen Repair with historical atomic-array permissions."""
import copy
import json

import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.core.repair_merge import merge_frozen_subtree
from infini_local.core.runtime_authoring import compile_runtime_program
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from test_low_level_three_stage_pipeline import _vfx_output


@pytest.mark.parametrize("old,new", [(True, 1), (False, 0), (1, True), (0, False), (1.0, 1), (1, 1.0)])
@pytest.mark.parametrize("shape", ["scalar", "object", "nested_array"])
def test_type_only_repair_requires_exact_permission(old, new, shape):
    if shape == "scalar":
        original, candidate, path = old, new, ""
    elif shape == "object":
        original, candidate, path = {"leaf": old}, {"leaf": new}, "leaf"
    else:
        original, candidate, path = {"nested": [{"leaf": old}]}, {"nested": [{"leaf": new}]}, "nested"
    original_before, candidate_before = json.dumps(original), json.dumps(candidate)
    merged, ignored, accepted = merge_frozen_subtree(
        original, candidate, mutable_paths=[path], audit_path="$", allow_additions=False,
    )
    assert json.dumps(merged) == candidate_before
    assert ignored == []
    assert accepted == ["$" + ("." + path if path else "")]
    frozen, ignored, accepted = merge_frozen_subtree(
        original, candidate, mutable_paths=[], audit_path="$", allow_additions=False,
    )
    assert json.dumps(frozen) == original_before
    assert len(ignored) == 1
    assert ignored[0]["path"] == "$" + ("." + path if path else "")
    assert ignored[0]["reason"] == "frozen_valid_value"
    assert not accepted
    assert json.dumps(original) == original_before
    assert json.dumps(candidate) == candidate_before


@pytest.mark.parametrize("permission", ["profile[1]", "profile.1"])
def test_array_descendant_permission_does_not_replace_atomic_array(permission):
    original = {"profile": [1, True, 0]}
    candidate = {"profile": [1, 1, 0]}
    merged, ignored, accepted = merge_frozen_subtree(
        original, candidate, mutable_paths=[permission], audit_path="$", allow_additions=False,
    )
    assert merged["profile"][1] is True
    assert not accepted
    assert ignored[0]["path"] == "$.profile"
    assert ignored[0]["reason"] == "frozen_valid_value"


def test_same_typed_json_is_unchanged_regardless_of_object_order():
    original = {"a": [None, False, 1, 1.0, "1"], "b": {"c": 0}}
    candidate = {"b": {"c": 0}, "a": [None, False, 1, 1.0, "1"]}
    merged, ignored, accepted = merge_frozen_subtree(
        original, candidate, mutable_paths=[""], audit_path="$",
    )
    assert merged == original
    assert not ignored
    assert not accepted
    assert merged is not original
    assert merged["a"] is not original["a"]


def test_type_only_leaf_change_does_not_hide_behind_ordinary_sibling_change():
    original = {"leaf": True, "sibling": "old"}
    candidate = {"leaf": 1, "sibling": "new"}
    merged, ignored, accepted = merge_frozen_subtree(
        original, candidate, mutable_paths=["leaf"], audit_path="$", allow_additions=False,
    )
    assert type(merged["leaf"]) is int
    assert merged["sibling"] == "old"
    assert accepted == ["$.leaf"]
    assert [row["path"] for row in ignored] == ["$.sibling"]


def _slot_patch(candidate):
    return {
        "schema": vfx.VFX_REPAIR_PATCH_SCHEMA,
        "effectMagnitude": None, "visualBudgetClass": None, "motif": None,
        "slotsUpsert": [candidate], "slotIdsDelete": [], "slotIndicesDelete": [],
        "note": "type-only repair",
    }


def test_vfx_filter_applies_type_only_repair_from_actual_validator_scope():
    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    previous = _vfx_output(data)
    previous["slots"][0]["scale"] = True
    report = vfx.validate_vfx_director_output(previous, data)
    assert not report["ok"]
    scope = vfx._build_vfx_repair_scope(previous, report["errors"])
    assert scope["fieldPermissions"]["slots"] == [{"slotId": "slot_0", "paths": ["scale"]}]
    candidate = copy.deepcopy(previous["slots"][0])
    candidate["scale"] = 1
    patch = _slot_patch(candidate)
    before = json.dumps(previous), json.dumps(patch)
    repaired, audit = vfx._apply_vfx_repair_patch(data, previous, patch, scope, return_audit=True)
    assert audit["ok"], audit
    assert audit["acceptedPaths"] == ["$.slotsUpsert[0].scale"]
    assert audit["ignoredChanges"] == []
    assert len(audit["filteredPatch"]["slotsUpsert"]) == 1
    assert type(repaired["slots"][0]["scale"]) is int
    expected = copy.deepcopy(previous)
    expected["slots"][0]["scale"] = 1
    assert json.dumps(repaired) == json.dumps(expected)
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]
    assert (json.dumps(previous), json.dumps(patch)) == before


def test_vfx_filter_audits_type_only_rewrite_of_independent_valid_slot():
    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    previous = _vfx_output(data)
    previous["slots"][0]["scale"] = 1
    report = vfx.validate_vfx_director_output(previous, data)
    assert report["ok"], report
    scope = vfx._build_vfx_repair_scope(previous, report["errors"])
    candidate = copy.deepcopy(previous["slots"][0])
    candidate["scale"] = 1.0
    repaired, audit = vfx._apply_vfx_repair_patch(data, previous, _slot_patch(candidate), scope, return_audit=True)
    assert audit["ok"], audit
    assert audit["acceptedPaths"] == []
    assert audit["filteredPatch"]["slotsUpsert"] == []
    assert len(audit["ignoredChanges"]) == 1
    ignored = audit["ignoredChanges"][0]
    assert ignored["path"] == "$.slotsUpsert[0]"
    assert ignored["reason"] == "independent_valid_slot_frozen"
    assert type(ignored["requested"]["scale"]) is float
    assert type(ignored["preserved"]["scale"]) is int
    assert type(repaired["slots"][0]["scale"]) is int
    assert json.dumps(repaired) == json.dumps(previous)
