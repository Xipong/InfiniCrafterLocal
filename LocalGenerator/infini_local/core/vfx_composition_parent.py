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
    tags_of,
)
from infini_local.core.vfx_composition_primitives import (
    _vfx_default_anchor,
    _vfx_default_backend,
    _vfx_event_group,
    _vfx_infer_channel,
    _vfx_renderer_family,
    _vfx_slot_score,
    _vfx_unit,
)
from infini_local.core.vfx_manifest_config import (
    VFX_PARENT_EFFECT_INHERITANCE,
    VFX_PARENT_EFFECT_MAX_INHERITED_SLOTS,
    VFX_PARENT_EFFECT_STRONG_THRESHOLD,
    VFX_PARENT_EFFECT_WEIGHT,
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
    if not raw and isinstance(item.get("debug"), dict):
        raw = str(item["debug"].get("vfxManifest") or "")
    if raw.strip().startswith("{"):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}

def _vfx_parent_profile_from_item(item: dict[str, Any], index: int = 0) -> dict[str, Any]:
    name = name_of(item)
    tags = set(tags_of(item))
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
        tl = t.lower()
        if any(x in tl for x in ["homing", "boomerang", "return"]):
            suggested.add("orbitalMotes")
        if any(x in tl for x in ["beam", "laser"]):
            suggested.add("beamLine")
        if any(x in tl for x in ["trail", "oldpos", "extra_updates"]):
            suggested.add("historyRibbon")
    if manifest_slots:
        effect_tags.add("generated_vfx_parent")
        for slot in manifest_slots:
            renderer = str(slot.get("renderer") or "")
            if renderer:
                suggested.add(renderer)
            ch = str(slot.get("channel") or "")
            if ch:
                effect_tags.add("channel_" + ch)
    runtime_signals = item.get("parentVfxSignals") if isinstance(item.get("parentVfxSignals"), dict) else {}
    # Do not infer VFX inheritance from parent names/tokens. Names still go to LLM/art prompts,
    # but parent VFX inheritance is driven by mechanical/runtime facts only.
    if isinstance(runtime_signals, dict) and runtime_signals:
        for t in runtime_signals.get("effectTags") or []:
            if str(t): effect_tags.add("runtime_" + str(t))
        for r in runtime_signals.get("suggestedRenderers") or []:
            if str(r): suggested.add(str(r))
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
    if isinstance(runtime_signals, dict) and runtime_signals:
        try:
            score = max(score, float(runtime_signals.get("specialScore") or 0.0))
        except Exception:
            pass
        if runtime_signals.get("hasProjectileEmission"):
            score += 0.05
        if runtime_signals.get("hasSustainedUse") or runtime_signals.get("hasBeamLikeProfile"):
            score += 0.06
        if runtime_signals.get("hasGeneratedManifest"):
            score += 0.12
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
        "parentRuntimeSignals": runtime_signals if isinstance(runtime_signals, dict) else {},
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

def _vfx_parent_effect_tag_set(profile: dict[str, Any]) -> set[str]:
    if not isinstance(profile, dict) or not profile.get("enabled"):
        return set()
    tags = {str(x).lower() for x in (profile.get("effectTags") or []) if str(x)}
    renderers = {str(x).lower() for x in (profile.get("suggestedRenderers") or []) if str(x)}
    return tags | renderers

def _vfx_parent_effect_recipe_bonus(recipe: dict[str, Any], profile: dict[str, Any]) -> tuple[float, list[str]]:
    if not isinstance(profile, dict) or not profile.get("enabled") or not profile.get("notable"):
        return 0.0, []
    tags = _vfx_parent_effect_tag_set(profile)
    if not tags:
        return 0.0, []
    raw_slots = [x for x in (recipe.get("slots") or []) if isinstance(x, dict)]
    slot_renderers = {_vfx_renderer_family(str(s.get("renderer") or "")).lower() for s in raw_slots}
    slot_channels = {str(s.get("channel") or _vfx_infer_channel(s.get("renderer"), s.get("event"))).lower() for s in raw_slots}
    bonus = 0.0
    reasons: list[str] = []
    if any(x in tags for x in {"slash", "held", "tiptrail", "historyribbon"}) and (slot_renderers & {"tiptrail", "historyribbon", "ghostarc"}):
        bonus += 22.0; reasons.append("parent_slash_renderer_match")
    if any(x in tags for x in {"projectile", "travel", "projectileafterimage"}) and (slot_renderers & {"projectileafterimage", "spritestamptrail"}):
        bonus += 17.0; reasons.append("parent_projectile_renderer_match")
    if any(x in tags for x in {"beam", "channel", "beamline"}) and ("beamline" in slot_renderers or "beam" in " ".join(slot_renderers)):
        bonus += 24.0; reasons.append("parent_beam_renderer_match")
    if any(x in tags for x in {"multihit", "pierce", "impactspriteburst", "impactshape"}) and ("impactshape" in slot_channels or "impactspriteburst" in slot_renderers):
        bonus += 18.0; reasons.append("parent_impact_renderer_match")
    if any(x in tags for x in {"light", "lightcue"}) and ("lightcue" in slot_renderers or "light" in slot_channels):
        bonus += 10.0; reasons.append("parent_light_cue_match")
    score = float(profile.get("maxSpecialScore") or 0.0)
    if score >= 0.70 and str(recipe.get("cost") or "") in {"high", "signature", "ultra"}:
        bonus += 12.0; reasons.append("strong_parent_allows_heavy_recipe")
    if str(recipe.get("id") or "").startswith("mundane_"):
        bonus -= 110.0; reasons.append("parent_effect_blocks_mundane_recipe")
    return bonus * VFX_PARENT_EFFECT_WEIGHT, reasons

def _vfx_transform_parent_slot_for_child(slot: dict[str, Any], source: str, seed: int, order: int) -> dict[str, Any]:
    out = dict(slot)
    renderer = str(out.get("renderer") or "ambientMotes")
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
    if not isinstance(profile, dict) or not profile.get("enabled") or not profile.get("notable"):
        return [], []
    max_slots = max(0, min(6, VFX_PARENT_EFFECT_MAX_INHERITED_SLOTS))
    if max_slots <= 0:
        return [], []
    raw: list[dict[str, Any]] = []
    debug: list[dict[str, Any]] = []
    # Prefer actual generated-parent manifest slots when present.
    for parent in profile.get("parents") or []:
        pass
    # The public profile intentionally strips manifestSlots from debug. Re-read them from recipeMeta cache if present.
    meta_profile = profile
    # If attach_hybrid_vfx_manifest has raw parent profiles in memory, they are stored in _rawParentSlots.
    for slot in meta_profile.get("_rawParentSlots") or []:
        if isinstance(slot, dict):
            raw.append(_vfx_transform_parent_slot_for_child(slot, "manifest", seed, len(raw)))
            if len(raw) >= max_slots:
                break
    tags = _vfx_parent_effect_tag_set(profile)
    def add(slot: dict[str, Any], reason: str) -> None:
        nonlocal raw, debug
        if len(raw) >= max_slots:
            return
        slot = dict(slot)
        slot.setdefault("source", f"parentEffect:{reason}")
        raw.append(slot)
        debug.append({"reason": reason, "renderer": slot.get("renderer"), "event": slot.get("event"), "channel": slot.get("channel", "")})
    if "projectile" in roles and any(x in tags for x in {"slash", "held", "tiptrail", "historyribbon", "strong_parent"}) and pattern in {"slash_holdout", "beam_slash", "basic"}:
        add({"event":"active", "renderer":"historyRibbon", "textureRole":"projectile", "backend":"Primitive", "channel":"motionTrail", "lane":"support", "importance":"secondary", "scale":[0.9,1.65], "density":[0.18,0.48], "duration":[10,24], "alpha":[0.22,0.58], "visualCost":[0.12,0.36], "signatureWeight":[0.22,0.55]}, "slash_history")
    if "projectile" in roles and any(x in tags for x in {"projectile", "travel", "projectileafterimage", "fast"}):
        add({"event":"travel", "renderer":"projectileAfterimage", "textureRole":"projectile", "backend":"Sprite", "channel":"motionTrail", "lane":"support", "importance":"secondary", "scale":[0.75,1.28], "density":[0.12,0.38], "duration":[6,16], "alpha":[0.18,0.46], "visualCost":[0.08,0.28], "signatureWeight":[0.12,0.42]}, "projectile_afterimage")
    if "impact" in roles and any(x in tags for x in {"multihit", "pierce", "strong_parent", "generated_vfx_parent", "impactspriteburst"}):
        add({"event":"hit", "renderer":"impactSpriteBurst", "textureRole":"impact", "particleRole":"child", "backend":"Baked", "channel":"impactShape", "lane":"support", "importance":"secondary", "scale":[1.25,2.65], "density":[0.18,0.55], "duration":[6,15], "alpha":[0.38,0.82], "visualCost":[0.12,0.42], "signatureWeight":[0.20,0.56]}, "impact_inherited")
    if any(x in tags for x in {"beam", "channel", "beamline"}) and "projectile" in roles:
        add({"event":"active", "renderer":"beamLine", "textureRole":"projectile", "backend":"Primitive", "channel":"motionTrail", "lane":"support", "importance":"secondary", "scale":[0.75,1.55], "density":[0.16,0.42], "duration":[10,24], "alpha":[0.18,0.48], "visualCost":[0.10,0.34], "signatureWeight":[0.18,0.50]}, "beam_inherited")
    if any(x in tags for x in {"light", "lightcue"}):
        add({"event":"active", "renderer":"lightCue", "textureRole":"projectile", "backend":"Realtime", "channel":"light", "lane":"cue", "importance":"accent", "scale":[0.8,1.7], "density":[0.08,0.22], "duration":[8,22], "alpha":[0.2,0.55], "visualCost":[0.03,0.10], "signatureWeight":[0.10,0.25]}, "light_inherited")
    raw = raw[:max_slots]
    return raw, debug

__all__ = [
    "_vfx_manifest_from_parent_item",
    "_vfx_parent_profile_from_item",
    "_vfx_parent_effect_profile",
    "_vfx_parent_effect_tag_set",
    "_vfx_parent_effect_recipe_bonus",
    "_vfx_transform_parent_slot_for_child",
    "_vfx_parent_inherited_raw_slots",
]
