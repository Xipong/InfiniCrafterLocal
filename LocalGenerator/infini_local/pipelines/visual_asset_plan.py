from __future__ import annotations

"""Per-runtime-entity visual asset plan.

The plan is a projection of Visual Director choices.  It never infers assets from
weapon families or mutates gameplay topology.
"""

import copy
from typing import Any, Mapping


_ALLOWED_MODES = {"baked_sprite", "reuse_item_icon", "runtime_geometry", "no_asset"}


def _runtime(data: Mapping[str, Any]) -> Mapping[str, Any]:
    value = data.get("runtimeProgram")
    return value if isinstance(value, Mapping) else {}


def _entity_rows(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _runtime(data).get("entities") or [] if isinstance(row, dict)]


def _entity_by_id(data: Mapping[str, Any], entity_id: str) -> dict[str, Any] | None:
    return next((row for row in _entity_rows(data) if str(row.get("id") or "") == entity_id), None)


def authored_asset_mode(data: dict[str, Any], role: str) -> str:
    if role == "item":
        return "baked_sprite"
    entity_id = role.removeprefix("entity:")
    entity = _entity_by_id(data, entity_id)
    visual = entity.get("visual") if isinstance(entity, dict) and isinstance(entity.get("visual"), dict) else {}
    mode = str(visual.get("assetMode") or "").strip().lower()
    return mode if mode in _ALLOWED_MODES else ""


def visual_asset_runtime_gate(data: dict[str, Any], role: str, authored_mode: str) -> tuple[str, str]:
    mode = str(authored_mode or "").strip().lower()
    if mode not in _ALLOWED_MODES:
        return "", "invalid_or_missing_authored_asset_mode"
    if role == "item" and mode != "baked_sprite":
        return "", "item_body_requires_baked_sprite"
    return mode, "authored_runtime_entity_asset_mode"


def apply_visual_asset_runtime_gates(data: dict[str, Any], kit: dict[str, Any]) -> None:
    del kit
    for entity in _entity_rows(data):
        visual = entity.get("visual") if isinstance(entity.get("visual"), dict) else {}
        role = "item" if entity.get("kind") == "item_body" else "entity:" + str(entity.get("id") or "")
        mode, reason = visual_asset_runtime_gate(data, role, str(visual.get("assetMode") or ""))
        visual["assetMode"] = mode
        visual["runtimeGateReason"] = reason
        entity["visual"] = visual


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
    item_visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    for entity in _entity_rows(data):
        entity_id = str(entity.get("id") or "")
        entity_visual = entity.get("visual") if isinstance(entity.get("visual"), dict) else {}
        is_item = entity.get("kind") == "item_body"
        role = "item" if is_item else "entity:" + entity_id
        mode, reason = visual_asset_runtime_gate(data, role, "baked_sprite" if is_item else str(entity_visual.get("assetMode") or ""))
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
    return copy.deepcopy(plan)


__all__ = [
    "apply_visual_asset_runtime_gates",
    "authored_asset_mode",
    "build_visual_asset_plan",
    "finalize_visual_asset_runtime_gates",
    "visual_asset_runtime_gate",
]
