from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from infini_local.web import trace_dashboard


# AGENT MAP: debug trace snapshot payload shaping for server.py. It reads trace
# files and status callables only; it must not run generation or mutate gameplay
# output/cache state.

FailureSummary = Callable[[], dict[str, Any]]
ProviderName = Callable[[], str]
PayloadCallable = Callable[[], dict[str, Any]]
SdcppSnapshot = Callable[..., dict[str, Any]]
TailNdjson = Callable[[Path, int], list[Any]]
TraceClip = Callable[[Any, int | None], str]


def build_trace_snapshot(
    *,
    app_version: str,
    root: Path,
    config_path: Path,
    cache_dir: Path,
    recipe_identity_version: str,
    world_recipes_dir: Path,
    use_llm: bool,
    llm_runtime_authoring: bool,
    llm_runtime_plan_required: bool,
    image_backend: str,
    visual_asset_mode: str,
    visual_director_llm: bool,
    vfx_llm_director_enabled: bool,
    openrouter_model: str,
    openai_compat_model: str,
    lmstudio_model: str,
    trace_prompts_enabled: bool,
    trace_max_prompt_chars: int,
    trace_events_tail: int,
    prompt_trace_file: Path,
    trace_file: Path,
    last_combine_failure_file: Path,
    last_combine_failure_summary: FailureSummary,
    active_llm_provider: ProviderName,
    llm_auth_snapshot: PayloadCallable,
    contract_versions_payload: PayloadCallable,
    sdcpp_debug_snapshot: SdcppSnapshot,
    tail_ndjson: TailNdjson,
) -> dict[str, Any]:
    failure: Any = last_combine_failure_summary()
    try:
        if last_combine_failure_file.exists():
            failure = json.loads(last_combine_failure_file.read_text(encoding="utf-8"))
    except Exception:
        pass
    provider = active_llm_provider()
    return {
        "ok": True,
        "version": app_version,
        "time": int(time.time()),
        "serverRoot": str(root),
        "configPath": str(config_path),
        "pid": os.getpid(),
        "cacheDir": str(cache_dir),
        "traceConfig": {
            "tracePrompts": trace_prompts_enabled,
            "maxPromptChars": trace_max_prompt_chars,
            "eventsTail": trace_events_tail,
            "promptTraceFile": str(prompt_trace_file),
            "pipelineTraceFile": str(trace_file),
            "eventsFile": str(cache_dir / "events.ndjson"),
        },
        "pipeline": {
            "useLLM": use_llm,
            "llmProvider": provider,
            "llmModel": (openrouter_model if provider == "openrouter" else openai_compat_model if provider == "openai_compat" else lmstudio_model),
            "llmAuth": llm_auth_snapshot(),
            "llmRuntimeAuthoring": llm_runtime_authoring,
            "llmRuntimePlanRequired": llm_runtime_plan_required,
            "imageBackend": image_backend,
            "visualAssetMode": visual_asset_mode,
            "visualDirectorLLM": visual_director_llm,
            "vfxLlmDirector": vfx_llm_director_enabled,
            "recipeIdentityVersion": recipe_identity_version,
            "contractVersions": contract_versions_payload(),
            "worldRecipesDir": str(world_recipes_dir),
        },
        "sdcpp": sdcpp_debug_snapshot(include_log_tail=True),
        "lastCombineFailure": failure,
        "events": tail_ndjson(cache_dir / "events.ndjson", trace_events_tail),
        "pipelineTrace": tail_ndjson(trace_file, trace_events_tail),
        "promptTrace": tail_ndjson(prompt_trace_file, min(trace_events_tail, 80)),
    }


def render_trace_snapshot_html(snapshot: dict[str, Any], *, app_version: str, trace_clip: TraceClip) -> str:
    return trace_dashboard.render_trace_snapshot_html(
        snapshot,
        app_version=app_version,
        trace_clip=trace_clip,
    )
