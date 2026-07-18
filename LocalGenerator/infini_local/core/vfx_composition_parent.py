from __future__ import annotations

import json
from typing import Any

from infini_local.core.item_identity_tools import (
    generation_depth,
    item_bool,
    item_field,
    item_identity,
    item_num,
    name_of,
)
from infini_local.core.vfx_composition_primitives import (
    _vfx_default_anchor,
    _vfx_default_backend,
    _vfx_infer_channel,
    _vfx_unit,
)
from infini_local.core.vfx_manifest_config import (
    VFX_PARENT_EFFECT_INHERITANCE,
    VFX_PARENT_EFFECT_MAX_INHERITED_SLOTS,
    VFX_PARENT_EFFECT_STRONG_THRESHOLD,
)
from infini_local.core.vfx_projectile_profile import (
    effective_projectile_profile_of,
    proj_bool,
    proj_num,
    projectile_behavior_tags,
    source_weapon_profile,
)

# AGENT MAP: parent VFX inheritance and generated-parent effect profiling.

def _vfx_manifest_from_parent_item(item: dict[str, Any]) -> dict[str, Any]:
    """Best-effort extraction of a frozen VFX manifest from a generated parent item.

    Parent manifests are data, not live logic. We only read their public slots/motif/magnitude and
    transform them into small support/accent layers for the child result.
    """
    if not isinstance(item, dict):
        return {}
    direct = item.get("vfxManifest") or item.get("VfxManifest")
    if isinstance(direct, dict):
        return direct
    attack = item.get("attack") if isinstance(item.get("attack"), dict) else item.get("Attack") if isinstance(item.get("Attack"), dict) else {}
    raw = ""
    if isinstance(attack, dict):
        raw = str(attack.get("vfxManifestJson") or attack.get("VfxManifestJson") or "")
    if raw.strip().startswith("{"):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}

def _vfx_parent_profile_from_item(item: dict[str, Any], index: int = 0) -> dict[str, Any]:
    name = name_of(item)
    try:
        rarity = int(float(item_field(item, "rare", item_field(item, "rarity", 0)) or 0))
    except Exception:
        rarity = 0
    try:
        damage = float(item_num(item, "damage", 0))
    except Exception:
        damage = 0.0
    try:
        use_time = float(item_num(item, "useTime", item_num(item, "useAnimation", 30)))
    except Exception:
        use_time = 30.0
    prof: dict[str, Any] = {}
    try:
        prof = source_weapon_profile(item)
    except Exception:
        prof = {}
    projectile = prof.get("projectileProfile") if isinstance(prof.get("projectileProfile"), dict) else effective_projectile_profile_of(item)
    behavior = set(str(x) for x in (prof.get("behaviorTags") or projectile_behavior_tags(item)) if str(x))
    manifest = _vfx_manifest_from_parent_item(item)
    manifest_slots = [x for x in (manifest.get("slots") or []) if isinstance(x, dict)] if isinstance(manifest, dict) else []
    manifest_mag = 0.0
    if isinstance(manifest, dict):
        try:
            manifest_mag = float(manifest.get("effectMagnitude") or 0.0)
        except Exception:
            manifest_mag = 0.0
    effect_tags: set[str] = set()
    suggested: set[str] = set()
    if damage > 0:
        effect_tags.add("weapon")
    if damage >= 25 or rarity >= 3:
        effect_tags.add("strong_parent")
    if item_num(item, "shoot", 0) > 0:
        effect_tags.update({"projectile", "travel"}); suggested.add("projectileAfterimage")
    if item_bool(item, "channel"):
        effect_tags.update({"channel", "beam", "sustained"}); suggested.add("beamLine")
    if item_bool(item, "noMelee"):
        effect_tags.add("projectile_delivery")
    if str(item_field(item, "damageClass", "")).lower() in {"melee", "meleenospeed", "melee damage"} or (damage > 0 and item_num(item, "shoot", 0) <= 0):
        effect_tags.update({"slash", "held"}); suggested.add("tipTrail")
    if isinstance(projectile, dict) and projectile:
        if proj_num(projectile, "light", 0) > 0:
            effect_tags.add("light"); suggested.add("lightCue")
        if proj_num(projectile, "extraUpdates", 0) > 0:
            effect_tags.add("fast")
        if proj_num(projectile, "penetrate", 1) == -1 or proj_num(projectile, "penetrate", 1) > 1:
            effect_tags.add("pierce"); suggested.add("historyRibbon")
        if not proj_bool(projectile, "tileCollide"):
            effect_tags.add("phase")
        if proj_bool(projectile, "usesLocalNPCImmunity") or proj_bool(projectile, "usesIDStaticNPCImmunity"):
            effect_tags.add("multihit"); suggested.add("impactSpriteBurst")
        if proj_bool(projectile, "minion") or proj_bool(projectile, "sentry"):
            effect_tags.add("summoned")
        ai_style = int(proj_num(projectile, "aiStyle", 0))
        if ai_style > 0:
            effect_tags.add(f"aiStyle_{ai_style}")
    for t in behavior:
        effect_tags.add(t)
        if t in {"homing", "boomerang", "returning"}:
            suggested.add("orbitingMotes")
        if t in {"beam", "channel"}:
            suggested.add("beamLine")
        if t in {"trail", "oldPos", "extraUpdates"}:
            suggested.add("historyRibbon")
    if manifest_slots:
        effect_tags.add("generated_vfx_parent")
        for slot in manifest_slots:
            renderer = str(slot.get("rendererKind") or "")
            if renderer:
                suggested.add(renderer)
            ch = str(slot.get("channel") or "")
            if ch:
                effect_tags.add("channel_" + ch)

    score = 0.0
    score += min(0.28, damage / 180.0)
    score += min(0.20, max(0, rarity) / 30.0)
    try:
        score += min(0.22, float(prof.get("effectiveDpsSignal") or 0.0) / 250.0)
    except Exception:
        pass
    score += min(0.16, len(behavior) * 0.025)
    if item_num(item, "shoot", 0) > 0: score += 0.08
    if item_bool(item, "channel"): score += 0.10
    if isinstance(projectile, dict) and projectile:
        if proj_num(projectile, "light", 0) > 0: score += 0.06
        if proj_num(projectile, "extraUpdates", 0) > 0: score += 0.04
        if proj_num(projectile, "penetrate", 1) == -1 or proj_num(projectile, "penetrate", 1) > 1: score += 0.05
        if not proj_bool(projectile, "tileCollide"): score += 0.04
        if proj_bool(projectile, "usesLocalNPCImmunity") or proj_bool(projectile, "usesIDStaticNPCImmunity"): score += 0.06
    if manifest_slots:
        score += min(0.42, 0.16 + manifest_mag * 0.24 + len(manifest_slots) * 0.015)

    score = max(0.0, min(1.0, score))
    return {
        "index": index,
        "name": name,
        "identity": item_identity(item),
        "generatedDepth": generation_depth(item),
        "damage": round(damage, 3),
        "rarity": rarity,
        "useTime": round(use_time, 3),
        "specialScore": round(score, 3),
        "notable": bool(score >= VFX_PARENT_EFFECT_STRONG_THRESHOLD or manifest_slots),
        "effectTags": sorted(effect_tags)[:48],
        "suggestedRenderers": sorted(suggested)[:20],
        "weaponProfile": {k: prof.get(k) for k in ["damage", "damageClass", "shoot", "shootSpeed", "channel", "aiStyle", "piercePotential", "lifetime", "extraUpdates", "localImmunity", "effectiveDpsSignal"] if k in prof},
        "manifestSummary": {
            "hasManifest": bool(manifest_slots),
            "recipeId": str(manifest.get("recipeId") or "") if isinstance(manifest, dict) else "",
            "effectMagnitude": round(manifest_mag, 3),
            "visualBudgetClass": str(manifest.get("visualBudgetClass") or "") if isinstance(manifest, dict) else "",
            "slotCount": len(manifest_slots),
            "motif": manifest.get("motif") if isinstance(manifest.get("motif"), dict) else {},
        },
        "manifestSlots": manifest_slots[:10],
    }

def _vfx_parent_effect_profile(data: dict[str, Any], parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None) -> dict[str, Any]:
    if not VFX_PARENT_EFFECT_INHERITANCE:
        return {"enabled": False}
    meta = data.setdefault("recipeMeta", {}) if isinstance(data, dict) else {}
    if not isinstance(meta, dict):
        meta = {}
    items = [x for x in (parent_a, parent_b) if isinstance(x, dict) and x]
    if not items and isinstance(meta.get("parentVfxEffectProfile"), dict):
        return meta["parentVfxEffectProfile"]
    if not items:
        return {"enabled": False, "reason": "no_parent_items_available"}
    parents = [_vfx_parent_profile_from_item(item, i) for i, item in enumerate(items)]
    max_score = max([float(p.get("specialScore") or 0.0) for p in parents] or [0.0])
    same_identity = len(parents) >= 2 and parents[0].get("identity") and parents[0].get("identity") == parents[1].get("identity")
    same_name = len(parents) >= 2 and str(parents[0].get("name") or "").strip().lower() == str(parents[1].get("name") or "").strip().lower()
    generated_manifest_parent = any((p.get("manifestSummary") or {}).get("hasManifest") for p in parents)
    tags = sorted({t for p in parents for t in (p.get("effectTags") or [])})[:80]
    renderers = sorted({r for p in parents for r in (p.get("suggestedRenderers") or [])})[:36]
    profile = {
        "enabled": True,
        "sameParent": bool(same_identity or same_name),
        "sameIdentity": bool(same_identity),
        "sameName": bool(same_name),
        "maxSpecialScore": round(max_score, 3),
        "notable": bool(max_score >= VFX_PARENT_EFFECT_STRONG_THRESHOLD or generated_manifest_parent),
        "generatedManifestParent": bool(generated_manifest_parent),
        "effectTags": tags,
        "suggestedRenderers": renderers,
        "parents": [{k: v for k, v in p.items() if k != "manifestSlots"} for p in parents],
    }
    meta["parentVfxEffectProfile"] = profile
    data["recipeMeta"] = meta
    return profile

def _vfx_transform_parent_slot_for_child(slot: dict[str, Any], source: str, seed: int, order: int) -> dict[str, Any]:
    out = dict(slot)
    renderer = str(out.get("rendererKind") or "childMotes")
    event = str(out.get("event") or "travel")
    # Parent effects become support/accent layers; the child result still owns the primary composition.
    out["source"] = f"parentEffect:{source}"
    out["importance"] = "accent" if order else "secondary"
    out["lane"] = "accent" if order else "support"
    out["channel"] = out.get("channel") or _vfx_infer_channel(renderer, event)
    out["backend"] = out.get("backend") or _vfx_default_backend(event, renderer)
    out["anchor"] = out.get("anchor") or _vfx_default_anchor(event, renderer)
    try: out["density"] = max(0.05, min(0.48, float(out.get("density") or 0.25) * 0.72))
    except Exception: out["density"] = 0.22
    try: out["alpha"] = max(0.16, min(0.62, float(out.get("alpha") or 0.38) * 0.82))
    except Exception: out["alpha"] = 0.32
    try: out["scale"] = max(0.45, min(2.35, float(out.get("scale") or 1.0) * (0.82 + _vfx_unit(seed, f"parentscale{order}") * 0.26)))
    except Exception: out["scale"] = 1.0
    try: out["signatureWeight"] = max(0.05, min(0.55, float(out.get("signatureWeight") or 0.22) * 0.65))
    except Exception: out["signatureWeight"] = 0.22
    try: out["visualCost"] = max(0.04, min(0.42, float(out.get("visualCost") or 0.18) * 0.66))
    except Exception: out["visualCost"] = 0.16
    out.pop("bakedCommands", None)
    out.pop("bakedClipId", None)
    out.pop("bakedClipHash", None)
    out.pop("bakedCommandCount", None)
    return out

def _vfx_parent_inherited_raw_slots(profile: dict[str, Any], pattern: str, roles: set[str], magnitude_class: str, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Inherit only frozen parent manifest slots; never synthesize VFX from tags or prose."""
    if not VFX_PARENT_EFFECT_INHERITANCE or not isinstance(profile, dict):
        return [], []
    max_slots = max(0, min(6, VFX_PARENT_EFFECT_MAX_INHERITED_SLOTS))
    if max_slots <= 0:
        return [], []
    raw: list[dict[str, Any]] = []
    debug: list[dict[str, Any]] = []
    for slot in profile.get("_rawParentSlots") or []:
        if not isinstance(slot, dict):
            continue
        transformed = _vfx_transform_parent_slot_for_child(slot, "manifest", seed, len(raw))
        raw.append(transformed)
        debug.append({
            "reason": "frozen_parent_manifest",
            "rendererKind": transformed.get("rendererKind"),
            "event": transformed.get("event"),
            "channel": transformed.get("channel", ""),
        })
        if len(raw) >= max_slots:
            break
    return raw, debug

__all__ = [
    "_vfx_manifest_from_parent_item",
    "_vfx_parent_profile_from_item",
    "_vfx_parent_effect_profile",
    "_vfx_transform_parent_slot_for_child",
    "_vfx_parent_inherited_raw_slots",
]
