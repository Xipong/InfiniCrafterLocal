"""Evidence-based provider failure and request-shape classification."""
from __future__ import annotations

import json
import re
from typing import Any
from urllib import error as urlerror

from infini_local.core import llm_config as config
from infini_local.core.http_io import HttpDeadlineExceeded
from infini_local.pipelines.transport import profiles
from infini_local.storage.failure_state import PROVIDER_ERROR_CODES, PROVIDER_ERROR_PARAMS


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
