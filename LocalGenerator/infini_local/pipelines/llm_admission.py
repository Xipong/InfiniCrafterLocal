"""Process-wide remote request admission and observed provider quotas.

The executor passes the current attempt's diagnostics explicitly. Admission does
not own HTTP requests, logical deadlines, retry decisions or LLM item leases.
"""
from __future__ import annotations

from email.utils import parsedate_to_datetime
import math
import re
import threading
import time
from typing import Any
from urllib import error as urlerror
from urllib.parse import urlsplit

from infini_local.core.http_io import HttpDeadlineExceeded, remaining_seconds
from infini_local.services.combine_endpoint import update_generation_activity

# Unknown routes retain the conservative wire estimate as local policy, not a
# provider quota. Verified Nous OpenAI routes use pacing and provider feedback.
# Native Codex owns its separate SSE transport; see LLM_PROVIDER_ADMISSION_RU.md.


_LLM_RATE_LOCK = threading.Lock()


_LLM_RATE_STATE: dict[str, dict[str, Any]] = {}


_LLM_RATE_WINDOW_SECONDS = 60.0


_LLM_RATE_TOKENS_PER_WINDOW = 16_000


_LLM_RATE_GENERIC_MIN_INTERVAL_SECONDS = 5.1


def _quota_reset_seconds(value: Any) -> float | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    value = value.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        seconds = float(value)
    elif re.fullmatch(r"(?:\d+(?:\.\d+)?(?:ms|s|m|h|d))+", value):
        units = {"ms": .001, "s": 1, "m": 60, "h": 3600, "d": 86400}
        seconds = sum(float(count) * units[unit] for count, unit in re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h|d)", value))
    else:
        return None
    return seconds if math.isfinite(seconds) and 0 <= seconds <= 31_536_000 else None


def _selected_quota_headers(headers: Any) -> dict[str, int | float]:
    # Never retain raw headers, account IDs, cookies or unvalidated strings.
    safe: dict[str, int | float] = {}
    if headers is None:
        return safe
    for resource in ("requests", "tokens", "project-tokens"):
        for field_name in ("limit", "remaining", "reset"):
            name = f"x-ratelimit-{field_name}-{resource}"
            values = headers.get_all(name, []) if hasattr(headers, "get_all") else [
                value for key, value in headers.items() if key.lower() == name]
            if len(values) != 1 or not isinstance(values[0], str):
                continue
            value = values[0].strip()
            if field_name == "reset":
                parsed = _quota_reset_seconds(value)
            else:
                parsed = int(value) if len(value) <= 12 and re.fullmatch(r"\d+", value) else None
            if parsed is not None:
                safe[name] = parsed
    values = headers.get_all("retry-after", []) if hasattr(headers, "get_all") else [
        value for key, value in headers.items() if key.lower() == "retry-after"]
    if len(values) == 1:
        seconds = _quota_reset_seconds(values[0])
        if seconds is None and isinstance(values[0], str) and len(values[0]) <= 64:
            try:
                date = parsedate_to_datetime(values[0])
                seconds = max(0.0, date.timestamp() - time.time()) if date.tzinfo is not None else None
            except (ValueError, TypeError, OverflowError):
                seconds = None
            if seconds is not None and (not math.isfinite(seconds) or seconds > 31_536_000):
                seconds = None
        if seconds is not None:
            safe["retry-after"] = seconds
    return safe


def _observe_remote_quota_headers(
    url: str, payload: dict[str, Any], headers: Any,
    *, attempt: dict[str, Any] | None = None,
) -> dict[str, int | float]:
    safe = _selected_quota_headers(headers)
    row = attempt
    if row is not None:
        row["rateLimitHeaders"] = safe
    key = _remote_rate_key(url, payload)
    if key:
        # Only explicit exhaustion establishes a block. Positive remaining tokens
        # are not a tokenizer, a cache discount or permission to lift local policy.
        resets = [safe[f"x-ratelimit-reset-{resource}"] for resource in ("requests", "tokens", "project-tokens")
                  if safe.get(f"x-ratelimit-remaining-{resource}") == 0 and f"x-ratelimit-reset-{resource}" in safe]
        if resets:
            with _LLM_RATE_LOCK:
                state = _LLM_RATE_STATE.setdefault(key, {"events": [], "lastRequest": -1.0e30, "blockedUntil": 0.0})
                state["quotaUntil"] = max(float(state.get("quotaUntil") or 0.0), time.monotonic() + max(resets))
    return safe


def _remote_admission_policy(url: str, payload: dict[str, Any]) -> str:
    parsed = urlsplit(url)
    try:
        canonical = (parsed.scheme == "https" and parsed.port is None
                     and parsed.username is None and parsed.password is None
                     and not parsed.query and not parsed.fragment)
    except ValueError:
        canonical = False
    if (canonical and parsed.hostname == "inference-api.nousresearch.com"
            and parsed.path in {"/v1/chat/completions", "/v1/responses"}
            and isinstance(payload.get("model"), str) and payload["model"].startswith("openai/")):
        return "nous_openai_feedback"
    return "unknown_conservative"


def _remote_rate_key(url: str, payload: dict[str, Any]) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").strip().lower()
    if host in {"", "localhost", "127.0.0.1", "::1"}:
        return ""
    model = str(payload.get("model") or "unknown").strip().lower()
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}|{model}"


def _model_min_interval_seconds(model: Any) -> float:
    normalized = str(model or "").strip().lower()
    if "gemma" in normalized:
        return 62.0
    if "gemini" in normalized:
        return 12.0
    return _LLM_RATE_GENERIC_MIN_INTERVAL_SECONDS


def _estimated_wire_tokens(serialized_bytes: bytes) -> int:
    # Conservative provider-independent estimate; exact tokenizers are not shared
    # across the configured pool.  One request may consume the whole window but can
    # never deadlock merely because its schema is large.
    return min(
        _LLM_RATE_TOKENS_PER_WINDOW,
        max(1, int(math.ceil(len(serialized_bytes.decode("utf-8", "replace")) / 4.0))),
    )


def _reserve_remote_rate_slot(
    url: str,
    payload: dict[str, Any],
    serialized_bytes: bytes,
    *,
    max_wait_seconds: float | None = None,
    attempt: dict[str, Any] | None = None,
) -> None:
    key = _remote_rate_key(url, payload)
    policy = _remote_admission_policy(url, payload) if key else "local_exempt"
    row = attempt
    if row is not None:
        row["rateAdmissionPolicy"] = policy
    if not key:
        return
    uses_token_window = policy == "unknown_conservative"
    tokens = _estimated_wire_tokens(serialized_bytes) if uses_token_window else 0
    minimum_interval = (_model_min_interval_seconds(payload.get("model")) if uses_token_window
                        else _LLM_RATE_GENERIC_MIN_INTERVAL_SECONDS)
    deadline = None if max_wait_seconds is None else time.monotonic() + max(0.0, max_wait_seconds)
    waiter = threading.Event()
    with _LLM_RATE_LOCK:
        state = _LLM_RATE_STATE.setdefault(
            key,
            {"events": [], "lastRequest": -1.0e30, "blockedUntil": 0.0},
        )
        waiters = state.setdefault("waiters", [])
        waiters.append(waiter)
    try:
        while True:
            if deadline is not None:
                remaining_seconds(deadline)
            wait_seconds = 0.0
            queue_timeout = None
            with _LLM_RATE_LOCK:
                now = time.monotonic()
                if deadline is not None:
                    remaining_seconds(deadline)
                is_head = waiters[0] is waiter
                row = attempt
                if not is_head:
                    # Only the oldest request may spend this key's quota. Smaller
                    # newcomers must not keep renewing the window ahead of it.
                    queue_timeout = None if deadline is None else deadline - now
                    if row is not None:
                        row["rateWaitReason"] = "rate_queue"
                    update_generation_activity(wait_reason="rate_queue", network_started=False)
                else:
                    events = [
                        (float(at), int(count))
                        for at, count in state.get("events", [])
                        if float(at) > now - _LLM_RATE_WINDOW_SECONDS
                    ]
                    state["events"] = events
                    blocked_wait = max(0.0, float(state.get("blockedUntil") or 0.0) - now)
                    quota_wait = max(0.0, float(state.get("quotaUntil") or 0.0) - now)
                    pacing_wait = max(
                        0.0,
                        float(state.get("lastRequest", -1.0e30)) + minimum_interval - now,
                    )
                    wait_seconds = max(blocked_wait, quota_wait, pacing_wait)
                    used_tokens = sum(count for _, count in events)
                    token_wait = uses_token_window and events and used_tokens + tokens > _LLM_RATE_TOKENS_PER_WINDOW
                    if token_wait:
                        wait_seconds = max(
                            wait_seconds,
                            events[0][0] + _LLM_RATE_WINDOW_SECONDS - now,
                        )
                    if row is not None and wait_seconds > 0.0:
                        row["rateWaitReason"] = (
                            "provider_cooldown" if blocked_wait >= wait_seconds else
                            "provider_quota" if quota_wait >= wait_seconds else
                            "token_window" if token_wait else "pacing")
                    if wait_seconds > 0.0:
                        update_generation_activity(wait_reason=(
                            "provider_cooldown" if blocked_wait >= wait_seconds else
                            "provider_quota" if quota_wait >= wait_seconds else
                            "token_window" if token_wait else "pacing"), network_started=False)
                    if wait_seconds <= 0.0:
                        update_generation_activity(wait_reason="none", network_started=False)
                        if uses_token_window:
                            events.append((now, tokens))
                        state["lastRequest"] = now
                        return
            if not is_head:
                waiter.wait(queue_timeout)
                continue
            # Own pacing and provider cooldown both consume the logical budget;
            # neither may reserve/send after it is spent. No event means no send.
            if deadline is not None and now + wait_seconds > deadline:
                time.sleep(max(0.0, deadline - time.monotonic()))
                raise HttpDeadlineExceeded("remote LLM rate wait exhausted the deadline; request not sent")
            time.sleep(wait_seconds)
    finally:
        with _LLM_RATE_LOCK:
            was_head = waiters[0] is waiter
            waiters.remove(waiter)
            if was_head and waiters:
                waiters[0].set()


def _mark_remote_rate_limited(url: str, payload: dict[str, Any], error: urlerror.HTTPError) -> None:
    key = _remote_rate_key(url, payload)
    if not key:
        return
    retry_after = _selected_quota_headers(error.headers).get("retry-after", 0.0)
    cooldown = max(60.0, retry_after, _model_min_interval_seconds(payload.get("model")))
    with _LLM_RATE_LOCK:
        state = _LLM_RATE_STATE.setdefault(
            key,
            {"events": [], "lastRequest": -1.0e30, "blockedUntil": 0.0},
        )
        state["blockedUntil"] = max(
            float(state.get("blockedUntil") or 0.0),
            time.monotonic() + cooldown,
        )
