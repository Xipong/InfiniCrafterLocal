from __future__ import annotations

"""Canonical delivery/runtime meaning of authored visual asset modes."""

from types import MappingProxyType
from typing import Mapping


VISUAL_ASSET_MODE_DESCRIPTIONS: Mapping[str, str] = MappingProxyType({
    "baked_sprite": "Generate and deliver a distinct PNG for this exact runtime entity.",
    "no_asset": "Deliver no PNG and draw no entity body; independent runtime VFX may still draw.",
    "reuse_item_icon": "Deliver no separate PNG; resolve this entity to the item_body generated PNG with identical pixels.",
    "runtime_geometry": "Deliver no PNG; draw the built-in bounded runtime primitive from entity hitbox and light fields.",
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
