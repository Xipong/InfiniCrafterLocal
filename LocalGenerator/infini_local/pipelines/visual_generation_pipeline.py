from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import queue
import random
import re
import shlex
import subprocess
import time
import traceback
from pathlib import Path
from typing import Any

from infini_local.core.env_utils import env_bool, env_float, env_int, env_str, env_first, env_path
from urllib import request as urlrequest
from urllib import error as urlerror
from urllib.parse import urlencode


def attach_visual(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any]) -> dict[str, Any]:
    visual = data.setdefault("visual", {})
    tags = set(data.get("tags", [])) | tags_of(a) | tags_of(b)
    anchors = visual.get("requiredAnchors") or required_anchors_from(ca, cb, tags)
    visual["requiredAnchors"] = list(dict.fromkeys(anchors))[:10]
    visual["palette"] = visual.get("palette") or palette_from(tags)
    visual["style"] = "terraria_item_sprite"
    stage = stage_profile_for(a, b, tags)
    size = size_profile_for(str(data.get("name", "generated item")), tags, data.get("gameplay", {}).get("kind") or data.get("category") or "generic", stage)
    visual.setdefault("preferredCanvasSize", size["preferredCanvasSize"])
    visual.setdefault("inventoryScale", size["inventoryScale"])
    visual.setdefault("worldScale", size["worldScale"])
    visual.setdefault("drawOffsetX", 0)
    visual.setdefault("drawOffsetY", 0)
    visual["negativePrompt"] = asset_negative_prompt("item")
    authored_prompt = str(visual.get("imagePrompt") or "").strip()
    if authored_prompt and is_llm_planner(data):
        visual["imagePrompt"] = sanitize_image_prompt_background(authored_prompt)
    else:
        visual["imagePrompt"] = sanitize_image_prompt_background(build_image_prompt(data, visual))
        if isinstance(data.get("presentationGenome"), dict):
            pg = data["presentationGenome"]
            visual["imagePrompt"] += ", coherent with " + str((pg.get("heldSprite") or {}).get("silhouette", "item")) + " and " + str((pg.get("attackVisual") or {}).get("effect", "neutral")) + " attack visuals"
    visual.setdefault("spriteStatus", "prompt_only")
    return data

def build_image_prompt(data: dict[str, Any], visual: dict[str, Any]) -> str:
    anchors = [str(a) for a in visual.get("requiredAnchors", []) if str(a).strip()]
    palette = [str(c).replace("_", " ") for c in visual.get("palette", []) if str(c).strip()]
    name = data.get("name", "generated item")
    canvas = int(visual.get("preferredCanvasSize") or 32)
    large_hint = "slightly oversized sprite allowed" if canvas >= 64 else "standard item sprite scale"
    parts = [
        "pixel art game item icon",
        "Terraria-like item sprite",
        sprite_background_positive_clause(),
        "centered single object",
        "simple readable silhouette",
        "limited palette",
        large_hint,
        role_contract_prompt_clause("item", canvas),
        f"target canvas feeling: {canvas}x{canvas}",
        f"item concept: {name}",
    ]
    if anchors:
        parts.append("must visibly include: " + ", ".join(anchors[:8]))
    if palette:
        parts.append("palette: " + ", ".join(palette[:6]))
    parts.append("no scene, no character, no text")
    return ", ".join(parts)

def maybe_generate_sprite(data: dict[str, Any]) -> dict[str, Any]:
    visual = data.setdefault("visual", {})
    visual.setdefault("authoringPolicy", "ai_primary_non_procedural")
    base_prompt = normalize_asset_prompt(data, "item", str(visual.get("imagePrompt") or ""), int(visual.get("preferredCanvasSize") or 32))
    visual["imagePrompt"] = base_prompt
    visual["finalItemPrompt"] = base_prompt[:1800]
    if IMAGE_BACKEND == "off":
        visual["spriteStatus"] = "prompt_only"
        return data
    canvas = int(visual.get("preferredCanvasSize") or 32)
    negative = str(visual.get("negativePrompt") or asset_negative_prompt("item"))
    asset_id = str(data.get("id") or "sprite")
    attempts: list[dict[str, Any]] = []
    max_attempts = max(1, int(SPRITE_RETRIES) + 1)
    last_path = ""
    last_raw_path = ""
    last_score = 0.0
    last_validation: dict[str, Any] | None = None
    for attempt in range(max_attempts):
        attempt_id = asset_id if attempt == 0 else f"{asset_id}_retry{attempt}"
        attempt_prompt = base_prompt if attempt == 0 else build_retry_prompt_from_validation(base_prompt, last_validation or {}, "item", attempt, canvas)
        trace_event("prompt", "IMAGE:item", f"{IMAGE_BACKEND} item prompt attempt {attempt}", {
            "assetId": asset_id, "attemptId": attempt_id, "attempt": attempt, "role": "item",
            "backend": IMAGE_BACKEND, "canvas": canvas, "spriteRetries": SPRITE_RETRIES,
        }, prompt=attempt_prompt, negative=negative)
        try:
            if IMAGE_BACKEND == "a1111":
                variants = generate_a1111(attempt_prompt, negative, attempt_id, canvas)
            elif IMAGE_BACKEND == "comfyui":
                variants = generate_comfyui(attempt_prompt, negative, attempt_id)
            elif IMAGE_BACKEND in {"sdcpp", "stablediffusioncpp", "stable-diffusion.cpp", "stable_diffusion_cpp"}:
                variants = generate_sdcpp(attempt_prompt, negative, attempt_id, canvas)
            elif IMAGE_BACKEND in {"image_api", "api_image", "openai_image", "openai_images", "openai_compat_image"}:
                variants = generate_image_api(attempt_prompt, negative, attempt_id, canvas)
            else:
                variants = [] if VISUAL_STRICT_AI_AUTHORSHIP else [visual_asset_pipeline.generate_procedural_sprite(data, variant=i, sprite_dir=SPRITE_DIR, image_cls=Image, image_draw_cls=ImageDraw) for i in range(max(1, GENERATE_VARIANTS))]
            variants = [p for p in variants if p and Path(p).exists()]
            if not variants:
                attempts.append({"attempt": attempt, "ok": False, "status": "no_raw_image"})
                trace_event("step", "IMAGE:item", "no raw image returned", {"assetId": asset_id, "attempt": attempt, "backend": IMAGE_BACKEND})
                continue
            best, score = pick_best_sprite(variants, "item", canvas)
            raw_best = best
            final_path = postprocess_sprite(best, attempt_id, canvas, "item")
            validation = validate_processed_sprite(final_path, "item")
            attempts.append({"attempt": attempt, "raw": raw_best, "final": final_path, "score": score, "validation": validation})
            last_path = final_path
            last_raw_path = raw_best
            last_score = float(score)
            last_validation = validation if isinstance(validation, dict) else None
            if validation.get("ok") or not sprite_validation_fatal(validation):
                if attempt != 0:
                    canonical = SPRITE_DIR / f"{data.get('id', 'sprite')}.png"
                    try:
                        import shutil
                        shutil.copyfile(final_path, canonical)
                        final_path = str(canonical)
                    except Exception:
                        pass
                visual["spritePath"] = str(Path(final_path).resolve())
                visual["spriteRawPath"] = str(Path(raw_best).resolve())
                visual["spriteStatus"] = sprite_status_from_raw_path(raw_best, IMAGE_BACKEND, invalid=not bool(validation.get("ok")))
                visual["visualJudgeScore"] = round(last_score, 3)
                visual["spriteUrl"] = f"/sprite/{Path(final_path).name}"
                attach_visual_soul_from_sprite(data, final_path, validation=validation, score=last_score)
                if not validation.get("ok"):
                    data.setdefault("debug", {})["itemSpriteAcceptedWithWarnings"] = json.dumps(validation, ensure_ascii=False)
                data.setdefault("debug", {})["itemSpriteValidation"] = json.dumps(attempts, ensure_ascii=False)
                trace_event("step", "IMAGE:item", "sprite accepted", {
                    "assetId": asset_id, "attempt": attempt, "raw": str(Path(raw_best).resolve()), "final": str(Path(final_path).resolve()),
                    "score": last_score, "status": visual.get("spriteStatus", ""), "validation": validation,
                })
                return data
        except Exception as e:
            attempts.append({"attempt": attempt, "ok": False, "error": repr(e)})
            data.setdefault("debug", {})["spriteError"] = repr(e)
            trace_event("error", "IMAGE:item", "sprite generation attempt failed", {"assetId": asset_id, "attempt": attempt, "backend": IMAGE_BACKEND}, error=repr(e))
            log_event("warn", "sprite generation failed", {"attempt": attempt, "error": repr(e), "trace": traceback.format_exc()})
    data.setdefault("debug", {})["itemSpriteValidation"] = json.dumps(attempts, ensure_ascii=False)
    if last_path:
        data.setdefault("debug", {})["itemSpriteInvalidGeneratedDiscarded"] = str(Path(last_path).resolve())
    if VISUAL_ALLOW_PROCEDURAL_FALLBACK and not VISUAL_STRICT_AI_AUTHORSHIP:
        try:
            fallback = visual_asset_pipeline.generate_procedural_asset(data, "item", variant=0, canvas_size=canvas, sprite_dir=SPRITE_DIR, image_cls=Image, image_draw_cls=ImageDraw)
            final = postprocess_sprite(fallback, str(data.get("id", "sprite")), canvas, "item")
            visual["spritePath"] = str(Path(final).resolve())
            visual["spriteRawPath"] = str(Path(fallback).resolve())
            visual["spriteStatus"] = "fallback_after_failed_generation"
            visual["visualJudgeScore"] = 0.0
            visual["spriteUrl"] = f"/sprite/{Path(final).name}"
            attach_visual_soul_from_sprite(data, final, validation={"ok": True, "source": "procedural_fallback"}, score=0.0)
            return data
        except Exception as e:
            data.setdefault("debug", {})["spriteFallbackError"] = repr(e)
    visual["spriteStatus"] = "failed"
    visual["spritePath"] = ""
    visual["spriteRawPath"] = ""
    visual["spriteUrl"] = ""
    visual["visualJudgeScore"] = round(last_score, 3)
    return data

def _clamp01(value: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


def _hex_from_rgb(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{max(0, min(255, int(r))):02x}{max(0, min(255, int(g))):02x}{max(0, min(255, int(b))):02x}"


def _rgb_to_hsv01(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = [max(0.0, min(1.0, float(x) / 255.0)) for x in rgb]
    mx, mn = max(r, g, b), min(r, g, b)
    delta = mx - mn
    if delta <= 1e-6:
        hue = 0.0
    elif mx == r:
        hue = ((g - b) / delta) % 6.0
    elif mx == g:
        hue = ((b - r) / delta) + 2.0
    else:
        hue = ((r - g) / delta) + 4.0
    hue = (hue * 60.0) % 360.0
    sat = 0.0 if mx <= 1e-6 else delta / mx
    return hue / 360.0, sat, mx


def visual_soul_archetype(rgb: tuple[int, int, int], coverage: float, edge_density: float) -> str:
    hue, sat, val = _rgb_to_hsv01(rgb)
    deg = hue * 360.0
    if coverage < 0.10 and val > 0.45:
        return "wisp"
    if val < 0.18:
        return "void"
    if sat < 0.18:
        return "silver" if val > 0.52 else "ashen"
    if deg < 18 or deg >= 345:
        return "crimson"
    if deg < 46:
        return "ember"
    if deg < 72:
        return "solar"
    if deg < 154:
        return "verdant"
    if deg < 196:
        return "aqua"
    if deg < 232:
        return "frost"
    if deg < 282:
        return "arcane"
    if deg < 330:
        return "rose"
    return "crimson"


def visual_soul_tooltip(archetype: str, glow: float, coverage: float, edge_density: float) -> str:
    tone = {
        "ember": "ember-forged",
        "solar": "sunlit",
        "verdant": "verdant",
        "aqua": "tidal",
        "frost": "frost-cut",
        "arcane": "arcane",
        "rose": "roseglass",
        "crimson": "crimson",
        "void": "void-touched",
        "silver": "silvered",
        "ashen": "ashen",
        "wisp": "wisp-light",
    }.get(archetype, archetype or "unknown")
    body = "dense" if coverage >= 0.46 else "clear" if coverage >= 0.22 else "thin"
    edge = "jagged" if edge_density >= 0.36 else "etched" if edge_density >= 0.20 else "smooth"
    pulse = "bright" if glow >= 0.66 else "soft" if glow >= 0.34 else "quiet"
    return f"Visual soul: {tone}, {body} {edge} silhouette, {pulse} aura"


def _rgba_pixels(image: Any) -> list[tuple[int, int, int, int]]:
    """Return flattened RGBA pixels without Pillow deprecated Image.getdata()."""
    raw = image.tobytes()
    return [tuple(raw[i:i + 4]) for i in range(0, len(raw), 4)]


def analyze_visual_soul_from_sprite(path: str, *, score: float = 0.0) -> dict[str, Any]:
    """Extract a tiny runtime personality from the finished Z-Image sprite.

    This intentionally reads the final postprocessed PNG, not LLM prose.  The generated
    art becomes gameplay presentation data: palette, glow, aura archetype, and a stable
    signature for tooltips/reveal effects.
    """
    if Image is None:
        return {}
    sprite_path = Path(path)
    if not sprite_path.exists():
        return {}
    try:
        img = Image.open(sprite_path).convert("RGBA")
        w, h = img.size
        if w <= 0 or h <= 0:
            return {}
        pixels = _rgba_pixels(img)
        opaque: list[tuple[int, int, int, int]] = [p for p in pixels if int(p[3]) >= 24]
        if not opaque:
            return {}
        count = len(opaque)
        coverage = count / float(max(1, w * h))
        # Alpha-weighted average gives the quiet body color; saturation-biased sample
        # gives the visible accent color for glows and particles.
        total_a = sum(max(1, int(a)) for _, _, _, a in opaque)
        avg = tuple(int(sum(int(p[i]) * max(1, int(p[3])) for p in opaque) / max(1, total_a)) for i in range(3))
        accent = max(
            opaque,
            key=lambda p: (_rgb_to_hsv01((p[0], p[1], p[2]))[1] * 1.35 + _rgb_to_hsv01((p[0], p[1], p[2]))[2] * 0.65) * (p[3] / 255.0),
        )
        accent_rgb = (int(accent[0]), int(accent[1]), int(accent[2]))
        # Cheap edge estimate: alpha boundary + local color contrast on occupied pixels.
        alpha = [int(p[3]) >= 24 for p in pixels]
        edges = 0
        checks = 0
        for y in range(h):
            row = y * w
            for x in range(w):
                idx = row + x
                if not alpha[idx]:
                    continue
                if x + 1 < w:
                    checks += 1
                    if alpha[idx + 1] != alpha[idx]:
                        edges += 1
                if y + 1 < h:
                    checks += 1
                    if alpha[idx + w] != alpha[idx]:
                        edges += 1
        edge_density = _clamp01(edges / float(max(1, checks)) * 2.0)
        _, sat, val = _rgb_to_hsv01(accent_rgb)
        glow = _clamp01(0.08 + sat * 0.38 + val * 0.16 + coverage * 0.18 + edge_density * 0.20 + _clamp01(score) * 0.10)
        pulse = _clamp01(0.15 + sat * 0.35 + edge_density * 0.35 + _clamp01(score) * 0.15)
        archetype = visual_soul_archetype(accent_rgb, coverage, edge_density)
        try:
            signature = hashlib.sha1(sprite_path.read_bytes()).hexdigest()[:10]
        except Exception:
            signature = hashlib.sha1(str(sprite_path).encode("utf-8", "ignore")).hexdigest()[:10]
        return {
            "visualSoulSignature": signature,
            "visualSoulArchetype": archetype,
            "dominantColorHex": _hex_from_rgb(avg),
            "accentColorHex": _hex_from_rgb(accent_rgb),
            "visualSoulGlow": round(glow, 3),
            "visualSoulPulse": round(pulse, 3),
            "visualSoulCoverage": round(_clamp01(coverage), 3),
            "visualSoulEdgeDensity": round(edge_density, 3),
            "visualSoulTooltip": visual_soul_tooltip(archetype, glow, coverage, edge_density),
        }
    except Exception as e:
        log_event("warn", "visual soul analysis failed", {"path": str(path), "error": repr(e)})
        return {}


def attach_visual_soul_from_sprite(data: dict[str, Any], path: str, *, validation: dict[str, Any] | None = None, score: float = 0.0) -> dict[str, Any]:
    visual = data.setdefault("visual", {})
    soul = analyze_visual_soul_from_sprite(path, score=score)
    if not soul:
        return data
    visual.update(soul)
    data.setdefault("debug", {})["visualSoul"] = json.dumps({**soul, "validationOk": bool((validation or {}).get("ok", True))}, ensure_ascii=False)
    # Make later visual-director/VFX debug screens show what the final PNG actually contributed.
    palette = [str(x) for x in visual.get("palette", []) if str(x).strip()]
    for color_key in ("accentColorHex", "dominantColorHex"):
        color = soul.get(color_key)
        if color and color not in palette:
            palette.insert(0, str(color))
    visual["palette"] = list(dict.fromkeys(palette))[:8]
    return data


def asset_negative_prompt(role: str = "item") -> str:
    # Z-Image Turbo does not use negative prompts as a reliable CFG channel;
    # technical exclusions are injected into the positive prompt instead.
    if image_backend_is_zimage():
        return ""
    base = sprite_background_negative_clause()
    if role == "projectile":
        return base + ", full inventory icon, large weapon held by character"
    if role == "impact":
        return base + ", full weapon, held weapon, blade, hilt, handle, furniture object, inventory item icon, placed object, persistent object"
    if role in {"child", "field"}:
        return base + ", full weapon, inventory item icon"
    return base

def chroma_rgb() -> tuple[int, int, int]:
    if BG_COLOR in {"green", "lime", "greenscreen"}:
        return (0, 255, 0)
    if BG_COLOR in {"blue"}:
        return (0, 0, 255)
    if BG_COLOR in {"white"}:
        return (255, 255, 255)
    if BG_COLOR in {"black"}:
        return (0, 0, 0)
    return (255, 0, 255)

def chroma_name() -> str:
    r, g, b = chroma_rgb()
    if (r, g, b) == (255, 0, 255):
        return "pure flat magenta background (#ff00ff)"
    if (r, g, b) == (0, 255, 0):
        return "pure flat green background (#00ff00)"
    if (r, g, b) == (255, 255, 255):
        return "pure flat white background (#ffffff)"
    if (r, g, b) == (0, 0, 0):
        return "pure flat black background (#000000)"
    return f"pure flat background color rgb({r},{g},{b})"

def sprite_background_positive_clause() -> str:
    # Prefer a magenta key over requesting alpha/transparency. Local postprocess owns alpha.
    if REMOVE_BG and BG_REMOVE_MODE in {"chroma", "floodfill"}:
        return f"on a perfectly solid untextured {chroma_name()}, object fully separated from background, no floor, no cast shadow, no gradient"
    if REMOVE_BG and BG_REMOVE_MODE == "rembg":
        return "on a plain solid magenta key background (#ff00ff), no scene, no floor, no cast shadow"
    return "on a perfectly solid untextured pure flat magenta background (#ff00ff), object fully separated from background, no floor, no cast shadow, no gradient"

def sprite_background_negative_clause() -> str:
    if REMOVE_BG and BG_REMOVE_MODE in {"chroma", "floodfill"}:
        return "scenery, room, landscape, floor, ground, pedestal, UI frame, text, watermark, character, hands, gradient, textured background, cast shadow, transparent checkerboard, transparency preview, glass background"
    return "scene, background, scenery, room, landscape, character holding item, hands, UI frame, text, watermark, shadow on floor, realistic render, 3d render, blurry, anti-aliased edges"

def image_backend_is_zimage() -> bool:
    """True when the configured image backend should use the Z-Image prompt contract.

    Keep this as backend metadata. It must never route item behavior or weapon
    family. ``auto`` detects Z-Image/Z-Image-Turbo sd.cpp configs; ``1`` forces
    the PE-style positive prompt contract for sd.cpp; ``0`` disables it.
    """
    if (IMAGE_BACKEND or "").lower() != "sdcpp":
        return False
    mode = ZIMAGE_PROMPT_CONTRACT
    if mode in {"0", "false", "off", "no", "disabled", "disable"}:
        return False
    if mode in {"1", "true", "on", "yes", "force", "forced"}:
        return True
    hay = " ".join([SDCPP_MODEL, SDCPP_SERVER_COMMAND_TEMPLATE, SDCPP_SERVER_EXTRA_ARGS]).lower().replace("_", "-")
    return "z-image" in hay or "zimage" in hay

def zimage_positive_only_enabled() -> bool:
    return bool(image_backend_is_zimage() and ZIMAGE_POSITIVE_ONLY)

def zimage_role_description(role: str, canvas: int) -> str:
    """Concrete role sentence for Z-Image Turbo prompts.

    Keep the opening sentence simple and object-focused. Do not inject tiny-size
    readability advice here; the model already renders to a large canvas and the
    postprocess stage handles the final bake.
    """
    r = (role or "item").lower()
    if r == "projectile":
        return "A Terraria-like pixel-art projectile sprite."
    if r == "impact":
        return "A Terraria-like pixel-art hit impact sprite."
    if r == "child":
        return "A Terraria-like pixel-art child shard, spark, or mote sprite."
    if r == "field":
        return "A Terraria-like pixel-art field, rune, cloud, or trap-mark sprite."
    return "A Terraria-like pixel-art item sprite."

def zimage_positive_guard_clause(role: str, data: dict[str, Any] | None = None) -> str:
    """Positive-only technical guard for Z-Image Turbo.

    Keep only the minimal technical instructions that improve sprite extraction:
    flat chroma background, one subject, full subject inside the frame, and the
    subject spanning most of the canvas on at least one axis.
    """
    r = (role or "item").lower()
    base = (
        "Flat #ff00ff magenta chroma-key background. "
        "Show only the described sprite subject, fully inside the frame. "
        "Let the subject span most of the canvas along at least one axis. "
        "Use crisp hard pixel edges, a limited palette, and a clean silhouette."
    )
    if r == "projectile":
        if isinstance(data, dict) and tether_sprite_guard_required(data, "projectile"):
            return base + " If rope, cord, chain, or tether detail is present, keep it as a short local attachment on the projectile body."
        return base + " Show one projectile body only."
    if r == "impact":
        return base + " Show one compact impact burst only."
    if r == "field":
        return base + " Show one field, rune, cloud, or trap-mark body only."
    if r == "child":
        return base + " Show one compact child shard, spark, or mote only."
    return base + " Show only the item sprite."



def _is_generated_usable_gear(data: dict[str, Any]) -> bool:
    """True for generated outputs that are used/held/equipped, not placed as scenes.

    This is visual prompt hygiene only.  It must not route gameplay families or
    change resultKind/runtimeFamily.  The intent is to keep an item icon for a
    usable object from becoming a full tile/room/placeable scene when one parent
    is furniture or a placeable material.
    """
    category = str(data.get("category") or "").lower()
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    runtime_kind = str(gameplay.get("runtimeOutputKind") or gameplay.get("kind") or "").lower()
    rp = runtime_plan(data)
    result_kind = str(rp.get("resultKind") or "").lower() if isinstance(rp, dict) else ""
    hay = " ".join([category, runtime_kind, result_kind])
    return any(x in hay for x in ["weapon", "tool", "accessory", "potion", "ammo", "consumable_weapon"])


def _compact_prompt_append(prompt: str, addition: str, *, limit: int = 1800) -> str:
    p = re.sub(r"\s+", " ", str(prompt or "").strip())
    add = re.sub(r"\s+", " ", str(addition or "").strip())
    if not add:
        return p[:limit]
    probe = re.sub(r"[^a-z0-9]+", " ", p.lower()).strip()
    add_probe = re.sub(r"[^a-z0-9]+", " ", add.lower()).strip()
    if add_probe and add_probe not in probe:
        p = (p.rstrip(" ,.;") + ", " + add).strip()
    return p[:limit]


_BLADE_SUBJECT_RE = re.compile(r"\b(?:blade|sword|broadsword|greatsword|dagger|saber|sabre)\b")
_FUSED_BLADE_RISK_RE = re.compile(
    r"\b(?:split[-\s]?blade|forked|two[-\s]?toned?|dual[-\s]?toned?|light[-/\s]*dark|dark[-/\s]*light)\b"
)


def _blade_shape_needs_fused_contour_guard(text: str) -> bool:
    """Detect blade-shape composition risk without a growing per-item keyword table."""
    blob = re.sub(r"[_/]+", " ", str(text or "").lower())
    return bool(_BLADE_SUBJECT_RE.search(blob) and _FUSED_BLADE_RISK_RE.search(blob))


def _item_blade_guard_context(prompt: str, data: dict[str, Any]) -> str:
    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    return " ".join(
        str(part or "")
        for part in (
            prompt,
            data.get("name"),
            concept.get("fantasy"),
            visual.get("silhouetteSummary"),
        )
    )


_ITEM_USABLE_GEAR_GUARD = (
    "depict one handheld or carriable usable item object, not a placed tile, room scene, "
    "furniture placement preview, pedestal, or environment; if furniture or placeable "
    "material is part of the design, show usable parts, fragments, straps, handle, head, "
    "blade, tool body, or silhouette cues integrated into the item"
)
_ITEM_USABLE_PARTS_GUARD = (
    "if furniture or placeable material is part of the design, show usable parts, "
    "fragments, straps, handle, head, blade, tool body, or silhouette cues integrated into the item"
)


def _prompt_probe(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _append_item_role_guard_once(prompt: str) -> str:
    """Keep the role guard once; add only the missing half for partial authored guards."""
    p = _strip_item_role_guard_fragments(prompt)
    probe = _prompt_probe(p)
    if "handheld or carriable usable item" not in probe:
        return _compact_prompt_append(p, _ITEM_USABLE_GEAR_GUARD)
    if "usable parts fragments" not in probe:
        return _compact_prompt_append(p, _ITEM_USABLE_PARTS_GUARD)
    return p[:1800]


def _strip_item_role_guard_fragments(prompt: str) -> str:
    """Remove old/duplicated generated-item role boilerplate before adding one canonical guard."""
    p = str(prompt or "")
    stop = r"(?=\s*,?\s*depict one handheld|\s*\.\s*Flat #ff00ff|\s*\.\s*Color scheme|\s*\.\s*without letters|$)"
    full_guard = (
        r"\s*,?\s*depict\s+one\s+handheld\s+or\s+carriable\s+usable\s+item\s+object,\s*"
        r"not\s+a\s+placed\s+tile(?:(?!depict\s+one\s+handheld).){0,560}?"
        r"silhouette\s+cues\s+integrated\s+into\s+the\s+item\s*[.;,]?"
    )
    partial_guard = (
        r"\s*,?\s*depict\s+one\s+handheld\s+or\s+carriable\s+usable\s+item\s+object,\s*"
        r"not\s+a\s+placed\s+tile(?:(?!depict\s+one\s+handheld).){0,260}?"
        r"(?:pedestal\s*,?\s*or\s+environment|furniture\s+placement\s+preview\s*,?\s*or\s+environment|environment)\s*[.;,]?"
    )
    p = re.sub(full_guard + stop, " ", p, flags=re.IGNORECASE)
    p = re.sub(partial_guard + stop, " ", p, flags=re.IGNORECASE)
    p = re.sub(r"\s+", " ", p)
    p = re.sub(r"\s*,\s*,+", ", ", p)
    return p.strip(" ,.;")


def _authored_item_silhouette_contract(data: dict[str, Any]) -> str:
    """Return an LLM/data-authored item silhouette contract; no hard-coded weapon taxonomy."""
    if not isinstance(data, dict):
        return ""
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    kit = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
    for source in (visual, kit):
        for key in (
            "itemSilhouetteContract",
            "silhouetteContract",
            "shapeContract",
            "itemShapeContract",
            "iconShapeContract",
        ):
            raw = source.get(key) if isinstance(source, dict) else ""
            if str(raw or "").strip():
                cleaned = strip_conflicting_sprite_prompt_bits(str(raw))
                cleaned = zimage_pe_clean_text(cleaned)
                cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;")
                if cleaned:
                    return compact_visual_words(cleaned, 360)
    return ""


def _prepend_prompt_contracts(prompt: str, clauses: list[str], *, limit: int = 1800) -> str:
    p = re.sub(r"\s+", " ", str(prompt or "").strip())
    for clause in reversed([c for c in clauses if str(c).strip()]):
        add = re.sub(r"\s+", " ", str(clause).strip())
        if _prompt_probe(add) not in _prompt_probe(p):
            p = (add.rstrip(" ,.;") + ", " + p.lstrip(" ,.;")).strip()
    return p[:limit]


def role_visual_prompt_guard(role: str, prompt: str, data: dict[str, Any]) -> str:
    """Small, role-local visual guard with no gameplay routing.

    The guard never rewrites delivery/runtime/result kind.  It only tells the
    image model what this asset slot is allowed to depict: item = one usable
    object, projectile = moving hit body, impact = short effect.  This keeps
    creative weirdness while preventing common role leakage like full furniture
    scenes in weapon icons or weapon-shaped impact sprites.
    """
    r = (role or "item").lower()
    p = str(prompt or "")
    if r == "item" and _is_generated_usable_gear(data):
        p = _append_item_role_guard_once(p)
        p = _prepend_prompt_contracts(p, [_authored_item_silhouette_contract(data)])
        blade_blob = _item_blade_guard_context(p, data)
        if _blade_shape_needs_fused_contour_guard(blade_blob):
            p = _compact_prompt_append(
                p,
                "if the blade is split, forked, light-dark, or two-toned, draw one fused weapon silhouette with the dark/black portion flush to the blade contour; avoid detached second-sword shapes, stray side spurs, dangling black tails, or extra protruding appendages",
            )
        return p[:1800]
    if r == "impact":
        return _compact_prompt_append(
            p,
            "depict only a momentary hit effect: dust, smoke, sparks, splash, shards, fragments, ring, puff, flash, or debris burst; no persistent item icon, no held weapon body, no handle, no blade, no furniture object, no placed object",
        )
    if r == "projectile":
        attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
        tags = attack.get("attackPatternTags") if isinstance(attack.get("attackPatternTags"), list) else []
        falling = str(attack.get("onHit") or "").lower() == "starfall" or "falling_star" in {str(x).lower() for x in tags}
        extra = "role contract: projectile body; same weapon shape may be reused when that is the actual hit body, but use attack-frame/projectile-body framing, not inventory-view framing"
        if falling:
            extra += "; falling star hit body, not a decorative background sparkle field"
        return _compact_prompt_append(
            p,
            "depict the moving hit object texture only; keep the authored projectile subject intact; not a placed object, not a room scene; " + extra,
        )
    if r == "child":
        return _compact_prompt_append(
            p,
            "role contract: child damaging projectile or mote; not a decorative background sparkle field, not an impact burst, not the inventory weapon icon",
        )
    return p[:1800]

def _authored_tether_context(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    for key in ("name", "tooltip", "category"):
        chunks.append(str(data.get(key) or ""))
    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    for key in ("fantasy", "mergeLogic", "weirdTwist"):
        chunks.append(str(concept.get(key) or ""))
    rp = runtime_plan(data)
    if isinstance(rp, dict):
        chunks.append(json.dumps(rp, ensure_ascii=False)[:4000])
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    for key in ("runtimeFamily", "delivery", "weaponFamily", "projectileFamily", "movement", "projectileShape", "projectileMotion", "projectileTrail", "projectileImpact"):
        chunks.append(str(attack.get(key) or ""))
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    for key in ("imagePrompt", "projectileImagePrompt", "impactImagePrompt"):
        chunks.append(str(visual.get(key) or ""))
    return " ".join(chunks).lower()

def authored_tether_like(data: dict[str, Any]) -> bool:
    ctx = _authored_tether_context(data)
    words = ("rope", "tether", "cord", "chain", "harpoon", "anchor", "reel", "returning_glaive", "snap back", "snaps back", "retract", "reels back")
    return any(w in ctx for w in words)

def tether_sprite_guard_required(data: dict[str, Any], role: str) -> bool:
    """Return True only when a sprite-body guard is technically needed.

    Rope/chain words alone are not enough: a rope item icon or decorative chain
    should keep its authored silhouette.  The guard is only for small projectile
    body textures whose long tether/cord is represented by gameplay/VFX state.
    """
    r = (role or "").lower()
    if r != "projectile":
        return False
    if not authored_tether_like(data):
        return False
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    runtime_family = str(attack.get("runtimeFamily") or "").lower()
    movement = str(attack.get("movement") or attack.get("pattern") or attack.get("attackPattern") or "").lower()
    pattern = str(attack.get("pattern") or attack.get("attackPattern") or "").lower()
    delivery = str(attack.get("delivery") or "").lower()
    weapon_family = str(attack.get("weaponFamily") or "").lower()
    projectile_family = str(attack.get("projectileFamily") or "").lower()
    family_blob = weapon_family + " " + projectile_family + " " + movement
    explicit_tether_family = any(w in family_blob for w in ["harpoon", "flail", "yoyo", "whip", "anchor", "return"])
    return (
        runtime_family in {"flail", "yoyo", "whip", "returning"}
        or movement in {"flail_tether", "yoyo_hover", "whip_lash", "returning_glaive", "boomerang"}
        or pattern == "spear_thrust" and delivery == "thrust"
        or runtime_family in {"throw", "shoot"} and explicit_tether_family
        or delivery in {"throw", "returning"} and explicit_tether_family
    )

def _scrub_tether_sprite_body_prompt(prompt: str, role: str) -> str:
    """Remove only full-canvas/off-canvas tether instructions.

    This is deliberately light-touch.  It preserves a visible local rope/chain
    detail when that detail helps the sprite read better, but prevents Z-Image
    from turning a projectile texture into a long line across the whole canvas.
    """
    p = str(prompt or "")
    if (role or "").lower() != "projectile":
        return p
    replacements = [
        (r"\bthin\s+taut\s+rope\s+tether\s+line\s+extending\s+left\b", "short local rope attachment at the base"),
        (r"\bthin\s+(?:taut|taught)\s+rope\s+line\s+back\s+to\s+the\s+player\b", "short local rope attachment at the base"),
        (r"\btrailing\s+a\s+thin\s+(?:taut|taught)\s+rope\s+line\s+back\s+to\s+the\s+player\b", "with a short rope loop at the base"),
        (r"\b(?:rope|chain|cord|tether)\s+line\s+extending\s+(?:left|right|back)\b", "short local tether attachment"),
        (r"\b(?:rope|chain|cord|tether)\s+back\s+to\s+the\s+player\b", "short local tether attachment"),
        (r"\boff[- ]canvas\s+(?:rope|chain|cord|tether)\b", "small coil attached to the body"),
        (r"\bfull[- ]screen\s+(?:rope|chain|cord|tether)\b", "short local rope or chain detail"),
    ]
    for pat, repl in replacements:
        p = re.sub(pat, repl, p, flags=re.IGNORECASE)
    return p

def tether_visual_prompt_guard(role: str, prompt: str, data: dict[str, Any]) -> str:
    """Minimal Z-Image guard for tethered projectile-body sprites.

    It does not route item families and it does not rewrite rope/chain items.
    It only keeps tiny projectile-body PNGs from becoming full-canvas tether
    drawings, which hurts bbox validation and in-game readability.
    """
    p = str(prompt or "")
    if not tether_sprite_guard_required(data, role):
        return p
    p = _scrub_tether_sprite_body_prompt(p, role)
    guard = "visible rope, cord, or chain may appear as a short local attachment, loop, nub, or compact coil attached to the main projectile body; keep the main projectile silhouette readable and keep all tether detail inside the canvas"
    guard_probe = re.sub(r"[^a-z0-9]+", " ", guard.lower()).strip()
    prompt_probe = re.sub(r"[^a-z0-9]+", " ", p.lower()).strip()
    if guard_probe not in prompt_probe:
        p = (p.rstrip(" ,.;") + ", " + guard).strip()
    return p[:1800]

def family_prompt_clause(data: dict[str, Any], role: str, canvas: int) -> str:
    if (role or "").lower() != "projectile":
        return role_contract_prompt_clause(role, canvas)
    family = infer_projectile_visual_family(data)
    spec = sprite_contract_for("projectile", canvas)
    fill = spec.get("promptFillWords", "the projectile body should fill most of the canvas")
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    runtime_family = str(attack.get("runtimeFamily") or "").lower()
    pattern = str(attack.get("pattern") or attack.get("attackPattern") or "").lower()
    projectile_family = str(attack.get("projectileFamily") or "").lower()
    spear_form = any(w in projectile_family for w in ["spear", "lance", "pike", "trident", "glaive", "halberd", "naginata"])
    if runtime_family == "thrust" or pattern == "spear_thrust":
        return ", ".join([
            "held close-range thrust projection texture matching the authored projectile body",
            "aligned for a forward stab or short lunge when the authored body has a clear long axis",
            "one projection texture only; keep unusual authored forms readable rather than forcing a spear or polearm silhouette",
            str(fill),
        ])
    if runtime_family in {"cast", "shoot", "throw"} and spear_form:
        return ", ".join([
            "free-flying spear/lance-shaped projectile body in a flight pose",
            "short readable spearhead or spectral lance aligned along its flight axis",
            "empty magenta canvas around the projectile body",
            "one projectile only",
            str(fill),
        ])
    if runtime_family == "flail" or pattern == "flail_tether":
        return ", ".join([
            "compact flail or mace head projectile body",
            "optional short local chain segment attached to the head",
            "one projectile head only",
            str(fill),
        ])
    if runtime_family == "yoyo" or pattern == "yoyo_hover":
        return ", ".join([
            "compact circular yoyo body sprite",
            "optional short local string nub attached to the yoyo",
            "one yoyo only",
            str(fill),
        ])
    if runtime_family == "whip" or pattern == "whip_lash":
        return ", ".join([
            "compact whip tip or short lash segment body",
            "one readable tip or short segment only",
            str(fill),
        ])
    if family == "linear_side":
        return ", ".join([
            "canonical side-view gameplay projectile, long axis horizontal left-to-right",
            "tip/nose points right in the texture because the game rotates projectile sprites at runtime",
            "not a vertical inventory icon, not a tiny upright arrow",
            "one projectile only",
            str(fill),
        ])
    if family == "spark_mote":
        return ", ".join([
            "compact spark or ember-like body if the authored projectile is a small spark",
            "one projectile only",
            str(fill),
        ])
    return role_contract_prompt_clause(role, canvas)

def sanitize_projectile_family_prompt(data: dict[str, Any], role: str, prompt: str) -> str:
    """Final technical prompt guard for sprite assets.

    The guard is minimal and role-aware: form/material/family words stay authored;
    only full-canvas tether text is compressed into a local visible detail when the
    executable family says this is a tethered projectile body.
    """
    p = tether_visual_prompt_guard(role, str(prompt or ""), data)
    return p[:1800]

def zimage_subject_sentence(role: str, authored_prompt: str, fantasy: str) -> str:
    """PE-style invariant subject sentence.

    Keep subject/count/action/state/material words in the model-authored prompt.
    Supporting fantasy is useful for item/projectile identity, but impact sprites
    must stay effect-only: adding the full item fantasy there tends to leak the
    weapon/item body into the hit flash.
    """
    r = (role or "item").lower()
    subject = zimage_pe_clean_text(authored_prompt)
    fantasy = "" if r == "impact" else zimage_pe_clean_text(fantasy)
    if subject and fantasy and fantasy.lower() not in subject.lower():
        return f"The main visual subject is {subject}. It visually represents {fantasy}."
    if subject:
        return f"The main visual subject is {subject}."
    if fantasy:
        return f"The main visual subject is {fantasy}."
    if r == "impact":
        return "The main visual subject is one compact hit effect burst."
    return f"The main visual subject is one {r} sprite asset."


def zimage_item_identity_sentence(role: str, data: dict[str, Any]) -> str:
    """Name the generated item in the prompt without asking for drawn text.

    The image model was sometimes receiving only a generic object description, so
    different recursive items with related parents collapsed into near-identical
    sprites. This is visual identity context only; text rendering remains banned.
    """
    if (role or "item").lower() != "item" or not isinstance(data, dict):
        return ""
    name = compact_visual_words(data.get("name") or "", 90)
    if not name:
        return ""
    return f"The generated item is named {name}; use the name only as identity context, without drawn letters or labels."


def item_name_prompt_clause(role: str, data: dict[str, Any]) -> str:
    if (role or "item").lower() != "item" or not isinstance(data, dict):
        return ""
    name = compact_visual_words(data.get("name") or "", 90)
    return f"generated item name: {name}; do not draw letters or labels" if name else ""

def sprite_contract_for(role: str, target_size: int = 32) -> dict[str, Any]:
    role = (role or "item").lower()
    size = max(16, min(96, int(target_size or 32)))
    table: dict[str, dict[str, Any]] = {
        "item": {
            "targetFill": ITEM_ICON_TARGET_FILL,
            "minFill": 0.82,
            "maxFill": 0.98,
            "coreAlphaThreshold": SPRITE_ITEM_CORE_ALPHA_THRESHOLD,
            "marginPx": 1 if size <= 32 else 2,
            "cropPadPx": 1,
            "maxEdgeTouch": 0.08,
            "promptFillWords": "the item body should span most of the canvas along its width or height while staying fully inside the frame",
            "promptPoseWords": "compose it as a clean Terraria-style item sprite",
        },
        "projectile": {
            "targetFill": PROJECTILE_ICON_TARGET_FILL,
            "minFill": 0.68,
            "maxFill": 0.96,
            "coreAlphaThreshold": SPRITE_EFFECT_CORE_ALPHA_THRESHOLD,
            "marginPx": 1 if size <= 32 else 2,
            "cropPadPx": 1,
            "maxEdgeTouch": 0.10,
            "promptFillWords": "the projectile body should span most of the canvas along its width or height while staying fully inside the frame",
            "promptPoseWords": "compose it as one clean projectile sprite in gameplay view",
        },
        "impact": {
            "targetFill": IMPACT_ICON_TARGET_FILL,
            "minFill": 0.52,
            "maxFill": 0.95,
            "coreAlphaThreshold": SPRITE_EFFECT_CORE_ALPHA_THRESHOLD,
            "marginPx": 1 if size <= 32 else 2,
            "cropPadPx": 1,
            "maxEdgeTouch": 0.18,
            "promptFillWords": "the burst shape should span most of the canvas along its width or height while staying fully inside the frame",
            "promptPoseWords": "single compact effect burst only, no item or weapon body",
        },
        "child": {
            "targetFill": CHILD_ICON_TARGET_FILL,
            "minFill": 0.48,
            "maxFill": 0.90,
            "coreAlphaThreshold": SPRITE_EFFECT_CORE_ALPHA_THRESHOLD,
            "marginPx": 1 if size <= 32 else 2,
            "cropPadPx": 1,
            "maxEdgeTouch": 0.14,
            "promptFillWords": "the child body should span a large visible portion of the canvas while staying fully inside the frame",
            "promptPoseWords": "one tiny separate object only",
        },
        "field": {
            "targetFill": FIELD_ICON_TARGET_FILL,
            "minFill": 0.62,
            "maxFill": 0.98,
            "coreAlphaThreshold": SPRITE_EFFECT_CORE_ALPHA_THRESHOLD,
            "marginPx": 1 if size <= 32 else 2,
            "cropPadPx": 1,
            "maxEdgeTouch": 0.14,
            "promptFillWords": "the field mark should span most of the canvas along its width or height while staying fully inside the frame",
            "promptPoseWords": "single field effect only",
        },
    }
    spec = dict(table.get(role, table["item"]))
    target_fill = max(0.40, min(0.98, float(spec["targetFill"])))
    margin = max(0, int(spec["marginPx"]))
    spec["role"] = role
    spec["size"] = size
    spec["targetLongAxisPx"] = max(4, min(size - margin * 2, int(round(size * target_fill))))
    spec["minLongAxisPx"] = max(3, int(math.floor(size * float(spec["minFill"]))))
    spec["maxLongAxisPx"] = max(spec["minLongAxisPx"], min(size, int(math.ceil(size * float(spec["maxFill"])))))
    # v0.4.49: effect extent must not be stricter than the accepted core long-axis.
    # The old value (size - margin*2) rejected perfectly usable diagonal/X-shaped
    # icons at 45px on a 48px canvas, causing an unnecessary placeholder fallback.
    spec["maxEffectLongAxisPx"] = max(int(spec.get("maxLongAxisPx") or size), int(spec["targetLongAxisPx"]))
    return spec

def role_contract_prompt_clause(role: str, canvas: int) -> str:
    spec = sprite_contract_for(role, canvas)
    return f"{spec['promptPoseWords']}, {spec['promptFillWords']}"

def role_style_prefix(role: str, canvas: int) -> str:
    role = (role or "item").lower()
    bg = sprite_background_positive_clause()
    contract = role_contract_prompt_clause(role, canvas)
    if role == "item":
        return f"pixel art inventory item icon for a Terraria-like mod, {bg}, one object only, {contract}"
    if role == "projectile":
        return f"pixel art flying projectile sprite for a Terraria-like mod, {bg}, {contract}"
    if role == "impact":
        return f"pixel art hit impact flash sprite, {bg}, small effect only, {contract}"
    if role == "child":
        return f"pixel art child mote/echo/spark projectile sprite, {bg}, tiny separate object, {contract}"
    if role == "field":
        return f"pixel art ground field/trap/rune/cloud sprite, {bg}, flat world effect, {contract}"
    return f"pixel art sprite asset, {bg}, one object, {contract}"

def normalize_asset_prompt(data: dict[str, Any], role: str, prompt: str, canvas: int) -> str:
    """Make every visual job explicit and role-separated.

    The visual director is allowed to be creative, but image backends need strict
    role framing.  For Z-Image Turbo we deliberately put all technical sprite
    constraints into the positive prompt and avoid relying on negative_prompt/CFG.
    """
    role = (role or "item").lower()
    prompt = sanitize_image_prompt_background(re.sub(r"\s+", " ", str(prompt or "")).strip())
    if role == "projectile":
        prompt = sanitize_projectile_prompt_multiplicity(prompt)
    prompt = sanitize_projectile_family_prompt(data, role, prompt)
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    palette = sanitize_visual_palette(visual.get("palette") or [], limit=8)
    palette_words = ", ".join(str(x).replace("_", " ") for x in palette[:6] if str(x).strip())
    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    fantasy = compact_visual_words(concept.get("fantasy") or data.get("tooltip") or data.get("name"), 180)
    if not prompt:
        if role == "projectile":
            prompt = build_projectile_image_prompt(data)
        elif role == "impact":
            prompt = build_impact_image_prompt(data)
        elif role == "child":
            prompt = build_child_image_prompt(data)
        elif role == "field":
            prompt = build_field_image_prompt(data)
        else:
            prompt = str(visual.get("imagePrompt") or data.get("name") or "generated item")

    prompt = role_visual_prompt_guard(role, prompt, data)

    if image_backend_is_zimage():
        # Z-Image Turbo: feed one final objective visual description, similar to
        # the public PE layer, not a Stable Diffusion negative-prompt recipe.
        role_clause = family_prompt_clause(data, role, canvas) if role == "projectile" else role_contract_prompt_clause(role, canvas)
        z_parts = [
            zimage_role_description(role, canvas),
            zimage_item_identity_sentence(role, data),
            zimage_subject_sentence(role, prompt, fantasy),
            role_clause,
            zimage_palette_sentence(palette_words),
            zimage_text_policy_sentence(data),
            zimage_positive_guard_clause(role, data),
        ]
        return compact_zimage_asset_prompt(z_parts, role, limit=env_int("INFINI_ZIMAGE_PROMPT_LIMIT", 1800))

    parts = [
        ((role_style_prefix(role, canvas) if role != "projectile" else (f"pixel art held spear/thrust projection sprite for a Terraria-like mod, {sprite_background_positive_clause()}, readable {'16x16 to 32x32' if canvas <= 32 else '32x32 to 64x64'} silhouette, {family_prompt_clause(data, role, canvas)}" if str((data.get("attack") if isinstance(data.get("attack"), dict) else {}).get("runtimeFamily") or "") == "thrust" else f"pixel art flying projectile sprite for a Terraria-like mod, {sprite_background_positive_clause()}, readable {'16x16 to 32x32' if canvas <= 32 else '32x32 to 64x64'} silhouette, {family_prompt_clause(data, role, canvas)}"))),
        f"asset role: {role}",
        item_name_prompt_clause(role, data),
        f"item fantasy: {fantasy}" if fantasy else "",
        prompt,
        f"palette: {palette_words}" if palette_words else "palette: limited high-contrast named colors",
        ("one authored projectile texture only; if the authored subject is a bundle, cluster, swarm, or fan, keep it as one readable projectile bundle rather than separate copies" if role == "projectile" else ""),
        "crisp hard pixel edges, limited palette, no antialiasing look, no UI frame, no text, no character, no scenery, centered single readable asset, keep unused area pure magenta key (#ff00ff)",
    ]
    return ", ".join(p for p in parts if p)[:2200]

def should_generate_child_asset(data: dict[str, Any]) -> bool:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    try:
        if int(float(attack.get("splitCount") or 0)) > 0 or int(float(attack.get("maxChildProjectiles") or 0)) > 0:
            return True
    except Exception:
        pass
    onhit = str(attack.get("onHit") or "").lower()
    if onhit in {"split", "starburst", "starfall", "spore_cloud", "mini_missiles", "vortex_spawn", "radial_beams"}:
        return True
    visual = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
    return bool(str(visual.get("childSpritePrompt") or visual.get("childVfx") or "").strip())

def should_generate_field_asset(data: dict[str, Any]) -> bool:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    text = " ".join(str(attack.get(k, "")).lower() for k in ["impactStyle", "projectileImpact", "visualMode"])
    visual = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
    text += " " + str(visual.get("fieldSpritePrompt") or visual.get("fieldVfx") or "").lower()
    return any(w in text for w in ["field", "trap", "rune", "cloud", "aura", "puddle", "anchor", "sigil", "zone", "mark on ground", "imprint"])

def projectile_visual_blob(data: dict[str, Any]) -> str:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    tags = data.get("tags") if isinstance(data.get("tags"), list) else []
    parents = []
    for key in ("parentA", "parentB"):
        p = data.get(key) if isinstance(data.get(key), dict) else {}
        parents.append(str(p.get("name") or p.get("internalName") or p.get("fullName") or ""))
    fields = [
        data.get("name"), data.get("category"), gameplay.get("kind"), gameplay.get("damageClass"),
        " ".join(str(t) for t in tags), " ".join(parents),
        visual.get("imagePrompt"), visual.get("projectileImagePrompt"),
        attack.get("projectileSpritePrompt"), attack.get("projectileShape"), attack.get("projectileMotion"),
        attack.get("projectileTrail"), attack.get("weaponFamily"), attack.get("projectileFamily"), attack.get("pattern"), attack.get("attackPattern"),
    ]
    return " ".join(str(x or "") for x in fields).lower()

def is_tiny_projectile_visual(data: dict[str, Any]) -> bool:
    blob = projectile_visual_blob(data)
    tiny_words = {"bullet", "pellet", "dart", "needle", "seed", "coin", "bb", "mote", "spark", "particle", "droplet", "tiny", "small shard", "micro"}
    melee_words = {"sword", "blade", "slash", "cut", "swipe", "stab", "thrust", "shortsword", "broadsword", "glaive", "spear", "lance", "scythe", "axe"}
    return any(w in blob for w in tiny_words) and not any(w in blob for w in melee_words)

def is_melee_arc_projectile_visual(data: dict[str, Any]) -> bool:
    blob = projectile_visual_blob(data)
    return any(w in blob for w in ["sword", "blade", "slash", "cut", "swipe", "stab", "thrust", "shortsword", "broadsword", "glaive", "spear", "lance", "scythe", "axe"])

def effective_projectile_canvas(data: dict[str, Any]) -> int:
    """Choose a readable projectile sprite canvas without changing balance tier.

    Canvas is visual resolution, not progression/medium-tier semantics. A wooden sword
    may stay early/cheap, but a sword/slash projectile should still be readable and not
    appear smaller than the starter Copper Shortsword attack.
    """
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    base = max(16, min(64, int(PROJECTILE_SPRITE_CANVAS or 32)))
    item_canvas = max(16, min(64, int(visual.get("preferredCanvasSize") or 32)))
    pw = int(float(attack.get("projectileWidth") or 0) or 0)
    ph = int(float(attack.get("projectileHeight") or 0) or 0)
    major = max(pw, ph)
    if is_tiny_projectile_visual(data):
        # bullets/sparks/darts may legitimately stay 32.
        return base
    if is_melee_arc_projectile_visual(data):
        # Sword/slash/thrust family: readability floor is 48 even for wooden-tier items.
        return max(base, 48, item_canvas if item_canvas >= 48 else 0)
    if major >= 21:
        return max(base, 64 if item_canvas >= 64 else 48)
    if major >= 16:
        return max(base, 48)
    return base

def _visual_kit(data: dict[str, Any]) -> dict[str, Any]:
    kit = data.get("visualKit")
    return kit if isinstance(kit, dict) else {}

def _role_baked_asset_spec(data: dict[str, Any], role: str) -> dict[str, Any]:
    """Model-authored per-role baked asset decision.

    This supports the clearer nested shape:
      visualKit.bakedAssets.projectile = {mode/enabled/prompt/reason}
    while keeping assetModes/projectileAssetMode as compact aliases.  Runtime never
    infers demand from prompt text alone; only these model-authored switches matter.
    """
    role = (role or "").strip().lower()
    for owner in [data.get("visualKit"), data.get("visual"), data]:
        if not isinstance(owner, dict):
            continue
        baked = owner.get("bakedAssets") or owner.get("assetsWanted") or owner.get("visualAssets")
        if isinstance(baked, dict):
            spec = baked.get(role)
            if isinstance(spec, dict):
                return spec
            if isinstance(spec, bool):
                return {"enabled": spec}
            if isinstance(spec, str):
                return {"mode": spec}
    return {}

def _role_asset_prompt(data: dict[str, Any], role: str) -> str:
    spec = _role_baked_asset_spec(data, role)
    for key in ["prompt", "spritePrompt", "imagePrompt"]:
        if isinstance(spec, dict) and spec.get(key):
            return str(spec.get(key) or "").strip()
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    return str(
        visual.get(f"{role}ImagePrompt")
        or attack.get(f"{role}SpritePrompt")
        or ""
    ).strip()

def _asset_mode_from_value(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in {"baked", "baked_sprite", "sprite", "png", "image", "separate_sprite", "generated_sprite"}:
        return "baked_sprite"
    if raw in {"particle", "particles", "particle_vfx", "vfx", "dust", "vanilla_vfx", "code_vfx", "runtime_vfx"}:
        return "particle_vfx"
    if raw in {"none", "off", "skip", "disabled", "false", "no"}:
        return "none"
    return ""

def compiled_child_projectile_needs_sprite(data: dict[str, Any]) -> bool:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    try:
        count = int(float(attack.get("splitCount") or 0))
        max_children = int(float(attack.get("maxChildProjectiles") or 0))
    except (TypeError, ValueError):
        count = max_children = 0
    if count <= 0 and max_children <= 0:
        return False
    return bool(str(attack.get("secondaryProjectileShape") or attack.get("secondaryMaterial") or "").strip())


def authored_asset_mode(data: dict[str, Any], role: str) -> str:
    """Return the model-authored baked-asset mode for a role.

    GUI flags are capability gates only.  They must not force impact/child/field PNGs.
    Only the LLM/visual director can request a separate baked sprite through these
    mode fields; plain prompts are candidate descriptions, not demand.
    """
    role = (role or "").strip().lower()
    if role == "child" and compiled_child_projectile_needs_sprite(data):
        final, _reason = visual_asset_runtime_gate(data, role, "baked_sprite")
        return final or "baked_sprite"
    kit = _visual_kit(data)
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    modes = kit.get("assetModes") if isinstance(kit.get("assetModes"), dict) else {}
    role_spec = _role_baked_asset_spec(data, role)
    candidates = [
        role_spec.get("mode") if isinstance(role_spec, dict) else None,
        role_spec.get("assetMode") if isinstance(role_spec, dict) else None,
        role_spec.get("spriteMode") if isinstance(role_spec, dict) else None,
        role_spec.get("enabled") if isinstance(role_spec, dict) else None,
        modes.get(role),
        kit.get(f"{role}AssetMode"),
        kit.get(f"{role}SpriteMode"),
        visual.get(f"{role}AssetMode"),
        attack.get(f"{role}AssetMode"),
    ]
    # Back-compat with a few natural boolean fields.  These are still model-authored.
    for key in [f"bake{role.capitalize()}Sprite", f"useBaked{role.capitalize()}Sprite", f"{role}BakedSprite"]:
        candidates.extend([kit.get(key), visual.get(key), attack.get(key)])
    for value in candidates:
        if isinstance(value, bool):
            mode = "baked_sprite" if value else "particle_vfx"
            return visual_asset_runtime_gate(data, role, mode)[0]
        mode = _asset_mode_from_value(value)
        if mode:
            return visual_asset_runtime_gate(data, role, mode)[0]
    return ""

def visual_asset_runtime_gate(data: dict[str, Any], role: str, authored_mode: str) -> tuple[str, str]:
    """Runtime-truth gate for optional baked assets.

    The visual director may request extra PNGs, but Python must not spend image
    compute or ship assets that no compiled runtime path can use.  This is a
    structural gate over compiled fields/VFX slots, not a prompt-word router.
    """
    mode = _asset_mode_from_value(authored_mode) or ""
    if not mode:
        return "", ""
    role = (role or "").lower()
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    runtime_family = str(attack.get("runtimeFamily") or "").lower()
    delivery = str(attack.get("delivery") or "").lower()
    hide_graphic = bool(attack.get("hideUseGraphic")) or bool(attack.get("disableItemMeleeHitbox"))

    if role == "projectile" and mode == "baked_sprite":
        # Plain broadsword/swing keeps its item/held sprite.  A separate projectile
        # PNG is only useful for emitted/held projectile executors.
        if runtime_family == "swing" and delivery == "swing" and not hide_graphic:
            return "particle_vfx", "melee_swing_uses_item_sprite_no_projectile_asset"

    if role == "field" and mode == "baked_sprite":
        manifest = data.get("vfxManifest") if isinstance(data.get("vfxManifest"), dict) else {}
        slots = manifest.get("slots") if isinstance(manifest.get("slots"), list) else []
        has_field_slot = any(
            isinstance(slot, dict) and any(
                "field" in str(slot.get(k) or "").lower()
                for k in ("rendererKind", "renderer", "textureRole", "particleRole", "channel", "stage")
            )
            for slot in slots
        )
        field_radius = float(attack.get("vfxFieldRadiusTiles") or attack.get("fieldRadiusTiles") or attack.get("fieldRadius") or 0)
        field_lifetime = float(attack.get("vfxFieldLifetimeTicks") or attack.get("fieldLifetimeTicks") or 0)
        if not has_field_slot and field_radius <= 0 and field_lifetime <= 0:
            return "none", "no_compiled_field_runtime_or_vfx_slot"

    return mode, ""


def apply_visual_asset_runtime_gates(data: dict[str, Any], kit: dict[str, Any]) -> None:
    if not isinstance(kit, dict):
        return
    modes = kit.get("assetModes") if isinstance(kit.get("assetModes"), dict) else {}
    gated: dict[str, str] = {}
    reports: list[dict[str, str]] = []
    baked = kit.get("bakedAssets") if isinstance(kit.get("bakedAssets"), dict) else {}
    for role in ["projectile", "impact", "child", "field"]:
        authored = _asset_mode_from_value(modes.get(role) if isinstance(modes, dict) else "") or _asset_mode_from_value(kit.get(f"{role}AssetMode"))
        if not authored and isinstance(baked, dict):
            spec = baked.get(role)
            if isinstance(spec, dict):
                authored = _asset_mode_from_value(spec.get("mode") or spec.get("assetMode") or spec.get("enabled"))
        final, reason = visual_asset_runtime_gate(data, role, authored)
        if final:
            gated[role] = final
            kit[f"{role}AssetMode"] = final
            if isinstance(baked, dict) and isinstance(baked.get(role), dict):
                baked[role]["mode"] = final
        if reason:
            reports.append({"role": role, "authoredMode": authored, "finalMode": final, "reason": reason})
    if gated:
        kit["assetModes"] = {**(modes if isinstance(modes, dict) else {}), **gated}
    if reports:
        data.setdefault("debug", {})["visualAssetRuntimeGates"] = json.dumps(reports, ensure_ascii=False)


def legacy_projectile_baked_sprite_fallback(data: dict[str, Any]) -> bool:
    """Legacy prompt-only projectile PNG demand is intentionally disabled.

    New worlds do not need to support old visual-director outputs.  A projectile image
    is generated only when the model explicitly authors projectileAssetMode=baked_sprite
    or visualKit.bakedAssets.projectile.enabled=true.
    """
    return False

def build_visual_asset_plan(data: dict[str, Any]) -> list[dict[str, Any]]:
    kit = _visual_kit(data)
    if kit:
        apply_visual_asset_runtime_gates(data, kit)
    attack = data.setdefault("attack", {})
    visual = data.setdefault("visual", {})
    base = str(data.get("id") or "sprite")
    plan: list[dict[str, Any]] = []
    # Item icon is generated by maybe_generate_sprite(), but include it in the manifest.
    plan.append({"role": "item", "assetId": base, "canvas": int(visual.get("preferredCanvasSize") or 32), "prompt": str(visual.get("imagePrompt") or ""), "required": True, "handledBy": "maybe_generate_sprite", "authoringPolicy": "ai_primary_non_procedural", "assetMode": "baked_sprite"})
    if isinstance(attack, dict) and attack.get("enabled"):
        runtime_authored = bool(LLM_RUNTIME_AUTHORING and runtime_plan(data))
        projectile_mode = authored_asset_mode(data, "projectile")
        projectile_prompt = _role_asset_prompt(data, "projectile")
        if VISUAL_GENERATE_PROJECTILE_IMAGES and projectile_mode == "baked_sprite":
            plan.append({"role": "projectile", "assetId": base + "_projectile", "canvas": effective_projectile_canvas(data), "prompt": projectile_prompt, "required": not runtime_authored, "authoringPolicy": "ai_primary_non_procedural", "assetMode": "baked_sprite", "assetDecisionBy": "model"})
        else:
            plan.append({"role": "projectile", "assetId": base + "_projectile", "canvas": effective_projectile_canvas(data), "prompt": projectile_prompt, "required": False, "status": "skipped_not_authored_baked" if VISUAL_GENERATE_PROJECTILE_IMAGES else "skipped_disabled_by_settings", "skipReason": "projectile prompt is not demand; explicit baked_sprite mode required", "authoringPolicy": "ai_primary_non_procedural", "assetMode": projectile_mode or "particle_vfx", "assetDecisionBy": "model"})

        for role, allow, canvas in [
            ("impact", VISUAL_GENERATE_IMPACT_IMAGES, IMPACT_SPRITE_CANVAS),
            ("child", VISUAL_GENERATE_CHILD_FIELD_IMAGES, CHILD_SPRITE_CANVAS),
            ("field", VISUAL_GENERATE_CHILD_FIELD_IMAGES, FIELD_SPRITE_CANVAS),
        ]:
            prompt = _role_asset_prompt(data, role)
            mode = authored_asset_mode(data, role)
            entry = {"role": role, "assetId": base + "_" + role, "canvas": canvas, "prompt": prompt, "required": False, "authoringPolicy": "ai_primary_non_procedural", "assetMode": mode or "particle_vfx", "assetDecisionBy": "model"}
            if allow and mode == "baked_sprite":
                plan.append(entry)
            else:
                entry["status"] = "skipped_not_authored_baked" if allow else "skipped_disabled_by_settings"
                entry["skipReason"] = f"{role} prompt is not demand; explicit baked_sprite mode required" if allow else f"{role} baked images disabled by settings"
                plan.append(entry)
    return plan

def _asset_sha256(path: Path) -> str:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""

def _asset_descriptor(value: Any, required: bool = False) -> dict[str, Any] | None:
    name = asset_sync_service.asset_filename_from_path(value)
    if not name:
        return None
    found = asset_sync_service.find_asset_file(name, sprite_dir=SPRITE_DIR, world_recipes_dir=WORLD_RECIPES_DIR)
    out = {"file": name, "required": bool(required), "exists": bool(found)}
    if found is not None:
        try:
            out["bytes"] = int(found.stat().st_size)
        except Exception:
            pass
        sha = _asset_sha256(found)
        if sha:
            out["sha256"] = sha
        out["contentType"] = asset_sync_service.asset_content_type(found)
    return out

def sprite_contract_for_asset(data: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    role = str(asset.get("role") or "item")
    out = sprite_contract_for(role, int(asset.get("canvas") or 32))
    if role == "projectile":
        fam = infer_projectile_visual_family(data)
        out["projectileVisualFamily"] = fam
        out["promptPoseWords"] = family_prompt_clause(data, "projectile", int(asset.get("canvas") or 32))
    return out

def _compact_text(value: Any, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text[:limit]

def _parent_manifest_summary(parent: Any) -> dict[str, Any]:
    if not isinstance(parent, dict):
        return {}
    fp = parent.get("fingerprint") if isinstance(parent.get("fingerprint"), dict) else {}
    gd = parent.get("generatedData") if isinstance(parent.get("generatedData"), dict) else {}
    return {
        "name": parent.get("name") or fp.get("name"),
        "sourceMod": parent.get("sourceMod") or fp.get("sourceMod") or "Terraria",
        "internalName": parent.get("internalName") or fp.get("internalName"),
        "type": parent.get("type") or parent.get("id") or fp.get("type"),
        "damage": parent.get("damage") if parent.get("damage") is not None else fp.get("damage"),
        "damageClass": parent.get("damageClass") or fp.get("damageClass"),
        "useStyle": parent.get("useStyle") if parent.get("useStyle") is not None else fp.get("useStyle"),
        "useTime": parent.get("useTime") if parent.get("useTime") is not None else fp.get("useTime"),
        "generated": bool(gd),
        "generatedId": gd.get("id") if gd else None,
    }

def _asset_manifest_entry(data: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    role = str(asset.get("role") or "asset")
    path_value = asset.get("path") or asset.get("file")
    desc = _asset_descriptor(path_value, bool(asset.get("required"))) or {"required": bool(asset.get("required")), "exists": False}
    out = {
        "role": role,
        "assetId": asset.get("assetId"),
        "canvas": int(asset.get("canvas") or 32),
        "required": bool(asset.get("required")),
        "status": asset.get("status"),
        "assetMode": asset.get("assetMode"),
        "assetDecisionBy": asset.get("assetDecisionBy"),
        "skipReason": asset.get("skipReason"),
        "handledBy": asset.get("handledBy") or "visual_asset_pipeline",
        "authoringPolicy": asset.get("authoringPolicy") or "ai_primary_non_procedural",
        "prompt": _compact_text(asset.get("prompt"), 520),
        "file": desc.get("file"),
        "exists": bool(desc.get("exists")),
        "bytes": desc.get("bytes"),
        "sha256": desc.get("sha256"),
        "contentType": desc.get("contentType"),
        "contract": sprite_contract_for_asset(data, asset),
    }
    return {k: v for k, v in out.items() if v not in (None, "", [])}

def write_visual_manifest(data: dict[str, Any], plan: list[dict[str, Any]]) -> None:
    try:
        mid = str(data.get("id") or "sprite")
        path = SPRITE_DIR / f"{mid}_asset_manifest.json"
        visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
        gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
        attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
        clean_assets = [_asset_manifest_entry(data, asset) for asset in plan if isinstance(asset, dict)]
        vanilla_hitbox_damage = (
            int(float(gameplay.get("damage") or 0)) > 0
            and int(float(gameplay.get("useStyle") or 0)) > 0
            and str(gameplay.get("kind") or data.get("category") or "").strip().lower() not in {"ammo", "accessory", "material", "furniture"}
            and not (bool(attack.get("enabled")) and bool(attack.get("disableItemMeleeHitbox")))
        )
        manifest = {
            "schema": "infini.visual.assets.v2",
            "version": APP_VERSION,
            "pipelineProfile": VISUAL_PIPELINE_PROFILE,
            "recipe": {
                "id": data.get("id"),
                "recipeKey": data.get("recipeKey"),
                "name": data.get("name"),
                "category": data.get("category"),
                "tags": data.get("tags") if isinstance(data.get("tags"), list) else [],
            },
            "gameplay": {
                "kind": gameplay.get("kind"),
                "damageClass": gameplay.get("damageClass"),
                "damage": gameplay.get("damage"),
                "useStyle": gameplay.get("useStyle"),
                "useTime": gameplay.get("useTime"),
                "preferredCanvasSize": visual.get("preferredCanvasSize"),
            },
            "attack": {
                # Backcompat field. Semantics: generated runtime executor, not
                # "can this item deal vanilla Terraria contact damage".
                "enabled": bool(attack.get("enabled")),
                "runtimeExecutorEnabled": bool(attack.get("enabled")),
                "customAttackEnabled": bool(attack.get("enabled")),
                "vanillaItemHitboxDamage": bool(vanilla_hitbox_damage),
                "damagePath": (
                    "generated_executor_plus_vanilla_hitbox" if bool(attack.get("enabled")) and vanilla_hitbox_damage
                    else "generated_runtime_executor" if bool(attack.get("enabled"))
                    else "vanilla_item_hitbox" if vanilla_hitbox_damage
                    else "utility_or_non_damaging"
                ),
                "pattern": attack.get("pattern") or attack.get("attackPattern"),
                "runtimeFamily": attack.get("runtimeFamily"),
                "weaponFamily": attack.get("weaponFamily"),
                "projectileWidth": attack.get("projectileWidth"),
                "projectileHeight": attack.get("projectileHeight"),
                "projectileScale": attack.get("projectileScale"),
                "effectiveProjectileCanvas": effective_projectile_canvas(data) if attack.get("enabled") else None,
            },
            "parents": [_parent_manifest_summary(data.get("parentA")), _parent_manifest_summary(data.get("parentB"))],
            "visualIntent": {
                "palette": visual.get("palette"),
                "requiredAnchors": visual.get("requiredAnchors"),
                "itemSilhouetteContract": visual.get("itemSilhouetteContract") or visual.get("silhouetteContract") or visual.get("shapeContract"),
                "styleGuide": _compact_text(visual.get("styleGuide"), 520),
                "imagePrompt": _compact_text(visual.get("imagePrompt"), 520),
                "projectileImagePrompt": _compact_text(visual.get("projectileImagePrompt") or attack.get("projectileSpritePrompt"), 520),
            },
            "projectileVisualFamily": infer_projectile_visual_family(data),
            "authoringPolicy": "ai_primary_non_procedural",
            "assets": clean_assets,
        }
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        data.setdefault("visual", {})["assetManifestPath"] = str(path.resolve())
        data.setdefault("debug", {})["visualAssetManifest"] = str(path.resolve())
    except Exception as e:
        data.setdefault("debug", {})["visualManifestError"] = repr(e)

def compact_visual_words(value: Any, limit: int = 180) -> str:
    text = str(value or "").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:limit]

def build_projectile_image_prompt(data: dict[str, Any]) -> str:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    pg = data.get("projectileGenome") if isinstance(data.get("projectileGenome"), dict) else {}
    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    projectile_canvas = effective_projectile_canvas(data)
    shape = attack.get("projectileShape") or pg.get("shape") or (data.get("presentationGenome", {}).get("projectileVisual", {}) if isinstance(data.get("presentationGenome"), dict) else {}).get("shape") or "custom projectile"
    trail = attack.get("projectileTrail") or pg.get("trail") or "readable small trail"
    impact = attack.get("projectileImpact") or pg.get("impact") or "small impact"
    motion = attack.get("projectileMotion") or pg.get("motionFeel") or attack.get("movement") or "distinct motion"
    palette = visual.get("palette") or (data.get("presentationGenome", {}).get("palette") if isinstance(data.get("presentationGenome"), dict) else []) or [attack.get("primaryColorName") or "white"]
    palette_words = ", ".join(str(x).replace("_", " ") for x in palette[:6] if str(x).strip())
    anchors = visual.get("requiredAnchors") or []
    anchor_words = ", ".join(str(x) for x in anchors[:5] if str(x).strip())
    return ", ".join([
        "pixel art projectile sprite for a Terraria-like mod",
        sprite_background_positive_clause(),
        "single projectile only, no item card, no player, no scene",
        f"readable projectile silhouette filling the useful area of a {projectile_canvas}x{projectile_canvas} sprite target",
        "limited palette, crisp hard edges",
        family_prompt_clause(data, "projectile", projectile_canvas),
        f"projectile shape: {compact_visual_words(shape, 90)}",
        f"motion feel: {compact_visual_words(motion, 90)}",
        f"trail identity: {compact_visual_words(trail, 90)}",
        f"impact theme: {compact_visual_words(impact, 90)}",
        f"item fantasy: {compact_visual_words(concept.get('fantasy') or data.get('name'), 120)}",
        f"must echo: {anchor_words}" if anchor_words else "must have a unique non-generic silhouette",
        f"palette: {palette_words}" if palette_words else "palette: readable high contrast",
    ])

def build_impact_image_prompt(data: dict[str, Any]) -> str:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    pg = data.get("projectileGenome") if isinstance(data.get("projectileGenome"), dict) else {}
    impact = attack.get("projectileImpact") or pg.get("impact") or attack.get("impactStyle") or "small magical hit flash"
    expire = pg.get("onExpireVisual") or attack.get("impactStyle") or "short-lived puff"
    color = attack.get("primaryColorName") or "white"
    return ", ".join([
        "pixel art impact flash sprite for a Terraria-like projectile",
        sprite_background_positive_clause(),
        "small effect burst only, no weapon, no character, no scene",
        "readable 16x16 to 32x32 effect silhouette",
        "limited particles, crisp pixels",
        role_contract_prompt_clause("impact", IMPACT_SPRITE_CANVAS),
        f"impact: {compact_visual_words(impact, 120)}",
        f"miss or expire residue: {compact_visual_words(expire, 120)}",
        f"main color: {str(color).replace('_',' ')}",
    ])

def build_child_image_prompt(data: dict[str, Any]) -> str:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    child = attack.get("secondaryProjectileShape") or attack.get("secondaryMaterial") or attack.get("projectileFamily") or "tiny echo mote related to the item"
    color = attack.get("primaryColorName") or ", ".join(str(x) for x in (visual.get("palette") or [])[:3]) or "white"
    return ", ".join([
        "pixel art child projectile sprite for a Terraria-like mod",
        sprite_background_positive_clause(),
        "one tiny echo spark/mote only, no item card, no player, no scene",
        "readable 12x12 to 24x24 silhouette",
        "crisp hard pixels, limited palette",
        role_contract_prompt_clause("child", CHILD_SPRITE_CANVAS),
        f"child/echo identity: {compact_visual_words(child, 140)}",
        f"parent item fantasy: {compact_visual_words(concept.get('fantasy') or data.get('name'), 120)}",
        f"main color: {str(color).replace('_',' ')}",
    ])

def build_field_image_prompt(data: dict[str, Any]) -> str:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    field = " ".join(str(attack.get(k) or "") for k in ["impactStyle", "projectileImpact", "visualMode"])
    color = attack.get("primaryColorName") or "white"
    return ", ".join([
        "pixel art ground field/trap/rune/cloud sprite for a Terraria-like mod",
        sprite_background_positive_clause(),
        "flat magical field effect only, no item, no character, no scene",
        "readable 24x24 to 32x32 silhouette, can be rune circle, small cloud, puddle, trap mark, or dust patch",
        "crisp pixels, limited particles",
        role_contract_prompt_clause("field", FIELD_SPRITE_CANVAS),
        f"field/trap identity: {compact_visual_words(field, 180)}",
        f"item fantasy: {compact_visual_words(concept.get('fantasy') or data.get('name'), 120)}",
        f"main color: {str(color).replace('_',' ')}",
    ])

def apply_visual_director(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any]) -> dict[str, Any]:
    """v0.3.9: LLM art director pass.

    The planner writes the toy. This pass turns that toy into a sprite asset pack:
    item icon, projectile, child/echo, impact and field/trap. It is deliberately
    separate from balance so the art prompt is not rebuilt into generic bolts.
    """
    if not (USE_LLM and VISUAL_DIRECTOR_LLM and is_llm_planner(data)):
        return data
    if VISUAL_ASSET_MODE not in {"full", "all", "projectile", "visualpack", "assetpack"}:
        return data
    try:
        concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
        attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
        visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
        payload = {
            "task": "Create a coherent pixel-art visual asset pack for this generated Terraria-like toy. Do not change gameplay stats.",
            "zImageAssumption": "For Z-Image Turbo, write PE-style final visual descriptions: preserve subject, quantity, action, state, colors and material identity; describe composition and texture as objective visual facts; do not rely on a negative prompt.",
            "rules": [
                "Return one JSON object; no markdown or analysis.",
                "Build role-separated assets, not one copied generic prompt.",
                "Each sprite prompt describes one pixel asset on solid #ff00ff, not a scene.",
                "Item icon for a usable gear result should read as one handheld/carriable object; furniture/placeable parents may appear as parts or integrated cues, not automatically as a full placed tile scene.",
                "Projectile sprite prompt describes the moving hit object texture; preserve weird authored forms, but do not change gameplay delivery/runtime in art text.",
                "Impact sprite prompt is effect-only: dust, smoke, sparks, fragments, flash, ring, splash or debris burst; do not describe a persistent weapon/item/furniture body there.",
                "Palette is foreground-only; do not list #ff00ff/background/canvas as material.",
                "One core sprite per role; code animates it.",
                "Distinct roles should look distinct when present.",
                "Choose asset modes yourself. Prompt text is not demand; only mode=baked_sprite requests a PNG.",
                "Ordinary melee, arrows/bullets, and simple hits usually use particle_vfx or none for impact.",
                "Use ParticleLibrary/Dust/runtime VFX for sparks, dust, glints, smoke, small bursts, trails, and simple fields. Use baked_sprite only for a real separate body/decal/rune/cloud/child entity.",
                "Keep the fantasy visible; avoid generic sword/wand/orb/bolt collapse.",
                "Use named foreground colors and concrete shape/material words.",
                "Keep the object large in frame along at least one axis; no frame/border wording.",
                "Projectile prompts preserve the authored object; use canonical gameplay view only when supported by object or parent projectile facts.",
                "Projectile prompts describe the moving hit texture; do not change gameplay/delivery based on visual words.",
                "Impact prompts describe only a short hit/expire effect: burst, puff, ring, splash, dust, sparks, shards, or fragments. Do not draw the item/weapon/furniture body inside impact.",
                "Effects are accents unless authored as the body.",
                "Z-Image prompts: subject first, then shape, materials, palette, and minimal sprite constraints.",
                "For item icons, write one itemSilhouetteContract sentence: concrete proportions/parts/readability for this exact generated object; do not use a generic weapon class label alone.",
                "No SD tags, negative-prompt blocks, masterpiece/8K/meta labels.",
                "If exact text must appear, quote it; otherwise use no text/logos/UI marks.",
                "Tethered/returning/harpoon sprites: compact moving body plus optional short local rope/chain attachment, not a full-canvas line.",
                "Do not force literal parent silhouettes into every asset; draw the authored final object.",
                "Write short VFX intent lines as plain visual hints, not code.",
                "VFX hints may use scale/tempo/material words, but no numeric particle counts.",
            ],
            "item": {
                "name": data.get("name"),
                "tooltip": data.get("tooltip"),
                "category": data.get("category"),
                "parents": [name_of(a), name_of(b)],
                "concept": concept,
                "runtimeAffordance": data.get("runtimeAffordance") if isinstance(data.get("runtimeAffordance"), dict) else {},
                "attack": {k: attack.get(k) for k in [
                    "delivery", "weaponFamily", "projectileFamily", "ammoKind",
                    "projectileShape", "projectileMotion", "projectileRotation", "projectileTrail", "projectileImpact", "secondaryProjectileShape", "secondaryMaterial", "effect", "onHit", "movement"
                ]},
                "existingVisual": {k: visual.get(k) for k in ["objectType", "requiredAnchors", "palette", "imagePrompt", "projectileImagePrompt", "impactImagePrompt"]},
            },
            "requiredJsonShape": {
                "visualKit": {
                    "styleGuide": "shared art direction in one sentence",
                    "palette": ["named colors"],
                    "silhouetteSummary": "main readable shape",
                    "itemSilhouetteContract": "one sentence: exact item icon proportions, required readable parts, and forbidden near-miss silhouettes for this generated object",
                    "itemIconPrompt": "item sprite prompt",
                    "heldSpritePrompt": "held sprite prompt or same as item",
                    "projectileSpritePrompt": "projectile sprite prompt",
                    "childSpritePrompt": "child/spark/mote prompt or empty",
                    "impactSpritePrompt": "hit/expire prompt",
                    "fieldSpritePrompt": "field/trap/rune/cloud prompt or empty",
                    "bakedAssets": {"projectile": {"mode": "none|particle_vfx|baked_sprite", "prompt": "only if baked_sprite", "reason": "short"}, "impact": {"mode": "none|particle_vfx|baked_sprite", "prompt": "only if baked_sprite", "reason": "short"}, "child": {"mode": "none|particle_vfx|baked_sprite", "prompt": "only if baked_sprite", "reason": "short"}, "field": {"mode": "none|particle_vfx|baked_sprite", "prompt": "only if baked_sprite", "reason": "short"}},
                    "assetModes": {"projectile": "none|particle_vfx|baked_sprite", "impact": "none|particle_vfx|baked_sprite", "child": "none|particle_vfx|baked_sprite", "field": "none|particle_vfx|baked_sprite"},
                    "projectileAssetMode": "none|particle_vfx|baked_sprite",
                    "impactAssetMode": "none|particle_vfx|baked_sprite",
                    "childAssetMode": "none|particle_vfx|baked_sprite",
                    "fieldAssetMode": "none|particle_vfx|baked_sprite",
                    "vfxIntent": "max 12 words: overall runtime VFX intent, e.g. large impact burst, short ragged trail",
                    "projectileVfx": "max 10 words: travel/active VFX hint",
                    "impactVfx": "max 10 words: hit/expire VFX hint",
                    "childVfx": "max 10 words: child/echo VFX hint, or empty string",
                    "fieldVfx": "max 10 words: field/trap VFX hint, or empty string",
                    "vfxScaleHint": "one of tiny, small, normal, large, huge; visual scale may differ from projectile size",
                    "vfxRhythmHint": "one of slow, normal, snappy, delayed, pulsing",
                    "vfxMaterialHints": ["3-8 plain words: smoke, shards, sparks, cloth, goo, frost, star, shadow, etc."],
                    "vfxAvoid": "short note about what VFX should avoid, or empty string",
                    "animationPlan": ["short visible beats, e.g. launch, travel, hit, expire"],
                    "assetDependencies": ["which gameplay event uses which asset"],
                    "qualityNotes": ["how to keep silhouettes distinct in game"],
                    "negativePrompt": "empty for Z-Image; optional only for non-Z-Image"
                }
            }
        }
        model_name = resolve_llm_model()
        req = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You direct pixel-art assets for Z-Image in a Terraria-like generated-item mod. Write concise final visual descriptions, not SD/negative-prompt recipes. Preserve authored subject, count, action, state, colors, and materials. Do not add unauthored glow, magic, energy, child motes, or material effects. Return one JSON object."},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
            ],
            "temperature": _env_float("INFINI_VISUAL_DIRECTOR_TEMPERATURE", 0.42, 0.0, 1.2),
            "max_tokens": visual_director_max_tokens(),
            "response_format": llm_json_response_format("infini_visual_director"),
        }
        raw = llm_chat_json(req, timeout=env_int("INFINI_LLM_TIMEOUT", 95))
        content = raw["choices"][0]["message"]["content"]
        obj = parse_first_valid_llm_json(content)
        kit = obj.get("visualKit") if isinstance(obj, dict) and isinstance(obj.get("visualKit"), dict) else obj if isinstance(obj, dict) else {}
        if not isinstance(kit, dict):
            return data
        # v0.4.49: keep the manifest honest too.  The old code mapped sanitized prompts
        # into visual/attack, but left visualKit itself with side-view/halo/dark-background
        # wording, making debug manifests look worse than the actual generated prompt.
        for prompt_key, role_hint in [
            ("itemIconPrompt", "item"),
            ("heldSpritePrompt", "item"),
            ("projectileSpritePrompt", "projectile"),
            ("childSpritePrompt", "child"),
            ("impactSpritePrompt", "impact"),
            ("fieldSpritePrompt", "field"),
            ("negativePrompt", "generic"),
        ]:
            if kit.get(prompt_key):
                cleaned = strip_conflicting_sprite_prompt_bits(kit.get(prompt_key) or "")
                cleaned = sanitize_projectile_family_prompt(data, role_hint, cleaned)
                cleaned = role_visual_prompt_guard(role_hint, cleaned, data)
                if cleaned:
                    kit[prompt_key] = cleaned
        for text_key in ["styleGuide", "silhouetteSummary", "itemSilhouetteContract", "silhouetteContract", "shapeContract", "itemShapeContract", "vfxIntent", "projectileVfx", "impactVfx", "childVfx", "vfxAvoid"]:
            if kit.get(text_key):
                kit[text_key] = sanitize_projectile_family_prompt(data, "projectile" if "projectile" in text_key.lower() else "item", str(kit.get(text_key)))[:700]
        data["visualKit"] = kit
        # Preserve explicit model decisions about whether a role needs a baked PNG.
        # build_visual_asset_plan() treats GUI flags as allow-gates, not force-generate.
        mode_map = kit.get("assetModes") if isinstance(kit.get("assetModes"), dict) else {}
        normalized_modes = {}
        for role in ["projectile", "impact", "child", "field"]:
            mode = _asset_mode_from_value(mode_map.get(role) if isinstance(mode_map, dict) else "") or _asset_mode_from_value(kit.get(f"{role}AssetMode")) or _asset_mode_from_value(kit.get(f"{role}SpriteMode"))
            if mode:
                normalized_modes[role] = mode
                kit[f"{role}AssetMode"] = mode
        baked_assets = kit.get("bakedAssets") if isinstance(kit.get("bakedAssets"), dict) else {}
        if isinstance(baked_assets, dict):
            clean_baked = {}
            for role in ["projectile", "impact", "child", "field"]:
                spec = baked_assets.get(role)
                if isinstance(spec, dict):
                    mode = _asset_mode_from_value(spec.get("mode") or spec.get("assetMode") or spec.get("enabled"))
                    prompt = strip_conflicting_sprite_prompt_bits(spec.get("prompt") or spec.get("spritePrompt") or spec.get("imagePrompt") or "")
                    if mode:
                        clean_baked[role] = {"mode": mode}
                        if prompt:
                            prompt = sanitize_projectile_family_prompt(data, role, prompt)
                            prompt = role_visual_prompt_guard(role, prompt, data)
                            clean_baked[role]["prompt"] = prompt[:1400]
                        if spec.get("reason"):
                            clean_baked[role]["reason"] = str(spec.get("reason"))[:240]
                        normalized_modes[role] = mode
                        kit[f"{role}AssetMode"] = mode
            if clean_baked:
                kit["bakedAssets"] = clean_baked
                kit["assetModes"] = normalized_modes
        if normalized_modes:
            kit["assetModes"] = normalized_modes
        apply_visual_asset_runtime_gates(data, kit)
        data.setdefault("debug", {})["visualDirectorRawOutput"] = content[:10000]
        data["debug"]["visualDirectorModel"] = model_name
        visual = data.setdefault("visual", {})
        attack = data.setdefault("attack", {})
        if kit.get("palette"):
            cleaned_palette = sanitize_visual_palette(kit.get("palette") or [], limit=8)
            if cleaned_palette:
                kit["palette"] = cleaned_palette
                visual["palette"] = cleaned_palette
            else:
                kit.pop("palette", None)
        neg = str(kit.get("negativePrompt") or "").strip()
        if neg:
            visual["negativePrompt"] = neg
        mapping = [
            (visual, "imagePrompt", "itemIconPrompt"),
            (visual, "projectileImagePrompt", "projectileSpritePrompt"),
            (visual, "impactImagePrompt", "impactSpritePrompt"),
            (visual, "childImagePrompt", "childSpritePrompt"),
            (visual, "fieldImagePrompt", "fieldSpritePrompt"),
            (attack, "projectileSpritePrompt", "projectileSpritePrompt"),
            (attack, "impactSpritePrompt", "impactSpritePrompt"),
            (attack, "childSpritePrompt", "childSpritePrompt"),
            (attack, "fieldSpritePrompt", "fieldSpritePrompt"),
        ]
        for dst, dst_key, src_key in mapping:
            val = strip_conflicting_sprite_prompt_bits(kit.get(src_key) or "")
            if val:
                dst[dst_key] = val[:1400]
        if kit.get("silhouetteSummary"):
            visual["silhouetteSummary"] = str(kit.get("silhouetteSummary"))[:700]
        for contract_key in ("itemSilhouetteContract", "silhouetteContract", "shapeContract", "itemShapeContract"):
            if kit.get(contract_key):
                visual["itemSilhouetteContract"] = str(kit.get(contract_key))[:700]
                break
        # v0.3.16: dirty VFX selector hints authored in the same visual-director pass as Z-Image prompts.
        for src_key, dst_key in [
            ("vfxIntent", "vfxIntent"),
            ("projectileVfx", "projectileVfx"),
            ("impactVfx", "impactVfx"),
            ("childVfx", "childVfx"),
            ("fieldVfx", "fieldVfx"),
            ("vfxScaleHint", "vfxScaleHint"),
            ("vfxRhythmHint", "vfxRhythmHint"),
            ("vfxAvoid", "vfxAvoid"),
        ]:
            val = str(kit.get(src_key) or "").strip()
            if val:
                visual[dst_key] = val[:700]
                attack[dst_key] = val[:700]
        if kit.get("animationPlan"):
            attack["visualAnimationPlan"] = _stringish(kit.get("animationPlan"), "")[:1200]
        if kit.get("assetDependencies"):
            visual["assetDependencies"] = _stringish(kit.get("assetDependencies"), "")[:1400]
        if kit.get("qualityNotes"):
            visual["qualityNotes"] = _stringish(kit.get("qualityNotes"), "")[:1400]
        if kit.get("vfxMaterialHints"):
            material_hints = [str(x).strip() for x in (kit.get("vfxMaterialHints") or []) if str(x).strip()][:12]
            if material_hints:
                visual["vfxMaterialHints"] = material_hints
                attack["vfxMaterialHints"] = material_hints
        data["attack"] = attack
        data["visual"] = visual
    except Exception as e:
        data.setdefault("debug", {})["visualDirectorError"] = repr(e)
        log_event("warn", "visual director failed", {"error": repr(e), "trace": traceback.format_exc()})
    return data

def _validation_reasons(validation: dict[str, Any] | None) -> list[str]:
    if not isinstance(validation, dict):
        return []
    return [str(x) for x in (validation.get("reasons") or [])]


def refit_processed_sprite_to_contract(path: str, asset_id: str, canvas: int, role: str, validation: dict[str, Any] | None) -> str:
    """Local no-regeneration salvage for fit-only sprite failures.

    If Z-Image produced a good subject but postprocess made the core silhouette a
    few pixels too small, crop the transparent bbox, scale it up with nearest-neighbor
    pixels, and center it back on the target canvas. Fatal alpha/key failures are not
    repaired here.
    """
    reasons = _validation_reasons(validation)
    if not any("silhouette_too_small" in r or "core_silhouette_too_small" in r or "effect_silhouette_too_small" in r for r in reasons):
        return ""
    if Image is None or not path or not Path(path).exists():
        return ""
    try:
        img = Image.open(path).convert("RGBA")
        stats = validation.get("stats") if isinstance(validation, dict) and isinstance(validation.get("stats"), dict) else {}
        bbox_stats = validation.get("bboxStats") if isinstance(validation, dict) and isinstance(validation.get("bboxStats"), dict) else {}
        bbox = bbox_stats.get("core_bbox") or bbox_stats.get("effect_bbox") or stats.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            bbox = img.getbbox()
        if not bbox:
            return ""
        left, top, right, bottom = [int(round(float(x))) for x in bbox]
        left = max(0, min(img.width - 1, left)); top = max(0, min(img.height - 1, top))
        right = max(left + 1, min(img.width, right)); bottom = max(top + 1, min(img.height, bottom))
        crop = img.crop((left, top, right, bottom))
        spec = bbox_stats.get("spec") if isinstance(bbox_stats.get("spec"), dict) else {}
        margin = int(spec.get("marginPx") or (2 if canvas >= 48 else 1))
        target = int(spec.get("targetLongAxisPx") or round(canvas * (0.84 if role == "projectile" else 0.88)))
        target = max(1, min(canvas - margin * 2, target))
        long_axis = max(crop.width, crop.height)
        if long_axis <= 0:
            return ""
        scale = target / float(long_axis)
        max_scale = min((canvas - 2 * margin) / max(1, crop.width), (canvas - 2 * margin) / max(1, crop.height))
        scale = max(1.0, min(scale, max_scale))
        if scale <= 1.01:
            return ""
        new_w = max(1, min(canvas - 2 * margin, int(round(crop.width * scale))))
        new_h = max(1, min(canvas - 2 * margin, int(round(crop.height * scale))))
        resampling = getattr(getattr(Image, "Resampling", Image), "NEAREST", 0)
        resized = crop.resize((new_w, new_h), resampling)
        out = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
        out.alpha_composite(resized, ((canvas - new_w) // 2, (canvas - new_h) // 2))
        out_path = SPRITE_DIR / f"{asset_id}_refit.png"
        out.save(out_path)
        return str(out_path)
    except (OSError, ValueError, TypeError, AttributeError):
        return ""


def generate_visual_asset(data: dict[str, Any], role: str, prompt: str, negative: str, asset_id: str, canvas: int) -> tuple[str, str, float, str]:
    """Generate one role-separated visual asset with retry-on-technical-fail.

    v0.3.9: no fake best-of-N judging by default. We generate one image, run local
    alpha/crop/fit validation, and retry only when the PNG is technically broken.
    """
    base_prompt = normalize_asset_prompt(data, role, prompt, canvas)
    negative = negative or asset_negative_prompt(role)
    data.setdefault("debug", {})[f"{role}FinalPrompt"] = base_prompt[:1800]
    data.setdefault("debug", {})[f"{role}AuthoringPolicy"] = "ai_primary_non_procedural"
    if IMAGE_BACKEND == "off":
        return "", "", 0.0, "prompt_only"
    attempts: list[dict[str, Any]] = []
    max_attempts = max(1, int(SPRITE_RETRIES) + 1)
    last_path = ""
    last_raw_path = ""
    last_score = 0.0
    last_validation: dict[str, Any] | None = None
    for attempt in range(max_attempts):
        attempt_id = asset_id if attempt == 0 else f"{asset_id}_retry{attempt}"
        attempt_prompt = base_prompt if attempt == 0 else build_retry_prompt_from_validation(base_prompt, last_validation or {}, role, attempt, canvas)
        trace_event("prompt", f"IMAGE:{role}", f"{IMAGE_BACKEND} {role} prompt attempt {attempt}", {
            "assetId": asset_id, "attemptId": attempt_id, "attempt": attempt, "role": role,
            "backend": IMAGE_BACKEND, "canvas": canvas, "spriteRetries": SPRITE_RETRIES,
        }, prompt=attempt_prompt, negative=negative)
        try:
            if IMAGE_BACKEND == "a1111":
                variants = generate_a1111(attempt_prompt, negative, attempt_id, canvas)
            elif IMAGE_BACKEND == "comfyui":
                variants = generate_comfyui(attempt_prompt, negative, attempt_id)
            elif IMAGE_BACKEND in {"sdcpp", "stablediffusioncpp", "stable-diffusion.cpp", "stable_diffusion_cpp"}:
                variants = generate_sdcpp(attempt_prompt, negative, attempt_id, canvas)
            elif IMAGE_BACKEND in {"image_api", "api_image", "openai_image", "openai_images", "openai_compat_image"}:
                variants = generate_image_api(attempt_prompt, negative, attempt_id, canvas)
            else:
                variants = [] if VISUAL_STRICT_AI_AUTHORSHIP else [visual_asset_pipeline.generate_procedural_asset(data, role, variant=0, canvas_size=canvas, sprite_dir=SPRITE_DIR, image_cls=Image, image_draw_cls=ImageDraw)]
            variants = [p for p in variants if p and Path(p).exists()]
            if not variants:
                attempts.append({"attempt": attempt, "ok": False, "status": "no_raw_image"})
                continue
            best, score = pick_best_sprite(variants, role, canvas)
            final_path = postprocess_sprite(best, attempt_id, canvas, role)
            validation = validate_processed_sprite(final_path, role)
            refit_path = ""
            refit_validation: dict[str, Any] | None = None
            if not validation.get("ok") and not sprite_validation_fatal(validation):
                refit_path = refit_processed_sprite_to_contract(final_path, attempt_id, canvas, role, validation)
                if refit_path:
                    refit_validation = validate_processed_sprite(refit_path, role)
                    if refit_validation.get("ok"):
                        data.setdefault("debug", {})[f"{role}SpriteRefit"] = json.dumps({
                            "from": str(Path(final_path).resolve()),
                            "to": str(Path(refit_path).resolve()),
                            "before": validation,
                            "after": refit_validation,
                        }, ensure_ascii=False)
                        final_path = refit_path
                        validation = refit_validation
            attempt_row = {"attempt": attempt, "raw": best, "final": final_path, "score": score, "validation": validation}
            if refit_path:
                attempt_row["refit"] = {"path": refit_path, "validation": refit_validation}
            attempts.append(attempt_row)
            last_path = final_path
            last_raw_path = best
            last_score = float(score)
            last_validation = validation if isinstance(validation, dict) else None
            if validation.get("ok") or not sprite_validation_fatal(validation):
                if attempt != 0:
                    canonical = SPRITE_DIR / f"{asset_id}.png"
                    try:
                        import shutil
                        shutil.copyfile(final_path, canonical)
                        final_path = str(canonical)
                    except Exception:
                        pass
                data.setdefault("debug", {})[f"{role}SpriteValidation"] = json.dumps(attempts, ensure_ascii=False)
                if not validation.get("ok"):
                    data.setdefault("debug", {})[f"{role}SpriteAcceptedWithWarnings"] = json.dumps(validation, ensure_ascii=False)
                status = sprite_status_from_raw_path(best, IMAGE_BACKEND, invalid=not bool(validation.get("ok")))
                trace_event("step", f"IMAGE:{role}", "sprite accepted", {
                    "assetId": asset_id, "attempt": attempt, "raw": best, "final": str(Path(final_path).resolve()),
                    "score": last_score, "status": status, "validation": validation,
                })
                return str(Path(final_path).resolve()), f"/sprite/{Path(final_path).name}", last_score, status
        except Exception as e:
            attempts.append({"attempt": attempt, "ok": False, "error": repr(e)})
            data.setdefault("debug", {})[f"{role}SpriteError"] = repr(e)
            trace_event("error", f"IMAGE:{role}", "sprite generation attempt failed", {"assetId": asset_id, "attempt": attempt, "backend": IMAGE_BACKEND}, error=repr(e))
            log_event("warn", f"{role} sprite generation attempt failed", {"attempt": attempt, "error": repr(e), "trace": traceback.format_exc()})
    data.setdefault("debug", {})[f"{role}SpriteValidation"] = json.dumps(attempts, ensure_ascii=False)
    if last_path:
        data.setdefault("debug", {})[f"{role}InvalidGeneratedDiscarded"] = str(Path(last_path).resolve())
        # v0.4.49: strict AI authorship should prefer an imperfect AI-authored sprite
        # over an engine placeholder when the failure is only fit/crop strictness.
        # Fatal technical failures (magenta still present, no alpha, empty sprite) stay failed.
        reasons = []
        try:
            reasons = list((last_validation or {}).get("reasons") or [])
        except Exception:
            reasons = []
        fatal_tokens = (
            "empty_alpha_bbox",
            "magenta_key_background_left",
            "almost_no_transparency_after_bg_removal",
            "too_few_opaque_pixels",
            "very_dense_opaque_area",
            "pillow_unavailable_required",
        )
        fatal = any(any(tok in str(reason) for tok in fatal_tokens) for reason in reasons)
        if not fatal and Path(last_path).exists():
            data.setdefault("debug", {})[f"{role}InvalidGeneratedUsedAsWarn"] = json.dumps({
                "path": str(Path(last_path).resolve()),
                "reasons": reasons,
                "policy": "strict_ai_authorship_keep_imperfect_ai_sprite_not_placeholder",
            }, ensure_ascii=False)
            canonical = SPRITE_DIR / f"{asset_id}.png"
            try:
                import shutil
                if Path(last_path).resolve() != canonical.resolve():
                    shutil.copyfile(last_path, canonical)
                last_path = str(canonical)
            except Exception:
                pass
            return str(Path(last_path).resolve()), f"/sprite/{Path(last_path).name}", round(last_score, 3), "generated_warn_invalid"
    if VISUAL_ALLOW_PROCEDURAL_FALLBACK and not VISUAL_STRICT_AI_AUTHORSHIP:
        try:
            fallback = visual_asset_pipeline.generate_procedural_asset(data, role, variant=0, canvas_size=canvas, sprite_dir=SPRITE_DIR, image_cls=Image, image_draw_cls=ImageDraw)
            final = postprocess_sprite(fallback, asset_id, canvas, role)
            return str(Path(final).resolve()), f"/sprite/{Path(final).name}", 0.0, "fallback_after_failed_generation"
        except Exception as e:
            log_event("warn", f"{role} sprite procedural fallback failed", {"error": repr(e)})
    trace_event("error", f"IMAGE:{role}", "sprite generation failed completely", {"assetId": asset_id, "role": role, "backend": IMAGE_BACKEND, "attempts": attempts})
    log_event("warn", f"{role} sprite generation failed completely", {"role": role, "backend": IMAGE_BACKEND, "strictAiAuthorship": VISUAL_STRICT_AI_AUTHORSHIP})
    return "", "", round(last_score, 3), "failed"

def maybe_generate_visual_assets(data: dict[str, Any]) -> dict[str, Any]:
    """Generate a coherent visual asset pack.

    v0.3.9: one explicit plan drives all assets. The manifest is saved next to sprites,
    so debugging can answer: what did the author want, what did the visual director ask,
    what was generated, and what fell back.
    """
    data = maybe_generate_sprite(data)
    plan = build_visual_asset_plan(data)
    data.setdefault("debug", {})["visualAssetPlan"] = json.dumps(plan, ensure_ascii=False)
    if VISUAL_ASSET_MODE not in {"full", "projectile", "all", "visualpack", "assetpack"}:
        write_visual_manifest(data, plan)
        return data
    attack = data.setdefault("attack", {})
    if not isinstance(attack, dict) or not attack.get("enabled"):
        write_visual_manifest(data, plan)
        return data
    visual = data.setdefault("visual", {})

    for slot in plan:
        role = slot.get("role")
        if role == "item":
            slot["status"] = visual.get("spriteStatus", "")
            slot["path"] = visual.get("spritePath", "")
            slot["score"] = visual.get("visualJudgeScore", 0)
            continue
        if role not in {"projectile", "impact", "child", "field"}:
            continue
        if str(slot.get("status") or "").startswith("skipped_"):
            slot["path"] = ""
            slot["url"] = ""
            slot["score"] = 0.0
            continue
        prompt = str(slot.get("prompt") or "")
        canvas = int(slot.get("canvas") or 32)
        path, url, score, status = generate_visual_asset(data, role, prompt, asset_negative_prompt(role), str(slot.get("assetId") or (str(data.get("id")) + "_" + role)), canvas)
        # Store the actual backend prompt in the manifest/debug plan. The raw
        # visual-director prompt remains in visual/attack fields, but manifests
        # should show what was really sent after Z-Image PE cleanup.
        final_prompt = str(data.get("debug", {}).get(f"{role}FinalPrompt") or "")
        if final_prompt:
            slot["prompt"] = final_prompt
        slot["status"] = status
        slot["path"] = path
        slot["url"] = url
        slot["score"] = score
        key = role.capitalize()
        usable_path = bool(path) and status not in {"failed", "prompt_only", "placeholder", "generated_warn_invalid"}
        if role == "projectile":
            attack["projectileSpritePrompt"] = prompt
            attack["projectileSpriteStatus"] = status
            if usable_path:
                attack["projectileSpritePath"] = path; attack["projectileSpriteUrl"] = url; attack["projectileSpriteScore"] = score
            else:
                attack["projectileSpritePath"] = ""; attack["projectileSpriteUrl"] = ""; attack["projectileSpriteScore"] = 0.0
            visual["projectileImagePrompt"] = prompt
        elif role == "impact":
            attack["impactSpritePrompt"] = prompt
            attack["impactSpriteStatus"] = status
            if usable_path:
                attack["impactSpritePath"] = path; attack["impactSpriteUrl"] = url; attack["impactSpriteScore"] = score
            else:
                attack["impactSpritePath"] = ""; attack["impactSpriteUrl"] = ""; attack["impactSpriteScore"] = 0.0
            visual["impactImagePrompt"] = prompt
        elif role == "child":
            attack["childSpritePrompt"] = prompt
            attack["childSpriteStatus"] = status
            if usable_path:
                attack["childSpritePath"] = path; attack["childSpriteUrl"] = url; attack["childSpriteScore"] = score
            else:
                attack["childSpritePath"] = ""; attack["childSpriteUrl"] = ""; attack["childSpriteScore"] = 0.0
            visual["childImagePrompt"] = prompt
        elif role == "field":
            attack["fieldSpritePrompt"] = prompt
            attack["fieldSpriteStatus"] = status
            if usable_path:
                attack["fieldSpritePath"] = path; attack["fieldSpriteUrl"] = url; attack["fieldSpriteScore"] = score
            else:
                attack["fieldSpritePath"] = ""; attack["fieldSpriteUrl"] = ""; attack["fieldSpriteScore"] = 0.0
            visual["fieldImagePrompt"] = prompt
    data["attack"] = attack
    data["visual"] = visual
    write_visual_manifest(data, plan)
    return data


class VisualDeliveryBlocked(RuntimeError):
    """Fresh craft cannot be delivered because the mandatory visual asset is not usable."""


def _sprite_status_is_usable(status: Any) -> bool:
    s = str(status or "").strip().lower()
    return bool(s) and s not in {"failed", "prompt_only", "placeholder", "generated_warn_invalid", "skipped", "skipped_disabled_by_settings", "skipped_not_authored_baked"}


def _item_sprite_status_is_usable(status: Any) -> bool:
    s = str(status or "").strip().lower()
    if s == "generated_warn_invalid":
        return True
    return _sprite_status_is_usable(status)


def _asset_path_exists(path_value: Any) -> bool:
    text = str(path_value or "").strip()
    if not text:
        return False
    try:
        p = Path(text)
        if p.exists() and p.is_file():
            return True
        name = asset_sync_service.asset_filename_from_path(text)
        if not name:
            return False
        found = asset_sync_service.find_asset_file(name, sprite_dir=SPRITE_DIR, world_recipes_dir=WORLD_RECIPES_DIR)
        return bool(found and found.exists() and found.is_file())
    except Exception:
        return False


def visual_delivery_report(data: dict[str, Any]) -> dict[str, Any]:
    """Inspect the exact visual payload that will be sent to tML.

    This is a delivery gate, not an art critic: it verifies that required runtime
    paths point at usable files and that config does not accidentally fall back to a
    non-visual craft. Optional projectile/impact/child/field slots are reported but
    do not block unless they are marked required by the asset plan/manifest.
    """
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    problems: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if VISUAL_REQUIRE_ZIMAGE_BACKEND and not image_backend_is_zimage():
        problems.append({
            "code": "zimage_required_but_inactive",
            "message": "INFINI_VISUAL_REQUIRE_ZIMAGE_BACKEND=1, but the active image backend is not Z-Image/sd.cpp.",
            "imageBackend": IMAGE_BACKEND,
            "zImagePromptContract": ZIMAGE_PROMPT_CONTRACT,
        })

    item_status = str(visual.get("spriteStatus") or "")
    item_path = str(visual.get("spritePath") or "")
    item_exists = _asset_path_exists(item_path)
    item_ok = _item_sprite_status_is_usable(item_status) and item_exists
    if item_status.strip().lower() == "generated_warn_invalid" and item_exists:
        warnings.append({
            "code": "item_sprite_generated_warn_invalid",
            "status": item_status,
            "path": item_path,
            "message": "Mandatory item sprite exists but failed an art-quality validation; deliver it with warning instead of treating it as missing.",
        })
    if VISUAL_REQUIRE_ITEM_SPRITE and not item_ok:
        problems.append({
            "code": "required_item_sprite_missing",
            "message": "Generated item sprite is required, but no usable processed PNG is present.",
            "status": item_status,
            "path": item_path,
            "backend": IMAGE_BACKEND,
        })

    slots: list[dict[str, Any]] = [{
        "role": "item",
        "required": bool(VISUAL_REQUIRE_ITEM_SPRITE),
        "status": item_status,
        "path": item_path,
        "exists": _asset_path_exists(item_path),
        "usable": item_ok,
        "score": visual.get("visualJudgeScore"),
    }]
    for role, prefix in [
        ("projectile", "projectile"),
        ("impact", "impact"),
        ("child", "child"),
        ("field", "field"),
    ]:
        status = str(attack.get(f"{prefix}SpriteStatus") or "")
        path = str(attack.get(f"{prefix}SpritePath") or "")
        exists = _asset_path_exists(path)
        usable = _sprite_status_is_usable(status) and exists
        required = role == "projectile" and bool(attack.get("enabled")) and authored_asset_mode(data, "projectile") == "baked_sprite" and not runtime_plan(data)
        if required and not usable:
            problems.append({
                "code": f"required_{role}_sprite_missing",
                "message": f"Required {role} baked sprite is missing or unusable.",
                "status": status,
                "path": path,
            })
        elif status and not usable and status not in {"skipped_not_authored_baked", "skipped_disabled_by_settings"}:
            warnings.append({"code": f"optional_{role}_sprite_unusable", "status": status, "path": path})
        slots.append({
            "role": role,
            "required": required,
            "status": status,
            "path": path,
            "exists": exists,
            "usable": usable,
            "score": attack.get(f"{prefix}SpriteScore"),
            "assetMode": authored_asset_mode(data, role),
        })

    return {
        "ok": not problems,
        "requiredItemSprite": bool(VISUAL_REQUIRE_ITEM_SPRITE),
        "requireZImageBackend": bool(VISUAL_REQUIRE_ZIMAGE_BACKEND),
        "imageBackend": IMAGE_BACKEND,
        "zImageBackendActive": image_backend_is_zimage(),
        "strictAiAuthorship": bool(VISUAL_STRICT_AI_AUTHORSHIP),
        "proceduralFallbackAllowed": bool(VISUAL_ALLOW_PROCEDURAL_FALLBACK),
        "problems": problems,
        "warnings": warnings,
        "slots": slots,
        "manifestPath": visual.get("assetManifestPath"),
    }


def assert_visual_delivery_ready(data: dict[str, Any]) -> dict[str, Any]:
    report = visual_delivery_report(data)
    data.setdefault("debug", {})["visualDeliveryReport"] = json.dumps(report, ensure_ascii=False)
    if not report.get("ok"):
        first = (report.get("problems") or [{}])[0]
        raise VisualDeliveryBlocked(str(first.get("message") or first.get("code") or "visual_delivery_blocked"))
    return data

# =============================================================================
# Explicit pipeline dependencies
# =============================================================================
from infini_local.pipelines.pipeline_support import (
    Image,
    ImageDraw,
    APP_VERSION,
    BG_COLOR,
    BG_REMOVE_MODE,
    CHILD_ICON_TARGET_FILL,
    CHILD_SPRITE_CANVAS,
    FIELD_ICON_TARGET_FILL,
    FIELD_SPRITE_CANVAS,
    GENERATE_VARIANTS,
    IMAGE_BACKEND,
    IMPACT_ICON_TARGET_FILL,
    IMPACT_SPRITE_CANVAS,
    ITEM_ICON_TARGET_FILL,
    LLM_RUNTIME_AUTHORING,
    PROJECTILE_ICON_TARGET_FILL,
    PROJECTILE_SPRITE_CANVAS,
    REMOVE_BG,
    SDCPP_MODEL,
    SDCPP_SERVER_COMMAND_TEMPLATE,
    SDCPP_SERVER_EXTRA_ARGS,
    SPRITE_DIR,
    SPRITE_EFFECT_CORE_ALPHA_THRESHOLD,
    SPRITE_ITEM_CORE_ALPHA_THRESHOLD,
    SPRITE_RETRIES,
    USE_LLM,
    VISUAL_ALLOW_PROCEDURAL_FALLBACK,
    VISUAL_ASSET_MODE,
    VISUAL_DIRECTOR_LLM,
    VISUAL_GENERATE_CHILD_FIELD_IMAGES,
    VISUAL_GENERATE_IMPACT_IMAGES,
    VISUAL_GENERATE_PROJECTILE_IMAGES,
    VISUAL_PIPELINE_PROFILE,
    VISUAL_REQUIRE_ITEM_SPRITE,
    VISUAL_REQUIRE_ZIMAGE_BACKEND,
    VISUAL_STRICT_AI_AUTHORSHIP,
    WORLD_RECIPES_DIR,
    ZIMAGE_POSITIVE_ONLY,
    ZIMAGE_PROMPT_CONTRACT,
    _env_float,
    asset_sync_service,
    compact_zimage_asset_prompt,
    log_event,
    name_of,
    parse_first_valid_llm_json,
    runtime_plan,
    sanitize_image_prompt_background,
    sanitize_projectile_prompt_multiplicity,
    sanitize_visual_palette,
    sprite_status_from_raw_path,
    strip_conflicting_sprite_prompt_bits,
    tags_of,
    trace_event,
    visual_asset_pipeline,
    zimage_palette_sentence,
    zimage_pe_clean_text,
    zimage_text_policy_sentence,
)

from infini_local.pipelines.combine_pipeline import (
    _stringish,
    infer_projectile_visual_family,
    is_llm_planner,
    palette_from,
    required_anchors_from,
    size_profile_for,
    stage_profile_for,
)

from infini_local.pipelines.image_backend_pipeline import (
    generate_a1111,
    generate_comfyui,
    generate_image_api,
    generate_sdcpp,
)

from infini_local.pipelines.llm_authoring_pipeline import (
    llm_chat_json,
    llm_json_response_format,
    resolve_llm_model,
    visual_director_max_tokens,
)

from infini_local.pipelines.sprite_processing_pipeline import (
    build_retry_prompt_from_validation,
    pick_best_sprite,
    postprocess_sprite,
    sprite_validation_fatal,
    validate_processed_sprite,
)
