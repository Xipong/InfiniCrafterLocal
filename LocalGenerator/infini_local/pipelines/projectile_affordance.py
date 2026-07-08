from __future__ import annotations

import json
from typing import Any

from infini_local.core.item_identity_tools import item_num
from infini_local.pipelines.parent_context_pipeline import (
    _pbool,
    _pnum,
    effective_projectile_profile_of,
)


# AGENT MAP: projectile visual-family and parent-projectile affordance seam.
# Owns visual-family inference and raw parent projectile size reference only;
# executable behavior stays authored through runtimePlan/attack genome.
# Public callers use infini_local.pipelines.combine_pipeline.

def parent_combo_looks_like_bow(a: dict[str, Any], b: dict[str, Any], tags: set[str], data: dict[str, Any]) -> bool:
    text = " ".join(str(x or "") for x in [
        a.get("name"), b.get("name"), a.get("internalName"), b.get("internalName"),
        data.get("name"), data.get("tooltip"), data.get("sourceReading"),
    ]).lower()
    return bool("bow" in tags or "arrow" in tags or "bow" in text or int(item_num(a, "useAmmo", 0)) == 40 or int(item_num(b, "useAmmo", 0)) == 40)

def projectile_family_text(data: dict[str, Any], a: dict[str, Any] | None = None, b: dict[str, Any] | None = None) -> str:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    chunks = [
        data.get("name"), data.get("tooltip"), data.get("parentA"), data.get("parentB"),
        concept.get("fantasy"), concept.get("mergeLogic"), concept.get("weirdTwist"),
        attack.get("weaponFamily"), attack.get("projectileFamily"), attack.get("projectileShape"), attack.get("projectileMotion"), attack.get("projectileTrail"),
        visual.get("imagePrompt"), visual.get("projectileImagePrompt"), visual.get("impactImagePrompt"), visual.get("silhouetteSummary"),
        " ".join(str(x) for x in (data.get("tags") or [])),
    ]
    for item in (a or {}, b or {}):
        chunks.extend([item.get("name"), item.get("internalName"), item.get("fullName"), " ".join(str(x) for x in (item.get("tags") or []))])
        try:
            proj = effective_projectile_profile_of(item)
            if isinstance(proj, dict):
                chunks.extend([proj.get("internalName"), proj.get("fullName"), proj.get("sourceItemInternalName")])
        except Exception:
            pass
    return " ".join(str(x or "") for x in chunks).lower()

def _explicit_visual_family_value(data: dict[str, Any]) -> str:
    raw = str(data.get("projectileVisualFamily") or data.get("projectileVisualFamilyHint") or "").strip().lower().replace("-", "_")
    aliases = {
        "throwing_star": "shuriken_star",
        "disc": "round_disc",
        "disk": "round_disc",
    }
    return aliases.get(raw, raw)

def infer_projectile_visual_family(data: dict[str, Any], a: dict[str, Any] | None = None, b: dict[str, Any] | None = None) -> str:
    """Return a visual-orientation family for generated projectile sprites.

    This is not gameplay routing: executable behavior still comes from runtimePlan.
    The fallback only uses authored runtime family fields and raw projectile facts to keep
    arrows/darts/bolts side-on instead of vertical inventory-icon sprites.
    """
    explicit = _explicit_visual_family_value(data)
    allowed = {"linear_side", "shuriken_star", "round_disc", "spark_mote", "orb_rune", "generic_projectile"}
    if explicit in allowed:
        return explicit
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    weapon_family = str(attack.get("weaponFamily") or attack.get("projectileFamily") or "").lower()
    runtime_family = str(attack.get("runtimeFamily") or attack.get("delivery") or "").lower()
    if weapon_family in {"bow", "crossbow", "repeater", "gun", "shotgun", "blowgun", "dart", "launcher", "harpoon"}:
        return "linear_side"
    if runtime_family in {"shoot", "throw"}:
        for parent in (a or {}, b or {}):
            try:
                fam = parent_projectile_family(effective_projectile_profile_of(parent))
            except Exception:
                fam = ""
            if fam == "linear_side":
                return "linear_side"
    return "generic_projectile"

def parent_projectile_family(proj: dict[str, Any]) -> str:
    """Internal raw-shape bucket for diagnostics only.

    Uses explicit raw projectile booleans/aiStyle buckets where available; does not inspect
    item names for semantic routing.
    """
    if not isinstance(proj, dict):
        return "generic_projectile"
    ai_style = int(_pnum(proj, "aiStyle", -1))
    if _pbool(proj, "arrow") or ai_style == 1:
        return "linear_side"
    if _pbool(proj, "minion"):
        return "minion"
    if _pbool(proj, "sentry"):
        return "sentry"
    if _pbool(proj, "ownerHitCheck") or ai_style in {19, 20, 161, 165, 190}:
        return "held_hitbox"
    return "generic_projectile"

def choose_parent_projectile_size_reference(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Aggregate raw parent projectile size floors without semantic family routing.

    This helper deliberately does not take desired runtime/projectile family. The parent
    projectile data is only a readability floor for width/height/scale; movement,
    delivery, prompt shape and gameplay remain authored by runtimePlan. If both parents
    have projectile facts, preserve the largest raw width, height and scale independently
    so a high-scale small projectile cannot hide a wider/taller sibling.
    """
    candidates: list[dict[str, Any]] = []
    for item, label in ((a, "A"), (b, "B")):
        try:
            proj = effective_projectile_profile_of(item)
        except Exception:
            proj = {}
        if isinstance(proj, dict) and proj:
            c = dict(proj)
            c["__parent"] = label
            c["__family"] = parent_projectile_family(c)
            candidates.append(c)
    if not candidates:
        return {}

    def num(proj: dict[str, Any], key: str, default: float = 0.0) -> float:
        try:
            return float(proj.get(key) if proj.get(key) is not None else default)
        except Exception:
            return default

    width_source = max(candidates, key=lambda p: num(p, "width", 0.0))
    height_source = max(candidates, key=lambda p: num(p, "height", 0.0))
    scale_source = max(candidates, key=lambda p: num(p, "scale", 1.0))
    primary = max(candidates, key=lambda p: (num(p, "width", 0.0) * num(p, "height", 0.0) * max(0.1, num(p, "scale", 1.0))))

    out = dict(primary)
    out["__parent"] = "max" if len(candidates) > 1 else str(primary.get("__parent") or "?")
    out["__family"] = str(primary.get("__family") or parent_projectile_family(primary))
    out["__basis"] = "max raw parent projectile width/height/scale"
    out["__sources"] = {
        "width": str(width_source.get("__parent") or "?"),
        "height": str(height_source.get("__parent") or "?"),
        "scale": str(scale_source.get("__parent") or "?"),
        "primary": str(primary.get("__parent") or "?"),
    }
    out["__candidates"] = [
        {
            "parent": str(p.get("__parent") or "?"),
            "internalName": str(p.get("internalName") or ""),
            "fullName": str(p.get("fullName") or ""),
            "family": str(p.get("__family") or ""),
            "aiStyle": int(num(p, "aiStyle", 0.0)),
            "width": int(num(p, "width", 0.0)),
            "height": int(num(p, "height", 0.0)),
            "scale": round(num(p, "scale", 1.0), 3),
        }
        for p in candidates
    ]
    out["width"] = int(num(width_source, "width", 0.0))
    out["height"] = int(num(height_source, "height", 0.0))
    out["scale"] = round(num(scale_source, "scale", 1.0), 3)
    return out

def apply_parent_projectile_affordance(genome: dict[str, Any], a: dict[str, Any], b: dict[str, Any], tags: set[str], data: dict[str, Any], damage_class: str) -> dict[str, Any]:
    """Expose raw parent projectile size facts without silently authoring size.

    Parent projectile width/height/scale are useful context, but generated projectile
    dimensions belong to the LLM/runtimePlan. By default this helper only writes debug
    provenance. It applies parent size floors only when the authored genome explicitly
    opts in through use_affordance.projectileSizePolicy.
    """
    delivery = str(genome.get("delivery") or "").lower()
    if delivery not in {"shoot", "throw", "cast"}:
        return genome
    parent_proj = choose_parent_projectile_size_reference(a, b)
    if not parent_proj:
        return genome

    size_policy = str(genome.get("projectileSizePolicy") or "authored").strip().lower().replace("-", "_")
    apply_floor = size_policy in {"inherit_parent_floor", "inherit_parent_max"}
    debug_payload = {
        "parent": parent_proj.get("__parent", "?"),
        "internalName": parent_proj.get("internalName", ""),
        "fullName": parent_proj.get("fullName", ""),
        "aiStyle": int(float(parent_proj.get("aiStyle") or 0)),
        "width": int(float(parent_proj.get("width") or 0)),
        "height": int(float(parent_proj.get("height") or 0)),
        "scale": float(parent_proj.get("scale") or 1.0),
        "basis": str(parent_proj.get("__basis") or "raw parent projectile dimensions only"),
        "sources": parent_proj.get("__sources") if isinstance(parent_proj.get("__sources"), dict) else {},
        "candidates": parent_proj.get("__candidates") if isinstance(parent_proj.get("__candidates"), list) else [],
        "projectileSizePolicy": size_policy,
        "appliedToGenome": bool(apply_floor),
    }
    if not apply_floor:
        debug_payload["note"] = "reference only; LLM did not opt into parent projectile size floor"
    try:
        data.setdefault("debug", {})["parentProjectileRef"] = json.dumps(debug_payload, ensure_ascii=False)
    except Exception:
        pass
    if not apply_floor:
        return genome
    try:
        pw = int(float(parent_proj.get("width") or 0))
        ph = int(float(parent_proj.get("height") or 0))
        ps = float(parent_proj.get("scale") or 1.0)
        if pw > 0:
            genome["projectileWidth"] = max(pw, int(float(genome.get("projectileWidth") or 0) or 0))
        if ph > 0:
            genome["projectileHeight"] = max(ph, int(float(genome.get("projectileHeight") or 0) or 0))
        if ps > 0:
            genome["projectileScale"] = round(max(ps, float(genome.get("projectileScale") or 1.0)), 3)
    except Exception:
        pass
    return genome

__all__ = [
    "parent_combo_looks_like_bow",
    "projectile_family_text",
    "_explicit_visual_family_value",
    "infer_projectile_visual_family",
    "parent_projectile_family",
    "choose_parent_projectile_size_reference",
    "apply_parent_projectile_affordance",
]
