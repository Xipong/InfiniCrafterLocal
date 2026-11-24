"""Bounded public transport receipt vocabulary; no runtime bootstrap."""
from typing import Any

KINDS = frozenset({"responses_to_chat", "schema_to_object"})
STATES = frozenset({"rejected", "recovery_failed", "recovered_not_saved", "saved", "saved_reused", "saved_inactive"})
PROFILE_IDS = frozenset({"llm_1", "llm_2", "llm_3", "llm_4"})
SCOPES = frozenset({"profile", "schema", "attempt"})

def safe_notices(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    result = []
    for row in raw[-24:]:
        if not isinstance(row, dict):
            continue
        if all(isinstance(row.get(name), str) and row[name] in domain
               for name, domain in (("kind", KINDS), ("profile", PROFILE_IDS), ("scope", SCOPES), ("state", STATES))):
            result.append({name: row[name] for name in ("kind", "profile", "scope", "state")})
    return result

