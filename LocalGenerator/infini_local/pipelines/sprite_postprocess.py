from __future__ import annotations

import traceback
from typing import Any

try:
    from PIL import Image, ImageEnhance
except Exception:
    Image = None
    ImageEnhance = None

from infini_local.core.config_bootstrap import SPRITE_DIR
from infini_local.core.env_utils import env_int
from infini_local.pipelines.pipeline_visual_config import (
    ALPHA_THRESHOLD,
    BG_REMOVE_MODE,
    CHROMA_TOLERANCE,
    DENOISE_STRAY_PIXELS,
    MAX_COLORS,
    PIXEL_POSTERIZE,
    REMOVE_BG,
    REQUIRE_PILLOW,
    SAVE_SPRITE_STAGES,
    SPRITE_CHROMA_DEFRINGE,
    SPRITE_DOWNSCALE_FILTER,
    SPRITE_MASTER_CANVAS,
    SPRITE_MAX_EDGE_TOUCH_PCT,
    SPRITE_MAX_OPAQUE_PCT,
    SPRITE_MIN_OPAQUE_PCT,
    SPRITE_PADDING,
    SPRITE_PREMULTIPLIED_RESIZE,
    SPRITE_PROCESSING_PROFILE,
)
from infini_local.services.visual_asset_pipeline import compact_zimage_asset_prompt
from infini_local.storage.trace_runtime import log_event
from infini_local.pipelines.sprite_geometry import (
    alpha_bbox_threshold,
    bbox_center,
    bbox_dims,
    bbox_expand,
    bbox_union,
    sprite_bbox_stats,
    sprite_principal_axis_stats,
)
from infini_local.pipelines.sprite_keyer import (
    apply_background_removal,
    chroma_like_rgb,
    estimate_sprite_key_profile,
    magenta_key_pixel_ratio,
    remove_nested_poster_card_background,
    remove_key_colored_holes,
    scrub_transparent_rgb,
)
from infini_local.pipelines.sprite_contracts import (
    chroma_rgb,
    image_backend_is_zimage,
    role_contract_prompt_clause,
    sprite_background_positive_clause,
    sprite_contract_for,
)

# AGENT MAP: sprite selection, alpha cleanup, resize/bake, validation/retry notes,
# and final postprocess orchestration.

# Fixed corpus-validated final color restore.  Native downscaling averages away a
# little luminance and chroma regardless of BOX/Bilinear/Bicubic/Lanczos.  A mild
# gamma lift restores shadow/midtone color while protecting hot highlights better
# than a raw brightness multiplier.  This is technical RGB compensation only:
# alpha, geometry, filter choice and role semantics remain untouched.
FINAL_COLOR_SATURATION = 1.08
FINAL_COLOR_GAMMA = 0.96
FINAL_COLOR_GAMMA_LUT = [
    max(0, min(255, int(round(255.0 * ((value / 255.0) ** FINAL_COLOR_GAMMA)))))
    for value in range(256)
]

def pick_best_sprite(paths: list[str], role: str = "item", canvas: int = 32) -> tuple[str, float]:
    if Image is None:
        return paths[0], 0.5
    best = paths[0]
    best_score = -9999.0
    spec = sprite_contract_for(role, canvas)
    target_fill = float(spec["targetFill"])
    for p in paths:
        try:
            img = Image.open(p).convert("RGBA")
            img = apply_background_removal(img)
            img = cleanup_alpha(img)
            img = denoise_alpha_singletons(img)
            s = sprite_bbox_stats(img, role, canvas)
            if not s.get("effect_bbox"):
                score = -999.0
            else:
                core_fill = float(s.get("core_fill") or 0.0)
                effect_fill = float(s.get("effect_fill") or 0.0)
                cx, cy = s.get("core_center_norm") or (0.5, 0.5)
                center_penalty = abs(cx - 0.5) + abs(cy - 0.5) if role in {"item", "equip_overlay"} else 0.0
                edge_ratio = edge_touch_ratio(img.getchannel("A"))
                fill_penalty = abs(core_fill - target_fill) * 2.1
                effect_penalty = max(0.0, effect_fill - 0.98) * 1.2
                edge_penalty = max(0.0, edge_ratio - float(spec.get("maxEdgeTouch") or 0.1)) * 3.0
                score = 1.0 - fill_penalty - effect_penalty - center_penalty - edge_penalty
            if score > best_score:
                best_score = score
                best = p
        except Exception:
            continue
    return best, round(max(0.0, min(1.0, best_score)), 3)

def save_stage(img: Any, sprite_id: str, stage: str) -> str:
    if not SAVE_SPRITE_STAGES or Image is None:
        return ""
    try:
        p = SPRITE_DIR / f"{sprite_id}_stage_{stage}.png"
        img.save(p)
        return str(p)
    except Exception:
        return ""

def cleanup_alpha(img: Any) -> Any:
    if Image is None:
        return img
    img = img.convert("RGBA")
    thr = max(0, min(255, int(ALPHA_THRESHOLD)))
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a <= thr:
                px[x, y] = (0, 0, 0, 0)
            elif a < 255:
                px[x, y] = (r, g, b, 255)
    return img

def denoise_alpha_singletons(img: Any) -> Any:
    if Image is None or not DENOISE_STRAY_PIXELS:
        return img
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    kill = []
    for y in range(1, h-1):
        for x in range(1, w-1):
            if px[x, y][3] == 0:
                continue
            n = 0
            for yy in (y-1, y, y+1):
                for xx in (x-1, x, x+1):
                    if (xx, yy) != (x, y) and px[xx, yy][3] > 0:
                        n += 1
            if n <= 1:
                kill.append((x, y))
    for x, y in kill:
        px[x, y] = (0, 0, 0, 0)
    return img

def defringe_chroma_edges(img: Any) -> Any:
    """Remove only technical chroma-key edge leftovers, without judging the art shape.

    Some SD/Z-Image outputs keep #ff00ff-ish pixels glued to the foreground after
    floodfill because antialias/diffusion noise made them non-exact.  This pass is
    deliberately conservative: it only targets chroma-like pixels adjacent to already
    transparent background.
    """
    if Image is None or not SPRITE_CHROMA_DEFRINGE:
        return img
    img = img.convert("RGBA")
    target = chroma_rgb()
    px = img.load()
    w, h = img.size
    tol = max(int(CHROMA_TOLERANCE) + 42, 72)
    kill: list[tuple[int, int]] = []
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a <= 0:
                continue
            magentaish = chroma_like_rgb((r, g, b), tolerance=tol, strict=True)
            if not magentaish:
                continue
            has_transparent_neighbor = False
            for yy in (y - 1, y, y + 1):
                for xx in (x - 1, x, x + 1):
                    if xx == x and yy == y:
                        continue
                    if 0 <= xx < w and 0 <= yy < h and px[xx, yy][3] <= 0:
                        has_transparent_neighbor = True
                        break
                if has_transparent_neighbor:
                    break
            if has_transparent_neighbor:
                kill.append((x, y))
    for x, y in kill:
        px[x, y] = (0, 0, 0, 0)
    return img

def neutralize_chroma_edge_colors(img: Any) -> Any:
    """Repair final-bake chroma fringe without eating white pixels.

    Only exterior, transparency-adjacent chroma-like pixels are touched.  The pass
    first tries to recolor them from nearby non-chroma foreground pixels and deletes
    only orphan key leftovers with no trustworthy neighbor.
    """
    if Image is None or not SPRITE_CHROMA_DEFRINGE:
        return img
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    tol = max(int(CHROMA_TOLERANCE) + 18, 58)

    def good_sample(xx: int, yy: int) -> tuple[int, int, int] | None:
        if not (0 <= xx < w and 0 <= yy < h):
            return None
        nr, ng, nb, na = px[xx, yy]
        if na <= 0:
            return None
        if chroma_like_rgb((nr, ng, nb), tolerance=tol):
            return None
        return (nr, ng, nb)

    updates: list[tuple[int, int, tuple[int, int, int, int]]] = []
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a <= 0:
                continue
            if not chroma_like_rgb((r, g, b), tolerance=tol):
                continue

            has_transparent_neighbor = False
            samples: list[tuple[int, int, int]] = []
            for yy in (y - 1, y, y + 1):
                for xx in (x - 1, x, x + 1):
                    if xx == x and yy == y:
                        continue
                    if not (0 <= xx < w and 0 <= yy < h):
                        continue
                    if px[xx, yy][3] <= 0:
                        has_transparent_neighbor = True
                    sample = good_sample(xx, yy)
                    if sample is not None:
                        samples.append(sample)

            if not has_transparent_neighbor:
                continue

            if not samples:
                for yy in range(max(0, y - 2), min(h, y + 3)):
                    for xx in range(max(0, x - 2), min(w, x + 3)):
                        if xx == x and yy == y:
                            continue
                        sample = good_sample(xx, yy)
                        if sample is not None:
                            samples.append(sample)

            if samples:
                rr = sum(v[0] for v in samples) // len(samples)
                gg = sum(v[1] for v in samples) // len(samples)
                bb = sum(v[2] for v in samples) // len(samples)
                updates.append((x, y, (rr, gg, bb, a)))
            else:
                updates.append((x, y, (0, 0, 0, 0)))

    for x, y, rgba in updates:
        px[x, y] = rgba
    return img

def sprite_resample_filter(stage: str = "final") -> Any:
    if Image is None:
        return 0
    mode = (SPRITE_DOWNSCALE_FILTER or "box").lower()
    if mode in {"lanczos", "antialias"}:
        return Image.Resampling.LANCZOS
    if mode in {"bicubic"}:
        return Image.Resampling.BICUBIC
    if mode in {"bilinear"}:
        return Image.Resampling.BILINEAR
    # BOX is the production default for fake pixel-art rendered at high resolution: it
    # averages the source footprint into coherent small clusters without sharpening halos.
    return Image.Resampling.BOX

def resize_rgba_premultiplied(img: Any, size: tuple[int, int], resample: Any) -> Any:
    """Resize RGBA without bleeding hidden RGB from transparent/keyed pixels.

    PIL's straight-alpha RGBA resize can leak the magenta-key RGB from transparent
    pixels into edges.  Premultiplying RGB by alpha before resize and unpremultiplying
    after is a purely technical quality fix.  Implemented with Pillow only: no numpy
    dependency for the local generator installer.
    """
    if Image is None:
        return img
    img = img.convert("RGBA")
    if not SPRITE_PREMULTIPLIED_RESIZE:
        return img.resize(size, resample)
    r, g, b, a = img.split()
    # Premultiply in integer space.
    pr = Image.new("L", img.size, 0)
    pg = Image.new("L", img.size, 0)
    pb = Image.new("L", img.size, 0)
    rp, gp, bp, ap = r.load(), g.load(), b.load(), a.load()
    prp, pgp, pbp = pr.load(), pg.load(), pb.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            av = ap[x, y]
            prp[x, y] = (rp[x, y] * av + 127) // 255
            pgp[x, y] = (gp[x, y] * av + 127) // 255
            pbp[x, y] = (bp[x, y] * av + 127) // 255
    pr = pr.resize(size, resample)
    pg = pg.resize(size, resample)
    pb = pb.resize(size, resample)
    a2 = a.resize(size, resample)
    out = Image.merge("RGBA", (pr, pg, pb, a2)).convert("RGBA")
    px = out.load()
    ow, oh = out.size
    for y in range(oh):
        for x in range(ow):
            rr, gg, bb, aa = px[x, y]
            if aa <= 0:
                px[x, y] = (0, 0, 0, 0)
            else:
                px[x, y] = (min(255, (rr * 255 + aa // 2) // aa), min(255, (gg * 255 + aa // 2) // aa), min(255, (bb * 255 + aa // 2) // aa), aa)
    return out

def prepare_sprite_master(img: Any, sprite_id: str, target_size: int, role: str = "item") -> Any:
    """Full-res/master-first normalisation.  Does not invent or redraw art.

    raw -> bg remove -> chroma defringe -> alpha cleanup -> crop visible bbox ->
    fit to a larger transparent master canvas.  Final 32/48/64 bakes are produced
    from this master, not from an already degraded tiny sprite.
    """
    img = img.convert("RGBA")
    final_size = max(16, min(96, int(target_size or 32)))
    spec_final = sprite_contract_for(role, final_size)
    effect_bbox = alpha_bbox_threshold(img, 1)
    core_bbox = alpha_bbox_threshold(img, int(spec_final.get("coreAlphaThreshold") or 1)) or effect_bbox
    if effect_bbox is None and core_bbox is None:
        master_size = max(final_size, min(512, max(128, int(SPRITE_MASTER_CANVAS or 256))))
        return Image.new("RGBA", (master_size, master_size), (0, 0, 0, 0))

    crop_bbox = bbox_union(effect_bbox, core_bbox)
    src_w, src_h = img.size
    # A small percentage pad keeps high-res antialias/key-edge data for clean downscale.
    crop_pad = max(int(SPRITE_PADDING), int(round(max(src_w, src_h) * 0.012)), int(spec_final.get("cropPadPx") or 0))
    crop_bbox = bbox_expand(crop_bbox, crop_pad, img.size)
    crop = img.crop(crop_bbox) if crop_bbox else img
    crop = scrub_transparent_rgb(crop)

    master_size = int(SPRITE_MASTER_CANVAS or 256)
    master_size = max(final_size * 3, min(768, max(96, master_size)))
    # Do not upscale tiny source crops too aggressively; but most model outputs are 512+.
    core_bbox2 = alpha_bbox_threshold(crop, int(spec_final.get("coreAlphaThreshold") or 1)) or alpha_bbox_threshold(crop, 1)
    effect_bbox2 = alpha_bbox_threshold(crop, 1)
    core_w, core_h = bbox_dims(core_bbox2)
    effect_w, effect_h = bbox_dims(effect_bbox2)
    core_long = max(1, max(core_w, core_h))
    effect_long = max(1, max(effect_w, effect_h))
    target_fill = float(spec_final.get("targetFill") or 0.88)
    max_effect_fill = min(0.98, float(spec_final.get("maxEffectLongAxisPx") or final_size) / max(1, final_size))
    target_core_long = max(1, int(round(master_size * target_fill)))
    max_effect_long = max(target_core_long, int(round(master_size * max_effect_fill)))
    scale = min(target_core_long / core_long, max_effect_long / effect_long)
    # Avoid accidental super-upscaling of small weird assets; this is processing, not redraw.
    scale = min(scale, 8.0)
    new_w = max(1, int(round(crop.size[0] * scale)))
    new_h = max(1, int(round(crop.size[1] * scale)))
    resample = sprite_resample_filter("master")
    resized = resize_rgba_premultiplied(crop, (new_w, new_h), resample)
    master = Image.new("RGBA", (master_size, master_size), (0, 0, 0, 0))
    x = (master_size - new_w) // 2
    y = (master_size - new_h) // 2
    master.alpha_composite(resized, (x, y))

    # Inventory and equipment overlays benefit from centering; projectile/VFX composition may have
    # authored directional or multipart placement and must not be re-authored here.
    if role in {"item", "equip_overlay"}:
        recentered = sprite_bbox_stats(master, role, master_size)
        core_bbox_canvas = recentered.get("core_bbox")
        if core_bbox_canvas is not None:
            cx, cy = bbox_center(core_bbox_canvas)
            dx = int(round(master_size / 2.0 - cx))
            dy = int(round(master_size / 2.0 - cy))
            if dx or dy:
                shifted = Image.new("RGBA", (master_size, master_size), (0, 0, 0, 0))
                shifted.alpha_composite(master, (dx, dy))
                master = shifted
    return scrub_transparent_rgb(master)

def bake_sprite_from_master(master: Any, target_size: int, role: str = "item") -> Any:
    final_size = max(16, min(96, int(target_size or 32)))
    master = scrub_transparent_rgb(master.convert("RGBA"))
    if master.size != (final_size, final_size):
        resample = sprite_resample_filter("final")
        img = resize_rgba_premultiplied(master, (final_size, final_size), resample)
    else:
        img = master
    # Final game PNG wants stable opaque/transparent pixels; do it after resizing, not before.
    img = cleanup_alpha(img)
    if role in {"item", "equip_overlay"}:
        img = denoise_alpha_singletons(img)
    img = palette_cleanup(img, role)
    img = cleanup_alpha(img)
    # Safe final rescue pass: recolor or remove only true chroma leftovers touching
    # transparency. This is much less destructive than the old blanket magenta wipe.
    img = neutralize_chroma_edge_colors(img)
    img = cleanup_alpha(img)
    img = restore_downscaled_sprite_color(img)
    return scrub_transparent_rgb(img)


def restore_downscaled_sprite_color(img: Any) -> Any:
    """Restore mild final-stage RGB loss without changing alpha or geometry."""
    if Image is None or ImageEnhance is None:
        return img
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    rgb = ImageEnhance.Color(rgba.convert("RGB")).enhance(FINAL_COLOR_SATURATION)
    rgb = rgb.point(FINAL_COLOR_GAMMA_LUT * 3)
    restored = rgb.convert("RGBA")
    restored.putalpha(alpha)
    return scrub_transparent_rgb(restored)

def alpha_stats(img: Any) -> dict[str, Any]:
    if Image is None:
        return {}
    img = img.convert("RGBA")
    alpha = img.getchannel("A")
    hist = alpha.histogram()
    total = max(1, img.size[0] * img.size[1])
    transparent = sum(hist[:1])
    partial = sum(hist[1:255])
    opaque = hist[255]
    return {
        "mode": img.mode,
        "size": list(img.size),
        "transparentPct": round(transparent / total, 4),
        "partialPct": round(partial / total, 4),
        "opaquePct": round(opaque / total, 4),
        "hasAlpha": transparent > 0 or partial > 0,
        "bbox": list(alpha.getbbox() or []),
    }


def canonicalize_projectile_forward_axis(img: Any, role: str = "projectile") -> tuple[Any, dict[str, Any]]:
    """Normalize an elongated projectile's local forward axis before final downscale.

    Local +X is only a texture-space convention. Terraria still rotates the sprite
    toward any world-space velocity. Near-radial sprites remain untouched; head/tail
    flipping is allowed only for a strongly tapered silhouette.
    """
    if Image is None:
        return img, {"beforeAngleDegrees": 0.0, "afterAngleDegrees": 0.0, "anisotropy": 1.0, "rotated": False, "flipped": False}
    normalized_role = str(role or "").strip().lower()
    source = img.convert("RGBA")
    before = sprite_principal_axis_stats(source, 8)
    evidence: dict[str, Any] = {
        "beforeAngleDegrees": float(before.get("angleDegrees") or 0.0),
        "afterAngleDegrees": float(before.get("angleDegrees") or 0.0),
        "anisotropy": float(before.get("anisotropy") or 1.0),
        "rotated": False,
        "flipped": False,
        "leftEndpointPixels": 0,
        "rightEndpointPixels": 0,
    }
    if normalized_role not in {"projectile", "child"} or evidence["anisotropy"] < 2.5:
        return source, evidence

    working = source
    angle = evidence["beforeAngleDegrees"]
    if abs(angle) > 3.0:
        working = source.rotate(
            angle,
            resample=Image.Resampling.BICUBIC,
            expand=True,
            fillcolor=(0, 0, 0, 0),
        )
        working = scrub_transparent_rgb(working)
        evidence["rotated"] = True

    # PCA is undirected. Infer head/tail only for highly elongated, strongly
    # tapered silhouettes (arrows/spears/shards), never coins or broad fire blobs.
    if evidence["anisotropy"] >= 8.0:
        alpha = working.getchannel("A")
        bbox = alpha_bbox_threshold(working, 8)
        if bbox is not None:
            x0, y0, x1, y1 = bbox
            edge_width = max(2, int(round((x1 - x0) * 0.24)))
            left = sum(
                1
                for y in range(y0, y1)
                for x in range(x0, min(x1, x0 + edge_width))
                if int(alpha.getpixel((x, y))) >= 8
            )
            right = sum(
                1
                for y in range(y0, y1)
                for x in range(max(x0, x1 - edge_width), x1)
                if int(alpha.getpixel((x, y))) >= 8
            )
            evidence["leftEndpointPixels"] = left
            evidence["rightEndpointPixels"] = right
            if left > 0 and right > 0 and left < right * 0.82:
                working = working.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                evidence["flipped"] = True

    after = sprite_principal_axis_stats(working, 8)
    evidence["afterAngleDegrees"] = float(after.get("angleDegrees") or 0.0)
    return working, evidence


def fit_to_canvas(img: Any, target_size: int, role: str = "item") -> Any:
    img = img.convert("RGBA")
    spec = sprite_contract_for(role, target_size)
    effect_bbox = alpha_bbox_threshold(img, 1)
    core_bbox = alpha_bbox_threshold(img, int(spec.get("coreAlphaThreshold") or 1)) or effect_bbox
    if effect_bbox is None and core_bbox is None:
        final_size = max(16, min(96, int(target_size or 32)))
        return Image.new("RGBA", (final_size, final_size), (0, 0, 0, 0))
    crop_bbox = bbox_union(effect_bbox, core_bbox)
    crop_bbox = bbox_expand(crop_bbox, max(int(SPRITE_PADDING), int(spec.get("cropPadPx") or 0)), img.size)
    if crop_bbox:
        img = img.crop(crop_bbox)
    effect_bbox = alpha_bbox_threshold(img, 1)
    core_bbox = alpha_bbox_threshold(img, int(spec.get("coreAlphaThreshold") or 1)) or effect_bbox
    crop_w, crop_h = img.size
    core_w, core_h = bbox_dims(core_bbox)
    effect_w, effect_h = bbox_dims(effect_bbox)
    core_long = max(1, max(core_w, core_h))
    effect_long = max(1, max(effect_w, effect_h))
    target_long = max(1, int(spec.get("targetLongAxisPx") or max(1, target_size - 2)))
    max_effect_long = max(target_long, int(spec.get("maxEffectLongAxisPx") or target_size))
    scale_core = target_long / core_long
    scale_effect = max_effect_long / effect_long
    scale = min(scale_core, scale_effect)
    new_w = max(1, int(round(crop_w * scale)))
    new_h = max(1, int(round(crop_h * scale)))
    resized = resize_rgba_premultiplied(img, (new_w, new_h), sprite_resample_filter("fit"))
    final_size = max(16, min(96, int(target_size or 32)))
    canvas = Image.new("RGBA", (final_size, final_size), (0, 0, 0, 0))
    x = (final_size - new_w) // 2
    y = (final_size - new_h) // 2
    canvas.alpha_composite(resized, (x, y))
    if role in {"item", "equip_overlay"}:
        recentered = sprite_bbox_stats(canvas, role, final_size)
        core_bbox_canvas = recentered.get("core_bbox")
        if core_bbox_canvas is not None:
            cx, cy = bbox_center(core_bbox_canvas)
            dx = int(round(final_size / 2.0 - cx))
            dy = int(round(final_size / 2.0 - cy))
            if dx or dy:
                shifted = Image.new("RGBA", (final_size, final_size), (0, 0, 0, 0))
                shifted.alpha_composite(canvas, (dx, dy))
                canvas = shifted
    return canvas

def palette_cleanup(img: Any, role: str = "item") -> Any:
    if Image is None or not PIXEL_POSTERIZE:
        return img
    normalized_role = str(role or "item").strip().lower()
    if normalized_role in {"impact", "field"}:
        return img
    img = img.convert("RGBA")
    alpha = img.getchannel("A")
    if normalized_role == "child":
        colors = max(32, min(48, int(MAX_COLORS)))
    else:
        colors = max(24, min(40, int(MAX_COLORS)))
    try:
        # Quantize only the visible bbox.  Quantizing the whole transparent canvas lets
        # transparent black dominate the palette and wastes colors that should go to the
        # actual item.
        bb = alpha.getbbox()
        if not bb:
            return img
        crop = img.crop(bb).convert("RGBA")
        crop_alpha = crop.getchannel("A")
        rgb = Image.new("RGB", crop.size, (0, 0, 0))
        rgb.paste(crop, mask=crop_alpha)
        pal_crop = rgb.quantize(colors=colors, method=Image.Quantize.MEDIANCUT).convert("RGBA")
        pal_crop.putalpha(crop_alpha)
        out = Image.new("RGBA", img.size, (0, 0, 0, 0))
        out.alpha_composite(pal_crop, (bb[0], bb[1]))
        return out
    except Exception:
        return img

def edge_touch_ratio(alpha: Any) -> float:
    if Image is None:
        return 0.0
    w, h = alpha.size
    if w <= 0 or h <= 0:
        return 1.0
    top = sum(1 for x in range(w) if alpha.getpixel((x, 0)) > 0)
    bottom = sum(1 for x in range(w) if alpha.getpixel((x, h - 1)) > 0)
    left = sum(1 for y in range(h) if alpha.getpixel((0, y)) > 0)
    right = sum(1 for y in range(h) if alpha.getpixel((w - 1, y)) > 0)
    return (top + bottom + left + right) / max(1, (w * 2 + h * 2))

def significant_alpha_component_areas(alpha: Any, *, alpha_threshold: int = 32) -> list[int]:
    """Return 8-connected visible component areas, largest first.

    This is role geometry only: it never inspects names, prompts, colors, or item types.
    Eight-way connectivity preserves diagonal pixel-art joins while still exposing a
    detached second body that would animate as a broken inventory sprite.
    """
    if Image is None:
        return []
    w, h = alpha.size
    pixels = alpha.load()
    visible = {(x, y) for y in range(h) for x in range(w) if int(pixels[x, y]) > alpha_threshold}
    areas: list[int] = []
    while visible:
        seed = visible.pop()
        stack = [seed]
        area = 0
        while stack:
            x, y = stack.pop()
            area += 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    neighbor = (x + dx, y + dy)
                    if neighbor in visible:
                        visible.remove(neighbor)
                        stack.append(neighbor)
        areas.append(area)
    return sorted(areas, reverse=True)


def validate_processed_sprite(
    path: str,
    role: str = "item",
    *,
    topology: str = "",
    part_count_min: int = 0,
    part_count_max: int = 0,
) -> dict[str, Any]:
    """Technical validation only. No art taste, no tier judging, no VLM."""
    if Image is None:
        return {"ok": False, "reasons": ["pillow_unavailable_required"], "warnings": [], "stats": {}, "role": role}
    img = Image.open(path).convert("RGBA")
    alpha = img.getchannel("A")
    stats = alpha_stats(img)
    reasons: list[str] = []
    warnings: list[str] = []
    w, h = img.size
    role = (role or "item").lower()
    spec = sprite_contract_for(role, max(w, h))
    bb = sprite_bbox_stats(img, role, max(w, h))
    principal_axis = sprite_principal_axis_stats(img, int(spec.get("coreAlphaThreshold") or 8))
    bb["principalAxis"] = principal_axis
    effect_bbox = bb.get("effect_bbox")
    core_bbox = bb.get("core_bbox")
    core_long = int(bb.get("core_long_axis") or 0)
    effect_long = int(bb.get("effect_long_axis") or 0)
    component_areas = significant_alpha_component_areas(alpha)
    visible_component_area = sum(component_areas)
    significant_components = [area for area in component_areas if area >= max(6, int(visible_component_area * 0.08))]
    bb["alphaComponentAreas"] = component_areas[:12]
    bb["significantAlphaComponents"] = len(significant_components)
    normalized_topology = str(topology or "unconstrained").strip().lower()
    if normalized_topology not in {"connected", "multipart_touching", "multipart_separated", "unconstrained"}:
        normalized_topology = "unconstrained"
    if normalized_topology == "unconstrained" and role == "item":
        warnings.append("missing_authored_topology")
    # Component count/connectivity is diagnostic only. Authored topology still guides
    # the Image model prompt, but Python must not retry or reject a usable PNG merely
    # because alpha islands do not match a code-side interpretation of the artwork.
    if not effect_bbox or not core_bbox:
        reasons.append("empty_alpha_bbox")
    else:
        edge_ratio = edge_touch_ratio(alpha)
        min_long = int(spec.get("minLongAxisPx") or 1)
        max_long = int(spec.get("maxLongAxisPx") or max(w, h))
        if core_long < min_long:
            reasons.append(f"core_silhouette_too_small:{core_long}px<{min_long}px")
        if core_long > max_long:
            reasons.append(f"core_silhouette_too_large:{core_long}px>{max_long}px")
        if effect_long > int(spec.get("maxEffectLongAxisPx") or max(w, h)):
            reasons.append(f"effect_extent_too_large:{effect_long}px")
        if edge_ratio > float(spec.get("maxEdgeTouch") or SPRITE_MAX_EDGE_TOUCH_PCT):
            reasons.append(f"object_touches_edges:{edge_ratio:.3f}")
        key_ratio = magenta_key_pixel_ratio(img)
        if key_ratio > 0.025:
            reasons.append(f"magenta_key_background_left:{key_ratio:.3f}")
        if stats.get("transparentPct", 0) < 0.03:
            reasons.append("almost_no_transparency_after_bg_removal")
        area_ratio = float(bb.get("core_area_ratio") or 0.0)
        if role == "item" and area_ratio < 0.18:
            warnings.append(f"item_diagonal_or_thin_core:{area_ratio:.3f}")
        if role in {"projectile", "child"} and area_ratio < 0.08:
            warnings.append(f"thin_projectile_core:{area_ratio:.3f}")
        if (
            role in {"projectile", "child"}
            and float(principal_axis.get("anisotropy") or 1.0) >= 2.5
            and float(principal_axis.get("horizontalErrorDegrees") or 0.0) > 12.0
        ):
            reasons.append(
                "projectile_forward_axis_misaligned:"
                f"{float(principal_axis.get('horizontalErrorDegrees') or 0.0):.1f}deg"
            )
        if stats.get("partialPct", 0) > 0.25:
            warnings.append("many_partial_alpha_pixels")
        if stats.get("opaquePct", 0) < SPRITE_MIN_OPAQUE_PCT:
            reasons.append(f"too_few_opaque_pixels:{stats.get('opaquePct')}")
        if stats.get("opaquePct", 0) > SPRITE_MAX_OPAQUE_PCT and role != "impact":
            # A nearly solid final sprite usually means the model drew the item on a
            # white/pink card/poster inside the magenta key. Treat it as a technical
            # background-removal failure, not as an acceptable warning, otherwise the
            # game receives an opaque square instead of a transparent Terraria sprite.
            reasons.append(f"very_dense_opaque_area:{stats.get('opaquePct')}")
    return {
        "ok": not reasons,
        "reasons": reasons,
        "warnings": warnings,
        "stats": stats,
        "bboxStats": bb,
        "role": role,
        "topology": normalized_topology,
        "partCountMin": max(0, int(part_count_min or 0)),
        "partCountMax": max(0, int(part_count_max or 0)),
    }


def technical_validation_score(validation: dict[str, Any] | None) -> float:
    """Score only final alpha/background/geometry validation, never visual taste.

    Candidate-selection scores describe a raw variant before postprocess and must not
    be presented as the quality of the delivered PNG. Fatal technical failures score
    zero; accepted geometry findings and warnings reduce the score modestly.
    """
    if not isinstance(validation, dict):
        return 0.0
    if sprite_validation_fatal(validation):
        return 0.0
    reasons = [str(x) for x in (validation.get("reasons") or []) if str(x).strip()]
    warnings = [str(x) for x in (validation.get("warnings") or []) if str(x).strip()]
    score = 1.0 - min(0.60, 0.12 * len(reasons)) - min(0.20, 0.03 * len(warnings))
    return round(max(0.20, min(1.0, score)), 3)


def sprite_validation_fatal(validation: dict[str, Any] | None) -> bool:
    """Only fatal technical failures should force a retry/fallback.

    v0.4.49 relaxes visual authoring: a readable but imperfect AI sprite should not be
    retried just because a local silhouette heuristic dislikes the exact shape. Retry is
    reserved for broken alpha/key/background/empty cases.
    """
    if not isinstance(validation, dict):
        return False
    reasons = [str(x) for x in (validation.get("reasons") or [])]
    fatal_tokens = (
        "empty_alpha_bbox",
        "magenta_key_background_left",
        "almost_no_transparency_after_bg_removal",
        "too_few_opaque_pixels",
        "very_dense_opaque_area",
        "pillow_unavailable_required",
        "projectile_forward_axis_misaligned",
    )
    return any(any(tok in reason for tok in fatal_tokens) for reason in reasons)

def validation_retry_notes(validation: dict[str, Any] | None, role: str = "item") -> str:
    if not isinstance(validation, dict):
        return ""
    reasons = [str(x) for x in (validation.get("reasons") or []) if str(x).strip()]
    bbox = validation.get("bboxStats") if isinstance(validation.get("bboxStats"), dict) else {}
    notes: list[str] = []
    mapping = [
        ("core_silhouette_too_small", "make the main subject noticeably larger inside the frame"),
        ("core_silhouette_too_large", "shrink the subject slightly so a thin safety border remains"),
        ("effect_extent_too_large", "keep glows or residue tighter to the subject"),
        ("object_touches_edges", "do not touch the image edges; leave a thin border"),
        ("magenta_key_background_left", "keep the magenta key as a perfectly flat background and do not paint the key color into the object"),
        ("almost_no_transparency_after_bg_removal", "keep the background perfectly flat magenta with a cleanly separated object"),
        ("too_few_opaque_pixels", "use a more solid readable silhouette with less emptiness"),
        ("very_dense_opaque_area", "remove any white/pink poster card or inner background; only the actual sprite body may remain outside the magenta key"),
        ("empty_alpha_bbox", "draw the authored role asset, not an empty image"),
        ("projectile_forward_axis_misaligned", "use canonical local +X: leading tip/nose screen-right and tail/trail screen-left; runtime rotates this axis to world velocity"),
    ]
    for raw, msg in mapping:
        if any(str(r).startswith(raw) for r in reasons):
            notes.append(msg)
    core_long = bbox.get("core_long_axis") if isinstance(bbox, dict) else None
    if core_long:
        notes.append(f"current visible core long axis is about {core_long}px after postprocess; improve role readability")
    return "; ".join(dict.fromkeys(notes))[:700]

def build_retry_prompt_from_validation(prompt: str, validation: dict[str, Any] | None, role: str, attempt: int, canvas: int) -> str:
    bg = sprite_background_positive_clause()
    contract = role_contract_prompt_clause(role, canvas)
    notes = validation_retry_notes(validation, role)
    if image_backend_is_zimage():
        retry_parts = [
            str(prompt or ""),
            f"Revision {attempt}: preserve the same exact {role} subject, quantity, action, state, materials, and colors.",
            f"Composition correction: keep the authored {role} components within the sprite bounds and make their physical arrangement clearer.",
            str(contract),
            "Background correction: use a flat #ff00ff magenta chroma-key background.",
            ("Technical correction: " + notes) if notes else "",
        ]
        return compact_zimage_asset_prompt(retry_parts, role, limit=env_int("INFINI_ZIMAGE_RETRY_PROMPT_LIMIT", 2200))
    extra = (
        f" STRICT RETRY {attempt}: draw the authored {role} physical arrangement, keep visible components within the sprite bounds, make it readable, "
        f"{contract}, {bg}, "
        "no checkerboard, no UI, no text, no scene, no ground, no shadow, no crop"
    )
    if notes:
        extra += ", fix these technical issues: " + notes
    return (str(prompt or "") + ", " + extra)[:2800]

def strengthen_prompt_for_retry(prompt: str, role: str, attempt: int) -> str:
    return build_retry_prompt_from_validation(prompt, {}, role, attempt, 32)[:2600]

def postprocess_sprite(
    path: str,
    sprite_id: str,
    target_size: int = 32,
    role: str = "unknown",
    *,
    topology: str = "",
    part_count_min: int = 0,
    part_count_max: int = 0,
) -> str:
    """Return processed sprite path; on postprocess failure, return the original path.

    The caller should treat the return value as a usable asset path, not as a nullable
    success flag. Failed cleanup preserves the raw generated image instead of dropping
    the sprite entirely.
    """
    if Image is None:
        raise RuntimeError("Pillow is required for sprite postprocess/validation")
    try:
        raw = Image.open(path).convert("RGBA")
        save_stage(raw, sprite_id, "00_raw")

        # Master-first pipeline: all destructive technical work happens before the
        # final downscale.  This does not change semantics; it only removes the
        # requested key background, normalizes the canvas and bakes a clean PNG.
        key_profile = estimate_sprite_key_profile(raw)
        bg_removed = apply_background_removal(raw)
        # Single supported background-removal protocol: sprite_keyer.  The following
        # steps are technical cleanup only, not an alternate semantic/image mode.
        # Layer 2 removes key-colored pockets that are enclosed by the generated object
        # and therefore unreachable by contiguous border flood-fill.
        bg_removed = remove_key_colored_holes(bg_removed, key_profile)
        bg_removed = defringe_chroma_edges(bg_removed)
        bg_removed = cleanup_alpha(bg_removed)
        # Layer 3 removes AI-drawn white/pink poster cards inside the requested key.
        # This keeps retry pressure low and prevents opaque square sprites from reaching the game.
        if role in {"item", "equip_overlay"}:
            bg_removed = remove_nested_poster_card_background(bg_removed, role)
        bg_removed = cleanup_alpha(bg_removed)
        if role in {"item", "equip_overlay"}:
            bg_removed = denoise_alpha_singletons(bg_removed)
        bg_removed = scrub_transparent_rgb(bg_removed)
        save_stage(bg_removed, sprite_id, "10_sprite_keyer_fullres")
        bg_removed, forward_axis = canonicalize_projectile_forward_axis(bg_removed, role)
        if forward_axis.get("rotated") or forward_axis.get("flipped"):
            save_stage(bg_removed, sprite_id, "15_projectile_forward_axis")

        master = prepare_sprite_master(bg_removed, sprite_id, target_size, role)
        save_stage(master, sprite_id, "20_master_norm")
        final = bake_sprite_from_master(master, target_size, role)
        save_stage(final, sprite_id, "30_baked_final")

        out = SPRITE_DIR / f"{sprite_id}.png"
        final.save(out)
        stats = alpha_stats(final)
        validation = validate_processed_sprite(
            str(out), role, topology=topology,
            part_count_min=part_count_min, part_count_max=part_count_max,
        )
        log_event("info", "sprite postprocessed", {"spriteId": sprite_id, "source": str(path), "out": str(out), "targetSize": target_size, "removeBg": REMOVE_BG,
                        "processingProfile": SPRITE_PROCESSING_PROFILE, "masterCanvas": SPRITE_MASTER_CANVAS, "downscaleFilter": SPRITE_DOWNSCALE_FILTER,
                        "premultipliedResize": SPRITE_PREMULTIPLIED_RESIZE, "chromaDefringe": SPRITE_CHROMA_DEFRINGE,
                        "requirePillow": REQUIRE_PILLOW,
                        "pillowAvailable": Image is not None, "bgMode": BG_REMOVE_MODE, "alpha": stats,
                        "projectileForwardAxis": forward_axis, "validation": validation})
        return str(out)
    except Exception as e:
        log_event("warn", "postprocess failed", {"path": path, "error": repr(e), "trace": traceback.format_exc()})
        return path

__all__ = [
    "pick_best_sprite",
    "save_stage",
    "cleanup_alpha",
    "denoise_alpha_singletons",
    "defringe_chroma_edges",
    "neutralize_chroma_edge_colors",
    "sprite_resample_filter",
    "resize_rgba_premultiplied",
    "prepare_sprite_master",
    "bake_sprite_from_master",
    "restore_downscaled_sprite_color",
    "alpha_stats",
    "fit_to_canvas",
    "palette_cleanup",
    "edge_touch_ratio",
    "canonicalize_projectile_forward_axis",
    "validate_processed_sprite",
    "technical_validation_score",
    "sprite_validation_fatal",
    "validation_retry_notes",
    "build_retry_prompt_from_validation",
    "strengthen_prompt_for_retry",
    "postprocess_sprite",
]
