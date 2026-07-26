from __future__ import annotations

import ast
import inspect
from types import ModuleType

from infini_local.core.runtime_authoring import compiler, repair_scope, validator
from infini_local.core.runtime_authoring.event_dependency_contract import (
    EventDependencyAlternative,
    event_alternative_is_present,
    event_dependency_alternatives,
)
from infini_local.core.runtime_authoring.primary_entity_contract import (
    MIN_AUTHORING_REPETITION_COMPRESSION,
    PRIMARY_BINDING_ROLE_LOWERER_ID,
    primary_binding_role,
    primary_entity_repair_transaction,
    primary_owner_for_kind,
)
from infini_local.core.runtime_authoring.technical_lowering import GLOBAL_TECHNICAL_LOWERINGS


def _imports_symbol(module: ModuleType, imported_module: str, symbol: str) -> bool:
    tree = ast.parse(inspect.getsource(module))
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == imported_module
        and any(alias.name == symbol for alias in node.names)
        for node in ast.walk(tree)
    )


def test_primary_entity_contract_owns_exact_projection_and_repair_transaction() -> None:
    assert MIN_AUTHORING_REPETITION_COMPRESSION == 5
    assert primary_binding_role("boomerang", "boomerang") == "primary"
    assert primary_binding_role("boomerang", "item") == "secondary"
    assert primary_owner_for_kind("item_body") == "item_body"
    assert primary_owner_for_kind("free_projectile") == "projectile"
    assert primary_entity_repair_transaction(["item", "boomerang", "item"]) == {
        "allowed": True,
        "candidateEntityIds": ["boomerang", "item"],
        "mustSelectExactlyOne": True,
    }

    lowerer = next(row for row in GLOBAL_TECHNICAL_LOWERINGS if row["id"] == PRIMARY_BINDING_ROLE_LOWERER_ID)
    assert lowerer["addsDesignChoice"] is False
    assert lowerer["authoringCompression"] == {
        "kind": "exact_repetition",
        "minimumRepeatedPlacements": 5,
        "equality": "binding.target == runtimeProgram.primaryEntityId",
    }
    assert _imports_symbol(
        compiler,
        "infini_local.core.runtime_authoring.primary_entity_contract",
        "primary_binding_role",
    )


def test_event_dependency_contract_is_typed_and_shared_by_validator_and_repair() -> None:
    alternatives = event_dependency_alternatives("on_hit", "free_projectile")
    assert alternatives == (
        EventDependencyAlternative.required_call("set_projectile_damage"),
    )
    assert event_alternative_is_present(
        alternatives[0],
        target_calls=[{"fn": "set_projectile_damage", "params": {"damage": 7}}],
        bindings=[],
    )
    assert not event_alternative_is_present(alternatives[0], target_calls=[], bindings=[])

    owner = "infini_local.core.runtime_authoring.event_dependency_contract"
    assert _imports_symbol(validator, owner, "event_dependency_alternatives")
    assert _imports_symbol(repair_scope, owner, "event_dependency_alternatives")
    assert not _imports_symbol(
        repair_scope,
        "infini_local.core.runtime_authoring.validator",
        "event_dependency_alternatives",
    )
