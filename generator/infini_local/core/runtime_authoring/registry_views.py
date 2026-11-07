"""Model and audit projections of the canonical runtime capability inventory.

This module only presents declared facts. It does not register capabilities,
choose mechanics, or change the provider/local validation contracts.
"""
from __future__ import annotations

from typing import Any

import infini_local.core.runtime_authoring.capability_registry as registry


def compact_capability_catalog() -> list[dict[str, Any]]:
    return [cap.author_prompt_card() for cap in registry.CAPABILITY_REGISTRY.values() if cap.author_visible]


def runtime_authoring_prompt_field_guide() -> dict[str, Any]:
    """Project shared low-level field semantics without duplicating capability rules."""
    return {
        "types": shared_parameter_schemas(),
        "eventMetadata": (
            "producerFreeKinds/baseEvents need no extra producer. producedBy lists capability alternatives; "
            "producedByBinding fields constrain binding producers. producerExactParams constrains the named capability. "
            "Omitted producer lists are empty; omitted contact-damage or exact-param conditions are unrestricted."
        ),
        "stableIdPattern": r"^[a-z][a-z0-9_]{0,47}$",
        "paramNotation": (
            "paramRef='function.param' borrows that parameter's complete card. Params are required unless marked optional. "
            "This notation also applies recursively to properties and oneOf branches. "
            "oneOf selects exactly one branch; additionalProperties=false closes that object. "
            "Any explicit required list adds cross-branch required names. "
            "default is the declared value when an optional field is omitted; neutral is a no-effect value, "
            "not permission to omit. omissionAllowedOnlyWhen further restricts omission. "
            "min/max are inclusive bounds; exclusiveMinimum/exclusiveMaximum are strict. "
            "Units omitted for names ending Seconds/Tiles/Px/Radians are seconds/blocks/pixels/radians respectively. "
            "typeRef resolves in fieldGuide.types; projectionConstraints describe exact Author-to-consumer conversions."
        ),
        "requirementNotation": {
            "omittedMetadata": {"target": "same_target", "equals": None},
            "readingRule": "Defaults for metadata in requires rows only.",
        },
        "effectGroups": next(cap.prompt_card()["effectGroups"] for cap in registry.CAPABILITY_REGISTRY.values()
                             if cap.author_visible and cap.effect_groupable),
        "stackCost": registry.STACK_COST_RULE,
        "armorParamInheritance": "armor params without meaning use the accessory meaning for the same name.",
        "setBonusParamPrefix": "Matching armor set (head piece only; matching head, body and legs must actually be equipped): ",
        "exclusiveGroup": {
            "scope": "per exact target entity",
            "rule": "At most one call in the same non-empty exclusiveGroup may target one entity.",
            "groups": sorted({
                capability.exclusive_group
                for capability in registry.CAPABILITY_REGISTRY.values()
                if capability.exclusive_group
            }),
        },
        "bindingTarget": (
            "contactDamage adds item-body contact to an active binding, including spawn_entity. "
            "It requires disableMeleeHitbox=false and no ammo category; otherwise native Item.noMelee suppresses "
            "body contact and its on_hit/on_crit events. Body damage comes from item_stats; "
            "projectile damage comes from projectile_damage."
        ),
    }


def shared_parameter_schemas() -> dict[str, Any]:
    # Defaults describe a capability's use, not every use of the shared grammar.
    return {spec.shared_type: {key: value for key, value in spec.schema().items()
                              if key not in {"default", "x-infini-neutral"}}
            for cap in registry.CAPABILITY_REGISTRY.values()
            for spec in cap.params.values() if cap.author_visible and spec.shared_type}


def capability_provider_union(*, shared_refs: bool = False) -> list[dict[str, Any]]:
    return [cap.provider_variant_schema(shared_refs=shared_refs) for cap in registry.CAPABILITY_REGISTRY.values() if cap.author_visible]


def capability_inventory_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cap in registry.CAPABILITY_REGISTRY.values():
        rows.append({
            "capability": cap.name,
            "purpose": cap.summary,
            "parameters": {
                name: {
                    "kind": spec.kind,
                    "required": spec.required,
                    "minimum": spec.minimum,
                    "maximum": spec.maximum,
                    "enum": list(spec.enum),
                    "units": spec.units,
                    "semanticType": spec.semantic_type,
                    "reference": spec.reference.card() if spec.reference is not None else None,
                }
                for name, spec in cap.params.items()
            },
            "targetKinds": list(cap.target_kinds),
            "events": list(cap.allowed_events),
            "emittedEvents": list(cap.emitted_events),
            "componentSlot": cap.component_slot,
            "exclusiveGroup": cap.exclusive_group,
            "positionOwnership": cap.position_ownership,
            "requirements": [row.card() for row in cap.requirements],
            "dependencies": list(cap.dependencies),
            "conflicts": list(cap.conflicts),
            "csharpOwner": cap.csharp_owner,
            "pythonOwner": cap.compiler_owner,
            "networkAuthority": cap.network_authority,
            "authorityByEffect": dict(cap.authority_by_effect),
            "safetyLimits": cap.performance_budget,
            "multiplicity": cap.multiplicity,
            "finalWirePaths": list(cap.final_wire_paths),
            "technicalLoweringOutputs": list(cap.technical_lowering_outputs),
        })
    return rows


def runtime_authoring_registry_manifest() -> dict[str, Any]:
    return {
        "schema": "infini.runtime-authoring-registry.v1",
        "apiVersion": registry.RUNTIME_PROGRAM_API_VERSION,
        "authoringSchema": registry.RUNTIME_PROGRAM_SCHEMA,
        "wireSchema": registry.RUNTIME_WIRE_SCHEMA,
        "entityKinds": [row.prompt_card() for row in registry.ENTITY_KIND_REGISTRY.values()],
        "inputs": [row.prompt_card() for row in registry.INPUT_KIND_REGISTRY.values()],
        "bindingActions": [row.prompt_card() for row in registry.BINDING_ACTION_REGISTRY.values()],
        "events": [row.prompt_card() for row in registry.EVENT_KIND_REGISTRY.values()],
        "capabilities": [cap.audit_card() for cap in registry.CAPABILITY_REGISTRY.values()],
    }
