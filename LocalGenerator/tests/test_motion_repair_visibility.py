"""Fresh Repair offers current primitives, not retained compound wire forms."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.qa.capability_witnesses import build_capability_witness


def test_missing_driver_repair_does_not_reintroduce_retained_compound_profiles():
    doc = build_capability_witness("move_straight")
    before = deepcopy(doc)
    calls = doc["runtimeProgram"]["calls"]
    movement = next(call for call in calls if call["fn"] == "move_straight")
    calls.remove(movement)
    report = validate_runtime_program(doc)
    assert not report["ok"]
    scope = build_runtime_repair_scope(doc, report["errors"])
    offered = scope["create"]["calls"]["allowedFns"]
    assert "move_straight" in offered, "retain a real simple-flight repair option"
    assert "move_phase" not in offered, "opacity+wobble is retained wire, not a fresh primitive"
    assert "move_sine_homing" not in offered, "steering+oscillation must be independently authored"
    assert "move_returning_glaive" not in offered, "return and body spin must not be silently bundled"
    expected = deepcopy(before)
    expected["runtimeProgram"]["calls"].remove(next(call for call in expected["runtimeProgram"]["calls"] if call["fn"] == "move_straight"))
    assert doc == expected, "scope construction must not reauthor the accepted context"


@pytest.mark.parametrize("fn,selector", [
    ("set_projectile_return_trigger", "onOwnerRelease"),
    ("set_projectile_owner_control", "requireChannel"),
])
@pytest.mark.parametrize("input_name", ["primary_use", "alternate_use"])
def test_channel_dependency_repairs_only_item_leaf_not_the_accepted_motion_choice(fn, selector, input_name):
    doc = build_capability_witness(fn)
    calls = doc["runtimeProgram"]["calls"]
    selected = next(call for call in calls if call["fn"] == fn)
    selected["params"][selector] = True
    use = next(call for call in calls if call["fn"] == "configure_item_use")
    use["params"]["channel"] = False
    doc["runtimeProgram"]["bindings"][0]["input"] = input_name
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert [row["code"] for row in report["errors"]] == ["missing_item_capability_param"], report
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": use["id"], "paths": ["params.channel"]}]
    hostile = deepcopy(use)
    hostile["params"].update(channel=True, autoReuse=not use["params"]["autoReuse"])
    motion = deepcopy(selected)
    motion["params"][selector] = False
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [hostile, motion], "note": "exact dependency only"}, scope)
    repaired = apply_repair_patch(doc, patch)
    expected = deepcopy(before)
    next(call for call in expected["runtimeProgram"]["calls"] if call["id"] == use["id"])["params"]["channel"] = True
    assert audit["ok"] and audit["ignoredChanges"]
    assert repaired == expected and doc == before
    assert validate_runtime_program(repaired)["ok"]
