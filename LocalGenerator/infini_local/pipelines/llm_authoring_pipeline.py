from __future__ import annotations

import copy
import json
import re
from typing import Any

from infini_local.core.env_utils import env_float, env_int
from infini_local.core.json_debug import bounded_json_dumps
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.item_identity_tools import name_of, stable_hash
from infini_local.core.llm_config import USE_LLM
from infini_local.core.llm_json_tools import parse_first_valid_llm_json
from infini_local.core.llm_stage_messages import (
    ATTRIBUTED_PLANNER_HISTORY_KIND,
    agent_handoff,
    attributed_planner_history,
    stage_chat_message,
)
from infini_local.core.runtime_contracts import (
    STRUCTURAL_RUNTIME_CONTRACT_SCHEMA,
    validate_structural_final_wire_contract,
    validate_structural_planner_contract,
)
from infini_local.core.runtime_authoring.engine_call_contracts import engine_params_model
from infini_local.core.runtime_authoring.reports import compiled_fields_for_authored_call
from infini_local.pipelines.author_item_contract import (
    author_item_prompt_shape_card,
    author_item_provider_repair_response_schema,
    author_item_provider_response_schema,
    author_item_provider_targeted_repair_delta_schema,
    author_item_repair_response_schema,
    author_item_targeted_repair_delta_schema,
    project_provider_author_item_to_local,
    strict_author_item_repair_report,
    strict_author_item_targeted_repair_delta_report,
)
from infini_local.pipelines.llm_authoring_prompt import (
    EQUIPMENT_LIGHT_ENCODING,
    PULL_ON_HIT_ENCODING,
    PRIMARY_FUNCTION_AUTHOR_RULES,
    RUNTIME_PLAN_METADATA_TYPES,
    VISUAL_TOPOLOGY_RULES,
    VISIBLE_ENGINE_FUNCTIONS,
    build_llm_author_payload,
    engine_runtime_capability_contract_for_llm,
)


_AUTHOR_STRUCTURAL_WIRE_RULES = (
    " Return exactly the source-derived requiredJsonShape fields. "
    "For combat, engineCalls[0] is set_item_stats with explicit resultKind and required combat stats; every later call uses only its catalog params. "
    "concept.coreMechanic is concise player-facing gameplay text. playerViewTimeline is optional and contains only relevant visible phases. "
    "Do not return compiler provenance, receipts, signatures, or final DTO paths."
)
from infini_local.pipelines.llm_transport import (
    active_llm_provider,
    apply_llm_common_options,
    llm_chat_json,
    llm_json_response_format,
    llm_reasoning_system_suffix,
    resolve_llm_model,
)
from infini_local.storage.trace_runtime import _trace_message_summary, log_event, trace_event


def _prepare_parsed_author_item(parsed: dict[str, Any]) -> dict[str, Any]:
    """Decode provider-only nullable omissions; perform no alias or semantic repair."""
    canonical = project_provider_author_item_to_local(parsed)
    raw_snapshot = copy.deepcopy(canonical)
    obj = copy.deepcopy(canonical)
    obj["_authorItemRaw"] = raw_snapshot
    return obj




def planner_runtime_promise_gate(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate author metadata without mutating the model-authored document."""
    return validate_structural_planner_contract(plan)


def final_runtime_promise_report(data: dict[str, Any]) -> dict[str, Any]:
    """Return the structured v3 compiler-provenance report without raising."""
    raw_contract_candidate = data.get("runtimeContract")
    raw_contract: dict[str, Any] = dict(raw_contract_candidate) if isinstance(raw_contract_candidate, dict) else {}
    if str(raw_contract.get("schema") or "") != STRUCTURAL_RUNTIME_CONTRACT_SCHEMA:
        return {
            "schema": "infini.final-wire-contract-report.v1",
            "ok": False,
            "blockingClaims": [{
                "kind": "missing_structural_v3_contract",
                "source": "runtimeContract.schema",
                "required": STRUCTURAL_RUNTIME_CONTRACT_SCHEMA,
            }],
            "finalWireReceipts": [],
            "executionStatus": "unsupported",
        }
    return validate_structural_final_wire_contract(data)


def validate_final_runtime_promise_boundary(data: dict[str, Any]) -> dict[str, Any]:
    """Require v3 compiler provenance at every runtime-authored final boundary."""
    gate = final_runtime_promise_report(data)
    data.setdefault("debug", {})
    if isinstance(data.get("debug"), dict):
        data["debug"]["finalWireExecutionReceipts"] = copy.deepcopy(gate.get("finalWireReceipts") or [])
        data["debug"]["finalRuntimePromiseGate"] = bounded_json_dumps(gate, max_chars=8000)
    if not gate.get("ok"):
        kinds = sorted({str(row.get("kind") or "unsupported") for row in gate.get("blockingClaims") or []})
        raise PlannerUnavailable("final structural runtime promise boundary rejected: " + ", ".join(kinds))
    return gate


def build_initial_author_request(
    a: dict[str, Any],
    b: dict[str, Any],
    ca: dict[str, Any],
    cb: dict[str, Any],
    key: str,
    *,
    model_name: str | None = None,
) -> tuple[dict[str, Any], str, str]:
    """Build the exact initial AuthorItem request without performing transport."""
    user = build_llm_author_payload(a, b, ca, cb, key)
    selected_model = model_name or resolve_llm_model()
    system = (
        "You are the AUTHOR of a Terraria-like generated item. "
        "Use raw parent fields, semantic notes, and engine functions to design one playable result. "
        "Follow the priorityHeader before the detailed API card. "
        "The server validates executable safety only; do not rely on legacy attackPattern/attack.genome. "
        + _AUTHOR_STRUCTURAL_WIRE_RULES
        + " "
        "Return ONLY one JSON object. No reasoning, no markdown, no second JSON."
        + llm_reasoning_system_suffix(selected_model)
    )
    user_content = json.dumps(user, ensure_ascii=False, separators=(",", ":"))
    req = {
        "model": selected_model,
        "messages": [
            stage_chat_message("system", "item_author_contract", system),
            stage_chat_message("user", "recipe_context", user_content),
        ],
        "temperature": env_float("INFINI_LLM_TEMPERATURE", 0.38, lo=0.0, hi=1.2),
        "response_format": llm_json_response_format(
            "infini_author_item_v3",
            schema=author_item_provider_response_schema(),
            strict=True,
            auto_preference="json_object",
        ),
    }
    return apply_llm_common_options(req, model_name=selected_model), user_content, system


def try_llm_plan(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any] | None:
    """Author-first chaos planner.

    v0.3.9 keeps the author-first architecture. The LLM authors the playable item: fantasy,
    category, gameplay numbers, projectile identity, behavior timeline, and visual briefs.
    Python does not choose the item. It only validates JSON, fills trivial serialization
    fields, then clamps catastrophic power/performance after the fact.
    """
    if not USE_LLM:
        return None
    try:
        model_name = resolve_llm_model()
        req, planner_user_content, system = build_initial_author_request(
            a, b, ca, cb, key, model_name=model_name
        )
        trace_event("prompt", "LLM:author_plan", f"Planner request: {name_of(a)} + {name_of(b)}", {
            "provider": active_llm_provider(), "model": model_name, "temperature": req.get("temperature"),
            "maxTokens": req.get("max_tokens"), "reasoning": req.get("reasoning"), "reasoningEffort": req.get("reasoning_effort"),
            "responseFormat": bool(req.get("response_format")), "messages": _trace_message_summary(req.get("messages")),
        }, prompt=planner_user_content)
        raw = llm_chat_json(req, timeout=env_int("INFINI_LLM_TIMEOUT", 95))
        content = raw["choices"][0]["message"]["content"]
        transport_debug = raw.get("_debug") if isinstance(raw.get("_debug"), dict) else {}
        trace_event("response", "LLM:author_plan", "Planner response", {"provider": active_llm_provider(), "model": model_name, "chars": len(str(content)), "transport": transport_debug}, response=content)
        parsed_child_json = parse_first_valid_llm_json(content)
        obj = _prepare_parsed_author_item(parsed_child_json)
        # The initial author call never retries internally. Source/runtime/compiler
        # rejection is owned by the one bounded same-author repair budget in
        # combine_pipeline.
        promise_gate = planner_runtime_promise_gate(obj)
        obj.setdefault("id", "g_" + stable_hash(key, content, length=16))
        obj.setdefault("recipeKey", key)
        obj.setdefault("schemaVersion", 1)
        obj.setdefault("parentA", name_of(a))
        obj.setdefault("parentB", name_of(b))
        obj.setdefault("sourceMode", "generated")
        obj.setdefault("debug", {})
        obj["debug"]["planner"] = "llm_author_first"
        obj["debug"]["plannerPromiseGate"] = promise_gate
        obj["debug"]["model"] = model_name
        obj["debug"]["promptMode"] = "runtime_authoring_family_contract_v0.4.30_priority_header_placeable_semantics_v0.4.172"
        obj["debug"]["balanceAuthority"] = "llm_authors_numbers_python_clamps_after_authoring"
        obj["debug"]["llmRawOutput"] = content[:12000]
        obj["debug"]["llmTopLevelKeys"] = ",".join(sorted(str(k) for k in obj.keys()))
        obj["debug"]["llmHistoryStored"] = ATTRIBUTED_PLANNER_HISTORY_KIND
        # Runtime-only named Chat Completions history.  Consumers receive one canonical
        # messages[] contract instead of reconstructing roles from parallel string fields.
        obj["_llmHistory"] = attributed_planner_history(system, planner_user_content, content)
        return obj
    except PlannerUnavailable as e:
        trace_event("error", "LLM:author_plan", "Planner rejected authored result", {"parents": [name_of(a), name_of(b)]}, error=repr(e))
        log_event("warn", "LLM author-first planner failed source validation", {"error": repr(e)})
        raise
    except Exception as e:
        trace_event("error", "LLM:author_plan", "Planner failed", {"parents": [name_of(a), name_of(b)]}, error=repr(e))
        log_event("warn", "LLM author-first planner failed", {"error": repr(e)})
        return None


def _author_item_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    """Return only the model-owned object, never compiler/debug projections."""
    raw = data.get("_authorItemRaw")
    candidate = raw if isinstance(raw, dict) else data
    schema = author_item_provider_response_schema()
    properties = schema.get("properties")
    keys = properties.keys() if isinstance(properties, dict) else ()
    snapshot = {
        str(field): copy.deepcopy(candidate[field])
        for field in keys
        if field in candidate
    }
    contract_candidate = snapshot.get("runtimeContract")
    if isinstance(contract_candidate, dict):
        snapshot["runtimeContract"] = {
            field: copy.deepcopy(contract_candidate[field])
            for field in ("primaryVerb", "controlStyle", "playerViewTimeline")
            if field in contract_candidate
        }
    return snapshot


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
            "authoredParam", "authoredValue", "compiledField", "compiledValue",
            "finalPath", "finalActual",
        )
        for key in provenance_keys:
            if isinstance(provenance, dict) and key in provenance:
                value = provenance[key]
                if isinstance(value, (str, bool, int, float)) or value is None:
                    row[key] = value
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
                if value or field in provenance_keys
            })

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for child in value:
                visit(child)
            return
        if isinstance(value, str):
            indexed = re.search(
                r"engineCalls(?:\[(\d+)\]|\.(\d+))(?:\.([A-Za-z0-9_.]+))?",
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


def _targeted_repair_param_paths(
    current_plan: dict[str, Any],
    invalid_targets: list[dict[str, Any]],
) -> dict[str, set[str]]:
    """Map typed rejection evidence to exact authored parameter leaf paths."""
    calls_candidate = current_plan.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    by_id: dict[str, dict[str, Any]] = {
        str(call.get("callId") or "").strip(): call
        for call in calls
        if isinstance(call, dict) and str(call.get("callId") or "").strip()
    }
    paths_by_call: dict[str, set[str]] = {}
    for target in invalid_targets:
        call_id = str(target.get("callId") or "").strip()
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
        path_match = re.search(r"\.params\.([A-Za-z0-9_.]+)$", target_path)
        if path_match:
            selected.add(str(path_match.group(1)))
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
    return {call_id: paths for call_id, paths in paths_by_call.items() if paths}


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
            call_id = str(call.get("callId") or "").strip()
            fn = str(call.get("fn") or "").strip()
            if not call_id or not fn:
                raise PlannerUnavailable(
                    f"indexed_target_owner_unresolved:engineCalls[{index}]"
                )
            supplied_call_id = str(target.get("callId") or "").strip()
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
        if nested_tails:
            projected["properties"][name] = _project_repair_leaf_schema(
                resolved_property,
                nested_tails,
                root,
            )
        elif not isinstance(resolved_property.get("properties"), dict):
            projected["properties"][name] = resolved_property
    return projected


def _targeted_repair_function_cards(
    current_plan: dict[str, Any],
    invalid_targets: list[dict[str, Any]],
    engine_card: dict[str, Any],
) -> dict[str, Any]:
    """Expose only rejected owners with source-derived schemas for exact leaf paths."""
    calls_candidate = current_plan.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    paths_by_call = _targeted_repair_param_paths(current_plan, invalid_targets)
    selected_calls = [
        call
        for call in calls
        if isinstance(call, dict)
        and str(call.get("callId") or "").strip() in paths_by_call
    ]
    cards: dict[str, Any] = {}
    for call in selected_calls:
        call_id = str(call.get("callId") or "").strip()
        fn = str(call.get("fn") or "").strip()
        leaf_paths = paths_by_call[call_id]
        card_candidate = engine_card.get(fn)
        if not isinstance(card_candidate, dict):
            continue
        card = copy.deepcopy(card_candidate)
        params_schema = engine_params_model(fn).model_json_schema()
        projected = _project_repair_leaf_schema(
            params_schema,
            leaf_paths,
            params_schema,
        )
        projected_params = projected.get("properties")
        if not isinstance(projected_params, dict) or not projected_params:
            continue
        card["callId"] = call_id
        card["fn"] = fn
        card["params"] = projected_params
        cards[call_id] = card
    return cards


def _targeted_visual_intent_paths(invalid_targets: list[dict[str, Any]]) -> set[str]:
    paths: set[str] = set()
    for target in invalid_targets:
        target_path = str(target.get("path") or "")
        match = re.search(r"\.visualIntent\.([A-Za-z0-9_.]+)$", target_path)
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
            rf"\.{re.escape(field)}\.([A-Za-z0-9_.]+)$",
            target_path,
        )
        if match:
            paths.add(str(match.group(1)))
        for name in target.get("repairParamNames") or []:
            value = str(name).strip()
            if value.startswith(prefix):
                paths.add(value.removeprefix(prefix))
    return paths


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
            projected = _project_repair_leaf_schema(field_schema, leaf_paths, base)
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
            projected = _project_repair_leaf_schema(field_schema, leaf_paths, base)
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


def _patch_leaf_paths(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        paths: list[str] = []
        for key, child in value.items():
            child_path = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(_patch_leaf_paths(child, child_path))
        return paths or ([prefix] if prefix else [])
    return [prefix] if prefix else []


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
                    str(call.get("callId") or "").strip()
                    for call in calls
                    if isinstance(call, dict) and str(call.get("callId") or "").strip()
                )
            call_id = value.get("callId")
            if isinstance(call_id, str) and call_id.strip():
                rejected.add(call_id.strip())
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
            call_id = str(calls[index].get("callId") or "").strip()
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
    authorized_visual_intent_paths = _targeted_visual_intent_paths(invalid_targets)
    authorized_source_role_paths = _targeted_author_object_paths(
        invalid_targets,
        "sourceRolePreservation",
    )
    authorized_runtime_metadata_fields = _targeted_runtime_metadata_fields(invalid_targets)
    authorized_identity_fields = _targeted_identity_fields(invalid_targets)

    allowed_delta_keys = {
        "identity", "authorFields", "runtimeMetadata", "engineCallParamPatches",
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
    seen_call_ids: set[str] = set()
    for param_patch in delta.get("engineCallParamPatches") or []:
        call_id = str(param_patch.get("callId") or "").strip()
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
        unauthorized = sorted(
            patch_paths - authorized_param_paths.get(call_id, set())
        )
        if unauthorized:
            raise PlannerUnavailable(
                "targeted repair delta contains out_of_scope_engine_call_param:"
                + call_id
                + ":"
                + ",".join(unauthorized)
            )
        for path in sorted(patch_paths):
            _set_nested_param(params, path, _get_nested_param(patch_params, path))
        current_call["params"] = params

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


def _scoped_repair_candidate(patch: dict[str, Any]) -> dict[str, Any]:
    """Project the compact repair response into model-owned AuthorItem domains."""
    candidate: dict[str, Any] = {}
    for field in ("name", "category"):
        if field in patch:
            candidate[field] = copy.deepcopy(patch[field])
    concept = {
        field: copy.deepcopy(patch[field])
        for field in ("fantasy", "mergeLogic", "coreMechanic")
        if field in patch
    }
    if concept:
        candidate["concept"] = concept
    contract = {
        field: copy.deepcopy(patch[field])
        for field in ("primaryVerb", "controlStyle", "playerViewTimeline")
        if field in patch
    }
    if contract:
        candidate["runtimeContract"] = contract
    plan = copy.deepcopy(patch["runtimePlan"]) if isinstance(patch.get("runtimePlan"), dict) else {}
    for field in ("sourceRolePreservation", "visualIntent"):
        if field in patch:
            plan[field] = copy.deepcopy(patch[field])
    if plan:
        candidate["runtimePlan"] = plan
    return candidate


def _scoped_repair_context(current_item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    concept_candidate = current_item.get("concept")
    concept: dict[str, Any] = concept_candidate if isinstance(concept_candidate, dict) else {}
    plan_candidate = current_item.get("runtimePlan")
    plan: dict[str, Any] = plan_candidate if isinstance(plan_candidate, dict) else {}
    current_runtime_plan = {
        field: copy.deepcopy(plan[field])
        for field in (
            "resultKind", "engineCalls", "runtimeStateIntent", "sourceReading",
            "balanceIntent", "anomalyFlags",
        )
        if field in plan
    }
    preserved_context = {
        "name": current_item.get("name"),
        "fantasy": concept.get("fantasy"),
        "mergeLogic": concept.get("mergeLogic"),
        "visualIntent": copy.deepcopy(plan.get("visualIntent")),
        "sourceRolePreservation": copy.deepcopy(plan.get("sourceRolePreservation")),
    }
    return current_runtime_plan, preserved_context


def _repair_allowed_patch_keys(failure_report: dict[str, Any], targeted: bool) -> list[str]:
    gameplay_keys = [
        "runtimePlan", "coreMechanic", "primaryVerb", "controlStyle", "playerViewTimeline",
    ]
    if not targeted:
        return ["category", *gameplay_keys]
    target_text = " ".join(
        " ".join(
            str(target.get(field) or "").casefold()
            for field in ("path", "reason", "callId", "fn", "kind")
        )
        for target in _repair_targets(failure_report)
    )
    keys: list[str] = []
    if any(str(target.get("callId") or "").strip() for target in _repair_targets(failure_report)):
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


def build_same_author_repair_request(
    data: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    failure_report: dict[str, Any],
) -> tuple[dict[str, Any], str, str, bool, dict[str, Any]]:
    """Build one bounded, concept-preserving same-author repair request."""
    current_item = _author_item_snapshot(data)
    current_runtime_plan, preserved_context = _scoped_repair_context(current_item)
    targeted_repair = not _failure_mentions(
        failure_report,
        "executor_not_representable",
        "unsupported_mechanic_family",
        "unrepresentable_mechanic",
    )
    model_name = resolve_llm_model()
    allowed_patch_keys = _repair_allowed_patch_keys(failure_report, targeted_repair)
    capability = engine_runtime_capability_contract_for_llm(a, b)
    available_function_cards = capability.get("availableFunctions")
    available_cards: dict[str, Any] = (
        available_function_cards if isinstance(available_function_cards, dict) else {}
    )
    invalid_targets = _resolve_indexed_target_call_owners(
        _repair_targets(failure_report),
        current_runtime_plan,
    )
    if targeted_repair:
        repair_function_cards = _targeted_repair_function_cards(
            current_runtime_plan,
            invalid_targets,
            available_cards,
        )
        (
            provider_author_field_schemas,
            provider_runtime_metadata_fields,
            provider_identity_field_schemas,
        ) = _targeted_provider_delta_scope(
            current_item,
            invalid_targets,
            allowed_patch_keys,
        )
        if not (
            repair_function_cards
            or provider_author_field_schemas
            or provider_runtime_metadata_fields
            or provider_identity_field_schemas
        ):
            raise PlannerUnavailable(
                "targeted_repair_has_no_authorized_delta_branches"
            )
    else:
        repair_function_cards = {
            fn: copy.deepcopy(available_cards[fn])
            for fn in sorted(set(VISIBLE_ENGINE_FUNCTIONS))
            if fn in available_cards
        }
        provider_author_field_schemas = {}
        provider_runtime_metadata_fields = set()
        provider_identity_field_schemas = {}
    metadata_shape = author_item_prompt_shape_card().get("runtimeContract")
    visual_intent_rule = (
        "visualIntent is a top-level patch key; never place it inside runtimePlan."
        if "visualIntent" in allowed_patch_keys
        else "Do not return visualIntent because it is not in allowedPatchKeys."
    )
    redesign_rules = [
        "A full redesign must remove non-representable calls instead of restating their params.",
        (
            "For passive armor/accessory light, use only armor_effect.stats or "
            "accessory_effect.stats with both lightStrength and lightColorName; omit "
            "set_alt_use_mode and emit_light."
        ),
        (
            "set_alt_use_mode mode=light is an active non-equipment utility and requires "
            "a positive emit_light call plus durationTicks."
        ),
    ]
    system = (
        "You are the scoped repair pass of the SAME ITEM AUTHOR ROLE. "
        "Return only a compact JSON patch using allowedPatchKeys; never repeat the full AuthorItem. "
        "Repair only invalidTargets. Preserve identity, fantasy, fusion, physical parts, and visual topology from preservedConceptContext. "
        "For targeted repair, accepted engine calls remain byte-equivalent unless their callId is invalid. "
        "For full_redesign, redesign gameplay only; the compiler still does not choose mechanics. "
        + " ".join(redesign_rules)
        + " "
        "No reasoning, markdown, wrapper, proof graph, receipts, or DTO paths."
        + llm_reasoning_system_suffix(model_name)
    )
    dossier = {
        "task": "Repair only the rejected authored domain and return a compact patch.",
        "agentHandoff": agent_handoff(
            previous_speaker="item_planner",
            current_speaker="authoring_contract_gate",
            next_speaker="item_planner",
            cause_by="authoring_domain_rejected",
            artifact_source="current_authored_item",
        ),
        "repairMode": "targeted_domain_repair" if targeted_repair else "full_redesign",
        "contextOnlyParentNames": {"itemA": name_of(a), "itemB": name_of(b)},
        "allowedPatchKeys": allowed_patch_keys,
        "allowedEngineFunctions": list(VISIBLE_ENGINE_FUNCTIONS),
        "primaryFunctionRules": dict(PRIMARY_FUNCTION_AUTHOR_RULES),
        "runtimePlanMetadataTypes": dict(RUNTIME_PLAN_METADATA_TYPES),
        "pullOnHitEncoding": dict(PULL_ON_HIT_ENCODING),
        "visualTopologyRules": copy.deepcopy(VISUAL_TOPOLOGY_RULES),
        "equipmentLightEncoding": copy.deepcopy(EQUIPMENT_LIGHT_ENCODING),
        "redesignRules": redesign_rules,
        "repairFunctionCards": repair_function_cards,
        "repairMetadataShape": copy.deepcopy(metadata_shape) if isinstance(metadata_shape, dict) else {},
        "patchRules": [
            visual_intent_rule,
            "Every runtimePlan patch must include resultKind; it must match set_item_stats.params.resultKind and category when category is repairable.",
            "Every runtimePlan.engineCalls replacement entry is a complete call with callId, fn, and params.",
            "Every fn must be one of allowedEngineFunctions; never invent or alias an engine function.",
            "Keep exactly one primary function; temporary helpers cannot fire or act as turrets; deploy_sentry is the only turret function.",
        ],
        "invalidTargets": invalid_targets,
        "currentRuntimePlan": current_runtime_plan,
        "currentCoreMechanic": (
            (current_item.get("concept") or {}).get("coreMechanic")
            if isinstance(current_item.get("concept"), dict)
            else ""
        ),
        "currentPlayerViewTimeline": (
            (current_item.get("runtimeContract") or {}).get("playerViewTimeline")
            if isinstance(current_item.get("runtimeContract"), dict)
            else []
        ),
        "preservedConceptContext": preserved_context,
    }
    response_schema = author_item_provider_repair_response_schema()
    response_schema_name = "infini_author_item_scoped_repair_v1"
    response_format_preference = "json_object"
    if targeted_repair:
        system = (
            "You are the SAME item_planner who authored the accepted item below. "
            "The item is a finished accepted product except for the exact rejected leaves. "
            "Calibrate only those leaves against the complete accepted item. "
            "Return only a TargetedRepairDelta JSON object: changed params only, never a runtimePlan wrapper, never a repeated AuthorItem, and never unchanged calls or params. "
            "Use engineCallParamPatches for ordinary value fixes. Structural call replacement, addition, and removal are not part of targeted repair. "
            "Do not change accepted callId/fn pairs, identity, concept, visual topology, or metadata except an exact leaf explicitly listed in invalidTargets. "
            "No reasoning, markdown, proof graph, receipts, or DTO paths."
            + llm_reasoning_system_suffix(model_name)
        )
        rejected_call_ids = sorted(_rejected_call_ids(failure_report, current_runtime_plan))
        targeted_delta_shape: dict[str, Any] = {}
        if provider_identity_field_schemas:
            targeted_delta_shape["identity"] = {
                "category": "current or exact authorized value",
                "resultKind": "current or exact authorized value",
            }
        if provider_author_field_schemas:
            targeted_delta_shape["authorFields"] = sorted(
                provider_author_field_schemas
            )
        if provider_runtime_metadata_fields:
            targeted_delta_shape["runtimeMetadata"] = sorted(
                provider_runtime_metadata_fields
            )
        if repair_function_cards:
            targeted_delta_shape["engineCallParamPatches"] = [{
                "callId": "existing rejected callId",
                "fn": "same accepted fn",
                "params": {"changedParamOnly": "new typed value"},
            }]
        dossier = {
            "task": "Repair only the exact rejected leaves in your otherwise accepted finished item.",
            "agentHandoff": agent_handoff(
                previous_speaker="authoring_contract_gate",
                current_speaker="item_planner",
                next_speaker="authoring_contract_gate",
                cause_by="exact_authored_leaves_rejected",
                artifact_source="acceptedAuthorItem",
            ),
            "repairMode": "targeted_leaf_delta",
            "acceptedAuthorItem": current_item,
            "invalidTargets": invalid_targets,
            "rejectedCallIds": rejected_call_ids,
            "allowedAuthorDomains": allowed_patch_keys,
            "repairFunctionCards": repair_function_cards,
            "targetedRepairDeltaShape": targeted_delta_shape,
            "deltaRules": [
                "Return the smallest sufficient delta; omit every unchanged top-level key.",
                "Each engineCallParamPatches.params object contains changed leaves only.",
                "A params patch must repeat the existing callId and fn exactly.",
                "If identity changes, return identity.category and identity.resultKind together and keep set_item_stats.params.resultKind equal.",
                "Do not add, remove, replace, or repeat accepted calls.",
            ],
        }
        response_schema = author_item_provider_targeted_repair_delta_schema(
            repair_function_cards,
            allowed_author_field_schemas=provider_author_field_schemas,
            allowed_runtime_metadata_fields=provider_runtime_metadata_fields,
            identity_field_schemas=provider_identity_field_schemas,
        )
        response_schema_name = "infini_author_item_targeted_repair_delta_v1"
        response_format_preference = "json_schema"
    user_content = json.dumps(dossier, ensure_ascii=False, separators=(",", ":"))
    req = {
        "model": model_name,
        "messages": [
            stage_chat_message("system", "item_author_contract", system),
            stage_chat_message("user", "final_wire_compiler", user_content),
        ],
        "temperature": env_float(
            "INFINI_LLM_REAUTHOR_TEMPERATURE",
            env_float("INFINI_LLM_TEMPERATURE", 0.38, lo=0.0, hi=1.2),
            lo=0.0,
            hi=1.2,
        ),
        "response_format": llm_json_response_format(
            response_schema_name,
            schema=response_schema,
            strict=True,
            auto_preference=response_format_preference,
        ),
    }
    return (
        apply_llm_common_options(req, model_name=model_name),
        user_content,
        system,
        targeted_repair,
        current_item,
    )


def repair_author_item_after_failure(
    data: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    ca: dict[str, Any],
    cb: dict[str, Any],
    key: str,
    *,
    failure_report: dict[str, Any],
) -> dict[str, Any]:
    """Give one exact domain rejection to the same item-author role before abort.

    The compiler remains evidence-only: it neither chooses nor edits a mechanic.
    Ordinary rejection uses a typed leaf delta. Full gameplay redesign remains a
    separate complete-patch contract. Both return to source validation and compile.
    """
    if not USE_LLM:
        raise PlannerUnavailable("same-author scoped repair requires the configured item author")

    req, user_content, system, targeted_repair, current_item = (
        build_same_author_repair_request(data, a, b, failure_report)
    )
    model_name = str(req.get("model") or resolve_llm_model())
    trace_event(
        "prompt",
        "LLM:author_plan_scoped_repair",
        "Planner same-author scoped repair request",
        {
            "provider": active_llm_provider(),
            "model": model_name,
            "failureStage": str(failure_report.get("stage") or "unknown"),
        },
        prompt=user_content,
    )
    raw = llm_chat_json(req, timeout=env_int("INFINI_LLM_TIMEOUT", 95))
    content = raw["choices"][0]["message"]["content"]
    transport_debug = raw.get("_debug") if isinstance(raw.get("_debug"), dict) else {}
    trace_event(
        "response",
        "LLM:author_plan_scoped_repair",
        "Planner same-author scoped repair response",
        {
            "provider": active_llm_provider(),
            "model": model_name,
            "chars": len(str(content)),
            "transport": transport_debug,
        },
        response=content,
    )
    raw_patch = parse_first_valid_llm_json(content)
    if targeted_repair:
        patch = project_provider_author_item_to_local(
            raw_patch,
            author_item_targeted_repair_delta_schema(),
        )
        patch_report = strict_author_item_targeted_repair_delta_report(patch)
        if not patch_report.get("ok"):
            raise PlannerUnavailable(
                "same-author targeted repair returned an invalid delta: "
                + bounded_json_dumps(patch_report, max_chars=4000)
            )
        parsed = _apply_targeted_repair_delta(current_item, patch, failure_report)
        repair_kind = "same_author_role_targeted_leaf_delta"
    else:
        patch = project_provider_author_item_to_local(
            raw_patch,
            author_item_repair_response_schema(),
        )
        patch_report = strict_author_item_repair_report(patch)
        allowed_patch_keys = set(_repair_allowed_patch_keys(failure_report, targeted_repair))
        unexpected_patch_keys = sorted(set(patch) - allowed_patch_keys)
        if unexpected_patch_keys:
            patch_report.setdefault("errors", []).append({
                "path": "$",
                "kind": "out_of_scope_repair_keys",
                "keys": unexpected_patch_keys,
            })
            patch_report["ok"] = False
        required_patch_keys = {"category", "coreMechanic", "primaryVerb", "controlStyle", "runtimePlan"}
        missing_patch_keys = sorted(required_patch_keys - set(patch))
        plan = patch.get("runtimePlan") if isinstance(patch.get("runtimePlan"), dict) else {}
        required_plan_keys = {
            "resultKind", "engineCalls", "runtimeStateIntent", "sourceReading",
            "balanceIntent", "anomalyFlags",
        }
        missing_plan_keys = sorted(required_plan_keys - set(plan))
        if missing_patch_keys or missing_plan_keys:
            patch_report.setdefault("errors", []).append({
                "path": "$",
                "kind": "incomplete_gameplay_redesign_patch",
                "missingPatchKeys": missing_patch_keys,
                "missingRuntimePlanKeys": missing_plan_keys,
            })
            patch_report["ok"] = False
        if not patch_report.get("ok"):
            raise PlannerUnavailable(
                "same-author scoped repair returned an invalid patch: "
                + bounded_json_dumps(patch_report, max_chars=4000)
            )
        parsed = _preserve_accepted_authoring(
            _scoped_repair_candidate(patch),
            current_item,
            failure_report,
        )
        repair_kind = "same_author_role_full_gameplay_redesign"
    obj = _prepare_parsed_author_item(parsed)
    source_gate = planner_runtime_promise_gate(copy.deepcopy(obj))
    if not source_gate.get("ok"):
        kinds = sorted({str(row.get("kind") or "unsupported") for row in source_gate.get("blockingClaims") or []})
        raise PlannerUnavailable("same-author scoped repair returned invalid source contract: " + ", ".join(kinds))

    obj.setdefault("id", str(data.get("id") or "g_" + stable_hash(key, content, length=16)))
    obj.setdefault("recipeKey", key)
    obj.setdefault("schemaVersion", 1)
    obj.setdefault("parentA", name_of(a))
    obj.setdefault("parentB", name_of(b))
    obj.setdefault("sourceMode", "generated")
    obj.setdefault("debug", {})
    obj["debug"]["planner"] = "llm_author_first"
    obj["debug"]["plannerPromiseGate"] = source_gate
    obj["debug"]["model"] = model_name
    obj["debug"]["authorRepair"] = repair_kind
    obj["debug"]["repairPatchKeys"] = sorted(patch)
    obj["debug"]["authorRepairTransport"] = copy.deepcopy(transport_debug)
    obj["debug"]["llmRawOutput"] = str(content)[:12000]
    obj["_llmHistory"] = attributed_planner_history(system, user_content, content)
    return obj


def call_llm_vfx_director(system: str, user: dict[str, Any], max_tokens: int, temperature: float, timeout: int, messages: list[dict[str, str]] | None = None) -> dict[str, Any] | None:
    """Small adapter used by vfx_manifest.py.

    Keeps the VFX module from creating a new LLM backend or importing server.py.
    The caller must supply the authoritative self-contained V3.1 system + VFX
    dossier. Planner transcript replay and standalone authoring are not supported.
    """
    if not USE_LLM:
        return None
    if not isinstance(messages, list) or not messages:
        raise ValueError("self-contained VFX stage messages are required")
    req_messages = [
        stage_chat_message(
            str(message.get("role") or "user"),
            str(message.get("name") or ""),
            str(message.get("content") or ""),
        )
        for message in messages
        if isinstance(message, dict) and str(message.get("content") or "").strip()
    ]
    if not req_messages:
        raise ValueError("self-contained VFX stage messages are required")
    try:
        model_name = resolve_llm_model()
        req = {
            "model": model_name,
            "messages": req_messages,
            "temperature": float(temperature),
            "response_format": llm_json_response_format("infini_vfx"),
        }
        req = apply_llm_common_options(req, model_name=model_name, default_max_tokens=int(max_tokens))
        trace_event("prompt", "LLM:vfx_director", "VFX director request", {
            "provider": active_llm_provider(), "model": model_name, "temperature": req.get("temperature"),
            "maxTokens": req.get("max_tokens"), "reasoning": req.get("reasoning"), "reasoningEffort": req.get("reasoning_effort"),
            "messageMode": "authoritative_stage_dossier_v31", "messages": _trace_message_summary(req.get("messages")),
        }, prompt=req_messages)
        raw = llm_chat_json(req, timeout=int(timeout))
        content = raw["choices"][0]["message"]["content"]
        transport_debug = raw.get("_debug") if isinstance(raw.get("_debug"), dict) else {}
        trace_event("response", "LLM:vfx_director", "VFX director response", {"model": model_name, "chars": len(str(content)), "transport": transport_debug}, response=content)
        # Return the model artifact exactly. Transport metadata belongs in trace/debug
        # side channels; injecting `_debug` here makes a valid strict VFX object fail its
        # own top-level contract.
        return parse_first_valid_llm_json(content)
    except Exception as e:
        trace_event("error", "LLM:vfx_director", "VFX director failed", error=repr(e))
        log_event("warn", "LLM VFX director failed", {"error": repr(e)})
        return None


# legacy contract marker for tests/documentation: ensure_llm_auth_configured()
