"""Generic reference constraints keep valid child programs frozen during Repair."""
from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType

import pytest

from infini_local.core.runtime_authoring import (
    apply_repair_patch, build_runtime_repair_scope, filter_repair_patch_scope, validate_runtime_program,
)
from infini_local.core.runtime_authoring import capability_registry as registry
from infini_local.core.runtime_authoring import repair_scope, validator
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


@pytest.fixture
def constrained_reference(monkeypatch):
    # Exercise generic metadata on an isolated registry entry. Production A10/A11
    # supply real adapter names/opcodes; this framework test adds no runtime alias.
    source = registry.CAPABILITY_REGISTRY["spawn_entity_on_event"]
    params = dict(source.params)
    params["entity"] = replace(params["entity"], reference=registry.ReferenceSpec(
        "entity", ("free_projectile", "child_projectile"), False, True))
    requirements = (*source.requirements,
        registry.RequirementSpec("referenced_entity_capability_params", param="entity", capability="configure_spawn",
            equals={"position": {"at": "activation_origin"}, "aim": "velocity", "offsetPx": 0},
            message="The emission reference needs explicit origin/velocity spawn without offset."),
        registry.RequirementSpec("referenced_entity_without_capability", param="entity", capability="spawn_over_target",
            message="The explicit emission reference cannot carry a second origin/telegraph adapter."))
    cap = replace(source, name="probe_reference_adapter", params=MappingProxyType(params), requirements=requirements)
    # Make this retired technical capability visible only in the isolated
    # generic-framework registry so its presence is a valid independent choice.
    mapping = dict(registry.CAPABILITY_REGISTRY, probe_reference_adapter=cap)
    mapping["spawn_over_target"] = replace(mapping["spawn_over_target"], decision="expose", prompt_visible=True)
    for owner in (registry, validator, repair_scope):
        monkeypatch.setattr(owner, "CAPABILITY_REGISTRY", mapping)
    return cap


def _doc(*, compatible_alternative=False):
    doc = build_runtime_fixture("workbench_blade")
    program = doc["runtimeProgram"]
    probe = deepcopy(next(row for row in program["calls"] if row["id"] == "shed_nails"))
    probe.update(id="probe_reference", fn="probe_reference_adapter")
    program["calls"].append(probe)
    if compatible_alternative:
        entity, calls = _new_child(doc, "other_nail")
        program["entities"].append(entity); program["calls"].extend(calls)
        keep = deepcopy(next(row for row in program["calls"] if row["id"] == "shed_nails"))
        keep["id"] = "keep_other_nail"; keep["params"]["entity"] = "other_nail"
        program["calls"].append(keep)
    return doc


def _new_child(doc, name):
    entity = {"id": name, "kind": "child_projectile"}
    calls = [deepcopy(row) for row in doc["runtimeProgram"]["calls"] if row.get("target") == "nail"]
    for row in calls:
        row["target"] = name; row["id"] = row["id"].replace("nail", name)
        if row["fn"] == "configure_spawn":
            row["params"].update(aim="velocity", position={"at": "activation_origin"}, offsetPx=0)
    return entity, calls


def _probe(doc):
    return next(row for row in doc["runtimeProgram"]["calls"] if row["id"] == "probe_reference")


@pytest.mark.parametrize("replacement", [None, False, 1, "0", 0, 0.0])
def test_reference_exact_params_have_no_missing_or_boolean_numeric_fallback(constrained_reference, replacement):
    doc = _doc()
    spawn = next(row for row in doc["runtimeProgram"]["calls"] if row["id"] == "nail_spawn")
    spawn["params"]["aim"] = "velocity"
    if replacement is None:
        spawn["params"].pop("offsetPx")
    else:
        spawn["params"]["offsetPx"] = replacement
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    exact_error = [row for row in report["errors"] if row["code"] == "reference_requirements_unsatisfied"]
    assert bool(exact_error) is not (type(replacement) is int and replacement == 0)
    if exact_error:
        assert exact_error[0]["path"].endswith(".params.entity")
    assert doc == before


def test_reference_exact_number_uses_declared_json_numeric_domain(constrained_reference):
    requirement = registry.RequirementSpec("referenced_entity_capability_params", param="entity",
        capability="configure_spawn", equals={"spreadRadians": 0})
    for value, accepted in [(0, True), (0.0, True), (False, False), (0.1, False)]:
        rows = {"child": [{"fn": "configure_spawn", "params": {"spreadRadians": value}}]}
        assert registry.referenced_entity_requirement_satisfied(requirement, "child", rows) is accepted


def test_reference_without_capability_is_not_a_supporting_dependency(constrained_reference):
    doc = _doc()
    spawn = next(row for row in doc["runtimeProgram"]["calls"] if row["id"] == "nail_spawn")
    spawn["params"]["aim"] = "velocity"
    assert validate_runtime_program(doc)["ok"]
    doc["runtimeProgram"]["calls"].append({"id": "nail_telegraph", "target": "nail", "fn": "spawn_over_target",
        "params": {"heightTiles": 3, "delayTicks": 0}})
    report = validate_runtime_program(doc)
    assert [row["code"] for row in report["errors"]] == ["reference_requirements_unsatisfied"]
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert "spawn_over_target" not in scope["capabilitySubset"]
    assert scope["fieldPermissions"]["calls"] == [{"id": "probe_reference", "paths": ["params.entity"]}]
    assert "nail_telegraph" not in scope["mutable"]["callIds"]


def test_reference_repair_retargets_without_rewriting_valid_child(constrained_reference):
    doc = _doc(compatible_alternative=True)
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert [row["code"] for row in report["errors"]] == ["reference_requirements_unsatisfied"]
    assert report["errors"][0]["allowed"] == ["other_nail"]
    scope = build_runtime_repair_scope(doc, report["errors"])
    candidate = deepcopy(_probe(doc)); candidate["params"]["entity"] = "other_nail"
    candidate["params"]["count"] = 11  # unrelated authored emission choice remains frozen
    hostile = deepcopy(next(row for row in doc["runtimeProgram"]["calls"] if row["id"] == "nail_spawn"))
    hostile["params"]["aim"] = "velocity"
    filtered, audit = filter_repair_patch_scope(doc, {"note": "explicit new reference", "callsUpsert": [candidate, hostile]}, scope)
    assert audit["ok"], audit
    assert any(row["reason"] == "independent_valid_node_frozen" for row in audit["ignoredChanges"])
    repaired = apply_repair_patch(doc, filtered)
    assert validate_runtime_program(repaired)["ok"]
    expected = deepcopy(doc); _probe(expected)["params"]["entity"] = "other_nail"
    assert repaired == expected
    assert doc == before


def test_reference_repair_can_create_complete_child_without_touching_existing_nodes(constrained_reference):
    doc = _doc()
    report = validate_runtime_program(doc)
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["create"]["entities"]["allowed"]
    assert set(scope["create"]["entities"]["allowedKinds"]) == {"free_projectile", "child_projectile"}
    assert scope["create"]["calls"]["allowedTargetIds"] == []
    assert "spawn_over_target" not in scope["create"]["calls"]["allowedFns"]
    entity, calls = _new_child(doc, "selected_nail")
    candidate = deepcopy(_probe(doc)); candidate["params"]["entity"] = entity["id"]
    patch = {"note": "explicit complete replacement child", "entitiesUpsert": [entity], "callsUpsert": [candidate, *calls]}
    filtered, audit = filter_repair_patch_scope(doc, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(doc, filtered)
    assert validate_runtime_program(repaired)["ok"]
    assert next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == "nail_spawn")["params"]["aim"] == "cursor"
    assert len(repaired["runtimeProgram"]["entities"]) == len(doc["runtimeProgram"]["entities"]) + 1
