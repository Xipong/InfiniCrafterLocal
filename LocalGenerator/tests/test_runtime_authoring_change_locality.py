from __future__ import annotations

import ast
import inspect
from dataclasses import replace
from types import ModuleType

from infini_local.core.runtime_authoring import (
    audit_compiler_receipts,
    compile_runtime_program,
    compiler,
    repair_scope,
    validator,
)
from infini_local.core.runtime_authoring import capability_registry
from infini_local.core.runtime_authoring.capability_registry import (
    EVENT_KIND_REGISTRY,
    EventDependencyAlternative,
    event_alternative_is_present,
    event_dependency_alternatives,
)
from infini_local.core.runtime_authoring.program_schema import (
    PRIMARY_ENTITY_FIELD,
    PRIMARY_ENTITY_SELECTION_FIELD,
    authored_primary_entity_id,
    primary_entity_repair_transaction,
)
from infini_local.core.runtime_authoring.technical_lowering import (
    EXACT_REPETITION_COMPRESSION_POLICY,
    GLOBAL_TECHNICAL_LOWERINGS,
    MIN_EXACT_REPETITION_COMPRESSION,
    PRIMARY_BINDING_ROLE_LOWERER_ID,
    PRIMARY_OWNER_LOWERER_ID,
    primary_binding_role,
    primary_owner_for_kind,
)
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def _imports_symbol(module: ModuleType, imported_module: str, symbol: str) -> bool:
    tree = ast.parse(inspect.getsource(module))
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == imported_module
        and any(alias.name == symbol for alias in node.names)
        for node in ast.walk(tree)
    )


def _imports_module(module: ModuleType, imported_module: str) -> bool:
    tree = ast.parse(inspect.getsource(module))
    return any(
        isinstance(node, ast.ImportFrom) and node.module == imported_module
        or isinstance(node, ast.Import)
        and any(alias.name == imported_module for alias in node.names)
        for node in ast.walk(tree)
    )


def test_primary_shape_and_repair_transaction_have_one_schema_owner() -> None:
    program = {PRIMARY_ENTITY_FIELD: "boomerang"}
    assert authored_primary_entity_id(program) == "boomerang"
    assert primary_entity_repair_transaction(["item", "boomerang", "item"]) == {
        "allowed": True,
        "candidateEntityIds": ["boomerang", "item"],
        "mustSelectExactlyOne": True,
    }
    assert _imports_symbol(
        validator,
        "infini_local.core.runtime_authoring.program_schema",
        "authored_primary_entity_id",
    )
    assert _imports_symbol(
        repair_scope,
        "infini_local.core.runtime_authoring.program_schema",
        "primary_entity_repair_transaction",
    )
    assert PRIMARY_ENTITY_SELECTION_FIELD == "primaryEntitySelection"


def test_primary_wire_projection_has_one_lowering_owner_and_receipts() -> None:
    assert primary_binding_role("boomerang", "boomerang") == "primary"
    assert primary_binding_role("boomerang", "item") == "secondary"
    assert primary_owner_for_kind("item_body") == "item_body"
    assert primary_owner_for_kind("free_projectile") == "projectile"
    assert primary_owner_for_kind("unknown_future_kind") == ""
    assert _imports_symbol(
        compiler,
        "infini_local.core.runtime_authoring.technical_lowering",
        "primary_binding_role",
    )

    compiled = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    receipts = compiled["runtimeContract"]["finalWireReceipts"]
    owner_receipts = [
        row for row in receipts
        if row.get("lowererId") == PRIMARY_OWNER_LOWERER_ID
    ]
    assert len(owner_receipts) == 1
    assert owner_receipts[0]["value"] == compiled["runtimeProgram"]["primaryOwner"]
    assert audit_compiler_receipts(receipts)["ok"] is True

    role_lowerer = next(
        row for row in GLOBAL_TECHNICAL_LOWERINGS
        if row["id"] == PRIMARY_BINDING_ROLE_LOWERER_ID
    )
    assert role_lowerer["addsDesignChoice"] is False
    assert "authoringCompression" not in role_lowerer


def test_exact_repetition_policy_is_global_and_not_a_primary_semantic_rule() -> None:
    assert MIN_EXACT_REPETITION_COMPRESSION == 5
    assert EXACT_REPETITION_COMPRESSION_POLICY == {
        "kind": "exact_repetition",
        "minimumRepeatedPlacements": 5,
        "requiresLiteralEquality": True,
        "mayAddDesignChoice": False,
    }
    for lowerer in GLOBAL_TECHNICAL_LOWERINGS:
        compression = lowerer.get("authoringCompression")
        if compression is not None:
            assert compression["minimumRepeatedPlacements"] >= 5
            assert compression["kind"] == "exact_repetition"


def test_event_dependency_is_a_typed_registry_projection() -> None:
    on_hit = event_dependency_alternatives("on_hit", "free_projectile")
    assert on_hit == (
        EventDependencyAlternative.required_call("set_projectile_damage"),
    )
    assert event_alternative_is_present(
        on_hit[0],
        target_id="projectile",
        target_calls=[{"fn": "set_projectile_damage", "params": {"damage": 7}}],
        bindings=[],
    )
    assert not event_alternative_is_present(
        on_hit[0], target_id="projectile", target_calls=[], bindings=[],
    )

    on_use = event_dependency_alternatives("on_use", "item_body")
    assert on_use == (
        EventDependencyAlternative.any_binding_input(
            ("primary_use", "alternate_use"),
            ("spawn_entity", "use_item_body", "apply_item_effects"),
        ),
    )
    assert event_alternative_is_present(
        on_use[0],
        target_id="item",
        target_calls=[],
        bindings=[{
            "input": "primary_use",
            "usePolicy": {
                "action": {"kind": "use_item_body", "targetId": "item"},
                "stackCost": 0,
                "contactDamage": True,
            },
        }],
    )
    assert not event_alternative_is_present(
        on_use[0],
        target_id="item",
        target_calls=[],
        bindings=[{
            "input": "primary_use",
            "usePolicy": {
                "action": {"kind": "place_item", "targetId": "item", "placementCallId": "place"},
                "stackCost": 1,
                "contactDamage": False,
            },
        }],
    )
    assert EVENT_KIND_REGISTRY["on_use"].prompt_card()["producerFreeKinds"] == []
    assert "free_projectile" in EVENT_KIND_REGISTRY["on_spawn"].prompt_card()["producerFreeKinds"]
    tile = event_dependency_alternatives("on_tile_collision", "free_projectile")
    assert tile == (
        EventDependencyAlternative.required_call(
            "set_projectile_collision",
            {"tileCollide": True},
        ),
    )


def test_event_registry_mutation_reaches_validator_and_repair_projection(monkeypatch) -> None:
    # Without damage, this on_hit has no producer under the original registry;
    # its existing collision call becomes the producer after the registry edit.
    without_damage = build_runtime_fixture("workbench_blade")
    without_damage["runtimeProgram"]["calls"] = [
        row for row in without_damage["runtimeProgram"]["calls"]
        if row["id"] != "workbench_blade_damage"
    ]
    original_errors = validator.validate_runtime_program(without_damage)["errors"]
    assert [(row["code"], row["allowed"]) for row in original_errors] == [
        ("event_not_emitted", ["set_projectile_damage"]),
    ]

    # Conversely, removing collision leaves an unrelated required-component
    # error, but on_hit itself is still emitted by the original damage call.
    without_collision = build_runtime_fixture("workbench_blade")
    without_collision["runtimeProgram"]["calls"] = [
        row for row in without_collision["runtimeProgram"]["calls"]
        if row["id"] != "workbench_blade_collision"
    ]
    assert [row["code"] for row in validator.validate_runtime_program(without_collision)["errors"]] == [
        "missing_required_component",
    ]

    registry = dict(EVENT_KIND_REGISTRY)
    registry["on_hit"] = replace(
        registry["on_hit"],
        producer_capabilities=("set_projectile_collision",),
    )
    monkeypatch.setattr(capability_registry, "EVENT_KIND_REGISTRY", registry)
    assert validator.validate_runtime_program(without_damage)["ok"] is True

    changed_errors = validator.validate_runtime_program(without_collision)["errors"]
    event_errors = [row for row in changed_errors if row["code"] == "event_not_emitted"]
    assert len(event_errors) == 1
    assert event_errors[0]["allowed"] == ["set_projectile_collision"]
    assert event_errors[0]["relatedIds"] == ["workbench_blade"]
    scope = repair_scope.build_runtime_repair_scope(without_collision, event_errors)
    assert scope["create"]["calls"]["allowedFns"] == ["set_projectile_collision"]
    assert scope["create"]["calls"]["allowedTargetIds"] == ["workbench_blade"]
    assert scope["repairRequirements"][0]["requiredOneOfCapabilities"] == ["set_projectile_collision"]
    assert scope["eventAlternatives"] == [{
        "callId": "shed_nails",
        "targetId": "workbench_blade",
        "allowed": [{
            "event": "on_hit",
            "requiredCalls": [{
                "fn": "set_projectile_collision",
                "targetId": "workbench_blade",
                "exactParams": [],
            }],
            "requiredBindings": [],
        }],
        "mustChooseOneCompleteAlternative": True,
    }]


def test_removed_facade_modules_have_no_consumers() -> None:
    consumers = (compiler, validator, repair_scope)
    forbidden = (
        "infini_local.core.runtime_authoring.primary_entity_contract",
        "infini_local.core.runtime_authoring.event_dependency_contract",
    )
    assert not any(
        _imports_module(module, imported_module)
        for module in consumers
        for imported_module in forbidden
    )
