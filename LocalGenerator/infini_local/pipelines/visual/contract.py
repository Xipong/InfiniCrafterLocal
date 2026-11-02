"""Canonical Visual response schemas and admission over accepted runtime facts."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping

from infini_local.core.visual_contract_schema import (
    SPRITE_CANVAS_SIZES,
    front_hand_sprite_errors,
    grip_schema,
    sprite_presentation_properties,
    body_geometry_schema,
    collision_path_source,
)
from infini_local.core.repair_merge import json_path_relative
from infini_local.core.schema_validation import strict_schema_errors
from infini_local.pipelines.visual.modes import VISUAL_ASSET_MODES


VISUAL_KIT_SCHEMA = "infini.visual-kit.runtime-entities.v3"


VISUAL_REPAIR_PATCH_SCHEMA = "infini.visual-kit-repair-patch.runtime-entities.v3"


_ALLOWED_ASSET_MODES = set(VISUAL_ASSET_MODES)


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
    response_format: Mapping[str, Any] | None = None


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
        branch = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "entityId": copy.deepcopy(nonitem_id),
                "assetMode": {"const": mode},
                "visualProjectRef": {"const": "none"},
                "scale": copy.deepcopy(scale),
            },
            "required": ["entityId", "assetMode", "visualProjectRef", "scale"],
        }
        if mode == "runtime_geometry":
            branch["properties"]["geometry"] = body_geometry_schema()
            branch["required"].append("geometry")
        non_sprite_branches.append(branch)
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
        accepted_runtime = accepted_data.get("runtimeProgram") or {}
        accepted_entities = {entity.get("id"): entity for entity in accepted_runtime.get("entities", []) if isinstance(entity, Mapping)}
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping) or not isinstance(row.get("geometry"), Mapping):
                continue
            entity = accepted_entities.get(row.get("entityId"), {})
            geometry = row["geometry"]
            if geometry.get("source") == "collision_path" and collision_path_source(entity) is None:
                errors.append({"path": f"$.entities[{index}].geometry.source", "message": "collision_path requires accepted beam or lash collision geometry"})
            if geometry.get("source") == "body_segment" and geometry.get("axis") == "aim" and not isinstance(entity.get("aim"), Mapping):
                errors.append({"path": f"$.entities[{index}].geometry.axis", "message": "aim axis requires an accepted aim component"})
        dependencies = front_hand_sprite_errors(accepted_data, kit=raw)
        seen_paths = {error["path"] for error in errors}
        errors.extend(error for error in dependencies if error["path"] not in seen_paths)
    return (copy.deepcopy(raw) if not errors else None), errors


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
