from __future__ import annotations


# AGENT MAP: final recipe normalization seam before delivery/cache.
# Use this layer to make emitted data consistent and debuggable, not to invent new
# mechanics after runtimePlan validation. If a value affects C# runtime, it must be
# explicit, tested and documented.
"""Final normalization seam for generated item JSON.

The legacy final_normalize() public entry remains in pipeline_support for
compatibility. The helper below is a pure minimal normalizer for tests/debug
callers that need no monolith.
"""

from typing import Any, Callable

from infini_local.pipelines.pipeline_support import final_normalize


def normalize_generated_item_json(data: dict[str, Any], *, normalize_category: Callable[[Any], str] | None = None) -> dict[str, Any]:
    out = dict(data)
    if normalize_category is not None:
        out["category"] = normalize_category(out.get("category"))
        gp = out.get("gameplay") if isinstance(out.get("gameplay"), dict) else None
        if gp is not None and gp.get("kind"):
            gp["kind"] = normalize_category(gp.get("kind"))
    out.setdefault("debug", {})
    out.setdefault("recipeMeta", {})
    return out


__all__ = ["final_normalize", "normalize_generated_item_json"]
