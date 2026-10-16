from __future__ import annotations

from typing import Any

from infini_local.core.runtime_authoring.program_schema import ITEM_NAME_MAX_LENGTH

from infini_local.pipelines.pipeline_runtime_constants import BAD_NAME_PATTERNS

from infini_local.core.item_identity_tools import name_of


# Final display-name sanity only; category and mechanics remain Author-owned.


def bad_result_name(name: Any, a: dict[str, Any] | None = None, b: dict[str, Any] | None = None) -> bool:
    n = str(name or "").strip()
    if len(n) < 3 or len(n) > ITEM_NAME_MAX_LENGTH:
        return True
    if any(p.search(n) for p in BAD_NAME_PATTERNS):
        return True
    low = n.lower().strip()
    parent_names = {name_of(x).lower().strip() for x in (a or {}, b or {}) if isinstance(x, dict)}
    if low in parent_names:
        return True
    if low in {"item", "generated item", "unknown", "thing", "object"}:
        return True
    return False


__all__ = ["bad_result_name"]
