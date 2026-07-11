from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from infini_local.core.vfx_director_contract import vfx_director_surface
from infini_local.core.vfx_manifest_config import (
    VFX_EMERGENCY_MAX_DRAW_CALLS,
    VFX_EMERGENCY_MAX_PARTICLES_PER_TICK,
    VFX_EMERGENCY_MAX_PARTICLES_TOTAL,
    VFX_PROCEDURAL_BLEND_CANDIDATES,
    VFX_PROCEDURAL_CHANCE,
    VFX_PROCEDURAL_COMPOSE,
    VFX_PROCEDURAL_MAX_EXTRA_SLOTS,
    VFX_RECIPE_BLEND_ENABLED,
    VFX_RENDER_QUALITY,
    VFX_RUNTIME_INTENT_FIRST,
)
from infini_local.core.vfx_composition_primitives import (
    _vfx_available_roles,
    _vfx_seed_int,
    _vfx_unit,
    _vfx_pick,
    _vfx_lerp_range,
    _vfx_default_importance,
    _vfx_default_visual_cost,
    _vfx_default_signature_weight,
    _vfx_event_stage,
    _vfx_default_backend,
    _vfx_default_anchor,
    _vfx_infer_channel,
    _vfx_infer_emission_mode,
    _vfx_infer_lane,
    _vfx_renderer_family,
    _vfx_renderer_kind,
    _vfx_event_group,
    _vfx_slot_score,
    _vfx_arbitrate_slots,
    _vfx_motif_from_data,
    _vfx_words,
    _vfx_color_hex,
    _vfx_resolve_particle_system_id,
)

# AGENT MAP: VFX slot compilation, baked command tape generation, procedural
# support layers, runtimePlan direct manifests, and explicit visual_effect_cue
# conversion.

def _vfx_baked_command_count(renderer: str, density: float, duration: int) -> int:
    r = str(renderer or "").lower()
    if any(x in r for x in ("flash", "ring", "light", "sound")):
        return max(1, min(4, int(round(1 + density * 3))))
    if any(x in r for x in ("burst", "mote", "spark", "smoke", "shard")):
        return max(3, min(18, int(round(4 + density * 20))))
    if any(x in r for x in ("trail", "ribbon", "stamp", "afterimage")):
        return max(2, min(12, int(round(2 + density * 12))))
    return max(1, min(8, int(round(1 + density * 8))))

def _vfx_should_bake_slot(raw: dict[str, Any], event: str, renderer: str, backend: str) -> bool:
    if raw.get("bake") is False or raw.get("baked") is False:
        return False
    if raw.get("bakedCommands"):
        return False
    b = str(backend or "").lower()
    e = str(event or "").lower()
    r = str(renderer or "").lower()
    if b in {"baked", "hybrid"}:
        return True
    if e in {"hit", "impact", "onhit", "kill", "expire", "decay"}:
        return True
    return any(x in r for x in ("burst", "smoke", "spark", "mote", "shard", "flash", "ring"))

def _vfx_bake_slot_commands(raw: dict[str, Any], seed: int, renderer: str, event: str, backend: str, density: float, duration: int, alpha: float, scale: float, spread: float) -> list[dict[str, Any]]:
    """Compile a lightweight baked spawn tape into the manifest.

    These commands are not semantic VFX. They are precomputed spawn events for the runtime
    to replay at deterministic ticks. Role textures/colors remain chosen by the manifest slot.
    """
    explicit = raw.get("bakedCommands")
    if isinstance(explicit, list):
        out = []
        for i, cmd in enumerate(explicit[:64]):
            if isinstance(cmd, dict):
                c = dict(cmd)
                c.setdefault("tick", 0)
                c.setdefault("particleSystemId", _vfx_resolve_particle_system_id(c, renderer, event, str(raw.get("channel") or ""), str(raw.get("blend") or ""), str(raw.get("emissionMode") or "")))
                c.setdefault("seedBucket", i)
                out.append(c)
        return out
    if not _vfx_should_bake_slot(raw, event, renderer, backend):
        return []
    count = _vfx_baked_command_count(renderer, density, duration)
    r = str(renderer or "").lower()
    out: list[dict[str, Any]] = []
    # Spread in local-space units. Runtime multiplies by projectile dimensions/scale.
    max_tick = max(1, min(120, duration))
    for i in range(count):
        cmd_seed = _vfx_seed_int(seed, renderer, event, "cmd", i)
        u = _vfx_unit(cmd_seed, "u")
        v = _vfx_unit(cmd_seed, "v")
        angle = (2.0 * math.pi) * u
        radial = (0.15 + 0.85 * v) * (0.35 + spread)
        # Trails bias backwards in local X, bursts are radial.
        if any(x in r for x in ("trail", "ribbon", "stamp", "afterimage")):
            local_x = -radial * (0.45 + i / max(1, count - 1))
            local_y = (v - 0.5) * (0.35 + spread * 0.45)
            vel_x = -0.20 - spread * 0.35 * u
            vel_y = (v - 0.5) * 0.55
            tick = int(round((i / max(1, count - 1)) * max_tick * 0.75))
        else:
            local_x = math.cos(angle) * radial
            local_y = math.sin(angle) * radial
            vel_x = math.cos(angle) * (0.35 + spread * 1.25)
            vel_y = math.sin(angle) * (0.35 + spread * 1.25)
            tick = int(round(_vfx_unit(cmd_seed, "tick") * max_tick * 0.75))
        out.append({
            "tick": max(0, min(max_tick, tick)),
            "particleSystemId": _vfx_resolve_particle_system_id(raw, renderer, event, str(raw.get("channel") or ""), str(raw.get("blend") or ""), str(raw.get("emissionMode") or "")),
            "textureRole": str(raw.get("particleRole") or raw.get("textureRole") or ""),
            "localX": round(local_x, 3),
            "localY": round(local_y, 3),
            "velocityX": round(vel_x, 3),
            "velocityY": round(vel_y, 3),
            "startColor": _vfx_color_hex(cmd_seed, "start"),
            "endColor": "#00000000",
            "scaleX": round(max(0.08, min(4.0, scale * (0.18 + _vfx_unit(cmd_seed, "sx") * 0.55))), 3),
            "scaleY": round(max(0.08, min(4.0, scale * (0.18 + _vfx_unit(cmd_seed, "sy") * 0.55))), 3),
            "scaleVelocityX": round(-0.002 - _vfx_unit(cmd_seed, "svx") * 0.018, 4),
            "scaleVelocityY": round(-0.002 - _vfx_unit(cmd_seed, "svy") * 0.018, 4),
            "rotation": round(angle, 3),
            "rotationVelocity": round((_vfx_unit(cmd_seed, "rv") - 0.5) * 0.25, 4),
            "lifespan": max(4, min(90, int(round(6 + duration * (0.35 + _vfx_unit(cmd_seed, "life") * 0.9))))),
            "alpha": round(max(0.02, min(1.0, alpha * (0.45 + _vfx_unit(cmd_seed, "a") * 0.55))), 3),
            "seedBucket": int(cmd_seed % 100000000),
        })
    return sorted(out, key=lambda x: int(x.get("tick", 0)))

def _vfx_baked_clip_meta(recipe_seed: int, slot_index: int, renderer: str, event: str, commands: list[dict[str, Any]]) -> dict[str, Any]:
    if not commands:
        return {"bakedClipId": "", "bakedClipHash": "", "bakedCommandCount": 0}
    compact = json.dumps(commands, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha1(compact.encode("utf-8")).hexdigest()[:16]
    safe_renderer = re.sub(r"[^a-zA-Z0-9_]+", "_", str(renderer or "clip")).strip("_").lower()[:32] or "clip"
    safe_event = re.sub(r"[^a-zA-Z0-9_]+", "_", str(event or "event")).strip("_").lower()[:16] or "event"
    return {
        "bakedClipId": f"{safe_event}_{safe_renderer}_{slot_index}_{digest[:8]}",
        "bakedClipHash": digest,
        "bakedCommandCount": len(commands),
    }

def _vfx_compile_slot(raw: dict[str, Any], seed: int, slot_index: int, power_budget: float, effect_magnitude: float = 0.5) -> dict[str, Any]:
    renderer_kind = _vfx_renderer_kind(raw.get("rendererKind") or raw.get("rendererKind"))
    if renderer_kind == "none":
        renderer_kind = "projectileAfterimage"
    renderer = renderer_kind
    event = str(raw.get("event") or "tick").strip()
    if event not in {"travel", "active", "tick", "hit", "kill", "expire"}:
        event = "tick"
    slot_seed = _vfx_seed_int(seed, renderer_kind, slot_index)
    variants = raw.get("variants") if isinstance(raw.get("variants"), list) else []
    scale = _vfx_lerp_range(slot_seed, "scale", raw.get("scale"), 1.0)
    density = _vfx_lerp_range(slot_seed, "density", raw.get("density"), 0.35)
    duration = int(round(_vfx_lerp_range(slot_seed, "duration", raw.get("duration"), 10)))
    alpha = _vfx_lerp_range(slot_seed, "alpha", raw.get("alpha"), 0.65)
    spread = _vfx_lerp_range(slot_seed, "spread", raw.get("spread"), 0.5)
    jitter = _vfx_lerp_range(slot_seed, "jitter", raw.get("jitter"), 0.35)
    phase_offset = _vfx_lerp_range(slot_seed, "phaseOffset", raw.get("phaseOffset"), 0.0)
    budget_weight = _vfx_lerp_range(slot_seed, "budgetWeight", raw.get("budgetWeight"), 1.0)
    start_tick = int(round(_vfx_lerp_range(slot_seed, "startTick", raw.get("startTick"), 0)))
    repeat_every = int(round(_vfx_lerp_range(slot_seed, "repeatEvery", raw.get("repeatEvery"), 0)))
    # Small power injection is allowed here; gameplay balance is not. Visual scale remains capped.
    visual_power = max(0.55, min(1.85, 0.72 + float(effect_magnitude or 0.5) * 0.86 + float(power_budget or 1.0) * 0.04))
    backend = str(raw.get("backend") or _vfx_default_backend(event, renderer_kind))
    event_group = _vfx_event_group(event)
    explicit_blend = str(raw.get("blend") or "").strip()
    blend = explicit_blend if explicit_blend in {"alpha", "additive"} else ("additive" if renderer_kind in {"lightCue", "beamLine"} else "alpha")
    channel = str(raw.get("channel") or _vfx_infer_channel(renderer_kind, event))
    importance = str(raw.get("importance") or _vfx_default_importance(event, renderer_kind))
    lane = str(raw.get("lane") or _vfx_infer_lane({**raw, "rendererKind": renderer_kind, "rendererKind": renderer_kind, "event": event, "importance": importance, "channel": channel}))
    emission_mode = str(raw.get("emissionMode") or _vfx_infer_emission_mode(renderer_kind, event))
    particle_system_id = _vfx_resolve_particle_system_id(raw, renderer_kind, event, channel, blend, emission_mode)
    baked_commands = _vfx_bake_slot_commands(raw, slot_seed, renderer_kind, event, backend, density, duration, alpha, scale, spread)
    baked_meta = _vfx_baked_clip_meta(seed, slot_index, renderer_kind, event, baked_commands)
    return {
        "event": event,
        "eventGroup": event_group,
        "stage": _vfx_event_stage(event, renderer_kind),
        "source": str(raw.get("source") or "recipe"),
        "backend": backend,
        "rendererKind": renderer_kind,
        "rendererKind": renderer_kind,
        "textureRole": str(raw.get("textureRole") or "projectile"),
        "particleRole": str(raw.get("particleRole") or raw.get("textureRole") or "child"),
        "anchor": str(raw.get("anchor") or _vfx_default_anchor(event, renderer_kind)),
        "blend": blend,
        "layer": str(raw.get("layer") or "BeforeProjectiles"),
        "channel": channel,
        "lane": lane,
        "emissionMode": emission_mode,
        "particleSystemId": particle_system_id,
        "fadeIn": round(max(0.0, min(0.95, _vfx_lerp_range(slot_seed, "fadeIn", raw.get("fadeIn"), 0.15))), 3),
        "fadeOut": round(max(0.0, min(0.95, _vfx_lerp_range(slot_seed, "fadeOut", raw.get("fadeOut"), 0.35))), 3),
        "curve": str(raw.get("curve") if raw.get("curve") in {"smooth", "linear", "sharp"} else "smooth"),
        "slotSeed": int(_vfx_seed_int(seed, "slot", slot_index, renderer, event)),
        "variant": int(_vfx_pick(slot_seed, "variant", variants, 0) or 0),
        "startTick": max(0, min(600, start_tick)),
        "repeatEvery": max(0, min(600, repeat_every)),
        "scale": round(max(0.05, min(8.0, scale * visual_power)), 3),
        "density": round(max(0.0, min(1.0, density)), 3),
        "duration": max(1, min(240, duration)),
        "alpha": round(max(0.0, min(1.0, alpha)), 3),
        "spread": round(max(0.0, min(3.0, spread)), 3),
        "jitter": round(max(0.0, min(2.0, jitter)), 3),
        "phaseOffset": round(max(-2.0, min(2.0, phase_offset)), 3),
        "budgetWeight": round(max(0.05, min(8.0, budget_weight)), 3),
        "importance": str(raw.get("importance") or _vfx_default_importance(event, renderer)),
        "visualCost": round(max(0.0, min(1.0, _vfx_lerp_range(slot_seed, "visualCost", raw.get("visualCost"), _vfx_default_visual_cost(renderer, density)))), 3),
        "signatureWeight": round(max(0.0, min(1.0, _vfx_lerp_range(slot_seed, "signatureWeight", raw.get("signatureWeight"), _vfx_default_signature_weight(event, renderer)))), 3),
        "bakedClipId": baked_meta["bakedClipId"],
        "bakedClipHash": baked_meta["bakedClipHash"],
        "bakedCommandCount": baked_meta["bakedCommandCount"],
        "bakedCommands": baked_commands,
    }

def _vfx_family_key(slot: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _vfx_event_group(slot.get("event")),
        str(slot.get("channel") or _vfx_infer_channel(slot.get("rendererKind"), slot.get("event"))),
        _vfx_renderer_family(slot.get("rendererKind")),
    )

def _vfx_slot_similarity_key(slot: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _vfx_event_group(slot.get("event")),
        str(slot.get("channel") or _vfx_infer_channel(slot.get("rendererKind"), slot.get("event"))),
        str(slot.get("lane") or _vfx_infer_lane(slot)),
        _vfx_renderer_family(slot.get("rendererKind")),
    )

def _vfx_demote_blended_raw_slot(raw: dict[str, Any], source_recipe_id: str, seed: int, order: int) -> dict[str, Any]:
    """Turn a runner-up recipe slot into support/accent material.

    This is the compromise between one selected recipe and JSON swamp: we borrow only
    secondary visual jobs from runner-up recipes, then let normal arbitration/budgeting
    keep or discard them. Gameplay is untouched.
    """
    slot = dict(raw)
    slot["source"] = f"blend:{source_recipe_id}"
    slot["importance"] = "accent" if order % 2 else "secondary"
    slot["lane"] = "accent" if order % 2 else "support"
    slot["signatureWeight"] = [0.22, 0.56]
    slot["visualCost"] = [0.12, 0.46]
    # Slightly reduce density so blended material reads as support, not a second main effect.
    if "density" in slot:
        d = slot["density"]
        if isinstance(d, list) and len(d) == 2:
            slot["density"] = [max(0.03, float(d[0]) * 0.55), max(0.08, float(d[1]) * 0.72)]
        else:
            try: slot["density"] = max(0.04, min(0.55, float(d) * 0.70))
            except Exception: pass
    else:
        slot["density"] = [0.10, 0.38]
    if "alpha" not in slot:
        slot["alpha"] = [0.22, 0.62]
    if "duration" in slot:
        dur = slot["duration"]
        if isinstance(dur, list) and len(dur) == 2:
            slot["duration"] = [max(2, int(float(dur[0]) * 0.75)), max(3, int(float(dur[1]) * 0.88))]
    slot["phaseOffset"] = [_vfx_unit(seed, f"blend_phase_{order}") * 0.35, _vfx_unit(seed, f"blend_phase_b_{order}") * 0.65]
    return slot

def _vfx_blend_runner_up_slots(top: list[tuple[float, dict[str, Any], list[str]]], selected_id: str, seed: int, base_raw_slots: list[dict[str, Any]], magnitude_class: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not VFX_RECIPE_BLEND_ENABLED or not top or VFX_PROCEDURAL_MAX_EXTRA_SLOTS <= 0:
        return [], []
    max_slots = max(0, min(VFX_PROCEDURAL_MAX_EXTRA_SLOTS, 2 if magnitude_class in {"tiny", "small"} else 4 if magnitude_class == "normal" else 5))
    if max_slots <= 0:
        return [], []
    used = {_vfx_slot_similarity_key(x) for x in base_raw_slots if isinstance(x, dict)}
    extras: list[dict[str, Any]] = []
    debug: list[dict[str, Any]] = []
    order = 0
    for score, recipe, reasons in top[1:max(1, VFX_PROCEDURAL_BLEND_CANDIDATES) + 1]:
        rid = str(recipe.get("id") or "")
        if rid == selected_id:
            continue
        raw_slots = [x for x in (recipe.get("slots") or []) if isinstance(x, dict)]
        # Prefer non-core hit particles / support motion / ambient layers from runner-up recipes.
        raw_slots.sort(key=lambda x: (_vfx_slot_score({**x, "channel": _vfx_infer_channel(x.get("rendererKind"), x.get("event")), "lane": _vfx_infer_lane(x)}), str(x.get("rendererKind"))), reverse=True)
        for raw in raw_slots:
            channel = _vfx_infer_channel(raw.get("rendererKind"), raw.get("event"))
            event_group = _vfx_event_group(raw.get("event"))
            if channel in {"sound", "light"}:
                continue
            # Do not borrow second primary shape from another recipe unless the item is large/signature.
            if magnitude_class not in {"large", "signature"} and channel in {"impactShape", "motionTrail"} and event_group in {"hit", "live"}:
                if len(extras) >= 1:
                    continue
            candidate = _vfx_demote_blended_raw_slot(raw, rid, seed, order)
            key = _vfx_slot_similarity_key(candidate)
            if key in used:
                continue
            used.add(key)
            extras.append(candidate)
            debug.append({"recipeId": rid, "rendererKind": candidate.get("rendererKind"), "event": candidate.get("event"), "channel": channel, "score": round(float(score), 3)})
            order += 1
            if len(extras) >= max_slots:
                return extras, debug
    return extras, debug

def _vfx_procedural_raw_slot_pool(pattern: str, roles: set[str], motif: dict[str, Any], magnitude_class: str, seed: int) -> list[dict[str, Any]]:
    """Small procedural composer: not a semantic parser, not a full recipe selector.

    It only adds generic structural layers that are safe for attackPattern/role availability:
    streaks, secondary rings, motes, decay, beam accent, field pulse. Actual art still comes
    from generated role sprites and the selected recipe.
    """
    large = magnitude_class in {"large", "signature"}
    signature = magnitude_class == "signature"
    pattern_l = str(pattern or "").lower()
    out: list[dict[str, Any]] = []
    if "projectile" in roles:
        if any(x in pattern_l for x in ["slash", "beam_slash"]):
            out.append({"event": "active", "rendererKind": "historyRibbon", "textureRole": "projectile", "channel": "motionTrail", "lane": "support", "importance": "secondary", "density": [0.22, 0.48], "scale": [0.75, 1.35], "alpha": [0.26, 0.58], "duration": [10, 28], "spread": [0.45, 1.05], "source": "procedural:slash_support_ribbon"})
            out.append({"event": "active", "rendererKind": "beamLine", "textureRole": "projectile", "channel": "motionTrail", "lane": "accent", "importance": "accent", "density": [0.10, 0.34], "scale": [0.65, 1.20], "alpha": [0.18, 0.46], "duration": [5, 16], "spread": [0.25, 0.75], "source": "procedural:slash_light_streak"})
        elif "beam" in pattern_l or "laser" in pattern_l:
            out.append({"event": "active", "rendererKind": "beamLine", "textureRole": "projectile", "channel": "motionTrail", "lane": "primary", "importance": "core", "density": [0.30, 0.72], "scale": [1.0, 1.85], "alpha": [0.45, 0.85], "duration": [8, 28], "spread": [0.25, 0.90], "source": "procedural:beam_core_line"})
            out.append({"event": "active", "rendererKind": "childMotes", "rendererKind": "childMotes", "textureRole": "child", "particleRole": "child", "channel": "ambientParticles", "lane": "accent", "importance": "accent", "emissionMode": "wake", "density": [0.12, 0.34], "scale": [0.5, 1.1], "alpha": [0.22, 0.52], "duration": [8, 20], "repeatEvery": [2, 5], "source": "procedural:beam_side_sparks"})
        else:
            out.append({"event": "travel", "rendererKind": "spriteStampTrail", "textureRole": "projectile", "channel": "motionTrail", "lane": "support", "importance": "secondary", "density": [0.18, 0.46], "scale": [0.65, 1.25], "alpha": [0.22, 0.55], "duration": [8, 22], "source": "procedural:travel_stamp_support"})
    if "impact" in roles:
        out.append({"event": "hit", "rendererKind": "impactRing", "textureRole": "impact", "particleRole": "child", "channel": "impactShape", "lane": "support", "importance": "secondary", "density": [0.18, 0.50], "scale": [0.9, 2.2 if large else 1.55], "alpha": [0.30, 0.72], "duration": [6, 18], "spread": [0.35, 1.15], "source": "procedural:impact_secondary_ring"})
        out.append({"event": "hit", "rendererKind": "impactSprite", "rendererKind": "impactSprite", "textureRole": "impact", "particleRole": "child", "channel": "impactShape", "lane": "accent", "importance": "accent", "density": [0.08, 0.24], "scale": [0.85, 1.85], "alpha": [0.25, 0.68], "duration": [4, 12], "source": "procedural:impact_snap_flash"})
    if "child" in roles or "impact" in roles:
        out.append({"event": "hit", "rendererKind": "childMotes", "rendererKind": "childMotes", "textureRole": "impact", "particleRole": "child", "channel": "impactParticles", "lane": "accent", "importance": "accent", "emissionMode": "cone", "density": [0.18, 0.58 if large else 0.38], "scale": [0.45, 1.15], "alpha": [0.28, 0.72], "duration": [10, 32], "spread": [0.55, 1.65], "source": "procedural:impact_child_motes"})
        if signature:
            out.append({"event": "kill", "rendererKind": "childMotes", "rendererKind": "childMotes", "textureRole": "impact", "particleRole": "child", "channel": "decaySmoke", "lane": "accent", "importance": "accent", "emissionMode": "spiral", "density": [0.14, 0.42], "scale": [0.65, 1.45], "alpha": [0.20, 0.54], "duration": [18, 52], "spread": [0.75, 1.85], "source": "procedural:signature_spiral_decay"})
    if "field" in roles or "field" in pattern_l:
        out.append({"event": "tick", "rendererKind": "fieldPulse", "textureRole": "field", "particleRole": "child", "channel": "coreGlow", "lane": "primary", "importance": "core", "density": [0.22, 0.60], "scale": [0.95, 2.25], "alpha": [0.28, 0.72], "duration": [20, 60], "spread": [0.55, 1.35], "source": "procedural:field_core_pulse"})
    # A tiny light cue makes layered recipes read cleaner, but only as cue and only for large-ish effects.
    if large:
        out.append({"event": "hit", "rendererKind": "lightCue", "textureRole": "impact", "channel": "light", "lane": "cue", "importance": "accent", "density": [0.10, 0.25], "scale": [0.8, 1.6], "alpha": [0.35, 0.8], "duration": [4, 10], "source": "procedural:impact_light_cue"})
    return out

def _vfx_add_procedural_slots(base_raw_slots: list[dict[str, Any]], pattern: str, roles: set[str], motif: dict[str, Any], magnitude_class: str, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not VFX_PROCEDURAL_COMPOSE or VFX_PROCEDURAL_MAX_EXTRA_SLOTS <= 0:
        return [], []
    max_slots = max(0, min(VFX_PROCEDURAL_MAX_EXTRA_SLOTS, 1 if magnitude_class in {"tiny", "small"} else 3 if magnitude_class == "normal" else 5))
    if max_slots <= 0:
        return [], []
    base_keys = {_vfx_slot_similarity_key(x) for x in base_raw_slots if isinstance(x, dict)}
    pool = _vfx_procedural_raw_slot_pool(pattern, roles, motif, magnitude_class, seed)
    # Weighted but stable. Prefer different channels/lanes/families from existing base slots.
    scored: list[tuple[float, dict[str, Any]]] = []
    for idx, raw in enumerate(pool):
        key = _vfx_slot_similarity_key(raw)
        if key in base_keys:
            continue
        chance = VFX_PROCEDURAL_CHANCE
        u = _vfx_unit(seed, f"proc_chance_{idx}_{raw.get('rendererKind')}")
        if u > chance and magnitude_class not in {"large", "signature"}:
            continue
        score = _vfx_slot_score({**raw, "channel": raw.get("channel") or _vfx_infer_channel(raw.get("rendererKind"), raw.get("event")), "lane": raw.get("lane") or _vfx_infer_lane(raw)})
        # Stable jitter so the same item does not always use the same procedural accent.
        score += (_vfx_unit(seed, f"proc_score_{idx}") - 0.5) * 18.0
        scored.append((score, raw))
    scored.sort(key=lambda x: x[0], reverse=True)
    chosen: list[dict[str, Any]] = []
    debug: list[dict[str, Any]] = []
    used = set(base_keys)
    for score, raw in scored:
        key = _vfx_slot_similarity_key(raw)
        if key in used:
            continue
        used.add(key)
        chosen.append(raw)
        debug.append({"rendererKind": raw.get("rendererKind"), "event": raw.get("event"), "channel": raw.get("channel"), "lane": raw.get("lane"), "source": raw.get("source"), "score": round(score, 3)})
        if len(chosen) >= max_slots:
            break
    return chosen, debug

def _vfx_runtime_plan_direct_manifest(data: dict[str, Any], recipe_key_value: str, reroll_salt: Any = "") -> dict[str, Any] | None:
    if not VFX_RUNTIME_INTENT_FIRST:
        return None
    rp = data.get("runtimePlan") if isinstance(data.get("runtimePlan"), dict) else {}
    has_runtime_plan = isinstance(rp, dict) and bool(rp)
    calls = rp.get("engineCalls") if isinstance(rp.get("engineCalls"), list) else []
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    if not attack.get("enabled"):
        return None
    if has_runtime_plan and not calls:
        calls = []
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    vi = rp.get("visualIntent") if isinstance(rp.get("visualIntent"), dict) else {}
    power = float(attack.get("powerBudget") or data.get("gameplay", {}).get("powerBudget") or 1.0) if isinstance(data.get("gameplay"), dict) else float(attack.get("powerBudget") or 1.0)
    seed = _vfx_seed_int(recipe_key_value, data.get("id"), "runtime_intent", reroll_salt)
    effect = str(attack.get("effect") or "none").lower()
    onhit = str(attack.get("onHit") or "none").lower()
    split_count = int(float(attack.get("splitCount") or 0))
    trail_len = int(float(attack.get("trailLength") or 0))
    burst_cap = int(float(attack.get("burstDustCap") or 0))
    slots_raw: list[dict[str, Any]] = []
    authored_raw, authored_debug = _vfx_authored_cue_raw_slots(data)
    slots_raw.extend(authored_raw)
    # Travel slot: small by default; no parent-inherited beam/history ribbons.
    if trail_len > 0 and effect not in {"none", ""}:
        slots_raw.append({
            "event": "travel", "rendererKind": "projectileAfterimage", "textureRole": "projectile",
            "variants": [0, 1], "scale": [0.65, 1.05], "density": [0.10, 0.24], "duration": [5, min(18, max(6, trail_len))],
            "alpha": [0.18, 0.42], "stage": "loop", "backend": "Sprite", "anchor": "self", "blend": "alpha",
            "layer": "BeforeProjectiles", "budgetWeight": [0.45, 0.9], "source": "runtimePlan:travel"
        })
    # Hit feedback is a contact flash/chips/dust unless the LLM explicitly requested real child projectiles.
    if onhit not in {"none", ""} or burst_cap > 0 or str(vi.get("impact") or visual.get("impactVfx") or "").strip():
        slots_raw.append({
            "event": "hit", "rendererKind": "impactSprite", "rendererKind": "impactSprite", "textureRole": "impact",
            "variants": [0, 1], "scale": [0.85, min(1.75, 0.98 + power * 0.20)], "density": [0.10, 0.26], "duration": [6, 13],
            "alpha": [0.45, 0.86], "stage": "impact", "backend": "Sprite", "anchor": "hitPoint", "blend": "alpha",
            "layer": "BeforeProjectiles", "budgetWeight": [0.60, 1.05], "source": "runtimePlan:impact_readable_flash_v0.4.174"
        })
    if False and split_count > 0 and attack.get("maxChildProjectiles", 0):
        # v0.4.8: real gameplay children are visible by themselves. Do not duplicate them
        # with VFX childSpriteMotes, or 3 authored shards look like 9+ fragments on screen.
        pass
    # v0.4.3: runtimePlan presence is authoritative even if it requests no visible VFX.
    # Return an empty tiny manifest instead of falling back to legacy recipe roulette.
    effect_mag = 0.0 if not slots_raw else max(0.08, min(0.38 if power <= 1.8 else 0.48, 0.12 + power * 0.08 + split_count * 0.015))
    budget = {
        "renderQuality": VFX_RENDER_QUALITY, "quality": VFX_RENDER_QUALITY, "effectMagnitude": round(effect_mag, 3),
        "visualBudgetClass": "small" if effect_mag < 0.42 else "normal", "emergencyCap": True,
        "maxParticlesPerTick": min(VFX_EMERGENCY_MAX_PARTICLES_PER_TICK, 80),
        "maxParticlesTotal": min(VFX_EMERGENCY_MAX_PARTICLES_TOTAL, 1800),
        "maxDrawCalls": min(VFX_EMERGENCY_MAX_DRAW_CALLS, 90),
        "spawnRateMultiplier": 0.0 if effect_mag <= 0 else (0.65 if power <= 1.8 else 0.9),
        "enableSoftGlow": effect in {"star", "flame", "electric", "lunar", "holy", "shadow"},
        "enablePointSparks": effect not in {"none", "dust", "sand", "smoke"},
        "enablePersistentSmoke": False,
    }
    slots = [_vfx_compile_slot(slot, seed, i, power, effect_mag) for i, slot in enumerate(slots_raw)]
    slots = _vfx_arbitrate_slots(slots, str(budget.get("visualBudgetClass") or "small"))
    provenance = attack.get("runtimeAuthoringProvenance") if isinstance(attack.get("runtimeAuthoringProvenance"), dict) else {}
    effect_lineage = {
        "mode": "runtime_plan_direct",
        "gameplayChildren": provenance.get("gameplayChildren", {}),
        "pureVfx": provenance.get("pureVfx", {}),
        "fieldSources": provenance.get("fieldSources", {}),
        "note": "VFX slots here are visual execution of runtimePlan intent; real damaging children are only those reported under gameplayChildren.",
    }
    manifest = {
        "schema": "infini.vfx.hybrid.v14",
        "recipeId": "runtime_intent_v0_4_8",
        "playbackMode": "Hybrid",
        "seed": seed,
        "confidence": 0.88,
        "effectMagnitude": round(effect_mag, 3),
        "visualBudgetClass": budget["visualBudgetClass"],
        "motif": _vfx_motif_from_data(data, _vfx_words(" ".join(str(x or "") for x in [data.get("name"), visual.get("vfxIntent"), attack.get("vfxIntent"), vi.get("vfxIntent")])) , str(attack.get("pattern") or "thrown_simple")),
        "overlayPolicy": "LocalOnly",
        "budget": budget,
        "slots": slots,
        "debug": {
            "composition": {
                "mode": "runtime_plan_direct_authored_cues" if authored_raw else "runtime_plan_direct", "baseRecipeId": "runtime_intent_v0_4_8",
                "preArbitrationSlotCount": len(slots_raw), "postArbitrationSlotCount": len(slots),
                "authoredCueSlots": authored_debug,
                "runtimePlanFunctions": [str(c.get("fn") or "") for c in calls if isinstance(c, dict)],
            },
            "pattern": str(attack.get("pattern") or attack.get("attackPattern") or ""),
            "roles": sorted(_vfx_available_roles(data)),
            "selectedScore": 1000.0,
            "selectedReasons": ["runtimePlan.engineCalls present", "legacy recipe selector bypassed", "authored visual cues compiled" if authored_raw else ("empty runtime VFX is allowed" if not slots_raw else "runtime VFX slots compiled")],
            "effectLineage": effect_lineage,
            "topCandidates": [], "wordProbe": [],
            "rerollSalt": str(reroll_salt or data.get("recipeMeta", {}).get("vfxRerollSalt", "") or ""),
        },
    }
    return manifest

def _vfx_authored_cue_event(raw: Any) -> str:
    e = str(raw or "").strip()
    return {
        "while_held": "active",
        "while_equipped": "active",
        "on_use": "active",
        "on_alt_use": "active",
        "on_projectile_impact": "hit",
        "on_hit": "hit",
    }.get(e, e if e in {"travel", "active", "tick", "hit", "kill", "expire"} else "active")

def _vfx_authored_cue_raw_slots(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert model-authored visual_effect_cue contracts into raw VFX slots.

    This is intentionally a narrow visual-only bridge: it does not infer cues from prose
    and does not create gameplay. The model must author visual_effect_cue explicitly.
    """
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    kit = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
    raw_cues: list[Any] = []
    for source in (attack, kit, visual, data):
        cues = source.get("vfxCues") if isinstance(source, dict) else None
        if isinstance(cues, list):
            raw_cues.extend(cues)
    if not raw_cues:
        return [], []
    surface = vfx_director_surface()
    allowed_renderer = set(surface["rendererKind"])
    allowed_channel = set(surface["channel"])
    allowed_lane = set(surface["lane"])
    allowed_roles = set(surface["textureRole"])
    allowed_emission = set(surface["emissionMode"])
    allowed_particles = set(surface["particleSystemId"])
    out: list[dict[str, Any]] = []
    debug: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for idx, cue in enumerate(raw_cues[:10]):
        if not isinstance(cue, dict):
            continue
        ev = _vfx_authored_cue_event(cue.get("event"))
        renderer = str(cue.get("rendererKind") or "").strip()
        if renderer not in allowed_renderer:
            renderer = "impactRing" if ev in {"hit", "kill", "expire"} else "projectileAfterimage"
        channel = str(cue.get("channel") or "").strip()
        if channel not in allowed_channel:
            channel = "impactShape" if ev in {"hit", "kill", "expire"} else "motionTrail"
        lane = str(cue.get("lane") or "").strip()
        if lane not in allowed_lane:
            lane = "primary" if idx == 0 else "accent"
        texture_role = str(cue.get("textureRole") or "projectile").strip()
        if texture_role not in allowed_roles:
            texture_role = "projectile"
        particle_role = str(cue.get("particleRole") or texture_role).strip()
        if particle_role not in allowed_roles:
            particle_role = "child"
        emission = str(cue.get("emissionMode") or "").strip()
        if emission not in allowed_emission:
            emission = "ring" if channel in {"impactShape", "impactParticles"} else "wake"
        pid = str(cue.get("particleSystemId") or "").strip()
        if pid not in allowed_particles:
            pid = "pl:glow" if channel in {"coreGlow", "light"} else "pl:spark"
        key = (ev, renderer, channel, lane)
        if key in seen:
            continue
        seen.add(key)
        def n(name: str, fallback: float) -> Any:
            try:
                value = cue.get(name)
                return fallback if value in (None, "") else float(value)
            except Exception:
                return fallback
        slot = {
            "event": ev,
            "rendererKind": renderer,
            "rendererKind": renderer,
            "backend": "Auto",
            "textureRole": texture_role,
            "particleRole": particle_role,
            "anchor": str(cue.get("anchor") or ("hitPoint" if ev in {"hit", "kill", "expire"} else "self")),
            "channel": channel,
            "lane": lane,
            "emissionMode": emission,
            "blend": str(cue.get("blend") or ("additive" if channel in {"coreGlow", "light"} or renderer in {"beamLine", "lightCue"} else "alpha")),
            "particleSystemId": pid,
            "scale": max(0.15, min(5.0, n("scale", 1.0))),
            "density": max(0.0, min(1.0, n("density", 0.35))),
            "duration": int(max(3, min(120, round(n("duration", 16))))),
            "alpha": max(0.0, min(1.0, n("alpha", 0.65))),
            "spread": max(0.0, min(2.0, n("spread", 0.6))),
            "jitter": max(0.0, min(1.5, n("jitter", 0.25))),
            "startTick": int(max(0, min(120, round(n("startTick", 0))))),
            "repeatEvery": int(max(0, min(120, round(n("repeatEvery", 0))))),
            "importance": str(cue.get("importance") or ("core" if lane == "primary" else "accent")),
            "source": "authoredCue",
            "signatureWeight": 0.72 if lane == "primary" else 0.36,
            "visualCost": 0.22 if lane == "primary" else 0.12,
        }
        out.append(slot)
        debug.append({"event": ev, "rendererKind": renderer, "channel": channel, "lane": lane, "particleSystemId": pid, "note": str(cue.get("note") or "")[:80]})
    return out[:8], debug[:8]

__all__ = [
    "_vfx_baked_command_count",
    "_vfx_should_bake_slot",
    "_vfx_bake_slot_commands",
    "_vfx_baked_clip_meta",
    "_vfx_compile_slot",
    "_vfx_family_key",
    "_vfx_slot_similarity_key",
    "_vfx_demote_blended_raw_slot",
    "_vfx_blend_runner_up_slots",
    "_vfx_procedural_raw_slot_pool",
    "_vfx_add_procedural_slots",
    "_vfx_runtime_plan_direct_manifest",
    "_vfx_authored_cue_event",
    "_vfx_authored_cue_raw_slots",
]
