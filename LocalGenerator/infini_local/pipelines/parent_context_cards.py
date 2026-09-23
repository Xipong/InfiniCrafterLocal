from __future__ import annotations

import copy
from typing import Any

from infini_local.pipelines.parent_context_pipeline import (
    _compact_keep,
    _compact_raw_value,
    _dedupe_projectile_profile,
    _raw_section_dict,
    compact_ammo_profile,
    compact_item_raw_for_llm,
    compact_projectile_profile,
    compact_vanilla_flags_for_llm,
    dict_get_ci,
    effective_projectile_profile_of,
    generated_data_of,
    item_field,
    name_of,
    projectile_profile_of,
)

# AGENT MAP: LLM raw parent card assembly. Kept separate from parent projectile
# profile extraction so parent_context_pipeline.py can stay below the large-file cap
# while keeping the card itself in this single owner module.

_FORBIDDEN_DERIVED_PACKET_KEYS = frozenset({
    "behaviorDigest", "mechanicalHint", "semantics",
    "canonical", "tags", "headNoun", "primaryCategory", "classifier", "class",
    "hardTags", "softTags", "shapeAnchors", "visualAnchors", "modifiers",
})


def _strip_derived_packet_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_derived_packet_fields(item)
            for key, item in value.items()
            if key not in _FORBIDDEN_DERIVED_PACKET_KEYS
        }
    if isinstance(value, list):
        return [_strip_derived_packet_fields(item) for item in value]
    return value

def raw_parent_card_for_llm(item: dict[str, Any]) -> dict[str, Any]:
    """Compact parent card for the LLM.

    The packet contains raw source fields or exact accepted generated runtime facts.
    It never adds code-derived semantics, behavior digests, categories or tags.
    """
    item_raw = compact_item_raw_for_llm(item)
    cross_mod_identity = {
        "sourceMod": str(item_field(item, "sourceMod", "Terraria")),
        "fullName": str(item_field(item, "fullName", "")),
        "shootProjectileFullName": str(item_field(item, "shootProjectileFullName", "")),
    }
    cross_mod_identity = {k: v for k, v in cross_mod_identity.items() if _compact_keep(v)}
    card: dict[str, Any] = {
        "name": name_of(item),
        "internalName": str(item_field(item, "internalName", "")),
        "sourceMod": str(item_field(item, "sourceMod", "Terraria")),
        "raw": {"item": item_raw},
    }
    if cross_mod_identity:
        card["raw"]["crossModIdentity"] = cross_mod_identity
    vanilla_flags = compact_vanilla_flags_for_llm(item)
    if vanilla_flags:
        card["raw"]["vanillaFlags"] = vanilla_flags
    gd = generated_data_of(item)
    direct: dict[str, Any] = {}
    effective: dict[str, Any] = {}
    ammo: dict[str, Any] = {}
    if not gd:
        direct = compact_projectile_profile(projectile_profile_of(item))
        effective = compact_projectile_profile(effective_projectile_profile_of(item))
        direct.pop("behaviorDigest", None)
        effective.pop("behaviorDigest", None)
        ammo = compact_ammo_profile(item)
    if direct:
        card["raw"]["directProjectile"] = direct
    if effective:
        card["raw"]["effectiveProjectile"] = effective

    if ammo:
        # v0.4.49: do not feed fallback/player-inventory ammo examples to the LLM.
        # They are useful debug context, but small models confuse them with parent identity.
        for noisy_key in [
            "fallbackAmmoRaw", "fallbackProjectileRaw", "representativeAmmoRaw", "representativeProjectileRaw",
            "playerInventoryAmmoRaw", "playerInventoryProjectileRaw", "exampleAmmo", "exampleProjectile",
        ]:
            ammo.pop(noisy_key, None)
        if direct:
            _dedupe_projectile_profile(card["raw"], "effectiveProjectile", "directProjectile", direct)
            _dedupe_projectile_profile(ammo, "projectileRaw", "directProjectile", direct)
            _dedupe_projectile_profile(ammo, "weaponShootFieldProjectileRaw", "directProjectile", direct)
        elif effective:
            _dedupe_projectile_profile(ammo, "projectileRaw", "effectiveProjectile", effective)
            _dedupe_projectile_profile(ammo, "weaponShootFieldProjectileRaw", "effectiveProjectile", effective)
        if ammo:
            card["raw"]["ammo"] = ammo
    elif direct:
        _dedupe_projectile_profile(card["raw"], "effectiveProjectile", "directProjectile", direct)
    runtime_probe = _raw_section_dict(item, "runtimeProbeRaw")
    if runtime_probe:
        card["raw"]["runtimeProbe"] = _compact_raw_value(runtime_probe)
    if isinstance(gd, dict) and gd:
        gameplay_raw = dict_get_ci(gd, "gameplay", {})
        runtime_raw = dict_get_ci(gd, "runtimeProgram", {})
        summary_raw = dict_get_ci(gd, "generatedParentSummary", {})
        gameplay = gameplay_raw if isinstance(gameplay_raw, dict) else {}
        runtime = runtime_raw if isinstance(runtime_raw, dict) else {}
        summary = summary_raw if isinstance(summary_raw, dict) else {}
        entities = []
        for row in runtime.get("entities") or []:
            if not isinstance(row, dict):
                continue
            entity_fact = {
                "id": row.get("id"),
                "kind": row.get("kind"),
                "visualRole": row.get("visualRole"),
                "spawn": row.get("spawn") if isinstance(row.get("spawn"), dict) else None,
                "damage": row.get("damage") if isinstance(row.get("damage"), dict) else None,
                "lifetimeTicks": row.get("lifetimeTicks"),
                "hitbox": row.get("hitbox") if isinstance(row.get("hitbox"), dict) else None,
                "collision": row.get("collision") if isinstance(row.get("collision"), dict) else None,
                "movement": row.get("movement") if isinstance(row.get("movement"), dict) else None,
                "controller": row.get("controller") if isinstance(row.get("controller"), dict) else None,
                "targeting": row.get("targeting") if isinstance(row.get("targeting"), dict) else None,
                "light": row.get("light") if isinstance(row.get("light"), dict) else None,
                "events": [
                    {key: event.get(key) for key in (
                        "id", "event", "action", "entityId", "count", "spreadRadians", "damageMultiplier",
                        "delayTicks", "periodTicks", "buffId", "durationTicks", "radiusPx", "rangeTiles", "mode",
                        "strength", "radiusTiles", "damageFraction", "maxHeal", "cooldownTicks", "safeTileOnly",
                    ) if key in event}
                    for event in row.get("events") or [] if isinstance(event, dict)
                ],
            }
            entities.append({key: value for key, value in entity_fact.items() if value not in (None, "", [], {})})
        generated_parent = {
            "gameplay": {key: gameplay.get(key) for key in (
                "kind", "damageClass", "damage", "knockback", "useTime", "useAnimation", "useStyleName",
                "autoReuse", "useTurn", "manaCost", "healLife", "healMana", "potion", "maxStack",
                "ammoCategory", "ammoProjectileId", "ammoShootSpeedPxPerTick", "notAmmo", "pickPower", "axePower", "hammerPower", "craftYield", "rarity", "value",
            ) if key in gameplay},
            "runtimeProgram": {
                "apiVersion": runtime.get("apiVersion"),
                "schema": runtime.get("schema"),
                "itemEntityId": runtime.get("itemEntityId"),
                "entities": entities,
                "bindings": [
                    {
                        "input": row.get("input"),
                        "usePolicy": copy.deepcopy(row.get("usePolicy")),
                    }
                    for row in runtime.get("bindings") or [] if isinstance(row, dict)
                ],
            },
        }
        if summary:
            generated_parent["summary"] = {key: copy.deepcopy(summary.get(key)) for key in (
                "schema", "name", "identity", "description", "playerExperience", "notableEffects",
                "runtimePrimaryEntityId", "runtimeEntityIds",
            ) if _compact_keep(summary.get(key))}
        card["raw"]["generatedParent"] = generated_parent
    # Do not send section bookkeeping or token-byte metadata to the LLM; the raw object keys are enough.
    return _strip_derived_packet_fields({k: v for k, v in card.items() if _compact_keep(v)})

__all__ = ["raw_parent_card_for_llm"]
