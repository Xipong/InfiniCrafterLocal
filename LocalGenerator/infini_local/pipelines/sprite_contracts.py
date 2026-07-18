from __future__ import annotations

import math
from typing import Any

from infini_local.pipelines.pipeline_visual_config import (
    BG_COLOR,
    BG_REMOVE_MODE,
    CHILD_ICON_TARGET_FILL,
    FIELD_ICON_TARGET_FILL,
    IMAGE_BACKEND,
    IMPACT_ICON_TARGET_FILL,
    ITEM_ICON_TARGET_FILL,
    PROJECTILE_ICON_TARGET_FILL,
    REMOVE_BG,
    SDCPP_MODEL,
    SDCPP_SERVER_COMMAND_TEMPLATE,
    SDCPP_SERVER_EXTRA_ARGS,
    SPRITE_EFFECT_CORE_ALPHA_THRESHOLD,
    SPRITE_ITEM_CORE_ALPHA_THRESHOLD,
    ZIMAGE_PROMPT_CONTRACT,
)

# AGENT MAP: cycle-safe sprite prompt/geometry contract helpers shared by
# visual prompts and sprite postprocessing. No image IO or gameplay routing here.




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


def image_backend_is_zimage() -> bool:
    """True when the configured image backend should use the Z-Image prompt contract."""
    if (IMAGE_BACKEND or "").lower() != "sdcpp":
        return False
    mode = ZIMAGE_PROMPT_CONTRACT
    if mode in {"0", "false", "off", "no", "disabled", "disable"}:
        return False
    if mode in {"1", "true", "on", "yes", "force", "forced"}:
        return True
    hay = " ".join([
        SDCPP_MODEL,
        SDCPP_SERVER_COMMAND_TEMPLATE,
        SDCPP_SERVER_EXTRA_ARGS,
    ]).lower().replace("_", "-")
    return "z-image" in hay or "zimage" in hay


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
            "promptPoseWords": "compose one clean projectile in canonical local +X pose: leading tip or nose faces screen-right, tail or trail faces screen-left; this local texture is later rotated to any world-space travel direction",
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
            "promptPoseWords": "one tiny separate object only; if elongated, use canonical local +X with its leading tip screen-right because this local texture is later rotated to any world-space travel direction",
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
    spec["maxLongAxisPx"] = max(spec["minLongAxisPx"], min(size, int(math.ceil(size * float(spec["maxFill"])))) )
    # v0.4.49: effect extent must not be stricter than the accepted core long-axis.
    spec["maxEffectLongAxisPx"] = max(int(spec.get("maxLongAxisPx") or size), int(spec["targetLongAxisPx"]))
    return spec


def role_contract_prompt_clause(role: str, canvas: int) -> str:
    spec = sprite_contract_for(role, canvas)
    return f"{spec['promptPoseWords']}, {spec['promptFillWords']}"


__all__ = [
    "chroma_rgb",
    "chroma_name",
    "image_backend_is_zimage",
    "role_contract_prompt_clause",
    "sprite_background_positive_clause",
    "sprite_contract_for",
]
