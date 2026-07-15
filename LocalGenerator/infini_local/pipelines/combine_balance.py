from __future__ import annotations

import json
import math
from typing import Any
from infini_local.core.balance_policy import weapon_envelope_for_bucket

from infini_local.core.balance_mode import current_balance_mode, should_apply_python_safety

from infini_local.core.item_identity_tools import item_num
from infini_local.pipelines.result_identity_policy import (
    normalize_category,
    parent_primary_category,
)
from infini_local.pipelines.item_power_knowledge import (
    RECURSIVE_POWER_GROWTH,
    generation_depth,
    infer_item_card,
    lower_name,
    mechanic_signal_power,
    pair_catalyst_pressure,
    recipe_coherence,
    tags_of,
)
from infini_local.pipelines.item_rarity_baseline import (
    MODDED_HIGH_TIERS,
    TIER_DEFAULT_POWER,
    TIER_RANK,
    VANILLA_ENDGAME_POWER,
    rarity_baseline_signal,
)
from infini_local.pipelines.presentation_sound import clamp


def apply_family_locks_to_genome(g: dict[str, Any], a: dict[str, Any], b: dict[str, Any], data: dict[str, Any], stage: dict[str, Any]) -> dict[str, Any]:
    """Universal execution guardrails for an LLM-authored combat genome.

    This function must not decide that a concrete source item "should" become a special
    family. It only clamps authored fields that can break gameplay, performance or sync.
    Normal authored values inside the broad corridor are preserved.
    """
    before = dict(g)
    balance_mode = current_balance_mode()
    if not should_apply_python_safety(balance_mode):
        data.setdefault("debug", {})["runtimeSafetyMode"] = {
            "mode": balance_mode,
            "applied": False,
            "reason": "python_runtime_safety_corridor_disabled; C# hard clamps remain active",
        }
        return g
    def _num(key: str, default: float) -> float:
        try:
            v = float(g.get(key) if g.get(key) not in (None, "") else default)
            return v if math.isfinite(v) else default
        except Exception:
            return default

    # The runtime plan already passed the canonical field bounds. This layer only
    # enforces the same absolute engine corridor; it must not rebalance authored values
    # from parent power, progression stage, infinite-pierce combinations, or family names.
    g["shotCount"] = min(max(1, int(round(_num("shotCount", 1)))), 8)
    raw_pierce = int(round(_num("pierce", 0)))
    g["pierce"] = -1 if raw_pierce == -1 else min(max(0, raw_pierce), 10)
    g["lifetimeTicks"] = min(max(25, int(round(_num("lifetimeTicks", 90)))), 900)
    g["extraUpdates"] = min(max(0, int(round(_num("extraUpdates", 0)))), 3)
    g["aoeRadiusTiles"] = min(max(0.0, _num("aoeRadiusTiles", 0.0)), 10.0)
    g["rangeTiles"] = min(max(4.0, _num("rangeTiles", 35.0)), 120.0)
    g["homingStrength"] = min(max(0.0, _num("homingStrength", 0.0)), 1.0)

    if before != g:
        try:
            data.setdefault("debug", {})["runtimeSafetyClamps"] = json.dumps({
                "before": {k: before.get(k) for k in ["shotCount", "pierce", "aoeRadiusTiles", "lifetimeTicks", "rangeTiles", "extraUpdates", "homingStrength"]},
                "after": {k: g.get(k) for k in ["shotCount", "pierce", "aoeRadiusTiles", "lifetimeTicks", "rangeTiles", "extraUpdates", "homingStrength"]},
                "basis": "absolute schema/runtime bounds only; authored values preserved",
                "mode": balance_mode,
            }, ensure_ascii=False)
        except Exception:
            pass
    return g

def preservation_score(data: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any]) -> float:
    required = set(ca.get("hardTags") or []) | set(cb.get("hardTags") or [])
    if not required:
        return 1.0
    hay = " ".join(json.dumps(x, ensure_ascii=False).lower() for x in [data.get("tags"), data.get("inheritance"), data.get("visual"), data.get("name")])
    hit = sum(1 for t in required if t.lower() in hay)
    return round(hit / max(1, len(required)), 3)

def item_power_score(item: dict[str, Any]) -> float:
    """Return power from live Terraria facts only.

    Names, fantasy tags and generated depth are identity/novelty context, not combat
    evidence. A word such as ``zenith`` or ``lunar`` must never raise damage by itself.
    Known ModRarity classes may still contribute through mechanic_signal_power because
    those are concrete tModLoader metadata, not item-name guesses.
    """
    signal = mechanic_signal_power(item)
    return max(0.0, float(signal.get("score") or 0))

def tier_rank(tier: Any) -> int:
    t = str(tier or "unknown")
    if t.endswith("_influenced"):
        t = t[:-11]
    return int(TIER_RANK.get(t, -1))

def influenced_tier(tier: str) -> str:
    tier = str(tier or "unknown")
    if tier in MODDED_HIGH_TIERS:
        return tier + "_influenced"
    return tier

def universal_parent_relation(strong_card: dict[str, Any], weak_card: dict[str, Any], tags: set[str]) -> dict[str, Any]:
    """Runtime-safe parent relation.

    This deliberately avoids hand-authored recipe graphs for specific mods/items.
    It only uses observable/card-level properties: category, tier score, source mod,
    broad tags, and whether a high-tier material has a credible non-trivial anchor.
    """
    s_cat = normalize_category(strong_card.get("category") or "generic")
    w_cat = normalize_category(weak_card.get("category") or "generic")
    s_power = float(strong_card.get("powerScore") or 0)
    w_power = float(weak_card.get("powerScore") or 0)
    s_sig = strong_card.get("signals") if isinstance(strong_card.get("signals"), dict) else {}
    w_sig = weak_card.get("signals") if isinstance(weak_card.get("signals"), dict) else {}
    s_mod = str(s_sig.get("sourceMod") or "Terraria")
    w_mod = str(w_sig.get("sourceMod") or "Terraria")
    same_nonvanilla_source = bool(s_mod and w_mod and s_mod == w_mod and s_mod.lower() != "terraria")
    same_family = s_cat == w_cat
    material_with_item = {s_cat, w_cat} & {"material"} and ({s_cat, w_cat} & {"weapon", "tool", "armor", "accessory"})
    high_pair = min(s_power, w_power) >= VANILLA_ENDGAME_POWER * 0.72
    high_material = max(s_power, w_power) >= VANILLA_ENDGAME_POWER and {s_cat, w_cat} & {"material"}

    if material_with_item and high_material and min(s_power, w_power) >= TIER_DEFAULT_POWER.get("post_plantera", 185):
        quality = "high_tier_material_with_credible_item"
        strength = 0.86
    elif s_cat == "material" and w_cat == "material" and high_pair:
        quality = "high_tier_material_blend"
        strength = 0.84
    elif same_family and min(s_power, w_power) >= TIER_DEFAULT_POWER.get("hardmode_early", 105):
        quality = "same_role_synergy"
        strength = 0.72
    elif same_nonvanilla_source and min(s_power, w_power) >= TIER_DEFAULT_POWER.get("pre_hardmode_late", 55):
        quality = "same_mod_soft_synergy"
        strength = 0.58
    else:
        quality = "loose_mix"
        strength = 0.0
    return {
        "quality": quality,
        "strength": round(strength, 3),
        "sameNonVanillaSource": same_nonvanilla_source,
        "strongCategory": s_cat,
        "weakCategory": w_cat,
        "strongSourceMod": s_mod,
        "weakSourceMod": w_mod,
        "runtimeOnly": True,
    }

def recipe_power_transfer(cards: list[dict[str, Any]], scores: list[float], tags: set[str]) -> dict[str, Any]:
    """How much of a parent tier can actually become the result.

v2.7 distinction:
    - parentTier says how advanced the strongest parent is;
    - resultTier says how advanced the produced item really is.

    This prevents high-rarity modded material + Wood from becoming full endgame gear,
    while still allowing a strong weapon/tool/accessory base to act as a credible anchor.
    """
    if len(cards) < 2:
        return {"quality": "single", "resultTier": "unknown", "resultPowerScore": 1, "strongestTier": "unknown", "weakestTier": "unknown", "powerMultiplier": 1.0, "weakAnchor": False}
    ordered = sorted(zip(cards, scores), key=lambda x: float(x[1] or 0), reverse=True)
    strong_card, strong_score = ordered[0]
    weak_card, weak_score = ordered[1]
    strong_tier = str(strong_card.get("tier") or "unknown")
    weak_tier = str(weak_card.get("tier") or "unknown")
    strong_cat = normalize_category(strong_card.get("category") or "generic")
    weak_cat = normalize_category(weak_card.get("category") or "generic")
    strong_rank = tier_rank(strong_tier)
    weak_rank = tier_rank(weak_tier)
    strong_score = float(strong_score or 0)
    weak_score = float(weak_score or 0)

    strong_is_high_modded = strong_tier in MODDED_HIGH_TIERS or strong_rank >= TIER_RANK.get("post_moonlord", 13)
    weak_is_basic = weak_score < 55 or weak_rank <= TIER_RANK.get("pre_boss", 3)
    weak_is_vanilla_endgameish = weak_rank >= TIER_RANK.get("lunar", 11) or float((weak_card.get("signals") or {}).get("damage") or 0) >= 150
    weapon_catalyst = weak_cat == "weapon" and weak_is_vanilla_endgameish
    same_family = strong_cat == weak_cat
    material_with_item = {strong_cat, weak_cat} & {"material"} and ({strong_cat, weak_cat} & {"weapon", "tool", "armor", "accessory"})
    recipe_relation = universal_parent_relation(strong_card, weak_card, tags)
    recipe_quality = str(recipe_relation.get("quality") or "")

    if strong_is_high_modded and recipe_quality in {"high_tier_material_with_credible_item", "high_tier_material_blend", "same_role_synergy", "same_mod_soft_synergy"}:
        quality = recipe_quality
        result_tier = strong_tier
        if recipe_quality == "high_tier_material_blend":
            multiplier, weak_factor = 0.90, 0.10
        elif recipe_quality == "high_tier_material_with_credible_item":
            multiplier, weak_factor = 0.88, 0.09
        else:
            multiplier, weak_factor = 0.94, 0.13
    elif strong_is_high_modded and weak_is_basic and not weapon_catalyst:
        quality = "diluted_weak_anchor"
        result_tier = influenced_tier(strong_tier)
        multiplier = 0.52
        weak_factor = 0.035
    elif strong_is_high_modded and weapon_catalyst:
        # Zenith is vanilla-endgame, not Calamity-endgame, but it is a very strong weapon base/catalyst.
        quality = "high_modded_material_plus_vanilla_endgame_catalyst"
        result_tier = strong_tier
        multiplier = 0.90
        weak_factor = 0.08
    elif strong_is_high_modded and material_with_item:
        quality = "high_modded_material_transfers_through_item"
        result_tier = strong_tier if weak_score >= VANILLA_ENDGAME_POWER * 0.55 else influenced_tier(strong_tier)
        multiplier = 0.80 if result_tier.endswith("_influenced") else 0.88
        weak_factor = 0.07
    elif recipe_quality in {"same_role_synergy", "same_mod_soft_synergy"} and strong_score >= TIER_DEFAULT_POWER.get("hardmode_early", 105):
        quality = recipe_quality
        result_tier = strong_tier
        multiplier = 0.92
        weak_factor = 0.12
    elif weak_score < strong_score * 0.20:
        quality = "asymmetric"
        result_tier = influenced_tier(strong_tier) if strong_is_high_modded else strong_tier
        multiplier = 0.68 if strong_is_high_modded else 0.78
        weak_factor = 0.06
    elif same_family or material_with_item:
        quality = "strong_synergy"
        result_tier = strong_tier
        multiplier = 0.94
        weak_factor = 0.14
    else:
        quality = "mixed"
        result_tier = strong_tier
        multiplier = 0.84
        weak_factor = 0.10

    result_power = max(1.0, strong_score * multiplier + weak_score * weak_factor)
    return {
        "quality": quality,
        "strongestTier": strong_tier,
        "weakestTier": weak_tier,
        "resultTier": result_tier,
        "strongestPowerScore": round(strong_score, 2),
        "weakestPowerScore": round(weak_score, 2),
        "resultPowerScore": round(result_power, 2),
        "powerMultiplier": round(multiplier, 3),
        "weakFactor": round(weak_factor, 3),
        "weakAnchor": bool(weak_is_basic and strong_score > 180),
        "weaponCatalyst": bool(weapon_catalyst),
        "recipeRelation": recipe_relation,
        "note": "High modded rarity tiers can outrank vanilla endgame; weak/basic anchors dilute result tier unless runtime metadata shows a credible anchor."
    }



def vanilla_like_weapon_envelope(stage: dict[str, Any] | str | None) -> dict[str, float]:
    return weapon_envelope_for_bucket(stage, extra_endgame_aliases=MODDED_HIGH_TIERS)


def clamp_vanilla_like_weapon_damage(
    raw_damage: int,
    max_parent_damage: int,
    stage: dict[str, Any],
    *,
    use_time: int | None = None,
    shot_count: int = 1,
    cost_multiplier: float = 1.0,
    raise_floor: bool = True,
) -> int:
    if raw_damage <= 0:
        return 0
    env = vanilla_like_weapon_envelope(stage)
    transfer = stage.get("powerTransfer") if isinstance(stage.get("powerTransfer"), dict) else {}
    weak_anchor = bool(transfer.get("weakAnchor"))
    catalyst = stage.get("catalystPressure") if isinstance(stage.get("catalystPressure"), dict) else {}
    catalyst_pressure = float(catalyst.get("pressure") or 0.0)

    stage_min = int(env["min"])
    stage_max = int(env["max"])
    # Parent inertia: generated upgrades should not randomly collapse, but weak/basic
    # anchors cannot multiply a strong weapon endlessly.
    if max_parent_damage > 0 and not weak_anchor:
        stage_min = min(max(stage_min, int(max_parent_damage * (0.42 + min(0.30, catalyst_pressure * 0.10)))), stage_max)
        stage_max = max(stage_max, int(max_parent_damage * (1.80 + min(0.55, catalyst_pressure * 0.14))) + 18)
    elif max_parent_damage > 0 and weak_anchor:
        stage_max = min(stage_max, max(max_parent_damage + int(env["weak_bonus"]), int(max_parent_damage * 1.32) + 12))

    # Fast/multishot authored weapons are bounded mostly by DPS, not by raw hit damage.
    if use_time is not None and use_time > 0:
        shots = max(1, min(8, int(shot_count or 1)))
        use = max(6.0, float(use_time))
        # `behavior_cost_multiplier` already includes shot_count pressure.  For DPS
        # comparison we count actual shots once, then apply only the non-shot part of
        # the cost as a mechanic pressure multiplier.  Older code divided by cost here,
        # which accidentally made expensive authored mechanics *easier* to keep at high
        # damage.
        shot_cost = 1.0 + max(0.0, shots - 1.0) * 0.55
        pressure_cost = max(0.55, min(2.75, float(cost_multiplier or 1.0) / max(1.0, shot_cost)))
        effective_dps = raw_damage * shots * 60.0 / use * pressure_cost
        dps_cap = float(env["dps"])
        if max_parent_damage > 0 and not weak_anchor:
            parent_use = max(6.0, float(stage.get("sourceFastestUseTime") or use_time))
            dps_cap = max(dps_cap, max_parent_damage * 60.0 / parent_use * 1.72)
        if weak_anchor:
            dps_cap *= 1.04
        if effective_dps > dps_cap:
            raw_damage = max(1, int(dps_cap * use / (60.0 * shots * pressure_cost)))

    floor = stage_min if raise_floor else 1
    return int(max(1, min(max(raw_damage, floor), stage_max)))

def stat_profile_for(a: dict[str, Any], b: dict[str, Any], tags: set[str]) -> dict[str, Any]:
    damages = [int(a.get("damage") or 0), int(b.get("damage") or 0)]
    rares = [int(a.get("rare") or 0), int(b.get("rare") or 0)]
    values = [int(a.get("value") or 0), int(b.get("value") or 0)]
    cards = [infer_item_card(a), infer_item_card(b)]
    rarity_baselines = [rarity_baseline_signal(a, tags_of(a), parent_primary_category(a)), rarity_baseline_signal(b, tags_of(b), parent_primary_category(b))]
    knowledge_scores = [float(c.get("powerScore") or 0) for c in cards]
    rarity_scores = [float(rarity_baselines[0].get("convertedPower") or 0), float(rarity_baselines[1].get("convertedPower") or 0)]
    scores = [max(item_power_score(a), knowledge_scores[0], rarity_scores[0]), max(item_power_score(b), knowledge_scores[1], rarity_scores[1])]
    transfer = recipe_power_transfer(cards, scores, tags)
    def _theme_only_parent(item: dict[str, Any]) -> bool:
        return (
            item_num(item, "damage", 0) <= 0
            and item_num(item, "shoot", 0) <= 0
            and item_num(item, "createTile", -1) >= 0
        )
    one_theme_parent = (_theme_only_parent(a) and item_num(b, "damage", 0) > 0) or (_theme_only_parent(b) and item_num(a, "damage", 0) > 0)
    catalyst = pair_catalyst_pressure(a, b)
    catalyst_pressure = float(catalyst.get("pressure") or 0.0)
    max_damage = max(damages)
    min_damage = min([d for d in damages if d > 0] or [0])
    second_damage = min_damage if max_damage != min_damage else (damages[0] if damages[0] else damages[1])
    # Fantasy tags are excluded from power. Mechanical stats, known rarity metadata,
    # value and category are the only progression evidence here.
    synergy = 0
    derived = max(float(transfer.get("resultPowerScore") or 0), max(scores) * 0.42 + min(scores) * 0.10 + synergy) + synergy
    if one_theme_parent and max_damage <= 18:
        derived = min(derived, 48.0)
    # Recursive generated items may become more complex, but depth alone must not staircase
    # weak early items into mech/plantera tiers.
    max_depth = max(generation_depth(a), generation_depth(b))
    if max_depth > 0 and max_damage <= 18:
        derived = min(derived, 54.0)  # at most pre-boss for weak recursive chains
    elif max_depth > 0 and max_damage <= 32:
        derived = min(derived, 84.0)  # at most late pre-hardmode for modest recursive chains
    # Broad serious-material lift. This is route/progression pressure, not a named recipe.
    if max_damage > 0 and catalyst_pressure > 0:
        derived += catalyst_pressure * 30.0
    if max_damage > 0:
        derived_damage = max_damage + int(second_damage * 0.28) + 5 + int((derived ** 0.5) * 0.72)
        if catalyst_pressure > 0:
            derived_damage += int(max(1, max_damage) * (0.12 + 0.14 * catalyst_pressure))
    else:
        derived_damage = 0
    # soft anti-spike: weak non-weapon ingredient should not drag a good weapon down, but also should not double it.
    damage_cap = max(12, max_damage + max(12, int(max_damage * (0.58 + 0.24 * catalyst_pressure))) + synergy) if max_damage > 0 else 0
    # A Calamity-tier material can raise a vanilla weapon base, but weak anchors still do not create a full-tier weapon.
    strongest_material_power = max([float(c.get("powerScore") or 0) for c in cards if c.get("category") == "material" or c.get("signals", {}).get("isMaterial")] or [0.0])
    if max_damage > 0 and strongest_material_power > VANILLA_ENDGAME_POWER:
        quality = str(transfer.get("quality") or "")
        lift_mul = 0.24 if "vanilla_endgame_catalyst" in quality else 0.12 if not str(transfer.get("resultTier", "")).endswith("_influenced") else 0.05
        material_lift = int(max(0.0, strongest_material_power - VANILLA_ENDGAME_POWER) * lift_mul)
        derived_damage += int(material_lift * 0.62)
        damage_cap = max(damage_cap, max_damage + max(10, material_lift))
    if max_damage > 0:
        derived_damage = clamp(derived_damage, max(1, max_damage + 1), damage_cap)
    power_budget = 0.95 + min(5.6, derived / 50.0)
    if derived < 16: hint = "wood"
    elif derived < 32: hint = "early"
    elif derived < 55: hint = "pre_boss"
    elif derived < 85: hint = "pre_hardmode_late"
    elif derived < 125: hint = "hardmode_early"
    elif derived < 175: hint = "mech"
    elif derived < 235: hint = "plantera"
    elif derived < 310: hint = "lunar"
    else: hint = "endgame"
    strongest_tiers = {str(c.get("tier", "")) for c in cards}
    transfer_tier = str(transfer.get("resultTier") or "")
    if transfer_tier in MODDED_HIGH_TIERS or transfer_tier.endswith("_influenced"):
        hint = "endgame"
    elif strongest_tiers & {"endgame", "post_moonlord", "superboss", "devourer", "auric", "exo_yharon_plus", "shadowspec", "calamity_red_prefix"}:
        hint = "endgame"
    elif "lunar" in strongest_tiers and hint not in {"endgame", "lunar"}:
        hint = "lunar"
    elif strongest_tiers & {"post_plantera", "post_golem"} and hint in {"wood", "early", "pre_boss", "pre_hardmode_late", "hardmode_early", "mech"}:
        hint = "plantera"
    return {
        "name": hint,
        "balanceMode": "stat_and_knowledge_derived",
        "scores": [round(scores[0], 2), round(scores[1], 2)],
        "knowledgePowerScores": [round(knowledge_scores[0], 2), round(knowledge_scores[1], 2)],
        "knowledgeTiers": [cards[0].get("tier", "unknown"), cards[1].get("tier", "unknown")],
        "powerTransfer": transfer,
        "catalystPressure": catalyst,
        "rarityBaselineScores": [round(rarity_scores[0], 2), round(rarity_scores[1], 2)],
        "rarityBaselines": rarity_baselines,
        "sourceDamage": damages,
        "sourceFastestUseTime": min([float(item_num(x, "useTime", 999)) for x in (a, b) if item_num(x, "damage") > 0] or [float(item_num(a, "useTime", 20) or item_num(b, "useTime", 20) or 20)]),
        "sourceRarity": rares,
        "sourceValue": values,
        "parentGeneratedDepths": [generation_depth(a), generation_depth(b)],
        "recipeCoherence": recipe_coherence(tags, a, b),
        "derivedPower": round(derived, 2),
        "derivedDamage": int(derived_damage),
        "powerBudget": round(power_budget, 2),
        "balanceEnvelope": vanilla_like_weapon_envelope(hint),
        "rarity": max(0, min(13, max(rares) + (1 if derived > 85 else 0) + (1 if derived > 175 else 0))),
        "value": max(values) + int(derived * 65) + 100,
        "useTime": clamp(30 - int(power_budget * 2.45), 13, 34),
        "speed": round(6.75 + min(7.25, power_budget * 1.15), 2),
        "pierce": 1 + int(power_budget >= 1.65) + int(power_budget >= 2.75) + int(power_budget >= 4.1) + int(power_budget >= 5.3),
        "mana": clamp(4 + int(power_budget * 1.25), 0, 18),
    }

def canvas_tier_for(name: str, tags: set[str], kind: str, stage: dict[str, Any]) -> dict[str, Any]:
    name_l = name.lower()
    head_small = any(x in name_l for x in ["shortsword", "dagger", "knife", "needle", "coin", "seed", "potion", "gem", "shard"])
    head_large = any(x in name_l for x in ["zenith", "night", "edge", "great", "grand", "giant", "station", "computer", "workbench", "throne"])
    power = float(stage.get("powerBudget", 1.0))
    if kind == "weapon":
        if head_small and power < 2.0:
            canvas = 32
        elif head_large or power >= 3.25:
            canvas = 64
        elif ("sword" in tags or "blade" in tags or "staff" in tags or "bow" in tags or "gun" in tags or power >= 1.8):
            canvas = 48
        else:
            canvas = 32
    elif kind in {"furniture", "technology", "placeable_station"}:
        canvas = 64 if head_large else 48
    else:
        canvas = 32
    visual_mass = {32: 0, 48: 1, 64: 2}[canvas]
    return {"canvas": canvas, "visualMass": visual_mass}

def size_profile_for(name: str, tags: set[str], kind: str, stage: dict[str, Any] | None = None) -> dict[str, Any]:
    stage = stage or {"powerBudget": 1.0, "name": "early"}
    canvas = canvas_tier_for(name, tags, kind, stage)
    visual_mass = canvas["visualMass"]
    power = float(stage.get("powerBudget", 1.0))
    if kind == "weapon":
        item_scale = 1.0 + 0.12 * visual_mass
        hitbox_scale = 1.0 + 0.10 * visual_mass + min(power, 4.8) * 0.035
        projectile_scale = 1.0 + 0.14 * visual_mass
    else:
        item_scale = 1.0 + 0.06 * visual_mass
        hitbox_scale = 1.0
        projectile_scale = 1.0
    return {
        "oversized": visual_mass,
        "itemScale": round(item_scale, 3),
        "inventoryScale": round(1.0 + 0.08 * visual_mass, 3),
        "worldScale": round(1.0 + 0.10 * visual_mass, 3),
        "preferredCanvasSize": canvas["canvas"],
        "projectileScale": round(max(projectile_scale, 1.08) if kind == "weapon" else projectile_scale, 3),
        # Visual/readability floor: even low-tier generated weapon projectiles should not
        # look smaller than vanilla starter attacks. Keep gameplay conservative, but stop
        # emitting 12px specks from readable weapon sprites.
        "projectileWidth": 16 + 4 * visual_mass if kind == "weapon" else 14,
        "projectileHeight": 16 + 4 * visual_mass if kind == "weapon" else 14,
        "hitboxScale": round(hitbox_scale, 3),
        "explosionRadius": 0,
        "holdoutOffsetX": -3 * visual_mass if kind == "weapon" else 0,
        "holdoutOffsetY": -2 * visual_mass if kind == "weapon" else 0,
    }

def balanced_damage(max_parent_damage: int, tags: set[str], stage: dict[str, Any]) -> int:
    if "weapon" not in tags and max_parent_damage <= 0:
        return 0
    raw = max(1, int(stage.get("derivedDamage") or max_parent_damage + 4))
    return clamp_vanilla_like_weapon_damage(raw, max_parent_damage, stage)

__all__ = [
    "apply_family_locks_to_genome",
    "preservation_score",
    "item_power_score",
    "tier_rank",
    "influenced_tier",
    "universal_parent_relation",
    "recipe_power_transfer",
    "vanilla_like_weapon_envelope",
    "clamp_vanilla_like_weapon_damage",
    "stat_profile_for",
    "canvas_tier_for",
    "size_profile_for",
    "balanced_damage",
]
