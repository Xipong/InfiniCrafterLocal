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


def uses_projectile_only_item_affordance(value: Any, delivery: Any = "") -> bool:
    """Whether the item body/hitbox should be replaced by its runtime projectile.

    Overhead barrage is delivery geometry, not a carrier class.  An explicit
    swing carrier (Starfury-style) keeps its melee item body while still
    spawning the overhead marker; shoot/cast carriers remain projectile-only.
    """
    family = canonical_runtime_family(value)
    delivery_token = str(delivery or "").strip().lower().replace("-", "_").replace(" ", "_")
    if family == "overhead_barrage" and delivery_token == "swing":
        return False
    return runtime_family_profile(family).projectile_owned


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
    "runtime_family_profile",
    "uses_held_projectile_family",
    "uses_projectile_only_item_affordance",
]
