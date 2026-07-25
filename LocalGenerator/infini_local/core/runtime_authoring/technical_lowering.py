from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY


TECHNICAL_LOWERING_SCHEMA = "infini.technical-lowering-manifest.v1"

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
        "outputs": ["runtimeProgram.entities[].visualRole"],
        "equivalence": "one canonical renderer role name for each explicitly authored entity kind",
        "preserves": ["entity kind", "entity identity", "all gameplay components"],
    },
    {
        "id": "capability_name_to_opcode",
        "inputs": ["runtimeProgram.calls[].fn"],
        "outputs": ["runtimeProgram.entities[].movement.code", "runtimeProgram.entities[].controller.code", "runtimeProgram.entities[].events[].actionCode"],
        "equivalence": "finite numeric wire opcode for the exact authored capability name",
        "preserves": ["capability identity", "target", "params", "event links"],
    },
    {
        "id": "item_fields_to_tml_projection",
        "inputs": ["item_body capability params"],
        "outputs": list(_ITEM_TECHNICAL_OUTPUTS),
        "equivalence": "same authored semantic value copied into the exact DTO fields consumed by Terraria/tModLoader",
        "preserves": ["all authored item values", "explicit zero", "units"],
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


def audit_compiler_receipts(receipts: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    for receipt in receipts:
        fn = str(receipt.get("fn") or "")
        path = str(receipt.get("finalPath") or "")
        declared = declared_outputs_for(fn)
        if not declared or not any(path_matches(pattern, path) for pattern in declared):
            violations.append({
                "callId": str(receipt.get("callId") or ""),
                "fn": fn,
                "finalPath": path,
                "declaredOutputs": list(declared),
                "reason": "compiler wrote an undeclared field",
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
        "globalLowerers": list(GLOBAL_TECHNICAL_LOWERINGS),
        "capabilities": capability_rows,
    }


__all__ = [
    "GLOBAL_TECHNICAL_LOWERINGS",
    "TECHNICAL_LOWERING_SCHEMA",
    "audit_compiler_receipts",
    "declared_outputs_for",
    "path_matches",
    "technical_lowering_manifest",
]
