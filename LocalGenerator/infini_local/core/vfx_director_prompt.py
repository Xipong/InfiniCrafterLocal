from __future__ import annotations

import copy
import json
from typing import Any

from infini_local.core.boundary_models import VisualKitBoundary
from infini_local.core.item_identity_tools import (
    dict_get_ci,
    generated_data_of,
    item_field,
    name_of,
)
from infini_local.core.vfx_composition_primitives import (
    vfx_cue_particle_system_id_text,
    _vfx_available_roles,
    _vfx_words,
)
from infini_local.core.vfx_director_contract import (
    vfx_director_required_json_shape,
    vfx_director_surface,
)
from infini_local.core.vfx_manifest_config import (
    VFX_EFFECT_NAME_BANK_MAX_CARDS,
    VFX_EFFECT_NAME_BANK_MAX_NAMES,
    VFX_EFFECT_NAME_BANK_PATH,
    load_json_file,
)
from infini_local.core.vfx_projectile_profile import effective_projectile_profile_of
from infini_local.core.llm_stage_messages import agent_handoff, stage_chat_message


# AGENT MAP: optional LLM VFX Director prompt/name-bank helpers.
# Owns compact parent/child prompt payloads and debug-only effect name bank;
# validation/manifest compilation stays in vfx_manifest/vfx_director_contract.
# Public callers use infini_local.core.vfx_manifest.

VFX_DIRECTOR_SYSTEM = (
    "You are the VFX+Sound Director for a Terraria/tModLoader generated item. "
    "The latest user vfxInputPacket is the authoritative current item truth after validation and visual authoring. "
    "This request is self-contained; use only its accepted facts and VisualAssetKit. "
    "Return only one JSON object, with no markdown or reasoning. "
    "Use only the listed VFX surface enums and ranges, including soundCue slots where useful; "
    "obey vfxSurface.rendererRules as hard cross-field constraints and never substitute a lane value for a channel value; "
    "never invent code names, gameplay, or extra top-level keys."
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


def _accepted_visual_asset_kit(value: dict[str, Any]) -> dict[str, Any]:
    direct = value.get("visualKit")
    if not isinstance(direct, dict):
        generated = generated_data_of(value)
        direct = generated.get("visualKit") if isinstance(generated, dict) else {}
    kit: dict[str, Any] = direct if isinstance(direct, dict) else {}
    return {
        field: copy.deepcopy(kit[field])
        for field in VisualKitBoundary.model_fields
        if field in kit
    }


def _vfx_compact_item_for_director(item: dict[str, Any] | None) -> dict[str, Any]:
    """Clean parent facts only: no tag/classifier/debug/provenance packets."""
    item = item if isinstance(item, dict) else {}
    generated = generated_data_of(item)
    generated = generated if isinstance(generated, dict) else {}
    attack = dict_get_ci(generated, "attack", {})
    attack = attack if isinstance(attack, dict) else {}
    visual = dict_get_ci(generated, "visual", {})
    visual = visual if isinstance(visual, dict) else {}
    source_identity = {
        key: copy.deepcopy(value)
        for key, value in {
            "id": item.get("id"),
            "sourceMod": item.get("sourceMod"),
            "internalName": item.get("internalName"),
            "fullName": item.get("fullName"),
        }.items()
        if value not in (None, "", [], {})
    }
    physical_facts = {
        key: copy.deepcopy(value)
        for key, value in {
            "damage": item_field(item, "damage", 0),
            "damageClass": item_field(item, "damageClass", ""),
            "rare": item_field(item, "rare", item_field(item, "rarity", 0)),
            "useTime": item_field(item, "useTime", 0),
            "useStyle": item_field(item, "useStyle", 0),
            "shoot": item_field(item, "shoot", 0),
            "shootSpeed": item_field(item, "shootSpeed", 0),
            "material": item_field(item, "material", False),
            "createTile": item_field(item, "createTile", -1),
            "createWall": item_field(item, "createWall", -1),
            "accessory": item_field(item, "accessory", False),
            "defense": item_field(item, "defense", 0),
        }.items()
        if value not in (None, "", [], {})
    }
    accepted_attack_fields = (
        "enabled", "runtimeFamily", "delivery", "movement", "effect", "onHit",
        "pattern", "attackPattern", "projectileShape", "projectileMotion",
        "projectileTrail", "projectileImpact", "secondaryTrigger",
        "soundUseCatalogId", "soundImpactCatalogId",
    )
    accepted_attack = {
        field: copy.deepcopy(dict_get_ci(attack, field, None))
        for field in accepted_attack_fields
        if dict_get_ci(attack, field, None) not in (None, "", [], {})
    }
    kit = _accepted_visual_asset_kit(generated or item)
    legacy_visual = {
        key: copy.deepcopy(dict_get_ci(visual, key, None))
        for key in (
            "palette", "styleGuide", "itemSilhouetteContract", "silhouetteSummary",
            "imagePrompt", "projectileImagePrompt", "impactImagePrompt",
            "childImagePrompt", "fieldImagePrompt",
        )
        if dict_get_ci(visual, key, None) not in (None, "", [], {})
    }
    raw_projectile_profile = effective_projectile_profile_of(item)
    projectile_profile_fields = (
        "type", "width", "height", "aiStyle", "timeLeft", "penetrate",
        "extraUpdates", "light", "scale", "alpha", "tileCollide", "ignoreWater",
        "friendly", "hostile", "minion", "sentry", "minionSlots",
        "usesLocalNPCImmunity", "localNPCHitCooldown",
        "usesIDStaticNPCImmunity", "idStaticNPCHitCooldown",
    )
    projectile_profile = {
        field: copy.deepcopy(raw_projectile_profile[field])
        for field in projectile_profile_fields
        if raw_projectile_profile.get(field) not in (None, "", [], {})
        and isinstance(raw_projectile_profile.get(field), (str, int, float, bool))
    }
    card: dict[str, Any] = {
        "name": name_of(item),
        "sourceIdentity": source_identity,
        "physicalFacts": physical_facts,
    }
    if projectile_profile:
        card["projectileProfile"] = projectile_profile
    if accepted_attack:
        card["acceptedAttackFacts"] = accepted_attack
    if kit:
        card["acceptedVisualAssetKit"] = kit
    elif legacy_visual:
        card["acceptedVisualFacts"] = legacy_visual
    return card


def _vfx_compact_child_for_director(data: dict[str, Any]) -> dict[str, Any]:
    """Self-contained accepted product context plus the full canonical VisualAssetKit."""
    attack_candidate = data.get("attack")
    attack: dict[str, Any] = attack_candidate if isinstance(attack_candidate, dict) else {}
    gameplay_candidate = data.get("gameplay")
    gameplay: dict[str, Any] = gameplay_candidate if isinstance(gameplay_candidate, dict) else {}
    concept_candidate = data.get("concept")
    concept: dict[str, Any] = concept_candidate if isinstance(concept_candidate, dict) else {}
    runtime_contract_candidate = data.get("runtimeContract")
    runtime_contract: dict[str, Any] = (
        runtime_contract_candidate if isinstance(runtime_contract_candidate, dict) else {}
    )
    attack_fields = (
        "enabled", "runtimeFamily", "delivery", "movement", "effect", "onHit",
        "pattern", "attackPattern", "weaponFamily", "projectileFamily", "ammoKind",
        "shotCount", "spreadRadians", "pierce", "aoeRadiusTiles", "splitCount",
        "chainCount", "secondaryTrigger", "secondaryDamageMultiplier",
        "secondaryLifetimeTicks", "channelUse", "useTimeTicks", "useAnimationTicks",
        "lifetimeTicks", "extraUpdates", "speed", "rangeTiles", "beamWidthPx",
        "beamChargeTicks", "chargeTicks", "chargePowerMultiplier", "delayTicks",
        "sentryPlacement", "sentryAttackIntervalTicks", "sentryTargetRangeTiles",
        "sentryLifetimeTicks", "immunityCooldown", "projectileShape",
        "projectileMotion", "projectileTrail", "projectileImpact", "projectileChild",
        "secondaryProjectileShape", "secondaryMaterial", "visualAnimationPlan",
    )
    attack_facts = {
        field: copy.deepcopy(attack[field])
        for field in attack_fields
        if attack.get(field) not in (None, "", [], {})
    }
    audio_fields = (
        "soundUseCatalogId", "soundImpactCatalogId", "soundVolume", "soundPitch",
        "soundPitchVariance",
    )
    audio_facts = {
        field: copy.deepcopy(attack[field])
        for field in audio_fields
        if attack.get(field) not in (None, "", [], {})
    }
    runtime_contract_fields = (
        "primaryVerb", "controlStyle", "playerViewTimeline",
    )
    accepted_runtime_contract = {
        field: copy.deepcopy(runtime_contract[field])
        for field in runtime_contract_fields
        if runtime_contract.get(field) not in (None, "", [], {})
    }
    gameplay_fields = (
        "kind", "damageClass", "damage", "knockback", "crit", "defense",
        "useTime", "useTimeTicks", "useAnimation", "useAnimationTicks", "mana",
        "rarity", "value", "maxStack", "craftYield", "consumable", "autoReuse",
        "channel", "healLife", "healMana", "buffType", "buffTime", "pick",
        "axe", "hammer", "shootSpeed", "powerBudget", "mobilityMode",
        "mobilityRangeTiles", "mobilityCooldownTicks",
    )
    gameplay_facts = {
        field: copy.deepcopy(gameplay[field])
        for field in gameplay_fields
        if gameplay.get(field) not in (None, "", [], {})
    }
    return {
        "name": data.get("name"),
        "tooltip": data.get("tooltip"),
        "category": data.get("category"),
        "acceptedConcept": copy.deepcopy(concept),
        "acceptedRuntimeContract": accepted_runtime_contract,
        "gameplayFacts": gameplay_facts,
        "attackFacts": attack_facts,
        "audioFacts": audio_facts,
        "visualAssetKit": _accepted_visual_asset_kit(data),
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
    packet: dict[str, Any] = {
        "parentA": parent_a_card,
        "parentB": parent_b_card,
        "childItem": child_card,
    }
    return {
        "vfxInputPacket": packet,
        "runtimeTruthInstruction": (
            "Use accepted runtimeFamily/delivery/movement/effect/onHit/secondaryTrigger/cadence "
            "and VisualAssetKit to choose VFX+sound events and exact rendererKind values. "
            "soundCue slots use the accepted audioFacts catalog IDs at runtime."
        ),
        "vfxSurface": surface,
        "constraints": constraints or {},
        "requiredJsonShape": vfx_director_required_json_shape(),
    }


def build_vfx_director_handoff_payload(parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None, child_item: dict[str, Any] | None = None, vfx_surface: dict[str, Any] | None = None, constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the rich self-contained authoritative v3.1 dossier for the VFX pass."""
    surface = vfx_surface or vfx_director_surface()
    constraints = constraints or {}
    required_shape = build_vfx_director_prompt(None, None, {}, surface, constraints).get("requiredJsonShape", {})
    vfx_input_packet = build_vfx_director_prompt(parent_a, parent_b, child_item or {}, surface, constraints).get("vfxInputPacket", {})
    return {
        "task": "Continue from the accepted generated item and author only its runtime VFX+sound manifest.",
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
            "Use accepted child concept, gameplay/attack/audio facts, full VisualAssetKit, clean parent facts, and VFX surface.",
            "Use soundCue slots for useful travel/impact/kill audio timing; runtime resolves accepted audioFacts catalog IDs.",
            "Use only listed VFX enums/ranges.",
            "particleSystemId must be explicit: "
            + vfx_cue_particle_system_id_text()
            + ".",
            "Author concrete slot parameters only; Python validates enums/ranges/budget.",
            "No baked commands or engine code."
        ],
        "vfxSurface": surface,
        "constraints": constraints,
        "requiredJsonShape": required_shape,
    }


def build_vfx_director_handoff_messages(child_item: dict[str, Any], parent_a: dict[str, Any] | None = None, parent_b: dict[str, Any] | None = None, vfx_surface: dict[str, Any] | None = None, constraints: dict[str, Any] | None = None) -> list[dict[str, str]] | None:
    """Build a self-contained system + accepted-product VFX dossier."""
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
    "build_vfx_director_handoff_messages",
]
