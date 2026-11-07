"""Read-only trace snapshot and HTML projection from canonical owners."""
from __future__ import annotations

import json
import os
import time
from typing import Any

from infini_local.core import config_bootstrap as config, llm_config
from infini_local.core.images import config as visual_config
from infini_local.core.vfx import config as vfx_config
from infini_local.pipelines import generation_debug
from infini_local.pipelines.images.backends import sdcpp_debug_snapshot
from infini_local.pipelines.transport.client import llm_auth_snapshot
from infini_local.pipelines.transport.profiles import active_llm_provider
from infini_local.storage import trace_runtime
from infini_local.storage.trace_tools import read_trace_tail, trace_clip
from infini_local.web.trace_dashboard import render_trace_snapshot_html


def trace_snapshot(*, full: bool = False) -> dict[str, Any]:
    failure: Any = generation_debug.last_combine_failure_summary()
    try:
        if generation_debug.LAST_COMBINE_FAILURE_FILE.exists():
            failure = json.loads(generation_debug.LAST_COMBINE_FAILURE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    provider = active_llm_provider()
    auth = llm_auth_snapshot()
    return {
        "ok": True,
        "version": config.APP_VERSION,
        "time": int(time.time()),
        "serverRoot": str(config.ROOT),
        "configPath": str(config.CONFIG_PATH),
        "pid": os.getpid(),
        "cacheDir": str(config.CACHE_DIR),
        "traceConfig": {
            "tracePrompts": trace_runtime.TRACE_PROMPTS_ENABLED,
            "maxPromptChars": trace_runtime.TRACE_MAX_PROMPT_CHARS,
            "eventsTail": trace_runtime.TRACE_EVENTS_TAIL,
            "promptTraceFile": str(trace_runtime.PROMPT_TRACE_FILE),
            "pipelineTraceFile": str(trace_runtime.TRACE_FILE),
            "eventsFile": str(config.CACHE_DIR / "events.ndjson"),
        },
        "pipeline": {
            "useLLM": llm_config.USE_LLM,
            "llmProvider": provider,
            "llmModel": str(auth.get("model") or ""),
            "llmAuth": auth,
            "imageBackend": visual_config.IMAGE_BACKEND,
            "visualAssetMode": visual_config.VISUAL_ASSET_MODE,
            "visualDirectorLLM": visual_config.VISUAL_DIRECTOR_LLM,
            "vfxLlmDirector": vfx_config.VFX_LLM_DIRECTOR_ENABLED,
            "recipeIdentityVersion": config.RECIPE_IDENTITY_VERSION,
            "contractVersions": visual_config.contract_versions_payload(),
            "worldRecipesDir": str(config.WORLD_RECIPES_DIR),
        },
        "sdcpp": sdcpp_debug_snapshot(include_log_tail=True),
        "lastCombineFailure": failure,
        "events": read_trace_tail(config.CACHE_DIR, config.CACHE_DIR / "events.ndjson", trace_runtime.TRACE_EVENTS_TAIL, full=full),
        "pipelineTrace": read_trace_tail(config.CACHE_DIR, trace_runtime.TRACE_FILE, trace_runtime.TRACE_EVENTS_TAIL, full=full),
        "promptTrace": read_trace_tail(config.CACHE_DIR, trace_runtime.PROMPT_TRACE_FILE, min(trace_runtime.TRACE_EVENTS_TAIL, 80), full=full),
    }


def trace_snapshot_html(*, full: bool = False) -> str:
    return render_trace_snapshot_html(
        trace_snapshot(full=full), app_version=config.APP_VERSION,
        trace_clip=(lambda value, _: trace_clip(value, default_max_chars=0)) if full else trace_runtime._trace_clip,
    )
