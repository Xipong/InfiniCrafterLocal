"""Read-only PNG delivery validation and technical scores."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from PIL import Image
except Exception:
    Image = None

from infini_local.services.visual_asset_pipeline import ImageOutputIOError, load_image_input
from infini_local.core.images.config import (
    SPRITE_MAX_EDGE_TOUCH_PCT,
    SPRITE_MAX_OPAQUE_PCT,
    SPRITE_MIN_OPAQUE_PCT,
)
from infini_local.services.asset_sync_service import is_complete_png_file
from infini_local.pipelines.images.geometry import (
    sprite_bbox_stats,
    sprite_principal_axis_stats,
)
from infini_local.pipelines.images.keyer import (
    magenta_key_pixel_ratio,
)
from infini_local.core.images.contracts import (
    SPRITE_MIN_TRANSPARENT_PCT,
    final_sprite_canvas,
    sprite_contract_for,
    sprite_uses_soft_alpha,
    uses_key_background,
)


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
    expected_canvas: int | None = None,
) -> dict[str, Any]:
    """Technical validation only. No art taste, no tier judging, no VLM."""
    if Image is None:
        return {"ok": False, "reasons": ["pillow_unavailable_required"], "warnings": [], "stats": {}, "role": role}
    envelope_reasons: list[str] = []
    img: Any = None
    if expected_canvas is not None:
        final_size = final_sprite_canvas(expected_canvas)
        try:
            if Path(path).suffix.lower() != ".png" or not is_complete_png_file(path):
                envelope_reasons.append("invalid_png_envelope")
            if Path(path).stat().st_size > 8 * 1024 * 1024:
                envelope_reasons.append("asset_png_byte_limit_exceeded")
            with Image.open(path) as source:
                if source.format != "PNG":
                    envelope_reasons.append("image_format_not_png")
                if source.size != (final_size, final_size):
                    envelope_reasons.append("final_canvas_mismatch")
                if "A" not in source.getbands() and "transparency" not in source.info:
                    envelope_reasons.append("png_alpha_channel_missing")
                img = source.convert("RGBA")
        except OSError as exc:
            if exc.errno is not None:
                raise ImageOutputIOError("final image filesystem read failed") from exc
            envelope_reasons.append("invalid_png_envelope")
        except ValueError:
            envelope_reasons.append("invalid_png_envelope")
        if envelope_reasons:
            return {"ok": False, "reasons": list(dict.fromkeys(envelope_reasons)), "warnings": [], "stats": {}, "role": role}
    else:
        img = load_image_input(path, Image)
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
        key_ratio = magenta_key_pixel_ratio(img) if uses_key_background() else 0.0
        if key_ratio > 0.025:
            reasons.append(f"magenta_key_background_left:{key_ratio:.3f}")
        if (role == "vfx_strip" and not stats.get("hasAlpha")) or (role != "vfx_strip" and stats.get("transparentPct", 0) < SPRITE_MIN_TRANSPARENT_PCT):
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
            reasons.append(f"projectile_forward_axis_misaligned:{float(principal_axis.get('horizontalErrorDegrees') or 0.0):.1f}deg")
        if not sprite_uses_soft_alpha(role) and stats.get("partialPct", 0) > 0.25:
            warnings.append("many_partial_alpha_pixels")
        if not sprite_uses_soft_alpha(role) and stats.get("opaquePct", 0) < SPRITE_MIN_OPAQUE_PCT:
            reasons.append(f"too_few_opaque_pixels:{stats.get('opaquePct')}")
        if stats.get("opaquePct", 0) > SPRITE_MAX_OPAQUE_PCT and role not in {"impact", "vfx_strip"}:
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
        "invalid_png_envelope",
        "asset_png_byte_limit_exceeded",
        "image_format_not_png",
        "final_canvas_mismatch",
        "png_alpha_channel_missing",
        "magenta_key_background_left",
        "almost_no_transparency_after_bg_removal",
        "too_few_opaque_pixels",
        "very_dense_opaque_area",
        "pillow_unavailable_required",
        "projectile_forward_axis_misaligned",
    )
    return any(any(tok in reason for tok in fatal_tokens) for reason in reasons)
