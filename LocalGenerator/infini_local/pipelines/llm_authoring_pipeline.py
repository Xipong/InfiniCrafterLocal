from __future__ import annotations

import copy
import json
from typing import Any, Mapping

from infini_local.core.env_utils import env_float, env_int
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.item_identity_tools import name_of, stable_hash
from infini_local.core.json_debug import bounded_json_dumps
from infini_local.core.llm_config import USE_LLM
from infini_local.core.llm_json_tools import parse_first_valid_llm_json, recover_object_with_trailing_commas
from infini_local.core.llm_stage_messages import (
    ATTRIBUTED_PLANNER_HISTORY_KIND,
    attributed_planner_history,
    stage_chat_message,
)
from infini_local.core.runtime_authoring import (
    BINDING_ACTION_REGISTRY,
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_PROGRAM_SCHEMA,
    RUNTIME_WIRE_SCHEMA,
    CAPABILITY_REGISTRY,
    apply_repair_patch,
    build_runtime_repair_scope,
    compile_runtime_program,
    filter_repair_patch_scope,
    runtime_repair_fragments,
    validate_runtime_program,
    validate_runtime_wire,
)
from infini_local.core.runtime_authoring.program_schema import (
    PRIMARY_ENTITY_SELECTION_FIELD,
)
from infini_local.core.runtime_authoring.binding_use_policy import STACK_COST_RULE
from infini_local.core.vfx_manifest import MalformedVfxDirectorOutput
from infini_local.pipelines.author_item_contract import (
    PRIMARY_AUTHOR_SYSTEM_RULE,
    PRIMARY_REPAIR_SYSTEM_RULE,
    author_item_provider_repair_response_schema,
    author_item_provider_response_schema,
    author_item_prompt_shape_card,
    author_item_repair_prompt_shape_card,
    project_provider_author_item_to_local,
    project_provider_nullable_optionals_to_local,
    strict_author_item_repair_report,
)
from infini_local.pipelines.llm_authoring_prompt import (
    build_llm_author_payload,
    realization_execution_truth_for_llm,
)
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
from infini_local.pipelines.llm_transport import (
    active_llm_provider,
    apply_minimum_reasoning_effort,
    apply_llm_common_options,
    llm_chat_json,
    llm_json_response_format,
    llm_reasoning_system_suffix,
    resolve_llm_model,
    with_llm_stage,
)
from infini_local.storage.trace_runtime import _trace_message_summary, trace_event


_AUTHOR_SYSTEM = (
    "You are Gameplay Author for InfiniCrafterLocal. Compose one bounded executable item directly from "
    "the supplied low-level capability catalog. Return exactly the required JSON object. The code validates, "
    "bounds, compiles, and executes your explicit choices; it does not infer a weapon archetype or complete "
    "missing movement, attachment, delivery, lifecycle, input, targeting, or child behaviour. Do not classify "
    "the item as sword/bow/staff/sentry for runtime. Preserve literal parent objects when useful: a workbench "
    "may remain a literal workbench attached to a blade. Do not add a mandatory weird twist. Treat concept as the "
    "non-binding initial_design_draft: it anchors the attempt but never becomes runtime authority and later drift from it does not reject a craft. "
    "runtimeProgram is the executable_gameplay_program and the only gameplay authority. After runtimeProgram, author realization as the final_gameplay_report of that executable program. "
    "Write realization.selfEvaluation last as the same_pass_self_evaluation: independently compare concept.plannedPlayerActions with runtimeProgram in planVsProgram.actionChecks, then compare every executable runtime lane with description/playerExperience in programVsReport.behaviorChecks. Every check must cite exact runtime ids, including aligned checks. Never describe mechanics absent from the program. Use only catalog capabilities. Check every reference, "
    "target kind, dependency, event, exclusive input, cycle, entity limit, and child budget before answering. "
    f"{PRIMARY_AUTHOR_SYSTEM_RULE} Group bindings by input and reject the draft if an exclusive input has more than one row. Every binding is one complete usePolicy transaction; configure_item_use never chooses or requires a companion action binding. Catalog membership is not a recommendation. "
    "Use exact catalog param names: configure_item_stats currency is params.valueCopper in copper coins; never use params.value. "
    "Percent-valued params are whole percentage numbers: for +15% enter 15, not 0.15 (which means +0.15%). "
    f"{STACK_COST_RULE} "
    f"{', '.join(BINDING_ACTION_REGISTRY['apply_item_effects'].required_item_capabilities_any_of)} require item_body apply_item_effects: apply_item_effects is the only active binding that enables item resource/buff/mobility effects. A spawn_entity or use_item_body binding alone does not heal or apply those effects. To heal and spawn in one use, author an apply_item_effects binding plus an explicit item_body.on_use spawn_entity_on_event action. "
    "Return a strict JSON object with double-quoted JSON object keys and string values; no trailing commas or JavaScript expressions. No markdown or reasoning."
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


def _prepare_parsed_author_item(parsed: Mapping[str, Any]) -> dict[str, Any]:
    canonical = project_provider_author_item_to_local(dict(parsed))
    if not isinstance(canonical, dict):
        raise PlannerUnavailable("Gameplay Author returned a non-object after provider projection")
    return copy.deepcopy(canonical)


def validate_final_runtime_wire_boundary(data: dict[str, Any]) -> dict[str, Any]:
    report = validate_runtime_wire(data)
    debug = data.setdefault("debug", {})
    debug["finalRuntimeProgramWireGate"] = bounded_json_dumps(report, max_chars=12000)
    if not report.get("ok"):
        raise PlannerUnavailable(
            "final low-level runtime wire rejected: "
            + "; ".join(f"{row.get('path')}: {row.get('message')}" for row in report.get("errors", [])[:12])
        )
    return report


def build_initial_author_request(
    a: dict[str, Any],
    b: dict[str, Any],
    ca: dict[str, Any],
    cb: dict[str, Any],
    key: str,
    *,
    model_name: str | None = None,
) -> tuple[dict[str, Any], str, str]:
    payload = build_llm_author_payload(a, b, ca, cb, key)
    selected_model = model_name or resolve_llm_model()
    system = _AUTHOR_SYSTEM + llm_reasoning_system_suffix(selected_model)
    user_content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    request = {
        "model": selected_model,
        "messages": [
            stage_chat_message("system", "item_author_contract", system),
            stage_chat_message("user", "recipe_context", user_content),
        ],
        "temperature": env_float("INFINI_LLM_TEMPERATURE", 0.38, lo=0.0, hi=1.2),
        "response_format": llm_json_response_format(
            "infini_low_level_runtime_author",
            schema=author_item_provider_response_schema(),
            strict=True,
            auto_preference="json_schema",
        ),
    }
    request = apply_llm_common_options(request, model_name=selected_model)
    request = apply_minimum_reasoning_effort(request, model_name=selected_model, minimum="medium")
    return request, user_content, system


def _repair_malformed_author_json(
    *,
    malformed_raw_text: str,
    parse_error: BaseException,
    original_recipe_context: str,
    model_name: str,
) -> tuple[dict[str, Any], str]:
    """Spend the one Gameplay Repair call on syntax-only Author recovery."""

    repair_context = {
        "schema": "infini.gameplay-author-format-repair.v1",
        "task": "Repair JSON syntax only and return the same complete Gameplay Author object.",
        "rules": [
            "Preserve every recoverable authored value, id, capability, parameter, binding transaction, concept, and realization from malformedRawText.",
            "Do not redesign, add, drop, replace, normalize, or reinterpret gameplay. This call repairs only JSON syntax/container damage.",
            "Call params must use allowedCallParamsReadOnly for their exact fn; do not invent undeclared params even if they sound plausible.",
            "Use originalRecipeContext only to disambiguate damaged syntax; never introduce a choice absent from malformedRawText.",
            "Return exactly one strict full Author JSON object with no markdown or prose.",
        ],
        "parseError": f"{type(parse_error).__name__}: {parse_error}",
        "malformedRawText": malformed_raw_text,
        "originalRecipeContext": json.loads(original_recipe_context),
        "allowedCallParamsReadOnly": {
            name: sorted(cap.params) for name, cap in CAPABILITY_REGISTRY.items() if cap.prompt_visible
        },
        "requiredJsonShape": author_item_prompt_shape_card(),
    }
    user_content = json.dumps(repair_context, ensure_ascii=False, separators=(",", ":"))
    system = (
        "You are the single conditional Gameplay Format Repair for InfiniCrafterLocal. "
        "Repair only JSON syntax/container damage in malformedRawText. Preserve the Author's exact recoverable design and executable choices; "
        "do not reauthor or complete missing gameplay; do not invent undeclared params. "
        "Use allowedCallParamsReadOnly to check each call's fn. Return strict full Author JSON only."
    )
    messages = [
        stage_chat_message("system", "author_repair_contract", system + llm_reasoning_system_suffix(model_name)),
        stage_chat_message("user", "author_repair_context", user_content),
    ]
    request = apply_llm_common_options({
        "model": model_name,
        "messages": messages,
        "temperature": env_float("INFINI_LLM_REPAIR_TEMPERATURE", 0.12, lo=0.0, hi=0.8),
        "response_format": llm_json_response_format(
            "infini_low_level_runtime_author_format_repair",
            schema=author_item_provider_response_schema(),
            strict=True,
            auto_preference="json_schema",
        ),
    }, model_name=model_name)
    request = apply_minimum_reasoning_effort(request, model_name=model_name, minimum="medium")
    trace_event(
        "prompt", "LLM:gameplay_repair", "Conditional Gameplay Author format-repair request",
        {"provider": active_llm_provider(), "model": model_name, "malformedChars": len(malformed_raw_text)},
        prompt=messages,
    )
    try:
        raw = llm_chat_json(with_llm_stage(request, "author_repair"), timeout=env_int("INFINI_LLM_TIMEOUT", 95))
        content = str(raw["choices"][0]["message"]["content"])
        trace_event(
            "response", "LLM:gameplay_repair", "Conditional Gameplay Author format-repair response",
            {"model": model_name, "chars": len(content), "transport": raw.get("_debug", {})},
            response=content,
        )
        parsed = parse_first_valid_llm_json(content)
        if not isinstance(parsed, Mapping):
            raise PlannerUnavailable("Gameplay Author format Repair returned non-object JSON")
        recovered = recover_object_with_trailing_commas(malformed_raw_text)
        if recovered is None:
            raise PlannerUnavailable("Gameplay format Repair cannot prove recoverable authored fields")
        if _prepare_parsed_author_item(recovered) != _prepare_parsed_author_item(parsed):
            raise PlannerUnavailable("Gameplay format Repair changed recoverable authored fields")
        return _prepare_parsed_author_item(parsed), content
    except PlannerUnavailable:
        raise
    except Exception as exc:
        raise PlannerUnavailable(f"Gameplay Author format Repair failed: {exc!r}") from exc


def try_llm_plan(
    a: dict[str, Any],
    b: dict[str, Any],
    ca: dict[str, Any],
    cb: dict[str, Any],
    key: str,
) -> dict[str, Any] | None:
    """Perform exactly one baseline Gameplay Author call.

    Validation failure is propagated to the one conditional Gameplay Repair owned by
    ``combine_pipeline.compile_and_validate_authored_runtime``. This function never
    retries and never asks code to select a replacement capability.
    """
    if not USE_LLM:
        return None
    model_name = resolve_llm_model()
    request, user_content, system = build_initial_author_request(a, b, ca, cb, key, model_name=model_name)
    try:
        trace_event(
            "prompt",
            "LLM:gameplay_author",
            f"Gameplay Author request: {name_of(a)} + {name_of(b)}",
            {
                "provider": active_llm_provider(),
                "model": model_name,
                "responseFormat": bool(request.get("response_format")),
                "messages": _trace_message_summary(request.get("messages")),
            },
            prompt=user_content,
        )
        raw = llm_chat_json(with_llm_stage(request, "planner"), timeout=env_int("INFINI_LLM_TIMEOUT", 95))
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
            item = _prepare_parsed_author_item(parsed)
        except (ValueError, TypeError, json.JSONDecodeError) as parse_error:
            item, format_repair_content = _repair_malformed_author_json(
                malformed_raw_text=str(content),
                parse_error=parse_error,
                original_recipe_context=user_content,
                model_name=model_name,
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
            "llmHistoryStored": ATTRIBUTED_PLANNER_HISTORY_KIND,
        })
        if format_repaired:
            debug["gameplayFormatRepairRawOutput"] = format_repair_content[:12000]
        accounting = _stage_accounting(item)
        accounting["gameplayAuthorCalls"] = 1
        accounting["gameplayRepairCalls"] = 1 if format_repaired else 0
        item["_llmHistory"] = attributed_planner_history(
            system,
            user_content,
            format_repair_content or str(content),
        )
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
    rows = failure_report.get("errors")
    if isinstance(rows, list):
        return [copy.deepcopy(row) for row in rows if isinstance(row, dict)][:40]
    validation = failure_report.get("validation")
    if isinstance(validation, Mapping) and isinstance(validation.get("errors"), list):
        return [copy.deepcopy(row) for row in validation["errors"] if isinstance(row, dict)][:40]
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
    ca: Mapping[str, Any],
    cb: Mapping[str, Any],
    *,
    failure_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the finite model-facing dossier for one Gameplay Repair call.

    This is intentionally a pure projection.  It contains exact invalid
    fragments, the local read-only dependency neighbourhood, a compact global
    id index, and only the blocker capability cards that can solve the current
    deterministic errors without rewriting frozen context.
    """

    _ = (ca, cb)
    exact_errors = _repair_error_rows(failure_report)
    scope = build_runtime_repair_scope(current, exact_errors)
    fragments = runtime_repair_fragments(current, scope)
    blocker_plan = scope.get("blockerPlan") if isinstance(scope.get("blockerPlan"), Mapping) else {}

    def cards(names: Any) -> list[dict[str, Any]]:
        return [
            CAPABILITY_REGISTRY[name].prompt_card()
            for name in names or []
            if name in CAPABILITY_REGISTRY
        ]

    return {
        "schema": GAMEPLAY_REPAIR_DOSSIER_SCHEMA,
        "task": "Repair only the deterministic mutable scope of this low-level runtime program.",
        "rules": [
            "Return exactly the repair patch schema; never return the full item.",
            "Every upsert entry must be a complete schema-valid node. For callsUpsert copy id, fn, target, and the complete params object from brokenFragments, changing only permitted fields; never omit unchanged required fields.",
            "Fix only exact fieldPermissions paths and explicitly allowed blocker/dependency nodes; do not add unrelated optional design fields.",
            "Extra rewrites of frozen values or independent ids are ignored rather than cancelling a useful repair.",
            "For each exact repairScope.deletable.callPropertyKeys entry that must be removed, emit the matching callPropertyKeysDelete {callId,key}; a note claiming removal does not mutate the program.",
            "Use create permissions only for the exact blocker or its declared support dependency.",
            "Keep stable ids when repairing existing nodes; use a new id only for an explicitly allowed missing node.",
            "immutableProgramIndex.entities[*].id is the exact allowlist for every target and entity-reference value that points to an existing entity in this patch; never carry an id from another item. When repairScope.create.calls.allowedTargetKinds is non-empty, a new call may instead target an id emitted exactly once in entitiesUpsert whose kind is listed there; use that same new id consistently and do not invent any other target.",
            "Do not introduce a weapon family, archetype, semantic root, or code-authored default.",
            "Resolve every exact error and re-check references, target kinds, inputs, cycles, and budgets.",
            "Always return realizationReplacement after considering the patch. It must be a literal post-repair execution report, obey runtimeExecutionTruth, describe only the actually repaired program, and rebuild selfEvaluation.planVsProgram and selfEvaluation.programVsReport from the final patch result; it is never deterministically synthesized.",
            f"When repairTransactions.{PRIMARY_ENTITY_SELECTION_FIELD}.allowed is true, set {PRIMARY_ENTITY_SELECTION_FIELD} to exactly one listed candidate; Lowery materializes technical wire roles from that exact authored identity.",
            "For each repairRequirements row with requiredBindingUpdates, emit every listed existing binding exactly once using one of its complete allowed transactions; mustApplyAll means these updates are one coupled repair, not alternatives. When mustCreateExactlyOne is true, emit exactly one allowedBindingTransactions row and it must have a new id. When mustChooseExactlyOne is true without mustCreateExactlyOne, emit exactly one complete allowedBindingTransactions choice: an existing id is eligible only when it appears in that row's allowedExistingBindingIds and its complete tuple is projected by bindingAlternatives; a new id is eligible only when repairScope.create.bindings permits it. Global mutability never authorizes an id for another requirement; never update every listed lane.",
            "For each repairTransactions.exclusiveInputSelections group, either retarget/delete conflicting bindings through exact fieldPermissions or emit one exclusiveInputSelections row choosing the keepBindingId; do not do both after the conflict is resolved.",
            "For each repairScope.eventAlternatives row, choose one complete alternative: author its exact event plus every listed required call/binding in the same patch, and emit no support from unselected alternatives. The engine never chooses or inserts an event producer for you.",
        ],
        "runtimeVersions": {
            "authorSchema": RUNTIME_PROGRAM_SCHEMA,
            "apiVersion": RUNTIME_PROGRAM_API_VERSION,
        },
        "parents": {
            "a": {"packet": raw_parent_card_for_llm(dict(a))},
            "b": {"packet": raw_parent_card_for_llm(dict(b))},
        },
        "acceptedItemContext": {
            "name": current.get("name"),
            "category": current.get("category"),
            "realization": copy.deepcopy(current.get("realization") or {}),
        },
        "exactValidationErrors": exact_errors,
        "failureStage": str(failure_report.get("stage") or "runtime_program_validation"),
        "repairScope": scope,
        "runtimeExecutionTruth": realization_execution_truth_for_llm(),
        "requiredJsonShape": author_item_repair_prompt_shape_card(),
        "brokenFragments": fragments["broken"],
        "brokenFragmentsByIndex": fragments["brokenByIndex"],
        "validDependencyFragments": fragments["dependencyContext"],
        "immutableProgramIndex": fragments["immutableIndex"],
        "blockerCapabilities": cards(blocker_plan.get("directCapabilityNames")),
        "supportingCapabilities": cards(blocker_plan.get("supportingCapabilityNames")),
        "existingBrokenCapabilityCards": cards(blocker_plan.get("existingBrokenCapabilityNames")),
    }


def repair_author_item_after_failure(
    current: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    ca: dict[str, Any],
    cb: dict[str, Any],
    key: str,
    *,
    failure_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Perform one conditional Gameplay Repair over a deterministic node scope.

    The model receives only invalid nodes, exact missing-dependency permissions,
    and immutable summaries/full dependency fragments.  The model may return a
    complete broken node, but deterministic merge changes only exact broken paths;
    already-valid old values remain frozen and independent nodes are ignored.
    """
    if not USE_LLM:
        raise PlannerUnavailable("Gameplay Repair required but LLM is disabled")
    model_name = resolve_llm_model()
    repair_context = build_gameplay_repair_dossier(
        current, a, b, ca, cb, failure_report=failure_report,
    )
    exact_errors = copy.deepcopy(repair_context["exactValidationErrors"])
    scope = copy.deepcopy(repair_context["repairScope"])
    if scope.get("nonRepairableErrors"):
        raise PlannerUnavailable(
            "Gameplay validation exposed a registry/runtime defect that LLM Repair must not hide: "
            + bounded_json_dumps(scope["nonRepairableErrors"], max_chars=5000)
        )
    repair_user = json.dumps(repair_context, ensure_ascii=False, separators=(",", ":"))
    repair_system = (
        "You are the conditional Gameplay Repair for InfiniCrafterLocal. Close exactValidationErrors through repairScope permissions, repairTransactions, eventAlternatives and repairScope.blockerPlan; never repair the whole item. "
        f"{PRIMARY_REPAIR_SYSTEM_RULE} For each exclusive-input transaction, either repair the conflicting binding input/delete path or choose one keepBindingId; do not emit a redundant choice after retargeting resolves the conflict. "
        "Every target or entity-reference id that points to an existing entity must be copied from immutableProgramIndex.entities[*].id; never carry an id from another item. When repairScope.create.calls.allowedTargetKinds is non-empty, a new call target may instead use an id emitted exactly once in entitiesUpsert whose kind is listed there; use that same new id consistently and never invent any other target. "
        "For every bindingId in repairScope.bindingAlternatives that you update, copy one complete input/action/target tuple verbatim into bindingsUpsert; never cross-product fields from different alternatives. When a repairRequirement sets mustChooseExactlyOne without mustCreateExactlyOne, emit exactly one complete allowed binding transaction: an existing id must be listed by that exact row's allowedExistingBindingIds and bindingAlternatives; a new id must be permitted by create.bindings. Global mutability does not let one blocker satisfy another; never update all candidate bindings. "
        "For every repairScope.eventAlternatives row, choose one complete event alternative, author every listed required call/binding in the same patch, and emit no call/binding from unselected alternatives; no event dependency is inserted automatically. "
        "Every llmRepairable repairRequirement whose requiredOneOfCapabilities is non-empty must be absent after the patch. An independently authorized delete/retarget may close it structurally; otherwise callsUpsert must patch or create one complete listed call on an affected target. A note claiming closure does not satisfy it. "
        "For an exact shape_additional_property under calls[*].params, remove only the matching repairScope.deletable.callParamKeys entry: either emit callParamKeysDelete or omit that key from the complete callsUpsert row. "

        "Omit unchanged root patch fields: absent optional arrays/metadataPatch mean no change; note and realizationReplacement are required. Do not copy dossier keys into the patch. Every upsert row must be complete and schema-valid; copy every unchanged required field from brokenFragments and modify only permitted paths. "
        "Deterministic merge will freeze already-valid old values and accept the exact broken or mandatory missing fields. Independent valid nodes and optional unreported fields are read-only; extra "
        "rewrites are ignored. New nodes are allowed only by the exact blocker create policy. Return strict patch JSON only."
    )
    messages = [
        stage_chat_message("system", "author_repair_contract", repair_system + llm_reasoning_system_suffix(model_name)),
        stage_chat_message("user", "author_repair_context", repair_user),
    ]
    request = apply_llm_common_options({
        "model": model_name,
        "messages": messages,
        "temperature": env_float("INFINI_LLM_REPAIR_TEMPERATURE", 0.12, lo=0.0, hi=0.8),
        "response_format": llm_json_response_format(
            "infini_low_level_runtime_repair",
            schema=author_item_provider_repair_response_schema(),
            strict=True,
            auto_preference="json_schema",
        ),
    }, model_name=model_name)
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
        prompt=messages,
    )
    try:
        raw = llm_chat_json(with_llm_stage(request, "author_repair"), timeout=env_int("INFINI_LLM_TIMEOUT", 95))
        content = raw["choices"][0]["message"]["content"]
        trace_event(
            "response",
            "LLM:gameplay_repair",
            "Conditional Gameplay Repair response",
            {"model": model_name, "chars": len(str(content)), "transport": raw.get("_debug", {})},
            response=content,
        )
        parsed = parse_first_valid_llm_json(content)
        patch = project_provider_nullable_optionals_to_local(parsed)
        if not isinstance(patch, Mapping) or not isinstance(patch.get("realizationReplacement"), Mapping):
            raise PlannerUnavailable("Gameplay Repair must return a non-null realizationReplacement")
        report = strict_author_item_repair_report(patch)
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
        repaired.setdefault("debug", {})["gameplayRepairRawPatch"] = copy.deepcopy(patch)
        repaired["debug"]["gameplayRepairPatch"] = copy.deepcopy(filtered_patch)
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


def call_llm_vfx_director(
    system: str,
    user: dict[str, Any],
    max_tokens: int,
    temperature: float,
    timeout: int,
    messages: list[dict[str, str]] | None = None,
) -> dict[str, Any] | MalformedVfxDirectorOutput | None:
    """Transport-only helper used by the finite VFX Director stage."""
    if not USE_LLM:
        return None
    model_name = resolve_llm_model()
    stage_name = "vfx_repair" if messages and any(message.get("name") == "vfx_repair_contract" for message in messages) else "vfx_director"
    output_schema = user.get("outputSchema") if isinstance(user.get("outputSchema"), Mapping) else None
    request = {
        "model": model_name,
        "messages": messages or [
            stage_chat_message("system", "vfx_director_contract", system + llm_reasoning_system_suffix(model_name)),
            stage_chat_message("user", "vfx_director_context", json.dumps(user, ensure_ascii=False, separators=(",", ":"))),
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": llm_json_response_format(
            "infini_vfx_repair_patch" if stage_name == "vfx_repair" else "infini_vfx_runtime_events",
            schema=output_schema,
            strict=True,
            auto_preference="json_schema",
        ) if output_schema else {"type": "json_object"},
    }
    request = apply_llm_common_options(request, model_name=model_name, default_max_tokens=max_tokens)
    raw = llm_chat_json(with_llm_stage(request, stage_name), timeout=timeout)
    content = raw["choices"][0]["message"]["content"]
    try:
        parsed = parse_first_valid_llm_json(content)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return MalformedVfxDirectorOutput(raw_text=str(content), error=f"{type(exc).__name__}: {exc}")
    return parsed if isinstance(parsed, dict) else None


__all__ = [
    "GAMEPLAY_REPAIR_DOSSIER_SCHEMA",
    "build_gameplay_repair_dossier",
    "build_initial_author_request",
    "call_llm_vfx_director",
    "repair_author_item_after_failure",
    "try_llm_plan",
    "validate_final_runtime_wire_boundary",
]
