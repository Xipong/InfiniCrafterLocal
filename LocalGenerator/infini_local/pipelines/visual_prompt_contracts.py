from __future__ import annotations

"""Image-backend prompt guards for exact runtime-entity assets.

This module knows visual roles and sprite constraints only. It never reads or
infers a weapon family, attack shape, or gameplay topology from prose.
"""

import re
from typing import Any, Mapping

from infini_local.pipelines import pipeline_visual_config as visual_config


def asset_negative_prompt(role: str = "item") -> str:
    role_name = str(role or "asset").replace("entity:", "runtime entity ")
    return (
        f"scene, environment, character, enemy, UI, text, watermark, multiple unrelated objects, "
        f"blur, antialiasing, photorealism; draw only the {role_name} sprite"
    )


def chroma_rgb() -> tuple[int, int, int]:
    name = str(getattr(visual_config, "BG_COLOR", "magenta") or "magenta").lower()
    return {"green": (0, 255, 0), "blue": (0, 0, 255), "cyan": (0, 255, 255)}.get(name, (255, 0, 255))


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
        "targetSizePx": max(8, min(256, int(target_size or 32))),
        "background": chroma_name(),
        "singleSubject": True,
        "transparentAfterPostprocess": True,
        "noPlaceholder": True,
    }


def role_contract_prompt_clause(role: str, canvas: int) -> str:
    if role == "item":
        subject = "inventory item"
        placement = "single centered inventory sprite"
    elif role == "equip_overlay":
        subject = "wearable equipment overlay"
        placement = "single centered wearable layer, isolated from any player body or inventory card"
    else:
        subject = str(role).removeprefix("entity:").replace("_", " ")
        placement = f"single centered {subject} sprite"
    return (
        f"{placement}, {int(canvas)}x{int(canvas)} pixel-art canvas, crisp hard pixels, "
        f"solid {chroma_name()} key background, no scene, no text, no extra entities"
    )


def normalize_asset_prompt(data: dict[str, Any], role: str, prompt: str, canvas: int) -> str:
    del data
    authored = compact_visual_words(prompt, 1400)
    clause = role_contract_prompt_clause(role, canvas)
    return compact_visual_words(f"{authored}. {clause}" if authored else clause, 1800)


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
]
