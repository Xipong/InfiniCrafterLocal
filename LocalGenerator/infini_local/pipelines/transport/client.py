"""Execute logical LLM requests with one deadline across physical attempts.

Profiles own leases and cooldowns, admission owns quota waits, and provider wire
owns payload projection. This executor owns HTTP, diagnostics and negotiation.
"""
from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
import copy
import hashlib
import json
import re
from pathlib import Path
import threading
import time
from typing import Any
from urllib import request as urlrequest
from urllib import error as urlerror

from infini_local.core import llm_config as config
from infini_local.core.env_utils import env_str
from infini_local.core.http_io import HttpDeadlineExceeded, HttpResponseTooLarge, remaining_seconds, read_with_deadline, urlopen_no_redirect
from infini_local.core.llm_prompt_cache import PROMPT_CACHE_METADATA_KEY, static_instruction_prefix_parts, instruction_segment_index
from infini_local.core.llm_json_tools import parse_first_valid_llm_json
from infini_local.pipelines.transport import admission
from infini_local.pipelines.transport import profiles
from infini_local.pipelines.transport import provider_wire as wire
from infini_local.storage.trace_runtime import log_event
from infini_local.storage.failure_state import PROVIDER_ERROR_CODES, PROVIDER_ERROR_PARAMS
from infini_local.services.combine_endpoint import update_generation_activity


_CURRENT_LLM_DEADLINE: ContextVar[float | None] = ContextVar("infini_llm_deadline", default=None)
_CURRENT_LLM_DIAGNOSTICS: ContextVar[dict[str, Any] | None] = ContextVar("infini_llm_diagnostics", default=None)
_CURRENT_LLM_ATTEMPT: ContextVar[dict[str, Any] | None] = ContextVar("infini_llm_attempt", default=None)
_LLM_MAX_DIAGNOSTIC_ATTEMPTS = 16
# Bound complete successful JSON bodies as well as provider error evidence.
MAX_PROVIDER_JSON_BYTES = 16 * 1024 * 1024
_LLM_CALL_SEQUENCE = 0
_LLM_CALL_LOCK = threading.Lock()


def _request_deadline(timeout: float) -> float:
    requested = time.monotonic() + float(timeout)
    current = _CURRENT_LLM_DEADLINE.get()
    return min(current, requested) if current is not None else requested


def _bounded_llm_call(call):
    """Share one budget across negotiation, retries, failover and body reads."""
    @wraps(call)
    def bounded(payload, timeout=10, *args, **kwargs):
        deadline = _CURRENT_LLM_DEADLINE.get()
        token = None
        if deadline is None:
            deadline = _request_deadline(timeout)
            token = _CURRENT_LLM_DEADLINE.set(deadline)
        diagnostic_token = None
        state = None
        if call.__name__ == "llm_chat_json" and _CURRENT_LLM_DIAGNOSTICS.get() is None:
            state = _new_llm_diagnostics(payload)
            diagnostic_token = _CURRENT_LLM_DIAGNOSTICS.set(state)
        try:
            remaining_seconds(deadline)
            result = call(payload, timeout, *args, **kwargs)
            if state is not None:
                result["_debug"] = {**(result.get("_debug") or {}), **_llm_diagnostic_summary(state)}
                log_event("info", "LLM logical call finished", {**_llm_diagnostic_summary(state), "outcome": "success"})
            return result
        except Exception as error:
            if state is not None:
                summary = _llm_diagnostic_summary(state)
                summary.update(_failure_metadata(error, state["lastAttempt"]))
                setattr(error, "_infini_transport_debug", summary)
                log_event("warn", "LLM logical call failed", {**summary, "outcome": "failure", "errorType": type(error).__name__})
            raise
        finally:
            if diagnostic_token is not None:
                _CURRENT_LLM_DIAGNOSTICS.reset(diagnostic_token)
            if token is not None:
                _CURRENT_LLM_DEADLINE.reset(token)
    return bounded


def _reasoning_diagnostic(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("reasoning") or payload.get(wire._REASONING_INTENT_KEY)
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    effort = payload.get("reasoning_effort") or raw.get("effort")
    if effort:
        out["effort"] = effort if isinstance(effort, str) and effort in wire._REASONING_EFFORT_RANK else "unsupported"
    if type(raw.get("max_tokens")) is int:
        out["max_tokens"] = max(0, min(64000, raw["max_tokens"]))
    for name in ("enabled", "exclude"):
        if type(raw.get(name)) is bool:
            out[name] = raw[name]
    return out


def _format_diagnostic(payload: dict[str, Any]) -> str:
    raw = payload.get("response_format")
    if not isinstance(raw, dict):
        text = payload.get("text")
        raw = text.get("format") if isinstance(text, dict) else None
    mode = raw.get("type") if isinstance(raw, dict) else "text"
    return mode if isinstance(mode, str) and mode in {"json_schema", "json_object", "text"} else "unsupported"


def _new_llm_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    global _LLM_CALL_SEQUENCE
    with _LLM_CALL_LOCK:
        _LLM_CALL_SEQUENCE += 1
        sequence = _LLM_CALL_SEQUENCE
    lease = profiles._CURRENT_LLM_ITEM_LEASE.get()
    return {
        "logicalCallId": f"{lease.lease_id if lease else 'standalone'}:call:{sequence}",
        "stage": _llm_replay_stage_from_payload(payload), "leaseId": lease.lease_id if lease else "",
        "requestedApiMode": profiles._normalized_api_mode(profiles._primary_llm_context().get("api_mode")),
        "requestedResponseFormat": _format_diagnostic(payload), "requestedReasoning": _reasoning_diagnostic(payload),
        "physicalAttemptCount": 0, "physicalAttemptsDropped": 0, "physicalAttempts": [],
        "lastAttempt": {}, "nextReason": "initial", "rateWaitMsTotal": 0.0, "diagnosticEventCount": 0,
    }


def _llm_diagnostic_summary(state: dict[str, Any]) -> dict[str, Any]:
    last = state["lastAttempt"]
    return {
        **{name: state[name] for name in ("logicalCallId", "stage", "leaseId", "requestedApiMode",
           "requestedResponseFormat", "requestedReasoning", "physicalAttemptCount", "physicalAttemptsDropped", "rateWaitMsTotal")},
        "physicalAttempts": copy.deepcopy(state["physicalAttempts"]),
        "rateWaitReason": last.get("rateWaitReason", "none"),
        "physicalAttemptScope": "llm_generation_http_post" if state["physicalAttemptCount"] is not None else "codex_owner_unobserved",
        "effectiveApiMode": last.get("effectiveApiMode"), "effectiveResponseFormat": last.get("effectiveResponseFormat"),
        "effectiveReasoning": copy.deepcopy(last.get("effectiveReasoning")),
    }


def _attempt_reason(reason: str) -> None:
    state = _CURRENT_LLM_DIAGNOSTICS.get()
    if state is not None:
        state["nextReason"] = reason


def _public_provider_body(body: str, context: dict[str, Any]) -> str:
    # Provider errors may reflect Authorization; retain internal evidence, not credentials in traces.
    secret = str(context.get("api_key") or "")
    try:
        body = json.dumps(json.loads(body), ensure_ascii=False)
    except (ValueError, TypeError):
        pass
    return body.replace(secret, "[redacted]")[:600] if secret else body[:600]


def _provider_error_metadata(body: str) -> dict[str, str | None]:
    # Finite vocabulary, not arbitrary provider strings that may echo secrets.
    try:
        parsed = json.loads(body)
        error = parsed.get("error") if isinstance(parsed, dict) else None
    except (ValueError, TypeError):
        error = None
    if not isinstance(error, dict):
        return {}
    return {
        "providerErrorCode": error.get("code") if error.get("code") in PROVIDER_ERROR_CODES else None,
        "providerErrorParam": error.get("param") if error.get("param") in PROVIDER_ERROR_PARAMS else None,
    } if all(type(error.get(k)) in {str, type(None)} for k in ("code", "param")) else {}


def _failure_metadata(error: BaseException, last: dict[str, Any]) -> dict[str, Any]:
    status = last.get("httpStatus")
    code = last.get("providerErrorCode")
    category = "provider_failure"
    if isinstance(error, HttpDeadlineExceeded):
        category = "admission_timeout" if last.get("networkStarted") is False and last.get("rateWaitReason", "none") != "none" else "logical_timeout"
    elif code in {"model_not_found", "model_unavailable", "invalid_model"}:
        category = "model_unavailable"
    elif status in {401, 403}:
        category = "auth_failed"
    elif status == 402 or code in {"insufficient_quota", "quota_exceeded"}:
        category = "quota_exhausted"
    elif status == 429:
        category = "rate_limited"
    elif status == 404:
        category = "endpoint_unavailable"
    elif status in {400, 422}:
        category = "request_rejected"
    elif isinstance(error, (TimeoutError, urlerror.URLError, ConnectionError)):
        category = "transport_unavailable"
    return {"failureCategory": category, **{name: last[name] for name in ("httpStatus", "providerErrorCode", "providerErrorParam", "networkStarted") if name in last}}


def _perform_llm_http(url: str, wire: dict[str, Any], timeout: float, context: dict[str, Any], *, api_mode: str) -> dict[str, Any]:
    state = _CURRENT_LLM_DIAGNOSTICS.get()
    if state is None:
        return http_json(url, wire, timeout=timeout, headers=profiles.llm_headers(context=context))
    effective_reasoning = _reasoning_diagnostic(wire)
    row = {
        **{name: state[name] for name in ("logicalCallId", "stage", "leaseId", "requestedApiMode", "requestedResponseFormat", "requestedReasoning")},
        "profileId": profiles._profile_id(context), "provider": profiles.active_llm_provider(context),
        "openrouterProvider": profiles._openrouter_provider(context),
        "effectiveApiMode": api_mode, "effectiveResponseFormat": _format_diagnostic(wire),
        "effectiveReasoning": effective_reasoning,
        "unsupportedReasoningFields": sorted(set(state["requestedReasoning"]) - set(effective_reasoning)),
        "reason": state["nextReason"], "networkStarted": None, "httpStatus": None,
        "physicalAttemptIndex": None, "rateWaitMs": 0.0, "rateWaitReason": "none",
        "connectMs": None, "openMs": 0.0, "readMs": 0.0,
    }
    token = _CURRENT_LLM_ATTEMPT.set(row)
    try:
        return http_json(url, wire, timeout=timeout, headers=profiles.llm_headers(context=context))
    except urlerror.HTTPError as error:
        row["httpStatus"] = error.code
        row.update(_provider_error_metadata(_read_llm_http_error(error, timeout)))
        row["errorType"] = type(error).__name__
        raise
    except Exception as error:
        row["errorType"] = type(error).__name__
        raise
    finally:
        row["deadlineRemainingMs"] = round(max(0.0, _request_deadline(timeout) - time.monotonic()) * 1000, 3)
        state["rateWaitMsTotal"] += row["rateWaitMs"]
        if row["networkStarted"] is True:
            state["physicalAttemptCount"] += 1
            row["physicalAttemptIndex"] = state["physicalAttemptCount"]
        state["lastAttempt"] = row
        if state["diagnosticEventCount"] < _LLM_MAX_DIAGNOSTIC_ATTEMPTS:
            if row["networkStarted"] is True:
                state["physicalAttempts"].append(copy.deepcopy(row))
            log_event("info", "LLM physical attempt" if row["networkStarted"] is True else "LLM transport wait", row)
        elif row["networkStarted"] is True:
            state["physicalAttemptsDropped"] += 1
        state["diagnosticEventCount"] += 1
        _CURRENT_LLM_ATTEMPT.reset(token)
        update_generation_activity(wait_reason="none")


def _llm_backoff(seconds: float) -> None:
    deadline = _CURRENT_LLM_DEADLINE.get()
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
# Per-run memory of whether a profile accepts strict provider-side json_schema.
# Discovered from the provider's own rejection, never configured: once a profile
# has refused the schema, later stages in the same run stop paying for a request
# that is already known to be rejected.
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


def http_get_json(url: str, timeout: float = 5, headers: dict[str, str] | None = None) -> dict[str, Any]:
    merged = {"Accept": "application/json"}
    if headers:
        merged.update(headers)
    req = urlrequest.Request(url, headers=merged, method="GET")
    deadline = _request_deadline(timeout)
    try:
        with urlopen_no_redirect(req, deadline=deadline) as resp:
            return json.loads(read_with_deadline(resp, deadline=deadline, max_bytes=MAX_PROVIDER_JSON_BYTES).decode("utf-8"))
    except urlerror.HTTPError as error:
        error.close()
        raise

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
        models = http_get_json(profiles.llm_models_url(ctx), timeout=6, headers=profiles.llm_headers({"Accept": "application/json"}, context=ctx))
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


def http_json(url: str, payload: dict[str, Any], timeout: float = 10, headers: dict[str, str] | None = None, *, max_response_bytes: int | None = MAX_PROVIDER_JSON_BYTES) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    deadline = _request_deadline(timeout)
    row = _CURRENT_LLM_ATTEMPT.get()
    if row is not None:
        row["networkStarted"] = False
    update_generation_activity(wait_reason="none", network_started=False)
    wait_started = time.monotonic()
    try:
        admission._reserve_remote_rate_slot(url, payload, data, max_wait_seconds=remaining_seconds(deadline), attempt=row)
    finally:
        if row is not None:
            row["rateWaitMs"] = round((time.monotonic() - wait_started) * 1000, 3)
    remaining_seconds(deadline)
    merged = {"Content-Type": "application/json"}
    if headers:
        merged.update(headers)
    req = urlrequest.Request(url, data=data, headers=merged, method="POST")
    try:
        open_started = time.monotonic()
        if row is not None:
            row["networkStarted"] = True
        update_generation_activity(wait_reason="none", network_started=True)
        try:
            response = urlopen_no_redirect(req, deadline=deadline)
        finally:
            if row is not None:
                row["openMs"] = round((time.monotonic() - open_started) * 1000, 3)
        with response as resp:
            admission._observe_remote_quota_headers(url, payload, getattr(resp, "headers", None), attempt=row)
            if row is not None:
                row["httpStatus"] = resp.status
            read_started = time.monotonic()
            try:
                raw = read_with_deadline(resp, deadline=deadline, max_bytes=max_response_bytes)
            finally:
                if row is not None:
                    row["readMs"] = round((time.monotonic() - read_started) * 1000, 3)
            result = json.loads(raw.decode("utf-8"))
            if isinstance(result, dict):
                result.pop("_debug", None)  # Client-owned metadata, never a provider-controlled trace injection.
            return result
    except urlerror.HTTPError as error:
        setattr(error, "_infini_deadline", deadline)
        admission._observe_remote_quota_headers(url, payload, error.headers, attempt=row)
        if error.code == 429:
            admission._mark_remote_rate_limited(url, payload, error)
        raise

def _read_llm_http_error(error: urlerror.HTTPError, timeout: float) -> str:
    existing = getattr(error, "_infini_body", None)
    if existing is not None:
        return str(existing)
    deadline = min(_request_deadline(timeout), getattr(error, "_infini_deadline", float("inf")))
    row = _CURRENT_LLM_ATTEMPT.get()
    read_started = time.monotonic()
    try:
        body = read_with_deadline(error, deadline=deadline, max_bytes=2000).decode("utf-8", "replace")
    except HttpResponseTooLarge:
        body = ""  # Incomplete evidence must not establish a capability rejection.
    except HttpDeadlineExceeded:
        raise
    except Exception:
        body = ""
    finally:
        error.close()
        if row is not None:
            row["readMs"] += round((time.monotonic() - read_started) * 1000, 3)
    setattr(error, "_infini_body", body)
    return body


def _llm_replay_stage_from_payload(payload: dict[str, Any]) -> str:
    """Read explicit finite transport metadata; never inspect prompt content."""
    return wire._normalized_llm_stage(payload.get(wire.LLM_STAGE_KEY))

def _replay_content_from_json_object(obj: Any, stage: str) -> str | None:
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        # Stage-keyed JSON object: {"planner":"...", "vfx_director":"..."}.
        direct = obj.get(stage)
        if isinstance(direct, str):
            return direct
        for key in ("content", "text", "response", "raw"):
            value = obj.get(key)
            if isinstance(value, str):
                return value
        choices = obj.get("choices")
        if isinstance(choices, list) and choices:
            try:
                content = choices[0]["message"]["content"]
                if isinstance(content, str):
                    return content
            except Exception:
                return None
    return None

def _load_llm_replay_raw(spec: str, stage: str) -> tuple[str, str]:
    path = Path(spec).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"INFINI_LLM_REPLAY_RAW path does not exist: {path}")

    if path.is_dir():
        candidates = [
            path / f"{stage}.txt",
            path / f"{stage}.json",
            path / f"{stage}.jsonl",
            path / "default.txt",
            path / "default.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                content, source = _load_llm_replay_raw(str(candidate), stage)
                return content, source
        raise FileNotFoundError(f"No replay fixture for LLM stage '{stage}' in {path}")

    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8")
    if suffix == ".json":
        content = _replay_content_from_json_object(json.loads(raw), stage)
        if content is None:
            raise ValueError(f"Could not extract replay content from {path}")
        return content, str(path)

    if suffix == ".jsonl":
        fallback: str | None = None
        for line in raw.splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                obj_stage = str(obj.get("stage") or obj.get("hop") or obj.get("kind") or "").strip()
                content = _replay_content_from_json_object(obj, stage)
                if content is None:
                    continue
                if obj_stage in {stage, "*", "all", "llm"}:
                    return content, f"{path}#{obj_stage or 'line'}"
                if fallback is None and not obj_stage:
                    fallback = content
            elif fallback is None and isinstance(obj, str):
                fallback = obj
        if fallback is not None:
            return fallback, f"{path}#fallback"
        raise ValueError(f"No replay content for LLM stage '{stage}' in {path}")

    return raw, str(path)

def _llm_replay_json_response(payload: dict[str, Any]) -> dict[str, Any] | None:
    spec = env_str("INFINI_LLM_REPLAY_RAW", "")
    if not spec:
        return None
    stage = _llm_replay_stage_from_payload(payload)
    content, source = _load_llm_replay_raw(spec, stage)
    log_event("info", "LLM replay raw response used", {"stage": stage, "source": source, "chars": len(content)})
    return {
        "choices": [
            {"message": {"role": "assistant", "content": content}}
        ],
        "_debug": {"replay": True, "stage": stage, "source": source},
    }

def _llm_error_text(exc: Exception) -> str:
    parts = [repr(exc), str(exc)]
    body = getattr(exc, "_infini_body", "")
    if body:
        parts.append(str(body))
    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        parts.append(repr(cause))
        parts.append(str(cause))
    return " | ".join(p for p in parts if p).lower()

def _is_transport_error(exc: Exception) -> bool:
    # HTTPError is a URLError subclass. Handle it first and return decisively;
    # otherwise permanent 400/401/403/404 responses fall through to the broad
    # URLError branch and consume quota in a guaranteed-useless retry.
    if isinstance(exc, urlerror.HTTPError):
        return exc.code in {408, 409, 425, 429, 500, 502, 503, 504}
    if isinstance(exc, (urlerror.URLError, TimeoutError, ConnectionError)):
        return True
    text = _llm_error_text(exc)
    return any(tok in text for tok in ["timed out", "timeout", "connection refused", "connection reset", "temporarily unavailable", "name or service not known", "nodename nor servname", "failed to establish a new connection", "remote end closed connection"])

def _is_budget_or_auth_failure(exc: Exception) -> bool:
    if isinstance(exc, urlerror.HTTPError) and exc.code in {401, 402, 403, 429}:
        return True
    text = _llm_error_text(exc)
    return any(tok in text for tok in ["insufficient", "quota", "credit", "billing", "payment", "out of credits", "rate limit", "unauthorized", "api key", "余额", "balance", "no money"])


# Only endpoint/request-shape incompatibility may downgrade Responses to Chat on
# the same profile. Timeouts, malformed responses and 5xx failures belong to the
# lease/pool failover owner; hiding them here would bypass provider isolation.
_RESPONSES_CHAT_COMPATIBILITY_STATUSES = frozenset({400, 404, 405, 415, 422, 501})


def request_shape_rejection_diagnosis(
    exc: Exception,
    payload: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Explain a provider request-shape rejection in terms of the user's own transport settings.

    Diagnostics only: it never selects a format, never retries and never mutates
    the payload.  A provider that rejects the request shape (typically HTTP 400)
    tells the user nothing actionable, so name the exact configuration that
    produced the rejected wire and the exact configuration known to be accepted.
    The transport's own per-run recovery is reported separately, by the caller
    that performs it.
    """
    request = payload if isinstance(payload, dict) else {}
    if not isinstance(exc, urlerror.HTTPError) or not _strict_schema_rejected(exc, request):
        return None
    response_format = request.get("response_format")
    response_mode = (
        str(response_format.get("type") or "") if isinstance(response_format, dict) else ""
    )
    if response_mode != "json_schema":
        return None
    schema_root = response_format.get("json_schema") if isinstance(response_format, dict) else None
    schema = schema_root.get("schema") if isinstance(schema_root, dict) else None
    schema_chars = len(json.dumps(schema, ensure_ascii=False, default=str)) if schema is not None else 0
    api_mode = profiles._normalized_api_mode((context or {}).get("api_mode"))
    return {
        "code": "provider_rejected_request_shape",
        "status": exc.code,
        "providerBody": _public_provider_body(str(getattr(exc, "_infini_body", "")), context or {}),
        "provider": profiles.active_llm_provider(context),
        "model": str((context or {}).get("model") or ""),
        "baseUrl": str((context or {}).get("base_url") or ""),
        "configuredResponseFormat": config.LLM_RESPONSE_FORMAT_MODE,
        "sentResponseFormat": response_mode,
        "configuredApiMode": api_mode,
        "openrouterProvider": profiles._openrouter_provider(context or profiles._primary_llm_context()),
        "schemaChars": schema_chars,
        "knownWorkingResponseFormat": "",
        "knownWorkingApiMode": "",
        "candidateResponseFormat": "json_object",
        "candidateApiMode": "chat_completions",
        "schemaCapabilityScope": _strict_schema_rejection_scope(exc, request),
        "hint": (
            "Провайдер явно отклонил json_schema/response_format; по одному статусу 400 причина не определяется. "
            f"Отправлен response_format={response_mode} (INFINI_LLM_RESPONSE_FORMAT={config.LLM_RESPONSE_FORMAT_MODE}), "
            f"схема {schema_chars} символов, INFINI_LLM_API_MODE={api_mode}. "
            "Кандидат для того же промпта — INFINI_LLM_RESPONSE_FORMAT=json_object и "
            "INFINI_LLM_API_MODE=chat_completions. Пригодность этой комбинации ещё не проверена; "
            "process cache меняется только после успешного ответа с валидным JSON. config.env код не меняет сам."
        ),
    }


def _responses_chat_fallback_allowed(exc: Exception) -> bool:
    if not isinstance(exc, urlerror.HTTPError) or exc.code not in _RESPONSES_CHAT_COMPATIBILITY_STATUSES:
        return False
    body = str(getattr(exc, "_infini_body", "")).lower()
    try:
        decoded = json.loads(body)
    except (ValueError, TypeError):
        decoded = None
    error = decoded.get("error") if isinstance(decoded, dict) else None
    error = error if isinstance(error, dict) else {}
    param = str(error.get("param") or "")
    if param in {"messages", "model", "temperature", "max_tokens"} or any(value in body for value in (
        "context_length", "context length", "context limit", "invalid_messages", "model_not_found",
    )):
        return False
    if exc.code in {404, 405, 415, 501}:
        return True
    return any(value in body for value in (
        "responses endpoint not supported", "responses api not supported", "unsupported endpoint",
        "unsupported_parameter", "unsupported parameter", "unrecognized request argument",
    ))

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
        _read_llm_http_error(error, timeout)
        raise


def _record_llm_stage(payload: dict[str, Any]) -> str:
    stage = _llm_replay_stage_from_payload(payload)
    lease = profiles._CURRENT_LLM_ITEM_LEASE.get()
    if lease is not None:
        lease.call_count += 1
        lease.stages.append(stage)
    return stage


@_bounded_llm_call
def _llm_json_single_context(payload: dict[str, Any], timeout: float, context: dict[str, Any]) -> dict[str, Any]:
    stage = _llm_replay_stage_from_payload(payload)
    # Raw replay is an explicit offline seam.  Resolve it before choosing
    # Responses vs Chat so auto/responses profiles can never make a network
    # call merely because replay used to live inside the Chat-only helper.
    replay = _llm_replay_json_response(payload)
    if replay is not None:
        return replay
    if profiles.active_llm_provider(context) == "openai_codex":
        from infini_local.services.codex_text_backend import generate_chat, _request_payload
        prepared = _payload_for_context(payload, context)
        if wire._prompt_cache_boundary(payload) is not None:
            identity_source = {**prepared, PROMPT_CACHE_METADATA_KEY: payload[PROMPT_CACHE_METADATA_KEY]}
            prepared["prompt_cache_key"] = wire._prompt_cache_identity(identity_source, str(prepared["model"]), context=context)
        state = _CURRENT_LLM_DIAGNOSTICS.get()
        if state is not None:
            state["physicalAttemptCount"] = None  # Unknown until the generation owner reports; excludes auth I/O.
            codex_wire = _request_payload(prepared)
            state["lastAttempt"] = {
                "effectiveApiMode": "codex_subscription_sse",
                "effectiveResponseFormat": _format_diagnostic(codex_wire),
                "effectiveReasoning": _reasoning_diagnostic(codex_wire),
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
                if len(state["physicalAttempts"]) < _LLM_MAX_DIAGNOSTIC_ATTEMPTS:
                    state["physicalAttempts"].append(copy.deepcopy(row))
                else:
                    state["physicalAttemptsDropped"] += 1
        with generation_observations(join, observe_codex):
            result = generate_chat(prepared, timeout=remaining_seconds(_request_deadline(timeout)))
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
            if _is_budget_or_auth_failure(error) or not _responses_chat_fallback_allowed(error):
                raise
            had_working_chain = bool(lease is not None and lease.context is context and lease.previous_response_id)
            if had_working_chain:
                _RESPONSES_CAPABILITY[capability_key] = True
            if lease is not None and lease.context is context:
                lease.responses_disabled = True
                lease.previous_response_id = ""
            responses_to_chat_fallback = True
            _attempt_reason("responses_to_chat_fallback")
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


def _strict_schema_rejection_scope(exc: Exception, payload: dict[str, Any]) -> str:
    """Relevant provider evidence only: unsupported format vs this exact schema."""
    if not isinstance(exc, urlerror.HTTPError) or exc.code != 400:
        return ""
    response_format = payload.get("response_format")
    if not isinstance(response_format, dict) or response_format.get("type") != "json_schema":
        return ""
    body = str(getattr(exc, "_infini_body", ""))
    try:
        decoded = json.loads(body)
    except (ValueError, TypeError):
        decoded = None
    details = decoded.get("error") if isinstance(decoded, dict) else None
    details = details if isinstance(details, dict) else {}
    param = str(details.get("param") or "").lower()
    code = str(details.get("code") or "").lower()
    text = str(details.get("message") or body).lower()
    if param and not param.startswith(("response_format", "text.format", "json_schema")):
        return ""
    if any(value in code + " " + text for value in (
        "context_length", "context length", "context limit", "invalid_messages", "model_not_found",
    )):
        return ""
    schema_named = bool(re.search(r"json[_ -]schema|response_format|strict schema", text + " " + code + " " + param))
    if not schema_named:
        return ""
    if any(value in code + " " + text + " " + param for value in (
        "complexity", "too complex", "too large", "nesting", "invalid_json_schema", ".schema",
    )):
        return "schema"
    if any(value in text + " " + code for value in (
        "not supported", "unsupported", "does not support", "not available",
    )):
        return "profile"
    return ""


def _strict_schema_rejected(exc: Exception, payload: dict[str, Any]) -> bool:
    return bool(_strict_schema_rejection_scope(exc, payload))


def _strict_schema_capability_keys(payload: dict[str, Any], context: dict[str, Any]) -> tuple[str, str]:
    model = str(payload.get(wire.LLM_MODEL_OVERRIDE_KEY) or "").strip() or resolve_llm_model(context)
    base = profiles._llm_context_key({**context, "model": model, "api_mode": "chat_completions"})
    schema_bytes = json.dumps(payload.get("response_format"), ensure_ascii=False,
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base, base + "|schema=" + hashlib.sha256(schema_bytes).hexdigest()


@_bounded_llm_call
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
        _attempt_reason("schema_capability_cached")
    try:
        return _llm_chat_json_exact_context(
            prepared, timeout, context, schema_downgraded=schema_downgraded
        )
    except urlerror.HTTPError as error:
        if schema_downgraded or not _strict_schema_rejected(error, prepared):
            raise
        diagnosis = getattr(error, "_infini_shape_diagnosis", None)
        scope = _strict_schema_rejection_scope(error, prepared)
        # The preceding diagnosis event already carries the full explanation, so
        # this one stays a short "what changed" line: three paragraphs of identical
        # prose in the server window would bury the fact that the craft recovered.
        log_event("warn", "LLM strict json_schema rejected; retrying same stage with json_object for this run", {
            "stage": _llm_replay_stage_from_payload(payload),
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
        _attempt_reason("json_schema_to_json_object_fallback")
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
            "stage": _llm_replay_stage_from_payload(payload), "profileId": context.get("profile_id"),
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
        body = _public_provider_body(_read_llm_http_error(error, timeout), context)
        provider = profiles.active_llm_provider(context)
        if provider == "openrouter" and error.code == 401:
            message = "OpenRouter auth failed: API key is missing/invalid or was not saved in config.env (401 Unauthorized)."
            log_event("warn", "OpenRouter auth failed", {"provider": provider, "openrouterProvider": profiles._openrouter_provider(context), "status": error.code, "body": body, "hint": message, "label": context.get("label")})
            raise RuntimeError(message) from error
        log_event("warn", "LLM HTTP error", {"provider": provider, "openrouterProvider": profiles._openrouter_provider(context), "status": error.code, "body": body, "label": context.get("label")})
        diagnosis = request_shape_rejection_diagnosis(error, candidate, context)
        if diagnosis is not None:
            setattr(error, "_infini_shape_diagnosis", diagnosis)
            log_event("warn", "LLM provider rejected the configured request shape", {
                **diagnosis,
                "label": context.get("label"),
            })
        raise

def _is_profile_failover_failure(error: Exception) -> bool:
    return (
        _is_budget_or_auth_failure(error)
        or _is_transport_error(error)
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


@_bounded_llm_call
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
    _attempt_reason(retry_cause)
    retry_result = _llm_json_single_context(retry_payload, timeout, context)
    return _with_transport_retry_debug(retry_result, [retry_cause], prior_result=result)


def _payload_without_model_override(payload: dict[str, Any]) -> dict[str, Any]:
    if wire.LLM_MODEL_OVERRIDE_KEY not in payload:
        return payload
    out = copy.deepcopy(payload)
    out.pop(wire.LLM_MODEL_OVERRIDE_KEY, None)
    return out


def _transport_footprint(payload: dict[str, Any], mode: str) -> dict[str, Any]:
    def content_chars(role: str) -> int:
        total = 0
        for message in payload.get("messages") or []:
            if not isinstance(message, dict) or str(message.get("role") or "") != role:
                continue
            content = message.get("content")
            total += len(content) if isinstance(content, str) else len(
                json.dumps(content, ensure_ascii=False, default=str)
            )
        return total

    def token_estimate(char_count: int) -> int:
        return max(0, (int(char_count) + 3) // 4)

    system_chars = content_chars("system")
    authored_user_chars = content_chars("user")
    is_repair = "repair" in mode or "retry" in mode
    schema = payload.get("response_format")
    schema_chars = len(json.dumps(schema, ensure_ascii=False, default=str)) if schema is not None else 0
    user_chars = 0 if is_repair else authored_user_chars
    repair_chars = authored_user_chars if is_repair else 0
    total_chars = len(json.dumps(wire._clean_llm_payload(payload), ensure_ascii=False, default=str))
    response_mode = str(schema.get("type") or "text") if isinstance(schema, dict) else "text"
    return {
        "mode": mode,
        "responseMode": response_mode,
        "provider": "",
        "profile": "",
        "systemChars": system_chars,
        "systemTokensEstimate": token_estimate(system_chars),
        "userChars": user_chars,
        "userTokensEstimate": token_estimate(user_chars),
        "schemaChars": schema_chars,
        "schemaTokensEstimate": token_estimate(schema_chars),
        "repairChars": repair_chars,
        "repairTokensEstimate": token_estimate(repair_chars),
        "totalChars": total_chars,
        "totalTokensEstimate": admission._estimated_wire_tokens(
            json.dumps(wire._clean_llm_payload(payload), ensure_ascii=False, default=str).encode("utf-8")
        ),
    }


def transport_footprint(payload: dict[str, Any], mode: str) -> dict[str, Any]:
    """Return internal request-size telemetry without mutating or sending the payload."""
    return _transport_footprint(payload, mode)


def _with_transport_footprint(result: dict[str, Any], payload: dict[str, Any], mode: str) -> dict[str, Any]:
    out = dict(result)
    raw_debug = out.get("_debug")
    debug = dict(raw_debug) if isinstance(raw_debug, dict) else {}
    footprint = _transport_footprint(payload, mode)
    footprint["provider"] = str(debug.get("provider") or profiles.active_llm_provider())
    footprint["profile"] = str(debug.get("profileId") or "")
    debug["transportFootprint"] = footprint
    out["_debug"] = debug
    return out


@_bounded_llm_call
def llm_chat_json(payload: dict[str, Any], timeout: float = 10) -> dict[str, Any]:
    mode = _record_llm_stage(payload)

    def finish(result: dict[str, Any], used_payload: dict[str, Any]) -> dict[str, Any]:
        return _with_transport_footprint(result, used_payload, mode)

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
                remaining_seconds(_request_deadline(timeout))
                if not _is_profile_failover_failure(profile_error):
                    raise
                profiles._mark_profile_failed(context, profile_error)
                if int(config.LLM_FALLBACK_NETWORK_FAILS or 2) <= 1:
                    raise
                next_context = profiles._next_lease_profile(lease, attempted)
                if next_context is None:
                    raise
                retry_causes.append("profile_failover")
                _attempt_reason("profile_failover")
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
        remaining_seconds(_request_deadline(timeout))
        if not fallback:
            if not _is_transport_error(first_error):
                raise
            last_error = first_error
            retry_causes: list[str] = []
            total_attempts = max(1, int(config.LLM_FALLBACK_NETWORK_FAILS or 2))
            for attempt in range(2, total_attempts + 1):
                retry_causes.append("transient_http")
                _attempt_reason("transient_http")
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
                    if not _is_transport_error(retry_error):
                        raise
            raise last_error

        if _is_budget_or_auth_failure(first_error):
            log_event("warn", "LLM primary failed; switching to fallback", {"reason": "budget_or_auth", "primaryProvider": profiles.active_llm_provider(primary), "primaryModel": primary.get("model"), "fallbackProvider": profiles.active_llm_provider(fallback), "fallbackModel": fallback.get("model")})
            _attempt_reason("legacy_fallback")
            profiles._switch_lease_to_legacy_fallback(lease, fallback)
            fallback_payload = _payload_without_model_override(payload)
            result = _llm_json_single_context_with_length_retry(fallback_payload, timeout, fallback)
            return finish(_with_transport_retry_debug(result, ["budget_or_auth_fallback"]), fallback_payload)

        if _is_transport_error(first_error):
            last_error = first_error
            retry_causes = []
            total_attempts = max(1, int(config.LLM_FALLBACK_NETWORK_FAILS or 2))
            for attempt in range(2, total_attempts + 1):
                retry_causes.append("primary_transport")
                _attempt_reason("primary_transport")
                try:
                    log_event("warn", "retrying primary LLM transport before fallback", {"attempt": attempt, "maxAttempts": total_attempts, "provider": profiles.active_llm_provider(primary), "model": primary.get("model")})
                    result = _llm_json_single_context_with_length_retry(primary_payload, timeout, primary)
                    return finish(_with_transport_retry_debug(result, retry_causes), primary_payload)
                except Exception as retry_error:
                    last_error = retry_error
                    if _is_budget_or_auth_failure(retry_error):
                        log_event("warn", "LLM primary changed from transport failure to budget/auth failure; switching to fallback", {"provider": profiles.active_llm_provider(primary), "fallbackProvider": profiles.active_llm_provider(fallback), "fallbackModel": fallback.get("model")})
                        _attempt_reason("legacy_fallback")
                        profiles._switch_lease_to_legacy_fallback(lease, fallback)
                        fallback_payload = _payload_without_model_override(payload)
                        result = _llm_json_single_context_with_length_retry(fallback_payload, timeout, fallback)
                        retry_causes.append("budget_or_auth_fallback")
                        return finish(_with_transport_retry_debug(result, retry_causes), fallback_payload)
                    if not _is_transport_error(retry_error):
                        raise
            log_event("warn", "LLM primary transport failed repeatedly; switching to fallback", {"attempts": total_attempts, "primaryProvider": profiles.active_llm_provider(primary), "primaryModel": primary.get("model"), "fallbackProvider": profiles.active_llm_provider(fallback), "fallbackModel": fallback.get("model")})
            _attempt_reason("legacy_fallback")
            profiles._switch_lease_to_legacy_fallback(lease, fallback)
            fallback_payload = _payload_without_model_override(payload)
            result = _llm_json_single_context_with_length_retry(fallback_payload, timeout, fallback)
            retry_causes.append("primary_transport_fallback")
            return finish(_with_transport_retry_debug(result, retry_causes), fallback_payload)
        raise
