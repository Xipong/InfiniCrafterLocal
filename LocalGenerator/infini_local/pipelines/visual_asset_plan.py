from __future__ import annotations

"""Per-runtime-entity visual asset plan.

The plan is a projection of Visual Director choices.  It never infers assets from
weapon families or mutates gameplay topology.
"""

import copy
from typing import Any, Mapping

from infini_local.pipelines.visual_asset_modes import VISUAL_ASSET_MODES


_ALLOWED_MODES = set(VISUAL_ASSET_MODES)


def _runtime(data: Mapping[str, Any]) -> Mapping[str, Any]:
    value = data.get("runtimeProgram")
    return value if isinstance(value, Mapping) else {}


def _entity_rows(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _runtime(data).get("entities") or [] if isinstance(row, dict)]


def equipment_overlay_requirement(data: Mapping[str, Any]) -> dict[str, Any]:
    raw_armor = data.get("armor")
    raw_accessory = data.get("accessory")
    armor: Mapping[str, Any] = raw_armor if isinstance(raw_armor, Mapping) else {}
    accessory: Mapping[str, Any] = raw_accessory if isinstance(raw_accessory, Mapping) else {}
    if armor.get("enabled") is True:
        return {"required": True, "slot": str(armor.get("slot") or "")}
    if accessory.get("enabled") is True:
        return {"required": True, "slot": "accessory"}
    return {"required": False, "slot": ""}


def _entity_by_id(data: Mapping[str, Any], entity_id: str) -> dict[str, Any] | None:
    return next((row for row in _entity_rows(data) if str(row.get("id") or "") == entity_id), None)


def _has_complete_visual_design(data: Mapping[str, Any], role: str) -> bool:
    runtime = _runtime(data)
    entity_id = str(runtime.get("itemEntityId") or "") if role == "item" else role.removeprefix("entity:")
    entity = _entity_by_id(data, entity_id)
    raw_visual = entity.get("visual") if isinstance(entity, Mapping) else None
    visual = raw_visual if isinstance(raw_visual, Mapping) else {}
    return all(
        isinstance(visual.get(field), str) and bool(str(visual.get(field)).strip())
        for field in ("prompt", "silhouette", "visualIdentity")
    )


def _recorded_fix_reason(data: Mapping[str, Any], entity_id: str) -> str:
    raw_debug = data.get("debug")
    debug = raw_debug if isinstance(raw_debug, Mapping) else {}
    for row in debug.get("visualAssetFixes") or []:
        if isinstance(row, Mapping) and str(row.get("entityId") or "") == entity_id:
            return str(row.get("reason") or "")
    return ""


def visual_asset_runtime_gate(data: dict[str, Any], role: str, authored_mode: str) -> tuple[str, str]:
    mode = str(authored_mode or "").strip().lower()
    if role == "item" and mode == "":
        if _has_complete_visual_design(data, role):
            # Conscious Fix: the complete model-authored item design proves that
            # a canonical inventory PNG is required; no visual meaning is invented.
            return "baked_sprite", "fix:item_body_baked_sprite_from_complete_visual_design"
        return "", "invalid_or_missing_authored_asset_mode"
    if mode not in _ALLOWED_MODES:
        return "", "invalid_or_missing_authored_asset_mode"
    if role == "item" and mode != "baked_sprite":
        return "", "item_body_requires_baked_sprite"
    return mode, "authored_runtime_entity_asset_mode"


def apply_visual_asset_runtime_gates(data: dict[str, Any], kit: dict[str, Any]) -> None:
    del kit
    raw_debug = data.get("debug")
    debug = raw_debug if isinstance(raw_debug, dict) else {}
    existing_fixes = {
        str(row.get("entityId") or ""): dict(row)
        for row in debug.get("visualAssetFixes") or []
        if isinstance(row, Mapping) and str(row.get("entityId") or "")
    }
    for entity in _entity_rows(data):
        raw_visual = entity.get("visual")
        visual = raw_visual if isinstance(raw_visual, dict) else {}
        entity_id = str(entity.get("id") or "")
        role = "item" if entity.get("kind") == "item_body" else "entity:" + entity_id
        mode, reason = visual_asset_runtime_gate(data, role, str(visual.get("assetMode") or ""))
        visual["assetMode"] = mode
        if reason.startswith("fix:") and str(visual.get("spriteStatus") or "") == "not_required":
            visual["spriteStatus"] = "pending"
        visual.pop("runtimeGateReason", None)
        entity["visual"] = visual
        if reason.startswith("fix:"):
            existing_fixes[entity_id] = {
                "entityId": entity_id,
                "field": "assetMode",
                "value": mode,
                "reason": reason,
            }
        elif mode != "baked_sprite":
            existing_fixes.pop(entity_id, None)
    if existing_fixes:
        debug["visualAssetFixes"] = [existing_fixes[key] for key in sorted(existing_fixes)]
        data["debug"] = debug
    elif isinstance(raw_debug, dict):
        raw_debug.pop("visualAssetFixes", None)


def finalize_visual_asset_runtime_gates(data: dict[str, Any]) -> dict[str, Any]:
    apply_visual_asset_runtime_gates(data, data.get("visualKit") if isinstance(data.get("visualKit"), dict) else {})
    return data


def _canvas_for(entity: Mapping[str, Any], data: Mapping[str, Any]) -> int:
    if entity.get("kind") == "item_body":
        visual = data.get("visual") if isinstance(data.get("visual"), Mapping) else {}
        return int(visual.get("preferredCanvasSize") or 32)
    hitbox = entity.get("hitbox") if isinstance(entity.get("hitbox"), Mapping) else {}
    largest = max(int(hitbox.get("widthPx") or 16), int(hitbox.get("heightPx") or 16))
    if largest <= 24: return 24
    if largest <= 32: return 32
    if largest <= 48: return 48
    if largest <= 64: return 64
    if largest <= 96: return 96
    return 128


def build_visual_asset_plan(data: dict[str, Any]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    raw_manifest = data.get("vfxManifest")
    manifest: Mapping[str, Any] = raw_manifest if isinstance(raw_manifest, Mapping) else {}
    impact_slots = {
        str(slot.get("entityId") or ""): slot
        for slot in manifest.get("slots") or []
        if isinstance(slot, Mapping) and str(slot.get("rendererKind") or "") == "impactSprite"
    }
    raw_item_visual = data.get("visual")
    item_visual: dict[str, Any] = raw_item_visual if isinstance(raw_item_visual, dict) else {}
    for entity in _entity_rows(data):
        entity_id = str(entity.get("id") or "")
        raw_entity_visual = entity.get("visual")
        entity_visual = raw_entity_visual if isinstance(raw_entity_visual, dict) else {}
        is_item = entity.get("kind") == "item_body"
        role = "item" if is_item else "entity:" + entity_id
        mode, reason = visual_asset_runtime_gate(data, role, str(entity_visual.get("assetMode") or ""))
        recorded_fix = _recorded_fix_reason(data, entity_id)
        if is_item and mode == "baked_sprite" and recorded_fix.startswith("fix:"):
            reason = recorded_fix
        if is_item:
            prompt = str(item_visual.get("imagePrompt") or entity_visual.get("prompt") or "")
            status = str(item_visual.get("spriteStatus") or "pending")
            path = str(item_visual.get("spritePath") or "")
            url = str(item_visual.get("spriteUrl") or "")
            score = float(item_visual.get("spriteTechnicalScore") or 0.0)
        else:
            prompt = str(entity_visual.get("prompt") or "")
            status = str(entity_visual.get("spriteStatus") or ("pending" if mode == "baked_sprite" else "not_required"))
            path = str(entity_visual.get("spritePath") or "")
            url = str(entity_visual.get("spriteUrl") or "")
            score = float(entity_visual.get("spriteTechnicalScore") or 0.0)
        plan.append({
            "role": role,
            "entityId": entity_id,
            "entityKind": str(entity.get("kind") or ""),
            "visualRole": str(entity.get("visualRole") or ""),
            "assetMode": mode,
            "runtimeGateReason": reason,
            "assetId": f"{str(data.get('id') or 'generated')}_{entity_id}",
            "prompt": prompt[:1400],
            "canvas": _canvas_for(entity, data),
            "status": status,
            "path": path,
            "url": url,
            "technicalScore": score,
        })
        impact_slot = impact_slots.get(entity_id)
        if isinstance(impact_slot, Mapping):
            plan.append({
                "role": "impact:" + entity_id,
                "entityId": entity_id,
                "entityKind": str(entity.get("kind") or ""),
                "visualRole": "impact",
                "assetMode": "baked_sprite",
                "runtimeGateReason": "authored_vfx_impact_texture",
                "assetId": f"{str(data.get('id') or 'generated')}_{entity_id}_impact",
                "prompt": str(entity_visual.get("impactPrompt") or "")[:1400],
                "negativePrompt": str(entity_visual.get("impactNegativePrompt") or "")[:700],
                "canvas": _canvas_for(entity, data),
                "required": True,
                "status": str(entity_visual.get("impactSpriteStatus") or "pending"),
                "path": str(entity_visual.get("impactSpritePath") or ""),
                "url": str(entity_visual.get("impactSpriteUrl") or ""),
                "technicalScore": float(entity_visual.get("impactSpriteTechnicalScore") or 0.0),
            })
    overlay_requirement = equipment_overlay_requirement(data)
    if overlay_requirement["required"]:
        runtime = _runtime(data)
        item_entity_id = str(runtime.get("itemEntityId") or "")
        if not item_entity_id:
            item_entity_id = next((str(row.get("id") or "") for row in _entity_rows(data) if row.get("kind") == "item_body"), "")
        raw_kit = data.get("visualKit")
        kit: dict[str, Any] = dict(raw_kit) if isinstance(raw_kit, Mapping) else {}
        raw_overlay = kit.get("equipOverlay")
        overlay: dict[str, Any] = dict(raw_overlay) if isinstance(raw_overlay, Mapping) else {}
        plan.append({
            "role": "equip_overlay",
            "entityId": item_entity_id,
            "entityKind": "item_body",
            "visualRole": "equip_overlay",
            "assetMode": "baked_sprite",
            "runtimeGateReason": "authored_equipment_overlay",
            "assetId": f"{str(data.get('id') or 'generated')}_equip_overlay",
            "prompt": str(item_visual.get("equipOverlayPrompt") or overlay.get("prompt") or "")[:1400],
            "canvas": int(overlay.get("preferredCanvasSize") or 48),
            "required": True,
            "equipmentSlot": str(overlay_requirement["slot"]),
            "status": str(item_visual.get("equipOverlayStatus") or "pending"),
            "path": str(item_visual.get("equipOverlayPath") or ""),
            "url": str(item_visual.get("equipOverlayUrl") or ""),
            "technicalScore": float(item_visual.get("equipOverlayTechnicalScore") or 0.0),
        })
    return copy.deepcopy(plan)


__all__ = [
    "apply_visual_asset_runtime_gates",
    "build_visual_asset_plan",
    "equipment_overlay_requirement",
    "finalize_visual_asset_runtime_gates",
    "visual_asset_runtime_gate",
]
