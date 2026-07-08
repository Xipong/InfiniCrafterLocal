from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from infini_local.pipelines.pipeline_support import Image, log_event


# AGENT MAP: final-PNG visual-soul analysis. Reads postprocessed sprite pixels
# and writes presentation/debug fields only; no prompt, category, or gameplay
# routing decisions belong here.


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


__all__ = [
    "_clamp01",
    "_hex_from_rgb",
    "_rgb_to_hsv01",
    "visual_soul_archetype",
    "visual_soul_tooltip",
    "_rgba_pixels",
    "analyze_visual_soul_from_sprite",
    "attach_visual_soul_from_sprite",
]
