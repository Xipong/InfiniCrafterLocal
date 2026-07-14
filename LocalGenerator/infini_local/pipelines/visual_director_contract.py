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
            "category", "headNoun", "shapeAnchors", "visualAnchors", "hardTags",
            "softTags", "sourceMod", "internalName",
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
        summary = generated.get("generatedParentSummary") if isinstance(generated.get("generatedParentSummary"), dict) else {}
        summary_context = {
            key: _bounded_visual_value(summary.get(key))
            for key in ("name", "fantasy", "visualIdentity", "notableEffects")
            if _nonempty(summary.get(key))
        }
        if visual_context:
            card["previouslyAuthoredVisual"] = visual_context
        if summary_context:
            card["generatedParentSummary"] = summary_context

    return card


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
    source_role_preservation = runtime_plan.get("sourceRolePreservation") if isinstance(runtime_plan.get("sourceRolePreservation"), dict) else {}
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    debug = data.get("debug") if isinstance(data.get("debug"), dict) else {}

    attack_facts = {
        key: copy.deepcopy(attack.get(key))
        for key in (
            "runtimeFamily", "delivery", "weaponFamily", "projectileFamily", "ammoKind",
            "projectileShape", "projectileMotion", "projectileRotation", "projectileTrail", "projectileImpact",
            "secondaryProjectileShape", "secondaryMaterial", "secondaryTrigger", "effect", "onHit", "movement",
            "shotCount", "spreadRadians", "splitCount", "chainCount", "channelUse", "beamWidthPx",
            "beamChargeTicks", "immunityCooldown",
        )
        if _nonempty(attack.get(key))
    }
    prompt_source = str(debug.get("visualPromptSource") or "unknown")
    existing_visual_keys = [
        "objectType", "requiredAnchors", "parentVisualContext", "palette",
        "itemPrompt", "projectilePrompt", "impactPrompt", "notes",
        "projectileImagePrompt", "impactImagePrompt", "childImagePrompt", "fieldImagePrompt",
        "itemSilhouetteContract",
    ]
    # A code fallback is useful to the image backend, but it is not authored evidence
    # for the Visual Director. Only expose imagePrompt as an authored decision when
    # provenance says it came from the planner.
    if prompt_source == "planner_authored":
        existing_visual_keys.append("imagePrompt")
    existing_visual = {
        key: _bounded_visual_value(visual.get(key))
        for key in existing_visual_keys
        if _nonempty(visual.get(key))
    }
    final_canonical_raw = data.get("canonical")
    final_canonical: dict[str, Any] = final_canonical_raw if isinstance(final_canonical_raw, dict) else {}
    final_identity = {
        key: _bounded_visual_value(final_canonical.get(key))
        for key in ("category", "headNoun", "shapeAnchors", "visualAnchors", "hardTags", "softTags")
        if _nonempty(final_canonical.get(key))
    }
    result_kind = runtime_plan.get("resultKind")
    if _nonempty(result_kind):
        final_identity = {"resultKind": _bounded_visual_value(result_kind), **final_identity}

    return {
        "name": data.get("name"),
        "tooltip": data.get("tooltip"),
        "category": data.get("category"),
        "finalIdentity": final_identity,
        "concept": _bounded_visual_value(concept),
        "sourceRolePreservation": _bounded_visual_value(source_role_preservation),
        "plannerVisualIntent": _bounded_visual_value(planner_visual_intent),
        "runtimeAffordance": copy.deepcopy(data.get("runtimeAffordance")) if isinstance(data.get("runtimeAffordance"), dict) else {},
        "attackFacts": attack_facts,
        "parents": [
            compact_visual_parent_card(parent_a, canonical_a),
            compact_visual_parent_card(parent_b, canonical_b),
        ],
        "existingVisual": existing_visual,
        "existingVisualProvenance": {
            "imagePrompt": prompt_source,
            "palette": str(debug.get("visualPaletteSource") or "unknown"),
            "requiredAnchors": str(debug.get("visualRequiredAnchorsSource") or "unknown"),
            "parentVisualContext": "raw_parent_facts_and_nonbinding_context",
        },
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
    "visual_kit_response_schema",
    "visual_kit_usefulness_errors",
    "visual_kit_projection_errors",
    "visual_director_context",
]
