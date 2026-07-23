from __future__ import annotations

from typing import Any

from infini_local.core.runtime_authoring.function_contract_registry import (
    ENGINE_FUNCTION_CONTRACT_BY_NAME,
    REPAIR_DEPENDENCY_GROUPS_BY_FUNCTION,
)

from infini_local.core.runtime_family_policy import (
    is_projectile_owned_family,
    keeps_item_body_damage_lane,
    runtime_family_accepts_delivery,
    runtime_family_accepts_movement,
    runtime_family_delivery_pairs,
    runtime_family_required_movements,
    uses_projectile_only_item_affordance,
)
from infini_local.core.runtime_secondary_policy import CANONICAL_SECONDARY_TRIGGERS
from infini_local.core.runtime_executor_vocabulary import MOVEMENT_CODE
from infini_local.core.runtime_authoring.vocabulary import normalize_authoring_token as _norm_name
from infini_local.core.vfx_composition_primitives import (
    vfx_cue_repair_combinations,
    vfx_cue_repair_values_allowed,
)


# AGENT MAP: static runtime authoring vocabulary/catalog/range schema.
# Runtime function vocabulary and bounds for the authoring package.

# Canonical active temporary-helper families. True sentry lifecycle is authored only
# through deploy_sentry; no legacy minion/sentry spellings are accepted here.
TEMPORARY_HELPER_FAMILIES = frozenset({"orbiter", "drone", "wisp", "temporary_turret", "pet_attack"})

COMBAT_EXECUTOR_RESULT_KINDS = frozenset({"weapon", "consumable_weapon"})


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
    elif keeps_item_body_damage_lane(runtime_family, delivery_token):
        # One root executor may preserve Terraria's body/tool swing while emitting
        # generated projectiles. This is a bounded carrier mode, not two controllers.
        out.update({"useStyleCode": USE_STYLE_SWING, "hideUseGraphic": False, "disableItemMeleeHitbox": False, "ownerHitCheck": False})
    elif is_projectile_owned_family(runtime_family):
        projectile_only = uses_projectile_only_item_affordance(runtime_family, delivery_token)
        out.update({"useStyleCode": USE_STYLE_SHOOT, "hideUseGraphic": projectile_only, "disableItemMeleeHitbox": projectile_only, "ownerHitCheck": runtime_family in {"whip", "beam"}})
        if runtime_family in {"yoyo", "beam"}:
            out["channelUse"] = True
    return out


PLANNER_HIDDEN_ENGINE_FUNCTIONS = frozenset()



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



def repair_param_dependency_groups(
    fn: str,
    selected_paths: set[str] | frozenset[str],
) -> tuple[frozenset[str], ...]:
    selected = {str(path).strip() for path in selected_paths if str(path).strip()}
    return tuple(
        group
        for group in REPAIR_DEPENDENCY_GROUPS_BY_FUNCTION.get(str(fn or ""), ())
        if group.intersection(selected)
    )


def repair_param_allowed_combinations(
    fn: str,
    group: frozenset[str],
    current_values: dict[str, Any] | None = None,
    *,
    result_kind: str = "",
) -> tuple[dict[str, str], ...]:
    if str(fn or "") == "shoot_projectile" and group == frozenset({"runtimeFamily", "delivery", "movement"}):
        current_movement = _norm_name((current_values or {}).get("movement"))
        combinations: list[dict[str, str]] = []
        for family, delivery in runtime_family_delivery_pairs():
            if family == "sentry":
                continue
            required_movements = runtime_family_required_movements(family)
            movements = sorted(required_movements)
            if not movements and current_movement and runtime_family_accepts_movement(family, current_movement):
                movements = [current_movement]
            combinations.extend(
                {"runtimeFamily": family, "delivery": delivery, "movement": movement}
                for movement in movements
            )
        return tuple(combinations)
    if str(fn or "") == "visual_effect_cue" and group == frozenset({"event", "rendererKind", "channel"}):
        return vfx_cue_repair_combinations(result_kind, current_values)
    if str(fn or "") == "set_alt_use_mode" and group == frozenset({"mode", "mobilityMode"}):
        current_mode = _norm_name((current_values or {}).get("mode"))
        if current_mode in {"recall_home", "blink_to_cursor"}:
            mobility_modes = (current_mode,)
        else:
            mobility_modes = ("recall_home", "blink_to_cursor")
        return tuple(
            {"mode": "mobility", "mobilityMode": mobility_mode}
            for mobility_mode in mobility_modes
        )
    if str(fn or "") == "spawn_contact_particles" and group == frozenset({"effect", "material"}):
        spec = ENGINE_FUNCTION_CONTRACT_BY_NAME["spawn_contact_particles"]
        enums = {param.name: tuple(param.enum_values) for param in spec.params}
        return tuple(
            {"effect": effect, "material": material}
            for effect in enums["effect"]
            for material in enums["material"]
            if material == "none" or effect in {"none", "dust"}
        )
    return ()


def repair_param_group_values_allowed(
    fn: str,
    group: frozenset[str],
    values: dict[str, Any],
    *,
    result_kind: str = "",
) -> bool:
    if str(fn or "") == "shoot_projectile" and group == frozenset({"runtimeFamily", "delivery", "movement"}):
        return (
            runtime_family_accepts_delivery(
                values.get("runtimeFamily"),
                values.get("delivery"),
            )
            and runtime_family_accepts_movement(
                values.get("runtimeFamily"),
                values.get("movement"),
            )
        )
    if str(fn or "") == "visual_effect_cue" and group == frozenset({"event", "rendererKind", "channel"}):
        return vfx_cue_repair_values_allowed(result_kind, values)
    if str(fn or "") == "set_alt_use_mode" and group == frozenset({"mode", "mobilityMode"}):
        return (
            _norm_name(values.get("mode")) == "mobility"
            and _norm_name(values.get("mobilityMode")) in {"recall_home", "blink_to_cursor"}
        )
    if str(fn or "") == "spawn_contact_particles" and group == frozenset({"effect", "material"}):
        effect = _norm_name(values.get("effect"))
        material = _norm_name(values.get("material"))
        return material == "none" or effect in {"none", "dust"}
    return True


NUMERIC_LIMITS = {
    "useTimeTicks": (10.0, 150.0), "useAnimationTicks": (6.0, 150.0), "knockback": (0.0, 12.0), "manaCost": (0.0, 80.0), "shotCount": (1.0, 8.0), "pierce": (-1.0, 10.0),
    "aoeRadiusTiles": (0.0, 10.0), "homingStrength": (0.0, 1.0), "lifetimeTicks": (25.0, 900.0),
    "extraUpdates": (0.0, 3.0), "rangeTiles": (4.0, 120.0),
    "spreadRadians": (0.0, 0.75),
    "speed": (3.0, 18.0), "beamWidthPx": (2.0, 96.0), "beamChargeTicks": (0.0, 300.0), "chargeTicks": (1.0, 300.0), "chargePowerMultiplier": (1.0, 3.0), "delayTicks": (0.0, 300.0), "sentryAttackIntervalTicks": (12.0, 180.0), "sentryTargetRangeTiles": (8.0, 60.0), "sentryLifetimeTicks": (120.0, 36000.0), "immunityCooldown": (0.0, 60.0), "splitCount": (0.0, 8.0), "chainCount": (0.0, 6.0), "pullStrength": (0.0, 1.0),
    "trailLength": (0.0, 24.0), "burstDustCap": (0.0, 40.0), "fieldRadiusTiles": (0.0, 6.0),
    "fieldLifetimeTicks": (0.0, 240.0), "tickRate": (1.0, 60.0), "secondaryDamageMultiplier": (0.0, 1.0),
    "secondarySpreadRadians": (0.0, 1.2), "secondaryLifetimeTicks": (5.0, 180.0), "sameTargetBias": (0.0, 1.0),
    "craftYield": (1.0, 999.0),
    "healLife": (0.0, 500.0), "healMana": (0.0, 500.0), "buffType": (0.0, 2147483647.0), "buffTime": (0.0, 21600.0),
    "pickPower": (0.0, 1000.0), "axePower": (0.0, 200.0), "hammerPower": (0.0, 1000.0),
    "lightStrength": (0.0, 1.5), "durationTicks": (1.0, 21600.0), "cooldownTicks": (0.0, 3600.0),
    "resultType": (0.0, 2147483647.0), "stack": (0.0, 999.0), "minLife": (0.0, 5000.0), "minMana": (0.0, 5000.0),
    "consumeChancePercent": (0.0, 100.0),
    "soundVolume": (0.05, 1.0), "soundPitch": (-0.9, 0.9), "soundPitchVariance": (0.0, 0.6),
    "scale": (0.15, 5.0), "density": (0.0, 1.0), "duration": (3.0, 120.0), "alpha": (0.0, 1.0), "spread": (0.0, 2.0), "jitter": (0.0, 1.5), "startTick": (0.0, 120.0), "repeatEvery": (0.0, 120.0),
    "maxValue": (1.0, 20.0), "initialValue": (0.0, 20.0), "gainOnUse": (0.0, 20.0), "gainOnHit": (0.0, 20.0),
    "gainOnKill": (0.0, 20.0), "spendOnUse": (0.0, 20.0), "spendOnAltUse": (0.0, 20.0),
    "decayPerSecond": (0.0, 20.0), "modeCount": (0.0, 8.0), "requiredValue": (0.0, 20.0), "spendValue": (0.0, 20.0),
    "createTile": (-1.0, 65535.0), "createWall": (-1.0, 65535.0), "placeStyle": (0.0, 1000.0),
}

INT_FIELDS = {"useTimeTicks", "useAnimationTicks", "manaCost", "lifetimeTicks", "beamChargeTicks", "chargeTicks", "delayTicks", "sentryAttackIntervalTicks", "sentryLifetimeTicks", "immunityCooldown", "shotCount", "pierce", "extraUpdates", "splitCount", "chainCount", "trailLength", "burstDustCap", "fieldLifetimeTicks", "tickRate", "craftYield", "healLife", "healMana", "buffType", "buffTime", "pickPower", "axePower", "hammerPower", "durationTicks", "cooldownTicks", "resultType", "stack", "minLife", "minMana", "consumeChancePercent", "maxValue", "initialValue", "gainOnUse", "gainOnHit", "gainOnKill", "spendOnUse", "spendOnAltUse", "modeCount", "requiredValue", "spendValue", "createTile", "createWall", "placeStyle"}


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
    "COMBAT_EXECUTOR_RESULT_KINDS",
    "PLANNER_HIDDEN_ENGINE_FUNCTIONS",
    "FORBIDDEN_WORLD_ENTITY_FN_NAMES",
    "FORBIDDEN_WORLD_ENTITY_FAMILIES",
    "SAFE_SUMMON_FAMILIES",
    "repair_param_allowed_combinations",
    "repair_param_dependency_groups",
    "repair_param_group_values_allowed",

    "NUMERIC_LIMITS",
    "INT_FIELDS",
]
