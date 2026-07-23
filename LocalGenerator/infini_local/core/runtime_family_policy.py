from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from infini_local.core.runtime_overhead_barrage_policy import normalize_overhead_barrage_family


@dataclass(frozen=True, slots=True)
class RuntimeFamilyProfile:
    name: str
    projectile_owned: bool
    held_projectile: bool
    item_bodied_projectile: bool
    held_render_role: str
    hand_pose: str
    release_timing: str
    sound_use: str
    sound_pitch: float = 0.0


# Canonical executor registry. These names cross Python -> JSON -> C#.
# Natural-language authoring terminology must be compiled before this boundary.
_RUNTIME_FAMILY_PROFILES: Final[dict[str, RuntimeFamilyProfile]] = {
    "none": RuntimeFamilyProfile("none", False, False, False, "generic", "short_weapon", "on_release", "soft"),
    "swing": RuntimeFamilyProfile("swing", False, False, False, "swing", "short_weapon", "on_release", "swing", -0.08),
    "thrust": RuntimeFamilyProfile("thrust", True, True, True, "thrust", "two_hand", "instant", "swing", -0.08),
    "returning": RuntimeFamilyProfile("returning", True, False, True, "tethered", "throwing", "early", "soft"),
    "flail": RuntimeFamilyProfile("flail", True, True, False, "tethered", "two_hand", "instant", "swing"),
    "yoyo": RuntimeFamilyProfile("yoyo", True, True, True, "tethered", "throwing", "instant", "swing"),
    "whip": RuntimeFamilyProfile("whip", True, True, False, "tethered", "two_hand", "instant", "swing"),
    "shoot": RuntimeFamilyProfile("shoot", True, False, False, "ranged", "held_out", "on_release", "gun"),
    "cast": RuntimeFamilyProfile("cast", True, False, False, "magic", "staff", "on_release", "magic"),
    "beam": RuntimeFamilyProfile("beam", True, True, False, "magic", "staff", "instant", "magic"),
    "charge_release": RuntimeFamilyProfile("charge_release", True, True, False, "generic", "held_out", "on_release", "soft"),
    "overhead_barrage": RuntimeFamilyProfile("overhead_barrage", True, False, False, "generic", "held_out", "on_release", "soft"),
    "throw": RuntimeFamilyProfile("throw", True, False, True, "generic", "throwing", "early", "soft"),
    "summon": RuntimeFamilyProfile("summon", True, False, False, "magic", "staff", "on_release", "summon"),
    "sentry": RuntimeFamilyProfile("sentry", True, False, False, "magic", "staff", "on_release", "summon"),
}

# A root executor owns one item-use lifecycle, not necessarily the only damage
# source.  These exact carriers keep Terraria's item/tool body active while the
# same use also emits a generated projectile.  Do not broaden this into a free-form
# owner graph: every other projectile family remains projectile-only.
_ITEM_BODY_PLUS_PROJECTILE_CARRIERS: Final[frozenset[tuple[str, str]]] = frozenset({
    ("shoot", "swing"),
    ("overhead_barrage", "swing"),
})

_RUNTIME_FAMILY_DELIVERIES: Final[dict[str, frozenset[str]]] = {
    "none": frozenset({"none"}),
    "swing": frozenset({"swing"}),
    "thrust": frozenset({"thrust"}),
    "returning": frozenset({"throw"}),
    "flail": frozenset({"flail"}),
    "yoyo": frozenset({"yoyo"}),
    "whip": frozenset({"whip"}),
    "shoot": frozenset({"shoot", "swing"}),
    "cast": frozenset({"cast"}),
    "beam": frozenset({"cast"}),
    "charge_release": frozenset({"shoot", "cast", "throw"}),
    "overhead_barrage": frozenset({"shoot", "cast", "swing"}),
    "throw": frozenset({"throw"}),
    "summon": frozenset({"summon"}),
    "sentry": frozenset({"summon"}),
}

_RUNTIME_FAMILY_REQUIRED_MOVEMENTS: Final[dict[str, frozenset[str]]] = {
    "returning": frozenset({"boomerang", "returning_glaive"}),
    "flail": frozenset({"flail_tether"}),
    "yoyo": frozenset({"yoyo_hover"}),
    "whip": frozenset({"whip_lash"}),
}
_EXCLUSIVE_MOVEMENT_OWNERS: Final[dict[str, str]] = {
    movement: family
    for family, movements in _RUNTIME_FAMILY_REQUIRED_MOVEMENTS.items()
    if family in {"flail", "yoyo", "whip"}
    for movement in movements
}

CANONICAL_RUNTIME_FAMILIES = frozenset(_RUNTIME_FAMILY_PROFILES)
PROJECTILE_OWNED_RUNTIME_FAMILIES = frozenset(
    name for name, profile in _RUNTIME_FAMILY_PROFILES.items() if profile.projectile_owned
)
HELD_PROJECTILE_RUNTIME_FAMILIES = frozenset(
    name for name, profile in _RUNTIME_FAMILY_PROFILES.items() if profile.held_projectile
)
ITEM_BODIED_PROJECTILE_RUNTIME_FAMILIES = frozenset(
    name for name, profile in _RUNTIME_FAMILY_PROFILES.items() if profile.item_bodied_projectile
)


def _runtime_family_token(value: Any) -> str:
    return normalize_overhead_barrage_family(value)


def is_canonical_runtime_family(value: Any) -> bool:
    return _runtime_family_token(value) in _RUNTIME_FAMILY_PROFILES


def canonical_runtime_family(value: Any) -> str:
    token = _runtime_family_token(value)
    return token if token in _RUNTIME_FAMILY_PROFILES else "none"


def runtime_family_profile(value: Any) -> RuntimeFamilyProfile:
    return _RUNTIME_FAMILY_PROFILES[canonical_runtime_family(value)]


def is_projectile_owned_family(value: Any) -> bool:
    return runtime_family_profile(value).projectile_owned


def uses_held_projectile_family(value: Any) -> bool:
    return runtime_family_profile(value).held_projectile


def is_item_bodied_projectile_family(value: Any) -> bool:
    return runtime_family_profile(value).item_bodied_projectile


def runtime_family_accepts_delivery(value: Any, delivery: Any) -> bool:
    family = canonical_runtime_family(value)
    delivery_token = str(delivery or "").strip().lower().replace("-", "_").replace(" ", "_")
    return delivery_token in _RUNTIME_FAMILY_DELIVERIES.get(family, frozenset())


def runtime_family_delivery_pairs() -> tuple[tuple[str, str], ...]:
    """Return the canonical immutable family/delivery policy projection."""
    return tuple(
        (family, delivery)
        for family in sorted(_RUNTIME_FAMILY_DELIVERIES)
        if family != "none"
        for delivery in sorted(_RUNTIME_FAMILY_DELIVERIES[family])
    )


def runtime_family_required_movements(value: Any) -> frozenset[str]:
    return _RUNTIME_FAMILY_REQUIRED_MOVEMENTS.get(
        canonical_runtime_family(value),
        frozenset(),
    )


def exclusive_movement_owner(value: Any) -> str:
    token = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _EXCLUSIVE_MOVEMENT_OWNERS.get(token, "")


def runtime_family_accepts_movement(value: Any, movement: Any) -> bool:
    family = canonical_runtime_family(value)
    token = str(movement or "").strip().lower().replace("-", "_").replace(" ", "_")
    required = runtime_family_required_movements(family)
    if required and token not in required:
        return False
    owner = exclusive_movement_owner(token)
    return not owner or owner == family


def keeps_item_body_damage_lane(value: Any, delivery: Any = "") -> bool:
    family = canonical_runtime_family(value)
    delivery_token = str(delivery or "").strip().lower().replace("-", "_").replace(" ", "_")
    return (family, delivery_token) in _ITEM_BODY_PLUS_PROJECTILE_CARRIERS


def uses_projectile_only_item_affordance(value: Any, delivery: Any = "") -> bool:
    """Whether the item body/hitbox should be replaced by its runtime projectile.

    A root executor may preserve one bounded item-body lane.  In particular,
    ``shoot+swing`` covers Terraria shooting swords and tool+splash/shard uses,
    while ``overhead_barrage+swing`` covers Starfury-style carriers.  The root
    executor is still singular; the item hitbox is not a second controller.
    """
    family = canonical_runtime_family(value)
    return runtime_family_profile(family).projectile_owned and not keeps_item_body_damage_lane(family, delivery)


__all__ = [
    "CANONICAL_RUNTIME_FAMILIES",
    "HELD_PROJECTILE_RUNTIME_FAMILIES",
    "ITEM_BODIED_PROJECTILE_RUNTIME_FAMILIES",
    "PROJECTILE_OWNED_RUNTIME_FAMILIES",
    "RuntimeFamilyProfile",
    "canonical_runtime_family",
    "is_canonical_runtime_family",
    "is_item_bodied_projectile_family",
    "is_projectile_owned_family",
    "keeps_item_body_damage_lane",
    "runtime_family_profile",
    "runtime_family_accepts_delivery",
    "runtime_family_delivery_pairs",
    "runtime_family_required_movements",
    "uses_held_projectile_family",
    "uses_projectile_only_item_affordance",
]
