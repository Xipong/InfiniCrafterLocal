from __future__ import annotations

from typing import Any


from infini_local.core.runtime_executor_vocabulary import EFFECT_CODE, MOVEMENT_CODE, ONHIT_CODE
from infini_local.core.runtime_family_policy import canonical_runtime_family
from infini_local.core.runtime_color_policy import normalize_runtime_color, runtime_color_for_effect
from infini_local.core.sound_catalog import (
    SOUND_CATALOG_SOURCE,
    default_impact_sound_id,
    default_use_sound_id,
    normalize_sound_catalog_id,
)


# AGENT MAP: presentation + exact attack-sound normalization seam.
# Owns presentationGenome defaults and canonical attack.sound* fallback values.
# It must not author gameplay behavior from prose or emit a duplicate sound DTO.

# Callers import this owner directly.

_EFFECT_PRESENTATION = {
    "none": {"color": "white", "trail": "faint", "impact": "small_flash", "sound": "soft"},
    "electric": {"color": "cyan_yellow", "trail": "jagged_sparks", "impact": "electric_snap", "sound": "electric"},
    "slime": {"color": "green", "trail": "glob_droplets", "impact": "squish_burst", "sound": "slime"},
    "star": {"color": "white_gold", "trail": "sparkle", "impact": "starburst", "sound": "star"},
    "flame": {"color": "orange_red", "trail": "embers", "impact": "flame_pop", "sound": "fire"},
    "frost": {"color": "ice_blue", "trail": "snow_sparks", "impact": "ice_flash", "sound": "ice"},
    "leaf": {"color": "green_yellow", "trail": "leaf_specks", "impact": "petal_puff", "sound": "leaf"},
    "shadow": {"color": "purple_black", "trail": "dark_wisps", "impact": "shadow_flash", "sound": "shadow"},
    "poison": {"color": "toxic_green", "trail": "toxic_bubbles", "impact": "venom_splash", "sound": "poison"},
    "blood": {"color": "deep_red", "trail": "red_sparks", "impact": "cut_splatter", "sound": "cut"},
    "honey": {"color": "amber", "trail": "sticky_drops", "impact": "sticky_pop", "sound": "slime"},
    "sand": {"color": "sand_gold", "trail": "sand_grain", "impact": "sand_puff", "sound": "sand"},
    "lunar": {"color": "cyan_violet", "trail": "cosmic_sparkle", "impact": "lunar_burst", "sound": "star"},
    "heal": {"color": "green_pink", "trail": "soft_sparkle", "impact": "heal_pop", "sound": "heal"},
    "holy": {"color": "white_gold", "trail": "sparkle", "impact": "soft_flash", "sound": "star"},
    "smoke": {"color": "gray", "trail": "smoke", "impact": "smoke_puff", "sound": "soft"},
}


def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(n)))

def movement_for(tags: set[str], stage: dict[str, Any]) -> tuple[str, int]:
    """Non-runtime fallback default only. Runtime authoring should supply movement explicitly."""
    return "straight", MOVEMENT_CODE["straight"]

def effect_for(tags: set[str], stage: dict[str, Any]) -> tuple[str, int]:
    """Non-runtime fallback default only. Runtime authoring should supply effect explicitly."""
    return "smoke", EFFECT_CODE["smoke"]

def onhit_for(tags: set[str], stage: dict[str, Any]) -> tuple[str, int]:
    """Non-runtime fallback default only. Runtime authoring should supply onHit explicitly."""
    return "none", ONHIT_CODE["none"]

def presentation_from_genome(data: dict[str, Any]) -> dict[str, Any]:
    """Derive bounded presentation only from explicit compiled fields.

    No names, tooltips, materials, tags or fuzzy projectile prose select a mode.
    Authored projectileShape/projectileFamily may describe the sprite body, but do
    not select gameplay or a different runtime executor.
    """
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    genome = attack.get("genome") if isinstance(attack.get("genome"), dict) else attack

    runtime_family = canonical_runtime_family(genome.get("runtimeFamily") or attack.get("runtimeFamily"))
    movement = str(genome.get("movement") or attack.get("movement") or "straight").strip()
    effect = str(genome.get("effect") or attack.get("effect") or "none").strip()
    onhit = str(genome.get("onHit") or attack.get("onHit") or "none").strip()
    profile = _EFFECT_PRESENTATION.get(effect, _EFFECT_PRESENTATION["none"])

    attack_mode_by_family = {
        "beam": "beam",
        "thrust": "spear_thrust",
        "flail": "flail_tether",
        "yoyo": "yoyo_hover",
        "whip": "whip_lash",
        "swing": "slash_arc",
        "overhead_barrage": "falling_projectile",
    }
    attack_mode = attack_mode_by_family.get(runtime_family)
    if not attack_mode:
        attack_mode = "orbiting_projectile" if movement in {"orbit", "spiral"} else "projectile"

    explicit_shape = str(attack.get("projectileShape") or genome.get("projectileShape") or "").strip()
    projectile_family = str(attack.get("projectileFamily") or genome.get("projectileFamily") or "").strip()
    default_shape_by_family = {
        "swing": "crescent",
        "thrust": "spear",
        "returning": "disc",
        "flail": "orb",
        "yoyo": "disc",
        "whip": "lash_segment",
        "beam": "beam",
        "overhead_barrage": "projectile",
    }
    shape = explicit_shape or projectile_family or default_shape_by_family.get(runtime_family, "bolt")

    trail = str(attack.get("projectileTrail") or genome.get("projectileTrail") or "").strip() or profile["trail"]
    impact = str(attack.get("projectileImpact") or genome.get("projectileImpact") or "").strip() or profile["impact"]

    color = profile["color"]
    silhouette_by_family = {
        "thrust": "spear",
        "flail": "flail",
        "yoyo": "yoyo",
        "whip": "whip",
        "cast": "staff",
        "beam": "staff",
        "swing": "sword",
    }
    return {
        "schema": "presentationGenome.v1",
        "palette": data.get("visual", {}).get("palette") or [color, "white"],
        "heldSprite": {
            "family": "weapon" if data.get("category") == "weapon" else str(data.get("category") or "generic"),
            "silhouette": silhouette_by_family.get(runtime_family, shape),
            "sizeClass": "large" if float(genome.get("rangeTiles") or 0) >= 80 else "medium",
            "accent": color,
        },
        "attackVisual": {
            "mode": attack_mode,
            "movement": movement,
            "effect": effect,
            "onHit": onhit,
            "arcStyle": "straight_thrust" if runtime_family == "thrust" else "chain_tether" if runtime_family == "flail" else "hover_tether" if runtime_family == "yoyo" else "lash" if runtime_family == "whip" else "wide_crescent" if runtime_family == "swing" else "none",
            "flash": impact,

            "glow": effect not in {"none", "sand", "smoke"},

        },
        "projectileVisual": {
            "enabled": bool(attack.get("enabled")),
            "shape": shape,
            "trailStyle": trail,
            "color": color,
            "frames": 1,
        },
        "impactVisual": {"style": impact, "size": "large" if float(genome.get("aoeRadiusTiles") or 0) >= 3 else "medium" if onhit != "none" else "small", "color": color},
        "trailVisual": {"style": trail, "density": round(min(0.95, 0.2 + float(genome.get("extraUpdates") or 0) * 0.16 + float(genome.get("shotCount") or 1) * 0.04), 2), "color": color},
    }



def attach_presentation_and_sound(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data.get("presentationGenome"), dict) or not data.get("presentationGenome"):
        data["presentationGenome"] = presentation_from_genome(data)
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    if attack.get("enabled"):
        pg = data.get("presentationGenome") or {}
        av = pg.get("attackVisual", {}) if isinstance(pg.get("attackVisual"), dict) else {}
        pv = pg.get("projectileVisual", {}) if isinstance(pg.get("projectileVisual"), dict) else {}
        iv = pg.get("impactVisual", {}) if isinstance(pg.get("impactVisual"), dict) else {}
        tv = pg.get("trailVisual", {}) if isinstance(pg.get("trailVisual"), dict) else {}
        attack["visualMode"] = str(av.get("mode") or "projectile")
        attack["trailStyle"] = str(tv.get("style") or pv.get("trailStyle") or "dust")
        attack["impactStyle"] = str(iv.get("style") or "small_flash")
        attack["primaryColorName"] = normalize_runtime_color(attack.get("primaryColorName"), runtime_color_for_effect(attack.get("effect")))
        genome = attack.get("genome") if isinstance(attack.get("genome"), dict) else {}
        use_catalog_id = normalize_sound_catalog_id(
            attack.get("soundUseCatalogId") or genome.get("soundUseCatalogId"),
            impact=False,
        )
        impact_catalog_id = normalize_sound_catalog_id(
            attack.get("soundImpactCatalogId") or genome.get("soundImpactCatalogId"),
            impact=True,
        )
        attack["soundUseCatalogId"] = use_catalog_id or default_use_sound_id(attack.get("runtimeFamily"), attack.get("effect"), attack.get("delivery"))
        attack["soundImpactCatalogId"] = impact_catalog_id or default_impact_sound_id(attack.get("onHit"), attack.get("effect"))
        attack["soundCatalogSource"] = SOUND_CATALOG_SOURCE
        pitch_raw = attack.get("soundPitch") if attack.get("soundPitch") not in (None, "") else genome.get("soundPitch", 0.0)
        volume_raw = attack.get("soundVolume") if attack.get("soundVolume") not in (None, "") else genome.get("soundVolume", 0.85)
        variance_raw = attack.get("soundPitchVariance") if attack.get("soundPitchVariance") not in (None, "") else genome.get("soundPitchVariance", 0.18)
        attack["soundPitch"] = round(max(-0.9, min(0.9, float(pitch_raw or 0.0))), 3)
        attack["soundVolume"] = round(max(0.05, min(1.0, float(volume_raw or 0.85))), 3)
        attack["soundPitchVariance"] = round(max(0.0, min(0.6, float(variance_raw or 0.0))), 3)
        data["attack"] = attack
    return data

__all__ = [
    "clamp",
    "movement_for",
    "effect_for",
    "onhit_for",
    "presentation_from_genome",
    "attach_presentation_and_sound",
]
