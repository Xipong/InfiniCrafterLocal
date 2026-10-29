"""Selected main-sprite dependencies shared by Visual admission and delivery.

These are presentation requirements of an explicit accepted driver, not gameplay
selection or defaults. Unresolved entity/project identities defer dependencies.
"""
from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from infini_local.core.schema_validation import strict_schema_errors
from infini_local.core.runtime_authoring.capability_registry import MOVEMENT_OPCODE, PROJECTILE_ENTITY_KINDS


SPRITE_CANVAS_SIZES = (24, 32, 48, 64, 96, 128)


def sprite_presentation_properties() -> dict[str, Any]:
    # Direct authored projection, never inferred from hitbox, canvas or prose.
    return {
        "renderSizePx": {
            "type": "integer", "minimum": 1, "maximum": 512,
            "description": "Base world-pixel length of the larger side of the complete final PNG frame, before rotation/camera and independent draw multipliers. Not alpha-bbox, collision, inventory fit or bake resolution. Runtime uses q=renderSizePx/max(actual final frame width,height).",
        },
        "forwardAngleDegrees": {
            "type": "number", "minimum": -180, "maximum": 180,
            "description": "Finite local forward-axis angle of the final PNG after crop/fit/padding, before facing/gravity flips. Degrees: 0=+X (right), positive clockwise in y-down image coordinates. Describes the authored pixels, not AI movement or a gameplay rotation override; no image/prose inference.",
        },
    }


def grip_schema() -> dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False,
        "description": "Atomic hand pivot on the selected final PNG canvas after crop/fit/padding, before facing/gravity flips. normalizedX=0 is left, 1 right; normalizedY=0 top, 1 bottom. Both required; no pixel units or gameplay geometry. Optional except for sprite-consuming attachment.anchor=front_hand or retained move_front_hand; armPose alone does not require it. Root/reuse select the single item grip; only distinct baked entities own an entity grip. Not authored HoldoutOffset.",
        "properties": {
            "normalizedX": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "normalizedY": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["normalizedX", "normalizedY"],
    }


def front_hand_sprite_requirement(entity: Mapping[str, Any]) -> dict[str, Any] | None:
    movement = entity.get("movement")
    attachment = entity.get("attachment")
    hand_attachment = (entity.get("kind") in PROJECTILE_ENTITY_KINDS
                       and isinstance(attachment, Mapping) and attachment.get("anchor") == "front_hand")
    historical_hand_driver = (entity.get("kind") == "owner_attached_projectile" and isinstance(movement, Mapping)
                              and movement.get("name") == "move_front_hand"
                              and type(movement.get("code")) is int
                              and movement["code"] == MOVEMENT_OPCODE.get("move_front_hand"))
    # Reading the hand anchor is independent of writing the arm pose. Neither
    # armPose alone nor a non-hand anchor consumes the hand-gripped PNG lane.
    if not hand_attachment and not historical_hand_driver:
        return None
    return {"requiredFields": ["renderSizePx", "forwardAngleDegrees", "grip"],
            "selectedOwnerByAssetMode": {"reuse_item_icon": "item", "baked_sprite": "entity",
                                        "no_asset": None, "runtime_geometry": None}}


def front_hand_sprite_dependencies(data: Mapping[str, Any], *, kit: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    runtime = data.get("runtimeProgram")
    if not isinstance(runtime, Mapping):
        return []
    entities = [row for row in runtime.get("entities") or [] if isinstance(row, Mapping)]
    ids = [row.get("id") for row in entities]
    item_ids = [row.get("id") for row in entities if row.get("kind") == "item_body"]
    if len(item_ids) != 1 or type(item_ids[0]) is not str or ids.count(item_ids[0]) != 1:
        return []
    rows = kit.get("entities") if kit is not None else None
    result = []
    for index, entity in enumerate(entities):
        requirement = front_hand_sprite_requirement(entity)
        entity_id = entity.get("id")
        if requirement is None or type(entity_id) is not str or ids.count(entity_id) != 1:
            continue
        if kit is not None:
            matches = [(i, row) for i, row in enumerate(rows if isinstance(rows, list) else [])
                       if isinstance(row, Mapping) and row.get("entityId") == entity_id]
            if len(matches) != 1:
                continue
            row_index, visual = matches[0]
            entity_visual_path = f"$.entities[{row_index}]"
            mode = visual.get("assetMode")
            expected_ref = "item" if mode == "reuse_item_icon" else "entity" if mode == "baked_sprite" else "none"
            if visual.get("visualProjectRef") != expected_ref:
                continue
            owner_path = "$.item" if mode == "reuse_item_icon" else f"$.entities[{row_index}]"
            owner = kit.get("item") if mode == "reuse_item_icon" else visual
        else:
            visual = entity.get("visual")
            if not isinstance(visual, Mapping):
                continue
            entity_visual_path = f"$.runtimeProgram.entities[{index}].visual"
            mode = visual.get("assetMode")
            owner_path = "$.visual" if mode == "reuse_item_icon" else f"$.runtimeProgram.entities[{index}].visual"
            owner = data.get("visual") if mode == "reuse_item_icon" else visual
        if mode not in {"reuse_item_icon", "baked_sprite"}:
            continue
        # A resolved selected project with no metadata still has dependencies;
        # absence cannot turn this explicit sprite driver into a legacy omission.
        owner = owner if isinstance(owner, Mapping) else {}
        result.append({"entityId": entity_id, "assetMode": mode, "ownerPath": owner_path,
                       "requiredFields": requirement["requiredFields"],
                       "nonowningFields": [field for field in requirement["requiredFields"] if mode == "reuse_item_icon" and field in visual],
                       "entityVisualPath": entity_visual_path,
                       "metadataReadOnly": copy.deepcopy(dict(owner))})
    return result


def front_hand_sprite_errors(data: Mapping[str, Any], *, kit: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    # The canonical Visual shape also owns strict optional-present metadata.
    properties = {**sprite_presentation_properties(), "grip": grip_schema()}
    errors = []
    for dependency in front_hand_sprite_dependencies(data, kit=kit):
        owner = dependency["metadataReadOnly"]
        for field in dependency["nonowningFields"]:
            errors.append({"path": dependency["entityVisualPath"] + "." + field,
                           "code": "nonowning_sprite_presentation",
                           "message": "reuse_item_icon selects root metadata; duplicate entity metadata is forbidden."})
        for field in dependency["requiredFields"]:
            path = dependency["ownerPath"] + "." + field
            if field not in owner:
                errors.append({"path": path, "code": "front_hand_sprite_metadata_required",
                               "message": f"Front-hand-attached sprite for {dependency['entityId']!r} requires its selected texture owner's {field}."})
            else:
                for error in strict_schema_errors(owner[field], properties[field], path=path):
                    errors.append({"path": error["path"], "code": "front_hand_sprite_metadata_invalid",
                                   "message": "Selected front-hand-attached sprite metadata must match the exact Visual shape."})
    return errors
