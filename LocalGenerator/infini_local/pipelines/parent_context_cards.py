from __future__ import annotations

from typing import Any

from infini_local.pipelines.parent_context_pipeline import (
    _compact_keep,
    _compact_raw_value,
    _dedupe_projectile_profile,
    _fishing_bait_semantics_for_llm,
    _placeable_consumption_semantics_for_llm,
    _projectile_semantics_for_llm,
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
# while preserving its legacy import surface.

def raw_parent_card_for_llm(item: dict[str, Any]) -> dict[str, Any]:
    """Compact parent card for the LLM.

    The raw section keeps factual item/projectile fields.  A tiny semantics section may
    clarify Terraria flag meaning when a raw flag is commonly overloaded (for example,
    placeable consumable stacks). It is explanatory context, not a hidden router.
    """
    item_raw = compact_item_raw_for_llm(item)
    cross_mod_identity = {
        "sourceMod": str(item_field(item, "sourceMod", "Terraria")),
        "fullName": str(item_field(item, "fullName", "")),
        "damageClassFullName": str(item_field(item, "damageClassFullName", "")),
        "shootProjectileFullName": str(item_field(item, "shootProjectileFullName", "")),
        "createTile": item.get("createTile"),
        "createWall": item.get("createWall"),
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
    semantics = _placeable_consumption_semantics_for_llm(item, item_raw)
    if semantics:
        card["semantics"] = semantics
    fishing_semantics = _fishing_bait_semantics_for_llm(item, item_raw)
    if fishing_semantics:
        sem = card.setdefault("semantics", {})
        if isinstance(sem, dict):
            sem["fishingBaitSemantics"] = fishing_semantics
    vanilla_flags = compact_vanilla_flags_for_llm(item)
    if vanilla_flags:
        card["raw"]["vanillaFlags"] = vanilla_flags
    direct = compact_projectile_profile(projectile_profile_of(item))
    effective = compact_projectile_profile(effective_projectile_profile_of(item))
    ammo = compact_ammo_profile(item)
    if direct:
        card["raw"]["directProjectile"] = direct
    if effective:
        card["raw"]["effectiveProjectile"] = effective
    projectile_semantics = _projectile_semantics_for_llm(effective if effective and "sameAs" not in effective else direct)
    if projectile_semantics:
        sem = card.setdefault("semantics", {})
        if isinstance(sem, dict):
            sem["projectileSemantics"] = projectile_semantics
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
    gd = generated_data_of(item)
    if isinstance(gd, dict) and gd:
        attack_raw = dict_get_ci(gd, "attack", {})
        gameplay_raw = dict_get_ci(gd, "gameplay", {})
        summary_raw = dict_get_ci(gd, "generatedParentSummary", {})
        attack = attack_raw if isinstance(attack_raw, dict) else {}
        gameplay = gameplay_raw if isinstance(gameplay_raw, dict) else {}
        summary = summary_raw if isinstance(summary_raw, dict) else {}
        accessory_raw = dict_get_ci(gd, "accessory", {})
        accessory = accessory_raw if isinstance(accessory_raw, dict) else {}
        generated_parent = {
            "gameplay": {k: gameplay.get(k) for k in ("kind", "damageClass", "damage", "knockback", "useTime", "useAnimation", "useStyle", "autoReuse", "useTurn", "channelUse", "itemScale", "holdoutOffsetX", "holdoutOffsetY", "manaCost", "healLife", "healMana", "buffCode", "buffTime", "maxStack", "consumable", "consumeChancePercent", "ammoFor", "pickPower", "axePower", "hammerPower", "mobilityMode", "altUseMode", "holdLightStrength", "extractinatorOutputItemType", "extractinatorOutputStack", "useConditionMode", "craftYield", "rarity", "value", "stage", "runtimeOutputKind") if k in gameplay},
            "accessory": {k: accessory.get(k) for k in ("enabled", "archetype", "defense", "maxLife", "maxMana", "lifeRegen", "manaRegen", "movementSpeed", "maxRunSpeed", "jumpSpeed", "genericDamage", "meleeDamage", "rangedDamage", "magicDamage", "summonDamage", "genericCrit", "attackSpeed", "knockback", "fallDamageImmune", "lavaImmune", "waterWalk", "minionSlots", "lightStrength", "lightColorName") if k in accessory},
            "attack": {k: attack.get(k) for k in ("enabled", "runtimePlanAuthored", "runtimeFamily", "delivery", "weaponFamily", "projectileFamily", "ammoKind", "movement", "effect", "onHit", "shotCount", "pierce", "splitCount", "chainCount", "speed", "lifetime", "rangeTiles", "projectileShape", "projectileMotion", "projectileTrail", "projectileImpact", "mobilityMode") if k in attack},
        }
        if summary:
            generated_parent["summary"] = {k: summary.get(k) for k in ("name", "fantasy", "category", "damageClass", "runtime", "visualIdentity", "notableEffects") if _compact_keep(summary.get(k))}
        card["raw"]["generatedParent"] = generated_parent
    # Do not send section bookkeeping or token-byte metadata to the LLM; the raw object keys are enough.
    return {k: v for k, v in card.items() if _compact_keep(v)}

__all__ = ["raw_parent_card_for_llm"]
