from __future__ import annotations

from typing import Any

from infini_local.core.runtime_family_policy import runtime_family_profile


_PROJECTILE_USE_DAMAGE_CLASSES = frozenset({"magic", "ranged", "summon"})


def runtime_presentation_defaults(runtime_family: Any, damage_class: Any, delivery: Any = "") -> dict[str, Any]:
    profile = runtime_family_profile(runtime_family)
    damage = str(damage_class or "").strip().lower()
    carrier = str(delivery or "").strip().lower().replace("-", "_").replace(" ", "_")
    if profile.name == "overhead_barrage":
        hand_pose = "staff" if carrier == "cast" else "short_weapon" if carrier == "swing" else "held_out"
        use_style = 1 if carrier == "swing" else 5
    else:
        hand_pose = profile.hand_pose
        use_style = 5 if profile.projectile_owned or damage in _PROJECTILE_USE_DAMAGE_CLASSES else 1
    return {
        "useStyle": use_style,
        "heldVisibility": "show_projectile" if profile.held_projectile else "show_item",
        "releaseTiming": profile.release_timing,
        "handPose": hand_pose,
    }


__all__ = ["runtime_presentation_defaults"]
