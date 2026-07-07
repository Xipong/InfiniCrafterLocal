from __future__ import annotations

import json
import math
import re
from typing import Any

from infini_local.core.result_models import RuntimeCompileResult
from infini_local.core.runtime_archetypes import compile_runtime_archetype_to_attack_patch
from infini_local.core.runtime_contracts import validate_runtime_contract
from infini_local.core.runtime_promise_truth import validate_runtime_promises

# AGENT MAP: runtimePlan.engineCalls compiler. This module is the Python side of
# the executable contract: it normalizes/validates structured engine calls and
# emits explicit game-facing fields/provenance. It must not read prose/name text
# to invent mechanics, and it is not a second free-form author after LLM output.
ENGINE_RUNTIME_API_VERSION = "v0.4.47"  # Runtime API/engine-call contract version, not project build version.

MOVEMENTS = {
    "straight", "slow_homing", "gravity_arc", "drift", "orbit", "boomerang", "bounce",
    "sine_homing", "phase", "accelerate", "spiral", "vortex_orb", "blackhole_pull",
    "proximity_missile", "returning_glaive", "expanding_wave",
    "flail_tether", "yoyo_hover", "whip_lash",
}
MOVEMENT_ALIASES = {
    "rain": "gravity_arc", "fall": "gravity_arc", "falling": "gravity_arc", "falling_projectile": "gravity_arc",
    "projectile_rain": "gravity_arc", "starfall": "gravity_arc", "skyfall": "gravity_arc", "meteor": "gravity_arc",
    "arc": "gravity_arc", "lob": "gravity_arc", "lobbed": "gravity_arc", "grenade_arc": "gravity_arc",
    "homing": "slow_homing", "seeking": "slow_homing", "guided": "slow_homing", "tracking": "slow_homing",
    "return": "returning_glaive", "returning": "returning_glaive", "returning_throw": "returning_glaive",
    "glaive_return": "returning_glaive", "chakram": "boomerang", "boomerang_return": "boomerang",
    "wave": "expanding_wave", "shockwave": "expanding_wave", "ring": "expanding_wave",
    "beam": "phase", "laser": "phase", "ray": "phase", "hitscan": "phase",
    "missile": "proximity_missile", "rocket": "proximity_missile", "orb": "vortex_orb",
    "flail": "flail_tether", "chain_flail": "flail_tether", "mace": "flail_tether", "anchor": "flail_tether",
    "yoyo": "yoyo_hover", "yo_yo": "yoyo_hover",
    "whip": "whip_lash", "lash": "whip_lash",
}
EFFECTS = {"none", "dust", "electric", "slime", "star", "flame", "frost", "leaf", "shadow", "poison", "blood", "honey", "sand", "lunar", "heal", "holy", "smoke"}
EFFECT_ALIASES = {
    "fire": "flame", "burn": "flame", "ember": "flame", "lava": "flame", "magma": "flame",
    "ice": "frost", "cold": "frost", "snow": "frost", "frostburn": "frost",
    "lightning": "electric", "shock": "electric", "thunder": "electric", "storm": "electric",
    "venom": "poison", "toxic": "poison", "acid": "poison", "ichor": "poison",
    "dark": "shadow", "void": "shadow", "grave": "shadow", "shadowflame": "shadow",
    "nature": "leaf", "plant": "leaf", "spore": "leaf",
    "water": "slime", "goo": "slime", "gel": "slime",
    "radiant": "holy", "light": "holy", "solar": "holy",
    "smog": "smoke", "ash": "smoke",
}
ONHITS = {"none", "burst", "split", "chain", "burn", "frostburn", "poison", "shadowflame", "starburst", "starfall", "bleed", "aura_pulse", "spore_cloud", "mini_missiles", "vortex_spawn", "blackhole", "radial_beams", "lightning_arc", "heal", "lifesteal"}
ONHIT_ALIASES = {
    "fire": "burn", "on_fire": "burn", "ignite": "burn",
    "ice": "frostburn", "freeze": "frostburn", "chill": "frostburn",
    "venom": "poison", "toxic": "poison", "acid": "poison",
    "electric": "lightning_arc", "electrified": "lightning_arc", "shock": "lightning_arc", "zap": "lightning_arc",
    "blood": "bleed", "bleeding": "bleed",
    "explode": "burst", "explosion": "burst", "nova": "burst",
    "fragment": "split", "fragments": "split", "shards": "split",
    "star": "starburst", "stars": "starburst", "star_rain": "starfall", "falling_stars": "starfall", "star_wrath": "starfall", "sky_stars": "starfall",
    "lifesteal": "lifesteal", "life_steal": "lifesteal",
}
# The planner may use Terraria-family words; the adapter canonicalizes them to the small
# runtime executor families instead of forcing the model to call a bow/staff/spear a generic shoot/swing.
DELIVERIES = {"none", "swing", "thrust", "spear", "shoot", "cast", "throw", "summon", "flail", "yoyo", "whip"}
DELIVERY_ALIASES = {
    "slash": "swing", "melee_arc": "swing", "blade_arc": "swing", "sword": "swing", "axe": "swing", "hammer": "swing", "club": "swing",
    "stab": "thrust", "rapier": "thrust", "shortsword": "thrust", "short_sword": "thrust", "held_thrust": "thrust", "spear_thrust": "thrust",
    "polearm": "thrust", "lance": "thrust", "pike": "thrust", "trident": "thrust", "halberd": "thrust", "naginata": "thrust",
    "ranged": "shoot", "bow": "shoot", "repeater": "shoot", "gun": "shoot", "launcher": "shoot", "crossbow": "shoot", "blowgun": "shoot",
    "magic": "cast", "spell": "cast", "staff": "cast", "wand": "cast", "rod": "cast", "book": "cast", "spellbook": "cast",
    "thrown": "throw", "knife": "throw", "dart": "throw", "grenade": "throw",
    "boomerang": "throw", "chakram": "throw", "glaive_throw": "throw", "returning_throw": "throw",
    "flail": "flail", "chain_flail": "flail", "ball_and_chain": "flail", "mace": "flail", "anchor": "flail",
    "yoyo": "yoyo", "yo_yo": "yoyo",
    "whip": "whip", "lash": "whip",
    "minion": "summon", "sentry": "summon", "summon_projectile": "summon",
}


RUNTIME_FAMILIES = {"none", "swing", "thrust", "returning", "flail", "yoyo", "whip", "shoot", "cast", "throw", "summon"}

TERRARIA_WEAPON_FAMILY_GROUPS: dict[str, set[str]] = {
    "swing": {"broadsword", "sword", "blade", "axe", "hammer", "club", "bat", "scythe"},
    "thrust": {"spear", "lance", "pike", "trident", "halberd", "naginata", "polearm", "jousting_lance", "shortsword", "short_sword", "rapier", "dagger", "gladius", "stab"},
    "returning": {"boomerang", "chakram", "light_disc", "glaive", "throwing_disc"},
    "flail": {"flail", "chain_flail", "mace", "anchor", "ball_and_chain"},
    "yoyo": {"yoyo", "yo_yo"},
    "whip": {"whip", "lash"},
    "ranged": {"bow", "repeater", "crossbow", "gun", "shotgun", "musket", "pistol", "launcher", "rocket_launcher", "dart", "blowgun", "harpoon"},
    # Magic group is the CARRIER/use context, not a material+shape classifier.
    # Words such as crystal_spear/light_spear/spectral_spear are ambiguous item
    # concepts: they may be melee thrusts, thrown/shoot projectiles, or magic spells.
    # They are only lowered to cast when authored through cast_magic_weapon(...) or
    # explicit runtimeFamily=cast/delivery=cast, never because of the compound name.
    "magic": {"staff", "wand", "rod", "spellbook", "book", "magic_gun", "channelled_beam", "channeled_beam", "beam_staff", "laser_staff"},
    "summon": {"minion", "sentry", "turret", "pet_attack"},
}


def _family_group(family: Any) -> str:
    f = _norm_name(family)
    for group, values in TERRARIA_WEAPON_FAMILY_GROUPS.items():
        if f in values:
            return group
    return ""


# Terraria ItemUseStyleID subset used by the generated runtime.  The model authors
# family-level intent; the compiler emits these explicit affordance fields so C#
# does not have to infer item animation/noUseGraphic/noMelee from prose or names.
USE_STYLE_NONE = 0
USE_STYLE_SWING = 1
USE_STYLE_THRUST = 3
USE_STYLE_HOLD_UP = 4
USE_STYLE_SHOOT = 5
USE_STYLE_RAPIER = 13


def _runtime_family_affordances(runtime_family: str, weapon_family: Any = "") -> dict[str, Any]:
    family = _norm_name(weapon_family)
    out: dict[str, Any] = {}
    if runtime_family == "swing":
        out.update({"useStyleCode": USE_STYLE_SWING, "hideUseGraphic": False, "disableItemMeleeHitbox": False, "ownerHitCheck": False})
    elif runtime_family == "thrust":
        # Spears/lances in Terraria are item-use-style Shoot with noUseGraphic/noMelee
        # and a held projectile. Shortsword/rapier-like stabs can use Rapier-style
        # animation, but still execute through the generated held-thrust projectile.
        style = USE_STYLE_RAPIER if family in {"shortsword", "short_sword", "rapier", "dagger", "gladius"} else USE_STYLE_SHOOT
        out.update({"useStyleCode": style, "hideUseGraphic": True, "disableItemMeleeHitbox": True, "ownerHitCheck": True})
    elif runtime_family in {"returning", "flail", "yoyo", "whip", "shoot", "cast", "throw", "summon"}:
        out.update({"useStyleCode": USE_STYLE_SHOOT, "hideUseGraphic": True, "disableItemMeleeHitbox": True, "ownerHitCheck": runtime_family == "whip"})
        if runtime_family == "yoyo":
            out["channelUse"] = True
    return out


ENGINE_FN_CATALOG_V2 = {
    "set_item_stats": {
        "meaning": "Declare kind + safe Terraria numbers: category, damage class, damage/use time, stack/yield, potion/tool/ammo/armor, rarity/value.",
        "params": {
            "resultKind": "weapon|ammo|consumable_weapon|tool|accessory|armor|potion|material|furniture|generic",
            "damageClass": "generic|melee|ranged|magic|summon; melee=held/contact, ranged/generic=free physical flight.",
            "damage": "0..source cap", "useTimeTicks": "10..150", "maxStack": "1 for gear; 25+ for ammo stacks",
            "weaponSubfamily": "taxonomy hint",
            "craftYield": "output stack count; ammo/material usually 25+",
            "healLife": "potion only; 0 otherwise",
            "healMana": "potion only; 0 otherwise",
            "buffType": "potion only; Terraria buff id from parent facts",
            "buffTime": "ticks paired with buffType",
            "pickPower": "tool only; requires tool facts",
            "axePower": "tool only; requires tool facts",
            "hammerPower": "tool only; requires tool facts",
            "ammoFor": "empty|arrow|bullet; empty for generated darts/throwables",
            "armorSlot": "head|body|legs for resultKind=armor",
            "defense": "armor only; 0..80; C# writes Item.defense",
            "consumable": "true only for ammo/potion/material outputs", "rarity": "-1..12", "value": "0..bounded",
        },
    },
    "shoot_projectile": {
        "meaning": "Low-level primary projectile/held executor. Prefer family calls; direct use must include runtimeFamily.",
        "params": {
            "delivery": "swing|thrust|spear|stab|rapier|shortsword|shoot|bow|gun|launcher|cast|staff|wand|book|throw|boomerang|summon|minion|sentry", "movement": "straight|slow_homing|gravity_arc|drift|orbit|boomerang|bounce|sine_homing|phase|accelerate|spiral|vortex_orb|blackhole_pull|proximity_missile|returning_glaive|expanding_wave; phase is projectile pass-through, not teleport",
            "speed": "3..18", "rangeTiles": "4..120", "lifetimeTicks": "25..900", "shotCount": "1..8", "spreadRadians": "0..0.75", "pierce": "-1 infinite, 0..10 finite", "extraUpdates": "0..3",
            "reliability": "0.45..1.25", "selfLockTicks": "0..120 recovery", "missPunish": "0..1 whiff penalty",
            "damageMultiplier": "0..3 optional; budget-clamped",
            "runtimeFamily": "swing|thrust|returning|flail|yoyo|whip|shoot|cast|throw|summon; required for direct call",
            "weaponFamily": "optional family: spear/bow/staff/flail/yoyo/whip/etc",
            "weaponSubfamily": "taxonomy hint",
            "projectileFamily": "emitted projectile form; not executor family",
            "projectileShape": "short visual/mechanical shape", "projectileMotion": "short motion feel", "projectileTrail": "short trail identity", "projectileImpact": "short hit identity",
        },
    },
    "perform_melee_attack": {
        "meaning": "Terraria melee families: swing, stab, thrust/spear, returning, flail, yoyo, whip. Projectile fields describe emitted/visual bodies, not hidden category routing.",
        "params": {
            "family": "broadsword|sword|axe|hammer|shortsword|rapier|dagger|spear|lance|pike|trident|halberd|naginata|jousting_lance|boomerang|chakram|flail|mace|anchor|yoyo|whip",
            "runtimeFamily": "derived; omit unless repairing",
            "speed": "3..18", "rangeTiles": "2..80", "lifetimeTicks": "10..900", "pierce": "-1..10", "useTimeTicks": "10..150",
            "shotCount": "1..8 emitted/free projectiles", "spreadRadians": "0..0.75",
            "projectileShape": "held/projectile body shape", "projectileMotion": "thrust/swing/return/tether/lash/hover", "projectileTrail": "short trail identity", "projectileImpact": "hit identity"
        },
    },
    "fire_ranged_weapon": {
        "meaning": "Terraria ranged weapon context: bows/guns/launchers/darts/harpoons. ammoFor arrow/bullet/rocket uses vanilla ammo; empty means generated projectile stack.",
        "params": {
            "family": "bow|repeater|gun|shotgun|launcher|rocket_launcher|dart|blowgun|harpoon", "ammoFor": "empty|arrow|bullet|rocket",
            "movement": "straight|gravity_arc|slow_homing|phase|proximity_missile|boomerang; phase is projectile pass-through", "speed": "3..18", "rangeTiles": "10..120", "lifetimeTicks": "25..900", "shotCount": "1..8", "spreadRadians": "0..0.75", "pierce": "-1..10",
            "projectileShape": "projectile body", "projectileMotion": "flight feel", "projectileTrail": "trail identity", "projectileImpact": "hit identity"
        },
    },
    "cast_magic_weapon": {
        "meaning": "Terraria magic cast context: staff/wand/book/rod/magic gun. Can fire bolts, beams, or spell-shaped projectiles; projectileFamily is visual/form, not executor.",
        "params": {
            "family": "staff|wand|rod|spellbook|book|magic_gun|channelled_beam|beam_staff|laser_staff|optional projectile form such as spear/lance/glaive/bolt/orb",
            "projectileFamily": "projectile form: spear|lance|bolt|beam|orb|book_page; not executor family",
            "movement": "straight|slow_homing|gravity_arc|phase|accelerate|vortex_orb|blackhole_pull|expanding_wave; phase is projectile pass-through", "speed": "3..18", "rangeTiles": "8..120", "lifetimeTicks": "25..900", "shotCount": "1..8", "spreadRadians": "0..0.75", "pierce": "-1..10",
            "projectileShape": "spell body", "projectileMotion": "spell motion", "projectileTrail": "trail identity", "projectileImpact": "hit identity"
        },
    },
    "summon_combat_entity": {
        "meaning": "Summon-family action for bounded generated projectile helpers: minion, sentry, turret, pet_attack, light_pet. Whips use perform_melee_attack family=whip.",
        "params": {
            "family": "minion|sentry|turret|pet_attack|light_pet", "movement": "orbit|slow_homing|drift|straight", "speed": "3..18", "rangeTiles": "8..120", "lifetimeTicks": "25..900", "shotCount": "1..4", "pierce": "0..10", "projectileShape": "summoned entity or sentry shot"
        },
    },
    "spawn_secondary_projectiles": {
        "meaning": "Real secondary damaging projectiles, not VFX motes. Use only for actual child hits.",
        "params": {"trigger": "on_hit only; other triggers rejected", "count": "0..8", "damageMultiplier": "0..1", "spreadRadians": "0..1.2", "lifetimeTicks": "5..180", "sameTargetBias": "0..1", "projectileShape": "optional child shape", "material": "optional child material"},
    },
    "apply_on_hit_effect": {
        "meaning": "Real on-hit gameplay: debuffs, bursts, chained hits, child-producing effects, pull/heal/lifesteal. Visual-only impact belongs in spawn_contact_particles.",
        "params": {"onHit": "none|burst|split|chain|burn|frostburn|poison|shadowflame|bleed|starburst|starfall|aura_pulse|spore_cloud|mini_missiles|vortex_spawn|blackhole|radial_beams|lightning_arc|heal|lifesteal", "aoeRadiusTiles": "0..10", "count": "0..8 for child-producing onHit; starfall = bounded falling-star child projectiles from above the hit", "chainCount": "0..6 for chain-like effects", "pullStrength": "0..1", "debuffHint": "short text or empty"},
    },
    "spawn_contact_particles": {
        "meaning": "Pure VFX/dust, no damage. Use this for chips, sawdust, sparks, slime, smoke, glow.",
        "params": {"effect": "none|dust|electric|slime|star|flame|frost|leaf|shadow|poison|blood|honey|sand|lunar|heal|holy|smoke", "amount": "0..40", "scale": "0..2", "durationTicks": "1..80", "material": "wood|metal|stone|magic|fire|slime|etc"},
    },
    "leave_trail_or_field": {
        "meaning": "Visual-only trail/line/residue. Does not create damage/projectiles/hitbox in the current runtime.",
        "params": {"trailLength": "0..24", "fieldLifetimeTicks": "0..240 visual only", "fieldRadiusTiles": "0..6 visual only", "tickRate": "0..60 visual only", "visualOnly": "true only; false rejected"},
    },
    "visual_effect_cue": {
        "meaning": "Explicit visual/audio cue authored by the model. Adds frozen VFX manifest slots; no damage, tile edit, loot, NPC spawn or hidden gameplay. Use it to make generated items look/sound distinct without changing balance.",
        "params": {"event": "travel|active|tick|hit|kill|expire|while_held|while_equipped|on_use|on_alt_use", "rendererKind": "projectileAfterimage|spriteStampTrail|historyRibbon|tipTrail|ghostArc|wavyStrip|beamLine|fieldPulse|orbitingMotes|actorAfterimage|impactRing|impactSprite|childMotes|lightCue|soundCue", "channel": "motionTrail|coreGlow|ambientParticles|impactShape|impactParticles|decaySmoke|light|sound", "lane": "primary|support|accent|ornament|cue", "textureRole": "projectile|impact|child|field", "particleRole": "projectile|impact|child|field", "emissionMode": "wake|orbit|residue|burst|cone|ring|spiral|point", "particleSystemId": "pl:glow|pl:shard|pl:smoke|pl:spark|dust", "scale": "0.15..5", "density": "0..1", "duration": "3..120", "alpha": "0..1", "spread": "0..2", "jitter": "0..1.5", "startTick": "0..120", "repeatEvery": "0..120", "importance": "core|secondary|accent|luxury", "note": "short identity/debug only"},
    },
    "apply_player_effect_on_use": {
        "meaning": "Executable non-combat use effects: healing, vanilla buffs, and bounded generated utility buffs.",
        "params": {"healLife": "0..500", "healMana": "0..500", "buffType": "vanilla buff id", "buffTime": "ticks", "buffs": "array of {buffType,buffTime}; max 4", "generatedBuff": "object with durationTicks, miningSpeedMultiplier, emitLightStrength, lightColorName, oreSenseRadiusTiles, movementSpeed, jumpBoost, manaRegen, lifeRegen; oreSense>0=findTreasure; radius debug-only", "note": "short identity/debug only"},
    },
    "tool_capability": {
        "meaning": "Executable Terraria tool stats for real tools only.",
        "params": {"pickPower": "0..230", "axePower": "0..50", "hammerPower": "0..120", "miningSpeedScale": "0.25..2 executable held-tool mining speed multiplier"},
    },
    "emit_light": {
        "meaning": "Executable runtime light cue on held/projectile/effect contexts. It is not a baked image request and not damage.",
        "params": {"strength": "0..1", "color": "named color", "durationTicks": "1..240"},
    },
    "mobility_effect": {
        "meaning": "Bounded movement: recall, blink to cursor, or blink to projectile impact; needs safe tile/cooldown.",
        "params": {"mode": "recall_home|blink_to_cursor|blink_to_projectile_impact", "rangeTiles": "0..80", "cooldownTicks": "0..3600", "safeTileOnly": "true"},
    },
    "state_meter": {
        "meaning": "Preserved state intent: charges/heat/modes/cooldowns. Immediate gameplay still needs executable calls.",
        "params": {"id": "short stable meter id", "label": "short display/debug name", "maxValue": "1..20", "initialValue": "0..20", "gainOnUse": "0..20", "gainOnHit": "0..20", "gainOnKill": "0..20", "spendOnUse": "0..20", "spendOnAltUse": "0..20", "decayPerSecond": "0..20", "cooldownTicks": "0..3600", "modeCount": "0..8"},
    },
    "triggered_action": {
        "meaning": "Future trigger/action intent. Must use safe trigger/action; boss/NPC/mob spawn is hard-rejected.",
        "params": {"trigger": "on_use|on_alt_use|on_hit_npc|on_kill_npc|on_projectile_impact|while_held|while_equipped|on_low_life|after_not_hit_for_ticks|while_moving|while_airborne|while_in_water", "action": "grant_charge|spend_charge|apply_generated_buff|apply_vanilla_buff|emit_light|spawn_secondary_projectiles|mobility_effect|temporary_stat_boost|spawn_particles|set_mode|cycle_mode", "meterId": "optional state_meter id", "requiredValue": "0..20", "spendValue": "0..20", "cooldownTicks": "0..3600", "note": "short identity/debug"},
    },
    "accessory_effect": {
        "meaning": "Equippable accessory stats, not temporary use effects.",
        "params": {"archetype": "mobility|defense|damage|utility|hybrid", "defense": "0..20", "stats": "life/mana/regen/move/jump/classDmg/crit/atkSpeed/kb/minions/sentries/manaCost/ammoSave/aggro/endurance/armorPen/light/immunities"},
    },
    "armor_effect": {
        "meaning": "Armor: slot, defense, equip/set bonuses.",
        "params": {"armorSlot": "head|body|legs", "setKey": "same id for set or empty", "archetype": "melee|ranged|magic|summon|defense|mobility|hybrid", "defense": "0..80", "stats": "life/mana/regen/move/jump/classDmg/crit/atkSpeed/kb/minions/light/immunities", "setBonus": "text + classDmg/crit/move/regen/minions"},
    },
    "set_alt_use_mode": {
        "meaning": "Right-click/alternate-use utility; normal use unchanged unless authored.",
        "params": {"mode": "mobility|generated_buff|light|none", "mobilityMode": "recall_home|blink_to_cursor", "rangeTiles": "0..80", "cooldownTicks": "0..3600", "safeTileOnly": "true", "generatedBuff": "same shape as apply_player_effect_on_use.generatedBuff"},
    },
    "hold_item_effect": {
        "meaning": "Held-item utility: light or short generated buff refreshed while held.",
        "params": {"lightStrength": "0..1.5", "lightColorName": "named color", "generatedBuff": "generated buff object"},
    },
    "extractinator_output": {
        "meaning": "Explicit Extractinator material output via dedicated proxy item.",
        "params": {"resultType": "Terraria item id", "stack": "1..999"},
    },
    "use_affordance": {
        "meaning": "Non-damaging use/draw feel; never changes gameplay.",
        "params": {"autoReuse": "bool", "useTurn": "bool", "channelUse": "bool", "itemScale": "0.55..1.55", "offsetPx": "holdout x/y -80..80", "useFantasy": "throw|stab|swing|slam|drink|plant|channel|equip|place", "heldVisibility": "show_item|hide_item|show_projectile|show_both", "releaseTiming": "instant|early|mid_swing|on_contact|on_release", "handPose": "short|two_hand|overhead|throw|staff|held_out|none", "spawnStyle": "from_hand|at_tip|centered|impact_only|world_anchor", "rotationMode": "face_velocity|spin|fixed|swing_locked|random", "drawDuringUse": "bool", "trailMode": "none|afterimage|dust|sprite_stamp|ribbon", "projectileSizePolicy": "authored|inherit_parent_floor"},
    },
    "consumption_behavior": {
        "meaning": "Consumable-use behavior; consumeChancePercent controls stack spend; no loot/spawn.",
        "params": {"consumeChancePercent": "0..100; 100 normal consume; 0 never consume"},
    },
    "ammo_behavior": {
        "meaning": "Vanilla ammo identity for generated ammo stacks; projectile behavior belongs to weapon/projectile calls.",
        "params": {"ammoFor": "arrow|bullet|empty"},
    },
    "use_condition": {
        "meaning": "Side-effect-free CanUseItem condition; blocks use only.",
        "params": {"mode": "grounded|not_wet|life_above|mana_above", "minLife": "0..5000", "minMana": "0..5000"},
    },
}

FN_ALIASES = {
    "item_stats": "set_item_stats", "set_stats": "set_item_stats",
    "primary_projectile": "shoot_projectile", "fire_projectile": "shoot_projectile", "shoot": "shoot_projectile",
    "melee_attack": "perform_melee_attack", "melee": "perform_melee_attack",
    "ranged_attack": "fire_ranged_weapon", "ranged_weapon": "fire_ranged_weapon",
    "magic_attack": "cast_magic_weapon", "magic_weapon": "cast_magic_weapon",
    "summon_attack": "summon_combat_entity", "summon_entity": "summon_combat_entity",
    "spawn_fragments": "spawn_secondary_projectiles", "secondary_projectiles": "spawn_secondary_projectiles", "child_projectiles": "spawn_secondary_projectiles",
    "on_hit": "apply_on_hit_effect", "hit_effect": "apply_on_hit_effect",
    "particles": "spawn_contact_particles", "contact_particles": "spawn_contact_particles", "dust": "spawn_contact_particles",
    "trail": "leave_trail_or_field", "visual_trail": "leave_trail_or_field", "field": "leave_trail_or_field",
    "player_effect": "apply_player_effect_on_use", "use_effect": "apply_player_effect_on_use", "buff_on_use": "apply_player_effect_on_use",
    "tool": "tool_capability", "tool_stats": "tool_capability",
    "light": "emit_light", "runtime_light": "emit_light",
    "mobility": "mobility_effect", "blink": "mobility_effect", "recall": "mobility_effect",
    "alt_use": "set_alt_use_mode", "right_click": "set_alt_use_mode",
    "hold_effect": "hold_item_effect", "held_effect": "hold_item_effect",
    "extractinator": "extractinator_output",
    "vfx_cue": "visual_effect_cue", "visual_cue": "visual_effect_cue", "effect_cue": "visual_effect_cue", "visual_effect": "visual_effect_cue",
    "affordance": "use_affordance", "use_feel": "use_affordance", "item_feel": "use_affordance",
    "consume_behavior": "consumption_behavior", "consumption": "consumption_behavior", "consume": "consumption_behavior",
    "ammo": "ammo_behavior", "ammo_identity": "ammo_behavior",
    "condition": "use_condition", "can_use": "use_condition",
    "accessory": "accessory_effect", "equip_effect": "accessory_effect", "accessory_stats": "accessory_effect",
    "armor": "armor_effect", "armor_stats": "armor_effect", "armor_effects": "armor_effect", "equip_armor": "armor_effect",
    "meter": "state_meter", "charge_meter": "state_meter", "heat_meter": "state_meter", "mode_meter": "state_meter",
    "trigger": "triggered_action", "triggered": "triggered_action", "triggered_effect": "triggered_action",
}



FORBIDDEN_WORLD_ENTITY_FN_NAMES = {
    "summon_boss", "spawn_boss", "call_boss", "boss_spawn", "boss_summon",
    "summon_npc", "spawn_npc", "create_npc", "npc_spawn", "npc_summon",
    "summon_mob", "spawn_mob", "spawn_enemy", "summon_enemy", "summon_monster", "spawn_monster",
}
FORBIDDEN_WORLD_ENTITY_FAMILIES = {
    "boss", "npc", "mob", "enemy", "monster", "town_npc", "townnpc", "critter",
    "slime", "zombie", "skeleton", "demon", "goblin", "worm", "boss_npc",
}
SAFE_SUMMON_FAMILIES = {"minion", "sentry", "turret", "pet_attack", "light_pet"}
STATE_METER_TRIGGERS = {"on_use", "on_alt_use", "on_hit_npc", "on_kill_npc", "on_projectile_impact", "while_held", "while_equipped"}
TRIGGERED_ACTION_TRIGGERS = STATE_METER_TRIGGERS | {"on_low_life", "after_not_hit_for_ticks", "while_moving", "while_airborne", "while_in_water"}
TRIGGERED_ACTION_KINDS = {
    "grant_charge", "spend_charge", "apply_generated_buff", "apply_vanilla_buff",
    "emit_light", "spawn_secondary_projectiles", "mobility_effect", "temporary_stat_boost",
    "spawn_particles", "set_mode", "cycle_mode",
}

NUMERIC_LIMITS = {
    "useTimeTicks": (10.0, 150.0), "shotCount": (1.0, 8.0), "pierce": (-1.0, 10.0),
    "aoeRadiusTiles": (0.0, 10.0), "homingStrength": (0.0, 1.0), "lifetimeTicks": (25.0, 900.0),
    "extraUpdates": (0.0, 3.0), "rangeTiles": (4.0, 120.0), "reliability": (0.45, 1.25),
    "selfLockTicks": (0.0, 120.0), "missPunish": (0.0, 1.0), "spreadRadians": (0.0, 0.75),
    "speed": (3.0, 18.0), "splitCount": (0.0, 8.0), "chainCount": (0.0, 6.0),
    "trailLength": (0.0, 24.0), "burstDustCap": (0.0, 40.0), "fieldRadiusTiles": (0.0, 6.0),
    "fieldLifetimeTicks": (0.0, 240.0), "secondaryDamageMultiplier": (0.0, 1.0),
    "secondarySpreadRadians": (0.0, 1.2), "secondaryLifetimeTicks": (5.0, 180.0), "sameTargetBias": (0.0, 1.0),
    "craftYield": (1.0, 999.0),
    "healLife": (0.0, 500.0), "healMana": (0.0, 500.0), "buffType": (0.0, 1024.0), "buffTime": (0.0, 21600.0),
    "pickPower": (0.0, 230.0), "axePower": (0.0, 50.0), "hammerPower": (0.0, 120.0),
    "lightStrength": (0.0, 1.5), "durationTicks": (1.0, 21600.0), "cooldownTicks": (0.0, 3600.0),
    "resultType": (0.0, 9999.0), "stack": (0.0, 999.0), "minLife": (0.0, 5000.0), "minMana": (0.0, 5000.0),
    "consumeChancePercent": (0.0, 100.0),
    "scale": (0.15, 5.0), "density": (0.0, 1.0), "duration": (3.0, 120.0), "alpha": (0.0, 1.0), "spread": (0.0, 2.0), "jitter": (0.0, 1.5), "startTick": (0.0, 120.0), "repeatEvery": (0.0, 120.0),
    "maxValue": (1.0, 20.0), "initialValue": (0.0, 20.0), "gainOnUse": (0.0, 20.0), "gainOnHit": (0.0, 20.0),
    "gainOnKill": (0.0, 20.0), "spendOnUse": (0.0, 20.0), "spendOnAltUse": (0.0, 20.0),
    "decayPerSecond": (0.0, 20.0), "modeCount": (0.0, 8.0), "requiredValue": (0.0, 20.0), "spendValue": (0.0, 20.0),
}

INT_FIELDS = {"useTimeTicks", "lifetimeTicks", "shotCount", "pierce", "extraUpdates", "splitCount", "chainCount", "trailLength", "burstDustCap", "fieldLifetimeTicks", "craftYield", "healLife", "healMana", "buffType", "buffTime", "pickPower", "axePower", "hammerPower", "durationTicks", "cooldownTicks", "resultType", "stack", "minLife", "minMana", "consumeChancePercent", "maxValue", "initialValue", "gainOnUse", "gainOnHit", "gainOnKill", "spendOnUse", "spendOnAltUse", "modeCount", "requiredValue", "spendValue"}


def _intish(field: str, value: float) -> int | float:
    return int(round(value)) if field in INT_FIELDS or field.endswith("Ticks") else round(value, 3)


def _norm_name(x: Any) -> str:
    return str(x or "").strip().lower().replace("-", "_").replace(" ", "_")


def _num(value: Any, default: float | None = None) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _clamp(value: Any, field: str, default: float | None = None) -> float | None:
    x = _num(value, default)
    if x is None:
        return None
    lo, hi = NUMERIC_LIMITS[field]
    return max(lo, min(hi, x))


def _enum(value: Any, allowed: set[str], fallback: str | None = None) -> str | None:
    v = _norm_name(value)
    if allowed is MOVEMENTS:
        v = MOVEMENT_ALIASES.get(v, v)
    elif allowed is DELIVERIES:
        v = DELIVERY_ALIASES.get(v, v)
    elif allowed is EFFECTS:
        v = EFFECT_ALIASES.get(v, v)
    elif allowed is ONHITS:
        v = ONHIT_ALIASES.get(v, v)
    if v in allowed:
        return v
    return fallback


def _forbidden_world_entity_rejection(raw: dict[str, Any], fn: str, params: dict[str, Any], index: int) -> dict[str, Any] | None:
    """Hard safety boundary: generated items may not spawn bosses/NPCs/mobs.

    Minions/sentries/light pets are projectile-owned runtime concepts; world NPC/boss/mob
    creation is not part of UnlimitedCraft authoring and is rejected rather than downgraded.
    """
    norm_fn = _norm_name(fn)
    if norm_fn in FORBIDDEN_WORLD_ENTITY_FN_NAMES:
        return {"index": index, "fn": fn, "reason": "forbidden_world_entity_spawn", "policy": "boss_npc_mob_spawn_disabled"}
    if norm_fn == "summon_combat_entity":
        family = _norm_name(params.get("family") or params.get("entity") or params.get("kind") or params.get("mob") or params.get("npc"))
        if family and family not in SAFE_SUMMON_FAMILIES:
            if family in FORBIDDEN_WORLD_ENTITY_FAMILIES or any(x in family for x in ("boss", "npc", "mob", "enemy", "monster")):
                return {"index": index, "fn": fn, "family": family, "reason": "forbidden_world_entity_spawn", "policy": "only_minion_sentry_turret_projectile_summons"}
    if norm_fn == "triggered_action":
        action = _norm_name(params.get("action") or params.get("fn") or params.get("effect"))
        if action in FORBIDDEN_WORLD_ENTITY_FN_NAMES or any(x in action for x in ("boss", "npc", "mob", "enemy", "monster")):
            return {"index": index, "fn": fn, "action": action, "reason": "forbidden_world_entity_spawn", "policy": "triggered_actions_cannot_spawn_world_entities"}
    return None


def _compile_state_meter_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, call in enumerate(calls):
        raw_id = _norm_name(call.get("id") or call.get("meterId") or call.get("name") or f"meter_{i+1}")
        meter_id = re.sub(r"[^a-z0-9_]+", "_", raw_id)[:32].strip("_") or f"meter_{i+1}"
        if meter_id in seen:
            meter_id = f"{meter_id}_{i+1}"[:32]
        seen.add(meter_id)
        row = {
            "id": meter_id,
            "label": str(call.get("label") or call.get("name") or meter_id)[:48],
            "maxValue": int(_clamp(call.get("maxValue"), "maxValue", 3) or 3),
            "initialValue": int(_clamp(call.get("initialValue"), "initialValue", 0) or 0),
            "gainOnUse": int(_clamp(call.get("gainOnUse"), "gainOnUse", 0) or 0),
            "gainOnHit": int(_clamp(call.get("gainOnHit"), "gainOnHit", 0) or 0),
            "gainOnKill": int(_clamp(call.get("gainOnKill"), "gainOnKill", 0) or 0),
            "spendOnUse": int(_clamp(call.get("spendOnUse"), "spendOnUse", 0) or 0),
            "spendOnAltUse": int(_clamp(call.get("spendOnAltUse"), "spendOnAltUse", 0) or 0),
            "decayPerSecond": round(_clamp(call.get("decayPerSecond"), "decayPerSecond", 0) or 0, 3),
            "cooldownTicks": int(_clamp(call.get("cooldownTicks"), "cooldownTicks", 0) or 0),
            "modeCount": int(_clamp(call.get("modeCount"), "modeCount", 0) or 0),
        }
        if row["initialValue"] > row["maxValue"]:
            row["initialValue"] = row["maxValue"]
        out.append(row)
        if len(out) >= 4:
            break
    return out


def _compile_triggered_action_calls(calls: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    out: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for call in calls:
        trigger = _norm_name(call.get("trigger"))
        action = _norm_name(call.get("action") or call.get("kind") or call.get("effect"))
        idx = call.get("_index")
        if trigger not in TRIGGERED_ACTION_TRIGGERS:
            rejected.append({"index": idx, "fn": "triggered_action", "trigger": trigger, "reason": "unsupported_trigger_intent"})
            continue
        if action not in TRIGGERED_ACTION_KINDS:
            rejected.append({"index": idx, "fn": "triggered_action", "action": action, "reason": "unsupported_action_intent"})
            continue
        if any(x in action for x in ("boss", "npc", "mob", "enemy", "monster")):
            rejected.append({"index": idx, "fn": "triggered_action", "action": action, "reason": "forbidden_world_entity_spawn"})
            continue
        row = {
            "trigger": trigger,
            "action": action,
            "meterId": re.sub(r"[^a-z0-9_]+", "_", _norm_name(call.get("meterId") or call.get("id")))[:32],
            "requiredValue": int(_clamp(call.get("requiredValue"), "requiredValue", 0) or 0),
            "spendValue": int(_clamp(call.get("spendValue"), "spendValue", 0) or 0),
            "cooldownTicks": int(_clamp(call.get("cooldownTicks"), "cooldownTicks", 0) or 0),
            "note": str(call.get("note") or "")[:80],
        }
        out.append(row)
        if len(out) >= 8:
            break
    return out, rejected


def normalize_runtime_plan_inplace(data: dict[str, Any]) -> dict[str, Any]:
    """Canonicalize runtimePlan shape without making design choices."""
    rp = data.get("runtimePlan") if isinstance(data.get("runtimePlan"), dict) else {}
    if not rp:
        for key in ("enginePlan", "runtimeAuthoring", "engineRuntimePlan"):
            val = data.get(key)
            if isinstance(val, dict):
                rp = val
                data["runtimePlan"] = rp
                break
    if not isinstance(rp, dict):
        return data
    calls = rp.get("engineCalls") if isinstance(rp.get("engineCalls"), list) else []
    prev_norm = rp.get("_normalization") if isinstance(rp.get("_normalization"), dict) else {}
    prev_dropped = prev_norm.get("droppedCalls") if isinstance(prev_norm.get("droppedCalls"), list) else []
    out = []
    dropped = list(prev_dropped)
    prev_rejected = prev_norm.get("rejectedEngineCalls") if isinstance(prev_norm.get("rejectedEngineCalls"), list) else []
    rejected = list(prev_rejected)
    for i, raw in enumerate(calls):
        if not isinstance(raw, dict):
            dropped.append({"index": i, "reason": "not_object", "rawType": type(raw).__name__})
            continue
        original_fn = str(raw.get("fn") or raw.get("function") or raw.get("name") or "").strip()
        fn = _norm_name(original_fn)
        fn = FN_ALIASES.get(fn, fn)
        params = raw.get("params") if isinstance(raw.get("params"), dict) else {k: v for k, v in raw.items() if k not in {"fn", "function", "name"}}
        params = params if isinstance(params, dict) else {}
        hard_reject = _forbidden_world_entity_rejection(raw, fn or original_fn, params, i)
        if hard_reject:
            rejected.append(hard_reject)
            continue
        if fn not in ENGINE_FN_CATALOG_V2:
            dropped.append({"index": i, "reason": "unknown_fn", "fn": original_fn})
            continue
        for expanded_fn, expanded_params in _expand_semantic_runtime_call(fn, params):
            hard_reject = _forbidden_world_entity_rejection(raw, expanded_fn, expanded_params, i)
            if hard_reject:
                rejected.append(hard_reject)
                continue
            if expanded_fn not in ENGINE_FN_CATALOG_V2:
                dropped.append({"index": i, "reason": "semantic_expand_unknown_fn", "fn": expanded_fn, "from": original_fn})
                continue
            row = {"fn": expanded_fn, "params": expanded_params, "_index": i, "_rawFn": original_fn}
            if expanded_fn != fn:
                row["_semanticFn"] = fn
            out.append(row)
    rp["engineCalls"] = out
    rp["_normalization"] = {"api": ENGINE_RUNTIME_API_VERSION, "inputCallCount": len(calls), "acceptedCallCount": len(out), "droppedCalls": dropped[:12], "rejectedEngineCalls": rejected[:16]}
    data["runtimePlan"] = rp
    return data


def runtime_plan(data: dict[str, Any]) -> dict[str, Any]:
    rp = data.get("runtimePlan") if isinstance(data.get("runtimePlan"), dict) else {}
    return rp if isinstance(rp, dict) else {}


STRUCTURAL_RUNTIME_CALL_KEYS = {"fn", "function", "name", "op", "type", "kind", "call"}
STRUCTURAL_PARAM_CONTAINER_KEYS = {"params", "args", "arguments", "payload", "values"}
STRUCTURAL_NUMERIC_PARAM_ALIASES = {
    "use_time": "useTimeTicks", "usetime": "useTimeTicks", "use_ticks": "useTimeTicks", "use_time_ticks": "useTimeTicks",
    "animation_time": "useAnimationTicks", "use_animation": "useAnimation",
    "shot_count": "shotCount", "shots": "shotCount", "projectile_count": "shotCount", "projectiles": "shotCount",
    "homing": "homingStrength", "homing_strength": "homingStrength",
    "projectile_speed": "speed", "projectilespeed": "speed", "velocity": "speed",
    "range": "rangeTiles", "range_tiles": "rangeTiles",
    "lifetime": "lifetimeTicks", "time_left": "lifetimeTicks", "timeleft": "lifetimeTicks", "duration": "lifetimeTicks",
    "aoe": "aoeRadiusTiles", "aoe_radius": "aoeRadiusTiles", "radius": "aoeRadiusTiles", "radius_tiles": "aoeRadiusTiles",
    "spread": "spreadRadians", "spread_radians": "spreadRadians",
    "extra_updates": "extraUpdates",
    "damage_class": "damageClass", "result_kind": "resultKind", "max_stack": "maxStack", "craft_yield": "craftYield",
    "buff_time": "buffTime", "buff_type": "buffType", "pick_power": "pickPower", "axe_power": "axePower", "hammer_power": "hammerPower",
    "ammo_for": "ammoFor", "armor_slot": "armorSlot",
    "runtime_family": "runtimeFamily", "weapon_family": "weaponFamily", "projectile_family": "projectileFamily",
    "self_lock": "selfLockTicks", "self_lock_ticks": "selfLockTicks", "miss_punish": "missPunish",
    "damage_multiplier": "damageMultiplier", "pull_strength": "pullStrength", "debuff_hint": "debuffHint",
    "light_strength": "lightStrength", "light_color": "lightColorName", "color": "lightColorName",
    "safe_tile_only": "safeTileOnly", "cooldown": "cooldownTicks", "cooldown_ticks": "cooldownTicks",
    "consume_chance": "consumeChancePercent", "consume_chance_percent": "consumeChancePercent",
}
STRUCTURAL_INTISH_PARAM_FIELDS = INT_FIELDS | {"damage", "useAnimation", "maxStack", "defense", "rarity", "value", "chainCount", "count"}


def _try_parse_jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return value


def _canonical_structural_key(key: Any) -> str:
    raw = str(key or "").strip()
    if not raw:
        return raw
    norm = _norm_name(raw)
    return STRUCTURAL_NUMERIC_PARAM_ALIASES.get(norm, raw)


def _structural_scalar(value: Any, key: str = "") -> Any:
    if isinstance(value, str):
        text = value.strip()
        lower = text.lower()
        if lower in {"true", "yes", "y", "on"}:
            return True
        if lower in {"false", "no", "n", "off"}:
            return False
        # Code-only repair for obvious numeric strings such as "24", "24 ticks",
        # "3 shots", "0.35". This preserves authored numbers instead of asking
        # the LLM to rewrite an otherwise good item.
        m = re.match(r"^[+\-]?(?:\d+(?:\.\d*)?|\.\d+)", text.replace(",", "."))
        if m and (key in STRUCTURAL_INTISH_PARAM_FIELDS or key.endswith("Ticks") or any(ch.isdigit() for ch in text)):
            try:
                x = float(m.group(0))
                if math.isfinite(x):
                    if key in STRUCTURAL_INTISH_PARAM_FIELDS or key.endswith("Ticks"):
                        return int(round(x))
                    return x
            except ValueError:
                pass
    return value


def _structural_params(raw_params: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fixes: list[dict[str, Any]] = []
    raw_params = _try_parse_jsonish(raw_params)
    if not isinstance(raw_params, dict):
        return {}, fixes
    out: dict[str, Any] = {}
    for k, v in raw_params.items():
        new_key = _canonical_structural_key(k)
        if new_key != k:
            fixes.append({"kind": "param_alias", "from": str(k), "to": new_key})
        v2 = _try_parse_jsonish(v)
        if isinstance(v2, dict):
            nested, nested_fixes = _structural_params(v2)
            v2 = nested
            fixes.extend(nested_fixes[:8])
        elif isinstance(v2, list):
            v2 = [_structural_scalar(_try_parse_jsonish(x), new_key) for x in v2]
        else:
            scalar = _structural_scalar(v2, new_key)
            if scalar is not v2 and scalar != v2:
                fixes.append({"kind": "scalar_parse", "field": new_key, "from": str(v2)[:48], "to": scalar})
            v2 = scalar
        out[new_key] = v2
    return out, fixes


def _structural_call_from_mapping_key(fn: str, value: Any) -> dict[str, Any] | None:
    norm = FN_ALIASES.get(_norm_name(fn), _norm_name(fn))
    if norm not in ENGINE_FN_CATALOG_V2:
        return None
    params, _fixes = _structural_params(value if isinstance(value, dict) else {})
    return {"fn": norm, "params": params}


def _structural_normalize_call(raw: Any, index: int) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    fixes: list[dict[str, Any]] = []
    raw = _try_parse_jsonish(raw)
    if not isinstance(raw, dict):
        return None, fixes
    # Common wrapper shapes: {"call": {...}}, {"engineCall": {...}}.
    for wrapper_key in ("call", "engineCall", "engine_call"):
        wrapped = raw.get(wrapper_key)
        if isinstance(wrapped, dict):
            inner, inner_fixes = _structural_normalize_call(wrapped, index)
            if inner is not None:
                fixes.append({"kind": "call_wrapper_unwrap", "field": wrapper_key, "index": index})
                fixes.extend(inner_fixes[:12])
                return inner, fixes
    # Mapping shorthand: {"shoot_projectile": {"shot_count": 3}}.
    if not any(k in raw for k in STRUCTURAL_RUNTIME_CALL_KEYS):
        for k, v in raw.items():
            mapped = _structural_call_from_mapping_key(str(k), v)
            if mapped is not None:
                fixes.append({"kind": "mapping_call", "from": str(k), "to": mapped["fn"], "index": index})
                return mapped, fixes
    original_fn = raw.get("fn") or raw.get("function") or raw.get("name") or raw.get("op") or raw.get("type") or raw.get("kind")
    fn = FN_ALIASES.get(_norm_name(original_fn), _norm_name(original_fn))
    if original_fn and fn != _norm_name(original_fn):
        fixes.append({"kind": "fn_alias", "from": str(original_fn), "to": fn, "index": index})
    params_raw = None
    for pk in STRUCTURAL_PARAM_CONTAINER_KEYS:
        if isinstance(raw.get(pk), dict) or isinstance(raw.get(pk), str):
            params_raw = raw.get(pk)
            if pk != "params":
                fixes.append({"kind": "params_alias", "from": pk, "to": "params", "index": index})
            break
    if params_raw is None:
        params_raw = {k: v for k, v in raw.items() if k not in STRUCTURAL_RUNTIME_CALL_KEYS | STRUCTURAL_PARAM_CONTAINER_KEYS}
    params, param_fixes = _structural_params(params_raw)
    fixes.extend(param_fixes[:20])
    return {"fn": fn, "params": params}, fixes


def structural_repair_runtime_plan_inplace(data: dict[str, Any]) -> dict[str, Any]:
    """Code-only repair for crooked runtimePlan shape when authored data is present.

    This is not a design/balance layer and never reads prose to invent mechanics. It only
    preserves obvious authored parameters that were placed in old/loose shapes, so the
    LLM is not called again when numbers and abilities are already concrete.
    """
    report: dict[str, Any] = {"schema": "infini.runtime-structural-repair.v1", "applied": False, "fixes": []}
    rp = data.get("runtimePlan")
    rp = _try_parse_jsonish(rp)
    if not isinstance(rp, dict):
        for key in ("enginePlan", "runtimeAuthoring", "engineRuntimePlan", "runtime_plan", "runtime"):
            val = _try_parse_jsonish(data.get(key))
            if isinstance(val, dict):
                rp = val
                data["runtimePlan"] = rp
                report["fixes"].append({"kind": "runtime_plan_alias", "from": key, "to": "runtimePlan"})
                break
    if not isinstance(rp, dict):
        return report
    calls_raw = None
    for key in ("engineCalls", "engine_calls", "calls", "actions", "action", "call"):
        if key in rp:
            calls_raw = _try_parse_jsonish(rp.get(key))
            if key != "engineCalls":
                report["fixes"].append({"kind": "engine_calls_alias", "from": key, "to": "engineCalls"})
            break
    if calls_raw is None:
        # Mapping shorthand at runtimePlan level: {"shoot_projectile": {...}}.
        mapped_calls = []
        for k, v in list(rp.items()):
            mapped = _structural_call_from_mapping_key(str(k), v)
            if mapped is not None:
                mapped_calls.append(mapped)
                report["fixes"].append({"kind": "runtime_plan_mapping_call", "from": str(k), "to": mapped["fn"]})
        calls_raw = mapped_calls if mapped_calls else rp.get("engineCalls")
    if isinstance(calls_raw, dict):
        mapped = []
        if any(k in calls_raw for k in STRUCTURAL_RUNTIME_CALL_KEYS):
            mapped = [calls_raw]
            report["fixes"].append({"kind": "single_call_object_to_list"})
        else:
            for k, v in calls_raw.items():
                call = _structural_call_from_mapping_key(str(k), v)
                if call is not None:
                    mapped.append(call)
            if mapped:
                report["fixes"].append({"kind": "engine_calls_mapping_to_list", "count": len(mapped)})
        calls_raw = mapped
    if not isinstance(calls_raw, list):
        return report
    out = []
    for i, raw in enumerate(calls_raw):
        call, fixes = _structural_normalize_call(raw, i)
        if call is not None:
            out.append(call)
        report["fixes"].extend(fixes[:24])
    if out:
        rp["engineCalls"] = out
        data["runtimePlan"] = rp
    # De-duplicate noisy identical fixes for compact debug.
    compact = []
    seen = set()
    for row in report["fixes"]:
        key = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        if key not in seen:
            compact.append(row)
            seen.add(key)
    report["fixes"] = compact[:48]
    report["applied"] = bool(report["fixes"])
    return report


def find_call(data_or_plan: dict[str, Any], fn: str) -> dict[str, Any]:
    rp = data_or_plan if isinstance(data_or_plan.get("engineCalls"), list) else runtime_plan(data_or_plan)
    for raw in rp.get("engineCalls") or []:
        if isinstance(raw, dict) and _norm_name(raw.get("fn")) == fn:
            params = raw.get("params") if isinstance(raw.get("params"), dict) else raw
            return params if isinstance(params, dict) else {}
    return {}


def all_calls(data_or_plan: dict[str, Any], fn: str) -> list[dict[str, Any]]:
    """Return every call of a function. The author can stack compatible calls; compiler aggregates only executable-compatible shapes."""
    rp = data_or_plan if isinstance(data_or_plan.get("engineCalls"), list) else runtime_plan(data_or_plan)
    out: list[dict[str, Any]] = []
    want = _norm_name(fn)
    for raw in rp.get("engineCalls") or []:
        if isinstance(raw, dict) and _norm_name(raw.get("fn")) == want:
            params = raw.get("params") if isinstance(raw.get("params"), dict) else raw
            if isinstance(params, dict):
                row = dict(params)
                if "_index" in raw: row["_index"] = raw.get("_index")
                if "_rawFn" in raw: row["_rawFn"] = raw.get("_rawFn")
                out.append(row)
    return out


def _first_non_empty(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return default


def _merged_params(calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge multiple calls of the same fn: later explicit params override earlier ones.

    This keeps Gemma free to split a design into several set_item_stats/on_hit calls
    without the runtime compiler silently discarding all but the first.
    """
    out: dict[str, Any] = {}
    for call in calls:
        if not isinstance(call, dict):
            continue
        for k, v in call.items():
            if k.startswith("_"):
                continue
            if v not in (None, "", [], {}):
                out[k] = v
    return out


def _select_primary_shoot_call(calls: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Choose one executable primary family and reject incompatible extras.

    The first authored projectile/held executor is the primary. Compatible extra
    calls may only aggregate multi-shot/spread/pierce pressure. Incompatible
    calls must not leak back into executableFields through a later-call merge.
    This is the anti-spaghetti boundary: it is based only on normalized engineCall
    fields, never on item names or prose.
    """
    if not calls:
        return {}, []
    primary = calls[0] if isinstance(calls[0], dict) else {}
    primary_delivery = _enum(primary.get("delivery"), DELIVERIES, "shoot")
    primary_movement = _enum(primary.get("movement"), MOVEMENTS, "straight")
    compatible: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    total_shots = 0
    max_spread = 0.0
    max_pierce: float = 0.0
    for sc in calls:
        if not isinstance(sc, dict):
            continue
        d = _enum(sc.get("delivery"), DELIVERIES, primary_delivery)
        m = _enum(sc.get("movement"), MOVEMENTS, primary_movement)
        same_primary = d == primary_delivery and m == primary_movement
        if same_primary:
            compatible.append(sc)
            total_shots += int(_clamp(sc.get("shotCount"), "shotCount", 1) or 1)
            max_spread = max(max_spread, float(_clamp(sc.get("spreadRadians"), "spreadRadians", 0) or 0))
            pv = _clamp(sc.get("pierce"), "pierce", 0)
            if pv == -1:
                max_pierce = -1
            elif max_pierce != -1:
                max_pierce = max(max_pierce, float(pv or 0))
        else:
            rejected.append({"index": sc.get("_index"), "delivery": d, "movement": m, "reason": "runtime_one_primary_family"})
    selected = _merged_params(compatible) if compatible else dict(primary)
    if total_shots > 0:
        selected["shotCount"] = min(8, total_shots)
        selected["spreadRadians"] = max(float(selected.get("spreadRadians") or 0), max_spread)
        selected["pierce"] = max(float(selected.get("pierce") or 0), max_pierce)
    return selected, rejected


def _call_by_index(calls: list[dict[str, Any]], index: Any) -> dict[str, Any]:
    for call in calls:
        if isinstance(call, dict) and call.get("_index") == index:
            return call
    return {}


def _recover_rejected_primary_as_swing_secondary(
    primary: dict[str, Any],
    rejected: list[dict[str, Any]],
    all_shoot_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    """Recover a second authored attack as an explicit swing secondary.

    This is not prompt/prose inference and it is not a new category router.  It only
    handles a structural ambiguity the LLM can produce today: a melee primary plus
    a second incompatible projectile primary.  Current C# has real on-hit swing
    secondary projectiles, so preserving the extra call there is safer than either
    letting it override the primary or deleting it.
    """
    if not rejected:
        return {}
    primary_delivery = _enum(primary.get("delivery"), DELIVERIES, "")
    primary_family = _enum(primary.get("runtimeFamily"), RUNTIME_FAMILIES, primary_delivery)
    if primary_delivery not in {"swing", "thrust"} and primary_family not in {"swing", "thrust"}:
        return {}

    for row in rejected:
        src = _call_by_index(all_shoot_calls, row.get("index"))
        if not src:
            continue
        delivery = _enum(src.get("delivery"), DELIVERIES, "")
        family = _enum(src.get("runtimeFamily"), RUNTIME_FAMILIES, delivery)
        if delivery not in {"shoot", "throw", "cast"} and family not in {"shoot", "throw", "cast"}:
            continue
        shape = str(src.get("projectileShape") or src.get("projectileFamily") or src.get("projectileTrail") or "shard").strip()[:80]
        material = str(src.get("material") or src.get("projectileTrail") or src.get("projectileFamily") or shape or "shard").strip()[:40]
        count = int(max(1, min(3, _clamp(src.get("shotCount"), "shotCount", 1) or 1)))
        life = int(max(6, min(120, _num(src.get("lifetimeTicks"), 24) or 24)))
        spread = float(_clamp(src.get("spreadRadians"), "secondarySpreadRadians", 0.18) or 0.18)
        dmg = float(_clamp(src.get("damageMultiplier"), "secondaryDamageMultiplier", 0.25) or 0.25)
        return {
            "_index": src.get("_index"),
            "_rawFn": "recovered_rejected_primary",
            "_recoveredFromRejectedPrimary": True,
            "trigger": "on_hit",
            "count": count,
            "damageMultiplier": round(max(0.08, min(0.35, dmg)), 3),
            "spreadRadians": round(max(0.0, min(1.2, spread)), 3),
            "lifetimeTicks": life,
            "projectileShape": shape or "shard",
            "material": material or "shard",
        }
    return {}


# Small effect ontology, not a per-item exception list.
# Parent knowledge should eventually expose canonical effect capabilities directly
# (burn/poison/frostburn/shadowflame).  Until then, a tiny alias layer maps common
# elemental trait words to existing runtime onHit values without reading prompt prose.
PARENT_EFFECT_TRAIT_ALIASES: dict[str, str] = {
    "flaming": "burn",
    "fire": "burn",
    "burning": "burn",
    "burn": "burn",
    "poison": "poison",
    "poisoned": "poison",
    "venom": "poison",
    "toxic": "poison",
    "frostburn": "frostburn",
    "frost": "frostburn",
    "shadowflame": "shadowflame",
}


def _iter_parent_tags(data: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    knowledge = data.get("itemKnowledge") if isinstance(data.get("itemKnowledge"), dict) else {}
    for parent in knowledge.get("parents") or []:
        if not isinstance(parent, dict):
            continue
        for tag in parent.get("tags") or []:
            t = _norm_name(tag)
            if t:
                tags.append(t)
        signals = parent.get("signals") if isinstance(parent.get("signals"), dict) else {}
        mech = signals.get("mechanicPower") if isinstance(signals.get("mechanicPower"), dict) else {}
        behavior = mech.get("weaponBehavior") if isinstance(mech.get("weaponBehavior"), dict) else {}
        for tag in behavior.get("behaviorTags") or []:
            t = _norm_name(tag)
            if t:
                tags.append(t)
    return list(dict.fromkeys(tags))


def _parent_grounded_onhit(data: dict[str, Any]) -> tuple[str, str]:
    """Return a parent-backed elemental on-hit effect, if unambiguous.

    This never reads free-form prompt/tooltip and therefore does not become category
    keyword routing. It only preserves concrete mechanics already present in parent
    runtime/knowledge tags. The alias map is deliberately tiny; broad item-specific
    behavior should come from richer parent probes, not a growing exception table.
    """
    for tag in _iter_parent_tags(data):
        if tag in PARENT_EFFECT_TRAIT_ALIASES:
            return PARENT_EFFECT_TRAIT_ALIASES[tag], tag
    return "", ""


def _material_color_name(materials: list[str], fallback: str = "dull") -> str:
    blob = " ".join(str(x or "").lower() for x in materials)
    if any(w in blob for w in ["wood", "sawdust", "bark", "splinter", "дерев"]): return "wood brown"
    if any(w in blob for w in ["copper", "bronze", "мед"]): return "copper orange"
    if any(w in blob for w in ["iron", "steel", "metal", "silver", "wire", "металл"]): return "metal gray"
    if any(w in blob for w in ["stone", "rock", "slate", "кам"]): return "stone gray"
    if any(w in blob for w in ["sand", "sawdust", "dust"]): return "sand tan"
    if any(w in blob for w in ["slime", "gel"]): return "slime green"
    if any(w in blob for w in ["fire", "flame", "ember"]): return "flame orange"
    if any(w in blob for w in ["electric", "lightning", "spark"]): return "cyan electric"
    if any(w in blob for w in ["shadow", "corrupt", "void"]): return "shadow purple"
    if any(w in blob for w in ["holy", "star", "lunar"]): return "gold star"
    return fallback


def _material_effect_hint(materials: list[str]) -> str | None:
    blob = " ".join(str(x or "").lower() for x in materials)
    if any(w in blob for w in ["wood", "sawdust", "bark", "stone", "rock", "metal", "copper", "iron", "sand", "dust", "гряз", "дерев", "кам"]):
        return "dust"
    if any(w in blob for w in ["slime", "gel"]): return "slime"
    if any(w in blob for w in ["fire", "flame", "ember"]): return "flame"
    if any(w in blob for w in ["electric", "lightning", "spark"]): return "electric"
    if any(w in blob for w in ["shadow", "corrupt", "void"]): return "shadow"
    if any(w in blob for w in ["poison", "toxic"]): return "poison"
    if any(w in blob for w in ["holy", "star", "lunar"]): return "star"
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool): return value
    s = _norm_name(value)
    return s in {"1", "true", "yes", "y", "visual", "visual_only"}


def _semantic_param_copy(params: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in keys:
        if k in params and params.get(k) not in (None, ""):
            out[k] = params.get(k)
    return out


_WEAPON_SUBFAMILY_ALIASES: dict[str, str] = {
    "short_sword": "shortsword", "short sword": "shortsword", "broad_sword": "broadsword",
    "sword": "broadsword", "greatsword": "broadsword", "rapier": "shortsword",
    "jousting_lance": "lance", "rocket_launcher": "launcher", "spell_book": "magic_book",
    "book": "magic_book", "spellbook": "magic_book", "wand": "magic_staff", "staff": "magic_staff",
    "rod": "magic_staff", "beam_staff": "laser_staff", "channelled_beam": "laser_staff", "channeled_beam": "laser_staff",
    "minion": "summon_staff", "pet_attack": "summon_staff", "turret": "sentry_staff", "sentry": "sentry_staff",
}

def _weapon_subfamily_from_fields(*, family: Any = "", projectile_family: Any = "", runtime_family: Any = "", delivery: Any = "", ammo: Any = "", explicit: Any = "") -> str:
    explicit_norm = _norm_name(explicit)
    if explicit_norm:
        return _WEAPON_SUBFAMILY_ALIASES.get(explicit_norm, explicit_norm)[:48]
    f = _norm_name(family)
    pf = _norm_name(projectile_family)
    rt = _norm_name(runtime_family)
    dlv = _norm_name(delivery)
    am = _norm_name(ammo)
    text = " ".join(x for x in [f, pf, rt, dlv, am] if x)
    if not text:
        return ""
    for key, value in _WEAPON_SUBFAMILY_ALIASES.items():
        if key in {f, pf, dlv, am} or key in text:
            return value
    if any(x in text for x in ["shotgun", "boomstick", "onyx"]): return "shotgun"
    if any(x in text for x in ["sniper", "sdmg"]): return "sniper"
    if any(x in text for x in ["chain_gun", "chaingun", "gatligator"]): return "chain_gun"
    if "dart" in text: return "dart_weapon"
    if any(x in text for x in ["blowpipe", "blowgun"]): return "blowgun"
    if "harpoon" in text: return "harpoon"
    if "bow" in text or "arrow" in text: return "bow"
    if "gun" in text or "bullet" in text or "pistol" in text or "rifle" in text: return "gun"
    if "launcher" in text or "rocket" in text or "missile" in text: return "launcher"
    if "whip" in text or "lash" in text: return "whip"
    if "yoyo" in text: return "yoyo"
    if "flail" in text or "mace" in text or "chain" in text: return "flail"
    if any(x in text for x in ["spear", "lance", "trident", "pike", "glaive", "halberd"]): return "spear"
    if any(x in text for x in ["boomerang", "chakram", "disc"]): return "boomerang"
    if rt == "cast": return "magic_staff"
    if rt == "summon": return "summon_staff"
    if rt == "swing": return "broadsword"
    return f[:48] if f else pf[:48]

def _attack_pattern_tags_from_patch(patch: dict[str, Any], *sources: dict[str, Any]) -> list[str]:
    raw: list[str] = []
    for src in sources:
        val = src.get("attackPatternTags") or src.get("patternTags")
        if isinstance(val, list):
            raw.extend(str(x) for x in val if x not in (None, ""))
        elif isinstance(val, str) and val.strip():
            raw.extend(x.strip() for x in val.replace(";", ",").split(","))
    blob = " ".join(str(src.get(k, "")) for src in [patch, *sources] for k in [
        "weaponFamily", "weaponSubfamily", "projectileFamily", "projectileShape", "projectileMotion",
        "projectileTrail", "projectileImpact", "movement", "effect", "onHit", "delivery"
    ]).lower()
    token_blob = " " + re.sub(r"[^a-z0-9]+", " ", blob).strip() + " "

    def has_semantic_needle(needle: str) -> bool:
        phrase = re.sub(r"[^a-z0-9]+", " ", str(needle).lower()).strip()
        return bool(phrase) and f" {phrase} " in token_blob
    candidates: list[tuple[str, list[str]]] = [
        ("falling_star", ["falling", "starfall", "star_wrath", "star wrath", "meteor"]),
        ("beam", ["beam", "laser", "prism", "ray"]),
        ("shotgun_spread", ["shotgun", "spread", "scatter"]),
        ("multi_arrow", ["multi_arrow", "volley", "phantasm", "tsunami", "arrow rain"]),
        ("homing_orb", ["homing", "orb", "arcanum", "spirit flame"]),
        ("splinter_burst", ["splinter", "shard", "fragment"]),
        ("bee_swarm", ["bee", "honey", "beenade"]),
        ("chain_flail", ["flail", "chain", "mace", "anchor"]),
        ("whip_lash", ["whip", "lash"]),
        ("summon_sentry", ["sentry", "turret", "hydra", "portal"]),
        ("growing_minion", ["dragon", "stardust dragon", "segment"]),
        ("bounce", ["bounce", "ricochet"]),
        ("boomerang_return", ["boomerang", "returning", "returning_glaive"]),
        ("explosive", ["explosion", "explode", "rocket", "grenade", "blast"]),
        ("elemental_debuff", ["burn", "frostburn", "poison", "shadowflame", "bleed"]),
    ]
    for tag, needles in candidates:
        if any(has_semantic_needle(n) for n in needles):
            raw.append(tag)
    out: list[str] = []
    for value in raw:
        tag = _norm_name(value)
        if tag and tag not in out:
            out.append(tag[:40])
        if len(out) >= 12:
            break
    return out

def _sound_query_from_patch(patch: dict[str, Any], *, impact: bool) -> str:
    bits = [
        patch.get("weaponSubfamily"), patch.get("weaponFamily"), patch.get("projectileFamily"),
        patch.get("movement"), patch.get("effect"), patch.get("onHit") if impact else patch.get("delivery"),
    ]
    bits.extend(patch.get("attackPatternTags") or [])
    words = [str(x).replace("_", " ").strip() for x in bits if x not in (None, "", [])]
    suffix = "impact hit" if impact else "use cast swing release"
    return (" ".join(dict.fromkeys(words)) + " " + suffix).strip()[:160]

def _apply_armor_slot_budget(armor: dict[str, Any]) -> None:
    slot = _norm_name(armor.get("slot")) or "body"
    # Soft Terraria-ish distribution: head carries class identity, body carries bulk, legs carry mobility.
    if slot == "head":
        caps = {"defense": 24, "movementSpeed": 0.18, "maxRunSpeed": 0.35, "jumpSpeed": 0.8, "endurance": 0.08}
    elif slot == "legs":
        caps = {"defense": 26, "genericDamage": 0.14, "meleeDamage": 0.16, "rangedDamage": 0.16, "magicDamage": 0.16, "summonDamage": 0.16, "endurance": 0.08}
    else:
        caps = {"defense": 42, "movementSpeed": 0.18, "maxRunSpeed": 0.45, "jumpSpeed": 1.0, "genericCrit": 12, "endurance": 0.18}
    clamped: dict[str, Any] = {}
    for field, cap in caps.items():
        if field in armor and isinstance(armor.get(field), (int, float)) and armor[field] > cap:
            clamped[field] = {"from": armor[field], "to": cap}
            armor[field] = int(cap) if isinstance(cap, int) else round(float(cap), 3)
    if clamped:
        armor["slotBudgetClamps"] = clamped


def _expand_semantic_runtime_call(fn: str, params: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Lower explicit Terraria-family engine calls into the compact runtime executor.

    This is not name aliasing: the planner authors a weapon family (spear/flail/yoyo/whip,
    bow/gun/launcher, staff/book, minion/sentry), then this compiler emits the small set
    of executable runtime fields the current C# runtime actually supports.
    """
    fn = _norm_name(fn)
    p = dict(params or {})
    family = _norm_name(p.get("family") or p.get("weaponFamily") or p.get("projectileFamily") or p.get("archetype"))
    common = _semantic_param_copy(p, [
        "movement", "effect", "speed", "rangeTiles", "lifetimeTicks", "shotCount", "spreadRadians",
        "pierce", "extraUpdates", "homingStrength", "useTimeTicks", "reliability",
        "selfLockTicks", "missPunish", "projectileShape", "projectileMotion",
        "projectileTrail", "projectileImpact", "damageMultiplier", "runtimeFamily",
        "weaponSubfamily", "attackPatternTags", "soundUseSearchQuery", "soundImpactSearchQuery",
    ])

    if fn == "perform_melee_attack":
        group = _family_group(family)
        if group == "thrust":
            common.update({"runtimeFamily": "thrust", "delivery": "thrust", "movement": common.get("movement") or "straight", "weaponFamily": family or "spear"})
            common.setdefault("projectileMotion", "held thrust")
        elif group == "returning":
            common.update({"runtimeFamily": "returning", "delivery": "throw", "movement": "boomerang", "weaponFamily": family or "boomerang"})
        elif group == "flail":
            common.update({"runtimeFamily": "flail", "delivery": "flail", "movement": "flail_tether", "weaponFamily": family or "flail"})
            common.setdefault("projectileMotion", "chain-tethered flail head")
        elif group == "yoyo":
            common.update({"runtimeFamily": "yoyo", "delivery": "yoyo", "movement": "yoyo_hover", "weaponFamily": "yoyo"})
            common.setdefault("projectileMotion", "channelled yoyo hover")
        elif group == "whip":
            common.update({"runtimeFamily": "whip", "delivery": "whip", "movement": "whip_lash", "weaponFamily": "whip"})
            common.setdefault("projectileMotion", "summon whip lash")
        else:
            common.update({"runtimeFamily": "swing", "delivery": "swing", "movement": common.get("movement") or "straight", "weaponFamily": family or "broadsword"})
        return [("shoot_projectile", common)]

    if fn == "fire_ranged_weapon":
        group = _family_group(family)
        if family in {"launcher", "rocket_launcher", "rocket", "missile_launcher"}:
            common.setdefault("movement", "proximity_missile")
        elif family in {"harpoon"}:
            common.setdefault("movement", "returning_glaive")
        else:
            common.setdefault("movement", "straight")
        common.update({"runtimeFamily": "shoot", "delivery": "shoot", "weaponFamily": family or "ranged", "projectileFamily": family or "ranged"})
        if p.get("ammoFor") not in (None, ""):
            common["ammoFor"] = p.get("ammoFor")
        return [("shoot_projectile", common)]

    if fn == "cast_magic_weapon":
        raw_projectile_family = _norm_name(p.get("projectileFamily"))
        if family in {"channelled_beam", "channeled_beam", "beam_staff", "laser_staff"}:
            common.setdefault("movement", "phase")
        else:
            common.setdefault("movement", "straight")

        # Important Terraria-style split: cast context decides the executor.  The
        # family/projectileFamily text is only carrier/form identity.  Do not encode
        # material+shape compounds (crystal_spear/light_spear/etc.) as magic families:
        # the same phrase may be authored as melee, thrown, ranged, or magic depending
        # on the explicit engine call/runtimeFamily/damageClass.
        projectile_form = raw_projectile_family
        weapon_family = family if _family_group(family) == "magic" else "magic"
        if family in TERRARIA_WEAPON_FAMILY_GROUPS.get("thrust", set()):
            projectile_form = projectile_form or family
        elif not projectile_form:
            # Generic form extraction only for authored cast context.  This is not a
            # runtime-family repair; it merely preserves spear/lance/glaive-shaped spell
            # visuals without deciding that those words are magic by themselves.
            if family.endswith("_spear") or "spear" in family:
                projectile_form = "spear"
            elif family.endswith("_lance") or "lance" in family:
                projectile_form = "lance"
            elif family.endswith("_glaive") or "glaive" in family:
                projectile_form = "glaive"

        common.update({"runtimeFamily": "cast", "delivery": "cast", "weaponFamily": weapon_family or "magic", "projectileFamily": projectile_form or "magic"})
        return [("shoot_projectile", common)]

    if fn == "summon_combat_entity":
        common.setdefault("movement", "orbit" if family in {"minion", "pet_attack"} else "drift")
        common.update({"runtimeFamily": "summon", "delivery": "summon", "weaponFamily": family or "minion", "projectileFamily": family or "summon"})
        return [("shoot_projectile", common)]

    return [(fn, p)]


def _runtime_family_from_fields(delivery: Any, movement: Any, weapon_family: Any = "", projectile_family: Any = "", explicit: Any = "") -> str:
    """Return explicit runtimeFamily only.

    This helper intentionally no longer performs broad behavior inference.  New
    runtime authoring must use runtimeFamily; the separate light repair below is
    the only permitted rescue path for small/local models.
    """
    explicit_norm = _enum(explicit, RUNTIME_FAMILIES, None)
    return explicit_norm if explicit_norm and explicit_norm != "none" else "none"


def _runtime_family_group_to_executor(group: str) -> str:
    if group == "thrust": return "thrust"
    if group == "returning": return "returning"
    if group in {"flail", "yoyo", "whip"}: return group
    if group == "ranged": return "shoot"
    if group == "magic": return "cast"
    if group == "summon": return "summon"
    return ""


def light_repair_runtime_family_from_fields(params: dict[str, Any]) -> tuple[str, str]:
    """Tiny, explicit, auditable repair for small models.

    This is deliberately weaker than legacy inference: it only accepts exact
    weaponFamily groups, exact delivery family words, or movement values that are
    already one-to-one executor opcodes. projectileFamily is deliberately excluded:
    it is projectile form, not an executable family signal.  If signals conflict, it
    returns none and the craft fails/asks LLM repair.
    """
    if not isinstance(params, dict):
        return "none", ""
    explicit = _enum(params.get("runtimeFamily"), RUNTIME_FAMILIES, None)
    if explicit and explicit != "none":
        return explicit, "authored_runtimeFamily"

    signals: list[tuple[str, str]] = []
    # Tiny repair treats weaponFamily as the executable weapon family.  projectileFamily
    # is only emitted projectile FORM (e.g. a magic spell can launch a spear-shaped
    # projectile), so it must not make a cast/shoot spell become a held spear.
    group = _family_group(params.get("weaponFamily"))
    fam = _runtime_family_group_to_executor(group)
    if fam:
        signals.append((fam, "weaponFamily"))

    d = _enum(params.get("delivery"), DELIVERIES, None)
    if d in {"swing", "shoot", "cast", "throw", "summon", "flail", "yoyo", "whip"}:
        signals.append((d, "delivery"))
    elif d in {"thrust", "spear"}:
        signals.append(("thrust", "delivery"))

    m = _enum(params.get("movement"), MOVEMENTS, None)
    movement_map = {
        "boomerang": "returning",
        "returning_glaive": "returning",
        "flail_tether": "flail",
        "yoyo_hover": "yoyo",
        "whip_lash": "whip",
    }
    if m in movement_map:
        signals.append((movement_map[m], "movement"))

    unique = sorted({fam for fam, _src in signals if fam and fam != "none"})
    if len(unique) != 1:
        return "none", ""
    srcs = "+".join(src for fam, src in signals if fam == unique[0])
    return unique[0], f"light:{srcs}"


def compile_runtime_plan_to_genome_patch(data: dict[str, Any]) -> dict[str, Any]:
    normalize_runtime_plan_inplace(data)
    rp = runtime_plan(data)
    if not rp:
        return {}
    shoots = all_calls(rp, "shoot_projectile")
    hits = all_calls(rp, "apply_on_hit_effect")
    particle_calls = all_calls(rp, "spawn_contact_particles")
    secondary_calls = all_calls(rp, "spawn_secondary_projectiles")
    trail_calls = all_calls(rp, "leave_trail_or_field")
    use_effect_calls = all_calls(rp, "apply_player_effect_on_use")
    tool_calls = all_calls(rp, "tool_capability")
    light_calls = all_calls(rp, "emit_light")
    vfx_cue_calls = all_calls(rp, "visual_effect_cue")
    mobility_calls = all_calls(rp, "mobility_effect")
    alt_use_calls = all_calls(rp, "set_alt_use_mode")
    hold_effect_calls = all_calls(rp, "hold_item_effect")
    extractinator_calls = all_calls(rp, "extractinator_output")
    use_affordance_calls = all_calls(rp, "use_affordance")
    consumption_calls = all_calls(rp, "consumption_behavior")
    ammo_behavior_calls = all_calls(rp, "ammo_behavior")
    use_condition_calls = all_calls(rp, "use_condition")
    accessory_calls = all_calls(rp, "accessory_effect")
    armor_calls = all_calls(rp, "armor_effect")
    state_meter_calls = all_calls(rp, "state_meter")
    triggered_action_calls = all_calls(rp, "triggered_action")
    itemstats_calls = all_calls(rp, "set_item_stats")
    shoot, rejected_primary = _select_primary_shoot_call(shoots) if shoots else ({}, [])
    hit = _merged_params(hits) if hits else {}
    itemstats = _merged_params(itemstats_calls) if itemstats_calls else {}
    patch: dict[str, Any] = {}
    norm = rp.get("_normalization") if isinstance(rp.get("_normalization"), dict) else {}
    if isinstance(norm.get("rejectedEngineCalls"), list) and norm.get("rejectedEngineCalls"):
        patch["rejectedEngineCalls"] = norm.get("rejectedEngineCalls")[:16]

    # Primary executable action: one primary family only.  Incompatible extra
    # primary calls stay visible in provenance/debug and never override final fields.
    recovered_primary_secondary = _recover_rejected_primary_as_swing_secondary(shoot, rejected_primary, shoots)
    secondary_from_rejected_primary = bool(recovered_primary_secondary)
    if recovered_primary_secondary:
        secondary_calls = [*secondary_calls, recovered_primary_secondary]
    if rejected_primary:
        patch["rejectedPrimaryCalls"] = rejected_primary[:8]
    if recovered_primary_secondary:
        patch["recoveredPrimaryConflictAsSecondary"] = {
            "sourceIndex": recovered_primary_secondary.get("_index"),
            "mode": "swing_on_hit_secondary",
            "projectileShape": recovered_primary_secondary.get("projectileShape"),
            "count": recovered_primary_secondary.get("count"),
        }

    parent_onhit, parent_onhit_source = _parent_grounded_onhit(data)
    if parent_onhit and _norm_name(hit.get("onHit")) in {"", "none"}:
        # Preserve parent-authored elemental mechanics for combat outputs without
        # routing from prompt words.  E.g. FlamingArrow + Torch should keep burn.
        hit["onHit"] = parent_onhit
        hit.setdefault("debuffHint", parent_onhit_source)
        patch["parentMechanicPreserved"] = {"kind": "onHit", "value": parent_onhit, "sourceTag": parent_onhit_source}

    raw_delivery = _norm_name(shoot.get("delivery"))
    delivery = _enum(shoot.get("delivery"), DELIVERIES, None)
    movement = _enum(shoot.get("movement"), MOVEMENTS, None)
    if raw_delivery and raw_delivery != delivery:
        patch["deliveryAlias"] = raw_delivery
    if delivery: patch["delivery"] = delivery
    if movement: patch["movement"] = movement
    if shoot.get("weaponFamily") not in (None, ""):
        patch["weaponFamily"] = _norm_name(shoot.get("weaponFamily"))[:40]
    if shoot.get("projectileFamily") not in (None, ""):
        patch["projectileFamily"] = _norm_name(shoot.get("projectileFamily"))[:40]
    if shoot.get("ammoFor") not in (None, ""):
        patch["ammoFor"] = _norm_name(shoot.get("ammoFor"))[:24]
    subfamily = _weapon_subfamily_from_fields(
        family=patch.get("weaponFamily") or shoot.get("weaponFamily"),
        projectile_family=patch.get("projectileFamily") or shoot.get("projectileFamily"),
        runtime_family=shoot.get("runtimeFamily"),
        delivery=shoot.get("delivery"),
        ammo=patch.get("ammoFor") or shoot.get("ammoFor"),
        explicit=shoot.get("weaponSubfamily") or itemstats.get("weaponSubfamily"),
    )
    if subfamily:
        patch["weaponSubfamily"] = subfamily
    explicit_runtime_family = _enum(shoot.get("runtimeFamily"), RUNTIME_FAMILIES, None)
    runtime_family = explicit_runtime_family or "none"
    repair_reason = ""
    if shoots and runtime_family == "none":
        # v0.4.30: tiny repair for weaker models.  This never reads prose and never
        # invents a family from names; it only accepts one unambiguous family signal.
        runtime_family, repair_reason = light_repair_runtime_family_from_fields(shoot)
    if shoots and runtime_family == "none":
        patch["runtimeContractError"] = "primary_attack_requires_runtimeFamily"
    else:
        patch["runtimeFamily"] = runtime_family
        if repair_reason and repair_reason != "authored_runtimeFamily":
            patch["runtimeFamilyRepair"] = repair_reason
        patch.update(_runtime_family_affordances(runtime_family, patch.get("weaponFamily") or shoot.get("weaponFamily")))

    tags = _attack_pattern_tags_from_patch(patch, shoot, hit, itemstats)
    if tags:
        patch["attackPatternTags"] = tags
    if shoot.get("soundUseSearchQuery") not in (None, ""):
        patch["soundUseSearchQuery"] = str(shoot.get("soundUseSearchQuery"))[:160]
    if shoot.get("soundImpactSearchQuery") not in (None, ""):
        patch["soundImpactSearchQuery"] = str(shoot.get("soundImpactSearchQuery"))[:160]

    # Aggregate pure VFX calls. This is still not gameplay child logic.
    particle_effects: list[str] = []
    particle_amount = 0.0
    particle_scale = 0.0
    particle_materials: list[str] = []
    for pc in particle_calls:
        eff = _enum(pc.get("effect"), EFFECTS, None)
        if eff and eff != "none":
            particle_effects.append(eff)
        particle_amount += _num(pc.get("amount"), 0) or 0
        particle_scale = max(particle_scale, _num(pc.get("scale"), 0) or 0)
        if pc.get("material") not in (None, ""):
            particle_materials.append(str(pc.get("material"))[:40])
    material_effect = _material_effect_hint(particle_materials)
    effect = _enum(_first_non_empty(*particle_effects, material_effect, shoot.get("effect")), EFFECTS, None)
    if particle_calls and not particle_effects:
        effect = "none"
    if effect:
        patch["effect"] = effect
    if particle_calls:
        patch["burstDustCap"] = int(round(max(0, min(NUMERIC_LIMITS["burstDustCap"][1], particle_amount))))
        # v0.4.13: C# distinguishes effect=none from mundane dust via DustSpawnDenom.
        # effectCode 0 is shared by none/dust for old compatibility, so denom=0 means literally no ambient dust.
        if particle_amount <= 0 or effect in {None, "none"}:
            patch["dustSpawnDenom"] = 0
            patch["burstDustCap"] = 0
        else:
            # Higher authored amount = more frequent, but still bounded; no WhiteTorch fallback in runtime.
            patch["dustSpawnDenom"] = int(max(2, min(12, round(10 - min(8, particle_amount / 5.0)))))
        if particle_scale:
            patch["vfxParticleScale"] = max(0.0, min(2.0, round(particle_scale, 3)))
        if particle_materials:
            # Human/debug lineage only; C# can ignore this safely.
            patch["vfxMaterial"] = ", ".join(dict.fromkeys(particle_materials))[:80]
            patch.setdefault("primaryColorName", _material_color_name(particle_materials))

    # Trails/fields are visual-only in this runtime. Do not let field prose become gameplay.
    rejected_trails: list[dict[str, Any]] = []
    if trail_calls:
        for t in trail_calls:
            if t.get("visualOnly") not in (None, "", True) and not _truthy(t.get("visualOnly")):
                rejected_trails.append({"index": t.get("_index"), "reason": "visualOnly_false_not_executable"})
        vals = [_clamp(t.get("trailLength"), "trailLength") for t in trail_calls if t.get("trailLength") not in (None, "")]
        vals = [v for v in vals if v is not None]
        if vals:
            patch["trailLength"] = _intish("trailLength", max(vals))
        # Preserve visual field dimensions for debug/VFX only under non-runtime keys.
        for field, out_field in [("fieldLifetimeTicks", "vfxFieldLifetimeTicks"), ("fieldRadiusTiles", "vfxFieldRadiusTiles")]:
            raw_vals = [_clamp(t.get(field), field) for t in trail_calls if t.get(field) not in (None, "")]
            raw_vals = [v for v in raw_vals if v is not None]
            if raw_vals:
                patch[out_field] = _intish(field, max(raw_vals))
        if rejected_trails:
            patch["rejectedTrailCalls"] = rejected_trails[:8]

    # Author-preserved state/trigger intents. These are not semantic routers and do not
    # execute unsupported gameplay by themselves; they are compact contract data for
    # lineage/future runtime wiring, while concrete engineCalls still carry immediate effects.
    runtime_state: dict[str, Any] = {}
    meters = _compile_state_meter_calls(state_meter_calls)
    if meters:
        runtime_state["stateMeters"] = meters
    triggered, rejected_triggered = _compile_triggered_action_calls(triggered_action_calls)
    if triggered:
        runtime_state["triggeredActions"] = triggered
    if rejected_triggered:
        patch.setdefault("rejectedEngineCalls", [])
        patch["rejectedEngineCalls"] = (patch.get("rejectedEngineCalls") or []) + rejected_triggered[:8]
    if runtime_state:
        runtime_state["executionStatus"] = "preserved_contract_not_gameplay_executor"
        patch["runtimeState"] = runtime_state

    # Executable utility calls: these expand runtime options without routing item identity
    # into rigid presets.  They only write concrete supported fields/provenance.
    extra_buffs: list[dict[str, int]] = []
    for uc in use_effect_calls:
        for field in ["healLife", "healMana"]:
            if uc.get(field) not in (None, ""):
                v = _clamp(uc.get(field), field, 0)
                if v is not None:
                    patch[field] = max(int(patch.get(field) or 0), int(round(v)))
        raw_buffs = uc.get("buffs") if isinstance(uc.get("buffs"), list) else []
        if uc.get("buffType") not in (None, ""):
            raw_buffs = list(raw_buffs) + [{"buffType": uc.get("buffType"), "buffTime": uc.get("buffTime")}]
        for b in raw_buffs:
            if not isinstance(b, dict):
                continue
            bt = _clamp(b.get("buffType"), "buffType", 0)
            tm = _clamp(b.get("buffTime"), "buffTime", 0)
            if bt and bt > 0:
                extra_buffs.append({"buffCode": int(round(bt)), "buffTime": int(round(tm or 60 * 30))})
    if extra_buffs:
        dedup: dict[int, int] = {}
        for b in extra_buffs:
            dedup[int(b["buffCode"])] = max(dedup.get(int(b["buffCode"]), 0), int(b["buffTime"]))
        patch["extraBuffs"] = [{"buffCode": k, "buffTime": max(1, min(21600, v))} for k, v in list(dedup.items())[:4]]
        patch.setdefault("buffCode", patch["extraBuffs"][0]["buffCode"])
        patch.setdefault("buffTime", patch["extraBuffs"][0]["buffTime"])
        patch["useEffectCallCount"] = len(use_effect_calls)

    generated_buff: dict[str, Any] = {}
    for uc in use_effect_calls:
        gb = uc.get("generatedBuff") if isinstance(uc.get("generatedBuff"), dict) else {}
        duration_raw = gb.get("durationTicks") or uc.get("durationTicks") or uc.get("buffTime")
        duration = _num(duration_raw, 0) if duration_raw not in (None, "") else 0
        if duration:
            generated_buff["durationTicks"] = max(int(generated_buff.get("durationTicks") or 0), int(round(max(1, min(21600, duration)))))
        for src, out, lo, hi in [
            ("miningSpeedMultiplier", "miningSpeedMultiplier", 0.25, 4.0),
            ("emitLightStrength", "emitLightStrength", 0.0, 1.5),
            ("oreSenseRadiusTiles", "oreSenseRadiusTiles", 0.0, 60.0),
            ("movementSpeed", "movementSpeed", -0.5, 2.0),
            ("jumpBoost", "jumpBoost", 0.0, 8.0),
            ("manaRegen", "manaRegen", 0.0, 120.0),
            ("lifeRegen", "lifeRegen", 0.0, 120.0),
        ]:
            raw = gb.get(src, uc.get(src))
            if raw in (None, ""):
                continue
            val = _num(raw, None)
            if val is None:
                continue
            val = max(lo, min(hi, val))
            if out in {"oreSenseRadiusTiles", "manaRegen", "lifeRegen"}:
                val = int(round(val))
            generated_buff[out] = max(generated_buff.get(out, val), val) if isinstance(val, (int, float)) and out not in {"movementSpeed"} else val
        color = str(gb.get("lightColorName") or gb.get("color") or uc.get("lightColorName") or "").strip()
        if color:
            generated_buff["lightColorName"] = color[:32]
    if generated_buff:
        generated_buff.setdefault("durationTicks", int(patch.get("buffTime") or 60 * 30))
        patch["generatedBuff"] = generated_buff

    if tool_calls:
        merged_tool = _merged_params(tool_calls)
        for field in ["pickPower", "axePower", "hammerPower"]:
            if merged_tool.get(field) not in (None, ""):
                v = _clamp(merged_tool.get(field), field, 0)
                if v is not None:
                    patch[field] = int(round(v))
        if merged_tool.get("miningSpeedScale") not in (None, ""):
            patch["miningSpeedScale"] = max(0.25, min(2.0, _num(merged_tool.get("miningSpeedScale"), 1.0) or 1.0))

    if light_calls:
        strengths = [_clamp(c.get("strength"), "lightStrength", 0) for c in light_calls if c.get("strength") not in (None, "")]
        strengths = [s for s in strengths if s is not None]
        if strengths:
            patch["runtimeLightStrength"] = round(max(strengths), 3)
        colors = [
            str(c.get("lightColorName") or c.get("color") or "").strip()
            for c in light_calls
            if str(c.get("lightColorName") or c.get("color") or "").strip()
        ]
        if colors:
            patch.setdefault("primaryColorName", colors[0][:32])
            patch.setdefault("runtimeLightColorName", colors[0][:32])
        patch["lightCallCount"] = len(light_calls)

    if vfx_cue_calls:
        allowed_events = {"travel", "active", "tick", "hit", "kill", "expire", "while_held", "while_equipped", "on_use", "on_alt_use"}
        allowed_renderers = {"projectileAfterimage", "spriteStampTrail", "historyRibbon", "tipTrail", "ghostArc", "wavyStrip", "beamLine", "fieldPulse", "orbitingMotes", "actorAfterimage", "impactRing", "impactSprite", "childMotes", "lightCue", "soundCue"}
        allowed_channels = {"motionTrail", "coreGlow", "ambientParticles", "impactShape", "impactParticles", "decaySmoke", "light", "sound"}
        allowed_lanes = {"primary", "support", "accent", "ornament", "cue"}
        allowed_roles = {"projectile", "impact", "child", "field"}
        allowed_emission = {"wake", "orbit", "residue", "burst", "cone", "ring", "spiral", "point"}
        allowed_particles = {"pl:glow", "pl:shard", "pl:smoke", "pl:spark", "dust"}
        cues: list[dict[str, Any]] = []
        for call in vfx_cue_calls[:8]:
            p = call.get("params") if isinstance(call, dict) and isinstance(call.get("params"), dict) else call if isinstance(call, dict) else {}
            event = str(p.get("event") or "").strip()
            renderer = str(p.get("rendererKind") or p.get("renderer") or "").strip()
            channel = str(p.get("channel") or "").strip()
            lane = str(p.get("lane") or "").strip()
            texture_role = str(p.get("textureRole") or "projectile").strip()
            particle_role = str(p.get("particleRole") or texture_role or "child").strip()
            emission = str(p.get("emissionMode") or "").strip()
            particle_id = str(p.get("particleSystemId") or "").strip()
            cue: dict[str, Any] = {"source": "runtimePlan.visual_effect_cue"}
            if event in allowed_events: cue["event"] = event
            if renderer in allowed_renderers: cue["rendererKind"] = renderer
            if channel in allowed_channels: cue["channel"] = channel
            if lane in allowed_lanes: cue["lane"] = lane
            if texture_role in allowed_roles: cue["textureRole"] = texture_role
            if particle_role in allowed_roles: cue["particleRole"] = particle_role
            if emission in allowed_emission: cue["emissionMode"] = emission
            if particle_id in allowed_particles: cue["particleSystemId"] = particle_id
            for field in ("scale", "density", "duration", "alpha", "spread", "jitter", "startTick", "repeatEvery"):
                if field in p and p.get(field) not in (None, ""):
                    cue[field] = _clamp(p.get(field), field, 0)
                    if field in {"duration", "startTick", "repeatEvery"}:
                        cue[field] = int(round(cue[field]))
            importance = str(p.get("importance") or "").strip()
            if importance in {"core", "secondary", "accent", "luxury"}:
                cue["importance"] = importance
            note = str(p.get("note") or p.get("identity") or "").strip()
            if note:
                cue["note"] = note[:80]
            if any(k in cue for k in ("event", "rendererKind", "channel", "particleSystemId")):
                cues.append(cue)
        if cues:
            patch["vfxCues"] = cues
            patch["vfxCueCount"] = len(cues)

    if mobility_calls:
        accepted_modes = {"recall_home", "blink_to_cursor", "blink_to_projectile_impact"}
        mobility = _merged_params(mobility_calls)
        mode = _norm_name(mobility.get("mode"))
        if mode in accepted_modes:
            patch["mobilityMode"] = mode
            if mobility.get("rangeTiles") not in (None, ""):
                patch["mobilityRangeTiles"] = int(max(0, min(80, _num(mobility.get("rangeTiles"), 0) or 0)))
            if mobility.get("cooldownTicks") not in (None, ""):
                patch["mobilityCooldownTicks"] = int(round(_clamp(mobility.get("cooldownTicks"), "cooldownTicks", 0) or 0))
            patch["mobilitySafeTileOnly"] = bool(mobility.get("safeTileOnly") is not False)

    if alt_use_calls:
        alt = _merged_params(alt_use_calls)
        mode = _norm_name(alt.get("mode")) or "mobility"
        patch["altUseMode"] = mode[:32]
        amode = _norm_name(alt.get("mobilityMode") or alt.get("mode"))
        if amode in {"recall_home", "blink_to_cursor"}:
            patch["altMobilityMode"] = amode
            patch["altMobilityRangeTiles"] = int(max(0, min(80, _num(alt.get("rangeTiles"), 0) or 0)))
            patch["altMobilityCooldownTicks"] = int(round(_clamp(alt.get("cooldownTicks"), "cooldownTicks", 0) or 0))
            patch["altMobilitySafeTileOnly"] = bool(alt.get("safeTileOnly") is not False)
        if isinstance(alt.get("generatedBuff"), dict):
            patch["altGeneratedBuff"] = alt.get("generatedBuff")
        elif mode == "light":
            alt_strengths = [_clamp(c.get("strength"), "lightStrength", 0) for c in light_calls if c.get("strength") not in (None, "")]
            alt_strengths = [s for s in alt_strengths if s is not None]
            strength = max(alt_strengths) if alt_strengths else 0
            colors = [str(c.get("lightColorName") or c.get("color") or "").strip() for c in light_calls if str(c.get("lightColorName") or c.get("color") or "").strip()]
            if strength > 0:
                patch["altGeneratedBuff"] = {
                    "durationTicks": int(round(_clamp(alt.get("durationTicks"), "durationTicks", 8 * 60) or 8 * 60)),
                    "emitLightStrength": round(max(0, min(1.5, strength)), 3),
                    "lightColorName": (colors[0] if colors else str(patch.get("primaryColorName") or ""))[:32],
                }

    if hold_effect_calls:
        hold = _merged_params(hold_effect_calls)
        if hold.get("lightStrength") not in (None, ""):
            patch["holdLightStrength"] = round(max(0, min(1.5, _num(hold.get("lightStrength"), 0) or 0)), 3)
        color = str(hold.get("lightColorName") or hold.get("color") or "").strip()
        if color:
            patch["holdLightColorName"] = color[:32]
        if isinstance(hold.get("generatedBuff"), dict):
            patch["holdGeneratedBuff"] = hold.get("generatedBuff")

    if extractinator_calls:
        ex = _merged_params(extractinator_calls)
        rt = _clamp(ex.get("resultType"), "resultType", 0) if ex.get("resultType") not in (None, "") else 0
        st = _clamp(ex.get("stack"), "stack", 1) if ex.get("stack") not in (None, "") else 1
        if rt and rt > 0:
            patch["extractinatorOutputItemType"] = int(round(rt))
            patch["extractinatorOutputStack"] = int(round(st or 1))

    if use_affordance_calls:
        ua = _merged_params(use_affordance_calls)
        for src, out, lo, hi in [
            ("itemScale", "itemScale", 0.55, 1.55),
            ("holdoutOffsetX", "holdoutOffsetX", -80, 80),
            ("holdoutOffsetY", "holdoutOffsetY", -80, 80),
        ]:
            if ua.get(src) not in (None, ""):
                val = max(lo, min(hi, _num(ua.get(src), 0) or 0))
                patch[out] = int(round(val)) if out.startswith("holdout") else round(val, 3)
        for src, out in [("autoReuse", "autoReuse"), ("useTurn", "useTurn"), ("channelUse", "channelUse"), ("drawDuringUse", "drawDuringUse")]:
            if src in ua:
                patch[out] = bool(ua.get(src))
        enum_fields = {
            "useFantasy": {"throw", "stab", "swing", "slam", "drink", "crush", "plant", "channel", "equip", "place"},
            "heldVisibility": {"show_item", "hide_item", "show_projectile", "show_both"},
            "releaseTiming": {"instant", "early", "mid_swing", "on_contact", "on_release"},
            "handPose": {"short_weapon", "two_hand", "overhead", "throwing", "staff", "held_out", "none"},
            "spawnStyle": {"from_hand", "at_tip", "centered", "impact_only", "world_anchor"},
            "rotationMode": {"face_velocity", "spin", "fixed", "swing_locked", "random"},
            "trailMode": {"none", "afterimage", "dust", "sprite_stamp", "ribbon"},
            "projectileSizePolicy": {"authored", "inherit_parent_floor", "inherit_parent_max"},
        }
        for field, allowed in enum_fields.items():
            value = _norm_name(ua.get(field))
            if value in allowed:
                patch[field] = value
        if ua.get("initialOffsetPx") not in (None, ""):
            patch["initialOffsetPx"] = int(round(max(-64, min(64, _num(ua.get("initialOffsetPx"), 0) or 0))))

    if consumption_calls:
        cb = _merged_params(consumption_calls)
        if cb.get("consumeChancePercent") not in (None, ""):
            patch["consumeChancePercent"] = int(round(max(0, min(100, _num(cb.get("consumeChancePercent"), 100) or 100))))

    if ammo_behavior_calls:
        ammo = _merged_params(ammo_behavior_calls)
        ammo_for = _norm_name(ammo.get("ammoFor") or ammo.get("kind"))
        if ammo_for in {"arrow", "arrows", "bullet", "bullets", "empty", "none"}:
            patch["ammoFor"] = "" if ammo_for in {"empty", "none"} else ammo_for
            if ammo_for not in {"empty", "none"}:
                patch.setdefault("kind", "ammo")
                patch.setdefault("consumable", True)

    if use_condition_calls:
        cond = _merged_params(use_condition_calls)
        mode = _norm_name(cond.get("mode"))
        if mode in {"grounded", "not_wet", "life_above", "mana_above"}:
            patch["useConditionMode"] = mode
            if cond.get("minLife") not in (None, ""):
                patch["useConditionMinLife"] = int(round(_clamp(cond.get("minLife"), "minLife", 0) or 0))
            if cond.get("minMana") not in (None, ""):
                patch["useConditionMinMana"] = int(round(_clamp(cond.get("minMana"), "minMana", 0) or 0))

    if accessory_calls:
        acc = _merged_params(accessory_calls)
        accessory: dict[str, Any] = {"enabled": True}
        if acc.get("archetype") not in (None, ""):
            accessory["archetype"] = _norm_name(acc.get("archetype"))[:32]
        for src, out, lo, hi, integer in [
            ("defense", "defense", 0, 20, True),
            ("maxLife", "maxLife", 0, 100, True),
            ("maxMana", "maxMana", 0, 100, True),
            ("lifeRegen", "lifeRegen", 0, 20, True),
            ("manaRegen", "manaRegen", 0, 20, True),
            ("movementSpeed", "movementSpeed", 0, 1.0, False),
            ("maxRunSpeed", "maxRunSpeed", 0, 2.0, False),
            ("jumpSpeed", "jumpSpeed", 0, 4.0, False),
            ("genericDamage", "genericDamage", 0, 0.4, False),
            ("meleeDamage", "meleeDamage", 0, 0.4, False),
            ("rangedDamage", "rangedDamage", 0, 0.4, False),
            ("magicDamage", "magicDamage", 0, 0.4, False),
            ("summonDamage", "summonDamage", 0, 0.4, False),
            ("genericCrit", "genericCrit", 0, 20, False),
            ("attackSpeed", "attackSpeed", 0, 0.4, False),
            ("knockback", "knockback", 0, 2.0, False),
            ("minionSlots", "minionSlots", 0, 2, True),
            ("sentrySlots", "sentrySlots", 0, 2, True),
            ("manaCostReduction", "manaCostReduction", 0, 0.4, False),
            ("ammoSaveChance", "ammoSaveChance", 0, 0.5, False),
            ("aggro", "aggro", -400, 400, True),
            ("endurance", "endurance", 0, 0.2, False),
            ("armorPenetration", "armorPenetration", 0, 40, False),
            ("lightStrength", "lightStrength", 0, 1.5, False),
        ]:
            raw = acc.get(src)
            if raw in (None, ""):
                continue
            val = max(lo, min(hi, _num(raw, 0) or 0))
            accessory[out] = int(round(val)) if integer else round(float(val), 3)
        for src, out in [("fallDamageImmune", "fallDamageImmune"), ("lavaImmune", "lavaImmune"), ("waterWalk", "waterWalk")]:
            if src in acc:
                accessory[out] = bool(acc.get(src) is not False)
        color = str(acc.get("lightColorName") or acc.get("color") or "").strip()
        if color:
            accessory["lightColorName"] = color[:32]
        patch["accessory"] = accessory
        patch["kind"] = "accessory"
        patch["maxStack"] = 1

    if armor_calls or _norm_name(itemstats.get("resultKind")) == "armor":
        arm = _merged_params(armor_calls) if armor_calls else {}
        armor: dict[str, Any] = {"enabled": True}
        slot = _norm_name(arm.get("armorSlot") or itemstats.get("armorSlot") or arm.get("slot"))
        armor["slot"] = slot if slot in {"head", "body", "legs"} else "body"
        if arm.get("setKey") not in (None, ""):
            armor["setKey"] = str(arm.get("setKey"))[:64]
        if arm.get("archetype") not in (None, ""):
            armor["archetype"] = _norm_name(arm.get("archetype"))[:32]
        for src, out, lo, hi, integer in [
            ("defense", "defense", 0, 80, True),
            ("maxLife", "maxLife", 0, 100, True),
            ("maxMana", "maxMana", 0, 100, True),
            ("lifeRegen", "lifeRegen", 0, 20, True),
            ("manaRegen", "manaRegen", 0, 20, True),
            ("movementSpeed", "movementSpeed", 0, 1.0, False),
            ("maxRunSpeed", "maxRunSpeed", 0, 2.0, False),
            ("jumpSpeed", "jumpSpeed", 0, 4.0, False),
            ("genericDamage", "genericDamage", 0, 0.4, False),
            ("meleeDamage", "meleeDamage", 0, 0.4, False),
            ("rangedDamage", "rangedDamage", 0, 0.4, False),
            ("magicDamage", "magicDamage", 0, 0.4, False),
            ("summonDamage", "summonDamage", 0, 0.4, False),
            ("genericCrit", "genericCrit", 0, 20, False),
            ("attackSpeed", "attackSpeed", 0, 0.4, False),
            ("knockback", "knockback", 0, 2.0, False),
            ("minionSlots", "minionSlots", 0, 2, True),
            ("sentrySlots", "sentrySlots", 0, 2, True),
            ("manaCostReduction", "manaCostReduction", 0, 0.4, False),
            ("ammoSaveChance", "ammoSaveChance", 0, 0.5, False),
            ("aggro", "aggro", -400, 400, True),
            ("endurance", "endurance", 0, 0.2, False),
            ("armorPenetration", "armorPenetration", 0, 40, False),
            ("whipRange", "whipRange", 0, 1.5, False),
            ("summonTagDamage", "summonTagDamage", 0, 0.75, False),
            ("lightStrength", "lightStrength", 0, 1.5, False),
            ("setBonusGenericDamage", "setBonusGenericDamage", 0, 0.4, False),
            ("setBonusMeleeDamage", "setBonusMeleeDamage", 0, 0.4, False),
            ("setBonusRangedDamage", "setBonusRangedDamage", 0, 0.4, False),
            ("setBonusMagicDamage", "setBonusMagicDamage", 0, 0.4, False),
            ("setBonusSummonDamage", "setBonusSummonDamage", 0, 0.4, False),
            ("setBonusGenericCrit", "setBonusGenericCrit", 0, 20, False),
            ("setBonusMovementSpeed", "setBonusMovementSpeed", 0, 1.0, False),
            ("setBonusLifeRegen", "setBonusLifeRegen", 0, 20, True),
            ("setBonusManaRegen", "setBonusManaRegen", 0, 20, True),
            ("setBonusMinionSlots", "setBonusMinionSlots", 0, 2, True),
            ("setBonusSentrySlots", "setBonusSentrySlots", 0, 2, True),
            ("setBonusManaCostReduction", "setBonusManaCostReduction", 0, 0.4, False),
            ("setBonusAmmoSaveChance", "setBonusAmmoSaveChance", 0, 0.5, False),
            ("setBonusAggro", "setBonusAggro", -400, 400, True),
            ("setBonusEndurance", "setBonusEndurance", 0, 0.2, False),
            ("setBonusArmorPenetration", "setBonusArmorPenetration", 0, 40, False),
        ]:
            raw = arm.get(src, itemstats.get(src))
            if raw in (None, ""):
                continue
            val = max(lo, min(hi, _num(raw, 0) or 0))
            armor[out] = int(round(val)) if integer else round(float(val), 3)
        for src, out in [("fallDamageImmune", "fallDamageImmune"), ("lavaImmune", "lavaImmune"), ("waterWalk", "waterWalk")]:
            if src in arm:
                armor[out] = bool(arm.get(src) is not False)
        for src, out in [("lightColorName", "lightColorName"), ("color", "lightColorName"), ("setBonusText", "setBonusText")]:
            if arm.get(src) not in (None, "") and out not in armor:
                armor[out] = str(arm.get(src))[:120 if out == "setBonusText" else 32]
        _apply_armor_slot_budget(armor)
        patch["armor"] = armor
        patch["kind"] = "armor"
        patch["maxStack"] = 1
        patch["damage"] = 0

    # Primary numeric mapping.
    for src, mapping in [
        (shoot, {"rangeTiles": "rangeTiles", "lifetimeTicks": "lifetimeTicks", "shotCount": "shotCount", "spreadRadians": "spreadRadians", "pierce": "pierce", "extraUpdates": "extraUpdates", "homingStrength": "homingStrength", "useTimeTicks": "useTimeTicks", "speed": "speed", "reliability": "reliability", "selfLockTicks": "selfLockTicks", "missPunish": "missPunish"}),
        (hit, {"aoeRadiusTiles": "aoeRadiusTiles", "chainCount": "chainCount", "count": "splitCount", "pullStrength": "pullStrength"}),
        (itemstats, {"useTimeTicks": "useTimeTicks", "craftYield": "craftYield"}),
    ]:
        for k, outk in mapping.items():
            if k in src and src.get(k) not in (None, "") and outk not in patch and outk in NUMERIC_LIMITS:
                v = _clamp(src.get(k), outk)
                if v is not None:
                    patch[outk] = _intish(outk, v)

    # Hit behavior: the first authored hit effect is primary. Later hit calls remain provenance.
    onhit = _enum(hit.get("onHit"), ONHITS, None)
    if onhit:
        patch["onHit"] = onhit
    debuff_hint = str(hit.get("debuffHint") or "").strip()
    if debuff_hint:
        patch["debuffHint"] = debuff_hint[:80]
        if hit.get("debuffTime") not in (None, ""):
            try:
                patch["debuffTime"] = int(max(15, min(360, float(hit.get("debuffTime")))))
            except Exception:
                patch["debuffTime"] = 90
        else:
            patch["debuffTime"] = 90

    # Some explicit on-hit effects spawn gameplay children in the C# runtime.
    # Give them a child budget only when the LLM actually requested an executable count.
    if onhit in {"chain", "lightning_arc"}:
        # For chain-like effects, generic params.count means chain hops, not split shards.
        existing_split_for_count = int(_num(patch.get("splitCount"), 0) or 0)
        if int(_num(patch.get("chainCount"), 0) or 0) <= 0 and existing_split_for_count > 0:
            patch["chainCount"] = existing_split_for_count
            patch["splitCount"] = 0
        chain_count = int(_num(patch.get("chainCount"), 0) or 0)
        if chain_count > 0:
            patch.setdefault("maxChildProjectiles", int(max(1, min(48, chain_count + 1))))
            patch.setdefault("maxChildDepth", 1)
        else:
            patch["onHitDemotedReason"] = f"{onhit}_requires_count_gt_0"
            patch["onHit"] = "none"
            onhit = "none"
    if onhit in {"mini_missiles", "vortex_spawn", "radial_beams", "starburst", "starfall", "spore_cloud"}:
        effect_count = int(_num(patch.get("splitCount"), 0) or 0)
        if effect_count <= 0:
            patch["onHitDemotedReason"] = f"{onhit}_requires_count_gt_0"
            patch["onHit"] = "none"
            onhit = "none"
        else:
            patch.setdefault("maxChildProjectiles", int(max(1, min(48, effect_count))))
            patch.setdefault("maxChildDepth", 1)

    # Real secondary damaging projectiles. The bounded runtime currently executes on-hit
    # secondaries. Other triggers are retained in validation/provenance as rejected until
    # C# has real on_expire/on_tick/on_use support.
    total_secondary = 0
    spread_values: list[float] = []
    dmg_values: list[float] = []
    life_values: list[float] = []
    bias_values: list[float] = []
    secondary_materials: list[str] = []
    secondary_shapes: list[str] = []
    accepted_secondary_indices: list[Any] = []
    rejected_secondary: list[dict[str, Any]] = []
    for sc in secondary_calls:
        trigger = _norm_name(sc.get("trigger")) or "on_hit"
        count = _clamp(sc.get("count"), "splitCount", 0) or 0
        if trigger in {"on_hit", "hit", ""} and count > 0:
            total_secondary += int(round(count))
            accepted_secondary_indices.append(sc.get("_index"))
            for k, store, lim in [
                ("spreadRadians", spread_values, "secondarySpreadRadians"),
                ("damageMultiplier", dmg_values, "secondaryDamageMultiplier"),
                ("lifetimeTicks", life_values, "secondaryLifetimeTicks"),
                ("sameTargetBias", bias_values, "sameTargetBias"),
            ]:
                v = _clamp(sc.get(k), lim) if sc.get(k) not in (None, "") else None
                if v is not None:
                    store.append(v)
            if sc.get("material") not in (None, ""):
                secondary_materials.append(str(sc.get("material"))[:40])
            if sc.get("projectileShape") not in (None, ""):
                secondary_shapes.append(str(sc.get("projectileShape"))[:80])
        elif count > 0:
            rejected_secondary.append({"index": sc.get("_index"), "trigger": trigger, "count": int(round(count)), "reason": "unsupported_trigger_current_runtime"})
    if total_secondary > 0:
        split = int(max(1, min(NUMERIC_LIMITS["splitCount"][1], total_secondary)))
        patch["splitCount"] = split
        patch["maxChildProjectiles"] = int(max(1, min(48, split)))
        patch["maxChildDepth"] = 1
        # spawn_secondary_projectiles is executable through split-like onHit in the current C#
        # runtime. Preserve simple authored debuffs by moving them into debuffHint; preserve
        # lifesteal/blackhole/aura-like primary onHit by rejecting gameplay secondaries instead
        # of silently replacing the core hit identity.
        debuff_onhits = {"burn", "frostburn", "poison", "shadowflame", "bleed"}
        child_onhits = {"split", "starburst", "starfall", "radial_beams", "mini_missiles", "vortex_spawn", "spore_cloud"}
        if not onhit or onhit in {"none", "burst"}:
            patch["onHit"] = "split"
            patch["onHitForcedBySecondary"] = True
        elif onhit in debuff_onhits:
            patch.setdefault("debuffHint", onhit)
            patch.setdefault("debuffTime", 180 if onhit != "burn" else 240)
            patch["onHit"] = "split"
            patch["onHitForcedBySecondary"] = True
            patch["secondaryPreservedDebuffOnHit"] = onhit
        elif onhit not in child_onhits:
            if secondary_from_rejected_primary and _norm_name(patch.get("runtimeFamily") or patch.get("delivery")) in {"swing", "thrust"}:
                # The recovered second primary is a small extra shard from the melee hit;
                # keep the main onHit identity (e.g. lifesteal) instead of converting the
                # whole weapon to split or deleting the recovered shard.
                patch["secondaryPreservedAlongsidePrimaryOnHit"] = onhit
            else:
                patch["secondarySuppressedByPrimaryOnHit"] = onhit
                patch["splitCount"] = 0
                patch["maxChildProjectiles"] = 0
                patch["maxChildDepth"] = 0
        elif onhit != "split":
            # Child-producing onHit values already execute their own child logic. Keep the authored
            # onHit and only preserve child numeric knobs.
            patch.setdefault("maxChildProjectiles", int(max(1, min(48, split))))
            patch.setdefault("maxChildDepth", 1)
        if spread_values: patch["secondarySpreadRadians"] = round(max(spread_values), 3)
        if dmg_values: patch["secondaryDamageMultiplier"] = round(sum(dmg_values) / len(dmg_values), 3)
        if life_values: patch["secondaryLifetimeTicks"] = int(round(max(life_values)))
        if bias_values: patch["sameTargetBias"] = round(sum(bias_values) / len(bias_values), 3)
        if secondary_materials:
            patch["secondaryMaterial"] = ", ".join(dict.fromkeys(secondary_materials))[:80]
            patch.setdefault("primaryColorName", _material_color_name(secondary_materials))
        if secondary_shapes:
            patch["secondaryProjectileShape"] = "; ".join(dict.fromkeys(secondary_shapes))[:120]
            patch.setdefault("projectileShape", patch["secondaryProjectileShape"])
        melee_core_secondary = (_norm_name(patch.get("runtimeFamily") or patch.get("delivery")) in {"swing", "thrust"})
        explicit_secondary_body = bool(secondary_materials or secondary_shapes)
        if melee_core_secondary and not explicit_secondary_body:
            patch["secondarySuppressedByMeleeCore"] = "spawn_secondary_projectiles_requires_secondaryMaterial_or_projectileShape_for_swing_thrust"
            patch["splitCount"] = 0
            patch["maxChildProjectiles"] = 0
            patch["maxChildDepth"] = 0
            patch["secondaryDamageMultiplier"] = 0
            if patch.get("onHitForcedBySecondary"):
                patch["onHit"] = "none"
                patch.pop("onHitForcedBySecondary", None)
        patch["secondaryCallIndices"] = [x for x in accepted_secondary_indices if x is not None]
    else:
        existing_split = int(_num(patch.get("splitCount"), 0) or 0)
        current_onhit = _norm_name(patch.get("onHit"))
        child_onhit_values = {"starburst", "starfall", "radial_beams", "mini_missiles", "vortex_spawn", "spore_cloud"}
        # Explicit child-producing apply_on_hit_effect(count=N) is executable even
        # without a separate spawn_secondary_projectiles call. Preserve the count/provenance.
        if current_onhit == "split" and existing_split > 0:
            patch.setdefault("maxChildProjectiles", int(max(1, min(48, existing_split))))
            patch.setdefault("maxChildDepth", 1)
        elif current_onhit in child_onhit_values and existing_split > 0:
            patch.setdefault("maxChildProjectiles", int(max(1, min(48, existing_split))))
            patch.setdefault("maxChildDepth", 1)
        else:
            patch["splitCount"] = 0
            patch.setdefault("maxChildProjectiles", 0)
            if current_onhit == "split":
                patch["onHitDemotedReason"] = "split_requires_secondary_count_gt_0"
                patch["onHit"] = "none"
    if rejected_secondary:
        patch["rejectedSecondaryCalls"] = rejected_secondary[:8]

    tags = _attack_pattern_tags_from_patch(patch, shoot, hit, itemstats)
    if tags:
        patch["attackPatternTags"] = tags
    patch.setdefault("soundUseSearchQuery", _sound_query_from_patch(patch, impact=False))
    patch.setdefault("soundImpactSearchQuery", _sound_query_from_patch(patch, impact=True))

    # Executable defaults: only fill execution slots after the LLM chose engine calls.
    if shoot:
        patch.setdefault("delivery", "shoot")
        patch.setdefault("movement", "straight")
        patch.setdefault("shotCount", 1)
        patch.setdefault("pierce", 0)
        patch.setdefault("rangeTiles", 45)
        patch.setdefault("lifetimeTicks", 90)
        patch.setdefault("spreadRadians", 0)
        patch.setdefault("speed", 8.0)
    patch.setdefault("effect", "none" if not particle_calls or int(_num(patch.get("dustSpawnDenom"), 0) or 0) <= 0 else "dust")
    if not particle_calls:
        patch.setdefault("dustSpawnDenom", 0)
        patch.setdefault("burstDustCap", 0)
    patch.setdefault("onHit", "none")
    patch.setdefault("aoeRadiusTiles", 0)
    patch.setdefault("useTimeTicks", int(_clamp(_first_non_empty(itemstats.get("useTimeTicks"), shoot.get("useTimeTicks")), "useTimeTicks", 24) or 24))
    patch.setdefault("reliability", 1.0)
    patch.setdefault("selfLockTicks", 0)
    patch.setdefault("missPunish", 0)
    patch.setdefault("extraUpdates", 0)
    patch.setdefault("homingStrength", 0)
    if trail_calls:
        patch.setdefault("trailLength", int(max([_clamp(t.get("trailLength"), "trailLength", 0) or 0 for t in trail_calls] or [0])))
    else:
        patch.setdefault("trailLength", 4 if particle_calls else 0)

    for field in ["projectileShape", "projectileMotion", "projectileTrail", "projectileImpact", "weaponFamily", "projectileFamily", "ammoKind"]:
        val = shoot.get(field) or rp.get(field)
        if val not in (None, ""):
            patch[field] = str(val)
    patch["runtimePlanAuthored"] = True
    patch, _archetype_report = compile_runtime_archetype_to_attack_patch(data, patch)
    return {k: v for k, v in patch.items() if v not in (None, "")}


def runtime_plan_quality_report(data: dict[str, Any]) -> dict[str, Any]:
    rp = runtime_plan(data)
    calls = rp.get("engineCalls") if isinstance(rp.get("engineCalls"), list) else []
    fns = [str(c.get("fn")) for c in calls if isinstance(c, dict)]
    counts = {fn: fns.count(fn) for fn in sorted(set(fns))}
    return {
        "hasRuntimePlan": bool(rp),
        "callCount": len(fns),
        "functions": fns,
        "functionCounts": counts,
        "hasStats": "set_item_stats" in fns,
        "hasPrimaryAction": "shoot_projectile" in fns,
        "hasPureVfx": "spawn_contact_particles" in fns,
        "hasRealChildren": "spawn_secondary_projectiles" in fns,
        "multiCallAware": True,
    }




def runtime_plan_validation_report(data: dict[str, Any]) -> dict[str, Any]:
    """Validate authoring plan as an interface contract, not as a game-design judge."""
    normalize_runtime_plan_inplace(data)
    rp = runtime_plan(data)
    q = runtime_plan_quality_report(data)
    calls = rp.get("engineCalls") if isinstance(rp.get("engineCalls"), list) else []
    errors: list[str] = []
    warnings: list[str] = []
    fns = q.get("functions") or []
    counts = q.get("functionCounts") if isinstance(q.get("functionCounts"), dict) else {}
    if counts.get("shoot_projectile", 0) > 1:
        warnings.append("multiple compatible shoot_projectile calls supplied; current adapter aggregates compatible calls and rejects incompatible extras")
    if counts.get("set_item_stats", 0) > 1:
        warnings.append("multiple set_item_stats calls supplied; current adapter merges later non-empty stat fields over earlier ones")
    if not rp:
        errors.append("missing runtimePlan")
    elif not calls:
        errors.append("runtimePlan.engineCalls has no accepted executable calls")
    norm = rp.get("_normalization") if isinstance(rp.get("_normalization"), dict) else {}
    if norm.get("droppedCalls"):
        warnings.append("some engineCalls were dropped as unknown/non-object")
    if norm.get("rejectedEngineCalls"):
        warnings.append("some engineCalls were hard-rejected by safety policy")
    if "state_meter" in fns or "triggered_action" in fns:
        warnings.append("state_meter/triggered_action are preserved as authored runtime state intent; current gameplay requires concrete executable calls too")
    combatish = str(data.get("category") or data.get("gameplay", {}).get("kind") or "").lower() in {"weapon", "summon"} or bool((data.get("attack") or {}).get("enabled") if isinstance(data.get("attack"), dict) else False)
    if combatish:
        if "set_item_stats" not in fns:
            errors.append("combat result lacks set_item_stats")
        if "shoot_projectile" not in fns:
            errors.append("combat result lacks a primary executable action; visual trail is not executable combat")
        else:
            compiled_patch = compile_runtime_plan_to_genome_patch(data)
            runtime_error = _norm_name(compiled_patch.get("runtimeContractError"))
            if runtime_error:
                errors.append("primary executable action did not compile: " + runtime_error)
            if runtime_error == "primary_attack_requires_runtimefamily" or not _norm_name(compiled_patch.get("runtimeFamily")) or _norm_name(compiled_patch.get("runtimeFamily")) == "none":
                errors.append("combat primary action lacks an executable runtimeFamily")
    for secondary in all_calls(rp, "spawn_secondary_projectiles"):
        count = _num(secondary.get("count"), 0) or 0
        trigger = _norm_name(secondary.get("trigger"))
        if count <= 0:
            warnings.append("spawn_secondary_projectiles present with count<=0")
        if count > 8:
            warnings.append("secondary projectile count exceeds executable adapter range; runtime will clamp")
        if trigger not in {"on_hit", "hit", ""}:
            warnings.append("secondary projectile trigger is not executable in v0.4.13 adapter; use on_hit or it will be rejected")
    stats = find_call(rp, "set_item_stats")
    result_kind = _norm_name(stats.get("resultKind"))
    max_stack = _num(stats.get("maxStack"), 0) or 0
    craft_yield = _num(stats.get("craftYield"), 0) or 0
    if result_kind == "ammo" and max(max_stack, craft_yield) < 25:
        warnings.append("ammo output has low stack/yield; playable ammo should usually output 25+")
    hit = find_call(rp, "apply_on_hit_effect")
    if hit:
        onhit = _norm_name(hit.get("onHit"))
        aoe = _num(hit.get("aoeRadiusTiles"), 0) or 0
        if onhit in {"burst", "starburst", "blackhole", "radial_beams", "mini_missiles", "vortex_spawn"} and aoe > 10:
            warnings.append("impact AoE exceeds executable range; runtime will clamp")
    contract_validation = validate_runtime_contract(data, compile_runtime_plan_to_genome_patch(data) if rp else {})
    warnings.extend(contract_validation.get("warnings") or [])
    return {
        "api": ENGINE_RUNTIME_API_VERSION,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "quality": q,
        "normalization": norm,
    }


def _authored_field_map(data_or_plan: dict[str, Any]) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Map compiled field names to the engine call that explicitly authored them."""
    rp = data_or_plan if isinstance(data_or_plan.get("engineCalls"), list) else runtime_plan(data_or_plan)
    authored: dict[str, str] = {}
    authored_by_fn: dict[str, list[str]] = {}
    maps: dict[str, dict[str, str]] = {
        "set_item_stats": {
            "resultKind": "resultKind",
            "damageClass": "damageClass",
            "damage": "damage",
            "useTimeTicks": "useTimeTicks",
            "maxStack": "maxStack",
            "consumable": "consumable",
            "rarity": "rarity",
            "value": "value",
            "manaCost": "manaCost",
            "craftYield": "craftYield",
            "defense": "defense",
        },
        "shoot_projectile": {
            "runtimeFamily": "runtimeFamily",
            "delivery": "delivery",
            "movement": "movement",
            "useStyleCode": "useStyleCode",
            "hideUseGraphic": "hideUseGraphic",
            "disableItemMeleeHitbox": "disableItemMeleeHitbox",
            "ownerHitCheck": "ownerHitCheck",
            "channelUse": "channelUse",
            "speed": "speed",
            "rangeTiles": "rangeTiles",
            "range": "rangeTiles",
            "lifetimeTicks": "lifetimeTicks",
            "lifetime": "lifetimeTicks",
            "shotCount": "shotCount",
            "spreadRadians": "spreadRadians",
            "pierce": "pierce",
            "extraUpdates": "extraUpdates",
            "homingStrength": "homingStrength",
            "reliability": "reliability",
        },
        "spawn_secondary_projectiles": {
            "splitCount": ("splitCount", "count"),
            "maxChildProjectiles": "maxChildProjectiles",
            "secondarySpreadRadians": "secondarySpreadRadians",
            "secondaryDamageMultiplier": "secondaryDamageMultiplier",
            "secondaryLifetimeTicks": "secondaryLifetimeTicks",
            "sameTargetBias": "sameTargetBias",
            "secondaryMaterial": "secondaryMaterial",
            "secondaryProjectileShape": "secondaryProjectileShape",
            "primaryColorName": "primaryColorName",
        },
        "apply_on_hit_effect": {
            "onHit": "onHit",
            "aoeRadiusTiles": "aoeRadiusTiles",
            "chainCount": "chainCount",
            "pullStrength": "pullStrength",
            "debuffHint": "debuffHint",
            "debuffTime": "debuffTime",
        },
        "spawn_contact_particles": {
            "effect": "effect",
            "burstDustCap": "burstDustCap",
            "vfxParticleScale": "vfxParticleScale",
            "vfxMaterial": "vfxMaterial",
            "primaryColorName": "primaryColorName",
        },
        "leave_trail_or_field": {
            "trailLength": "trailLength",
            "vfxFieldLifetimeTicks": "fieldLifetimeTicks",
            "vfxFieldRadiusTiles": ("fieldRadiusTiles", "fieldRadius"),
            "fieldRadius": ("fieldRadiusTiles", "fieldRadius"),
        },
        "visual_effect_cue": {"vfxCues": "cue", "vfxCueCount": "cue"},
        "state_meter": {"runtimeState": "kind"},
        "triggered_action": {"runtimeState": "trigger"},
        "use_affordance": {
            "itemScale": "itemScale",
            "holdoutOffsetX": "holdoutOffsetX",
            "holdoutOffsetY": "holdoutOffsetY",
            "autoReuse": "autoReuse",
            "useTurn": "useTurn",
            "channelUse": "channelUse",
            "useFantasy": "useFantasy",
            "heldVisibility": "heldVisibility",
            "releaseTiming": "releaseTiming",
            "handPose": "handPose",
            "spawnStyle": "spawnStyle",
            "rotationMode": "rotationMode",
            "initialOffsetPx": "initialOffsetPx",
            "drawDuringUse": "drawDuringUse",
            "trailMode": "trailMode",
            "projectileSizePolicy": "projectileSizePolicy",
        },
    }
    calls = rp.get("engineCalls") if isinstance(rp.get("engineCalls"), list) else []
    for raw in calls:
        if not isinstance(raw, dict):
            continue
        fn = _norm_name(raw.get("fn"))
        param_obj = raw.get("params") if isinstance(raw.get("params"), dict) else raw
        if not isinstance(param_obj, dict):
            continue
        authored_keys = {str(k) for k, v in param_obj.items() if not str(k).startswith("_") and v not in (None, "", [], {})}
        for compiled_field, authored_param in maps.get(fn, {}).items():
            params = authored_param if isinstance(authored_param, tuple) else (authored_param,)
            if any(param in authored_keys for param in params):
                authored[compiled_field] = fn
                authored_by_fn.setdefault(fn, []).append(compiled_field)
    authored_by_fn = {fn: sorted(set(fields)) for fn, fields in authored_by_fn.items()}
    return authored, authored_by_fn


def runtime_plan_provenance_report(data: dict[str, Any], patch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Explain authored-vs-applied runtime fields so VFX is not confused with gameplay."""
    normalize_runtime_plan_inplace(data)
    rp = runtime_plan(data)
    patch = patch or compile_runtime_plan_to_genome_patch(data)
    calls = rp.get("engineCalls") if isinstance(rp.get("engineCalls"), list) else []
    fns = [str(c.get("fn") or "") for c in calls if isinstance(c, dict)]
    authored_sources, authored_by_fn = _authored_field_map(rp)

    field_sources: dict[str, str] = {}
    authored_fields: dict[str, bool] = {}
    for field in (patch or {}):
        if field in authored_sources:
            field_sources[field] = authored_sources[field]
            authored_fields[field] = True
        else:
            field_sources[field] = "runtime_compiler_default"
            authored_fields[field] = False
    for field, source in authored_sources.items():
        field_sources.setdefault(field, source)
        authored_fields.setdefault(field, True)

    # Alias view requested by the debug contract: both compiled names and compact names
    # point to the same authoring fn when present.
    alias_pairs = {
        "range": "rangeTiles",
        "lifetime": "lifetimeTicks",
        "fieldRadius": "vfxFieldRadiusTiles",
    }
    for alias, compiled_field in alias_pairs.items():
        if compiled_field in field_sources:
            field_sources.setdefault(alias, field_sources[compiled_field])
            authored_fields.setdefault(alias, authored_fields.get(compiled_field, False))

    split = int(_num((patch or {}).get("splitCount"), 0) or 0)
    max_child = int(_num((patch or {}).get("maxChildProjectiles"), 0) or 0)
    burst_cap = int(_num((patch or {}).get("burstDustCap"), 0) or 0)
    secondary_calls = all_calls(rp, "spawn_secondary_projectiles")
    particle_calls = all_calls(rp, "spawn_contact_particles")
    trail_calls = all_calls(rp, "leave_trail_or_field")
    normalized_calls = [
        {"index": c.get("_index"), "fn": c.get("fn"), "paramKeys": sorted(list((c.get("params") or {}).keys())) if isinstance(c.get("params"), dict) else []}
        for c in calls if isinstance(c, dict)
    ]
    child_onhits = {"chain", "lightning_arc", "mini_missiles", "vortex_spawn", "radial_beams", "starburst", "starfall", "spore_cloud"}
    onhit = _norm_name((patch or {}).get("onHit"))
    effect_child_count = 0
    if onhit in {"chain", "lightning_arc"}:
        effect_child_count = int(_num((patch or {}).get("chainCount"), 0) or 0)
    elif onhit in child_onhits:
        effect_child_count = split if split > 0 else int(_num((patch or {}).get("maxChildProjectiles"), 0) or 0)
    norm = rp.get("_normalization", {}) if isinstance(rp.get("_normalization"), dict) else {}
    unsupported: list[Any] = []
    for key in ("rejectedEngineCalls", "rejectedPrimaryCalls", "rejectedSecondaryCalls", "rejectedTrailCalls"):
        values = norm.get(key) if key in norm else (patch or {}).get(key)
        if isinstance(values, list):
            unsupported.extend(values)
    future_disabled = []
    if (patch or {}).get("runtimeState"):
        future_disabled.append({"field": "runtimeState", "reason": "preserved_authored_intent_not_executed"})
    return {
        "api": ENGINE_RUNTIME_API_VERSION,
        "engineFunctions": fns,
        "normalizedCalls": normalized_calls,
        "authoredFields": authored_fields,
        "authoredByFunction": authored_by_fn,
        "gameplayChildren": {
            "enabled": (split > 0 and max_child > 0) or effect_child_count > 0,
            "source": "spawn_secondary_projectiles" if split > 0 else ("apply_on_hit_effect" if effect_child_count > 0 else "none"),
            "authoredCallCount": len(secondary_calls),
            "compiledFromCallIndices": (patch or {}).get("secondaryCallIndices", []),
            "splitCount": split,
            "onHit": onhit,
            "onHitChildEstimate": effect_child_count,
            "maxChildProjectiles": max_child,
            "rejectedSecondaryCalls": (patch or {}).get("rejectedSecondaryCalls", []),
            "note": "Real gameplay child projectiles come from spawn_secondary_projectiles or child-producing apply_on_hit_effect values. VFX motes are separate renderer slots."
        },
        "pureVfx": {
            "enabled": "spawn_contact_particles" in fns or "leave_trail_or_field" in fns or burst_cap > 0,
            "source": "spawn_contact_particles" if "spawn_contact_particles" in fns else ("leave_trail_or_field" if "leave_trail_or_field" in fns else "runtime_compiler_default"),
            "authoredCallCount": len(particle_calls) + len(trail_calls),
            "burstDustCap": burst_cap,
            "trailLength": (patch or {}).get("trailLength", 0),
            "fieldRadius": (patch or {}).get("vfxFieldRadiusTiles", 0),
            "material": (patch or {}).get("vfxMaterial", ""),
            "note": "Pure VFX/dust/trails do not imply damaging child projectiles."
        },
        "unsupported": unsupported[:24],
        "futureDisabled": future_disabled,
        "fieldSources": field_sources,
        "normalization": norm,
    }

def compiled_runtime_contract(data: dict[str, Any], patch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compact executable output for server/debug: this is what the runtime receives."""
    normalize_runtime_plan_inplace(data)
    patch = patch or compile_runtime_plan_to_genome_patch(data)
    rp = runtime_plan(data)
    q = runtime_plan_quality_report(data)
    out = {
        "api": ENGINE_RUNTIME_API_VERSION,
        "compiler": "runtime_plan_to_attack_spec",
        "executableFields": dict(patch),
        "functionCounts": q.get("functionCounts", {}),
        "primaryCall": (rp.get("engineCalls") or [{}])[0] if isinstance(rp.get("engineCalls"), list) and rp.get("engineCalls") else {},
        "notes": [
            "runtimeFamily is required for executable attacks; only tiny unambiguous family-field repair is allowed",
            "splitCount/maxChildProjectiles represent gameplay children only, not VFX motes",
            "state_meter/triggered_action are preserved as explicit authored intent; they do not spawn bosses/NPCs/mobs and do not execute unsupported gameplay by prose",
            "runtimeArchetype/runtimeContract are data contracts; unsupported families are preserved as intent, not executed magically",
        ],
    }
    if isinstance(data.get("runtimeArchetype"), dict):
        out["runtimeArchetype"] = data.get("runtimeArchetype")
    if isinstance(data.get("runtimeContract"), dict):
        out["runtimeContract"] = data.get("runtimeContract")
    if isinstance(patch.get("archetypeCompiler"), dict):
        out["archetypeCompiler"] = patch.get("archetypeCompiler")
    debug = data.get("debug") if isinstance(data.get("debug"), dict) else {}
    promise_truth = debug.get("runtimePromiseTruth") if isinstance(debug, dict) else None
    if isinstance(promise_truth, str) and promise_truth.strip().startswith("{"):
        try:
            out["runtimePromiseTruth"] = json.loads(promise_truth)
        except (json.JSONDecodeError, TypeError):
            pass
    return out


def compile_runtime_plan_to_genome_result(data: dict[str, Any]) -> dict[str, Any]:
    patch = compile_runtime_plan_to_genome_patch(data)
    contract_validation = validate_runtime_contract(data, patch)
    promise_truth = validate_runtime_promises(data, patch)
    validation = runtime_plan_validation_report(data)
    validation["warnings"] = list(dict.fromkeys((validation.get("warnings") or []) + (contract_validation.get("warnings") or []) + (promise_truth.get("warnings") or [])))
    provenance = runtime_plan_provenance_report(data, patch)
    model = RuntimeCompileResult(
        patch=patch,
        provenance=provenance,
        clamps=[],
        errors=list(validation.get("errors") or []),
    )
    result = model.to_dict()
    # Backwards-compatible debug payload used by older tests/tools.
    result.update({
        "compiled": compiled_runtime_contract(data, patch),
        "validation": validation,
        "quality": runtime_plan_quality_report(data),
        "runtimeContractValidation": contract_validation,
        "runtimePromiseTruth": promise_truth,
    })
    return result


def infer_attack_pattern_from_runtime(genome: dict[str, Any], damage_class: str = "generic") -> str:
    delivery = _norm_name(genome.get("delivery"))
    runtime_family = _enum(_norm_name(genome.get("runtimeFamily")), RUNTIME_FAMILIES, "none")
    movement = _norm_name(genome.get("movement"))
    onhit = _norm_name(genome.get("onHit"))
    damage_class = _norm_name(damage_class)
    if movement in {"orbit", "vortex_orb", "blackhole_pull"}:
        return "orbiting_projectile"
    if movement == "expanding_wave" or onhit in {"aura_pulse", "spore_cloud", "blackhole"}:
        return "field_trap"
    if movement == "gravity_arc" and runtime_family in {"cast", "summon"}:
        return "falling_projectile"
    if runtime_family == "thrust":
        return "spear_thrust"
    if runtime_family == "flail" or movement == "flail_tether":
        return "flail_tether"
    if runtime_family == "yoyo" or movement == "yoyo_hover":
        return "yoyo_hover"
    if runtime_family == "whip" or movement == "whip_lash":
        return "whip_lash"
    if runtime_family == "swing":
        return "beam_slash" if movement in {"phase", "expanding_wave"} else "slash_holdout"
    if movement in {"phase", "accelerate"} and runtime_family in {"cast", "shoot"}:
        return "laser_beam" if damage_class == "magic" or runtime_family == "cast" else "thrown_simple"
    # Child-producing onHit values are executed by OnHitCode. They must not force the
    # animation archetype to thrown_simple; runtime family/source identity wins.
    if runtime_family == "cast" or damage_class == "magic":
        return "magic_projectile"
    if runtime_family == "summon" or damage_class == "summon":
        return "summon_projectile"
    if runtime_family == "shoot" or damage_class == "ranged":
        return "ranged_projectile"
    if runtime_family in {"throw", "returning"}:
        return "thrown_simple"
    return "thrown_simple"
