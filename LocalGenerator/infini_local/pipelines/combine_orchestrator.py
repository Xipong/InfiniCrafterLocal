from __future__ import annotations

"""High-level combine orchestration without web/HTTP details."""

from dataclasses import dataclass, field
from typing import Any, Callable

from infini_local.core.env_utils import env_str
from infini_local.pipelines.combine_pipeline import combine, combine_cache_lookup


@dataclass(slots=True)
class CombineOrchestrationContext:
    recipe_key: str
    world_id: str = ""
    world_name: str = ""
    pipeline_log: list[dict[str, Any]] = field(default_factory=list)


def run_combine_orchestration(payload: dict[str, Any], combine_fn: Callable[[dict[str, Any]], dict[str, Any]] = combine) -> dict[str, Any]:
    """HTTP-free orchestration seam for tests and future refactors."""
    return combine_fn(payload)


def multipass_authoring_mode() -> str:
    return env_str("INFINI_MULTIPASS_AUTHORING", "").strip().lower()


def build_multipass_debug_report(single_pass_item: dict[str, Any]) -> dict[str, Any]:
    """Debug-only multipass status report; never applies fragments to gameplay."""
    return {
        "mode": multipass_authoring_mode(),
        "applied": False,
        "reason": "single-pass remains authoritative until multipass has a real validated merge path",
        "singlePassCategory": single_pass_item.get("category"),
        "singlePassHasRuntimePlan": bool(single_pass_item.get("runtimePlan")),
        "fragments": [],
        "validation": {"ok": True, "mainPathUnchanged": True},
    }


__all__ = [
    "combine",
    "combine_cache_lookup",
    "CombineOrchestrationContext",
    "run_combine_orchestration",
    "multipass_authoring_mode",
    "build_multipass_debug_report",
]
