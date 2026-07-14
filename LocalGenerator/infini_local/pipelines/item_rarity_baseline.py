from __future__ import annotations

from typing import Any

from infini_local.core.env_utils import env_bool, env_float
from infini_local.core.item_identity_tools import fingerprint_of, item_num
from infini_local.core.item_signals import knowledge_key
from infini_local.pipelines.result_identity_policy import normalize_category

# AGENT MAP: rarity/tier baseline for parent item knowledge.
# Owns vanilla and modded rarity conversion only; live stat/mechanics power stays
# in item_power_knowledge.py.


def _env_float(name: str, default: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return env_float(name, default, lo=lo, hi=hi)

RARITY_BASELINE_ENABLED = env_bool("INFINI_RARITY_BASELINE_ENABLED", True)

RARITY_BASELINE_STRENGTH = _env_float("INFINI_RARITY_BASELINE_STRENGTH", 0.90, 0.0, 1.5)

MATERIAL_RARITY_MULT = _env_float("INFINI_MATERIAL_RARITY_MULT", 1.18, 0.4, 2.2)

TIER_DEFAULT_POWER = {
    "trash": 2, "wood": 5, "early": 18, "pre_boss": 32, "evil_boss": 50,
    "pre_hardmode_late": 64, "hardmode_early": 82, "mech": 125,
    "plantera": 156, "post_plantera": 185, "post_golem": 205,
    "lunar": 235,
    # Vanilla Moon Lord / Zenith band. Important: Calamity post-ML tiers are intentionally far above this.
    "endgame": 285,
    # Calamity-like progression. These are crafting/progression anchors, not direct +damage values.
    "post_moonlord": 360, "post_moonlord_plus": 420,
    "superboss": 470, "devourer": 540, "auric": 660, "exo_yharon_plus": 720,
    "shadowspec": 750, "calamity_red_prefix": 790, "modded_high_unknown": 500, "superboss_unknown": 620,
    "draedon_arsenal": 320,
    # Result-only labels used when a huge Calamity material is mixed with a weak/basic anchor.
    "post_moonlord_influenced": 300, "devourer_influenced": 335, "auric_influenced": 370,
    "exo_yharon_plus_influenced": 410, "shadowspec_influenced": 425, "calamity_red_prefix_influenced": 440,
}

TIER_RANK = {
    "trash": 0, "wood": 1, "early": 2, "pre_boss": 3, "evil_boss": 4,
    "pre_hardmode_late": 5, "hardmode_early": 6, "mech": 7,
    "plantera": 8, "post_plantera": 9, "post_golem": 10,
    "lunar": 11, "endgame": 12,
    "post_moonlord": 13, "post_moonlord_plus": 14, "superboss": 15,
    "devourer": 16, "auric": 17, "exo_yharon_plus": 18, "shadowspec": 19, "calamity_red_prefix": 20,
    "draedon_arsenal": 13,
}

MODDED_HIGH_TIERS = {"post_moonlord", "post_moonlord_plus", "superboss", "devourer", "auric", "exo_yharon_plus", "shadowspec", "calamity_red_prefix"}

VANILLA_ENDGAME_POWER = TIER_DEFAULT_POWER["endgame"]

RARITY_BASELINE_TABLE = [
    (-99, "trash", 1, "Unknown", "#FFFFFF"),
    (-1, "trash", 2, "Gray", "#828282"),
    (0, "wood", 5, "White", "#FFFFFF"),
    (1, "early", 18, "Blue", "#9696FF"),
    (2, "pre_boss", 32, "Green", "#96FF96"),
    (3, "evil_boss", 50, "Orange", "#FFC896"),
    (4, "pre_hardmode_late", 64, "LightRed", "#FF9696"),
    (5, "hardmode_early", 82, "Pink", "#FF96FF"),
    (6, "mech", 125, "LightPurple", "#D2A0FF"),
    (7, "plantera", 156, "Lime", "#96FF0A"),
    (8, "post_plantera", 185, "Yellow", "#FFFF0A"),
    (9, "post_golem", 205, "Cyan", "#05C8FF"),
    (10, "lunar", 235, "Red", "#FF2864"),
    (11, "endgame", 285, "Purple", "#B428FF"),
]

MODDED_RARITY_LADDER = {
    "calamitymod/turquoise": {"ordinal": 12, "tierEstimate": "post_moonlord", "tierScore": 360, "displayName": "Turquoise", "colorHex": "#00FFC8", "role": "calamity_rarity_class"},
    "turquoise": {"ordinal": 12, "tierEstimate": "post_moonlord", "tierScore": 360, "displayName": "Turquoise", "colorHex": "#00FFC8", "role": "calamity_rarity_class"},
    "calamitymod/puregreen": {"ordinal": 13, "tierEstimate": "post_moonlord_plus", "tierScore": 420, "displayName": "Pure Green", "colorHex": "#00FF00", "role": "calamity_rarity_class"},
    "puregreen": {"ordinal": 13, "tierEstimate": "post_moonlord_plus", "tierScore": 420, "displayName": "Pure Green", "colorHex": "#00FF00", "role": "calamity_rarity_class"},
    "pure green": {"ordinal": 13, "tierEstimate": "post_moonlord_plus", "tierScore": 420, "displayName": "Pure Green", "colorHex": "#00FF00", "role": "calamity_rarity_class"},
    "calamitymod/cosmicpurple": {"ordinal": 14, "tierEstimate": "devourer", "tierScore": 540, "displayName": "Cosmic Purple", "colorHex": "#CE84FF", "baseColorHex": "#67428A", "role": "calamity_rarity_class"},
    "cosmicpurple": {"ordinal": 14, "tierEstimate": "devourer", "tierScore": 540, "displayName": "Cosmic Purple", "colorHex": "#CE84FF", "baseColorHex": "#67428A", "role": "calamity_rarity_class"},
    "cosmic purple": {"ordinal": 14, "tierEstimate": "devourer", "tierScore": 540, "displayName": "Cosmic Purple", "colorHex": "#CE84FF", "baseColorHex": "#67428A", "role": "calamity_rarity_class"},
    "calamitymod/burnishedauric": {"ordinal": 15, "tierEstimate": "auric", "tierScore": 660, "displayName": "Burnished Auric", "colorHex": "#FFDC16", "baseColorHex": "#9D6E0B", "role": "calamity_rarity_class"},
    "burnishedauric": {"ordinal": 15, "tierEstimate": "auric", "tierScore": 660, "displayName": "Burnished Auric", "colorHex": "#FFDC16", "baseColorHex": "#9D6E0B", "role": "calamity_rarity_class"},
    "burnished auric": {"ordinal": 15, "tierEstimate": "auric", "tierScore": 660, "displayName": "Burnished Auric", "colorHex": "#FFDC16", "baseColorHex": "#9D6E0B", "role": "calamity_rarity_class"},
    "calamitymod/hotpink": {"ordinal": 16, "tierEstimate": "shadowspec", "tierScore": 750, "displayName": "Hot Pink", "colorHex": "#FF00FF", "role": "calamity_rarity_class"},
    "hotpink": {"ordinal": 16, "tierEstimate": "shadowspec", "tierScore": 750, "displayName": "Hot Pink", "colorHex": "#FF00FF", "role": "calamity_rarity_class"},
    "hot pink": {"ordinal": 16, "tierEstimate": "shadowspec", "tierScore": 750, "displayName": "Hot Pink", "colorHex": "#FF00FF", "role": "calamity_rarity_class"},
    "calamitymod/calamityred": {"ordinal": 17, "tierEstimate": "calamity_red_prefix", "tierScore": 790, "displayName": "Calamity Red", "colorHex": "#FF3636", "baseColorHex": "#F21B1B", "role": "calamity_rarity_class_prefix"},
    "calamityred": {"ordinal": 17, "tierEstimate": "calamity_red_prefix", "tierScore": 790, "displayName": "Calamity Red", "colorHex": "#FF3636", "baseColorHex": "#F21B1B", "role": "calamity_rarity_class_prefix"},
    "calamity red": {"ordinal": 17, "tierEstimate": "calamity_red_prefix", "tierScore": 790, "displayName": "Calamity Red", "colorHex": "#FF3636", "baseColorHex": "#F21B1B", "role": "calamity_rarity_class_prefix"},
    "calamitymod/darkorange": {"ordinal": 12, "tierEstimate": "draedon_arsenal", "tierScore": 320, "displayName": "Draedon's Arsenal / Rust / Bronze", "colorHex": "#CC4723", "role": "special_rarity_class"},
    "darkorange": {"ordinal": 12, "tierEstimate": "draedon_arsenal", "tierScore": 320, "displayName": "Draedon's Arsenal / Rust / Bronze", "colorHex": "#CC4723", "role": "special_rarity_class"},
}

MODDED_RARITY_COLOR_HINTS = {
    "#00FFC8": "turquoise",
    "#00FF00": "puregreen",
    "#CE84FF": "cosmicpurple",
    "#67428A": "cosmicpurple",
    "#FFDC16": "burnishedauric",
    "#9D6E0B": "burnishedauric",
    "#FF00FF": "hotpink",
    "#FF3636": "calamityred",
    "#F21B1B": "calamityred",
    "#CC4723": "darkorange",
}

def rarity_details_of(item: dict[str, Any]) -> dict[str, Any]:
    details = item.get("rarityDetails")
    if isinstance(details, dict):
        return details
    fp = fingerprint_of(item)
    details = fp.get("rarityDetails")
    return details if isinstance(details, dict) else {}

def _norm_rarity_key(text: Any) -> str:
    return knowledge_key(str(text or "")).replace(" ", "").replace("_", "").replace("-", "")

def _norm_hex(text: Any) -> str:
    h = str(text or "").strip().upper()
    if not h:
        return ""
    if not h.startswith("#"):
        h = "#" + h
    return h

def modded_rarity_entry(details: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(details, dict) or not details:
        return None
    name = str(details.get("name") or details.get("displayName") or "")
    mod = str(details.get("mod") or "")
    full = str(details.get("fullName") or (mod + "/" + name if mod or name else ""))
    candidates = {
        _norm_rarity_key(name),
        _norm_rarity_key(full),
        _norm_rarity_key(mod + "/" + name),
        knowledge_key(name),
        knowledge_key(full),
        knowledge_key(mod + "/" + name),
    }
    for cand in list(candidates):
        if cand in MODDED_RARITY_LADDER:
            return dict(MODDED_RARITY_LADDER[cand])
    color = _norm_hex(details.get("colorHex"))
    if color in MODDED_RARITY_COLOR_HINTS:
        key = MODDED_RARITY_COLOR_HINTS[color]
        if key in MODDED_RARITY_LADDER:
            return dict(MODDED_RARITY_LADDER[key])
    return None

def rarity_tier_estimate(raw_rare: int | float, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Map Terraria/tModLoader rarity to an approximate tier.
    Exact item knowledge still wins; mod rarity class names/colors beat arbitrary runtime ids.
    """
    try:
        rare = int(raw_rare)
    except Exception:
        rare = 0

    details = details or {}
    modded = modded_rarity_entry(details)
    if modded:
        out = dict(modded)
        out.update({
            "rawRare": rare,
            "tierScore": float(out.get("tierScore") or 0),
            "confidence": 0.82,
            "runtimeRarityName": details.get("name"),
            "runtimeRarityMod": details.get("mod"),
            "runtimeColorHex": details.get("colorHex"),
        })
        return out

    if rare > 11:
        # ModRarity numeric ids are registration/load-order ids, not progression ordinals.
        # Without a recognized class name/color there is no defensible tier signal. Live
        # damage/tool/armor/value facts can still carry the item in mechanic_signal_power.
        return {
            "rawRare": rare,
            "tierEstimate": "unknown",
            "tierScore": 0,
            "confidence": 0.0,
            "role": "unknown_modded_rarity",
            "displayName": str(details.get("name") or "Unknown ModRarity"),
            "colorHex": details.get("colorHex"),
        }

    best_tier, best_score, best_name, best_hex = "trash", 1, "Unknown", "#FFFFFF"
    for threshold, tier, score, display, hex_color in RARITY_BASELINE_TABLE:
        if rare >= threshold:
            best_tier, best_score, best_name, best_hex = tier, score, display, hex_color
    conf = 0.66 if rare >= 0 else 0.46
    return {"rawRare": rare, "tierEstimate": best_tier, "tierScore": best_score, "confidence": conf, "role": "vanilla_rarity_baseline", "displayName": best_name, "colorHex": best_hex}

def rarity_role_weight(category: str, tags: set[str]) -> tuple[float, str]:
    # Tags may contain display-name tokens; they cannot alter progression math.
    _ = tags
    category = normalize_category(category)
    if category == "weapon":
        return 1.00, "weapon rarity transfers to combat power"
    if category == "material":
        return MATERIAL_RARITY_MULT, "material rarity transfers to crafting-tier power"
    if category == "tool":
        return 0.92, "tool rarity transfers to utility/tool power"
    if category == "armor":
        return 0.90, "armor rarity transfers to defense-tier power"
    if category == "accessory":
        return 0.82, "accessory rarity transfers to passive potential"
    if category in {"furniture", "placeable_station", "technology"}:
        return 0.66, "placeable rarity transfers mostly to tier/novelty"
    if category in {"vanity", "pet", "light_pet", "mount"}:
        return 0.50, "cosmetic rarity transfers mostly to novelty"
    return 0.70, "unknown role rarity baseline"

def rarity_baseline_signal(item: dict[str, Any], tags: set[str], category: str) -> dict[str, Any]:
    tags = set(tags)
    category = normalize_category(category)
    raw = int(item_num(item, "rare"))
    details = rarity_details_of(item)
    est = rarity_tier_estimate(raw, details)
    weight, note = rarity_role_weight(category, tags)
    converted = float(est["tierScore"]) * weight * RARITY_BASELINE_STRENGTH
    if not RARITY_BASELINE_ENABLED:
        converted = 0.0
    return {
        "rawRare": raw,
        "tierEstimate": est["tierEstimate"],
        "tierScore": round(float(est["tierScore"]), 2),
        "role": est["role"],
        "confidence": round(float(est["confidence"]), 2),
        "conversionCategory": category,
        "roleWeight": round(weight, 3),
        "strength": round(RARITY_BASELINE_STRENGTH, 3),
        "convertedPower": round(max(0.0, converted), 2),
        "note": note,
        "displayName": est.get("displayName"),
        "colorHex": est.get("colorHex"),
        "ordinal": est.get("ordinal"),
        "rarityDetails": details,
    }

__all__ = [
    "RARITY_BASELINE_ENABLED",
    "RARITY_BASELINE_STRENGTH",
    "MATERIAL_RARITY_MULT",
    "TIER_DEFAULT_POWER",
    "TIER_RANK",
    "MODDED_HIGH_TIERS",
    "VANILLA_ENDGAME_POWER",
    "RARITY_BASELINE_TABLE",
    "MODDED_RARITY_LADDER",
    "MODDED_RARITY_COLOR_HINTS",
    "rarity_details_of",
    "modded_rarity_entry",
    "rarity_tier_estimate",
    "rarity_role_weight",
    "rarity_baseline_signal",
]
