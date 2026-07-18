from __future__ import annotations

import json
from typing import Any

from infini_local.pipelines.result_identity_policy import normalize_category
from infini_local.pipelines.visual_prompt_contracts import compact_visual_words


# AGENT MAP: generated-parent summary serialization shared by direct consumers.
# Keep this as read-only summary/debug shaping; no gameplay
# authoring or validation belongs here.


def generated_parent_summary_from_data(data: dict[str, Any]) -> dict[str, Any]:
    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    accessory = data.get("accessory") if isinstance(data.get("accessory"), dict) else {}
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    effects: list[str] = []
    for value in [attack.get("effect"), attack.get("onHit"), attack.get("movement"), attack.get("trailStyle"), attack.get("impactStyle")]:
        text = str(value or "").strip()
        if text and text.lower() not in {"none", "dust", "small_flash", "straight"}:
            effects.append(text[:64])
    gb = gameplay.get("generatedBuff") if isinstance(gameplay.get("generatedBuff"), dict) else {}
    if gb:
        if float(gb.get("miningSpeedMultiplier") or 1) != 1:
            effects.append("generated buff: mining speed")
        if float(gb.get("emitLightStrength") or 0) > 0:
            effects.append("generated buff: light")
        if int(gb.get("oreSenseRadiusTiles") or 0) > 0:
            effects.append("generated buff: ore sense")
        if float(gb.get("movementSpeed") or 0) != 0 or float(gb.get("jumpBoost") or 0) > 0:
            effects.append("generated buff: mobility stats")
        if int(gb.get("manaRegen") or 0) > 0 or int(gb.get("lifeRegen") or 0) > 0:
            effects.append("generated buff: regeneration")
    mobility = str(gameplay.get("mobilityMode") or "").strip()
    if mobility:
        effects.append("mobility: " + mobility[:48])

    if int(gameplay.get("consumeChancePercent") or 100) < 100:
        effects.append("custom consume chance")

    if gameplay.get("rejectedEngineCalls"):
        effects.append("rejected unsupported calls")
    try:
        vanilla_hitbox_damage = (
            int(float(gameplay.get("damage") or 0)) > 0
            and int(float(gameplay.get("useStyle") or 0)) > 0
            and normalize_category(data.get("category") or gameplay.get("kind") or "generic") not in {"ammo", "accessory", "material", "furniture"}
            and not (bool(attack.get("enabled")) and bool(attack.get("disableItemMeleeHitbox")))
        )
    except Exception:
        vanilla_hitbox_damage = False
    if vanilla_hitbox_damage and not attack.get("enabled"):
        effects.append("vanilla item/tool hitbox")
    if accessory.get("enabled"):
        acc_parts = []
        if int(accessory.get("defense") or 0) > 0: acc_parts.append("defense")
        if float(accessory.get("movementSpeed") or 0) > 0 or float(accessory.get("jumpSpeed") or 0) > 0: acc_parts.append("mobility")
        if float(accessory.get("genericDamage") or 0) > 0 or float(accessory.get("meleeDamage") or 0) > 0 or float(accessory.get("rangedDamage") or 0) > 0 or float(accessory.get("magicDamage") or 0) > 0 or float(accessory.get("summonDamage") or 0) > 0: acc_parts.append("damage")
        if float(accessory.get("lightStrength") or 0) > 0: acc_parts.append("light")
        if int(accessory.get("minionSlots") or 0) > 0: acc_parts.append("minion slots")
        effects.append("accessory" + (": " + ", ".join(acc_parts[:4]) if acc_parts else ""))
    return {
        "name": str(data.get("name") or "")[:80],
        "fantasy": compact_visual_words(concept.get("fantasy") or data.get("tooltip") or data.get("name"), 180),
        "category": normalize_category(data.get("category") or gameplay.get("kind") or "generic"),
        "damageClass": str(gameplay.get("damageClass") or "generic")[:32],
        "runtime": (
            str(attack.get("runtimeFamily") or "")[:32]
            if attack.get("enabled")
            else "vanilla_item_hitbox" if vanilla_hitbox_damage
            else "none"
        ),
        "customAttackEnabled": bool(attack.get("enabled")),
        "vanillaItemHitboxDamage": bool(vanilla_hitbox_damage),
        "visualIdentity": compact_visual_words(visual.get("imagePrompt") or concept.get("visualIdentity") or data.get("name"), 180),
        "notableEffects": list(dict.fromkeys(effects))[:8],
    }


def attach_generated_parent_summary(data: dict[str, Any]) -> dict[str, Any]:
    data["generatedParentSummary"] = generated_parent_summary_from_data(data)
    data.setdefault("debug", {})["generatedParentSummary"] = json.dumps(data["generatedParentSummary"], ensure_ascii=False)
    return data


__all__ = [
    "generated_parent_summary_from_data",
    "attach_generated_parent_summary",
]
