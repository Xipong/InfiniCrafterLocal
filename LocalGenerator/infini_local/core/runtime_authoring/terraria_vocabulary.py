from __future__ import annotations

"""Finite canonical Terraria/tModLoader vocabulary used by runtime-program v5.

This module deliberately contains *mappings*, not semantic aliases.  Every
Author-visible token names one exact stable tModLoader value.  Do not add loose
spellings, weapon-family shortcuts, loose mod lookups, or prose-derived fallbacks here.
"""

from types import MappingProxyType
from typing import Final, Mapping


DAMAGE_CLASS_TOKENS: Final[tuple[str, ...]] = (
    "default",
    "generic",
    "melee",
    "melee_no_speed",
    "ranged",
    "magic",
    "magic_summon_hybrid",
    "summon",
    "summon_melee_speed",
    "throwing",
)

# Exact tModLoader content identity for optional modded damage classes. Built-ins
# use the finite tokens above; modded values must use the registered FullName
# shape `ModName/ClassName`, copied from loaded parent facts. This is not an alias.
DAMAGE_CLASS_TOKEN_PATTERN: Final[str] = (
    r"^(?:"
    + "|".join(DAMAGE_CLASS_TOKENS)
    + r"|[A-Za-z][A-Za-z0-9_]{0,63}/[A-Za-z][A-Za-z0-9_]{0,63})$"
)

# ItemUseStyleID stable/1.4.4 names, excluding None and the unused DrinkOld.
ITEM_USE_STYLE_TOKENS: Final[tuple[str, ...]] = (
    "swing",
    "eat_food",
    "thrust",
    "hold_up",
    "shoot",
    "drink_long",
    "drink_liquid",
    "golf_play",
    "hidden_animation",
    "mow_the_lawn",
    "guitar",
    "rapier",
    "raise_lamp",
)

# Generated ammo items can safely set the per-instance Item.ammo value for these
# stable vanilla categories.  Sand is intentionally excluded: its complete
# semantics require ItemID.Sets.SandgunAmmoProjectileData, a type-wide static set,
# while all generated items share one proxy Item.type.
VANILLA_AMMO_CATEGORY_TOKENS: Final[tuple[str, ...]] = (
    "arrow",
    "bullet",
    "candy_corn",
    "coin",
    "dart",
    "fallen_star",
    "flare",
    "gel",
    "jack_o_lantern",
    "nail_friendly",
    "rocket",
    "snowball",
    "solution",
    "stake",
    "stynger_bolt",
)

# Stable Terraria 1.4.4 ProjectileID.Count is 1022, therefore vanilla IDs
# accepted by this contract are 1..1021. Modded projectile IDs require a future
# explicit loaded-content catalog rather than a guessed integer.
VANILLA_PROJECTILE_TYPE_ID_MAX: Final[int] = 1021

# Documentation/audit projections only.  C# owns the executable integer mapping.
ITEM_USE_STYLE_TMODLOADER_NAMES: Final[Mapping[str, str]] = MappingProxyType({
    "swing": "ItemUseStyleID.Swing",
    "eat_food": "ItemUseStyleID.EatFood",
    "thrust": "ItemUseStyleID.Thrust",
    "hold_up": "ItemUseStyleID.HoldUp",
    "shoot": "ItemUseStyleID.Shoot",
    "drink_long": "ItemUseStyleID.DrinkLong",
    "drink_liquid": "ItemUseStyleID.DrinkLiquid",
    "golf_play": "ItemUseStyleID.GolfPlay",
    "hidden_animation": "ItemUseStyleID.HiddenAnimation",
    "mow_the_lawn": "ItemUseStyleID.MowTheLawn",
    "guitar": "ItemUseStyleID.Guitar",
    "rapier": "ItemUseStyleID.Rapier",
    "raise_lamp": "ItemUseStyleID.RaiseLamp",
})

DAMAGE_CLASS_TMODLOADER_NAMES: Final[Mapping[str, str]] = MappingProxyType({
    "default": "DamageClass.Default",
    "generic": "DamageClass.Generic",
    "melee": "DamageClass.Melee",
    "melee_no_speed": "DamageClass.MeleeNoSpeed",
    "ranged": "DamageClass.Ranged",
    "magic": "DamageClass.Magic",
    "magic_summon_hybrid": "DamageClass.MagicSummonHybrid",
    "summon": "DamageClass.Summon",
    "summon_melee_speed": "DamageClass.SummonMeleeSpeed",
    "throwing": "DamageClass.Throwing",
})

AMMO_CATEGORY_TMODLOADER_NAMES: Final[Mapping[str, str]] = MappingProxyType({
    "arrow": "AmmoID.Arrow",
    "bullet": "AmmoID.Bullet",
    "candy_corn": "AmmoID.CandyCorn",
    "coin": "AmmoID.Coin",
    "dart": "AmmoID.Dart",
    "fallen_star": "AmmoID.FallenStar",
    "flare": "AmmoID.Flare",
    "gel": "AmmoID.Gel",
    "jack_o_lantern": "AmmoID.JackOLantern",
    "nail_friendly": "AmmoID.NailFriendly",
    "rocket": "AmmoID.Rocket",
    "snowball": "AmmoID.Snowball",
    "solution": "AmmoID.Solution",
    "stake": "AmmoID.Stake",
    "stynger_bolt": "AmmoID.StyngerBolt",
})


__all__ = [
    "AMMO_CATEGORY_TMODLOADER_NAMES",
    "DAMAGE_CLASS_TMODLOADER_NAMES",
    "DAMAGE_CLASS_TOKEN_PATTERN",
    "DAMAGE_CLASS_TOKENS",
    "ITEM_USE_STYLE_TMODLOADER_NAMES",
    "ITEM_USE_STYLE_TOKENS",
    "VANILLA_AMMO_CATEGORY_TOKENS",
    "VANILLA_PROJECTILE_TYPE_ID_MAX",
]
