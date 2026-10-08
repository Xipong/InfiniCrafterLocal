from __future__ import annotations

"""Image-backend prompt guards for exact runtime-entity assets.

This module knows visual roles and sprite constraints only. It never reads or
infers a weapon family, attack shape, or gameplay topology from prose.
"""

import json
import re
from typing import Any, Mapping

from infini_local.core.llm_stage_messages import generation_art_direction

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


def image_generation_prompt_suffix() -> str:
    """Explicit target/style metadata outside the existing authored-art bound."""
    direction = generation_art_direction()
    return ". Terraria (tModLoader) game asset." + (f" {direction}" if direction else "")


def image_final_frame_prompt_clause(data: Mapping[str, Any], role: str, canvas: int, *, entity_id: str = "") -> str:
    """Read-only selected main-PNG facts; no guesses from hitboxes or prose."""
    raw_runtime = data.get("runtimeProgram")
    runtime: Mapping[str, Any] = raw_runtime if isinstance(raw_runtime, Mapping) else {}
    entities = [row for row in runtime.get("entities") or [] if isinstance(row, Mapping)]
    raw_root = data.get("visual")
    root: Mapping[str, Any] = raw_root if isinstance(raw_root, Mapping) else {}
    entity = next((row for row in entities if row.get("id") == entity_id), None) if entity_id else None
    owner: Mapping[str, Any]
    if role == "item":
        owner = root
        root_project = True
    elif role.startswith(("runtime:", "entity:")) and entity is not None:
        raw_entity_visual = entity.get("visual")
        entity_visual: Mapping[str, Any] = raw_entity_visual if isinstance(raw_entity_visual, Mapping) else {}
        root_project = entity.get("kind") == "item_body" or entity_visual.get("assetMode") == "reuse_item_icon"
        if not root_project and entity_visual.get("assetMode") != "baked_sprite":
            return ""
        owner = root if root_project else entity_visual
    else:
        # Dedicated impacts, UV ingredients and overlays do not use main-body R.
        return ""
    if not any(field in owner for field in ("renderSizePx", "forwardAngleDegrees")):
        # Retain delivered legacy prompts and metadata absence; do not give a
        # guessed display budget to an old project or a manual-only fixture.
        return ""
    facts: dict[str, Any] = {"canvasSizePx": final_sprite_canvas(canvas)}
    if entity is not None:
        facts["entityId"] = entity["id"]
    for field in ("renderSizePx", "forwardAngleDegrees", "silhouette", "visualIdentity"):
        if field in owner:
            facts[field] = owner[field]
    multipliers: dict[str, Any] = {}
    if root_project:
        raw_gameplay = data.get("gameplay")
        gameplay: Mapping[str, Any] = raw_gameplay if isinstance(raw_gameplay, Mapping) else {}
        if "itemScale" in gameplay:
            multipliers["gameplay.itemScale"] = gameplay["itemScale"]
        for field in ("inventoryScale", "worldScale"):
            if field in root:
                multipliers["visual." + field] = root[field]
        if "grip" in root:
            facts["grip"] = root["grip"]
        shared = []
        for row in entities:
            raw_visual = row.get("visual")
            visual: Mapping[str, Any] = raw_visual if isinstance(raw_visual, Mapping) else {}
            if row.get("kind") == "item_body" or visual.get("assetMode") != "reuse_item_icon":
                continue
            scale_row: dict[str, Any] = {"entityId": row["id"]}
            raw_hitbox = row.get("hitbox")
            hitbox: Mapping[str, Any] = raw_hitbox if isinstance(raw_hitbox, Mapping) else {}
            if "drawScale" in hitbox:
                scale_row["hitbox.drawScale"] = hitbox["drawScale"]
            if "scale" in visual:
                scale_row["visual.scale"] = visual["scale"]
            shared.append(scale_row)
        if shared:
            facts["sharedEntityMultipliers"] = shared
    elif entity is not None:
        raw_hitbox = entity.get("hitbox")
        hitbox = raw_hitbox if isinstance(raw_hitbox, Mapping) else {}
        if "drawScale" in hitbox:
            multipliers["hitbox.drawScale"] = hitbox["drawScale"]
        if "scale" in owner:
            multipliers["visual.scale"] = owner["scale"]
    if multipliers:
        facts["multipliers"] = multipliers
    grip_instruction = (
        " The visible handle/hand-contact region must contain the declared final-space grip, not the guard, blade or empty space. "
        "It is a normalized final-canvas point after framing/padding, not a RAW-image coordinate; keep that contact region there before facing flips."
        if "grip" in facts else ""
    )
    return (
        ". Read-only final-frame facts: " + json.dumps(facts, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        + ". C=canvasSizePx is the final baked frame side; R=renderSizePx is its base world-pixel max-side, not hitbox or visible shaft length. "
        "When R is declared, base pixel scale is R/C; visible alpha extent uses that scale and independent draw multipliers. "
        "Keep major pixel clusters readable at this selected display budget; a larger bake canvas alone does not enlarge the world body. "
        "Item inventory is caller-fit times inventoryScale, without R/C; dropped world uses R/C times caller scale times worldScale; "
        "held item uses R/C times adjusted item scale (gameplay.itemScale included once). "
        "Entity body uses R/C times clamp(current Projectile.scale,0.1,8), initially hitbox.drawScale times visual.scale; later growth is independent. "
        "forwardAngleDegrees describes the final PNG local forward axis: 0=+X, positive clockwise in y-down coordinates, before facing/gravity flips. "
        "Retain the literal authored silhouette, component count, spatial arrangement and distinctive elements from the art description and read-only facts. "
        "Do not omit or merge authored parts to simplify the sprite."
        + grip_instruction
    )


def normalize_asset_prompt(data: dict[str, Any], role: str, prompt: str, canvas: int, *, entity_id: str = "") -> str:
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
    # Append outside the historical authored-art bound: style must not displace
    # literal geometry, framing/background or the accepted hand-contact point.
    return text + image_final_frame_prompt_clause(data, role, canvas, entity_id=entity_id) + image_generation_prompt_suffix()


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
    "image_generation_prompt_suffix", "image_final_frame_prompt_clause",
]
