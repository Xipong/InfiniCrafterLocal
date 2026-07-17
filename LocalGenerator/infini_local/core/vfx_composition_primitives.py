from __future__ import annotations

import re
from typing import Any

from infini_local.core.item_identity_tools import stable_hash
from infini_local.core.vfx_manifest_config import (
    VFX_EMERGENCY_MAX_DRAW_CALLS,
    VFX_EMERGENCY_MAX_PARTICLES_PER_TICK,
    VFX_EMERGENCY_MAX_PARTICLES_TOTAL,
    VFX_MAGNITUDE_JITTER,
    VFX_RENDER_QUALITY,
)

# AGENT MAP: shared VFX composition primitives. Owns deterministic jitter,
# renderer/channel normalization, slot scoring/arbitration, effect magnitude,
# emergency budgets, and particle-system address resolution.

_VFX_PARTICLE_ADDRESS_CATALOG: dict[str, dict[str, Any]] = {
    "pl:glow": {
        "kind": "quad",
        "blend": "additive",
        "layer": "BeforeProjectiles",
        "notes": "Soft additive quads for beams, magic ribbons, core glow and luminous baked tape.",
    },
    "pl:shard": {
        "kind": "quad",
        "blend": "alpha",
        "layer": "BeforeProjectiles",
        "notes": "Material-looking quad particles for impact chunks, fragment bursts and heavier hit debris.",
    },
    "pl:smoke": {
        "kind": "quad",
        "blend": "alpha",
        "layer": "BeforeProjectiles",
        "notes": "Longer-lived alpha quads for decay, smoke, residue and field haze.",
    },
    "pl:spark": {
        "kind": "point",
        "blend": "additive",
        "layer": "BeforeProjectiles",
        "notes": "Cheap additive point particles for sparks, glints, star specks and high-count accents.",
    },
    "dust": {
        "kind": "fallback",
        "blend": "alpha",
        "layer": "BeforeProjectiles",
        "notes": "Explicit vanilla Dust fallback. Use only when ParticleLibrary routing is not desired.",
    },
}

def _vfx_available_roles(data: dict[str, Any]) -> set[str]:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    roles: set[str] = set()
    if attack.get("projectileSpritePath") or attack.get("projectileSpritePrompt") or visual.get("projectileImagePrompt"):
        roles.add("projectile")
    if attack.get("impactSpritePath") or attack.get("impactSpritePrompt") or visual.get("impactImagePrompt"):
        roles.add("impact")
    if attack.get("childSpritePath") or attack.get("childSpritePrompt") or visual.get("childImagePrompt"):
        roles.add("child")
    if attack.get("fieldSpritePath") or attack.get("fieldSpritePrompt") or visual.get("fieldImagePrompt"):
        roles.add("field")
    return roles


def _vfx_seed_int(*parts: Any) -> int:
    return int(stable_hash(*parts, length=12), 16) & 0x7fffffff

def _vfx_unit(seed: int, salt: str) -> float:
    return (_vfx_seed_int(seed, salt) % 100000) / 99999.0

def _vfx_pick(seed: int, salt: str, values: list[Any], fallback: Any = 0) -> Any:
    if not values:
        return fallback
    return values[_vfx_seed_int(seed, salt) % len(values)]

def _vfx_lerp_range(seed: int, salt: str, value: Any, fallback: float) -> float:
    if isinstance(value, list) and len(value) >= 2:
        try:
            lo = float(value[0]); hi = float(value[1])
            if hi < lo:
                lo, hi = hi, lo
            return lo + (hi - lo) * _vfx_unit(seed, salt)
        except Exception:
            return fallback
    try:
        return float(value)
    except Exception:
        return fallback

CANONICAL_VFX_RENDERERS = frozenset({
    "projectileAfterimage", "spriteStampTrail", "historyRibbon", "tipTrail", "ghostArc", "wavyStrip",
    "beamLine", "fieldPulse", "orbitingMotes", "actorAfterimage", "impactRing", "impactSprite",
    "childMotes", "lightCue", "soundCue",
})

_MOTION_RENDERERS = frozenset({"projectileAfterimage", "spriteStampTrail", "historyRibbon", "tipTrail", "ghostArc", "wavyStrip", "beamLine"})
_PRIMITIVE_RENDERERS = frozenset({"historyRibbon", "tipTrail", "wavyStrip", "beamLine"})
_SPRITE_RENDERERS = frozenset({"projectileAfterimage", "spriteStampTrail", "ghostArc", "fieldPulse", "actorAfterimage", "impactRing", "impactSprite"})
_ACCENT_RENDERERS = frozenset({"childMotes", "orbitingMotes"})
_IMPACT_RENDERERS = frozenset({"impactRing", "impactSprite"})


def _vfx_renderer_kind(renderer: Any) -> str:
    """Accept one exact current renderer id; never classify free text."""
    raw = str(renderer or "").strip()
    return raw if raw in CANONICAL_VFX_RENDERERS else "none"


def _vfx_default_importance(event: Any, renderer: Any = "") -> str:
    e = str(event or "").strip()
    r = _vfx_renderer_kind(renderer)
    if e == "hit" or r in _IMPACT_RENDERERS:
        return "core"
    if r in _MOTION_RENDERERS or r == "fieldPulse":
        return "secondary"
    if r in _ACCENT_RENDERERS or r in {"soundCue", "lightCue"}:
        return "accent"
    if r == "actorAfterimage":
        return "luxury"
    return "secondary"


def _vfx_default_visual_cost(renderer: Any, density: float = 0.35) -> float:
    r = _vfx_renderer_kind(renderer)
    base = {
        "impactRing": 0.42, "impactSprite": 0.42,
        "historyRibbon": 0.34, "tipTrail": 0.34, "wavyStrip": 0.34,
        "projectileAfterimage": 0.30, "spriteStampTrail": 0.30, "ghostArc": 0.30,
        "childMotes": 0.28, "orbitingMotes": 0.34,
        "actorAfterimage": 0.58, "fieldPulse": 0.58, "beamLine": 0.46,
        "lightCue": 0.12, "soundCue": 0.08,
    }.get(r, 0.18)
    try:
        return max(0.0, min(1.0, base + float(density or 0) * 0.28))
    except Exception:
        return base


def _vfx_default_signature_weight(event: Any, renderer: Any = "") -> float:
    e = str(event or "").strip()
    r = _vfx_renderer_kind(renderer)
    if e == "hit" or r in _IMPACT_RENDERERS:
        return 0.72
    if r in {"historyRibbon", "tipTrail", "wavyStrip", "beamLine", "fieldPulse"}:
        return 0.58
    if r in {"actorAfterimage", "orbitingMotes"}:
        return 0.52
    if r == "childMotes":
        return 0.30
    return 0.45


def _vfx_event_stage(event: Any, renderer: Any = "") -> str:
    e = str(event or "").strip()
    if e == "hit": return "impact"
    if e in {"kill", "expire"}: return "decay"
    if e == "active": return "active"
    return "loop"


def _vfx_default_backend(event: Any, renderer: Any = "") -> str:
    r = _vfx_renderer_kind(renderer)
    if r in _PRIMITIVE_RENDERERS: return "Primitive"
    if r in _SPRITE_RENDERERS: return "Sprite"
    if r in _ACCENT_RENDERERS: return "Realtime"
    return "Auto"


def _vfx_default_anchor(event: Any, renderer: Any = "") -> str:
    e = str(event or "").strip()
    r = _vfx_renderer_kind(renderer)
    if e == "hit": return "hitPoint"
    if r in {"tipTrail", "historyRibbon", "ghostArc", "wavyStrip"}: return "tipHistory"
    if r == "beamLine": return "velocity"
    if r == "fieldPulse": return "field"
    return "self"


def _vfx_infer_channel(renderer: Any, event: Any = "") -> str:
    r = _vfx_renderer_kind(renderer)
    e = str(event or "").strip()
    if r == "soundCue": return "sound"
    if r == "lightCue": return "light"
    if r in _MOTION_RENDERERS: return "motionTrail"
    if r in {"fieldPulse", "orbitingMotes", "actorAfterimage"}: return "coreGlow"
    if r == "childMotes": return "impactParticles" if e in {"hit", "kill", "expire"} else "ambientParticles"
    if r in _IMPACT_RENDERERS: return "impactShape"
    return "motionTrail"


def _vfx_infer_emission_mode(renderer: Any, event: Any = "") -> str:
    r = _vfx_renderer_kind(renderer)
    e = str(event or "").strip()
    if r == "orbitingMotes": return "orbit"
    if e == "hit": return "ring" if r == "impactRing" else "burst"
    if e in {"kill", "expire"}: return "residue"
    return "wake"


def _vfx_infer_lane(slot: dict[str, Any]) -> str:
    lane = str(slot.get("lane") or "").strip()
    if lane in {"primary", "support", "accent", "ornament", "cue"}: return lane
    imp = str(slot.get("importance") or "").strip()
    renderer = _vfx_renderer_kind(slot.get("rendererKind"))
    channel = str(slot.get("channel") or _vfx_infer_channel(renderer, slot.get("event")))
    if channel in {"light", "sound"} or renderer in {"lightCue", "soundCue"}: return "cue"
    if imp == "core": return "primary"
    if imp == "secondary": return "support"
    if imp == "luxury": return "ornament"
    if imp == "accent": return "accent"
    if renderer in _IMPACT_RENDERERS: return "support"
    if renderer in _ACCENT_RENDERERS: return "accent"
    return "primary"


def _vfx_renderer_family(renderer: Any) -> str:
    return _vfx_renderer_kind(renderer)


def _vfx_event_group(event: Any) -> str:
    e = str(event or "").strip()
    if e == "hit": return "hit"
    if e in {"kill", "expire"}: return "kill"
    return "live"

def _vfx_score_number(value: Any, fallback: float = 0.0) -> float:
    try:
        if isinstance(value, list):
            vals = [float(x) for x in value[:2]]
            return sum(vals) / max(1, len(vals))
        return float(value)
    except Exception:
        return fallback

def _vfx_slot_score(slot: dict[str, Any]) -> float:
    imp = str(slot.get("importance") or "secondary")
    score = {"core": 100.0, "secondary": 50.0, "accent": 20.0, "luxury": 5.0}.get(imp, 25.0)
    score += _vfx_score_number(slot.get("signatureWeight"), 0.0) * 20.0
    score -= _vfx_score_number(slot.get("visualCost"), 0.0) * 10.0
    score += _vfx_score_number(slot.get("density"), 0.0) * 3.0
    if str(slot.get("source") or "").lower() == "authoredcue":
        # Explicit model-authored VFX cues should survive recipe/background slots when
        # they compete for the same visual lane. This is still visual-only: it does
        # not bypass slot caps, gameplay validation, or renderer sanitization.
        score += 40.0
    if slot.get("channel") in {"light", "sound"}:
        score += 8.0
    return score

def _vfx_max_channel_count(group: str, channel: str, magnitude_class: str) -> int:
    if channel in {"light", "sound"}:
        return 1
    large = magnitude_class in {"large", "signature"}
    signature = magnitude_class == "signature"
    if group == "live" and channel == "motionTrail":
        return 3 if signature else (2 if large else 1)
    if group == "live" and channel == "coreGlow":
        return 2 if signature else 1
    if group == "live" and channel == "ambientParticles":
        return 2 if large else 1
    if group == "hit" and channel == "impactShape":
        return 3 if signature else (2 if large else 1)
    if group == "hit" and channel == "impactParticles":
        return 2 if large else 1
    if group == "kill" and channel in {"decaySmoke", "impactShape"}:
        return 3 if signature else 2
    return 1

def _vfx_arbitrate_slots(slots: list[dict[str, Any]], magnitude_class: str) -> list[dict[str, Any]]:
    """Scene composer: allow Calamity-like layered slots, but only across distinct lanes.

    Old v0.3.29 logic was intentionally anti-kasha: one main slot per visual channel.
    That was too strict for references like Terratomere, where a crescent, light streak,
    motes and impact flash coexist. v0.3.30 keeps channel caps, but separates lanes:
    primary/support/accent/ornament/cue.
    """
    selected: dict[tuple[str, str, str], dict[str, Any]] = {}
    channel_counts: dict[tuple[str, str], int] = {}
    used_families: set[tuple[str, str, str]] = set()

    for slot in sorted([x for x in slots if isinstance(x, dict)], key=_vfx_slot_score, reverse=True):
        group = _vfx_event_group(slot.get("event"))
        channel = str(slot.get("channel") or _vfx_infer_channel(slot.get("rendererKind"), slot.get("event")))
        lane = _vfx_infer_lane(slot)
        family = _vfx_renderer_family(slot.get("rendererKind"))
        lane_key = (group, channel, lane)
        channel_key = (group, channel)
        fam_key = (group, channel, family)

        if fam_key in used_families and channel not in {"light", "sound"}:
            continue

        max_count = _vfx_max_channel_count(group, channel, magnitude_class)
        current = channel_counts.get(channel_key, 0)

        if lane_key not in selected:
            if current >= max_count:
                # Replace weakest non-primary lane in this channel only if the new slot is better.
                candidates = [(k, v) for k, v in selected.items() if k[0] == group and k[1] == channel]
                if not candidates:
                    continue
                def replace_score(pair: tuple[tuple[str, str, str], dict[str, Any]]) -> float:
                    k, v = pair
                    score = _vfx_slot_score(v)
                    if k[2] == "primary":
                        score += 25.0
                    return score
                weakest_key, weakest = min(candidates, key=replace_score)
                if _vfx_slot_score(slot) <= _vfx_slot_score(weakest):
                    continue
                selected.pop(weakest_key, None)
                current -= 1
            selected[lane_key] = slot | {"lane": lane, "channel": channel}
            channel_counts[channel_key] = current + 1
            used_families.add(fam_key)
            continue

        if _vfx_slot_score(slot) > _vfx_slot_score(selected[lane_key]):
            selected[lane_key] = slot | {"lane": lane, "channel": channel}
            used_families.add(fam_key)

    out = list(selected.values())
    out.sort(key=_vfx_slot_score, reverse=True)
    return out

def _vfx_motif_from_data(data: dict[str, Any], words: set[str], pattern: str) -> dict[str, Any]:
    element = "neutral"
    probes = [
        ("fire", {"fire", "flame", "ember", "burn"}),
        ("frost", {"ice", "frost", "snow", "crystal"}),
        ("shadow", {"shadow", "void", "dark", "curse", "ghost", "soul"}),
        ("toxic", {"toxic", "poison", "acid", "slime", "goo"}),
        ("blood", {"blood", "red", "flesh"}),
        ("holy", {"holy", "light", "gold", "star", "solar"}),
        ("metal", {"metal", "iron", "steel", "coin", "gear"}),
    ]
    for name, ws in probes:
        if words & ws:
            element = name
            break
    shape = "beam" if "beam" in pattern or "laser" in pattern else "field" if "field" in pattern else "slash" if "slash" in pattern else "shard"
    if words & {"ring", "circle", "rune"}:
        shape = "ring"
    elif words & {"smoke", "cloud", "mist"}:
        shape = "smoke"
    motion = "orbit" if "orbit" in pattern or "orbit" in words else "pulse" if "field" in pattern else "forward"
    rhythm = 1.35 if words & {"snappy", "quick", "fast"} else 0.75 if words & {"slow", "delayed"} else 1.0
    chaos = 0.6 if words & {"chaotic", "ragged", "broken", "frayed", "wild"} else 0.25
    return {"element": element, "shapeLanguage": shape, "motionLanguage": motion, "paletteRole": "primary", "rhythm": round(rhythm, 2), "chaos": round(chaos, 2)}

def _vfx_magnitude_class(value: float) -> str:
    v = max(0.0, min(1.0, float(value or 0.0)))
    if v < 0.22:
        return "tiny"
    if v < 0.42:
        return "small"
    if v < 0.66:
        return "normal"
    if v < 0.86:
        return "large"
    return "signature"

def _vfx_compute_effect_magnitude(recipe: dict[str, Any], power: float, seed: int | str | None = None, data: dict[str, Any] | None = None) -> float:
    """Item-driven VFX magnitude.

    v0.3.26 deliberately separates item effect magnitude from render quality.
    Terraria does not need Low/Medium/High/Ultra as an art axis; magnitude is
    derived from item power/recipe cost/novelty-ish debug hints plus stable seed.
    """
    cost = str(recipe.get("cost") or "medium").lower()
    cost_bias = {"tiny": -0.18, "low": -0.12, "medium": 0.0, "normal": 0.0, "high": 0.13, "signature": 0.24, "ultra": 0.30}.get(cost, 0.0)
    try:
        pwr = float(power or 1.0)
    except Exception:
        pwr = 1.0
    # powerBudget in this project is not a Terraria damage number; keep it soft and capped.
    power_bias = max(-0.16, min(0.28, (pwr - 1.0) * 0.18))
    debug = (data or {}).get("debug") if isinstance((data or {}).get("debug"), dict) else {}
    gameplay = (data or {}).get("gameplay") if isinstance((data or {}).get("gameplay"), dict) else {}
    novelty_raw = debug.get("novelty") or debug.get("noveltyScore") or gameplay.get("novelty") or gameplay.get("noveltyScore") or 0.0
    try:
        novelty_bias = max(0.0, min(0.14, float(novelty_raw) * 0.08))
    except Exception:
        novelty_bias = 0.0
    slot_count = len(recipe.get("slots") or [])
    structural_bias = max(-0.06, min(0.12, (slot_count - 2) * 0.018))
    stable_seed = _vfx_seed_int(seed or "magnitude", recipe.get("id"), pwr, cost)
    jitter = (_vfx_unit(stable_seed, "mag") - 0.5) * max(0.0, VFX_MAGNITUDE_JITTER)
    value = 0.48 + cost_bias + power_bias + novelty_bias + structural_bias + jitter
    return round(max(0.08, min(1.0, value)), 3)

def _vfx_budget_for_recipe(recipe: dict[str, Any], power: float, seed: int | str | None = None, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Emergency budget, not a graphics-quality preset.

    Render quality is always Full. Budget numbers are emergency caps and are scaled
    by effectMagnitude so weak items do not get signature-sized particle spam while
    rare/high-power items can still look large.
    """
    magnitude = _vfx_compute_effect_magnitude(recipe, power, seed, data)
    budget_class = _vfx_magnitude_class(magnitude)
    # v0.3.26: these are true emergency ceilings, not art-direction sliders.
    # Do not shrink the cap for weak/common items: recipe selection, slot density,
    # effectMagnitude and baked tape size already define how "large" the VFX is.
    # The cap only catches runaway manifests or pathological recipe combinations.
    spawn_mult = round(max(0.35, min(3.25, 0.60 + magnitude * 1.85)), 3)
    budget = {
        "renderQuality": VFX_RENDER_QUALITY,
        "quality": VFX_RENDER_QUALITY,  # compat: old C# reads Budget.Quality, but runtime no longer gates by it.
        "effectMagnitude": magnitude,
        "visualBudgetClass": budget_class,
        "emergencyCap": True,
        "maxParticlesPerTick": max(0, VFX_EMERGENCY_MAX_PARTICLES_PER_TICK),
        "maxParticlesTotal": max(0, VFX_EMERGENCY_MAX_PARTICLES_TOTAL),
        "maxDrawCalls": max(0, VFX_EMERGENCY_MAX_DRAW_CALLS),
        "spawnRateMultiplier": spawn_mult,
        "enableSoftGlow": True,
        "enablePointSparks": True,
        "enablePersistentSmoke": True,
    }
    return budget

def _vfx_playback_mode_for_recipe(recipe: dict[str, Any]) -> str:
    explicit = str(recipe.get("playbackMode") or recipe.get("preferredMode") or "").strip()
    if explicit:
        return explicit
    slots = recipe.get("slots") if isinstance(recipe.get("slots"), list) else []
    backends = {str(x.get("backend") or _vfx_default_backend(x.get("event"), x.get("rendererKind"))).lower() for x in slots if isinstance(x, dict)}
    if "baked" in backends and ("realtime" in backends or "primitive" in backends or "sprite" in backends):
        return "Hybrid"
    if "baked" in backends:
        return "Baked"
    if "realtime" in backends or "primitive" in backends:
        return "Realtime"
    return "Auto"

def _vfx_words(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-zA-Zа-яА-ЯёЁ0-9]+", (text or "").lower()) if len(w) >= 3}

def _vfx_color_hex(seed: int, salt: str, fallback: str = "") -> str:
    palettes = [
        "#78FF7A", "#DDF8FF", "#FFD36A", "#FF6A6A", "#9A7CFF", "#6AF5FF", "#FFFFFF", "#6AFFA6",
    ]
    if fallback:
        return fallback
    return palettes[_vfx_seed_int(seed, salt) % len(palettes)]

def _vfx_particle_address_catalog() -> dict[str, Any]:
    return {
        "schema": "infini.vfx.particle_address_catalog.v0",
        "default": "auto",
        "systems": _VFX_PARTICLE_ADDRESS_CATALOG,
        "guideline": "Recipes should set particleSystemId explicitly when they care about material: pl:glow, pl:shard, pl:smoke, pl:spark. Missing/auto ids are resolved from renderer/channel/event.",
    }

def _vfx_canonical_particle_address(value: Any) -> str:
    raw = str(value or "").strip()
    return raw if raw in {"auto", "pl:glow", "pl:shard", "pl:smoke", "pl:spark", "dust"} else "auto"

def _vfx_resolve_particle_system_id(raw: dict[str, Any] | None, renderer: str, event: str, channel: str = "", blend: str = "", emission_mode: str = "") -> str:
    raw = raw or {}
    explicit = _vfx_canonical_particle_address(raw.get("particleSystemId"))
    if explicit != "auto":
        return explicit
    r = _vfx_renderer_kind(renderer)
    e = str(event or "").strip()
    c = str(channel or "").strip()
    m = str(emission_mode or "").strip()
    if r == "soundCue" or c == "sound":
        return "dust"
    if r in {"lightCue", "beamLine", "fieldPulse", "historyRibbon", "tipTrail", "ghostArc", "wavyStrip", "projectileAfterimage", "spriteStampTrail"} or c in {"coreGlow", "light"}:
        return "pl:glow"
    if r == "childMotes":
        if c == "decaySmoke" or m == "residue" or e in {"kill", "expire"}:
            return "pl:smoke"
        if c == "impactParticles" or e == "hit":
            return "pl:shard"
        return "pl:spark"
    if r in {"impactRing", "impactSprite"}:
        return "pl:shard" if c == "impactParticles" else "pl:glow"
    if r == "orbitingMotes" or c == "ambientParticles":
        return "pl:spark"
    if e in {"kill", "expire"}:
        return "pl:smoke"
    if e == "hit":
        return "pl:shard"
    return "pl:glow"

__all__ = [
    "_VFX_PARTICLE_ADDRESS_CATALOG",
    "_vfx_available_roles",
    "_vfx_seed_int",
    "_vfx_unit",
    "_vfx_pick",
    "_vfx_lerp_range",
    "_vfx_default_importance",
    "_vfx_default_visual_cost",
    "_vfx_default_signature_weight",
    "_vfx_event_stage",
    "_vfx_default_backend",
    "_vfx_default_anchor",
    "_vfx_infer_channel",
    "_vfx_infer_emission_mode",
    "_vfx_infer_lane",
    "_vfx_renderer_family",
    "_vfx_renderer_kind",
    "_vfx_event_group",
    "_vfx_score_number",
    "_vfx_slot_score",
    "_vfx_max_channel_count",
    "_vfx_arbitrate_slots",
    "_vfx_motif_from_data",
    "_vfx_magnitude_class",
    "_vfx_compute_effect_magnitude",
    "_vfx_budget_for_recipe",
    "_vfx_playback_mode_for_recipe",
    "_vfx_words",
    "_vfx_color_hex",
    "_vfx_particle_address_catalog",
    "_vfx_canonical_particle_address",
    "_vfx_resolve_particle_system_id",
]
