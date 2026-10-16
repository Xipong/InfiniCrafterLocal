from __future__ import annotations

import copy
import json
from typing import Any

from infini_local.core.runtime_authoring.binding_use_policy import (
    wire_action_kind as binding_action_kind,
    wire_target_id as binding_target_id,
)
from infini_local.core.item_identity_tools import (
    dict_get_ci,
    fingerprint_of,
    generated_data_of,
    item_field,
)
from infini_local.pipelines.pipeline_runtime_constants import (
    LLM_AMMO_ITEM_KEYS,
    LLM_INCLUDE_AISTYLE_RAW,
    LLM_ITEM_RAW_KEYS,
    LLM_PROJECTILE_RAW_KEYS,
)
from infini_local.services.runtime_dump_service import (
    runtime_projectile_lookup,
)


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
    """Read native projectile facts; generated parents use their full accepted graph."""
    if generated_data_of(item):
        # Generated parents expose their complete accepted entity graph. There
        # is no truthful single vanilla projectile profile to select for it.
        return {}
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
    return _raw_section_dict(item, "ammoRaw")


def effective_projectile_profile_of(item: dict[str, Any]) -> dict[str, Any]:
    if generated_data_of(item):
        return {}
    raw_effective = _raw_section_dict(item, "effectiveProjectileRaw")
    if raw_effective:
        return _strip_texture_metrics_for_llm(raw_effective)
    return projectile_profile_of(item)


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
    raw = {key: item_field(item, key, None) for key in LLM_ITEM_RAW_KEYS
           if item_field(item, key, None) is not None}
    out = _select_raw_keys(raw, LLM_ITEM_RAW_KEYS)
    # Literal source text/provenance is one observation: preserve line order,
    # whitespace, empty lines and source-bound refusal without compacting it.
    for key in ("tooltipLines", "tooltipSource"):
        value = item_field(item, key, None)
        if value is not None:
            out[key] = copy.deepcopy(value)
    if generated_data_of(item):
        for key in ("createTile", "createWall", "placeStyle"):
            out.pop(key, None)
        out.update(_generated_placement_fields(item))
    return out

def _generated_placement_fields(item: dict[str, Any]) -> dict[str, Any]:
    """Only a single explicit canonical place binding can be represented as item fields.

    Active-use Item fields can be reset to nonplacing outside the use hook. Multiple
    distinct placements remain visible on their separate generatedParent bindings.
    """
    program = dict_get_ci(generated_data_of(item), "runtimeProgram", {})
    if not isinstance(program, dict):
        return {}
    placements = []
    for binding in program.get("bindings") or []:
        if not isinstance(binding, dict):
            continue
        policy = dict_get_ci(binding, "usePolicy", {})
        action = dict_get_ci(policy, "action", {}) if isinstance(policy, dict) else {}
        if not isinstance(action, dict) or dict_get_ci(action, "kind") != "place_item":
            continue
        placement = dict_get_ci(action, "placement", {})
        if isinstance(placement, dict):
            placements.append(placement)
    if len(placements) != 1:
        return {}
    placement = placements[0]
    return {key: placement[source] for key, source in (
        ("createTile", "tileId"), ("createWall", "wallId"), ("placeStyle", "placeStyle")
    ) if source in placement and placement[source] is not None}

def compact_projectile_profile(proj: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(proj, dict) or not proj:
        return {}
    out = _select_raw_keys(proj, LLM_PROJECTILE_RAW_KEYS)
    # The native producer owns verification and scope. Never infer a trajectory
    # from names/aiStyle or compact/clip this optional read-only observation.
    if isinstance(proj.get("motionReference"), dict):
        out["motionReference"] = copy.deepcopy(proj["motionReference"])
    if LLM_INCLUDE_AISTYLE_RAW and _compact_keep(proj.get("aiStyle")):
        out["aiStyle"] = _compact_raw_value(proj.get("aiStyle"))
    return out

def compact_ammo_profile(item: dict[str, Any]) -> dict[str, Any]:
    ap = ammo_profile_of(item)
    if not isinstance(ap, dict) or not ap:
        return {}
    out: dict[str, Any] = {}
    if _compact_keep(ap.get("mode")):
        out["mode"] = ap["mode"]
    if _compact_keep(ap.get("ammoId")):
        out["ammoId"] = ap["ammoId"]
    if isinstance(ap.get("ammoItemRaw"), dict):
        out["ammoItemRaw"] = _select_raw_keys(ap["ammoItemRaw"], LLM_AMMO_ITEM_KEYS)
    for key in ("projectileRaw", "weaponShootFieldProjectileRaw"):
        if isinstance(ap.get(key), dict):
            out[key] = compact_projectile_profile(ap[key])
    return {k: v for k, v in out.items() if _compact_keep(v)}

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
        "pickPower", "axePower", "hammerPower", "defense", "healLife", "healMana", "potion", "buffType", "buffTime",
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
        if n > 0 or k in {"createTile", "createWall", "placeStyle"}:
            out[k] = n
    if generated_data_of(item):
        for key in ("createTile", "createWall", "placeStyle"):
            out.pop(key, None)
        out.update(_generated_placement_fields(item))
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
    """Deduplicate only equivalent retained facts, not similar core mechanics.

    Only the top-level provenance `source` may differ; the replacement retains
    it separately. Nested source/scope, sets, presence and scalar types are facts.
    Canonical JSON ignores object order without Python's 0 == False == 0.0 alias.
    """
    if not isinstance(a, dict) or not isinstance(b, dict) or not a or not b:
        return False
    identity_keys = ("type", "internalName", "sourceMod")
    if not any(_compact_keep(a.get(k)) and a.get(k) == b.get(k) for k in identity_keys):
        return False
    return json.dumps({k: v for k, v in a.items() if k != "source"}, sort_keys=True) == json.dumps(
        {k: v for k, v in b.items() if k != "source"}, sort_keys=True,
    )

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
