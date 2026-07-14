from __future__ import annotations

import json
from typing import Any

from infini_local.core.item_identity_tools import (
    dict_get_ci,
    fingerprint_of,
    generated_data_of,
    item_field,
    name_of,
)
from infini_local.core.vfx_composition_primitives import (
    _vfx_available_roles,
    _vfx_words,
)
from infini_local.core.vfx_director_context import _vfx_director_tag_packet
from infini_local.core.vfx_director_contract import vfx_director_surface
from infini_local.core.vfx_manifest_config import (
    VFX_EFFECT_NAME_BANK_MAX_CARDS,
    VFX_EFFECT_NAME_BANK_MAX_NAMES,
    VFX_EFFECT_NAME_BANK_PATH,
    load_json_file,
)
from infini_local.core.vfx_projectile_profile import effective_projectile_profile_of
from infini_local.core.llm_stage_messages import agent_handoff, attributed_planner_messages, stage_chat_message


# AGENT MAP: optional LLM VFX Director prompt/name-bank helpers.
# Owns compact parent/child prompt payloads and debug-only effect name bank;
# validation/manifest compilation stays in vfx_manifest/vfx_director_contract.
# Public callers use infini_local.core.vfx_manifest.

VFX_DIRECTOR_SYSTEM = (
    "You are the VFX Director for a Terraria/tModLoader generated item. "
    "The latest user vfxInputPacket is the authoritative current item truth after validation, runtime repair, and visual authoring; any earlier item_planner response is provenance only. "
    "Return only one JSON object, with no markdown or reasoning. "
    "Use only the listed VFX surface enums and ranges, author concrete slot parameters, and never invent code names, gameplay, or extra top-level keys."
)

def get_vfx_effect_name_bank() -> dict[str, Any]:
    """Load the tiny VFX naming bank for the debug endpoint/documentation only.

    The optional LLM VFX Director no longer receives this bank; generated manifests
    are controlled only by canonical enum/range fields.
    """
    data = load_json_file(VFX_EFFECT_NAME_BANK_PATH, {})
    return data if isinstance(data, dict) else {}


def _vfx_text_for_name_bank(parent_a: dict[str, Any] | None, parent_b: dict[str, Any] | None, child_item: dict[str, Any] | None) -> str:
    parts: list[str] = []
    for item in (parent_a, parent_b, child_item):
        if not isinstance(item, dict):
            continue
        gd = generated_data_of(item)
        attack = dict_get_ci(gd, "attack", {}) if isinstance(gd, dict) else item.get("attack") if isinstance(item.get("attack"), dict) else {}
        visual = dict_get_ci(gd, "visual", {}) if isinstance(gd, dict) else item.get("visual") if isinstance(item.get("visual"), dict) else {}
        kit = item.get("visualKit") if isinstance(item.get("visualKit"), dict) else {}
        parts.extend([
            str(item.get("name") or ""),
            str(item.get("tooltip") or ""),
            str(dict_get_ci(attack, "pattern", "") or dict_get_ci(attack, "attackPattern", "")),
            str(dict_get_ci(attack, "toyIdentity", "")),
            str(dict_get_ci(attack, "projectileTrail", "")),
            str(dict_get_ci(attack, "projectileImpact", "")),
            str(dict_get_ci(attack, "visualAnimationPlan", "")),
            str(dict_get_ci(visual, "styleGuide", "") or kit.get("styleGuide", "")),
            str(dict_get_ci(visual, "projectileImagePrompt", "") or kit.get("projectileSpritePrompt", "")),
            str(dict_get_ci(visual, "impactImagePrompt", "") or kit.get("impactSpritePrompt", "")),
            " ".join(str(t) for t in (item.get("tags") or [])[:12]) if isinstance(item.get("tags"), list) else "",
        ])
    return "\n".join(x for x in parts if x)


def vfx_director_name_bank(parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None, child_item: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return compact VFX name cards for the debug endpoint/documentation only.

    These names are not passed to the optional LLM VFX Director and are never
    executable identifiers.
    """
    bank = get_vfx_effect_name_bank()
    cards = [c for c in (bank.get("cards") or []) if isinstance(c, dict)]
    if not cards:
        return {"note": "empty name bank", "cards": []}
    words = _vfx_words(_vfx_text_for_name_bank(parent_a, parent_b, child_item))
    scored: list[tuple[float, dict[str, Any]]] = []
    for idx, card in enumerate(cards):
        families = {str(x).lower() for x in (card.get("families") or [])}
        names = [str(x) for x in (card.get("names") or [])]
        card_words = _vfx_words(" ".join(list(families) + names))
        score = len(words & card_words) * 6.0 + (len(words & families) * 8.0)
        # Keep a little stable diversity even with sparse text.
        score += (idx % 3) * 0.05
        scored.append((score, card))
    scored.sort(key=lambda x: x[0], reverse=True)
    max_cards = max(1, VFX_EFFECT_NAME_BANK_MAX_CARDS)
    max_names = max(8, VFX_EFFECT_NAME_BANK_MAX_NAMES)
    selected = []
    used_names = 0
    for score, card in scored[:max_cards]:
        names = [str(x) for x in (card.get("names") or []) if str(x).strip()]
        if used_names + len(names) > max_names:
            names = names[:max(0, max_names - used_names)]
        if not names:
            continue
        used_names += len(names)
        selected.append({
            "id": str(card.get("id") or ""),
            "families": [str(x) for x in (card.get("families") or [])[:5]],
            "names": names,
            "runtimeBias": card.get("runtimeBias") if isinstance(card.get("runtimeBias"), dict) else {},
        })
        if used_names >= max_names:
            break
    return {
        "note": "Debug/documentation VFX vocabulary only. Not passed to the LLM VFX Director and not used as runtime enum values.",
        "sources": [s for s in (bank.get("sources") or [])[:4] if isinstance(s, dict)],
        "cards": selected,
    }


def _vfx_compact_item_for_director(item: dict[str, Any] | None) -> dict[str, Any]:
    item = item if isinstance(item, dict) else {}
    gd = generated_data_of(item)
    attack = dict_get_ci(gd, "attack", {}) if isinstance(gd, dict) else {}
    visual = dict_get_ci(gd, "visual", {}) if isinstance(gd, dict) else {}
    fp = fingerprint_of(item)
    tags_packet = _vfx_director_tag_packet(item)
    return {
        "name": name_of(item),
        "id": item.get("id"),
        "sourceMod": item.get("sourceMod") or fp.get("sourceMod"),
        "internalName": item.get("internalName") or fp.get("internalName"),
        "displayName": name_of(item),
        "fullName": item.get("fullName") or fp.get("fullName"),
        "damage": item_field(item, "damage", 0),
        "rare": item_field(item, "rare", item_field(item, "rarity", 0)),
        "useTime": item_field(item, "useTime", 0),
        "shoot": item_field(item, "shoot", 0),
        "shootSpeed": item_field(item, "shootSpeed", 0),
        "nameTokens": tags_packet["nameTokens"],
        "runtimeAutoFeatures": tags_packet["runtimeAutoFeatures"],
        "generatedAuthoredTags": tags_packet["generatedAuthoredTags"],
        "tagProvenance": tags_packet["tagProvenance"],
        "tagProvenanceNote": tags_packet["provenanceNote"],
        # Read-only convenience view of actually authored generated tags.  Python no
        # longer invents semantic tags from parent names/runtime facts.
        "tags": list(tags_packet["generatedAuthoredTags"])[:24],
        "projectileProfile": effective_projectile_profile_of(item),
        "parentVfxSignals": item.get("parentVfxSignals") or fp.get("parentVfxSignals"),
        "generatedAttack": {
            "enabled": bool(attack.get("enabled")) if isinstance(attack, dict) else False,
            "pattern": dict_get_ci(attack, "pattern", dict_get_ci(attack, "attackPattern", "")) if isinstance(attack, dict) else "",
            "toyIdentity": dict_get_ci(attack, "toyIdentity", "") if isinstance(attack, dict) else "",
            "projectileTrail": dict_get_ci(attack, "projectileTrail", "") if isinstance(attack, dict) else "",
            "projectileImpact": dict_get_ci(attack, "projectileImpact", "") if isinstance(attack, dict) else "",
        },
        "visual": {
            "palette": dict_get_ci(visual, "palette", []) if isinstance(visual, dict) else [],
            "projectilePrompt": dict_get_ci(visual, "projectileImagePrompt", "") if isinstance(visual, dict) else "",
            "impactPrompt": dict_get_ci(visual, "impactImagePrompt", "") if isinstance(visual, dict) else "",
            "childPrompt": dict_get_ci(visual, "childImagePrompt", "") if isinstance(visual, dict) else "",
            "fieldPrompt": dict_get_ci(visual, "fieldImagePrompt", "") if isinstance(visual, dict) else "",
        },
    }


def _vfx_compact_child_for_director(data: dict[str, Any]) -> dict[str, Any]:
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    kit = data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {}
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    return {
        "name": data.get("name"),
        "tooltip": data.get("tooltip"),
        "category": data.get("category"),
        "gameplay": {
            "damage": gameplay.get("damage"),
            "damageClass": gameplay.get("damageClass"),
            "useTime": gameplay.get("useTime"),
            "rarity": gameplay.get("rarity"),
            "stage": gameplay.get("stage"),
            "powerBudget": gameplay.get("powerBudget"),
        },
        "attack": {
            "enabled": attack.get("enabled"),
            "runtimeFamily": attack.get("runtimeFamily"),
            "delivery": attack.get("delivery"),
            "movement": attack.get("movement"),
            "effect": attack.get("effect"),
            "onHit": attack.get("onHit"),
            "pattern": attack.get("pattern") or attack.get("attackPattern"),
            "weaponFamily": attack.get("weaponFamily"),
            "projectileFamily": attack.get("projectileFamily"),
            "shotCount": attack.get("shotCount"),
            "spreadRadians": attack.get("spreadRadians"),
            "splitCount": attack.get("splitCount"),
            "secondaryTrigger": attack.get("secondaryTrigger"),
            "channelUse": attack.get("channelUse"),
            "beamWidthPx": attack.get("beamWidthPx"),
            "beamChargeTicks": attack.get("beamChargeTicks"),
            "chargeTicks": attack.get("chargeTicks"),
            "chargePowerMultiplier": attack.get("chargePowerMultiplier"),
            "sentryPlacement": attack.get("sentryPlacement"),
            "sentryAttackIntervalTicks": attack.get("sentryAttackIntervalTicks"),
            "sentryTargetRangeTiles": attack.get("sentryTargetRangeTiles"),
            "sentryLifetimeTicks": attack.get("sentryLifetimeTicks"),
            "immunityCooldown": attack.get("immunityCooldown"),
            "toyIdentity": attack.get("toyIdentity"),
            "specialRule": attack.get("specialRule"),
            "behaviorTimeline": attack.get("behaviorTimeline"),
            "projectileShape": attack.get("projectileShape"),
            "projectileMotion": attack.get("projectileMotion"),
            "projectileTrail": attack.get("projectileTrail"),
            "projectileImpact": attack.get("projectileImpact"),
            "projectileChild": attack.get("projectileChild"),
            "visualAnimationPlan": attack.get("visualAnimationPlan"),
        },
        "visual": {
            "styleGuide": kit.get("styleGuide") or visual.get("styleGuide"),
            "palette": kit.get("palette") or visual.get("palette"),
            "projectilePrompt": attack.get("projectileSpritePrompt") or kit.get("projectileSpritePrompt") or visual.get("projectileImagePrompt"),
            "impactPrompt": attack.get("impactSpritePrompt") or kit.get("impactSpritePrompt") or visual.get("impactImagePrompt"),
            "childPrompt": attack.get("childSpritePrompt") or kit.get("childSpritePrompt") or visual.get("childImagePrompt"),
            "fieldPrompt": attack.get("fieldSpritePrompt") or kit.get("fieldSpritePrompt") or visual.get("fieldImagePrompt"),
        },
        "availableRoles": sorted(_vfx_available_roles(data)),
    }


def build_vfx_director_prompt(parent_a: dict[str, Any] | None, parent_b: dict[str, Any] | None, child_item: dict[str, Any], vfx_surface: dict[str, Any] | None = None, constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the user payload for the optional LLM VFX Director pass.

    Keep this payload narrow: Gemma receives only the two parents, the child item,
    canonical VFX surface enums/ranges, constraints, and a field contract.
    """
    surface = vfx_surface or vfx_director_surface()
    parent_a_card = _vfx_compact_item_for_director(parent_a)
    parent_b_card = _vfx_compact_item_for_director(parent_b)
    child_card = _vfx_compact_child_for_director(child_item)
    packet = {
        "parentA": parent_a_card,
        "parentB": parent_b_card,
        "childItem": child_card,
        "provenanceContract": {
            "nameTokens": "tokens sent by C# GeneratorClient.NameTokens from internalName/displayName only",
            "runtimeAutoFeatures": "mechanical facts from C# AutoFeaturesFromItem / runtime fields",
            "generatedAuthoredTags": "only tags authored in generatedData for generated items",
            "tagProvenance": "per-tag source + matched text/fact; vanilla parents are not treated as hand-authored tagged items",
        },
    }
    return {
        "vfxInputPacket": packet,
        "runtimeTruthInstruction": "Use compiled runtimeFamily/delivery/movement/effect/onHit/secondaryTrigger/cadence to choose matching VFX events and exact rendererKind values. Do not infer gameplay from names or prose.",
        "parentA": parent_a_card,
        "parentB": parent_b_card,
        "childItem": child_card,
        "vfxSurface": surface,
        "constraints": constraints or {},
        "requiredJsonShape": {
            "type": "object",
            "requiredTopLevelFields": ["effectMagnitude", "visualBudgetClass", "slots"],
            "optionalTopLevelFields": ["identity"],
            "additionalTopLevelFields": "do not add keys outside this contract. Known forbidden fields are rejected; unknown extras are validation errors.",
            "topLevelContract": {
                "effectMagnitude": "float in vfxSurface.numericRanges.effectMagnitude",
                "visualBudgetClass": "one of tiny|small|normal|large|signature",
                "identity": "optional short debug note only; runtime must not parse it",
            },
            "slots": {
                "type": "array",
                "count": "between constraints.slots[0] and constraints.slots[1]",
                "additionalSlotFields": "do not add keys outside this contract. Known forbidden fields are rejected; unknown extras are validation errors.",
                "requiredSlotFields": [
                    "event", "rendererKind", "backend", "textureRole", "particleRole",
                    "anchor", "channel", "lane", "emissionMode", "blend", "particleSystemId",
                    "scale", "density", "duration", "alpha", "spread", "jitter",
                    "budgetWeight", "signatureWeight", "visualCost", "fadeIn", "fadeOut"
                ],
                "enumFields": {
                    "event": "one vfxSurface.events value",
                    "rendererKind": "one vfxSurface.rendererKind value",
                    "backend": "one vfxSurface.backend value",
                    "textureRole": "one vfxSurface.textureRole value",
                    "particleRole": "one vfxSurface.particleRole value",
                    "anchor": "one vfxSurface.anchor value",
                    "channel": "one vfxSurface.channel value",
                    "lane": "one vfxSurface.lane value",
                    "emissionMode": "one vfxSurface.emissionMode value",
                    "blend": "one vfxSurface.blend value",
                    "particleSystemId": "one explicit vfxSurface.particleSystemId value: pl:glow, pl:shard, pl:smoke, pl:spark, or dust",
                },
                "numericFields": {
                    "scale": "float in vfxSurface.numericRanges.scale",
                    "density": "float in vfxSurface.numericRanges.density",
                    "duration": "integer in vfxSurface.numericRanges.duration",
                    "alpha": "float in vfxSurface.numericRanges.alpha",
                    "spread": "float in vfxSurface.numericRanges.spread",
                    "jitter": "float in vfxSurface.numericRanges.jitter",
                    "phaseOffset": "optional float in vfxSurface.numericRanges.phaseOffset",
                    "budgetWeight": "float in vfxSurface.numericRanges.budgetWeight",
                    "signatureWeight": "float in vfxSurface.numericRanges.signatureWeight",
                    "visualCost": "float in vfxSurface.numericRanges.visualCost",
                    "fadeIn": "float in vfxSurface.numericRanges.fadeIn",
                    "fadeOut": "float in vfxSurface.numericRanges.fadeOut",
                    "startTick": "optional integer in vfxSurface.numericRanges.startTick",
                    "repeatEvery": "optional integer in vfxSurface.numericRanges.repeatEvery",
                },
            },
        },
    }


def build_vfx_director_handoff_payload(parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None, child_item: dict[str, Any] | None = None, vfx_surface: dict[str, Any] | None = None, constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the rich self-contained authoritative v3.1 dossier for the VFX pass."""
    surface = vfx_surface or vfx_director_surface()
    constraints = constraints or {}
    required_shape = build_vfx_director_prompt(None, None, {}, surface, constraints).get("requiredJsonShape", {})
    vfx_input_packet = build_vfx_director_prompt(parent_a, parent_b, child_item or {}, surface, constraints).get("vfxInputPacket", {})
    return {
        "task": "Continue from the generated item and author only its runtime VFX manifest.",
        "continuationMode": "No Planner transcript is replayed. vfxInputPacket is the authoritative current accepted item truth.",
        "agentHandoff": agent_handoff(
            previous_speaker="item_planner",
            current_speaker="pipeline_orchestrator",
            next_speaker="vfx_director",
            cause_by="vfx_manifest_authoring_stage",
            artifact_source="vfxInputPacket.childItem",
        ),
        "vfxInputPacket": vfx_input_packet,
        "rules": [
            "Return one JSON object; no markdown or reasoning.",
            "Do not redesign, rename, rebalance, or add gameplay mechanics.",
            "No unauthored glow, magic, energy, material effects, child motes, or fields.",
            "If no visible VFX was requested, return empty slots when allowed.",
            "Weak hints are optional; combine them with child concept, attack/visual fields, parent facts, and VFX surface; avoid same-hint repetition.",
            "Use only listed VFX enums/ranges.",
            "particleSystemId must be explicit: pl:glow, pl:shard, pl:smoke, pl:spark, or dust.",
            "Author concrete slot parameters only; Python validates enums/ranges/budget.",
            "No baked commands or engine code."
        ],
        "vfxSurface": surface,
        "constraints": constraints,
        "requiredJsonShape": required_shape,
    }


def _vfx_attributed_planner_history(child_item: dict[str, Any]) -> list[dict[str, str]] | None:
    """Read the canonical transient attributed Planner history from the child item."""
    if not isinstance(child_item, dict):
        return None
    return attributed_planner_messages(child_item.get("_llmHistory"))


def build_vfx_director_handoff_messages(child_item: dict[str, Any], parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None, vfx_surface: dict[str, Any] | None = None, constraints: dict[str, Any] | None = None) -> list[dict[str, str]] | None:
    """Build system + authoritative VFX dossier after validating live provenance."""
    history = _vfx_attributed_planner_history(child_item)
    if not history:
        return None
    instruction = build_vfx_director_handoff_payload(parent_a, parent_b, child_item, vfx_surface, constraints)
    return [
        stage_chat_message("system", "vfx_director_contract", VFX_DIRECTOR_SYSTEM),
        stage_chat_message(
            "user",
            "pipeline_orchestrator",
            json.dumps(instruction, ensure_ascii=False, separators=(",", ":")),
        ),
    ]

__all__ = [
    "get_vfx_effect_name_bank",
    "_vfx_text_for_name_bank",
    "vfx_director_name_bank",
    "_vfx_compact_item_for_director",
    "_vfx_compact_child_for_director",
    "build_vfx_director_prompt",
    "build_vfx_director_handoff_payload",
    "VFX_DIRECTOR_SYSTEM",
    "_vfx_attributed_planner_history",
    "build_vfx_director_handoff_messages",
]
