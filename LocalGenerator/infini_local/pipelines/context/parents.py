from __future__ import annotations

import copy
import json
from typing import Any

from infini_local.core.item_identity_tools import (
    dict_get_ci,
    fingerprint_of,
    generated_data_of,
    item_field,
)
from infini_local.pipelines.context.attack_behavior import project_attack_behavior
from infini_local.pipelines.context.attack_tables import pack_attack_tables
from infini_local.pipelines.pipeline_runtime_constants import (
    LLM_AMMO_ITEM_KEYS,
    LLM_INCLUDE_AISTYLE_RAW,
    LLM_ITEM_RAW_KEYS,
    LLM_PROJECTILE_RAW_KEYS,
)
from infini_local.services.runtime_dump_service import (
    runtime_projectile_lookup,
    runtime_item_lookup,
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



def _observed_parent_field(item: dict[str, Any], name: str) -> tuple[bool, Any]:
    """Presence, not truthiness; preserve the existing readers' case aliases."""
    fingerprint = item.get("fingerprint")
    projectile_alias = name in ("directProjectileRaw", "effectiveProjectileRaw")
    runtime_alias = projectile_alias or name in (
        "nativeEquipmentReference", "nativeEnvironmentReference", "parentSourceGraph")
    sources = [(item, projectile_alias), (fingerprint, projectile_alias),
               (dict_get_ci(item, "runtimeFacts"), runtime_alias)]
    if isinstance(fingerprint, dict):
        sources.append((dict_get_ci(fingerprint, "runtimeFacts"), runtime_alias))
    absent = object()
    for source, case_alias in sources:
        if not isinstance(source, dict):
            continue
        value = dict_get_ci(source, name, absent) if case_alias else source.get(name, absent)
        if value is not absent:
            return True, value
    return False, None


# Whole producer-owned observations only. Never copy combat scalars, stateful
# effective/ammo snapshots, fingerprints, generated data, tags or inferred design.
_DUMP_ITEM_OBSERVATIONS = (
    "nativeShootReference", "nativeContactHitStatusReference", "nativeEquipmentReference",
    "nativeEnvironmentReference", "nativeBuffEffectReference",
    "parentSourceGraph", "directProjectileRaw", "spriteReferenceRaw",
)


def native_item_context_from_dump(item: dict[str, Any]) -> dict[str, Any]:
    """Read-only card enrichment; the input/recipe/fingerprint remain unchanged."""
    if isinstance(item.get("generatedData"), dict) or item.get("unavailable") is True:
        return item
    absent = object()
    for container in (item, item.get("fingerprint")):
        runtime = dict_get_ci(container, "runtimeFacts", absent)
        if runtime is not absent and (not isinstance(runtime, dict) or runtime.get("unavailable") is True):
            return item
    missing = [key for key in _DUMP_ITEM_OBSERVATIONS if not _observed_parent_field(item, key)[0]]
    # Lines and their source form one observation; don't splice another locale
    # or capture's certificate onto a present (even empty) live tooltip.
    if not any(_observed_parent_field(item, key)[0] for key in ("tooltipLines", "tooltipSource")):
        missing.extend(("tooltipLines", "tooltipSource"))
    if not missing:
        return item
    _, identity = _observed_parent_field(item, "id")
    if identity is None:
        _, identity = _observed_parent_field(item, "type")
    if type(identity) not in (int, str):
        return item
    _, full_name = _observed_parent_field(item, "fullName")
    if not isinstance(full_name, str) or not full_name:
        _, mod = _observed_parent_field(item, "sourceMod")
        _, name = _observed_parent_field(item, "internalName")
        if isinstance(mod, str) and mod and isinstance(name, str) and name:
            full_name = name if name.startswith(mod + "/") else mod + "/" + name
    _, graph = _observed_parent_field(item, "parentSourceGraph")
    _, shoot = _observed_parent_field(item, "shoot")
    source = runtime_item_lookup(identity, expected_full_name=full_name,
        expected_modules=graph.get("modules") if isinstance(graph, dict) else None, expected_shoot=shoot)
    if not source:
        return item
    provenance = copy.deepcopy(source.get("runtimeDumpProvenance", {}))
    if source.get("unavailable") is True:
        # Refusal is observable at the lookup/startup diagnostic, not a new
        # property of a live parent that consumed no saved observation.
        return item
    added = [key for key in missing if key in source]
    if not added:
        return item
    out = dict(item)
    for key in added:
        out[key] = copy.deepcopy(source[key])
    provenance.update(fields=added, scope="saved_item_source_observations; not_current_player_state")
    if "directProjectileRaw" in added and isinstance(out["directProjectileRaw"], dict):
        direct_provenance = {key: copy.deepcopy(value) for key, value in provenance.items() if key != "fields"}
        out["directProjectileRaw"]["runtimeDumpProvenance"] = direct_provenance
        out["directProjectileRaw"]["fromRuntimeDump"] = True
    out["runtimeDumpItemProvenance"] = provenance
    return out

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
    observed, raw_direct = _observed_parent_field(item, "directProjectileRaw")
    if observed:
        if not isinstance(raw_direct, dict) or not raw_direct:
            return {}
        out = _strip_texture_metrics_for_llm(raw_direct)
        if isinstance(raw_direct.get("runtimeDumpProvenance"), dict):
            out.setdefault("fromRuntimeDump", True)
        else:
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
        graph = item_field(item, "parentSourceGraph", {})
        if not isinstance(graph, dict):
            graph = {}
        identity_context = {}
        full_name = item_field(item, "shootProjectileFullName", None)
        if full_name:
            identity_context["expected_full_name"] = full_name
        if graph.get("modules"):
            identity_context["expected_modules"] = graph["modules"]
        found = runtime_projectile_lookup(shoot, **identity_context)
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
    # A present request-local observation, even empty or unavailable, owns this
    # envelope. Never replace it with the fingerprint's player-free examples.
    missing = object()
    direct = dict_get_ci(item, "ammoRaw", missing)
    if direct is not missing:
        return direct if isinstance(direct, dict) else {}
    return _raw_section_dict(item, "ammoRaw")


def effective_projectile_profile_of(item: dict[str, Any]) -> dict[str, Any]:
    if generated_data_of(item):
        return {}
    observed, raw_effective = _observed_parent_field(item, "effectiveProjectileRaw")
    if observed:
        return _strip_texture_metrics_for_llm(raw_effective) if isinstance(raw_effective, dict) else {}
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
    # Native null means no explicit per-animation cap, not an unknown field.
    # Preserve a present request-local null instead of borrowing an older
    # fingerprint cap; packets from before this observation remain absent.
    for source in (item, fingerprint_of(item)):
        if "useLimitPerAnimation" in source:
            out["useLimitPerAnimation"] = copy.deepcopy(source["useLimitPerAnimation"])
            break
    # Literal source text/provenance is one observation: preserve line order,
    # whitespace, empty lines and source-bound refusal without compacting it.
    for key in ("tooltipLines", "tooltipSource", "nativeShootReference", "nativeContactHitStatusReference",
                "nativeEquipmentReference", "nativeEnvironmentReference", "nativeBuffEffectReference", "parentSourceGraph"):
        observed, value = _observed_parent_field(item, key)
        if observed and value is not None:
            out[key] = copy.deepcopy(value)
    if generated_data_of(item):
        for key in ("nativeEquipmentReference", "nativeEnvironmentReference", "parentSourceGraph"):
            out.pop(key, None)
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
    # Behavior is model context; certificates/instruction offsets remain in the
    # authoritative raw dump. No connected mechanic or branch is truncated.
    if isinstance(proj.get("attackReference"), dict):
        source = project_attack_behavior(proj["attackReference"])
        out["attackReference"] = pack_attack_tables(source)
    # The native producer owns verification and scope. Never infer a trajectory
    # from names/aiStyle or clip this optional read-only observation.
    if isinstance(proj.get("motionReference"), dict):
        out["motionReference"] = copy.deepcopy(proj["motionReference"])
    # Exact native producer certificate and its limitations travel together.
    # Item.buffType is a self-use buff, not this projectile's NPC-hit status.
    if isinstance(proj.get("onHitStatusReference"), dict):
        out["onHitStatusReference"] = copy.deepcopy(proj["onHitStatusReference"])
    if isinstance(proj.get("collisionReference"), dict):
        out["collisionReference"] = copy.deepcopy(proj["collisionReference"])
    if LLM_INCLUDE_AISTYLE_RAW and _compact_keep(proj.get("aiStyle")):
        out["aiStyle"] = _compact_raw_value(proj.get("aiStyle"))
    return out

def _compact_ammo_item_source(value: dict[str, Any]) -> dict[str, Any]:
    out = _select_raw_keys(value, LLM_AMMO_ITEM_KEYS)
    if isinstance(value.get("pickAmmoHookReference"), dict):
        out["pickAmmoHookReference"] = copy.deepcopy(value["pickAmmoHookReference"])
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
    if isinstance(ap.get("projectileSemanticsReference"), dict):
        # Native source proof and its unresolved hook scope are inseparable.
        # Ammo candidates remain inputs, not observed outgoing shots.
        out["projectileSemanticsReference"] = copy.deepcopy(ap["projectileSemanticsReference"])
    if isinstance(ap.get("candidateProjectileBindings"), list):
        out["candidateProjectileBindings"] = copy.deepcopy(ap["candidateProjectileBindings"])
    if isinstance(ap.get("playerInventoryObservation"), dict):
        out["playerInventoryObservation"] = copy.deepcopy(ap["playerInventoryObservation"])
    if isinstance(ap.get("ammoItemRaw"), dict):
        out["ammoItemRaw"] = _compact_ammo_item_source(ap["ammoItemRaw"])
    for key in ("projectileRaw", "weaponShootFieldProjectileRaw"):
        if isinstance(ap.get(key), dict):
            out[key] = compact_projectile_profile(ap[key])
    # These are already bounded observations from the native producer, not a
    # selected/best ammo or a replacement for the weapon's own shoot identity.
    # Keep order and multiplicity, and keep an observed empty inventory distinct
    # from an unavailable observation. Each entry retains source and slot.
    for key in ("playerInventoryAmmoRaw", "fallbackAmmoRaw"):
        if isinstance(ap.get(key), list):
            out[key] = [_compact_ammo_item_source(value)
                        for value in ap[key] if isinstance(value, dict)]
    for key in ("playerInventoryProjectileRaw", "fallbackProjectileRaw", "nativeReplacementProjectileRaw"):
        if isinstance(ap.get(key), list):
            out[key] = [compact_projectile_profile(value)
                        for value in ap[key] if isinstance(value, dict)]
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
        for key in ("nativeEquipmentReference", "nativeEnvironmentReference", "parentSourceGraph"):
            out.pop(key, None)
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
