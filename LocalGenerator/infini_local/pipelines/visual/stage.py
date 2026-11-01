"""Visual stage lifecycle and accepted kit projection; no gameplay authorship."""

from __future__ import annotations

import copy
import json
from typing import Any, Mapping

from infini_local.core.errors import PlannerUnavailable
from infini_local.core.llm_config import USE_LLM
from infini_local.core.llm_stage_messages import stage_accounting
from infini_local.core.llm_json_tools import recover_object_with_syntax_only_repairs
from infini_local.core.runtime_authoring.wire_views import runtime_visual_roles
from infini_local.core.images.config import VISUAL_DIRECTOR_LLM
from infini_local.pipelines.visual.assets import equipment_overlay_requirement
from infini_local.pipelines.visual.contract import (
    MalformedVisualDirectorOutput,
    VISUAL_KIT_SCHEMA,
    _validate_kit,
)
from infini_local.pipelines.visual.repair_scope import _build_visual_repair_scope
from infini_local.pipelines.visual.repair import _apply_visual_repair_patch
from infini_local.pipelines.visual.request import _request_visual_kit


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
        if "geometry" in row:
            entity_visual["geometry"] = copy.deepcopy(row["geometry"])
        else:
            entity_visual.pop("geometry", None)
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
        realization = data.get("realization")
        description = realization.get("description") if isinstance(realization, Mapping) else realization if isinstance(realization, str) else None
        dev_item = {
            "prompt": f"Terraria pixel-art inventory sprite of {data.get('name')}; literal combined parent object, transparent background",
            "negativePrompt": "placeholder, text, watermark",
            "silhouette": "compact readable combined object",
            "visualIdentity": str(description or data.get("name") or "generated item"),
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

    accounting = stage_accounting(data)
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
