"""Strict nested parameter boundaries for Author engine function contracts."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictEngineParamModel(BaseModel):
    """Strict authoring boundary; validates wire shape without gameplay defaults."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class BuffParamBoundary(StrictEngineParamModel):
    buffType: int
    buffTime: int


class GeneratedBuffParamBoundary(StrictEngineParamModel):
    durationTicks: int = 0
    miningSpeedMultiplier: int | float = 1.0
    emitLightStrength: int | float = 0.0
    lightColorName: str = ""
    oreSenseRadiusTiles: int = 0
    movementSpeed: int | float = 0.0
    jumpBoost: int | float = 0.0
    manaRegen: int = 0
    lifeRegen: int = 0


class EquipmentStatsParamBoundary(StrictEngineParamModel):
    """Finite equipment-stat object flattened by the specialized compiler owner."""

    maxLife: int | None = None
    maxMana: int | None = None
    lifeRegen: int | None = None
    manaRegen: int | None = None
    movementSpeed: int | float | None = None
    maxRunSpeed: int | float | None = None
    jumpSpeed: int | float | None = None
    genericDamage: int | float | None = None
    meleeDamage: int | float | None = None
    rangedDamage: int | float | None = None
    magicDamage: int | float | None = None
    summonDamage: int | float | None = None
    genericCrit: int | float | None = None
    attackSpeed: int | float | None = None
    knockback: int | float | None = None
    minionSlots: int | None = None
    sentrySlots: int | None = None
    manaCostReduction: int | float | None = None
    ammoSaveChance: int | float | None = None
    aggro: int | None = None
    endurance: int | float | None = None
    armorPenetration: int | float | None = None
    lightStrength: int | float | None = None
    lightColorName: str | None = None
    fallDamageImmune: bool | None = None
    lavaImmune: bool | None = None
    waterWalk: bool | None = None
    whipRange: int | float | None = None
    summonTagDamage: int | float | None = None


class ArmorSetBonusParamBoundary(StrictEngineParamModel):
    text: str = ""
    genericDamage: int | float | None = None
    meleeDamage: int | float | None = None
    rangedDamage: int | float | None = None
    magicDamage: int | float | None = None
    summonDamage: int | float | None = None
    genericCrit: int | float | None = None
    movementSpeed: int | float | None = None
    lifeRegen: int | None = None
    manaRegen: int | None = None
    minionSlots: int | None = None
    sentrySlots: int | None = None
    manaCostReduction: int | float | None = None
    ammoSaveChance: int | float | None = None
    aggro: int | None = None
    endurance: int | float | None = None
    armorPenetration: int | float | None = None


__all__ = [
    "StrictEngineParamModel",
    "BuffParamBoundary",
    "GeneratedBuffParamBoundary",
    "EquipmentStatsParamBoundary",
    "ArmorSetBonusParamBoundary",
]
