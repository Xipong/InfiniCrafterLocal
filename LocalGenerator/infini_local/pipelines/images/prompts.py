from __future__ import annotations

"""Image-backend prompt guards for exact runtime-entity assets.

This module knows visual roles and sprite constraints only. It never reads or
infers a weapon family, attack shape, or gameplay topology from prose.
"""

import copy
import json
import re
from typing import Any, Mapping

from infini_local.core.llm_stage_messages import generation_art_direction
from infini_local.core.runtime_authoring.capability_registry import PROJECTILE_MODIFIER_COMPONENTS
from infini_local.core.visual_contract_schema import front_hand_sprite_requirement

from infini_local.core.images import config as visual_config
from infini_local.core.images.contracts import chroma_rgb, uses_key_background, final_sprite_canvas, sprite_uses_soft_alpha, native_held_frame_facts
from infini_local.pipelines.visual.assets import equipment_overlay_requirement


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


def _image_equipment_frame_prompt_clause(data: Mapping[str, Any], canvas: int) -> str:
    """Forward the accepted overlay design and existing single-PNG draw budget."""
    raw_kit = data.get("visualKit")
    kit = raw_kit if isinstance(raw_kit, Mapping) else {}
    overlay = kit.get("equipOverlay")
    requirement = equipment_overlay_requirement(data)
    # Missing authored designs still belong to Visual validation/Repair. Do not
    # borrow the inventory silhouette or infer a wearable from its name/category.
    if not requirement["required"] or not isinstance(overlay, Mapping):
        return ""
    if not all(isinstance(overlay.get(field), str) and overlay[field].strip()
               for field in ("prompt", "silhouette", "visualIdentity")):
        return ""
    # Read-only projection of GeneratedEquipOverlayDrawLayer.Draw's whole-texture
    # fit, not a new authored size/anchor or a guarantee about visible alpha size.
    placement = {
        "head": ("head", 25),
        "body": ("torso", 31),
        "legs": ("legs", 27),
        "accessory": ("body", 18),
    }.get(requirement["slot"])
    if placement is None:
        return ""
    body_part, fit = placement
    facts = {
        "equipmentSlot": requirement["slot"],
        "canvasSizePx": final_sprite_canvas(canvas),
        "wholeTextureFitMaxPx": fit,
        "silhouette": overlay["silhouette"],
        "visualIdentity": overlay["visualIdentity"],
    }
    raw_visual = data.get("visual")
    visual = raw_visual if isinstance(raw_visual, Mapping) else {}
    if requirement["slot"] == "accessory" and "accessoryMount" in visual:
        facts["accessoryMount"] = visual["accessoryMount"]
    mount_placement = "; its authored accessoryMount selects body-local placement" if "accessoryMount" in facts else ""
    return (
        ". Read-only equipment overlay facts: " + json.dumps(facts, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        + f". One static centered PNG badge attached to the player's {body_part}{mount_placement}. "
        "The renderer fits the whole final PNG within wholeTextureFitMaxPx world pixels on its longest side; "
        "padding makes the visible silhouette smaller, so keep the authored silhouette, parts, arrangement and identity readable at that size."
    )


def selected_main_image_visual(data: Mapping[str, Any], role: str, *, entity_id: str = "") -> Mapping[str, Any] | None:
    """Select the same explicit PNG owner for image instructions and pixel framing."""
    root = data.get("visual")
    root = root if isinstance(root, Mapping) else {}
    if role == "item":
        return root
    runtime = data.get("runtimeProgram")
    if not role.startswith(("runtime:", "entity:")) or not entity_id or not isinstance(runtime, Mapping):
        return None
    entity = next((row for row in runtime.get("entities") or []
                   if isinstance(row, Mapping) and row.get("id") == entity_id), None)
    if entity is None:
        return None
    visual = entity.get("visual")
    visual = visual if isinstance(visual, Mapping) else {}
    if entity.get("kind") == "item_body" or visual.get("assetMode") == "reuse_item_icon":
        return root
    return visual if visual.get("assetMode") == "baked_sprite" else None


def image_final_frame_prompt_clause(data: Mapping[str, Any], role: str, canvas: int, *, entity_id: str = "") -> str:
    """Read-only selected PNG facts; no guesses from hitboxes or prose."""
    if role == "equip_overlay":
        return _image_equipment_frame_prompt_clause(data, canvas)
    raw_runtime = data.get("runtimeProgram")
    runtime: Mapping[str, Any] = raw_runtime if isinstance(raw_runtime, Mapping) else {}
    entities = [row for row in runtime.get("entities") or [] if isinstance(row, Mapping)]
    raw_root = data.get("visual")
    root: Mapping[str, Any] = raw_root if isinstance(raw_root, Mapping) else {}
    entity = next((row for row in entities if row.get("id") == entity_id), None) if entity_id else None
    owner = selected_main_image_visual(data, role, entity_id=entity_id)
    if owner is None:
        return ""  # Dedicated impacts and UV ingredients do not use main-body R.
    entity_visual = entity.get("visual") if entity is not None else None
    root_project = role == "item" or (entity is not None and (
        entity.get("kind") == "item_body" or isinstance(entity_visual, Mapping) and entity_visual.get("assetMode") == "reuse_item_icon"))
    if "runtimeProgram" in data and any(field not in owner for field in ("renderSizePx", "forwardAngleDegrees")):
        raise ValueError("Selected main PNG requires explicit renderSizePx and forwardAngleDegrees")
    if not any(field in owner for field in ("renderSizePx", "forwardAngleDegrees")):
        return ""  # Standalone image diagnostics have no runtime display project.
    facts: dict[str, Any] = {"canvasSizePx": final_sprite_canvas(canvas)}
    if entity is not None:
        facts["entityId"] = entity["id"]
    for field in ("renderSizePx", "forwardAngleDegrees", "silhouette", "visualIdentity", "grip"):
        if field in owner:
            facts[field] = owner[field]
    multipliers: dict[str, Any] = {}
    if root_project:
        native_frame = native_held_frame_facts(data, canvas)
        if native_frame:
            facts["nativeHeldCanvas"] = native_frame
        raw_gameplay = data.get("gameplay")
        gameplay: Mapping[str, Any] = raw_gameplay if isinstance(raw_gameplay, Mapping) else {}
        if "itemScale" in gameplay:
            multipliers["gameplay.itemScale"] = gameplay["itemScale"]
        for field in ("inventoryScale", "worldScale"):
            if field in root:
                multipliers["visual." + field] = root[field]
        # Item-use links describe accepted actions, not an emission point on
        # this PNG. Resolve only explicit item and action target identities.
        item_id = runtime.get("itemEntityId")
        items = [row for row in entities if item_id and row.get("id") == item_id]
        item = items[0] if len(items) == 1 and items[0].get("kind") == "item_body" else None
        uses = []
        if item is not None:
            for binding in runtime.get("bindings") or []:
                policy = binding.get("usePolicy") if isinstance(binding, Mapping) else None
                action = policy.get("action") if isinstance(policy, Mapping) else None
                if not isinstance(action, Mapping) or action.get("kind") != "spawn_entity":
                    continue
                targets = [row for row in entities if action.get("targetId") and row.get("id") == action["targetId"]]
                target = targets[0] if len(targets) == 1 else None
                if target is not None and isinstance(target.get("spawn"), Mapping):
                    spawn = target["spawn"]
                    placement = {key: copy.deepcopy(spawn[key]) for key in ("placement", "offsetPx") if key in spawn}
                    if spawn.get("offsetPx") and "aim" in spawn:
                        placement["aim"] = copy.deepcopy(spawn["aim"])
                    above = spawn.get("overTarget")
                    if isinstance(above, Mapping) and above.get("heightTiles"):
                        placement["overTarget"] = {"heightTiles": copy.deepcopy(above["heightTiles"])}
                    uses.append({"bindingId": binding.get("id"), "input": binding.get("input"),
                                 "action": copy.deepcopy(dict(action)), "targetPlacement": placement})
        if uses:
            facts["itemUseSpawnsReadOnly"] = {"itemEntityId": item["id"], "bindings": uses}
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
            for field in ("hitboxCurve", *PROJECTILE_MODIFIER_COMPONENTS.values(), "whipUsesOwnerGravity"):
                if field in row:
                    scale_row[field] = copy.deepcopy(row[field])
            if "movement" in row and front_hand_sprite_requirement(row) is not None:
                scale_row["movementReadOnly"] = copy.deepcopy(row["movement"])
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
        for field in ("hitboxCurve", *PROJECTILE_MODIFIER_COMPONENTS.values(), "whipUsesOwnerGravity"):
            if field in entity:
                facts[field] = copy.deepcopy(entity[field])
    if entity is not None and "movement" in entity and front_hand_sprite_requirement(entity) is not None:
        facts["movementReadOnly"] = copy.deepcopy(entity["movement"])
    if multipliers:
        facts["multipliers"] = multipliers
    grip_instruction = (
        " Place the artwork handle point at the normalized final-canvas grip in the read-only facts. "
        "The visible handle region must contain that grip, not the guard, blade or empty space. "
        "Coordinates run from upper-left=(0,0) to lower-right=(1,1), before facing flips. "
        "Return a square image with the contact region at those same normalized coordinates; the full frame is resized without cropping or recentering to preserve that contact."
        if "grip" in facts else ""
    )
    return (
        ". Read-only final-frame facts: " + json.dumps(facts, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        + ". renderSizePx is the base in-game size of the whole frame, not the hitbox or the visible object's length; "
        "other scales can change its displayed size. Keep major pixel clusters readable at the selected in-game size. "
        + ("This same item sprite is also used for the listed in-use bodies; keep its design readable in both uses. "
           if facts.get("sharedEntityMultipliers") else "")
        + "forwardAngleDegrees describes the final PNG local forward axis: 0=+X, positive clockwise in y-down coordinates, before facing/gravity flips. "
        "Draw that declared local PNG axis literally. Native item bodies keep the native frame pose without PNG-axis correction or grip-to-hand binding; independent bodies retain their accepted rotation and attachment rules. "
        "Retain the literal authored silhouette, component count, spatial arrangement and distinctive elements from the art description and read-only facts. "
        "Do not omit or merge authored parts to simplify the sprite."
        + grip_instruction
    )


def normalize_asset_prompt(data: dict[str, Any], role: str, prompt: str, canvas: int, *, entity_id: str = "") -> str:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(f"{role}: explicit non-empty authored image prompt required")
    authored = compact_visual_words(prompt, 1400)
    clause = role_contract_prompt_clause(role, canvas)
    text = compact_visual_words(f"{authored}. {clause}", 1800)
    frame_clause = image_final_frame_prompt_clause(data, role, canvas, entity_id=entity_id)
    visual = data.get("visual")
    if not frame_clause and role == "item" and isinstance(visual, Mapping) and "grip" in visual:
        # The Visual stage validates this atomic object. Forward it literally;
        # do not infer the contact point or truncate art to make room for metadata.
        grip = json.dumps(visual["grip"], separators=(",", ":"), allow_nan=False)
        text += (
            f". Place the artwork handle point at normalized final canvas coordinates {grip}; "
            "upper-left=(0,0), lower-right=(1,1), after framing/padding and before facing flips."
        )
    # Append after the authored-art bound: style must not displace
    # literal geometry, framing/background or the accepted hand-contact point.
    return text + frame_clause + image_generation_prompt_suffix()


__all__ = [
    "asset_negative_prompt", "chroma_rgb", "chroma_name", "image_backend_is_zimage",
    "zimage_positive_only_enabled", "compact_visual_words", "sprite_contract_for",
    "role_contract_prompt_clause", "normalize_asset_prompt",
    "visual_background_transport_rule",
    "image_generation_prompt_suffix", "image_final_frame_prompt_clause",
]
