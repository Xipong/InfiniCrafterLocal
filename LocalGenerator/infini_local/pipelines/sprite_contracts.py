from __future__ import annotations

import math
from typing import Any

from infini_local.pipelines import pipeline_visual_config as visual_config
from infini_local.pipelines.pipeline_visual_config import (
    CHILD_ICON_TARGET_FILL,
    FIELD_ICON_TARGET_FILL,
    IMAGE_BACKEND,
    IMPACT_ICON_TARGET_FILL,
    ITEM_ICON_TARGET_FILL,
    PROJECTILE_ICON_TARGET_FILL,
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
    # Exact supported aliases only; a typo must never choose a different key.
    colors = {
        "magenta": (255, 0, 255),
        "green": (0, 255, 0), "lime": (0, 255, 0), "greenscreen": (0, 255, 0),
        "blue": (0, 0, 255), "cyan": (0, 255, 255),
        "white": (255, 255, 255), "black": (0, 0, 0),
    }
    name = str(visual_config.BG_COLOR).strip().lower()
    if name not in colors:
        raise ValueError(f"Invalid INFINI_BG_COLOR {visual_config.BG_COLOR!r}; supported: {', '.join(colors)}")
    return colors[name]


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


def uses_key_background() -> bool:
    """Match apply_background_removal: legacy enabled modes use sprite_keyer."""
    mode = (visual_config.BG_REMOVE_MODE or "sprite_keyer").strip().lower().replace("-", "_")
    return bool(visual_config.REMOVE_BG) and mode not in {"", "none", "off"}


def sprite_background_positive_clause() -> str:
    if not uses_key_background():
        return "on a transparent background, no scene, no floor, no cast shadow"
    # The supported local keyer owns alpha, including legacy mode aliases.
    return f"on a perfectly solid untextured {chroma_name()}, object fully separated from background, no floor, no cast shadow, no gradient"


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


def final_sprite_canvas(target_size: int) -> int:
    """Final PNG bounds (geometry measurements may use larger raw/master images)."""
    size = int(target_size)
    if size != target_size or not 16 <= size <= 128:
        raise ValueError(f"Unsupported final sprite canvas {target_size!r}; expected integer 16..128")
    return size


def sprite_uses_soft_alpha(role: str) -> bool:
    """Exact processing roles only; entity identity never selects alpha policy."""
    return str(role).strip().lower() in {"impact", "field", "effect", "runtime:field", "vfx_cutout", "vfx_strip"}


def sprite_contract_for(role: str, target_size: int = 32) -> dict[str, Any]:
    # Also used to measure high-resolution raw/master images. Final PNG bounds
    # belong to final_sprite_canvas, not to this dimension-relative geometry table.
    role = (role or "item").lower()
    size = max(16, int(target_size or 32))
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
        "equip_overlay": {
            "targetFill": 0.78,
            "minFill": 0.58,
            "maxFill": 0.94,
            "coreAlphaThreshold": SPRITE_ITEM_CORE_ALPHA_THRESHOLD,
            "marginPx": 2,
            "cropPadPx": 1,
            "maxEdgeTouch": 0.08,
            "promptFillWords": "the wearable layer should fit comfortably inside the canvas with transparent breathing room around its silhouette",
            "promptPoseWords": "compose one centered wearable equipment overlay only, isolated from any player body or inventory card",
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
    table["vfx_cutout"] = {
        "targetFill": 0.82, "minFill": 0.10, "maxFill": 0.98,
        "coreAlphaThreshold": 1, "marginPx": 1 if size <= 32 else 2,
        "cropPadPx": 1, "maxEdgeTouch": 0.18,
        "promptFillWords": "keep one isolated texture ingredient inside its independent canvas",
        "promptPoseWords": "preserve the authored ingredient orientation and soft edges; no item or weapon body",
    }
    table["vfx_strip"] = {
        **table["vfx_cutout"], "targetFill": 1.0, "minFill": 0.0, "maxFill": 1.0,
        "marginPx": 0, "cropPadPx": 0, "maxEdgeTouch": 1.0,
        "promptFillWords": "preserve the full authored frame and UV placement; the long axis may reach the frame edges",
        "promptPoseWords": "one VFX texture ingredient, no atlas; no rotation, crop, recentering or silhouette refit",
    }
    # Runtime bodies retain their authored orientation. In particular do not route
    # runtime:projectile through the legacy +X projectile contract/canonicalizer.
    runtime_roles = {"held_body", "projectile", "deployed_entity", "helper", "child_projectile"}
    if role.startswith("runtime:") and role.removeprefix("runtime:") in runtime_roles:
        spec = dict(table["equip_overlay"])
        spec.update(promptPoseWords="preserve the authored entity pose",
                    promptFillWords="keep the complete entity inside the frame")
    else:
        table_role = "field" if role in {"runtime:field", "effect"} else role
        spec = dict(table.get(table_role, table["item"]))
    spec["alphaMode"] = "soft" if sprite_uses_soft_alpha(role) else "binary"
    if sprite_uses_soft_alpha(role):
        spec["coreAlphaThreshold"] = 1
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
    "final_sprite_canvas",
    "uses_key_background",
]
