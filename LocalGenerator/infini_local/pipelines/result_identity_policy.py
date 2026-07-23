from __future__ import annotations

import json
import re
from typing import Any

from infini_local.core.category_policy import (
    ACCESSORY_HINT_TAGS,
    ALLOWED_CATEGORIES,
    AMMO_HINT_TAGS,
    ARMOR_HINT_TAGS,
    PLACEABLE_HINT_TAGS,
    STRONG_ACCESSORY_TAGS,
    TOOL_HINT_TAGS,
    WEAPON_UPGRADE_TAGS,
)
from infini_local.core.env_utils import env_bool, env_float, env_str

from infini_local.core.item_identity_tools import (
    generated_data_of,
    generation_depth,
    item_bool,
    item_identity,
    item_num,
    name_of,
    stable_hash,
    tags_of,
)
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.item_signals import HARD_TAGS, VISUAL_SYNONYMS



# AGENT MAP: result identity/category policy seam for combine_pipeline.
# Owns generated item naming, category sampling/coercion, canonical result
# representation helpers and palette/anchor derivation. Callers import this
# owner directly; combine_pipeline is not a compatibility API.

CATEGORY_CREATIVITY = env_float("INFINI_CATEGORY_CREATIVITY", 0.38)
CATEGORY_ENFORCE_SAMPLED = env_bool("INFINI_CATEGORY_ENFORCE_SAMPLED", False)
CATEGORY_SALT = env_str("INFINI_CATEGORY_SALT", "default")

BAD_NAME_PATTERNS = [
    re.compile(r"^\s*infini(?:\s|$|[-_])", re.I),
    re.compile(r"^\s*generated(?:\s|$|[-_])", re.I),
    re.compile(r"^\s*combined(?:\s|$|[-_])", re.I),
    re.compile(r"\bhybrid\b", re.I),
]

PALETTES = {
    "wood": ["brown", "tan", "dark_brown"],
    "wire": ["dark_gray", "yellow"],
    "electric": ["yellow", "cyan", "white"],
    "star": ["gold", "white", "blue"],
    "daybloom": ["yellow", "green", "white"],
    "flower": ["green", "yellow", "pink"],
    "slime": ["green", "cyan"],
    "shadow": ["purple", "black"],
    "fire": ["orange", "red", "yellow"],
    "ice": ["cyan", "white", "blue"],
    "technology": ["dark_gray", "cyan", "blue"],
    "accessory": ["silver", "gold", "blue"],
    "boots": ["brown", "silver", "blue"],
    "wings": ["white", "blue", "gold"],
    "shield": ["gray", "silver", "dark_gray"],
    "emblem": ["gold", "red", "white"],
    "charm": ["gold", "purple", "cyan"],
    "tool": ["brown", "gray", "silver"],
    "axe": ["brown", "steel", "green"],
    "drill": ["gray", "yellow", "blue"],
    "ammo": ["gray", "brass", "red"],
    "armor": ["gray", "silver", "blue"],
    "dirt": ["brown", "tan", "dark_brown"],
    "earth": ["brown", "green", "tan"],
    "stone": ["gray", "dark_gray", "white"],
    "sand": ["tan", "yellow", "white"],
    "block": ["gray", "brown", "tan"],
    "material": ["gray", "tan", "white"],
    "coin": ["gold", "silver", "copper"],
}

# Visual tag order must not depend on Python's randomized ``set`` iteration.
# The insertion order of the canonical dictionaries is intentional and is the
# only policy here: this helper does not reinterpret a parent or decide how its
# silhouette must be fused into the result.
def _ordered_known_tags(tags: set[str], canonical: dict[str, Any]) -> list[str]:
    known = [key for key in canonical if key in tags]
    unknown = sorted(str(tag) for tag in tags if tag not in canonical)
    return known + unknown


def guess_head(name: str, tags: set[str]) -> str:
    for t in ["boots", "wings", "shield", "emblem", "charm", "ring", "glove", "accessory", "dirt", "stone", "sand", "block", "material", "chair", "wire", "headset", "computer", "circuit", "workbench", "bench", "potion", "sword", "blade", "bow", "gun", "wand", "staff", "flower", "daybloom", "star", "gel", "slime", "tool", "pickaxe", "axe", "hammer", "drill", "chainsaw", "ammo", "armor"]:
        if t in tags:
            return t
    parts = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", name)
    return (parts[-1].lower() if parts else "item")

def clean_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9А-Яа-яЁё]+", "", s) or "Item"

def theme_word(tags: set[str]) -> str:
    # Non-final fallback word only; final result names are produced by creative_result_name().
    if "star" in tags: return "Astral"
    if "slime" in tags or "gel" in tags: return "Gelatinous"
    if "wire" in tags or "electric" in tags: return "Electric"
    if "daybloom" in tags or "flower" in tags: return "Blooming"
    if "shadow" in tags or "night" in tags: return "Umbral"
    if "fire" in tags: return "Ember"
    if "ice" in tags or "frost" in tags: return "Frost"
    if "technology" in tags or "circuit" in tags: return "Circuit"
    if "dirt" in tags or "earth" in tags: return "Loam"
    if "stone" in tags: return "Stonebound"
    if "sand" in tags: return "Sandy"
    if "lunar" in tags or "moon" in tags: return "Moonlit"
    if "gun" in tags or "rifle" in tags: return "Locksteel"
    if "sword" in tags or "blade" in tags: return "Edgewise"
    return "Patchwork"

def title_words(text: str) -> str:
    parts = re.findall(r"[A-Za-zА-Яа-яЁё0-9']+", str(text or ""))
    return " ".join(w[:1].upper() + w[1:] for w in parts)

def bad_result_name(name: Any, a: dict[str, Any] | None = None, b: dict[str, Any] | None = None) -> bool:
    n = str(name or "").strip()
    if len(n) < 3 or len(n) > 48:
        return True
    if any(p.search(n) for p in BAD_NAME_PATTERNS):
        return True
    low = n.lower().strip()
    parent_names = {name_of(x).lower().strip() for x in (a or {}, b or {}) if isinstance(x, dict)}
    if low in parent_names:
        return True
    if low in {"item", "generated item", "unknown", "thing", "object"}:
        return True
    return False

def choose_from(options: list[str], key: str, *parts: Any) -> str:
    if not options:
        return "Patchwork"
    h = int(stable_hash(key, *parts, length=8), 16)
    return options[h % len(options)]

def name_noun_for(category: str, tags: set[str], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any]) -> str:
    category = normalize_category(category)
    if category == "ammo":
        if "bullet" in tags or "gun" in tags: return "Rounds"
        if "arrow" in tags or "bow" in tags: return "Arrows"
        return "Shots"
    if category in {"technology", "placeable_station"}: return "Engine"
    if category == "furniture": return "Relic"
    if category == "tool":
        if "pickaxe" in tags: return "Pick"
        if "axe" in tags or "chainsaw" in tags: return "Cutter"
        if "hammer" in tags: return "Hammer"
        return "Tool"
    if category == "accessory":
        if "boots" in tags: return "Treads"
        if "shield" in tags: return "Ward"
        if "wings" in tags: return "Wings"
        if "emblem" in tags: return "Emblem"
        return "Charm"
    if category == "potion": return "Draught"
    if category == "armor": return "Plate"
    if "gun" in tags or "rifle" in tags: return choose_from(["Rifle", "Carbine", "Handcannon", "Lock"], "noun", name_of(a), name_of(b))
    if "bow" in tags: return choose_from(["Bow", "String", "Greatbow"], "noun", name_of(a), name_of(b))
    if "staff" in tags or "wand" in tags or "magic" in tags: return choose_from(["Staff", "Wand", "Focus", "Scepter"], "noun", name_of(a), name_of(b))
    if "summon" in tags: return choose_from(["Totem", "Bell", "Idol", "Sigil"], "noun", name_of(a), name_of(b))
    if "sword" in tags or "blade" in tags or category == "weapon": return choose_from(["Blade", "Edge", "Saber", "Cleaver"], "noun", name_of(a), name_of(b))
    for c in (ca, cb):
        head = str(c.get("headNoun") or "").strip()
        if head and head.lower() not in {"item", "material", "generic"}:
            return title_words(head)
    return "Relic"

def name_prefixes_for(tags: set[str]) -> list[str]:
    pool: list[str] = []
    if "star" in tags or "lunar" in tags or "moon" in tags:
        pool += ["Stargrazed", "Comet-Bent", "Moon-Scarred", "Falling-Light", "Astral"]
    if "slime" in tags or "gel" in tags:
        pool += ["Gelbound", "Slimeglass", "Jelly-Sealed", "Ooze-Kissed"]
    if "wire" in tags or "electric" in tags or "circuit" in tags or "technology" in tags:
        pool += ["Sparkwired", "Copper-Spark", "Voltaic", "Circuit-Bitten"]
    if "dirt" in tags or "earth" in tags or "stone" in tags or "sand" in tags:
        pool += ["Loamforged", "Claybitten", "Stone-Sunk", "Dustbound"]
    if "fire" in tags or "ember" in tags:
        pool += ["Emberwake", "Ash-Loaded", "Cinderborn"]
    if "ice" in tags or "frost" in tags:
        pool += ["Rimecut", "Frostlocked", "Cold-Sewn"]
    if "shadow" in tags or "night" in tags:
        pool += ["Umbral", "Night-Bent", "Blackglass", "Dusk-Eaten"]
    if "flower" in tags or "daybloom" in tags or "plant" in tags:
        pool += ["Bloomwake", "Petal-Sewn", "Sunroot", "Verdant"]
    if "bar" in tags or "ore" in tags or "alloy" in tags or "material" in tags:
        pool += ["Alloyed", "Forge-Spliced", "Tempered", "Graft-Made"]
    if not pool:
        pool += ["Miscast", "Patchwork", "Crooked", "Borrowed", "Oddly-Forged", "Secondhand"]
    return pool

def creative_result_name(a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], category: str, tags: set[str], key: str) -> str:
    prefix = choose_from(name_prefixes_for(tags), key, "prefix", sorted(tags), category)
    noun = name_noun_for(category, tags, a, b, ca, cb)
    patterns = [f"{prefix} {noun}", f"{noun} of {prefix.replace('-', ' ')}", f"{prefix} {noun}"]
    name = choose_from(patterns, key, "pattern", name_of(a), name_of(b), category)
    name = re.sub(r"\s+", " ", name).strip()
    if bad_result_name(name, a, b):
        name = f"{prefix} {noun}"
    return name[:48].strip()

def repair_name_if_needed(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any], key: str) -> dict[str, Any]:
    tags = set(str(t).lower() for t in data.get("tags", [])) | tags_of(a) | tags_of(b)
    category = normalize_category(data.get("category", data.get("gameplay", {}).get("kind", "generic")))
    old = str(data.get("name") or "")
    if not bad_result_name(old, a, b):
        return data

    debug = data.setdefault("debug", {})
    planner = str(debug.get("planner") or "")
    if planner == "llm" or planner.startswith("llm_"):
        raise PlannerUnavailable("LLM returned an invalid item name; scoped same-author identity repair is required")

    new_name = creative_result_name(a, b, ca, cb, category, tags, key)
    repair_source = "deterministic_dev_name_fallback"

    data["name"] = new_name
    debug["nameRepair"] = json.dumps({"from": old, "to": new_name, "source": repair_source, "planner": planner}, ensure_ascii=False)
    data["canonical"] = canonical_for_result(new_name, category, list(tags))
    return data


def normalize_category(category: Any) -> str:
    c = str(category or "generic").lower().strip()
    aliases = {
        "placeable": "furniture",
        "station": "placeable_station",
        "crafting_station": "placeable_station",
        "device": "technology",
        "trinket": "accessory",
        "acc": "accessory",
        # Do not alias generic consumable to potion. v0.4 runtime has separate
        # stackable generated consumable weapons; potion is only for healing/buff items.
        "consumable_item": "consumable",
        "stack_consumable": "consumable",
        "thrown_stack": "consumable",
    }
    c = aliases.get(c, c)
    return c if c in ALLOWED_CATEGORIES else "generic"


def parent_primary_category(item: dict[str, Any]) -> str:
    """Stable primary role for parent context.

    Important: Terraria Item.material means "can be used in recipes later", not
    "this item is primarily a material". Many weapons/tools are material=true.
    Treat material as a secondary craftability flag unless no stronger role fits.
    """
    damage = int(item_num(item, "damage", 0))
    pick = int(item_num(item, "pickPower", item_num(item, "pick", 0)))
    axe = int(item_num(item, "axePower", item_num(item, "axe", 0)))
    hammer = int(item_num(item, "hammerPower", item_num(item, "hammer", 0)))
    create_tile = int(item_num(item, "createTile", -1))
    create_wall = int(item_num(item, "createWall", -1))

    if item_bool(item, "accessory"):
        return "accessory"
    if item_num(item, "defense", 0) > 0:
        return "armor"
    if pick > 0 or axe > 0 or hammer > 0:
        return "tool"
    if damage > 0:
        return "weapon"
    if item_num(item, "ammo", 0) > 0:
        return "ammo"
    if item_num(item, "healLife", 0) > 0 or item_num(item, "healMana", 0) > 0 or item_num(item, "buffType", 0) > 0:
        return "potion"
    if item_bool(item, "consumable") and item_num(item, "shoot", 0) > 0:
        return "consumable"
    if create_tile >= 0 or create_wall >= 0:
        return "furniture"
    if item_bool(item, "consumable") and not item_bool(item, "material"):
        return "consumable"
    if item_bool(item, "material"):
        return "material"
    return "generic"

def is_weapon_like_parent(item: dict[str, Any]) -> bool:
    """Runtime category pressure helper.

    Generated weapons keep being weapons when used in later weapon chains. This is not
    a creativity judgment; it prevents a playthrough chain from randomly losing its
    main combat item to a non-weapon category just because a stable hash sampled a
    rare lane. Explicit accessory/tool/ammo/armor parents can still pull the result
    sideways through category_policy.
    """
    gd = generated_data_of(item)
    gp = gd.get("gameplay") if isinstance(gd.get("gameplay"), dict) else {}
    if normalize_category(gd.get("category")) == "weapon" or normalize_category(gp.get("kind")) == "weapon":
        return True
    t = tags_of(item)
    return item_num(item, "damage") > 0 or item_num(item, "shoot") > 0 or "weapon" in t

def _weighted_choice(weights: dict[str, float], seed: str) -> str:
    clean = {normalize_category(k): max(0.0, float(v)) for k, v in weights.items() if normalize_category(k) != "generic"}
    clean = {k: v for k, v in clean.items() if v > 0}
    if not clean:
        return "generic"
    total = sum(clean.values())
    roll = int(stable_hash("weighted", seed, CATEGORY_SALT, length=12), 16) / float(16 ** 12)
    cursor = roll * total
    for key, weight in sorted(clean.items()):
        cursor -= weight
        if cursor <= 0:
            return key
    return sorted(clean)[-1]

def _policy_seed(a: dict[str, Any], b: dict[str, Any], key: str | None = None) -> str:
    if key:
        return str(key)
    return stable_hash(item_identity(a), item_identity(b), CATEGORY_SALT, length=24)

def category_policy(tags: set[str], a: dict[str, Any], b: dict[str, Any], key: str | None = None) -> dict[str, Any]:
    """Controlled randomness: high creativity, but no category freefall.

    The old v1.6 policy was too deterministic: default + allowed. This version adds a
    sampled intent lane. The LLM does not freely choose category; it receives a sampled
    category target that can be normal, twist, or rare-but-grounded.
    """
    ca0, cb0 = parent_primary_category(a), parent_primary_category(b)
    cats = {ca0, cb0} - {"generic"}
    parent_damage = max(int(a.get("damage") or 0), int(b.get("damage") or 0))
    min_damage = min(int(a.get("damage") or 0), int(b.get("damage") or 0))
    max_rare = max(int(a.get("rare") or 0), int(b.get("rare") or 0))
    max_depth = max(generation_depth(a), generation_depth(b))
    recursive_pair = max_depth > 0
    weapon_like_count = sum(1 for x in (a, b) if is_weapon_like_parent(x))
    generated_weapon_chain = recursive_pair and weapon_like_count >= 2
    generated_weapon_spine = any(generation_depth(x) > 0 and is_weapon_like_parent(x) for x in (a, b))
    accessory_signal = len(tags & ACCESSORY_HINT_TAGS)
    strong_accessory_signal = len(tags & STRONG_ACCESSORY_TAGS)
    tool_signal = len(tags & TOOL_HINT_TAGS)
    ammo_signal = len(tags & AMMO_HINT_TAGS)
    armor_signal = len(tags & ARMOR_HINT_TAGS)
    has_accessory = "accessory" in cats or strong_accessory_signal > 0
    has_tool = "tool" in cats or tool_signal > 0
    # Ammo tags may appear from projectile behavior (arrow/bullet), but that does not mean
    # the parent item itself is ammunition. Only an actual ammo parent may pull a weapon
    # chain into ammo.
    has_ammo = "ammo" in cats
    has_armor = "armor" in cats or armor_signal > 0
    # Terraria tools/armor/accessories often have damage, but damage alone should not
    # convert them into weapon pressure. Actual weapon category or weapon tag is stronger.
    damage_only_weapon = parent_damage > 0 and not (has_tool or has_accessory or has_armor or has_ammo)
    has_weapon = "weapon" in cats or "weapon" in tags or damage_only_weapon
    has_placeable = bool(tags & PLACEABLE_HINT_TAGS)
    has_tech = bool(tags & {"technology", "circuit", "wire", "electric", "vr", "headset"})
    has_magic = bool(tags & {"magic", "mana", "star", "fallen_star", "fallen star", "crystal", "shadow"})
    has_slime = bool(tags & {"slime", "gel"})
    has_pet = "pet" in cats or "pet" in tags or "minipet" in tags
    seed = _policy_seed(a, b, key)
    roll = int(stable_hash("lane", seed, CATEGORY_SALT, length=12), 16) / float(16 ** 12)
    creativity = CATEGORY_CREATIVITY

    reasons: list[str] = [f"parents={ca0}+{cb0}", f"damage={parent_damage}", f"depth={max_depth}", f"creativity={creativity:.2f}", f"roll={roll:.3f}"]
    default = "generic"
    allowed: set[str] = {"generic"}
    creative_allowed: set[str] = set()
    weights: dict[str, float] = {}
    locked = False

    if has_weapon:
        weapon_pressure = parent_damage + max_rare * 8 + (10 if tags & WEAPON_UPGRADE_TAGS else 0) + (6 if has_magic else 0)
        accessory_pressure = strong_accessory_signal * 12 + (8 if "accessory" in cats else 0)
        tool_pressure = tool_signal * 11 + (8 if "tool" in cats else 0)
        ammo_pressure = ammo_signal * 12 + (8 if "ammo" in cats else 0)
        armor_pressure = armor_signal * 10 + (8 if "armor" in cats else 0)
        default = "weapon"
        allowed = {"weapon"}
        creative_allowed = {"weapon"}
        weights = {"weapon": max(35.0, weapon_pressure + 20.0)}
        reasons.append(f"weapon_pressure={weapon_pressure}")

        # Direct grounded transmutations: visible parent/category signal exists.
        if has_accessory:
            allowed.add("accessory"); creative_allowed.add("accessory")
            weights["accessory"] = 10 + accessory_pressure
            reasons.append(f"accessory_pressure={accessory_pressure}")
        if has_tool:
            allowed.add("tool"); creative_allowed.add("tool")
            weights["tool"] = 9 + tool_pressure
            reasons.append(f"tool_pressure={tool_pressure}")
        if has_ammo and ("ranged" in tags or "gun" in tags or "bow" in tags or ammo_signal >= 2):
            allowed.add("ammo"); creative_allowed.add("ammo")
            weights["ammo"] = 8 + ammo_pressure
        if has_armor:
            allowed.add("armor"); creative_allowed.add("armor")
            weights["armor"] = 7 + armor_pressure

        # Rare but still semantic twists. These are deliberately not always default.
        if has_magic and parent_damage <= 90:
            creative_allowed.add("summon")
            weights["summon"] = 3 + min(18, max_rare * 2 + parent_damage * 0.06)
        if has_tech and parent_damage <= 75:
            creative_allowed.add("technology")
            weights["technology"] = 4 + (8 if has_tech else 0)
        if has_pet and parent_damage <= 70:
            creative_allowed.add("pet")
            weights["pet"] = 2 + (6 if has_slime else 0)
        if has_placeable and parent_damage <= 40:
            creative_allowed.add("placeable_station")
            weights["placeable_station"] = 3 + (6 if has_placeable else 0)

        # Generated combat chains have inertia, not a hard lock. A recursive weapon used
        # as an upgrade spine should usually remain combat-capable, but it may still drift
        # into grounded outcomes when the other parent or the concept supports it: summon
        # weapons, ammo, tools, stations, etc. This prevents both category freefall and the
        # opposite mistake: forcing every recursive chain back to plain weapon forever.
        if generated_weapon_chain or generated_weapon_spine:
            weights["weapon"] = max(weights.get("weapon", 80.0), weapon_pressure + 52.0)
            # Magic/star/shadow parents can rarely transmute a weapon spine into a summon-class
            # combat outcome. attach_gameplay_and_attack maps selected "summon" to a combat
            # item with summon damage, not to a nonfunctional generic object.
            if has_magic or "summon" in tags:
                creative_allowed.add("summon")
                weights["summon"] = max(weights.get("summon", 0.0), 4.0 + min(12.0, max_rare * 1.2 + parent_damage * 0.025))
            # Actual ammo/tool/placeable parent signals are allowed to pull the chain sideways.
            # Mere projectile-profile tags such as arrow/bullet do not set has_ammo.
            if has_ammo:
                creative_allowed.add("ammo"); allowed.add("ammo")
                weights["ammo"] = max(weights.get("ammo", 0.0), 10.0 + ammo_pressure)
            if has_tool:
                creative_allowed.add("tool"); allowed.add("tool")
                weights["tool"] = max(weights.get("tool", 0.0), 10.0 + tool_pressure)
            if has_placeable:
                creative_allowed.add("placeable_station")
                # A strong combat spine can still become a station if a real station/block parent
                # is present, but the chance is small instead of forbidden.
                station_weight = 2.0 + (7.0 if has_placeable else 0.0) / (1.0 + max(0.0, parent_damage - 40.0) / 140.0)
                weights["placeable_station"] = max(weights.get("placeable_station", 0.0), station_weight)
            reasons.append("generated combat spine has inertia, not lock")

        # Strong plain weapons should be heavily biased toward combat, but not hard-locked.
        # If another real parent supplies a grounded transmutation signal, the sampled lane may
        # still accept it. Without such a signal creative_allowed usually contains only weapon.
        if parent_damage >= 60 and not recursive_pair and not (has_accessory or has_tool or has_ammo or has_magic or has_tech or has_placeable):
            weights["weapon"] = max(weights.get("weapon", 80.0), weapon_pressure + 35.0)
            reasons.append("strong plain weapon biased to weapon")
    elif has_accessory:
        default = "accessory"; allowed = {"accessory"}; creative_allowed = {"accessory"}; weights = {"accessory": 60}
        if tags & {"emblem", "glove", "claw", "spike", "tooth"}:
            creative_allowed.add("weapon"); allowed.add("weapon"); weights["weapon"] = 18
        if has_magic:
            creative_allowed.add("summon"); weights["summon"] = 8
    elif has_tool:
        default = "tool"; allowed = {"tool"}; creative_allowed = {"tool"}; weights = {"tool": 60}
        if tags & {"axe", "hammer", "pickaxe", "drill", "chainsaw"}:
            allowed.add("weapon"); creative_allowed.add("weapon"); weights["weapon"] = 20 + parent_damage
    elif has_ammo:
        default = "ammo"; allowed = {"ammo"}; creative_allowed = {"ammo"}; weights = {"ammo": 60}
        if tags & {"rocket", "bullet", "arrow", "explosive"}:
            allowed.add("weapon"); creative_allowed.add("weapon"); weights["weapon"] = 14
    elif has_armor:
        default = "armor"; allowed = {"armor", "accessory"}; creative_allowed = {"armor", "accessory"}; weights = {"armor": 50, "accessory": 18}
    elif "potion" in tags or "consumable" in tags:
        default = "potion"; allowed = {"potion"}; creative_allowed = {"potion"}; weights = {"potion": 60}
        if has_magic:
            creative_allowed.add("accessory"); weights["accessory"] = 5
    elif has_tech:
        default = "technology"; allowed = {"technology", "placeable_station", "furniture"}; creative_allowed = set(allowed); weights = {"technology": 44, "placeable_station": 22, "furniture": 12}
    elif "material" in tags and not (tags & {"chair", "workbench", "bench", "furniture", "crafting_station"}):
        default = "material"; allowed = {"material"}; creative_allowed = {"material", "accessory", "weapon", "placeable_station"}; weights = {"material": 62, "accessory": 5, "weapon": 7, "placeable_station": 4 if has_placeable else 1}
    elif has_placeable:
        default = "furniture"; allowed = {"furniture", "placeable_station"}; creative_allowed = set(allowed); weights = {"furniture": 45, "placeable_station": 18}

    allowed = {normalize_category(x) for x in allowed if normalize_category(x) != "generic"} or {normalize_category(default)}
    creative_allowed = {normalize_category(x) for x in creative_allowed if normalize_category(x) != "generic"} or set(allowed)
    default = normalize_category(default if default != "generic" else sorted(allowed)[0])

    # Lane selection. More creativity means fewer stable results and more twist/rare results.
    effective_creativity = min(1.0, creativity + 0.06 * max_depth)
    stable_threshold = max(0.42, 0.86 - 0.42 * effective_creativity)
    twist_threshold = max(stable_threshold, min(0.96, stable_threshold + 0.10 + 0.28 * effective_creativity))
    if locked or len(creative_allowed) <= 1:
        lane = "stable"
        selected = default
    elif roll < stable_threshold:
        lane = "stable"
        selected = default
    elif roll < twist_threshold:
        lane = "twist"
        candidate_weights = {k: v for k, v in weights.items() if k in allowed}
        if len(candidate_weights) <= 1:
            candidate_weights = {k: v for k, v in weights.items() if k in creative_allowed}
        selected = _weighted_choice(candidate_weights, seed + ":twist")
        if selected == "generic":
            selected = default
    else:
        lane = "rare"
        candidate_weights = {k: max(1.0, weights.get(k, 4.0)) for k in creative_allowed}
        # In rare lane, downweight the default so surprise can actually happen.
        if default in candidate_weights and len(candidate_weights) > 1:
            candidate_weights[default] *= 0.28
        selected = _weighted_choice(candidate_weights, seed + ":rare")
        if selected == "generic":
            selected = default

    return {
        "default": default,
        "selected": normalize_category(selected),
        "lane": lane,
        "allowed": sorted(allowed),
        "creativeAllowed": sorted(creative_allowed),
        "locked": bool(locked),
        "enforceSampled": bool(CATEGORY_ENFORCE_SAMPLED),
        "parentCategories": [ca0, cb0],
        "recursivePair": bool(recursive_pair),
        "maxGenerationDepth": int(max_depth),
        "reason": "; ".join(reasons),
        "weights": {k: round(float(v), 2) for k, v in sorted(weights.items())},
    }

def choose_result_category(tags: set[str], a: dict[str, Any], b: dict[str, Any], key: str | None = None) -> str:
    return str(category_policy(tags, a, b, key).get("selected") or category_policy(tags, a, b, key)["default"])

def coerce_category_by_policy(requested: Any, tags: set[str], a: dict[str, Any], b: dict[str, Any], key: str | None = None) -> tuple[str, dict[str, Any]]:
    policy = category_policy(tags, a, b, key)
    requested_norm = normalize_category(requested)
    selected_target = normalize_category(policy.get("selected") or policy.get("default"))
    allowed = set(policy.get("allowed") or []) | set(policy.get("creativeAllowed") or [])
    if CATEGORY_ENFORCE_SAMPLED:
        selected = selected_target
        if requested_norm != selected_target:
            policy["repair"] = f"category '{requested_norm}' replaced by sampled intent '{selected_target}' ({policy.get('lane')})"
    else:
        selected = requested_norm if requested_norm in allowed else selected_target
        if selected != requested_norm:
            policy["repair"] = f"category '{requested_norm}' is outside grounded categories {sorted(allowed)}; repaired to '{selected}'"
        elif selected != policy.get("default"):
            policy["transmutation"] = f"accepted grounded category '{selected}' over default '{policy['default']}'"
    policy["requested"] = requested_norm
    policy["final"] = selected
    return selected, policy

def canonical_for_result(name: str, category: str, tags: list[str]) -> dict[str, Any]:
    tagset = set(tags)
    head = guess_head(name, tagset)
    hard = sorted(t for t in tagset if t in HARD_TAGS)
    soft = sorted(t for t in tagset if t not in hard)
    return {
        "headNoun": head,
        "modifiers": [],
        "material": "wood" if "wood" in tagset else "",
        "class": category,
        "shapeAnchors": sorted(set([head] + VISUAL_SYNONYMS.get(head, []))),
        "visualAnchors": sorted(set(required_anchors_from_tags(tagset) or [name])),
        "hardTags": hard,
        "softTags": soft,
    }

def rep(parent: str, mode: str, importance: str, visual_anchor: str, placement: str) -> dict[str, Any]:
    return {"parent": parent, "mode": mode, "importance": importance, "visualAnchor": visual_anchor, "placement": placement, "rationale": "preserve parent provenance"}

def rep_for_parent(item: dict[str, Any], c: dict[str, Any], importance: str) -> dict[str, Any]:
    va = (c.get("visualAnchors") or [name_of(item)])[0]
    return rep(name_of(item), "visual", importance, va, "visible in item icon")

def inh_for_parent(item: dict[str, Any], c: dict[str, Any], role: str) -> dict[str, Any]:
    return {
        "parent": name_of(item),
        "role": role,
        "preservedFeatures": list(dict.fromkeys((c.get("hardTags") or []) + ([c.get("headNoun")] if c.get("headNoun") else []))),
        "visualAnchors": c.get("visualAnchors") or [name_of(item)],
        "gameplayAnchors": [],
        "lossPolicy": "preserve_hard_tags",
    }

def required_anchors_from(ca: dict[str, Any], cb: dict[str, Any], tags: set[str]) -> list[str]:
    anchors: list[str] = []
    anchors.extend(ca.get("visualAnchors") or [])
    anchors.extend(cb.get("visualAnchors") or [])
    anchors.extend(required_anchors_from_tags(tags))
    return list(dict.fromkeys(anchors))[:8]

def required_anchors_from_tags(tags: set[str]) -> list[str]:
    anchors = []
    for tag in _ordered_known_tags(tags, VISUAL_SYNONYMS):
        anchors.extend(VISUAL_SYNONYMS.get(tag, []))
    return list(dict.fromkeys(anchors))

def palette_from(tags: set[str]) -> list[str]:
    colors = []
    for t in _ordered_known_tags(tags, PALETTES):
        colors.extend(PALETTES.get(t, []))
    return list(dict.fromkeys(colors))[:6] or ["gray", "white"]


__all__ = [
    "clean_name",
    "theme_word",
    "title_words",
    "bad_result_name",
    "choose_from",
    "name_noun_for",
    "name_prefixes_for",
    "creative_result_name",
    "repair_name_if_needed",

    "normalize_category",
    "parent_primary_category",
    "is_weapon_like_parent",
    "_weighted_choice",
    "_policy_seed",
    "category_policy",
    "choose_result_category",
    "coerce_category_by_policy",
    "canonical_for_result",
    "rep",
    "rep_for_parent",
    "inh_for_parent",
    "required_anchors_from",
    "required_anchors_from_tags",
    "palette_from",
]
