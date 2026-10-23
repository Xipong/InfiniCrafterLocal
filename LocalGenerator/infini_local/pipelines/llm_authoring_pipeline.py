from __future__ import annotations

import copy
import json
import math
from typing import Any, Mapping

from infini_local.core.env_utils import env_first_allow_empty, env_float, env_int
from infini_local.core.generation_defaults import GENERATION_DEFAULTS
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.item_identity_tools import name_of, stable_hash
from infini_local.core.json_debug import bounded_json_dumps
from infini_local.core.llm_config import USE_LLM
from infini_local.core.llm_prompt_cache import with_instruction_segments
from infini_local.core.llm_json_tools import parse_first_valid_llm_json, recover_object_with_syntax_only_repairs
from infini_local.core.llm_stage_messages import (
    generation_system_suffix,
    stage_chat_message,
)
from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION, RUNTIME_PROGRAM_SCHEMA, CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope, runtime_repair_fragments
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.program_schema import (
    PRIMARY_ENTITY_SELECTION_FIELD,
    assert_bounded_author_input,
    strict_repair_structure_report,
)
from infini_local.core.runtime_authoring.capability_registry import STACK_COST_RULE
from infini_local.core.runtime_authoring.repair_scope import runtime_repair_schema_capabilities
from infini_local.pipelines.author_item_contract import (
    PRIMARY_REPAIR_SYSTEM_RULE,
    RUNTIME_ROW_SHAPE_RULE,
    author_item_provider_repair_response_schema,
    author_item_provider_response_schema,
    author_item_response_schema,
    author_item_repair_prompt_shape_card,
    author_item_repair_response_schema,
    provider_nullable_transport_rule,
    project_provider_author_item_to_local,
    project_provider_nullable_optionals_to_local,
)
from infini_local.pipelines.llm_authoring_prompt import (
    build_llm_author_payload,
    realization_execution_truth_for_llm,
    runtime_units_for_llm,
    source_wire_units_for_llm,
)
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
from infini_local.pipelines.llm_provider_wire import (
    effective_response_format,
    apply_minimum_reasoning_effort,
    apply_llm_common_options,
    llm_json_response_format,
    llm_reasoning_system_suffix,
    with_llm_stage,
)
from infini_local.pipelines.llm_profiles import active_llm_provider
from infini_local.pipelines.llm_transport import (
    llm_chat_json,
    resolve_llm_model,
)
from infini_local.storage.trace_runtime import trace_event, trace_stage_request
from infini_local.storage.trace_tools import trace_message_summary


_AUTHOR_CACHE_PREFIX_KEYS = (
    "priorityHeader", "runtimeProgramInvariants",
    "runtimeCapabilityContract", "requiredJsonShape", "diagnosticReport",
)
_REPAIR_CACHE_PREFIX_KEYS = ("schema", "task", "rules", "runtimeVersions", "runtimeExecutionTruth")
_FORMAT_REPAIR_CACHE_PREFIX_KEYS = ("schema", "task", "rules", "requiredJsonShape")


_AUTHOR_SYSTEM = (
    "You are Gameplay Author for InfiniCrafterLocal. Construct a single immutable JSON object "
    "matching requiredJsonShape, using the supplied capability catalog. "
    "runtimeProgram alone defines executable gameplay. Optional concept, realization and selfEvaluation "
    "may help your design and self-check, but are advisory only: no mandatory report ceremony, "
    "acceptance evidence or prose-based rejection. Code does not invent missing mechanics. "
    "Apply the construction contracts beside each JSON fragment. Return strict JSON only: "
    "double-quoted keys and strings, no trailing commas, JavaScript expressions, markdown or external reasoning."
)


def _stage_accounting(data: dict[str, Any]) -> dict[str, int]:
    debug = data.setdefault("debug", {})
    accounting = debug.setdefault("llmStageAccounting", {})
    defaults = {
        "gameplayAuthorCalls": 0,
        "gameplayRepairCalls": 0,
        "visualDirectorCalls": 0,
        "visualRepairCalls": 0,
        "vfxDirectorCalls": 0,
        "vfxRepairCalls": 0,
    }
    for key, value in defaults.items():
        accounting.setdefault(key, value)
    return accounting


def _prepare_parsed_author_item(
    parsed: Mapping[str, Any], *, response_format: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    assert_bounded_author_input(parsed, authored_only=False)
    canonical = project_provider_author_item_to_local(dict(parsed), response_format=response_format)
    if not isinstance(canonical, dict):
        raise PlannerUnavailable("Gameplay Author returned a non-object after provider projection")
    return copy.deepcopy(canonical)


def _gameplay_repair_temperature() -> float:
    """Canonical key wins by presence; the GUI spelling is a legacy alias.

    Blank/invalid values use the scoped Repair default, never planner temperature.
    """
    default = 0.12
    raw = env_first_allow_empty(("INFINI_LLM_REPAIR_TEMPERATURE", "INFINI_LLM_REAUTHOR_TEMPERATURE"))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(value):
        return default
    return max(0.0, min(0.8, value))


def build_initial_author_request(
    a: dict[str, Any],
    b: dict[str, Any],
    key: str,
    *,
    model_name: str | None = None,
) -> tuple[dict[str, Any], str, str]:
    payload = build_llm_author_payload(a, b, key)
    selected_model = model_name or resolve_llm_model()
    system = _AUTHOR_SYSTEM + generation_system_suffix() + llm_reasoning_system_suffix(selected_model)
    user_content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    request = {
        "model": selected_model,
        "messages": [
            stage_chat_message("system", "item_author_contract", system),
            stage_chat_message("user", "recipe_context", user_content),
        ],
        "temperature": env_float("INFINI_LLM_TEMPERATURE", float(GENERATION_DEFAULTS["INFINI_LLM_TEMPERATURE"]), lo=0.0, hi=1.2),
        "response_format": llm_json_response_format(
            "infini_low_level_runtime_author",
            schema=author_item_provider_response_schema,
            strict=True,
            auto_preference="json_schema",
        ),
    }
    request = apply_llm_common_options(request, model_name=selected_model)
    system += provider_nullable_transport_rule(request.get("response_format"))
    request["messages"][0]["content"] = system
    request = apply_minimum_reasoning_effort(request, model_name=selected_model, minimum="medium")
    request = with_instruction_segments(request, payload, _AUTHOR_CACHE_PREFIX_KEYS)
    return request, user_content, system


def _repair_malformed_author_json(
    *,
    malformed_raw_text: str,
    parse_error: BaseException,
    original_recipe_context: str,
    model_name: str,
    source_response_format: Mapping[str, Any] | None = None,
    recipe_key: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Spend the one Gameplay Repair call on syntax-only Author recovery."""

    original_context = json.loads(original_recipe_context)
    recovered = recover_object_with_syntax_only_repairs(malformed_raw_text)
    # Syntax recovery has one design source, not another Author request. Only
    # unambiguous registered function identities may narrow its output grammar.
    # Unknown/damaged identities keep the complete grammar and final refusal.
    runtime = recovered.get("runtimeProgram") if isinstance(recovered, Mapping) else None
    calls = runtime.get("calls") if isinstance(runtime, Mapping) else None
    known_calls = isinstance(calls, list) and bool(calls) and all(
        isinstance(row, Mapping) and isinstance(row.get("fn"), str) and row["fn"] in CAPABILITY_REGISTRY
        for row in calls
    )
    functions = sorted({row["fn"] for row in calls}) if known_calls and isinstance(calls, list) else sorted(CAPABILITY_REGISTRY)
    local_schema = author_item_response_schema()
    call_schema = local_schema["properties"]["runtimeProgram"]["properties"]["calls"]
    variants = [row for row in call_schema["items"]["oneOf"] if row["properties"]["fn"]["const"] in functions]
    call_schema["items"] = {"oneOf": variants} if len(variants) > 1 else variants[0]
    repair_context = {
        "schema": "infini.gameplay-author-format-repair.v1",
        "task": "Repair JSON syntax only and return the same complete Gameplay Author object.",
        "rules": [
            "Preserve every recoverable authored value, id, capability, parameter, binding transaction, concept, and realization from malformedRawText.",
            "Do not redesign, add, drop, replace, normalize, or reinterpret gameplay. This call repairs only JSON syntax/container damage.",
            "Call params must use allowedCallParamsReadOnly for their exact fn; do not invent undeclared params even if they sound plausible.",
            "malformedRawText is the sole design source; never introduce a choice absent from it. Keep every source key and array row, including optional advisory text.",
            "Return exactly one strict full Author JSON object with no markdown or prose.",
        ],
        "allowedCallParamsReadOnly": {
            name: sorted(CAPABILITY_REGISTRY[name].params) for name in functions
        },
        "requiredJsonShape": {
            "root": list(local_schema["required"]),
            "runtimeProgram": list(local_schema["properties"]["runtimeProgram"]["required"]),
            "sourcePreservation": "Return the complete source object, not this key index. Copy source values and optional keys; fix syntax only.",
        },
        "parseError": f"{type(parse_error).__name__}: {parse_error}",
        "malformedRawText": malformed_raw_text,
    }
    user_content = json.dumps(repair_context, ensure_ascii=False, separators=(",", ":"))
    system = (
        "You are the single conditional Gameplay Format Repair for InfiniCrafterLocal. "
        "Repair only JSON syntax/container damage in malformedRawText. Preserve the Author's exact recoverable design and executable choices; "
        "do not reauthor or complete missing gameplay; do not invent undeclared params. "
        "Use allowedCallParamsReadOnly to check each call's fn. Return strict full Author JSON only."
    )
    messages = [
        stage_chat_message("system", "author_repair_contract", system + generation_system_suffix() + llm_reasoning_system_suffix(model_name)),
        stage_chat_message("user", "author_repair_context", user_content),
    ]
    request = apply_llm_common_options({
        "model": model_name,
        "messages": messages,
        "temperature": _gameplay_repair_temperature(),
        "response_format": llm_json_response_format(
            "infini_low_level_runtime_author_format_repair",
            schema=lambda: author_item_provider_response_schema(local_schema=local_schema),
            strict=True,
            auto_preference="json_schema",
        ),
    }, model_name=model_name)
    messages[0]["content"] += provider_nullable_transport_rule(request.get("response_format"))
    request = apply_minimum_reasoning_effort(request, model_name=model_name, minimum="medium")
    request = with_instruction_segments(request, repair_context, _FORMAT_REPAIR_CACHE_PREFIX_KEYS)
    trace_event(
        "prompt", "LLM:gameplay_repair", "Conditional Gameplay Author format-repair request",
        {"provider": active_llm_provider(), "model": model_name, "malformedChars": len(malformed_raw_text)},
        prompt=request["messages"],
    )
    try:
        # The Author caller owns the join; standalone syntax replays may lack it.
        # Let the recorder explicitly refuse a missing join without blocking Repair.
        trace_key = recipe_key if recipe_key is not None else original_context.get("recipeKey")
        trace_stage_request("gameplay_format_repair", trace_key, request)
        raw = llm_chat_json(with_llm_stage(request, "author_repair"), timeout=env_int("INFINI_LLM_TIMEOUT", int(GENERATION_DEFAULTS["INFINI_LLM_TIMEOUT"])))
        content = str(raw["choices"][0]["message"]["content"])
        trace_event(
            "response", "LLM:gameplay_repair", "Conditional Gameplay Author format-repair response",
            {"model": model_name, "chars": len(content), "transport": raw.get("_debug", {})},
            response=content,
        )
        parsed = parse_first_valid_llm_json(content)
        if not isinstance(parsed, Mapping):
            raise PlannerUnavailable("Gameplay Author format Repair returned non-object JSON")
        if recovered is None:
            raise PlannerUnavailable("Gameplay format Repair cannot prove recoverable authored fields")
        original = _prepare_parsed_author_item(recovered, response_format=source_response_format)
        projected = project_provider_nullable_optionals_to_local(
            parsed, local_schema, response_format=effective_response_format(request, raw),
        )
        repaired = _prepare_parsed_author_item(projected)
        if original != repaired:
            raise PlannerUnavailable("Gameplay format Repair changed recoverable authored fields")
        return repaired, content
    except PlannerUnavailable:
        raise
    except Exception as exc:
        raise PlannerUnavailable(f"Gameplay Author format Repair failed: {exc!r}") from exc


def try_llm_plan(
    a: dict[str, Any],
    b: dict[str, Any],
    key: str,
) -> dict[str, Any] | None:
    """Perform exactly one baseline Gameplay Author call.

    Validation failure is propagated to the one conditional Gameplay Repair owned by
    ``gameplay_stage.compile_and_validate_authored_runtime``. This function never
    retries and never asks code to select a replacement capability.
    """
    if not USE_LLM:
        return None
    model_name = resolve_llm_model()
    request, user_content, _ = build_initial_author_request(a, b, key, model_name=model_name)
    try:
        trace_event(
            "prompt",
            "LLM:gameplay_author",
            f"Gameplay Author request: {name_of(a)} + {name_of(b)}",
            {
                "provider": active_llm_provider(),
                "model": model_name,
                "responseFormat": bool(request.get("response_format")),
                "messages": trace_message_summary(request.get("messages")),
            },
            prompt=user_content,
        )
        trace_stage_request("gameplay_author", key, request)
        raw = llm_chat_json(with_llm_stage(request, "planner"), timeout=env_int("INFINI_LLM_TIMEOUT", int(GENERATION_DEFAULTS["INFINI_LLM_TIMEOUT"])))
        content = raw["choices"][0]["message"]["content"]
        trace_event(
            "response",
            "LLM:gameplay_author",
            "Gameplay Author response",
            {"provider": active_llm_provider(), "model": model_name, "chars": len(str(content)), "transport": raw.get("_debug", {})},
            response=content,
        )
        format_repaired = False
        format_repair_content = ""
        try:
            parsed = parse_first_valid_llm_json(content)
            if not isinstance(parsed, dict):
                raise TypeError("Gameplay Author returned non-object JSON")
            item = _prepare_parsed_author_item(parsed, response_format=effective_response_format(request, raw))
        except (ValueError, TypeError, json.JSONDecodeError) as parse_error:
            item, format_repair_content = _repair_malformed_author_json(
                malformed_raw_text=str(content),
                parse_error=parse_error,
                original_recipe_context=user_content,
                model_name=model_name,
                source_response_format=effective_response_format(request, raw),
                recipe_key=key,
            )
            format_repaired = True
        item.setdefault("id", "g_" + stable_hash(key, format_repair_content or content, length=16))
        item.setdefault("recipeKey", key)
        item.setdefault("schemaVersion", 5)
        item.setdefault("parentA", name_of(a))
        item.setdefault("parentB", name_of(b))
        item.setdefault("sourceMode", "generated")
        debug = item.setdefault("debug", {})
        debug.update({
            "planner": "llm_low_level_runtime_author",
            "model": model_name,
            "promptMode": "low_level_runtime_program_v5",
            "runtimeAuthorSchema": RUNTIME_PROGRAM_SCHEMA,
            "runtimeApiVersion": RUNTIME_PROGRAM_API_VERSION,
            "llmRawOutput": str(content)[:12000],
        })
        if format_repaired:
            debug["gameplayFormatRepairRawOutput"] = format_repair_content[:12000]
        accounting = _stage_accounting(item)
        accounting["gameplayAuthorCalls"] = 1
        accounting["gameplayRepairCalls"] = 1 if format_repaired else 0
        return item
    except PlannerUnavailable:
        raise
    except Exception as exc:
        diagnosis = getattr(exc, "_infini_shape_diagnosis", None)
        trace_event(
            "error", "LLM:gameplay_author", "Gameplay Author transport/parse failure",
            {"model": model_name, **({"requestShapeRejection": diagnosis} if isinstance(diagnosis, dict) else {})},
            error=repr(exc),
        )
        if isinstance(diagnosis, dict):
            # Surface the actionable configuration mismatch instead of a bare provider 400.
            raise PlannerUnavailable(
                f"Gameplay Author failed: {exc!r} | {diagnosis.get('hint') or ''}"
            ) from exc
        raise PlannerUnavailable(f"Gameplay Author failed: {exc!r}") from exc


def _repair_error_rows(failure_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    validation = failure_report.get("validation")
    canonical = (
        [copy.deepcopy(row) for row in validation["errors"] if isinstance(row, dict)]
        if isinstance(validation, Mapping) and isinstance(validation.get("errors"), list) else []
    )
    rows = failure_report.get("errors")
    if isinstance(rows, list):
        exact = [copy.deepcopy(row) for row in rows if isinstance(row, dict)]
        # A failure envelope may carry a display-only prefix alongside the full
        # same-pass Author report. Recover that exact report, never combine or
        # replace distinct compiler-owned provenance with broader permissions.
        if exact and len(exact) < len(canonical) and exact == canonical[:len(exact)]:
            return canonical
        return exact
    if isinstance(validation, Mapping) and isinstance(validation.get("errors"), list):
        return canonical
    return [{
        "path": str(failure_report.get("path") or "$"),
        "code": str(failure_report.get("code") or "runtime_program_rejected"),
        "message": str(failure_report.get("error") or "Runtime program failed deterministic validation")[:1600],
    }]


GAMEPLAY_REPAIR_DOSSIER_SCHEMA = "infini.gameplay-repair-dossier.v1"


def build_gameplay_repair_dossier(
    current: Mapping[str, Any],
    a: Mapping[str, Any],
    b: Mapping[str, Any],
    *,
    failure_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the finite model-facing dossier for one Gameplay Repair call.

    This is intentionally a pure projection.  It contains exact invalid
    fragments, local dependencies, a compact global id index, and exact read-only
    concept/runtimeProgram for the complete realizationReplacement. Capability
    cards remain limited to current blockers; source visibility grants no edits.
    """

    assert_bounded_author_input(current)
    exact_errors = _repair_error_rows(failure_report)
    scope = build_runtime_repair_scope(current, exact_errors)
    fragments = runtime_repair_fragments(current, scope)
    blocker_plan = scope.get("blockerPlan") if isinstance(scope.get("blockerPlan"), Mapping) else {}
    parents = {
        "a": {"packet": raw_parent_card_for_llm(dict(a))},
        "b": {"packet": raw_parent_card_for_llm(dict(b))},
    }

    def cards(names: Any) -> list[dict[str, Any]]:
        return [
            CAPABILITY_REGISTRY[name].prompt_card()
            for name in names or []
            if name in CAPABILITY_REGISTRY and CAPABILITY_REGISTRY[name].author_visible
        ]

    return {
        "schema": GAMEPLAY_REPAIR_DOSSIER_SCHEMA,
        "task": "Repair only the deterministic mutable scope of this low-level runtime program.",
        "rules": [
            "Return exactly the repair patch schema; never return the full item.",
            "Every upsert entry must be a complete schema-valid node. Copy the existing node from readOnlySourceFragments.brokenFragments, changing only permitted fields; preserve unchanged required fields and accepted optional values or absences. Do not add or remove target/params merely to match an example; only exact fieldPermissions authorize edits.",
            RUNTIME_ROW_SHAPE_RULE,
            STACK_COST_RULE,
            "Fix only exact fieldPermissions paths and explicitly allowed blocker/dependency nodes; do not add unrelated optional design fields.",
            "For existing nodes, omission means no change, not reset to a card default. Preserve accepted absences too; an optional default describes the full Author object after frozen-first merge, never permission to add or delete a field. New nodes must satisfy the full capability requirements.",
            "Extra rewrites of frozen values or independent ids are ignored rather than cancelling a useful repair.",
            "For each exact repairScope.deletable.callPropertyKeys entry that must be removed, emit the matching callPropertyKeysDelete {callId,key}; a note claiming removal does not mutate the program.",
            "Use create permissions only for the exact blocker or its declared support dependency.",
            "Keep stable ids when repairing existing nodes; use a new id only for an explicitly allowed missing node.",
            "immutableProgramIndex.entities[*].id is the exact allowlist for every target and entity-reference value that points to an existing entity in this patch; never carry an id from another item. When repairScope.create.calls.allowedTargetKinds is non-empty, a new call may instead target an id emitted exactly once in entitiesUpsert whose kind is listed there; use that same new id consistently and do not invent any other target.",
            "Do not introduce a weapon family, archetype, semantic root, or code-authored default.",
            "Resolve every exact error and re-check references, target kinds, inputs, cycles, and budgets.",
            "realizationReplacement is optional advisory context about the post-merge program, never an observed run or an acceptance requirement. Do not repair or complete prose or self-evaluation. acceptedItemContext.runtimeProgram is the exact read-only pre-repair source, including invalid fields; overlay only edits admitted by repairScope and keep every frozen value and absence unchanged.",
            f"When repairTransactions.{PRIMARY_ENTITY_SELECTION_FIELD}.allowed is true, set {PRIMARY_ENTITY_SELECTION_FIELD} to exactly one listed candidate; Lowery materializes technical wire roles from that exact authored identity.",
            "For each repairRequirements row with requiredBindingUpdates, emit every listed existing binding exactly once using one of its complete allowed transactions; mustApplyAll means these updates are one coupled repair, not alternatives. When mustCreateExactlyOne is true, emit exactly one allowedBindingTransactions row and it must have a new id. When mustChooseExactlyOne is true without mustCreateExactlyOne, emit exactly one complete allowedBindingTransactions choice: an existing id is eligible only when it appears in that row's allowedExistingBindingIds and its complete tuple is projected by bindingAlternatives; a new id is eligible only when repairScope.create.bindings permits it. Global mutability never authorizes an id for another requirement; never update every listed lane.",
            "For each repairTransactions.exclusiveInputSelections group, either retarget/delete conflicting bindings through exact fieldPermissions or emit one exclusiveInputSelections row choosing the keepBindingId; do not do both after the conflict is resolved.",
            "For each repairScope.eventAlternatives row, choose one complete alternative: author its exact event plus every listed required call/binding in the same patch, and emit no support from unselected alternatives. The engine never chooses or inserts an event producer for you.",
        ],
        "runtimeVersions": {
            "authorSchema": RUNTIME_PROGRAM_SCHEMA,
            "apiVersion": RUNTIME_PROGRAM_API_VERSION,
        },
        "runtimeExecutionTruth": {
            **realization_execution_truth_for_llm(),
            "units": runtime_units_for_llm(include_source_units=False),
        },
        "parents": parents,
        # Like Author, keep parent-dependent reading aids beside the raw facts,
        # outside the shared instruction prefix. Visibility never grants edits.
        "sourceWireUnits": source_wire_units_for_llm([row["packet"] for row in parents.values()]),
        "acceptedItemContext": {
            "name": current.get("name"),
            "category": current.get("category"),
            "realization": copy.deepcopy(current.get("realization") or {}),
            **{key: copy.deepcopy(current[key]) for key in ("concept", "runtimeProgram") if key in current},
        },
        "exactValidationErrors": exact_errors,
        "failureStage": str(failure_report.get("stage") or "runtime_program_validation"),
        "repairScope": scope,
        "readOnlySourceFragments": {
            "brokenFragments": fragments["broken"],
            "brokenFragmentsByIndex": fragments["brokenByIndex"],
            "validDependencyFragments": fragments["dependencyContext"],
        },
        "immutableProgramIndex": fragments["immutableIndex"],
        "blockerCapabilities": cards(blocker_plan.get("directCapabilityNames")),
        "supportingCapabilities": cards(blocker_plan.get("supportingCapabilityNames")),
        "existingBrokenCapabilityCards": cards(blocker_plan.get("existingBrokenCapabilityNames")),
        "requiredJsonShape": author_item_repair_prompt_shape_card(capability_names=runtime_repair_schema_capabilities(scope)),
    }


def repair_author_item_after_failure(
    current: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    key: str,
    *,
    failure_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Perform one conditional Gameplay Repair over a deterministic node scope.

    The model receives invalid nodes, exact missing-dependency permissions, and
    read-only source context for its full report. The model may return a
    complete broken node, but deterministic merge changes only exact broken paths;
    already-valid old values remain frozen and independent nodes are ignored.
    """
    if not USE_LLM:
        raise PlannerUnavailable("Gameplay Repair required but LLM is disabled")
    model_name = resolve_llm_model()
    repair_context = build_gameplay_repair_dossier(
        current, a, b, failure_report=failure_report,
    )
    exact_errors = copy.deepcopy(repair_context["exactValidationErrors"])
    scope = copy.deepcopy(repair_context["repairScope"])
    if scope.get("nonRepairableErrors"):
        raise PlannerUnavailable(
            "Gameplay validation exposed a registry/runtime defect that LLM Repair must not hide: "
            + bounded_json_dumps(scope["nonRepairableErrors"], max_chars=5000)
        )
    local_repair_schema = author_item_repair_response_schema(
        capability_names=runtime_repair_schema_capabilities(scope))
    repair_user = json.dumps(repair_context, ensure_ascii=False, separators=(",", ":"))
    repair_system = (
        "You are the conditional Gameplay Repair for InfiniCrafterLocal. Close exactValidationErrors through repairScope permissions, repairTransactions, eventAlternatives and repairScope.blockerPlan; never repair the whole item. "
        f"{PRIMARY_REPAIR_SYSTEM_RULE} For each exclusive-input transaction, either repair the conflicting binding input/delete path or choose one keepBindingId; do not emit a redundant choice after retargeting resolves the conflict. "
        "Every target or entity-reference id that points to an existing entity must be copied from immutableProgramIndex.entities[*].id; never carry an id from another item. When repairScope.create.calls.allowedTargetKinds is non-empty, a new call target may instead use an id emitted exactly once in entitiesUpsert whose kind is listed there; use that same new id consistently and never invent any other target. "
        "For every bindingId in repairScope.bindingAlternatives that you update, copy one complete input/action/target tuple verbatim into bindingsUpsert; never cross-product fields from different alternatives. When a repairRequirement sets mustChooseExactlyOne without mustCreateExactlyOne, emit exactly one complete allowed binding transaction: an existing id must be listed by that exact row's allowedExistingBindingIds and bindingAlternatives; a new id must be permitted by create.bindings. Global mutability does not let one blocker satisfy another; never update all candidate bindings. "
        "For every repairScope.eventAlternatives row, choose one complete event alternative, author every listed required call/binding in the same patch, and emit no call/binding from unselected alternatives; no event dependency is inserted automatically. "
        "Every llmRepairable repairRequirement whose requiredOneOfCapabilities is non-empty must be absent after the patch. An independently authorized delete/retarget may close it structurally; otherwise callsUpsert must patch or create one complete listed call on an affected target. A note claiming closure does not satisfy it. "
        "For an exact shape_additional_property under calls[*].params, remove only the matching repairScope.deletable.callParamKeys entry: either emit callParamKeysDelete or omit that key from the complete callsUpsert row. "

        "Omit unchanged root patch fields: absent optional arrays/metadataPatch mean no change; note is required; realizationReplacement is optional advisory text. Do not copy dossier keys into the patch, especially readOnlySourceFragments or any of its diagnostic children. Every upsert row must be complete and schema-valid; copy every unchanged required field from readOnlySourceFragments.brokenFragments and modify only permitted paths. "
        "Deterministic merge will freeze already-valid old values and accept the exact broken or mandatory missing fields. Independent valid nodes and optional unreported fields are read-only; extra "
        "rewrites are ignored. New nodes are allowed only by the exact blocker create policy. The final requiredJsonShape field of the user JSON is solely the output patch shape; emit only its listed root keys with your chosen values, never source-context keys or requiredJsonShape itself. Return strict patch JSON only."
    )
    messages = [
        stage_chat_message("system", "author_repair_contract", repair_system + generation_system_suffix() + llm_reasoning_system_suffix(model_name)),
        stage_chat_message("user", "author_repair_context", repair_user),
    ]
    request = apply_llm_common_options({
        "model": model_name,
        "messages": messages,
        "temperature": _gameplay_repair_temperature(),
        "response_format": llm_json_response_format(
            "infini_low_level_runtime_repair",
            schema=lambda: author_item_provider_repair_response_schema(local_schema=local_repair_schema),
            strict=True,
            auto_preference="json_schema",
        ),
    }, model_name=model_name)
    messages[0]["content"] += provider_nullable_transport_rule(request.get("response_format"))
    request = with_instruction_segments(request, repair_context, _REPAIR_CACHE_PREFIX_KEYS)
    trace_event(
        "prompt",
        "LLM:gameplay_repair",
        "Conditional node-scoped Gameplay Repair request",
        {
            "provider": active_llm_provider(),
            "model": model_name,
            "errorCount": len(exact_errors),
            "mutableCounts": {key: len(value) for key, value in (scope.get("mutable") or {}).items()},
        },
        prompt=request["messages"],
    )
    try:
        trace_stage_request("gameplay_repair", key, request, recipe_id=current.get("id"))
        raw = llm_chat_json(with_llm_stage(request, "author_repair"), timeout=env_int("INFINI_LLM_TIMEOUT", int(GENERATION_DEFAULTS["INFINI_LLM_TIMEOUT"])))
        content = raw["choices"][0]["message"]["content"]
        trace_event(
            "response",
            "LLM:gameplay_repair",
            "Conditional Gameplay Repair response",
            {"model": model_name, "chars": len(str(content)), "transport": raw.get("_debug", {})},
            response=content,
        )
        parsed = parse_first_valid_llm_json(content)
        patch = project_provider_nullable_optionals_to_local(
            parsed, local_schema=local_repair_schema,
            response_format=effective_response_format(request, raw),
        )
        if not isinstance(patch, Mapping):
            raise PlannerUnavailable("Gameplay Repair must return a patch object")
        report = strict_repair_structure_report(patch)
        if not report.get("ok"):
            raise PlannerUnavailable("Gameplay Repair patch shape rejected: " + bounded_json_dumps(report, max_chars=6000))
        filtered_patch, filter_report = filter_repair_patch_scope(current, patch, scope)
        if not filter_report.get("ok"):
            raise PlannerUnavailable(
                "Gameplay Repair patch could not be deterministically filtered: "
                + bounded_json_dumps(filter_report, max_chars=7000),
                author_repair_targets=copy.deepcopy(filter_report.get("errors") or []),
            )
        repaired = apply_repair_patch(current, filtered_patch)
        validation = validate_runtime_program(repaired)
        if not validation.get("ok"):
            raise PlannerUnavailable(
                "Gameplay Repair did not resolve runtime validation: "
                + "; ".join(f"{row.get('path')}: {row.get('message')}" for row in validation.get("errors", [])[:12]),
                author_repair_targets=copy.deepcopy(validation.get("errors") or []),
            )
        repaired.setdefault("debug", {})["gameplayRepairRawPatch"] = copy.deepcopy(parsed)
        repaired["debug"]["gameplayRepairPatch"] = copy.deepcopy(filtered_patch)
        repaired["debug"]["gameplayRepairStructureValidation"] = copy.deepcopy(report)
        repaired["debug"]["gameplayRepairFilterAudit"] = copy.deepcopy(filter_report)
        repaired["debug"]["gameplayRepairScope"] = copy.deepcopy(scope)
        accounting = _stage_accounting(repaired)
        accounting["gameplayAuthorCalls"] = max(1, int(accounting.get("gameplayAuthorCalls", 0)))
        accounting["gameplayRepairCalls"] = 1
        return repaired
    except PlannerUnavailable:
        raise
    except Exception as exc:
        raise PlannerUnavailable(f"Gameplay Repair failed: {exc!r}") from exc


__all__ = [
    "GAMEPLAY_REPAIR_DOSSIER_SCHEMA",
    "build_gameplay_repair_dossier",
    "build_initial_author_request",
    "repair_author_item_after_failure",
    "try_llm_plan",
]
