from __future__ import annotations

import copy
from typing import Any

from infini_local.core.boundary_models import VisualKitBoundary
from infini_local.core.item_identity_tools import generated_data_of, item_field, name_of


# AGENT MAP: pure Visual Director input/output contract.
# This module packages facts and validates shape/usefulness only. It must not decide
# how parent items are fused, which materials should dominate, or what the final
# object ought to look like.

_PARENT_RAW_VISUAL_KEYS = (
    "internalName",
    "fullName",
    "sourceMod",
    "material",
    "createTile",
    "createWall",
    "placeStyle",
    "maxStack",
    "damage",
    "damageClass",
    "useStyle",
    "shoot",
    "accessory",
    "defense",
    "pickPower",
    "axePower",
    "hammerPower",
)

_VISUAL_CONTEXT_KEYS = (
    "imagePrompt",
    "itemPrompt",
    "projectilePrompt",
    "impactPrompt",
    "notes",
    "projectileImagePrompt",
    "projectilePrompt",
    "impactImagePrompt",
    "impactPrompt",
    "childImagePrompt",
    "fieldImagePrompt",
    "itemSilhouetteContract",
    "silhouetteSummary",
    "palette",
    "requiredAnchors",
)

_VISUAL_DIRECTOR_ROLE_FIELDS = {
    "item": {
        "promptField": "itemIconPrompt",
        "assetDecision": "the item icon is always the required generated inventory/held sprite",
        "requiredWhen": "always",
    },
    "projectile": {
        "promptField": "projectileSpritePrompt",
        "assetModeField": "bakedAssets.projectile.mode",
        "requiredWhen": "the role is visually relevant; a non-empty prompt is mandatory when mode=baked_sprite",
    },
    "impact": {
        "promptField": "impactSpritePrompt",
        "assetModeField": "bakedAssets.impact.mode",
        "requiredWhen": "the role is visually relevant; a non-empty prompt is mandatory when mode=baked_sprite",
    },
    "child": {
        "promptField": "childSpritePrompt",
        "assetModeField": "bakedAssets.child.mode",
        "requiredWhen": "the accepted runtime has a child role; a non-empty prompt is mandatory when mode=baked_sprite",
    },
    "field": {
        "promptField": "fieldSpritePrompt",
        "assetModeField": "bakedAssets.field.mode",
        "requiredWhen": "the accepted runtime has a field role; a non-empty prompt is mandatory when mode=baked_sprite",
    },
}


def _nonempty(value: Any) -> bool:
    if value in (None, "", [], {}):
        return False
    return True


def _bounded_visual_value(value: Any, *, text_limit: int = 900, list_limit: int = 12) -> Any:
    """Bound context size without interpreting or rewriting authored meaning."""
    if isinstance(value, str):
        return value[:text_limit]
    if isinstance(value, list):
        return [
            _bounded_visual_value(item, text_limit=text_limit, list_limit=list_limit)
            for item in value[:list_limit]
        ]
    if isinstance(value, dict):
        return {
            str(key): _bounded_visual_value(item, text_limit=text_limit, list_limit=list_limit)
            for key, item in list(value.items())[:list_limit]
        }
    return copy.deepcopy(value)


def compact_visual_parent_card(item: dict[str, Any], canonical: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return bounded source facts without interpreting the parent's design.

    Raw Terraria fields and previously authored generated-parent visual data are
    evidence. No tag router, material priority, silhouette conversion, or fusion
    recommendation is added here.
    """
    raw: dict[str, Any] = {}
    for key in _PARENT_RAW_VISUAL_KEYS:
        value = item_field(item, key, None)
        if _nonempty(value):
            raw[key] = value

    card: dict[str, Any] = {
        "name": name_of(item),
        "rawFacts": raw,
    }
    canonical = canonical if isinstance(canonical, dict) else {}
    canonical_facts = {
        key: _bounded_visual_value(canonical.get(key))
        for key in (
            "category", "sourceMod", "internalName",
        )
        if _nonempty(canonical.get(key))
    }
    if canonical_facts:
        card["canonicalFacts"] = canonical_facts

    generated = generated_data_of(item)
    if isinstance(generated, dict) and generated:
        authored_visual = generated.get("visual") if isinstance(generated.get("visual"), dict) else {}
        visual_context = {
            key: _bounded_visual_value(authored_visual.get(key))
            for key in _VISUAL_CONTEXT_KEYS
            if _nonempty(authored_visual.get(key))
        }
        visual_kit_candidate = generated.get("visualKit")
        visual_kit: dict[str, Any] = (
            visual_kit_candidate if isinstance(visual_kit_candidate, dict) else {}
        )
        accepted_visual_kit = {
            field: _bounded_visual_value(visual_kit[field])
            for field in VisualKitBoundary.model_fields
            if field in visual_kit
        }
        if accepted_visual_kit:
            card["previouslyAcceptedVisualAssetKit"] = accepted_visual_kit
        elif visual_context:
            card["previouslyAuthoredVisual"] = visual_context
    return card


def visual_director_output_contract() -> dict[str, Any]:
    """Describe the one root wrapper and the canonical field for every visual role."""
    return {
        "rootKey": "visualKit",
        "rootRule": (
            'The root object must contain exactly one key named "visualKit". '
            "Never return itemIconPrompt, bakedAssets, or any other VisualKit field at the root."
        ),
        "roleFields": copy.deepcopy(_VISUAL_DIRECTOR_ROLE_FIELDS),
        "assetDemandRule": (
            "A role prompt describes appearance but never requests a PNG by itself; "
            "only bakedAssets.<role>.mode=baked_sprite requests one."
        ),
    }


def visual_kit_response_schema() -> dict[str, Any]:
    """OpenAI-compatible wrapper schema for the Visual Director response."""
    kit_schema = copy.deepcopy(VisualKitBoundary.model_json_schema())
    defs = kit_schema.pop("$defs", {})
    # Live authoring has one canonical prompt per role. BakedAssetBoundary.prompt
    # remains in the Python boundary only for old cache/replay compatibility; mode
    # selection in new model output must not create a second competing prompt source.
    baked_def = defs.get("BakedAssetBoundary") if isinstance(defs, dict) else None
    if isinstance(baked_def, dict) and isinstance(baked_def.get("properties"), dict):
        baked_def["properties"].pop("prompt", None)
        effect_def = copy.deepcopy(baked_def)
        effect_properties = effect_def.get("properties")
        if isinstance(effect_properties, dict):
            effect_properties.pop("distinctFromItem", None)
            mode_schema = effect_properties.get("mode")
            if isinstance(mode_schema, dict) and isinstance(mode_schema.get("enum"), list):
                mode_schema["enum"] = [value for value in mode_schema["enum"] if value != "reuse_item_sprite"]
        effect_def["title"] = "EffectBakedAssetBoundary"
        defs["EffectBakedAssetBoundary"] = effect_def
    kit_properties = kit_schema.get("properties") if isinstance(kit_schema.get("properties"), dict) else {}
    kit_schema["description"] = (
        "The VisualKit value nested under the required root key visualKit. "
        "These fields must never be emitted directly at the response root."
    )
    role_descriptions = {
        "itemIconPrompt": "Canonical appearance prompt for the required item inventory/held sprite.",
        "projectileSpritePrompt": "Canonical appearance prompt for the projectile role when that role is relevant.",
        "impactSpritePrompt": "Canonical appearance prompt for the impact role when that role is relevant.",
        "childSpritePrompt": "Canonical appearance prompt for the child role when that role is relevant.",
        "fieldSpritePrompt": "Canonical appearance prompt for the field role when that role is relevant.",
    }
    for field, description in role_descriptions.items():
        field_schema = kit_properties.get(field)
        if isinstance(field_schema, dict):
            field_schema["description"] = description
    if "bakedAssets" in kit_properties:
        kit_properties["bakedAssets"] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "projectile": {"$ref": "#/$defs/BakedAssetBoundary"},
                "impact": {"$ref": "#/$defs/EffectBakedAssetBoundary"},
                "child": {"$ref": "#/$defs/EffectBakedAssetBoundary"},
                "field": {"$ref": "#/$defs/EffectBakedAssetBoundary"},
            },
        }
    schema: dict[str, Any] = {
        "type": "object",
        "description": (
            'The root object must contain exactly one key named "visualKit"; '
            "VisualKit fields are forbidden at the root."
        ),
        "additionalProperties": False,
        "properties": {"visualKit": kit_schema},
        "required": ["visualKit"],
    }
    if defs:
        schema["$defs"] = defs
    return schema


def visual_kit_usefulness_errors(kit: dict[str, Any]) -> list[str]:
    """Reject only a completely empty/default director response.

    Partial kits are valid: a director may intentionally keep the planner item prompt
    and only author a distinct projectile asset, palette, silhouette, or VFX surface.
    """
    meaningful_keys = (
        "styleGuide", "palette", "silhouetteSummary", "itemSilhouetteContract",
        "itemIconPrompt", "projectileSpritePrompt", "childSpritePrompt",
        "impactSpritePrompt", "fieldSpritePrompt", "bakedAssets", "vfxIntent",
        "projectileVfx", "impactVfx", "childVfx", "fieldVfx", "vfxMaterialHints",
        "vfxAvoid", "animationPlan", "assetDependencies", "qualityNotes",
        "animeReference",
    )
    if any(_nonempty(kit.get(key)) for key in meaningful_keys):
        return []
    return ["visualKit contains no authored visual decision"]


def visual_director_context(
    data: dict[str, Any],
    parent_a: dict[str, Any],
    parent_b: dict[str, Any],
    canonical_a: dict[str, Any] | None = None,
    canonical_b: dict[str, Any] | None = None,
) -> dict[str, Any]:
    concept = data.get("concept") if isinstance(data.get("concept"), dict) else {}
    runtime_plan = data.get("runtimePlan") if isinstance(data.get("runtimePlan"), dict) else {}
    planner_visual_intent = runtime_plan.get("visualIntent") if isinstance(runtime_plan.get("visualIntent"), dict) else {}
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}

    attack_facts = {
        key: copy.deepcopy(attack.get(key))
        for key in (
            "runtimeFamily", "delivery", "weaponFamily", "projectileFamily", "ammoKind",
            "projectileShape", "projectileMotion", "projectileRotation", "projectileTrail", "projectileImpact",
            "secondaryProjectileShape", "secondaryMaterial", "secondaryTrigger", "effect", "onHit", "movement",
            "shotCount", "spreadRadians", "splitCount", "chainCount", "channelUse", "beamWidthPx",
            "beamChargeTicks", "immunityCooldown", "aoeRadiusTiles", "secondaryLifetimeTicks",
            "maxChildProjectiles", "maxChildDepth", "trailLength", "vfxFieldLifetimeTicks",
            "vfxFieldRadiusTiles", "vfxFieldTickRate",
        )
        if _nonempty(attack.get(key))
    }

    final_identity: dict[str, Any] = {}
    if _nonempty(data.get("category")):
        final_identity["category"] = _bounded_visual_value(data.get("category"))
    result_kind = runtime_plan.get("resultKind")
    if _nonempty(result_kind):
        final_identity = {"resultKind": _bounded_visual_value(result_kind), **final_identity}

    return {
        "name": data.get("name"),
        "tooltip": data.get("tooltip"),
        "category": data.get("category"),
        "finalIdentity": final_identity,
        "concept": _bounded_visual_value(concept),
        "plannerVisualIntent": _bounded_visual_value(planner_visual_intent),
        "runtimeAffordance": copy.deepcopy(data.get("runtimeAffordance")) if isinstance(data.get("runtimeAffordance"), dict) else {},
        "attackFacts": attack_facts,
        "parents": [
            compact_visual_parent_card(parent_a, canonical_a),
            compact_visual_parent_card(parent_b, canonical_b),
        ],
    }


_ROLE_PROMPT_FIELDS = {
    "projectile": "projectileSpritePrompt",
    "impact": "impactSpritePrompt",
    "child": "childSpritePrompt",
    "field": "fieldSpritePrompt",
}
_ROLE_FALLBACK_FIELDS = {
    "projectile": ("projectileImagePrompt", "projectileSpritePrompt"),
    "impact": ("impactImagePrompt", "impactSpritePrompt"),
    "child": ("childImagePrompt", "childSpritePrompt"),
    "field": ("fieldImagePrompt", "fieldSpritePrompt"),
}


def visual_kit_projection_errors(kit: dict[str, Any], data: dict[str, Any]) -> list[str]:
    """Check only whether authored asset decisions can be projected technically.

    This does not judge visual quality or parent fusion. It prevents an asset-mode
    decision from requesting a PNG when no canonical or pre-existing prompt exists.
    """
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    baked = kit.get("bakedAssets") if isinstance(kit.get("bakedAssets"), dict) else {}
    errors: list[str] = []
    for role, spec in baked.items():
        if not isinstance(spec, dict) or str(spec.get("mode") or "") != "baked_sprite":
            continue
        prompt_field = _ROLE_PROMPT_FIELDS.get(role, "")
        visual_field, attack_field = _ROLE_FALLBACK_FIELDS.get(role, ("", ""))
        prompt = str(
            kit.get(prompt_field)
            or visual.get(visual_field)
            or attack.get(attack_field)
            or ""
        ).strip()
        if not prompt:
            errors.append(f"bakedAssets.{role}: mode=baked_sprite requires a role prompt")
    return errors


__all__ = [
    "compact_visual_parent_card",
    "visual_director_output_contract",
    "visual_kit_response_schema",
    "visual_kit_usefulness_errors",
    "visual_kit_projection_errors",
    "visual_director_context",
]
