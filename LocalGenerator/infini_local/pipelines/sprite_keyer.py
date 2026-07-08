from __future__ import annotations

import math
from typing import Any

try:
    from PIL import Image
except Exception:
    Image = None

from infini_local.pipelines.pipeline_visual_config import (
    ALPHA_THRESHOLD,
    BG_REMOVE_MODE,
    CHROMA_TOLERANCE,
    REMOVE_BG,
    SPRITE_CHROMA_DEFRINGE,
    SPRITE_KEYER_RESIDUE_STEPS,
    SPRITE_KEYER_SPILL_RADIUS,
)
from infini_local.pipelines.sprite_contracts import chroma_rgb
from infini_local.pipelines.sprite_geometry import alpha_bbox_threshold
from infini_local.storage.trace_runtime import log_event

# AGENT MAP: technical chroma-key/background removal and key-spill cleanup.
# No semantic art judgment belongs here.

def color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2)

def chroma_like_rgb(rgb: tuple[int, int, int], *, tolerance: int | None = None, strict: bool = False) -> bool:
    """Classify chroma-key contamination while protecting whites/grays.

    This is a technical key-color test, not material/palette inference.  The old
    broad rule could eat pale blade/highlight pixels if Z-Image mixed magenta into
    a white edge.  Here neutral whites and low-saturation grays are protected, and
    only genuinely magenta-like leftovers are treated as key contamination.
    """
    r, g, b = [max(0, min(255, int(v))) for v in rgb]
    target = chroma_rgb()
    tol = max(0, int(CHROMA_TOLERANCE if tolerance is None else tolerance))

    spread = max(r, g, b) - min(r, g, b)
    # Protect common foreground whites / grays / steel highlights.
    if min(r, g, b) >= 170 and spread <= 72:
        return False
    if spread <= 34 and max(r, g, b) >= 92:
        return False

    if color_distance((r, g, b), target) <= tol:
        return True

    rb_min = min(r, b)
    rb_max = max(r, b)
    green_gap = rb_min - g
    if strict:
        return rb_min >= 150 and rb_max >= 180 and g <= 78 and green_gap >= 82 and abs(r - b) <= 96
    return rb_min >= 150 and rb_max >= 175 and g <= 105 and green_gap >= 58 and abs(r - b) <= 112

def magenta_key_pixel_ratio(img: Any, tolerance: int | None = None) -> float:
    """How much of the opaque image still looks like the magenta key.

    This is intentionally technical, not taste-based: a Terraria sprite that still
    has a #ff00ff square is not a valid processed asset.
    """
    if Image is None:
        return 0.0
    img = img.convert("RGBA")
    target = chroma_rgb()
    tol = max(int(CHROMA_TOLERANCE), 58) if tolerance is None else max(0, int(tolerance))
    px = img.load()
    w, h = img.size
    opaque = 0
    keyed = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a <= max(0, int(ALPHA_THRESHOLD)):
                continue
            opaque += 1
            if chroma_like_rgb((r, g, b), tolerance=tol):
                keyed += 1
    return keyed / max(1, opaque)

def dilate_mask(mask: set[tuple[int, int]], w: int, h: int, radius: int) -> set[tuple[int, int]]:
    radius = max(0, min(32, int(radius)))
    if radius <= 0 or not mask:
        return set(mask)
    out = set(mask)
    frontier = set(mask)
    for _ in range(radius):
        nxt: set[tuple[int, int]] = set()
        for x, y in frontier:
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in out:
                    out.add((nx, ny)); nxt.add((nx, ny))
        frontier = nxt
        if not frontier:
            break
    return out

def cleanup_alpha_soft(img: Any) -> Any:
    """Keep useful partial alpha until premultiplied resize; only snap extremes."""
    if Image is None:
        return img
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    low = max(0, min(255, int(ALPHA_THRESHOLD)))
    high = max(low + 1, 248)
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a <= low:
                px[x, y] = (0, 0, 0, 0)
            elif a >= high:
                px[x, y] = (r, g, b, 255)
    return img

def is_neutral_or_white_foreground_rgb(rgb: tuple[int, int, int]) -> bool:
    """Protect Photoshop-style highlights from key spill cleanup.

    This is not semantic material logic. It only says: if a pixel is bright/neutral
    enough to plausibly be foreground highlight, do not classify it as magenta key
    merely because the model mixed a little pink into it.
    """
    r, g, b = [max(0, min(255, int(v))) for v in rgb]
    spread = max(r, g, b) - min(r, g, b)
    if min(r, g, b) >= 150 and spread <= 96:
        return True
    if max(r, g, b) >= 205 and spread <= 118 and g >= 128:
        return True
    if spread <= 42 and max(r, g, b) >= 92:
        return True
    return False

def is_dark_key_residue_rgb(rgb: tuple[int, int, int]) -> bool:
    r, g, b = [max(0, min(255, int(v))) for v in rgb]
    if is_neutral_or_white_foreground_rgb((r, g, b)):
        return False
    rb_min = min(r, b)
    if rb_min < 72:
        return False
    return g <= max(42, int(rb_min * 0.34)) and abs(r - b) <= 104 and (rb_min - g) >= 28

def median_int(values: list[int], fallback: int) -> int:
    if not values:
        return int(fallback)
    values = sorted(int(v) for v in values)
    return int(values[len(values) // 2])

def percentile(values: list[float], q: float, fallback: float = 0.0) -> float:
    if not values:
        return float(fallback)
    values = sorted(float(v) for v in values)
    idx = max(0, min(len(values) - 1, int(round((len(values) - 1) * q))))
    return values[idx]

def border_sample_pixels(img: Any, border: int = 2) -> list[tuple[int, int, int]]:
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    b = max(1, min(max(w, h), int(border)))
    samples: list[tuple[int, int, int]] = []
    for y in range(h):
        for x in range(w):
            if x >= b and y >= b and x < w - b and y < h - b:
                continue
            r, g, bb, a = px[x, y]
            if a > 0:
                samples.append((int(r), int(g), int(bb)))
    return samples

def estimate_sprite_key_profile(img: Any) -> dict[str, Any]:
    """Photoshop-like sample phase: build a key profile from the border.

    Magic Wand is not a single hardcoded #ff00ff compare; it samples a color and uses
    tolerance/contiguous selection.  Here the border is our click-source because the
    prompt asks the model to keep the background as a flat key around the asset.
    """
    configured = chroma_rgb()
    border = border_sample_pixels(img, 3)
    magentaish = [rgb for rgb in border if chroma_like_rgb(rgb, tolerance=max(96, int(CHROMA_TOLERANCE) + 64)) or color_distance(rgb, configured) <= 122]
    # If the model polluted the whole border, take the dominant magenta-like subset;
    # otherwise fall back to the configured key color.
    if len(magentaish) >= max(12, int(len(border) * 0.08)):
        key = (
            median_int([c[0] for c in magentaish], configured[0]),
            median_int([c[1] for c in magentaish], configured[1]),
            median_int([c[2] for c in magentaish], configured[2]),
        )
        dists = [color_distance(c, key) for c in magentaish]
        tol = int(max(int(CHROMA_TOLERANCE) + 38, min(150, percentile(dists, 0.90, 76) + 26)))
        return {"key": key, "tolerance": tol, "samples": len(magentaish), "source": "border_profile"}

    # Z-Image can miss the exact #ff00ff target and paint a very uniform saturated
    # pink/magenta canvas (for example around #ca048c). If the border is strongly
    # uniform and saturated, use that sampled border as the key instead of assuming
    # the configured pure magenta. This is still a technical background pass, not art judging.
    if border:
        buckets: dict[tuple[int, int, int], int] = {}
        for r, g, b in border:
            bucket = (int(round(r / 8) * 8), int(round(g / 8) * 8), int(round(b / 8) * 8))
            buckets[bucket] = buckets.get(bucket, 0) + 1
        dominant, dom_count = max(buckets.items(), key=lambda kv: kv[1])
        uniform = dom_count / max(1, len(border))
        r, g, b = dominant
        saturated_key_like = max(r, g, b) - min(r, g, b) >= 72 and r >= 120 and b >= 90 and g <= 130
        if uniform >= 0.72 and saturated_key_like:
            close = [c for c in border if color_distance(c, dominant) <= 38]
            key = (
                median_int([c[0] for c in close], r),
                median_int([c[1] for c in close], g),
                median_int([c[2] for c in close], b),
            )
            return {"key": key, "tolerance": 58, "samples": len(close), "source": "uniform_saturated_border"}
    return {"key": configured, "tolerance": max(76, int(CHROMA_TOLERANCE) + 42), "samples": len(magentaish), "source": "configured_key"}

def magic_wand_bg_candidate_rgb(rgb: tuple[int, int, int], key: tuple[int, int, int], tolerance: int, *, include_residue: bool = False) -> bool:
    if is_neutral_or_white_foreground_rgb(rgb):
        return False
    if color_distance(rgb, key) <= tolerance:
        return True
    if chroma_like_rgb(rgb, tolerance=max(tolerance, int(CHROMA_TOLERANCE) + 52)):
        return True
    if include_residue and is_dark_key_residue_rgb(rgb):
        return True
    return False

def local_edge_contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    # Weighted RGB distance; green/luma contrast matters because magenta spill usually
    # differs from the actual object by a strong green/luma jump.
    ar, ag, ab = a; br, bg, bb = b
    return math.sqrt(((ar - br) * 0.75) ** 2 + ((ag - bg) * 1.15) ** 2 + ((ab - bb) * 0.75) ** 2)

def floodfill_keylike_background(img: Any, *, tolerance: int = 76, key_profile: dict[str, Any] | None = None) -> set[tuple[int, int]]:
    """Adaptive Magic-Wand-like background selection.

    Photoshop bits we borrow:
    - sampled key profile, not blind fixed #ff00ff;
    - contiguous selection from the image border;
    - edge-aware stop so the fill does not crawl into bright foreground edges.
    """
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    profile = key_profile or estimate_sprite_key_profile(img)
    key = tuple(profile.get("key") or chroma_rgb())
    tol = max(int(tolerance), int(profile.get("tolerance") or tolerance))
    edge_stop = 135

    def is_bg_candidate(x: int, y: int, *, include_residue: bool = False) -> bool:
        r, g, b, a = px[x, y]
        if a <= 0:
            return True
        return magic_wand_bg_candidate_rgb((int(r), int(g), int(b)), key, tol, include_residue=include_residue)

    seeds: list[tuple[int, int]] = []
    for x in range(w):
        if is_bg_candidate(x, 0):
            seeds.append((x, 0))
        if is_bg_candidate(x, h - 1):
            seeds.append((x, h - 1))
    for y in range(h):
        if is_bg_candidate(0, y):
            seeds.append((0, y))
        if is_bg_candidate(w - 1, y):
            seeds.append((w - 1, y))

    bg: set[tuple[int, int]] = set()
    q = list(dict.fromkeys(seeds))
    while q:
        x, y = q.pop()
        if x < 0 or y < 0 or x >= w or y >= h or (x, y) in bg:
            continue
        if not is_bg_candidate(x, y):
            continue
        bg.add((x, y))
        base = px[x, y]
        base_rgb = (int(base[0]), int(base[1]), int(base[2]))
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if nx < 0 or ny < 0 or nx >= w or ny >= h or (nx, ny) in bg:
                continue
            nr, ng, nb, na = px[nx, ny]
            if na > 0:
                n_rgb = (int(nr), int(ng), int(nb))
                if is_neutral_or_white_foreground_rgb(n_rgb):
                    continue
                # If the neighbor is not confidently key-like and there is a hard edge,
                # stop like Quick Selection would stop on an object edge.
                confident_key = color_distance(n_rgb, key) <= max(42, tol * 0.72) or chroma_like_rgb(n_rgb, tolerance=max(72, tol))
                if not confident_key and local_edge_contrast(base_rgb, n_rgb) > edge_stop:
                    continue
            if is_bg_candidate(nx, ny):
                q.append((nx, ny))
    return bg

def grow_background_through_key_residue(img: Any, bg: set[tuple[int, int]], *, steps: int = 8, key_profile: dict[str, Any] | None = None) -> set[tuple[int, int]]:
    """Eat fake magenta shadow/residue only when connected to the selected background."""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    profile = key_profile or estimate_sprite_key_profile(img)
    key = tuple(profile.get("key") or chroma_rgb())
    tol = max(int(profile.get("tolerance") or 76), int(CHROMA_TOLERANCE) + 52)
    out = set(bg)
    frontier = set(bg)
    max_steps = max(0, min(24, int(steps)))
    for _ in range(max_steps):
        nxt: set[tuple[int, int]] = set()
        for x, y in frontier:
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1), (x + 1, y + 1), (x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1)):
                if nx < 0 or ny < 0 or nx >= w or ny >= h or (nx, ny) in out:
                    continue
                r, g, b, a = px[nx, ny]
                rgb = (int(r), int(g), int(b))
                if a <= 0 or magic_wand_bg_candidate_rgb(rgb, key, tol, include_residue=True):
                    out.add((nx, ny)); nxt.add((nx, ny))
        if not nxt:
            break
        frontier = nxt
    return out

def remove_key_colored_holes(img: Any, key_profile: dict[str, Any] | None = None) -> Any:
    """Delete sampled chroma-key islands that survived contiguous border selection.

    Z-Image often draws the bow/string/outline as a closed shape, leaving small
    magenta background pockets inside the silhouette. A pure border flood-fill cannot
    reach those pockets, so the final 48px PNG still contains visible key color and
    fails validation. This pass is intentionally technical: it removes only pixels
    that match the sampled border key profile, not arbitrary pink material guesses.
    """
    if Image is None:
        return img
    img = img.convert("RGBA")
    profile = key_profile or estimate_sprite_key_profile(img)
    key = tuple(profile.get("key") or chroma_rgb())
    tol = max(int(profile.get("tolerance") or 76), int(CHROMA_TOLERANCE) + 52)
    px = img.load()
    w, h = img.size
    killed = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a <= 0:
                continue
            rgb = (int(r), int(g), int(b))
            if magic_wand_bg_candidate_rgb(rgb, key, tol, include_residue=True):
                px[x, y] = (0, 0, 0, 0)
                killed += 1
    try:
        if killed:
            log_event("debug", "sprite_keyer removed key-colored holes", {"pixels": killed, "key": list(key), "tolerance": tol, "profileSource": profile.get("source")})
    except Exception:
        pass
    return scrub_transparent_rgb(img)

def _poster_card_like_rgb(rgb: tuple[int, int, int]) -> bool:
    r, g, b = [max(0, min(255, int(v))) for v in rgb]
    spread = max(r, g, b) - min(r, g, b)
    # White/light-gray card, pale pink card, or near-white model canvas.
    if min(r, g, b) >= 205 and spread <= 86:
        return True
    if r >= 215 and b >= 205 and g >= 120 and spread <= 135:
        return True
    return False

def _quant_bucket(rgb: tuple[int, int, int], step: int = 12) -> tuple[int, int, int]:
    step = max(2, int(step))
    return tuple(max(0, min(255, int(round(int(v) / step) * step))) for v in rgb)

def remove_inner_poster_card_background(img: Any, role: str = "item") -> Any:
    """Remove AI-drawn white/pink poster cards left inside the magenta key.

    This is the second background layer. The primary chroma key removes the requested
    #ff00ff canvas. If the model draws a white square/card inside that canvas, the
    first pass cannot know whether it is foreground or background. We only remove it
    when the visible bbox is mostly a poster-card-like color *and* there is a distinct
    non-card foreground object inside. A plain white item on magenta is preserved.
    """
    if Image is None:
        return img
    img = img.convert("RGBA")
    bbox = alpha_bbox_threshold(img, 1)
    if not bbox:
        return img
    w, h = img.size
    x0, y0, x1, y1 = bbox
    bw = max(1, x1 - x0)
    bh = max(1, y1 - y0)
    bbox_area = bw * bh
    full_area = max(1, w * h)
    if bbox_area / full_area < 0.48:
        return img

    px = img.load()
    band = max(2, int(round(max(bw, bh) * 0.035)))
    border_samples: list[tuple[int, int, int]] = []
    for y in range(y0, y1):
        for x in range(x0, x1):
            if x >= x0 + band and x < x1 - band and y >= y0 + band and y < y1 - band:
                continue
            r, g, b, a = px[x, y]
            if a <= 0:
                continue
            rgb = (int(r), int(g), int(b))
            if _poster_card_like_rgb(rgb):
                border_samples.append(rgb)
    if len(border_samples) < max(18, int((bw + bh) * 0.35)):
        return img

    buckets: dict[tuple[int, int, int], int] = {}
    for rgb in border_samples:
        bkt = _quant_bucket(rgb, 12)
        buckets[bkt] = buckets.get(bkt, 0) + 1
    card_key, card_count = max(buckets.items(), key=lambda kv: kv[1])
    if card_count / max(1, len(border_samples)) < 0.30:
        return img
    if not _poster_card_like_rgb(card_key):
        return img

    tol = 46

    def is_card(x: int, y: int) -> bool:
        r, g, b, a = px[x, y]
        if a <= 0:
            return False
        rgb = (int(r), int(g), int(b))
        return _poster_card_like_rgb(rgb) and color_distance(rgb, card_key) <= tol

    alpha_count = 0
    card_like_count = 0
    non_card_count = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            if px[x, y][3] <= 0:
                continue
            alpha_count += 1
            if is_card(x, y):
                card_like_count += 1
            else:
                non_card_count += 1
    if alpha_count <= 0:
        return img
    # Preserve genuine white/simple items: if there is no separate colored/dark object,
    # the near-white shape is probably the asset itself, not a poster card.
    if non_card_count / alpha_count < 0.045:
        return img
    if card_like_count / alpha_count < 0.28:
        return img

    seeds: list[tuple[int, int]] = []
    for x in range(x0, x1):
        for y in (y0, y1 - 1):
            if is_card(x, y):
                seeds.append((x, y))
    for y in range(y0, y1):
        for x in (x0, x1 - 1):
            if is_card(x, y):
                seeds.append((x, y))
    if not seeds:
        return img

    q = list(dict.fromkeys(seeds))
    card: set[tuple[int, int]] = set()
    while q:
        x, y = q.pop()
        if x < x0 or x >= x1 or y < y0 or y >= y1 or (x, y) in card:
            continue
        if not is_card(x, y):
            continue
        card.add((x, y))
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if nx >= x0 and nx < x1 and ny >= y0 and ny < y1 and (nx, ny) not in card:
                if is_card(nx, ny):
                    q.append((nx, ny))
    if len(card) < max(24, int(alpha_count * 0.18)):
        return img
    if len(card) > int(alpha_count * 0.96):
        return img
    for x, y in card:
        px[x, y] = (0, 0, 0, 0)
    try:
        log_event("debug", "sprite_keyer removed inner poster card", {"pixels": len(card), "key": list(card_key), "role": role, "alphaCount": alpha_count, "nonCardCount": non_card_count})
    except Exception:
        pass
    return scrub_transparent_rgb(img)

def find_nearby_clean_foreground_color(px: Any, w: int, h: int, x: int, y: int, bg: set[tuple[int, int]], radius: int, key_profile: dict[str, Any] | None = None) -> tuple[int, int, int] | None:
    radius = max(1, min(10, int(radius)))
    profile = key_profile or {"key": chroma_rgb(), "tolerance": max(76, int(CHROMA_TOLERANCE) + 42)}
    key = tuple(profile.get("key") or chroma_rgb())
    tol = max(int(profile.get("tolerance") or 76), int(CHROMA_TOLERANCE) + 46)
    for rr in range(1, radius + 1):
        samples: list[tuple[int, int, int]] = []
        for yy in range(max(0, y - rr), min(h, y + rr + 1)):
            for xx in range(max(0, x - rr), min(w, x + rr + 1)):
                if (xx, yy) in bg or (xx == x and yy == y):
                    continue
                nr, ng, nb, na = px[xx, yy]
                if na <= 0:
                    continue
                rgb = (int(nr), int(ng), int(nb))
                if magic_wand_bg_candidate_rgb(rgb, key, tol, include_residue=True):
                    continue
                samples.append(rgb)
        if samples:
            # Use median rather than mean: like a tiny local clone/decontaminate pass,
            # but robust to one noisy edge pixel.
            return (
                median_int([v[0] for v in samples[:32]], samples[0][0]),
                median_int([v[1] for v in samples[:32]], samples[0][1]),
                median_int([v[2] for v in samples[:32]], samples[0][2]),
            )
    return None

def close_tiny_background_cracks(mask: set[tuple[int, int]], w: int, h: int) -> set[tuple[int, int]]:
    """Selection cleanup: fill 1px cracks in selected background, not object holes."""
    out = set(mask)
    add: set[tuple[int, int]] = set()
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if (x, y) in out:
                continue
            n4 = sum((nx, ny) in out for nx, ny in ((x+1,y), (x-1,y), (x,y+1), (x,y-1)))
            if n4 >= 3:
                add.add((x, y))
    out.update(add)
    return out

def remove_background_sprite_keyer(img: Any) -> Any:
    """Final Photoshop-like sprite keyer for generated Terraria-like assets.

    Pipeline:
    - adaptive border sampling (Magic Wand sample/tolerance idea),
    - contiguous edge flood-fill from borders,
    - edge-aware stop for bright/neutral foreground,
    - connected residue cleanup,
    - small Select-and-Mask-like refine band for key-spill decontamination,
    - hard alpha output for game sprites.
    """
    if Image is None:
        return img
    src = img.convert("RGBA")
    w, h = src.size
    px = src.load()
    profile = estimate_sprite_key_profile(src)

    bg = floodfill_keylike_background(src, tolerance=max(76, int(CHROMA_TOLERANCE) + 42), key_profile=profile)
    bg = grow_background_through_key_residue(src, bg, steps=int(SPRITE_KEYER_RESIDUE_STEPS), key_profile=profile)
    bg = close_tiny_background_cracks(bg, w, h)
    if len(bg) > int(w * h * 0.96):
        return src

    edge_band = dilate_mask(bg, w, h, max(1, int(SPRITE_KEYER_SPILL_RADIUS))) - bg
    key = tuple(profile.get("key") or chroma_rgb())
    tol = max(int(profile.get("tolerance") or 76), int(CHROMA_TOLERANCE) + 48)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    opx = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a <= 0 or (x, y) in bg:
                opx[x, y] = (0, 0, 0, 0)
                continue
            rgb = (int(r), int(g), int(b))
            in_refine = (x, y) in edge_band
            # Decontaminate colors only in the narrow refine band. Bright neutral
            # foreground is preserved unless it is truly key-like, which avoids the
            # earlier "white edge got eaten" failure.
            spill = in_refine and magic_wand_bg_candidate_rgb(rgb, key, tol, include_residue=True) and not is_neutral_or_white_foreground_rgb(rgb)
            if spill:
                repl = find_nearby_clean_foreground_color(px, w, h, x, y, bg, max(2, int(SPRITE_KEYER_SPILL_RADIUS) + 3), key_profile=profile)
                if repl is not None:
                    opx[x, y] = (repl[0], repl[1], repl[2], 255)
                else:
                    opx[x, y] = (0, 0, 0, 0)
            else:
                opx[x, y] = (int(r), int(g), int(b), 255)
    out = scrub_transparent_rgb(out)
    try:
        log_event("debug", "sprite_keyer profile", {"key": list(profile.get("key") or []), "tolerance": profile.get("tolerance"), "source": profile.get("source"), "samples": profile.get("samples"), "bgPixels": len(bg)})
    except Exception:
        pass
    return out

def apply_background_removal(img: Any) -> Any:
    if Image is None:
        return img
    img = img.convert("RGBA")
    mode = (BG_REMOVE_MODE or "sprite_keyer").strip().lower().replace("-", "_")
    if not REMOVE_BG or mode in {"", "none", "off"}:
        return img
    # v0.4.65: the runtime pipeline keeps a single supported background-removal
    # protocol. Old config.env values are accepted only as compatibility aliases and
    # intentionally routed here, so hidden legacy modes cannot silently come back.
    if mode != "sprite_keyer":
        try:
            log_event("warn", "unsupported bg remove mode routed to sprite_keyer", {"requested": mode, "used": "sprite_keyer"})
        except Exception:
            pass
    return remove_background_sprite_keyer(img)

def scrub_transparent_rgb(img: Any) -> Any:
    """Set RGB of fully transparent pixels to zero so resize filters cannot bleed key color."""
    if Image is None:
        return img
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a <= 0:
                px[x, y] = (0, 0, 0, 0)
    return img

__all__ = [
    "color_distance",
    "chroma_like_rgb",
    "magenta_key_pixel_ratio",
    "dilate_mask",
    "cleanup_alpha_soft",
    "is_neutral_or_white_foreground_rgb",
    "is_dark_key_residue_rgb",
    "median_int",
    "percentile",
    "border_sample_pixels",
    "estimate_sprite_key_profile",
    "magic_wand_bg_candidate_rgb",
    "local_edge_contrast",
    "floodfill_keylike_background",
    "grow_background_through_key_residue",
    "remove_key_colored_holes",
    "_poster_card_like_rgb",
    "_quant_bucket",
    "remove_inner_poster_card_background",
    "find_nearby_clean_foreground_color",
    "close_tiny_background_cracks",
    "remove_background_sprite_keyer",
    "apply_background_removal",
    "scrub_transparent_rgb",
]
