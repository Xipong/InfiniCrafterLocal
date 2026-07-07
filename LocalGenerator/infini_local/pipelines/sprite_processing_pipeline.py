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


def alpha_bbox_threshold(img: Any, threshold: int = 1) -> tuple[int, int, int, int] | None:
    if Image is None:
        return None
    img = img.convert("RGBA")
    alpha = img.getchannel("A")
    thr = max(0, min(255, int(threshold)))
    px = alpha.load()
    w, h = alpha.size
    min_x = w
    min_y = h
    max_x = -1
    max_y = -1
    for y in range(h):
        for x in range(w):
            if px[x, y] >= thr:
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y
    if max_x < min_x or max_y < min_y:
        return None
    return (min_x, min_y, max_x + 1, max_y + 1)

def bbox_union(a: tuple[int, int, int, int] | None, b: tuple[int, int, int, int] | None) -> tuple[int, int, int, int] | None:
    if a is None:
        return b
    if b is None:
        return a
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))

def bbox_expand(b: tuple[int, int, int, int] | None, pad: int, bounds: tuple[int, int] | None = None) -> tuple[int, int, int, int] | None:
    if b is None:
        return None
    x1, y1, x2, y2 = b
    x1 -= pad
    y1 -= pad
    x2 += pad
    y2 += pad
    if bounds is not None:
        bw, bh = bounds
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(bw, x2)
        y2 = min(bh, y2)
    return (x1, y1, x2, y2)

def bbox_dims(b: tuple[int, int, int, int] | None) -> tuple[int, int]:
    if b is None:
        return (0, 0)
    return (max(0, b[2] - b[0]), max(0, b[3] - b[1]))

def bbox_center(b: tuple[int, int, int, int] | None) -> tuple[float, float]:
    if b is None:
        return (0.0, 0.0)
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)

def sprite_bbox_stats(img: Any, role: str = "item", target_size: int | None = None) -> dict[str, Any]:
    role = (role or "item").lower()
    spec = sprite_contract_for(role, target_size or (img.size[0] if getattr(img, "size", None) else 32))
    img = img.convert("RGBA")
    w, h = img.size
    effect_bbox = alpha_bbox_threshold(img, 1)
    core_bbox = alpha_bbox_threshold(img, int(spec.get("coreAlphaThreshold") or 1)) or effect_bbox
    core_w, core_h = bbox_dims(core_bbox)
    effect_w, effect_h = bbox_dims(effect_bbox)
    return {
        "role": role,
        "spec": spec,
        "effect_bbox": effect_bbox,
        "core_bbox": core_bbox,
        "core_long_axis": max(core_w, core_h),
        "effect_long_axis": max(effect_w, effect_h),
        "core_short_axis": min(core_w, core_h),
        "effect_short_axis": min(effect_w, effect_h),
        "core_fill": (max(core_w, core_h) / max(1, max(w, h))),
        "effect_fill": (max(effect_w, effect_h) / max(1, max(w, h))),
        "core_area_ratio": (core_w * core_h) / max(1, w * h),
        "effect_area_ratio": (effect_w * effect_h) / max(1, w * h),
        "core_center_norm": tuple(v / max(1, max(w, h)) for v in bbox_center(core_bbox)),
        "effect_center_norm": tuple(v / max(1, max(w, h)) for v in bbox_center(effect_bbox)),
    }

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
                center_penalty = abs(cx - 0.5) + abs(cy - 0.5)
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
    profile = (SPRITE_PROCESSING_PROFILE or "master_soft").lower()
    if profile in {"legacy", "legacy_nearest", "pixel_strict"} or mode == "nearest":
        return Image.Resampling.NEAREST
    if mode in {"lanczos", "antialias"}:
        return Image.Resampling.LANCZOS
    if mode in {"bicubic"}:
        return Image.Resampling.BICUBIC
    if mode in {"bilinear"}:
        return Image.Resampling.BILINEAR
    # BOX is a good default for fake pixel-art rendered at high resolution: it averages
    # full-res blocks instead of randomly sampling one source pixel like NEAREST.
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
    if not SPRITE_PREMULTIPLIED_RESIZE or resample == Image.Resampling.NEAREST:
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
    if SPRITE_PROCESSING_PROFILE in {"legacy", "legacy_nearest"}:
        return fit_to_canvas(img, final_size, role)
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

    # Recentre by core bbox on the master canvas.
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
    img = denoise_alpha_singletons(img)
    img = palette_cleanup(img)
    img = cleanup_alpha(img)
    # Safe final rescue pass: recolor or remove only true chroma leftovers touching
    # transparency. This is much less destructive than the old blanket magenta wipe.
    img = neutralize_chroma_edge_colors(img)
    img = cleanup_alpha(img)
    return scrub_transparent_rgb(img)

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
    resized = img.resize((new_w, new_h), Image.Resampling.NEAREST)
    final_size = max(16, min(96, int(target_size or 32)))
    canvas = Image.new("RGBA", (final_size, final_size), (0, 0, 0, 0))
    x = (final_size - new_w) // 2
    y = (final_size - new_h) // 2
    canvas.alpha_composite(resized, (x, y))
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

def palette_cleanup(img: Any) -> Any:
    if Image is None or not PIXEL_POSTERIZE:
        return img
    img = img.convert("RGBA")
    alpha = img.getchannel("A")
    colors = max(2, min(256, int(MAX_COLORS)))
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

def validate_processed_sprite(path: str, role: str = "item") -> dict[str, Any]:
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
    effect_bbox = bb.get("effect_bbox")
    core_bbox = bb.get("core_bbox")
    core_long = int(bb.get("core_long_axis") or 0)
    effect_long = int(bb.get("effect_long_axis") or 0)
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
    return {"ok": not reasons, "reasons": reasons, "warnings": warnings, "stats": stats, "bboxStats": bb, "role": role}

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
        ("empty_alpha_bbox", "draw exactly one visible asset, not an empty image"),
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
            f"Composition correction: keep the full {role} subject inside the frame and make it larger and clearer.",
            str(contract),
            "Background correction: use a flat #ff00ff magenta chroma-key background.",
            ("Technical correction: " + notes) if notes else "",
        ]
        return compact_zimage_asset_prompt(retry_parts, role, limit=env_int("INFINI_ZIMAGE_RETRY_PROMPT_LIMIT", 2200))
    extra = (
        f" STRICT RETRY {attempt}: draw only one {role} asset, keep the full object visible, make the subject large in frame, "
        f"{contract}, {bg}, "
        "no checkerboard, no UI, no text, no scene, no ground, no shadow, no crop"
    )
    if notes:
        extra += ", fix these technical issues: " + notes
    return (str(prompt or "") + ", " + extra)[:2800]

def strengthen_prompt_for_retry(prompt: str, role: str, attempt: int) -> str:
    return build_retry_prompt_from_validation(prompt, {}, role, attempt, 32)[:2600]

def postprocess_sprite(path: str, sprite_id: str, target_size: int = 32, role: str = "unknown") -> str:
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
        bg_removed = remove_inner_poster_card_background(bg_removed, role)
        bg_removed = cleanup_alpha(bg_removed)
        bg_removed = denoise_alpha_singletons(bg_removed)
        bg_removed = scrub_transparent_rgb(bg_removed)
        save_stage(bg_removed, sprite_id, "10_sprite_keyer_fullres")

        if SPRITE_PROCESSING_PROFILE in {"legacy", "legacy_nearest"}:
            fitted = fit_to_canvas(bg_removed, target_size, role)
            save_stage(fitted, sprite_id, "20_legacy_fit")
            final = palette_cleanup(fitted)
            final = cleanup_alpha(final)
            final = neutralize_chroma_edge_colors(final)
            final = cleanup_alpha(final)
        else:
            master = prepare_sprite_master(bg_removed, sprite_id, target_size, role)
            save_stage(master, sprite_id, "20_master_norm")
            final = bake_sprite_from_master(master, target_size, role)
            save_stage(final, sprite_id, "30_baked_final")

        out = SPRITE_DIR / f"{sprite_id}.png"
        final.save(out)
        stats = alpha_stats(final)
        validation = validate_processed_sprite(str(out), role)
        log_event("info", "sprite postprocessed", {"spriteId": sprite_id, "source": str(path), "out": str(out), "targetSize": target_size, "removeBg": REMOVE_BG,
                        "processingProfile": SPRITE_PROCESSING_PROFILE, "masterCanvas": SPRITE_MASTER_CANVAS, "downscaleFilter": SPRITE_DOWNSCALE_FILTER,
                        "premultipliedResize": SPRITE_PREMULTIPLIED_RESIZE, "chromaDefringe": SPRITE_CHROMA_DEFRINGE,
                        "requirePillow": REQUIRE_PILLOW,
                        "pillowAvailable": Image is not None, "bgMode": BG_REMOVE_MODE, "alpha": stats, "validation": validation})
        return str(out)
    except Exception as e:
        log_event("warn", "postprocess failed", {"path": path, "error": repr(e), "trace": traceback.format_exc()})
        return path

# =============================================================================
# Explicit pipeline dependencies
# =============================================================================
from infini_local.pipelines.pipeline_support import (
    Image,
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
    SPRITE_DIR,
    SPRITE_DOWNSCALE_FILTER,
    SPRITE_KEYER_RESIDUE_STEPS,
    SPRITE_KEYER_SPILL_RADIUS,
    SPRITE_MASTER_CANVAS,
    SPRITE_MAX_EDGE_TOUCH_PCT,
    SPRITE_MAX_OPAQUE_PCT,
    SPRITE_MIN_OPAQUE_PCT,
    SPRITE_PADDING,
    SPRITE_PREMULTIPLIED_RESIZE,
    SPRITE_PROCESSING_PROFILE,
    compact_zimage_asset_prompt,
    log_event,
)

from infini_local.pipelines.visual_generation_pipeline import (
    chroma_rgb,
    image_backend_is_zimage,
    role_contract_prompt_clause,
    sprite_background_positive_clause,
    sprite_contract_for,
)
