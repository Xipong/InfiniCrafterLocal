from __future__ import annotations

from typing import Any


from infini_local.core.runtime_executor_vocabulary import EFFECT_CODE, MOVEMENT_CODE, ONHIT_CODE
from infini_local.core.runtime_family_policy import canonical_runtime_family
from infini_local.core.runtime_color_policy import normalize_runtime_color
from infini_local.core.sound_catalog import (
    SOUND_CATALOG_SOURCE,
    normalize_sound_catalog_id,
)


# AGENT MAP: presentation + exact attack-sound normalization seam.
# Owns presentationGenome defaults and canonical attack.sound* fallback values.
# It must not author gameplay behavior from prose or emit a duplicate sound DTO.

# Callers import this owner directly.


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
    attack_candidate = data.get("attack")
    attack: dict[str, Any] = attack_candidate if isinstance(attack_candidate, dict) else {}
    genome_candidate = attack.get("genome")
    genome: dict[str, Any] = genome_candidate if isinstance(genome_candidate, dict) else attack

    runtime_family = canonical_runtime_family(genome.get("runtimeFamily") or attack.get("runtimeFamily"))
    movement = str(genome.get("movement") or attack.get("movement") or "straight").strip()
    effect = str(genome.get("effect") or attack.get("effect") or "none").strip()
    onhit = str(genome.get("onHit") or attack.get("onHit") or "none").strip()


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

    trail = str(attack.get("projectileTrail") or genome.get("projectileTrail") or "").strip()
    impact = str(attack.get("projectileImpact") or genome.get("projectileImpact") or "").strip()
    color = normalize_runtime_color(attack.get("primaryColorName") or genome.get("primaryColorName"))
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
        "palette": data.get("visual", {}).get("palette") or ([color] if color else []),
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

            "glow": float(attack.get("runtimeLightStrength") or 0) > 0,

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
    attack_candidate = data.get("attack")
    attack: dict[str, Any] = attack_candidate if isinstance(attack_candidate, dict) else {}
    if attack.get("enabled"):
        pg = data.get("presentationGenome") or {}
        av = pg.get("attackVisual", {}) if isinstance(pg.get("attackVisual"), dict) else {}
        pv = pg.get("projectileVisual", {}) if isinstance(pg.get("projectileVisual"), dict) else {}
        iv = pg.get("impactVisual", {}) if isinstance(pg.get("impactVisual"), dict) else {}
        tv = pg.get("trailVisual", {}) if isinstance(pg.get("trailVisual"), dict) else {}
        attack["visualMode"] = str(av.get("mode") or "projectile")
        attack["trailStyle"] = str(tv.get("style") or pv.get("trailStyle") or "dust")
        attack["impactStyle"] = str(iv.get("style") or "small_flash")
        attack["primaryColorName"] = normalize_runtime_color(attack.get("primaryColorName"))
        genome_candidate = attack.get("genome")
        genome: dict[str, Any] = genome_candidate if isinstance(genome_candidate, dict) else {}
        use_catalog_id = normalize_sound_catalog_id(
            attack.get("soundUseCatalogId") or genome.get("soundUseCatalogId"),
            impact=False,
        )
        impact_catalog_id = normalize_sound_catalog_id(
            attack.get("soundImpactCatalogId") or genome.get("soundImpactCatalogId"),
            impact=True,
        )
        attack["soundUseCatalogId"] = use_catalog_id
        attack["soundImpactCatalogId"] = impact_catalog_id
        attack["soundCatalogSource"] = SOUND_CATALOG_SOURCE if use_catalog_id or impact_catalog_id else ""
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
