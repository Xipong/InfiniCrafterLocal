from __future__ import annotations

from typing import Any

from infini_local.core.result_models import ClampRecord


# AGENT MAP: generated equipment stat budgets for combine_pipeline.
# Owns accessory/armor stat generation and soft total-stat budget clamps.
# Callers import this owner directly.

_ACCESSORY_COST_WEIGHTS: dict[str, float] = {
    "genericDamage": 42.0,
    "meleeDamage": 42.0,
    "rangedDamage": 42.0,
    "magicDamage": 42.0,
    "summonDamage": 42.0,
    "genericCrit": 0.75,
    "attackSpeed": 38.0,
    "knockback": 8.0,
    "movementSpeed": 18.0,
    "maxRunSpeed": 14.0,
    "jumpSpeed": 16.0,
    "endurance": 115.0,
    "manaCostReduction": 62.0,
    "ammoSaveChance": 62.0,
    "armorPenetration": 1.05,
    "aggro": 0.12,
    "defense": 0.95,
    "maxLife": 0.08,
    "maxMana": 0.055,
    "lifeRegen": 1.6,
    "manaRegen": 1.35,
    "minionSlots": 12.0,
    "sentrySlots": 12.0,
    "lightStrength": 2.0,
}

_ARMOR_PIECE_COST_WEIGHTS: dict[str, float] = {
    "defense": 0.92,
    "genericDamage": 38.0,
    "meleeDamage": 38.0,
    "rangedDamage": 38.0,
    "magicDamage": 38.0,
    "summonDamage": 38.0,
    "genericCrit": 0.62,
    "attackSpeed": 34.0,
    "knockback": 7.0,
    "movementSpeed": 14.0,
    "maxRunSpeed": 12.0,
    "jumpSpeed": 12.0,
    "endurance": 110.0,
    "manaCostReduction": 54.0,
    "ammoSaveChance": 54.0,
    "armorPenetration": 0.95,
    "maxLife": 0.075,
    "maxMana": 0.052,
    "lifeRegen": 1.45,
    "manaRegen": 1.2,
    "minionSlots": 11.0,
    "sentrySlots": 11.0,
    "lightStrength": 1.8,
}

_SET_BONUS_COST_WEIGHTS: dict[str, float] = {
    "setBonusGenericDamage": 48.0,
    "setBonusMeleeDamage": 48.0,
    "setBonusRangedDamage": 48.0,
    "setBonusMagicDamage": 48.0,
    "setBonusSummonDamage": 48.0,
    "setBonusGenericCrit": 0.8,
    "setBonusMovementSpeed": 20.0,
    "setBonusLifeRegen": 1.8,
    "setBonusManaRegen": 1.45,
    "setBonusMinionSlots": 13.0,
    "setBonusSentrySlots": 13.0,
    "setBonusEndurance": 125.0,
    "setBonusArmorPenetration": 1.08,
}

_ACCESSORY_BOOLEAN_COSTS: dict[str, float] = {
    "fallDamageImmune": 1.0,
    "waterWalk": 1.15,
    "lavaImmune": 5.5,
}

_ARMOR_BOOLEAN_COSTS: dict[str, float] = {
    "fallDamageImmune": 1.0,
    "waterWalk": 1.0,
    "lavaImmune": 4.75,
}

def _equipment_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def _equipment_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default

def _equipment_budget_base(stage: dict[str, Any], *, kind: str, slot: str = "", set_bonus: bool = False) -> float:
    power = max(1.0, min(7.5, _equipment_float(stage.get("powerBudget"), 1.0)))
    rarity = max(0, min(12, _equipment_int(stage.get("rarity"), 0)))
    depths = stage.get("parentGeneratedDepths") if isinstance(stage.get("parentGeneratedDepths"), list) else []
    depth_bonus = min(4.0, max((_equipment_int(x, 0) for x in depths), default=0) * 0.8)
    if kind == "accessory":
        return 18.0 + power * 8.2 + rarity * 1.45 + depth_bonus
    if set_bonus:
        return 16.0 + power * 7.0 + rarity * 1.35 + depth_bonus
    slot_factor = {"head": 0.92, "body": 1.12, "legs": 1.0}.get(slot, 1.0)
    return (20.0 + power * 8.8 + rarity * 1.55 + depth_bonus) * slot_factor

def _equipment_cost(stats: dict[str, Any], weights: dict[str, float], booleans: dict[str, float] | None = None) -> tuple[float, list[str]]:
    cost = 0.0
    active: list[str] = []
    for field, weight in weights.items():
        value = stats.get(field)
        amount = abs(_equipment_float(value, 0.0))
        if amount > 0:
            cost += amount * weight
            active.append(field)
    for field, weight in (booleans or {}).items():
        if bool(stats.get(field)):
            cost += weight
            active.append(field)
    return cost, active

def _scale_equipment_fields(stats: dict[str, Any], fields: list[str], scale: float, reason: str, source: str) -> list[dict[str, Any]]:
    clamps: list[dict[str, Any]] = []
    for field in fields:
        raw = stats.get(field)
        if isinstance(raw, bool) or raw in (None, "", 0, 0.0):
            continue
        if isinstance(raw, int) and not isinstance(raw, bool):
            final: Any = int(round(float(raw) * scale))
            if raw > 0:
                final = max(0, final)
            elif raw < 0:
                final = min(0, final)
        else:
            final = round(float(raw) * scale, 3)
        if final != raw:
            stats[field] = final
            clamps.append(ClampRecord(field=field, raw=raw, final=final, kind="balance", reason=reason, source=source).to_dict())
    return clamps

def apply_accessory_soft_budget(stats: dict[str, Any], stage: dict[str, Any], *, apply_clamps: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    """Soft total-stat budget for accessories; no prompt-word routing."""
    acc = dict(stats)
    budget = _equipment_budget_base(stage, kind="accessory")
    raw_cost, active = _equipment_cost(acc, _ACCESSORY_COST_WEIGHTS, _ACCESSORY_BOOLEAN_COSTS)
    reasons: list[str] = []
    if raw_cost > budget:
        reasons.append("total_stat_budget")
    if _equipment_float(acc.get("endurance"), 0.0) > 0.0 and raw_cost > budget * 0.72:
        reasons.append("endurance_pressure")
    if len(active) >= 7 and raw_cost > budget * 0.86:
        reasons.append("all_in_one_accessory")
    scale = 1.0 if raw_cost <= budget or raw_cost <= 0 else max(0.18, min(1.0, budget / raw_cost))
    clamps: list[dict[str, Any]] = []
    if scale < 0.999:
        clamps.extend(_scale_equipment_fields(acc, list(_ACCESSORY_COST_WEIGHTS), scale, "total_stat_budget", "accessory_soft_budget"))
        # High-cost binary immunities are bounded only when the item is trying to do everything.
        if "all_in_one_accessory" in reasons and bool(acc.get("lavaImmune")) and raw_cost > budget * 1.25:
            raw = acc.get("lavaImmune")
            acc["lavaImmune"] = False
            clamps.append(ClampRecord(field="lavaImmune", raw=raw, final=False, kind="balance", reason="all_in_one_accessory", source="accessory_soft_budget").to_dict())
    suggested_clamps = list(clamps)
    if not apply_clamps:
        acc = dict(stats)
        clamps = []
    final_cost, final_active = _equipment_cost(acc, _ACCESSORY_COST_WEIGHTS, _ACCESSORY_BOOLEAN_COSTS)
    report = {
        "schema": "infini.equipment-budget.v1",
        "kind": "accessory",
        "budget": round(budget, 3),
        "rawCost": round(raw_cost, 3),
        "finalCost": round(final_cost, 3),
        "scale": round(scale, 4),
        "activeFields": active[:24],
        "finalActiveFields": final_active[:24],
        "reasons": sorted(set(reasons)),
        "applied": bool(apply_clamps),
        "clamps": clamps,
        "suggestedClamps": [] if apply_clamps else suggested_clamps,
    }
    return acc, report

def apply_armor_soft_budget(stats: dict[str, Any], stage: dict[str, Any], slot: str, *, apply_clamps: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    """Soft total-stat budget for armor piece + separate set bonus budget."""
    armor = dict(stats)
    piece_budget = _equipment_budget_base(stage, kind="armor", slot=slot)
    set_budget = _equipment_budget_base(stage, kind="armor", slot=slot, set_bonus=True)
    piece_cost, piece_active = _equipment_cost(armor, _ARMOR_PIECE_COST_WEIGHTS, _ARMOR_BOOLEAN_COSTS)
    set_cost, set_active = _equipment_cost(armor, _SET_BONUS_COST_WEIGHTS, {})
    reasons: list[str] = []
    clamps: list[dict[str, Any]] = []
    piece_scale = 1.0 if piece_cost <= piece_budget or piece_cost <= 0 else max(0.2, min(1.0, piece_budget / piece_cost))
    set_scale = 1.0 if set_cost <= set_budget or set_cost <= 0 else max(0.2, min(1.0, set_budget / set_cost))
    if piece_scale < 0.999:
        reasons.append("total_stat_budget")
        if _equipment_float(armor.get("endurance"), 0.0) > 0.0:
            reasons.append("endurance_pressure")
        clamps.extend(_scale_equipment_fields(armor, list(_ARMOR_PIECE_COST_WEIGHTS), piece_scale, "total_stat_budget", "armor_soft_budget"))
    if set_scale < 0.999:
        reasons.append("set_bonus_pressure")
        clamps.extend(_scale_equipment_fields(armor, list(_SET_BONUS_COST_WEIGHTS), set_scale, "set_bonus_pressure", "armor_soft_budget"))
    suggested_clamps = list(clamps)
    if not apply_clamps:
        armor = dict(stats)
        clamps = []
    final_piece_cost, final_piece_active = _equipment_cost(armor, _ARMOR_PIECE_COST_WEIGHTS, _ARMOR_BOOLEAN_COSTS)
    final_set_cost, final_set_active = _equipment_cost(armor, _SET_BONUS_COST_WEIGHTS, {})
    report = {
        "schema": "infini.equipment-budget.v1",
        "kind": "armor",
        "slot": slot,
        "pieceBudget": round(piece_budget, 3),
        "setBonusBudget": round(set_budget, 3),
        "rawPieceCost": round(piece_cost, 3),
        "rawSetBonusCost": round(set_cost, 3),
        "finalPieceCost": round(final_piece_cost, 3),
        "finalSetBonusCost": round(final_set_cost, 3),
        "pieceScale": round(piece_scale, 4),
        "setBonusScale": round(set_scale, 4),
        "pieceActiveFields": piece_active[:24],
        "setBonusActiveFields": set_active[:24],
        "finalPieceActiveFields": final_piece_active[:24],
        "finalSetBonusActiveFields": final_set_active[:24],
        "reasons": sorted(set(reasons)),
        "applied": bool(apply_clamps),
        "clamps": clamps,
        "suggestedClamps": [] if apply_clamps else suggested_clamps,
    }
    return armor, report

def accessory_stats_for(tags: set[str], stage: dict[str, Any]) -> dict[str, Any]:
    power = float(stage.get("powerBudget", 1.0))
    rarity = int(stage.get("rarity", 0))
    stats: dict[str, Any] = {
        "enabled": True,
        "archetype": "hybrid",
        "defense": 0,
        "maxLife": 0,
        "maxMana": 0,
        "lifeRegen": 0,
        "manaRegen": 0,
        "movementSpeed": 0.0,
        "maxRunSpeed": 0.0,
        "jumpSpeed": 0.0,
        "genericDamage": 0.0,
        "meleeDamage": 0.0,
        "rangedDamage": 0.0,
        "magicDamage": 0.0,
        "summonDamage": 0.0,
        "genericCrit": 0.0,
        "attackSpeed": 0.0,
        "knockback": 0.0,
        "fallDamageImmune": False,
        "lavaImmune": False,
        "waterWalk": False,
        "minionSlots": 0,
    }
    if tags & {"boots", "wings", "mobility", "aglet", "anklet", "balloon", "horseshoe"}:
        stats["archetype"] = "mobility"
        stats["movementSpeed"] = round(0.05 + min(power, 5.0) * 0.028, 3)
        stats["maxRunSpeed"] = round(0.06 + min(power, 5.0) * 0.045, 3)
        if tags & {"wings", "balloon", "horseshoe"}:
            stats["jumpSpeed"] = round(0.05 + min(power, 4.5) * 0.028, 3)
            stats["fallDamageImmune"] = True
    if tags & {"shield", "defense", "guard", "armor"}:
        stats["archetype"] = "defense" if stats["archetype"] == "hybrid" else "hybrid"
        stats["defense"] = max(stats["defense"], max(1, int(2 + power * 1.25 + rarity * 0.55)))
        if power >= 2.0:
            stats["maxLife"] = 20
    if tags & {"emblem", "charm", "ring", "band", "amulet", "weapon", "damage"}:
        stats["archetype"] = "damage" if stats["archetype"] == "hybrid" else "hybrid"
        dmg = round(0.035 + min(power, 5.2) * 0.024, 3)
        if "melee" in tags or "sword" in tags or "glove" in tags:
            stats["meleeDamage"] = dmg
            stats["attackSpeed"] = round(min(0.18, dmg * 0.9), 3)
        elif "ranged" in tags or "gun" in tags or "bow" in tags:
            stats["rangedDamage"] = dmg
            stats["genericCrit"] = round(min(7.0, 1.0 + power * 1.25), 2)
        elif "magic" in tags or "mana" in tags or "staff" in tags or "wand" in tags:
            stats["magicDamage"] = dmg
            stats["maxMana"] = 30 if power >= 1.5 else 15
            stats["manaRegen"] = 3 if power >= 2.0 else 1
        elif "summon" in tags or "minion" in tags:
            stats["summonDamage"] = dmg
            if power >= 2.3:
                stats["minionSlots"] = 1
        else:
            stats["genericDamage"] = round(dmg * 0.9, 3)
    if tags & {"fire", "hellstone"} and power >= 2.3:
        stats["lavaImmune"] = True
    if tags & {"water", "ocean", "flipper"}:
        stats["waterWalk"] = True
    return stats

def armor_slot_from_authoring(data: dict[str, Any], tags: set[str], runtime_stats: dict[str, Any]) -> str:
    raw = str(runtime_stats.get("armorSlot") or (data.get("armor") or {}).get("slot") or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"head", "helmet", "helm", "hood", "hat", "mask"}:
        return "head"
    if raw in {"legs", "leg", "leggings", "greaves", "pants", "boots"}:
        return "legs"
    if raw in {"body", "chest", "chestplate", "breastplate", "shirt", "robe", "torso"}:
        return "body"
    name = str(data.get("name") or "").lower()
    all_text = name + " " + " ".join(sorted(tags))
    if any(x in all_text for x in ["helmet", "helm", "hood", "hat", "mask"]):
        return "head"
    if any(x in all_text for x in ["leggings", "greaves", "pants", "boots"]):
        return "legs"
    return "body"

def armor_stats_for(tags: set[str], stage: dict[str, Any], slot: str) -> dict[str, Any]:
    power = float(stage.get("powerBudget", 1.0))
    rarity = int(stage.get("rarity", 0))
    slot_factor = {"head": 0.72, "body": 1.0, "legs": 0.82}.get(slot, 1.0)
    defense = max(1, int(round((1.5 + power * 2.25 + rarity * 0.70) * slot_factor)))
    stats: dict[str, Any] = {
        "enabled": True,
        "slot": slot,
        "setKey": "",
        "archetype": "hybrid",
        "defense": defense,
        "maxLife": 0,
        "maxMana": 0,
        "lifeRegen": 0,
        "manaRegen": 0,
        "movementSpeed": 0.0,
        "maxRunSpeed": 0.0,
        "jumpSpeed": 0.0,
        "genericDamage": 0.0,
        "meleeDamage": 0.0,
        "rangedDamage": 0.0,
        "magicDamage": 0.0,
        "summonDamage": 0.0,
        "genericCrit": 0.0,
        "attackSpeed": 0.0,
        "knockback": 0.0,
        "fallDamageImmune": False,
        "lavaImmune": False,
        "waterWalk": False,
        "minionSlots": 0,
        "lightStrength": 0.0,
        "lightColorName": "",
        "setBonusText": "",
        "setBonusGenericDamage": 0.0,
        "setBonusMeleeDamage": 0.0,
        "setBonusRangedDamage": 0.0,
        "setBonusMagicDamage": 0.0,
        "setBonusSummonDamage": 0.0,
        "setBonusGenericCrit": 0.0,
        "setBonusMovementSpeed": 0.0,
        "setBonusLifeRegen": 0,
        "setBonusManaRegen": 0,
        "setBonusMinionSlots": 0,
    }
    dmg = round(0.026 + min(power, 5.2) * 0.017, 3)
    if tags & {"melee", "sword", "blade", "warrior"}:
        stats["archetype"] = "melee"
        if slot == "head": stats["meleeDamage"] = dmg
        if slot == "body": stats["attackSpeed"] = round(min(0.14, dmg * 0.76), 3)
        if slot == "legs": stats["movementSpeed"] = round(min(0.16, dmg * 1.35), 3)
    elif tags & {"ranged", "gun", "bow", "bullet", "arrow"}:
        stats["archetype"] = "ranged"
        if slot == "head": stats["rangedDamage"] = dmg
        if slot == "body": stats["genericCrit"] = round(min(7.0, 1.0 + power * 1.25), 2)
        if slot == "legs": stats["movementSpeed"] = round(min(0.10, dmg), 3)
    elif tags & {"magic", "mana", "staff", "wand", "spell"}:
        stats["archetype"] = "magic"
        if slot == "head": stats["magicDamage"] = dmg
        if slot == "body": stats["maxMana"] = 30 if power >= 1.5 else 15
        if slot == "legs": stats["manaRegen"] = 1 if power < 2.5 else 3
    elif tags & {"summon", "minion", "sentry"}:
        stats["archetype"] = "summon"
        if slot == "head": stats["summonDamage"] = dmg
        if slot == "body" and power >= 2.2: stats["minionSlots"] = 1
        if slot == "legs": stats["movementSpeed"] = round(min(0.10, dmg), 3)
    elif tags & {"boots", "wings", "mobility", "aglet", "anklet"}:
        stats["archetype"] = "mobility"
        stats["movementSpeed"] = round(0.04 + min(power, 5.0) * 0.024, 3)
        if slot == "legs": stats["maxRunSpeed"] = round(0.06 + min(power, 5.0) * 0.036, 3)
    elif tags & {"defense", "shield", "guard", "armor"}:
        stats["archetype"] = "defense"
        if power >= 2.0 and slot == "body": stats["maxLife"] = 20
    if tags & {"fire", "hellstone", "lava"} and power >= 2.3:
        stats["lavaImmune"] = slot == "body"
    if tags & {"water", "ocean", "flipper"}:
        stats["waterWalk"] = slot == "legs"
    if tags & {"light", "star", "holy", "lunar", "glow"}:
        stats["lightStrength"] = round(min(0.85, 0.14 + power * 0.085), 3)
        stats["lightColorName"] = "gold" if "star" in tags or "holy" in tags else "blue"
    return stats

__all__ = [
    "_ACCESSORY_COST_WEIGHTS",
    "_ARMOR_PIECE_COST_WEIGHTS",
    "_SET_BONUS_COST_WEIGHTS",
    "_ACCESSORY_BOOLEAN_COSTS",
    "_ARMOR_BOOLEAN_COSTS",
    "_equipment_float",
    "_equipment_int",
    "_equipment_budget_base",
    "_equipment_cost",
    "_scale_equipment_fields",
    "apply_accessory_soft_budget",
    "apply_armor_soft_budget",
    "accessory_stats_for",
    "armor_slot_from_authoring",
    "armor_stats_for",
]
