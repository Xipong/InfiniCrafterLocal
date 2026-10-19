"""LLM request options and provider wire projections.

Build payloads, reasoning controls and cache identities without sending requests
or learning provider capabilities. Negotiation remains in llm_transport.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from infini_local.core import llm_config as config
from infini_local.core.env_utils import env_str
from infini_local.core.generation_defaults import GENERATION_DEFAULTS
from infini_local.core.llm_prompt_cache import (
    PROMPT_CACHE_METADATA_KEY, static_instruction_prefix_parts, instruction_segment_index,
)
from infini_local.pipelines import llm_profiles as profiles


def llm_json_response_format(
    name: str = "infini_json",
    *,
    schema: dict[str, Any] | Callable[[], dict[str, Any]] | None = None,
    strict: bool = False,
    auto_preference: str | None = None,
) -> dict[str, Any] | None:
    """OpenAI-compatible structured JSON hint.

    ``auto`` normally uses provider-safe ``json_object`` on remote gateways and
    JSON Schema on local servers.  A large-stage caller may request a lighter
    auto default without overriding an explicit environment choice.  Remote or
    local constrained decoding can otherwise duplicate a very large schema and
    time out before the authoritative local boundary sees the answer.
    """
    mode = config.LLM_RESPONSE_FORMAT_MODE
    if mode == "auto":
        preferred = str(auto_preference or "").strip().lower()
        if preferred not in {"", "json_object", "json_schema"}:
            raise ValueError(f"unsupported auto response-format preference: {auto_preference!r}")
        mode = preferred or ("json_schema" if profiles.active_llm_provider() == "local" else "json_object")
    if mode in {"off", "none", "0", "false", "disabled"}:
        return None
    if mode == "json_object":
        return {"type": "json_object"}
    # Stage schemas can be large. Do not construct a provider projection that
    # json_object/off will discard; local validation remains unchanged.
    resolved_schema = schema() if callable(schema) else schema
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": bool(strict),
            "schema": resolved_schema or {"type": "object", "additionalProperties": True},
        },
    }


def llm_answer_max_tokens(default: int | None = None) -> int:
    raw = config.LLM_MAX_TOKENS if default is None else default
    try:
        value = int(raw)
    except Exception:
        value = int(GENERATION_DEFAULTS["INFINI_LLM_MAX_TOKENS"])
    return max(512, min(64000, value))


def visual_director_max_tokens() -> int:
    """Token budget for the visual-director LLM step.

    If INFINI_VISUAL_DIRECTOR_MAX_TOKENS is blank/unset, inherit the global
    INFINI_LLM_MAX_TOKENS so the main GUI setting also affects the Z-Image
    prompt-authoring hop.
    """
    raw = env_str("INFINI_VISUAL_DIRECTOR_MAX_TOKENS", "")
    if not raw:
        return llm_answer_max_tokens()
    try:
        value = int(raw)
    except Exception:
        return llm_answer_max_tokens()
    return max(512, min(64000, value))


def _configured_reasoning_payload() -> dict[str, Any] | None:
    mode = str(config.LLM_REASONING_MODE or "off").strip().lower().replace("-", "_")
    if mode in {"", "off", "false", "0", "disabled", "disable"}:
        return None
    exclude = bool(config.LLM_REASONING_EXCLUDE)
    if mode in {"auto", "default", "enabled", "on"}:
        return {"enabled": True, "exclude": exclude}
    if mode in {"none", "no_reasoning"}:
        return {"effort": "none", "exclude": exclude}
    if mode in {"minimal", "low", "medium", "high", "xhigh"}:
        return {"effort": mode, "exclude": exclude}
    if mode in {"tokens", "token_budget", "max_tokens", "budget"}:
        return {"max_tokens": max(0, min(64000, int(config.LLM_REASONING_MAX_TOKENS or 0))), "exclude": exclude}
    # prompt_light / prompt_strong are local-only/prompt-only modes; do not send API field.
    return None


def llm_reasoning_payload(model_name: str = "", context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Return OpenRouter/OpenAI-compatible reasoning controls, or None.

    OpenRouter normalizes reasoning through `reasoning`: effort/max_tokens/enabled/exclude.
    Local LM Studio/Ollama-compatible servers often reject this field, so local reasoning is
    handled by system-prompt hinting instead.
    """
    configured = _configured_reasoning_payload()
    provider = profiles.active_llm_provider(context)
    if configured is None and provider == "openai_codex" and str(config.LLM_REASONING_MODE or "").strip().lower() == "max":
        configured = {"effort": "max", "exclude": bool(config.LLM_REASONING_EXCLUDE)}
    if configured is None or provider == "local":
        return None
    return configured


def _is_google_openai_compat_reasoning_model(model_name: str, context: dict[str, Any] | None = None) -> bool:
    lowered = str(model_name or "").lower()
    try:
        parsed_base_url = urlsplit(profiles.llm_base_url(context))
        hostname = str(parsed_base_url.hostname or "").lower()
        _ = parsed_base_url.port  # Validate malformed and out-of-range explicit ports.
        if parsed_base_url.username is not None or parsed_base_url.password is not None:
            hostname = ""
    except ValueError:
        hostname = ""
    return (
        profiles.active_llm_provider(context) == "openai_compat"
        and hostname == "generativelanguage.googleapis.com"
        and ("gemini" in lowered or "gemma" in lowered)
    )


def _google_reasoning_effort(reasoning: dict[str, Any]) -> str:
    """Map Infini reasoning controls to Google's documented OpenAI-compatible field."""
    effort = str(reasoning.get("effort") or "").strip().lower()
    if effort == "xhigh":
        return "high"
    if effort in {"minimal", "low", "medium", "high"}:
        return effort
    # Gemini 3 cannot disable thinking. Keep explicit none bounded rather than sending
    # an unsupported semantic value; auto/enabled gets useful but not maximal thinking.
    if effort == "none":
        return "minimal"
    if reasoning.get("max_tokens") is not None:
        budget = int(reasoning.get("max_tokens") or 0)
        if budget <= 1024:
            return "low"
        if budget <= 8192:
            return "medium"
        return "high"
    return "medium"


_REASONING_INTENT_KEY = "_infini_reasoning_intent"


LLM_MODEL_OVERRIDE_KEY = "_infini_model_override"


def _remap_reasoning_for_context(payload: dict[str, Any], *, model_name: str, context: dict[str, Any]) -> None:
    """Rewrite reasoning controls for the provider that will actually receive the request."""
    intent = payload.get(_REASONING_INTENT_KEY) if isinstance(payload.get(_REASONING_INTENT_KEY), dict) else None
    explicit = payload.get("reasoning") if isinstance(payload.get("reasoning"), dict) else None
    effort = str(payload.get("reasoning_effort") or "").strip().lower()
    payload.pop(_REASONING_INTENT_KEY, None)
    payload.pop("reasoning", None)
    payload.pop("reasoning_effort", None)
    if profiles.active_llm_provider(context) == "local":
        return
    reasoning = dict(explicit or intent or {})
    if not reasoning and effort:
        reasoning = {"effort": effort, "exclude": bool(config.LLM_REASONING_EXCLUDE)}
    if not reasoning:
        return
    if _is_google_openai_compat_reasoning_model(model_name, context):
        payload["reasoning_effort"] = _google_reasoning_effort(reasoning)
    else:
        payload["reasoning"] = reasoning


def _apply_google_high_reasoning_completion_headroom(
    payload: dict[str, Any],
    *,
    model_name: str,
    context: dict[str, Any],
) -> None:
    """Translate Infini's answer budget to Google's reasoning-inclusive cap.

    Infini stage ``max_tokens`` values are budgets for the emitted JSON answer.
    Google's OpenAI-compatible Gemini endpoint counts hidden reasoning tokens
    against that same provider field.  At high effort, reserve one additional
    answer budget for hidden reasoning so it cannot truncate the JSON while
    leaving the logical stage budget unchanged.
    """
    if not _is_google_openai_compat_reasoning_model(model_name, context):
        return
    if str(payload.get("reasoning_effort") or "").strip().lower() != "high":
        return
    try:
        answer_budget = int(payload.get("max_tokens") or 0)
    except (TypeError, ValueError):
        return
    if answer_budget <= 0:
        return
    payload["max_tokens"] = min(64000, answer_budget * 2)


def llm_reasoning_system_suffix(model_name: str = "") -> str:
    """Tiny prompt-only reasoning hint for local models.

    This does not ask the model to expose chain-of-thought. It just allows a private
    checklist before emitting the required JSON. Useful for Qwen/Gemma local runs where
    OpenRouter-style `reasoning` parameters are unavailable.
    """
    mode = str(config.LLM_REASONING_MODE or "off").strip().lower().replace("-", "_")
    provider = profiles.active_llm_provider()
    if mode in {"", "off", "false", "0", "disabled", "disable", "none", "no_reasoning"}:
        return ""
    if provider != "local" and mode not in {"prompt", "prompt_light", "prompt_strong", "local_prompt", "local_light", "local_strong"}:
        return ""
    if not config.LLM_LOCAL_REASONING_PROMPT:
        return ""
    if mode in {"prompt_strong", "local_strong"}:
        return " Privately check parent facts, engine functions, schema, and balance. Output only the final JSON object."
    return " Privately check constraints briefly. Output only the final JSON object."


def apply_llm_common_options(req: dict[str, Any], *, model_name: str, default_max_tokens: int | None = None, allow_reasoning: bool = True) -> dict[str, Any]:
    req["max_tokens"] = llm_answer_max_tokens(default_max_tokens)
    if allow_reasoning:
        configured = _configured_reasoning_payload()
        if configured:
            # Internal intent survives a local-primary attempt and is stripped before
            # every real HTTP request; remote fallbacks remap it for their provider.
            req[_REASONING_INTENT_KEY] = dict(configured)
        reasoning = llm_reasoning_payload(model_name)
        if reasoning:
            if _is_google_openai_compat_reasoning_model(model_name):
                req["reasoning_effort"] = _google_reasoning_effort(reasoning)
            else:
                req["reasoning"] = reasoning
    return req


_REASONING_EFFORT_RANK = {
    "none": 0,
    "minimal": 1,
    "low": 2,
    "medium": 3,
    "high": 4,
    "xhigh": 5,
    "max": 6,
}


def apply_minimum_reasoning_effort(
    req: dict[str, Any],
    *,
    model_name: str,
    minimum: str = "medium",
) -> dict[str, Any]:
    """Apply a stage-local reasoning floor without lowering a stronger user choice."""
    floor = str(minimum or "").strip().lower()
    if floor not in _REASONING_EFFORT_RANK:
        raise ValueError(f"unsupported minimum reasoning effort: {minimum!r}")
    intent_raw = req.get(_REASONING_INTENT_KEY)
    intent: dict[str, Any] = intent_raw if isinstance(intent_raw, dict) else {}
    explicit_raw = req.get("reasoning")
    explicit: dict[str, Any] = explicit_raw if isinstance(explicit_raw, dict) else {}
    current = str(
        req.get("reasoning_effort")
        or explicit.get("effort")
        or intent.get("effort")
        or ""
    ).strip().lower()
    selected = current if _REASONING_EFFORT_RANK.get(current, -1) >= _REASONING_EFFORT_RANK[floor] else floor
    reasoning = {"effort": selected, "exclude": bool(config.LLM_REASONING_EXCLUDE)}
    req[_REASONING_INTENT_KEY] = dict(reasoning)
    if profiles.active_llm_provider() == "local":
        req.pop("reasoning", None)
        req.pop("reasoning_effort", None)
    elif _is_google_openai_compat_reasoning_model(model_name):
        req.pop("reasoning", None)
        req["reasoning_effort"] = _google_reasoning_effort(reasoning)
    else:
        req.pop("reasoning_effort", None)
        req["reasoning"] = reasoning
    return req


LLM_STAGE_KEY = "_infini_stage"


LLM_STAGES = frozenset({
    "llm",
    "planner",
    "author_repair",
    "genome_repair",
    "name_repair",
    "visual_director",
    "visual_repair",
    "vfx_director",
    "vfx_repair",
})


def _normalized_llm_stage(value: Any) -> str:
    stage = str(value or "llm").strip()
    if stage not in LLM_STAGES:
        raise ValueError(f"unsupported finite LLM stage: {stage!r}")
    return stage


def with_llm_stage(payload: dict[str, Any], stage: str) -> dict[str, Any]:
    """Attach internal finite stage metadata without mutating the provider payload."""
    out = dict(payload)
    out[LLM_STAGE_KEY] = _normalized_llm_stage(stage)
    return out


def _clean_llm_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(payload, ensure_ascii=False))
    out.pop(LLM_STAGE_KEY, None)
    out.pop(PROMPT_CACHE_METADATA_KEY, None)
    if out.get("response_format") is None:
        out.pop("response_format", None)
    return out


def _prompt_cache_boundary(payload: dict[str, Any]) -> tuple[int, int] | None:
    segment = instruction_segment_index(payload)
    if segment is not None:
        return segment, len(payload["messages"][segment]["content"])
    marker = payload.get(PROMPT_CACHE_METADATA_KEY)
    if not isinstance(marker, dict):
        return None
    index, chars = marker.get("messageIndex"), marker.get("prefixChars")
    messages = payload.get("messages")
    if (type(index) is not int or type(chars) is not int or not isinstance(messages, list)
            or index < 0 or index >= len(messages)):
        return None
    message = messages[index]
    if (not isinstance(message, dict) or message.get("role") != "user"
            or not isinstance(message.get("content"), str)
            or chars <= 0 or chars > len(message["content"])):
        return None
    return index, chars


def _prompt_cache_identity(payload: dict[str, Any], model: str, *, context: dict[str, Any] | None = None) -> str:
    """Content-derived routing hint, never a receipt of provider cache reuse."""
    boundary = _prompt_cache_boundary(payload)
    if boundary is None:
        raise ValueError("prompt cache identity requires a valid static boundary")
    index, chars = boundary
    messages = payload["messages"]
    if context is not None and profiles.active_llm_provider(context) == "openai_codex":
        from infini_local.services.codex_text_backend import _request_payload
        # Hash exactly what this provider consumes, not client-only message names
        # or ignored reasoning.exclude. The adapter is the canonical projection
        # owner; other providers retain their existing identity semantics.
        prefix_packet = _clean_llm_payload(payload)
        prefix_packet["model"] = model
        prefix_packet.pop("prompt_cache_key", None)  # Never hash our own routing hint.
        prefix_packet["messages"] = prefix_packet["messages"][:index + 1]
        prefix_packet["messages"][index]["content"] = messages[index]["content"][:chars]
        static_prefix = static_instruction_prefix_parts(payload)
        if static_prefix is not None:
            prefix_packet["messages"][index] = {"role": "developer", "content": static_prefix[1]}
        stable = {"provider": "openai_codex", "wire": _request_payload(prefix_packet)}
        if static_prefix is not None or instruction_segment_index(payload) is not None:
            stable["framing"] = {"version": 1, "authority": "builder-declared-static-instructions"}
    else:
        stable = {
            "model": model,
            "messages": [*messages[:index], {**messages[index], "content": messages[index]["content"][:chars]}],
            "response_format": payload.get("response_format"),
            "reasoning": payload.get("reasoning"),
            "reasoning_effort": payload.get("reasoning_effort"),
        }
    if instruction_segment_index(payload) is not None and (context is None or profiles.active_llm_provider(context) != "openai_codex"):
        stable["framing"] = "complete-builder-instructions-v1"
    segment = instruction_segment_index(payload)
    if segment is not None and "schemaDefinitions" in json.loads(messages[segment]["content"]):
        stable["framing"] = "complete-builder-instructions-and-grammar-v1"
        # The full schema is a case-dependent constraint, not routing affinity.
        # Mode/name/strictness remain identity; canonical definitions are already
        # included in the declared DEVELOPER endpoint. Author identity is untouched.
        if "wire" in stable:
            shape = stable["wire"].get("text", {}).get("format", {})
        else:
            shape = copy.deepcopy(stable.get("response_format") or {})
            stable["response_format"] = shape or None
            shape = shape.get("json_schema", {})
        shape.pop("schema", None)
    digest = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()
    return "infini-" + digest[:32]


def _cache_route(context: dict[str, Any], model: str) -> str:
    """Only documented canonical OpenAI Platform / OpenRouter endpoint+model pairs."""
    parsed = urlsplit(str(context.get("base_url") or "").rstrip("/"))
    base = (parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.path.rstrip("/"))
    provider = profiles.active_llm_provider(context)
    if provider == "openai_compat" and base == ("https", "inference-api.nousresearch.com", "/v1") and not parsed.port and model.startswith("openai/"):
        return "key"  # Measured Chat subscription field; no Platform breakpoints/retention.
    if provider == "openai_compat" and base == ("https", "api.openai.com", "/v1") and not parsed.port:
        slug = model
    elif provider == "openrouter" and base == ("https", "openrouter.ai", "/api/v1") and not parsed.port and model.startswith("openai/"):
        slug = model.removeprefix("openai/")
    else:
        return ""
    match = re.fullmatch(r"gpt-(\d+)(?:\.(\d+))?(?:-[a-z0-9-]+)?", slug.lower())
    if not match:
        return ""
    return "explicit" if (int(match.group(1)), int(match.group(2) or 0)) >= (5, 6) else "key"


def _usage_fields(result: dict[str, Any]) -> dict[str, Any]:
    usage_raw = result.get("usage")
    usage: dict[str, Any] = usage_raw if isinstance(usage_raw, dict) else {}
    input_details_raw = usage.get("input_tokens_details")
    prompt_details_raw = usage.get("prompt_tokens_details")
    input_details: dict[str, Any] = input_details_raw if isinstance(input_details_raw, dict) else {}
    prompt_details: dict[str, Any] = prompt_details_raw if isinstance(prompt_details_raw, dict) else {}

    def counter(name: str) -> int | None:
        for details in (input_details, prompt_details):
            value = details.get(name)
            if type(value) is int and value >= 0:
                return value
        return None

    cached = counter("cached_tokens")
    output_details = usage.get("output_tokens_details")
    if not isinstance(output_details, dict):
        output_details = usage.get("completion_tokens_details")
    reasoning = output_details.get("reasoning_tokens") if isinstance(output_details, dict) else None
    attribution = usage.get("attribution")
    request_fields = attribution.get("request_fields") if isinstance(attribution, dict) else None
    instructions = request_fields.get("instructions") if isinstance(request_fields, dict) else None

    def instruction_counter(name: str) -> int | None:
        value = instructions.get(name) if isinstance(instructions, dict) else None
        return value if type(value) is int and value >= 0 else None

    def total_counter(primary: str, alternate: str) -> int | None:
        value = usage.get(primary) if primary in usage else usage.get(alternate)
        return value if type(value) is int and value >= 0 else None

    return {
        "inputTokens": total_counter("input_tokens", "prompt_tokens"),
        "outputTokens": total_counter("output_tokens", "completion_tokens"),
        "cachedInputTokens": cached,
        "cacheWriteTokens": counter("cache_write_tokens"),
        "cacheHit": (cached > 0) if cached is not None else None,
        "reasoningTokens": reasoning if type(reasoning) is int and reasoning >= 0 else None,
        "instructionsInputTokens": instruction_counter("input_tokens"),
        "instructionsCachedInputTokens": instruction_counter("cached_tokens"),
        "instructionsCacheWriteTokens": instruction_counter("cache_write_tokens"),
    }


def _response_format_for_responses(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    kind = str(value.get("type") or "")
    if kind == "json_object":
        return {"type": "json_object"}
    if kind != "json_schema" or not isinstance(value.get("json_schema"), dict):
        return None
    schema_raw = value["json_schema"]
    schema: dict[str, Any] = schema_raw
    return {
        "type": "json_schema",
        "name": str(schema.get("name") or "infini_json"),
        "strict": bool(schema.get("strict")),
        "schema": schema.get("schema") or {"type": "object", "additionalProperties": True},
    }


def _cache_wire_options(wire: dict[str, Any], source: dict[str, Any],
                        context: dict[str, Any], *, api_mode: str) -> None:
    boundary = _prompt_cache_boundary(source)
    wire.pop(PROMPT_CACHE_METADATA_KEY, None)
    if boundary is None:
        return
    model = str(wire.get("model") or "")
    route = _cache_route(context, model)
    if api_mode == "responses" and profiles.llm_responses_url(context) == "https://inference-api.nousresearch.com/v1/responses":
        route = ""  # Chat-only measured subscription cache hint; do not guess Responses support.
    if not route:
        return
    index, chars = boundary
    content = source["messages"][index]["content"]
    if route == "explicit":
        if api_mode == "responses":
            target = index - sum(1 for message in source["messages"][:index]
                                 if isinstance(message, dict) and message.get("role") == "system")
            messages = wire.get("input")
            block_type = "input_text"
        else:
            target = index
            messages = wire.get("messages")
            block_type = "text"
        if (not isinstance(messages, list) or target >= len(messages) or target < 0
                or messages[target].get("content") != content):
            return
        # The two blocks concatenate to precisely the original authored text.
        blocks = [{"type": block_type, "text": content[:chars],
                   "prompt_cache_breakpoint": {"mode": "explicit"}}]
        if chars < len(content):
            blocks.append({"type": block_type, "text": content[chars:]})
        messages[target]["content"] = blocks
        wire["prompt_cache_options"] = {"mode": "explicit"}
    # Breakpoints define what is reusable; a content-stable routing key also
    # keeps different recipes on the same provider cache route. Hash effective
    # reasoning settings, not superseded pre-adapter aliases.
    identity_source = {**source, "reasoning": wire.get("reasoning"),
                       "reasoning_effort": wire.get("reasoning_effort")}
    wire["prompt_cache_key"] = _prompt_cache_identity(identity_source, model, context=context)


def _ensure_json_input_marker(messages: list[dict[str, Any]]) -> None:
    """Frame JSON mode without editing an authored dossier or its cache identity."""
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {"user", "developer", "assistant"}:
            continue
        content = message.get("content")
        if isinstance(content, str):
            texts = [content]
        elif isinstance(content, list):
            texts = [part.get("text") for part in content if isinstance(part, dict)
                     and part.get("type") in {"text", "input_text", "output_text"}]
        else:
            texts = []
        if any(isinstance(text, str) and re.search(r"\bjson\b", text, re.IGNORECASE) for text in texts):
            return
    messages.append({"role": "user", "content": "JSON response."})


def _responses_payload_from_chat(payload: dict[str, Any], previous_response_id: str = "", *,
                                 cache_source: dict[str, Any] | None = None,
                                 context: dict[str, Any] | None = None) -> dict[str, Any]:
    instructions: list[str] = []
    input_messages: list[dict[str, Any]] = []
    for raw in payload.get("messages") or []:
        if not isinstance(raw, dict):
            continue
        role = str(raw.get("role") or "user")
        content = str(raw.get("content") or "")
        if role == "system":
            if content:
                instructions.append(content)
            continue
        if role not in {"developer", "user", "assistant"}:
            raise ValueError(f"Responses cannot preserve unsupported message role: {role}")
        input_messages.append({"role": role, "content": content})
    out: dict[str, Any] = {
        "model": payload.get("model"),
        "input": input_messages,
    }
    if instructions:
        out["instructions"] = "\n\n".join(instructions)
    if context is not None and profiles.active_llm_provider(context) == "openrouter" and isinstance(payload.get("provider"), dict):
        out["provider"] = copy.deepcopy(payload["provider"])
    if previous_response_id:
        out["previous_response_id"] = previous_response_id
    if payload.get("temperature") is not None:
        out["temperature"] = payload.get("temperature")
    if payload.get("max_tokens") is not None:
        out["max_output_tokens"] = payload.get("max_tokens")
    response_format = _response_format_for_responses(payload.get("response_format"))
    if response_format is not None:
        out["text"] = {"format": response_format}
    reasoning_raw = payload.get("reasoning")
    reasoning: dict[str, Any] = reasoning_raw if isinstance(reasoning_raw, dict) else {}
    effort = str(payload.get("reasoning_effort") or reasoning.get("effort") or "").strip()
    if effort:
        out["reasoning"] = {"effort": "high" if effort == "xhigh" else effort}
    if cache_source is not None and context is not None:
        _cache_wire_options(out, cache_source, context, api_mode="responses")
    if (context is not None and profiles.active_llm_provider(context) == "openai_compat"
            and profiles.llm_responses_url(context) == "https://inference-api.nousresearch.com/v1/responses"
            and str(out.get("model") or "").startswith("openai/")
            and response_format == {"type": "json_object"}):
        _ensure_json_input_marker(out["input"])
    return out


def _responses_output_text(result: dict[str, Any]) -> str:
    direct = result.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    chunks: list[str] = []
    for item in result.get("output") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            if str(part.get("type") or "") == "refusal":
                raise RuntimeError(str(part.get("refusal") or "LLM Responses request refused"))
            text = part.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "".join(chunks).strip()


def effective_response_format(request: Mapping[str, Any], raw: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Use actual transport metadata when a provider relaxed the requested schema."""
    response_format = request.get("response_format")
    debug = raw.get("_debug")
    if isinstance(debug, Mapping):
        if debug.get("strictSchemaDowngraded") or debug.get("responseFormatUsed") is False:
            return None
        if "responseFormatType" in debug and debug["responseFormatType"] != "json_schema":
            return None
    return response_format if isinstance(response_format, Mapping) else None
