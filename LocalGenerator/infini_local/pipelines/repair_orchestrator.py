from __future__ import annotations

"""Structural repair + targeted retry boundary orchestration seam."""

from typing import Any

from infini_local.core.result_models import RepairResult
from infini_local.pipelines.combine_pipeline import (
    canonical_for_result,
    merge_genome_repair,
    repair_llm_combat_genome_if_needed,
    repair_name_if_needed,
    try_llm_genome_repair,
    try_llm_name_repair,
    validate_and_repair,
)

_ALLOWED_PATCH_FIELDS = {
    "runtimePlan",
    "attack",
    "gameplay",
    "debug",
}

_REJECTED_AUTHOR_FIELDS = {
    "name",
    "displayName",
    "description",
    "lore",
    "visual",
    "visualPrompt",
    "parents",
    "category",
    "tags",
}


def reduce_targeted_repair_patch(raw_patch: Any) -> tuple[dict[str, Any], list[str]]:
    """Reduce repair-LLM output to executable patch fields only.

    A repair response may accidentally include a whole item. This boundary keeps
    prose/identity/category from becoming a second authoring pass.
    """
    if not isinstance(raw_patch, dict):
        return {}, []
    patch = raw_patch.get("repairPatch") if isinstance(raw_patch.get("repairPatch"), dict) else raw_patch
    out: dict[str, Any] = {}
    rejected: list[str] = []
    for key, value in patch.items():
        if key in _ALLOWED_PATCH_FIELDS:
            out[key] = value
        elif key in _REJECTED_AUTHOR_FIELDS or key not in _ALLOWED_PATCH_FIELDS:
            rejected.append(str(key))
    return out, sorted(set(rejected))


def repair_result_from_boundary(
    *,
    kind: str,
    code_repaired: bool = False,
    retry_attempted: bool = False,
    retry_accepted: bool = False,
    raw_patch: Any = None,
    fatal: str = "",
) -> RepairResult:
    patch, rejected = reduce_targeted_repair_patch(raw_patch or {})
    return RepairResult(
        kind=kind,
        code_repaired=code_repaired,
        retry_attempted=retry_attempted,
        retry_accepted=retry_accepted,
        patch=patch,
        rejected_fields=rejected,
        fatal=fatal,
    )


__all__ = [
    "validate_and_repair",
    "merge_genome_repair",
    "try_llm_genome_repair",
    "repair_llm_combat_genome_if_needed",
    "repair_name_if_needed",
    "try_llm_name_repair",
    "canonical_for_result",
    "reduce_targeted_repair_patch",
    "repair_result_from_boundary",
]
