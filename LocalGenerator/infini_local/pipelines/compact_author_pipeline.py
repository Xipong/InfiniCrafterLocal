from __future__ import annotations

"""Explicit opt-in transport for the versioned compact Author API.

The existing generator keeps its current syntax. Callers choose this entrypoint
and compile with compact_api, so a parse error can never switch syntax versions.
"""

from copy import deepcopy
import json
from typing import Any, Mapping

from infini_local.core.env_utils import env_int
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.llm_json_tools import parse_first_valid_llm_json
from infini_local.core.llm_prompt_cache import json_prefix_chars, with_prompt_cache_prefix
from infini_local.core.llm_stage_messages import stage_chat_message
from infini_local.core.runtime_authoring.compact_api import apply_compact_repair, build_compact_repair_scope, compact_repair_schema
from infini_local.core.runtime_authoring.compact_notation import COMPACT_AUTHOR_SCHEMA, compact_author_item_schema
from infini_local.core.runtime_authoring.program_schema import assert_bounded_author_input
from infini_local.pipelines.author_item_contract import (
    _provider_strict_projection, author_item_prompt_shape_card, project_provider_nullable_optionals_to_local,
    provider_nullable_transport_rule,
)
from infini_local.pipelines.llm_authoring_pipeline import _AUTHOR_CACHE_PREFIX_KEYS, _effective_response_format, build_initial_author_request
from infini_local.pipelines.llm_transport import apply_llm_common_options, apply_minimum_reasoning_effort, llm_chat_json, llm_json_response_format, with_llm_stage


def compact_author_prompt_shape_card() -> dict[str, Any]:
    card = author_item_prompt_shape_card()
    program = card["runtimeProgram"]
    program["schema"] = COMPACT_AUTHOR_SCHEMA
    program.pop("calls")
    program["callGroups"] = [
        {"calls": [{"id": "stable_call_id", "fn": "capability whose targets is exactly [item_body]", "params": "exact capability parameters; absent for a zero-argument fn"}]},
        {"target": "exact declared entity ID", "calls": [{"id": "stable_call_id", "fn": "any other public capability", "params": "exact capability parameters; absent for a zero-argument fn"}]},
    ]
    program["bindings"] = [
        {"id": "stable_binding_id", "input": "equipped"},
        {"id": "stable_binding_id", "input": "hold", "action": {"targetId": "exact spawn target"}},
        {
            "id": "stable_binding_id", "input": "primary_use|alternate_use",
            "action": {"kind": "selected catalog action", "targetId": "only spawn_entity; otherwise omit", "placementCallId": "only place_item; otherwise omit"},
            "stackCost": "choose 0|1 except place_item, which omits the field and costs 1",
            "contactDamage": "choose true|false except place_item, which omits the field and forbids contact",
        },
    ]
    row = card["realization"]["selfEvaluation"]["planVsProgram"]["actionChecks"][0]
    row.pop("plannedIntent")
    row["plannedActionIndex"] = "explicit zero-based index into concept.plannedPlayerActions; null iff result=added"
    card["notationRules"] = [
        "Exactly one explicitly authored item_body must exist before implicit item-only references can be resolved.",
        "callGroups are consecutive source ranges; expand group order then call order. Same target may occur in multiple separated groups.",
        "Never renumber IDs, merge nonconsecutive groups, share params, infer a primary entity or infer gameplay from category/name.",
        "Binding policy fields are flat. Omitted variant constants are forbidden as extra fields, not silently overwritten.",
        "Catalog target restrictions still apply. Item-only calls/actions omit targets; all other call groups/actions choose exact targets.",
        "A no-argument call has no params property. Optional parameters with a registered neutral default retain that exact full-Author omission meaning.",
        "Choose plannedActionIndex explicitly even if two planned intents have identical text. Concept order is frozen during Repair.",
    ]
    return card


def compact_author_provider_schema() -> dict[str, Any]:
    return _provider_strict_projection(compact_author_item_schema())


def build_compact_author_request(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str, *, model_name: str | None = None) -> tuple[dict[str, Any], str, str]:
    request, user, system = build_initial_author_request(a, b, ca, cb, key, model_name=model_name)
    payload = json.loads(user)
    payload["requiredJsonShape"] = compact_author_prompt_shape_card()
    catalog = payload["runtimeCapabilityContract"]["catalog"]
    catalog["authoringSchema"] = COMPACT_AUTHOR_SCHEMA
    guide = catalog["fieldGuide"]
    guide["bindingTarget"] = guide["bindingTarget"].replace(
        "Every binding owns one usePolicy with action, stackCost and contactDamage; no call/global shadows it.",
        "Every compact binding owns its flat action, stackCost and contactDamage; exact variant constants are omitted as requiredJsonShape states.")
    guide["compactCallGroups"] = payload["requiredJsonShape"]["notationRules"]
    def project_catalog_paths(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: project_catalog_paths(child) for key, child in value.items()}
        if isinstance(value, list):
            return [project_catalog_paths(child) for child in value]
        if isinstance(value, str):
            return value.replace("bindings[].usePolicy.", "bindings[].").replace("binding usePolicy.", "binding ").replace("usePolicy.contactDamage", "contactDamage")
        return value
    payload["runtimeCapabilityContract"]["catalog"] = project_catalog_paths(catalog)
    # Source facts and parameter cards are reused exactly; only the output syntax
    # declaration and its one wrapper sentence differ in this explicit version.
    user = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    request["messages"][1]["content"] = user
    request["response_format"] = llm_json_response_format(
        "infini_compact_runtime_author", schema=compact_author_provider_schema, strict=True, auto_preference="json_schema")
    request = with_prompt_cache_prefix(request, message_index=1,
        prefix_chars=json_prefix_chars(payload, _AUTHOR_CACHE_PREFIX_KEYS), static_instruction_prefix=True)
    return request, user, system


def accept_compact_author_response(value: Mapping[str, Any], *, response_format: Mapping[str, Any] | None = None) -> dict[str, Any]:
    schema = compact_author_item_schema()
    assert_bounded_author_input(value, schema=schema, authored_only=False)
    result = project_provider_nullable_optionals_to_local(value, schema, response_format=response_format)
    # Strict shape is reported at admission/Repair, not repaired by the decoder.
    if not isinstance(result, dict) or not isinstance(result.get("runtimeProgram"), dict) or result["runtimeProgram"].get("schema") != COMPACT_AUTHOR_SCHEMA:
        raise PlannerUnavailable("The compact entrypoint requires its explicit Author schema version")
    if set(result) - set(schema["properties"]):
        raise PlannerUnavailable("The compact entrypoint rejects unknown Author root fields")
    return result


def request_compact_author(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str, *, model_name: str | None = None) -> dict[str, Any]:
    """One explicit model call; no syntax-version fallback or hidden retries."""
    request, _, _ = build_compact_author_request(a, b, ca, cb, key, model_name=model_name)
    raw = llm_chat_json(with_llm_stage(request, "planner"), timeout=env_int("INFINI_LLM_TIMEOUT", 95))
    parsed = parse_first_valid_llm_json(raw["choices"][0]["message"]["content"])
    return accept_compact_author_response(parsed, response_format=_effective_response_format(request, raw))


def build_compact_repair_request(document: Mapping[str, Any], *, model_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    scope = build_compact_repair_scope(document)
    payload = {"authorSchema": COMPACT_AUTHOR_SCHEMA, "acceptedItemContext": deepcopy(dict(document)),
               "repairScope": scope, "requiredPatchSchema": compact_repair_schema()}
    request = {"model": model_name, "temperature": 0.12, "messages": [
        stage_chat_message("system", "author_repair_contract", "Repair only the exact permitted compact Author leaves by stable IDs. Preserve frozen values, source group order and concept ordering. No syntax version changes, source inference or invented runtime choices. Return the strict compact Repair patch only."),
        stage_chat_message("user", "author_repair_context", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
    ], "response_format": llm_json_response_format(
        "infini_compact_author_repair", schema=lambda: _provider_strict_projection(compact_repair_schema()), strict=True, auto_preference="json_schema")}
    request = apply_llm_common_options(request, model_name=model_name)
    request["messages"][0]["content"] += provider_nullable_transport_rule(request.get("response_format"))
    request = apply_minimum_reasoning_effort(request, model_name=model_name, minimum="medium")
    return request, scope


def accept_compact_repair_response(document: Mapping[str, Any], value: Mapping[str, Any], scope: Mapping[str, Any], *, response_format: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    patch = project_provider_nullable_optionals_to_local(value, compact_repair_schema(), response_format=response_format)
    return apply_compact_repair(document, patch, scope)


def request_compact_repair(document: Mapping[str, Any], *, model_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """One explicitly requested Repair call against a frozen source digest."""
    request, scope = build_compact_repair_request(document, model_name=model_name)
    raw = llm_chat_json(with_llm_stage(request, "author_repair"), timeout=env_int("INFINI_LLM_TIMEOUT", 95))
    parsed = parse_first_valid_llm_json(raw["choices"][0]["message"]["content"])
    return accept_compact_repair_response(document, parsed, scope, response_format=_effective_response_format(request, raw))
