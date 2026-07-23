from __future__ import annotations

import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from infini_local.core import strict_json
from infini_local.core.json_debug import bounded_json_dumps
from infini_local.core.boundary_models import (
    ATTACK_NON_WIRE_FIELDS,
    GAMEPLAY_DEBUG_ONLY_FIELDS,
    REJECTED_ENGINE_CALL_DEBUG_ONLY_FIELDS,
)


# Exact lower-camel JSON surface accepted by strict C# VisualSpec deserialization.
# Visual Director/planner fields remain available during generation in visualKit/debug,
# but must not leak into the committed Terraria wire payload.
VISUAL_DELIVERY_FIELDS = frozenset({
    "accentColorHex",
    "assetManifestPath",
    "childImagePrompt",
    "dominantColorHex",
    "drawOffsetX",
    "drawOffsetY",
    "fieldImagePrompt",
    "imagePrompt",
    "impactImagePrompt",
    "inventoryScale",
    "negativePrompt",
    "objectType",
    "palette",
    "preferredCanvasSize",
    "preservationScore",
    "projectileImagePrompt",
    "requiredAnchors",
    "spritePath",
    "spriteRawPath",
    "spriteStatus",
    "spriteUrl",
    "equipOverlayPrompt",
    "equipOverlayStatus",
    "equipOverlayPath",
    "equipOverlayUrl",
    "equipOverlayScore",
    "style",
    "spriteTechnicalScore",
    "semanticReviewStatus",
    "visualSoulArchetype",
    "visualSoulCoverage",
    "visualSoulEdgeDensity",
    "visualSoulGlow",
    "visualSoulPulse",
    "visualSoulSignature",
    "visualSoulTooltip",
    "worldScale",
})

GENERATED_PARENT_SUMMARY_DELIVERY_FIELDS = frozenset({
    "category",
    "damageClass",
    "fantasy",
    "name",
    "notableEffects",
    "runtime",
    "visualIdentity",
})

PARENT_ITEM_CARD_DELIVERY_FIELDS = frozenset({
    "category",
    "confidence",
    "generatedDepth",
    "identity",
    "name",
    "powerScore",
    "sourceHint",
    "tags",
    "tier",
})

RECIPE_META_DELIVERY_FIELDS = frozenset({
    "assetBaseUrl",
    "assetFiles",
    "assetTransport",
    "chaosBudget",
    "generationDepth",
    "noveltyBudget",
    "parentCategories",
    "parentGeneratedDepths",
    "parentIdentities",
    "recipeCoherence",
    "sampledCategory",
    "sampledLane",
    "universalRecipe",
    "worldId",
    "worldScoped",
})

VFX_QUALITY_BUDGET_DELIVERY_FIELDS = frozenset({
    "effectMagnitude",
    "emergencyCap",
    "enablePersistentSmoke",
    "enablePointSparks",
    "enableSoftGlow",
    "maxDrawCalls",
    "maxParticlesPerTick",
    "maxParticlesTotal",
    "spawnRateMultiplier",
    "visualBudgetClass",
})

VFX_DEBUG_DELIVERY_FIELDS = frozenset({
    "pattern",
    "roles",
    "selectedReasons",
    "selectedScore",
    "topCandidates",
    "wordProbe",
})



_STORAGE_LOCKS_GUARD = threading.Lock()
_STORAGE_LOCKS: dict[str, threading.RLock] = {}


def _storage_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _STORAGE_LOCKS_GUARD:
        return _STORAGE_LOCKS.setdefault(key, threading.RLock())


def _fsync_parent_directory(path: Path) -> None:
    """Best-effort durability for an atomic rename without affecting Windows support."""
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



# AGENT MAP: world-scoped recipe storage.
# Generated recipes/items are keyed by recipe/world context. Preserve world scoping
# and avoid cache paths that let generated parents leak between Terraria worlds.
def safe_file_part(text: Any, default: str = "value", max_len: int = 80) -> str:
    """Return a filesystem-safe, still-readable path fragment."""
    raw = str(text or "").strip()
    raw = re.sub(r"[^A-Za-z0-9._-]+", "_", raw)
    raw = raw.strip("._-")
    return (raw[:max_len] or default)


def world_recipe_dir(world_recipes_dir: Path, world_id: Any) -> Path:
    return Path(world_recipes_dir) / f"world_{safe_file_part(world_id, 'unknown_world')}"


def world_recipe_file(world_recipes_dir: Path, world_id: Any, recipe_key_value: str) -> Path:
    return world_recipe_dir(world_recipes_dir, world_id) / "recipes" / f"{safe_file_part(recipe_key_value, 'recipe')}.json"


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically replace one JSON file after flushing a unique sibling temp."""
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


def _maybe_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = strict_json.loads(text)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
    return []


def _role_slot_from_visual_report(report: dict[str, Any], role: str) -> dict[str, Any]:
    for slot in report.get("slots") or []:
        if isinstance(slot, dict) and str(slot.get("role") or "") == role:
            return dict(slot)
    return {}


def build_recipe_health(
    data: dict[str, Any],
    *,
    app_version: str,
    contract_versions: dict[str, Any] | None = None,
    visual_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact, stable health summary for one generated recipe.

    Health is deliberately diagnostic: it never repairs, rejects, or reauthors a
    recipe.  It answers the recurring debug question: did gameplay, assets, VFX,
    and contract stamps reach the committed recipe?
    """
    debug_candidate = data.get("debug")
    debug: dict[str, Any] = debug_candidate if isinstance(debug_candidate, dict) else {}
    attack_candidate = data.get("attack")
    attack: dict[str, Any] = attack_candidate if isinstance(attack_candidate, dict) else {}
    gameplay_candidate = data.get("gameplay")
    gameplay: dict[str, Any] = gameplay_candidate if isinstance(gameplay_candidate, dict) else {}
    recipe_meta_candidate = data.get("recipeMeta")
    recipe_meta: dict[str, Any] = recipe_meta_candidate if isinstance(recipe_meta_candidate, dict) else {}
    affordance_candidate = data.get("runtimeAffordance")
    affordance: dict[str, Any] = affordance_candidate if isinstance(affordance_candidate, dict) else {}
    if not affordance:
        affordance = _maybe_json_obj(debug.get("runtimeAffordance"))

    visual_report = visual_report or _maybe_json_obj(debug.get("visualDeliveryReport"))
    runtime_validation = _maybe_json_obj(debug.get("runtimePlanValidation"))
    runtime_quality = _maybe_json_obj(debug.get("runtimePlanQuality"))
    runtime_provenance = _maybe_json_obj(debug.get("runtimePlanProvenance"))
    if not runtime_provenance:
        runtime_provenance = _maybe_json_obj(debug.get("runtimeAuthoringProvenance"))
    gameplay_children = runtime_provenance.get("gameplayChildren") if isinstance(runtime_provenance.get("gameplayChildren"), dict) else {}
    pure_vfx = runtime_provenance.get("pureVfx") if isinstance(runtime_provenance.get("pureVfx"), dict) else {}

    slots: dict[str, Any] = {}
    for role in ["item", "projectile", "impact", "child", "field", "equip_overlay"]:
        slot = _role_slot_from_visual_report(visual_report, role)
        slots[role] = {
            "required": bool(slot.get("required")),
            "status": str(slot.get("status") or ""),
            "exists": bool(slot.get("exists")),
            "usable": bool(slot.get("usable")),
            "assetMode": str(slot.get("assetMode") or ""),
        }
        if slot.get("score") is not None:
            slots[role]["score"] = slot.get("score")

    asset_files = recipe_meta.get("assetFiles")
    if not isinstance(asset_files, list):
        asset_files = _maybe_json_list(debug.get("assetFiles"))

    runtime_valid = True
    if runtime_validation:
        runtime_valid = bool(runtime_validation.get("ok", True))
    elif data.get("runtimePlan"):
        runtime_plan_raw = data.get("runtimePlan")
        runtime_plan: dict[str, Any] = runtime_plan_raw if isinstance(runtime_plan_raw, dict) else {}
        gameplay_raw = data.get("gameplay")
        gameplay: dict[str, Any] = gameplay_raw if isinstance(gameplay_raw, dict) else {}
        attack_raw = data.get("attack")
        attack: dict[str, Any] = attack_raw if isinstance(attack_raw, dict) else {}
        result_kind = str(runtime_plan.get("resultKind") or gameplay.get("kind") or data.get("category") or "").strip().lower()
        root_required = result_kind in {"weapon", "consumable_weapon", "summon"} or bool(attack.get("enabled"))
        runtime_valid = bool(
            runtime_quality.get("hasStats", True)
            and (not root_required or runtime_quality.get("hasRootExecutor", False))
        ) if runtime_quality else True

    deliverable = is_deliverable_recipe_payload(data)
    visual_ok = bool(visual_report.get("ok", True))
    required_assets_ok = all(bool(slot.get("usable")) for slot in slots.values() if slot.get("required"))
    warnings: list[str] = []
    visual_director_status = str(debug.get("visualDirectorStatus") or "")
    if visual_director_status == "visual_director_degraded":
        warnings.append("visual_director_degraded")
    if attack.get("enabled") and slots.get("projectile", {}).get("assetMode") == "baked_sprite" and not slots.get("projectile", {}).get("usable"):
        warnings.append("projectile_baked_sprite_missing_or_unusable")
    if attack.get("impactSpriteStatus") and not slots.get("impact", {}).get("usable") and slots.get("impact", {}).get("status") not in {"", "skipped_not_authored_baked", "skipped_disabled_by_settings"}:
        warnings.append("impact_sprite_unusable")

    problems: list[str] = []
    if not deliverable:
        problems.append("recipe_payload_not_deliverable")
    if not runtime_valid:
        problems.append("runtime_plan_invalid")
    if not visual_ok or not required_assets_ok:
        problems.append("required_visual_delivery_failed")

    if problems:
        status = "blocked"
    elif warnings or (visual_report.get("warnings") if isinstance(visual_report, dict) else None):
        status = "warning"
    else:
        status = "healthy"

    return {
        "schema": "infini.recipe-health.v1",
        "ok": not problems,
        "status": status,
        "appVersion": str(app_version),
        "contractVersions": contract_versions or data.get("contractVersions") or {},
        "recipeKey": str(recipe_meta.get("recipeKey") or data.get("recipeKey") or ""),
        "resultId": str(data.get("id") or ""),
        "resultName": str(data.get("name") or ""),
        "parents": {
            "a": str(recipe_meta.get("parentA") or data.get("parentA") or ""),
            "b": str(recipe_meta.get("parentB") or data.get("parentB") or ""),
        },
        "runtime": {
            "valid": runtime_valid,
            "resultKind": str((data.get("runtimePlan") or {}).get("resultKind") or gameplay.get("runtimeOutputKind") or gameplay.get("kind") or ""),
            "attackEnabled": bool(attack.get("enabled")),
            "runtimeExecutorEnabled": bool(attack.get("runtimeExecutorEnabled", attack.get("enabled", False))),
            "damagePath": str(attack.get("damagePath") or ""),
            "delivery": str(attack.get("delivery") or ""),
            "runtimeFamily": str(attack.get("runtimeFamily") or ""),
            "hasRealChildren": bool(gameplay_children.get("enabled")),
            "pureVfx": bool(pure_vfx.get("enabled")),
        },
        "runtimeAffordance": {
            "heldVisibility": str(affordance.get("heldVisibility") or ""),
            "releaseTiming": str(affordance.get("releaseTiming") or ""),
            "handPose": str(affordance.get("handPose") or ""),
            "initialOffsetPx": int(affordance.get("initialOffsetPx") or 0) if str(affordance.get("initialOffsetPx") or "").lstrip("-").isdigit() else 0,
        },
        "visual": {
            "ok": visual_ok,
            "directorStatus": visual_director_status,
            "slots": slots,
            "assetFileCount": len(asset_files or []),
            "assetSync": recipe_meta.get("assetSync") if isinstance(recipe_meta.get("assetSync"), dict) else {},
        },
        "vfx": {
            "slotCount": len((data.get("vfxManifest") or {}).get("slots") or []) if isinstance(data.get("vfxManifest"), dict) else 0,
            "playbackMode": str((data.get("vfxManifest") or {}).get("playbackMode") or "") if isinstance(data.get("vfxManifest"), dict) else "",
        },
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
        data.setdefault("recipeMeta", {})["contractVersions"] = contract_versions
    data["recipeHealth"] = build_recipe_health(
        data,
        app_version=app_version,
        contract_versions=contract_versions,
        visual_report=visual_report,
    )
    return data


def write_world_manifest(world_recipes_dir: Path, app_version: str, world_id: Any, world_name: Any = None) -> None:
    """Create/update small world metadata only when stable metadata actually changes."""
    root = world_recipe_dir(world_recipes_dir, world_id)
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "manifest.json"
    with _storage_lock(manifest_path):
        old = read_json_file(manifest_path) or {}
        stable = {
            "schema": "infini-world-recipes-v2",
            "worldId": str(world_id),
            "worldName": str(world_name or old.get("worldName") or ""),
            "worldScoped": True,
            "recipesDir": "recipes",
            "recipeAuthority": "recipe_files",
            "derivedViews": "scan_on_demand",
            "appVersion": str(app_version),
        }
        if old and all(old.get(key) == value for key, value in stable.items()):
            return
        now = time.time()
        payload = {
            **stable,
            "createdAt": old.get("createdAt", now),
            "updatedAt": now,
        }
        atomic_write_json(manifest_path, payload)


def strip_runtime_only_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Remove fields that are only needed inside one in-memory generation pass."""
    if not isinstance(data, dict):
        return data
    out = dict(data)
    out.pop("_llmHistory", None)
    out.pop("_runtimePlanCompileCache", None)
    return out


def delivery_safe_debug(debug: Any) -> dict[str, str]:
    """Return a string-only debug bag for cache/client delivery."""
    if not isinstance(debug, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in debug.items():
        key = str(k)[:96]
        try:
            if v is None:
                text = ""
            elif isinstance(v, (str, int, float, bool)):
                text = str(v)
            else:
                text = bounded_json_dumps(v, max_chars=2000)
        except Exception:
            text = repr(v)
        out[key] = text[:2000]
    return out


def _project_delivery_fields(value: Any, allowed: frozenset[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {key: item for key, item in value.items() if key in allowed}


def sanitize_recipe_for_delivery(data: Any) -> Any:
    """Make a recipe payload safe to send to Terraria clients without changing runtime semantics."""
    if not isinstance(data, dict):
        return data
    out = strip_runtime_only_fields(data)
    for internal_field in ("runtimePlan", "runtimeContract", "runtimeCompiled", "runtimeAffordance", "runtimeArchetype", "debug"):
        out.pop(internal_field, None)
    attack = out.get("attack") if isinstance(out.get("attack"), dict) else None
    gameplay = out.get("gameplay") if isinstance(out.get("gameplay"), dict) else None
    visual = out.get("visual") if isinstance(out.get("visual"), dict) else None
    if attack is not None:
        out["attack"] = {k: v for k, v in attack.items() if k not in ATTACK_NON_WIRE_FIELDS}
    if gameplay is not None:
        clean_gameplay = {k: v for k, v in gameplay.items() if k not in GAMEPLAY_DEBUG_ONLY_FIELDS}
        rejected = clean_gameplay.get("rejectedEngineCalls")
        if isinstance(rejected, list):
            clean_gameplay["rejectedEngineCalls"] = [
                {k: v for k, v in row.items() if k not in REJECTED_ENGINE_CALL_DEBUG_ONLY_FIELDS}
                if isinstance(row, dict) else row
                for row in rejected
            ]
        out["gameplay"] = clean_gameplay
    if visual is not None:
        out["visual"] = {k: v for k, v in visual.items() if k in VISUAL_DELIVERY_FIELDS}

    summary = _project_delivery_fields(out.get("generatedParentSummary"), GENERATED_PARENT_SUMMARY_DELIVERY_FIELDS)
    if summary is not None:
        out["generatedParentSummary"] = summary

    recipe_meta = _project_delivery_fields(out.get("recipeMeta"), RECIPE_META_DELIVERY_FIELDS)
    if recipe_meta is not None:
        out["recipeMeta"] = recipe_meta

    item_knowledge = out.get("itemKnowledge")
    if isinstance(item_knowledge, dict):
        clean_knowledge = dict(item_knowledge)
        parents = clean_knowledge.get("parents")
        if isinstance(parents, list):
            clean_knowledge["parents"] = [
                _project_delivery_fields(parent, PARENT_ITEM_CARD_DELIVERY_FIELDS)
                if isinstance(parent, dict) else parent
                for parent in parents
            ]
        result_card = _project_delivery_fields(clean_knowledge.get("resultCard"), PARENT_ITEM_CARD_DELIVERY_FIELDS)
        if result_card is not None:
            clean_knowledge["resultCard"] = result_card
        out["itemKnowledge"] = clean_knowledge

    vfx_manifest = out.get("vfxManifest")
    if isinstance(vfx_manifest, dict):
        clean_vfx_manifest = dict(vfx_manifest)
        budget = _project_delivery_fields(clean_vfx_manifest.get("budget"), VFX_QUALITY_BUDGET_DELIVERY_FIELDS)
        if budget is not None:
            clean_vfx_manifest["budget"] = budget
        vfx_debug = _project_delivery_fields(clean_vfx_manifest.get("debug"), VFX_DEBUG_DELIVERY_FIELDS)
        if vfx_debug is not None:
            clean_vfx_manifest["debug"] = vfx_debug
        out["vfxManifest"] = clean_vfx_manifest

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
    """Commit one authoritative recipe file; no aggregate index is rewritten."""
    write_world_manifest(world_recipes_dir, app_version, world_id, world_name)
    payload = sanitize_recipe_for_delivery(data)
    payload.setdefault("recipeMeta", {})
    payload["recipeMeta"].update({
        "worldScoped": True,
        "worldId": str(world_id),
        "worldName": str(world_name or payload.get("recipeMeta", {}).get("worldName", "")),
        "recipeKey": recipe_key_value,
        "storage": "world_recipe_file_authority",
        "parentA": parent_a_name or payload.get("recipeMeta", {}).get("parentA", ""),
        "parentB": parent_b_name or payload.get("recipeMeta", {}).get("parentB", ""),
    })
    if not isinstance(payload.get("recipeHealth"), dict):
        attach_recipe_health(
            payload,
            app_version=app_version,
            contract_versions=payload.get("contractVersions") if isinstance(payload.get("contractVersions"), dict) else None,
        )
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
    if str(data.get("id") or "").strip().lower() == "placeholder":
        return False
    source_mode = str(data.get("sourceMode") or "").strip().lower()
    if source_mode in {"fallback", "failed", "placeholder"} or source_mode.startswith("fallback_"):
        return False
    return True
