"""Account-scoped Codex text catalog; image generation exposes no model-list API."""
from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlencode

from infini_local.services import codex_auth

MODELS_URL = "https://chatgpt.com/backend-api/codex/models"
# This is the Codex protocol client version, not the InfiniCrafter app version.
# The subscription catalog filters by minimum client version: sending 0.4.241
# returned zero models while the pinned upstream Codex release exposed them.
CLIENT_VERSION = "0.156.1"
_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")


@dataclass(frozen=True)
class CodexModel:
    slug: str
    label: str
    efforts: tuple[str, ...]
    default_effort: str
    priority: int


def list_text_models() -> list[CodexModel]:
    """Fetch current account's visible *text* models, never Platform's catalog."""
    credentials = codex_auth.get_credentials()
    secrets = tuple(secret for secret in (credentials.access_token, credentials.refresh_token, credentials.account_id)
                    if len(secret) >= 8)
    def safe_metadata(value: str) -> bool:
        decoded = codex_auth._decode_unicode_runs(value)
        return not any(secret in decoded for secret in secrets)
    url = MODELS_URL + "?" + urlencode({"client_version": CLIENT_VERSION})
    result = codex_auth.get_json(url, headers={
        "Authorization": "Bearer " + credentials.access_token,
        "ChatGPT-Account-Id": credentials.account_id,
        "Accept": "application/json",
    }, timeout=8, limit=2 * 1024 * 1024)
    raw = result.get("models")
    if not isinstance(raw, list):
        raise codex_auth.CodexError("Codex text model catalog has an invalid shape")
    models: list[CodexModel] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or item.get("visibility") != "list":
            continue
        slug = item.get("slug")
        if not isinstance(slug, str) or not _MODEL_ID.fullmatch(slug) or not safe_metadata(slug) or slug in seen:
            continue
        seen.add(slug)
        title = item.get("display_name")
        title = title.strip() if isinstance(title, str) and safe_metadata(title) else ""
        raw_levels = item.get("supported_reasoning_levels")
        levels: list[str] = []
        if isinstance(raw_levels, list):
            for entry in raw_levels:
                effort = entry.get("effort") if isinstance(entry, dict) else None
                if isinstance(effort, str) and _MODEL_ID.fullmatch(effort) and safe_metadata(effort) and effort not in levels:
                    levels.append(effort)
        default = item.get("default_reasoning_level")
        default = default if isinstance(default, str) and default in levels else ""
        priority = item.get("priority")
        priority = priority if isinstance(priority, int) and not isinstance(priority, bool) else 999
        models.append(CodexModel(slug, title or slug, tuple(levels), default, priority))
    models.sort(key=lambda model: (model.priority, model.slug))
    if not models:
        raise codex_auth.CodexError("Codex returned no visible text models for this account")
    return models
