from __future__ import annotations

import json
from typing import Any

from infini_local.pipelines.item_rarity_baseline import (
    MODDED_HIGH_TIERS,
    TIER_DEFAULT_POWER,
)
from infini_local.pipelines.result_identity_policy import normalize_category


# AGENT MAP: generated result knowledge-card seam for combine_pipeline.
# Owns the compact resultCard attached after runtime stats are known.
# Callers import this owner directly; combine_pipeline only invokes the attach step.

def build_result_item_card(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    gp = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    k = data.get("itemKnowledge") if isinstance(data.get("itemKnowledge"), dict) else {}
    tags = set(str(t).lower() for t in data.get("tags", []) if str(t).strip())
    stage_tier = str(gp.get("stage") or "unknown")
    strongest_tier = str(k.get("strongestTier") or "unknown")
    try:
        parent_power = float(k.get("strongestPowerScore") or 0)
    except Exception:
        parent_power = 0.0
    stage_power = float(TIER_DEFAULT_POWER.get(stage_tier, 0))
    strongest_tier_power = float(TIER_DEFAULT_POWER.get(strongest_tier, 0))
    transfer = gp.get("powerTransfer") if isinstance(gp.get("powerTransfer"), dict) else {}
    # Keep Calamity/custom parent tiers visible, but distinguish full transfer from weak-anchor influence.
    tier = str(transfer.get("resultTier") or (strongest_tier if strongest_tier_power > stage_power * 1.08 else stage_tier))
    try:
        budget_power = float(gp.get("powerBudget") or 1.0) * 55.0
    except Exception:
        budget_power = 55.0
    try:
        damage_power = float(gp.get("damage") or 0) * 1.05
    except Exception:
        damage_power = 0.0
    depth = int((data.get("recipeMeta") or {}).get("generationDepth") or 1)
    transfer_power = float(transfer.get("resultPowerScore") or 0.0)
    transfer_quality = str(transfer.get("quality") or "")
    diluted_transfer = transfer_quality in {"diluted_weak_anchor", "asymmetric"} or str(tier).endswith("_influenced")
    parent_factor = 0.38 if diluted_transfer else 0.82
    budget_factor = 0.82 if diluted_transfer else 1.0
    if depth > 1:
        # powerBudget prices active behavior/complexity; do not let recursive generated parents
        # become stronger tier anchors solely because they have projectiles, split, VFX or uptime.
        budget_factor = min(budget_factor, 0.58)
    power = max(transfer_power, parent_power * parent_factor, budget_power * budget_factor, damage_power) + min(20.0, depth * 2.0)
    if tier not in MODDED_HIGH_TIERS and not str(tier).endswith("_influenced"):
        stage_soft_ceiling = max(
            stage_power * (1.55 if depth <= 1 else 1.35),
            transfer_power * 1.12,
            damage_power * (2.35 if depth <= 1 else 2.05),
            parent_power * parent_factor + 14.0,
        ) + min(14.0, depth * 1.75)
        power = min(power, max(stage_soft_ceiling, damage_power, transfer_power, stage_power))
    if data.get("category") in {"material", "generic"} and damage_power <= 0:
        # Materials/generic results preserve tier influence, but weak-anchor recipes should not become full Calamity-tier gear.
        if transfer_power > 0:
            power = max(power, transfer_power)
        else:
            power = max(power, parent_power * (0.42 if diluted_transfer else 0.72))
    return {
        "name": str(data.get("name") or "Generated Item"),
        "identity": "generated:" + str(data.get("id") or ""),
        "category": normalize_category(str(data.get("category") or gp.get("kind") or "generic")),
        "tier": tier,
        "powerScore": round(max(1.0, power), 2),
        "confidence": 0.74,
        "sourceHint": "generated result card from gameplay + parent knowledge",
        "tags": sorted(tags),
        "generatedDepth": depth,
        "signals": {
            "parentStrongestPower": parent_power,
            "gameplayBudgetPower": round(budget_power, 2),
            "damagePower": round(damage_power, 2),
            "basis": "result_card",
            "powerTransfer": transfer,
        },
    }

def attach_result_knowledge_card(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    k = data.setdefault("itemKnowledge", {})
    if not isinstance(k, dict):
        k = {}
        data["itemKnowledge"] = k
    k["resultCard"] = build_result_item_card(data, a, b)
    data.setdefault("debug", {})["resultKnowledgeCard"] = json.dumps(k["resultCard"], ensure_ascii=False)
    return data

__all__ = [
    "build_result_item_card",
    "attach_result_knowledge_card",
]
