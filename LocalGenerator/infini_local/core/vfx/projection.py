"""Lossless VFX wire projection, asset captions and sound identity receipts."""
from __future__ import annotations

import copy
import hashlib
from typing import Any, Mapping

from infini_local.core.repair_merge import json_values_equal
from infini_local.core.vfx.contours import (
    MAX_DRAW_WORK_UNITS,
    required_contour_budget,
)
from infini_local.core.vfx.contract import (
    VFX_MANIFEST_SCHEMA,
    _rows,
    _sound_schema,
)


def _seed(*parts: Any) -> int:
    digest = hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "little") & 0x7FFFFFFF


def _sound_projection_receipts(authored: Mapping[str, Any]) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for index, slot in enumerate(_rows(authored, "slots")):
        if not isinstance(slot, Mapping) or slot.get("rendererKind") != "soundCue":
            continue
        leaves = {"soundId": slot["soundId"]} if "soundId" in slot else {}
        if isinstance(slot.get("sound"), Mapping):
            leaves.update({f"sound.{field}": slot["sound"][field]
                           for field in _sound_schema()["properties"] if field in slot["sound"]})
        for leaf, value in leaves.items():
            receipts.append({"slotId": slot.get("id"), "status": "identity",
                             "authoredPath": f"slots[{index}].{leaf}",
                             "finalPath": f"vfxManifest.slots[{index}].{leaf}",
                             "value": copy.deepcopy(value)})
    return receipts


def audit_vfx_sound_projection(authored: Mapping[str, Any], manifest: Mapping[str, Any], receipts: Any) -> dict[str, Any]:
    """Diagnostic identity receipts; playback remains owned solely by VFX wire."""
    expected = _sound_projection_receipts(authored)
    errors: list[dict[str, Any]] = []
    if not json_values_equal(receipts, expected):
        errors.append({"path": "$.debug.vfxSoundReceipts", "message": "exact source-backed sound receipts required"})
    final_slots = _rows(manifest, "slots")
    for index, source in enumerate(_rows(authored, "slots")):
        if not isinstance(source, Mapping):
            continue
        delivered = final_slots[index] if index < len(final_slots) and isinstance(final_slots[index], Mapping) else {}
        for field in ("soundId", "sound"):
            if (field in source) != (field in delivered) or not json_values_equal(source.get(field), delivered.get(field)):
                errors.append({"path": f"$.vfxManifest.slots[{index}].{field}",
                               "message": "sound projection must preserve exact authored presence and value"})
        if any(field in source for field in ("soundId", "sound")) and any(source.get(field) != delivered.get(field) for field in ("id", "entityId", "event", "rendererKind")):
            errors.append({"path": f"$.vfxManifest.slots[{index}]", "message": "sound consumer identity must preserve its exact authored binding"})
    if len(final_slots) != len(_rows(authored, "slots")):
        errors.append({"path": "$.vfxManifest.slots", "message": "sound projection cannot add or remove slots"})
    return {"ok": not errors, "errors": errors, "receiptCount": len(expected)}


def _compile_manifest(data: Mapping[str, Any], authored: Mapping[str, Any], recipe_key_value: str) -> dict[str, Any]:
    slots: list[dict[str, Any]] = []
    for source in authored["slots"]:
        slot = copy.deepcopy(dict(source))
        # Director-only captions are consumed into RuntimeEntityVisualSpec below;
        # VfxSlotSpec is a fail-closed runtime DTO and must not carry them.
        slot.pop("spritePrompt", None)
        slot.pop("spriteNegativePrompt", None)
        slot.pop("spriteCanvasSize", None)
        slot["slotSeed"] = _seed(recipe_key_value, slot.get("id"))
        slots.append(slot)
    return {
        "schema": VFX_MANIFEST_SCHEMA,
        "recipeId": str(recipe_key_value or data.get("id") or ""),
        "budget": {
            "maxParticlesPerTick": max(16, min(256, 32 + len(slots) * 24)),
            "maxParticlesTotal": max(256, min(12000, 1000 + len(slots) * 1200)),
            "maxDrawCalls": max(32, min(MAX_DRAW_WORK_UNITS, max(64 + len(slots) * 36, required_contour_budget(slots)))),
        },
        "slots": slots,
        **({"assets": [{**copy.deepcopy(row), "spritePath": "", "spriteUrl": "", "spriteStatus": "pending", "spriteTechnicalScore": 0.0} for row in authored["assets"]]} if "assets" in authored else {}),
    }


def _hydrate_vfx_asset_prompts(data: dict[str, Any], authored: Mapping[str, Any]) -> None:
    """Losslessly move selected VFX captions into the known entity visual DTO."""

    runtime_raw = data.get("runtimeProgram")
    runtime: Mapping[str, Any] = runtime_raw if isinstance(runtime_raw, Mapping) else {}
    by_id = {
        str(row.get("id") or ""): row
        for row in runtime.get("entities") or []
        if isinstance(row, dict) and str(row.get("id") or "")
    }
    for source in authored.get("slots") or []:
        if not isinstance(source, Mapping) or str(source.get("rendererKind") or "") != "impactSprite":
            continue
        entity = by_id.get(str(source.get("entityId") or ""))
        if not isinstance(entity, dict):
            continue
        visual = entity.setdefault("visual", {})
        visual.update({
            "impactPrompt": str(source.get("spritePrompt") or "")[:1400],
            "impactNegativePrompt": str(source.get("spriteNegativePrompt") or "")[:700],
            "impactCanvasSize": source["spriteCanvasSize"],
            "impactSpritePath": "",
            "impactSpriteUrl": "",
            "impactSpriteStatus": "pending",
            "impactSpriteTechnicalScore": 0.0,
        })


def _development_manifest(data: Mapping[str, Any], recipe_key_value: str) -> dict[str, Any]:
    return _compile_manifest(data, {"slots": []}, recipe_key_value)
