"""Explicit offline raw-response fixture loading, before network selection."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from infini_local.core.env_utils import env_str
from infini_local.pipelines.transport import provider_wire as wire
from infini_local.storage.trace_runtime import log_event


def _llm_replay_stage_from_payload(payload: dict[str, Any]) -> str:
    """Read explicit finite transport metadata; never inspect prompt content."""
    return wire._normalized_llm_stage(payload.get(wire.LLM_STAGE_KEY))



def _replay_content_from_json_object(obj: Any, stage: str) -> str | None:
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        # Stage-keyed JSON object: {"planner":"...", "vfx_director":"..."}.
        direct = obj.get(stage)
        if isinstance(direct, str):
            return direct
        for key in ("content", "text", "response", "raw"):
            value = obj.get(key)
            if isinstance(value, str):
                return value
        choices = obj.get("choices")
        if isinstance(choices, list) and choices:
            try:
                content = choices[0]["message"]["content"]
                if isinstance(content, str):
                    return content
            except Exception:
                return None
    return None



def _load_llm_replay_raw(spec: str, stage: str) -> tuple[str, str]:
    path = Path(spec).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"INFINI_LLM_REPLAY_RAW path does not exist: {path}")

    if path.is_dir():
        candidates = [
            path / f"{stage}.txt",
            path / f"{stage}.json",
            path / f"{stage}.jsonl",
            path / "default.txt",
            path / "default.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                content, source = _load_llm_replay_raw(str(candidate), stage)
                return content, source
        raise FileNotFoundError(f"No replay fixture for LLM stage '{stage}' in {path}")

    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8")
    if suffix == ".json":
        content = _replay_content_from_json_object(json.loads(raw), stage)
        if content is None:
            raise ValueError(f"Could not extract replay content from {path}")
        return content, str(path)

    if suffix == ".jsonl":
        fallback: str | None = None
        for line in raw.splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                obj_stage = str(obj.get("stage") or obj.get("hop") or obj.get("kind") or "").strip()
                content = _replay_content_from_json_object(obj, stage)
                if content is None:
                    continue
                if obj_stage in {stage, "*", "all", "llm"}:
                    return content, f"{path}#{obj_stage or 'line'}"
                if fallback is None and not obj_stage:
                    fallback = content
            elif fallback is None and isinstance(obj, str):
                fallback = obj
        if fallback is not None:
            return fallback, f"{path}#fallback"
        raise ValueError(f"No replay content for LLM stage '{stage}' in {path}")

    return raw, str(path)



def _llm_replay_json_response(payload: dict[str, Any]) -> dict[str, Any] | None:
    spec = env_str("INFINI_LLM_REPLAY_RAW", "")
    if not spec:
        return None
    stage = _llm_replay_stage_from_payload(payload)
    content, source = _load_llm_replay_raw(spec, stage)
    log_event("info", "LLM replay raw response used", {"stage": stage, "source": source, "chars": len(content)})
    return {
        "choices": [
            {"message": {"role": "assistant", "content": content}}
        ],
        "_debug": {"replay": True, "stage": stage, "source": source},
    }
