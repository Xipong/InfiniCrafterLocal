from __future__ import annotations

"""Final visual delivery gate for runtime-entity assets."""

import json
from pathlib import Path
from typing import Any

from infini_local.core.config_bootstrap import SPRITE_DIR, WORLD_RECIPES_DIR
from infini_local.pipelines.pipeline_visual_config import (
    IMAGE_BACKEND,
    IMAGE_BACKEND_CONFIG_ERROR,
    IMAGE_BACKEND_RAW,
    VISUAL_ALLOW_PROCEDURAL_FALLBACK,
    VISUAL_REQUIRE_ITEM_SPRITE,
    VISUAL_REQUIRE_ZIMAGE_BACKEND,
    VISUAL_STRICT_AI_AUTHORSHIP,
    ZIMAGE_PROMPT_CONTRACT,
)
from infini_local.pipelines.visual_prompt_contracts import image_backend_is_zimage
from infini_local.pipelines.visual_asset_plan import equipment_overlay_requirement
from infini_local.services import asset_sync_service


MAX_DELIVERABLE_ASSET_FILES = 32
MAX_DELIVERABLE_ASSET_BYTES = 16 * 1024 * 1024


class VisualDeliveryBlocked(RuntimeError):
    """Fresh craft cannot be delivered because a required authored PNG is absent."""


def _sprite_status_is_usable(status: Any) -> bool:
    value = str(status or "").strip().lower()
    return bool(value) and value not in {
        "failed", "prompt_only", "placeholder", "backend_config_error",
        "skipped", "skipped_disabled_by_settings", "not_required",
        "invalid_or_missing_authored_asset_mode", "required_item_icon_missing",
    }


def _item_sprite_status_is_usable(status: Any) -> bool:
    return str(status or "").strip().lower() == "generated_warn_invalid" or _sprite_status_is_usable(status)


def _resolved_asset_path(path_value: Any) -> Path | None:
    text = str(path_value or "").strip()
    if not text:
        return None
    try:
        path = Path(text)
        if path.exists() and path.is_file():
            return path
        name = asset_sync_service.asset_filename_from_path(text)
        if not name:
            return None
        found = asset_sync_service.find_asset_file(name, sprite_dir=SPRITE_DIR, world_recipes_dir=WORLD_RECIPES_DIR)
        if not found or not found.exists() or not found.is_file():
            return None
        return found
    except Exception:
        return None


def _asset_path_exists(path_value: Any) -> bool:
    path = _resolved_asset_path(path_value)
    if path is None:
        return False
    return asset_sync_service.is_complete_png_file(path) if path.suffix.lower() == ".png" else True


def _asset_roster_problems(paths: list[Path]) -> list[dict[str, Any]]:
    unique = {str(path.resolve()): path for path in paths}
    problems: list[dict[str, Any]] = []
    if len(unique) > MAX_DELIVERABLE_ASSET_FILES:
        problems.append({
            "code": "asset_roster_file_limit_exceeded",
            "message": f"Generated asset roster has {len(unique)} files; maximum is {MAX_DELIVERABLE_ASSET_FILES}.",
        })
    try:
        total_bytes = sum(path.stat().st_size for path in unique.values())
    except OSError:
        total_bytes = MAX_DELIVERABLE_ASSET_BYTES + 1
    if total_bytes > MAX_DELIVERABLE_ASSET_BYTES:
        problems.append({
            "code": "asset_roster_byte_limit_exceeded",
            "message": f"Generated asset roster is {total_bytes} bytes; maximum is {MAX_DELIVERABLE_ASSET_BYTES}.",
        })
    return problems


def _runtime_entities(data: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), dict) else {}
    return [row for row in runtime.get("entities") or [] if isinstance(row, dict)]


def _impact_entity_ids(data: dict[str, Any]) -> set[str]:
    manifest = data.get("vfxManifest") if isinstance(data.get("vfxManifest"), dict) else {}
    return {
        str(slot.get("entityId") or "").strip()
        for slot in manifest.get("slots") or []
        if isinstance(slot, dict) and str(slot.get("textureRole") or "").strip().lower() == "impact"
    } - {""}


def visual_delivery_report(data: dict[str, Any], *, check_backend_config: bool = True) -> dict[str, Any]:
    raw_visual = data.get("visual")
    visual: dict[str, Any] = raw_visual if isinstance(raw_visual, dict) else {}
    problems: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if check_backend_config and IMAGE_BACKEND_CONFIG_ERROR:
        problems.append({"code": "image_backend_configuration_invalid", "message": IMAGE_BACKEND_CONFIG_ERROR})
    if check_backend_config and IMAGE_BACKEND == "procedural" and (VISUAL_STRICT_AI_AUTHORSHIP or not VISUAL_ALLOW_PROCEDURAL_FALLBACK):
        problems.append({"code": "procedural_backend_not_explicitly_allowed", "message": "Procedural authoring is disabled by visual policy."})
    if check_backend_config and VISUAL_REQUIRE_ZIMAGE_BACKEND and not image_backend_is_zimage():
        problems.append({"code": "zimage_required_but_inactive", "message": "The configured delivery policy requires Z-Image/sd.cpp."})

    item_status = str(visual.get("spriteStatus") or "")
    item_path = str(visual.get("spritePath") or "")
    item_exists = _asset_path_exists(item_path)
    item_usable = _item_sprite_status_is_usable(item_status) and item_exists
    if VISUAL_REQUIRE_ITEM_SPRITE and not item_usable:
        problems.append({"code": "required_item_sprite_missing", "message": "Generated item sprite is required, but no usable processed PNG is present.", "status": item_status, "path": item_path})

    slots: list[dict[str, Any]] = [{
        "role": "item", "entityId": next((str(e.get("id") or "") for e in _runtime_entities(data) if e.get("kind") == "item_body"), ""),
        "assetMode": "baked_sprite", "required": bool(VISUAL_REQUIRE_ITEM_SPRITE), "status": item_status,
        "path": item_path, "exists": item_exists, "completePng": item_exists, "usable": item_usable,
        "technicalScore": visual.get("spriteTechnicalScore"),
    }]

    overlay_requirement = equipment_overlay_requirement(data)
    if overlay_requirement["required"]:
        overlay_status = str(visual.get("equipOverlayStatus") or "")
        overlay_path = str(visual.get("equipOverlayPath") or "")
        overlay_exists = _asset_path_exists(overlay_path)
        overlay_usable = _sprite_status_is_usable(overlay_status) and overlay_exists
        if not overlay_usable:
            problems.append({
                "code": "required_equipment_overlay_missing",
                "message": "Equipment item requires a separate usable overlay PNG.",
                "slot": str(overlay_requirement["slot"]),
                "status": overlay_status,
                "path": overlay_path,
            })
        slots.append({
            "role": "equip_overlay",
            "entityId": slots[0]["entityId"],
            "assetMode": "baked_sprite",
            "required": True,
            "equipmentSlot": str(overlay_requirement["slot"]),
            "status": overlay_status,
            "path": overlay_path,
            "exists": overlay_exists,
            "completePng": overlay_exists,
            "usable": overlay_usable,
            "technicalScore": visual.get("equipOverlayTechnicalScore"),
        })

    for entity in _runtime_entities(data):
        if entity.get("kind") == "item_body":
            continue
        entity_id = str(entity.get("id") or "")
        raw_entity_visual = entity.get("visual")
        entity_visual = raw_entity_visual if isinstance(raw_entity_visual, dict) else {}
        mode = str(entity_visual.get("assetMode") or "").strip().lower()
        status = str(entity_visual.get("spriteStatus") or "")
        path = str(entity_visual.get("spritePath") or "")
        exists = _asset_path_exists(path)
        required = mode == "baked_sprite"
        if mode == "reuse_item_icon":
            usable = item_usable and path == item_path and bool(path)
        elif mode == "baked_sprite":
            usable = _sprite_status_is_usable(status) and exists
        elif mode in {"runtime_geometry", "no_asset"}:
            usable = status == "not_required" and not path
        else:
            usable = False
        if required and not usable:
            problems.append({"code": "required_entity_sprite_missing", "entityId": entity_id, "message": f"Runtime entity {entity_id!r} requires a baked PNG, but it is missing or unusable.", "status": status, "path": path})
        elif mode == "reuse_item_icon" and not usable:
            problems.append({"code": "entity_item_icon_reference_invalid", "entityId": entity_id, "message": f"Runtime entity {entity_id!r} cannot reuse a missing item sprite."})
        elif mode not in {"baked_sprite", "reuse_item_icon", "runtime_geometry", "no_asset"}:
            problems.append({"code": "entity_asset_mode_invalid", "entityId": entity_id, "message": f"Runtime entity {entity_id!r} has no valid authored asset mode."})
        slots.append({"role": "entity:" + entity_id, "entityId": entity_id, "assetMode": mode, "required": required, "status": status, "path": path, "exists": exists, "completePng": exists if path else False, "usable": usable, "technicalScore": entity_visual.get("spriteTechnicalScore")})

    entities_by_id = {str(entity.get("id") or ""): entity for entity in _runtime_entities(data)}
    for entity_id in sorted(_impact_entity_ids(data)):
        entity = entities_by_id.get(entity_id)
        raw_impact_visual = entity.get("visual") if isinstance(entity, dict) else None
        entity_visual: dict[str, Any] = raw_impact_visual if isinstance(raw_impact_visual, dict) else {}
        impact_status = str(entity_visual.get("impactSpriteStatus") or "")
        impact_path = str(entity_visual.get("impactSpritePath") or "")
        impact_exists = _asset_path_exists(impact_path)
        impact_usable = _sprite_status_is_usable(impact_status) and impact_exists
        if not impact_usable:
            problems.append({
                "code": "required_impact_sprite_missing",
                "entityId": entity_id,
                "message": f"VFX textureRole impact for {entity_id!r} requires a dedicated authored PNG.",
                "status": impact_status,
                "path": impact_path,
            })
        slots.append({
            "role": "impact:" + entity_id,
            "entityId": entity_id,
            "assetMode": "baked_sprite",
            "required": True,
            "status": impact_status,
            "path": impact_path,
            "exists": impact_exists,
            "completePng": impact_exists,
            "usable": impact_usable,
            "technicalScore": entity_visual.get("impactSpriteTechnicalScore"),
        })

    roster_paths = [resolved for slot in slots if (resolved := _resolved_asset_path(slot.get("path"))) is not None]
    problems.extend(_asset_roster_problems(roster_paths))

    return {
        "ok": not problems,
        "requiredItemSprite": bool(VISUAL_REQUIRE_ITEM_SPRITE),
        "equipmentOverlayRequired": bool(overlay_requirement["required"]),
        "requireZImageBackend": bool(VISUAL_REQUIRE_ZIMAGE_BACKEND),
        "imageBackend": IMAGE_BACKEND,
        "imageBackendRaw": IMAGE_BACKEND_RAW,
        "imageBackendConfigError": IMAGE_BACKEND_CONFIG_ERROR,
        "backendConfigChecked": bool(check_backend_config),
        "zImageBackendActive": image_backend_is_zimage(),
        "strictAiAuthorship": bool(VISUAL_STRICT_AI_AUTHORSHIP),
        "proceduralFallbackAllowed": bool(VISUAL_ALLOW_PROCEDURAL_FALLBACK),
        "problems": problems,
        "warnings": warnings,
        "slots": slots,
        "manifestPath": visual.get("assetManifestPath"),
    }


def assert_visual_delivery_ready(data: dict[str, Any]) -> dict[str, Any]:
    report = visual_delivery_report(data)
    data.setdefault("debug", {})["visualDeliveryReport"] = json.dumps(report, ensure_ascii=False)
    if not report.get("ok"):
        first = (report.get("problems") or [{}])[0]
        raise VisualDeliveryBlocked(str(first.get("message") or first.get("code") or "visual_delivery_blocked"))
    return data


__all__ = ["VisualDeliveryBlocked", "_sprite_status_is_usable", "_item_sprite_status_is_usable", "_asset_path_exists", "_asset_roster_problems", "visual_delivery_report", "assert_visual_delivery_ready"]
