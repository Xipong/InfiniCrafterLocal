from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable


ParentName = Callable[[dict[str, Any]], str]
JsonSlim = Callable[[Any, int], Any]
LogEvent = Callable[[str, str, Any], None]

SUMMARY_KEYS = ["ok", "version", "time", "stage", "error", "parents", "worldId", "pipelineLog"]

# Finite client-owned vocabulary: unknown provider text must never echo into diagnostics.
PROVIDER_ERROR_CODES = frozenset({
    "model_not_found", "model_unavailable", "invalid_model", "invalid_api_key",
    "authentication_error", "permission_denied", "insufficient_quota",
    "quota_exceeded", "rate_limit_exceeded", "not_found", "invalid_request_error",
    "unsupported_parameter", "invalid_json_schema", "context_length_exceeded",
})
PROVIDER_ERROR_PARAMS = frozenset({
    "model", "response_format", "response_format.json_schema", "messages",
    "max_tokens", "max_output_tokens", "reasoning", "temperature",
})
TRANSPORT_FAILURE_CATEGORIES = frozenset({
    "model_unavailable", "auth_failed", "quota_exhausted", "rate_limited",
    "endpoint_unavailable", "request_rejected", "admission_timeout", "logical_timeout",
    "transport_unavailable", "provider_failure", "profile_unavailable",
})
_TRANSPORT_VOCABULARIES = {
    "category": TRANSPORT_FAILURE_CATEGORIES,
    "provider_code": PROVIDER_ERROR_CODES,
    "provider_param": PROVIDER_ERROR_PARAMS,
}

# Client-owned transport metadata only; never body, headers, messages or provider extras.
_TRANSPORT_COMMON_FIELDS = {
    **dict.fromkeys(("logicalCallId", "stage", "leaseId", "requestedApiMode", "requestedResponseFormat",
                     "effectiveApiMode", "effectiveResponseFormat", "rateWaitReason"), "text"),
    "requestedReasoning": "reasoning", "effectiveReasoning": "reasoning",
}
_TRANSPORT_SUMMARY_FIELDS = {
    **_TRANSPORT_COMMON_FIELDS, "physicalAttemptScope": "text", "physicalAttempts": "attempts",
    "failureCategory": "category", "httpStatus": "number", "networkStarted": "bool",
    "providerErrorCode": "provider_code", "providerErrorParam": "provider_param",
    **dict.fromkeys(("physicalAttemptCount", "physicalAttemptsDropped", "rateWaitMsTotal"), "number"),
}
_TRANSPORT_ATTEMPT_FIELDS = {
    **_TRANSPORT_COMMON_FIELDS,
    **dict.fromkeys(("profileId", "provider", "openrouterProvider", "reason", "errorType"), "text"),
    **dict.fromkeys(("httpStatus", "physicalAttemptIndex", "rateWaitMs", "connectMs", "openMs", "readMs",
                     "deadlineRemainingMs"), "number"),
    "networkStarted": "bool", "unsupportedReasoningFields": "reasoning_fields",
    "providerErrorCode": "provider_code", "providerErrorParam": "provider_param",
}
_REASONING_FIELDS = {"effort": "text", "max_tokens": "tokens", "enabled": "bool", "exclude": "bool"}


def _project_transport_fields(value: Any, fields: dict[str, str]) -> dict[str, Any]:
    """Bounded, detached lossy projection; unknown/wrong-type/nonfinite values are omitted."""
    if type(value) is not dict:
        return {}
    out: dict[str, Any] = {}
    for name, kind in fields.items():
        if name not in value:
            continue
        item = value[name]
        if item is None:
            out[name] = None
        elif kind in {"category", "provider_code", "provider_param"} and type(item) is str:
            # Revalidate even persisted/operator-supplied supplements.
            if item in _TRANSPORT_VOCABULARIES[kind]:
                out[name] = item
        elif kind == "text" and type(item) is str:
            out[name] = item[:160]
        elif kind in {"number", "tokens"} and type(item) in {int, float}:
            ceiling = 64000 if kind == "tokens" else 10**12
            if 0 <= item <= ceiling and (kind != "tokens" or type(item) is int):
                out[name] = item
        elif kind == "bool" and type(item) is bool:
            out[name] = item
        elif kind == "reasoning" and type(item) is dict:
            out[name] = _project_transport_fields(item, _REASONING_FIELDS)
        elif kind == "attempts" and type(item) is list:
            out[name] = [_project_transport_fields(row, _TRANSPORT_ATTEMPT_FIELDS) for row in item[:16] if type(row) is dict]
        elif kind == "reasoning_fields" and type(item) is list:
            out[name] = list(dict.fromkeys(field for field in item[:4] if type(field) is str and field in _REASONING_FIELDS))
    return out


def _resume_status(value: Any) -> dict[str, Any]:
    if (isinstance(value, dict) and value.get("available") is True
            and isinstance(value.get("stage"), str) and value["stage"] in {"gameplay", "visual", "vfx"}):
        return {"available": True, "stage": value["stage"]}
    return {}


def summarize_failure(failure: dict[str, Any]) -> dict[str, Any]:
    if not failure:
        return {}
    summary = {k: failure.get(k) for k in SUMMARY_KEYS}
    supplement = _project_transport_fields(failure.get("transportDebug"), _TRANSPORT_SUMMARY_FIELDS)
    if supplement:
        summary["transportDebug"] = supplement
    resume = _resume_status(failure.get("generationResume"))
    if resume:
        summary["generationResume"] = resume
    return summary


def _transport_debug(error: BaseException | str) -> dict[str, Any]:
    """Take the nearest usable explicit-cause supplement, visiting at most 16 errors."""
    current: Any = error
    seen: set[int] = set()
    for _ in range(16):
        if not isinstance(current, BaseException) or id(current) in seen:
            break
        seen.add(id(current))
        try:
            supplement = _project_transport_fields(getattr(current, "_infini_transport_debug", None), _TRANSPORT_SUMMARY_FIELDS)
        except Exception:
            supplement = {}
        if supplement:
            return supplement
        try:
            current = getattr(current, "__cause__", None)
        except Exception:
            break
    return {}


def build_combine_failure(
    *,
    app_version: str,
    stage: str,
    error: BaseException | str,
    payload: dict[str, Any] | None,
    partial_data: Any,
    pipeline_log: list[dict[str, Any]] | None,
    parent_name: ParentName,
    json_slim: JsonSlim,
) -> dict[str, Any]:
    """Build the diagnostic payload for the last failed /combine attempt.

    This module owns debug-state shaping only. It does not decide craft success,
    mutate gameplay output, or touch the runtime authoring contract.
    """
    source_payload = payload if isinstance(payload, dict) else {}
    failure = {
        "ok": False,
        "version": app_version,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stage": str(stage or "unknown"),
        "error": str(error),
        "repr": repr(error),
        "pipelineLog": list(pipeline_log or []),
        "parents": {
            "a": parent_name(source_payload.get("itemA") or {}),
            "b": parent_name(source_payload.get("itemB") or {}),
        },
        "worldId": str(source_payload.get("worldId") or ""),
        "partialData": json_slim(partial_data, 60000) if isinstance(partial_data, dict) else {},
    }
    supplement = _transport_debug(error)
    if supplement:
        failure["transportDebug"] = supplement
    debug = partial_data.get("debug") if isinstance(partial_data, dict) else None
    resume = debug.get("generationResume") if isinstance(debug, dict) else None
    if projected := _resume_status(resume):
        failure["generationResume"] = projected
    return failure


def persist_failure(cache_dir: Path, failure_file: Path, failure: dict[str, Any], log_event: LogEvent) -> None:
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        failure_file.write_text(json.dumps(failure, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except Exception as write_error:
        log_event("warn", "could not write last_combine_failure.json", {"error": repr(write_error)})


def clear_persisted_failure(failure_file: Path, log_event: LogEvent, reason: str = "success") -> None:
    try:
        if failure_file.exists():
            failure_file.unlink()
    except Exception as e:
        log_event("debug", "could not clear last_combine_failure.json", {"reason": reason, "error": repr(e)})


def read_failure_summary(failure: dict[str, Any], failure_file: Path) -> dict[str, Any]:
    if failure:
        return summarize_failure(failure)
    try:
        if failure_file.exists():
            obj = json.loads(failure_file.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                return summarize_failure(obj)
    except Exception:
        pass
    return {}
