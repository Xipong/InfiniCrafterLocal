from __future__ import annotations

import atexit
import copy
import json
import queue
import threading
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


def _json_slim(obj: Any, max_chars: int = 40000) -> Any:
    return trace_tools.json_slim(obj, max_chars)


def log_event(level: str, message: str, payload: Any = None) -> None:
    if not TRACE_PROMPTS_ENABLED:
        if str(level).lower() != "error":
            return
        message, payload = trace_tools._redact_diagnostic(str(message))[:500], None
    trace_tools.log_event(CACHE_DIR, level, message, payload, echo_levels=CONSOLE_EVENT_LEVELS)


def _trace_clip(value: Any, max_chars: int | None = None) -> str:
    return trace_tools.trace_clip(value, default_max_chars=TRACE_MAX_PROMPT_CHARS, max_chars=max_chars)


def _trace_message_summary(messages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return trace_tools.trace_message_summary(messages)


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
_CODEX_TRACE_WORKER: threading.Thread | None = None


def _write_codex_transport(payload, raw, secrets, cache_dir, trace_file, prompt_trace_file, max_chars, body_reader):
    try:
        if body_reader is not None:
            raw, payload["bodyComplete"], payload["bodyReadErrorType"], partial = body_reader()
            if partial:
                exception_payload = {**payload, "event": "reader_exception_partial",
                                     "byteScope": "reader_exception_partial_unclassified"}
                _write_codex_transport(exception_payload, partial, secrets, cache_dir, trace_file, prompt_trace_file, max_chars, None)
        from infini_local.services.codex_auth import redact_credentials
        safe = json.loads(redact_credentials(json.dumps(payload, ensure_ascii=False), secrets))
        if raw is not None:
            safe["artifact"] = trace_tools.persist_transport_artifact(cache_dir, raw, secrets=secrets)
        trace_tools.trace_event(cache_dir=cache_dir, trace_prompts_enabled=True,
            trace_max_prompt_chars=max_chars, trace_file=trace_file, prompt_trace_file=prompt_trace_file,
            kind="codex_transport", stage="transport", title="Codex generation HTTP observation", payload=safe)
    except Exception:
        pass


def _codex_trace_worker() -> None:
    while True:
        item = _CODEX_TRACE_QUEUE.get()
        if isinstance(item, threading.Event):
            item.set()
        else:
            _write_codex_transport(*item)


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
        _CODEX_TRACE_QUEUE.put((copy.deepcopy(payload), raw, secrets, CACHE_DIR, TRACE_FILE, PROMPT_TRACE_FILE, TRACE_MAX_PROMPT_CHARS, body_reader))
        return True
    except Exception:
        return False


def flush_codex_transport(timeout: float = 2) -> bool:
    """Explicit bounded drain for diagnostic readback; generation never waits here."""
    if _CODEX_TRACE_WORKER is None:
        return True
    done = threading.Event()
    _CODEX_TRACE_QUEUE.put(done)
    return done.wait(timeout)


def _tail_text_file(path: str | Path, max_chars: int = 16000) -> str:
    return trace_tools.tail_text_file(path, max_chars)


def _tail_ndjson(path: str | Path, limit: int = 80) -> list[dict[str, Any]]:
    return trace_tools.tail_ndjson(path, limit)


__all__ = [
    "TRACE_PROMPTS_ENABLED",
    "TRACE_MAX_PROMPT_CHARS",
    "TRACE_EVENTS_TAIL",
    "TRACE_FILE",
    "PROMPT_TRACE_FILE",
    "initialize_trace_storage",
    "_json_slim",
    "log_event",
    "_trace_clip",
    "_trace_message_summary",
    "trace_event",
    "trace_stage_request",
    "_tail_text_file",
    "_tail_ndjson",
]
