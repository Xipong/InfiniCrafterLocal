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
from infini_local.services import asset_sync_service


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


def _asset_path_exists(path_value: Any) -> bool:
    text = str(path_value or "").strip()
    if not text:
        return False
    try:
        path = Path(text)
        if path.exists() and path.is_file():
            return True
        name = asset_sync_service.asset_filename_from_path(text)
        if not name:
            return False
        found = asset_sync_service.find_asset_file(name, sprite_dir=SPRITE_DIR, world_recipes_dir=WORLD_RECIPES_DIR)
        return bool(found and found.exists() and found.is_file())
    except Exception:
        return False


def _runtime_entities(data: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), dict) else {}
    return [row for row in runtime.get("entities") or [] if isinstance(row, dict)]


def visual_delivery_report(data: dict[str, Any], *, check_backend_config: bool = True) -> dict[str, Any]:
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
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
        "path": item_path, "exists": item_exists, "usable": item_usable,
        "technicalScore": visual.get("spriteTechnicalScore"),
    }]

    for entity in _runtime_entities(data):
        if entity.get("kind") == "item_body":
            continue
        entity_id = str(entity.get("id") or "")
        entity_visual = entity.get("visual") if isinstance(entity.get("visual"), dict) else {}
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
        slots.append({"role": "entity:" + entity_id, "entityId": entity_id, "assetMode": mode, "required": required, "status": status, "path": path, "exists": exists, "usable": usable, "technicalScore": entity_visual.get("spriteTechnicalScore")})

    return {
        "ok": not problems,
        "requiredItemSprite": bool(VISUAL_REQUIRE_ITEM_SPRITE),
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


__all__ = ["VisualDeliveryBlocked", "_sprite_status_is_usable", "_item_sprite_status_is_usable", "_asset_path_exists", "visual_delivery_report", "assert_visual_delivery_ready"]
