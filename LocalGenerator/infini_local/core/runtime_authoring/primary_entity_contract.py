from __future__ import annotations

from typing import Any, Iterable, Mapping


PRIMARY_ENTITY_FIELD = "primaryEntityId"
PRIMARY_ENTITY_AUTHOR_PATH = f"runtimeProgram.{PRIMARY_ENTITY_FIELD}"
PRIMARY_ENTITY_JSON_PATH = f"$.{PRIMARY_ENTITY_AUTHOR_PATH}"
PRIMARY_ENTITY_SELECTION_FIELD = "primaryEntitySelection"
PRIMARY_BINDING_ROLE_LOWERER_ID = "primary_entity_to_binding_role"
MIN_AUTHORING_REPETITION_COMPRESSION = 5
PRIMARY_AUTHOR_SYSTEM_RULE = (
    f"Before returning, require {PRIMARY_ENTITY_AUTHOR_PATH} to equal exactly one emitted entity id; "
    "binding/call rows do not carry role because Lowery derives technical wire roles from exact target equality."
)
PRIMARY_REPAIR_SYSTEM_RULE = (
    f"Use {PRIMARY_ENTITY_SELECTION_FIELD} whenever its repair transaction is enabled."
)


def authored_primary_entity_id(program: Mapping[str, Any]) -> str:
    return str(program.get(PRIMARY_ENTITY_FIELD) or "")


def primary_binding_role(primary_entity_id: str, binding_target: str) -> str:
    return "primary" if binding_target == primary_entity_id else "secondary"


def primary_owner_for_kind(entity_kind: str) -> str:
    return "item_body" if entity_kind == "item_body" else "projectile"


def primary_entity_repair_transaction(entity_ids: Iterable[str]) -> dict[str, Any]:
    candidates = sorted({str(entity_id) for entity_id in entity_ids if str(entity_id)})
    if not candidates:
        return {}
    return {
        "allowed": True,
        "candidateEntityIds": candidates,
        "mustSelectExactlyOne": True,
    }


def primary_entity_llm_invariant() -> dict[str, Any]:
    return {
        "exactlyOnePrimaryEntity": True,
        "authoredField": PRIMARY_ENTITY_AUTHOR_PATH,
        "primaryRule": (
            f"Choose exactly one id from runtimeProgram.entities and emit it once as {PRIMARY_ENTITY_AUTHOR_PATH}. "
            "Primary means executable ownership, not importance."
        ),
        "preEmissionCheck": (
            f"Reject your draft unless {PRIMARY_ENTITY_FIELD} exactly equals one emitted entity id. "
            "Binding and call rows do not carry role; technical wire roles are losslessly lowered from exact target equality."
        ),
    }


def primary_entity_self_check() -> str:
    return (
        f"set {PRIMARY_ENTITY_AUTHOR_PATH} to exactly one existing entity id and never emit role in Author "
        "bindings or calls; Lowery materializes wire roles from exact target equality"
    )


def primary_binding_role_receipt(*, source_index: int, final_index: int, role: str) -> dict[str, Any]:
    return {
        "lowererId": PRIMARY_BINDING_ROLE_LOWERER_ID,
        "authoredPaths": [PRIMARY_ENTITY_AUTHOR_PATH, f"runtimeProgram.bindings[{source_index}].target"],
        "finalPath": f"runtimeProgram.bindings[{final_index}].role",
        "value": role,
        "status": "technical_projection",
    }


__all__ = [
    "MIN_AUTHORING_REPETITION_COMPRESSION",
    "PRIMARY_AUTHOR_SYSTEM_RULE",
    "PRIMARY_BINDING_ROLE_LOWERER_ID",
    "PRIMARY_ENTITY_AUTHOR_PATH",
    "PRIMARY_ENTITY_FIELD",
    "PRIMARY_ENTITY_JSON_PATH",
    "PRIMARY_ENTITY_SELECTION_FIELD",
    "PRIMARY_REPAIR_SYSTEM_RULE",
    "authored_primary_entity_id",
    "primary_binding_role",
    "primary_binding_role_receipt",
    "primary_entity_llm_invariant",
    "primary_entity_repair_transaction",
    "primary_entity_self_check",
    "primary_owner_for_kind",
]
