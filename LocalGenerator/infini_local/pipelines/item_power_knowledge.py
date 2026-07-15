from __future__ import annotations

import json
import math
import re
from typing import Any

from infini_local.core.category_policy import (
    ACCESSORY_HINT_TAGS,
    AMMO_HINT_TAGS,
    ARMOR_HINT_TAGS,
    TOOL_HINT_TAGS,
)
from infini_local.core.config_bootstrap import DATA_DIR
from infini_local.core.env_utils import env_bool, env_float, env_path, env_str
from infini_local.core.item_identity_tools import (
    dict_get_ci,
    fingerprint_of,
    generated_data_of,
    item_bool,
    item_field,
    item_identity,
    item_num,
    name_of,
    slug,
)
from infini_local.core.item_signals import HARD_TAGS, VISUAL_SYNONYMS, knowledge_key, wire_identity_names
from infini_local.core.runtime_authoring.normalize import runtime_plan
from infini_local.pipelines.result_identity_policy import (
    normalize_category,
    parent_primary_category,
    required_anchors_from_tags,
)
from infini_local.pipelines.item_rarity_baseline import (
    TIER_DEFAULT_POWER,
    rarity_details_of,
    rarity_baseline_signal,
)

from infini_local.pipelines.parent_context_pipeline import (
    projectile_behavior_tags,
    source_weapon_profile,
)
from infini_local.pipelines.pipeline_runtime_constants import LLM_RUNTIME_AUTHORING


# AGENT MAP: parent item signal, rarity baseline and generated item-knowledge cards.
# This module owns mechanical power/tier inference from live item facts and generated
# result cards. It deliberately avoids per-recipe outcome tables.


def _env_float(name: str, default: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return env_float(name, default, lo=lo, hi=hi)



# 0.0 = almost vanilla/logical, 1.0 = more surprise. The random is deterministic per recipe key.
CATEGORY_CREATIVITY = _env_float("INFINI_CATEGORY_CREATIVITY", 0.38)
# 1 = category is sampled before the LLM and then enforced; 0 = LLM may override within allowed categories.
CATEGORY_ENFORCE_SAMPLED = env_bool("INFINI_CATEGORY_ENFORCE_SAMPLED", False)
CATEGORY_SALT = env_str("INFINI_CATEGORY_SALT", "default")
RECURSIVE_POWER_GROWTH = _env_float("INFINI_RECURSIVE_POWER_GROWTH", 0.035, 0.0, 0.5)
UNIVERSAL_RECIPE_MODE = env_bool("INFINI_UNIVERSAL_RECIPE_MODE", True)
KNOWLEDGE_ENABLED = env_bool("INFINI_KNOWLEDGE_ENABLED", True)
ITEM_KNOWLEDGE_PATH = env_path("INFINI_ITEM_KNOWLEDGE_PATH", DATA_DIR / "item_knowledge.json")


def load_item_knowledge() -> dict[str, Any]:
    if not KNOWLEDGE_ENABLED:
        return {"items": {}, "patterns": []}
    try:
        if ITEM_KNOWLEDGE_PATH.exists():
            return json.loads(ITEM_KNOWLEDGE_PATH.read_text(encoding="utf-8-sig"))
    except Exception as e:
        print(f"[InfiniCrafterLocal] item knowledge load failed: {e!r}")
    return {"items": {}, "patterns": []}


ITEM_KNOWLEDGE = load_item_knowledge()

def fingerprint_tags(item: dict[str, Any]) -> set[str]:
    """Mechanics-derived tags. This is deliberately independent from rarity."""
    tags: set[str] = set()
    if item_num(item, "damage") > 0:
        tags.add("weapon")
    dc = str(item_field(item, "damageClass", "") or "").lower()
    if dc in {"melee", "ranged", "magic", "summon"}:
        tags.update({"weapon", dc})
    if item_bool(item, "accessory"):
        tags.add("accessory")
    if item_num(item, "defense") > 0 or item_num(item, "headSlot", -1) >= 0 or item_num(item, "bodySlot", -1) >= 0 or item_num(item, "legSlot", -1) >= 0:
        tags.add("armor")
    if item_num(item, "pickPower") > 0:
        tags.update({"tool", "pickaxe"})
    if item_num(item, "axePower") > 0:
        tags.update({"tool", "axe"})
    if item_num(item, "hammerPower") > 0:
        tags.update({"tool", "hammer"})
    if item_num(item, "healLife") > 0 or item_num(item, "healMana") > 0:
        tags.update({"potion", "consumable"})
    if item_num(item, "ammo") > 0 or item_num(item, "useAmmo") > 0:
        tags.add("ammo")
    if item_num(item, "shoot") > 0 and item_num(item, "damage") > 0:
        tags.add("projectile")
    tags |= projectile_behavior_tags(item)
    if item_num(item, "createTile", -1) >= 0 or item_num(item, "createWall", -1) >= 0:
        tags.add("placeable")
    if item_bool(item, "consumable"):
        tags.add("consumable")
    return tags


def is_currency_ammo_item(item: dict[str, Any], tags: set[str] | None = None) -> bool:
    """Coins are ammo/currency, not a full weapon anchor by themselves.

    Money Gun exists, so coin damage fields are real Terraria data, but a lone coin
    parent should not transfer lunar/post-Moon-Lord combat tier into generated tosses.
    """
    tags = set(tags or tags_of(item))
    return bool(
        "coin" in tags
        and "ammo" in tags
        and item_bool(item, "consumable")
        and item_num(item, "ammo", 0) > 0
        and item_num(item, "useAmmo", 0) <= 0
        and item_num(item, "maxStack", 1) > 1
    )


def is_low_tier_consumable_projectile_item(item: dict[str, Any], tags: set[str] | None = None) -> bool:
    """Stackable projectile consumables are poor progression anchors.

    Their direct damage is real and remains available to the authored result, but item
    use cadence plus a technical projectile lifetime/pierce snapshot must not price a
    disposable stack as a reusable late-game weapon.
    """
    tags = set(tags or tags_of(item))
    return bool(
        item_bool(item, "consumable")
        and item_num(item, "maxStack", 1) > 1
        and item_num(item, "damage", 0) > 0
        and item_num(item, "shoot", 0) > 0
        and item_num(item, "useAmmo", 0) <= 0
        and not item_bool(item, "channel")
        and (tags & {"ammo", "throwing", "ranged", "projectile", "dart", "shuriken", "knife", "consumable", "weapon"})
    )


def is_simple_low_tier_melee_weapon(item: dict[str, Any], tags: set[str] | None = None) -> bool:
    tags = set(tags or tags_of(item))
    return bool(
        item_num(item, "damage", 0) > 0
        and item_num(item, "damage", 0) <= 20
        and item_num(item, "shoot", 0) <= 0
        and not item_bool(item, "noMelee")
        and ("melee" in tags or str(item_field(item, "damageClass", "")).lower() == "melee")
    )

def mechanic_signal_power(item: dict[str, Any]) -> dict[str, Any]:
    """Item strength fingerprint.

    Runtime strength fingerprint. The runtime may use live stats, projectile behavior, rarity metadata and broad classification hints, but not hand-authored recipe graphs or per-item power-oracle tables.
    """
    dmg = item_num(item, "damage")
    pick = item_num(item, "pickPower")
    axe = item_num(item, "axePower")
    hammer = item_num(item, "hammerPower")
    defense = item_num(item, "defense")
    heal_life = item_num(item, "healLife")
    heal_mana = item_num(item, "healMana")
    mana = item_num(item, "manaCost", item_num(item, "mana"))
    shoot = item_num(item, "shoot")
    shoot_speed = item_num(item, "shootSpeed")
    knock = item_num(item, "knockback", item_num(item, "knockBack"))
    value = item_num(item, "value")
    tags = tags_of(item)
    category = parent_primary_category(item)
    rarity = rarity_baseline_signal(item, tags, category)
    rarity_signal = float(rarity.get("convertedPower") or 0.0)

    behavior = source_weapon_profile(item)
    behavior_signal = 0.0
    currency_ammo = is_currency_ammo_item(item, tags)
    consumable_projectile_anchor = is_low_tier_consumable_projectile_item(item, tags)
    simple_low_melee = is_simple_low_tier_melee_weapon(item, tags)
    if dmg > 0:
        behavior_signal = min(260.0, math.sqrt(max(0.0, float(behavior.get("effectiveDpsSignal") or 0))) * 12.0)
        if simple_low_melee:
            # Raw DPS on a fast starter melee item is not a boss-tier signal.
            behavior_signal = min(behavior_signal, dmg * 3.0 + 8.0)
        if currency_ammo:
            # Money Gun makes coin damage meaningful, but the coin alone is an ammo/currency
            # source, not a full weapon parent. Preserve the signal, but cap stage pressure.
            behavior_signal = min(behavior_signal, dmg * 0.45 + 14.0)
        if consumable_projectile_anchor:
            # Stackable projectiles are consumed inventory, not reusable roots.
            behavior_signal = min(behavior_signal, dmg * 2.4 + 18.0)
        if item_num(item, "useAmmo", 0) > 0:
            # Ammo supplies the real projectile body; Item.shoot fallback metadata may
            # describe a technical placeholder and cannot buy progression by itself.
            behavior_signal = min(behavior_signal, max(36.0, rarity_signal * 1.6, dmg * 2.5 + 12.0))
        if bool(behavior.get("minion")) or bool(behavior.get("sentry")):
            # Staff useTime is spawn cadence, not the persistent root's hit cadence.
            behavior_signal = min(behavior_signal, max(42.0, rarity_signal * 1.15, dmg * 2.5 + 12.0))
        if bool(behavior.get("ownerHitCheck")) or (
            float(behavior.get("piercePotential") or 0) >= 8.0
            and float(behavior.get("lifetime") or 0) >= 1800.0
        ):
            # Held/returning roots expose technical lifetime and infinite penetrate;
            # those fields describe lifecycle, not unconstrained simultaneous DPS.
            behavior_signal = min(behavior_signal, max(42.0, rarity_signal * 1.4, dmg * 3.0 + 10.0))

    # Practical power, not raw projectile theory. Avoid per-item exception tables here;
    # consumable/stack penalties are handled by generic economy fields and stage caps.
    damage_signal = max(
        dmg * 1.05 + min(10.0, knock * 1.2) + (8.0 if shoot > 0 and dmg > 0 else 0.0) + min(10.0, shoot_speed * 0.75),
        behavior_signal,
    )
    if simple_low_melee:
        damage_signal = min(damage_signal, dmg * 3.0 + 10.0)
    if currency_ammo:
        coin_value_hint = min(8.0, (value ** 0.5) * 0.14 if value > 0 else 0.0)
        damage_signal = min(damage_signal, dmg * 0.55 + 18.0 + coin_value_hint)
    if consumable_projectile_anchor:
        projectile_value_hint = min(6.0, (value ** 0.5) * 0.08 if value > 0 else 0.0)
        damage_signal = min(damage_signal, dmg * 2.35 + 20.0 + projectile_value_hint)
    tool_signal = max(pick * 1.35, axe * 7.0, hammer * 1.25)
    armor_signal = defense * 8.0
    heal_signal = max(heal_life * 0.55, heal_mana * 0.65)
    magic_signal = mana * 2.2 if dmg > 0 else 0.0
    value_signal = min(90.0, (value ** 0.5) * 0.14) if value > 0 else 0.0

    generic_mod_signal = generic_modded_progression_signal(item, tags, category, rarity)
    generic_mod_score = float(generic_mod_signal.get("score") or 0.0)

    primary = max(damage_signal, tool_signal, armor_signal, heal_signal, magic_signal)
    # Rarity is a strong baseline for unknown high-tier items, not just a tiny tie-breaker.
    # But mechanics still matter: if we have real combat/tool/armor stats, use them and add a small rarity lift.
    if primary <= 0:
        score = max(rarity_signal, value_signal, generic_mod_score)
        if generic_mod_score >= max(rarity_signal, value_signal):
            basis = "generic_modded_progression_signal"
        else:
            basis = "rarity_baseline" if rarity_signal >= value_signal else "value_baseline"
    else:
        score = max(primary, rarity_signal * 0.72, generic_mod_score) + min(max(value_signal, rarity_signal), 90.0) * 0.18
        basis = "mechanics_plus_rarity_baseline" if generic_mod_score <= max(primary, rarity_signal * 0.72) else "mechanics_plus_generic_modded_progression"
    if currency_ammo:
        score = min(score, 72.0)
        basis = (basis + "+currency_ammo_cap")[:80]
    if consumable_projectile_anchor:
        score = min(score, 54.0)
        basis = (basis + "+consumable_projectile_cap")[:80]
    if simple_low_melee:
        score = min(score, 42.0)
        basis = (basis + "+starter_melee_cap")[:80]
    return {
        "score": round(max(0.0, score), 2),
        "basis": basis,
        "damageSignal": round(damage_signal, 2),
        "toolSignal": round(tool_signal, 2),
        "armorSignal": round(armor_signal, 2),
        "healSignal": round(heal_signal, 2),
        "valueSignal": round(value_signal, 2),
        "raritySignal": round(rarity_signal, 2),
        "genericModdedSignal": generic_mod_signal,
        "rarityBaseline": rarity,
        "weaponBehavior": behavior,
    }


def generation_depth(item: dict[str, Any]) -> int:
    gd = generated_data_of(item)
    if not gd:
        return 0
    meta_raw = dict_get_ci(gd, "recipeMeta", {})
    debug_raw = dict_get_ci(gd, "debug", {})
    meta = meta_raw if isinstance(meta_raw, dict) else {}
    debug = debug_raw if isinstance(debug_raw, dict) else {}
    for source in (meta, debug):
        for key in ("generationDepth", "depth"):
            try:
                if key in source:
                    return max(1, int(float(source[key])))
            except Exception:
                pass
    return 1


def recipe_coherence(tags: set[str], a: dict[str, Any], b: dict[str, Any]) -> str:
    # This is deliberately broad: every pair is valid, but the corridor changes.
    if generation_depth(a) > 0 or generation_depth(b) > 0:
        return "recursive"
    hard = tags & HARD_TAGS
    if len(hard) >= 3:
        return "strong"
    if len(hard) >= 1 or max(int(a.get("damage") or 0), int(b.get("damage") or 0)) > 0:
        return "weak"
    return "nonsense"


def recipe_meta(a: dict[str, Any], b: dict[str, Any], tags: set[str], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    depths = [generation_depth(a), generation_depth(b)]
    coherence = recipe_coherence(tags, a, b)
    return {
        "universalRecipe": True,
        "generationDepth": max(depths) + 1,
        "parentGeneratedDepths": depths,
        "recipeCoherence": coherence,
        "chaosBudget": round(min(1.0, CATEGORY_CREATIVITY + 0.07 * max(depths) + (0.12 if coherence in {"weak", "nonsense"} else 0.0)), 3),
        "noveltyBudget": round(min(1.0, 0.18 + 0.08 * max(depths) + (0.18 if coherence == "recursive" else 0.0)), 3),
        "parentIdentities": [item_identity(a), item_identity(b)],
        "parentCategories": [parent_primary_category(a), parent_primary_category(b)],
        "sampledLane": (policy or {}).get("lane", ""),
        "sampledCategory": (policy or {}).get("selected", ""),
    }


def is_material_parent(item: dict[str, Any]) -> bool:
    # Material-ness for balance must come from live item mechanics, not words such
    # as "ore", "fragment" or "lunar" in a display name.
    return (
        int(item_num(item, "maxStack", 1)) > 1
        and int(item_num(item, "damage", 0)) <= 0
        and int(item_num(item, "defense", 0)) <= 0
        and int(item_num(item, "pick", 0)) <= 0
        and int(item_num(item, "axe", 0)) <= 0
        and int(item_num(item, "hammer", 0)) <= 0
        and int(item_num(item, "healLife", 0)) <= 0
        and int(item_num(item, "healMana", 0)) <= 0
        and not bool(item_field(item, "accessory", False))
    )


def material_catalyst_pressure(item: dict[str, Any], weapon_tags: set[str] | None = None) -> dict[str, Any]:
    """Progression pressure from live material facts, never fantasy tokens.

    tModLoader rarity class metadata and sell value are observable. Words such as
    ``lunar``, ``hero`` or ``fragment`` are not. ``weapon_tags`` remains in the signature
    for call compatibility but deliberately cannot alter power.
    """
    _ = weapon_tags
    tags = tags_of(item)
    rare = int(item_num(item, "rare", 0))
    value = max(0.0, item_num(item, "value", 0))
    pressure = 0.0
    reasons: list[str] = []
    if not is_material_parent(item):
        return {"pressure": 0.0, "reasons": []}
    if rare >= 2:
        pressure += min(0.85, rare * 0.08)
        reasons.append("rarity")
    if value >= 10000:
        pressure += min(0.75, math.sqrt(value) / 520.0)
        reasons.append("value")
    rarity = rarity_baseline_signal(item, tags, parent_primary_category(item))
    if str(rarity.get("role") or "").startswith(("calamity_rarity_class", "special_rarity_class")):
        pressure += min(0.6, float(rarity.get("convertedPower") or 0.0) / 900.0)
        reasons.append("recognized_mod_rarity_class")
    pressure = max(0.0, min(2.2, pressure))
    return {"pressure": round(pressure, 3), "reasons": reasons}


def pair_catalyst_pressure(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    ta, tb = tags_of(a), tags_of(b)
    pa = material_catalyst_pressure(a, tb)
    pb = material_catalyst_pressure(b, ta)
    total = max(float(pa.get("pressure") or 0), float(pb.get("pressure") or 0))
    return {"pressure": round(total, 3), "left": pa, "right": pb}

def lower_name(item: dict[str, Any]) -> str:
    return name_of(item).lower()


def tags_of(item: dict[str, Any]) -> set[str]:
    # Internal tags are mechanically derived from runtime fields/name tokens/generated parents.
    # Vanilla/modded input payloads do not need hand-authored semantic tags.
    tags = {str(t).lower() for t in item.get("tags", []) if str(t).strip()}
    tags |= {str(t).lower() for t in item.get("autoFeatures", []) if str(t).strip()}
    tags |= {str(t).lower() for t in item.get("nameTokens", []) if str(t).strip()}
    gd = item.get("generatedData")
    if isinstance(gd, dict):
        tags |= {str(t).lower() for t in dict_get_ci(gd, "tags", []) if str(t).strip()}
        can = dict_get_ci(gd, "canonical", {}) or {}
        tags |= {str(t).lower() for t in dict_get_ci(can, "hardTags", []) if str(t).strip()}
        tags |= {str(t).lower() for t in dict_get_ci(can, "softTags", []) if str(t).strip()}
    fp = fingerprint_of(item)
    if isinstance(fp, dict):
        tags |= {str(t).lower() for t in fp.get("autoFeatures", []) if str(t).strip()}
        tags |= {str(t).lower() for t in fp.get("nameTokens", []) if str(t).strip()}
    tags |= fingerprint_tags(item)
    source_mod = str(item_field(item, "sourceMod", "Terraria") or "")
    if source_mod and source_mod.lower() != "terraria":
        tags.add("modded")
        tags.add("mod_" + slug(source_mod))
    names_blob = " ".join(str(x or "") for x in [
        name_of(item),
        item_field(item, "internalName", ""),
        item_field(item, "fullName", ""),
        item_field(item, "typeName", ""),
    ]).lower()
    n = names_blob
    def add_if(substr: str, *add: str):
        if substr in n:
            tags.update(add)
    add_if("wooden", "wood")
    add_if("wood", "wood")
    add_if("dirt", "dirt", "earth", "block", "material", "placeable")
    add_if("stone", "stone", "block", "material", "placeable")
    add_if("sand", "sand", "block", "material", "placeable")
    add_if("mud", "mud", "earth", "block", "material", "placeable")
    add_if("clay", "clay", "earth", "block", "material", "placeable")
    add_if("block", "block", "material", "placeable")
    add_if("ore", "ore", "material")
    add_if("bar", "bar", "material")
    add_if("coin", "coin", "material")
    add_if("chair", "chair", "furniture", "placeable")
    add_if("wire", "wire", "electric", "mechanism")
    add_if("electric", "electric")
    add_if("star", "star", "light", "mana")
    add_if("fallen star", "star", "light", "mana")
    add_if("daybloom", "daybloom", "flower", "plant", "day")
    add_if("sunflower", "sunflower", "flower", "plant", "sun", "day")
    add_if("flower", "flower", "plant")
    add_if("gel", "gel", "slime")
    add_if("slime", "slime")
    add_if("circuit", "circuit", "technology", "electric")
    add_if("work bench", "workbench", "bench", "crafting_station", "wood")
    add_if("workbench", "workbench", "bench", "crafting_station", "wood")
    add_if("computer", "computer", "technology", "screen")
    add_if("virtual reality", "vr", "headset", "technology")
    add_if("vr", "vr", "headset", "technology")
    add_if("headset", "headset", "technology")
    add_if("boot", "accessory", "mobility", "boots")
    add_if("treads", "accessory", "mobility", "boots")
    add_if("aglet", "accessory", "mobility", "aglet")
    add_if("anklet", "accessory", "mobility", "anklet")
    add_if("wing", "accessory", "mobility", "wings")
    add_if("shield", "accessory", "defense", "shield")
    add_if("guard", "accessory", "defense", "shield")
    add_if("emblem", "accessory", "damage", "emblem")
    add_if("charm", "accessory", "charm")
    add_if("ring", "accessory", "ring", "charm")
    add_if("band", "accessory", "band", "charm")
    add_if("necklace", "accessory", "necklace", "charm")
    add_if("amulet", "accessory", "amulet", "charm")
    add_if("glove", "accessory", "melee", "glove")
    add_if("claw", "accessory", "melee", "glove")
    add_if("balloon", "accessory", "mobility", "balloon")
    add_if("horseshoe", "accessory", "mobility", "horseshoe")
    add_if("pickaxe", "tool", "pickaxe")
    add_if("hammer", "tool", "hammer")
    add_if("drill", "tool", "drill")
    add_if("axe", "tool", "axe")
    add_if("chainsaw", "tool", "chainsaw", "axe")
    add_if("hook", "grappling_hook", "hook")
    add_if("arrow", "ammo", "arrow")
    add_if("bullet", "ammo", "bullet")
    add_if("rocket", "ammo", "rocket", "explosive")
    add_if("helmet", "armor", "helmet")
    add_if("breastplate", "armor", "breastplate")
    add_if("greaves", "armor", "leggings")
    add_if("sword", "weapon", "melee", "sword")
    add_if("blade", "weapon", "melee", "blade")
    add_if("bow", "weapon", "ranged", "bow")
    add_if("gun", "weapon", "ranged", "gun")
    add_if("rifle", "weapon", "ranged", "gun")
    add_if("wand", "weapon", "magic", "wand")
    add_if("staff", "weapon", "magic", "staff")
    add_if("potion", "potion", "consumable")
    add_if("healing", "potion", "healing", "heal")
    add_if("lesserhealing", "potion", "healing", "heal")
    add_if("lesser healing", "potion", "healing", "heal")
    add_if("mana", "potion", "mana")
    add_if("glowstick", "glowstick", "light", "throwing", "projectile")
    add_if("glow stick", "glowstick", "light", "throwing", "projectile")
    add_if("mushroom", "mushroom", "plant", "consumable")
    add_if("glowingmushroom", "glowing", "mushroom", "light")
    add_if("glowing mushroom", "glowing", "mushroom", "light")
    add_if("shuriken", "weapon", "ranged", "throwing", "shuriken")
    add_if("throwingknife", "weapon", "ranged", "throwing", "knife")
    add_if("throwing knife", "weapon", "ranged", "throwing", "knife")
    add_if("knife", "weapon", "ranged", "throwing", "knife")
    add_if("banner", "banner", "furniture", "placeable")
    add_if("bomb", "bomb", "explosive", "throwing")
    add_if("grenade", "grenade", "explosive", "throwing")
    add_if("dynamite", "dynamite", "explosive", "throwing")
    add_if("obsidian", "obsidian", "lava", "fire")
    add_if("lava", "lava", "fire")
    # High-tier material keywords. These are only hints; exact tier comes from item_knowledge.json/runtime item facts.
    add_if("luminite", "luminite", "lunar", "moon_lord", "endgame_material", "material")
    add_if("solar fragment", "solar", "fragment", "lunar", "melee", "material")
    add_if("vortex fragment", "vortex", "fragment", "lunar", "ranged", "material")
    add_if("nebula fragment", "nebula", "fragment", "lunar", "magic", "material")
    add_if("stardust fragment", "stardust", "fragment", "lunar", "summon", "material")
    add_if("fragment", "fragment", "material")
    add_if("hallowed", "hallowed", "holy", "material")
    add_if("chlorophyte", "chlorophyte", "jungle", "plant", "material")
    add_if("shroomite", "shroomite", "mushroom", "ranged", "material")
    add_if("spectre", "spectre", "magic", "ghost", "material")
    add_if("beetle", "beetle", "golem", "material")
    add_if("auric", "auric", "tesla", "post_moonlord", "endgame_material", "material")
    add_if("cosmilite", "cosmilite", "cosmic", "post_moonlord", "endgame_material", "material")
    add_if("exodium", "exodium", "cosmic", "post_moonlord", "material")
    add_if("uelibloom", "uelibloom", "jungle", "post_moonlord", "material")
    add_if("shadowspec", "shadowspec", "shadow", "superboss", "endgame_material", "material")
    tags |= projectile_behavior_tags(item)
    if int(item.get("damage") or 0) > 0 and not (tags & (TOOL_HINT_TAGS | ARMOR_HINT_TAGS | ACCESSORY_HINT_TAGS | AMMO_HINT_TAGS)):
        tags.add("weapon")
    if item.get("accessory"):
        tags.add("accessory")
    if item.get("consumable"):
        tags.add("consumable")
    if int(item.get("createTile") or -1) >= 0:
        tags.add("placeable")
    return tags


def guess_head(name: str, tags: set[str]) -> str:
    for t in ["boots", "wings", "shield", "emblem", "charm", "ring", "glove", "accessory", "dirt", "stone", "sand", "block", "material", "chair", "wire", "headset", "computer", "circuit", "workbench", "bench", "potion", "sword", "blade", "bow", "gun", "wand", "staff", "flower", "daybloom", "star", "gel", "slime", "tool", "pickaxe", "axe", "hammer", "drill", "chainsaw", "ammo", "armor"]:
        if t in tags:
            return t
    parts = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", name)
    return (parts[-1].lower() if parts else "item")


def canonicalize(item: dict[str, Any]) -> dict[str, Any]:
    gd = item.get("generatedData")
    if isinstance(gd, dict) and gd.get("canonical"):
        c = dict(gd["canonical"])
        # Ensure arrays exist.
        for k in ["modifiers", "shapeAnchors", "visualAnchors", "hardTags", "softTags"]:
            c.setdefault(k, [])
        return c
    tags = tags_of(item)
    n = name_of(item)
    head = guess_head(n, tags)
    material = "wood" if "wood" in tags else "dirt" if "dirt" in tags or "earth" in tags else "stone" if "stone" in tags else "sand" if "sand" in tags else "iron" if "iron" in tags else "gold" if "gold" in tags else ""
    cls = "accessory" if "accessory" in tags else "weapon" if "weapon" in tags else "consumable" if "consumable" in tags else "tool" if "tool" in tags else "ammo" if "ammo" in tags else "armor" if "armor" in tags else "placeable" if "placeable" in tags else "material" if "material" in tags or "block" in tags else "generic"
    visual = required_anchors_from_tags(tags)
    if not visual:
        visual = [n]
    hard = sorted(t for t in tags if t in HARD_TAGS)
    soft = sorted(t for t in tags if t not in hard)
    modifiers = []
    if "wood" in tags or "wooden" in n.lower():
        modifiers.append("wooden")
    if "virtual reality" in n.lower():
        modifiers.append("virtual reality")
    return {
        "headNoun": head,
        "modifiers": modifiers,
        "material": material,
        "class": cls,
        "shapeAnchors": sorted(set([head] + VISUAL_SYNONYMS.get(head, []))),
        "visualAnchors": sorted(set(visual)),
        "hardTags": hard,
        "softTags": soft,
    }


# -----------------------------------------------------------------------------
# Runtime item knowledge / classification cards
# -----------------------------------------------------------------------------


# Terraria vanilla rarity is an approximate progression signal.
# Calamity and other mods add real ModRarity classes; their runtime numeric ids are not stable semantic tiers.
# Prefer rarityDetails.name/mod/color when C# provides it, then fall back to raw Item.rare.

# Semantic ladder for Calamity ModRarity classes. These are not just anonymous ids above 11:
# they have class names and colors in the mod code, and prefix rarity can shift them.


def generic_modded_progression_signal(item: dict[str, Any], tags: set[str] | None = None, category: str | None = None, rarity: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generic non-vanilla progression signal without per-mod material name tables.

    This deliberately does not claim a stage. It only says: the live item looks high-tier
    because of raw ModRarity/value/combat/tool/armor signals. The LLM still authors the result.
    """
    source_mod = str(item_field(item, "sourceMod", "Terraria") or "Terraria")
    if not source_mod or source_mod.lower() == "terraria":
        return {"score": 0.0, "confidence": 0.0, "reasons": []}
    tags = set(tags or tags_of(item))
    category = normalize_category(category or parent_primary_category(item))
    rarity = rarity or rarity_baseline_signal(item, tags, category)
    reasons: list[str] = ["non_vanilla_source"]
    score = 0.0
    conf = 0.35
    try:
        raw_rare = int(rarity.get("rawRare") or item_num(item, "rare", 0))
    except Exception:
        raw_rare = 0
    tier_score = float(rarity.get("tierScore") or 0.0)
    converted = float(rarity.get("convertedPower") or 0.0)
    if raw_rare > 11 or str(rarity.get("role") or "").startswith("unknown_modded"):
        score = max(score, converted, tier_score * (0.72 if category in {"material", "generic"} else 0.82))
        conf = max(conf, 0.52)
        reasons.append("modded_rarity")
    value = max(0.0, item_num(item, "value", 0))
    if value >= 50000:
        # Sell value is noisy, but it is one of the only generic progression signals for arbitrary mods.
        value_score = min(560.0, 80.0 + math.log1p(value / 50000.0) * 115.0)
        score = max(score, value_score)
        conf = max(conf, 0.46)
        reasons.append("high_value")
    dmg = item_num(item, "damage", 0)
    if dmg > 0:
        prof = source_weapon_profile(item)
        mech = min(620.0, math.sqrt(max(0.0, float(prof.get("effectiveDpsSignal") or 0.0))) * 13.5)
        score = max(score, mech)
        conf = max(conf, 0.58)
        reasons.append("combat_stats")
    tool = max(item_num(item, "pickPower", 0) * 1.35, item_num(item, "axePower", 0) * 7.0, item_num(item, "hammerPower", 0) * 1.25)
    if tool > 0:
        score = max(score, min(520.0, tool))
        conf = max(conf, 0.54)
        reasons.append("tool_stats")
    defense = item_num(item, "defense", 0)
    if defense > 0:
        score = max(score, min(520.0, defense * 9.0))
        conf = max(conf, 0.54)
        reasons.append("armor_stats")
    return {"score": round(max(0.0, score), 2), "confidence": round(min(0.78, conf), 2), "reasons": reasons, "sourceMod": source_mod, "rarity": rarity}


def known_item_entry(item: dict[str, Any]) -> dict[str, Any] | None:
    if not KNOWLEDGE_ENABLED:
        return None
    items = ITEM_KNOWLEDGE.get("items") or {}
    candidates = set(wire_identity_names(item))
    name = knowledge_key(name_of(item))
    candidates.add(name)
    # Generated names often preserve the real parent after a prefix.
    candidates.add(re.sub(r"^(generated|infini|triple generated|triple compacted)\s+", "", name).strip())
    for cand in list(candidates):
        if cand in items:
            return dict(items[cand])
    # Also allow a normalized key without spaces for internal IDs from mods.
    compact_items = {knowledge_key(k).replace(" ", ""): v for k, v in items.items()}
    for cand in list(candidates):
        compact = cand.replace(" ", "")
        if compact in compact_items:
            return dict(compact_items[compact])
    for pattern in ITEM_KNOWLEDGE.get("patterns") or []:
        contains = [knowledge_key(x) for x in pattern.get("contains", [])]
        if contains and all(any(x in cand for cand in candidates) for x in contains):
            return dict(pattern)
    return None


def runtime_recipe_frame_for_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Runtime-safe recipe frame.

    Hand-authored mod recipe graphs were intentionally removed in v2.7.
    A future adapter may feed live tModLoader Recipe data here.
    Runtime archives should not include hand-scored training examples.
    """
    rf = entry.get("runtimeRecipeFrame") if isinstance(entry, dict) else None
    return dict(rf) if isinstance(rf, dict) else {}


def stat_signal_power(item: dict[str, Any]) -> float:
    return float(mechanic_signal_power(item).get("score") or 0)


def infer_item_card(item: dict[str, Any], canonical: dict[str, Any] | None = None) -> dict[str, Any]:
    # Cached/generated result cards and item-name knowledge are descriptive context only.
    # Recompute progression from the live Terraria item facts every time.
    _ = canonical
    tags = set(tags_of(item))
    entry = known_item_entry(item) or {}
    tags |= {str(t).lower() for t in entry.get("tags", []) if str(t).strip()}
    category = normalize_category(parent_primary_category(item))
    tier = "unknown"
    signal = mechanic_signal_power(item)
    signal_power = float(signal.get("score") or 0)
    rarity_base = rarity_baseline_signal(item, set(), category)
    rarity_power = float(rarity_base.get("convertedPower") or 0)
    depth = generation_depth(item)
    power = max(signal_power, rarity_power)
    if power <= 0:
        if is_material_parent(item):
            power = max(8.0, rarity_power)
        elif int(item_num(item, "damage", 0)) > 0:
            power = max(10.0, int(item_num(item, "damage", 0)) * 1.05, rarity_power * 0.72)
        else:
            power = max(5.0, rarity_power * 0.65)
    for candidate, default in sorted(TIER_DEFAULT_POWER.items(), key=lambda kv: kv[1], reverse=True):
        if power >= default * 0.92:
            tier = candidate
            break
    if tier == "unknown":
        tier = "trash" if power < 8 else "early"
    confidence = 0.48
    if str(signal.get("basis", "")).startswith("mechanics"):
        confidence = 0.66
    if rarity_power > signal_power:
        confidence = max(confidence, 0.58 if int(rarity_base.get("rawRare") or 0) <= 11 else 0.52)
    return {
        "name": name_of(item),
        "identity": item_identity(item),
        "category": category,
        "tier": tier,
        "powerScore": round(power, 2),
        "confidence": round(min(0.98, confidence), 2),
        "sourceHint": "live rarity metadata + Terraria mechanics" if rarity_power > 0 else "live Terraria mechanics",
        "tags": sorted(tags),
        "generatedDepth": depth,
        "recipeFrame": runtime_recipe_frame_for_entry(entry),
        "signals": {
            "damage": int(item_num(item, "damage")),
            "rare": int(item_num(item, "rare")),
            "rarityDetails": rarity_details_of(item),
            "value": int(item_num(item, "value")),
            "pickPower": int(item_num(item, "pickPower")),
            "axePower": int(item_num(item, "axePower")),
            "hammerPower": int(item_num(item, "hammerPower")),
            "defense": int(item_num(item, "defense")),
            "healLife": int(item_num(item, "healLife")),
            "healMana": int(item_num(item, "healMana")),
            "sourceMod": str(item_field(item, "sourceMod", "Terraria")),
            "internalName": str(item_field(item, "internalName", "")),
            "mechanicPower": signal,
            "rarityBaseline": rarity_base,
            "isMaterial": is_material_parent(item),
            "isGenerated": depth > 0,
        },
    }


def build_item_knowledge(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any] | None = None, cb: dict[str, Any] | None = None) -> dict[str, Any]:
    cards = [infer_item_card(a, ca), infer_item_card(b, cb)]
    strongest = max(cards, key=lambda c: float(c.get("powerScore") or 0))
    material_cards = [c for c in cards if c.get("category") == "material" or c.get("signals", {}).get("isMaterial")]
    strongest_material = max(material_cards, key=lambda c: float(c.get("powerScore") or 0), default=None)
    tags = []
    for c in cards:
        tags.extend(c.get("tags") or [])
    return {
        "enabled": KNOWLEDGE_ENABLED,
        "parents": cards,
        "strongestTier": strongest.get("tier", "unknown"),
        "strongestPowerScore": strongest.get("powerScore", 0),
        "strongestSourceHint": strongest.get("sourceHint", ""),
        "strongestMaterialTier": (strongest_material or {}).get("tier", ""),
        "strongestMaterialPowerScore": (strongest_material or {}).get("powerScore", 0),
        "tagsFromKnowledge": sorted(set(str(t).lower() for t in tags)),
    }


def apply_item_knowledge(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any]) -> dict[str, Any]:
    knowledge = build_item_knowledge(a, b, ca, cb)
    data["itemKnowledge"] = knowledge
    # v0.4.24 prompt validation slim: parent knowledge is validator/debug context.
    # Do not inject inferred parent tags into LLM-authored result tags in runtime authoring mode,
    # because that makes later VFX/category layers behave as if the code authored semantics.
    tags = set(str(t).lower() for t in data.get("tags", []))
    if not (LLM_RUNTIME_AUTHORING and runtime_plan(data)):
        tags |= set(knowledge.get("tagsFromKnowledge") or [])
    data["tags"] = sorted(tags)
    dbg = data.setdefault("debug", {})
    dbg["itemKnowledge"] = json.dumps(knowledge, ensure_ascii=False)
    dbg["itemKnowledgeTagMerge"] = "disabled_runtime_authoring" if (LLM_RUNTIME_AUTHORING and runtime_plan(data)) else "enabled_non_runtime_fallback"
    return data


def item_knowledge_power(data: dict[str, Any]) -> float:
    k = data.get("itemKnowledge") if isinstance(data.get("itemKnowledge"), dict) else {}
    try:
        return float(k.get("strongestPowerScore") or 0)
    except Exception:
        return 0.0

__all__ = [
    "CATEGORY_CREATIVITY",
    "CATEGORY_ENFORCE_SAMPLED",
    "CATEGORY_SALT",
    "RECURSIVE_POWER_GROWTH",
    "UNIVERSAL_RECIPE_MODE",
    "KNOWLEDGE_ENABLED",
    "ITEM_KNOWLEDGE_PATH",
    "LLM_RUNTIME_AUTHORING",
    "load_item_knowledge",
    "ITEM_KNOWLEDGE",
    "fingerprint_tags",
    "is_currency_ammo_item",
    "is_low_tier_consumable_projectile_item",
    "is_simple_low_tier_melee_weapon",
    "mechanic_signal_power",
    "generation_depth",
    "recipe_coherence",
    "recipe_meta",
    "is_material_parent",
    "material_catalyst_pressure",
    "pair_catalyst_pressure",
    "lower_name",
    "tags_of",
    "guess_head",
    "canonicalize",
    "generic_modded_progression_signal",
    "known_item_entry",
    "runtime_recipe_frame_for_entry",
    "stat_signal_power",
    "infer_item_card",
    "build_item_knowledge",
    "apply_item_knowledge",
    "item_knowledge_power",
]
