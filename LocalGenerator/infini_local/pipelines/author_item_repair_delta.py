from __future__ import annotations

import copy
import re
from typing import Any

from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring.schema import (
    repair_param_dependency_groups,
    repair_param_group_values_allowed,
)
from infini_local.pipelines.author_item_repair_scope import (
    _failure_mentions,
    _rejected_call_ids,
    _repair_allowed_patch_keys,
    _repair_targets,
    _resolve_indexed_target_call_owners,
    _targeted_author_object_paths,
    _targeted_call_id_repair_specs,
    _targeted_identity_fields,
    _targeted_param_delete_specs,
    _targeted_repair_param_paths,
    _targeted_required_param_paths,
    _targeted_runtime_metadata_fields,
    _targeted_visual_intent_paths,
)


def _patch_leaf_paths(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        paths: list[str] = []
        for key, child in value.items():
            child_path = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(_patch_leaf_paths(child, child_path))
        return paths or ([prefix] if prefix else [])
    return [prefix] if prefix else []


def _path_prefixes(paths: set[str]) -> set[str]:
    prefixes: set[str] = set()
    for path in paths:
        parts = [part for part in str(path).split(".") if part]
        prefixes.update(".".join(parts[:index]) for index in range(1, len(parts) + 1))
    return prefixes


def _path_is_authorized(path: str, authorized: set[str]) -> bool:
    return "*" in authorized or any(
        path == allowed or path.startswith(allowed + ".")
        for allowed in authorized
    )


def _set_nested_param(target: dict[str, Any], path: str, value: Any) -> None:
    parts = [part for part in str(path).split(".") if part]
    if not parts:
        raise PlannerUnavailable("targeted repair delta contains empty_engine_call_param_path")
    cursor = target
    for part in parts[:-1]:
        child = cursor.get(part)
        if child is None:
            child = {}
            cursor[part] = child
        if not isinstance(child, dict):
            raise PlannerUnavailable(
                f"targeted repair delta cannot descend through non_object_param:{path}"
            )
        cursor = child
    cursor[parts[-1]] = copy.deepcopy(value)


def _get_nested_param(source: dict[str, Any], path: str) -> Any:
    current: Any = source
    for part in [part for part in str(path).split(".") if part]:
        if not isinstance(current, dict) or part not in current:
            raise PlannerUnavailable(
                f"targeted repair delta contains missing_engine_call_param_path:{path}"
            )
        current = current[part]
    return current


def _delete_nested_param(target: dict[str, Any], path: str) -> None:
    parts = [part for part in str(path).split(".") if part]
    if not parts:
        raise PlannerUnavailable("targeted repair delta contains empty_engine_call_param_delete")
    cursor: Any = target
    for part in parts[:-1]:
        if not isinstance(cursor, dict) or part not in cursor:
            raise PlannerUnavailable(
                f"targeted repair delta deletes missing_engine_call_param_path:{path}"
            )
        cursor = cursor[part]
    if not isinstance(cursor, dict) or parts[-1] not in cursor:
        raise PlannerUnavailable(
            f"targeted repair delta deletes missing_engine_call_param_path:{path}"
        )
    del cursor[parts[-1]]


def _apply_targeted_repair_delta(
    current_item: dict[str, Any],
    delta: dict[str, Any],
    failure_report: dict[str, Any],
) -> dict[str, Any]:
    """Apply sparse same-author leaf edits without whole-object merge semantics."""
    candidate = copy.deepcopy(current_item)
    plan_candidate = candidate.get("runtimePlan")
    plan: dict[str, Any] = plan_candidate if isinstance(plan_candidate, dict) else {}
    calls_candidate = plan.get("engineCalls")
    calls: list[dict[str, Any]] = (
        [call for call in calls_candidate if isinstance(call, dict)]
        if isinstance(calls_candidate, list)
        else []
    )
    plan["engineCalls"] = calls
    candidate["runtimePlan"] = plan

    invalid_targets = _resolve_indexed_target_call_owners(
        _repair_targets(failure_report),
        plan,
    )
    allowed_patch_keys = set(_repair_allowed_patch_keys(failure_report, True))
    rejected_call_ids = _rejected_call_ids(failure_report, plan) | {
        str(target.get("callId") or "").strip()
        for target in invalid_targets
        if str(target.get("callId") or "").strip()
    }
    authorized_param_paths = _targeted_repair_param_paths(plan, invalid_targets)
    required_param_paths = _targeted_required_param_paths(plan, invalid_targets)
    authorized_dependency_groups = {
        call_id: repair_param_dependency_groups(
            str((next(
                (call for call in calls if str(call.get("callId") or "").strip() == call_id),
                {},
            ) or {}).get("fn") or ""),
            paths,
        )
        for call_id, paths in authorized_param_paths.items()
    }
    authorized_visual_intent_paths = _targeted_visual_intent_paths(invalid_targets)
    authorized_source_role_paths = _targeted_author_object_paths(
        invalid_targets,
        "sourceRolePreservation",
    )
    authorized_runtime_metadata_fields = _targeted_runtime_metadata_fields(invalid_targets)
    authorized_identity_fields = _targeted_identity_fields(invalid_targets)
    authorized_call_id_repairs = {
        int(spec["callIndex"]): spec
        for spec in _targeted_call_id_repair_specs(plan, invalid_targets)
    }
    authorized_param_deletes = {
        str(spec["callId"]): spec
        for spec in _targeted_param_delete_specs(plan, invalid_targets)
    }

    allowed_delta_keys = {
        "identity", "authorFields", "runtimeMetadata", "engineCallParamPatches",
        "engineCallParamDeletes", "engineCallIdPatches",
    }
    unknown_delta_keys = sorted(set(delta) - allowed_delta_keys)
    if unknown_delta_keys:
        first = unknown_delta_keys[0]
        if first == "engineCallReplacements":
            raise PlannerUnavailable(
                "targeted repair delta contains out_of_scope_engine_call_replacement"
            )
        if first == "engineCallAdditions":
            raise PlannerUnavailable(
                "targeted repair delta contains out_of_scope_engine_call_addition"
            )
        if first == "engineCallRemovals":
            raise PlannerUnavailable(
                "targeted repair delta contains out_of_scope_engine_call_removal"
            )
        raise PlannerUnavailable(
            "targeted repair delta contains unknown_top_level_key:" + first
        )

    identity = delta.get("identity")
    if isinstance(identity, dict):
        category = str(identity.get("category") or "").strip()
        result_kind = str(identity.get("resultKind") or "").strip()
        current_category = str(candidate.get("category") or "").strip()
        current_result_kind = str(plan.get("resultKind") or "").strip()
        if category != current_category and "category" not in authorized_identity_fields:
            raise PlannerUnavailable("targeted repair delta contains out_of_scope_identity_category")
        if result_kind != current_result_kind and "resultKind" not in authorized_identity_fields:
            raise PlannerUnavailable("targeted repair delta contains out_of_scope_identity_result_kind")
        candidate["category"] = category
        plan["resultKind"] = result_kind

    author_fields = delta.get("authorFields")
    if isinstance(author_fields, dict):
        concept_candidate = candidate.setdefault("concept", {})
        concept: dict[str, Any] = concept_candidate if isinstance(concept_candidate, dict) else {}
        candidate["concept"] = concept
        contract_candidate = candidate.setdefault("runtimeContract", {})
        runtime_contract: dict[str, Any] = contract_candidate if isinstance(contract_candidate, dict) else {}
        candidate["runtimeContract"] = runtime_contract
        targets: dict[str, tuple[str, dict[str, Any]]] = {
            "name": ("name", candidate),
            "fantasy": ("fantasy", concept),
            "mergeLogic": ("mergeLogic", concept),
            "coreMechanic": ("coreMechanic", concept),
            "primaryVerb": ("primaryVerb", runtime_contract),
            "controlStyle": ("controlStyle", runtime_contract),
            "playerViewTimeline": ("playerViewTimeline", runtime_contract),
            "sourceRolePreservation": ("sourceRolePreservation", plan),
            "visualIntent": ("visualIntent", plan),
        }
        for field, value in author_fields.items():
            if field not in allowed_patch_keys:
                raise PlannerUnavailable(
                    f"targeted repair delta contains out_of_scope_author_field:{field}"
                )
            target_key, target = targets[field]
            if field == "visualIntent":
                if not isinstance(value, dict):
                    raise PlannerUnavailable(
                        "targeted repair delta visualIntent patch must be an object"
                    )
                patch_paths = set(_patch_leaf_paths(value))
                unauthorized = sorted(
                    patch_paths - authorized_visual_intent_paths
                )
                if unauthorized:
                    raise PlannerUnavailable(
                        "targeted repair delta contains out_of_scope_visual_intent_leaf:"
                        + ",".join(unauthorized)
                    )
                current_intent_candidate = target.get(target_key)
                current_intent: dict[str, Any] = copy.deepcopy(
                    current_intent_candidate
                ) if isinstance(current_intent_candidate, dict) else {}
                for path in sorted(patch_paths):
                    _set_nested_param(
                        current_intent,
                        path,
                        _get_nested_param(value, path),
                    )
                target[target_key] = current_intent
                continue
            if field == "sourceRolePreservation":
                if not isinstance(value, dict):
                    raise PlannerUnavailable(
                        "targeted repair delta sourceRolePreservation patch must be an object"
                    )
                patch_paths = set(_patch_leaf_paths(value))
                unauthorized = sorted(
                    patch_paths - authorized_source_role_paths
                    if "*" not in authorized_source_role_paths
                    else set()
                )
                if unauthorized:
                    raise PlannerUnavailable(
                        "targeted repair delta contains out_of_scope_author_field_leaf:"
                        + ",".join(unauthorized)
                    )
                current_roles_candidate = target.get(target_key)
                current_roles: dict[str, Any] = copy.deepcopy(
                    current_roles_candidate
                ) if isinstance(current_roles_candidate, dict) else {}
                for path in sorted(patch_paths):
                    _set_nested_param(
                        current_roles,
                        path,
                        _get_nested_param(value, path),
                    )
                target[target_key] = current_roles
                continue
            target[target_key] = copy.deepcopy(value)

    runtime_metadata = delta.get("runtimeMetadata")
    if isinstance(runtime_metadata, dict):
        if "runtimePlan" not in allowed_patch_keys:
            raise PlannerUnavailable("targeted repair delta contains out_of_scope_runtime_metadata")
        unauthorized_metadata = sorted(
            set(runtime_metadata) - authorized_runtime_metadata_fields
        )
        if unauthorized_metadata:
            raise PlannerUnavailable(
                "targeted repair delta contains out_of_scope_runtime_metadata_leaf:"
                + ",".join(unauthorized_metadata)
            )
        for field, value in runtime_metadata.items():
            plan[field] = copy.deepcopy(value)

    index_by_call_id = {
        str(call.get("callId") or "").strip(): index
        for index, call in enumerate(calls)
        if str(call.get("callId") or "").strip()
    }
    prepared_id_patches: list[tuple[int, str]] = []
    id_alias_to_current: dict[str, str] = {}
    seen_id_patch_indexes: set[int] = set()
    for id_patch in delta.get("engineCallIdPatches") or []:
        index = id_patch.get("callIndex") if isinstance(id_patch, dict) else None
        if not isinstance(index, int) or index not in authorized_call_id_repairs:
            raise PlannerUnavailable(
                f"targeted repair delta contains out_of_scope_engine_call_id_patch:{index}"
            )
        if index in seen_id_patch_indexes:
            raise PlannerUnavailable(f"targeted repair delta repeats callIndex:{index}")
        seen_id_patch_indexes.add(index)
        spec = authorized_call_id_repairs[index]
        current_call = calls[index]
        current_id = str(current_call.get("callId") or "").strip()
        current_fn = str(current_call.get("fn") or "").strip()
        patch_current_id = str(id_patch.get("currentCallId") or "").strip()
        patch_fn = str(id_patch.get("fn") or "").strip()
        if patch_fn != current_fn or patch_fn != str(spec.get("fn") or ""):
            raise PlannerUnavailable(
                f"targeted repair delta callId patch cannot change fn:{index}:{current_fn}->{patch_fn}"
            )
        if patch_current_id != current_id or patch_current_id != str(spec.get("currentCallId") or ""):
            raise PlannerUnavailable(
                f"targeted repair delta callId patch owner mismatch:{index}:{current_id}!={patch_current_id}"
            )
        new_call_id = str(id_patch.get("newCallId") or "").strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", new_call_id):
            raise PlannerUnavailable(
                f"targeted repair delta contains invalid newCallId:{new_call_id}"
            )
        if new_call_id in id_alias_to_current:
            raise PlannerUnavailable(
                f"targeted repair delta creates duplicate callId:{new_call_id}"
            )
        if any(
            other_index != index
            and str(other_call.get("callId") or "").strip() == new_call_id
            for other_index, other_call in enumerate(calls)
        ):
            raise PlannerUnavailable(
                f"targeted repair delta creates duplicate callId:{new_call_id}"
            )
        id_alias_to_current[new_call_id] = current_id
        prepared_id_patches.append((index, new_call_id))
    missing_id_patches = sorted(set(authorized_call_id_repairs) - seen_id_patch_indexes)
    if missing_id_patches:
        raise PlannerUnavailable(
            "targeted repair delta omits required_call_id_patch:"
            + ",".join(str(index) for index in missing_id_patches)
        )

    def current_mutation_call_id(raw_call_id: Any) -> str:
        submitted = str(raw_call_id or "").strip()
        return id_alias_to_current.get(submitted, submitted)

    seen_delete_call_ids: set[str] = set()
    for delete in delta.get("engineCallParamDeletes") or []:
        call_id = current_mutation_call_id(delete.get("callId"))
        if call_id in seen_delete_call_ids:
            raise PlannerUnavailable(f"targeted repair delta repeats param delete callId:{call_id}")
        seen_delete_call_ids.add(call_id)
        spec = authorized_param_deletes.get(call_id)
        index = index_by_call_id.get(call_id)
        if spec is None or index is None:
            raise PlannerUnavailable(
                f"targeted repair delta contains out_of_scope_engine_call_param_delete:{call_id}"
            )
        current_call = calls[index]
        current_fn = str(current_call.get("fn") or "").strip()
        delete_fn = str(delete.get("fn") or "").strip()
        if delete_fn != current_fn or delete_fn != str(spec.get("fn") or ""):
            raise PlannerUnavailable(
                f"targeted repair delta param delete cannot change fn:{call_id}:{current_fn}->{delete_fn}"
            )
        requested = [str(path).strip() for path in delete.get("paramPaths") or []]
        expected = {str(path).strip() for path in spec.get("paramPaths") or [] if str(path).strip()}
        if len(requested) != len(set(requested)) or set(requested) != expected:
            raise PlannerUnavailable(
                "targeted repair delta param delete must match exact rejected paths:"
                + call_id
                + ":"
                + ",".join(sorted(expected))
            )
        params_candidate = current_call.get("params")
        params = copy.deepcopy(params_candidate) if isinstance(params_candidate, dict) else {}
        for path in sorted(expected):
            _delete_nested_param(params, path)
        current_call["params"] = params

    seen_call_ids: set[str] = set()
    applied_param_paths: dict[str, set[str]] = {}
    for param_patch in delta.get("engineCallParamPatches") or []:
        call_id = current_mutation_call_id(param_patch.get("callId"))
        if call_id in seen_call_ids:
            raise PlannerUnavailable(f"targeted repair delta repeats callId:{call_id}")
        seen_call_ids.add(call_id)
        if call_id not in rejected_call_ids:
            raise PlannerUnavailable(
                f"targeted repair delta contains out_of_scope_engine_call_param_patch:{call_id}"
            )
        index = index_by_call_id.get(call_id)
        if index is None:
            raise PlannerUnavailable(f"targeted repair delta references unknown callId:{call_id}")
        current_call = calls[index]
        patch_fn = str(param_patch.get("fn") or "").strip()
        current_fn = str(current_call.get("fn") or "").strip()
        if patch_fn != current_fn:
            raise PlannerUnavailable(
                f"targeted repair delta params patch cannot change fn:{call_id}:{current_fn}->{patch_fn}"
            )
        params_candidate = current_call.get("params")
        params = copy.deepcopy(params_candidate) if isinstance(params_candidate, dict) else {}
        patch_params_candidate = param_patch.get("params")
        patch_params: dict[str, Any] = (
            patch_params_candidate if isinstance(patch_params_candidate, dict) else {}
        )
        patch_paths = set(_patch_leaf_paths(patch_params))
        patch_coverage_paths = _path_prefixes(patch_paths)
        applied_param_paths[call_id] = patch_coverage_paths
        for group in authorized_dependency_groups.get(call_id, ()):
            if group.intersection(patch_coverage_paths) and not group.issubset(patch_coverage_paths):
                raise PlannerUnavailable(
                    "targeted repair delta contains incomplete_dependency_group:"
                    + call_id
                    + ":"
                    + ",".join(sorted(group))
                )
            if group.issubset(patch_coverage_paths) and not repair_param_group_values_allowed(
                current_fn,
                group,
                patch_params,
                result_kind=str(plan.get("resultKind") or ""),
            ):
                raise PlannerUnavailable(
                    "targeted repair delta contains incompatible_dependency_group:"
                    + call_id
                    + ":"
                    + ",".join(sorted(group))
                )
        authorized_paths = authorized_param_paths.get(call_id, set())
        unauthorized = sorted(
            path for path in patch_paths
            if not _path_is_authorized(path, authorized_paths)
        )
        if unauthorized:
            raise PlannerUnavailable(
                "targeted repair delta contains out_of_scope_engine_call_param:"
                + call_id
                + ":"
                + ",".join(unauthorized)
            )
        whole_object_roots = {
            key
            for key, value in patch_params.items()
            if isinstance(value, dict) and key in authorized_paths
        }
        for root in sorted(whole_object_roots):
            params[root] = copy.deepcopy(patch_params[root])
        for path in sorted(patch_paths):
            if any(path == root or path.startswith(root + ".") for root in whole_object_roots):
                continue
            _set_nested_param(params, path, _get_nested_param(patch_params, path))
        current_call["params"] = params

    for call_id, required_paths in required_param_paths.items():
        missing = sorted(required_paths - applied_param_paths.get(call_id, set()))
        if missing:
            raise PlannerUnavailable(
                "targeted repair delta omits required_exact_param:"
                + call_id
                + ":"
                + ",".join(missing)
            )

    for index, new_call_id in prepared_id_patches:
        calls[index]["callId"] = new_call_id

    return candidate


def _preserve_accepted_engine_calls(
    replacement_plan: dict[str, Any],
    current_plan: dict[str, Any],
    rejected_call_ids: set[str],
) -> None:
    current_candidate = current_plan.get("engineCalls")
    replacement_candidate = replacement_plan.get("engineCalls")
    current_calls: list[Any] = current_candidate if isinstance(current_candidate, list) else []
    replacement_calls: list[Any] = replacement_candidate if isinstance(replacement_candidate, list) else []
    replacement_by_id = {
        str(call.get("callId") or "").strip(): call
        for call in replacement_calls
        if isinstance(call, dict) and str(call.get("callId") or "").strip()
    }
    current_ids = {
        str(call.get("callId") or "").strip()
        for call in current_calls
        if isinstance(call, dict) and str(call.get("callId") or "").strip()
    }
    merged: list[Any] = []
    for raw_call in current_calls:
        if not isinstance(raw_call, dict):
            continue
        call_id = str(raw_call.get("callId") or "").strip()
        if call_id in rejected_call_ids:
            replacement_call = replacement_by_id.get(call_id)
            if replacement_call is not None:
                merged.append(copy.deepcopy(replacement_call))
        else:
            merged.append(copy.deepcopy(raw_call))
    merged.extend(
        copy.deepcopy(call)
        for call in replacement_calls
        if isinstance(call, dict)
        and str(call.get("callId") or "").strip() not in current_ids
    )
    replacement_plan["engineCalls"] = merged


def _merge_missing_authored_param_leaves(
    accepted: dict[str, Any],
    redesigned: dict[str, Any],
) -> dict[str, Any]:
    """Overlay explicit redesign values while retaining omitted authored leaves."""
    merged = copy.deepcopy(accepted)
    for key, value in redesigned.items():
        accepted_value = accepted.get(key)
        if isinstance(accepted_value, dict) and isinstance(value, dict):
            merged[key] = _merge_missing_authored_param_leaves(accepted_value, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _preserve_retained_call_param_leaves_for_redesign(
    replacement_plan: dict[str, Any],
    current_plan: dict[str, Any],
) -> None:
    """Keep omitted leaves only for calls explicitly retained by callId and fn."""
    current_candidate = current_plan.get("engineCalls")
    replacement_candidate = replacement_plan.get("engineCalls")
    current_calls: list[Any] = current_candidate if isinstance(current_candidate, list) else []
    replacement_calls: list[Any] = replacement_candidate if isinstance(replacement_candidate, list) else []
    current_by_id = {
        str(call.get("callId") or "").strip(): call
        for call in current_calls
        if isinstance(call, dict) and str(call.get("callId") or "").strip()
    }
    for replacement_call in replacement_calls:
        if not isinstance(replacement_call, dict):
            continue
        call_id = str(replacement_call.get("callId") or "").strip()
        current_call = current_by_id.get(call_id)
        if not isinstance(current_call, dict):
            continue
        if str(current_call.get("fn") or "").strip() != str(replacement_call.get("fn") or "").strip():
            continue
        accepted_params = current_call.get("params")
        redesigned_params = replacement_call.get("params")
        if isinstance(accepted_params, dict) and isinstance(redesigned_params, dict):
            replacement_call["params"] = _merge_missing_authored_param_leaves(
                accepted_params,
                redesigned_params,
            )


def _preserve_accepted_authoring(
    replacement: dict[str, Any],
    current: dict[str, Any],
    failure_report: dict[str, Any],
) -> dict[str, Any]:
    """Keep accepted identity/fusion/visual authoring out of a domain repair."""
    gameplay_redesign = _failure_mentions(
        failure_report,
        "executor_not_representable",
        "unsupported_mechanic_family",
        "unrepresentable_mechanic",
    )

    preserved = copy.deepcopy(replacement)
    if not _failure_mentions(failure_report, "invalid_item_name", "invalid_identity") and current.get("name"):
        preserved["name"] = copy.deepcopy(current["name"])
    identity_mismatch = _failure_mentions(
        failure_report,
        "category_result_kind_mismatch",
        "result_kind_mismatch",
    )
    result_kind_invalid = identity_mismatch or _failure_mentions(
        failure_report,
        "invalid_result_kind",
        "runtimeplan.resultkind",
        "resultkind",
    )
    category_explicitly_invalid = identity_mismatch or _failure_mentions(
        failure_report,
        "invalid_category",
        "$.category",
    )
    category_repair_allowed = category_explicitly_invalid or result_kind_invalid
    if current.get("category"):
        if not category_repair_allowed:
            preserved["category"] = copy.deepcopy(current["category"])
        elif "category" not in preserved and not category_explicitly_invalid:
            preserved["category"] = copy.deepcopy(current["category"])
    current_concept = current.get("concept")
    if isinstance(current_concept, dict):
        concept = preserved.setdefault("concept", {})
        if isinstance(concept, dict):
            fields = [field for field in ("fantasy", "mergeLogic") if field not in concept]
            if "coreMechanic" not in concept:
                fields.append("coreMechanic")
            for field in fields:
                if field in current_concept:
                    concept[field] = copy.deepcopy(current_concept[field])
    current_plan = current.get("runtimePlan")
    if isinstance(current_plan, dict):
        plan = preserved.setdefault("runtimePlan", {})
        if isinstance(plan, dict):
            if "sourceRolePreservation" in current_plan and "sourceRolePreservation" not in plan:
                plan["sourceRolePreservation"] = copy.deepcopy(current_plan["sourceRolePreservation"])
            current_visual = current_plan.get("visualIntent")
            if isinstance(current_visual, dict):
                replacement_visual = plan.get("visualIntent")
                visual = copy.deepcopy(replacement_visual) if isinstance(replacement_visual, dict) else {}
                rejected_paths = {
                    str(target.get("path") or "").strip()
                    for target in _repair_targets(failure_report)
                    if str(target.get("path") or "").strip()
                }
                whole_visual_rejected = "$.runtimePlan.visualIntent" in rejected_paths
                for field, value in current_visual.items():
                    rejected_path = f"$.runtimePlan.visualIntent.{field}"
                    if not whole_visual_rejected and rejected_path not in rejected_paths:
                        visual[field] = copy.deepcopy(value)
                plan["visualIntent"] = visual
            if not gameplay_redesign and not result_kind_invalid and current_plan.get("resultKind"):
                plan["resultKind"] = copy.deepcopy(current_plan["resultKind"])
            if gameplay_redesign:
                _preserve_retained_call_param_leaves_for_redesign(plan, current_plan)
            else:
                for field in (
                    "runtimeStateIntent",
                    "sourceReading",
                    "balanceIntent",
                    "anomalyFlags",
                ):
                    if field in current_plan and not _failure_mentions(failure_report, field):
                        plan[field] = copy.deepcopy(current_plan[field])
                if not _failure_mentions(failure_report, "duplicate_call_id"):
                    _preserve_accepted_engine_calls(
                        plan,
                        current_plan,
                        _rejected_call_ids(failure_report, current_plan),
                    )
    current_contract = current.get("runtimeContract")
    if not gameplay_redesign and isinstance(current_contract, dict):
        contract = preserved.setdefault("runtimeContract", {})
        if isinstance(contract, dict):
            contract_markers = {
                "primaryVerb": ("primaryverb", "missing_primary_verb"),
                "controlStyle": ("controlstyle", "invalid_control_style"),
                "playerViewTimeline": ("playerviewtimeline", "timeline_runtime_conflict"),
            }
            for field in contract_markers:
                if field in current_contract and field not in contract:
                    contract[field] = copy.deepcopy(current_contract[field])
    return preserved
