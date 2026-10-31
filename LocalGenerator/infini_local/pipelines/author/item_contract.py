from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping

from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION, RUNTIME_PROGRAM_SCHEMA
from infini_local.core.runtime_authoring.program_schema import (
    author_item_repair_schema as _repair_schema,
    author_item_response_schema as _author_schema,
    PRIMARY_ENTITY_AUTHOR_PATH,
    PRIMARY_ENTITY_FIELD,
    PRIMARY_ENTITY_SELECTION_FIELD,
    _binding_variant_schema,
)
from infini_local.core.provider_schema import _provider_strict_projection, project_provider_nullable_optionals_to_local


AUTHOR_DESIGN_QUALITY_RULE = (
    "Create a new Terraria item based on the combination of these parents. Freely choose how they influence the result. Aim for a coherent concept and interesting gameplay use. "
    "Choose mechanics and controls that reinforce each other, with readable strengths, limitations and costs. "
    "Design the actual play sequence: where the player and targets are, how effects reach them, and what visible motion communicates the action. "
    "Make the relationship between the player and the visible item or effect intentional: a held body, an independently moving object or a detached effect should read as that choice throughout its motion. "
    "Choose geometry for its executed motion and contact shape; later art and VFX dress that motion rather than replace it."
)

AUTHOR_STATUS_COMPOSITION_RULE = (
    "Composed status effects do not inherit native buff immunity or AI. "
    "Parent effect references cover only their listed operations and conditions."
)


PRIMARY_REPAIR_SYSTEM_RULE = (
    f"Use {PRIMARY_ENTITY_SELECTION_FIELD} whenever its repair transaction is enabled."
)
RUNTIME_ROW_SHAPE_RULE = (
    "Rows illustrate alternative forms. Calls may omit target only for item-body-only capabilities, "
    "and params only for zero-argument capabilities. "
    "Fixed binding literals may be omitted: hold kind=spawn_entity; equipped kind=equip_passive; "
    "item-body-only action targetId=the unique item_body id; hold/equipped stackCost=0 and contactDamage=false; "
    "place_item stackCost=1 and contactDamage=false. Active non-placement kind, stackCost and contactDamage are explicit. "
    "placementCallId belongs only to place_item; effectGroupId belongs only to apply_item_effects, "
    "where absence selects ungrouped effects."
    " Physical composition: owner_mounted is owner.MountedCenter, not the hand. "
    "attach reads an anchor; front_arm_pose independently writes the front arm, whose native stretch length is only 4 to 10px. "
    "There is no automatic arm follow of body motion. front_hand reads the native hand but does not cancel "
    "physical axis/normal offsets or reachCurve: they translate actual body center and collision geometry. "
    "The selected PNG grip adapter compensates attachment offsets only, not reachCurve. "
    "For constant contact of a rigid PNG grip, use front_hand with the selected grip and no reachCurve; "
    "its static attachment offsets remain compensated by that PNG adapter. A hand-rooted beam/path needs its "
    "authored line origin at the hand; front_arm_pose independently chooses arm motion, not line displacement. "
    "PNG grip metadata is needed only by PNG consumers. Deliberately displaced bodies remain valid. "
    "beam_geometry uses the same Aim world unit axis (MotionAxis): start=body center+axis*startOffsetBlocks, "
    "end=start+axis*length, with blocks converted to world pixels; omitted offset is zero. "
    "Its signed offset changes only the line origin, never length, width, attachment/reach, body physics or PNG scale. "
    "An inventory grip or hidden root PNG does not anchor a separate path surface. "
    "For native-like held motion, projectile.Center is not the grip: a rigid body may extend behind its pivot "
    "while its hilt region slides beneath the palm. A held claim draws a selected body PNG in the native held-projectile pass, "
    "where the front hand can cover it; detached VFX layers do not imply that occlusion. This is not a fixed grip-point guarantee. "
    "Visual/VFX cannot repair accepted attachment, pose or geometry. These facts grant no Repair edit permissions."
)


def primary_entity_llm_invariant() -> dict[str, Any]:
    return {
        "exactlyOnePrimaryEntity": True,
        "authoredField": PRIMARY_ENTITY_AUTHOR_PATH,
        "primaryRule": (
            "Select the entity owning lifecycle/held representation. "
            "Use the item_body for item-graphic/body-contact representation. When all active bindings spawn "
            "the same entity, all have contactDamage=false and item_use.hideUseGraphic=true, select "
            "that spawn target. "
            "A movement/controller that claims held-projectile representation does so only for this primary entity. "
        ),
    }


def author_item_response_schema() -> dict[str, Any]:
    return copy.deepcopy(_author_schema())


def _binding_prompt_shape_cards() -> list[dict[str, Any]]:
    """Project a few instructional rows from the sole binding-shape owner.

    These leaf values are examples only, never Author defaults or Repair edits.
    Required/forbidden keys and discriminators come from the canonical schema.
    """
    example_leaves = {
        "id": "binding_id", "targetId": "projectile_id", "placementCallId": "placement_call_id",
        "effectGroupId": "effect_group_id", "stackConsumeChancePercent": 50, "contactDamage": False,
    }

    def project(schema: Mapping[str, Any], name: str = "") -> Any:
        if "const" in schema:
            return schema["const"]
        if schema.get("type") == "object":
            return {key: project(child, key) for key, child in schema["properties"].items()}
        return "exact_item_body_id" if name == "targetId" and schema.get("x-infini-reference", {}).get("targetKinds") == ["item_body"] else example_leaves[name]

    return [project(_binding_variant_schema(input_name, action, cost)) for input_name, action, cost in (
        ("primary_use", "spawn_entity", 0),
        ("alternate_use", "use_item_body", 0),
        ("primary_use", "apply_item_effects", 1),
        ("alternate_use", "place_item", None),
        ("hold", "spawn_entity", None),
        ("equipped", "equip_passive", None),
    )]


def _call_prompt_shape_cards(variants: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Share only top-level forms present in this Author or scoped Repair union.

    Parameter grammar stays in capability cards, without invented example
    mechanics or a second capability catalogue in the shape card.
    """
    hints = {
        "id": "stable_call_id", "fn": "catalog capability name",
        "target": "entity_id",
        "params": {"selected capability parameters": "values"},
    }
    forms: dict[tuple[str, ...], dict[str, Any]] = {}
    for variant in variants:
        keys = tuple(variant["properties"])
        forms.setdefault(keys, {key: copy.deepcopy(hints[key]) for key in keys})
    return list(forms.values())


def _realization_prompt_shape_card() -> dict[str, str]:
    """Separate optional player-facing prose from implementation debug."""
    properties = _author_schema()["properties"]["realization"]["properties"]
    roles = {
        "description": "Brief player-facing description of actual use, effects and conditions.",
        "playerExperience": "Optional practical-use notes for the player.",
        "selfEvaluation": "Optional implementation/debug notes, including any mismatch with the idea. Not player text or an observed test result.",
    }
    return {name: f"{roles[name]} String minLength={spec['minLength']}, maxLength={spec['maxLength']} Unicode characters."
            for name, spec in properties.items()}


def author_item_prompt_shape_card() -> dict[str, Any]:
    """Executable item plus concise advisory design/debug notes."""
    schema = _author_schema()
    call_variants = schema["properties"]["runtimeProgram"]["properties"]["calls"]["items"]["oneOf"]
    return {
        "root": ["name", "category", "concept", "runtimeProgram", "realization"],
        "concept": "Brief design intent: the item you want to create.",
        "realization": {key: value for key, value in _realization_prompt_shape_card().items()
                        if key in {"description", "selfEvaluation"}},
        "name": "non-empty item name",
        "category": "UI/equipment classification: combat|tool|equipment|placeable|consumable|material|hybrid|generic",
        "runtimeProgram": {
            "apiVersion": RUNTIME_PROGRAM_API_VERSION,
            "schema": RUNTIME_PROGRAM_SCHEMA,
            PRIMARY_ENTITY_FIELD: "lifecycle/held entity id",
            "entities": [{"id": "stable_id", "kind": "catalog entity kind"}],
            "bindings": _binding_prompt_shape_cards(),
            "calls": _call_prompt_shape_cards(call_variants),
        },
    }


def author_item_provider_response_schema(*, local_schema: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return _provider_strict_projection(
        author_item_response_schema() if local_schema is None else local_schema, omit_annotations=True,
    )


def _generation_author_schema() -> dict[str, Any]:
    """Separate player text from debug without restoring structured concept essays."""
    schema = author_item_response_schema()
    schema["properties"]["concept"] = {"type": "string"}
    report = schema["properties"]["realization"]
    report["properties"] = {key: value for key, value in report["properties"].items()
                            if key in {"description", "selfEvaluation"}}
    return schema


def author_item_generation_provider_schema() -> dict[str, Any]:
    return author_item_provider_response_schema(local_schema=_generation_author_schema())


def author_item_repair_response_schema(
    *, capability_names: Iterable[str] | None = None,
) -> dict[str, Any]:
    return copy.deepcopy(_repair_schema(
        capability_names=capability_names))


def author_item_repair_prompt_shape_card(*, capability_names: Iterable[str] | None = None) -> dict[str, Any]:
    """Expose the repair root cardinality when provider JSON Schema is unavailable."""
    schema = author_item_repair_response_schema(capability_names=capability_names)
    properties = schema.get("properties") or {}
    placeholders: dict[str, Any] = {}
    for key, child in properties.items():
        if key == "entitiesUpsert":
            placeholders[key] = [{"id": "stable_entity_id", "kind": "catalog entity kind"}]
            continue
        if key == "bindingsUpsert":
            placeholders[key] = _binding_prompt_shape_cards()
            continue
        if key == "callsUpsert":
            placeholders[key] = _call_prompt_shape_cards((child.get("items") or {}).get("oneOf") or [])
            continue
        if key == "callParamKeysDelete":
            placeholders[key] = [{
                "callId": "exact call id from repairScope.deletable.callParamKeys",
                "key": "exact invalid parameter key from repairScope.deletable.callParamKeys",
            }]
            continue
        if key == "realizationReplacement":
            placeholders[key] = _realization_prompt_shape_card()
            continue
        if key == PRIMARY_ENTITY_SELECTION_FIELD:
            placeholders[key] = f"entity_id chosen from repairScope.repairTransactions.{PRIMARY_ENTITY_SELECTION_FIELD}.candidateEntityIds, or null"
            continue
        if key == "exclusiveInputSelections":
            placeholders[key] = [{"input": "conflicting exclusive input", "keepBindingId": "chosen candidate binding id"}]
            continue
        child_type = child.get("type") if isinstance(child, Mapping) else None
        if child_type == "array":
            placeholders[key] = []
        elif child_type == "object":
            placeholders[key] = {}
        elif child_type == "boolean":
            placeholders[key] = False
        elif child_type in {"integer", "number"}:
            placeholders[key] = 0
        else:
            placeholders[key] = "non-empty repair note"
    return placeholders


def author_item_provider_repair_response_schema(
    *_: Any, local_schema: Mapping[str, Any] | None = None, **__: Any,
) -> dict[str, Any]:
    return _provider_strict_projection(
        local_schema if local_schema is not None else author_item_repair_response_schema(),
        omit_annotations=True)


def project_provider_author_item_to_local(
    value: Any, *, response_format: Mapping[str, Any] | None = None,
) -> Any:
    if not isinstance(response_format, Mapping) or response_format.get("type") != "json_schema":
        return copy.deepcopy(value)
    local = author_item_response_schema()
    envelope = response_format.get("json_schema")
    provider = envelope.get("schema") if isinstance(envelope, Mapping) else None
    if isinstance(provider, Mapping):
        # Decode only the exact fresh-generation advisory projection. Historical
        # string reports and other shapes remain raw advisory data.
        generation = _generation_author_schema()
        for field in ("concept", "realization"):
            child = generation["properties"][field]
            expected = {"anyOf": [_provider_strict_projection(child, omit_annotations=True), {"type": "null"}]}
            if (provider.get("properties") or {}).get(field) == expected:
                local["properties"][field] = child
    return project_provider_nullable_optionals_to_local(
        value, local, response_format=response_format,
    )


__all__ = [
    "AUTHOR_DESIGN_QUALITY_RULE",
    "PRIMARY_REPAIR_SYSTEM_RULE",
    "author_item_prompt_shape_card",
    "author_item_provider_repair_response_schema",
    "author_item_provider_response_schema",
    "author_item_repair_prompt_shape_card",
    "author_item_repair_response_schema",
    "author_item_response_schema",
    "project_provider_author_item_to_local",
    "primary_entity_llm_invariant",
]
