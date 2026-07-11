from __future__ import annotations

import math
import re
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from infini_local.core.runtime_authoring.schema import (
    ENGINE_FN_CATALOG_V2,
    INT_FIELDS,
    accepted_engine_param_names,
)


class StrictEngineParamModel(BaseModel):
    """Strict per-function authoring boundary.

    Models are generated from the canonical engine function catalog.  This is a
    validator only: it never fills gameplay defaults and never compiles behavior.
    """

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


# These params are intentionally typed as nested authoring objects.  They are
# flattened by the compiler; adding a new stat requires extending this model and
# the compiler owner, which makes the change visible to agents instead of inert.
class EquipmentStatsParamBoundary(StrictEngineParamModel):
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


_BOOL_PARAMS = frozenset({
    "autoReuse", "consumable", "visualOnly", "safeTileOnly", "drawDuringUse",
    "useTurn", "channelUse", "fallDamageImmune", "lavaImmune", "waterWalk",
})
_INT_PARAMS = frozenset({
    *INT_FIELDS,
    "damage", "maxStack", "rarity", "value", "defense", "count", "amount",
    "attackIntervalTicks", "helperLifetimeTicks", "secondaryLifetimeTicks",
    "startTick", "repeatEvery", "duration", "tickRate", "offsetPx", "debuffTime",
    "oreSenseRadiusTiles", "manaRegen", "lifeRegen", "minionSlots", "sentrySlots",
    "aggro", "armorPenetration", "summonTagDamage",
})
# Deliberately explicit. NUMERIC_LIMITS contains both integral and continuous
# fields, so using the whole map as a float inventory would make strict raw
# boundaries accept values such as chargeTicks=1.5.
_FLOAT_PARAMS = frozenset({
    "knockback", "aoeRadiusTiles", "homingStrength", "rangeTiles", "reliability",
    "missPunish", "spreadRadians", "speed", "beamWidthPx", "chargePowerMultiplier",
    "sentryTargetRangeTiles", "fieldRadiusTiles", "secondaryDamageMultiplier",
    "secondarySpreadRadians", "sameTargetBias", "lightStrength", "soundVolume",
    "soundPitch", "soundPitchVariance", "scale", "density", "alpha", "spread",
    "jitter", "decayPerSecond", "strength", "miningSpeedScale", "itemScale",
    "damageMultiplier", "pullStrength", "targetRangeTiles", "movementSpeed",
    "maxRunSpeed", "jumpSpeed", "genericDamage", "meleeDamage", "rangedDamage",
    "magicDamage", "summonDamage", "genericCrit", "attackSpeed", "manaCostReduction",
    "ammoSaveChance", "endurance", "whipRange", "emitLightStrength", "jumpBoost",
})
_LIST_PARAMS: dict[tuple[str, str], Any] = {
    ("apply_player_effect_on_use", "buffs"): list[BuffParamBoundary],
}
_OBJECT_PARAMS: dict[tuple[str, str], Any] = {
    ("apply_player_effect_on_use", "generatedBuff"): GeneratedBuffParamBoundary,
    ("set_alt_use_mode", "generatedBuff"): GeneratedBuffParamBoundary,
    ("hold_item_effect", "generatedBuff"): GeneratedBuffParamBoundary,
    ("accessory_effect", "stats"): EquipmentStatsParamBoundary,
    ("armor_effect", "stats"): EquipmentStatsParamBoundary,
    ("armor_effect", "setBonus"): ArmorSetBonusParamBoundary,
}

# Semantic enums whose unknown values must never silently become executable.
_ENUM_PARAMS: dict[tuple[str, str] | str, tuple[str, ...]] = {
    "damageClass": ("generic", "melee", "ranged", "magic", "summon"),
    "delivery": ("swing", "thrust", "shoot", "cast", "throw", "summon"),
    "runtimeFamily": (
        "swing", "thrust", "returning", "flail", "yoyo", "whip", "shoot", "cast",
        "beam", "charge_release", "overhead_barrage", "throw", "summon",
    ),
    # Function-specific trigger catalogs take precedence. This shared fallback
    # exists only for generic trigger-bearing calls whose catalog does not expose
    # a closed set.
    "trigger": (
        "on_hit", "on_expire", "on_use", "on_alt_use", "on_hit_npc", "on_kill_npc",
        "on_projectile_impact", "while_held", "while_equipped", "on_low_life",
        "after_not_hit_for_ticks", "while_moving", "while_airborne", "while_in_water",
    ),
    ("spawn_secondary_projectiles", "trigger"): ("on_expire", "on_hit"),
    ("deploy_sentry", "placement"): ("grounded", "floating"),
    ("mobility_effect", "mode"): ("recall_home", "blink_to_cursor", "blink_to_projectile_impact"),
    ("set_alt_use_mode", "mode"): ("mobility", "generated_buff", "light", "none"),
    ("set_alt_use_mode", "mobilityMode"): ("recall_home", "blink_to_cursor"),
    ("ammo_behavior", "ammoFor"): ("arrow", "bullet", "empty"),
    ("use_condition", "mode"): ("grounded", "not_wet", "life_above", "mana_above"),
    ("triggered_action", "action"): (
        "grant_charge", "spend_charge", "apply_generated_buff", "apply_vanilla_buff",
        "emit_light", "spawn_secondary_projectiles", "mobility_effect",
        "temporary_stat_boost", "spawn_particles", "set_mode", "cycle_mode",
    ),
}




_OPEN_ENUM_SENTINELS = frozenset({"etc", "other", "any", "custom", "optional"})


def _catalog_enum_values(fn: str, name: str) -> tuple[str, ...] | None:
    """Infer only genuinely closed pipe-delimited enums from the catalog.

    Catalog cards also document extensible identities using tails such as
    ``|etc`` or prose such as ``other exact family``. Treating those as Literal
    values would make adding a new projectile/material/family fail before the
    compiler can see it, so open descriptions deliberately stay ``str``.
    """
    entry: Any = ENGINE_FN_CATALOG_V2.get(fn) or {}
    params: Any = entry.get("params") if isinstance(entry, dict) else {}
    descriptor = str((params.get(name) if isinstance(params, dict) else "") or "")
    clause = descriptor.split(";", 1)[0].strip()
    if "|" not in clause:
        return None
    values = tuple(part.strip() for part in clause.split("|"))
    if not values or any(not value or not re.fullmatch(r"[a-z0-9_]+", value) for value in values):
        return None
    if any(value in _OPEN_ENUM_SENTINELS for value in values):
        return None
    return values

def _literal_type(values: tuple[str, ...]) -> Any:
    # Pydantic accepts this runtime form on Python 3.10; keeping the dynamic
    # factory typed as Any avoids pretending static type checkers can enumerate
    # catalog values that are intentionally data-driven.
    literal_factory: Any = Literal
    return literal_factory.__getitem__(values)


def _param_annotation(fn: str, name: str) -> Any:
    nested = _LIST_PARAMS.get((fn, name)) or _OBJECT_PARAMS.get((fn, name))
    if nested is not None:
        return nested
    # Most-specific policy first. A function card may intentionally narrow a
    # shared semantic (for example secondary trigger is only on_hit/on_expire).
    enum_values = _ENUM_PARAMS.get((fn, name)) or _catalog_enum_values(fn, name) or _ENUM_PARAMS.get(name)
    if enum_values:
        return _literal_type(enum_values)
    if name in _BOOL_PARAMS:
        return bool
    if name in _INT_PARAMS:
        return int
    if name in _FLOAT_PARAMS:
        return int | float
    return str


@lru_cache(maxsize=None)
def engine_params_model(fn: str) -> type[BaseModel]:
    if fn not in ENGINE_FN_CATALOG_V2:
        raise KeyError(fn)
    fields: dict[str, tuple[Any, Any]] = {}
    for name in sorted(accepted_engine_param_names(fn)):
        annotation = _param_annotation(fn, name)
        fields[name] = (annotation | None, None)
    model_factory: Any = create_model
    return model_factory(
        "EngineParams_" + "".join(part.capitalize() for part in fn.split("_")),
        __base__=StrictEngineParamModel,
        **fields,
    )


def validate_engine_call_params(fn: str, params: Any) -> tuple[dict[str, Any] | None, list[str]]:
    if fn not in ENGINE_FN_CATALOG_V2:
        return None, [f"unknown function {fn}"]
    if not isinstance(params, dict):
        return None, ["params must be an object"]
    try:
        parsed = engine_params_model(fn).model_validate(params)
    except ValidationError as exc:
        errors: list[str] = []
        for row in exc.errors(include_url=False):
            loc = ".".join(str(x) for x in row.get("loc") or ())
            msg = str(row.get("msg") or "invalid")
            errors.append(f"{loc}: {msg}" if loc else msg)
        return None, errors
    out = parsed.model_dump(exclude_none=True)
    for key, value in out.items():
        if isinstance(value, float) and not math.isfinite(value):
            return None, [f"{key}: finite number required"]
    return out, []


def engine_contract_inventory() -> dict[str, dict[str, str]]:
    return {
        fn: {name: str(_param_annotation(fn, name)) for name in sorted(accepted_engine_param_names(fn))}
        for fn in sorted(ENGINE_FN_CATALOG_V2)
    }


__all__ = [
    "StrictEngineParamModel",
    "BuffParamBoundary",
    "GeneratedBuffParamBoundary",
    "EquipmentStatsParamBoundary",
    "ArmorSetBonusParamBoundary",
    "engine_params_model",
    "validate_engine_call_params",
    "engine_contract_inventory",
]
