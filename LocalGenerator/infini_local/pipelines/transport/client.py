"""Logical LLM request execution, profile failover and provider negotiation."""
from __future__ import annotations

import copy
import hashlib
import json
import time
from typing import Any
from urllib import error as urlerror

from infini_local.core import llm_config as config
from infini_local.core.http_io import remaining_seconds
from infini_local.core.llm_json_tools import parse_first_valid_llm_json
from infini_local.core.llm_prompt_cache import PROMPT_CACHE_METADATA_KEY, instruction_segment_index, static_instruction_prefix_parts
from infini_local.pipelines.transport import diagnostics, http, profiles, rejections
from infini_local.pipelines.transport import provider_wire as wire
from infini_local.pipelines.transport import replay as offline_replay
from infini_local.services.combine_endpoint import update_generation_activity
from infini_local.storage.trace_runtime import log_event


def _perform_llm_http(url: str, wire: dict[str, Any], timeout: float, context: dict[str, Any], *, api_mode: str) -> dict[str, Any]:
    state = diagnostics._CURRENT_LLM_DIAGNOSTICS.get()
    if state is None:
        return http.http_json(url, wire, timeout=timeout, headers=profiles.llm_headers(context=context))
    effective_reasoning = diagnostics._reasoning_diagnostic(wire)
    row = {
        **{name: state[name] for name in ("logicalCallId", "stage", "leaseId", "requestedApiMode", "requestedResponseFormat", "requestedReasoning")},
        "profileId": profiles._profile_id(context), "provider": profiles.active_llm_provider(context),
        "openrouterProvider": profiles._openrouter_provider(context),
        "effectiveApiMode": api_mode, "effectiveResponseFormat": diagnostics._format_diagnostic(wire),
        "effectiveReasoning": effective_reasoning,
        "unsupportedReasoningFields": sorted(set(state["requestedReasoning"]) - set(effective_reasoning)),
        "reason": state["nextReason"], "networkStarted": None, "httpStatus": None,
        "physicalAttemptIndex": None, "rateWaitMs": 0.0, "rateWaitReason": "none",
        "connectMs": None, "openMs": 0.0, "readMs": 0.0,
    }
    token = diagnostics._CURRENT_LLM_ATTEMPT.set(row)
    try:
        return http.http_json(url, wire, timeout=timeout, headers=profiles.llm_headers(context=context))
    except urlerror.HTTPError as error:
        row["httpStatus"] = error.code
        row.update(rejections._provider_error_metadata(http._read_llm_http_error(error, timeout)))
        row["errorType"] = type(error).__name__
        raise
    except Exception as error:
        row["errorType"] = type(error).__name__
        raise
    finally:
        row["deadlineRemainingMs"] = round(max(0.0, diagnostics._request_deadline(timeout) - time.monotonic()) * 1000, 3)
        state["rateWaitMsTotal"] += row["rateWaitMs"]
        if row["networkStarted"] is True:
            state["physicalAttemptCount"] += 1
            row["physicalAttemptIndex"] = state["physicalAttemptCount"]
        state["lastAttempt"] = row
        if state["diagnosticEventCount"] < diagnostics._LLM_MAX_DIAGNOSTIC_ATTEMPTS:
            if row["networkStarted"] is True:
                state["physicalAttempts"].append(copy.deepcopy(row))
            log_event("info", "LLM physical attempt" if row["networkStarted"] is True else "LLM transport wait", row)
        elif row["networkStarted"] is True:
            state["physicalAttemptsDropped"] += 1
        state["diagnosticEventCount"] += 1
        diagnostics._CURRENT_LLM_ATTEMPT.reset(token)
        update_generation_activity(wait_reason="none")



def _llm_backoff(seconds: float) -> None:
    deadline = diagnostics._CURRENT_LLM_DEADLINE.get()
    remaining = remaining_seconds(deadline) if deadline is not None else seconds
    update_generation_activity(wait_reason="retry_backoff", network_started=False)
    try:
        time.sleep(min(seconds, remaining))
    finally:
        update_generation_activity(wait_reason="none")
    if deadline is not None:
        remaining_seconds(deadline)



_RESOLVED_LLM_MODELS: dict[str, str] = {}



_RESPONSES_CAPABILITY: dict[str, bool] = {}



_STRICT_SCHEMA_CAPABILITY: dict[str, bool] = {}



def llm_auth_snapshot() -> dict[str, Any]:
    """Small UI/trace diagnostic for the currently selected LLM backend.

    This is intentionally config-only; it does not call remote APIs. It makes the
    common failure mode visible: OpenRouter selected, but no API key is loaded.
    """
    primary = profiles._legacy_primary_llm_context()
    provider = profiles.active_llm_provider(primary)
    pool_view = [
        {
            "profileId": context.get("profile_id"),
            "provider": context.get("provider"),
            "baseUrl": context.get("base_url"),
            "model": context.get("model"),
            "apiMode": context.get("api_mode"),
            "openrouterProvider": profiles._openrouter_provider(context),
            "apiKeyConfigured": (
                bool(context.get("api_key"))
                if context.get("provider") in {"openrouter", "openai_compat"}
                else None
            ),
            "responsesSupported": _RESPONSES_CAPABILITY.get(profiles._llm_context_key(context)),
        }
        for context in profiles.configured_llm_pool()
    ]
    fallback = profiles._fallback_llm_context()
    fallback_view = None
    if fallback is not None:
        fallback_view = {
            "provider": fallback.get("provider"),
            "baseUrl": fallback.get("base_url"),
            "model": fallback.get("model"),
            "apiKeyConfigured": bool(fallback.get("api_key")) if fallback.get("provider") in {"openrouter", "openai_compat"} else None,
            "networkFailsBeforeSwitch": config.LLM_FALLBACK_NETWORK_FAILS,
            "openrouterProvider": profiles._openrouter_provider(fallback),
        }
    if provider == "openrouter":
        configured = bool(primary.get("api_key"))
        return {
            "provider": provider,
            "baseUrl": primary.get("base_url") or "https://openrouter.ai/api/v1",
            "openrouterProvider": profiles._openrouter_provider(primary),
            "model": primary.get("model") or "auto",
            "apiKeyConfigured": configured,
            "status": "configured" if configured else "missing_api_key",
            "hint": "OK" if configured else "Set INFINI_OPENROUTER_API_KEY in config.env or choose the local LM Studio preset.",
            "fallback": fallback_view,
            "pool": pool_view,
        }
    if provider == "openai_compat":
        configured = bool(primary.get("api_key"))
        return {
            "provider": provider,
            "baseUrl": primary.get("base_url"),
            "model": primary.get("model") or "auto",
            "apiKeyConfigured": configured,
            "status": "configured" if configured else "missing_or_optional_api_key",
            "hint": "Set INFINI_OPENAI_COMPAT_API_KEY if your compatible endpoint requires Bearer auth.",
            "fallback": fallback_view,
            "pool": pool_view,
        }
    if provider == "openai_codex":
        from infini_local.services.codex_auth import auth_status

        signed_in = bool(auth_status().get("authenticated"))
        model = str(primary.get("model") or "").strip()
        status = "sign_in_required" if not signed_in else "model_required" if not model else "signed_in_unverified"
        return {
            "provider": provider,
            "baseUrl": primary.get("base_url"),
            "model": model,
            "apiKeyConfigured": None,
            "status": status,
            "hint": "Refresh the subscription catalog and select a model; status alone does not verify account access.",
            "fallback": fallback_view,
            "pool": pool_view,
        }
    return {
        "provider": provider or "local",
        "baseUrl": primary.get("base_url") or config.LMSTUDIO_URL,
        "model": primary.get("model") or "auto",
        "apiKeyConfigured": None,
        "status": "local_endpoint_required",
        "hint": "LM Studio must be running and exposing /v1 on the configured URL.",
        "fallback": fallback_view,
        "pool": pool_view,
    }



def resolve_llm_model(context: dict[str, Any] | None = None) -> str:
    """Resolve the active OpenAI-compatible model name.

    Local: model=auto asks /v1/models and uses the first loaded model.
    OpenRouter: explicit INFINI_OPENROUTER_MODEL is preferred; model=auto tries to
    select a :free model from /models, then falls back to the first advertised model.
    """
    global _RESOLVED_LLM_MODELS
    ctx = context or profiles._primary_llm_context()
    provider = profiles.active_llm_provider(ctx)
    configured = str(ctx.get("model") or "auto").strip()
    if provider == "openai_codex" and configured.lower() in {"", "auto", "default"}:
        from infini_local.services.codex_auth import CodexError
        raise CodexError("Choose an available Codex text model in settings before generating")
    if configured and configured.lower() not in {"auto", "local-model", "local_model", "default"}:
        return configured
    cache_key = profiles._llm_context_key(ctx)
    if _RESOLVED_LLM_MODELS.get(cache_key):
        return _RESOLVED_LLM_MODELS[cache_key]
    try:
        models = http.http_get_json(profiles.llm_models_url(ctx), timeout=6, headers=profiles.llm_headers({"Accept": "application/json"}, context=ctx))
        data = models.get("data") if isinstance(models, dict) else None
        if isinstance(data, list) and data:
            model_ids = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                mid = item.get("id") or item.get("name")
                if isinstance(mid, str) and mid.strip():
                    model_ids.append(mid.strip())
            if model_ids:
                mid = (next((name for name in model_ids if name.endswith(":free")), model_ids[0])
                       if provider == "openrouter" else model_ids[0])
                _RESOLVED_LLM_MODELS[cache_key] = mid
                log_event("info", "resolved LLM model", {"provider": provider, "model": mid, "label": ctx.get("label")})
                return mid
    except Exception as e:
        log_event("warn", "could not auto-resolve LLM model", {"provider": provider, "error": repr(e), "url": profiles.llm_models_url(ctx), "label": ctx.get("label")})
    if provider == "openrouter":
        # No invented fallback slug: "~openai/gpt-latest" does not exist on
        # OpenRouter, so sending it would fail every call with an opaque
        # provider error.  Return the configured value verbatim; when the
        # user truly left model=auto and /models is unreachable, the empty
        # string surfaces as a clear configuration failure instead of a
        # per-request provider 404.
        return configured if configured.lower() not in {"auto", "default"} else ""
    return configured or "local-model"



def _payload_for_context(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if profiles.active_llm_provider(context) == "openai_codex" or instruction_segment_index(payload) is not None:
        # Validate the original typed envelope before JSON copying can coerce an
        # invalid declared boundary (e.g. tuple messages) into an admitted shape.
        static_instruction_prefix_parts(payload)
    out = wire._clean_llm_payload(payload)
    if (profiles.active_llm_provider(context) == "openai_codex" or instruction_segment_index(payload) is not None) and PROMPT_CACHE_METADATA_KEY in payload:
        # Native adapter-only metadata; retain even invalid explicit declarations
        # so the authority validator refuses them instead of silently downgrading.
        out[PROMPT_CACHE_METADATA_KEY] = copy.deepcopy(payload[PROMPT_CACHE_METADATA_KEY])
    # Routing belongs to the selected profile, not a stale caller payload.
    out.pop("provider", None)
    upstream = profiles._openrouter_provider(context)
    if upstream:
        out["provider"] = {"only": [upstream], "allow_fallbacks": False}
    model_override = str(out.pop(wire.LLM_MODEL_OVERRIDE_KEY, "") or "").strip()
    model_name = model_override or resolve_llm_model(context)
    out["model"] = model_name
    wire._remap_reasoning_for_context(out, model_name=model_name, context=context)
    if profiles.active_llm_provider(context) == "openai_codex" and payload.get(wire.LLM_STAGE_KEY) in {"visual_director", "visual_repair"}:
        if config.CODEX_VISUAL_REASONING == "model_default":
            out.pop("reasoning", None)
            out.pop("reasoning_effort", None)
        elif config.CODEX_VISUAL_REASONING != "inherit":
            from infini_local.services.codex_auth import CodexError
            from infini_local.services.codex_text_backend import EFFORTS
            if config.CODEX_VISUAL_REASONING not in EFFORTS:
                raise CodexError("Unsupported Visual Director Codex reasoning effort")
            out["reasoning"] = {"effort": config.CODEX_VISUAL_REASONING}
            out.pop("reasoning_effort", None)
    wire._apply_google_high_reasoning_completion_headroom(
        out,
        model_name=model_name,
        context=context,
    )
    return out



def _llm_responses_json_single_context(payload: dict[str, Any], timeout: float, context: dict[str, Any]) -> dict[str, Any]:
    profiles.ensure_llm_auth_configured(context)
    prepared = _payload_for_context(payload, context)
    lease = profiles._CURRENT_LLM_ITEM_LEASE.get()
    previous_id = ""
    messages_raw = prepared.get("messages")
    messages: list[Any] = messages_raw if isinstance(messages_raw, list) else []
    clean_stage_dossier = (
        len(messages) == 2
        and isinstance(messages[0], dict)
        and isinstance(messages[1], dict)
        and messages[0].get("role") == "system"
        and messages[1].get("role") == "user"
    )
    if lease is not None and lease.context is context and not lease.responses_disabled and clean_stage_dossier and PROMPT_CACHE_METADATA_KEY not in payload:
        previous_id = lease.previous_response_id
    request_payload = wire._responses_payload_from_chat(prepared, previous_id, cache_source=payload, context=context)
    try:
        result = _perform_llm_http(profiles.llm_responses_url(context), request_payload, timeout, context, api_mode="responses")
        if not isinstance(result, dict):
            raise RuntimeError("LLM Responses endpoint returned a non-object response")
        status = str(result.get("status") or "completed").lower()
        if status in {"failed", "cancelled", "incomplete"}:
            raise RuntimeError(f"LLM Responses request ended with status={status}")
        content = wire._responses_output_text(result)
        if not content:
            raise RuntimeError("LLM Responses endpoint returned no output text")
        response_id = str(result.get("id") or "")
        if lease is not None and lease.context is context:
            lease.previous_response_id = "" if PROMPT_CACHE_METADATA_KEY in payload else response_id
        usage = wire._usage_fields(result)
        return {
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": result.get("usage") or {},
            "_debug": {
                "apiMode": "responses",
                "openrouterProvider": profiles._openrouter_provider(context),
                "requestMode": "exact",
                "provider": profiles.active_llm_provider(context),
                "profileId": context.get("profile_id"),
                "responseId": response_id,
                "previousResponseId": previous_id,
                **usage,
            },
        }
    except urlerror.HTTPError as error:
        http._read_llm_http_error(error, timeout)
        raise



def _record_llm_stage(payload: dict[str, Any]) -> str:
    stage = offline_replay._llm_replay_stage_from_payload(payload)
    lease = profiles._CURRENT_LLM_ITEM_LEASE.get()
    if lease is not None:
        lease.call_count += 1
        lease.stages.append(stage)
    return stage



@diagnostics._bounded_llm_call
def _llm_json_single_context(payload: dict[str, Any], timeout: float, context: dict[str, Any]) -> dict[str, Any]:
    stage = offline_replay._llm_replay_stage_from_payload(payload)
    # Raw replay is an explicit offline seam.  Resolve it before choosing
    # Responses vs Chat so auto/responses profiles can never make a network
    # call merely because replay used to live inside the Chat-only helper.
    replay = offline_replay._llm_replay_json_response(payload)
    if replay is not None:
        return replay
    if profiles.active_llm_provider(context) == "openai_codex":
        from infini_local.services.codex_text_backend import _request_payload, generate_chat
        prepared = _payload_for_context(payload, context)
        if wire._prompt_cache_boundary(payload) is not None:
            identity_source = {**prepared, PROMPT_CACHE_METADATA_KEY: payload[PROMPT_CACHE_METADATA_KEY]}
            prepared["prompt_cache_key"] = wire._prompt_cache_identity(identity_source, str(prepared["model"]), context=context)
        state = diagnostics._CURRENT_LLM_DIAGNOSTICS.get()
        if state is not None:
            state["physicalAttemptCount"] = None  # Unknown until the generation owner reports; excludes auth I/O.
            codex_wire = _request_payload(prepared)
            state["lastAttempt"] = {
                "effectiveApiMode": "codex_subscription_sse",
                "effectiveResponseFormat": diagnostics._format_diagnostic(codex_wire),
                "effectiveReasoning": diagnostics._reasoning_diagnostic(codex_wire),
            }
        from infini_local.services.codex_auth import generation_observations
        join = {name: state[name] for name in ("logicalCallId", "stage", "leaseId")} if state is not None else {}
        def observe_codex(observation):
            if state is None:
                return
            if observation["event"] == "request" and state["physicalAttemptCount"] is None:
                state["physicalAttemptCount"] = 0
            if observation["event"] == "post_start":
                state["physicalAttemptCount"] = (state["physicalAttemptCount"] or 0) + 1
            if observation["event"] == "attempt_end" and observation["networkStarted"]:
                row = {**state["lastAttempt"], **observation, "provider": "openai_codex", "profileId": profiles._profile_id(context)}
                state["lastAttempt"] = row
                if len(state["physicalAttempts"]) < diagnostics._LLM_MAX_DIAGNOSTIC_ATTEMPTS:
                    state["physicalAttempts"].append(copy.deepcopy(row))
                else:
                    state["physicalAttemptsDropped"] += 1
        with generation_observations(join, observe_codex):
            result = generate_chat(prepared, timeout=remaining_seconds(diagnostics._request_deadline(timeout)))
        usage = wire._usage_fields(result)
        result["_debug"] = {**(result.get("_debug") or {}), **usage}
        log_event("info", "LLM usage", {"stage": stage, **result["_debug"]})
        return result
    mode = profiles._normalized_api_mode(context.get("api_mode"))
    effective_model = str(payload.get(wire.LLM_MODEL_OVERRIDE_KEY) or "").strip() or resolve_llm_model(context)
    capability_key = profiles._llm_context_key({**context, "model": effective_model})
    lease = profiles._CURRENT_LLM_ITEM_LEASE.get()
    responses_allowed = mode in {"auto", "responses"}
    responses_to_chat_fallback = False
    had_working_chain = False
    if _RESPONSES_CAPABILITY.get(capability_key) is False:
        responses_allowed = False
    if lease is not None and lease.context is context and lease.responses_disabled:
        responses_allowed = False
    if responses_allowed:
        try:
            result = _llm_responses_json_single_context(payload, timeout, context)
            _RESPONSES_CAPABILITY[capability_key] = True
            log_event("info", "LLM usage", {"stage": stage, **(result.get("_debug") or {})})
            return result
        except Exception as error:
            if rejections._is_budget_or_auth_failure(error) or not rejections._responses_chat_fallback_allowed(error):
                raise
            had_working_chain = bool(lease is not None and lease.context is context and lease.previous_response_id)
            if had_working_chain:
                _RESPONSES_CAPABILITY[capability_key] = True
            if lease is not None and lease.context is context:
                lease.responses_disabled = True
                lease.previous_response_id = ""
            responses_to_chat_fallback = True
            diagnostics._attempt_reason("responses_to_chat_fallback")
            log_event("warn", "LLM Responses incompatible; retrying same stage through stateless Chat Completions", {
                "stage": stage,
                "profileId": context.get("profile_id"),
                "provider": profiles.active_llm_provider(context),
                "status": getattr(error, "code", None),
                "error": repr(error),
            })
    result = _llm_chat_json_single_context(payload, timeout, context)
    if isinstance(result, dict):
        debug_raw = result.get("_debug")
        debug: dict[str, Any] = debug_raw if isinstance(debug_raw, dict) else {}
        result["_debug"] = {
            **debug,
            "apiMode": "chat_completions",
            "profileId": context.get("profile_id"),
            **wire._usage_fields(result),
        }
        if responses_to_chat_fallback:
            if not had_working_chain:
                try:
                    parse_first_valid_llm_json(result["choices"][0]["message"]["content"])
                except (ValueError, TypeError, KeyError, IndexError):
                    pass
                else:
                    _RESPONSES_CAPABILITY[capability_key] = False
            result = _with_transport_retry_debug(result, ["responses_to_chat_fallback"])
        log_event("info", "LLM usage", {"stage": stage, **result["_debug"]})
    return result



def _json_object_response_format() -> dict[str, Any]:
    return {"type": "json_object"}



def _payload_without_strict_schema(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the same request with strict provider-side schema relaxed to json_object.

    Only the response envelope changes.  Messages, model, sampling and reasoning
    are copied unchanged, so the authored prompt — which already carries
    requiredJsonShape and the runtime invariants — stays byte-identical.
    """
    relaxed = dict(payload)
    relaxed["response_format"] = _json_object_response_format()
    return relaxed



def _strict_schema_capability_keys(payload: dict[str, Any], context: dict[str, Any]) -> tuple[str, str]:
    model = str(payload.get(wire.LLM_MODEL_OVERRIDE_KEY) or "").strip() or resolve_llm_model(context)
    base = profiles._llm_context_key({**context, "model": model, "api_mode": "chat_completions"})
    schema_bytes = json.dumps(payload.get("response_format"), ensure_ascii=False,
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base, base + "|schema=" + hashlib.sha256(schema_bytes).hexdigest()



@diagnostics._bounded_llm_call
def _llm_chat_json_single_context(payload: dict[str, Any], timeout: float, context: dict[str, Any]) -> dict[str, Any]:
    profiles.ensure_llm_auth_configured(context)
    prepared = dict(payload)
    capability_key, schema_key = _strict_schema_capability_keys(payload, context)
    schema_downgraded = False
    # Only successful negotiations establish unsupported format or exact-schema scope.
    if (
        (_STRICT_SCHEMA_CAPABILITY.get(capability_key) is False
         or _STRICT_SCHEMA_CAPABILITY.get(schema_key) is False)
        and isinstance(prepared.get("response_format"), dict)
        and str((prepared.get("response_format") or {}).get("type") or "") == "json_schema"
    ):
        prepared = _payload_without_strict_schema(prepared)
        schema_downgraded = True
        diagnostics._attempt_reason("schema_capability_cached")
    try:
        return _llm_chat_json_exact_context(
            prepared, timeout, context, schema_downgraded=schema_downgraded
        )
    except urlerror.HTTPError as error:
        if schema_downgraded or not rejections._strict_schema_rejected(error, prepared):
            raise
        diagnosis = getattr(error, "_infini_shape_diagnosis", None)
        scope = rejections._strict_schema_rejection_scope(error, prepared)
        # The preceding diagnosis event already carries the full explanation, so
        # this one stays a short "what changed" line: three paragraphs of identical
        # prose in the server window would bury the fact that the craft recovered.
        log_event("warn", "LLM strict json_schema rejected; retrying same stage with json_object for this run", {
            "stage": offline_replay._llm_replay_stage_from_payload(payload),
            "profileId": context.get("profile_id"),
            "provider": profiles.active_llm_provider(context),
            "model": str(context.get("model") or ""),
            "status": error.code,
            "repairedFor": "this run only; config.env is not modified",
            "was": "json_schema",
            "now": "json_object",
            "schemaChars": (diagnosis or {}).get("schemaChars"),
            "configuredResponseFormat": config.LLM_RESPONSE_FORMAT_MODE,
            "detail": (
                "Провайдер явно отклонил json_schema (HTTP 400). Тот же промпт повторяется с "
                "response_format=json_object; успешное восстановление ещё не установлено. "
                "INFINI_LLM_RESPONSE_FORMAT=json_object — кандидат, не доказанная конфигурация. "
                "Cache меняется только после валидного ответа; config.env код не меняет."
            ),
        })
        diagnostics._attempt_reason("json_schema_to_json_object_fallback")
        result = _llm_chat_json_exact_context(
            _payload_without_strict_schema(prepared), timeout, context, schema_downgraded=True
        )
        result = _with_transport_retry_debug(result, ["json_schema_to_json_object_fallback"])
        # A 2xx envelope with malformed authored JSON is not a valid recovery.
        try:
            parse_first_valid_llm_json(result["choices"][0]["message"]["content"])
        except (ValueError, TypeError, KeyError, IndexError):
            return result
        _STRICT_SCHEMA_CAPABILITY[schema_key if scope == "schema" else capability_key] = False
        log_event("info", "LLM schema negotiation accepted", {
            "stage": offline_replay._llm_replay_stage_from_payload(payload), "profileId": context.get("profile_id"),
            "schemaCapabilityScope": scope, "knownWorkingResponseFormat": "json_object",
            "knownWorkingApiMode": "chat_completions",
        })
        return result



def _llm_chat_json_exact_context(
    payload: dict[str, Any],
    timeout: float,
    context: dict[str, Any],
    *,
    schema_downgraded: bool = False,
) -> dict[str, Any]:
    candidate = _payload_for_context(payload, context)
    wire._cache_wire_options(candidate, payload, context, api_mode="chat")
    url = profiles.llm_chat_completions_url(context)
    # This gateway maps OpenAI Chat JSON mode to Responses, whose input check
    # excludes system instructions. Keep the logical packet/cache source intact.
    if (profiles.active_llm_provider(context) == "openai_compat"
            and url == "https://inference-api.nousresearch.com/v1/chat/completions"
            and str(candidate.get("model") or "").startswith("openai/")
            and candidate.get("response_format") == {"type": "json_object"}):
        if instruction_segment_index(payload) is not None:
            marker = {"role": "user", "content": "JSON response."}
            if candidate["messages"][-1] != marker:
                candidate["messages"].append(marker)
        else:
            wire._ensure_json_input_marker(candidate["messages"])
    try:
        result = _perform_llm_http(url, candidate, timeout, context, api_mode="chat_completions")
        choices = result.get("choices") if isinstance(result, dict) else None
        first_choice = choices[0] if isinstance(choices, list) and choices else None
        message = first_choice.get("message") if isinstance(first_choice, dict) else None
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise RuntimeError("LLM provider returned an invalid Chat Completions envelope")
        debug_raw = result.get("_debug")
        debug: dict[str, Any] = debug_raw if isinstance(debug_raw, dict) else {}
        response_format = candidate.get("response_format")
        result["_debug"] = {
            **debug,
            "requestMode": "exact",
            "provider": profiles.active_llm_provider(context),
            "openrouterProvider": profiles._openrouter_provider(context),
            "responseFormatRequested": bool(response_format),
            "responseFormatUsed": bool(response_format),
            "responseFormatType": str(response_format.get("type") or "") if isinstance(response_format, dict) else "",
            "reasoningRequested": bool(candidate.get("reasoning") or candidate.get("reasoning_effort")),
            "reasoningUsed": bool(candidate.get("reasoning") or candidate.get("reasoning_effort")),
            "reasoningEffort": candidate.get("reasoning_effort"),
        }
        if schema_downgraded:
            result["_debug"]["strictSchemaDowngraded"] = True
        return result
    except urlerror.HTTPError as error:
        body = rejections._public_provider_body(http._read_llm_http_error(error, timeout), context)
        provider = profiles.active_llm_provider(context)
        if provider == "openrouter" and error.code == 401:
            message = "OpenRouter auth failed: API key is missing/invalid or was not saved in config.env (401 Unauthorized)."
            log_event("warn", "OpenRouter auth failed", {"provider": provider, "openrouterProvider": profiles._openrouter_provider(context), "status": error.code, "body": body, "hint": message, "label": context.get("label")})
            raise RuntimeError(message) from error
        log_event("warn", "LLM HTTP error", {"provider": provider, "openrouterProvider": profiles._openrouter_provider(context), "status": error.code, "body": body, "label": context.get("label")})
        diagnosis = rejections.request_shape_rejection_diagnosis(error, candidate, context)
        if diagnosis is not None:
            setattr(error, "_infini_shape_diagnosis", diagnosis)
            log_event("warn", "LLM provider rejected the configured request shape", {
                **diagnosis,
                "label": context.get("label"),
            })
        raise



def _is_profile_failover_failure(error: Exception) -> bool:
    return (
        rejections._is_budget_or_auth_failure(error)
        or rejections._is_transport_error(error)
        or isinstance(error, (urlerror.HTTPError, RuntimeError, ValueError, KeyError, json.JSONDecodeError))
    )



def _with_transport_retry_debug(
    result: dict[str, Any],
    causes: list[str],
    *,
    prior_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not causes and prior_result is None:
        return result
    debug_candidate = result.get("_debug")
    debug: dict[str, Any] = debug_candidate if isinstance(debug_candidate, dict) else {}
    prior_debug_candidate = prior_result.get("_debug") if isinstance(prior_result, dict) else None
    prior_debug: dict[str, Any] = prior_debug_candidate if isinstance(prior_debug_candidate, dict) else {}
    existing_causes = [str(value) for value in debug.get("transportRetryCauses") or []]
    prior_causes = [str(value) for value in prior_debug.get("transportRetryCauses") or []]
    result["_debug"] = {
        **debug,
        "transportRetryCount": (
            int(prior_debug.get("transportRetryCount") or 0)
            + int(debug.get("transportRetryCount") or 0)
            + len(causes)
        ),
        "transportRetryCauses": [*prior_causes, *existing_causes, *causes],
    }
    return result



@diagnostics._bounded_llm_call
def _llm_json_single_context_with_length_retry(
    payload: dict[str, Any],
    timeout: float,
    context: dict[str, Any],
) -> dict[str, Any]:
    result = _llm_json_single_context(payload, timeout, context)
    choices = result.get("choices") if isinstance(result, dict) else None
    first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    model_name = str(payload.get(wire.LLM_MODEL_OVERRIDE_KEY) or resolve_llm_model(context) or "")
    finish_reason = str(first.get("finish_reason") or "").lower()
    raw_message = first.get("message")
    message = raw_message if isinstance(raw_message, dict) else {}
    content = str(message.get("content") or "")
    malformed_json = False
    complete_json = False
    json_response_expected = isinstance(payload.get("response_format"), dict)
    if json_response_expected or finish_reason == "length":
        try:
            parse_first_valid_llm_json(content)
            complete_json = True
        except (ValueError, TypeError, json.JSONDecodeError):
            malformed_json = json_response_expected
    gemini_length = (
        finish_reason == "length"
        and not complete_json
        and "gemini-3.1-flash" in model_name.lower()
        and wire._is_google_openai_compat_reasoning_model(model_name, context)
    )
    if not gemini_length and not malformed_json:
        return result
    # A total network-attempt budget of one is an acceptance contract: no
    # content retry may silently turn one logical stage into a second HTTP
    # request. The malformed response is returned to the caller for normal
    # domain failure accounting.
    if int(config.LLM_FALLBACK_NETWORK_FAILS or 2) <= 1:
        return result

    retry_payload = copy.deepcopy(payload)
    if gemini_length:
        retry_payload.pop("reasoning", None)
        retry_payload.pop("reasoning_effort", None)
        retry_payload[wire._REASONING_INTENT_KEY] = {"effort": "minimal", "exclude": bool(config.LLM_REASONING_EXCLUDE)}
    retry_cause = "length" if gemini_length else "malformed_json"
    log_event("warn", "retrying incomplete JSON LLM response within the same logical call", {
        "provider": profiles.active_llm_provider(context),
        "model": model_name,
        "finishReason": finish_reason,
        "cause": retry_cause,
    })
    diagnostics._attempt_reason(retry_cause)
    retry_result = _llm_json_single_context(retry_payload, timeout, context)
    return _with_transport_retry_debug(retry_result, [retry_cause], prior_result=result)



def _payload_without_model_override(payload: dict[str, Any]) -> dict[str, Any]:
    if wire.LLM_MODEL_OVERRIDE_KEY not in payload:
        return payload
    out = copy.deepcopy(payload)
    out.pop(wire.LLM_MODEL_OVERRIDE_KEY, None)
    return out



@diagnostics._bounded_llm_call
def llm_chat_json(payload: dict[str, Any], timeout: float = 10) -> dict[str, Any]:
    mode = _record_llm_stage(payload)

    def finish(result: dict[str, Any], used_payload: dict[str, Any]) -> dict[str, Any]:
        return diagnostics._with_transport_footprint(result, used_payload, mode)

    lease = profiles._CURRENT_LLM_ITEM_LEASE.get()
    if profiles.active_llm_provider(profiles._primary_llm_context()) == "openai_codex":
        # A subscription quota/auth failure must never switch silently to a
        # paid Platform/OpenRouter route or multiply one stage into retries.
        return finish(_llm_json_single_context(payload, timeout, profiles._primary_llm_context()), payload)
    if lease is not None and lease.pool_size > 1:
        attempted: set[str] = set()
        retry_causes: list[str] = []
        override_profile_id = lease.initial_profile_id
        while True:
            context = lease.context
            attempted.add(lease.profile_id)
            attempt_payload = payload if lease.profile_id == override_profile_id else _payload_without_model_override(payload)
            try:
                result = _llm_json_single_context_with_length_retry(attempt_payload, timeout, context)
                return finish(_with_transport_retry_debug(result, retry_causes), attempt_payload)
            except Exception as profile_error:
                remaining_seconds(diagnostics._request_deadline(timeout))
                if not _is_profile_failover_failure(profile_error):
                    raise
                profiles._mark_profile_failed(context, profile_error)
                if int(config.LLM_FALLBACK_NETWORK_FAILS or 2) <= 1:
                    raise
                next_context = profiles._next_lease_profile(lease, attempted)
                if next_context is None:
                    raise
                retry_causes.append("profile_failover")
                diagnostics._attempt_reason("profile_failover")
                profiles._switch_lease_profile(lease, next_context, profile_error)

    primary = profiles._primary_llm_context()
    fallback = (
        profiles._fallback_llm_context()
        if not profiles._openrouter_provider(primary) and (lease is None or lease.legacy_fallback_allowed)
        else None
    )
    primary_payload = payload
    if lease is not None and lease.profile_id != lease.initial_profile_id:
        primary_payload = _payload_without_model_override(payload)
    try:
        result = _llm_json_single_context_with_length_retry(primary_payload, timeout, primary)
        return finish(result, primary_payload)
    except Exception as first_error:
        remaining_seconds(diagnostics._request_deadline(timeout))
        if not fallback:
            if not rejections._is_transport_error(first_error):
                raise
            last_error = first_error
            retry_causes: list[str] = []
            total_attempts = max(1, int(config.LLM_FALLBACK_NETWORK_FAILS or 2))
            for attempt in range(2, total_attempts + 1):
                retry_causes.append("transient_http")
                diagnostics._attempt_reason("transient_http")
                delay = min(1.5, 0.2 * (2 ** (attempt - 2)))
                log_event("warn", "retrying transient LLM failure without fallback", {
                    "attempt": attempt,
                    "maxAttempts": total_attempts,
                    "delaySeconds": delay,
                    "provider": profiles.active_llm_provider(primary),
                    "model": primary.get("model"),
                    "status": getattr(last_error, "code", None),
                })
                _llm_backoff(delay)
                try:
                    result = _llm_json_single_context_with_length_retry(primary_payload, timeout, primary)
                    return finish(_with_transport_retry_debug(result, retry_causes), primary_payload)
                except Exception as retry_error:
                    last_error = retry_error
                    if not rejections._is_transport_error(retry_error):
                        raise
            raise last_error

        if rejections._is_budget_or_auth_failure(first_error):
            log_event("warn", "LLM primary failed; switching to fallback", {"reason": "budget_or_auth", "primaryProvider": profiles.active_llm_provider(primary), "primaryModel": primary.get("model"), "fallbackProvider": profiles.active_llm_provider(fallback), "fallbackModel": fallback.get("model")})
            diagnostics._attempt_reason("legacy_fallback")
            profiles._switch_lease_to_legacy_fallback(lease, fallback)
            fallback_payload = _payload_without_model_override(payload)
            result = _llm_json_single_context_with_length_retry(fallback_payload, timeout, fallback)
            return finish(_with_transport_retry_debug(result, ["budget_or_auth_fallback"]), fallback_payload)

        if rejections._is_transport_error(first_error):
            last_error = first_error
            retry_causes = []
            total_attempts = max(1, int(config.LLM_FALLBACK_NETWORK_FAILS or 2))
            for attempt in range(2, total_attempts + 1):
                retry_causes.append("primary_transport")
                diagnostics._attempt_reason("primary_transport")
                try:
                    log_event("warn", "retrying primary LLM transport before fallback", {"attempt": attempt, "maxAttempts": total_attempts, "provider": profiles.active_llm_provider(primary), "model": primary.get("model")})
                    result = _llm_json_single_context_with_length_retry(primary_payload, timeout, primary)
                    return finish(_with_transport_retry_debug(result, retry_causes), primary_payload)
                except Exception as retry_error:
                    last_error = retry_error
                    if rejections._is_budget_or_auth_failure(retry_error):
                        log_event("warn", "LLM primary changed from transport failure to budget/auth failure; switching to fallback", {"provider": profiles.active_llm_provider(primary), "fallbackProvider": profiles.active_llm_provider(fallback), "fallbackModel": fallback.get("model")})
                        diagnostics._attempt_reason("legacy_fallback")
                        profiles._switch_lease_to_legacy_fallback(lease, fallback)
                        fallback_payload = _payload_without_model_override(payload)
                        result = _llm_json_single_context_with_length_retry(fallback_payload, timeout, fallback)
                        retry_causes.append("budget_or_auth_fallback")
                        return finish(_with_transport_retry_debug(result, retry_causes), fallback_payload)
                    if not rejections._is_transport_error(retry_error):
                        raise
            log_event("warn", "LLM primary transport failed repeatedly; switching to fallback", {"attempts": total_attempts, "primaryProvider": profiles.active_llm_provider(primary), "primaryModel": primary.get("model"), "fallbackProvider": profiles.active_llm_provider(fallback), "fallbackModel": fallback.get("model")})
            diagnostics._attempt_reason("legacy_fallback")
            profiles._switch_lease_to_legacy_fallback(lease, fallback)
            fallback_payload = _payload_without_model_override(payload)
            result = _llm_json_single_context_with_length_retry(fallback_payload, timeout, fallback)
            retry_causes.append("primary_transport_fallback")
            return finish(_with_transport_retry_debug(result, retry_causes), fallback_payload)
        raise
