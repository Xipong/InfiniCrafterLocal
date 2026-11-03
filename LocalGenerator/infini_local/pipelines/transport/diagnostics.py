"""Request-local deadlines and bounded transport observation."""
from __future__ import annotations

import copy
import json
import threading
import time
from contextvars import ContextVar
from functools import wraps
from typing import Any

from infini_local.core.http_io import remaining_seconds
from infini_local.pipelines.transport import admission, profiles, rejections, replay
from infini_local.pipelines.transport import provider_wire as wire
from infini_local.storage.trace_runtime import log_event

_CURRENT_LLM_DEADLINE: ContextVar[float | None] = ContextVar("infini_llm_deadline", default=None)



_CURRENT_LLM_DIAGNOSTICS: ContextVar[dict[str, Any] | None] = ContextVar("infini_llm_diagnostics", default=None)



_CURRENT_LLM_ATTEMPT: ContextVar[dict[str, Any] | None] = ContextVar("infini_llm_attempt", default=None)



_LLM_MAX_DIAGNOSTIC_ATTEMPTS = 16



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
                summary.update(rejections._failure_metadata(error, state["lastAttempt"]))
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
        "stage": replay._llm_replay_stage_from_payload(payload), "leaseId": lease.lease_id if lease else "",
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
