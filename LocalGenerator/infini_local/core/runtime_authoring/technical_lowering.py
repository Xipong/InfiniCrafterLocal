from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from infini_local.core.runtime_authoring.capability_registry import (
    CAPABILITY_REGISTRY,
    ENTITY_KIND_REGISTRY,
)
from infini_local.core.runtime_authoring.program_schema import (
    PRIMARY_ENTITY_AUTHOR_PATH,
)


TECHNICAL_LOWERING_SCHEMA = "infini.technical-lowering-manifest.v1"
MIN_EXACT_REPETITION_COMPRESSION = 5
PRIMARY_BINDING_ROLE_LOWERER_ID = "primary_entity_to_binding_role"
PRIMARY_OWNER_LOWERER_ID = "primary_entity_kind_to_owner"
PRIMARY_OWNER_FINAL_PATH = "runtimeProgram.primaryOwner"
EXACT_REPETITION_COMPRESSION_POLICY = {
    "kind": "exact_repetition",
    "minimumRepeatedPlacements": MIN_EXACT_REPETITION_COMPRESSION,
    "requiresLiteralEquality": True,
    "mayAddDesignChoice": False,
}


def primary_binding_role(primary_entity_id: str, binding_target: str) -> str:
    return "primary" if binding_target == primary_entity_id else "secondary"


def primary_owner_for_kind(entity_kind: str) -> str:
    spec = ENTITY_KIND_REGISTRY.get(entity_kind)
    if spec is None:
        return ""
    return "projectile" if spec.projectile else "item_body"


def primary_binding_role_receipt(
    *,
    source_index: int,
    final_index: int,
    role: str,
) -> dict[str, Any]:
    return {
        "lowererId": PRIMARY_BINDING_ROLE_LOWERER_ID,
        "authoredPaths": [
            PRIMARY_ENTITY_AUTHOR_PATH,
            f"runtimeProgram.bindings[{source_index}].usePolicy.action.targetId",
        ],
        "finalPath": f"runtimeProgram.bindings[{final_index}].role",
        "value": role,
        "status": "technical_projection",
    }


def primary_owner_receipt(*, source_index: int, owner: str) -> dict[str, Any]:
    entity_path = f"runtimeProgram.entities[{source_index}]"
    return {
        "lowererId": PRIMARY_OWNER_LOWERER_ID,
        "authoredPaths": [
            PRIMARY_ENTITY_AUTHOR_PATH,
            f"{entity_path}.id",
            f"{entity_path}.kind",
        ],
        "finalPath": PRIMARY_OWNER_FINAL_PATH,
        "value": owner,
        "status": "technical_projection",
    }

# These are the only non-capability design-neutral projections. They serialize one
# authored value into the tModLoader-facing DTO shape or derive an opcode/role from
# an already-authored exact capability/entity kind. They never choose movement,
# attachment, delivery, lifecycle, input, damage, or visual topology.
_ITEM_TECHNICAL_OUTPUTS = tuple(dict.fromkeys(
    path
    for capability in CAPABILITY_REGISTRY.values()
    if capability.target_kinds == ("item_body",)
    for path in capability.final_wire_paths
    if path.startswith(("gameplay.", "accessory.", "armor.", "runtimeProgram.itemUse.", "runtimeProgram.itemContact."))
))

GLOBAL_TECHNICAL_LOWERINGS: tuple[dict[str, Any], ...] = (
    {
        "id": "entity_kind_to_visual_role",
        "inputs": ["runtimeProgram.entities[].kind"],
        "outputs": ["runtimeProgram.entities[].visualRole", "runtimeProgram.entities[].visual.role"],
        "equivalence": "one canonical renderer role name for each explicitly authored entity kind",
        "preserves": ["entity kind", "entity identity", "all gameplay components"],
        "addsDesignChoice": False,
    },
    {
        "id": PRIMARY_BINDING_ROLE_LOWERER_ID,
        "inputs": [PRIMARY_ENTITY_AUTHOR_PATH, "runtimeProgram.bindings[].usePolicy.action.targetId"],
        "outputs": ["runtimeProgram.bindings[].role"],
        "equivalence": "primary exactly when the authored binding target equals the exact authored primary entity id; secondary otherwise",
        "preserves": ["primary entity identity", "binding identity", "binding target", "input", "action"],
        "addsDesignChoice": False,
    },
    {
        "id": PRIMARY_OWNER_LOWERER_ID,
        "inputs": [PRIMARY_ENTITY_AUTHOR_PATH, "runtimeProgram.entities[].id", "runtimeProgram.entities[].kind"],
        "outputs": [PRIMARY_OWNER_FINAL_PATH],
        "equivalence": "wire owner family for the exact kind of the exact authored primary entity id",
        "preserves": ["primary entity identity", "entity kind"],
        "addsDesignChoice": False,
    },
    {
        "id": "capability_name_to_opcode",
        "inputs": ["runtimeProgram.calls[].fn"],
        "outputs": ["runtimeProgram.entities[].movement.code", "runtimeProgram.entities[].controller.code", "runtimeProgram.entities[].events[].actionCode"],
        "equivalence": "finite numeric wire opcode for the exact authored capability name",
        "preserves": ["capability identity", "target", "params", "event links"],
        "addsDesignChoice": False,
    },
    {
        "id": "item_fields_to_tml_projection",
        "inputs": ["item_body capability params"],
        "outputs": list(_ITEM_TECHNICAL_OUTPUTS),
        "equivalence": "same authored semantic value copied into the exact DTO fields consumed by Terraria/tModLoader",
        "preserves": ["all authored item values", "explicit zero", "units"],
        "addsDesignChoice": False,
    },
)


def _normalize(path: str) -> str:
    return re.sub(r"\[\d+\]", "[]", path)


def path_matches(pattern: str, path: str) -> bool:
    normalized = _normalize(path)
    expression = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
    return re.fullmatch(expression, normalized) is not None


def declared_outputs_for(fn: str) -> tuple[str, ...]:
    cap = CAPABILITY_REGISTRY.get(fn)
    if cap is None:
        return ()
    return tuple(dict.fromkeys((*cap.final_wire_paths, *cap.technical_lowering_outputs)))


def declared_global_outputs_for(lowerer_id: str) -> tuple[str, ...]:
    for lowerer in GLOBAL_TECHNICAL_LOWERINGS:
        if str(lowerer.get("id") or "") == lowerer_id:
            return tuple(str(path) for path in lowerer.get("outputs") or ())
    return ()


def declared_global_inputs_for(lowerer_id: str) -> tuple[str, ...]:
    for lowerer in GLOBAL_TECHNICAL_LOWERINGS:
        if str(lowerer.get("id") or "") == lowerer_id:
            return tuple(str(path) for path in lowerer.get("inputs") or ())
    return ()


def audit_compiler_receipts(receipts: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    for receipt in receipts:
        fn = str(receipt.get("fn") or "")
        lowerer_id = str(receipt.get("lowererId") or "")
        path = str(receipt.get("finalPath") or "")
        declared = declared_global_outputs_for(lowerer_id) if lowerer_id else declared_outputs_for(fn)
        declared_inputs = declared_global_inputs_for(lowerer_id) if lowerer_id else ()
        authored_paths = tuple(str(value) for value in receipt.get("authoredPaths") or ())
        inputs_match = not lowerer_id or (
            all(any(path_matches(pattern, value) for value in authored_paths) for pattern in declared_inputs)
            and all(any(path_matches(pattern, value) for pattern in declared_inputs) for value in authored_paths)
        )
        if not declared or not any(path_matches(pattern, path) for pattern in declared) or not inputs_match:
            violations.append({
                "callId": str(receipt.get("callId") or ""),
                "fn": fn,
                "lowererId": lowerer_id,
                "finalPath": path,
                "authoredPaths": list(authored_paths),
                "declaredInputs": list(declared_inputs),
                "declaredOutputs": list(declared),
                "reason": "compiler receipt used an undeclared input or output field",
            })
    return {
        "schema": "infini.technical-lowering-audit.v1",
        "ok": not violations,
        "violations": violations,
        "lowerers": list(GLOBAL_TECHNICAL_LOWERINGS),
    }


def technical_lowering_manifest() -> dict[str, Any]:
    capability_rows = []
    for name, cap in CAPABILITY_REGISTRY.items():
        capability_rows.append({
            "capability": name,
            "outputs": list(declared_outputs_for(name)),
            "authoredDecisionsPreserved": True,
            "addsDesignChoice": False,
            "compilerOwner": cap.compiler_owner,
            "csharpOwner": cap.csharp_owner,
        })
    return {
        "schema": TECHNICAL_LOWERING_SCHEMA,
        "exactRepetitionCompressionPolicy": dict(EXACT_REPETITION_COMPRESSION_POLICY),
        "globalLowerers": list(GLOBAL_TECHNICAL_LOWERINGS),
        "capabilities": capability_rows,
    }


__all__ = [
    "EXACT_REPETITION_COMPRESSION_POLICY",
    "GLOBAL_TECHNICAL_LOWERINGS",
    "MIN_EXACT_REPETITION_COMPRESSION",
    "PRIMARY_BINDING_ROLE_LOWERER_ID",
    "PRIMARY_OWNER_FINAL_PATH",
    "PRIMARY_OWNER_LOWERER_ID",
    "TECHNICAL_LOWERING_SCHEMA",
    "audit_compiler_receipts",
    "declared_global_inputs_for",
    "declared_global_outputs_for",
    "declared_outputs_for",
    "path_matches",
    "primary_binding_role",
    "primary_binding_role_receipt",
    "primary_owner_for_kind",
    "primary_owner_receipt",
    "technical_lowering_manifest",
]
