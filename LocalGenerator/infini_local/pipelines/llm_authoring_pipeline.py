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
from infini_local.pipelines.author_item_contract import (
    author_item_provider_repair_response_schema,
    author_item_provider_response_schema,
    author_item_repair_response_schema,
    project_provider_author_item_to_local,
    strict_author_item_repair_report,
)
from infini_local.pipelines.llm_authoring_prompt import (
    PRIMARY_FUNCTION_AUTHOR_RULES,
    VISIBLE_ENGINE_FUNCTIONS,
    build_llm_author_payload,
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
    if sources:
        return sources
    if fallback_errors:
        return fallback_errors
    if any(key in failure_report for key in ("kind", "status", "path", "callId")):
        return [failure_report]
    return []


def _repair_targets(failure_report: dict[str, Any]) -> list[dict[str, str]]:
    """Extract bounded structural evidence without interpreting authored prose."""
    targets: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add(
        *,
        path: Any = "",
        call_id: Any = "",
        fn: Any = "",
        reason: Any = "",
    ) -> None:
        row = {
            "path": str(path or "").strip(),
            "callId": str(call_id or "").strip(),
            "fn": str(fn or "").strip(),
            "reason": str(reason or "").strip(),
        }
        if not any(row.values()):
            return
        key = (row["path"], row["callId"], row["fn"], row["reason"])
        if key not in seen and len(targets) < 24:
            seen.add(key)
            targets.append({key: value for key, value in row.items() if value})

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
        text = str(value or "")
        indexed = re.search(r"engineCalls(?:\[(\d+)\]|\.(\d+))(?:\.|\]|$)", text)
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
    category_invalid = identity_mismatch or _failure_mentions(
        failure_report,
        "invalid_category",
        "$.category",
    )
    result_kind_invalid = identity_mismatch or _failure_mentions(
        failure_report,
        "invalid_result_kind",
        "runtimeplan.resultkind",
    )
    if not gameplay_redesign and not category_invalid and current.get("category"):
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
            if not gameplay_redesign:
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
    system = (
        "You are the scoped repair pass of the SAME ITEM AUTHOR ROLE. "
        "Return only a compact JSON patch using allowedPatchKeys; never repeat the full AuthorItem. "
        "Repair only invalidTargets. Preserve identity, fantasy, fusion, physical parts, and visual topology from preservedConceptContext. "
        "For targeted repair, accepted engine calls remain byte-equivalent unless their callId is invalid. "
        "For full_redesign, redesign gameplay only; the compiler still does not choose mechanics. "
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
        "allowedPatchKeys": _repair_allowed_patch_keys(failure_report, targeted_repair),
        "allowedEngineFunctions": list(VISIBLE_ENGINE_FUNCTIONS),
        "primaryFunctionRules": dict(PRIMARY_FUNCTION_AUTHOR_RULES),
        "patchRules": [
            "visualIntent is a top-level patch key; never place it inside runtimePlan.",
            "Every runtimePlan.engineCalls replacement entry is a complete call with callId, fn, and params.",
            "Every fn must be one of allowedEngineFunctions; never invent or alias an engine function.",
            "Keep exactly one primary function; temporary helpers cannot fire or act as turrets; deploy_sentry is the only turret function.",
        ],
        "invalidTargets": _repair_targets(failure_report),
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
            "infini_author_item_scoped_repair_v1",
            schema=author_item_provider_repair_response_schema(),
            strict=True,
            auto_preference="json_object",
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
    The configured author returns only a bounded patch, which is merged into the
    rejected authored object before ordinary source validation and recompilation.
    """
    if not USE_LLM:
        raise PlannerUnavailable("same-author scoped repair requires the configured item author")

    req, user_content, system, _, current_item = (
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
    patch = project_provider_author_item_to_local(
        raw_patch,
        author_item_repair_response_schema(),
    )
    patch_report = strict_author_item_repair_report(patch)
    targeted_repair = not _failure_mentions(
        failure_report,
        "executor_not_representable",
        "unsupported_mechanic_family",
        "unrepresentable_mechanic",
    )
    allowed_patch_keys = set(_repair_allowed_patch_keys(failure_report, targeted_repair))
    unexpected_patch_keys = sorted(set(patch) - allowed_patch_keys)
    if unexpected_patch_keys:
        patch_report.setdefault("errors", []).append({
            "path": "$",
            "kind": "out_of_scope_repair_keys",
            "keys": unexpected_patch_keys,
        })
        patch_report["ok"] = False
    if not targeted_repair:
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
    obj["debug"]["authorRepair"] = "same_author_role_scoped_patch"
    obj["debug"]["repairPatchKeys"] = sorted(patch)
    obj["debug"]["authorRepairTransport"] = copy.deepcopy(transport_debug)
    obj["debug"]["llmRawOutput"] = str(content)[:12000]
    obj["_llmHistory"] = attributed_planner_history(system, user_content, content)
    return obj


def call_llm_vfx_director(system: str, user: dict[str, Any], max_tokens: int, temperature: float, timeout: int, messages: list[dict[str, str]] | None = None) -> dict[str, Any] | None:
    """Small adapter used by vfx_manifest.py.

    Keeps the VFX module from creating a new LLM backend or importing server.py.
    When messages is supplied, the caller already built the authoritative V3.1
    system + VFX dossier. Planner transcript replay is not part of this adapter.
    """
    if not USE_LLM:
        return None
    try:
        model_name = resolve_llm_model()
        if messages is not None:
            req_messages = [
                stage_chat_message(
                    str(m.get("role") or "user"),
                    str(m.get("name") or ""),
                    str(m.get("content") or ""),
                )
                for m in messages
                if str(m.get("content") or "").strip()
            ]
            if not req_messages:
                return None
        else:
            standalone_user = dict(user)
            standalone_user.setdefault("agentHandoff", agent_handoff(
                previous_speaker="pipeline_orchestrator",
                current_speaker="vfx_director_context",
                next_speaker="vfx_director",
                cause_by="vfx_manifest_authoring",
                artifact_source="vfxInputPacket.childItem",
            ))
            handoff_value = standalone_user.get("agentHandoff")
            handoff: dict[str, Any] = handoff_value if isinstance(handoff_value, dict) else {}
            current_speaker = str(handoff.get("currentSpeaker") or "vfx_director_context")
            req_messages = [
                stage_chat_message("system", "vfx_director_contract", system + llm_reasoning_system_suffix(model_name)),
                stage_chat_message("user", current_speaker, json.dumps(standalone_user, ensure_ascii=False, separators=(",", ":"))),
            ]
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
            "messageMode": "authoritative_stage_dossier_v31" if messages is not None else "legacy_no_history_standalone", "messages": _trace_message_summary(req.get("messages")),
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
