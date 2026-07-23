from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from typing import Any

from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring.engine_call_contracts import engine_params_model
from infini_local.core.runtime_authoring.reports import compiled_fields_for_authored_call
from infini_local.core.runtime_authoring.schema import (
    repair_param_allowed_combinations,
    repair_param_dependency_groups,
)
from infini_local.pipelines.author_item_contract import (
    author_item_targeted_repair_delta_schema,
)


def _call_id_text(value: Any) -> str:
    """Preserve invalid scalar IDs so the targeted ID repair can own them."""
    return "" if value is None else str(value).strip()


def _failure_rejection_sources(failure_report: dict[str, Any]) -> list[Any]:
    """Collect validator diagnostics without treating receipts or source payloads as failures."""
    sources: list[Any] = []
    fallback_errors: list[Any] = []
    diagnostic_keys = {
        "blockingClaims",
        "errors",
        "errorDetails",
        "invalidTargets",
        "identityError",
        "authorRepairRejectedDomains",
        "authorRepairTargets",
    }

    def collect(value: Any) -> None:
        if isinstance(value, list):
            for child in value:
                collect(child)
            return
        if not isinstance(value, dict):
            return
        for key, child in value.items():
            if key == "error":
                if child not in (None, "", [], {}):
                    fallback_errors.append(child)
                continue
            if key in diagnostic_keys:
                if child not in (None, "", [], {}):
                    sources.append(child)
                continue
            if isinstance(child, (dict, list)):
                collect(child)

    collect(failure_report)
    if sources or fallback_errors:
        combined: list[Any] = []
        seen: set[str] = set()
        for value in [*sources, *fallback_errors]:
            key = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            combined.append(value)
        return combined
    if any(key in failure_report for key in ("kind", "status", "path", "callId")):
        return [failure_report]
    return []


def _repair_targets(failure_report: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract bounded structural evidence without interpreting authored prose."""
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(
        *,
        path: Any = "",
        call_id: Any = "",
        fn: Any = "",
        reason: Any = "",
        repair_param_names: Any = None,
        compiled_fields: Any = None,
        provenance: dict[str, Any] | None = None,
    ) -> None:
        row: dict[str, Any] = {
            "path": str(path or "").strip(),
            "callId": str(call_id or "").strip(),
            "fn": str(fn or "").strip(),
            "reason": str(reason or "").strip(),
        }
        provenance_keys = (
            "kind",
            "expectedResultKind", "parentStrongRole",
            "authoredParam", "authoredValue", "compiledField", "compiledValue",
            "finalPath", "finalActual",
        )
        for key in provenance_keys:
            if isinstance(provenance, dict) and key in provenance:
                value = provenance[key]
                if isinstance(value, (str, bool, int, float)) or value is None:
                    row[key] = value
        if isinstance(provenance, dict) and isinstance(provenance.get("placeableParents"), list):
            row["placeableParents"] = copy.deepcopy(provenance["placeableParents"][:4])
        if isinstance(provenance, dict) and isinstance(provenance.get("expectedArmorSlots"), list):
            row["expectedArmorSlots"] = copy.deepcopy(provenance["expectedArmorSlots"][:3])
        if isinstance(provenance, dict) and isinstance(provenance.get("repairParamConstraints"), dict):
            row["repairParamConstraints"] = copy.deepcopy(provenance["repairParamConstraints"])
        for key, candidate in (
            ("repairParamNames", repair_param_names),
            ("compiledFields", compiled_fields),
        ):
            if isinstance(candidate, list):
                values = [str(value).strip() for value in candidate if str(value).strip()]
                if values:
                    row[key] = list(dict.fromkeys(values))
        if not any(row.values()):
            return
        key = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        if key not in seen and len(targets) < 24:
            seen.add(key)
            targets.append({
                field: value
                for field, value in row.items()
                if value or field in provenance_keys or field == "placeableParents"
            })

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for child in value:
                visit(child)
            return
        if isinstance(value, str):
            indexed = re.search(
                r"engineCalls(?:\[(\d+)\]|\.(\d+))(?:\.([A-Za-z0-9_.-]+))?",
                value,
            )
            if indexed is not None:
                index = int(indexed.group(1) or indexed.group(2))
                field = str(indexed.group(3) or "").strip(".")
                path = f"$.runtimePlan.engineCalls[{index}]"
                if field:
                    path += "." + field
                add(path=path, reason=value)
            return
        if not isinstance(value, dict):
            return
        add(
            path=value.get("path") or value.get("source") or value.get("field"),
            call_id=value.get("callId"),
            fn=value.get("fn"),
            reason=(
                value.get("reason")
                or value.get("message")
                or value.get("error")
                or value.get("kind")
                or value.get("status")
            ),
            repair_param_names=value.get("repairParamNames"),
            compiled_fields=value.get("compiledFields"),
            provenance=value,
        )
        for child in value.values():
            if isinstance(child, (dict, list)):
                visit(child)

    rejection_sources = _failure_rejection_sources(failure_report)
    if rejection_sources:
        for source in rejection_sources:
            visit(source)
    else:
        visit({
            key: value
            for key, value in failure_report.items()
            if key not in {"finalWireReceipts", "contract"}
        })
    if not targets:
        add(path="$", reason=failure_report.get("error") or failure_report.get("stage") or "validation_rejected")
    return targets


def _target_exact_param_delete_path(target: dict[str, Any]) -> str:
    authored_param = str(target.get("authoredParam") or "").strip()
    evidence = " ".join(
        str(target.get(key) or "")
        for key in ("reason", "kind", "status")
    ).lower()
    if authored_param and (
        "compiler_provenance_dropped" in evidence
        or str(target.get("status") or "").lower() == "dropped"
    ):
        return authored_param
    if (
        str(target.get("kind") or "").lower() == "additional_property"
        or "extra inputs are not permitted" in evidence
    ):
        match = re.search(
            r"\.runtimePlan\.engineCalls\[\d+\]\.params\.([A-Za-z0-9_.-]+)$",
            str(target.get("path") or ""),
        )
        if match:
            return str(match.group(1))
    return ""


def _target_is_exact_param_delete(target: dict[str, Any]) -> bool:
    return bool(_target_exact_param_delete_path(target))


def _invalid_call_identity_ids(invalid_targets: list[dict[str, Any]]) -> set[str]:
    """Return calls whose receipt ownership is blocked by an invalid callId."""
    invalid: set[str] = set()
    for target in invalid_targets:
        call_id = _call_id_text(target.get("callId"))
        if not call_id:
            continue
        kind = str(target.get("kind") or "").strip().lower()
        reason = str(target.get("reason") or "").strip().lower()
        path = str(target.get("path") or "").strip()
        if (
            kind == "invalid_or_missing_call_id"
            or "invalid_or_missing_call_id" in reason
            or (path.endswith(".callId") and kind in {"pattern", "required"})
        ):
            invalid.add(call_id)
    return invalid


def _is_secondary_missing_receipt(
    target: dict[str, Any],
    invalid_call_ids: set[str],
) -> bool:
    call_id = _call_id_text(target.get("callId"))
    evidence = " ".join(
        str(target.get(key) or "")
        for key in ("kind", "reason", "status")
    ).lower()
    return bool(
        call_id in invalid_call_ids
        and "compiler_provenance_receipt_missing" in evidence
    )


def _targeted_repair_param_paths(
    current_plan: dict[str, Any],
    invalid_targets: list[dict[str, Any]],
) -> dict[str, set[str]]:
    """Map typed rejection evidence to exact authored parameter leaf paths."""
    calls_candidate = current_plan.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    by_id: dict[str, dict[str, Any]] = {
        _call_id_text(call.get("callId")): call
        for call in calls
        if isinstance(call, dict) and _call_id_text(call.get("callId"))
    }
    paths_by_call: dict[str, set[str]] = {}
    deleted_paths_by_call: dict[str, set[str]] = {}
    invalid_call_ids = _invalid_call_identity_ids(invalid_targets)
    for target in invalid_targets:
        if _is_secondary_missing_receipt(target, invalid_call_ids):
            continue
        if _target_is_exact_param_delete(target):
            delete_call_id = _call_id_text(target.get("callId"))
            delete_path = _target_exact_param_delete_path(target)
            if delete_call_id and delete_path:
                deleted_paths_by_call.setdefault(delete_call_id, set()).add(delete_path)
            continue
        call_id = _call_id_text(target.get("callId"))
        call = by_id.get(call_id)
        if call is None:
            continue
        selected = paths_by_call.setdefault(call_id, set())
        for name in target.get("repairParamNames") or []:
            path = str(name).strip()
            if path:
                selected.add(path)
        authored_param = str(target.get("authoredParam") or "").strip()
        if authored_param:
            selected.add(authored_param)
        target_path = str(target.get("path") or "")
        path_match = re.search(r"\.params\.([A-Za-z0-9_.-]+)$", target_path)
        if path_match:
            parts = [part for part in path_match.group(1).split(".") if part]
            while parts and parts[-1] in _SCHEMA_UNION_BRANCH_SUFFIXES:
                parts.pop()
            if parts:
                selected.add(".".join(parts))
        rejected_compiled = {
            str(field).strip()
            for field in target.get("compiledFields") or []
            if str(field).strip()
        }
        if rejected_compiled:
            params_candidate = call.get("params")
            params: dict[str, Any] = params_candidate if isinstance(params_candidate, dict) else {}
            fn = str(call.get("fn") or "").strip()
            for authored_name in params:
                compiled = compiled_fields_for_authored_call(fn, params, str(authored_name))
                if compiled.intersection(rejected_compiled):
                    selected.add(str(authored_name))
    for call_id, paths in paths_by_call.items():
        paths.difference_update(deleted_paths_by_call.get(call_id, set()))
        call = by_id.get(call_id)
        fn = str((call or {}).get("fn") or "").strip()
        for group in repair_param_dependency_groups(fn, paths):
            paths.update(group)
    return {call_id: paths for call_id, paths in paths_by_call.items() if paths}


_SCHEMA_UNION_BRANCH_SUFFIXES = frozenset({
    "bool", "float", "int", "integer", "number", "str", "string",
})


def _targeted_required_param_paths(
    current_plan: dict[str, Any],
    invalid_targets: list[dict[str, Any]],
) -> dict[str, set[str]]:
    """Return exact rejected leaves, excluding call-level repair alternatives."""
    calls_candidate = current_plan.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    by_id = {
        _call_id_text(call.get("callId")): call
        for call in calls
        if isinstance(call, dict) and _call_id_text(call.get("callId"))
    }
    required: dict[str, set[str]] = {}
    deleted_paths_by_call: dict[str, set[str]] = {}
    invalid_call_ids = _invalid_call_identity_ids(invalid_targets)
    for target in invalid_targets:
        if _is_secondary_missing_receipt(target, invalid_call_ids):
            continue
        if _target_is_exact_param_delete(target):
            delete_call_id = _call_id_text(target.get("callId"))
            delete_path = _target_exact_param_delete_path(target)
            if delete_call_id and delete_path:
                deleted_paths_by_call.setdefault(delete_call_id, set()).add(delete_path)
            continue
        call_id = _call_id_text(target.get("callId"))
        if call_id not in by_id:
            continue
        exact_paths: set[str] = set()
        authored_param = str(target.get("authoredParam") or "").strip()
        if authored_param:
            exact_paths.add(authored_param)
        target_path = str(target.get("path") or "")
        path_match = re.search(r"\.params\.([A-Za-z0-9_.-]+)$", target_path)
        if path_match:
            parts = [part for part in path_match.group(1).split(".") if part]
            while parts and parts[-1] in _SCHEMA_UNION_BRANCH_SUFFIXES:
                parts.pop()
            if parts:
                exact_paths.add(".".join(parts))
        if exact_paths:
            required.setdefault(call_id, set()).update(exact_paths)
        constraints = target.get("repairParamConstraints")
        if isinstance(constraints, dict):
            required.setdefault(call_id, set()).update(
                str(path).strip()
                for path in constraints
                if str(path).strip()
            )
    for call_id, paths in required.items():
        paths.difference_update(deleted_paths_by_call.get(call_id, set()))
        call = by_id[call_id]
        fn = str(call.get("fn") or "").strip()
        for group in repair_param_dependency_groups(fn, paths):
            paths.update(group)
    return {call_id: paths for call_id, paths in required.items() if paths}


def _targeted_param_delete_specs(
    current_plan: dict[str, Any],
    invalid_targets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    calls_candidate = current_plan.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    by_id = {
        _call_id_text(call.get("callId")): call
        for call in calls
        if isinstance(call, dict) and _call_id_text(call.get("callId"))
    }
    grouped: dict[str, set[str]] = {}
    for target in invalid_targets:
        if not _target_is_exact_param_delete(target):
            continue
        call_id = _call_id_text(target.get("callId"))
        authored_param = _target_exact_param_delete_path(target)
        call = by_id.get(call_id)
        params = call.get("params") if isinstance(call, dict) else None
        if not isinstance(params, dict) or not authored_param:
            continue
        current_path: Any = params
        for part in [part for part in str(authored_param).split(".") if part]:
            if not isinstance(current_path, dict) or part not in current_path:
                raise PlannerUnavailable(
                    f"targeted repair delta contains missing_engine_call_param_path:{authored_param}"
                )
            current_path = current_path[part]
        grouped.setdefault(call_id, set()).add(authored_param)
    return [
        {
            "callId": call_id,
            "fn": str(by_id[call_id].get("fn") or "").strip(),
            "paramPaths": sorted(paths),
        }
        for call_id, paths in sorted(grouped.items())
        if paths and str(by_id[call_id].get("fn") or "").strip()
    ]


def _resolve_indexed_target_call_owners(
    invalid_targets: list[dict[str, Any]],
    current_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    """Attach immutable authored call identity to strict-schema indexed paths."""
    calls_candidate = current_plan.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    resolved: list[dict[str, Any]] = []
    for raw_target in invalid_targets:
        target = copy.deepcopy(raw_target)
        match = re.search(
            r"\.runtimePlan\.engineCalls\[(\d+)\](?:\.|$)",
            str(target.get("path") or ""),
        )
        if match:
            index = int(match.group(1))
            call = calls[index] if 0 <= index < len(calls) else None
            if not isinstance(call, dict):
                raise PlannerUnavailable(
                    f"indexed_target_owner_unresolved:engineCalls[{index}]"
                )
            call_id = _call_id_text(call.get("callId"))
            fn = str(call.get("fn") or "").strip()
            call_id_target = str(target.get("path") or "").endswith(".callId")
            if (not call_id and not call_id_target) or not fn:
                raise PlannerUnavailable(
                    f"indexed_target_owner_unresolved:engineCalls[{index}]"
                )
            supplied_call_id = _call_id_text(target.get("callId"))
            supplied_fn = str(target.get("fn") or "").strip()
            if (
                supplied_call_id and supplied_call_id != call_id
            ) or (
                supplied_fn and supplied_fn != fn
            ):
                raise PlannerUnavailable(
                    "indexed_target_owner_mismatch:"
                    f"engineCalls[{index}]:{supplied_call_id or '-'}:{supplied_fn or '-'}"
                    f"!={call_id}:{fn}"
                )
            target["callId"] = call_id
            target["fn"] = fn
        resolved.append(target)
    return resolved


def _targeted_call_id_repair_specs(
    current_plan: dict[str, Any],
    invalid_targets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return exact structural ID leaves authorized by validator paths."""
    calls_candidate = current_plan.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    specs: list[dict[str, Any]] = []
    seen_indexes: set[int] = set()
    for target in invalid_targets:
        path = str(target.get("path") or "")
        match = re.search(r"\.runtimePlan\.engineCalls\[(\d+)\]\.callId$", path)
        if not match:
            continue
        index = int(match.group(1))
        if index in seen_indexes or not (0 <= index < len(calls)):
            continue
        call = calls[index]
        if not isinstance(call, dict):
            continue
        fn = str(call.get("fn") or "").strip()
        if not fn:
            continue
        specs.append({
            "callIndex": index,
            "currentCallId": _call_id_text(call.get("callId")),
            "fn": fn,
        })
        seen_indexes.add(index)
    return specs


def _resolve_local_schema_ref(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    current = copy.deepcopy(schema)
    seen: set[str] = set()
    while True:
        nullable = current.get("anyOf")
        if isinstance(nullable, list):
            object_candidates = [
                candidate
                for candidate in nullable
                if isinstance(candidate, dict) and candidate.get("type") != "null"
            ]
            if len(object_candidates) == 1:
                current = copy.deepcopy(object_candidates[0])
                continue
        ref = current.get("$ref")
        if not isinstance(ref, str):
            break
        if not ref.startswith("#/$defs/") or ref in seen:
            break
        seen.add(ref)
        name = ref.removeprefix("#/$defs/")
        definition = (root.get("$defs") or {}).get(name)
        if not isinstance(definition, dict):
            break
        current = copy.deepcopy(definition)
    return current


def _project_repair_leaf_schema(
    schema: dict[str, Any],
    leaf_paths: set[str],
    root: dict[str, Any],
    required_leaf_paths: set[str] | None = None,
) -> dict[str, Any]:
    """Project an object schema to exact authorized leaves and inline local refs."""
    source = _resolve_local_schema_ref(schema, root)
    properties = source.get("properties")
    if not isinstance(properties, dict):
        return source
    grouped: dict[str, set[str]] = {}
    for path in leaf_paths:
        head, separator, tail = path.partition(".")
        if head:
            grouped.setdefault(head, set()).add(tail if separator else "")
    required_grouped: dict[str, set[str]] = {}
    for path in required_leaf_paths or set():
        head, separator, tail = path.partition(".")
        if head:
            required_grouped.setdefault(head, set()).add(tail if separator else "")
    projected: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {},
        "required": [],
    }
    for name, tails in grouped.items():
        property_schema = properties.get(name)
        if not isinstance(property_schema, dict):
            continue
        resolved_property = _resolve_local_schema_ref(property_schema, root)
        nested_tails = {tail for tail in tails if tail}
        required_tails = {
            tail for tail in required_grouped.get(name, set()) if tail
        }
        if name in required_grouped:
            projected["required"].append(name)
        if nested_tails:
            projected["properties"][name] = _project_repair_leaf_schema(
                resolved_property,
                nested_tails,
                root,
                required_tails,
            )
        else:
            # An authorized path may name the complete object leaf (for example
            # armor_effect.setBonus). Keep that typed object boundary intact;
            # dropping object-valued leaves made the dossier require a field that
            # the provider response schema did not permit the model to return.
            projected["properties"][name] = resolved_property
    return projected


def _provenance_repair_values_by_call(
    invalid_targets: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for target in invalid_targets:
        evidence = " ".join(
            str(target.get(key) or "")
            for key in ("reason", "kind", "status")
        ).lower()
        if "compiler_provenance_mismatched" not in evidence:
            continue
        call_id = _call_id_text(target.get("callId"))
        authored_param = str(target.get("authoredParam") or "").strip()
        if not call_id or not authored_param or "compiledValue" not in target:
            continue
        compiled_value = target.get("compiledValue")
        if compiled_value is None:
            continue
        values.setdefault(call_id, {})[authored_param] = copy.deepcopy(compiled_value)
    return values


def _set_projected_leaf_const(
    projected_schema: dict[str, Any],
    path: str,
    value: Any,
) -> None:
    current = projected_schema
    parts = [part for part in str(path).split(".") if part]
    for index, part in enumerate(parts):
        properties = current.get("properties")
        if not isinstance(properties, dict) or part not in properties:
            return
        if index == len(parts) - 1:
            properties[part] = {"const": copy.deepcopy(value)}
            return
        child = properties.get(part)
        if not isinstance(child, dict):
            return
        current = child


def _set_projected_leaf_constraints(
    projected_schema: dict[str, Any],
    path: str,
    constraints: dict[str, Any],
) -> None:
    current = projected_schema
    parts = [part for part in str(path).split(".") if part]
    for index, part in enumerate(parts):
        properties = current.get("properties")
        if not isinstance(properties, dict) or part not in properties:
            return
        child = properties.get(part)
        if not isinstance(child, dict):
            return
        if index != len(parts) - 1:
            current = child
            continue
        candidates = [child]
        candidates.extend(
            branch
            for branch in child.get("anyOf") or []
            if isinstance(branch, dict)
        )
        for candidate in candidates:
            if candidate.get("type") not in {"integer", "number"}:
                continue
            minimum = constraints.get("minimum")
            maximum = constraints.get("maximum")
            if isinstance(minimum, (int, float)):
                candidate["minimum"] = max(minimum, candidate.get("minimum", minimum))
            if isinstance(maximum, (int, float)):
                candidate["maximum"] = min(maximum, candidate.get("maximum", maximum))
        return


def _repair_param_constraints_by_call(
    invalid_targets: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for target in invalid_targets:
        call_id = _call_id_text(target.get("callId"))
        constraints = target.get("repairParamConstraints")
        if not call_id or not isinstance(constraints, dict):
            continue
        for path, bounds in constraints.items():
            if isinstance(bounds, dict) and str(path).strip():
                grouped.setdefault(call_id, {})[str(path).strip()] = copy.deepcopy(bounds)
    return grouped


def _targeted_repair_function_cards(
    current_plan: dict[str, Any],
    invalid_targets: list[dict[str, Any]],
    engine_card: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose only rejected owners with source-derived schemas for exact leaf paths."""
    calls_candidate = current_plan.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    paths_by_call = _targeted_repair_param_paths(current_plan, invalid_targets)
    required_paths_by_call = _targeted_required_param_paths(current_plan, invalid_targets)
    required_values_by_call = _provenance_repair_values_by_call(invalid_targets)
    constraints_by_call = _repair_param_constraints_by_call(invalid_targets)
    selected_calls = [
        call
        for call in calls
        if isinstance(call, dict)
        and _call_id_text(call.get("callId")) in paths_by_call
    ]
    cards: dict[str, Any] = {}
    for call in selected_calls:
        call_id = _call_id_text(call.get("callId"))
        fn = str(call.get("fn") or "").strip()
        leaf_paths = paths_by_call[call_id]
        card_candidate = engine_card.get(fn)
        if not isinstance(card_candidate, dict):
            continue
        card = copy.deepcopy(card_candidate)
        params_schema = engine_params_model(fn).model_json_schema()
        required_param_paths = required_paths_by_call.get(call_id, set())
        projected = _project_repair_leaf_schema(
            params_schema,
            leaf_paths,
            params_schema,
            required_param_paths,
        )
        required_values = required_values_by_call.get(call_id, {})
        for path, value in required_values.items():
            _set_projected_leaf_const(projected, path, value)
        repair_constraints = constraints_by_call.get(call_id, {})
        for path, constraints in repair_constraints.items():
            _set_projected_leaf_constraints(projected, path, constraints)
        projected_params = projected.get("properties")
        if not isinstance(projected_params, dict) or not projected_params:
            continue
        card["callId"] = call_id
        card["fn"] = fn
        card["params"] = projected_params
        if required_param_paths:
            card["requiredParamPaths"] = sorted(required_param_paths)
            card["requiredParams"] = sorted(
                {path.split(".", 1)[0] for path in required_param_paths}
            )
        if required_values:
            card["requiredValues"] = copy.deepcopy(required_values)
        if repair_constraints:
            card["repairParamConstraints"] = copy.deepcopy(repair_constraints)
        dependency_groups = repair_param_dependency_groups(fn, leaf_paths)
        if dependency_groups:
            card["requiredTogether"] = [
                sorted(group)
                for group in dependency_groups
            ]
            allowed_together_values = [
                values
                for group in dependency_groups
                for values in repair_param_allowed_combinations(
                    fn,
                    group,
                    call.get("params") if isinstance(call.get("params"), dict) else {},
                    result_kind=str(current_plan.get("resultKind") or ""),
                )
            ]
            if allowed_together_values:
                card["allowedTogetherValues"] = allowed_together_values
        cards[call_id] = card
    return cards


def _targeted_visual_intent_paths(invalid_targets: list[dict[str, Any]]) -> set[str]:
    paths: set[str] = set()
    for target in invalid_targets:
        target_path = str(target.get("path") or "")
        match = re.search(r"\.visualIntent\.([A-Za-z0-9_.-]+)$", target_path)
        if match:
            paths.add(str(match.group(1)))
        for name in target.get("repairParamNames") or []:
            value = str(name).strip()
            if value.startswith("visualIntent."):
                paths.add(value.removeprefix("visualIntent."))
    return paths


def _targeted_author_object_paths(
    invalid_targets: list[dict[str, Any]],
    field: str,
) -> set[str]:
    paths: set[str] = set()
    marker = f".{field}"
    prefix = f"{field}."
    for target in invalid_targets:
        target_path = str(target.get("path") or "")
        if target_path.endswith(marker):
            paths.add("*")
        match = re.search(
            rf"\.{re.escape(field)}\.([A-Za-z0-9_.-]+)$",
            target_path,
        )
        if match:
            paths.add(str(match.group(1)))
        for name in target.get("repairParamNames") or []:
            value = str(name).strip()
            if value.startswith(prefix):
                paths.add(value.removeprefix(prefix))
    return paths


def _targeted_required_author_object_paths(
    invalid_targets: list[dict[str, Any]],
    field: str,
) -> set[str]:
    required_targets = [
        target
        for target in invalid_targets
        if str(target.get("kind") or "").strip().lower() == "required"
        or str(target.get("reason") or "").strip().lower() == "required"
    ]
    return _targeted_author_object_paths(required_targets, field)


def _targeted_runtime_metadata_fields(invalid_targets: list[dict[str, Any]]) -> set[str]:
    allowed_fields = {
        "runtimeStateIntent", "sourceReading", "balanceIntent", "anomalyFlags",
    }
    authorized: set[str] = set()
    for target in invalid_targets:
        candidates = [str(target.get("path") or "")]
        candidates.extend(str(value) for value in (target.get("repairParamNames") or []))
        for candidate in candidates:
            segments = [segment for segment in re.split(r"[^A-Za-z0-9_]+", candidate) if segment]
            authorized.update(field for field in allowed_fields if field in segments)
    return authorized


def _targeted_identity_fields(invalid_targets: list[dict[str, Any]]) -> set[str]:
    authorized: set[str] = set()
    for target in invalid_targets:
        target_path = str(target.get("path") or "").strip()
        if target_path == "$.category":
            authorized.add("category")
        if target_path == "$.runtimePlan.resultKind":
            authorized.add("resultKind")
        for raw_name in target.get("repairParamNames") or []:
            name = str(raw_name).strip()
            if name == "category":
                authorized.add("category")
            if name in {"resultKind", "runtimePlan.resultKind"}:
                authorized.add("resultKind")
    return authorized


def _targeted_provider_delta_scope(
    current_item: dict[str, Any],
    invalid_targets: list[dict[str, Any]],
    allowed_patch_keys: list[str],
) -> tuple[dict[str, dict[str, Any]], set[str], dict[str, dict[str, Any]]]:
    """Project provider grammar from the exact targets used by the applicator."""
    base = author_item_targeted_repair_delta_schema()
    properties = base["properties"]
    author_properties = properties["authorFields"]["properties"]
    allowed_keys = set(allowed_patch_keys)
    author_schemas: dict[str, dict[str, Any]] = {}
    for field in sorted(allowed_keys.intersection(author_properties)):
        field_schema = author_properties[field]
        if field == "visualIntent":
            leaf_paths = _targeted_visual_intent_paths(invalid_targets)
            required_paths = _targeted_required_author_object_paths(
                invalid_targets,
                "visualIntent",
            )
            projected = _project_repair_leaf_schema(
                field_schema,
                leaf_paths,
                base,
                required_paths,
            )
            if projected.get("properties"):
                author_schemas[field] = projected
            continue
        if field == "sourceRolePreservation":
            leaf_paths = _targeted_author_object_paths(
                invalid_targets,
                "sourceRolePreservation",
            )
            if "*" in leaf_paths:
                author_schemas[field] = copy.deepcopy(field_schema)
                continue
            required_paths = _targeted_required_author_object_paths(
                invalid_targets,
                "sourceRolePreservation",
            )
            projected = _project_repair_leaf_schema(
                field_schema,
                leaf_paths,
                base,
                required_paths,
            )
            if projected.get("properties"):
                author_schemas[field] = projected
            continue
        author_schemas[field] = copy.deepcopy(field_schema)

    metadata_fields = (
        _targeted_runtime_metadata_fields(invalid_targets)
        if "runtimePlan" in allowed_keys
        else set()
    )

    identity_fields = _targeted_identity_fields(invalid_targets)
    identity_schemas: dict[str, dict[str, Any]] = {}
    if identity_fields:
        identity_properties = properties["identity"]["properties"]
        current_plan_candidate = current_item.get("runtimePlan")
        current_plan: dict[str, Any] = (
            current_plan_candidate if isinstance(current_plan_candidate, dict) else {}
        )
        current_values = {
            "category": str(current_item.get("category") or "").strip(),
            "resultKind": str(current_plan.get("resultKind") or "").strip(),
        }
        for field in ("category", "resultKind"):
            field_schema = copy.deepcopy(identity_properties[field])
            if field not in identity_fields:
                field_schema["const"] = current_values[field]
            identity_schemas[field] = field_schema
    return author_schemas, metadata_fields, identity_schemas


def _failure_mentions(failure_report: dict[str, Any], *markers: str) -> bool:
    """Classify finite validator reasons, not item names or gameplay prose."""
    marker_set = {marker.lower() for marker in markers}

    def visit(value: Any) -> bool:
        if isinstance(value, dict):
            return any(visit(child) for child in value.values())
        if isinstance(value, list):
            return any(visit(child) for child in value)
        text = str(value or "").strip().lower()
        return any(marker in text for marker in marker_set)

    return any(visit(source) for source in _failure_rejection_sources(failure_report))


def _rejected_call_ids(
    failure_report: dict[str, Any],
    current_plan: dict[str, Any],
) -> set[str]:
    calls_candidate = current_plan.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    rejected: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if str(value.get("path") or "").strip() == "$.runtimePlan.engineCalls":
                rejected.update(
                    _call_id_text(call.get("callId"))
                    for call in calls
                    if isinstance(call, dict) and _call_id_text(call.get("callId"))
                )
            call_id = _call_id_text(value.get("callId"))
            if call_id:
                rejected.add(call_id)
            for child in value.values():
                visit(child)
            return
        if isinstance(value, list):
            for child in value:
                visit(child)
            return
        text_value = str(value or "")
        indexed = re.search(r"engineCalls(?:\[(\d+)\]|\.(\d+))(?:\.|\]|$)", text_value)
        if indexed is None:
            return
        index = int(indexed.group(1) or indexed.group(2))
        if 0 <= index < len(calls) and isinstance(calls[index], dict):
            call_id = _call_id_text(calls[index].get("callId"))
            if call_id:
                rejected.add(call_id)

    rejection_sources = _failure_rejection_sources(failure_report)
    if rejection_sources:
        for source in rejection_sources:
            visit(source)
    else:
        visit({
            key: value
            for key, value in failure_report.items()
            if key not in {"finalWireReceipts", "contract"}
        })
    return rejected


def _whole_engine_call_domain_rejected(failure_report: dict[str, Any]) -> bool:
    found = False

    def visit(value: Any) -> None:
        nonlocal found
        if found:
            return
        if isinstance(value, dict):
            if str(value.get("path") or "").strip() == "$.runtimePlan.engineCalls":
                found = True
                return
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for source in _failure_rejection_sources(failure_report):
        visit(source)
    return found


def _repair_allowed_patch_keys(failure_report: dict[str, Any], targeted: bool) -> list[str]:
    gameplay_keys = [
        "runtimePlan", "coreMechanic", "primaryVerb", "controlStyle", "playerViewTimeline",
    ]
    keys: list[str] = [] if targeted else ["category", *gameplay_keys]
    target_text = " ".join(
        " ".join(
            str(target.get(field) or "").casefold()
            for field in ("path", "reason", "callId", "fn", "kind")
        )
        for target in _repair_targets(failure_report)
    )
    if (
        any(_call_id_text(target.get("callId")) for target in _repair_targets(failure_report))
        and "runtimePlan" not in keys
    ):
        keys.append("runtimePlan")
    mappings = (
        (("runtimeplan.enginecalls", "runtime_plan", "executor", "engine_call"), ["runtimePlan"]),
        (("$.name", "invalid_item_name", "invalid_identity"), ["name"]),
        (("$.category", "invalid_category", "resultkind"), ["category", "runtimePlan"]),
        (("concept.fantasy",), ["fantasy"]),
        (("concept.mergelogic",), ["mergeLogic"]),
        (("concept.coremechanic",), ["coreMechanic"]),
        (("runtimecontract.primaryverb",), ["primaryVerb"]),
        (("runtimecontract.controlstyle",), ["controlStyle"]),
        (("playerviewtimeline", "timeline_runtime_conflict"), ["playerViewTimeline"]),
        (("sourcerolepreservation",), ["sourceRolePreservation"]),
        (("visualintent",), ["visualIntent"]),
        (("runtimestateintent", "sourcereading", "balanceintent", "anomalyflags"), ["runtimePlan"]),
    )
    for markers, additions in mappings:
        if any(marker in target_text for marker in markers):
            for key in additions:
                if key not in keys:
                    keys.append(key)
    return keys or gameplay_keys


FULL_REDESIGN_REQUIRED_PATCH_KEYS = frozenset({
    "category", "coreMechanic", "primaryVerb", "controlStyle", "runtimePlan",
})


FULL_REDESIGN_REQUIRED_PLAN_KEYS = frozenset({
    "resultKind", "engineCalls", "runtimeStateIntent", "sourceReading",
    "balanceIntent", "anomalyFlags",
})
