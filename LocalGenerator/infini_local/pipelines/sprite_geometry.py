from __future__ import annotations

import math
from typing import Any

try:
    from PIL import Image
except Exception:
    Image = None

from infini_local.pipelines.sprite_contracts import sprite_contract_for

# AGENT MAP: sprite bbox/geometry helpers shared by keyer, scorer and postprocess.

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


def sprite_principal_axis_stats(img: Any, alpha_threshold: int = 8) -> dict[str, float | int]:
    """Measure an undirected visible-body axis without interpreting item semantics."""
    if Image is None:
        return {"visiblePixels": 0, "angleDegrees": 0.0, "anisotropy": 1.0, "horizontalErrorDegrees": 0.0}
    alpha = img.convert("RGBA").getchannel("A")
    threshold = max(1, min(255, int(alpha_threshold)))
    points = [
        (x, y)
        for y in range(alpha.height)
        for x in range(alpha.width)
        if int(alpha.getpixel((x, y))) >= threshold
    ]
    if len(points) < 4:
        return {"visiblePixels": len(points), "angleDegrees": 0.0, "anisotropy": 1.0, "horizontalErrorDegrees": 0.0}

    mean_x = sum(x for x, _ in points) / len(points)
    mean_y = sum(y for _, y in points) / len(points)
    variance_x = sum((x - mean_x) ** 2 for x, _ in points) / len(points)
    variance_y = sum((y - mean_y) ** 2 for _, y in points) / len(points)
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in points) / len(points)
    trace = variance_x + variance_y
    discriminant = math.sqrt(max(0.0, (variance_x - variance_y) ** 2 + 4.0 * covariance * covariance))
    major = max(0.0, (trace + discriminant) / 2.0)
    minor = max(1e-9, (trace - discriminant) / 2.0)
    angle = 0.5 * math.degrees(math.atan2(2.0 * covariance, variance_x - variance_y))
    return {
        "visiblePixels": len(points),
        "angleDegrees": round(angle, 4),
        "anisotropy": round(major / minor, 4),
        "horizontalErrorDegrees": round(abs(angle), 4),
    }

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

__all__ = [
    "alpha_bbox_threshold",
    "bbox_union",
    "bbox_expand",
    "bbox_dims",
    "bbox_center",
    "sprite_principal_axis_stats",
    "sprite_bbox_stats",
]
