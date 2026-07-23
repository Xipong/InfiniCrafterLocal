from __future__ import annotations

import copy
import json
from typing import Any

from infini_local.core.env_utils import env_float, env_int
from infini_local.core.json_debug import bounded_json_dumps
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.item_identity_tools import name_of, stable_hash
from infini_local.core.llm_config import USE_LLM
from infini_local.core.llm_json_tools import parse_first_valid_llm_json
from infini_local.core.llm_stage_messages import (
    ATTRIBUTED_PLANNER_HISTORY_KIND,
    attributed_planner_history,
    stage_chat_message,
)
from infini_local.core.runtime_contracts import (
    STRUCTURAL_RUNTIME_CONTRACT_SCHEMA,
    apply_structural_final_wire_contract,
    structural_final_wire_report,
    validate_structural_planner_contract,
)
from infini_local.core.runtime_authoring.schema import (
    COMBAT_ROOT_AUTHORED_REQUIRED_PARAMS,
)
from infini_local.pipelines.author_item_contract import (
    author_item_provider_response_schema,
    author_item_repair_response_schema,
    author_item_targeted_repair_delta_schema,
    normalize_author_item_targeted_repair_delta_text_limits,
    project_provider_author_item_to_local,
    strict_author_item_repair_report,
    strict_author_item_targeted_repair_delta_report,
)
from infini_local.pipelines import author_item_repair
from infini_local.pipelines import author_item_repair_delta
from infini_local.pipelines import author_item_repair_scope
from infini_local.pipelines.llm_authoring_prompt import (
    COMBAT_EXECUTOR_RESULT_KIND_RULE,
    build_llm_author_payload,
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


_AUTHOR_STRUCTURAL_WIRE_RULES = (
    " Return exactly the source-derived requiredJsonShape fields. "
    "For combat, engineCalls[0] is set_item_stats with explicit resultKind and required combat stats; every later call uses only its catalog params. "
    f"Every combat root engine call MUST include {', '.join(COMBAT_ROOT_AUTHORED_REQUIRED_PARAMS)} explicitly. "
    + COMBAT_EXECUTOR_RESULT_KIND_RULE
    + " "
    "concept.coreMechanic is concise authored design intent for repair/debug, never the final tooltip. playerViewTimeline is optional and contains only relevant visible phases. "
    "Do not return compiler provenance, receipts, signatures, or final DTO paths."
)


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
    return structural_final_wire_report(data)


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
    apply_structural_final_wire_contract(data, gate)
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
        author_item_repair.build_same_author_repair_request(data, a, b, failure_report)
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
        patch = normalize_author_item_targeted_repair_delta_text_limits(patch)
        patch_report = strict_author_item_targeted_repair_delta_report(patch)
        if not patch_report.get("ok"):
            raise PlannerUnavailable(
                "same-author targeted repair returned an invalid delta: "
                + bounded_json_dumps(patch_report, max_chars=4000)
            )
        parsed = author_item_repair_delta._apply_targeted_repair_delta(
            current_item, patch, failure_report
        )
        repair_kind = "same_author_role_targeted_leaf_delta"
    else:
        patch = project_provider_author_item_to_local(
            raw_patch,
            author_item_repair_response_schema(),
        )
        patch_report = strict_author_item_repair_report(patch)
        allowed_patch_keys = set(
            author_item_repair_scope._repair_allowed_patch_keys(failure_report, targeted_repair)
        )
        unexpected_patch_keys = sorted(set(patch) - allowed_patch_keys)
        if unexpected_patch_keys:
            patch_report.setdefault("errors", []).append({
                "path": "$",
                "kind": "out_of_scope_repair_keys",
                "keys": unexpected_patch_keys,
            })
            patch_report["ok"] = False
        required_patch_keys = author_item_repair_scope.FULL_REDESIGN_REQUIRED_PATCH_KEYS
        missing_patch_keys = sorted(required_patch_keys - set(patch))
        plan = patch.get("runtimePlan") if isinstance(patch.get("runtimePlan"), dict) else {}
        required_plan_keys = author_item_repair_scope.FULL_REDESIGN_REQUIRED_PLAN_KEYS
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
        parsed = author_item_repair_delta._preserve_accepted_authoring(
            author_item_repair._scoped_repair_candidate(patch),
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
