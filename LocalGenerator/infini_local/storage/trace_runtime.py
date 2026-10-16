from __future__ import annotations

import atexit
import copy
import json
import os
import queue
from dataclasses import dataclass, replace
import threading
import time
from pathlib import Path
from typing import Any

from infini_local.core.config_bootstrap import CACHE_DIR
from infini_local.core.env_utils import env_bool, env_int, env_str
from infini_local.storage import trace_tools


# AGENT MAP: full optional debug/trace runtime wiring shared by pipeline support and
# the HTTP server. This is evidence/debug infrastructure only; no gameplay
# authoring or repair logic belongs here.


# Append-only black box recorder for GUI/debug: prompts, LLM responses, image prompts,
# sd.cpp startup/image attempts and pipeline steps. This is debug state, not gameplay state.
TRACE_PROMPTS_ENABLED = env_bool("INFINI_TRACE_PROMPTS", True)
TRACE_MAX_PROMPT_CHARS = max(0, env_int("INFINI_TRACE_MAX_PROMPT_CHARS", 0))
TRACE_EVENTS_TAIL = max(20, min(500, env_int("INFINI_TRACE_EVENTS_TAIL", 120)))
TRACE_FILE = CACHE_DIR / "pipeline_trace.ndjson"
PROMPT_TRACE_FILE = CACHE_DIR / "prompt_trace.ndjson"

# events.ndjson stays the complete record.  These levels are additionally mirrored
# to the server console so a failing craft is visible while it happens: the window
# used to show only the startup banner, which made silent failures look like the
# generator doing nothing.  "off" restores the previous file-only behaviour.
_ECHO_LEVEL_ORDER = ("debug", "info", "warn", "error")


def _configured_echo_levels() -> tuple[str, ...]:
    threshold = str(env_str("INFINI_CONSOLE_EVENT_LEVEL", "warn") or "warn").strip().lower()
    # Silence is opt-in: an unset, empty or unrecognized value keeps the
    # recommended warn+error echo rather than hiding failures by accident.
    if threshold in {"off", "none", "silent"}:
        return ()
    if threshold not in _ECHO_LEVEL_ORDER:
        threshold = "warn"
    return _ECHO_LEVEL_ORDER[_ECHO_LEVEL_ORDER.index(threshold):]


CONSOLE_EVENT_LEVELS = _configured_echo_levels()


def initialize_trace_storage() -> dict[str, bool]:
    """Repair corrupt trailing records before the HTTP server starts accepting work."""
    paths = [CACHE_DIR / "events.ndjson"]
    if TRACE_PROMPTS_ENABLED:
        paths += [TRACE_FILE, PROMPT_TRACE_FILE]
    return trace_tools.initialize_trace_storage(tuple(path for path in paths if path.exists()))


def log_event(level: str, message: str, payload: Any = None) -> None:
    if not TRACE_PROMPTS_ENABLED:
        if str(level).lower() != "error":
            return
        message, payload = trace_tools._redact_diagnostic(str(message))[:500], None
    trace_tools.log_event(CACHE_DIR, level, message, payload, echo_levels=CONSOLE_EVENT_LEVELS)


def _trace_clip(value: Any, max_chars: int | None = None) -> str:
    return trace_tools.trace_clip(value, default_max_chars=TRACE_MAX_PROMPT_CHARS, max_chars=max_chars)


def trace_event(kind: str, stage: str, title: str, payload: Any = None, *, prompt: Any = None, negative: Any = None, response: Any = None, error: Any = None) -> None:
    trace_tools.trace_event(
        cache_dir=CACHE_DIR,
        trace_prompts_enabled=TRACE_PROMPTS_ENABLED,
        trace_max_prompt_chars=TRACE_MAX_PROMPT_CHARS,
        trace_file=TRACE_FILE,
        prompt_trace_file=PROMPT_TRACE_FILE,
        kind=kind,
        stage=stage,
        title=title,
        payload=payload,
        prompt=prompt,
        negative=negative,
        response=response,
        error=error,
    )


def trace_stage_request(stage: str, recipe_key: str, request: dict[str, Any], *, recipe_id: str | None = None) -> dict[str, Any]:
    """The existing trace toggle controls full-message artifacts and their joins."""
    if not TRACE_PROMPTS_ENABLED:
        return {"status": "disabled"}
    receipt = trace_tools.persist_stage_request(CACHE_DIR, stage, recipe_key, request, recipe_id=recipe_id)
    trace_event("request_artifact", stage, "Exact sanitized stage request", receipt)
    return receipt


_CODEX_TRACE_QUEUE: queue.SimpleQueue = queue.SimpleQueue()
_CODEX_TRACE_START_LOCK = threading.Lock()
_CODEX_TRACE_COMMIT_LOCK = threading.Lock()
_CODEX_TRACE_EPOCHS: dict[str, int] = {}
_CODEX_TRACE_WORKER: threading.Thread | None = None
_CODEX_TRACE_CLEAR = object()
_CODEX_TRACE_MAX_PENDING_BYTES = 8 * 1024 * 1024
_CODEX_TRACE_MAX_PENDING_EVENTS = 4096
_CODEX_TRACE_MAX_PENDING_ATTEMPTS = 64


def _trace_target(path) -> str:
    return os.path.normcase(os.path.abspath(path))


@dataclass(frozen=True)
class _CodexObservation:
    payload: dict
    raw: bytes | None
    secrets: tuple[str, ...]
    cache_dir: Path
    trace_file: Path
    prompt_trace_file: Path
    max_chars: int
    body_reader: Any
    epoch: int


def clear_trace_files(paths) -> list[str]:
    """Invalidate pending transport rows before clearing the selected NDJSON files."""
    cleared = []
    # Generation only reads epochs and enqueues; it never waits for this lock.
    with _CODEX_TRACE_COMMIT_LOCK:
        for path in paths:
            key = _trace_target(path)
            _CODEX_TRACE_EPOCHS[key] = _CODEX_TRACE_EPOCHS.get(key, 0) + 1
            try:
                trace_tools.clear_ndjson(path)
                cleared.append(str(path))
            except Exception:
                pass
    _CODEX_TRACE_QUEUE.put(_CODEX_TRACE_CLEAR)
    return cleared


def _write_codex_transport(item: _CodexObservation):
    try:
        payload, raw = item.payload, item.raw
        if item.body_reader is not None:
            raw, payload["bodyComplete"], payload["bodyReadErrorType"], partial = item.body_reader()
            if partial:
                exception_payload = {**payload, "event": "reader_exception_partial",
                                     "byteScope": "reader_exception_partial_unclassified"}
                _write_codex_transport(replace(item, payload=exception_payload, raw=partial, body_reader=None))
        from infini_local.services.codex_auth import redact_credentials
        safe = json.loads(redact_credentials(json.dumps(payload, ensure_ascii=False), item.secrets))
        if raw is not None:
            safe["artifact"] = trace_tools.persist_transport_artifact(item.cache_dir, raw, secrets=item.secrets)
        # Artifact/body I/O remains outside the commit boundary. An old write
        # finishing after Clear cannot repopulate the selected trace files.
        with _CODEX_TRACE_COMMIT_LOCK:
            if item.epoch != _CODEX_TRACE_EPOCHS.get(_trace_target(item.trace_file), 0):
                return
            safe["persistedAt"] = time.time()
            trace_tools.trace_event(cache_dir=item.cache_dir, trace_prompts_enabled=True,
                trace_max_prompt_chars=item.max_chars, trace_file=item.trace_file, prompt_trace_file=item.prompt_trace_file,
                kind="codex_transport", stage="transport", title="Codex generation HTTP observation", payload=safe)
    except Exception:
        pass


def _safe_sse_batch(items: list[_CodexObservation]) -> list[_CodexObservation]:
    """Check assembled stream text before publishing any of its raw fragments.

    Per-event redaction cannot detect a token split across deltas or final
    output parts. Keep clean bytes exact; refuse all raw events in a sensitive
    attempt rather than inventing replacement provider content.
    """
    from infini_local.services.codex_auth import redact_credentials
    from infini_local.core.env_utils import env_credential_values
    secrets = tuple({secret for item in items for secret in item.secrets}) + env_credential_values()
    streams: dict[str, list[str]] = {}
    candidates = []
    combined: list[str] = []
    uncertain = False

    def strings(value, groups):
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, str) and key in {"delta", "text", "arguments", "refusal"}:
                    groups.setdefault(key, []).append(child)
                    combined.append(child)
                else:
                    strings(child, groups)
        elif isinstance(value, list):
            for child in value:
                strings(child, groups)

    for item in items:
        try:
            raw = (item.raw or b"").decode("utf-8")
            # Late reads can include an original data: line; EOF tails do not.
            raw = "\n".join(line[5:].strip() if line.startswith("data:") else line for line in raw.splitlines())
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            # A malformed event could finish an earlier credential prefix,
            # including escaped field names. Only the protocol sentinel is safe
            # without JSON decoding; unknown fragments remain memory-only.
            if (item.raw or b"").strip() != b"[DONE]":
                uncertain = True
            continue
        groups: dict[str, list[str]] = {}
        strings(value, groups)
        candidates.extend("".join(parts) for parts in groups.values())
        for key, parts in groups.items():
            streams.setdefault(key, []).extend(parts)
    candidates.extend("".join(parts) for parts in streams.values())
    candidates.append("".join(combined))
    sensitive = uncertain or any(redact_credentials(value, secrets) != value for value in candidates)
    if not sensitive:
        return items
    reason = "stream_redaction_unverified" if uncertain else "stream_credential_redaction"
    return [replace(item, raw=None, payload={**item.payload,
        "artifact": {"status": "refused", "reason": reason}}) for item in items]


@dataclass
class _SseTraceBatch:
    first: _CodexObservation
    items: list[_CodexObservation]
    bytes: int = 0
    refused: bool = False


def _refuse_pending_sse(batch: _SseTraceBatch, reason: str) -> None:
    _write_codex_transport(replace(batch.first, raw=None, payload={**batch.first.payload,
        "event": "sse_trace_refused", "bufferedEvents": len(batch.items),
        "artifact": {"status": "refused", "reason": reason}}))
    batch.items.clear()
    batch.bytes = 0
    batch.refused = True


def _codex_trace_worker() -> None:
    pending: dict[tuple, _SseTraceBatch] = {}
    while True:
        item = _CODEX_TRACE_QUEUE.get()
        # Clear wakes this worker, including when no later generation arrives.
        # Epoch is part of the key, so new rows never join a retired batch.
        for old_key in list(pending):
            if old_key[-1] != _CODEX_TRACE_EPOCHS.get(old_key[0], 0):
                del pending[old_key]
        if item is _CODEX_TRACE_CLEAR:
            continue
        if isinstance(item, threading.Event):
            item.set()
            continue
        target = _trace_target(item.trace_file)
        key = (target, item.payload.get("transportCallId"), item.payload.get("physicalAttemptIndex"), item.epoch)
        if str(item.payload.get("event", "")).startswith("sse_") and item.raw is not None:
            if item.epoch != _CODEX_TRACE_EPOCHS.get(target, 0):
                continue
            if key not in pending:
                if len(pending) >= _CODEX_TRACE_MAX_PENDING_ATTEMPTS:
                    _refuse_pending_sse(pending.pop(next(iter(pending))), "pending_attempt_limit")
                pending[key] = _SseTraceBatch(replace(item, raw=None), [])
            batch = pending[key]
            if batch.refused:
                continue
            size = sum(part.bytes for part in pending.values()) + len(item.raw)
            count = sum(len(part.items) for part in pending.values()) + 1
            if size > _CODEX_TRACE_MAX_PENDING_BYTES or count > _CODEX_TRACE_MAX_PENDING_EVENTS:
                _refuse_pending_sse(batch, "pending_stream_limit")
                continue
            batch.items.append(item)
            batch.bytes += len(item.raw)
            continue
        if item.payload.get("event") == "attempt_end":
            batch = pending.pop(key, None)
            rows = batch.items if batch is not None else []
            try:
                safe_batch = _safe_sse_batch(rows)
            except Exception:
                # Optional evidence fails closed; no raw fragments escape when
                # assembly/redaction cannot be established.
                safe_batch = [replace(row, raw=None, payload={**row.payload,
                    "artifact": {"status": "refused", "reason": "stream_redaction_failed"}}) for row in rows]
            if rows and all(row.raw is not None for row in safe_batch):
                first = safe_batch[0]
                try:
                    receipts = trace_tools.persist_transport_batch(first.cache_dir,
                        [row.raw for row in safe_batch if row.raw is not None],
                        secrets=tuple({secret for row in safe_batch for secret in row.secrets}))
                except Exception:
                    receipts = [{"status": "refused", "reason": "stream_persistence_failed"} for _ in safe_batch]
                safe_batch = [replace(row, raw=None, payload={**row.payload, "artifact": receipt})
                              for row, receipt in zip(safe_batch, receipts)]
            for row in safe_batch:
                _write_codex_transport(row)
        elif item.payload.get("event") == "call_end":
            for old_key in list(pending):
                if old_key[:2] == key[:2]:
                    _refuse_pending_sse(pending.pop(old_key), "missing_attempt_boundary")
        _write_codex_transport(item)


def trace_codex_transport(payload: dict[str, Any], *, raw: bytes | None = None, secrets: tuple[str, ...] = (), body_reader=None) -> bool:
    """Detach observations; disk locks/fsync never occupy the generation deadline."""
    if not TRACE_PROMPTS_ENABLED:
        return False
    try:
        global _CODEX_TRACE_WORKER
        with _CODEX_TRACE_START_LOCK:
            if _CODEX_TRACE_WORKER is None:
                _CODEX_TRACE_WORKER = threading.Thread(target=_codex_trace_worker, daemon=True, name="codex-transport-trace")
                _CODEX_TRACE_WORKER.start()
                atexit.register(flush_codex_transport)
        epoch = _CODEX_TRACE_EPOCHS.get(_trace_target(TRACE_FILE), 0)
        _CODEX_TRACE_QUEUE.put(_CodexObservation(copy.deepcopy(payload), raw, secrets, CACHE_DIR, TRACE_FILE,
                                               PROMPT_TRACE_FILE, TRACE_MAX_PROMPT_CHARS, body_reader, epoch))
        return True
    except Exception:
        return False


def flush_codex_transport(timeout: float = 2) -> bool:
    """Drain queued work; open SSE attempts stay private until their boundary."""
    if _CODEX_TRACE_WORKER is None:
        return True
    done = threading.Event()
    _CODEX_TRACE_QUEUE.put(done)
    return done.wait(timeout)


__all__ = [
    "TRACE_PROMPTS_ENABLED",
    "TRACE_MAX_PROMPT_CHARS",
    "TRACE_EVENTS_TAIL",
    "TRACE_FILE",
    "PROMPT_TRACE_FILE",
    "initialize_trace_storage",
    "log_event",
    "_trace_clip",
    "trace_event",
    "trace_stage_request",
]
