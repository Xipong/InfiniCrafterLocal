from __future__ import annotations

from typing import Any

from infini_local.core.runtime_authoring import runtime_plan
from infini_local.pipelines.pipeline_support import (
    EFFECT_CODE,
    EFFECT_PRESENTATION,
    LLM_RUNTIME_AUTHORING,
    MOVEMENT_CODE,
    ONHIT_CODE,
)


# AGENT MAP: presentation/sound derivation seam for combine/final-normalize.
# Owns presentationGenome and soundProfile defaults derived from explicit attack
# genome fields. It must not author gameplay behavior from prose.
# Public callers use infini_local.pipelines.combine_pipeline.

def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(n)))

def movement_for(tags: set[str], stage: dict[str, Any]) -> tuple[str, int]:
    """Non-runtime fallback default only. Runtime authoring should supply movement explicitly."""
    return "straight", MOVEMENT_CODE["straight"]

def effect_for(tags: set[str], stage: dict[str, Any]) -> tuple[str, int]:
    """Non-runtime fallback default only. Runtime authoring should supply effect explicitly."""
    return "dust", EFFECT_CODE["dust"]

def onhit_for(tags: set[str], stage: dict[str, Any]) -> tuple[str, int]:
    """Non-runtime fallback default only. Runtime authoring should supply onHit explicitly."""
    return "none", ONHIT_CODE["none"]

def presentation_from_genome(data: dict[str, Any]) -> dict[str, Any]:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    genome = attack.get("genome") if isinstance(attack.get("genome"), dict) else attack
    delivery = str(genome.get("delivery") or attack.get("delivery") or "none")
    runtime_family = str(genome.get("runtimeFamily") or attack.get("runtimeFamily") or "none")
    pattern = str(genome.get("attackPattern") or attack.get("pattern") or "").lower()
    movement = str(genome.get("movement") or attack.get("movement") or "straight")
    effect = str(genome.get("effect") or attack.get("effect") or "dust")
    onhit = str(genome.get("onHit") or attack.get("onHit") or "none")
    visual_text = " ".join(str(attack.get(k, "")) for k in ["weaponFamily", "projectileFamily", "projectileShape", "projectileMotion", "projectileTrail", "projectileImpact", "visualMode"]).lower()
    profile = EFFECT_PRESENTATION.get(effect, EFFECT_PRESENTATION.get(effect.replace("fire", "flame"), EFFECT_PRESENTATION["dust"]))
    if pattern == "laser_beam" or movement == "beam" or ("beam" in visual_text and "slash" not in visual_text):
        attack_mode = "beam"
    elif pattern in {"beam_slash", "beam_slash_burst"}:
        attack_mode = "slash_plus_projectile"
    elif pattern == "spear_thrust" or runtime_family == "thrust":
        attack_mode = "spear_thrust"
    elif pattern == "flail_tether" or movement == "flail_tether" or runtime_family == "flail":
        attack_mode = "flail_tether"
    elif pattern == "yoyo_hover" or movement == "yoyo_hover" or runtime_family == "yoyo":
        attack_mode = "yoyo_hover"
    elif pattern == "whip_lash" or movement == "whip_lash" or runtime_family == "whip":
        attack_mode = "whip_lash"
    elif pattern == "slash_holdout" or runtime_family == "swing":
        attack_mode = "slash_plus_projectile" if movement not in {"none", "straight"} or pattern == "slash_holdout" else "slash_arc"
    elif pattern == "falling_projectile" or movement in {"rain", "falling", "fall", "gravity_arc"} and ("fall" in visual_text or "rain" in visual_text or "meteor" in visual_text or "starfall" in visual_text):
        attack_mode = "falling_projectile"
    elif movement in {"orbit", "spiral"} or "orbit" in visual_text:
        attack_mode = "orbiting_projectile"
    else:
        attack_mode = "projectile"

    shape = str(attack.get("projectileShape") or "").strip()
    if not shape:
        if "knife" in visual_text or "blade" in visual_text:
            shape = "knife"
        elif "shuriken" in visual_text or "star" in visual_text:
            shape = "shuriken"
        elif "banner" in visual_text or "flag" in visual_text:
            shape = "banner_knife" if "knife" in visual_text else "banner"
        elif "rune" in visual_text or "glyph" in visual_text:
            shape = "rune"
        elif "lantern" in visual_text:
            shape = "lantern"
        elif "bottle" in visual_text or "potion" in visual_text or "vial" in visual_text:
            shape = "bottle"
        elif "orb" in visual_text or "bomb" in visual_text:
            shape = "orb"
        elif runtime_family == "swing":
            shape = "crescent"
        elif movement in {"orbit", "spiral"}:
            shape = "disc"
        else:
            shape = "bolt"

    trail = str(attack.get("projectileTrail") or "").strip() or profile["trail"]
    impact = str(attack.get("projectileImpact") or "").strip() or profile["impact"]
    color = profile["color"]
    return {
        "schema": "presentationGenome.v1",
        "palette": data.get("visual", {}).get("palette") or [color, "white"],
        "heldSprite": {
            "family": "weapon" if data.get("category") == "weapon" else str(data.get("category") or "generic"),
            "silhouette": "spear" if runtime_family == "thrust" else "flail" if runtime_family == "flail" else "yoyo" if runtime_family == "yoyo" else "whip" if runtime_family == "whip" else "staff" if runtime_family == "cast" else "sword" if runtime_family == "swing" else shape,
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
            "glow": effect not in {"none", "dust", "sand", "smoke"} or "glow" in visual_text or "light" in visual_text,
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

def sound_profile_from_genome(data: dict[str, Any]) -> dict[str, Any]:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    genome = attack.get("genome") if isinstance(attack.get("genome"), dict) else attack
    delivery = str(genome.get("delivery") or attack.get("delivery") or "none")
    runtime_family = str(genome.get("runtimeFamily") or attack.get("runtimeFamily") or "none")
    effect = str(genome.get("effect") or attack.get("effect") or "dust")
    onhit = str(genome.get("onHit") or attack.get("onHit") or "none")
    tag_text = " ".join(str(x) for x in (attack.get("attackPatternTags") or []) if x not in (None, "")) if isinstance(attack.get("attackPatternTags"), list) else str(attack.get("attackPatternTags") or "")
    text = " ".join(str(attack.get(k, "")) for k in ["soundUse", "soundImpact", "weaponFamily", "weaponSubfamily", "projectileFamily", "projectileImpact", "impactStyle", "soundUseSearchQuery", "soundImpactSearchQuery"]).lower()
    text = (text + " " + tag_text.lower()).strip()
    effect_profile = EFFECT_PRESENTATION.get(effect, EFFECT_PRESENTATION["dust"])
    subfamily = str(attack.get("weaponSubfamily") or attack.get("weaponFamily") or "").lower()
    use = subfamily if subfamily else ("gun" if runtime_family == "shoot" else "magic" if runtime_family == "cast" else "summon" if runtime_family == "summon" else "swing" if runtime_family in {"swing", "thrust", "flail", "yoyo", "whip"} else "soft")
    if "cloth" in text or "banner" in text: use = "soft"
    if "glass" in text or "chime" in text: use = "crystal"
    if "potion" in text or "heal" in text: use = "potion"
    explosive_effect = effect in {"explosion", "flame", "fire", "smoke"} and float(genome.get("aoeRadiusTiles") or 0) >= 0.75
    impact = "explosion" if explosive_effect else effect_profile["sound"]
    if "cloth" in text or "snap" in text: impact = "soft"
    if "heal" in text or "potion" in text: impact = "potion"
    if "glass" in text or "chime" in text: impact = "crystal"
    return {
        "schema": "soundProfile.v1",
        "use": use,
        "impact": impact,
        "effectLayer": effect_profile["sound"],
        "volume": 0.85,
        "pitch": 0.1 if effect in {"star", "electric", "crystal"} else -0.08 if runtime_family in {"swing", "thrust"} else 0.0,
        "variation": 0.18,
    }

def attach_presentation_and_sound(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data.get("presentationGenome"), dict) or not data.get("presentationGenome"):
        data["presentationGenome"] = presentation_from_genome(data)
    if not isinstance(data.get("soundProfile"), dict) or not data.get("soundProfile"):
        data["soundProfile"] = sound_profile_from_genome(data)
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    if attack.get("enabled"):
        pg = data.get("presentationGenome") or {}
        sp = data.get("soundProfile") or {}
        av = pg.get("attackVisual", {}) if isinstance(pg.get("attackVisual"), dict) else {}
        pv = pg.get("projectileVisual", {}) if isinstance(pg.get("projectileVisual"), dict) else {}
        iv = pg.get("impactVisual", {}) if isinstance(pg.get("impactVisual"), dict) else {}
        tv = pg.get("trailVisual", {}) if isinstance(pg.get("trailVisual"), dict) else {}
        attack["visualMode"] = str(av.get("mode") or "projectile")
        attack["trailStyle"] = str(tv.get("style") or pv.get("trailStyle") or "dust")
        attack["impactStyle"] = str(iv.get("style") or "small_flash")
        palette = pg.get("palette") if isinstance(pg.get("palette"), list) else []
        attack["primaryColorName"] = str(attack.get("primaryColorName") or pv.get("color") or (palette[0] if palette else ("dull" if bool(LLM_RUNTIME_AUTHORING and runtime_plan(data)) else "white")))
        attack["useSoundProfile"] = str(sp.get("use") or "soft")
        attack["impactSoundProfile"] = str(sp.get("impact") or sp.get("effectLayer") or "soft")
        attack["soundPitch"] = round(float(sp.get("pitch") or 0.0), 3)
        attack["soundVolume"] = round(float(sp.get("volume") or 0.85), 3)
        if not attack.get("soundUseSearchQuery"):
            q_bits = [attack.get("weaponSubfamily"), attack.get("weaponFamily"), attack.get("projectileFamily"), attack.get("movement"), attack.get("effect"), attack.get("useSoundProfile")]
            q_bits.extend(attack.get("attackPatternTags") or [] if isinstance(attack.get("attackPatternTags"), list) else [])
            attack["soundUseSearchQuery"] = " ".join(str(x).replace("_", " ") for x in q_bits if x not in (None, "", []))[:160]
        if not attack.get("soundImpactSearchQuery"):
            q_bits = [attack.get("weaponSubfamily"), attack.get("weaponFamily"), attack.get("projectileFamily"), attack.get("movement"), attack.get("effect"), attack.get("onHit"), attack.get("impactSoundProfile")]
            q_bits.extend(attack.get("attackPatternTags") or [] if isinstance(attack.get("attackPatternTags"), list) else [])
            attack["soundImpactSearchQuery"] = " ".join(str(x).replace("_", " ") for x in q_bits if x not in (None, "", []))[:160]
        data["attack"] = attack
    return data

__all__ = [
    "clamp",
    "movement_for",
    "effect_for",
    "onhit_for",
    "presentation_from_genome",
    "sound_profile_from_genome",
    "attach_presentation_and_sound",
]
