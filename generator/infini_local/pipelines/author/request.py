from __future__ import annotations

import copy
import json
import math
from typing import Any, Mapping

from infini_local.core import llm_config
from infini_local.core.env_utils import env_float, env_int, env_str
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.generation_defaults import GENERATION_DEFAULTS
from infini_local.core.item_identity_tools import name_of, stable_hash
from infini_local.core.json_debug import bounded_json_dumps
from infini_local.core.llm_config import USE_LLM
from infini_local.core.llm_json_tools import parse_first_valid_llm_json, parse_llm_json_with_syntax_fix
from infini_local.core.llm_prompt_cache import with_instruction_segments
from infini_local.core.llm_stage_messages import (
    generation_art_direction,
    stage_accounting,
    stage_chat_message,
)
from infini_local.core.provider_schema import project_provider_nullable_optionals_to_local, provider_nullable_transport_rule
from infini_local.core.runtime_authoring.capability_registry import (
    CAPABILITY_REGISTRY,
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_PROGRAM_SCHEMA,
    STACK_COST_RULE,
)
from infini_local.core.runtime_authoring.program_schema import (
    GENERATED_ITEM_ROOT_FIELDS,
    PRIMARY_ENTITY_SELECTION_FIELD,
    author_item_response_schema,
    strict_author_shape_report,
    apply_repair_patch,
    assert_bounded_author_input,
    strict_repair_structure_report,
)
from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
from infini_local.core.runtime_authoring.repair.fragments import runtime_repair_fragments
from infini_local.core.runtime_authoring.repair.schema import runtime_repair_schema_capabilities
from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.pipelines.author.item_contract import (
    RUNTIME_ROW_SHAPE_RULE,
    author_item_generation_provider_schema,
    author_item_provider_repair_response_schema,
    author_item_repair_prompt_shape_card,
    author_item_repair_response_schema,
    project_provider_author_item_to_local,
)
from infini_local.pipelines.author.prompt import (
    build_llm_author_payload,
    realization_execution_truth_for_llm,
    runtime_units_for_llm,
    sharp_engine_fn_catalog_for_llm,
    source_wire_units_for_llm,
)
from infini_local.pipelines.context.parent_stage import parent_context_for_stage
from infini_local.pipelines.context.cards import raw_parent_card_for_llm
from infini_local.pipelines.transport.client import (
    llm_chat_json,
    resolve_llm_model,
)
from infini_local.pipelines.transport.profiles import active_llm_provider
from infini_local.pipelines.transport.provider_wire import (
    apply_llm_common_options,
    effective_response_format,
    llm_json_response_format,
    llm_reasoning_system_suffix,
    with_llm_stage,
)
from infini_local.storage.trace_runtime import log_event, trace_event, trace_stage_request
from infini_local.storage.trace_tools import trace_message_summary

# Diagnostic threshold only; never an admission limit or a truncation target.
AUTHOR_CONTEXT_WARN_CHARS = 350_000

_AUTHOR_CACHE_PREFIX_KEYS = (
    "priorityHeader", "runtimeProgramInvariants",
    "runtimeCapabilityContract", "requiredJsonShape",
)
_REPAIR_CACHE_PREFIX_KEYS = ("schema", "task", "rules", "runtimeVersions", "runtimeExecutionTruth")


_AUTHOR_SYSTEM = (
    "You are Gameplay Author for InfiniCrafterLocal, a Terraria (tModLoader) item generator. "
    "Return one JSON object matching requiredJsonShape and the capability catalog. "
    "Implement the item's gameplay in runtimeProgram."
)


def _item_language_instruction() -> str:
    return "\nНазвание и описание предмета пиши на русском языке." if llm_config.LANGUAGE == "ru" else ""


def _prepare_parsed_author_item(
    parsed: Mapping[str, Any], *, response_format: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    assert_bounded_author_input(parsed, authored_only=False)
    canonical = project_provider_author_item_to_local(dict(parsed), response_format=response_format)
    if not isinstance(canonical, dict):
        raise PlannerUnavailable("Gameplay Author returned a non-object after provider projection")
    # Only engine code may introduce the generated-item envelope. Its later
    # Author projection deliberately omits metadata, so reject provider-owned
    # versions here, before assigning identity or trusting debug/accounting.
    reserved = canonical.keys() & (GENERATED_ITEM_ROOT_FIELDS - author_item_response_schema()["properties"].keys())
    if reserved:
        report = strict_author_shape_report(canonical, authored_only=False)
        raise PlannerUnavailable(
            "Gameplay Author supplied engine-owned fields: " + ", ".join(sorted(reserved))
            + "; raw Author shape rejected: " + bounded_json_dumps(report, max_chars=2000)
        )
    return copy.deepcopy(canonical)


def _gameplay_repair_temperature() -> float:
    """Blank/invalid values use the scoped Repair default, never planner temperature."""
    default = 0.12
    raw = env_str("INFINI_LLM_REPAIR_TEMPERATURE")
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
    system = _AUTHOR_SYSTEM + _item_language_instruction() + llm_reasoning_system_suffix(selected_model)
    user_content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(user_content) >= AUTHOR_CONTEXT_WARN_CHARS:
        log_event("warn", f"Author context is {len(user_content)} characters (warning threshold {AUTHOR_CONTEXT_WARN_CHARS}); continuing without truncation", {
            "stage": "author", "contextChars": len(user_content),
            "warningThresholdChars": AUTHOR_CONTEXT_WARN_CHARS,
        })
    request = {
        "model": selected_model,
        "messages": [
            stage_chat_message("system", "item_author_contract", system),
            stage_chat_message("user", "recipe_context", user_content),
        ],
        "temperature": env_float("INFINI_LLM_TEMPERATURE", float(GENERATION_DEFAULTS["INFINI_LLM_TEMPERATURE"]), lo=0.0, hi=1.2),
        "response_format": llm_json_response_format(
            "infini_low_level_runtime_author",
            schema=author_item_generation_provider_schema,
            strict=True,
            auto_preference="json_schema",
        ),
    }
    request = apply_llm_common_options(request, model_name=selected_model)
    system += provider_nullable_transport_rule(request.get("response_format"))
    request["messages"][0]["content"] = system
    request = with_instruction_segments(request, payload, _AUTHOR_CACHE_PREFIX_KEYS)
    return request, user_content, system


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
    request, _, _ = build_initial_author_request(a, b, key, model_name=model_name)
    try:
        trace_stage_request("gameplay_author", key, request,
            prompt_title=f"Gameplay Author request: {name_of(a)} + {name_of(b)}",
            prompt_payload={
                "provider": active_llm_provider(), "model": model_name,
                "responseFormat": bool(request.get("response_format")),
                "messages": trace_message_summary(request.get("messages")),
            })
        raw = llm_chat_json(with_llm_stage(request, "planner"), timeout=env_int("INFINI_LLM_TIMEOUT", int(GENERATION_DEFAULTS["INFINI_LLM_TIMEOUT"])))
        content = raw["choices"][0]["message"]["content"]
        trace_event(
            "response",
            "LLM:gameplay_author",
            "Gameplay Author response",
            {"provider": active_llm_provider(), "model": model_name, "chars": len(str(content)), "transport": raw.get("_debug", {})},
            response=content,
        )
        parsed, syntax_fix = parse_llm_json_with_syntax_fix(content)
        item = _prepare_parsed_author_item(parsed, response_format=effective_response_format(request, raw))
        if syntax_fix:
            trace_event("fix", "LLM:gameplay_author", "Author JSON syntax recovered locally", syntax_fix)
        item["id"] = "g_" + stable_hash(key, content, length=16)
        item["recipeKey"] = key
        item["schemaVersion"] = 5
        item["parentA"] = name_of(a)
        item["parentB"] = name_of(b)
        item["sourceMode"] = "generated"
        debug = item["debug"] = {}
        debug.update({
            "planner": "llm_low_level_runtime_author",
            "model": model_name,
            "promptMode": "low_level_runtime_program_v5",
            "runtimeAuthorSchema": RUNTIME_PROGRAM_SCHEMA,
            "runtimeApiVersion": RUNTIME_PROGRAM_API_VERSION,
            "llmRawOutput": str(content)[:12000],
        })
        if syntax_fix:
            debug["gameplaySyntaxFix"] = syntax_fix
        accounting = stage_accounting(item)
        accounting["gameplayAuthorCalls"] = 1
        accounting["gameplayRepairCalls"] = 0
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
    concept/runtimeProgram for the complete realizationReplacement. Blocker
    cards stay local; mutable function identities also receive the replacement
    catalog. Visibility grants no edits beyond the exact repair scope.
    """

    assert_bounded_author_input(current)
    exact_errors = _repair_error_rows(failure_report)
    scope = build_runtime_repair_scope(current, exact_errors)
    fragments = runtime_repair_fragments(current, scope)
    blocker_plan = scope.get("blockerPlan") if isinstance(scope.get("blockerPlan"), Mapping) else {}
    grammar_names = runtime_repair_schema_capabilities(scope)
    documented_names = {
        name
        for key in ("directCapabilityNames", "supportingCapabilityNames", "existingBrokenCapabilityNames")
        for name in blocker_plan.get(key) or []
    }

    attack_source_memo: dict[str, Any] = {}
    parents = {
        "a": {"packet": raw_parent_card_for_llm(dict(a), attack_source_memo=attack_source_memo)},
        "b": {"packet": raw_parent_card_for_llm(dict(b), attack_source_memo=attack_source_memo)},
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
            "Return only a JSON patch matching requiredJsonShape, not the item or dossier. note is required; omit unchanged root fields. Omission means no change.",
            "Each upsert is a complete schema-valid node. Copy existing nodes from readOnlySourceFragments.brokenFragments, preserving required values, accepted optional values and absences outside exact fieldPermissions. Do not add or remove target/params merely to match an example. Extra frozen rewrites are ignored.",
            RUNTIME_ROW_SHAPE_RULE,
            STACK_COST_RULE,
            "Compose with low-level capabilities; do not introduce a weapon family, archetype, semantic root, or code-authored default.",
            "New nodes are allowed only by the exact blocker/dependency create policy and must satisfy the full capability requirements. Keep existing ids; use new ids only for permitted missing nodes. Defaults describe Author omission, not Repair edits.",
            "Existing target/entity references come from immutableProgramIndex.entities[*].id. Where create.calls.allowedTargetKinds permits a new target, emit it exactly once in entitiesUpsert with an allowed kind and use that same id consistently.",
            "Remove exact deletable.callPropertyKeys through callPropertyKeysDelete {callId,key}. For exact deletable.callParamKeys, use callParamKeysDelete or omit the invalid key from its complete callsUpsert row.",
            "Binding updates use complete input/action/target transactions from bindingAlternatives, never a cross-product of their fields. Each repairRequirements row owns its allowed transactions and existing ids; permissions from another row do not apply.",
            "requiredBindingUpdates with mustApplyAll are coupled: emit every listed existing binding exactly once. mustCreateExactlyOne requires one allowed transaction with a new id. mustChooseExactlyOne without mustCreateExactlyOne requires one transaction: an existing id must be in that row's allowedExistingBindingIds and bindingAlternatives; a new id requires create.bindings permission.",
            f"When repairTransactions.{PRIMARY_ENTITY_SELECTION_FIELD}.allowed is true, choose exactly one listed candidate through {PRIMARY_ENTITY_SELECTION_FIELD}; the compiler derives technical wire roles from that identity.",
            "For an exclusiveInputSelections group, either resolve the conflict through permitted retarget/delete edits or emit one keepBindingId selection; a resolved conflict needs no redundant selection.",
            "For each repairScope.eventAlternatives row, choose one complete alternative: emit its exact event and every listed required call/binding together, with no support from unselected alternatives. The engine does not insert event producers.",
            "Close every llmRepairable repairRequirement. For requiredOneOfCapabilities, either an authorized structural delete/retarget closes the blocker or callsUpsert supplies one complete listed capability on an affected target. Notes do not change the program. Check references, kinds, inputs, cycles and budgets after the permitted edits.",
            "realizationReplacement is optional advisory context, never an acceptance requirement or observed test. Omit it or use null to leave the report unchanged; an object replaces it, including {} to clear it. acceptedItemContext.runtimeProgram is the read-only pre-repair source, including invalid fields. Describe only the program after permitted edits; prose and self-evaluation are not repair targets.",
        ],
        "runtimeVersions": {
            "authorSchema": RUNTIME_PROGRAM_SCHEMA,
            "apiVersion": RUNTIME_PROGRAM_API_VERSION,
        },
        "runtimeExecutionTruth": {
            **realization_execution_truth_for_llm(),
            "units": runtime_units_for_llm(include_source_units=False),
        },

        **parent_context_for_stage(parents, stage="author"),
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
        # Mutable function identities retain the full Author grammar. Reuse its
        # compact, self-contained catalog rather than repeating raw schemas or
        # leaving schema-free transports with unexplained replacement names.
        **({"replacementCapabilityCatalog": sharp_engine_fn_catalog_for_llm(include_source_units=False)}
           if set(grammar_names) - documented_names else {}),
        "requiredJsonShape": author_item_repair_prompt_shape_card(capability_names=grammar_names),
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
        "You are the conditional Gameplay Repair for InfiniCrafterLocal. "
        "Resolve exactValidationErrors within repairScope using the dossier rules and supplied alternatives. "
        "Preserve all accepted values and absences outside that scope. Return only the JSON patch defined by requiredJsonShape."
    )
    direction = generation_art_direction()
    art_context = ("\n\nArt direction is advisory and does not override the output contract, accepted gameplay or frozen fields. " + direction) if direction else ""
    messages = [
        stage_chat_message("system", "author_repair_contract", repair_system + _item_language_instruction() + art_context + llm_reasoning_system_suffix(model_name)),
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
    try:
        trace_stage_request("gameplay_repair", key, request, recipe_id=current.get("id"),
            prompt_title="Conditional node-scoped Gameplay Repair request",
            prompt_payload={"provider": active_llm_provider(), "model": model_name,
                            "errorCount": len(exact_errors),
                            "mutableCounts": {key: len(value) for key, value in (scope.get("mutable") or {}).items()}})
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
        accounting = stage_accounting(repaired)
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
