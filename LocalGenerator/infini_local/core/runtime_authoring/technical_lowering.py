from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from infini_local.core.runtime_authoring.capability_registry import (
    CAPABILITY_REGISTRY,
    ENTITY_KIND_REGISTRY,
    equipment_damage_wire_path,
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


_MISSING = object()


def _final_value(document: Mapping[str, Any], path: str) -> Any:
    """Read a compiler receipt path without evaluating arbitrary expressions."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*|\[\d+\])*", path):
        return _MISSING
    value: Any = document
    for segment in re.findall(r"[A-Za-z][A-Za-z0-9_]*|\[\d+\]", path):
        if segment.startswith("["):
            index = int(segment[1:-1])
            if not isinstance(value, list) or index >= len(value):
                return _MISSING
            value = value[index]
        else:
            if not isinstance(value, Mapping) or segment not in value:
                return _MISSING
            value = value[segment]
    return value


def audit_compiler_receipts(
    receipts: Iterable[Mapping[str, Any]], *, authored_document: Mapping[str, Any] | None = None,
    final_document: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    program = authored_document.get("runtimeProgram") if authored_document is not None else None
    source_calls = program.get("calls") if isinstance(program, Mapping) else None
    source_calls = source_calls if isinstance(source_calls, list) else []
    violations: list[dict[str, Any]] = []
    receipt_rows = tuple(receipts)
    delivered_equipment: dict[str, int] = {}
    for receipt in receipt_rows:
        fn = str(receipt.get("fn") or "")
        lowerer_id = str(receipt.get("lowererId") or "")
        path = str(receipt.get("finalPath") or "")
        authored_path = str(receipt.get("authoredPath") or "")
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
        if final_document is not None and _final_value(final_document, path) != receipt.get("value"):
            violations.append({
                "callId": str(receipt.get("callId") or ""),
                "fn": fn,
                "finalPath": path,
                "reason": "final wire value differs from compiler receipt",
            })
        parameter_match = re.fullmatch(
            r"runtimeProgram\.calls\[(\d+)\]\.params\.([A-Za-z][A-Za-z0-9_]*)", authored_path
        ) if fn and not lowerer_id else None
        if fn and authored_paths and (fn != "add_equipment_damage_bonus" or receipt.get("status") != "delivered"):
            violations.append({
                "callId": str(receipt.get("callId") or ""), "fn": fn,
                "authoredPath": authored_path, "finalPath": path,
                "reason": "unexpected capability parameter source list or status",
            })
        if fn and not lowerer_id and (receipt.get("status") == "delivered" or parameter_match is not None):
            match = parameter_match
            cap = CAPABILITY_REGISTRY.get(fn)
            if match is not None and receipt.get("status") != "delivered" and not (
                fn == "apply_vanilla_buff_on_use" and receipt.get("status") == "technical_projection"
            ):
                violations.append({
                    "callId": str(receipt.get("callId") or ""), "fn": fn,
                    "authoredPath": authored_path, "finalPath": path,
                    "reason": "capability parameter receipt has an unexpected status",
                })
            if match is not None and cap is not None and match.group(2) in cap.params and fn != "add_equipment_damage_bonus":
                param = match.group(2)
                spec = cap.params[param]
                names = {param, spec.wire_name} - {""}
                expected_paths = tuple(
                    candidate for candidate in cap.final_wire_paths
                    if candidate.rsplit(".", 1)[-1] in names
                )
                if not expected_paths or not any(path_matches(candidate, path) for candidate in expected_paths):
                    violations.append({
                        "callId": str(receipt.get("callId") or ""),
                        "fn": fn,
                        "authoredPath": authored_path,
                        "finalPath": path,
                        "expectedPaths": list(expected_paths),
                        "reason": "wrong capability output for authored parameter",
                    })
            if match is None or cap is None or match.group(2) not in cap.params:
                violations.append({
                    "callId": str(receipt.get("callId") or ""),
                    "fn": fn,
                    "authoredPath": authored_path,
                    "finalPath": path,
                    "reason": "compiler receipt used an undeclared authored parameter",
                })
            elif authored_document is not None:
                index = int(match.group(1))
                source_call = source_calls[index] if index < len(source_calls) else None
                source_params = source_call.get("params") if isinstance(source_call, Mapping) else None
                if (not isinstance(source_call, Mapping)
                    or source_call.get("fn") != fn
                    or source_call.get("id") != receipt.get("callId")
                    or not isinstance(source_params, Mapping)
                    or match.group(2) not in source_params):
                    violations.append({
                        "callId": str(receipt.get("callId") or ""),
                        "fn": fn,
                        "authoredPath": authored_path,
                        "finalPath": path,
                        "reason": "authored parameter absent from originating call",
                    })
                elif receipt.get("value") != cap.params[match.group(2)].to_wire(source_params[match.group(2)]):
                    violations.append({
                        "callId": str(receipt.get("callId") or ""),
                        "fn": fn,
                        "authoredPath": authored_path,
                        "finalPath": path,
                        "reason": "compiler receipt value is not the declared projection of its authored parameter",
                    })
                if fn == "configure_item_stats":
                    param = match.group(2)
                    expected = f"gameplay.{cap.params[param].wire_name or param}"
                    if path != expected:
                        violations.append({
                            "callId": str(receipt.get("callId") or ""),
                            "fn": fn,
                            "authoredPath": authored_path,
                            "finalPath": path,
                            "expectedPath": expected,
                            "reason": "wrong item stat output for authored parameter",
                        })
                if fn in {"configure_accessory", "configure_armor"}:
                    prefix = "accessory" if fn == "configure_accessory" else "armor"
                    expected = f"{prefix}.{cap.params[match.group(2)].wire_name or match.group(2)}"
                    if path != expected:
                        violations.append({
                            "callId": str(receipt.get("callId") or ""),
                            "fn": fn,
                            "authoredPath": authored_path,
                            "finalPath": path,
                            "expectedPath": expected,
                            "reason": "wrong equipment output for authored parameter",
                        })
                    delivered_equipment[authored_path] = delivered_equipment.get(authored_path, 0) + 1
                elif fn == "add_equipment_damage_bonus" and isinstance(source_params, Mapping):
                    source_target = str(source_call.get("target") or "") if isinstance(source_call, Mapping) else ""
                    configs = [row for row in source_calls
                               if isinstance(row, Mapping) and row.get("target") == source_target
                               and row.get("fn") in {"configure_accessory", "configure_armor"}]
                    if len(configs) == 1 and match.group(2) == "bonusPercent":
                        try:
                            expected = equipment_damage_wire_path(
                                str(source_params.get("phase") or ""),
                                str(source_params.get("damageClass") or ""),
                                armor=configs[0].get("fn") == "configure_armor",
                            )
                        except ValueError:
                            expected = ""
                        base = f"runtimeProgram.calls[{index}].params"
                        expected_sources = [f"{base}.phase", f"{base}.damageClass", f"{base}.bonusPercent"]
                        if path != expected or receipt.get("authoredPaths") != expected_sources:
                            violations.append({
                                "callId": str(receipt.get("callId") or ""),
                                "fn": fn,
                                "finalPath": path,
                                "expectedPath": expected,
                                "reason": "wrong equipment output for authored parameter",
                            })
                        delivered_equipment[authored_path] = delivered_equipment.get(authored_path, 0) + 1
                    else:
                        violations.append({
                            "callId": str(receipt.get("callId") or ""), "fn": fn,
                            "finalPath": path, "reason": "equipment class modifier has no unique declared configuration",
                        })
    if authored_document is not None:
        for index, call in enumerate(source_calls):
            if not isinstance(call, Mapping) or call.get("fn") not in {"configure_accessory", "configure_armor", "add_equipment_damage_bonus"}:
                continue
            params = call.get("params")
            if not isinstance(params, Mapping):
                continue
            param_names = params if call.get("fn") != "add_equipment_damage_bonus" else ("bonusPercent",)
            for param in param_names:
                authored_path = f"runtimeProgram.calls[{index}].params.{param}"
                if delivered_equipment.get(authored_path, 0) != 1:
                    violations.append({
                        "callId": str(call.get("id") or ""),
                        "fn": str(call.get("fn") or ""),
                        "authoredPath": authored_path,
                        "reason": "equipment parameter has no receipt or more than one receipt",
                    })
        delivered_sources = {
            (str(receipt.get("fn") or ""), str(receipt.get("callId") or ""), str(source))
            for receipt in receipt_rows
            if receipt.get("fn") and receipt.get("callId")
            for source in (receipt.get("authoredPath"), *(receipt.get("authoredPaths") or ()))
            if source
        }
        for index, source_call in enumerate(source_calls):
            if not isinstance(source_call, Mapping):
                continue
            source_params = source_call.get("params")
            if not isinstance(source_params, Mapping):
                continue
            for name in source_params:
                key = (str(source_call.get("fn") or ""), str(source_call.get("id") or ""),
                       f"runtimeProgram.calls[{index}].params.{name}")
                if key not in delivered_sources:
                    violations.append({
                        "callId": key[1], "fn": key[0], "authoredPath": key[2],
                        "reason": "authored parameter has no compiler receipt",
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
