from __future__ import annotations

from typing import Any

from infini_local.core.item_identity_tools import (
    dict_get_ci,
    fingerprint_of,
    generated_data_of,
    item_bool,
    item_field,
    item_num,
)


# AGENT MAP: projectile/source weapon facts used by VFX manifest authoring.
# These helpers summarize explicit item/attack fields only; no prose gameplay routing.

def projectile_profile_of(item: dict[str, Any]) -> dict[str, Any]:
    gd = generated_data_of(item)
    attack = dict_get_ci(gd, "attack", {}) if gd else {}
    if isinstance(attack, dict) and attack.get("enabled"):
        try:
            pierce = int(float(attack.get("pierce") or 1))
        except Exception:
            pierce = 1
        penetrate = -1 if pierce == -1 else max(1, min(12, pierce))
        return {
            "type": int(item_num(item, "shoot", 0)),
            "sourceMod": "InfiniCrafterLocal",
            "internalName": "GeneratedProjectile",
            "fullName": "InfiniCrafterLocal/GeneratedProjectile",
            "itemShootSpeed": float(attack.get("speed") or item_num(item, "shootSpeed", 0)),
            "width": int(float(attack.get("projectileWidth") or 14)),
            "height": int(float(attack.get("projectileHeight") or 14)),
            "scale": float(attack.get("projectileScale") or 1.0),
            "aiStyle": 0,
            "penetrate": penetrate,
            "maxPenetrate": penetrate,
            "timeLeft": int(float(attack.get("lifetime") or 90)),
            "extraUpdates": int(float(attack.get("extraUpdates") or 0)),
            "tileCollide": bool(attack.get("tileCollide", True)),
            "ownerHitCheck": str(attack.get("delivery") or "") == "swing",
            "usesLocalNPCImmunity": True,
            "localNPCHitCooldown": int(float(attack.get("immunityCooldown") or 10)),
            "usesIDStaticNPCImmunity": False,
            "light": 0,
            "minion": False,
            "sentry": False,
            "engineMetrics": attack.get("engineMetrics") if isinstance(attack.get("engineMetrics"), dict) else {},
        }
    pp = item.get("projectileProfile")
    if isinstance(pp, dict):
        return pp
    fp = fingerprint_of(item)
    pp = fp.get("projectileProfile") if isinstance(fp, dict) else None
    return pp if isinstance(pp, dict) else {}

def effective_projectile_profile_of(item: dict[str, Any]) -> dict[str, Any]:
    return projectile_profile_of(item)

def proj_num(proj: dict[str, Any], name: str, default: float = 0.0) -> float:
    try:
        return float(proj.get(name, default) or 0)
    except Exception:
        return default

def proj_bool(proj: dict[str, Any], name: str) -> bool:
    v = proj.get(name, False)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in {"1", "true", "yes", "y"}
    return bool(v)

def projectile_behavior_tags(item: dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    proj = effective_projectile_profile_of(item)
    if not proj or proj.get("unavailable"):
        return tags
    tags.add("projectile")
    ai_style = int(proj_num(proj, "aiStyle", 0))
    penetrate = int(proj_num(proj, "penetrate", 1))
    time_left = int(proj_num(proj, "timeLeft", 0))
    extra_updates = int(proj_num(proj, "extraUpdates", 0))
    if penetrate == -1 or penetrate > 1:
        tags.add("piercing")
    if penetrate == -1:
        tags.add("infinite_pierce")
    if extra_updates > 0:
        tags.add("fast_projectile")
    if extra_updates >= 2:
        tags.add("very_fast_projectile")
    if not proj_bool(proj, "tileCollide"):
        tags.add("noncolliding_projectile")
    if proj_bool(proj, "ownerHitCheck"):
        tags.add("melee_projection")
    if proj_bool(proj, "minion"):
        tags.update({"summon", "minion"})
    if proj_bool(proj, "sentry"):
        tags.update({"summon", "sentry"})
    if proj_bool(proj, "usesLocalNPCImmunity") or proj_bool(proj, "usesIDStaticNPCImmunity"):
        tags.add("multi_hit_projectile")
    if time_left >= 240:
        tags.add("long_lived_projectile")
    if ai_style > 0:
        tags.add("vanilla_ai_style")
    return tags

def source_weapon_profile(item: dict[str, Any]) -> dict[str, Any]:
    proj = effective_projectile_profile_of(item)
    damage = max(0.0, item_num(item, "damage"))
    use_time = max(6.0, item_num(item, "useTime", item_num(item, "useAnimation", 30)))
    shoot = item_num(item, "shoot")
    shoot_speed = item_num(item, "shootSpeed")
    channel = item_bool(item, "channel")
    damage_class = str(item_field(item, "damageClass", "generic") or "generic").lower()
    behavior = sorted(projectile_behavior_tags(item))
    pierce = 0.0
    lifetime = 0.0
    extra_updates = 0.0
    ai_style = 0
    local_immune = False
    if proj:
        penetrate = int(proj_num(proj, "penetrate", 1))
        pierce = 8.0 if penetrate == -1 else max(0.0, float(penetrate - 1))
        lifetime = max(0.0, min(1800.0, proj_num(proj, "timeLeft", 0)))
        extra_updates = max(0.0, min(4.0, proj_num(proj, "extraUpdates", 0)))
        ai_style = int(proj_num(proj, "aiStyle", 0))
        local_immune = proj_bool(proj, "usesLocalNPCImmunity") or proj_bool(proj, "usesIDStaticNPCImmunity")
    attacks_per_second = 60.0 / max(6.0, use_time)
    effective_dps = damage * attacks_per_second * (1.0 + min(1.15, pierce * 0.18)) * (1.0 + min(0.35, extra_updates * 0.12))
    return {
        "damage": damage,
        "damageClass": damage_class,
        "shoot": shoot,
        "shootSpeed": shoot_speed,
        "channel": channel,
        "aiStyle": ai_style,
        "piercePotential": pierce,
        "lifetime": lifetime,
        "extraUpdates": extra_updates,
        "localImmunity": local_immune,
        "effectiveDpsSignal": round(effective_dps, 3),
        "projectileProfile": proj,
        "behaviorTags": behavior,
    }

__all__ = [
    "projectile_profile_of",
    "effective_projectile_profile_of",
    "proj_num",
    "proj_bool",
    "projectile_behavior_tags",
    "source_weapon_profile",
]
