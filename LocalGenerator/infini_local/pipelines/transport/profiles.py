"""Configured LLM profiles, item leases and profile health.

This owner selects profiles and mutates lease state. The request executor decides
when a failed HTTP attempt permits a retry or failover.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import threading
import time
from typing import Any

from infini_local.core import llm_config as config
from infini_local.core.env_utils import env_str
from infini_local.services.combine_endpoint import update_generation_activity
from infini_local.storage.trace_runtime import log_event


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
    initial_profile_id: str = ""
    profiles: tuple[dict[str, Any], ...] = ()
    legacy_fallback_allowed: bool = False
    previous_response_id: str = ""
    responses_disabled: bool = False
    call_count: int = 0
    stages: list[str] = field(default_factory=list)
    failovers: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.initial_profile_id:
            self.initial_profile_id = self.profile_id

    def snapshot(self) -> dict[str, Any]:
        return {
            "leaseId": self.lease_id,
            "initialProfileId": self.initial_profile_id,
            "profileId": self.profile_id,
            "provider": self.context.get("provider"),
            "baseUrl": self.context.get("base_url"),
            "model": self.context.get("model"),
            "apiMode": self.context.get("api_mode"),
            "openrouterProvider": _openrouter_provider(self.context),
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
        if not configured and config.OPENROUTER_API_KEY and config.OPENROUTER_MODEL and str(config.OPENROUTER_MODEL).lower() not in {"auto", "default"}:
            return "openrouter"
        return "local"
    return configured


def active_llm_provider(context: dict[str, Any] | None = None) -> str:
    if isinstance(context, dict) and context.get("provider"):
        return str(context.get("provider") or "local")
    lease = _CURRENT_LLM_ITEM_LEASE.get()
    if lease is not None and lease.context.get("provider"):
        return str(lease.context.get("provider") or "local")
    return _normalized_llm_provider(config.LLM_PROVIDER or "")


def _normalized_api_mode(value: Any) -> str:
    mode = str(value or "auto").strip().lower().replace("-", "_")
    if mode in {"responses", "response"}:
        return "responses"
    if mode in {"chat", "chat_completion", "chat_completions", "completions"}:
        return "chat_completions"
    return "auto"


def _openrouter_provider(context: dict[str, Any]) -> str:
    if active_llm_provider(context) != "openrouter":
        return ""
    return str(context.get("openrouter_provider") or "").strip()


def _llm_context_key(context: dict[str, Any] | None) -> str:
    ctx = context or {}
    key = "|".join([
        str(ctx.get("provider") or "local"),
        str(ctx.get("base_url") or ""),
        str(ctx.get("model") or "auto"),
        str(ctx.get("api_mode") or "chat_completions"),
    ])
    upstream = _openrouter_provider(ctx)
    return f"{key}|{upstream}" if upstream else key


def _legacy_primary_llm_context() -> dict[str, Any]:
    provider = _normalized_llm_provider(config.LLM_PROVIDER or "")
    if provider == "openai_codex":
        return {
            "provider": provider,
            "base_url": "https://chatgpt.com/backend-api/codex",
            "model": config.CODEX_LLM_MODEL,
            "api_key": "",
            "label": "llm_1",
            "profile_id": "llm_1",
            "api_mode": "responses",
        }
    if provider == "openrouter":
        return {
            "provider": provider,
            "base_url": config.OPENROUTER_BASE_URL or "https://openrouter.ai/api/v1",
            "model": config.OPENROUTER_MODEL or "auto",
            "openrouter_provider": config.OPENROUTER_PROVIDER,
            "api_key": config.OPENROUTER_API_KEY,
            "http_referer": config.OPENROUTER_HTTP_REFERER,
            "app_title": config.OPENROUTER_APP_TITLE,
            "label": "llm_1",
            "profile_id": "llm_1",
            "api_mode": _normalized_api_mode(config.LLM_API_MODE),
        }
    if provider == "openai_compat":
        return {
            "provider": provider,
            "base_url": config.OPENAI_COMPAT_BASE_URL or env_str("OPENAI_BASE_URL", "").rstrip("/"),
            "model": config.OPENAI_COMPAT_MODEL or "auto",
            "api_key": config.OPENAI_COMPAT_API_KEY,
            "label": "llm_1",
            "profile_id": "llm_1",
            "api_mode": _normalized_api_mode(config.LLM_API_MODE),
        }
    return {
        "provider": "local",
        "base_url": config.LMSTUDIO_URL,
        "model": config.LMSTUDIO_MODEL or "auto",
        "api_key": "",
        "label": "llm_1",
        "profile_id": "llm_1",
        "api_mode": _normalized_api_mode(config.LLM_API_MODE),
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
        base_url = base_url or config.OPENROUTER_BASE_URL or "https://openrouter.ai/api/v1"
        api_key = api_key or config.OPENROUTER_API_KEY
    elif provider == "local":
        base_url = base_url or config.LMSTUDIO_URL
        api_key = ""
    elif provider == "openai_codex":
        base_url = "https://chatgpt.com/backend-api/codex"
        api_key = ""
    else:
        provider = "openai_compat"
        base_url = base_url or config.OPENAI_COMPAT_BASE_URL or env_str("OPENAI_BASE_URL", "").rstrip("/")
        api_key = api_key or config.OPENAI_COMPAT_API_KEY
    profile_id = str(raw.get("id") or "llm_pool").strip()
    return {
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "label": profile_id,
        "profile_id": profile_id,
        "api_mode": "responses" if provider == "openai_codex" else _normalized_api_mode(raw.get("api_mode")),
        "http_referer": config.OPENROUTER_HTTP_REFERER if provider == "openrouter" else "",
        "app_title": config.OPENROUTER_APP_TITLE if provider == "openrouter" else "",
        "openrouter_provider": str(raw.get("openrouter_provider") or "").strip() if provider == "openrouter" else "",
    }


def configured_llm_pool() -> list[dict[str, Any]]:
    profiles = [_legacy_primary_llm_context()]
    seen_ids = {"llm_1"}
    for raw in config.LLM_POOL_PROFILES:
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


def begin_llm_item_lease(recipe_key: str, *, preferred_profile_id: str = "") -> tuple[LlmItemLease, Any]:
    global _LLM_POOL_CURSOR, _LLM_LEASE_SEQUENCE
    profiles = configured_llm_pool()
    preferred = str(preferred_profile_id or "").strip().lower()
    with _LLM_POOL_LOCK:
        if preferred:
            selected_index = next(
                (index for index, context in enumerate(profiles) if _profile_id(context).lower() == preferred),
                -1,
            )
            if selected_index < 0:
                from infini_local.core.errors import PlannerUnavailable
                error = PlannerUnavailable(f"Configured LLM profile {preferred!r} is unavailable for multi-dev lane")
                setattr(error, "_infini_transport_debug", {"failureCategory": "profile_unavailable", "networkStarted": False})
                raise error
        else:
            selected_index = _available_profile_index(profiles, _LLM_POOL_CURSOR % len(profiles))
            _LLM_POOL_CURSOR = (selected_index + 1) % len(profiles)
        selected = dict(profiles[selected_index])
        _LLM_LEASE_SEQUENCE += 1
        sequence = _LLM_LEASE_SEQUENCE
    profile_id = str(selected.get("profile_id") or selected.get("label") or "llm_1")
    pinned_profiles = (dict(selected),) if preferred else tuple(dict(profile) for profile in profiles)
    lease = LlmItemLease(
        recipe_key=str(recipe_key or ""),
        lease_id=f"{profile_id}:{sequence}",
        profile_id=profile_id,
        context=selected,
        pool_size=len(pinned_profiles),
        profiles=pinned_profiles,
        legacy_fallback_allowed=not preferred and len(profiles) == 1,
    )
    token = _CURRENT_LLM_ITEM_LEASE.set(lease)
    try:
        update_generation_activity(profile_id=profile_id)
        log_event("info", "LLM item lease acquired", lease.snapshot())
    except BaseException:
        _CURRENT_LLM_ITEM_LEASE.reset(token)
        raise
    return lease, token


def end_llm_item_lease(lease: LlmItemLease, token: Any) -> None:
    try:
        log_event("info", "LLM item lease released", lease.snapshot())
    finally:
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


def _fallback_llm_context() -> dict[str, Any] | None:
    model = str(config.LLM_FALLBACK_MODEL or "").strip()
    if not model:
        return None
    primary = _legacy_primary_llm_context()
    provider = _normalized_llm_provider(config.LLM_FALLBACK_PROVIDER or str(primary.get("provider") or "local"))
    ctx: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "label": "fallback",
        "profile_id": "legacy_fallback",
        "api_mode": "chat_completions",
    }
    if provider == "openrouter":
        ctx["base_url"] = config.LLM_FALLBACK_BASE_URL or config.OPENROUTER_BASE_URL or "https://openrouter.ai/api/v1"
        ctx["api_key"] = config.LLM_FALLBACK_API_KEY or config.OPENROUTER_API_KEY
        ctx["http_referer"] = config.OPENROUTER_HTTP_REFERER
        ctx["app_title"] = config.OPENROUTER_APP_TITLE
        ctx["openrouter_provider"] = config.LLM_FALLBACK_OPENROUTER_PROVIDER
    elif provider == "openai_compat":
        ctx["base_url"] = config.LLM_FALLBACK_BASE_URL or config.OPENAI_COMPAT_BASE_URL or env_str("OPENAI_BASE_URL", "").rstrip("/")
        ctx["api_key"] = config.LLM_FALLBACK_API_KEY or config.OPENAI_COMPAT_API_KEY
    elif provider == "openai_codex":
        ctx["base_url"] = "https://chatgpt.com/backend-api/codex"
        ctx["api_key"] = ""
        ctx["api_mode"] = "responses"
    else:
        ctx["provider"] = "local"
        ctx["base_url"] = config.LLM_FALLBACK_BASE_URL or config.LMSTUDIO_URL
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
    if active_llm_provider(context or _primary_llm_context()) == "openai_codex":
        from infini_local.services.codex_auth import CodexError
        raise CodexError("Codex subscription does not support chat/completions")
    return _join_openai_compat_url(llm_base_url(context), "/chat/completions")


def llm_responses_url(context: dict[str, Any] | None = None) -> str:
    if active_llm_provider(context or _primary_llm_context()) == "openai_codex":
        from infini_local.services.codex_text_backend import RESPONSES_URL
        return RESPONSES_URL
    return _join_openai_compat_url(llm_base_url(context), "/responses")


def llm_models_url(context: dict[str, Any] | None = None) -> str:
    if active_llm_provider(context or _primary_llm_context()) == "openai_codex":
        from infini_local.services.codex_catalog import CLIENT_VERSION, MODELS_URL
        return f"{MODELS_URL}?client_version={CLIENT_VERSION}"
    return _join_openai_compat_url(llm_base_url(context), "/models")


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


def _mark_profile_failed(context: dict[str, Any], error: Exception) -> None:
    cooldown = max(1, int(config.LLM_POOL_FAILURE_COOLDOWN_SECONDS or 45))
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
    # A strict upstream selection may retry in place, never leave its profile.
    if _openrouter_provider(lease.context):
        return None
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
    update_generation_activity(profile_id=next_id)
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
