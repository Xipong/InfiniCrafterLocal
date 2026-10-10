from __future__ import annotations

import re
import json
from typing import Any, Iterable, Mapping

from infini_local.core.runtime_authoring.capability_registry import (
    CAPABILITY_REGISTRY,
    ENTITY_KIND_REGISTRY,
    VISUAL_ROLE_BY_ENTITY_KIND,
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
STACK_CHANCE_LOWERER_ID = "binding_stack_chance_identity"
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


def stack_chance_receipt(*, source_index: int, final_index: int, value: int) -> dict[str, Any]:
    return {
        "lowererId": STACK_CHANCE_LOWERER_ID,
        "authoredPaths": [f"runtimeProgram.bindings[{source_index}].id",
                          f"runtimeProgram.bindings[{source_index}].usePolicy.stackConsumeChancePercent"],
        "finalPath": f"runtimeProgram.bindings[{final_index}].usePolicy.stackConsumeChancePercent",
        "value": value, "status": "technical_projection",
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
        "id": STACK_CHANCE_LOWERER_ID,
        "inputs": ["runtimeProgram.bindings[].id", "runtimeProgram.bindings[].usePolicy.stackConsumeChancePercent"],
        "outputs": ["runtimeProgram.bindings[].usePolicy.stackConsumeChancePercent"],
        "equivalence": "literal optional authored probability on the same exact binding identity",
        "preserves": ["binding identity", "explicit zero", "probability", "absence", "placement escrow"],
        "addsDesignChoice": False,
    },
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


def declared_neutral_omissions(fn: str, params: Mapping[str, Any]) -> dict[str, Any]:
    """Only explicit optional registry defaults equal to their neutral may fill an absent leaf."""
    cap = CAPABILITY_REGISTRY.get(fn)
    if cap is None:
        return {}
    return {
        name: spec.default for name, spec in cap.params.items()
        if name not in params and not spec.required and spec.default is not None
        and type(spec.default) is type(spec.neutral) and spec.default == spec.neutral
    }


def _parameter_outputs(fn: str, name: str) -> tuple[str, ...]:
    cap = CAPABILITY_REGISTRY[fn]
    spec = cap.params[name]
    names = {name, spec.wire_name} - {""}
    return tuple(dict.fromkeys(
        candidate for candidate in cap.final_wire_paths
        if candidate.rsplit(".", 1)[-1] in names
    ))


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


def _same_receipt_value(actual: Any, expected: Any) -> bool:
    """Preserve wire types and JSON representation, including signed zero."""
    return (type(actual) is type(expected)
            and json.dumps(actual, sort_keys=True, default=repr) == json.dumps(expected, sort_keys=True, default=repr))


def _receipt_path_segments(path: str) -> list[str | int] | None:
    """Parse receipt grammar; unrepresentable numeric indices are malformed."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*|\[\d+\])*", path):
        return None
    try:
        return [int(segment[1:-1]) if segment.startswith("[") else segment
                for segment in re.findall(r"[A-Za-z][A-Za-z0-9_]*|\[\d+\]", path)]
    except ValueError:
        # Python bounds decimal conversion. Report bad input, never truncate it
        # or change the process-wide integer conversion limit.
        return None


def _final_value(document: Mapping[str, Any], path: str) -> Any:
    """Read a compiler receipt path without evaluating arbitrary expressions."""
    segments = _receipt_path_segments(path)
    if segments is None:
        return _MISSING
    value: Any = document
    for segment in segments:
        if isinstance(segment, int):
            if not isinstance(value, list) or segment >= len(value):
                return _MISSING
            value = value[segment]
        else:
            if not isinstance(value, Mapping) or segment not in value:
                return _MISSING
            value = value[segment]
    return value


def _primary_receipt_source_error(
    receipt: Mapping[str, Any], authored_document: Mapping[str, Any],
    final_document: Mapping[str, Any] | None,
) -> str:
    """Check the actual source relation, not just declared path shapes."""
    lowerer_id = receipt.get("lowererId")
    if lowerer_id not in {PRIMARY_OWNER_LOWERER_ID, PRIMARY_BINDING_ROLE_LOWERER_ID}:
        return ""
    primary = _final_value(authored_document, PRIMARY_ENTITY_AUTHOR_PATH)
    entities = _final_value(authored_document, "runtimeProgram.entities")
    primary_rows = [(i, row) for i, row in enumerate(entities if isinstance(entities, list) else [])
                    if isinstance(row, Mapping) and row.get("id") == primary]
    if not isinstance(primary, str) or not primary or len(primary_rows) != 1:
        return "global receipt lacks a unique authored primary entity"
    source_index, entity = primary_rows[0]
    if final_document is not None and _final_value(final_document, PRIMARY_ENTITY_AUTHOR_PATH) != primary:
        return "global receipt primary identity differs from the authored source"
    if lowerer_id == PRIMARY_OWNER_LOWERER_ID:
        kind = entity.get("kind")
        expected = primary_owner_receipt(source_index=source_index, owner=primary_owner_for_kind(kind if isinstance(kind, str) else ""))
        if not expected["value"]:
            return "global receipt has an undeclared primary entity kind"
    else:
        paths = receipt.get("authoredPaths", [])
        match = re.fullmatch(r"runtimeProgram\.bindings\[(\d+)\]\.usePolicy\.action\.targetId", paths[1]) if len(paths) == 2 else None
        if match is None:
            return "global receipt lacks exact declared binding inputs"
        source_index = int(match.group(1))
        binding = _final_value(authored_document, f"runtimeProgram.bindings[{source_index}]")
        target = _final_value(authored_document, paths[1])
        if not isinstance(binding, Mapping) or not isinstance(target, str) or not target:
            return "global receipt lacks its originating authored binding"
        final_index = 0
        if final_document is not None:
            bindings = _final_value(final_document, "runtimeProgram.bindings")
            finals = [(i, row) for i, row in enumerate(bindings if isinstance(bindings, list) else [])
                      if isinstance(row, Mapping) and row.get("id") == binding.get("id")]
            if len(finals) != 1:
                return "global receipt lacks a unique final binding identity"
            final_index, _ = finals[0]
            if _final_value(final_document, f"runtimeProgram.bindings[{final_index}].usePolicy.action.targetId") != target:
                return "global receipt binding target differs from the authored source"
        expected = primary_binding_role_receipt(
            source_index=source_index, final_index=final_index, role=primary_binding_role(primary, target),
        )
    if any(receipt.get(key) != expected[key] for key in ("authoredPaths", "value", "status")):
        return "global receipt is not the exact declared projection of its authored source"
    if final_document is not None and receipt.get("finalPath") != expected["finalPath"]:
        return "global receipt output is not bound to its authored identity"
    return ""


def _visual_receipt_source_error(
    receipt: Mapping[str, Any], authored_document: Mapping[str, Any],
    final_document: Mapping[str, Any] | None,
) -> str:
    paths = receipt.get("authoredPaths", [])
    match = re.fullmatch(r"runtimeProgram\.entities\[(\d+)\]\.kind", paths[0]) if len(paths) == 1 else None
    entity = _final_value(authored_document, paths[0].rsplit(".", 1)[0]) if match else None
    kind = entity.get("kind") if isinstance(entity, Mapping) else None
    expected = VISUAL_ROLE_BY_ENTITY_KIND.get(kind) if isinstance(kind, str) else None
    if not isinstance(entity, Mapping) or expected is None or receipt.get("value") != expected:
        return "global visual receipt is not the declared projection of its authored kind"
    if final_document is not None:
        entities = _final_value(final_document, "runtimeProgram.entities")
        finals = [(i, row) for i, row in enumerate(entities if isinstance(entities, list) else [])
                  if isinstance(row, Mapping) and row.get("id") == entity.get("id")]
        if len(finals) != 1 or finals[0][1].get("kind") != kind or receipt.get("finalPath") not in {
            f"runtimeProgram.entities[{finals[0][0]}].visualRole",
            f"runtimeProgram.entities[{finals[0][0]}].visual.role",
        }:
            return "global visual receipt output is not bound to its authored entity identity/kind"
    return ""


def _global_receipt_wire_error(receipt: Mapping[str, Any], final_document: Mapping[str, Any]) -> str:
    """Recompute from wire facts only; these cannot authenticate Author indices."""
    lowerer_id = receipt.get("lowererId")
    path = receipt.get("finalPath", "")
    expected = _MISSING
    if lowerer_id == PRIMARY_OWNER_LOWERER_ID:
        primary = _final_value(final_document, PRIMARY_ENTITY_AUTHOR_PATH)
        entities = _final_value(final_document, "runtimeProgram.entities")
        rows = [row for row in entities if isinstance(row, Mapping) and row.get("id") == primary] if isinstance(entities, list) else []
        kind = rows[0].get("kind") if len(rows) == 1 else None
        expected = primary_owner_for_kind(kind) if isinstance(kind, str) else _MISSING
    elif lowerer_id == PRIMARY_BINDING_ROLE_LOWERER_ID:
        primary = _final_value(final_document, PRIMARY_ENTITY_AUTHOR_PATH)
        target = _final_value(final_document, path.rsplit(".", 1)[0] + ".usePolicy.action.targetId")
        if isinstance(primary, str) and primary and isinstance(target, str) and target:
            expected = primary_binding_role(primary, target)
    elif lowerer_id == "entity_kind_to_visual_role":
        match = re.fullmatch(r"(runtimeProgram\.entities\[\d+\])\.(?:visualRole|visual\.role)", path)
        kind = _final_value(final_document, match.group(1) + ".kind") if match else None
        expected = VISUAL_ROLE_BY_ENTITY_KIND.get(kind, _MISSING) if isinstance(kind, str) else _MISSING
    else:
        return ""
    return "global receipt is not the declared projection of final wire facts" if receipt.get("value") != expected else ""


def _stack_chance_source_error(receipt: Mapping[str, Any], authored: Mapping[str, Any], final: Mapping[str, Any] | None) -> str:
    paths = receipt.get("authoredPaths", [])
    match = re.fullmatch(r"runtimeProgram\.bindings\[(\d+)\]\.id", paths[0]) if len(paths) == 2 else None
    if not match or paths[1] != f"runtimeProgram.bindings[{match.group(1)}].usePolicy.stackConsumeChancePercent":
        return "stack chance receipt lacks exact same-binding inputs"
    binding_id = _final_value(authored, paths[0])
    value = _final_value(authored, paths[1])
    if type(value) is not int or not _same_receipt_value(value, receipt.get("value")):
        return "stack chance receipt differs from the explicit authored probability"
    if final is not None:
        bindings = _final_value(final, "runtimeProgram.bindings")
        matches = [i for i, binding in enumerate(bindings if isinstance(bindings, list) else [])
                   if isinstance(binding, Mapping) and binding.get("id") == binding_id]
        if len(matches) != 1 or receipt.get("finalPath") != f"runtimeProgram.bindings[{matches[0]}].usePolicy.stackConsumeChancePercent":
            return "stack chance receipt differs from its exact binding identity"
    return ""


def audit_compiler_receipts(
    receipts: Iterable[Any], *, authored_document: Mapping[str, Any] | None = None,
    final_document: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit supplied evidence; without Author, success is wire consistency only."""
    program = authored_document.get("runtimeProgram") if authored_document is not None else None
    source_calls = program.get("calls") if isinstance(program, Mapping) else None
    source_calls = source_calls if isinstance(source_calls, list) else []
    violations: list[dict[str, Any]] = []
    receipt_rows: list[Mapping[str, Any]] = []
    for receipt_index, receipt in enumerate(receipts):
        row_path = f"$.runtimeContract.finalWireReceipts[{receipt_index}]"
        malformed: list[str] = []
        if not isinstance(receipt, Mapping):
            malformed.append("")
        else:
            required = {"finalPath", "status"}
            required.update({"authoredPaths"} if receipt.get("lowererId") else {"fn", "callId", "authoredPath"})
            for key in ("fn", "lowererId", "callId", "finalPath", "authoredPath", "status"):
                if key in receipt or key in required:
                    if not isinstance(receipt.get(key), str) or not receipt[key]:
                        malformed.append(key)
            if "authoredPaths" in receipt or "authoredPaths" in required:
                paths = receipt.get("authoredPaths")
                if not isinstance(paths, list) or not all(isinstance(p, str) and p for p in paths):
                    malformed.append("authoredPaths")
            if "value" not in receipt:
                malformed.append("value")
            for key in ("finalPath", "authoredPath", "authoredPaths"):
                paths = receipt.get(key)
                paths = paths if key == "authoredPaths" else [paths]
                if isinstance(paths, list):
                    for index, path in enumerate(paths):
                        if isinstance(path, str) and _receipt_path_segments(path) is None:
                            malformed.append(f"{key}[{index}]" if key == "authoredPaths" else key)
        if malformed:
            violations.extend({"receiptIndex": receipt_index,
                               "path": row_path + (f".{key}" if key else ""),
                               "reason": "malformed compiler receipt row or field"}
                              for key in malformed)
            continue
        # Only structurally valid rows can participate in source coverage.
        receipt_rows.append(receipt)
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
            len(authored_paths) == len(declared_inputs)
            and all(path_matches(pattern, value) for pattern, value in zip(declared_inputs, authored_paths))
        )
        if lowerer_id == PRIMARY_OWNER_LOWERER_ID and inputs_match:
            inputs_match = authored_paths[1].rsplit(".", 1)[0] == authored_paths[2].rsplit(".", 1)[0]
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
        if lowerer_id and receipt.get("status") != "technical_projection":
            violations.append({"lowererId": lowerer_id, "finalPath": path,
                               "reason": "global receipt has an unexpected status"})
        if final_document is not None and not _same_receipt_value(_final_value(final_document, path), receipt.get("value")):
            violations.append({
                "callId": str(receipt.get("callId") or ""),
                "fn": fn,
                "finalPath": path,
                "reason": "final wire value differs from compiler receipt",
            })
        if authored_document is not None:
            reason = (_stack_chance_source_error(receipt, authored_document, final_document)
                      if lowerer_id == STACK_CHANCE_LOWERER_ID
                      else _visual_receipt_source_error(receipt, authored_document, final_document)
                      if lowerer_id == "entity_kind_to_visual_role"
                      else _primary_receipt_source_error(receipt, authored_document, final_document))
            if reason:
                violations.append({"lowererId": lowerer_id, "finalPath": path, "reason": reason})
        if final_document is not None and lowerer_id:
            reason = _global_receipt_wire_error(receipt, final_document)
            if reason:
                violations.append({"lowererId": lowerer_id, "finalPath": path, "reason": reason})
        if fn == "present_placed_item_sprite" and receipt.get("status") == "technical_projection":
            match = re.fullmatch(r"runtimeProgram\.calls\[(\d+)\]\.params\.placementCallId", authored_path)
            source_call = source_calls[int(match.group(1))] if match and int(match.group(1)) < len(source_calls) else None
            if authored_document is not None:
                source_index = int(match.group(1)) if match else -1
                source_bindings = program.get("bindings", []) if isinstance(program, Mapping) else []
                source_bindings = source_bindings if isinstance(source_bindings, list) else []
                source_params = source_call.get("params") if isinstance(source_call, Mapping) else None
                matches = [(i, binding) for i, binding in enumerate(source_bindings)
                           if isinstance(binding, Mapping) and isinstance(binding.get("usePolicy"), Mapping)
                           and isinstance(binding["usePolicy"].get("action"), Mapping)
                           and isinstance(source_call, Mapping) and isinstance(source_params, Mapping)
                           and binding["usePolicy"]["action"].get("kind") == "place_item"
                           and binding["usePolicy"]["action"].get("targetId") == source_call.get("target")
                           and binding["usePolicy"]["action"].get("placementCallId") == source_params.get("placementCallId")]
                expected_inputs = []
                expected_path = ""
                if len(matches) == 1:
                    bi, binding = matches[0]
                    cb = f"runtimeProgram.calls[{source_index}]"
                    bb = f"runtimeProgram.bindings[{bi}].usePolicy.action"
                    expected_inputs = [f"{cb}.fn", f"{cb}.target", f"{cb}.params.placementCallId",
                                       f"{bb}.kind", f"{bb}.targetId", f"{bb}.placementCallId"]
                    final_bindings = final_document.get("runtimeProgram", {}).get("bindings", []) if final_document is not None else []
                    finals = [i for i, b in enumerate(final_bindings) if isinstance(b, Mapping) and b.get("id") == binding.get("id")]
                    if len(finals) == 1:
                        expected_path = f"runtimeProgram.bindings[{finals[0]}].usePolicy.action.placement.placedBody"
                if (not isinstance(source_call, Mapping) or source_call.get("fn") != fn
                    or source_call.get("id") != receipt.get("callId") or not expected_inputs
                    or list(authored_paths) != expected_inputs or (final_document is not None and path != expected_path)):
                    violations.append({"fn": fn, "callId": receipt.get("callId"), "finalPath": path,
                                       "reason": "placed-body receipt lacks exact target/placement/binding association"})
            else:
                binding_match = re.fullmatch(r"runtimeProgram\.bindings\[(\d+)\]\.usePolicy\.action\.kind", authored_paths[3]) if len(authored_paths) == 6 else None
                expected_inputs = [pattern.replace("[]", f"[{match.group(1) if i < 3 and match else binding_match.group(1) if binding_match else '?'}]")
                                   for i, pattern in enumerate(CAPABILITY_REGISTRY[fn].technical_lowering_inputs)]
                if not match or not binding_match or list(authored_paths) != expected_inputs:
                    violations.append({"fn": fn, "finalPath": path, "reason": "placed-body association receipt missing exact declared source paths"})
            continue
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
            is_omission = receipt.get("status") == "declared_neutral_omission"
            if match is not None and receipt.get("status") != "delivered" and not is_omission and not (
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
                expected_paths = _parameter_outputs(fn, param)
                if not expected_paths or not any(path_matches(candidate, path) for candidate in expected_paths):
                    violations.append({
                        "callId": str(receipt.get("callId") or ""),
                        "fn": fn,
                        "authoredPath": authored_path,
                        "finalPath": path,
                        "expectedPaths": list(expected_paths),
                        "reason": "wrong capability output for authored parameter",
                    })
            if match is not None and cap is not None and match.group(2) in cap.params and is_omission:
                name = match.group(2)
                spec = cap.params[name]
                if (spec.required or spec.default is None
                    or type(spec.default) is not type(spec.neutral)
                    or spec.default != spec.neutral
                    or type(receipt.get("value")) is not type(spec.to_wire(spec.default))
                    or receipt.get("value") != spec.to_wire(spec.default)):
                    violations.append({
                        "callId": str(receipt.get("callId") or ""), "fn": fn,
                        "authoredPath": authored_path, "finalPath": path,
                        "reason": "omission receipt lacks an exact declared neutral default/projection",
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
                    or not isinstance(source_params, Mapping)):
                    violations.append({
                        "callId": str(receipt.get("callId") or ""),
                        "fn": fn,
                        "authoredPath": authored_path,
                        "finalPath": path,
                        "reason": "authored parameter absent from originating call",
                    })
                elif is_omission:
                    if match.group(2) in source_params:
                        violations.append({
                            "callId": str(receipt.get("callId") or ""), "fn": fn,
                            "authoredPath": authored_path, "finalPath": path,
                            "reason": "omission receipt points to an explicitly authored parameter",
                        })
                elif match.group(2) not in source_params:
                    violations.append({
                        "callId": str(receipt.get("callId") or ""), "fn": fn,
                        "authoredPath": authored_path, "finalPath": path,
                        "reason": "authored parameter absent from originating call",
                    })
                elif not _same_receipt_value(receipt.get("value"), cap.params[match.group(2)].to_wire(source_params[match.group(2)])):
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
    # Require the existing primary receipts, never synthesize new provenance.
    # Source and wire indices are separate: bindings may be sorted during compile.
    if authored_document is not None:
        if _final_value(authored_document, PRIMARY_ENTITY_AUTHOR_PATH) is not _MISSING:
            matching = [r for r in receipt_rows if r.get("lowererId") == PRIMARY_OWNER_LOWERER_ID]
            if len(matching) != 1:
                violations.append({"lowererId": PRIMARY_OWNER_LOWERER_ID, "finalPath": PRIMARY_OWNER_FINAL_PATH,
                                   "reason": "global projection has no unique compiler receipt"})
        bindings = _final_value(authored_document, "runtimeProgram.bindings")
        for bi, _ in enumerate(bindings if isinstance(bindings, list) else []):
            source_path = f"runtimeProgram.bindings[{bi}].usePolicy.action.targetId"
            matching = [r for r in receipt_rows if r.get("lowererId") == PRIMARY_BINDING_ROLE_LOWERER_ID
                        and r.get("authoredPaths") == [PRIMARY_ENTITY_AUTHOR_PATH, source_path]]
            if len(matching) != 1:
                violations.append({"lowererId": PRIMARY_BINDING_ROLE_LOWERER_ID, "authoredPath": source_path,
                                   "reason": "global projection has no unique compiler receipt"})
            chance_path = f"runtimeProgram.bindings[{bi}].usePolicy.stackConsumeChancePercent"
            if _final_value(authored_document, chance_path) is not _MISSING:
                matching = [r for r in receipt_rows if r.get("lowererId") == STACK_CHANCE_LOWERER_ID
                            and r.get("authoredPaths") == [f"runtimeProgram.bindings[{bi}].id", chance_path]]
                if len(matching) != 1:
                    violations.append({"lowererId": STACK_CHANCE_LOWERER_ID, "authoredPath": chance_path,
                                       "reason": "global projection has no unique compiler receipt"})
        entities = _final_value(authored_document, "runtimeProgram.entities")
        for ei, _ in enumerate(entities if isinstance(entities, list) else []):
            source_path = f"runtimeProgram.entities[{ei}].kind"
            for output in declared_global_outputs_for("entity_kind_to_visual_role"):
                matching = [r for r in receipt_rows if r.get("lowererId") == "entity_kind_to_visual_role"
                            and r.get("authoredPaths") == [source_path] and path_matches(output, r["finalPath"])]
                if len(matching) != 1:
                    violations.append({"lowererId": "entity_kind_to_visual_role", "authoredPath": source_path,
                                       "reason": "global projection has no unique compiler receipt"})
    if final_document is not None:
        expected_globals = []
        if _final_value(final_document, PRIMARY_OWNER_FINAL_PATH) is not _MISSING:
            expected_globals.append((PRIMARY_OWNER_LOWERER_ID, PRIMARY_OWNER_FINAL_PATH))
        bindings = _final_value(final_document, "runtimeProgram.bindings")
        expected_globals.extend((PRIMARY_BINDING_ROLE_LOWERER_ID, f"runtimeProgram.bindings[{bi}].role")
                                for bi, _ in enumerate(bindings if isinstance(bindings, list) else []))
        expected_globals.extend((STACK_CHANCE_LOWERER_ID, f"runtimeProgram.bindings[{bi}].usePolicy.stackConsumeChancePercent")
                                for bi, binding in enumerate(bindings if isinstance(bindings, list) else [])
                                if isinstance(binding, Mapping) and isinstance(binding.get("usePolicy"), Mapping)
                                and "stackConsumeChancePercent" in binding["usePolicy"])
        entities = _final_value(final_document, "runtimeProgram.entities")
        # Isolated capability projectors can supply partial entity DTOs without
        # global fields; require coverage for each actual global output slot.
        expected_globals.extend(("entity_kind_to_visual_role", output.replace("[]", f"[{ei}]"))
                                for ei, _ in enumerate(entities if isinstance(entities, list) else [])
                                for output in declared_global_outputs_for("entity_kind_to_visual_role")
                                if _final_value(final_document, output.replace("[]", f"[{ei}]")) is not _MISSING)
        for lowerer_id, path in expected_globals:
            matching = [r for r in receipt_rows if r.get("lowererId") == lowerer_id and r.get("finalPath") == path]
            if len(matching) != 1:
                violations.append({"lowererId": lowerer_id, "finalPath": path,
                                   "reason": "global projection has no unique compiler receipt"})
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
        for index, source_call in enumerate(source_calls):
            if not isinstance(source_call, Mapping):
                continue
            fn = str(source_call.get("fn") or "")
            params = source_call.get("params")
            if not isinstance(params, Mapping):
                continue
            for name in declared_neutral_omissions(fn, params):
                source_path = f"runtimeProgram.calls[{index}].params.{name}"
                for expected in _parameter_outputs(fn, name):
                    matching = [row for row in receipt_rows
                                if row.get("fn") == fn and row.get("callId") == source_call.get("id")
                                and row.get("authoredPath") == source_path
                                and path_matches(expected, str(row.get("finalPath") or ""))
                                and row.get("status") == "declared_neutral_omission"]
                    if len(matching) != 1:
                        violations.append({
                            "callId": str(source_call.get("id") or ""), "fn": fn,
                            "authoredPath": source_path, "finalPath": expected,
                            "reason": "declared neutral omission has no unique omission receipt",
                        })
    if final_document is not None:
        # Presence is an explicit root-PNG source selection. With provenance
        # supplied, every body requires one exact association and each transform
        # requires its own unique receipt from that association's source call.
        runtime = final_document.get("runtimeProgram", {})
        bindings = runtime.get("bindings", []) if isinstance(runtime, Mapping) else []
        for bi, binding in enumerate(bindings):
            policy = binding.get("usePolicy", {}) if isinstance(binding, Mapping) else {}
            action = policy.get("action", {}) if isinstance(policy, Mapping) else {}
            placement = action.get("placement", {}) if isinstance(action, Mapping) else {}
            if not isinstance(placement, Mapping) or "placedBody" not in placement:
                continue
            base = f"runtimeProgram.bindings[{bi}].usePolicy.action.placement.placedBody"
            associations = [r for r in receipt_rows if r.get("fn") == "present_placed_item_sprite"
                            and r.get("finalPath") == base and r.get("status") == "technical_projection"
                            and str(r.get("authoredPath") or "").endswith(".params.placementCallId")]
            if len(associations) != 1:
                violations.append({"finalPath": base, "reason": "placed body has no unique association receipt"})
                continue
            association = associations[0]
            source_base = association["authoredPath"].rsplit(".", 1)[0]
            for name in CAPABILITY_REGISTRY["present_placed_item_sprite"].params:
                if name == "placementCallId":
                    continue
                matching = [r for r in receipt_rows if r.get("fn") == "present_placed_item_sprite"
                            and r.get("callId") == association.get("callId")
                            and r.get("authoredPath") == f"{source_base}.{name}"
                            and r.get("finalPath") == f"{base}.{name}" and r.get("status") == "delivered"]
                if len(matching) != 1:
                    violations.append({"finalPath": f"{base}.{name}", "reason": "placed transform has no unique originating receipt"})
        # Wire-only auditing has no Author call list: require coverage of each
        # present declared default slot, but do not claim whether it was omitted.
        for fn, cap in CAPABILITY_REGISTRY.items():
            for name in declared_neutral_omissions(fn, {}):
                for expected in _parameter_outputs(fn, name):
                    if "[]" in expected or _final_value(final_document, expected) is _MISSING:
                        continue
                    matching = [row for row in receipt_rows
                                if row.get("fn") == fn and row.get("finalPath") == expected
                                and re.fullmatch(r"runtimeProgram\.calls\[\d+\]\.params\." + re.escape(name),
                                                 str(row.get("authoredPath") or ""))]
                    if len(matching) != 1:
                        violations.append({
                            "fn": fn, "finalPath": expected,
                            "reason": "declared neutral wire slot has no unique parameter receipt",
                        })
    return {
        "schema": "infini.technical-lowering-audit.v1",
        "ok": not violations,
        "violations": violations,
        "lowerers": [row for row in GLOBAL_TECHNICAL_LOWERINGS
                     if row["id"] != STACK_CHANCE_LOWERER_ID
                     or any(receipt.get("lowererId") == STACK_CHANCE_LOWERER_ID for receipt in receipt_rows)],
        # Keep source-backed compiler serialization unchanged. Only standalone
        # audits need an explicit limit on what their successful check proves.
        **({"authoredSourceChecked": False} if authored_document is None else {}),
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
            **({"technicalProjectionInputs": list(cap.technical_lowering_inputs)} if cap.technical_lowering_inputs else {}),
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
