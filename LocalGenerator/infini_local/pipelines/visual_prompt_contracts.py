from __future__ import annotations

"""Image-backend prompt guards for exact runtime-entity assets.

This module knows visual roles and sprite constraints only. It never reads or
infers a weapon family, attack shape, or gameplay topology from prose.
"""

import json
import re
from typing import Any, Mapping

from infini_local.pipelines import pipeline_visual_config as visual_config
from infini_local.pipelines.sprite_contracts import chroma_rgb, uses_key_background, final_sprite_canvas, sprite_uses_soft_alpha


def asset_negative_prompt(role: str = "item") -> str:
    role_name = str(role or "asset").removeprefix("runtime:").replace("entity:", "runtime entity ")
    edge_negative = "" if sprite_uses_soft_alpha(role) else "blur, antialiasing, "
    return (
        f"scene, environment, character, enemy, UI, text, watermark, multiple unrelated objects, "
        f"{edge_negative}photorealism; draw only the {role_name} sprite"
    )


def chroma_name() -> str:
    r, g, b = chroma_rgb()
    return f"rgb({r},{g},{b})"


def image_backend_is_zimage() -> bool:
    backend = str(getattr(visual_config, "IMAGE_BACKEND", "") or "").strip().lower()
    raw = str(getattr(visual_config, "IMAGE_BACKEND_RAW", "") or "").strip().lower()
    return backend in {"sdcpp", "sd.cpp", "zimage", "z-image"} or raw in {"sdcpp", "sd.cpp", "zimage", "z-image"}


def zimage_positive_only_enabled() -> bool:
    return bool(getattr(visual_config, "ZIMAGE_POSITIVE_ONLY", False))


def compact_visual_words(value: Any, limit: int = 180) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def sprite_contract_for(role: str, target_size: int = 32) -> dict[str, Any]:
    role_token = str(role or "asset")
    return {
        "schema": "infini.sprite-contract.runtime-entity.v1",
        "role": role_token,
        "targetSizePx": final_sprite_canvas(target_size),
        "background": chroma_name() if uses_key_background() else "transparent",
        "singleSubject": True,
        "transparentAfterPostprocess": True,
        "noPlaceholder": True,
    }


def visual_background_transport_rule() -> str:
    final = "Every baked_sprite and equipOverlay final PNG requires a transparent background, not an opaque background. "
    if uses_key_background():
        return final + (
            f"The local sprite_keyer creates final transparency from a raw image on a solid {chroma_name()} key background. "
            "Author item/entity/overlay prompts for that raw image background, not raw transparency; preserve all authored foreground colors."
        )
    return final + "Local background removal is disabled; request a transparent background in the raw image, not a solid key."


def role_contract_prompt_clause(role: str, canvas: int) -> str:
    if role == "item":
        subject = "inventory item"
        placement = "single centered inventory sprite"
    elif role == "vfx_strip":
        subject = "VFX strip texture ingredient"
        placement = ("one VFX strip texture ingredient, preserve the full authored frame and UV placement, "
                     "the long axis may reach the frame edges, no rotation, crop, recentering or silhouette refit, no UI or atlas")
    elif role == "vfx_cutout":
        subject = "VFX texture ingredient"
        placement = "one isolated VFX texture ingredient, preserve authored orientation, no UI or atlas"
    elif role == "equip_overlay":
        subject = "wearable equipment overlay"
        placement = "single centered wearable layer, isolated from any player body or inventory card"
    else:
        subject = str(role).removeprefix("runtime:").removeprefix("entity:").replace("_", " ")
        placement = f"single centered {subject} sprite"
    canvas = final_sprite_canvas(canvas)
    background = f"solid {chroma_name()} key background" if uses_key_background() else "transparent background"
    edges = "preserve authored soft effect edges" if sprite_uses_soft_alpha(role) else "crisp hard pixels"
    return (
        f"{placement}, {canvas}x{canvas} pixel-art canvas, {edges}, "
        f"{background}, no scene, no text, no extra entities"
    )


def normalize_asset_prompt(data: dict[str, Any], role: str, prompt: str, canvas: int) -> str:
    authored = compact_visual_words(prompt, 1400)
    clause = role_contract_prompt_clause(role, canvas)
    text = compact_visual_words(f"{authored}. {clause}" if authored else clause, 1800)
    visual = data.get("visual")
    if role == "item" and isinstance(visual, Mapping) and "grip" in visual:
        # The Visual stage validates this atomic object. Forward it literally;
        # do not infer the contact point or truncate art to make room for metadata.
        grip = json.dumps(visual["grip"], separators=(",", ":"), allow_nan=False)
        text += (
            f". Place the handle/hand-contact point at normalized final canvas coordinates {grip}; "
            "upper-left=(0,0), lower-right=(1,1), after framing/padding and before facing flips."
        )
    return text


def effective_projectile_canvas(data: Mapping[str, Any]) -> int:
    runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), Mapping) else {}
    largest = 16
    for entity in runtime.get("entities") or []:
        if not isinstance(entity, Mapping) or entity.get("kind") == "item_body":
            continue
        hitbox = entity.get("hitbox") if isinstance(entity.get("hitbox"), Mapping) else {}
        largest = max(largest, int(hitbox.get("widthPx") or 16), int(hitbox.get("heightPx") or 16))
    for canvas in (24, 32, 48, 64, 96, 128):
        if largest <= canvas:
            return canvas
    return 128


__all__ = [
    "asset_negative_prompt", "chroma_rgb", "chroma_name", "image_backend_is_zimage",
    "zimage_positive_only_enabled", "compact_visual_words", "sprite_contract_for",
    "role_contract_prompt_clause", "normalize_asset_prompt", "effective_projectile_canvas",
    "visual_background_transport_rule",
]
