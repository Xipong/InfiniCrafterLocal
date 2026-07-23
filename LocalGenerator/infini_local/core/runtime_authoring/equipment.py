from __future__ import annotations

from typing import Any

from infini_local.core.runtime_authoring.common import _norm_name, _num
from infini_local.core.runtime_authoring.structural import _merged_params

# AGENT MAP: accessory/armor compile lowerers only.
# Shared clamp table owns equipment stat bounds once. compiler.py must not
# re-author these field lists.

_EQUIPMENT_STAT_FIELDS: list[tuple[str, str, float, float, bool]] = [
    ("maxLife", "maxLife", 0, 100, True), ("maxMana", "maxMana", 0, 100, True),
    ("lifeRegen", "lifeRegen", 0, 20, True), ("manaRegen", "manaRegen", 0, 20, True),
    ("movementSpeed", "movementSpeed", 0, 1.0, False), ("maxRunSpeed", "maxRunSpeed", 0, 2.0, False),
    ("jumpSpeed", "jumpSpeed", 0, 4.0, False), ("genericDamage", "genericDamage", 0, 0.4, False),
    ("meleeDamage", "meleeDamage", 0, 0.4, False), ("rangedDamage", "rangedDamage", 0, 0.4, False),
    ("magicDamage", "magicDamage", 0, 0.4, False), ("summonDamage", "summonDamage", 0, 0.4, False),
    ("genericCrit", "genericCrit", 0, 20, False), ("attackSpeed", "attackSpeed", 0, 0.4, False),
    ("knockback", "knockback", 0, 2.0, False), ("minionSlots", "minionSlots", 0, 2, True),
    ("sentrySlots", "sentrySlots", 0, 2, True), ("manaCostReduction", "manaCostReduction", 0, 0.4, False),
    ("ammoSaveChance", "ammoSaveChance", 0, 0.5, False), ("aggro", "aggro", -400, 400, True),
    ("endurance", "endurance", 0, 0.2, False), ("armorPenetration", "armorPenetration", 0, 40, False),
    ("whipRange", "whipRange", 0, 1.5, False), ("summonTagDamage", "summonTagDamage", 0, 0.75, False),
    ("lightStrength", "lightStrength", 0, 1.5, False),
]

_BOOL_STAT_FIELDS = ("fallDamageImmune", "lavaImmune", "waterWalk")

_SET_BONUS_MAP = {
    "text": "setBonusText", "genericDamage": "setBonusGenericDamage", "meleeDamage": "setBonusMeleeDamage",
    "rangedDamage": "setBonusRangedDamage", "magicDamage": "setBonusMagicDamage", "summonDamage": "setBonusSummonDamage",
    "genericCrit": "setBonusGenericCrit", "movementSpeed": "setBonusMovementSpeed", "lifeRegen": "setBonusLifeRegen",
    "manaRegen": "setBonusManaRegen", "minionSlots": "setBonusMinionSlots", "sentrySlots": "setBonusSentrySlots",
    "manaCostReduction": "setBonusManaCostReduction", "ammoSaveChance": "setBonusAmmoSaveChance", "aggro": "setBonusAggro",
    "endurance": "setBonusEndurance", "armorPenetration": "setBonusArmorPenetration",
}

_SET_BONUS_INTEGER = {"lifeRegen", "manaRegen", "minionSlots", "sentrySlots", "aggro"}

_SET_BONUS_LIMITS = {
    "genericDamage": (0, 0.4), "meleeDamage": (0, 0.4), "rangedDamage": (0, 0.4),
    "magicDamage": (0, 0.4), "summonDamage": (0, 0.4), "genericCrit": (0, 20),
    "movementSpeed": (0, 1.0), "lifeRegen": (0, 20), "manaRegen": (0, 20),
    "minionSlots": (0, 2), "sentrySlots": (0, 2), "manaCostReduction": (0, 0.4),
    "ammoSaveChance": (0, 0.5), "aggro": (-400, 400), "endurance": (0, 0.2),
    "armorPenetration": (0, 40),
}


def _apply_equipment_stats(target: dict[str, Any], stats: dict[str, Any]) -> None:
    for src, out, lo, hi, integer in _EQUIPMENT_STAT_FIELDS:
        raw = stats.get(src)
        if raw in (None, ""):
            continue
        val = max(lo, min(hi, _num(raw, 0) or 0))
        target[out] = int(round(val)) if integer else round(float(val), 3)
    for src in _BOOL_STAT_FIELDS:
        if src in stats:
            target[src] = bool(stats.get(src))
    color = str(stats.get("lightColorName") or "").strip()
    if color:
        target["lightColorName"] = color[:32]


def apply_accessory_calls(
    patch: dict[str, Any],
    accessory_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compile accessory_effect calls into a bounded accessory AttackSpec block."""
    if not accessory_calls:
        return patch
    acc = _merged_params(accessory_calls)
    raw_stats = acc.get("stats")
    stats: dict[str, Any] = raw_stats if isinstance(raw_stats, dict) else {}
    accessory: dict[str, Any] = {"enabled": True}
    if acc.get("archetype") not in (None, ""):
        accessory["archetype"] = _norm_name(acc.get("archetype"))[:32]
    if acc.get("defense") not in (None, ""):
        accessory["defense"] = int(round(max(0, min(20, _num(acc.get("defense"), 0) or 0))))
    _apply_equipment_stats(accessory, stats)
    patch["accessory"] = accessory
    patch["kind"] = "accessory"
    patch["maxStack"] = 1
    return patch


def apply_armor_calls(
    patch: dict[str, Any],
    armor_calls: list[dict[str, Any]],
    itemstats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile armor_effect (or armor resultKind) into a bounded armor AttackSpec block."""
    itemstats = itemstats if isinstance(itemstats, dict) else {}
    if not armor_calls and _norm_name(itemstats.get("resultKind")) != "armor":
        return patch
    arm = _merged_params(armor_calls) if armor_calls else {}
    raw_stats = arm.get("stats")
    stats: dict[str, Any] = raw_stats if isinstance(raw_stats, dict) else {}
    raw_set_bonus = arm.get("setBonus")
    set_bonus: dict[str, Any] = raw_set_bonus if isinstance(raw_set_bonus, dict) else {}
    armor: dict[str, Any] = {"enabled": True}
    slot = _norm_name(arm.get("armorSlot") or itemstats.get("armorSlot") or arm.get("slot"))
    armor["slot"] = slot if slot in {"head", "body", "legs"} else ""
    if arm.get("setKey") not in (None, ""):
        armor["setKey"] = str(arm.get("setKey"))[:64]
    if arm.get("archetype") not in (None, ""):
        armor["archetype"] = _norm_name(arm.get("archetype"))[:32]
    if arm.get("defense") not in (None, "") or itemstats.get("defense") not in (None, ""):
        raw_defense = arm.get("defense", itemstats.get("defense"))
        armor["defense"] = int(round(max(0, min(80, _num(raw_defense, 0) or 0))))
    _apply_equipment_stats(armor, stats)
    for src, out in _SET_BONUS_MAP.items():
        raw = set_bonus.get(src)
        if raw in (None, ""):
            continue
        if src == "text":
            armor[out] = str(raw)[:120]
        else:
            val = _num(raw, 0) or 0
            lo, hi = _SET_BONUS_LIMITS[src]
            val = max(lo, min(hi, val))
            armor[out] = int(round(val)) if src in _SET_BONUS_INTEGER else round(float(val), 3)
    patch["armor"] = armor
    patch["kind"] = "armor"
    patch["maxStack"] = 1
    patch["damage"] = 0
    return patch


__all__ = ["apply_accessory_calls", "apply_armor_calls", "_EQUIPMENT_STAT_FIELDS"]
