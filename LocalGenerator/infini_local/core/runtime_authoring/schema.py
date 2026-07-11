from __future__ import annotations

from typing import Any

from infini_local.core.runtime_family_policy import is_projectile_owned_family, uses_projectile_only_item_affordance
from infini_local.core.runtime_secondary_policy import CANONICAL_SECONDARY_TRIGGERS
from infini_local.core.runtime_authoring.vocabulary import normalize_authoring_token as _norm_name


# AGENT MAP: static runtime authoring vocabulary/catalog/range schema.
# Runtime function vocabulary and bounds for the authoring package.

# Canonical active temporary-helper families. True sentry lifecycle is authored only
# through deploy_sentry; no legacy minion/sentry spellings are accepted here.
TEMPORARY_HELPER_FAMILIES = frozenset({"orbiter", "drone", "wisp", "temporary_turret", "pet_attack"})


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


def _runtime_family_affordances(runtime_family: str, weapon_family: Any = "", delivery: Any = "") -> dict[str, Any]:
    family = _norm_name(weapon_family)
    delivery_token = _norm_name(delivery)
    out: dict[str, Any] = {}
    if runtime_family == "swing":
        out.update({"useStyleCode": USE_STYLE_SWING, "hideUseGraphic": False, "disableItemMeleeHitbox": False, "ownerHitCheck": False})
    elif runtime_family == "thrust":
        # Spears/lances in Terraria are item-use-style Shoot with noUseGraphic/noMelee
        # and a held projectile. Shortsword/rapier-like stabs can use Rapier-style
        # animation, but still execute through the generated held-thrust projectile.
        style = USE_STYLE_RAPIER if family in {"shortsword", "short_sword", "rapier", "dagger", "gladius"} else USE_STYLE_SHOOT
        out.update({"useStyleCode": style, "hideUseGraphic": True, "disableItemMeleeHitbox": True, "ownerHitCheck": True})
    elif runtime_family == "overhead_barrage" and delivery_token == "swing":
        # Starfury-style carrier: the item still swings and owns its melee hitbox;
        # overhead_barrage only owns where the authored projectile appears.
        out.update({"useStyleCode": USE_STYLE_SWING, "hideUseGraphic": False, "disableItemMeleeHitbox": False, "ownerHitCheck": False})
    elif is_projectile_owned_family(runtime_family):
        projectile_only = uses_projectile_only_item_affordance(runtime_family, delivery_token)
        out.update({"useStyleCode": USE_STYLE_SHOOT, "hideUseGraphic": projectile_only, "disableItemMeleeHitbox": projectile_only, "ownerHitCheck": runtime_family in {"whip", "beam"}})
        if runtime_family in {"yoyo", "beam"}:
            out["channelUse"] = True
    return out


ENGINE_FN_CATALOG_V2 = {
    "set_item_stats": {
        "meaning": "Result kind and bounded item stats.",
        "params": {
            "resultKind": "weapon|ammo|consumable_weapon|tool|accessory|armor|potion|material|furniture|generic",
            "damageClass": "generic|melee|ranged|magic|summon",
            "damage": "0..cap", "useTimeTicks": "10..150", "useAnimationTicks": "6..150; =useTime one action/click; >useTime may repeat", "knockback": "0..12", "manaCost": "0..80", "autoReuse": "bool", "maxStack": "1 gear; 25+ stacks",
            "craftYield": "output count", "healLife": "potion only", "healMana": "potion only", "buffType": "potion buff id", "buffTime": "ticks paired with buffType",
            "pickPower": "tool only", "axePower": "tool only", "hammerPower": "tool only",
            "ammoFor": "empty custom; arrow|bullet vanilla ammo identity",
            "armorSlot": "head|body|legs for armor", "defense": "armor 0..80",
            "consumable": "true stack-spent; false gear", "rarity": "-1..12", "value": ">=0",
        },
    },
    "shoot_projectile": {
        "meaning": "Low-level primary projectile/held executor; runtimeFamily required.",
        "params": {
            "delivery": "swing|thrust|shoot|cast|throw|summon", "movement": "straight|slow_homing|gravity_arc|drift|orbit|boomerang|bounce|sine_homing|phase|accelerate|spiral|vortex_orb|blackhole_pull|proximity_missile|returning_glaive|expanding_wave; phase passes tiles",
            "speed": "3..18", "rangeTiles": "4..120", "lifetimeTicks": "25..900", "shotCount": "1..8 simultaneous", "spreadRadians": "0..0.75", "pierce": "-1=infinite hits; 0 or 1=one target total; 2..10=total targets", "extraUpdates": "0..3", "homingStrength": "0..1", "beamWidthPx": "2..96", "beamChargeTicks": "0..300", "chargeTicks": "1..300", "chargePowerMultiplier": "1..3", "immunityCooldown": "4..60",
            "reliability": "0.45..1.25 metadata", "selfLockTicks": "0..120 metadata", "missPunish": "0..1 metadata",
            "runtimeFamily": "swing|thrust|returning|flail|yoyo|whip|shoot|cast|beam|charge_release|overhead_barrage|throw|summon; sentry uses deploy_sentry",
            "weaponFamily": "exact optional", "projectileFamily": "visual form",
            "projectileShape": "visual body", "projectileMotion": "visual motion", "projectileTrail": "visual trail", "projectileImpact": "visual impact",
        },
    },
    "perform_melee_attack": {
        "meaning": "Melee family executor.",
        "params": {
            "family": "broadsword|sword|axe|hammer|shortsword|rapier|dagger|spear|lance|pike|trident|halberd|naginata|jousting_lance|boomerang|chakram|flail|mace|anchor|yoyo|whip",
            "runtimeFamily": "omit; derived", "speed": "3..18", "rangeTiles": "2..80", "lifetimeTicks": "10..900", "pierce": "-1=infinite hits; 0 or 1=one target total; 2..10=total targets", "useTimeTicks": "10..150",
            "shotCount": "1..8 simultaneous emitted; not swing count", "spreadRadians": "0..0.75",
            "projectileShape": "body", "projectileMotion": "motion", "projectileTrail": "trail", "projectileImpact": "impact"
        },
    },
    "fire_ranged_weapon": {
        "meaning": "Ranged executor; charge_release holds, overhead_barrage spawns above target.",
        "params": {
            "family": "bow|repeater|gun|shotgun|launcher|rocket_launcher|dart|blowgun|harpoon|charge_release|overhead_barrage", "ammoFor": "empty custom; arrow|bullet consume vanilla ammo",
            "movement": "straight|gravity_arc|slow_homing|phase|proximity_missile|boomerang; phase passes tiles", "speed": "3..18", "rangeTiles": "10..120", "lifetimeTicks": "25..900", "shotCount": "1..8 simultaneous", "spreadRadians": "0..0.75", "pierce": "-1=infinite hits; 0 or 1=one target total; 2..10=total targets", "delayTicks": "0..300; barrage 0=immediate",
            "projectileFamily": "visual form; launcher+empty=custom rocket", "chargeTicks": "1..300 charge_release hold", "chargePowerMultiplier": "1..3 max power", "projectileShape": "body", "projectileMotion": "motion", "projectileTrail": "trail", "projectileImpact": "impact"
        },
    },
    "cast_magic_weapon": {
        "meaning": "Magic executor; beam channels, charge_release holds, overhead_barrage spawns above target.",
        "params": {
            "family": "staff|wand|rod|book|magic_gun|channelled_beam|charge_release|overhead_barrage|other exact family", "projectileFamily": "spear|bolt|beam|orb|etc",
            "movement": "straight|slow_homing|gravity_arc|phase|accelerate|vortex_orb|blackhole_pull|expanding_wave", "speed": "3..18", "rangeTiles": "8..120", "chargePowerMultiplier": "1..3 charge_release", "lifetimeTicks": "25..900", "shotCount": "1..8 simultaneous", "spreadRadians": "0..0.75", "pierce": "-1=infinite hits; 0 or 1=one target total; 2..10=total targets", "homingStrength": "0..1", "beamWidthPx": "2..96", "chargeTicks": "beam 0=full immediately; charge_release 1..300", "delayTicks": "0..300; barrage 0=immediate", "immunityCooldown": "4..60",
            "projectileShape": "body", "projectileMotion": "motion", "projectileTrail": "trail", "projectileImpact": "impact"
        },
    },
    "deploy_sentry": {
        "meaning": "Bounded Terraria sentry at cursor; stationary, targets NPCs, fires generated shots; not a minion.",
        "params": {"placement": "grounded|floating", "attackIntervalTicks": "12..180 ticks/volley", "targetRangeTiles": "8..60", "helperLifetimeTicks": "120..36000 root", "shotCount": "1..4 simultaneous/volley", "speed": "3..18", "spreadRadians": "0..0.75", "movement": "shot movement", "effect": "shot effect", "onHit": "none|non-child effect only", "projectileShape": "sentry body", "secondaryProjectileShape": "shot body", "secondaryLifetimeTicks": "5..180 shot lifetime; not sentry lifetime"},
    },
    "spawn_temporary_helper_projectile": {
        "meaning": "Temporary bounded helper projectile. It is not a persistent Terraria minion or sentry: no buff lifecycle, minion slots, sentry slots, automatic resummon, or save persistence. Use it only when a short-lived orbiting/drifting helper is the authored mechanic. Whips use perform_melee_attack family=whip.",
        "params": {
            "family": "|".join(sorted(TEMPORARY_HELPER_FAMILIES)), "movement": "orbit|slow_homing|drift|straight", "speed": "3..18", "rangeTiles": "8..120 target/orbit radius", "lifetimeTicks": "25..900 ticks; 60=1s", "shotCount": "1..4 simultaneous helpers", "pierce": "0/1 one hit; 2..10 total hits", "projectileShape": "temporary helper body"
        },
    },
    "spawn_secondary_projectiles": {
        "meaning": "Real secondary damaging projectiles, not VFX motes. Use only for actual child hits.",
        "params": {"trigger": "|".join(sorted(CANONICAL_SECONDARY_TRIGGERS)), "count": "0 off; 1..8 children", "damageMultiplier": "0..1 parent damage", "spreadRadians": "0..1.2 total spread", "lifetimeTicks": "5..180 child ticks", "sameTargetBias": "0..1 chance aim at hit target", "projectileShape": "optional child visual", "material": "optional child visual"},
    },
    "apply_on_hit_effect": {
        "meaning": "Real on-hit gameplay: debuffs, bursts, chained hits, child-producing effects, pull/heal/lifesteal. Visual-only impact belongs in spawn_contact_particles.",
        "params": {"onHit": "none|burst|split|chain|burn|frostburn|poison|shadowflame|bleed|starburst|overhead_barrage|aura_pulse|spore_cloud|mini_missiles|vortex_spawn|blackhole|radial_beams|lightning_arc|heal|lifesteal", "aoeRadiusTiles": "0..10", "count": "0..8 for child-producing onHit; overhead_barrage = bounded authored child projectiles descending from above the hit", "chainCount": "0..6 for chain-like effects", "pullStrength": "0..1", "debuffHint": "short text or empty"},
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
        "meaning": "Frozen VFX/audio slot; presentation only, no gameplay.",
        "params": {"event": "travel|active|tick|hit|kill|expire|while_held|while_equipped|on_use|on_alt_use", "rendererKind": "projectileAfterimage|spriteStampTrail|historyRibbon|tipTrail|ghostArc|wavyStrip|beamLine|fieldPulse|orbitingMotes|actorAfterimage|impactRing|impactSprite|childMotes|lightCue|soundCue", "channel": "motionTrail|coreGlow|ambientParticles|impactShape|impactParticles|decaySmoke|light|sound", "lane": "primary|support|accent|ornament|cue", "textureRole": "projectile|impact|child|field", "particleRole": "projectile|impact|child|field", "emissionMode": "wake|orbit|residue|burst|cone|ring|spiral|point", "particleSystemId": "pl:glow|pl:shard|pl:smoke|pl:spark|dust", "scale": "0.15..5", "density": "0..1", "duration": "3..120", "alpha": "0..1", "spread": "0..2", "jitter": "0..1.5", "startTick": "0..120", "repeatEvery": "0..120", "importance": "core|secondary|accent|luxury", "note": "short debug"},
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
        "params": {"lightStrength": "0..1.5", "lightColorName": "white|gray|brown|tan|red|orange|yellow|gold|green|cyan|blue|purple|pink", "generatedBuff": "generated buff object"},
    },
    "extractinator_output": {
        "meaning": "Explicit Extractinator material output via dedicated proxy item.",
        "params": {"resultType": "Terraria item id", "stack": "1..999"},
    },
    "use_affordance": {
        "meaning": "Non-damaging use/draw presentation.",
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

# Accepted by normalization for old/debug payloads, but intentionally omitted from
# the active planner prompt until a finite C# executor exists. Keeping this list next
# to the engine catalog makes the distinction obvious instead of hiding it in prompt code.
PLANNER_HIDDEN_ENGINE_FUNCTIONS = frozenset({"state_meter", "triggered_action"})



FORBIDDEN_WORLD_ENTITY_FN_NAMES = {
    "summon_boss", "spawn_boss", "call_boss", "boss_spawn", "boss_summon",
    "summon_npc", "spawn_npc", "create_npc", "npc_spawn", "npc_summon",
    "summon_mob", "spawn_mob", "spawn_enemy", "summon_enemy", "summon_monster", "spawn_monster",
}
FORBIDDEN_WORLD_ENTITY_FAMILIES = {
    "boss", "npc", "mob", "enemy", "monster", "town_npc", "townnpc", "critter",
    "slime", "zombie", "skeleton", "demon", "goblin", "worm", "boss_npc",
}
SAFE_SUMMON_FAMILIES = set(TEMPORARY_HELPER_FAMILIES) | {"minion", "sentry", "turret", "light_pet"}
STATE_METER_TRIGGERS = {"on_use", "on_alt_use", "on_hit_npc", "on_kill_npc", "on_projectile_impact", "while_held", "while_equipped"}
TRIGGERED_ACTION_TRIGGERS = STATE_METER_TRIGGERS | {"on_low_life", "after_not_hit_for_ticks", "while_moving", "while_airborne", "while_in_water"}
TRIGGERED_ACTION_KINDS = {
    "grant_charge", "spend_charge", "apply_generated_buff", "apply_vanilla_buff",
    "emit_light", "spawn_secondary_projectiles", "mobility_effect", "temporary_stat_boost",
    "spawn_particles", "set_mode", "cycle_mode",
}


# Exact cross-card fields accepted on primary attack calls.  They are documented
# once in the global sound/critical-value contract instead of duplicated into every
# function card.  This is a finite field set, not an alias or fuzzy compatibility map.
_PRIMARY_ATTACK_SHARED_PARAM_NAMES = frozenset({
    "effect", "useTimeTicks", "useAnimationTicks",
    "soundUseCatalogId", "soundImpactCatalogId", "soundVolume", "soundPitch", "soundPitchVariance",
})
_ENGINE_FN_ACCEPTED_PARAM_EXTRAS: dict[str, frozenset[str]] = {
    "shoot_projectile": _PRIMARY_ATTACK_SHARED_PARAM_NAMES,
    "perform_melee_attack": _PRIMARY_ATTACK_SHARED_PARAM_NAMES,
    "fire_ranged_weapon": _PRIMARY_ATTACK_SHARED_PARAM_NAMES,
    "cast_magic_weapon": _PRIMARY_ATTACK_SHARED_PARAM_NAMES,
    "apply_on_hit_effect": frozenset({"debuffTime"}),
}


def accepted_engine_param_names(fn: str) -> frozenset[str]:
    card = ENGINE_FN_CATALOG_V2.get(str(fn or ""), {})
    params = card.get("params") if isinstance(card, dict) else {}
    declared = frozenset(str(key) for key in params) if isinstance(params, dict) else frozenset()
    return declared | _ENGINE_FN_ACCEPTED_PARAM_EXTRAS.get(str(fn or ""), frozenset())

NUMERIC_LIMITS = {
    "useTimeTicks": (10.0, 150.0), "useAnimationTicks": (6.0, 150.0), "knockback": (0.0, 12.0), "manaCost": (0.0, 80.0), "shotCount": (1.0, 8.0), "pierce": (-1.0, 10.0),
    "aoeRadiusTiles": (0.0, 10.0), "homingStrength": (0.0, 1.0), "lifetimeTicks": (25.0, 900.0),
    "extraUpdates": (0.0, 3.0), "rangeTiles": (4.0, 120.0), "reliability": (0.45, 1.25),
    "selfLockTicks": (0.0, 120.0), "missPunish": (0.0, 1.0), "spreadRadians": (0.0, 0.75),
    "speed": (3.0, 18.0), "beamWidthPx": (2.0, 96.0), "beamChargeTicks": (0.0, 300.0), "chargeTicks": (1.0, 300.0), "chargePowerMultiplier": (1.0, 3.0), "delayTicks": (0.0, 300.0), "sentryAttackIntervalTicks": (12.0, 180.0), "sentryTargetRangeTiles": (8.0, 60.0), "sentryLifetimeTicks": (120.0, 36000.0), "immunityCooldown": (4.0, 60.0), "splitCount": (0.0, 8.0), "chainCount": (0.0, 6.0),
    "trailLength": (0.0, 24.0), "burstDustCap": (0.0, 40.0), "fieldRadiusTiles": (0.0, 6.0),
    "fieldLifetimeTicks": (0.0, 240.0), "secondaryDamageMultiplier": (0.0, 1.0),
    "secondarySpreadRadians": (0.0, 1.2), "secondaryLifetimeTicks": (5.0, 180.0), "sameTargetBias": (0.0, 1.0),
    "craftYield": (1.0, 999.0),
    "healLife": (0.0, 500.0), "healMana": (0.0, 500.0), "buffType": (0.0, 1024.0), "buffTime": (0.0, 21600.0),
    "pickPower": (0.0, 230.0), "axePower": (0.0, 50.0), "hammerPower": (0.0, 120.0),
    "lightStrength": (0.0, 1.5), "durationTicks": (1.0, 21600.0), "cooldownTicks": (0.0, 3600.0),
    "resultType": (0.0, 9999.0), "stack": (0.0, 999.0), "minLife": (0.0, 5000.0), "minMana": (0.0, 5000.0),
    "consumeChancePercent": (0.0, 100.0),
    "soundVolume": (0.05, 1.0), "soundPitch": (-0.9, 0.9), "soundPitchVariance": (0.0, 0.6),
    "scale": (0.15, 5.0), "density": (0.0, 1.0), "duration": (3.0, 120.0), "alpha": (0.0, 1.0), "spread": (0.0, 2.0), "jitter": (0.0, 1.5), "startTick": (0.0, 120.0), "repeatEvery": (0.0, 120.0),
    "maxValue": (1.0, 20.0), "initialValue": (0.0, 20.0), "gainOnUse": (0.0, 20.0), "gainOnHit": (0.0, 20.0),
    "gainOnKill": (0.0, 20.0), "spendOnUse": (0.0, 20.0), "spendOnAltUse": (0.0, 20.0),
    "decayPerSecond": (0.0, 20.0), "modeCount": (0.0, 8.0), "requiredValue": (0.0, 20.0), "spendValue": (0.0, 20.0),
}

INT_FIELDS = {"useTimeTicks", "useAnimationTicks", "manaCost", "lifetimeTicks", "beamChargeTicks", "chargeTicks", "delayTicks", "sentryAttackIntervalTicks", "sentryLifetimeTicks", "immunityCooldown", "shotCount", "pierce", "extraUpdates", "splitCount", "chainCount", "trailLength", "burstDustCap", "fieldLifetimeTicks", "craftYield", "healLife", "healMana", "buffType", "buffTime", "pickPower", "axePower", "hammerPower", "durationTicks", "cooldownTicks", "resultType", "stack", "minLife", "minMana", "consumeChancePercent", "maxValue", "initialValue", "gainOnUse", "gainOnHit", "gainOnKill", "spendOnUse", "spendOnAltUse", "modeCount", "requiredValue", "spendValue"}


__all__ = [
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
    "PLANNER_HIDDEN_ENGINE_FUNCTIONS",
    "FORBIDDEN_WORLD_ENTITY_FN_NAMES",
    "FORBIDDEN_WORLD_ENTITY_FAMILIES",
    "SAFE_SUMMON_FAMILIES",
    "STATE_METER_TRIGGERS",
    "TRIGGERED_ACTION_TRIGGERS",
    "TRIGGERED_ACTION_KINDS",
    "NUMERIC_LIMITS",
    "INT_FIELDS",
]
