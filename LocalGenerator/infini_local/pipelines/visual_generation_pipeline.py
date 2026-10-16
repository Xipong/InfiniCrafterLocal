from __future__ import annotations

"""Visual Director over accepted low-level runtime entities.

The Director sees the already-validated runtime program and parent facts.  It may
choose appearance and per-entity asset modes, but it cannot add/change gameplay,
entities, bindings, events, movement, damage, or lifecycle.
"""

import copy
import json
from dataclasses import dataclass
from typing import Any, Mapping

from infini_local.core.env_utils import env_float, env_int
from infini_local.core.generation_defaults import GENERATION_DEFAULTS
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.visual_contract_schema import (
    SPRITE_CANVAS_SIZES, front_hand_sprite_errors, front_hand_sprite_requirement, grip_schema,
    sprite_presentation_properties,
)
from infini_local.core.llm_config import USE_LLM
from infini_local.core.llm_json_tools import parse_first_valid_llm_json, recover_object_with_syntax_only_repairs
from infini_local.core.llm_prompt_cache import with_instruction_segments, with_schema_instruction_definitions
from infini_local.core.llm_stage_messages import generation_system_suffix, stage_chat_message
from infini_local.storage.trace_runtime import trace_event, trace_stage_request
from infini_local.core.repair_merge import json_path_child, json_path_relative, json_values_equal, merge_frozen_subtree
from infini_local.core.runtime_authoring.wire_views import runtime_event_inventory, runtime_visual_roles
from infini_local.core.schema_validation import strict_schema_errors
from infini_local.pipelines.llm_transport import (
    effective_response_format,
    apply_llm_common_options,
    llm_chat_json,
    llm_json_response_format,
    llm_reasoning_system_suffix,
    resolve_llm_model,
    visual_director_max_tokens,
    with_llm_stage,
)
from infini_local.pipelines.author_item_contract import (
    _provider_strict_projection,
    project_provider_nullable_optionals_to_local,
    provider_nullable_transport_rule,
)
from infini_local.pipelines.pipeline_visual_config import VISUAL_DIRECTOR_LLM
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
from infini_local.pipelines.visual_asset_plan import equipment_overlay_requirement
from infini_local.pipelines.visual_prompt_contracts import visual_background_transport_rule
from infini_local.pipelines.visual_asset_modes import (
    VISUAL_ASSET_MODES,
    visual_asset_mode_catalog,
)


VISUAL_KIT_SCHEMA = "infini.visual-kit.runtime-entities.v2"
VISUAL_REPAIR_PATCH_SCHEMA = "infini.visual-kit-repair-patch.runtime-entities.v2"
_ALLOWED_ASSET_MODES = set(VISUAL_ASSET_MODES)
_VISUAL_STATIC_PREFIX_KEYS = ("task", "assetModeCatalog", "rules", "spritePresentationReadOnly")

# Canonical model-facing units for the unchanged Visual wire. Repair reuses the
# same item, overlay and entity schema builders as the ordinary Director.
_ITEM_CANVAS_DESCRIPTION = (
    "Requested square item PNG target canvas, in pixels per side; not the item's world size "
    "or a guaranteed on-screen display size."
)
_OVERLAY_CANVAS_DESCRIPTION = (
    "Requested square equipment-overlay PNG target canvas, in pixels per side; "
    "not the on-player display size (the draw layer fits the texture separately)."
)
_INVENTORY_SCALE_DESCRIPTION = (
    "Engine-units multiplicative inventory sprite draw factor after the texture/frame fit; "
    "1 is neutral, not a pixel size."
)
_WORLD_SCALE_DESCRIPTION = (
    "Engine-units multiplicative dropped world-item sprite draw factor applied to the "
    "engine-provided draw scale; 1 is neutral, not a pixel size or inventory scale."
)
_ENTITY_SCALE_DESCRIPTION = (
    "Engine-units multiplicative per-entity visual factor; 1 is neutral. "
    "Not the collision hitbox size or item.worldScale: projectile draw scale multiplies "
    "hitbox.drawScale separately. no_asset entities may have no visible sprite."
)


@dataclass(frozen=True)
class MalformedVisualDirectorOutput:
    raw_text: str
    error: str


def _stage_accounting(data: dict[str, Any]) -> dict[str, int]:
    debug = data.setdefault("debug", {})
    accounting = debug.setdefault("llmStageAccounting", {})
    for key in (
        "gameplayAuthorCalls", "gameplayRepairCalls", "visualDirectorCalls",
        "visualRepairCalls", "vfxDirectorCalls", "vfxRepairCalls",
    ):
        accounting.setdefault(key, 0)
    return accounting


def attach_visual(data: dict[str, Any]) -> dict[str, Any]:
    visual = data.setdefault("visual", {})
    visual.setdefault("preferredCanvasSize", 32)
    visual.setdefault("inventoryScale", 1.0)
    visual.setdefault("worldScale", 1.0)
    visual.setdefault("drawOffsetX", 0)
    visual.setdefault("drawOffsetY", 0)
    visual.setdefault("palette", [])
    visual.setdefault("spriteStatus", "")
    visual.setdefault("spritePath", "")
    visual.setdefault("spriteUrl", "")
    visual.setdefault("spriteTechnicalScore", 0.0)
    data.setdefault("debug", {})["runtimeVisualRoles"] = runtime_visual_roles(data)
    return data


def _visual_item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "prompt": {"type": "string", "minLength": 1, "maxLength": 1400},
            "negativePrompt": {"type": "string", "maxLength": 700},
            "silhouette": {"type": "string", "minLength": 1, "maxLength": 700},
            "visualIdentity": {"type": "string", "minLength": 1, "maxLength": 700},
            "palette": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 256}, "minItems": 1, "maxItems": 8},
            "preferredCanvasSize": {"type": "integer", "enum": list(SPRITE_CANVAS_SIZES), "description": _ITEM_CANVAS_DESCRIPTION},
            **sprite_presentation_properties(),
            "inventoryScale": {"type": "number", "minimum": 0.25, "maximum": 4.0, "description": _INVENTORY_SCALE_DESCRIPTION},
            "worldScale": {"type": "number", "minimum": 0.25, "maximum": 4.0, "description": _WORLD_SCALE_DESCRIPTION},
            "grip": grip_schema(),
        },
        "required": ["prompt", "negativePrompt", "silhouette", "visualIdentity", "palette", "preferredCanvasSize", "renderSizePx", "forwardAngleDegrees", "inventoryScale", "worldScale"],
    }


def _visual_equip_overlay_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "prompt": {"type": "string", "minLength": 1, "maxLength": 1400},
            "silhouette": {"type": "string", "minLength": 1, "maxLength": 700},
            "visualIdentity": {"type": "string", "minLength": 1, "maxLength": 700},
            "preferredCanvasSize": {"type": "integer", "enum": [32, 48, 64, 96], "description": _OVERLAY_CANVAS_DESCRIPTION},
            "accessoryMount": {
                "type": "string", "enum": ["chest", "back", "waist", "shoulder", "orbit"],
                "description": "Optional accessory-only body-local badge anchor, using the existing overlay PNG, body pivot/rotation and 18px fit. chest=(0,-2), back=(-10,-4), waist=(0,10), shoulder=(8,-12) player pixels relative to center, X facing-mirrored and Y gravity-mirrored. orbit uses the existing accessory slot ring. Armor ignores this field. No atlas or gameplay change.",
            },
        },
        "required": ["prompt", "silhouette", "visualIdentity", "preferredCanvasSize"],
    }


def _visual_entity_schema(entity_ids: list[str], item_body_id: str | None = None) -> dict[str, Any]:
    entity_id = {"type": "string", "enum": entity_ids}
    scale = {"type": "number", "minimum": 0.25, "maximum": 4.0, "description": _ENTITY_SCALE_DESCRIPTION}
    authored = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "entityId": copy.deepcopy(entity_id),
            "assetMode": {"const": "baked_sprite"},
            "visualProjectRef": {"const": "item"},
            "scale": copy.deepcopy(scale),
        },
        "required": ["entityId", "assetMode", "visualProjectRef", "scale"],
    }
    if item_body_id is not None:
        authored["properties"]["entityId"]["enum"] = [item_body_id]
    distinct = copy.deepcopy(authored)
    distinct["properties"]["visualProjectRef"] = {"const": "entity"}
    distinct["properties"]["entityId"]["enum"] = [value for value in entity_ids if value != item_body_id]
    distinct["properties"].update({
        "prompt": {"type": "string", "minLength": 1, "maxLength": 1400},
        "silhouette": {"type": "string", "minLength": 1, "maxLength": 700},
        "visualIdentity": {"type": "string", "minLength": 1, "maxLength": 700},
        "preferredCanvasSize": {"type": "integer", "enum": list(SPRITE_CANVAS_SIZES), "description": _ITEM_CANVAS_DESCRIPTION.replace("item PNG", "independent entity PNG")},
        **sprite_presentation_properties(),
        "grip": grip_schema(),
    })
    distinct["required"].extend(["prompt", "silhouette", "visualIdentity", "preferredCanvasSize", "renderSizePx", "forwardAngleDegrees"])
    nonitem_id = {"type": "string", "enum": [value for value in entity_ids if value != item_body_id]}
    reuse = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "entityId": copy.deepcopy(nonitem_id),
            "assetMode": {"const": "reuse_item_icon"},
            "visualProjectRef": {"const": "item"},
            "scale": copy.deepcopy(scale),
        },
        "required": ["entityId", "assetMode", "visualProjectRef", "scale"],
    }
    non_sprite_branches = []
    for mode in ("runtime_geometry", "no_asset"):
        non_sprite_branches.append({
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "entityId": copy.deepcopy(nonitem_id),
                "assetMode": {"const": mode},
                "visualProjectRef": {"const": "none"},
                "scale": copy.deepcopy(scale),
            },
            "required": ["entityId", "assetMode", "visualProjectRef", "scale"],
        })
    return {"oneOf": [authored, distinct, reuse, *non_sprite_branches]} if nonitem_id["enum"] else authored


def _visual_repair_schema(entity_ids: list[str], equipment_overlay_required: bool = False, item_body_id: str | None = None) -> dict[str, Any]:
    # itemPatch is partial: Repair returns only the visual fields it is fixing.
    # Omitted fields stay frozen - the deterministic merge completes the patch from
    # the previous kit before applying; valid design remains frozen.
    full_item = _visual_item_schema()
    partial_item = {
        "type": "object",
        "additionalProperties": False,
        "properties": full_item["properties"],
        "minProperties": 1,
    }
    properties: dict[str, Any] = {
        "schema": {"const": VISUAL_REPAIR_PATCH_SCHEMA},
        "itemPatch": {"anyOf": [partial_item, {"type": "null"}]},
        "entitiesUpsert": {"type": "array", "items": _visual_entity_schema(entity_ids, item_body_id), "maxItems": len(entity_ids)},
        "entityIdsDelete": {"type": "array", "items": {"type": "string", "enum": entity_ids}, "maxItems": len(entity_ids)},
        "entityIndicesDelete": {"type": "array", "description": "Zero-based array index values into the previous entities array to delete; structural positions, not time or size.", "items": {"type": "integer", "minimum": 0, "maximum": max(0, len(entity_ids) * 2)}, "maxItems": max(1, len(entity_ids) * 2)},
        "note": {"type": "string", "minLength": 1, "maxLength": 500},
    }
    required = ["schema", "itemPatch", "entitiesUpsert", "entityIdsDelete", "entityIndicesDelete", "note"]
    if equipment_overlay_required:
        properties["equipOverlayPatch"] = {"anyOf": [_visual_equip_overlay_schema(), {"type": "null"}]}
        required.insert(2, "equipOverlayPatch")
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def _scoped_visual_patch_node(schema: Mapping[str, Any], paths: list[str]) -> dict[str, Any]:
    """Project only exact permitted descendants; canonical admission stays full."""
    if "" in paths:
        return copy.deepcopy(dict(schema))
    properties = {}
    for field, child in (schema.get("properties") or {}).items():
        relative = [value for path in paths
                    if (value := json_path_relative(path, json_path_child("", field))) is not None]
        if relative:
            properties[field] = _scoped_visual_patch_node(child, relative)
    if "properties" not in schema:
        return copy.deepcopy(dict(schema))
    return {"type": "object", "additionalProperties": False, "properties": properties, "required": list(properties)}


def _scoped_visual_repair_schema(
    entity_ids: list[str], equipment_overlay_required: bool, item_body_id: str,
    scope: Mapping[str, Any], previous: Any,
) -> dict[str, Any]:
    full = _visual_repair_schema(entity_ids, equipment_overlay_required, item_body_id)
    permissions = scope.get("fieldPermissions") or {}
    properties = {key: copy.deepcopy(full["properties"][key]) for key in ("schema", "note")}
    for key, paths_key, owner in (("itemPatch", "itemPaths", _visual_item_schema()),
                                  ("equipOverlayPatch", "equipOverlayPaths", _visual_equip_overlay_schema())):
        paths = permissions.get(paths_key) or []
        if paths and key in full["properties"]:
            properties[key] = {"anyOf": [_scoped_visual_patch_node(owner, paths), {"type": "null"}]}
    source = previous if isinstance(previous, Mapping) else {}
    rows = {}
    raw_rows = source.get("entities")
    source_rows = raw_rows if isinstance(raw_rows, list) else []
    for row in source_rows:
        if isinstance(row, Mapping) and isinstance(row.get("entityId"), str):
            rows.setdefault(row["entityId"], row)
    entity_schema = _visual_entity_schema(entity_ids, item_body_id)
    branches = entity_schema.get("oneOf") or [entity_schema]
    variants = []
    for permission in permissions.get("entities") or []:
        entity_id, paths = permission["entityId"], permission["paths"]
        old = rows.get(entity_id, {})
        for branch in branches:
            props = branch["properties"]
            if entity_id not in props["entityId"]["enum"]:
                continue
            if any(field not in paths and "" not in paths and field in old and old[field] != props[field].get("const")
                   for field in ("assetMode", "visualProjectRef")):
                continue
            partial = _scoped_visual_patch_node(branch, paths)
            partial["properties"]["entityId"] = {"const": entity_id}
            partial["required"] = list(dict.fromkeys([*partial.get("required", []), "entityId"]))
            if partial not in variants:
                variants.append(partial)
    if variants:
        properties["entitiesUpsert"] = {"type": "array", "items": variants[0] if len(variants) == 1 else {"anyOf": variants}, "maxItems": len(permissions.get("entities") or [])}
    for key, scope_key in (("entityIdsDelete", "deletableEntityIds"), ("entityIndicesDelete", "deletableEntityIndices")):
        allowed = scope.get(scope_key) or []
        if allowed:
            properties[key] = copy.deepcopy(full["properties"][key])
            properties[key]["items"] = {"type": "integer" if key == "entityIndicesDelete" else "string", "enum": list(allowed)}
    return {"type": "object", "additionalProperties": False, "properties": properties, "required": list(properties)}


def _expand_scoped_visual_repair_patch(patch: Any, previous: Any, scope: Mapping[str, Any], entity_ids: list[str]) -> Any:
    """Lossless transport completion before the unchanged frozen-first filter."""
    if not isinstance(patch, dict):
        return patch
    out = copy.deepcopy(patch)
    source = previous if isinstance(previous, Mapping) else {}
    canonical = _visual_repair_schema(entity_ids, bool(scope.get("equipmentOverlayRequired")))
    for key in canonical["required"]:
        if key not in out and key not in ("schema", "note"):
            out[key] = [] if canonical["properties"][key].get("type") == "array" else None
    # Complete only existing authored fields, never invent absent design choices.
    def complete(old: Any, new: Any) -> Any:
        if not isinstance(old, Mapping) or not isinstance(new, Mapping):
            return copy.deepcopy(new)
        return {**copy.deepcopy(dict(old)), **{key: complete(old.get(key), value) for key, value in new.items()}}
    if isinstance(out.get("itemPatch"), dict):
        original_item = source.get("item")
        out["itemPatch"] = complete(original_item, out["itemPatch"])
        if isinstance(original_item, Mapping):
            out["itemPatch"] = _drop_schema_forbidden_mutable_fields(
                original_item, out["itemPatch"],
                mutable_paths=tuple((scope.get("fieldPermissions") or {}).get("itemPaths") or []),
                schema=_visual_item_schema(), audit_path="", accepted=[])
    if isinstance(out.get("equipOverlayPatch"), dict):
        out["equipOverlayPatch"] = complete(source.get("equipOverlay"), out["equipOverlayPatch"])
    by_id = {}
    raw_rows = source.get("entities")
    source_rows = raw_rows if isinstance(raw_rows, list) else []
    for row in source_rows:
        if isinstance(row, Mapping) and isinstance(row.get("entityId"), str):
            by_id.setdefault(row["entityId"], row)
    for index, row in enumerate(out.get("entitiesUpsert") or []):
        if isinstance(row, Mapping):
            merged = complete(by_id.get(row.get("entityId")), row)
            # Invalid extra source keys are removed by the existing exact-scope
            # structural-deletion filter, not advertised as output grammar.
            permitted = next((entry["paths"] for entry in (scope.get("fieldPermissions") or {}).get("entities") or [] if entry["entityId"] == row.get("entityId")), [])
            merged = _drop_schema_forbidden_mutable_fields(by_id.get(row.get("entityId"), {}), merged,
                mutable_paths=tuple(permitted), schema=_visual_entity_schema(entity_ids), audit_path="", accepted=[])
            out["entitiesUpsert"][index] = merged
    return out


def _response_schema(entity_ids: list[str], equipment_overlay_required: bool = False, item_body_id: str | None = None) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "schema": {"const": VISUAL_KIT_SCHEMA},
        "item": _visual_item_schema(),
        "entities": {"type": "array", "items": _visual_entity_schema(entity_ids, item_body_id), "minItems": len(entity_ids), "maxItems": len(entity_ids)},
        "animationPlan": {"type": "string", "maxLength": 1200, "description": "Optional advisory presentation intent for later generators; never executable or a Repair requirement."},
    }
    required = ["schema", "item", "entities"]
    if equipment_overlay_required:
        properties["equipOverlay"] = _visual_equip_overlay_schema()
        required.insert(2, "equipOverlay")
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def _runtime_card(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    from infini_local.core.runtime_authoring.capability_registry import (
        CAPABILITY_REGISTRY,
        CONTROLLER_OPCODE,
        MOVEMENT_OPCODE,
        PROJECTILE_MODIFIER_COMPONENTS,
    )
    runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), Mapping) else {}
    events_by_entity: dict[str, list[str]] = {}
    for row in runtime_event_inventory(data):
        if isinstance(row, Mapping):
            events_by_entity.setdefault(str(row.get("entityId") or ""), []).append(str(row.get("event") or ""))
    rows: list[dict[str, Any]] = []
    for entity in runtime.get("entities") or []:
        if not isinstance(entity, Mapping):
            continue
        movement = dict(entity["movement"]) if isinstance(entity.get("movement"), Mapping) else {}
        controller = dict(entity["controller"]) if isinstance(entity.get("controller"), Mapping) else {}
        # Explain exact accepted drivers from their canonical owner, not a
        # name/category classifier or a second geometry/representation registry.
        driver_meanings = {}
        for slot, driver, opcodes in (("movement", movement, MOVEMENT_OPCODE), ("controller", controller, CONTROLLER_OPCODE)):
            name = driver.get("name")
            capability = CAPABILITY_REGISTRY.get(name) if type(name) is str else None
            if capability is not None and capability.component_slot == slot and type(driver.get("code")) is int and opcodes.get(capability.name) == driver["code"]:
                driver_meanings[slot] = capability.summary
        rows.append({
            "id": str(entity.get("id") or ""),
            "kind": str(entity.get("kind") or ""),
            "visualRole": str(entity.get("visualRole") or ""),
            "movement": copy.deepcopy(dict(movement)),
            "controller": copy.deepcopy(dict(controller)),
            "driverMeaningReadOnly": driver_meanings,
            **({"spriteDependenciesReadOnly": requirement} if (requirement := front_hand_sprite_requirement(entity)) is not None else {}),
            "modifierMeaningReadOnly": {
                member: CAPABILITY_REGISTRY[fn].summary for fn, member in PROJECTILE_MODIFIER_COMPONENTS.items() if member in entity
            } | ({"whipUsesOwnerGravity": CAPABILITY_REGISTRY["orient_whip_to_owner_gravity"].summary} if entity.get("whipUsesOwnerGravity") is True else {}),
            "events": sorted(set(events_by_entity.get(str(entity.get("id") or ""), []))),
            "hitbox": copy.deepcopy(entity.get("hitbox") or {}),
            **{field: copy.deepcopy(entity[field]) for field in ("spawn", "lifetimeTicks", "collision", "hitboxCurve", *PROJECTILE_MODIFIER_COMPONENTS.values(), "whipUsesOwnerGravity") if field in entity},
        })
    return rows


def _presentation_packet_context(data: Mapping[str, Any], runtime_rows: list[dict[str, Any]]) -> dict[str, Any]:
    from infini_local.pipelines.sprite_contracts import sprite_contract_for
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), Mapping) else {}
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), Mapping) else {}
    mechanics = {
        "gameplay": {field: copy.deepcopy(gameplay[field]) for field in ("itemScale", "width", "height", "useTime", "useAnimation", "reuseDelay") if field in gameplay},
        **{field: copy.deepcopy(runtime[field]) for field in ("itemEntityId", "primaryEntityId", "primaryOwner", "itemUse", "itemContact", "bindings") if field in runtime},
    }
    canvases = _visual_item_schema()["properties"]["preferredCanvasSize"]["enum"]
    roles = {"item", *("runtime:" + row["visualRole"] for row in runtime_rows if row["kind"] != "item_body")}
    fill_fields = ("targetFill", "minFill", "maxFill", "marginPx", "cropPadPx", "targetLongAxisPx", "alphaMode")
    fill = {}
    for role in sorted(roles):
        fill[role] = {}
        for canvas in canvases:
            contract = sprite_contract_for(role, canvas)
            fill[role][str(canvas)] = {field: copy.deepcopy(contract[field]) for field in fill_fields}
    return {
        "acceptedPresentationMechanicsReadOnly": mechanics,
        "spritePresentationReadOnly": {
            "placedBody": {
                "operation": "present_placed_item_sprite",
                **{key: copy.deepcopy(value) for key, value in CAPABILITY_REGISTRY["present_placed_item_sprite"].prompt_card().items() if key == "params"},
                "meaning": CAPABILITY_REGISTRY["present_placed_item_sprite"].summary,
                "ownership": "Accepted bindings[].usePolicy.action.placement.placedBody transforms are immutable gameplay-owned facts. Visual designs the existing root item PNG only: no additional placed PNG/project, source flag, placement entity, or redesign of these transforms. Its full-frame pivot is independent of held grip, forwardAngleDegrees and dropped-item worldScale. An absent placedBody is native presentation, never infer this operation from parents or furniture appearance.",
            },
            "units": "R=renderSizePx is the larger complete final frame side in base world pixels, not alpha-bbox, hitbox, requested canvas or physical shaft/tip length. C is the actual loaded final frame max-side. G=gameplay.itemScale, W=item.worldScale, I=item.inventoryScale, D=hitbox.drawScale, E=entity.scale and current P=Projectile.scale are independent dimensionless multipliers; Visual cannot edit G or D.",
            "axis": "forwardAngleDegrees is the final PNG local forward-axis in degrees: 0=+X, positive clockwise in y-down coordinates, before facing/gravity flips. It describes pixels, not AI movement. Describe this pose in the same authored prompt; reuse inherits root pixels and axis, never a second inferred axis.",
            "heldRootVisibility": {
                "hideUseGraphic": CAPABILITY_REGISTRY["configure_item_use"].params["hideUseGraphic"].description,
                "customHeldSprite": CAPABILITY_REGISTRY["configure_item_use"].params["customHeldSprite"].description,
                "wireHint": "runtimeProgram.itemUse.releaseTiming",
            },
            "formulas": {
                "q": "R / max(actual final PNG frame width, height)",
                "inventory": "s_inventory * min(1, caller inventory frame max-side / C) * I; unchanged, no q",
                "world": "q_item * s_world * W",
                "held": "q_item * player.GetAdjustedItemScale(held) (G already included once)",
                "heldRegistryOnly": "q_item * baseScale * clamp(G, .25, 4)",
                "body": "q_selected * P when accepted hitboxCurve.mirrorToSprite=true or visualScaleCurve is present, with P=D*E*curveScale(active age) from that explicit visual owner; otherwise q_selected * clamp(P, .1, 8). No new curve or mirror is inferred.",
                "liveBodyCopy": "q_selected * clamp(P, .1, 8) * slot.Scale",
                "detachedBodyCopy": "q_selected * existing dimensionless pose/slot multiplier; capture/network pose remains dimensionless",
                "visibleAlphaExtent": "alpha-bbox pixels * q_selected * independent draw multipliers",
                "equalHeldBody": "Shared root guarantees equal base frame size, not final size: with neutral caller modifiers equality requires G == clamp(D*E, .1, 8), or G == D*E*curveScale(active age) for an accepted explicit mirror or visualScaleCurve. An independent hitbox curve does not multiply visual scale. Never change accepted gameplay to force equality.",
            },
            "frontHand": "Only explicit move_front_hand (opcode 20) attaches to the native front hand H. Author owns collision center C = H + aimedAxis * hitboxOffsetPx, aimMode, durationTicks and stretch; never derive mechanics from PNG size/axis/grip. For sprite modes require selected R, forwardAngleDegrees and final-canvas atomic grip: reuse_item_icon selects item.grip with no duplicate entity metadata; a distinct baked_sprite owns its entity grip. no_asset/runtime_geometry require no PNG grip; geometry stays at the authored collision center. Describe the actual hand-contact region in that owner's art prompt. Repair only the diagnosed owner leaf, never accepted gameplay, mode or valid coordinates.",
            "handContactGeometry": "For explicit move_front_hand, native none-to-full stretch moves the hand only 6px (lengths 4..10px), not a long thrust. The sprite grip stays on H; hitboxOffsetPx does not extend the visible body. Compare the signed distance from grip to the authored contact region, projected along the final PNG forward axis using the effective multiplier from formulas.body: R/C * clamp(P, .1, 8), or its explicit curve/mirror exception, with the immutable hitbox center offset and rectangle. Choose art framing, grip and size coherently in that fixed geometry; never move only the picture to pretend to extend collision reach. A mismatch needing different motion/collision is not repairable by Visual. Native parent texture size is read-only calibration, not automatic reach inheritance or a mandatory size floor. In Repair preserve valid art and mechanics outside exact permissions.",
            "ownership": "Root item owns R/canvas/axis for item_body and reuse_item_icon. A distinct baked entity owns R/canvas/axis. no_asset/runtime_geometry own none. Dedicated impact, overlay, material world widths, textured paths and collision/movement are outside this main-PNG conversion.",
            "fill": "Canonical bake fill/padding below describes artwork span inside the requested frame, not world size. Baked final frame and alpha extent may differ; no post-image axis/bbox inference. Runtime tip anchors remain existing gameplay geometry, not measured PNG tips.",
            "geometryCoverage": "Match the intended physical body to the accepted driverMeaningReadOnly and exact movement/controller params. A single center/tip PNG does not follow a curved collision path. runtime_geometry can draw the implemented beam/whip collision geometry directly; baked_sprite/reuse_item_icon draw a single PNG rather than the full collision path. texturedPath is an independent VFX renderer for compatible accepted path sources. Optionally describe intended composition in advisory animationPlan, but later VFX is not yet authored: do not claim a slot already exists. no_asset leaves the entity body undrawn; choose it for deliberate invisibility or an explicitly intended alternate presentation. There is no automatic mode conversion, sprite stretching, path or VFX-slot insertion. Do not alter accepted mechanics or visibility to fit the art.",
            "sourceCalibration": "Use available parent raw.spriteReference loaded texture/currentFrame or generatedParent.visual.renderSizePx as read-only size calibration, not a required copy. Consider chosen renderSizePx together with canonical bake fill/padding and intended visible alpha extent; canvas resolution alone does not set body size. Missing reference or alpha bounds are unknown: never substitute hitbox/collider dimensions, fallback textures or an inferred parent size. Accepted useTime/useAnimation, spawn, lifetimeTicks and collision constrain animation description only; do not change gameplay or frozen Repair fields.",
            "requiredMetadata": "Explicitly choose required presentation fields. No defaults, clamps, inferred axis or rebake.",
        },
        # This selected role roster is a runtime fact, not instruction authority.
        # All other presentation members above are invariant application rules.
        "bakeFillByProcessingRole": fill,
    }


def _known_baked_project_target_schema(
    row: Any, entity_ids: list[str], item_body_id: str,
) -> Mapping[str, Any] | None:
    """Diagnose only an exact known baked ownership transition, never infer one."""
    if not isinstance(row, Mapping) or not item_body_id or item_body_id not in entity_ids:
        return None
    entity_id = row.get("entityId")
    if type(entity_id) is not str or entity_id not in entity_ids or row.get("assetMode") != "baked_sprite":
        return None
    target_ref = "item" if entity_id == item_body_id else "entity"
    source_ref = "entity" if target_ref == "item" else "item"
    if row.get("visualProjectRef") != source_ref:
        return None
    schema = _visual_entity_schema(entity_ids, item_body_id)
    branches = schema.get("oneOf") or [schema]
    selected = [branch for branch in branches
                if branch["properties"]["assetMode"].get("const") == "baked_sprite"
                and branch["properties"]["visualProjectRef"].get("const") == target_ref
                and entity_id in branch["properties"]["entityId"]["enum"]]
    return selected[0] if len(selected) == 1 else None


def _validate_kit(
    raw: Any,
    entity_ids: list[str],
    item_body_id: str,
    *,
    equipment_overlay_required: bool = False,
    accepted_data: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    if isinstance(raw, MalformedVisualDirectorOutput):
        return None, [{"path": "$", "message": f"malformed_json: {raw.error}"}]
    if not isinstance(raw, dict):
        return None, [{"path": "$", "message": "Visual Director response must be an object"}]
    # Declared lossless normalization: the exact asset mode plus exact entity id
    # uniquely determines project ownership. The only missing-mode Fix remains
    # the complete root item design -> baked inventory project case.
    source_rows_raw = raw.get("entities")
    source_rows = source_rows_raw if isinstance(source_rows_raw, list) else []
    candidate = copy.deepcopy(raw)
    candidate_rows_raw = candidate.get("entities")
    candidate_rows: list[Any] = candidate_rows_raw if isinstance(candidate_rows_raw, list) else []
    for row in candidate_rows:
        if not isinstance(row, dict):
            continue
        entity_id = str(row.get("entityId") or "")
        mode = str(row.get("assetMode") or "").strip().lower()
        design = candidate.get("item") if entity_id == item_body_id else row
        complete = isinstance(design, Mapping) and all(str(design.get(field) or "").strip() for field in ("prompt", "silhouette", "visualIdentity"))
        if not mode and entity_id == item_body_id and complete:
            mode = "baked_sprite"
            row["assetMode"] = mode
        if mode and not str(row.get("visualProjectRef") or "").strip():
            row["visualProjectRef"] = (
                "item" if entity_id == item_body_id or mode == "reuse_item_icon"
                else "entity" if mode == "baked_sprite"
                else "none"
            )
    raw = candidate
    schema_errors = strict_schema_errors(raw, _response_schema(entity_ids, equipment_overlay_required, item_body_id))
    for index, source_row in enumerate(source_rows):
        target_schema = _known_baked_project_target_schema(source_row, entity_ids, item_body_id)
        if target_schema is None:
            continue
        # The authored ref is still invalid and must be chosen by Repair. The
        # accepted identity/mode fixes its ownership domain, so diagnose against
        # that exact schema: old inapplicable leaves or new missing leaves, not
        # a false entityId error from the opposite project branch. No values are
        # corrected/materialized here; unknown/missing discriminators stay on
        # the ordinary strict path above.
        row_path = f"$.entities[{index}]"
        schema_errors = [error for error in schema_errors
                         if json_path_relative(str(error.get("path") or ""), row_path) is None]
        schema_errors.extend(strict_schema_errors(source_row, target_schema, path=row_path))
    for schema_error in schema_errors:
        if json_path_relative(str(schema_error.get("path") or ""), "$.animationPlan") is not None:
            continue  # Advisory intent never spends Visual Repair.
        errors.append({
            "path": str(schema_error.get("path") or "$"),
            "message": f"schema {schema_error.get('kind')}: expected {schema_error.get('expected')!r}",
        })
    if raw.get("schema") != VISUAL_KIT_SCHEMA:
        errors.append({"path": "$.schema", "message": f"expected {VISUAL_KIT_SCHEMA}"})
    item = raw.get("item")
    if not isinstance(item, dict):
        errors.append({"path": "$.item", "message": "required object"})
    else:
        for field in ("prompt", "silhouette", "visualIdentity"):
            if not str(item.get(field) or "").strip():
                errors.append({"path": f"$.item.{field}", "message": "required non-empty string"})
        if not isinstance(item.get("palette"), list) or not [x for x in item.get("palette", []) if str(x).strip()]:
            errors.append({"path": "$.item.palette", "message": "at least one palette entry required"})
    if equipment_overlay_required:
        overlay = raw.get("equipOverlay")
        if not isinstance(overlay, dict):
            errors.append({"path": "$.equipOverlay", "message": "equipment item requires a separate authored overlay object"})
        else:
            for field in ("prompt", "silhouette", "visualIdentity"):
                if not str(overlay.get(field) or "").strip():
                    errors.append({"path": f"$.equipOverlay.{field}", "message": "required non-empty string"})
    rows = raw.get("entities")
    if not isinstance(rows, list):
        errors.append({"path": "$.entities", "message": "required array"})
        rows = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        path = f"$.entities[{index}]"
        if not isinstance(row, dict):
            errors.append({"path": path, "message": "must be object"})
            continue
        entity_id = str(row.get("entityId") or "")
        if entity_id not in entity_ids:
            errors.append({"path": path + ".entityId", "message": f"unknown entity id {entity_id!r}"})
        elif entity_id in seen:
            errors.append({"path": path + ".entityId", "message": "duplicate entity id"})
        seen.add(entity_id)
        mode = str(row.get("assetMode") or "").strip().lower()
        project_ref = str(row.get("visualProjectRef") or "").strip().lower()
        if mode not in _ALLOWED_ASSET_MODES:
            errors.append({"path": path + ".assetMode", "message": f"unsupported mode {mode!r}"})
        if entity_id == item_body_id:
            if mode != "baked_sprite":
                errors.append({"path": path + ".assetMode", "message": f"item entity {item_body_id!r} must use baked_sprite"})
            if project_ref != "item":
                errors.append({"path": path + ".visualProjectRef", "message": "item body must reference the single item visual project"})
        elif mode == "baked_sprite" and project_ref != "entity":
            errors.append({"path": path + ".visualProjectRef", "message": "distinct baked entity must own the entity visual project"})
        elif mode == "reuse_item_icon" and project_ref != "item":
            errors.append({"path": path + ".visualProjectRef", "message": "reuse_item_icon must reference the item visual project"})
        elif mode in {"runtime_geometry", "no_asset"} and project_ref != "none":
            errors.append({"path": path + ".visualProjectRef", "message": f"{mode} must not claim a sprite project"})
    missing = [entity_id for entity_id in entity_ids if entity_id not in seen]
    if missing:
        errors.append({"path": "$.entities", "message": "missing entity rows: " + ", ".join(missing)})
    if len(rows) != len(entity_ids):
        errors.append({"path": "$.entities", "message": f"expected exactly {len(entity_ids)} rows"})
    if accepted_data is not None:
        dependencies = front_hand_sprite_errors(accepted_data, kit=raw)
        seen_paths = {error["path"] for error in errors}
        errors.extend(error for error in dependencies if error["path"] not in seen_paths)
    return (copy.deepcopy(raw) if not errors else None), errors


def _build_visual_repair_scope(
    raw: Any,
    errors: list[dict[str, Any]],
    entity_ids: list[str],
    item_body_id: str,
    *,
    equipment_overlay_required: bool = False,
) -> dict[str, Any]:
    rows_raw = raw.get("entities") if isinstance(raw, Mapping) else None
    rows = rows_raw if isinstance(rows_raw, list) else []
    original_indices: dict[str, int] = {}
    for index, row in enumerate(rows):
        if isinstance(row, Mapping) and row.get("entityId") in entity_ids:
            original_indices.setdefault(row["entityId"], index)
    entity_child_error_indices: set[int] = set()
    for diagnostic in errors:
        diagnostic_path = str(diagnostic.get("path") or "")
        child_match = __import__("re").match(r"^\$\.entities\[(\d+)\]", diagnostic_path)
        if child_match and json_path_relative(diagnostic_path, child_match.group(0)):
            entity_child_error_indices.add(int(child_match.group(1)))
    mutable_ids: set[str] = set()
    delete_indices: set[int] = set()
    missing_ids: set[str] = set()
    item_mutable = False
    overlay_mutable = False
    item_paths: set[str] = set()
    overlay_paths: set[str] = set()
    entity_paths: dict[str, set[str]] = {}
    whole_response = not isinstance(raw, Mapping)

    def grant_entity(entity_id: str, relative: str) -> None:
        if entity_id:
            mutable_ids.add(entity_id)
            entity_paths.setdefault(entity_id, set()).add(relative.strip("."))

    for error in errors:
        path = str(error.get("path") or "$")
        message = str(error.get("message") or "")
        if path == "$":
            whole_response = True
        relative_item_path = json_path_relative(path, "$.item")
        if relative_item_path is not None:
            item_mutable = True
            item_paths.add(relative_item_path)
        relative_overlay_path = json_path_relative(path, "$.equipOverlay")
        if equipment_overlay_required and relative_overlay_path is not None:
            overlay_mutable = True
            overlay_paths.add(relative_overlay_path)
        match = __import__("re").match(r"^\$\.entities\[(\d+)\]", path)
        relative = json_path_relative(path, match.group(0)) if match else None
        if match and relative is not None:
            index = int(match.group(1))
            if not relative and index in entity_child_error_indices and "schema one_of" in message:
                # oneOf emits an aggregate row marker alongside exact branch
                # diagnostics. The aggregate must not widen exact field scope.
                continue
            if 0 <= index < len(rows) and isinstance(rows[index], Mapping):
                entity_id = str(rows[index].get("entityId") or "")
                if entity_id in entity_ids:
                    if original_indices[entity_id] != index:
                        # The first occurrence owns ID-keyed leaf repairs. A
                        # later duplicate's errors grant only original-index
                        # deletion, never permissions on the first row.
                        delete_indices.add(index)
                        continue
                    grant_entity(entity_id, relative)
                else:
                    delete_indices.add(index)
            else:
                delete_indices.add(index)
        if path == "$.entities":
            if "missing entity rows:" in message:
                tail = message.split("missing entity rows:", 1)[1]
                for value in tail.split(","):
                    entity_id = value.strip()
                    if entity_id in entity_ids:
                        missing_ids.add(entity_id)
                        grant_entity(entity_id, "")
            if "item entity" in message:
                grant_entity(item_body_id, "assetMode")
            seen: dict[str, int] = {}
            for index, row in enumerate(rows):
                if not isinstance(row, Mapping):
                    delete_indices.add(index)
                    continue
                entity_id = str(row.get("entityId") or "")
                if entity_id not in entity_ids:
                    delete_indices.add(index)
                elif entity_id in seen:
                    delete_indices.add(index)
                else:
                    seen[entity_id] = index
            for entity_id in entity_ids:
                if entity_id not in seen:
                    grant_entity(entity_id, "")
    if whole_response:
        item_mutable = True
        overlay_mutable = equipment_overlay_required
        item_paths.add("")
        if equipment_overlay_required:
            overlay_paths.add("")
        for entity_id in entity_ids:
            grant_entity(entity_id, "")
        delete_indices.update(range(len(rows)))
    replacement_transactions: list[dict[str, Any]] = []
    if not whole_response and len(delete_indices) == 1 and len(missing_ids) == 1:
        replacement_transactions.append({
            "entityId": next(iter(missing_ids)),
            "replaceIndex": next(iter(delete_indices)),
        })
    return {
        "schema": "infini.visual-repair-scope.v3",
        "itemMutable": item_mutable,
        "equipmentOverlayRequired": equipment_overlay_required,
        "equipOverlayMutable": overlay_mutable,
        "mutableEntityIds": sorted(mutable_ids),
        "deletableEntityIds": [],
        "deletableEntityIndices": sorted(delete_indices),
        "entityReplacementTransactions": replacement_transactions,
        "fieldPermissions": {
            "itemPaths": sorted(item_paths),
            "equipOverlayPaths": sorted(overlay_paths),
            "entities": [
                {"entityId": entity_id, "paths": sorted(paths)}
                for entity_id, paths in sorted(entity_paths.items())
            ],
        },
        "errorPaths": [str(row.get("path") or "$") for row in errors],
    }


def _visual_repair_context(raw: Any, scope: Mapping[str, Any]) -> dict[str, Any]:
    source = raw if isinstance(raw, Mapping) else {}
    mutable_ids = set(str(value) for value in scope.get("mutableEntityIds") or [])
    rows = source.get("entities") if isinstance(source.get("entities"), list) else []
    return {
        "malformedRawText": raw.raw_text if isinstance(raw, MalformedVisualDirectorOutput) else "",
        "broken": {
            "item": copy.deepcopy(source.get("item")) if scope.get("itemMutable") else None,
            "equipOverlay": copy.deepcopy(source.get("equipOverlay")) if scope.get("equipOverlayMutable") else None,
            "entities": [copy.deepcopy(row) for row in rows if isinstance(row, Mapping) and str(row.get("entityId") or "") in mutable_ids],
        },
        "validReadOnly": {
            "item": copy.deepcopy(source.get("item")) if not scope.get("itemMutable") else None,
            "equipOverlay": copy.deepcopy(source.get("equipOverlay")) if scope.get("equipmentOverlayRequired") and not scope.get("equipOverlayMutable") else None,
            "entities": [copy.deepcopy(row) for row in rows if isinstance(row, Mapping) and str(row.get("entityId") or "") not in mutable_ids],
            **({"animationPlan": source["animationPlan"]} if isinstance(source.get("animationPlan"), str) else {}),
        },
    }


def _visual_filter_ignored(path: str, requested: Any, preserved: Any, reason: str) -> dict[str, Any]:
    return {"path": path, "reason": reason, "requested": copy.deepcopy(requested), "preserved": copy.deepcopy(preserved)}


def _drop_schema_forbidden_mutable_fields(
    source: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    mutable_paths: tuple[str, ...],
    schema: Mapping[str, Any],
    audit_path: str,
    accepted: list[str],
) -> dict[str, Any]:
    """Delete only exact mutable fields forbidden by the strict row schema."""

    out: dict[str, Any] = copy.deepcopy(dict(candidate))
    branches = [row for row in schema.get("oneOf") or [] if isinstance(row, Mapping)]
    if branches:
        # Select only a unique exact literal discriminator branch. Never use the
        # union of fields or a smallest-error guess to authorize deletion.
        selected = []
        for branch in branches:
            constants = {field: spec["const"] for field, spec in (branch.get("properties") or {}).items()
                         if isinstance(spec, Mapping) and "const" in spec}
            # candidate has already passed frozen merge; only permitted repairs
            # can change its discriminator. Select that effective branch, not
            # the source branch whose dependent fields may now be inapplicable.
            if constants and all(field in out and type(out[field]) is type(value) and out[field] == value
                                 for field, value in constants.items()):
                selected.append(branch)
        if len(selected) != 1:
            return out
        schema = selected[0]
    strict_shapes = [schema]
    if not strict_shapes or any(row.get("additionalProperties") is not False for row in strict_shapes):
        return out
    valid_fields = {
        str(field)
        for row in strict_shapes
        for field in (row.get("properties") or {})
    }
    forbidden_fields = {
        str(field) for field in source
        if field not in valid_fields
        and json_path_child("", str(field)) in mutable_paths
    }
    for field in sorted(forbidden_fields):
        if field in source and field in out:
            out.pop(field, None)
            accepted.append(json_path_child(audit_path, field))
    # Nested strict objects (the atomic grip) still repair exact leaves: an extra
    # child key must be removable without granting either valid coordinate.
    for field, child_schema in (schema.get("properties") or {}).items():
        child_paths = tuple(relative for path in mutable_paths
                            if (relative := json_path_relative(path, json_path_child("", field))))
        if child_paths and isinstance(source.get(field), Mapping) and isinstance(out.get(field), Mapping):
            out[field] = _drop_schema_forbidden_mutable_fields(
                source[field], out[field], mutable_paths=child_paths, schema=child_schema,
                audit_path=json_path_child(audit_path, field), accepted=accepted,
            )
    return out


def _filter_visual_repair_patch(
    previous: Any,
    patch: Mapping[str, Any],
    scope: Mapping[str, Any],
    entity_ids: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    equipment_overlay_required = bool(scope.get("equipmentOverlayRequired"))
    # Advisory prose is not a Repair edit target or a structural requirement.
    # Ignore any echoed advisory value before checking executable patch shape.
    patch = {key: value for key, value in patch.items() if key != "animationPlan"}
    schema_errors = strict_schema_errors(patch, _visual_repair_schema(entity_ids, equipment_overlay_required))
    filtered = {
        "schema": VISUAL_REPAIR_PATCH_SCHEMA,
        "itemPatch": None,
        "entitiesUpsert": [],
        "entityIdsDelete": [],
        "entityIndicesDelete": [],
        "note": str(patch.get("note") or "deterministically filtered Visual Repair"),
    }
    if equipment_overlay_required:
        filtered["equipOverlayPatch"] = None
    if schema_errors:
        return filtered, {"schema": "infini.visual-repair-filter-report.v1", "ok": False, "errors": schema_errors, "acceptedPaths": [], "ignoredChanges": []}

    source = previous if isinstance(previous, Mapping) else {}
    mutable_ids = set(str(value) for value in scope.get("mutableEntityIds") or [])
    deletable_ids = set(str(value) for value in scope.get("deletableEntityIds") or [])
    deletable_indices = set(int(value) for value in scope.get("deletableEntityIndices") or [])
    raw_permissions = scope.get("fieldPermissions")
    permission_root: Mapping[str, Any] = raw_permissions if isinstance(raw_permissions, Mapping) else {}
    item_paths = tuple(str(value) for value in permission_root.get("itemPaths") or [])
    overlay_paths = tuple(str(value) for value in permission_root.get("equipOverlayPaths") or [])
    entity_permissions = {
        str(row.get("entityId") or ""): tuple(str(value) for value in row.get("paths") or [])
        for row in permission_root.get("entities") or [] if isinstance(row, Mapping)
    }
    ignored: list[dict[str, Any]] = []
    accepted: list[str] = []

    item_patch = patch.get("itemPatch")
    if item_patch is not None:
        original_item = source.get("item")
        if not scope.get("itemMutable"):
            ignored.append(_visual_filter_ignored("$.itemPatch", item_patch, original_item, "valid_item_block_frozen"))
        elif isinstance(original_item, Mapping):
            merged, row_ignored, row_accepted = merge_frozen_subtree(
                original_item, item_patch, mutable_paths=item_paths, audit_path="$.itemPatch", allow_additions=False,
            )
            filtered["itemPatch"] = merged
            ignored.extend(row_ignored)
            accepted.extend(row_accepted)
        else:
            filtered["itemPatch"] = copy.deepcopy(item_patch)
            accepted.append("$.itemPatch")

    # Strict Repair rows cannot repeat a schema-forbidden source field. Its
    # exact diagnostic path authorizes structural deletion instead of preserving
    # the invalid key through frozen merge.
    original_item = source.get("item")
    if scope.get("itemMutable") and isinstance(original_item, Mapping):
        candidate_item = filtered.get("itemPatch")
        repair_source: Mapping[str, Any] = candidate_item if isinstance(candidate_item, Mapping) else original_item
        filtered["itemPatch"] = _drop_schema_forbidden_mutable_fields(
            original_item,
            repair_source,
            mutable_paths=item_paths,
            schema=_visual_item_schema(),
            audit_path="$.itemPatch",
            accepted=accepted,
        )

    if equipment_overlay_required:
        overlay_patch = patch.get("equipOverlayPatch")
        original_overlay = source.get("equipOverlay")
        if overlay_patch is not None:
            if not scope.get("equipOverlayMutable"):
                ignored.append(_visual_filter_ignored("$.equipOverlayPatch", overlay_patch, original_overlay, "valid_equip_overlay_block_frozen"))
            elif isinstance(original_overlay, Mapping):
                merged, row_ignored, row_accepted = merge_frozen_subtree(
                    original_overlay,
                    overlay_patch,
                    mutable_paths=overlay_paths,
                    audit_path="$.equipOverlayPatch",
                    allow_additions=False,
                )
                filtered["equipOverlayPatch"] = merged
                ignored.extend(row_ignored)
                accepted.extend(row_accepted)
            else:
                filtered["equipOverlayPatch"] = copy.deepcopy(overlay_patch)
                accepted.append("$.equipOverlayPatch")
        if scope.get("equipOverlayMutable") and isinstance(original_overlay, Mapping):
            candidate_overlay = filtered.get("equipOverlayPatch")
            repair_overlay: Mapping[str, Any] = candidate_overlay if isinstance(candidate_overlay, Mapping) else original_overlay
            filtered["equipOverlayPatch"] = _drop_schema_forbidden_mutable_fields(
                original_overlay,
                repair_overlay,
                mutable_paths=overlay_paths,
                schema=_visual_equip_overlay_schema(),
                audit_path="$.equipOverlayPatch",
                accepted=accepted,
            )

    for index, entity_id in enumerate(patch.get("entityIdsDelete") or []):
        path = f"$.entityIdsDelete[{index}]"
        if str(entity_id) in deletable_ids:
            filtered["entityIdsDelete"].append(str(entity_id))
            accepted.append(path)
        else:
            ignored.append(_visual_filter_ignored(path, entity_id, entity_id, "valid_entity_delete_ignored"))
    rows_raw = source.get("entities")
    rows = rows_raw if isinstance(rows_raw, list) else []
    for index, source_index in enumerate(patch.get("entityIndicesDelete") or []):
        path = f"$.entityIndicesDelete[{index}]"
        numeric = int(source_index)
        if numeric in deletable_indices:
            filtered["entityIndicesDelete"].append(numeric)
            accepted.append(path)
        else:
            preserved = rows[numeric] if 0 <= numeric < len(rows) else None
            ignored.append(_visual_filter_ignored(path, numeric, preserved, "valid_entity_index_delete_ignored"))

    by_id: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if isinstance(row, Mapping) and str(row.get("entityId") or ""):
            by_id.setdefault(str(row["entityId"]), row)
    replacement_indices: dict[str, int] = {}
    for transaction in scope.get("entityReplacementTransactions") or []:
        if not isinstance(transaction, Mapping):
            continue
        entity_id = str(transaction.get("entityId") or "")
        replace_index = transaction.get("replaceIndex")
        if entity_id and isinstance(replace_index, int) and not isinstance(replace_index, bool):
            replacement_indices[entity_id] = replace_index
    for index, candidate in enumerate(patch.get("entitiesUpsert") or []):
        entity_id = str(candidate.get("entityId") or "")
        path = f"$.entitiesUpsert[{index}]"
        original = by_id.get(entity_id)
        if entity_id not in mutable_ids:
            if original is None or not json_values_equal(dict(candidate), dict(original)):
                ignored.append(_visual_filter_ignored(path, candidate, original, "independent_valid_entity_frozen"))
            continue
        if original is None:
            filtered["entitiesUpsert"].append(copy.deepcopy(candidate))
            accepted.append(path)
            replace_index = replacement_indices.get(entity_id)
            if replace_index is not None and replace_index in deletable_indices:
                if replace_index not in filtered["entityIndicesDelete"]:
                    filtered["entityIndicesDelete"].append(replace_index)
                accepted.append(f"$.entityReplacementTransactions[{entity_id}]")
            continue
        permissions = entity_permissions.get(entity_id, ())
        merged, row_ignored, row_accepted = merge_frozen_subtree(
            original, candidate, mutable_paths=permissions, audit_path=path, allow_additions=False,
        )
        ignored.extend(row_ignored)
        accepted.extend(row_accepted)
        merged = _drop_schema_forbidden_mutable_fields(
            original,
            merged,
            mutable_paths=permissions,
            schema=_visual_entity_schema(entity_ids),
            audit_path=path,
            accepted=accepted,
        )
        if not json_values_equal(merged, original):
            filtered["entitiesUpsert"].append(merged)

    filtered["entityIndicesDelete"] = sorted(set(filtered["entityIndicesDelete"]))
    return filtered, {
        "schema": "infini.visual-repair-filter-report.v1",
        "ok": True,
        "errors": [],
        "acceptedPaths": sorted(set(accepted)),
        "ignoredChanges": ignored,
        "filteredPatch": copy.deepcopy(filtered),
    }


def _apply_visual_repair_patch(
    previous: Any,
    patch: Mapping[str, Any],
    scope: Mapping[str, Any],
    entity_ids: list[str],
    *,
    return_audit: bool = False,
) -> Any:
    filtered, audit = _filter_visual_repair_patch(previous, patch, scope, entity_ids)
    if not audit.get("ok"):
        raise PlannerUnavailable("Visual Repair patch shape rejected: " + json.dumps(audit.get("errors", [])[:16], ensure_ascii=False))

    out = copy.deepcopy(dict(previous)) if isinstance(previous, Mapping) else {}
    out["schema"] = VISUAL_KIT_SCHEMA
    if filtered.get("itemPatch") is not None:
        out["item"] = copy.deepcopy(filtered["itemPatch"])
    if filtered.get("equipOverlayPatch") is not None:
        out["equipOverlay"] = copy.deepcopy(filtered["equipOverlayPatch"])
    rows = list(out.get("entities") or []) if isinstance(out.get("entities"), list) else []
    rows = [row for index, row in enumerate(rows) if index not in set(filtered.get("entityIndicesDelete") or [])]
    doomed = set(str(value) for value in filtered.get("entityIdsDelete") or [])
    rows = [row for row in rows if not isinstance(row, Mapping) or str(row.get("entityId") or "") not in doomed]
    original_indices: dict[str, int] = {}
    for index, row in enumerate(rows):
        if isinstance(row, Mapping) and str(row.get("entityId") or ""):
            original_indices.setdefault(str(row["entityId"]), index)
    for row in filtered.get("entitiesUpsert") or []:
        entity_id = str(row.get("entityId") or "")
        index = original_indices.get(entity_id)
        if index is None:
            original_indices[entity_id] = len(rows)
            rows.append(copy.deepcopy(row))
        else:
            rows[index] = copy.deepcopy(row)
    # Keep every other original slot, including undeleted malformed/duplicate
    # rows. An ID-keyed upsert repairs only its first surviving occurrence.
    out["entities"] = rows
    return (out, audit) if return_audit else out



def _request_visual_kit(
    data: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    repair_errors: list[dict[str, Any]] | None = None,
    previous: Any = None,
    repair_scope: Mapping[str, Any] | None = None,
) -> dict[str, Any] | MalformedVisualDirectorOutput:
    runtime_rows = _runtime_card(data)
    entity_ids = [row["id"] for row in runtime_rows]
    item_body_id = next((row["id"] for row in runtime_rows if row["kind"] == "item_body"), "")
    equipment_overlay = equipment_overlay_requirement(data)
    equipment_overlay_required = bool(equipment_overlay["required"])
    repair = repair_errors is not None
    scoped_repair = (repair and isinstance(repair_scope, Mapping) and "fieldPermissions" in repair_scope
                     and not any(error.get("path") == "$" for error in repair_errors or []))
    schema = (
        _scoped_visual_repair_schema(entity_ids, equipment_overlay_required, item_body_id, repair_scope or {}, previous)
        if scoped_repair else _visual_repair_schema(entity_ids, equipment_overlay_required, item_body_id)
        if repair
        else _response_schema(entity_ids, equipment_overlay_required, item_body_id)
    )
    response_format = llm_json_response_format(
        "infini_visual_kit_repair_patch" if repair else "infini_visual_kit_runtime_entities",
        schema=lambda: _provider_strict_projection(schema), strict=True, auto_preference="json_schema",
    )
    sent_schema = response_format["json_schema"]["schema"] if response_format and response_format.get("type") == "json_schema" else schema
    if repair:
        system = (
            "You are the conditional Visual Repair. Return only a narrow patch for exact invalid visual fields/rows. "
            "You may return a complete broken row; deterministic merge freezes every already-valid old field and keeps "
            "the exact repaired or newly missing fields. Extra rewrites are ignored. Runtime gameplay is immutable. "
            "The runtime entity with kind=item_body must use baked_sprite regardless of its entityId; set visualProjectRef=item and omit prompt/silhouette/visualIdentity; root item owns that design. "
            "Only another non-item_body entity that is the same physical object as item_body may use reuse_item_icon with visualProjectRef=item; never create a second visual project for it. "
            "Use assetModeCatalog as the exact PNG-delivery and runtime-draw contract. Return JSON only."
        )
        if isinstance(previous, MalformedVisualDirectorOutput):
            system += (
                " The previous response is malformed JSON. Repair its syntax and container only: preserve all "
                "recoverable visual fields and entity choices verbatim from malformedRawText; do not invent "
                "an absent design. Emit the complete broken visual response through the repair patch fields."
            )
        context = _visual_repair_context(previous, repair_scope or {})
        payload: dict[str, Any] = {
            "task": "Patch only exact invalid visualKit fields/rows.",
            "exactErrors": copy.deepcopy(repair_errors or []),
            "malformedRawText": context["malformedRawText"],
            "repairScope": copy.deepcopy(dict(repair_scope or {})),
            "brokenFragments": context["broken"],
            "validGeneratedContext": context["validReadOnly"],
            "parentFactsReadOnly": {
                "parentA": {"packet": raw_parent_card_for_llm(a, include_visual_reference=True)},
                "parentB": {"packet": raw_parent_card_for_llm(b, include_visual_reference=True)},
            },
            "runtimeEntitiesReadOnly": runtime_rows,
            "itemReadOnly": {
                "name": data.get("name"),
                "realization": copy.deepcopy(data.get("realization") or {}),
            },
            "equipmentOverlayReadOnly": copy.deepcopy(equipment_overlay),
            "assetModeCatalog": visual_asset_mode_catalog(),
            "rules": [
                "fill only fields listed in repairScope.fieldPermissions; optional unreported fields stay absent",
                visual_background_transport_rule(),
                "already-valid fields and independent rows are frozen; extra rewrites are ignored",
                "preserve valid literal parent composition and accepted runtime entity set",
                "the runtime entity with kind=item_body must use baked_sprite regardless of its entityId; set visualProjectRef=item and omit prompt/silhouette/visualIdentity; root item owns that design",
                "only another non-item_body entity that is the same physical object as item_body may use reuse_item_icon with visualProjectRef=item and must not author a second visual project",
                "when equipmentOverlayReadOnly.required is true, repair equipOverlayPatch as a separate wearable presentation asset",
            ],
            "responseSchema": sent_schema,
        }
    else:
        system = (
            "You are Visual Director for InfiniCrafterLocal. Design appearance only for the accepted runtime entities. "
            "Do not add, remove, merge, rename or reinterpret gameplay entities/events. Do not classify the item as a weapon family. "
            "Preserve literal parent objects and their physical relationships. For each exact entityId choose one finite assetMode: "
            "baked_sprite, reuse_item_icon, runtime_geometry, or no_asset. The entity with kind=item_body, regardless of its entityId, uses baked_sprite with visualProjectRef=item and only entityId/assetMode/visualProjectRef/scale; root item owns its prompt/silhouette/visualIdentity. "
            "A distinct baked entity uses visualProjectRef=entity and authors prompt/silhouette/visualIdentity. reuse_item_icon uses visualProjectRef=item and omits those fields; runtime_geometry/no_asset use visualProjectRef=none and omit them. "
            "Only another non-item_body entity that is the same physical object as item_body may use reuse_item_icon with visualProjectRef=item; never create a second visual project for it. "
            "Use assetModeCatalog as the exact PNG-delivery and runtime-draw contract. "
            "A baked sprite is mandatory delivery: never request or accept a placeholder. Return a strict JSON object with double-quoted JSON object keys and string values; no trailing commas or JavaScript expressions."
        )
        payload = {
            "task": "Author one visualKit for the accepted runtime program.",
            "item": {
                "name": data.get("name"),
                "realization": copy.deepcopy(data.get("realization") or {}),
            },
            "parents": {
                "parentA": {"packet": raw_parent_card_for_llm(a, include_visual_reference=True)},
                "parentB": {"packet": raw_parent_card_for_llm(b, include_visual_reference=True)},
            },
            "runtimeEntities": runtime_rows,
            "requiredEntityIds": entity_ids,
            "equipmentOverlayReadOnly": copy.deepcopy(equipment_overlay),
            "assetModeCatalog": visual_asset_mode_catalog(),
            "rules": [
                "appearance only; runtime program is immutable",
                "For a newly designed held item choose item.grip explicitly at its actual handle/contact point on the final item PNG canvas after crop/fit/padding, before facing/gravity flips. Both normalized coordinates are required together. Describe that same contact point in item.prompt; do not infer coordinates from an entityId or request image analysis.",
                "For a newly designed accessory choose equipOverlay.accessoryMount explicitly from chest/back/waist/shoulder/orbit to suit its authored appearance. It attaches the existing single PNG badge to the body pivot; it is not a full armor sheet or a behind-body occlusion guarantee. Optional omission selects the existing orbit presentation; never fill optional metadata during Repair unless its exact path is permitted.",
                "literal furniture, tools and materials may remain literal",
                "movement/controller names describe motion, not a weapon taxonomy",
                "baked_sprite requires a real generated PNG; no placeholder",
                visual_background_transport_rule(),
                "never author impact sprite prompts here; VFX owns them only when it selects rendererKind=impactSprite",
                "the runtime entity with kind=item_body must use baked_sprite regardless of its entityId; set visualProjectRef=item and omit prompt/silhouette/visualIdentity; root item owns that design",
                "only another non-item_body entity that is the same physical object as item_body may use reuse_item_icon with visualProjectRef=item and must not author a second visual project",
                "reuse_item_icon carries only entityId, assetMode, visualProjectRef=item and scale; do not duplicate prompt or identity fields",
                "runtime_geometry/no_asset carry only entityId, assetMode, visualProjectRef=none and scale",
                "when equipmentOverlayReadOnly.required is true, author equipOverlay as a separate transparent wearable layer for that exact slot, without drawing a player body",
            ],
            "responseSchema": sent_schema,
        }
    response_schema = payload.pop("responseSchema")
    presentation = _presentation_packet_context(data, runtime_rows)
    if scoped_repair:
        permissions = (repair_scope or {})["fieldPermissions"]
        paths = [*(permissions.get("itemPaths") or []), *(permissions.get("equipOverlayPaths") or []),
                 *(path for row in permissions.get("entities") or [] for path in row.get("paths") or [])]
        roots = {path.split(".", 1)[0].split("[", 1)[0] for path in paths}
        design = bool(roots & {"", "prompt", "silhouette", "visualIdentity", "palette", "assetMode", "visualProjectRef"})
        sizing = bool(roots & {"", "renderSizePx", "preferredCanvasSize", "inventoryScale", "worldScale", "scale", "grip", "forwardAngleDegrees", "assetMode", "visualProjectRef"})
        if not design:
            parents = payload.pop("parentFactsReadOnly")
            references = {}
            for key, parent in parents.items():
                card = parent["packet"]
                raw_parent = card.get("raw") or {}
                generated = raw_parent.get("generatedParent") or {}
                references[key] = {
                    **({"spriteReference": copy.deepcopy(raw_parent["spriteReference"])} if "spriteReference" in raw_parent else {}),
                    **({"visual": copy.deepcopy(generated["visual"])} if "visual" in generated else {}),
                    "entities": [{"id": row["id"], **({"visual": copy.deepcopy(row["visual"])} if "visual" in row else {})}
                                 for row in (generated.get("runtimeProgram") or {}).get("entities") or []],
                }
            payload["parentSizeReferencesReadOnly"] = references
        guidance = presentation["spritePresentationReadOnly"]
        selected = {"requiredMetadata"}
        if design:
            selected.update({"ownership", "geometryCoverage", "axis"})
        if sizing:
            selected.update({"units", "formulas", "ownership", "sourceCalibration"})
        if roots & {"", "forwardAngleDegrees", "grip"}:
            selected.add("axis")
        mechanics = presentation["acceptedPresentationMechanicsReadOnly"]
        if sizing and any(isinstance(((row.get("usePolicy") or {}).get("action") or {}).get("placement"), Mapping)
                          and "placedBody" in row["usePolicy"]["action"]["placement"]
                          for row in mechanics.get("bindings") or []):
            selected.add("placedBody")
        if roots & {"", "preferredCanvasSize", "renderSizePx", "grip", "assetMode", "visualProjectRef"}:
            selected.add("fill")
        if roots & {"", "grip", "renderSizePx", "forwardAngleDegrees", "assetMode", "visualProjectRef"} and any("spriteDependenciesReadOnly" in row for row in runtime_rows):
            selected.update({"frontHand", "handContactGeometry", "axis"})
        presentation["spritePresentationReadOnly"] = {key: value for key, value in guidance.items() if key in selected}
        if not sizing:
            presentation.pop("bakeFillByProcessingRole")
            presentation.pop("acceptedPresentationMechanicsReadOnly")
        else:
            roles = {"item"} if not permissions.get("entities") else set(presentation["bakeFillByProcessingRole"])
            presentation["bakeFillByProcessingRole"] = {key: value for key, value in presentation["bakeFillByProcessingRole"].items() if key in roles}
        if not roots & {"", "assetMode", "visualProjectRef"}:
            payload["assetModeCatalog"] = {}
        payload["rules"] = [
            "fill only fields listed in repairScope.fieldPermissions; optional unreported fields stay absent",
            "already-valid fields and independent rows are frozen; extra rewrites are ignored; runtime gameplay is immutable",
        ] + ([visual_background_transport_rule()] if design else [])
        system = (
            "You are the conditional Visual Repair. Return only the exact permitted patch leaves and selectors "
            "in responseSchema. Omitted fields are unchanged. Accepted design, independent rows and gameplay "
            "are immutable; extra rewrites are ignored by frozen-first merge. Return JSON only."
        ) if not isinstance(previous, MalformedVisualDirectorOutput) else system
    payload.update(presentation)
    if not scoped_repair:
        payload["rules"].append("Explicitly choose required renderSizePx and forwardAngleDegrees for item and those plus preferredCanvasSize for each distinct baked project; item_body/reuse inherit root and must not duplicate them. Canvas is resolution, not world size; do not use gameplay hitbox dimensions as a bake canvas chooser.")
    payload["responseSchema"] = response_schema
    # Ordering only: keep every field/value in the same complete JSON object.
    # Entity-specific responseSchema (including its exact ID enums) remains after
    # the boundary, as do all parent, item, error, and Repair context fields.
    payload = {
        **{key: payload[key] for key in _VISUAL_STATIC_PREFIX_KEYS},
        **{key: value for key, value in payload.items() if key not in _VISUAL_STATIC_PREFIX_KEYS},
    }
    system += provider_nullable_transport_rule(response_format)
    model = resolve_llm_model()
    request = {
        "model": model,
        "messages": [
            stage_chat_message("system", "visual_repair_contract" if repair else "visual_director_contract", system + generation_system_suffix() + llm_reasoning_system_suffix(model)),
            stage_chat_message("user", "visual_repair_context" if repair else "visual_director_context", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
        ],
        "temperature": (
            env_float("INFINI_VISUAL_REPAIR_TEMPERATURE", 0.12)
            if repair
            else env_float("INFINI_VISUAL_DIRECTOR_TEMPERATURE", float(GENERATION_DEFAULTS["INFINI_VISUAL_DIRECTOR_TEMPERATURE"]))
        ),
        "max_tokens": visual_director_max_tokens(),
        "response_format": response_format,
    }
    request = apply_llm_common_options(request, model_name=model, default_max_tokens=visual_director_max_tokens())
    request = with_instruction_segments(request, payload, _VISUAL_STATIC_PREFIX_KEYS)
    item_key = "itemPatch" if repair else "item"
    item_path = ("properties", item_key, "anyOf", 0) if repair else ("properties", item_key)
    definition_paths: dict[str, tuple[str | int, ...] | tuple[tuple[str | int, ...], ...]] = {
        item_key: item_path,
    }
    if not repair:
        definition_paths["animationPlan"] = ("properties", "animationPlan")
    # Explicit canonical entity leaves; ownership/ID enums and roster bounds stay
    # inline USER constraints. Both local oneOf and provider anyOf are supported.
    entity_path = ("properties", "entitiesUpsert" if repair else "entities", "items")
    entity_schema = sent_schema["properties"].get(entity_path[1], {}).get("items", {"properties": {}})
    union = "anyOf" if "anyOf" in entity_schema else "oneOf"
    branches = entity_schema.get(union, [entity_schema])
    branch_paths = [entity_path + (union, index) for index in range(len(branches))] if union in entity_schema else [entity_path]
    scale_paths = tuple(path + ("properties", "scale") for path, branch in zip(branch_paths, branches) if "scale" in branch.get("properties", {}))
    if scale_paths:
        definition_paths["entityScale"] = scale_paths
    for field in ("prompt", "silhouette", "visualIdentity"):
        paths = tuple(
            path + ("properties", field) for path, branch in zip(branch_paths, branches)
            if field in branch["properties"]
        )
        if paths:
            definition_paths["entity_" + field] = paths
    if not scoped_repair:
        request = with_schema_instruction_definitions(request, "responseSchema", definition_paths)
    stage_name = "visual_repair" if repair else "visual_director"
    trace_event("prompt", "LLM:" + stage_name, "Visual stage request", {"recipeKey": data.get("recipeKey"), "recipeId": data.get("id")}, prompt=request["messages"])
    trace_stage_request(stage_name, data.get("recipeKey"), request, recipe_id=data.get("id"))
    raw = llm_chat_json(with_llm_stage(request, "visual_repair" if repair else "visual_director"), timeout=env_int("INFINI_LLM_TIMEOUT", int(GENERATION_DEFAULTS["INFINI_LLM_TIMEOUT"])))
    content = raw["choices"][0]["message"]["content"]
    trace_event("response", "LLM:" + stage_name, "Visual stage response", {"recipeKey": data.get("recipeKey"), "recipeId": data.get("id")}, response=content)
    try:
        parsed = parse_first_valid_llm_json(content)
        effective_format = effective_response_format(request, raw)
        # Repair's object-or-null blocks have no semantic discriminator. Select the
        # object branch by container type, not by whether invalid authored leaves
        # happen to validate; those leaves must still reach exact-scope Repair.
        if repair and isinstance(parsed, dict) and effective_format and effective_format.get("type") == "json_schema":
            provider_props = effective_format["json_schema"]["schema"]["properties"]
            for key in ("itemPatch", "equipOverlayPatch"):
                if isinstance(parsed.get(key), dict) and key in schema["properties"]:
                    parsed[key] = project_provider_nullable_optionals_to_local(
                        parsed[key], schema["properties"][key]["anyOf"][0],
                        response_format={"type": "json_schema", "json_schema": {"schema": provider_props[key]["anyOf"][0]}},
                    )
        parsed = project_provider_nullable_optionals_to_local(parsed, schema, response_format=effective_format)
        return _expand_scoped_visual_repair_patch(parsed, previous, repair_scope or {}, entity_ids) if scoped_repair else parsed
    except (ValueError, TypeError) as exc:
        if repair:
            raise PlannerUnavailable(f"Visual Repair returned malformed JSON: {type(exc).__name__}: {exc}") from exc
        return MalformedVisualDirectorOutput(raw_text=str(content), error=f"{type(exc).__name__}: {exc}")


def _apply_kit(data: dict[str, Any], kit: Mapping[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(data)
    item = dict(kit.get("item") or {})
    visual = out.setdefault("visual", {})
    visual.update({
        "imagePrompt": item["prompt"],
        "negativePrompt": item["negativePrompt"],
        "silhouette": item["silhouette"],
        "visualIdentity": item["visualIdentity"],
        "palette": copy.deepcopy(item["palette"]),
        "preferredCanvasSize": item["preferredCanvasSize"],
        "inventoryScale": item["inventoryScale"],
        "worldScale": item["worldScale"],
    })
    for field in ("grip", "renderSizePx", "forwardAngleDegrees"):
        if field in item:
            visual[field] = copy.deepcopy(item[field])
        else:
            visual.pop(field, None)
    overlay = kit.get("equipOverlay")
    if isinstance(overlay, Mapping) and "accessoryMount" in overlay:
        visual["accessoryMount"] = overlay["accessoryMount"]
    else:
        visual.pop("accessoryMount", None)
    if isinstance(overlay, Mapping):
        visual.update({
            "equipOverlayPrompt": str(overlay.get("prompt") or "")[:1400],
            "equipOverlayPath": "",
            "equipOverlayUrl": "",
            "equipOverlayStatus": "pending",
            "equipOverlayTechnicalScore": 0.0,
        })
    runtime = out.get("runtimeProgram") if isinstance(out.get("runtimeProgram"), dict) else {}
    by_id = {str(row.get("entityId")): row for row in kit.get("entities") or [] if isinstance(row, dict)}
    for entity in runtime.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        row = by_id[str(entity.get("id") or "")]
        entity_visual = entity.setdefault("visual", {})
        for stale_impact_field in (
            "impactPrompt", "impactNegativePrompt", "impactSpritePath", "impactSpriteUrl",
            "impactSpriteStatus", "impactSpriteTechnicalScore",
        ):
            entity_visual.pop(stale_impact_field, None)
        project_ref = str(row.get("visualProjectRef") or "")
        project = item if project_ref == "item" else row
        # Only distinct baked projects own these metadata; item/reuse select root.
        for field in ("renderSizePx", "preferredCanvasSize", "forwardAngleDegrees", "grip"):
            if project_ref == "entity" and field in row:
                entity_visual[field] = copy.deepcopy(row[field])
            else:
                entity_visual.pop(field, None)
        entity_visual.update({
            "role": str(entity.get("visualRole") or ""),
            "assetMode": str(row.get("assetMode") or ""),
            "prompt": str(project.get("prompt") or "")[:1400],
            "silhouette": str(project.get("silhouette") or "")[:700],
            "visualIdentity": str(project.get("visualIdentity") or "")[:700],
            "scale": float(row.get("scale") or 1.0),
            "spritePath": "",
            "spriteUrl": "",
            "spriteStatus": "pending" if row.get("assetMode") == "baked_sprite" else "not_required",
            "spriteTechnicalScore": 0.0,
        })
    out["visualKit"] = copy.deepcopy(dict(kit))
    return out


def apply_visual_director(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), dict) else {}
    entities = [row for row in runtime.get("entities") or [] if isinstance(row, dict)]
    entity_ids = [str(row.get("id") or "") for row in entities]
    item_body_id = next((str(row.get("id") or "") for row in entities if row.get("kind") == "item_body"), "")
    equipment_overlay_required = bool(equipment_overlay_requirement(data)["required"])
    if not entity_ids or not item_body_id:
        raise PlannerUnavailable("Visual Director has no accepted runtime entities")
    if not (USE_LLM and VISUAL_DIRECTOR_LLM):
        # Explicit development mode only. Production LLM crafts must not silently
        # manufacture a visual design in code.
        if str((data.get("debug") or {}).get("planner") or "").startswith("llm_"):
            raise PlannerUnavailable("Visual Director is required for LLM-authored craft")
        if equipment_overlay_required:
            raise PlannerUnavailable("Equipment overlay requires a model-authored Visual Director response")
        dev_item = {
            "prompt": f"Terraria pixel-art inventory sprite of {data.get('name')}; literal combined parent object, transparent background",
            "negativePrompt": "placeholder, text, watermark",
            "silhouette": "compact readable combined object",
            "visualIdentity": str((data.get("realization") or {}).get("description") or data.get("name") or "generated item"),
            "palette": ["neutral", "accent"],
            "preferredCanvasSize": 32,
            "inventoryScale": 1.0,
            "worldScale": 1.0,
        }
        kit = {
            "schema": VISUAL_KIT_SCHEMA,
            "item": dev_item,
            "entities": [
                ({
                    "entityId": entity_id,
                    "assetMode": "baked_sprite",
                    "visualProjectRef": "item",
                    "scale": 1.0,
                } if entity_id == item_body_id else {
                    "entityId": entity_id,
                    "assetMode": "reuse_item_icon",
                    "visualProjectRef": "item",
                    "scale": 1.0,
                })
                for entity_id in entity_ids
            ],
            "animationPlan": "Use the authored runtime movement without changing gameplay.",
        }
        data.setdefault("debug", {})["visualDirectorStatus"] = "development_fixture"
        return _apply_kit(data, kit)

    accounting = _stage_accounting(data)
    accounting["visualDirectorCalls"] += 1
    raw = _request_visual_kit(data, a, b)
    kit, errors = _validate_kit(
        raw,
        entity_ids,
        item_body_id,
        equipment_overlay_required=equipment_overlay_required,
        accepted_data=data,
    )
    if kit is None:
        accounting["visualRepairCalls"] += 1
        repair_scope = _build_visual_repair_scope(
            raw,
            errors,
            entity_ids,
            item_body_id,
            equipment_overlay_required=equipment_overlay_required,
        )
        patch = _request_visual_kit(data, a, b, repair_errors=errors, previous=raw, repair_scope=repair_scope)
        if not isinstance(patch, Mapping):
            raise PlannerUnavailable("Visual Repair response must be a JSON object")
        repaired, repair_audit = _apply_visual_repair_patch(raw, patch, repair_scope, entity_ids, return_audit=True)
        kit, errors = _validate_kit(
            repaired,
            entity_ids,
            item_body_id,
            equipment_overlay_required=equipment_overlay_required,
            accepted_data=data,
        )
        if kit is None:
            raise PlannerUnavailable("Visual Repair did not produce an entity-complete visual kit: " + json.dumps(errors[:16], ensure_ascii=False))
        if isinstance(raw, MalformedVisualDirectorOutput):
            source = recover_object_with_syntax_only_repairs(raw.raw_text)
            if source is None:
                raise PlannerUnavailable("Visual format Repair cannot prove recoverable visual fields")
            recovered_kit, _ = _validate_kit(
                source, entity_ids, item_body_id,
                equipment_overlay_required=equipment_overlay_required,
                accepted_data=data,
            )
            if recovered_kit is None:
                raise PlannerUnavailable("Visual format Repair cannot prove recoverable visual fields")
            recovered_design = {key: value for key, value in recovered_kit.items() if key != "animationPlan"}
            repaired_design = {key: value for key, value in kit.items() if key != "animationPlan"}
            if recovered_design != repaired_design:
                raise PlannerUnavailable("Visual format Repair changed recoverable visual fields")
            if "animationPlan" in recovered_kit:
                kit["animationPlan"] = copy.deepcopy(recovered_kit["animationPlan"])
        raw = repaired
        data.setdefault("debug", {})["visualRepairRawPatch"] = copy.deepcopy(patch)
        data["debug"]["visualRepairPatch"] = copy.deepcopy(repair_audit.get("filteredPatch") or {})
        data["debug"]["visualRepairFilterAudit"] = copy.deepcopy(repair_audit)
        data["debug"]["visualRepairScope"] = copy.deepcopy(repair_scope)
    out = _apply_kit(data, kit)
    out.setdefault("debug", {})["visualDirectorStatus"] = "validated_and_applied"
    out["debug"]["visualDirectorEntityIds"] = entity_ids
    out["debug"]["visualDirectorRaw"] = copy.deepcopy(raw)
    return out


def visual_response_schema(entity_ids: list[str], equipment_overlay_required: bool | None = None, *, item_body_id: str | None = None) -> dict[str, Any]:
    """Public schema; ``None`` exports the capability-neutral optional superset."""

    if equipment_overlay_required is not None:
        return _response_schema(entity_ids, equipment_overlay_required, item_body_id)
    schema = _response_schema(entity_ids, False, item_body_id)
    schema["properties"]["equipOverlay"] = _visual_equip_overlay_schema()
    return schema


def visual_repair_schema(entity_ids: list[str], equipment_overlay_required: bool | None = None, *, item_body_id: str | None = None) -> dict[str, Any]:
    """Public Repair schema; ``None`` exports the optional capability superset."""

    if equipment_overlay_required is not None:
        return _visual_repair_schema(entity_ids, equipment_overlay_required, item_body_id)
    schema = _visual_repair_schema(entity_ids, False, item_body_id)
    schema["properties"]["equipOverlayPatch"] = {"anyOf": [_visual_equip_overlay_schema(), {"type": "null"}]}
    return schema


__all__ = [
    "VISUAL_KIT_SCHEMA",
    "VISUAL_REPAIR_PATCH_SCHEMA",
    "apply_visual_director",
    "attach_visual",
    "visual_repair_schema",
    "visual_response_schema",
]
