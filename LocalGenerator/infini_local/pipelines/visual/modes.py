from __future__ import annotations

"""Canonical delivery/runtime meaning of authored visual asset modes."""

from types import MappingProxyType
from typing import Mapping


VISUAL_ASSET_MODE_DESCRIPTIONS: Mapping[str, str] = MappingProxyType({
    "baked_sprite": "Generate and deliver a distinct PNG for this exact runtime entity. item_body owns the root item project; a distinct entity owns its renderSizePx, preferredCanvasSize and forwardAngleDegrees.",
    "no_asset": "Deliver no PNG and draw no entity body; independent runtime VFX may still draw.",
    "reuse_item_icon": "Deliver no separate PNG; resolve this entity to the item_body generated PNG with identical pixels, root base renderSizePx, canvas and forwardAngleDegrees. No own prompt/size/canvas/axis; entity scale remains independent.",
    "runtime_geometry": "Deliver no PNG; author explicit geometry: a centered body_segment with chosen length and axis, or collision_path following an existing beam/lash centerline. Width, RGB color and opacity are independent presentation choices, not inherited from hitbox/light. This is a plain untextured solid strip, not a textured skin; independent VFX overlays do not replace or hide this base.",
})
VISUAL_ASSET_MODES = tuple(VISUAL_ASSET_MODE_DESCRIPTIONS)


def visual_asset_mode_catalog() -> list[dict[str, str]]:
    return [
        {"mode": mode, "runtimeEffect": runtime_effect}
        for mode, runtime_effect in VISUAL_ASSET_MODE_DESCRIPTIONS.items()
    ]


__all__ = [
    "VISUAL_ASSET_MODE_DESCRIPTIONS",
    "VISUAL_ASSET_MODES",
    "visual_asset_mode_catalog",
]
