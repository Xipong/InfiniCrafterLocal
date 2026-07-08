from __future__ import annotations

from pathlib import Path
from typing import Any

from infini_local.core.config_bootstrap import CACHE_DIR
from infini_local.core.env_utils import env_bool, env_int
from infini_local.storage import trace_tools


# AGENT MAP: rolling debug/trace runtime wiring shared by pipeline support and
# the HTTP server. This is evidence/debug infrastructure only; no gameplay
# authoring or repair logic belongs here.


# Rolling black box recorder for GUI/debug: prompts, LLM responses, image prompts,
# sd.cpp startup/image attempts and pipeline steps. This is debug state, not gameplay state.
TRACE_PROMPTS_ENABLED = env_bool("INFINI_TRACE_PROMPTS", True)
TRACE_MAX_PROMPT_CHARS = max(1000, min(120000, env_int("INFINI_TRACE_MAX_PROMPT_CHARS", 18000)))
TRACE_EVENTS_TAIL = max(20, min(500, env_int("INFINI_TRACE_EVENTS_TAIL", 120)))
TRACE_FILE = CACHE_DIR / "pipeline_trace.ndjson"
PROMPT_TRACE_FILE = CACHE_DIR / "prompt_trace.ndjson"


def _json_slim(obj: Any, max_chars: int = 40000) -> Any:
    return trace_tools.json_slim(obj, max_chars)


def log_event(level: str, message: str, payload: Any = None) -> None:
    trace_tools.log_event(CACHE_DIR, level, message, payload)


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
    "_json_slim",
    "log_event",
    "_trace_clip",
    "_trace_message_summary",
    "trace_event",
    "_tail_text_file",
    "_tail_ndjson",
]
