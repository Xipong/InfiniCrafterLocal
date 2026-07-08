from __future__ import annotations

from typing import Any


# AGENT MAP: static runtime authoring vocabulary/catalog/range schema.
# Runtime function vocabulary and bounds for the authoring package.


def _norm_name(x: Any) -> str:
    return str(x or "").strip().lower().replace("-", "_").replace(" ", "_")


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


__all__ = [
    "MOVEMENTS",
    "MOVEMENT_ALIASES",
    "EFFECTS",
    "EFFECT_ALIASES",
    "ONHITS",
    "ONHIT_ALIASES",
    "DELIVERIES",
    "DELIVERY_ALIASES",
    "RUNTIME_FAMILIES",
    "TERRARIA_WEAPON_FAMILY_GROUPS",
    "_family_group",
    "USE_STYLE_NONE",
    "USE_STYLE_SWING",
    "USE_STYLE_THRUST",
    "USE_STYLE_HOLD_UP",
    "USE_STYLE_SHOOT",
    "USE_STYLE_RAPIER",
    "_runtime_family_affordances",
    "ENGINE_FN_CATALOG_V2",
    "FN_ALIASES",
    "FORBIDDEN_WORLD_ENTITY_FN_NAMES",
    "FORBIDDEN_WORLD_ENTITY_FAMILIES",
    "SAFE_SUMMON_FAMILIES",
    "STATE_METER_TRIGGERS",
    "TRIGGERED_ACTION_TRIGGERS",
    "TRIGGERED_ACTION_KINDS",
    "NUMERIC_LIMITS",
    "INT_FIELDS",
]
