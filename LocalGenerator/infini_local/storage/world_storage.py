from __future__ import annotations

import copy
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from infini_local.core import strict_json
from infini_local.core.json_debug import bounded_json_dumps
from infini_local.core.runtime_authoring.capability_registry import (
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_WIRE_SCHEMA,
)
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.vfx_manifest import VFX_MANIFEST_SCHEMA


# Exact lower-camel nested DTO surfaces accepted by strict C# v5 deserialization.
VISUAL_DELIVERY_FIELDS = frozenset({
    "accentColorHex", "assetManifestPath", "dominantColorHex", "drawOffsetX", "drawOffsetY",
    "equipOverlayPath", "equipOverlayPrompt", "equipOverlayScore", "equipOverlayStatus", "equipOverlayUrl",
    "imagePrompt", "inventoryScale", "negativePrompt", "objectType", "palette", "preferredCanvasSize",
    "preservationScore", "requiredAnchors", "semanticReviewStatus", "spritePath", "spriteRawPath",
    "spriteStatus", "spriteTechnicalScore", "spriteUrl", "style", "visualSoulArchetype",
    "visualSoulCoverage", "visualSoulEdgeDensity", "visualSoulGlow", "visualSoulPulse",
    "visualSoulSignature", "worldScale",
})

GENERATED_PARENT_SUMMARY_DELIVERY_FIELDS = frozenset({
    "schema", "name", "identity", "description", "playerExperience", "notableEffects", "backedByClaims",
    "parentComposition", "runtimePrimaryEntityId", "runtimeEntityIds",
})

PARENT_ITEM_CARD_DELIVERY_FIELDS = frozenset({
    "category", "confidence", "generatedDepth", "identity", "name", "powerScore", "sourceHint", "tags", "tier",
})

RECIPE_META_DELIVERY_FIELDS = frozenset({
    "assetBaseUrl", "assetFiles", "assetTransport", "chaosBudget", "generationDepth", "noveltyBudget",
    "parentCategories", "parentGeneratedDepths", "parentIdentities", "recipeCoherence", "sampledCategory",
    "sampledLane", "universalRecipe", "worldId", "worldScoped",
})

VFX_QUALITY_BUDGET_DELIVERY_FIELDS = frozenset({
    "effectMagnitude", "emergencyCap", "enablePersistentSmoke", "enablePointSparks", "enableSoftGlow",
    "maxDrawCalls", "maxParticlesPerTick", "maxParticlesTotal", "spawnRateMultiplier", "visualBudgetClass",
})

VFX_DEBUG_DELIVERY_FIELDS = frozenset({
    "pattern", "roles", "selectedReasons", "selectedScore", "topCandidates", "wordProbe",
})

_STORAGE_LOCKS_GUARD = threading.Lock()
_STORAGE_LOCKS: dict[str, threading.RLock] = {}


def _storage_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _STORAGE_LOCKS_GUARD:
        return _STORAGE_LOCKS.setdefault(key, threading.RLock())


def _fsync_parent_directory(path: Path) -> None:
    flags = os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0))
    try:
        fd = os.open(path, flags)
    except (OSError, ValueError):
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def safe_file_part(text: Any, default: str = "value", max_len: int = 80) -> str:
    raw = re.sub(r"[^A-Za-z0-9._-]+", "_", str(text or "").strip()).strip("._-")
    return raw[:max_len] or default


def world_recipe_dir(world_recipes_dir: Path, world_id: Any) -> Path:
    return Path(world_recipes_dir) / f"world_{safe_file_part(world_id, 'unknown_world')}"


def world_recipe_file(world_recipes_dir: Path, world_id: Any, recipe_key_value: str) -> Path:
    return world_recipe_dir(world_recipes_dir, world_id) / "recipes" / f"{safe_file_part(recipe_key_value, 'recipe')}.json"


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(strict_json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        _fsync_parent_directory(path.parent)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        return strict_json.loads_object(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError, TypeError):
        return None


def _maybe_json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = strict_json.loads(text)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
    return {}


def _runtime_entities(data: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), dict) else {}
    return [row for row in runtime.get("entities") or [] if isinstance(row, dict)]


def _visual_slots(data: dict[str, Any], report: dict[str, Any]) -> list[dict[str, Any]]:
    slots = [dict(row) for row in report.get("slots") or [] if isinstance(row, dict)]
    if slots:
        return slots
    visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
    out: list[dict[str, Any]] = []
    for entity in _runtime_entities(data):
        entity_id = str(entity.get("id") or "")
        is_item = entity.get("kind") == "item_body"
        entity_visual = entity.get("visual") if isinstance(entity.get("visual"), dict) else {}
        if is_item:
            mode = "baked_sprite"
            status = str(visual.get("spriteStatus") or "")
            path = str(visual.get("spritePath") or "")
        else:
            mode = str(entity_visual.get("assetMode") or "")
            status = str(entity_visual.get("spriteStatus") or "")
            path = str(entity_visual.get("spritePath") or "")
        out.append({
            "role": "item" if is_item else f"entity:{entity_id}",
            "entityId": entity_id,
            "assetMode": mode,
            "required": is_item or mode == "baked_sprite",
            "status": status,
            "path": path,
            "exists": bool(path),
            "usable": bool(path) if (is_item or mode == "baked_sprite") else mode in {"reuse_item_icon", "runtime_geometry", "no_asset"},
        })
    return out


def build_recipe_health(
    data: dict[str, Any],
    *,
    app_version: str,
    contract_versions: dict[str, Any] | None = None,
    visual_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Observe the accepted v5 wire; never infer or repair gameplay design."""
    debug = data.get("debug") if isinstance(data.get("debug"), dict) else {}
    visual_report = visual_report or _maybe_json_obj(debug.get("visualDeliveryReport"))
    wire = validate_runtime_wire(data)
    runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), dict) else {}
    entities = _runtime_entities(data)
    slots = _visual_slots(data, visual_report)
    required_assets_ok = all(bool(row.get("usable")) for row in slots if row.get("required"))
    visual_ok = bool(visual_report.get("ok", required_assets_ok))
    manifest = data.get("vfxManifest") if isinstance(data.get("vfxManifest"), dict) else {}
    vfx_slots = [row for row in manifest.get("slots") or [] if isinstance(row, dict)]
    vfx_ok = str(manifest.get("schema") or "") == VFX_MANIFEST_SCHEMA
    stage = data.get("llmStageAccounting") if isinstance(data.get("llmStageAccounting"), dict) else debug.get("llmStageAccounting")
    stage = dict(stage) if isinstance(stage, dict) else {}
    deliverable = is_deliverable_recipe_payload(data)
    problems: list[str] = []
    if not wire.get("ok"):
        problems.append("runtime_program_invalid")
    if not visual_ok or not required_assets_ok:
        problems.append("required_visual_delivery_failed")
    if not vfx_ok:
        problems.append("vfx_manifest_invalid")
    if not deliverable:
        problems.append("recipe_payload_not_deliverable")
    warnings: list[str] = []
    for row in visual_report.get("warnings") or []:
        warnings.append(str(row.get("code") if isinstance(row, dict) else row))
    return {
        "schema": "infini.recipe-health.runtime-program.v2",
        "ok": not problems,
        "status": "blocked" if problems else ("warning" if warnings else "healthy"),
        "appVersion": str(app_version),
        "contractVersions": contract_versions or data.get("contractVersions") or {},
        "recipeKey": str(data.get("recipeKey") or ""),
        "resultId": str(data.get("id") or ""),
        "resultName": str(data.get("name") or ""),
        "parents": {"a": str(data.get("parentA") or ""), "b": str(data.get("parentB") or "")},
        "runtime": {
            "apiVersion": str(runtime.get("apiVersion") or ""),
            "schema": str(runtime.get("schema") or ""),
            "valid": bool(wire.get("ok")),
            "entityCount": len(entities),
            "bindingCount": len(runtime.get("bindings") or []) if isinstance(runtime.get("bindings"), list) else 0,
            "eventActionCount": sum(len(row.get("events") or []) for row in entities if isinstance(row.get("events"), list)),
            "entityKinds": sorted({str(row.get("kind") or "") for row in entities}),
        },
        "visual": {"ok": visual_ok, "slots": slots, "requiredAssetsOk": required_assets_ok},
        "vfx": {"ok": vfx_ok, "schema": str(manifest.get("schema") or ""), "slotCount": len(vfx_slots)},
        "stageAccounting": {str(k): int(v or 0) for k, v in stage.items() if isinstance(v, (int, float)) and not isinstance(v, bool)},
        "warnings": warnings[:16],
        "problems": problems[:16],
        "updatedAt": time.time(),
    }


def attach_recipe_health(
    data: dict[str, Any],
    *,
    app_version: str,
    contract_versions: dict[str, Any] | None = None,
    visual_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(data, dict):
        return data
    if contract_versions:
        data["contractVersions"] = contract_versions
    data["recipeHealth"] = build_recipe_health(
        data, app_version=app_version, contract_versions=contract_versions, visual_report=visual_report,
    )
    return data


def write_world_manifest(world_recipes_dir: Path, app_version: str, world_id: Any, world_name: Any = None) -> None:
    root = world_recipe_dir(world_recipes_dir, world_id)
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "manifest.json"
    with _storage_lock(manifest_path):
        old = read_json_file(manifest_path) or {}
        stable = {
            "schema": "infini-world-recipes-v3",
            "worldId": str(world_id),
            "worldName": str(world_name or old.get("worldName") or ""),
            "worldScoped": True,
            "recipesDir": "recipes",
            "recipeAuthority": "runtime_program_v5_recipe_files",
            "derivedViews": "scan_on_demand",
            "appVersion": str(app_version),
            "runtimeApiVersion": RUNTIME_PROGRAM_API_VERSION,
        }
        if old and all(old.get(key) == value for key, value in stable.items()):
            return
        now = time.time()
        atomic_write_json(manifest_path, {**stable, "createdAt": old.get("createdAt", now), "updatedAt": now})


def strip_runtime_only_fields(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return data
    out = copy.deepcopy(data)
    for key in ("_llmHistory", "_runtimeProgramCompileCache", "_runtimePlanCompileCache"):
        out.pop(key, None)
    return out


def delivery_safe_debug(debug: Any) -> dict[str, str]:
    if not isinstance(debug, dict):
        return {}
    out: dict[str, str] = {}
    for key_raw, value in debug.items():
        key = str(key_raw)[:96]
        try:
            text = "" if value is None else (str(value) if isinstance(value, (str, int, float, bool)) else bounded_json_dumps(value, max_chars=2000))
        except Exception:
            text = repr(value)
        out[key] = text[:2000]
    return out


def _project_delivery_fields(value: Any, allowed: frozenset[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {key: copy.deepcopy(item) for key, item in value.items() if key in allowed}


def sanitize_recipe_for_delivery(data: Any) -> Any:
    """Project the accepted v5 wire; never translate legacy contracts."""
    if not isinstance(data, dict):
        return data
    out = strip_runtime_only_fields(data)
    for retired in ("attack", "runtimePlan", "runtimeCompiled", "runtimeAffordance", "runtimeArchetype", "presentationGenome"):
        out.pop(retired, None)
    out.pop("visualKit", None)
    out.pop("runtimeContract", None)
    out["debug"] = delivery_safe_debug(out.get("debug"))

    visual = _project_delivery_fields(out.get("visual"), VISUAL_DELIVERY_FIELDS)
    if visual is not None:
        out["visual"] = visual
    summary = _project_delivery_fields(out.get("generatedParentSummary"), GENERATED_PARENT_SUMMARY_DELIVERY_FIELDS)
    if summary is not None:
        out["generatedParentSummary"] = summary
    recipe_meta = _project_delivery_fields(out.get("recipeMeta"), RECIPE_META_DELIVERY_FIELDS)
    if recipe_meta is not None:
        out["recipeMeta"] = recipe_meta

    item_knowledge = out.get("itemKnowledge")
    if isinstance(item_knowledge, dict):
        clean_knowledge = copy.deepcopy(item_knowledge)
        if isinstance(clean_knowledge.get("parents"), list):
            clean_knowledge["parents"] = [
                _project_delivery_fields(row, PARENT_ITEM_CARD_DELIVERY_FIELDS) if isinstance(row, dict) else row
                for row in clean_knowledge["parents"]
            ]
        result_card = _project_delivery_fields(clean_knowledge.get("resultCard"), PARENT_ITEM_CARD_DELIVERY_FIELDS)
        if result_card is not None:
            clean_knowledge["resultCard"] = result_card
        out["itemKnowledge"] = clean_knowledge

    manifest = out.get("vfxManifest")
    if isinstance(manifest, dict):
        clean_manifest = copy.deepcopy(manifest)
        budget = _project_delivery_fields(clean_manifest.get("budget"), VFX_QUALITY_BUDGET_DELIVERY_FIELDS)
        if budget is not None:
            clean_manifest["budget"] = budget
        vfx_debug = _project_delivery_fields(clean_manifest.get("debug"), VFX_DEBUG_DELIVERY_FIELDS)
        if vfx_debug is not None:
            clean_manifest["debug"] = vfx_debug
        out["vfxManifest"] = clean_manifest
    return out


def write_world_recipe_cache(
    world_recipes_dir: Path,
    app_version: str,
    recipe_key_value: str,
    world_id: Any,
    data: dict[str, Any],
    *,
    parent_a_name: str = "",
    parent_b_name: str = "",
    world_name: Any = None,
) -> None:
    write_world_manifest(world_recipes_dir, app_version, world_id, world_name)
    payload = sanitize_recipe_for_delivery(data)
    payload["recipeKey"] = str(recipe_key_value)
    if parent_a_name:
        payload["parentA"] = str(parent_a_name)
    if parent_b_name:
        payload["parentB"] = str(parent_b_name)
    payload.setdefault("recipeMeta", {})
    payload["recipeMeta"].update({"worldScoped": True, "worldId": str(world_id)})
    if not isinstance(payload.get("recipeHealth"), dict):
        attach_recipe_health(
            payload,
            app_version=app_version,
            contract_versions=payload.get("contractVersions") if isinstance(payload.get("contractVersions"), dict) else None,
        )
    if not is_deliverable_recipe_payload(payload):
        raise ValueError("refusing to cache non-deliverable runtime-program v5 payload")
    recipe_path = world_recipe_file(world_recipes_dir, world_id, recipe_key_value)
    with _storage_lock(recipe_path):
        atomic_write_json(recipe_path, payload)


def quarantine_world_recipe_cache(
    world_recipes_dir: Path,
    *,
    world_id: Any,
    recipe_key_value: str,
    reason: str,
    details: dict[str, Any] | None = None,
) -> str:
    """Move one broken authoritative recipe aside so future crafts can regenerate it."""
    source = world_recipe_file(world_recipes_dir, world_id, recipe_key_value)
    with _storage_lock(source):
        if not source.exists():
            return ""
        invalid_dir = world_recipe_dir(world_recipes_dir, world_id) / "invalid"
        invalid_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        reason_part = safe_file_part(reason, "invalid", 48)
        destination = invalid_dir / f"{safe_file_part(recipe_key_value, 'recipe')}_{stamp}_{reason_part}.json"
        counter = 1
        while destination.exists():
            destination = invalid_dir / f"{safe_file_part(recipe_key_value, 'recipe')}_{stamp}_{reason_part}_{counter}.json"
            counter += 1
        source.replace(destination)
        _fsync_parent_directory(source.parent)
        _fsync_parent_directory(destination.parent)
        atomic_write_json(
            destination.with_suffix(".reason.json"),
            {
                "schema": "infini-invalid-recipe-cache-v1",
                "worldId": str(world_id),
                "recipeKey": str(recipe_key_value),
                "reason": str(reason),
                "quarantinedAt": time.time(),
                "payloadFile": destination.name,
                "details": details or {},
            },
        )
        return str(destination)

def read_world_recipe_cache(
    world_recipes_dir: Path,
    app_version: str,
    recipe_identity_version: str,
    recipe_key_value: str,
    world_id: Any,
    world_name: Any = None,
) -> dict[str, Any] | None:
    recipe_path = world_recipe_file(world_recipes_dir, world_id, recipe_key_value)
    with _storage_lock(recipe_path):
        data = read_json_file(recipe_path)
        if not data:
            # A syntactically broken/empty cache file otherwise survives forever and is
            # reparsed on every craft. Preserve it under invalid/ for diagnosis, then let
            # the caller regenerate from the original parents.
            if recipe_path.exists():
                try:
                    quarantine_world_recipe_cache(
                        world_recipes_dir,
                        world_id=world_id,
                        recipe_key_value=recipe_key_value,
                        reason="json_unreadable_or_empty",
                        details={"sourcePath": str(recipe_path)},
                    )
                except (OSError, ValueError, TypeError):
                    pass
            return None
        data.pop("_llmHistory", None)
        data.setdefault("debug", {})["cacheHit"] = "world_file"
        data.setdefault("debug", {})["cacheScope"] = "world"
        data.setdefault("debug", {}).setdefault("recipeIdentityVersion", recipe_identity_version)
        data.setdefault("recipeMeta", {})["worldScoped"] = True
        data.setdefault("recipeMeta", {})["worldId"] = str(world_id)
        data.setdefault("recipeMeta", {})["storage"] = "world_recipe_file_authority"
        return sanitize_recipe_for_delivery(data)





def is_deliverable_recipe_payload(data: Any) -> bool:
    if not isinstance(data, dict) or not str(data.get("name") or "").strip():
        return False
    if int(data.get("schemaVersion") or 0) != 5:
        return False
    if str(data.get("runtimeApiVersion") or "") != RUNTIME_PROGRAM_API_VERSION:
        return False
    if str(data.get("id") or "").strip().lower() in {"", "placeholder"}:
        return False
    source_mode = str(data.get("sourceMode") or "").strip().lower()
    if source_mode in {"fallback", "failed", "placeholder"} or source_mode.startswith("fallback_"):
        return False
    runtime = data.get("runtimeProgram")
    if not isinstance(runtime, dict) or runtime.get("schema") != RUNTIME_WIRE_SCHEMA:
        return False
    if not validate_runtime_wire(data).get("ok"):
        return False
    manifest = data.get("vfxManifest")
    if not isinstance(manifest, dict) or manifest.get("schema") != VFX_MANIFEST_SCHEMA:
        return False
    return True
