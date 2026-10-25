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


@pytest.mark.parametrize("fn,selector,choice,field,value", [
    ("seek_projectile", "target", "cursor", "searchRangeTiles", 20),
    ("seek_projectile", "target", "owner_center", "cursorLeashBlocks", 4),
    ("set_projectile_lash_geometry", "clock", "owner_animation", "durationSeconds", 1),
])
@pytest.mark.parametrize("explicit_delete", [False, True])
def test_inactive_optional_motion_leaf_can_be_removed_without_reauthoring_its_selector(
        fn, selector, choice, field, value, explicit_delete):
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire

    doc = build_capability_witness(fn)
    selected = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)
    selected["params"][selector] = choice
    selected["params"][field] = value
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert not report["ok"]
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["deletable"]["callParamKeys"] == [{"callId": selected["id"], "key": field}]
    assert scope["fieldPermissions"]["calls"] == [{"id": selected["id"], "paths": ["params." + field]}]
    hostile = deepcopy(selected)
    hostile["params"].pop(field)
    hostile["params"][selector] = "nearest_npc" if fn == "seek_projectile" else "active"
    proposed = {"callsUpsert": [hostile], "note": "remove only the inactive optional leaf"}
    if explicit_delete:
        proposed["callParamKeysDelete"] = [{"callId": selected["id"], "key": field},
                                           {"callId": selected["id"], "key": selector}]
    patch, audit = filter_repair_patch_scope(doc, proposed, scope)
    repaired = apply_repair_patch(doc, patch)
    expected = deepcopy(before)
    next(c for c in expected["runtimeProgram"]["calls"] if c["id"] == selected["id"])["params"].pop(field)
    assert audit["ok"] and audit["ignoredChanges"], audit
    assert repaired == expected and doc == before
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]


@pytest.mark.parametrize("fn,selector,field,value", [
    ("seek_projectile", "target", "cursorLeashBlocks", 4),
    ("set_projectile_lash_geometry", "clock", "durationSeconds", 1),
])
@pytest.mark.parametrize("choice", [None, "not_a_registered_choice", {"invalid": "selector"}])
def test_undecided_motion_selector_does_not_thaw_its_valid_optional_leaf(fn, selector, field, value, choice):
    doc = build_capability_witness(fn)
    selected = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)
    selected["params"][field] = value
    if choice is None:
        selected["params"].pop(selector)
    else:
        selected["params"][selector] = choice
    report = validate_runtime_program(doc)
    assert not report["ok"]
    assert not any(e["code"] == "incompatible_param_variant" for e in report["errors"]), report
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["deletable"]["callParamKeys"] == []
    assert not any("params." + field in row["paths"] for row in scope["fieldPermissions"]["calls"])


@pytest.mark.parametrize("fn,property,core,value,extra", [
    ("set_projectile_beam_geometry", "ramp", "lengthBlocks", 20, {"warmupSeconds": 1}),
    ("attach_projectile", "reachCurve", "anchor", "owner_center", {
        "durationSeconds": 1, "startOffsetBlocks": 0, "peakOffsetBlocks": 2,
        "endOffsetBlocks": 0, "peakProgress": 0.5}),
    ("accumulate_projectile_charge", "releaseEffect", "durationSeconds", 1, {"launchSpeedBlocksPerSecond": 30}),
])
def test_repair_of_parent_does_not_invent_absent_nested_effect(fn, property, core, value, extra):
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire

    doc = build_capability_witness(fn)
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)
    call["params"][core] = None
    before = deepcopy(doc)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    proposed = deepcopy(call)
    proposed["params"].update({core: value, property: extra})
    patch, audit = filter_repair_patch_scope(doc, {"callsUpsert": [proposed], "note": "fix parent only"}, scope)
    fixed = apply_repair_patch(doc, patch)
    expected = deepcopy(before)
    next(c for c in expected["runtimeProgram"]["calls"] if c["id"] == call["id"])["params"][core] = value
    assert fixed == expected and doc == before
    assert audit["ok"] and audit["ignoredChanges"]
    assert validate_runtime_wire(compile_runtime_program(fixed))["ok"]
