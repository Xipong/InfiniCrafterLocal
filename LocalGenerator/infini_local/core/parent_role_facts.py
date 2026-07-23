from __future__ import annotations

from typing import Any

from infini_local.core.item_identity_tools import item_bool, item_field, item_num, name_of


def strong_parent_roles(item: dict[str, Any] | None) -> set[str]:
    """Return only executable raw parent roles that must outrank incidental placement."""
    if not isinstance(item, dict):
        return set()
    roles: set[str] = set()
    if item_num(item, "damage") > 0:
        roles.add("weapon")
    if any(item_num(item, field) > 0 for field in ("pickPower", "axePower", "hammerPower")):
        roles.add("tool")
    if item_bool(item, "accessory"):
        roles.add("accessory")
    if any(item_num(item, field, -1) >= 0 for field in ("headSlot", "bodySlot", "legSlot")):
        roles.add("armor")
    if any(item_num(item, field) > 0 for field in ("healLife", "healMana", "buffType")):
        roles.add("potion")
    return roles


def sole_strong_parent_role_obligation(
    *parents: dict[str, Any] | None,
) -> dict[str, Any]:
    typed_parents = [parent for parent in parents if isinstance(parent, dict)]
    roles = set().union(*(strong_parent_roles(parent) for parent in typed_parents))
    if len(roles) != 1:
        return {"applicable": False, "strongParentRoles": sorted(roles)}
    role = next(iter(roles))
    expected_kind = role
    if role == "weapon":
        weapon_parents = [
            parent for parent in typed_parents
            if "weapon" in strong_parent_roles(parent)
        ]
        if weapon_parents and all(
            item_field(parent, "consumable", None) is True
            for parent in weapon_parents
        ):
            expected_kind = "consumable_weapon"
    armor_slots: set[str] = set()
    if role == "armor":
        for parent in typed_parents:
            if item_num(parent, "headSlot", -1) >= 0:
                armor_slots.add("head")
            if item_num(parent, "bodySlot", -1) >= 0:
                armor_slots.add("body")
            if item_num(parent, "legSlot", -1) >= 0:
                armor_slots.add("legs")
    return {
        "applicable": True,
        "strongParentRoles": [role],
        "expectedResultKind": expected_kind,
        "expectedArmorSlots": sorted(armor_slots),
    }


def placeable_parent_candidates(*parents: dict[str, Any] | None) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for parent in parents:
        if not isinstance(parent, dict):
            continue
        create_tile = int(item_num(parent, "createTile", -1))
        create_wall = int(item_num(parent, "createWall", -1))
        if create_tile < 0 and create_wall < 0:
            continue
        candidates.append({
            "name": name_of(parent),
            "createTile": create_tile,
            "createWall": create_wall,
            "placeStyle": int(item_num(parent, "placeStyle", 0)),
        })
    return candidates


def placeable_only_parent_obligation(
    *parents: dict[str, Any] | None,
) -> dict[str, Any]:
    roles = sorted(set().union(*(strong_parent_roles(parent) for parent in parents)))
    candidates = placeable_parent_candidates(*parents)
    applicable = bool(candidates and not roles)
    return {
        "applicable": applicable,
        "strongParentRoles": roles,
        "expectedResultKind": "furniture" if applicable else "",
        "requiredEngineFunction": "placeable_behavior" if applicable else "",
        "placeableParents": candidates if applicable else [],
    }


__all__ = [
    "placeable_only_parent_obligation",
    "placeable_parent_candidates",
    "sole_strong_parent_role_obligation",
    "strong_parent_roles",
]
