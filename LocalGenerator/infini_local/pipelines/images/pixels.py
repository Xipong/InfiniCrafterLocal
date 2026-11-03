"""Technical pixel transforms: alpha, framing, resampling and palette."""

from __future__ import annotations

from typing import Any

try:
    from PIL import Image, ImageEnhance
except Exception:
    Image = None
    ImageEnhance = None

from infini_local.core.images.config import (
    ALPHA_THRESHOLD,
    CHROMA_TOLERANCE,
    DENOISE_STRAY_PIXELS,
    MAX_COLORS,
    PIXEL_POSTERIZE,
    SPRITE_CHROMA_DEFRINGE,
    SPRITE_DOWNSCALE_FILTER,
    SPRITE_MASTER_CANVAS,
    SPRITE_PADDING,
    SPRITE_PREMULTIPLIED_RESIZE,
)
from infini_local.pipelines.images.geometry import (
    alpha_bbox_threshold,
    bbox_center,
    bbox_dims,
    bbox_expand,
    bbox_union,
    sprite_bbox_stats,
    sprite_principal_axis_stats,
)
from infini_local.pipelines.images.keyer import (
    chroma_like_rgb,
    scrub_transparent_rgb,
)
from infini_local.core.images.contracts import (
    chroma_rgb,
    final_sprite_canvas,
    sprite_contract_for,
    sprite_uses_soft_alpha,
    uses_key_background,
)


# Technical RGB compensation after downscaling; alpha and geometry remain unchanged.
FINAL_COLOR_SATURATION = 1.08
FINAL_COLOR_GAMMA = 0.96
FINAL_COLOR_GAMMA_LUT = [max(0, min(255, int(round(255.0 * ((value / 255.0) ** FINAL_COLOR_GAMMA))))) for value in range(256)]


def cleanup_alpha(img: Any, role: str = "item") -> Any:
    if Image is None:
        return img
    img = img.convert("RGBA")
    if sprite_uses_soft_alpha(role):
        return scrub_transparent_rgb(img)
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
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if px[x, y][3] == 0:
                continue
            n = 0
            for yy in (y - 1, y, y + 1):
                for xx in (x - 1, x, x + 1):
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
    if Image is None or not SPRITE_CHROMA_DEFRINGE or not uses_key_background():
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
            magentaish = chroma_like_rgb((r, g, b), tolerance=tol)
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
    if Image is None or not SPRITE_CHROMA_DEFRINGE or not uses_key_background():
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
                px[x, y] = (
                    min(255, (rr * 255 + aa // 2) // aa),
                    min(255, (gg * 255 + aa // 2) // aa),
                    min(255, (bb * 255 + aa // 2) // aa),
                    aa,
                )
    return out


def prepare_sprite_master(img: Any, sprite_id: str, target_size: int, role: str = "item") -> Any:
    """Full-res/master-first normalisation.  Does not invent or redraw art.

    raw -> bg remove -> chroma defringe -> alpha cleanup -> crop visible bbox ->
    fit to a larger transparent master canvas.  Final 32/48/64 bakes are produced
    from this master, not from an already degraded tiny sprite.
    """
    img = img.convert("RGBA")
    final_size = final_sprite_canvas(target_size)
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
    final_size = final_sprite_canvas(target_size)
    master = scrub_transparent_rgb(master.convert("RGBA"))
    if master.size != (final_size, final_size):
        resample = sprite_resample_filter("final")
        img = resize_rgba_premultiplied(master, (final_size, final_size), resample)
    else:
        img = master
    # Hard sprites snap alpha after resizing; effect sprites retain authored coverage.
    img = cleanup_alpha(img, role)
    if role in {"item", "equip_overlay"}:
        img = denoise_alpha_singletons(img)
    img = palette_cleanup(img, role)
    img = cleanup_alpha(img, role)
    # Safe final rescue pass: recolor or remove only true chroma leftovers touching
    # transparency. This is much less destructive than the old blanket magenta wipe.
    img = neutralize_chroma_edge_colors(img)
    img = cleanup_alpha(img, role)
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
            left = sum(1 for y in range(y0, y1) for x in range(x0, min(x1, x0 + edge_width)) if int(alpha.getpixel((x, y))) >= 8)
            right = sum(1 for y in range(y0, y1) for x in range(max(x0, x1 - edge_width), x1) if int(alpha.getpixel((x, y))) >= 8)
            evidence["leftEndpointPixels"] = left
            evidence["rightEndpointPixels"] = right
            if left > 0 and right > 0 and left < right * 0.82:
                working = working.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                evidence["flipped"] = True

    after = sprite_principal_axis_stats(working, 8)
    evidence["afterAngleDegrees"] = float(after.get("angleDegrees") or 0.0)
    return working, evidence


def palette_cleanup(img: Any, role: str = "item") -> Any:
    if Image is None or not PIXEL_POSTERIZE:
        return img
    normalized_role = str(role or "item").strip().lower()
    if sprite_uses_soft_alpha(normalized_role):
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
