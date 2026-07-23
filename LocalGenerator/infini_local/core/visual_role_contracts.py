from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class VisualRoleContract:
    role: str
    prompt_field: str
    required_when: str
    baked_asset_allowed: bool
    reuse_item_sprite_allowed: bool = False
    distinct_from_item_allowed: bool = False
    asset_decision: str = ""


VISUAL_ROLE_CONTRACTS: tuple[VisualRoleContract, ...] = (
    VisualRoleContract(
        role="item",
        prompt_field="itemIconPrompt",

        required_when="always",
        baked_asset_allowed=False,
        asset_decision=(
            "the item icon is always the required generated inventory/held sprite; "
            "it is never represented by a bakedAssets.item entry"
        ),
    ),
    VisualRoleContract(
        role="projectile",
        prompt_field="projectileSpritePrompt",

        required_when="the role is visually relevant; a non-empty prompt is mandatory when mode=baked_sprite",
        baked_asset_allowed=True,
        reuse_item_sprite_allowed=True,
        distinct_from_item_allowed=True,
    ),
    VisualRoleContract(
        role="impact",
        prompt_field="impactSpritePrompt",

        required_when="the role is visually relevant; a non-empty prompt is mandatory when mode=baked_sprite",
        baked_asset_allowed=True,
    ),
    VisualRoleContract(
        role="child",
        prompt_field="childSpritePrompt",

        required_when="the accepted runtime has a child role; a non-empty prompt is mandatory when mode=baked_sprite",
        baked_asset_allowed=True,
    ),
    VisualRoleContract(
        role="field",
        prompt_field="fieldSpritePrompt",

        required_when="the accepted runtime has a field role; a non-empty prompt is mandatory when mode=baked_sprite",
        baked_asset_allowed=True,
    ),
    VisualRoleContract(
        role="equip_overlay",
        prompt_field="equipOverlayPrompt",

        required_when=(
            "resultKind is armor or accessory; author one transparent single-pose overlay emblem, "
            "not an armor sheet or inventory icon"
        ),
        baked_asset_allowed=True,
    ),
)

VISUAL_ROLE_CONTRACT_BY_NAME = MappingProxyType({
    contract.role: contract
    for contract in VISUAL_ROLE_CONTRACTS
})
VISUAL_BAKED_ROLE_CONTRACTS = tuple(
    contract
    for contract in VISUAL_ROLE_CONTRACTS
    if contract.baked_asset_allowed
)
VISUAL_BAKED_ROLE_PROMPT_FIELDS = MappingProxyType({
    contract.role: contract.prompt_field
    for contract in VISUAL_BAKED_ROLE_CONTRACTS
})
VISUAL_FORBIDDEN_BAKED_ASSET_KEYS = ("item", "vfx")


def visual_director_role_fields() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for contract in VISUAL_ROLE_CONTRACTS:
        card: dict[str, Any] = {
            "promptField": contract.prompt_field,
        }
        if contract.baked_asset_allowed:
            card["assetModeField"] = f"bakedAssets.{contract.role}.mode"
        else:
            card["assetDecision"] = contract.asset_decision
        card["requiredWhen"] = contract.required_when
        out[contract.role] = card
    return out


__all__ = [
    "VisualRoleContract",
    "VISUAL_ROLE_CONTRACTS",
    "VISUAL_ROLE_CONTRACT_BY_NAME",
    "VISUAL_BAKED_ROLE_CONTRACTS",
    "VISUAL_BAKED_ROLE_PROMPT_FIELDS",

    "VISUAL_FORBIDDEN_BAKED_ASSET_KEYS",
    "visual_director_role_fields",
]
