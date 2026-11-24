"""Private, exact-scope receipts for proven transport fallbacks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import Lock
from typing import Any

from infini_local.core import config_bootstrap as bootstrap
from infini_local.core import llm_config as config
from infini_local.core.env_utils import skip_config_file
from infini_local.core.llm_negotiation_notice import safe_notices
from infini_local.pipelines.transport import profiles

_lock = Lock()
_next = 0
_notices: dict[tuple[str, str, str], tuple[int, dict[str, Any]]] = {}


def _configuration_is_current() -> bool:
    if skip_config_file() or not bootstrap.CONFIG_LOADED_SHA256:
        return False
    try:
        return hashlib.sha256(bootstrap.CONFIG_PATH.read_bytes()).hexdigest() == bootstrap.CONFIG_LOADED_SHA256
    except OSError:
        return False


def model_is_pinned(context: dict[str, Any]) -> bool:
    return str(context.get("model") or "").strip().lower() not in {"", "auto", "default", "local-model", "local_model", "openrouter/auto"}


def reusable_in_memory() -> bool:
    # Process-only configurations retain the existing negotiation cache.
    # A configured file that changed on disk must not reuse its old answers.
    return not bootstrap.CONFIG_LOADED_SHA256 or _configuration_is_current()


def _receipt(kind: str, key: str, context: dict[str, Any]) -> Path | None:
    if not model_is_pinned(context) or not _configuration_is_current():
        return None
    # Secrets and URLs never enter the receipt payload or diagnostics. The
    # cache key already separates accounts; hash the full owner tuple again.
    binding = [bootstrap.CONFIG_LOADED_SHA256, str(bootstrap.CONFIG_PATH.resolve()), kind, key,
               context.get("profile_id"), context.get("api_mode"), config.LLM_RESPONSE_FORMAT_MODE]
    digest = hashlib.sha256(json.dumps(binding, separators=(",", ":")).encode()).hexdigest()
    return bootstrap.CACHE_DIR / "llm-negotiation-v1" / f"{digest}.json"


def confirmed(kind: str, key: str, context: dict[str, Any]) -> bool:
    path = _receipt(kind, key, context)
    if path is None:
        return False
    try:
        with path.open("rb") as fd:
            return json.loads(fd.read(128)) == {"version": 1, "kind": kind} and _configuration_is_current()
    except (OSError, ValueError):
        return False


def persist(kind: str, key: str, context: dict[str, Any]) -> bool:
    path = _receipt(kind, key, context)
    if path is None:
        return False
    from infini_local.storage.world_storage import atomic_write_json
    try:
        atomic_write_json(path, {"version": 1, "kind": kind})
    except OSError:
        return False
    # If a settings save raced the independent publication, its new bytes
    # do not match the old key; neither report nor apply the stale override.
    return _configuration_is_current()


def _update(identity: tuple[str, str, str], serial: int | None, state: str) -> int:
    global _next
    kind, profile, scope = identity
    with _lock:
        if serial is None:
            _next += 1
            serial = _next
        previous = _notices.get(identity)
        if state == "saved_reused" and previous is not None and previous[1]["state"] == "saved":
            # A fast next stage must not hide the newly saved outcome from
            # the slower, independently polled Studio health view.
            return serial
        if previous is None or previous[0] <= serial:
            _notices.pop(identity, None)
            _notices[identity] = (serial, {"kind": kind, "profile": profile, "scope": scope, "state": state})
            if len(_notices) > 24:
                _notices.pop(next(iter(_notices)))
        return serial


def begin(kind: str, context: dict[str, Any], scope: str) -> tuple[tuple[str, str, str], int]:
    identity = (kind, profiles._profile_id(context), scope)
    return identity, _update(identity, None, "rejected")


def finish(attempt: tuple[tuple[str, str, str], int], state: str) -> None:
    _update(*attempt, state)


def reused(kind: str, context: dict[str, Any], scope: str) -> None:
    identity = (kind, profiles._profile_id(context), scope)
    _update(identity, None, "saved_reused")



def snapshot() -> list[dict[str, str]]:
    with _lock:
        rows = [row.copy() for _, row in _notices.values()]
    if not _configuration_is_current():
        rows = [row for row in rows if row["state"] != "saved_reused"]
        for row in rows:
            if row["state"] == "saved":
                row["state"] = "saved_inactive"
    return safe_notices(rows)
