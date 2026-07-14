from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def json_slim(obj: Any, max_chars: int = 40000) -> Any:
    """Return a JSON-safe, size-bounded debug object for failure traces."""
    try:
        text = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)[:max_chars]
    if len(text) <= max_chars:
        try:
            return json.loads(text)
        except Exception:
            return text
    return {"_truncated": True, "jsonPrefix": text[:max_chars]}


def log_event(cache_dir: Path, level: str, message: str, payload: Any = None) -> None:
    """Append human-readable diagnostics to cache/events.ndjson."""
    try:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        event = {
            "createdAt": time.time(),
            "level": str(level),
            "message": str(message),
            "payload": payload,
        }
        with (cache_dir / "events.ndjson").open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")
    except Exception:
        pass


def trace_clip(value: Any, *, default_max_chars: int, max_chars: int | None = None) -> str:
    limit = int(default_max_chars) if max_chars is None else max(200, int(max_chars))
    try:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str, indent=2)
    except Exception:
        text = str(value)
    if len(text) > limit:
        return text[:limit] + "\n...<clipped " + str(len(text) - limit) + " chars>"
    return text


def trace_message_summary(messages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, m in enumerate(messages or []):
        content = str((m or {}).get("content") or "")
        out.append({
            "index": i,
            "role": str((m or {}).get("role") or ""),
            "name": str((m or {}).get("name") or ""),
            "chars": len(content),
            "preview": content[:420],
        })
    return out


def trace_event(
    *,
    cache_dir: Path,
    trace_prompts_enabled: bool,
    trace_max_prompt_chars: int,
    trace_file: Path,
    prompt_trace_file: Path,
    kind: str,
    stage: str,
    title: str,
    payload: Any = None,
    prompt: Any = None,
    negative: Any = None,
    response: Any = None,
    error: Any = None,
) -> None:
    if not trace_prompts_enabled and kind in {"prompt", "response"}:
        return
    try:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        event: dict[str, Any] = {"ts": int(time.time()), "kind": str(kind), "stage": str(stage), "title": str(title)}
        if payload is not None:
            event["payload"] = json_slim(payload, 24000)
        if prompt is not None:
            event["prompt"] = trace_clip(prompt, default_max_chars=trace_max_prompt_chars)
        if negative is not None:
            event["negative"] = trace_clip(negative, default_max_chars=trace_max_prompt_chars, max_chars=6000)
        if response is not None:
            event["response"] = trace_clip(response, default_max_chars=trace_max_prompt_chars)
        if error is not None:
            event["error"] = trace_clip(error, default_max_chars=trace_max_prompt_chars, max_chars=6000)
        target = prompt_trace_file if kind in {"prompt", "response"} or prompt is not None else trace_file
        with Path(target).open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def tail_text_file(path: str | Path, max_chars: int = 16000) -> str:
    try:
        p = Path(path)
        if not p.exists():
            return ""
        text = p.read_text(encoding="utf-8", errors="replace")
        return text[-max_chars:]
    except Exception as e:
        return f"<tail failed: {e!r}>"


def tail_ndjson(path: str | Path, limit: int = 80) -> list[dict[str, Any]]:
    try:
        p = Path(path)
        if not p.exists():
            return []
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-max(1, int(limit)):]
        out: list[dict[str, Any]] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                out.append(obj if isinstance(obj, dict) else {"raw": obj})
            except Exception:
                out.append({"raw": line})
        return out
    except Exception as e:
        return [{"level": "error", "message": "trace read failed", "error": repr(e)}]
