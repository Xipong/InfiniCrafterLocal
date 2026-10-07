from __future__ import annotations

"""Final visual delivery gate for runtime-entity assets."""

import copy
import json
from pathlib import Path
from typing import Any

from infini_local.core.config_bootstrap import SPRITE_DIR, WORLD_RECIPES_DIR
from infini_local.core.vfx_manifest import validate_vfx_manifest_wire, vfx_png_dependencies
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
from infini_local.pipelines.sprite_postprocess import validate_processed_sprite, sprite_validation_fatal
from infini_local.pipelines.visual_asset_plan import equipment_overlay_requirement
from infini_local.services import asset_sync_service
from infini_local.web.server_utility_routes import MAX_ASSET_RESPONSE_BYTES


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
    # Readiness is for the filename transfer contract, not arbitrary local files.
    # Project stale Windows paths/URLs just as /get_asset does, then validate the
    # exact root-local file chosen by that existing serving owner (including its
    # root precedence). A local shadow must never supply different ready bytes.
    name = asset_sync_service.asset_filename_from_path(path_value)
    if not name or Path(name).suffix.lower() != ".png":
        return None
    return asset_sync_service.find_asset_file(
        name, sprite_dir=SPRITE_DIR, world_recipes_dir=WORLD_RECIPES_DIR,
    )


def _file_snapshot(path: Path) -> tuple[int, int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


class _DeliveryAssetAssessment:
    """One read-only assessment; no result survives into another operation.

    Keep the serving owner's selection and file identity stable across the
    envelope/ingredient validators and all consumers of their results. Changes
    during the call fail closed, including same-size/restored-mtime writes.
    This is an observation, not a persisted AssetSync certificate.
    """

    def __init__(self, assets: list[dict[str, Any]] | None = None) -> None:
        self.selected: dict[str, Path | None] = {}
        self.files: dict[Path, dict[str, Any]] = {}
        self.ingredients: dict[Path, dict[str, Any]] = {}
        for asset in assets or []:
            path = self.path(asset.get("spritePath"))
            if path is not None:
                self.ingredients.setdefault(path.resolve(), asset)

    def path(self, value: Any) -> Path | None:
        name = asset_sync_service.asset_filename_from_path(value)
        if not name or Path(name).suffix.lower() != ".png":
            return None
        if name not in self.selected:
            selected = _resolved_asset_path(name)
            self.selected[name] = selected.resolve() if selected is not None else None
        return self.selected[name]

    def facts(self, value: Any) -> dict[str, Any]:
        path = self.path(value)
        if path is None:
            return {"path": None, "size": 0, "complete": False}
        key = path.resolve()
        if key not in self.files:
            facts: dict[str, Any] = {"path": path, "size": 0, "complete": False, "snapshot": None}
            self.files[key] = facts
            try:
                facts["snapshot"] = _file_snapshot(path)
                facts["size"] = facts["snapshot"][2]
                if facts["size"] <= MAX_ASSET_RESPONSE_BYTES:
                    ingredient = self.ingredients.get(key)
                    if ingredient is None:
                        facts["complete"] = asset_sync_service.is_complete_png_file(path)
                    else:
                        # This validator already invokes the canonical PNG
                        # envelope gate. Reuse it instead of validating twice.
                        validation = validate_processed_sprite(
                            str(path), "vfx_" + ingredient["layout"], expected_canvas=ingredient["canvasSize"],
                        )
                        facts["validation"] = validation
                        facts["complete"] = not any(reason in {
                            "invalid_png_envelope", "pillow_unavailable_required",
                        } for reason in validation.get("reasons", []))
                if _file_snapshot(path) != facts["snapshot"]:
                    facts["complete"] = False
            except (OSError, ValueError):
                facts["complete"] = False
        return self.files[key]

    def complete(self, value: Any) -> bool:
        return bool(self.facts(value)["complete"])

    def ingredient_validation(self, asset: dict[str, Any]) -> dict[str, Any]:
        facts = self.facts(asset.get("spritePath"))
        if facts["size"] > MAX_ASSET_RESPONSE_BYTES:
            return {"ok": False, "reasons": ["asset_png_byte_limit_exceeded"]}
        if not facts["complete"]:
            return {"ok": False, "reasons": ["invalid_png_envelope"]}
        path = facts["path"]
        owner = self.ingredients.get(path.resolve()) if path is not None else None
        if owner is not None and (owner["layout"], owner["canvasSize"]) != (asset["layout"], asset["canvasSize"]):
            # Conflicting ingredient identities are rejected by the roster too;
            # never lend another ingredient's topology-specific validation.
            return {"ok": False, "reasons": ["final_canvas_mismatch"]}
        return facts.get("validation") or {"ok": False, "reasons": ["invalid_png_envelope"]}

    def changed_problems(self) -> list[dict[str, Any]]:
        changed: list[dict[str, Any]] = []
        for name, path in self.selected.items():
            current = _resolved_asset_path(name)
            try:
                same_selection = (current.resolve() if current is not None else None) == (path.resolve() if path is not None else None)
                facts = self.files.get(path.resolve()) if path is not None else None
                same_file = facts is None or (path is not None and _file_snapshot(path) == facts["snapshot"])
            except OSError:
                same_selection = same_file = False
            if not same_selection or not same_file:
                changed.append({"code": "asset_roster_changed_during_assessment", "file": name,
                                "message": f"Runtime PNG {name!r} or its serving selection changed during assessment."})
        return changed


def _asset_path_exists(path_value: Any, *, _assessment: _DeliveryAssetAssessment | None = None) -> bool:
    assessment = _assessment if _assessment is not None else _DeliveryAssetAssessment()
    complete = assessment.complete(path_value)
    return complete and (_assessment is not None or not assessment.changed_problems())


def _asset_roster_problems(paths: list[Any], *, _assessment: _DeliveryAssetAssessment | None = None) -> list[dict[str, Any]]:
    """Validate every nonempty canonical DTO path, not only resolved files.

    Filename projection and root precedence are the existing HTTP sync owner's.
    Inactive overlay/body/impact paths remain in that owner's transfer roster.
    They therefore need the same envelope and transfer bounds as active images.
    """
    assessment = _assessment if _assessment is not None else _DeliveryAssetAssessment()
    unique: dict[str, Path | None] = {}
    sizes: dict[str, int] = {}
    problems: list[dict[str, Any]] = []
    checked: set[str] = set()
    for value in paths:
        if value is None or value == "":
            continue
        name = asset_sync_service.asset_filename_from_path(value)
        detail = {"path": str(value), "file": name}
        if not name or Path(name).suffix.lower() != ".png":
            problems.append({"code": "asset_roster_invalid_filename", **detail,
                             "message": "Every nonempty runtime asset path requires a safe PNG transfer basename."})
            continue
        key = name.casefold()
        path = assessment.path(value)
        unique.setdefault(key, None)
        if path is None:
            problems.append({"code": "asset_roster_file_missing", **detail,
                             "message": f"Runtime PNG {name!r} is not available from the canonical serving roots."})
            continue
        previous = unique.get(key)
        if previous is not None and previous.resolve() != path.resolve():
            problems.append({"code": "asset_roster_filename_collision", **detail,
                             "message": f"Distinct local assets alias the network PNG filename {key!r}."})
        unique[key] = path
        if key in checked:
            continue
        checked.add(key)
        facts = assessment.facts(value)
        size = facts["size"]
        sizes[key] = size
        if size > MAX_ASSET_RESPONSE_BYTES:
            problems.append({"code": "asset_roster_file_byte_limit_exceeded", **detail,
                             "message": f"Runtime PNG {name!r} is {size} bytes; maximum is {MAX_ASSET_RESPONSE_BYTES}."})
        elif not facts["complete"]:
            problems.append({"code": "asset_roster_invalid_png", **detail,
                             "message": f"Runtime PNG {name!r} is not a complete PNG."})
    if len(unique) > MAX_DELIVERABLE_ASSET_FILES:
        problems.append({
            "code": "asset_roster_file_limit_exceeded",
            "message": f"Generated asset roster has {len(unique)} files; maximum is {MAX_DELIVERABLE_ASSET_FILES}.",
        })
    total_bytes = sum(sizes.values())
    if total_bytes > MAX_DELIVERABLE_ASSET_BYTES:
        problems.append({
            "code": "asset_roster_byte_limit_exceeded",
            "message": f"Generated asset roster is {total_bytes} bytes; maximum is {MAX_DELIVERABLE_ASSET_BYTES}.",
        })
    if _assessment is None:
        problems.extend(assessment.changed_problems())
    return problems


def _runtime_entities(data: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), dict) else {}
    return [row for row in runtime.get("entities") or [] if isinstance(row, dict)]


def visual_delivery_report(data: dict[str, Any], *, check_backend_config: bool = True) -> dict[str, Any]:
    # Every selected producer/status and retained path belongs to this same DTO
    # snapshot; caller mutations cannot mix a healthy sibling into its proof.
    data = copy.deepcopy(data)
    raw_visual = data.get("visual")
    visual: dict[str, Any] = raw_visual if isinstance(raw_visual, dict) else {}
    problems: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    vfx_report = validate_vfx_manifest_wire(data) if "vfxManifest" in data else {"ok": True, "errors": []}
    png_dependencies = vfx_png_dependencies(data)["dependencies"] if vfx_report["ok"] else []
    manifest_value = data.get("vfxManifest")
    manifest: dict[str, Any] = manifest_value if isinstance(manifest_value, dict) else {}
    assessment = _DeliveryAssetAssessment((manifest.get("assets") or []) if vfx_report["ok"] else [])
    if not vfx_report["ok"]:
        problems.append({"code": "vfx_manifest_invalid", "message": "VFX wire shape/references are invalid.", "errors": vfx_report["errors"]})
    if check_backend_config and IMAGE_BACKEND_CONFIG_ERROR:
        problems.append({"code": "image_backend_configuration_invalid", "message": IMAGE_BACKEND_CONFIG_ERROR})
    if check_backend_config and IMAGE_BACKEND == "procedural" and (VISUAL_STRICT_AI_AUTHORSHIP or not VISUAL_ALLOW_PROCEDURAL_FALLBACK):
        problems.append({"code": "procedural_backend_not_explicitly_allowed", "message": "Procedural authoring is disabled by visual policy."})
    if check_backend_config and VISUAL_REQUIRE_ZIMAGE_BACKEND and not image_backend_is_zimage():
        problems.append({"code": "zimage_required_but_inactive", "message": "The configured delivery policy requires Z-Image/sd.cpp."})

    item_status = str(visual.get("spriteStatus") or "")
    item_path = str(visual.get("spritePath") or "")
    item_exists = _asset_path_exists(item_path, _assessment=assessment)
    item_usable = _item_sprite_status_is_usable(item_status) and item_exists
    from infini_local.core.runtime_authoring.binding_use_policy import placed_body_binding_ids
    placed_bindings = placed_body_binding_ids(data)
    if placed_bindings and not item_usable:
        problems.append({"code": "required_placed_body_sprite_missing",
                         "message": "Explicit placed-body presentation requires the existing root item PNG; no native/procedural replacement is permitted.",
                         "bindingIds": list(placed_bindings), "status": item_status, "path": item_path})
    if VISUAL_REQUIRE_ITEM_SPRITE and not item_usable:
        problems.append({"code": "required_item_sprite_missing", "message": "Generated item sprite is required, but no usable processed PNG is present.", "status": item_status, "path": item_path})

    slots: list[dict[str, Any]] = [{
        "role": "item", "entityId": next((str(e.get("id") or "") for e in _runtime_entities(data) if e.get("kind") == "item_body"), ""),
        "assetMode": "baked_sprite", "required": bool(VISUAL_REQUIRE_ITEM_SPRITE or placed_bindings), "status": item_status,
        "path": item_path, "exists": item_exists, "completePng": item_exists, "usable": item_usable,
        "technicalScore": visual.get("spriteTechnicalScore"),
    }]

    overlay_requirement = equipment_overlay_requirement(data)
    if overlay_requirement["required"]:
        overlay_status = str(visual.get("equipOverlayStatus") or "")
        overlay_path = str(visual.get("equipOverlayPath") or "")
        overlay_exists = _asset_path_exists(overlay_path, _assessment=assessment)
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
        exists = _asset_path_exists(path, _assessment=assessment)
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
    for entity_id in sorted({row["entityId"] for row in png_dependencies if row["source"] == "impact"}):
        entity = entities_by_id.get(entity_id)
        raw_impact_visual = entity.get("visual") if isinstance(entity, dict) else None
        entity_visual: dict[str, Any] = raw_impact_visual if isinstance(raw_impact_visual, dict) else {}
        impact_status = str(entity_visual.get("impactSpriteStatus") or "")
        impact_path = str(entity_visual.get("impactSpritePath") or "")
        impact_exists = _asset_path_exists(impact_path, _assessment=assessment)
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

    raw_manifest = data.get("vfxManifest")
    manifest = raw_manifest if isinstance(raw_manifest, dict) else {}
    occupied_names = {asset_sync_service.asset_filename_from_path(path).casefold()
                      for path in asset_sync_service.runtime_asset_paths(data, include_vfx_assets=False) if path}
    for asset in (manifest.get("assets") or []) if vfx_report["ok"] else []:
        path = str(asset.get("spritePath") or "")
        name = asset_sync_service.asset_filename_from_path(path).casefold()
        if name and name in occupied_names:
            problems.append({"code": "asset_roster_filename_collision", "assetId": asset["id"],
                             "message": f"Requested VFX ingredient {asset['id']!r} aliases another asset's PNG filename."})
        occupied_names.add(name)
        status = str(asset.get("spriteStatus") or "")
        resolved = assessment.path(path)
        complete = _asset_path_exists(path, _assessment=assessment)
        validation = assessment.ingredient_validation(asset)
        usable = complete and status in {"generated", "generated_warn_invalid"} and not sprite_validation_fatal(validation)
        if not usable:
            problems.append({
                "code": "required_vfx_sprite_missing_or_invalid", "assetId": asset["id"],
                "message": f"Requested VFX ingredient {asset['id']!r} requires its exact canvas and a usable alpha PNG.",
                "status": status, "path": path, "validation": validation,
            })
        slots.append({
            "role": "vfx:" + asset["id"], "vfxAssetId": asset["id"], "assetMode": "baked_sprite",
            "layout": asset["layout"], "canvas": asset["canvasSize"], "required": True,
            "status": status, "path": path, "exists": resolved is not None, "completePng": complete,
            "usable": usable, "technicalScore": asset.get("spriteTechnicalScore"), "validation": validation,
        })
    # The same canonical projection gates legacy and material consumers. Reuse
    # selects the item owner, aliases select only their exact entity, and ignored
    # primitive/Dust/cue hints can never invent a PNG requirement.
    slots_by_role = {row["role"]: row for row in slots}
    for dependency in png_dependencies:
        role = dependency["role"]
        producer = slots_by_role.get(role)
        # Item-body baked entity selection consumes its projected entity path,
        # while reuse consumes the root path. Check the actual selected metadata,
        # not a healthy sibling/item image that the renderer never selects.
        ready = bool(producer and producer["usable"]
            and asset_sync_service.asset_filename_from_path(dependency["spritePath"])
                == asset_sync_service.asset_filename_from_path(producer["path"])
            and str(dependency["spriteStatus"] or "").strip().lower() in {
                "generated", "generated_warn_invalid", "fallback", "fallback_after_failed_generation",
            })
        if producer is not None:
            producer["required"] = True
            producer["usable"] = ready
        if not ready:
            problems.append({
                "code": "required_vfx_texture_not_ready", "slotId": dependency["slotId"], "role": role,
                "message": f"VFX slot {dependency['slotId']!r} requires its selected {dependency['source']} producer's ready PNG.",
            })
    problems.extend(_asset_roster_problems(asset_sync_service.runtime_asset_paths(data), _assessment=assessment))
    problems.extend(assessment.changed_problems())

    return {
        "ok": not problems,
        "requiredItemSprite": bool(VISUAL_REQUIRE_ITEM_SPRITE or placed_bindings),
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
