"""Provider request/response boundary for the finite VFX Director stage.

VFX grammar and frozen Repair contracts live in core.vfx; stage orchestration
lives in pipelines.vfx.stage. This transport adapter has
no dependency on Gameplay Author requests or gameplay acceptance.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from infini_local.core.llm_config import USE_LLM
from infini_local.core.llm_json_tools import parse_first_valid_llm_json
from infini_local.core.llm_prompt_cache import with_instruction_segments, with_schema_instruction_definitions
from infini_local.core.llm_stage_messages import stage_chat_message
from infini_local.core.vfx.contract import MalformedVfxDirectorOutput
from infini_local.core.vfx.materials import vfx_model_context, vfx_model_payload
from infini_local.core.vfx.schema import vfx_schema_instruction_paths
from infini_local.pipelines.transport.client import (
    llm_chat_json,
    resolve_llm_model,
)
from infini_local.pipelines.transport.provider_wire import (
    apply_llm_common_options,
    llm_json_response_format,
    llm_reasoning_system_suffix,
    with_llm_stage,
)
from infini_local.pipelines.vfx.prompt import VFX_PROMPT_STATIC_KEYS, VFX_REPAIR_PROMPT_STATIC_KEYS
from infini_local.storage.trace_runtime import trace_event, trace_stage_request


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
    user = vfx_model_context(user)
    if messages:
        messages = [dict(message) for message in messages]
        for message in messages:
            if message.get("name") == "vfx_repair_context":
                message["content"] = json.dumps(user, ensure_ascii=False, separators=(",", ":"))
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
    static_keys = VFX_REPAIR_PROMPT_STATIC_KEYS if stage_name == "vfx_repair" else VFX_PROMPT_STATIC_KEYS
    request = with_instruction_segments(request, user, static_keys)
    definition_paths = vfx_schema_instruction_paths(
        repair=stage_name == "vfx_repair", schema=output_schema if stage_name == "vfx_repair" else None,
    )
    if definition_paths:
        request = with_schema_instruction_definitions(request, "outputSchema", definition_paths)
    item = user.get("item") or {}
    recipe_id = item.get("id") if isinstance(item, Mapping) else None
    trace_event("prompt", "LLM:" + stage_name, "VFX stage request", {"recipeId": recipe_id}, prompt=request["messages"])
    trace_stage_request(stage_name, user.get("recipeKey"), request, recipe_id=recipe_id)
    raw = llm_chat_json(with_llm_stage(request, stage_name), timeout=timeout)
    content = raw["choices"][0]["message"]["content"]
    trace_event("response", "LLM:" + stage_name, "VFX stage response", {"recipeId": recipe_id}, response=content)
    try:
        parsed = parse_first_valid_llm_json(content)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return MalformedVfxDirectorOutput(raw_text=str(content), error=f"{type(exc).__name__}: {exc}")
    try:
        return vfx_model_payload(parsed, to_wire=True) if isinstance(parsed, dict) else None
    except ValueError as exc:
        return MalformedVfxDirectorOutput(raw_text=str(content), error=str(exc))
