from __future__ import annotations

import json
import re
from typing import Any

from infini_local.core.item_identity_tools import (
    dict_get_ci,
    fingerprint_of,
    generated_data_of,
    generation_depth,
    item_bool,
    item_field,
    item_num,
    name_of,
    tags_of,
)
from infini_local.pipelines.pipeline_runtime_constants import (
    LLM_AMMO_ITEM_KEYS,
    LLM_AMMO_REP_LIMIT,
    LLM_INCLUDE_AISTYLE_RAW,
    LLM_INCLUDE_PROJECTILE_BEHAVIOR_DIGEST,
    LLM_ITEM_RAW_KEYS,
    LLM_PROJECTILE_RAW_KEYS,
)
from infini_local.pipelines.pipeline_runtime_dumps import (
    RUNTIME_ITEMS,
    runtime_projectile_lookup,
)
from infini_local.pipelines.result_identity_policy import parent_primary_category


def _raw_section_dict(item: dict[str, Any], *names: str) -> dict[str, Any]:
    for name in names:
        v = dict_get_ci(item, name, None)
        if isinstance(v, dict) and v:
            return v
        fp = fingerprint_of(item)
        v = dict_get_ci(fp, name, None) if isinstance(fp, dict) else None
        if isinstance(v, dict) and v:
            return v
    return {}

def _raw_section_list(item: dict[str, Any], *names: str) -> list[Any]:
    for name in names:
        v = dict_get_ci(item, name, None)
        if isinstance(v, list) and v:
            return v
        fp = fingerprint_of(item)
        v = dict_get_ci(fp, name, None) if isinstance(fp, dict) else None
        if isinstance(v, list) and v:
            return v
    return []

def _strip_texture_metrics_for_llm(profile: dict[str, Any]) -> dict[str, Any]:
    """Keep source texture metrics out of LLM authoring cards by default.

    The metrics are factual and useful for diagnostics/validation, but feeding them into the
    authoring prompt makes small models overfit raw pixels instead of authoring the item.
    """
    if not isinstance(profile, dict):
        return {}
    out = dict(profile)
    out.pop("textureMetrics", None)
    out.pop("sourceTextureMetrics", None)
    return out

def projectile_profile_of(item: dict[str, Any]) -> dict[str, Any]:
    """C# sends a Projectile.SetDefaults(item.shoot) snapshot for vanilla/modded projectiles.
    This is not full AI simulation, but it is a much better source than item names:
    penetrate/timeLeft/extraUpdates/tileCollide/ownerHitCheck/local immunity/minion/sentry/aiStyle.

    GeneratedItem is special: Terraria can only SetDefaults the generic GeneratedProjectile
    type, but the actual behavior lives in generatedData.attack. When a generated item is
    used as a parent, synthesize a projectile profile from that attack spec so recursive
    crafting does not forget pierce/lifetime/extraUpdates/tile collision/multi-hit pressure.
    """
    gd = generated_data_of(item)
    attack = dict_get_ci(gd, "attack", {}) if gd else {}
    if isinstance(attack, dict) and attack.get("enabled"):
        pierce = int(float(attack.get("pierce") or 1))
        # attack.pierce is the real projectile penetrate count in the generated item JSON.
        # Keep -1 only if a future schema explicitly emits it; otherwise clamp to a sane count.
        if pierce == -1:
            penetrate = -1
        else:
            penetrate = max(1, min(12, pierce))
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
            "ignoreWater": False,
            "friendly": True,
            "hostile": False,
            "arrow": False,
            "minion": str((dict_get_ci(gd, "gameplay", {}) or {}).get("damageClass") or "").lower() == "summon",
            "sentry": False,
            "minionSlots": 0,
            "ownerHitCheck": str(attack.get("runtimeFamily") or attack.get("delivery") or "") in {"thrust", "spear", "whip"},
            "usesLocalNPCImmunity": True,
            "localNPCHitCooldown": int(float(attack.get("immunityCooldown") or 10)),
            "usesIDStaticNPCImmunity": False,
            "idStaticNPCHitCooldown": -1,
            "stopsDealingDamageAfterPenetrateHits": False,
            "light": 0,
            "alpha": 0,
            "netImportant": False,
            "fromGeneratedAttack": True,
            "engineMetrics": attack.get("engineMetrics") if isinstance(attack.get("engineMetrics"), dict) else {},
        }
    raw_direct = _raw_section_dict(item, "directProjectileRaw")
    if raw_direct:
        out = _strip_texture_metrics_for_llm(raw_direct)
        out.setdefault("fromLiveWireRaw", True)
        out.setdefault("fromItemShoot", item_field(item, "shoot", 0))
        return out
    pp = item.get("projectileProfile")
    if isinstance(pp, dict):
        return pp
    fp = fingerprint_of(item)
    pp = fp.get("projectileProfile") if isinstance(fp, dict) else None
    if isinstance(pp, dict):
        return pp
    shoot = item_field(item, "shoot", 0)
    if shoot:
        found = runtime_projectile_lookup(shoot)
        if found:
            out = _strip_texture_metrics_for_llm(found)
            out["fromRuntimeDump"] = True
            out["fromItemShoot"] = int(float(shoot))
            return out
    return {}

def ammo_profile_of(item: dict[str, Any]) -> dict[str, Any]:
    """Raw ammo context for ammo-using weapons.

    Ammo examples are not the canonical weapon identity: a modded gun/bow may have
    important item.shoot mechanics independent of the player's current bullets.
    """
    raw_ammo = _raw_section_dict(item, "ammoRaw")
    if raw_ammo:
        out = dict(raw_ammo)
        out.setdefault("fromLiveWireRaw", True)
        return out
    use_ammo = int(item_num(item, "useAmmo", 0))
    if use_ammo <= 0 or not RUNTIME_ITEMS:
        return {}
    candidates = []
    source = str(item_field(item, "sourceMod", "Terraria") or "Terraria")
    for row in RUNTIME_ITEMS:
        try:
            if int(row.get("ammo") or 0) != use_ammo:
                continue
            if int(row.get("shoot") or 0) <= 0:
                continue
            candidates.append(row)
        except Exception:
            continue
    if not candidates:
        return {"ammoId": use_ammo}
    def score(row: dict[str, Any]) -> tuple[int, int, int, int]:
        # Prefer same-source basic/cheap ammo; avoid endless pouches as the canonical example.
        internal = str(row.get("internalName") or "").lower()
        same_source = 0 if str(row.get("sourceMod") or "") == source else 1
        endless = 1 if "endless" in internal or "infinite" in internal else 0
        rare = int(row.get("rare") or 0)
        value = int(row.get("value") or 0)
        return (same_source, endless, rare, value)
    ammo = sorted(candidates, key=score)[0]
    projectile = runtime_projectile_lookup(ammo.get("shoot"))
    profile = {
        "ammoId": use_ammo,
        "exampleAmmo": ammo.get("internalName") or ammo.get("name"),
        "exampleAmmoType": ammo.get("type"),
        "exampleAmmoSourceMod": ammo.get("sourceMod"),
        "exampleAmmoDamage": ammo.get("damage"),
        "exampleAmmoShoot": ammo.get("shoot"),
        "exampleAmmoShootSpeed": ammo.get("shootSpeed"),
        "exampleAmmoKnockback": ammo.get("knockback"),
    }
    if projectile:
        profile["exampleProjectile"] = _strip_texture_metrics_for_llm(projectile)
    return profile

def effective_projectile_profile_of(item: dict[str, Any]) -> dict[str, Any]:
    raw_effective = _raw_section_dict(item, "effectiveProjectileRaw")
    raw_direct = _raw_section_dict(item, "directProjectileRaw")
    if raw_effective:
        # Older live-wire dumps sometimes used representative ammo as "effective".
        # If the weapon has its own direct shoot field, keep that as the primary executable profile.
        src = str(raw_effective.get("source") or "").lower() if isinstance(raw_effective, dict) else ""
        if raw_direct and ("representative" in src or "fallback" in src or "player_inventory" in src):
            out = _strip_texture_metrics_for_llm(raw_direct)
            out.setdefault("fromLiveWireRaw", True)
            out.setdefault("effective", True)
            out.setdefault("effectiveSourcePolicy", "prefer_weapon_direct_over_ammo_candidate")
            return out
        out = _strip_texture_metrics_for_llm(raw_effective)
        out.setdefault("fromLiveWireRaw", True)
        out.setdefault("effective", True)
        return out
    if raw_direct:
        out = _strip_texture_metrics_for_llm(raw_direct)
        out.setdefault("fromLiveWireRaw", True)
        out.setdefault("effective", True)
        return out
    ammo = ammo_profile_of(item)
    ep = ammo.get("exampleProjectile") if isinstance(ammo, dict) else None
    if isinstance(ep, dict) and ep:
        out = _strip_texture_metrics_for_llm(ep)
        out["fromAmmoProfile"] = True
        return out
    inv_eps = ammo.get("playerInventoryProjectileRaw") if isinstance(ammo, dict) else None
    if isinstance(inv_eps, list) and inv_eps and isinstance(inv_eps[0], dict):
        out = dict(inv_eps[0])
        out["fromAmmoProfile"] = True
        out["fromPlayerInventoryAmmoCandidate"] = True
        return out
    selected_ep = ammo.get("selectedPlayerProjectileRaw") if isinstance(ammo, dict) else None
    if isinstance(selected_ep, dict) and selected_ep:
        out = dict(selected_ep)
        out["fromAmmoProfile"] = True
        out["fromPlayerInventoryAmmoCandidate"] = True
        return out
    fb_eps = ammo.get("fallbackProjectileRaw") if isinstance(ammo, dict) else None
    if isinstance(fb_eps, list) and fb_eps and isinstance(fb_eps[0], dict):
        out = dict(fb_eps[0])
        out["fromAmmoProfile"] = True
        out["fromFallbackAmmoCandidate"] = True
        return out
    rep_eps = ammo.get("representativeProjectileRaw") if isinstance(ammo, dict) else None
    if isinstance(rep_eps, list) and rep_eps and isinstance(rep_eps[0], dict):
        out = dict(rep_eps[0])
        out["fromAmmoProfile"] = True
        out["fromFallbackAmmoCandidate"] = True
        return out
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
    if proj_bool(proj, "arrow"):
        tags.add("arrow")
    disposable_throwable = item_bool(item, "consumable") and item_num(item, "maxStack", 1) > 1 and proj_bool(proj, "tileCollide") and item_num(item, "damage", 0) <= 20
    owner_checked = proj_bool(proj, "ownerHitCheck")
    if penetrate == -1 or penetrate > 1:
        tags.add("piercing")
    if penetrate == -1 and not disposable_throwable and not owner_checked:
        tags.add("infinite_pierce")
    if disposable_throwable:
        tags.add("disposable_throwable")
    if extra_updates > 0:
        tags.add("fast_projectile")
    if extra_updates >= 2:
        tags.add("very_fast_projectile")
    if not proj_bool(proj, "tileCollide"):
        tags.add("noncolliding_projectile")
    if owner_checked:
        tags.add("melee_projection")
    if proj_bool(proj, "minion"):
        tags.update({"summon", "minion"})
    if proj_bool(proj, "sentry"):
        tags.update({"summon", "sentry"})
    if proj_bool(proj, "usesLocalNPCImmunity") or proj_bool(proj, "usesIDStaticNPCImmunity"):
        tags.add("multi_hit_projectile")
    if time_left >= 240 and not owner_checked and not (item_bool(item, "consumable") and item_num(item, "maxStack", 1) > 1 and proj_bool(proj, "tileCollide")):
        tags.add("long_lived_projectile")
    if ai_style > 0:
        tags.add("vanilla_ai_style")
    return tags

def source_weapon_profile(item: dict[str, Any]) -> dict[str, Any]:
    """Observable parent weapon profile. No named Calamity/vanilla recipes, no per-item hand scores.
    In runtime-authoring mode the weapon's own shoot field remains primary; ammoRaw is
    additional candidate context for the LLM, not a code-authored override.
    """
    proj = effective_projectile_profile_of(item)
    damage = max(0.0, item_num(item, "damage"))
    use_time = max(6.0, item_num(item, "useTime", item_num(item, "useAnimation", 30)))
    use_anim = max(6.0, item_num(item, "useAnimation", use_time))
    shoot = item_num(item, "shoot")
    shoot_speed = item_num(item, "shootSpeed")
    no_melee = item_bool(item, "noMelee")
    channel = item_bool(item, "channel")
    damage_class = str(item_field(item, "damageClass", "generic") or "generic").lower()
    proj_count = 1.0
    pierce = 0.0
    lifetime = 0.0
    extra_updates = 0.0
    tile_collide = True
    owner_hit_check = False
    local_immune = False
    ai_style = 0
    minion = False
    sentry = False
    if proj and not proj.get("unavailable"):
        penetrate = int(proj_num(proj, "penetrate", 1))
        tile_collide = proj_bool(proj, "tileCollide")
        disposable_throwable = item_bool(item, "consumable") and item_num(item, "maxStack", 1) > 1 and tile_collide and damage <= 20
        pierce = 8.0 if penetrate == -1 else max(0.0, float(penetrate - 1))
        lifetime = max(0.0, min(1800.0, proj_num(proj, "timeLeft", 0)))
        if disposable_throwable:
            # Raw timeLeft on vanilla shuriken/throwing knife is a technical expiry value,
            # not real target uptime. Do not let starter stackables become mech-tier.
            pierce = min(pierce, 2.0)
            lifetime = min(lifetime, 120.0)
        owner_hit_check = proj_bool(proj, "ownerHitCheck")
        if owner_hit_check:
            # Vanilla spears/held melee projections often expose indefinite pierce and long
            # technical timeLeft, but that is the held-hitbox implementation, not free-flight uptime.
            pierce = min(pierce, 2.0)
            lifetime = min(lifetime, 90.0)
        extra_updates = max(0.0, min(4.0, proj_num(proj, "extraUpdates", 0)))
        local_immune = proj_bool(proj, "usesLocalNPCImmunity") or proj_bool(proj, "usesIDStaticNPCImmunity")
        ai_style = int(proj_num(proj, "aiStyle", 0))
        minion = proj_bool(proj, "minion")
        sentry = proj_bool(proj, "sentry")
    # Conservative effective-power approximation. It prices delivery reliability, not exact AI DPS.
    attacks_per_second = 60.0 / max(6.0, use_time)
    pierce_mult = 1.0 + min(1.15, pierce * 0.18)
    lifetime_mult = 1.0 + min(0.55, lifetime / 900.0) if shoot > 0 else 1.0
    speed_mult = 1.0 + min(0.28, max(0.0, shoot_speed - 8.0) / 40.0)
    update_mult = 1.0 + min(0.35, extra_updates * 0.12)
    safety_mult = 1.0
    if shoot > 0 and no_melee:
        safety_mult += 0.12
    if not tile_collide and shoot > 0:
        safety_mult += 0.18
    if owner_hit_check:
        safety_mult -= 0.12
    if channel:
        safety_mult += 0.08
    if minion or sentry:
        safety_mult += 0.25
    immune_mult = 1.10 if local_immune else 1.0
    raw_dps = damage * attacks_per_second
    effective = raw_dps * proj_count * pierce_mult * lifetime_mult * speed_mult * update_mult * max(0.65, safety_mult) * immune_mult
    return {
        "damage": round(damage, 3),
        "useTime": round(use_time, 3),
        "useAnimation": round(use_anim, 3),
        "attacksPerSecond": round(attacks_per_second, 3),
        "damageClass": damage_class,
        "shoot": int(shoot),
        "shootSpeed": round(shoot_speed, 3),
        "noMelee": no_melee,
        "channel": channel,
        "aiStyle": ai_style,
        "piercePotential": round(pierce, 3),
        "lifetime": round(lifetime, 3),
        "extraUpdates": round(extra_updates, 3),
        "tileCollide": tile_collide,
        "ownerHitCheck": owner_hit_check,
        "localImmunity": local_immune,
        "minion": minion,
        "sentry": sentry,
        "ammoProfile": ammo_profile_of(item),
        "effectiveDpsSignal": round(effective, 3),
        "behaviorTags": sorted(projectile_behavior_tags(item)),
        "projectileProfile": proj,
    }

def parent_weapon_profiles(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for item in (a, b):
        if item_num(item, "damage") > 0 or item_num(item, "shoot") > 0:
            prof = source_weapon_profile(item)
            prof["name"] = name_of(item)
            out.append(prof)
    return out

def runtime_facts_for_prompt(item: dict[str, Any]) -> dict[str, Any]:
    rf = item.get("runtimeFacts")
    if isinstance(rf, dict):
        return rf
    fp = fingerprint_of(item)
    rf = fp.get("runtimeFacts") if isinstance(fp, dict) else None
    if isinstance(rf, dict):
        return rf
    keys = ["type", "damage", "damageClass", "useStyle", "useTime", "useAnimation", "rare", "rarityDetails", "value", "maxStack", "consumable", "accessory", "defense", "createTile", "createWall", "pickPower", "axePower", "hammerPower", "healLife", "healMana", "manaCost", "ammo", "useAmmo", "shoot", "shootSpeed", "knockback", "buffType", "buffTime"]
    return {k: item_field(item, k, None) for k in keys if item_field(item, k, None) is not None}

def auto_features_for_prompt(item: dict[str, Any]) -> dict[str, Any]:
    raw_features = item.get("autoFeatures")
    if not isinstance(raw_features, list):
        fp = fingerprint_of(item)
        raw_features = fp.get("autoFeatures") if isinstance(fp, dict) else []
    raw_tokens = item.get("nameTokens")
    if not isinstance(raw_tokens, list):
        fp = fingerprint_of(item)
        raw_tokens = fp.get("nameTokens") if isinstance(fp, dict) else []
    features = sorted({str(x).lower() for x in (raw_features or []) if str(x).strip()})
    tokens = sorted({str(x).lower() for x in (raw_tokens or []) if str(x).strip()})
    return {
        "runtimeRoles": features,
        "nameTokens": tokens,
        "projectileBehavior": sorted(projectile_behavior_tags(item)),
        "note": "autoFeatures are mechanically derived from runtime fields/name tokens; they are not hand-authored Terraria tags",
    }

def llm_parent_card(item: dict[str, Any], canonical: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name_of(item),
        "sourceMod": str(item_field(item, "sourceMod", "Terraria")),
        "internalName": str(item_field(item, "internalName", "")),
        "fullName": str(item_field(item, "fullName", "")),
        "primaryCategory": parent_primary_category(item),
        "runtimeFacts": runtime_facts_for_prompt(item),
        "autoFeatures": auto_features_for_prompt(item),
        "canonical": canonical,
        "weaponProfile": source_weapon_profile(item),
        "directProjectileProfile": projectile_profile_of(item),
        "ammoProfile": ammo_profile_of(item),
        "generatedDepth": generation_depth(item),
    }

def _compact_keep(value: Any) -> bool:
    # Keep 0 and False; those are real raw values. Drop only absent/empty containers/empty text.
    return value is not None and value != "" and value != [] and value != {}

def _compact_raw_value(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return value
    if isinstance(value, dict):
        return {str(k): _compact_raw_value(v, depth + 1) for k, v in value.items() if _compact_keep(v)}
    if isinstance(value, list):
        return [_compact_raw_value(v, depth + 1) for v in value if _compact_keep(v)]
    return value

def _select_raw_keys(d: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    if not isinstance(d, dict):
        return {}
    out: dict[str, Any] = {}
    for k in keys:
        if k in d and _compact_keep(d.get(k)):
            out[k] = _compact_raw_value(d.get(k))
    return out

def compact_item_raw_for_llm(item: dict[str, Any]) -> dict[str, Any]:
    raw = _raw_item_fields_for_llm(item)
    # If the live client sent richer fields, keep them; if older payload, itemRaw is built from item fields.
    raw.update({k: item_field(item, k, None) for k in LLM_ITEM_RAW_KEYS if item_field(item, k, None) is not None})
    return _select_raw_keys(raw, LLM_ITEM_RAW_KEYS)

def _pnum(proj: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(proj.get(key, default) or default)
    except Exception:
        return default

def _pbool(proj: dict[str, Any], key: str) -> bool:
    v = proj.get(key, False)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "y"}
    return bool(v)

def projectile_behavior_digest_for_llm(proj: dict[str, Any]) -> dict[str, Any]:
    """Compact raw-flag digest for LLM input.

    Keep this deliberately non-semantic: no aiStyle example names and no vanilla family
    prose are exposed to the planner. aiStyle buckets are too broad (for example knives,
    shurikens, bones and sparks can share one bucket), so the LLM should see stable
    mechanical flags rather than inherited item-family suggestions.
    """
    if not isinstance(proj, dict) or not proj:
        return {}
    owner_checked = _pbool(proj, "ownerHitCheck")
    tile_collide = _pbool(proj, "tileCollide")
    if owner_checked:
        mechanical_hint = "owner_checked_close_or_held_hitbox"
    elif tile_collide:
        mechanical_hint = "free_projectile_with_tile_collision"
    else:
        mechanical_hint = "free_projectile_without_tile_collision"
    out: dict[str, Any] = {
        "mechanicalHint": mechanical_hint,
        "facts": [],
        "basis": [],
        "note": "Raw flag digest only. It is not an item family, not a visual instruction, and not a command to copy source behavior.",
    }
    facts: list[str] = []
    basis: list[str] = []
    if _pbool(proj, "arrow"):
        facts.append("arrow flag is true")
        basis.append("arrow=true")
    if _pbool(proj, "minion"):
        facts.append("minion flag is true")
        basis.append("minion=true")
    if _pbool(proj, "sentry"):
        facts.append("sentry flag is true")
        basis.append("sentry=true")
    if owner_checked:
        facts.append("hit validation depends on player/owner contact; this often means close or held hitbox behavior")
        basis.append("ownerHitCheck=true")
    if tile_collide:
        facts.append("collides with tiles")
        basis.append("tileCollide=true")
    else:
        facts.append("does not collide with tiles")
        basis.append("tileCollide=false")
    if _pbool(proj, "ignoreWater"):
        facts.append("ignores water")
        basis.append("ignoreWater=true")
    penetrate = int(_pnum(proj, "penetrate", 0))
    if penetrate == -1:
        facts.append("raw penetrate is infinite/indefinite")
        basis.append("penetrate=-1")
    elif penetrate > 1:
        facts.append(f"raw penetrate allows up to {penetrate} hits before expiry")
        basis.append("penetrate>1")
    elif penetrate == 1:
        facts.append("raw penetrate usually expires after one hit")
        basis.append("penetrate=1")
    time_left = int(_pnum(proj, "timeLeft", 0))
    if 0 < time_left <= 30:
        facts.append("raw timeLeft is very short")
        basis.append("timeLeft<=30")
    elif time_left >= 600:
        if owner_checked:
            facts.append("raw timeLeft is high; for owner-checked/held projectiles this is not evidence of long free flight")
        else:
            facts.append("raw timeLeft is high; treat it as an engine lifetime budget, not a fantasy instruction")
        basis.append("timeLeft>=600")
    extra = int(_pnum(proj, "extraUpdates", 0))
    if extra > 0:
        facts.append(f"uses extra update steps ({extra})")
        basis.append("extraUpdates>0")
    w = int(_pnum(proj, "width", 0)); h = int(_pnum(proj, "height", 0))
    if w > 0 and h > 0:
        facts.append(f"projectile hitbox size {w}x{h}")
        basis.append("width/height")
    if _pbool(proj, "fromGeneratedAttack"):
        facts.append("parent is another InfiniCraft generated projectile; behavior comes from generated runtime fields")
        basis.append("fromGeneratedAttack=true")
    out["facts"] = facts[:10]
    out["basis"] = basis[:12]
    return {k: v for k, v in out.items() if _compact_keep(v)}

def compact_projectile_profile(proj: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(proj, dict) or not proj:
        return {}
    out = _select_raw_keys(proj, LLM_PROJECTILE_RAW_KEYS)
    if LLM_INCLUDE_AISTYLE_RAW and _compact_keep(proj.get("aiStyle")):
        out["aiStyle"] = _compact_raw_value(proj.get("aiStyle"))
    if LLM_INCLUDE_PROJECTILE_BEHAVIOR_DIGEST:
        digest = projectile_behavior_digest_for_llm(proj)
        if digest:
            out["behaviorDigest"] = digest
    return out

def compact_ammo_profile(item: dict[str, Any]) -> dict[str, Any]:
    ap = ammo_profile_of(item)
    if not isinstance(ap, dict) or not ap:
        return {}
    out: dict[str, Any] = {}
    mode = ap.get("mode") or ("legacy_profile" if ap else "")
    if mode:
        out["mode"] = mode
    if _compact_keep(ap.get("ammoId")):
        out["ammoId"] = ap.get("ammoId")
    if isinstance(ap.get("ammoItemRaw"), dict):
        out["ammoItemRaw"] = _select_raw_keys(ap["ammoItemRaw"], LLM_AMMO_ITEM_KEYS)
    if isinstance(ap.get("projectileRaw"), dict):
        out["projectileRaw"] = compact_projectile_profile(ap["projectileRaw"])

    # v0.4.24: ammo examples are context, not the canonical identity of the weapon.
    # The weapon's own item.shoot field is separate from inventory/fallback ammo candidates.
    if isinstance(ap.get("weaponShootFieldProjectileRaw"), dict):
        out["weaponShootFieldProjectileRaw"] = compact_projectile_profile(ap["weaponShootFieldProjectileRaw"])

    inv_ammo = ap.get("playerInventoryAmmoRaw")
    if isinstance(inv_ammo, list):
        out["playerInventoryAmmoRaw"] = [_select_raw_keys(x, LLM_AMMO_ITEM_KEYS) for x in inv_ammo if isinstance(x, dict)][:max(0, LLM_AMMO_REP_LIMIT)]
    inv_proj = ap.get("playerInventoryProjectileRaw")
    if isinstance(inv_proj, list):
        out["playerInventoryProjectileRaw"] = [compact_projectile_profile(x) for x in inv_proj if isinstance(x, dict)][:max(0, LLM_AMMO_REP_LIMIT)]
    fb_ammo = ap.get("fallbackAmmoRaw")
    if isinstance(fb_ammo, list):
        out["fallbackAmmoRaw"] = [_select_raw_keys(x, LLM_AMMO_ITEM_KEYS) for x in fb_ammo if isinstance(x, dict)][:max(0, LLM_AMMO_REP_LIMIT)]
    fb_proj = ap.get("fallbackProjectileRaw")
    if isinstance(fb_proj, list):
        out["fallbackProjectileRaw"] = [compact_projectile_profile(x) for x in fb_proj if isinstance(x, dict)][:max(0, LLM_AMMO_REP_LIMIT)]

    # Backward-compatible readers for older dumps.
    if isinstance(ap.get("selectedPlayerAmmoRaw"), dict):
        out["playerInventoryAmmoRaw"] = [_select_raw_keys(ap["selectedPlayerAmmoRaw"], LLM_AMMO_ITEM_KEYS)]
    if isinstance(ap.get("selectedPlayerProjectileRaw"), dict):
        out["playerInventoryProjectileRaw"] = [compact_projectile_profile(ap["selectedPlayerProjectileRaw"])]
    reps = ap.get("representativeAmmoRaw")
    if isinstance(reps, list) and "fallbackAmmoRaw" not in out:
        out["fallbackAmmoRaw"] = [_select_raw_keys(x, LLM_AMMO_ITEM_KEYS) for x in reps if isinstance(x, dict)][:max(0, LLM_AMMO_REP_LIMIT)]
    preps = ap.get("representativeProjectileRaw")
    if isinstance(preps, list) and "fallbackProjectileRaw" not in out:
        out["fallbackProjectileRaw"] = [compact_projectile_profile(x) for x in preps if isinstance(x, dict)][:max(0, LLM_AMMO_REP_LIMIT)]

    # Legacy runtime dump fallback.
    if not out or mode == "legacy_profile":
        for k in ["ammoId", "exampleAmmo", "exampleAmmoType", "exampleAmmoSourceMod", "exampleAmmoDamage", "exampleAmmoShoot", "exampleAmmoShootSpeed", "exampleAmmoKnockback"]:
            if k in ap and _compact_keep(ap.get(k)):
                out[k] = ap.get(k)
        if isinstance(ap.get("exampleProjectile"), dict):
            out["exampleProjectile"] = compact_projectile_profile(ap["exampleProjectile"])
    return {k: v for k, v in out.items() if _compact_keep(v)}

def _raw_item_fields_for_llm(item: dict[str, Any]) -> dict[str, Any]:
    """Raw-ish item fields for the planner.

    Do not add interpretations such as "no magic observed" or "wood implies chips" here.
    Missing projectile/probe sections are simply omitted; Gemma does the source reading.
    """
    keys = [
        "type", "name", "internalName", "fullName", "sourceMod",
        "damage", "damageClass", "useStyle", "useTime", "useAnimation",
        "rare", "rarityDetails", "value", "maxStack", "stack", "consumable", "material",
        "accessory", "defense", "createTile", "createWall", "placeStyle",
        "pickPower", "axePower", "hammerPower", "pick", "axe", "hammer",
        "healLife", "healMana", "manaCost", "buffType", "buffTime",
        "ammo", "useAmmo", "shoot", "shootSpeed", "knockback", "knockBack",
        "questItem", "expert", "master",
        "mountType", "cartTrack", "pet", "lightPet",
        "fishingPole", "bait",
        "autoReuse", "channel", "noMelee", "noUseGraphic",
    ]
    out: dict[str, Any] = {}
    for k in keys:
        v = item_field(item, k, None)
        if v is not None and v != "":
            out[k] = v
    return out

def compact_vanilla_flags_for_llm(item: dict[str, Any]) -> dict[str, Any]:
    """Compact raw Terraria item role flags for planner context.

    This is not a classifier: every value is copied from runtime dumps when present.
    Missing keys stay absent so the LLM does not read unknowns as negative claims.
    """
    bool_keys = [
        "consumable", "material", "accessory", "questItem", "expert", "master",
        "autoReuse", "channel", "noMelee", "noUseGraphic", "pet", "lightPet",
    ]
    num_keys = [
        "createTile", "createWall", "placeStyle", "shoot", "useAmmo", "ammo",
        "mountType", "cartTrack", "fishingPole", "bait",
        "pickPower", "axePower", "hammerPower", "defense", "healLife", "healMana", "buffType", "buffTime",
    ]
    out: dict[str, Any] = {}
    for k in bool_keys:
        v = item_field(item, k, None)
        if isinstance(v, bool):
            if v:
                out[k] = True
        elif v not in (None, ""):
            text = str(v).strip().lower()
            if text in {"true", "1", "yes"}:
                out[k] = True
    for k in num_keys:
        v = item_field(item, k, None)
        if v in (None, ""):
            continue
        try:
            n = int(float(v))
        except Exception:
            continue
        if n > 0 or k in {"createTile", "createWall"}:
            out[k] = n
    sets = item.get("itemSetsRaw") or item.get("setsRaw")
    if isinstance(sets, dict):
        selected: dict[str, Any] = {}
        for k in ["staff", "sword", "gun", "bow", "countsAsTorch", "isLavaImmune", "sortingPriorityMaterials", "extractinatorMode"]:
            v = sets.get(k)
            if _compact_keep(v):
                selected[k] = v
        if selected:
            out["sets"] = selected
    return out

def _projectile_profile_same_except_source(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """True when two compact projectile raw cards carry the same core mechanics.

    `source`, `setsRaw`, and behavior digest prose are intentionally ignored:
    directProjectile/effectiveProjectile/ammo can point at the same item.shoot
    projectile through different dump paths. Keeping all copies verbatim bloats
    planner prompts and makes small LLMs over-read projectile internal names as
    extra ingredients. Missing core fields are not treated as equal, so lossy ammo
    snippets remain available as raw context instead of being hidden.
    """
    if not isinstance(a, dict) or not isinstance(b, dict) or not a or not b:
        return False
    identity_keys = ("type", "internalName", "sourceMod")
    if not any(_compact_keep(a.get(k)) and a.get(k) == b.get(k) for k in identity_keys):
        return False
    core_keys = (
        "type", "internalName", "sourceMod", "aiStyle", "penetrate", "timeLeft",
        "extraUpdates", "tileCollide", "ownerHitCheck", "arrow", "minion", "sentry",
        "width", "height", "scale", "light",
    )
    matched = 0
    for k in core_keys:
        av = a.get(k)
        bv = b.get(k)
        if _compact_keep(av) and _compact_keep(bv):
            if av != bv:
                return False
            matched += 1
        elif _compact_keep(av) != _compact_keep(bv):
            # One side lacks a real core fact; keep both raw cards unless this is
            # a non-core/prose field handled above.
            return False
    return matched >= 3

def _dedupe_projectile_profile(raw: dict[str, Any], key: str, reference_key: str, reference: dict[str, Any]) -> None:
    cur = raw.get(key)
    if not isinstance(cur, dict) or not isinstance(reference, dict):
        return
    if not _projectile_profile_same_except_source(cur, reference):
        return
    replacement: dict[str, Any] = {"sameAs": f"raw.{reference_key}"}
    if _compact_keep(cur.get("source")):
        replacement["source"] = cur.get("source")
    raw[key] = replacement

def _fishing_bait_semantics_for_llm(item: dict[str, Any], item_raw: dict[str, Any]) -> dict[str, Any]:
    """Label fishing/bait parent facts as preserved intent, not enabled gameplay.

    Generated fishing poles and bait outputs are deliberately future-disabled in
    this build. Keeping the raw values in the parent card is useful identity and
    flavor context, but it must not look like a supported generated result kind.
    """
    raw_fishing = item_raw.get("fishingPole", item.get("fishingPole", 0))
    raw_bait = item_raw.get("bait", item.get("bait", 0))
    def _positive_intish(value: Any) -> int:
        if isinstance(value, bool) or value in (None, ""):
            return 0
        if isinstance(value, int):
            return max(0, value)
        if isinstance(value, float):
            return max(0, int(value))
        text = str(value).strip()
        if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
            return 0
        return max(0, int(float(text)))
    fishing_power = _positive_intish(raw_fishing)
    bait_power = _positive_intish(raw_bait)
    if fishing_power <= 0 and bait_power <= 0:
        return {}
    roles: list[str] = []
    if fishing_power > 0:
        roles.append("fishing_pole_parent")
    if bait_power > 0:
        roles.append("bait_parent")
    return {
        "roles": roles,
        "supportStatus": "future_disabled_for_generated_outputs",
        "note": "Fishing/bait parent facts are preserved as identity/flavor/debug context; this build does not generate executable fishing poles or bait items.",
        "creativePermission": "The LLM may use the theme for another supported result, but must not treat fishingPole/bait as an enabled generated runtime.",
    }


def _placeable_consumption_semantics_for_llm(item: dict[str, Any], item_raw: dict[str, Any]) -> dict[str, Any]:
    """Clarify the one Terraria raw flag that small planners misread most often.

    Placeable tiles/walls are `consumable` because the stack is spent when the
    player places the tile.  That fact is important raw data, but it is not the
    same authoring signal as a potion, ammo stack, or thrown consumable weapon.
    This card does not forbid consumable outputs; it only labels the source
    meaning so the LLM can make that choice intentionally.
    """
    create_tile = item_raw.get("createTile", item.get("createTile", -1))
    create_wall = item_raw.get("createWall", item.get("createWall", -1))
    try:
        has_placeable_target = int(float(create_tile)) >= 0 or int(float(create_wall)) >= 0
    except Exception:
        has_placeable_target = False
    if not has_placeable_target or not bool(item_raw.get("consumable", item.get("consumable", False))):
        return {}
    return {
        "consumptionSemantics": "consumed_when_placed_as_tile_or_wall",
        "note": "The raw consumable flag here means the source stack is spent when placed; it does not automatically mean potion, ammo, thrown stack, or consumable weapon.",
        "creativePermission": "A consumable result is still allowed when mergeLogic/sourceReading intentionally authors that behavior.",
    }


def _projectile_semantics_for_llm(profile: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(profile, dict) or not profile:
        return {}
    out: dict[str, Any] = {}
    if profile.get("ownerHitCheck") is True:
        out["itemOwnedProjectileMeaning"] = "owner_checked_close_or_held_hitbox; not automatically a free-flying thrown projectile"
    try:
        if int(float(profile.get("penetrate") or 0)) < 0:
            out["penetrateSemantics"] = "raw indefinite penetration on vanilla held/projectile source; do not copy literally unless intentionally authored"
    except Exception:
        pass
    if profile.get("tileCollide") is False:
        out["tileCollisionSemantics"] = "source projectile does not collide with tiles; may be held/visual/contact style"
    return out

def combined_tags(*items: dict[str, Any], data: dict[str, Any] | None = None) -> set[str]:
    tags: set[str] = set()
    for item in items:
        tags |= tags_of(item)
    if isinstance(data, dict):
        tags |= {str(t).lower() for t in data.get("tags", []) if str(t).strip()}
        for section in (data.get("designFeatures"), data.get("sourceRepresentation"), data.get("inheritance")):
            try:
                tags |= {tok.lower() for tok in re.findall(r"[A-Za-z_]+", json.dumps(section, ensure_ascii=False)) if len(tok) >= 3}
            except Exception:
                pass
    return tags

def behavior_policy_for_prompt(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Authoring contract note for the LLM.

    This is intentionally not a semantic router. Older builds used small families such as
    explosive/thrown/light/heal here; that grew into code-side design. The planner should
    author the role/effect itself, while the server only validates executable bounds.
    """
    return {
        "family": "runtime_authored",
        "serverWillEnforce": "technical safety only: finite numbers, supported engine calls, active projectile/sync pressure, bounded recursion",
        "note": "No item-name family exception table is applied here. If you want an effect, author it explicitly in runtimePlan.engineCalls.",
    }

# Parent-relative soft damage caps are deliberately not exposed to the LLM prompt.
# Balance lives in llm_authoring_prompt.authored_weapon_damage() and
# combine_balance.clamp_vanilla_like_weapon_damage();
# this module only packages raw parent facts and hard executable context for authoring.
