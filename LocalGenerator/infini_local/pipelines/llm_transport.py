from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib import request as urlrequest
from urllib import error as urlerror

from infini_local.core.env_utils import env_str
from infini_local.pipelines.pipeline_support import (
    LLM_LOCAL_REASONING_PROMPT,
    LLM_MAX_TOKENS,
    LLM_FALLBACK_API_KEY,
    LLM_FALLBACK_BASE_URL,
    LLM_FALLBACK_MODEL,
    LLM_FALLBACK_NETWORK_FAILS,
    LLM_FALLBACK_PROVIDER,
    LLM_PROVIDER,
    LLM_REASONING_EXCLUDE,
    LLM_REASONING_MAX_TOKENS,
    LLM_REASONING_MODE,
    LLM_RESPONSE_FORMAT_MODE,
    LMSTUDIO_MODEL,
    LMSTUDIO_URL,
    OPENAI_COMPAT_API_KEY,
    OPENAI_COMPAT_BASE_URL,
    OPENAI_COMPAT_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_APP_TITLE,
    OPENROUTER_BASE_URL,
    OPENROUTER_HTTP_REFERER,
    OPENROUTER_MODEL,
    log_event,
)


def _facade_override(name: str, default: Any) -> Any:
    module = sys.modules.get("infini_local.pipelines.llm_authoring_pipeline")
    if module is not None and hasattr(module, name):
        return getattr(module, name)
    return default

def _normalized_llm_provider(configured: str) -> str:
    configured = (configured or "").strip().lower().replace("-", "_")
    if configured in {"openrouter", "or"}:
        return "openrouter"
    if configured in {"openai", "openai_compat", "api", "remote"}:
        return "openai_compat"
    if configured in {"local", "lmstudio", "lm_studio", "ollama", ""}:
        if not configured and _facade_override("OPENROUTER_API_KEY", OPENROUTER_API_KEY) and _facade_override("OPENROUTER_MODEL", OPENROUTER_MODEL) and str(_facade_override("OPENROUTER_MODEL", OPENROUTER_MODEL)).lower() not in {"auto", "default"}:
            return "openrouter"
        return "local"
    return configured

def active_llm_provider(context: dict[str, Any] | None = None) -> str:
    if isinstance(context, dict) and context.get("provider"):
        return str(context.get("provider") or "local")
    return _normalized_llm_provider(_facade_override("LLM_PROVIDER", LLM_PROVIDER) or "")

def _llm_context_key(context: dict[str, Any] | None) -> str:
    ctx = context or {}
    return "|".join([
        str(ctx.get("provider") or "local"),
        str(ctx.get("base_url") or ""),
        str(ctx.get("model") or "auto"),
    ])

def _primary_llm_context() -> dict[str, Any]:
    provider = active_llm_provider()
    if provider == "openrouter":
        return {
            "provider": provider,
            "base_url": _facade_override("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL) or "https://openrouter.ai/api/v1",
            "model": _facade_override("OPENROUTER_MODEL", OPENROUTER_MODEL) or "auto",
            "api_key": _facade_override("OPENROUTER_API_KEY", OPENROUTER_API_KEY),
            "http_referer": _facade_override("OPENROUTER_HTTP_REFERER", OPENROUTER_HTTP_REFERER),
            "app_title": _facade_override("OPENROUTER_APP_TITLE", OPENROUTER_APP_TITLE),
            "label": "primary",
        }
    if provider == "openai_compat":
        return {
            "provider": provider,
            "base_url": _facade_override("OPENAI_COMPAT_BASE_URL", OPENAI_COMPAT_BASE_URL) or env_str("OPENAI_BASE_URL", "").rstrip("/"),
            "model": _facade_override("OPENAI_COMPAT_MODEL", OPENAI_COMPAT_MODEL) or "auto",
            "api_key": _facade_override("OPENAI_COMPAT_API_KEY", OPENAI_COMPAT_API_KEY),
            "label": "primary",
        }
    return {
        "provider": "local",
        "base_url": _facade_override("LMSTUDIO_URL", LMSTUDIO_URL),
        "model": _facade_override("LMSTUDIO_MODEL", LMSTUDIO_MODEL) or "auto",
        "api_key": "",
        "label": "primary",
    }

def _fallback_llm_context() -> dict[str, Any] | None:
    model = str(_facade_override("LLM_FALLBACK_MODEL", LLM_FALLBACK_MODEL) or "").strip()
    if not model:
        return None
    primary = _primary_llm_context()
    provider = _normalized_llm_provider(_facade_override("LLM_FALLBACK_PROVIDER", LLM_FALLBACK_PROVIDER) or str(primary.get("provider") or "local"))
    ctx: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "label": "fallback",
    }
    if provider == "openrouter":
        ctx["base_url"] = _facade_override("LLM_FALLBACK_BASE_URL", LLM_FALLBACK_BASE_URL) or _facade_override("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL) or "https://openrouter.ai/api/v1"
        ctx["api_key"] = _facade_override("LLM_FALLBACK_API_KEY", LLM_FALLBACK_API_KEY) or _facade_override("OPENROUTER_API_KEY", OPENROUTER_API_KEY)
        ctx["http_referer"] = _facade_override("OPENROUTER_HTTP_REFERER", OPENROUTER_HTTP_REFERER)
        ctx["app_title"] = _facade_override("OPENROUTER_APP_TITLE", OPENROUTER_APP_TITLE)
    elif provider == "openai_compat":
        ctx["base_url"] = _facade_override("LLM_FALLBACK_BASE_URL", LLM_FALLBACK_BASE_URL) or _facade_override("OPENAI_COMPAT_BASE_URL", OPENAI_COMPAT_BASE_URL) or env_str("OPENAI_BASE_URL", "").rstrip("/")
        ctx["api_key"] = _facade_override("LLM_FALLBACK_API_KEY", LLM_FALLBACK_API_KEY) or _facade_override("OPENAI_COMPAT_API_KEY", OPENAI_COMPAT_API_KEY)
    else:
        ctx["provider"] = "local"
        ctx["base_url"] = _facade_override("LLM_FALLBACK_BASE_URL", LLM_FALLBACK_BASE_URL) or _facade_override("LMSTUDIO_URL", LMSTUDIO_URL)
        ctx["api_key"] = ""
    if _llm_context_key(ctx) == _llm_context_key(primary):
        return None
    return ctx

def _join_openai_compat_url(base: str, endpoint: str) -> str:
    base = (base or "").rstrip("/")
    endpoint = "/" + endpoint.strip("/")
    if not base:
        return endpoint
    if base.endswith("/v1") or base.endswith("/api/v1"):
        return base + endpoint
    return base + "/v1" + endpoint

def llm_base_url(context: dict[str, Any] | None = None) -> str:
    ctx = context or _primary_llm_context()
    return str(ctx.get("base_url") or "")

def llm_chat_completions_url(context: dict[str, Any] | None = None) -> str:
    return _join_openai_compat_url(llm_base_url(context), "/chat/completions")

def llm_models_url(context: dict[str, Any] | None = None) -> str:
    return _join_openai_compat_url(llm_base_url(context), "/models")

def llm_auth_snapshot() -> dict[str, Any]:
    """Small UI/trace diagnostic for the currently selected LLM backend.

    This is intentionally config-only; it does not call remote APIs. It makes the
    common failure mode visible: OpenRouter selected, but no API key is loaded.
    """
    primary = _primary_llm_context()
    provider = active_llm_provider(primary)
    fallback = _fallback_llm_context()
    fallback_view = None
    if fallback is not None:
        fallback_view = {
            "provider": fallback.get("provider"),
            "baseUrl": fallback.get("base_url"),
            "model": fallback.get("model"),
            "apiKeyConfigured": bool(fallback.get("api_key")) if fallback.get("provider") in {"openrouter", "openai_compat"} else None,
            "networkFailsBeforeSwitch": _facade_override("LLM_FALLBACK_NETWORK_FAILS", LLM_FALLBACK_NETWORK_FAILS),
        }
    if provider == "openrouter":
        configured = bool(primary.get("api_key"))
        return {
            "provider": provider,
            "baseUrl": primary.get("base_url") or "https://openrouter.ai/api/v1",
            "model": primary.get("model") or "auto",
            "apiKeyConfigured": configured,
            "status": "configured" if configured else "missing_api_key",
            "hint": "OK" if configured else "Set INFINI_OPENROUTER_API_KEY in config.env or choose the local LM Studio preset.",
            "fallback": fallback_view,
        }
    if provider == "openai_compat":
        configured = bool(primary.get("api_key"))
        return {
            "provider": provider,
            "baseUrl": primary.get("base_url"),
            "model": primary.get("model") or "auto",
            "apiKeyConfigured": configured,
            "status": "configured" if configured else "missing_or_optional_api_key",
            "hint": "Set INFINI_OPENAI_COMPAT_API_KEY if your compatible endpoint requires Bearer auth.",
            "fallback": fallback_view,
        }
    return {
        "provider": provider or "local",
        "baseUrl": primary.get("base_url") or LMSTUDIO_URL,
        "model": primary.get("model") or "auto",
        "apiKeyConfigured": None,
        "status": "local_endpoint_required",
        "hint": "LM Studio must be running and exposing /v1 on the configured URL.",
        "fallback": fallback_view,
    }

def ensure_llm_auth_configured(context: dict[str, Any] | None = None) -> None:
    ctx = context or _primary_llm_context()
    provider = active_llm_provider(ctx)
    if provider == "openrouter" and not ctx.get("api_key"):
        raise RuntimeError("OpenRouter API key is missing: set INFINI_OPENROUTER_API_KEY in config.env or choose the local LM Studio preset.")

def llm_headers(extra: dict[str, str] | None = None, context: dict[str, Any] | None = None) -> dict[str, str]:
    ctx = context or _primary_llm_context()
    provider = active_llm_provider(ctx)
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if provider == "openrouter":
        if ctx.get("api_key"):
            headers["Authorization"] = f"Bearer {ctx.get('api_key')}"
        if ctx.get("http_referer"):
            headers["HTTP-Referer"] = str(ctx.get("http_referer"))
        if ctx.get("app_title"):
            headers["X-OpenRouter-Title"] = str(ctx.get("app_title"))
    elif provider == "openai_compat":
        if ctx.get("api_key"):
            headers["Authorization"] = f"Bearer {ctx.get('api_key')}"
    if extra:
        headers.update(extra)
    return headers

def llm_json_response_format(name: str = "infini_json") -> dict[str, Any] | None:
    """OpenAI-compatible structured JSON hint.

    Local LM Studio usually handles json_schema well. Remote gateways/models vary, so
    INFINI_LLM_RESPONSE_FORMAT can be set to json_schema/json_object/off. In auto mode
    remote APIs use json_object and llm_chat_json retries without response_format if a
    provider rejects the field.
    """
    mode = _facade_override("LLM_RESPONSE_FORMAT_MODE", LLM_RESPONSE_FORMAT_MODE)
    if mode == "auto":
        mode = "json_schema" if active_llm_provider() == "local" else "json_object"
    if mode in {"off", "none", "0", "false", "disabled"}:
        return None
    if mode == "json_object":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": False,
            "schema": {"type": "object", "additionalProperties": True},
        },
    }

def llm_answer_max_tokens(default: int | None = None) -> int:
    raw = _facade_override("LLM_MAX_TOKENS", LLM_MAX_TOKENS) if default is None else default
    try:
        value = int(raw)
    except Exception:
        value = 9000
    return max(512, min(64000, value))

def visual_director_max_tokens() -> int:
    """Token budget for the visual-director LLM step.

    If INFINI_VISUAL_DIRECTOR_MAX_TOKENS is blank/unset, inherit the global
    INFINI_LLM_MAX_TOKENS so the main GUI setting also affects the Z-Image
    prompt-authoring hop.
    """
    raw = env_str("INFINI_VISUAL_DIRECTOR_MAX_TOKENS", "")
    if not raw:
        return llm_answer_max_tokens()
    try:
        value = int(raw)
    except Exception:
        return llm_answer_max_tokens()
    return max(512, min(64000, value))

def llm_reasoning_payload(model_name: str = "") -> dict[str, Any] | None:
    """Return OpenRouter/OpenAI-compatible reasoning controls, or None.

    OpenRouter normalizes reasoning through `reasoning`: effort/max_tokens/enabled/exclude.
    Local LM Studio/Ollama-compatible servers often reject this field, so local reasoning is
    handled by system-prompt hinting instead.
    """
    mode = str(_facade_override("LLM_REASONING_MODE", LLM_REASONING_MODE) or "off").strip().lower().replace("-", "_")
    if mode in {"", "off", "false", "0", "disabled", "disable"}:
        return None
    provider = active_llm_provider()
    if provider == "local":
        return None
    exclude = bool(_facade_override("LLM_REASONING_EXCLUDE", LLM_REASONING_EXCLUDE))
    if mode in {"auto", "default", "enabled", "on"}:
        return {"enabled": True, "exclude": exclude}
    if mode in {"none", "no_reasoning"}:
        return {"effort": "none", "exclude": exclude}
    if mode in {"minimal", "low", "medium", "high", "xhigh"}:
        return {"effort": mode, "exclude": exclude}
    if mode in {"tokens", "token_budget", "max_tokens", "budget"}:
        return {"max_tokens": max(0, min(64000, int(_facade_override("LLM_REASONING_MAX_TOKENS", LLM_REASONING_MAX_TOKENS) or 0))), "exclude": exclude}
    # prompt_light / prompt_strong are local-only/prompt-only modes; do not send API field.
    if mode in {"prompt", "prompt_light", "prompt_strong", "local_prompt", "local_light", "local_strong"}:
        return None
    return None

def llm_reasoning_system_suffix(model_name: str = "") -> str:
    """Tiny prompt-only reasoning hint for local models.

    This does not ask the model to expose chain-of-thought. It just allows a private
    checklist before emitting the required JSON. Useful for Qwen/Gemma local runs where
    OpenRouter-style `reasoning` parameters are unavailable.
    """
    mode = str(_facade_override("LLM_REASONING_MODE", LLM_REASONING_MODE) or "off").strip().lower().replace("-", "_")
    provider = active_llm_provider()
    if mode in {"", "off", "false", "0", "disabled", "disable", "none", "no_reasoning"}:
        return ""
    if provider != "local" and mode not in {"prompt", "prompt_light", "prompt_strong", "local_prompt", "local_light", "local_strong"}:
        return ""
    if not _facade_override("LLM_LOCAL_REASONING_PROMPT", LLM_LOCAL_REASONING_PROMPT):
        return ""
    if mode in {"prompt_strong", "local_strong"}:
        return " Privately check parent facts, engine functions, schema, and balance. Output only the final JSON object."
    return " Privately check constraints briefly. Output only the final JSON object."

def apply_llm_common_options(req: dict[str, Any], *, model_name: str, default_max_tokens: int | None = None, allow_reasoning: bool = True) -> dict[str, Any]:
    req["max_tokens"] = llm_answer_max_tokens(default_max_tokens)
    if allow_reasoning:
        reasoning = llm_reasoning_payload(model_name)
        if reasoning:
            req["reasoning"] = reasoning
    return req

def http_get_json(url: str, timeout: int = 5, headers: dict[str, str] | None = None) -> dict[str, Any]:
    merged = {"Accept": "application/json"}
    if headers:
        merged.update(headers)
    req = urlrequest.Request(url, headers=merged, method="GET")
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def resolve_llm_model(context: dict[str, Any] | None = None) -> str:
    """Resolve the active OpenAI-compatible model name.

    Local: model=auto asks /v1/models and uses the first loaded model.
    OpenRouter: explicit INFINI_OPENROUTER_MODEL is preferred; model=auto tries to
    select a :free model from /models, then falls back to the first advertised model.
    """
    global _RESOLVED_LLM_MODELS
    ctx = context or _primary_llm_context()
    provider = active_llm_provider(ctx)
    configured = str(ctx.get("model") or "auto").strip()
    if configured and configured.lower() not in {"auto", "local-model", "local_model", "default"}:
        return configured
    cache_key = _llm_context_key(ctx)
    if _RESOLVED_LLM_MODELS.get(cache_key):
        return _RESOLVED_LLM_MODELS[cache_key]
    try:
        models = _facade_override("http_get_json", http_get_json)(llm_models_url(ctx), timeout=6, headers=llm_headers({"Accept": "application/json"}, context=ctx))
        data = models.get("data") if isinstance(models, dict) else None
        if isinstance(data, list) and data:
            preferred = None
            if provider == "openrouter":
                for item in data:
                    mid = str((item or {}).get("id") or (item or {}).get("name") or "").strip()
                    if mid.endswith(":free"):
                        preferred = mid
                        break
            first = data[0] or {}
            mid = preferred or str(first.get("id") or first.get("name") or "").strip()
            if mid:
                _RESOLVED_LLM_MODELS[cache_key] = mid
                log_event("info", "resolved LLM model", {"provider": provider, "model": mid, "label": ctx.get("label")})
                return mid
    except Exception as e:
        log_event("warn", "could not auto-resolve LLM model", {"provider": provider, "error": repr(e), "url": llm_models_url(ctx), "label": ctx.get("label")})
    if provider == "openrouter":
        return configured if configured.lower() not in {"auto", "default"} else "~openai/gpt-latest"
    return configured or "local-model"

def _clean_llm_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(payload, ensure_ascii=False))
    if out.get("response_format") is None:
        out.pop("response_format", None)
    return out

def http_json(url: str, payload: dict[str, Any], timeout: int = 10, headers: dict[str, str] | None = None) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    merged = {"Content-Type": "application/json"}
    if headers:
        merged.update(headers)
    req = urlrequest.Request(url, data=data, headers=merged, method="POST")
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def _llm_replay_stage_from_payload(payload: dict[str, Any]) -> str:
    """Best-effort label for an LLM hop, used only by raw replay fixtures.

    This is intentionally diagnostic/test infrastructure, not item design logic.
    It lets one INFINI_LLM_REPLAY_RAW directory feed planner, VFX-director,
    name/JSON repair, and genome-repair calls through the real JSON parse/repair path.
    """
    parts: list[str] = []
    for msg in payload.get("messages") or []:
        if isinstance(msg, dict):
            parts.append(str(msg.get("role") or ""))
            parts.append(str(msg.get("content") or ""))
    text = "\n".join(parts).lower()
    if "pixel-art asset director" in text or "infini_visual_director" in text or "visualkit" in text:
        return "vfx_director"
    if "repair incomplete combat genomes" in text or "infini_genome_repair" in text:
        return "genome_repair"
    # Planner markers must win over loose "repair"/"name" substring matches that often
    # appear inside planner payloads (repairPolicy, display names, etc.).
    if (
        "author of a terraria-like generated item" in text
        or "combine itema and itemb" in text
        or "infini_runtime_plan" in text
        or "priorityheader" in text
    ):
        return "planner"
    if "same planner" in text and "not a fallback" in text:
        return "author_repair"
    if ("repair this item name" in text) or ("name repair" in text) or ("infini_name_repair" in text):
        return "name_repair"
    if "repair" in text and "name" in text and "runtimeplan" not in text and "enginecalls" not in text:
        return "name_repair"
    return "llm"

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

def _llm_error_text(exc: Exception) -> str:
    parts = [repr(exc), str(exc)]
    body = getattr(exc, "_infini_body", "")
    if body:
        parts.append(str(body))
    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        parts.append(repr(cause))
        parts.append(str(cause))
    return " | ".join(p for p in parts if p).lower()

def _is_transport_error(exc: Exception) -> bool:
    if isinstance(exc, (urlerror.URLError, TimeoutError, ConnectionError)):
        return True
    text = _llm_error_text(exc)
    return any(tok in text for tok in ["timed out", "timeout", "connection refused", "connection reset", "temporarily unavailable", "name or service not known", "nodename nor servname", "failed to establish a new connection", "remote end closed connection"])

def _is_budget_or_auth_failure(exc: Exception) -> bool:
    if isinstance(exc, urlerror.HTTPError) and exc.code in {401, 402, 403, 429}:
        return True
    text = _llm_error_text(exc)
    return any(tok in text for tok in ["insufficient", "quota", "credit", "billing", "payment", "out of credits", "rate limit", "unauthorized", "api key", "余额", "balance", "no money"])

def _payload_for_context(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    out = _clean_llm_payload(payload)
    out["model"] = resolve_llm_model(context)
    return out

def _llm_chat_json_single_context(payload: dict[str, Any], timeout: int, context: dict[str, Any]) -> dict[str, Any]:
    ensure_llm_auth_configured(context)
    payload = _clean_llm_payload(payload)
    replay = _llm_replay_json_response(payload)
    if replay is not None:
        return replay
    payload = _payload_for_context(payload, context)
    url = llm_chat_completions_url(context)
    candidates: list[tuple[str, dict[str, Any]]] = [("original", payload)]
    if payload.get("reasoning") is not None:
        retry = dict(payload)
        retry.pop("reasoning", None)
        candidates.append(("without_reasoning", retry))
    if payload.get("response_format") is not None:
        retry = dict(payload)
        retry.pop("response_format", None)
        candidates.append(("without_response_format", retry))
    if payload.get("reasoning") is not None and payload.get("response_format") is not None:
        retry = dict(payload)
        retry.pop("reasoning", None)
        retry.pop("response_format", None)
        candidates.append(("without_reasoning_and_response_format", retry))

    last_error: Exception | None = None
    for label, candidate in candidates:
        try:
            if label != "original":
                log_event("warn", "retrying LLM request with reduced compatibility fields", {"provider": active_llm_provider(context), "mode": label, "label": context.get("label")})
            return _facade_override("http_json", http_json)(url, candidate, timeout=timeout, headers=llm_headers(context=context))
        except urlerror.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:2000]
                setattr(e, "_infini_body", body)
            except Exception:
                pass
            last_error = e
            provider = active_llm_provider(context)
            if provider == "openrouter" and e.code == 401:
                msg = "OpenRouter auth failed: API key is missing/invalid or was not saved in config.env (401 Unauthorized)."
                log_event("warn", "OpenRouter auth failed", {"provider": provider, "mode": label, "status": e.code, "body": body, "hint": msg, "label": context.get("label")})
                raise RuntimeError(msg) from e
            if e.code in {400, 404, 422} and label != candidates[-1][0]:
                log_event("warn", "LLM endpoint rejected request fields; trying compatibility fallback", {"provider": provider, "mode": label, "status": e.code, "body": body, "label": context.get("label")})
                continue
            log_event("warn", "LLM HTTP error", {"provider": provider, "mode": label, "status": e.code, "body": body, "label": context.get("label")})
            raise
    if last_error:
        raise last_error
    raise RuntimeError("LLM request failed without HTTP response")

def llm_chat_json(payload: dict[str, Any], timeout: int = 10) -> dict[str, Any]:
    primary = _primary_llm_context()
    fallback = _fallback_llm_context()
    try:
        return _llm_chat_json_single_context(payload, timeout, primary)
    except Exception as first_error:
        if not fallback:
            raise
        if _is_budget_or_auth_failure(first_error):
            log_event("warn", "LLM primary failed; switching to fallback", {"reason": "budget_or_auth", "primaryProvider": active_llm_provider(primary), "primaryModel": primary.get("model"), "fallbackProvider": active_llm_provider(fallback), "fallbackModel": fallback.get("model")})
            return _llm_chat_json_single_context(payload, timeout, fallback)
        if _is_transport_error(first_error):
            last_error = first_error
            total_attempts = max(2, int(_facade_override("LLM_FALLBACK_NETWORK_FAILS", LLM_FALLBACK_NETWORK_FAILS) or 2))
            for attempt in range(2, total_attempts + 1):
                try:
                    log_event("warn", "retrying primary LLM transport before fallback", {"attempt": attempt, "maxAttempts": total_attempts, "provider": active_llm_provider(primary), "model": primary.get("model")})
                    return _llm_chat_json_single_context(payload, timeout, primary)
                except Exception as retry_error:
                    last_error = retry_error
                    if _is_budget_or_auth_failure(retry_error):
                        log_event("warn", "LLM primary changed from transport failure to budget/auth failure; switching to fallback", {"provider": active_llm_provider(primary), "fallbackProvider": active_llm_provider(fallback), "fallbackModel": fallback.get("model")})
                        return _llm_chat_json_single_context(payload, timeout, fallback)
                    if not _is_transport_error(retry_error):
                        raise
            log_event("warn", "LLM primary transport failed repeatedly; switching to fallback", {"attempts": total_attempts, "primaryProvider": active_llm_provider(primary), "primaryModel": primary.get("model"), "fallbackProvider": active_llm_provider(fallback), "fallbackModel": fallback.get("model")})
            return _llm_chat_json_single_context(payload, timeout, fallback)
        raise

__all__ = ['_normalized_llm_provider', 'active_llm_provider', '_llm_context_key', '_primary_llm_context', '_fallback_llm_context', '_join_openai_compat_url', 'llm_base_url', 'llm_chat_completions_url', 'llm_models_url', 'llm_auth_snapshot', 'ensure_llm_auth_configured', 'llm_headers', 'llm_json_response_format', 'llm_answer_max_tokens', 'visual_director_max_tokens', 'llm_reasoning_payload', 'llm_reasoning_system_suffix', 'apply_llm_common_options', 'http_get_json', 'resolve_llm_model', '_clean_llm_payload', 'http_json', '_llm_replay_stage_from_payload', '_replay_content_from_json_object', '_load_llm_replay_raw', '_llm_replay_json_response', '_llm_error_text', '_is_transport_error', '_is_budget_or_auth_failure', '_payload_for_context', '_llm_chat_json_single_context', 'llm_chat_json']
