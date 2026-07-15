from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from infini_local.core.config_bootstrap import (
    SPRITE_DIR,
    WORLD_RECIPES_DIR,
)
from infini_local.core.runtime_authoring.normalize import runtime_plan
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
from infini_local.services import asset_sync_service
from infini_local.pipelines.visual_asset_plan import authored_asset_mode
from infini_local.pipelines.visual_prompt_contracts import image_backend_is_zimage


# AGENT MAP: final delivery gate for already-produced visual assets.
# It reports missing files/config problems only; it does not judge art or route gameplay.




class VisualDeliveryBlocked(RuntimeError):
    """Fresh craft cannot be delivered because the mandatory visual asset is not usable."""

def _sprite_status_is_usable(status: Any) -> bool:
    s = str(status or "").strip().lower()
    return bool(s) and s not in {"failed", "prompt_only", "placeholder", "skipped", "skipped_disabled_by_settings", "skipped_not_authored_baked"}

def _item_sprite_status_is_usable(status: Any) -> bool:
    s = str(status or "").strip().lower()
    if s == "generated_warn_invalid":
        return True
    return _sprite_status_is_usable(status)

def _asset_path_exists(path_value: Any) -> bool:
    text = str(path_value or "").strip()
    if not text:
        return False
    try:
        p = Path(text)
        if p.exists() and p.is_file():
            return True
        name = asset_sync_service.asset_filename_from_path(text)
        if not name:
            return False
        found = asset_sync_service.find_asset_file(name, sprite_dir=SPRITE_DIR, world_recipes_dir=WORLD_RECIPES_DIR)
        return bool(found and found.exists() and found.is_file())
    except Exception:
        return False

def visual_delivery_report(data: dict[str, Any], *, check_backend_config: bool = True) -> dict[str, Any]:
    """Inspect the exact visual payload that will be sent to tML.

    This is a delivery gate, not an art critic: it verifies that required runtime
    paths point at usable files and that config does not accidentally fall back to a
    non-visual craft. Optional projectile/impact/child/field slots are reported but
    do not block unless they are marked required by the asset plan/manifest.
    """
    visual_raw = data.get("visual")
    attack_raw = data.get("attack")
    visual: dict[str, Any] = dict(visual_raw) if isinstance(visual_raw, dict) else {}
    attack: dict[str, Any] = dict(attack_raw) if isinstance(attack_raw, dict) else {}
    problems: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if check_backend_config and IMAGE_BACKEND_CONFIG_ERROR:
        problems.append({
            "code": "image_backend_configuration_invalid",
            "message": IMAGE_BACKEND_CONFIG_ERROR,
            "imageBackendRaw": IMAGE_BACKEND_RAW,
            "imageBackend": IMAGE_BACKEND,
        })
    if check_backend_config and IMAGE_BACKEND == "procedural" and (VISUAL_STRICT_AI_AUTHORSHIP or not VISUAL_ALLOW_PROCEDURAL_FALLBACK):
        problems.append({
            "code": "procedural_backend_not_explicitly_allowed",
            "message": "Procedural image authoring is disabled by the active AI-authorship policy.",
            "imageBackend": IMAGE_BACKEND,
            "strictAiAuthorship": bool(VISUAL_STRICT_AI_AUTHORSHIP),
            "proceduralFallbackAllowed": bool(VISUAL_ALLOW_PROCEDURAL_FALLBACK),
        })

    if check_backend_config and VISUAL_REQUIRE_ZIMAGE_BACKEND and not image_backend_is_zimage():
        problems.append({
            "code": "zimage_required_but_inactive",
            "message": "INFINI_VISUAL_REQUIRE_ZIMAGE_BACKEND=1, but the active image backend is not Z-Image/sd.cpp.",
            "imageBackend": IMAGE_BACKEND,
            "zImagePromptContract": ZIMAGE_PROMPT_CONTRACT,
        })

    item_status = str(visual.get("spriteStatus") or "")
    item_path = str(visual.get("spritePath") or "")
    item_exists = _asset_path_exists(item_path)
    item_ok = _item_sprite_status_is_usable(item_status) and item_exists
    if item_status.strip().lower() == "generated_warn_invalid" and item_exists:
        warnings.append({
            "code": "item_sprite_generated_warn_invalid",
            "status": item_status,
            "path": item_path,
            "message": "Mandatory item sprite exists but failed an art-quality validation; deliver it with warning instead of treating it as missing.",
        })
    if VISUAL_REQUIRE_ITEM_SPRITE and not item_ok:
        problems.append({
            "code": "required_item_sprite_missing",
            "message": "Generated item sprite is required, but no usable processed PNG is present.",
            "status": item_status,
            "path": item_path,
            "backend": IMAGE_BACKEND,
        })

    slots: list[dict[str, Any]] = [{
        "role": "item",
        "required": bool(VISUAL_REQUIRE_ITEM_SPRITE),
        "status": item_status,
        "path": item_path,
        "exists": _asset_path_exists(item_path),
        "usable": item_ok,
        "technicalScore": visual.get("spriteTechnicalScore"),
    }]
    for role, prefix in [
        ("projectile", "projectile"),
        ("impact", "impact"),
        ("child", "child"),
        ("field", "field"),
    ]:
        status = str(attack.get(f"{prefix}SpriteStatus") or "")
        path = str(attack.get(f"{prefix}SpritePath") or "")
        exists = _asset_path_exists(path)
        usable = _sprite_status_is_usable(status) and exists
        required = role == "projectile" and bool(attack.get("enabled")) and authored_asset_mode(data, "projectile") == "baked_sprite" and not runtime_plan(data)
        if status.strip().lower() == "generated_warn_invalid" and exists:
            warnings.append({
                "code": f"{role}_sprite_generated_warn_invalid",
                "status": status,
                "path": path,
                "message": f"{role} sprite exists and has only nonfatal fit/art warnings; deliver the AI-authored asset with diagnostics.",
            })
        if required and not usable:
            problems.append({
                "code": f"required_{role}_sprite_missing",
                "message": f"Required {role} baked sprite is missing or unusable.",
                "status": status,
                "path": path,
            })
        elif status and not usable and status not in {"skipped_not_authored_baked", "skipped_disabled_by_settings"}:
            warnings.append({"code": f"optional_{role}_sprite_unusable", "status": status, "path": path})
        slots.append({
            "role": role,
            "required": required,
            "status": status,
            "path": path,
            "exists": exists,
            "usable": usable,
            "technicalScore": attack.get(f"{prefix}SpriteScore"),
            "assetMode": authored_asset_mode(data, role),
        })

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
        "semanticReviewStatus": str(visual.get("semanticReviewStatus") or "not_performed"),
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


__all__ = [
    "VisualDeliveryBlocked",
    "_sprite_status_is_usable",
    "_item_sprite_status_is_usable",
    "_asset_path_exists",
    "visual_delivery_report",
    "assert_visual_delivery_ready",
]
