from __future__ import annotations

"""Canonical delivery/runtime meaning of authored visual asset modes."""

from types import MappingProxyType
from typing import Mapping

from infini_local.core.images import config as image_config


VISUAL_ASSET_MODE_DESCRIPTIONS: Mapping[str, str] = MappingProxyType({
    "baked_sprite": "Generate and deliver a real PNG, never a placeholder. Required for kind=item_body regardless of entityId: use visualProjectRef=item and only entityId/assetMode/visualProjectRef/scale; inherit the root item design without prompt/silhouette/visualIdentity. A distinct baked entity uses visualProjectRef=entity and owns its prompt, silhouette, visualIdentity, renderSizePx, preferredCanvasSize and forwardAngleDegrees.",
    "no_asset": "Deliver no PNG and draw no entity body; independent runtime VFX may still draw.",
    "reuse_item_icon": "Only a non-item_body entity representing the same physical object as item_body may use this mode. Set visualProjectRef=item and never create a second visual project; deliver no separate PNG and resolve to the item_body generated PNG with identical pixels, root base renderSizePx, canvas and forwardAngleDegrees. Only entityId/assetMode/visualProjectRef/scale; no own prompt/size/canvas/axis. Entity scale remains independent.",
    "runtime_geometry": "Deliver no PNG; author explicit geometry: a centered body_segment with chosen length and axis, or collision_path following an existing beam/lash centerline. Width, RGB color and opacity are independent presentation choices, not inherited from hitbox/light. This is a plain untextured solid strip, not a textured skin; independent VFX overlays do not replace or hide this base.",
})
VISUAL_ASSET_MODES = tuple(VISUAL_ASSET_MODE_DESCRIPTIONS)


def entity_baked_sprites_enabled() -> bool:
    return image_config.VISUAL_ASSET_MODE == "full"


def visual_asset_mode_catalog() -> list[dict[str, str]]:
    return [
        {"mode": mode, "runtimeEffect": (runtime_effect if mode != "baked_sprite" or entity_baked_sprites_enabled() else
            "Only item_body may use baked_sprite and must reference the root item project. Separate entity PNG generation is disabled; choose reuse_item_icon, runtime_geometry or no_asset for non-item entities. VFX ingredient and equipment-overlay PNG generation remain independent.")}
        for mode, runtime_effect in VISUAL_ASSET_MODE_DESCRIPTIONS.items()
    ]


__all__ = [
    "VISUAL_ASSET_MODE_DESCRIPTIONS",
    "VISUAL_ASSET_MODES",
    "visual_asset_mode_catalog",
]
