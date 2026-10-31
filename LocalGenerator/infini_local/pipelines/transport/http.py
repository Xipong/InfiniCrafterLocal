"""HTTP JSON I/O with one logical deadline and admission accounting."""
from __future__ import annotations

import json
import time
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from infini_local.core.http_io import HttpDeadlineExceeded, HttpResponseTooLarge, read_with_deadline, remaining_seconds, urlopen_no_redirect
from infini_local.pipelines.transport import admission, diagnostics
from infini_local.services.combine_endpoint import update_generation_activity

MAX_PROVIDER_JSON_BYTES = 16 * 1024 * 1024



def http_get_json(url: str, timeout: float = 5, headers: dict[str, str] | None = None) -> dict[str, Any]:
    merged = {"Accept": "application/json"}
    if headers:
        merged.update(headers)
    req = urlrequest.Request(url, headers=merged, method="GET")
    deadline = diagnostics._request_deadline(timeout)
    try:
        with urlopen_no_redirect(req, deadline=deadline) as resp:
            return json.loads(read_with_deadline(resp, deadline=deadline, max_bytes=MAX_PROVIDER_JSON_BYTES).decode("utf-8"))
    except urlerror.HTTPError as error:
        error.close()
        raise



def http_json(url: str, payload: dict[str, Any], timeout: float = 10, headers: dict[str, str] | None = None, *, max_response_bytes: int | None = MAX_PROVIDER_JSON_BYTES) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    deadline = diagnostics._request_deadline(timeout)
    row = diagnostics._CURRENT_LLM_ATTEMPT.get()
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
    deadline = min(diagnostics._request_deadline(timeout), getattr(error, "_infini_deadline", float("inf")))
    row = diagnostics._CURRENT_LLM_ATTEMPT.get()
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
