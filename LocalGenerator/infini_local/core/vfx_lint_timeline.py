from __future__ import annotations

from typing import Any

from infini_local.core.vfx_composition_primitives import (
    _vfx_default_backend,
    _vfx_event_stage,
    _vfx_infer_channel,
    _vfx_infer_emission_mode,
    _vfx_infer_lane,
)


# AGENT MAP: debug-only VFX lint/effect-stack/timeline helpers.
# Owns manifest linting, renderer/layer cost estimates and timeline previews;
# runtime manifest assembly stays in vfx_manifest/vfx_composition.
# Public callers use infini_local.core.vfx_manifest.

VFX_MAGNITUDE_CLASSES = {
    "tiny": {"range": [0.00, 0.22], "meaning": "barely magical / cheap / utility item", "expected": "core silhouette + small hit"},
    "small": {"range": [0.22, 0.42], "meaning": "minor generated effect", "expected": "short trail + readable hit"},
    "normal": {"range": [0.42, 0.66], "meaning": "default generated weapon VFX", "expected": "main trail + impact + light residue"},
    "large": {"range": [0.66, 0.86], "meaning": "rare/weird/high-power VFX", "expected": "layered trail + bigger impact + decay"},
    "signature": {"range": [0.86, 1.00], "meaning": "signature item effect", "expected": "full stack; emergency caps only"},
}

def _vfx_layer_kind_for_renderer(renderer: Any) -> str:
    r = str(renderer or "").lower()
    if "sound" in r:
        return "SoundCueLayer"
    if "light" in r:
        return "LightCueLayer"
    if "actor" in r or "playerghost" in r:
        return "ActorAfterimageLayer"
    if "ribbon" in r or "trail" in r or "beam" in r or "tip" in r or "history" in r:
        return "PrimitiveTrailLayer"
    if "afterimage" in r or "ghost" in r or "stamp" in r or "field" in r or "wavy" in r or "cloth" in r:
        return "SpriteGhostLayer"
    if "ambient" in r or "mote" in r or "spark" in r or "smoke" in r or "particle" in r or "burst" in r or "ring" in r:
        return "ParticleBurstLayer"
    return "ParticleEmitterLayer"

def _vfx_slot_cost_estimate(slot: dict[str, Any]) -> dict[str, Any]:
    density = float(slot.get("density") or 0.0)
    duration = int(float(slot.get("duration") or 1))
    weight = float(slot.get("budgetWeight") or 1.0)
    renderer = str(slot.get("rendererKind") or "")
    layer = _vfx_layer_kind_for_renderer(renderer)
    draw_calls = 0
    particles = 0
    if layer in {"PrimitiveTrailLayer", "SpriteGhostLayer", "ActorAfterimageLayer"}:
        draw_calls = max(1, int(round(1 + density * 12)))
    if layer in {"ParticleBurstLayer", "ParticleEmitterLayer"}:
        particles = max(1, int(round((2 + density * 28) * weight)))
    if layer == "LightCueLayer":
        draw_calls = 0
    if layer == "SoundCueLayer":
        draw_calls = 0
    baked = slot.get("bakedCommands") if isinstance(slot.get("bakedCommands"), list) else []
    return {
        "layerKind": layer,
        "estimatedDrawCalls": draw_calls,
        "estimatedParticles": particles + len(baked),
        "duration": duration,
        "bakedCommands": len(baked),
    }

def vfx_manifest_effect_stack(manifest: dict[str, Any]) -> dict[str, Any]:
    slots = [s for s in (manifest.get("slots") or []) if isinstance(s, dict)]
    rows = []
    stage_groups: dict[str, list[dict[str, Any]]] = {}
    backend_groups: dict[str, list[dict[str, Any]]] = {}
    kind_groups: dict[str, list[dict[str, Any]]] = {}
    total_draw = 0
    total_particles = 0
    for idx, slot in enumerate(slots):
        cost = _vfx_slot_cost_estimate(slot)
        stage = str(slot.get("stage") or _vfx_event_stage(slot.get("event"), slot.get("rendererKind")))
        backend = str(slot.get("backend") or _vfx_default_backend(slot.get("event"), slot.get("rendererKind")))
        row = {
            "index": idx,
            "event": slot.get("event"),
            "stage": stage,
            "backend": backend,
            "rendererKind": slot.get("rendererKind"),
            "layerKind": cost["layerKind"],
            "textureRole": slot.get("textureRole"),
            "particleRole": slot.get("particleRole"),
            "duration": slot.get("duration"),
            "density": slot.get("density"),
            "scale": slot.get("scale"),
            "estimatedDrawCalls": cost["estimatedDrawCalls"],
            "estimatedParticles": cost["estimatedParticles"],
            "bakedCommands": cost["bakedCommands"],
            "minQuality": slot.get("minQuality", "Low"),
        }
        rows.append(row)
        stage_groups.setdefault(stage, []).append(row)
        backend_groups.setdefault(backend, []).append(row)
        kind_groups.setdefault(cost["layerKind"], []).append(row)
        total_draw += int(cost["estimatedDrawCalls"])
        total_particles += int(cost["estimatedParticles"])
    return {
        "schema": "infini.vfx.effect_stack.v0",
        "recipeId": manifest.get("recipeId"),
        "manifestSchema": manifest.get("schema"),
        "playbackMode": manifest.get("playbackMode"),
        "slotCount": len(rows),
        "estimatedDrawCalls": total_draw,
        "estimatedParticles": total_particles,
        "byStage": {k: len(v) for k, v in stage_groups.items()},
        "byBackend": {k: len(v) for k, v in backend_groups.items()},
        "byLayerKind": {k: len(v) for k, v in kind_groups.items()},
        "layers": rows,
    }

VFX_KNOWN_RENDERERS = {
    "projectileAfterimage", "spriteStampTrail", "historyRibbon", "tipTrail", "ghostArc", "wavyStrip",
    "beamLine", "fieldPulse", "orbitingMotes", "actorAfterimage", "impactRing", "impactSprite",
    "childMotes", "lightCue", "soundCue",
}

VFX_KNOWN_EVENTS = {
    "travel", "active", "tick", "hit", "kill", "expire",
    "while_held", "while_equipped", "on_use", "on_alt_use",
}

VFX_KNOWN_BACKENDS = {"auto", "baked", "realtime", "primitive", "sprite", "particle", "hybrid"}

VFX_KNOWN_ROLES = {"projectile", "impact", "child", "particle", "mote", "field", "trail", "self"}

VFX_KNOWN_CHANNELS = {"motionTrail", "coreGlow", "ambientParticles", "impactShape", "impactParticles", "decaySmoke", "light", "sound"}

VFX_KNOWN_LANES = {"auto", "primary", "support", "accent", "ornament", "cue"}

VFX_KNOWN_EMISSION_MODES = {"auto", "wake", "orbit", "residue", "burst", "cone", "ring", "spiral", "point"}

def _vfx_slot_value_range_ok(value: Any, name: str, lo: float, hi: float) -> list[str]:
    issues: list[str] = []
    if isinstance(value, list):
        if len(value) != 2:
            issues.append(f"{name}: range list should have 2 values")
        vals = value[:2]
    else:
        vals = [value]
    for v in vals:
        try:
            f = float(v)
            if f < lo or f > hi:
                issues.append(f"{name}: {f} outside recommended {lo}..{hi}")
        except Exception:
            issues.append(f"{name}: non-numeric value {v!r}")
    return issues

def _vfx_lint_slot(slot: dict[str, Any], idx: int, recipe_id: str = "") -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    renderer = str(slot.get("rendererKind") or "").strip()
    event = str(slot.get("event") or "").strip().lower()
    backend = str(slot.get("backend") or _vfx_default_backend(event, renderer)).strip().lower()
    texture_role = str(slot.get("textureRole") or "projectile").strip().lower()
    particle_role = str(slot.get("particleRole") or "").strip().lower()
    if not renderer:
        errors.append("missing renderer")
    elif renderer not in VFX_KNOWN_RENDERERS:
        errors.append(f"unknown renderer '{renderer}'")
    if event not in VFX_KNOWN_EVENTS:
        errors.append(f"unknown event '{event}'")
    if backend not in VFX_KNOWN_BACKENDS:
        warnings.append(f"unknown backend '{backend}'")
    if texture_role and texture_role not in VFX_KNOWN_ROLES:
        warnings.append(f"unusual textureRole '{texture_role}'")
    if particle_role and particle_role not in VFX_KNOWN_ROLES:
        warnings.append(f"unusual particleRole '{particle_role}'")
    channel = slot.get("channel") or _vfx_infer_channel(renderer, event)
    if channel not in VFX_KNOWN_CHANNELS:
        warnings.append(f"unknown channel '{channel}'")
    lane = str(slot.get("lane") or _vfx_infer_lane(slot))
    if lane not in VFX_KNOWN_LANES:
        warnings.append(f"unknown lane '{lane}'")
    emission_mode = str(slot.get("emissionMode") or _vfx_infer_emission_mode(renderer, event))
    if emission_mode not in VFX_KNOWN_EMISSION_MODES:
        warnings.append(f"unknown emissionMode '{emission_mode}'")
    # minQuality/quality is deprecated in v0.3.26, but old macro data may still carry it.
    # Linter stays quiet so legacy recipes do not drown real errors.
    importance = str(slot.get("importance") or "").strip().lower()
    if importance and importance not in {"core", "secondary", "accent", "luxury"}:
        warnings.append(f"unknown importance '{importance}'")
    for name, lo, hi in [("visualCost", 0.0, 1.0), ("signatureWeight", 0.0, 1.0), ("fadeIn", 0.0, 0.95), ("fadeOut", 0.0, 0.95)]:
        if name in slot:
            warnings.extend(_vfx_slot_value_range_ok(slot.get(name), name, lo, hi))
    for name, lo, hi in [("scale", 0.05, 8.0), ("density", 0.0, 1.0), ("alpha", 0.0, 1.0), ("spread", 0.0, 3.0), ("jitter", 0.0, 2.0), ("budgetWeight", 0.05, 8.0)]:
        if name in slot:
            warnings.extend(_vfx_slot_value_range_ok(slot.get(name), name, lo, hi))
    if "duration" in slot:
        warnings.extend(_vfx_slot_value_range_ok(slot.get("duration"), "duration", 1, 240))
    baked = slot.get("bakedCommands") if isinstance(slot.get("bakedCommands"), list) else []
    if baked and backend in {"realtime", "primitive", "sprite"}:
        warnings.append("slot has bakedCommands but backend is realtime/primitive/sprite")
    if len(baked) > 180:
        warnings.append(f"large bakedCommands list: {len(baked)}")
    for j, cmd in enumerate(baked[:220]):
        if not isinstance(cmd, dict):
            errors.append(f"bakedCommands[{j}] is not an object")
            continue
        for n in ["tick", "localX", "localY", "velocityX", "velocityY", "scaleX", "scaleY", "lifespan", "alpha"]:
            if n not in cmd:
                continue
            # keep broad ranges matching C# Normalize.
            ranges = {
                "tick": (0, 600), "localX": (-8, 8), "localY": (-8, 8),
                "velocityX": (-12, 12), "velocityY": (-12, 12), "scaleX": (0.03, 8),
                "scaleY": (0.03, 8), "lifespan": (1, 240), "alpha": (0, 1),
            }
            lo, hi = ranges[n]
            try:
                f = float(cmd.get(n))
                if f < lo or f > hi:
                    warnings.append(f"bakedCommands[{j}].{n}={f} outside {lo}..{hi}")
            except Exception:
                warnings.append(f"bakedCommands[{j}].{n} non-numeric")
    return {"index": idx, "rendererKind": renderer, "event": event, "backend": backend, "errors": errors, "warnings": warnings}

def _vfx_lint_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    rid = str(recipe.get("id") or "")
    errors: list[str] = []
    warnings: list[str] = []
    if not rid:
        errors.append("missing recipe id")
    patterns = recipe.get("compatiblePatterns") or []
    if not isinstance(patterns, list) or not patterns:
        warnings.append("missing compatiblePatterns")
    slots = recipe.get("slots") or []
    if not isinstance(slots, list) or not slots:
        errors.append("recipe has no slots")
        slots = []
    if len(slots) > 9:
        warnings.append(f"recipe has many slots: {len(slots)}")
    slot_reports = []
    for i, slot in enumerate(slots):
        if not isinstance(slot, dict):
            slot_reports.append({"index": i, "errors": ["slot is not object"], "warnings": []})
            continue
        rep = _vfx_lint_slot(slot, i, rid)
        slot_reports.append(rep)
        errors.extend([f"slot[{i}]: {x}" for x in rep["errors"]])
        warnings.extend([f"slot[{i}]: {x}" for x in rep["warnings"]])
    return {"id": rid, "ok": not errors, "errors": errors, "warnings": warnings, "slotReports": slot_reports}



def _vfx_timeline_from_manifest(manifest: dict[str, Any], max_ticks: int = 180) -> dict[str, Any]:
    """Build a compact per-tick timeline preview from a frozen manifest.

    This is a debug/authoring helper, not runtime logic. It makes baked/realtime
    stage problems visible without opening the game.
    """
    slots = [s for s in (manifest.get("slots") or []) if isinstance(s, dict)]
    frames: dict[int, list[dict[str, Any]]] = {}
    max_seen = 0
    for idx, slot in enumerate(slots):
        event = str(slot.get("event") or "tick")
        stage = str(slot.get("stage") or _vfx_event_stage(event, slot.get("rendererKind")))
        renderer = str(slot.get("rendererKind") or "")
        start = max(0, int(float(slot.get("startTick") or 0)))
        duration = max(1, int(float(slot.get("duration") or 1)))
        repeat = max(0, int(float(slot.get("repeatEvery") or 0)))
        backend = str(slot.get("backend") or "Auto")
        min_quality = str(slot.get("minQuality") or "Low")
        # Realtime/live slots are sampled at start/repeat ticks so authors can see they exist.
        if event.lower() in {"tick", "travel", "active", "slash", "beam", "loop", "windup", "spawn"}:
            ticks = [start]
            if repeat > 0:
                ticks = list(range(start, min(max_ticks, start + duration), repeat))[:32]
            elif duration > 1:
                ticks = sorted({start, start + duration // 2, start + duration - 1})
            for tick in ticks:
                max_seen = max(max_seen, tick)
                frames.setdefault(tick, []).append({
                    "slot": idx,
                    "kind": "sample",
                    "event": event,
                    "stage": stage,
                    "rendererKind": renderer,
                    "backend": backend,
                    "minQuality": min_quality,
                })
        cmds = slot.get("bakedCommands") if isinstance(slot.get("bakedCommands"), list) else []
        for cidx, cmd in enumerate(cmds):
            if not isinstance(cmd, dict):
                continue
            tick = start + max(0, int(float(cmd.get("tick") or 0)))
            if tick > max_ticks:
                continue
            max_seen = max(max_seen, tick)
            frames.setdefault(tick, []).append({
                "slot": idx,
                "cmd": cidx,
                "kind": "baked",
                "event": event,
                "stage": stage,
                "rendererKind": renderer,
                "backend": backend,
                "particleSystemId": cmd.get("particleSystemId", "dust"),
                "alpha": cmd.get("alpha"),
                "lifespan": cmd.get("lifespan"),
                "minQuality": min_quality,
            })
    compact = [{"tick": tick, "events": frames[tick]} for tick in sorted(frames.keys())[:max_ticks]]
    return {
        "schema": "infini.vfx.timeline_preview.v0",
        "recipeId": manifest.get("recipeId"),
        "manifestSchema": manifest.get("schema"),
        "playbackMode": manifest.get("playbackMode"),
        "durationEstimate": max_seen + 1,
        "frameCount": len(compact),
        "eventsTotal": sum(len(x["events"]) for x in compact),
        "frames": compact,
    }

__all__ = [
    "VFX_MAGNITUDE_CLASSES",
    "VFX_KNOWN_RENDERERS",
    "VFX_KNOWN_EVENTS",
    "VFX_KNOWN_BACKENDS",
    "VFX_KNOWN_ROLES",
    "VFX_KNOWN_CHANNELS",
    "VFX_KNOWN_LANES",
    "VFX_KNOWN_EMISSION_MODES",
    "_vfx_layer_kind_for_renderer",
    "_vfx_slot_cost_estimate",
    "vfx_manifest_effect_stack",
    "_vfx_slot_value_range_ok",
    "_vfx_lint_slot",
    "_vfx_lint_recipe",
    "_vfx_timeline_from_manifest",
]
