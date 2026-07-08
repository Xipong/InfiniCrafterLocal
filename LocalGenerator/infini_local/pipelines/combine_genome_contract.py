from __future__ import annotations

from typing import Any

from infini_local.pipelines.result_identity_policy import normalize_category
from infini_local.pipelines.pipeline_support import COMBAT_CATEGORIES


def is_llm_planner(data: dict[str, Any]) -> bool:
    debug = data.get("debug") if isinstance(data.get("debug"), dict) else {}
    planner = str(debug.get("planner") or "").lower()
    return planner == "llm" or planner.startswith("llm_") or "llm" in planner


def combat_genome_required_for(data: dict[str, Any]) -> bool:
    """Return True when an LLM result needs an executable combat genome."""
    if not is_llm_planner(data):
        return False
    category = normalize_category(data.get("category", "generic"))
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    kind = normalize_category(gameplay.get("kind", category))
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    return category in COMBAT_CATEGORIES or kind in COMBAT_CATEGORIES or bool(attack.get("enabled"))


__all__ = ["is_llm_planner", "combat_genome_required_for"]
