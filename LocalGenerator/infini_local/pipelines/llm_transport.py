from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
from pathlib import Path
import threading
import time
from typing import Any
from urllib import request as urlrequest
from urllib import error as urlerror

from infini_local.core.env_utils import env_str
from infini_local.core.llm_config import (
    LLM_FALLBACK_API_KEY,
    LLM_FALLBACK_BASE_URL,
    LLM_FALLBACK_MODEL,
    LLM_FALLBACK_NETWORK_FAILS,
    LLM_FALLBACK_PROVIDER,
    LLM_API_MODE,
    LLM_LOCAL_REASONING_PROMPT,
    LLM_MAX_TOKENS,
    LLM_PROVIDER,
    LLM_POOL_FAILURE_COOLDOWN_SECONDS,
    LLM_POOL_PROFILES,
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
)
from infini_local.storage.trace_runtime import log_event


_RESOLVED_LLM_MODELS: dict[str, str] = {}
_RESPONSES_CAPABILITY: dict[str, bool] = {}
_PROFILE_COOLDOWN_UNTIL: dict[str, float] = {}
_LLM_POOL_LOCK = threading.Lock()
_LLM_POOL_CURSOR = 0
_LLM_LEASE_SEQUENCE = 0


@dataclass
class LlmItemLease:
    recipe_key: str
    lease_id: str
    profile_id: str
    context: dict[str, Any]
    pool_size: int
    profiles: tuple[dict[str, Any], ...] = ()
    legacy_fallback_allowed: bool = False
    previous_response_id: str = ""
    responses_disabled: bool = False
    call_count: int = 0
    stages: list[str] = field(default_factory=list)
    failovers: list[dict[str, str]] = field(default_factory=list)

    def snapshot(self) -> dict[str, Any]:
        return {
            "leaseId": self.lease_id,
            "profileId": self.profile_id,
            "provider": self.context.get("provider"),
            "baseUrl": self.context.get("base_url"),
            "model": self.context.get("model"),
            "apiMode": self.context.get("api_mode"),
            "poolSize": self.pool_size,
            "callCount": self.call_count,
            "stages": list(self.stages),
            "failovers": list(self.failovers),
            "responseChainActive": bool(self.previous_response_id and not self.responses_disabled),
        }


_CURRENT_LLM_ITEM_LEASE: ContextVar[LlmItemLease | None] = ContextVar("infini_llm_item_lease", default=None)



def _normalized_llm_provider(configured: str) -> str:
    configured = (configured or "").strip().lower().replace("-", "_")
    if configured in {"openrouter", "or"}:
        return "openrouter"
    if configured in {"openai", "openai_compat", "api", "remote"}:
        return "openai_compat"
    if configured in {"local", "lmstudio", "lm_studio", "ollama", ""}:
        if not configured and OPENROUTER_API_KEY and OPENROUTER_MODEL and str(OPENROUTER_MODEL).lower() not in {"auto", "default"}:
            return "openrouter"
        return "local"
    return configured

def active_llm_provider(context: dict[str, Any] | None = None) -> str:
    if isinstance(context, dict) and context.get("provider"):
        return str(context.get("provider") or "local")
    lease = _CURRENT_LLM_ITEM_LEASE.get()
    if lease is not None and lease.context.get("provider"):
        return str(lease.context.get("provider") or "local")
    return _normalized_llm_provider(LLM_PROVIDER or "")


def _normalized_api_mode(value: Any) -> str:
    mode = str(value or "auto").strip().lower().replace("-", "_")
    if mode in {"responses", "response"}:
        return "responses"
    if mode in {"chat", "chat_completion", "chat_completions", "completions"}:
        return "chat_completions"
    return "auto"


def _llm_context_key(context: dict[str, Any] | None) -> str:
    ctx = context or {}
    return "|".join([
        str(ctx.get("provider") or "local"),
        str(ctx.get("base_url") or ""),
        str(ctx.get("model") or "auto"),
        str(ctx.get("api_mode") or "chat_completions"),
    ])


def _legacy_primary_llm_context() -> dict[str, Any]:
    provider = _normalized_llm_provider(LLM_PROVIDER or "")
    if provider == "openrouter":
        return {
            "provider": provider,
            "base_url": OPENROUTER_BASE_URL or "https://openrouter.ai/api/v1",
            "model": OPENROUTER_MODEL or "auto",
            "api_key": OPENROUTER_API_KEY,
            "http_referer": OPENROUTER_HTTP_REFERER,
            "app_title": OPENROUTER_APP_TITLE,
            "label": "llm_1",
            "profile_id": "llm_1",
            "api_mode": _normalized_api_mode(LLM_API_MODE),
        }
    if provider == "openai_compat":
        return {
            "provider": provider,
            "base_url": OPENAI_COMPAT_BASE_URL or env_str("OPENAI_BASE_URL", "").rstrip("/"),
            "model": OPENAI_COMPAT_MODEL or "auto",
            "api_key": OPENAI_COMPAT_API_KEY,
            "label": "llm_1",
            "profile_id": "llm_1",
            "api_mode": _normalized_api_mode(LLM_API_MODE),
        }
    return {
        "provider": "local",
        "base_url": LMSTUDIO_URL,
        "model": LMSTUDIO_MODEL or "auto",
        "api_key": "",
        "label": "llm_1",
        "profile_id": "llm_1",
        "api_mode": _normalized_api_mode(LLM_API_MODE),
    }


def _primary_llm_context() -> dict[str, Any]:
    lease = _CURRENT_LLM_ITEM_LEASE.get()
    return lease.context if lease is not None else _legacy_primary_llm_context()


def _pool_profile_context(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not bool(raw.get("enabled")):
        return None
    model = str(raw.get("model") or "").strip()
    if not model:
        return None
    provider = _normalized_llm_provider(str(raw.get("provider") or "openai_compat"))
    base_url = str(raw.get("base_url") or "").rstrip("/")
    api_key = str(raw.get("api_key") or "")
    if provider == "openrouter":
        base_url = base_url or OPENROUTER_BASE_URL or "https://openrouter.ai/api/v1"
        api_key = api_key or OPENROUTER_API_KEY
    elif provider == "local":
        base_url = base_url or LMSTUDIO_URL
        api_key = ""
    else:
        provider = "openai_compat"
        base_url = base_url or OPENAI_COMPAT_BASE_URL or env_str("OPENAI_BASE_URL", "").rstrip("/")
        api_key = api_key or OPENAI_COMPAT_API_KEY
    profile_id = str(raw.get("id") or "llm_pool").strip()
    return {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "label": profile_id,
        "profile_id": profile_id,
        "api_mode": _normalized_api_mode(raw.get("api_mode")),
        "http_referer": OPENROUTER_HTTP_REFERER if provider == "openrouter" else "",
        "app_title": OPENROUTER_APP_TITLE if provider == "openrouter" else "",
    }


def configured_llm_pool() -> list[dict[str, Any]]:
    profiles = [_legacy_primary_llm_context()]
    seen_ids = {"llm_1"}
    for raw in LLM_POOL_PROFILES:
        context = _pool_profile_context(raw)
        if context is None:
            continue
        profile_id = str(context.get("profile_id") or "")
        if profile_id and profile_id not in seen_ids:
            profiles.append(context)
            seen_ids.add(profile_id)
    return profiles


def _profile_id(context: dict[str, Any]) -> str:
    return str(context.get("profile_id") or context.get("label") or "llm_1")


def _profile_is_available(context: dict[str, Any], *, now: float | None = None) -> bool:
    current = time.monotonic() if now is None else now
    return _PROFILE_COOLDOWN_UNTIL.get(_profile_id(context), 0.0) <= current


def _available_profile_index(profiles: list[dict[str, Any]], start_index: int) -> int:
    now = time.monotonic()
    for offset in range(len(profiles)):
        index = (start_index + offset) % len(profiles)
        if _profile_is_available(profiles[index], now=now):
            return index
    return start_index % len(profiles)


def begin_llm_item_lease(recipe_key: str) -> tuple[LlmItemLease, Any]:
    global _LLM_POOL_CURSOR, _LLM_LEASE_SEQUENCE
    profiles = configured_llm_pool()
    with _LLM_POOL_LOCK:
        selected_index = _available_profile_index(profiles, _LLM_POOL_CURSOR % len(profiles))
        selected = dict(profiles[selected_index])
        _LLM_POOL_CURSOR = (selected_index + 1) % len(profiles)
        _LLM_LEASE_SEQUENCE += 1
        sequence = _LLM_LEASE_SEQUENCE
    profile_id = str(selected.get("profile_id") or selected.get("label") or "llm_1")
    lease = LlmItemLease(
        recipe_key=str(recipe_key or ""),
        lease_id=f"{profile_id}:{sequence}",
        profile_id=profile_id,
        context=selected,
        pool_size=len(profiles),
        profiles=tuple(dict(profile) for profile in profiles),
        legacy_fallback_allowed=len(profiles) == 1,
    )
    token = _CURRENT_LLM_ITEM_LEASE.set(lease)
    log_event("info", "LLM item lease acquired", lease.snapshot())
    return lease, token


def end_llm_item_lease(lease: LlmItemLease, token: Any) -> None:
    log_event("info", "LLM item lease released", lease.snapshot())
    _CURRENT_LLM_ITEM_LEASE.reset(token)


@contextmanager
def llm_item_lease(recipe_key: str):
    lease, token = begin_llm_item_lease(recipe_key)
    try:
        yield lease
    finally:
        end_llm_item_lease(lease, token)


def current_llm_item_lease() -> LlmItemLease | None:
    return _CURRENT_LLM_ITEM_LEASE.get()


def _reset_llm_pool_runtime_for_tests() -> None:
    global _LLM_POOL_CURSOR, _LLM_LEASE_SEQUENCE, _RESOLVED_LLM_MODELS, _RESPONSES_CAPABILITY, _PROFILE_COOLDOWN_UNTIL
    with _LLM_POOL_LOCK:
        _LLM_POOL_CURSOR = 0
        _LLM_LEASE_SEQUENCE = 0
    _RESOLVED_LLM_MODELS = {}
    _RESPONSES_CAPABILITY = {}
    _PROFILE_COOLDOWN_UNTIL = {}


def _fallback_llm_context() -> dict[str, Any] | None:
    model = str(LLM_FALLBACK_MODEL or "").strip()
    if not model:
        return None
    primary = _legacy_primary_llm_context()
    provider = _normalized_llm_provider(LLM_FALLBACK_PROVIDER or str(primary.get("provider") or "local"))
    ctx: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "label": "fallback",
        "profile_id": "legacy_fallback",
        "api_mode": "chat_completions",
    }
    if provider == "openrouter":
        ctx["base_url"] = LLM_FALLBACK_BASE_URL or OPENROUTER_BASE_URL or "https://openrouter.ai/api/v1"
        ctx["api_key"] = LLM_FALLBACK_API_KEY or OPENROUTER_API_KEY
        ctx["http_referer"] = OPENROUTER_HTTP_REFERER
        ctx["app_title"] = OPENROUTER_APP_TITLE
    elif provider == "openai_compat":
        ctx["base_url"] = LLM_FALLBACK_BASE_URL or OPENAI_COMPAT_BASE_URL or env_str("OPENAI_BASE_URL", "").rstrip("/")
        ctx["api_key"] = LLM_FALLBACK_API_KEY or OPENAI_COMPAT_API_KEY
    else:
        ctx["provider"] = "local"
        ctx["base_url"] = LLM_FALLBACK_BASE_URL or LMSTUDIO_URL
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


def llm_responses_url(context: dict[str, Any] | None = None) -> str:
    return _join_openai_compat_url(llm_base_url(context), "/responses")


def llm_models_url(context: dict[str, Any] | None = None) -> str:
    return _join_openai_compat_url(llm_base_url(context), "/models")

def llm_auth_snapshot() -> dict[str, Any]:
    """Small UI/trace diagnostic for the currently selected LLM backend.

    This is intentionally config-only; it does not call remote APIs. It makes the
    common failure mode visible: OpenRouter selected, but no API key is loaded.
    """
    primary = _legacy_primary_llm_context()
    provider = active_llm_provider(primary)
    pool_view = [
        {
            "profileId": context.get("profile_id"),
            "provider": context.get("provider"),
            "baseUrl": context.get("base_url"),
            "model": context.get("model"),
            "apiMode": context.get("api_mode"),
            "apiKeyConfigured": (
                bool(context.get("api_key"))
                if context.get("provider") in {"openrouter", "openai_compat"}
                else None
            ),
            "responsesSupported": _RESPONSES_CAPABILITY.get(_llm_context_key(context)),
        }
        for context in configured_llm_pool()
    ]
    fallback = _fallback_llm_context()
    fallback_view = None
    if fallback is not None:
        fallback_view = {
            "provider": fallback.get("provider"),
            "baseUrl": fallback.get("base_url"),
            "model": fallback.get("model"),
            "apiKeyConfigured": bool(fallback.get("api_key")) if fallback.get("provider") in {"openrouter", "openai_compat"} else None,
            "networkFailsBeforeSwitch": LLM_FALLBACK_NETWORK_FAILS,
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
            "pool": pool_view,
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
            "pool": pool_view,
        }
    return {
        "provider": provider or "local",
        "baseUrl": primary.get("base_url") or LMSTUDIO_URL,
        "model": primary.get("model") or "auto",
        "apiKeyConfigured": None,
        "status": "local_endpoint_required",
        "hint": "LM Studio must be running and exposing /v1 on the configured URL.",
        "fallback": fallback_view,
        "pool": pool_view,
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

def llm_json_response_format(
    name: str = "infini_json",
    *,
    schema: dict[str, Any] | None = None,
    strict: bool = False,
) -> dict[str, Any] | None:
    """OpenAI-compatible structured JSON hint.

    Callers may supply their real boundary schema. In auto mode, a supplied schema
    is attempted on every OpenAI-compatible provider; ``llm_chat_json`` retries
    without the field when a gateway rejects it. Calls without a schema keep the
    conservative remote ``json_object`` behavior. The Pydantic boundary remains
    authoritative in every mode.
    """
    mode = LLM_RESPONSE_FORMAT_MODE
    if mode == "auto":
        # When a caller supplies a real schema, try it on every OpenAI-compatible
        # provider. llm_chat_json already retries without response_format when a
        # gateway rejects json_schema, so remote capability variance does not need
        # to weaken the first attempt. Callers without a schema keep the old policy.
        mode = "json_schema" if schema is not None or active_llm_provider() == "local" else "json_object"
    if mode in {"off", "none", "0", "false", "disabled"}:
        return None
    if mode == "json_object":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": bool(strict),
            "schema": schema or {"type": "object", "additionalProperties": True},
        },
    }

def llm_answer_max_tokens(default: int | None = None) -> int:
    raw = LLM_MAX_TOKENS if default is None else default
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

def _configured_reasoning_payload() -> dict[str, Any] | None:
    mode = str(LLM_REASONING_MODE or "off").strip().lower().replace("-", "_")
    if mode in {"", "off", "false", "0", "disabled", "disable"}:
        return None
    exclude = bool(LLM_REASONING_EXCLUDE)
    if mode in {"auto", "default", "enabled", "on"}:
        return {"enabled": True, "exclude": exclude}
    if mode in {"none", "no_reasoning"}:
        return {"effort": "none", "exclude": exclude}
    if mode in {"minimal", "low", "medium", "high", "xhigh"}:
        return {"effort": mode, "exclude": exclude}
    if mode in {"tokens", "token_budget", "max_tokens", "budget"}:
        return {"max_tokens": max(0, min(64000, int(LLM_REASONING_MAX_TOKENS or 0))), "exclude": exclude}
    # prompt_light / prompt_strong are local-only/prompt-only modes; do not send API field.
    return None


def llm_reasoning_payload(model_name: str = "", context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Return OpenRouter/OpenAI-compatible reasoning controls, or None.

    OpenRouter normalizes reasoning through `reasoning`: effort/max_tokens/enabled/exclude.
    Local LM Studio/Ollama-compatible servers often reject this field, so local reasoning is
    handled by system-prompt hinting instead.
    """
    configured = _configured_reasoning_payload()
    if configured is None or active_llm_provider(context) == "local":
        return None
    return configured


def _is_google_gemini_openai_compat(model_name: str, context: dict[str, Any] | None = None) -> bool:
    return (
        active_llm_provider(context) == "openai_compat"
        and "generativelanguage.googleapis.com" in llm_base_url(context).lower()
        and "gemini" in str(model_name or "").lower()
    )


def _google_reasoning_effort(reasoning: dict[str, Any]) -> str:
    """Map Infini reasoning controls to Google's documented OpenAI-compatible field."""
    effort = str(reasoning.get("effort") or "").strip().lower()
    if effort == "xhigh":
        return "high"
    if effort in {"minimal", "low", "medium", "high"}:
        return effort
    # Gemini 3 cannot disable thinking. Keep explicit none bounded rather than sending
    # an unsupported semantic value; auto/enabled gets useful but not maximal thinking.
    if effort == "none":
        return "minimal"
    if reasoning.get("max_tokens") is not None:
        budget = int(reasoning.get("max_tokens") or 0)
        if budget <= 1024:
            return "low"
        if budget <= 8192:
            return "medium"
        return "high"
    return "medium"


_REASONING_INTENT_KEY = "_infini_reasoning_intent"


def _remap_reasoning_for_context(payload: dict[str, Any], *, model_name: str, context: dict[str, Any]) -> None:
    """Rewrite reasoning controls for the provider that will actually receive the request."""
    intent = payload.get(_REASONING_INTENT_KEY) if isinstance(payload.get(_REASONING_INTENT_KEY), dict) else None
    explicit = payload.get("reasoning") if isinstance(payload.get("reasoning"), dict) else None
    effort = str(payload.get("reasoning_effort") or "").strip().lower()
    payload.pop(_REASONING_INTENT_KEY, None)
    payload.pop("reasoning", None)
    payload.pop("reasoning_effort", None)
    if active_llm_provider(context) == "local":
        return
    reasoning = dict(explicit or intent or {})
    if not reasoning and effort:
        reasoning = {"effort": effort, "exclude": bool(LLM_REASONING_EXCLUDE)}
    if not reasoning:
        return
    if _is_google_gemini_openai_compat(model_name, context):
        payload["reasoning_effort"] = _google_reasoning_effort(reasoning)
    else:
        payload["reasoning"] = reasoning


def llm_reasoning_system_suffix(model_name: str = "") -> str:
    """Tiny prompt-only reasoning hint for local models.

    This does not ask the model to expose chain-of-thought. It just allows a private
    checklist before emitting the required JSON. Useful for Qwen/Gemma local runs where
    OpenRouter-style `reasoning` parameters are unavailable.
    """
    mode = str(LLM_REASONING_MODE or "off").strip().lower().replace("-", "_")
    provider = active_llm_provider()
    if mode in {"", "off", "false", "0", "disabled", "disable", "none", "no_reasoning"}:
        return ""
    if provider != "local" and mode not in {"prompt", "prompt_light", "prompt_strong", "local_prompt", "local_light", "local_strong"}:
        return ""
    if not LLM_LOCAL_REASONING_PROMPT:
        return ""
    if mode in {"prompt_strong", "local_strong"}:
        return " Privately check parent facts, engine functions, schema, and balance. Output only the final JSON object."
    return " Privately check constraints briefly. Output only the final JSON object."

def apply_llm_common_options(req: dict[str, Any], *, model_name: str, default_max_tokens: int | None = None, allow_reasoning: bool = True) -> dict[str, Any]:
    req["max_tokens"] = llm_answer_max_tokens(default_max_tokens)
    if allow_reasoning:
        configured = _configured_reasoning_payload()
        if configured:
            # Internal intent survives a local-primary attempt and is stripped before
            # every real HTTP request; remote fallbacks remap it for their provider.
            req[_REASONING_INTENT_KEY] = dict(configured)
        reasoning = llm_reasoning_payload(model_name)
        if reasoning:
            if _is_google_gemini_openai_compat(model_name):
                req["reasoning_effort"] = _google_reasoning_effort(reasoning)
            else:
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
        models = http_get_json(llm_models_url(ctx), timeout=6, headers=llm_headers({"Accept": "application/json"}, context=ctx))
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
    stage_by_system_name = {
        "item_author_contract": "planner",
        "runtime_repair_contract": "author_repair",
        "genome_repair_contract": "genome_repair",
        "name_repair_contract": "name_repair",
        "visual_director_contract": "visual_director",
        "vfx_director_contract": "vfx_director",
    }
    parts: list[str] = []
    for msg in payload.get("messages") or []:
        if isinstance(msg, dict):
            if str(msg.get("role") or "") == "system":
                stage = stage_by_system_name.get(str(msg.get("name") or ""))
                if stage:
                    return stage
            parts.append(str(msg.get("role") or ""))
            parts.append(str(msg.get("content") or ""))
    text = "\n".join(parts).lower()
    if "pixel-art asset director" in text or "infini_visual_director" in text or "visualkit" in text:
        return "visual_director"
    if "vfx director" in text or "vfxinputpacket" in text or "infini_vfx" in text:
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
    model_name = resolve_llm_model(context)
    out["model"] = model_name
    _remap_reasoning_for_context(out, model_name=model_name, context=context)
    return out


def _usage_fields(result: dict[str, Any]) -> dict[str, int]:
    usage_raw = result.get("usage")
    usage: dict[str, Any] = usage_raw if isinstance(usage_raw, dict) else {}
    input_details_raw = usage.get("input_tokens_details")
    prompt_details_raw = usage.get("prompt_tokens_details")
    input_details: dict[str, Any] = input_details_raw if isinstance(input_details_raw, dict) else {}
    prompt_details: dict[str, Any] = prompt_details_raw if isinstance(prompt_details_raw, dict) else {}
    return {
        "inputTokens": int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
        "outputTokens": int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
        "cachedInputTokens": int(input_details.get("cached_tokens") or prompt_details.get("cached_tokens") or 0),
    }


def _response_format_for_responses(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    kind = str(value.get("type") or "")
    if kind == "json_object":
        return {"type": "json_object"}
    if kind != "json_schema" or not isinstance(value.get("json_schema"), dict):
        return None
    schema_raw = value["json_schema"]
    schema: dict[str, Any] = schema_raw
    return {
        "type": "json_schema",
        "name": str(schema.get("name") or "infini_json"),
        "strict": bool(schema.get("strict")),
        "schema": schema.get("schema") or {"type": "object", "additionalProperties": True},
    }


def _responses_payload_from_chat(payload: dict[str, Any], previous_response_id: str = "") -> dict[str, Any]:
    instructions: list[str] = []
    input_messages: list[dict[str, str]] = []
    for raw in payload.get("messages") or []:
        if not isinstance(raw, dict):
            continue
        role = str(raw.get("role") or "user")
        content = str(raw.get("content") or "")
        if role == "system":
            if content:
                instructions.append(content)
            continue
        if role not in {"user", "assistant"}:
            role = "user"
        input_messages.append({"role": role, "content": content})
    out: dict[str, Any] = {
        "model": payload.get("model"),
        "input": input_messages,
    }
    if instructions:
        out["instructions"] = "\n\n".join(instructions)
    if previous_response_id:
        out["previous_response_id"] = previous_response_id
    if payload.get("temperature") is not None:
        out["temperature"] = payload.get("temperature")
    if payload.get("max_tokens") is not None:
        out["max_output_tokens"] = payload.get("max_tokens")
    response_format = _response_format_for_responses(payload.get("response_format"))
    if response_format is not None:
        out["text"] = {"format": response_format}
    reasoning_raw = payload.get("reasoning")
    reasoning: dict[str, Any] = reasoning_raw if isinstance(reasoning_raw, dict) else {}
    effort = str(payload.get("reasoning_effort") or reasoning.get("effort") or "").strip()
    if effort:
        out["reasoning"] = {"effort": "high" if effort == "xhigh" else effort}
    return out


def _responses_output_text(result: dict[str, Any]) -> str:
    direct = result.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    chunks: list[str] = []
    for item in result.get("output") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            if str(part.get("type") or "") == "refusal":
                raise RuntimeError(str(part.get("refusal") or "LLM Responses request refused"))
            text = part.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "".join(chunks).strip()


def _llm_responses_json_single_context(payload: dict[str, Any], timeout: int, context: dict[str, Any]) -> dict[str, Any]:
    ensure_llm_auth_configured(context)
    prepared = _payload_for_context(payload, context)
    lease = _CURRENT_LLM_ITEM_LEASE.get()
    previous_id = ""
    messages_raw = prepared.get("messages")
    messages: list[Any] = messages_raw if isinstance(messages_raw, list) else []
    clean_stage_dossier = (
        len(messages) == 2
        and isinstance(messages[0], dict)
        and isinstance(messages[1], dict)
        and messages[0].get("role") == "system"
        and messages[1].get("role") == "user"
    )
    if lease is not None and lease.context is context and not lease.responses_disabled and clean_stage_dossier:
        previous_id = lease.previous_response_id
    request_payload = _responses_payload_from_chat(prepared, previous_id)
    candidates: list[tuple[str, dict[str, Any]]] = [("original", request_payload)]
    if request_payload.get("reasoning") is not None:
        reduced = dict(request_payload)
        reduced.pop("reasoning", None)
        candidates.append(("without_reasoning", reduced))
    if request_payload.get("text") is not None:
        reduced = dict(request_payload)
        reduced.pop("text", None)
        candidates.append(("without_text_format", reduced))
    if request_payload.get("reasoning") is not None and request_payload.get("text") is not None:
        reduced = dict(request_payload)
        reduced.pop("reasoning", None)
        reduced.pop("text", None)
        candidates.append(("without_reasoning_and_text_format", reduced))

    last_error: Exception | None = None
    for label, candidate in candidates:
        try:
            result = http_json(llm_responses_url(context), candidate, timeout=timeout, headers=llm_headers(context=context))
            if not isinstance(result, dict):
                raise RuntimeError("LLM Responses endpoint returned a non-object response")
            status = str(result.get("status") or "completed").lower()
            if status in {"failed", "cancelled", "incomplete"}:
                raise RuntimeError(f"LLM Responses request ended with status={status}")
            content = _responses_output_text(result)
            if not content:
                raise RuntimeError("LLM Responses endpoint returned no output text")
            response_id = str(result.get("id") or "")
            if lease is not None and lease.context is context:
                lease.previous_response_id = response_id
            usage = _usage_fields(result)
            return {
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": result.get("usage") or {},
                "_debug": {
                    "apiMode": "responses",
                    "requestMode": label,
                    "provider": active_llm_provider(context),
                    "profileId": context.get("profile_id"),
                    "responseId": response_id,
                    "previousResponseId": previous_id,
                    **usage,
                },
            }
        except urlerror.HTTPError as error:
            try:
                body = error.read().decode("utf-8", "replace")[:2000]
                setattr(error, "_infini_body", body)
            except Exception:
                pass
            last_error = error
            if error.code in {400, 422} and label != candidates[-1][0]:
                continue
            raise
        except Exception as error:
            last_error = error
            raise
    if last_error is not None:
        raise last_error
    raise RuntimeError("LLM Responses request failed without response")


def _record_llm_stage(payload: dict[str, Any]) -> str:
    stage = _llm_replay_stage_from_payload(payload)
    lease = _CURRENT_LLM_ITEM_LEASE.get()
    if lease is not None:
        lease.call_count += 1
        lease.stages.append(stage)
    return stage


def _llm_json_single_context(payload: dict[str, Any], timeout: int, context: dict[str, Any]) -> dict[str, Any]:
    stage = _record_llm_stage(payload)
    mode = _normalized_api_mode(context.get("api_mode"))
    capability_key = _llm_context_key(context)
    lease = _CURRENT_LLM_ITEM_LEASE.get()
    responses_allowed = mode in {"auto", "responses"}
    if _RESPONSES_CAPABILITY.get(capability_key) is False:
        responses_allowed = False
    if lease is not None and lease.context is context and lease.responses_disabled:
        responses_allowed = False
    if responses_allowed:
        try:
            result = _llm_responses_json_single_context(payload, timeout, context)
            _RESPONSES_CAPABILITY[capability_key] = True
            log_event("info", "LLM usage", {"stage": stage, **(result.get("_debug") or {})})
            return result
        except Exception as error:
            if _is_budget_or_auth_failure(error):
                raise
            had_working_chain = bool(lease is not None and lease.context is context and lease.previous_response_id)
            _RESPONSES_CAPABILITY[capability_key] = True if had_working_chain else False
            if lease is not None and lease.context is context:
                lease.responses_disabled = True
                lease.previous_response_id = ""
            log_event("warn", "LLM Responses unavailable; retrying same stage through stateless Chat Completions", {
                "stage": stage,
                "profileId": context.get("profile_id"),
                "provider": active_llm_provider(context),
                "error": repr(error),
            })
    result = _llm_chat_json_single_context(payload, timeout, context)
    if isinstance(result, dict):
        debug_raw = result.get("_debug")
        debug: dict[str, Any] = debug_raw if isinstance(debug_raw, dict) else {}
        result["_debug"] = {
            **debug,
            "apiMode": "chat_completions",
            "profileId": context.get("profile_id"),
            **_usage_fields(result),
        }
        log_event("info", "LLM usage", {"stage": stage, **result["_debug"]})
    return result


def _llm_chat_json_single_context(payload: dict[str, Any], timeout: int, context: dict[str, Any]) -> dict[str, Any]:
    ensure_llm_auth_configured(context)
    payload = _clean_llm_payload(payload)
    replay = _llm_replay_json_response(payload)
    if replay is not None:
        return replay
    payload = _payload_for_context(payload, context)
    url = llm_chat_completions_url(context)
    candidates: list[tuple[str, dict[str, Any]]] = [("original", payload)]
    reasoning_requested = payload.get("reasoning") is not None or payload.get("reasoning_effort") is not None
    if reasoning_requested:
        retry = dict(payload)
        retry.pop("reasoning", None)
        retry.pop("reasoning_effort", None)
        candidates.append(("without_reasoning", retry))
    if payload.get("response_format") is not None:
        retry = dict(payload)
        retry.pop("response_format", None)
        candidates.append(("without_response_format", retry))
    if reasoning_requested and payload.get("response_format") is not None:
        retry = dict(payload)
        retry.pop("reasoning", None)
        retry.pop("reasoning_effort", None)
        retry.pop("response_format", None)
        candidates.append(("without_reasoning_and_response_format", retry))

    last_error: Exception | None = None
    for label, candidate in candidates:
        try:
            if label != "original":
                log_event("warn", "retrying LLM request with reduced compatibility fields", {"provider": active_llm_provider(context), "mode": label, "label": context.get("label")})
            result = http_json(url, candidate, timeout=timeout, headers=llm_headers(context=context))
            choices = result.get("choices") if isinstance(result, dict) else None
            first_choice = choices[0] if isinstance(choices, list) and choices else None
            message = first_choice.get("message") if isinstance(first_choice, dict) else None
            if not isinstance(message, dict) or not isinstance(message.get("content"), str):
                raise RuntimeError("LLM provider returned an invalid Chat Completions envelope")
            debug_raw = result.get("_debug")
            debug: dict[str, Any] = debug_raw if isinstance(debug_raw, dict) else {}
            result["_debug"] = {
                **debug,
                "requestMode": label,
                "provider": active_llm_provider(context),
                "responseFormatRequested": bool(payload.get("response_format")),
                "responseFormatUsed": bool(candidate.get("response_format")),
                "reasoningRequested": bool(payload.get("reasoning") or payload.get("reasoning_effort")),
                "reasoningUsed": bool(candidate.get("reasoning") or candidate.get("reasoning_effort")),
                "reasoningEffort": candidate.get("reasoning_effort"),
            }
            return result
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

def _is_profile_failover_failure(error: Exception) -> bool:
    return (
        _is_budget_or_auth_failure(error)
        or _is_transport_error(error)
        or isinstance(error, (urlerror.HTTPError, RuntimeError, ValueError, KeyError, json.JSONDecodeError))
    )


def _mark_profile_failed(context: dict[str, Any], error: Exception) -> None:
    cooldown = max(1, int(LLM_POOL_FAILURE_COOLDOWN_SECONDS or 45))
    profile_id = _profile_id(context)
    with _LLM_POOL_LOCK:
        _PROFILE_COOLDOWN_UNTIL[profile_id] = time.monotonic() + cooldown
    log_event("warn", "LLM profile entered failure cooldown", {
        "profileId": profile_id,
        "provider": active_llm_provider(context),
        "model": context.get("model"),
        "cooldownSeconds": cooldown,
        "error": repr(error),
    })


def _next_lease_profile(lease: LlmItemLease, attempted: set[str]) -> dict[str, Any] | None:
    profiles = list(lease.profiles)
    if len(profiles) <= 1:
        return None
    current_id = lease.profile_id
    current_index = next((index for index, context in enumerate(profiles) if _profile_id(context) == current_id), 0)
    ordered = [profiles[(current_index + offset) % len(profiles)] for offset in range(1, len(profiles))]
    candidates = [context for context in ordered if _profile_id(context) not in attempted]
    available = [context for context in candidates if _profile_is_available(context)]
    selected = available[0] if available else (candidates[0] if candidates else None)
    return dict(selected) if isinstance(selected, dict) else None


def _switch_lease_profile(lease: LlmItemLease, context: dict[str, Any], error: Exception) -> None:
    previous_id = lease.profile_id
    next_id = _profile_id(context)
    lease.context = context
    lease.profile_id = next_id
    lease.previous_response_id = ""
    lease.responses_disabled = False
    lease.failovers.append({
        "fromProfileId": previous_id,
        "toProfileId": next_id,
        "reason": type(error).__name__,
    })
    log_event("warn", "LLM item lease switched to next profile", {
        "leaseId": lease.lease_id,
        "recipeKey": lease.recipe_key,
        "fromProfileId": previous_id,
        "toProfileId": next_id,
        "provider": active_llm_provider(context),
        "model": context.get("model"),
        "reason": repr(error),
    })


def _switch_lease_to_legacy_fallback(lease: LlmItemLease | None, fallback: dict[str, Any]) -> None:
    if lease is None:
        return
    lease.context = fallback
    lease.profile_id = str(fallback.get("profile_id") or "legacy_fallback")
    lease.previous_response_id = ""
    lease.responses_disabled = False


def llm_chat_json(payload: dict[str, Any], timeout: int = 10) -> dict[str, Any]:
    lease = _CURRENT_LLM_ITEM_LEASE.get()
    if lease is not None and lease.pool_size > 1:
        attempted: set[str] = set()
        while True:
            context = lease.context
            attempted.add(lease.profile_id)
            try:
                return _llm_json_single_context(payload, timeout, context)
            except Exception as profile_error:
                if not _is_profile_failover_failure(profile_error):
                    raise
                _mark_profile_failed(context, profile_error)
                next_context = _next_lease_profile(lease, attempted)
                if next_context is None:
                    raise
                _switch_lease_profile(lease, next_context, profile_error)

    primary = _primary_llm_context()
    fallback = _fallback_llm_context() if lease is None or lease.legacy_fallback_allowed else None
    try:
        return _llm_json_single_context(payload, timeout, primary)
    except Exception as first_error:
        if not fallback:
            raise
        if _is_budget_or_auth_failure(first_error):
            log_event("warn", "LLM primary failed; switching to fallback", {"reason": "budget_or_auth", "primaryProvider": active_llm_provider(primary), "primaryModel": primary.get("model"), "fallbackProvider": active_llm_provider(fallback), "fallbackModel": fallback.get("model")})
            _switch_lease_to_legacy_fallback(lease, fallback)
            return _llm_json_single_context(payload, timeout, fallback)
        if _is_transport_error(first_error):
            last_error = first_error
            total_attempts = max(2, int(LLM_FALLBACK_NETWORK_FAILS or 2))
            for attempt in range(2, total_attempts + 1):
                try:
                    log_event("warn", "retrying primary LLM transport before fallback", {"attempt": attempt, "maxAttempts": total_attempts, "provider": active_llm_provider(primary), "model": primary.get("model")})
                    return _llm_json_single_context(payload, timeout, primary)
                except Exception as retry_error:
                    last_error = retry_error
                    if _is_budget_or_auth_failure(retry_error):
                        log_event("warn", "LLM primary changed from transport failure to budget/auth failure; switching to fallback", {"provider": active_llm_provider(primary), "fallbackProvider": active_llm_provider(fallback), "fallbackModel": fallback.get("model")})
                        _switch_lease_to_legacy_fallback(lease, fallback)
                        return _llm_json_single_context(payload, timeout, fallback)
                    if not _is_transport_error(retry_error):
                        raise
            log_event("warn", "LLM primary transport failed repeatedly; switching to fallback", {"attempts": total_attempts, "primaryProvider": active_llm_provider(primary), "primaryModel": primary.get("model"), "fallbackProvider": active_llm_provider(fallback), "fallbackModel": fallback.get("model")})
            _switch_lease_to_legacy_fallback(lease, fallback)
            return _llm_json_single_context(payload, timeout, fallback)
        raise

__all__ = ['_normalized_llm_provider', 'active_llm_provider', '_llm_context_key', '_primary_llm_context', '_fallback_llm_context', '_join_openai_compat_url', 'llm_base_url', 'llm_chat_completions_url', 'llm_models_url', 'llm_auth_snapshot', 'ensure_llm_auth_configured', 'llm_headers', 'llm_json_response_format', 'llm_answer_max_tokens', 'visual_director_max_tokens', 'llm_reasoning_payload', 'llm_reasoning_system_suffix', 'apply_llm_common_options', 'http_get_json', 'resolve_llm_model', '_clean_llm_payload', 'http_json', '_llm_replay_stage_from_payload', '_replay_content_from_json_object', '_load_llm_replay_raw', '_llm_replay_json_response', '_llm_error_text', '_is_transport_error', '_is_budget_or_auth_failure', '_payload_for_context', '_llm_chat_json_single_context', 'llm_chat_json']
