from __future__ import annotations

import copy
from typing import Any

from infini_local.core.boundary_models import VisualKitBoundary
from infini_local.core.item_identity_tools import generated_data_of, item_field, name_of
from infini_local.core.visual_role_contracts import (
    VISUAL_BAKED_ROLE_CONTRACTS,
    VISUAL_BAKED_ROLE_PROMPT_FIELDS,
    VISUAL_FORBIDDEN_BAKED_ASSET_KEYS,
    visual_director_role_fields,
)


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

_RUNTIME_VISUAL_ROLE_SPECS: dict[str, dict[str, dict[str, Any]]] = {
    "sentry": {
        "projectile": {
            "allowedModes": ("baked_sprite",),
            "promptField": "projectileSpritePrompt",
            "promptRequiredModes": ("baked_sprite",),
            "contextRule": "required baked_sprite for the stationary sentry root/body",
            "error": "sentry projectile required: baked_sprite + projectileSpritePrompt",
        },
        "child": {
            "allowedModes": ("baked_sprite",),
            "promptField": "childSpritePrompt",
            "promptRequiredModes": ("baked_sprite",),
            "contextRule": "required baked_sprite for the fired sentry shot body",
            "error": "sentry child required: baked_sprite + childSpritePrompt",
        },
    },
    "summon": {
        "projectile": {
            "allowedModes": ("baked_sprite", "reuse_item_sprite"),
            "promptField": "projectileSpritePrompt",
            "promptRequiredModes": ("baked_sprite",),
            "contextRule": (
                "required explicit persistent summon body: baked_sprite + projectileSpritePrompt, "
                "or reuse_item_sprite for an item-bodied summon"
            ),
            "error": (
                "summon projectile body required: baked_sprite + projectileSpritePrompt "
                "or reuse_item_sprite"
            ),
        },
    },
}


def _runtime_visual_role_specs(runtime_family: str) -> dict[str, dict[str, Any]]:
    return _RUNTIME_VISUAL_ROLE_SPECS.get(runtime_family.strip().lower(), {})

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
        "roleFields": visual_director_role_fields(),
        "bakedAssetRoleKeys": [contract.role for contract in VISUAL_BAKED_ROLE_CONTRACTS],
        "forbiddenBakedAssetKeys": list(VISUAL_FORBIDDEN_BAKED_ASSET_KEYS),
        "fieldPlacementRule": (
            "Role prompt and VFX fields belong directly inside visualKit; "
            "never inside bakedAssets and never inside a vfx object. "
            "Each bakedAssets role object contains only mode, reason, and projectile-only distinctFromItem."
        ),
        "assetDemandRule": (
            "A role prompt describes appearance but never requests a PNG by itself; "
            "only bakedAssets.<role>.mode=baked_sprite requests one."
        ),
    }


def _inline_local_schema_refs(value: Any, definitions: dict[str, Any]) -> Any:
    if isinstance(value, list):
        return [_inline_local_schema_refs(item, definitions) for item in value]
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    ref = value.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        name = ref.rsplit("/", 1)[-1]
        definition = definitions.get(name)
        if not isinstance(definition, dict):
            raise ValueError(f"visual provider schema references unknown definition: {name}")
        merged = copy.deepcopy(definition)
        merged.update({key: item for key, item in value.items() if key != "$ref"})
        return _inline_local_schema_refs(merged, definitions)
    return {
        key: _inline_local_schema_refs(item, definitions)
        for key, item in value.items()
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
    property_descriptions = {
        "itemIconPrompt": "Canonical appearance prompt for the required item inventory/held sprite.",
        "projectileSpritePrompt": "Canonical appearance prompt for the projectile role when that role is relevant.",
        "impactSpritePrompt": "Canonical appearance prompt for the impact role when that role is relevant.",
        "childSpritePrompt": "Canonical appearance prompt for the child role when that role is relevant.",
        "fieldSpritePrompt": "Canonical appearance prompt for the field role when that role is relevant.",
        "vfxScaleHint": (
            "Exactly one enum string: tiny, small, normal, large, or huge. "
            "This field is never an array and never contains multiple choices."
        ),
        "vfxRhythmHint": (
            "Exactly one enum string: slow, normal, snappy, delayed, or pulsing. "
            "This field is never an array and never contains multiple choices."
        ),
        "vfxMaterialHints": (
            "The only VFX hint field that is an array; return zero or more material strings."
        ),
        "vfxAvoid": (
            "Exactly one string containing the complete concise avoid instruction. "
            "This field is never an array; combine multiple avoid concepts into this one string."
        ),
    }
    for field, description in property_descriptions.items():
        field_schema = kit_properties.get(field)
        if isinstance(field_schema, dict):
            field_schema["description"] = description
    if "bakedAssets" in kit_properties:
        kit_properties["bakedAssets"] = {
            "type": "object",
            "description": (
                "bakedAssets may contain only projectile, impact, child, field, and equip_overlay; never item. "
                "The required item sprite is described by itemIconPrompt outside bakedAssets. "
                "Role prompt fields are direct visualKit properties and must never be nested in a bakedAssets role."
            ),
            "additionalProperties": False,
            "properties": {
                contract.role: {
                    "$ref": (
                        "#/$defs/BakedAssetBoundary"
                        if contract.reuse_item_sprite_allowed
                        else "#/$defs/EffectBakedAssetBoundary"
                    )
                }
                for contract in VISUAL_BAKED_ROLE_CONTRACTS
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
    return _inline_local_schema_refs(schema, defs)


def visual_kit_usefulness_errors(kit: dict[str, Any]) -> list[str]:
    """Reject only a completely empty/default director response.

    Partial kits are valid: a director may intentionally keep the planner item prompt
    and only author a distinct projectile asset, palette, silhouette, or VFX surface.
    """
    meaningful_keys = (
        "styleGuide", "palette", "silhouetteSummary", "itemSilhouetteContract",
        "itemIconPrompt", "projectileSpritePrompt", "childSpritePrompt",
        "impactSpritePrompt", "fieldSpritePrompt", "equipOverlayPrompt", "bakedAssets", "vfxIntent",
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
    attack_candidate = data.get("attack")
    attack: dict[str, Any] = attack_candidate if isinstance(attack_candidate, dict) else {}

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
    runtime_family = str(attack.get("runtimeFamily") or "").strip().lower()
    runtime_role_obligations = {
        role: str(spec["contextRule"])
        for role, spec in _runtime_visual_role_specs(runtime_family).items()
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
        "runtimeVisualRoleObligations": runtime_role_obligations,
        "parents": [
            compact_visual_parent_card(parent_a, canonical_a),
            compact_visual_parent_card(parent_b, canonical_b),
        ],
    }


def visual_kit_projection_errors(kit: dict[str, Any], data: dict[str, Any]) -> list[str]:
    """Check only whether authored asset decisions can be projected technically.

    This does not judge visual quality or parent fusion. It prevents an asset-mode
    decision from requesting a PNG when the same canonical VisualKit has no role prompt.
    """
    baked_raw = kit.get("bakedAssets")
    baked: dict[str, Any] = baked_raw if isinstance(baked_raw, dict) else {}
    errors: list[str] = []
    gameplay_raw = data.get("gameplay")
    gameplay: dict[str, Any] = gameplay_raw if isinstance(gameplay_raw, dict) else {}
    result_kind = str(gameplay.get("kind") or data.get("category") or "").strip().lower()
    if result_kind in {"armor", "accessory"}:
        equip_raw = baked.get("equip_overlay")
        equip_spec: dict[str, Any] = equip_raw if isinstance(equip_raw, dict) else {}
        if str(equip_spec.get("mode") or "") != "baked_sprite" or not str(kit.get("equipOverlayPrompt") or "").strip():
            errors.append("equip_overlay required for armor/accessory: baked_sprite + equipOverlayPrompt")
    attack_raw = data.get("attack")
    attack: dict[str, Any] = attack_raw if isinstance(attack_raw, dict) else {}
    runtime_family = str(attack.get("runtimeFamily") or "").strip().lower()
    for role, obligation in _runtime_visual_role_specs(runtime_family).items():
        role_raw = baked.get(role)
        role_spec: dict[str, Any] = role_raw if isinstance(role_raw, dict) else {}
        mode = str(role_spec.get("mode") or "")
        allowed_modes = tuple(obligation["allowedModes"])
        prompt_required_modes = tuple(obligation["promptRequiredModes"])
        prompt = str(kit.get(str(obligation["promptField"])) or "").strip()
        if mode not in allowed_modes or (mode in prompt_required_modes and not prompt):
            errors.append(str(obligation["error"]))
    for role, spec in baked.items():
        if not isinstance(spec, dict) or str(spec.get("mode") or "") != "baked_sprite":
            continue
        prompt_field = VISUAL_BAKED_ROLE_PROMPT_FIELDS.get(role, "")
        prompt = str(kit.get(prompt_field) or "").strip()
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
