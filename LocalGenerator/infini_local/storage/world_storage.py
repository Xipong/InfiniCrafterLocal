from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from infini_local.core.boundary_models import (
    ATTACK_DEBUG_ONLY_FIELDS,
    GAMEPLAY_DEBUG_ONLY_FIELDS,
    REJECTED_ENGINE_CALL_DEBUG_ONLY_FIELDS,
)



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
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None



def _maybe_json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
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
                parsed = json.loads(text)
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
    debug = data.get("debug") if isinstance(data.get("debug"), dict) else {}
    attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
    gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
    recipe_meta = data.get("recipeMeta") if isinstance(data.get("recipeMeta"), dict) else {}
    affordance = data.get("runtimeAffordance") if isinstance(data.get("runtimeAffordance"), dict) else {}
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
    for role in ["item", "projectile", "impact", "child", "field"]:
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
        runtime_valid = bool(runtime_quality.get("hasStats", True) and runtime_quality.get("hasPrimaryAction", True)) if runtime_quality else True

    deliverable = is_deliverable_recipe_payload(data)
    visual_ok = bool(visual_report.get("ok", True))
    required_assets_ok = all(bool(slot.get("usable")) for slot in slots.values() if slot.get("required"))
    warnings: list[str] = []
    if attack.get("enabled") and slots.get("projectile", {}).get("assetMode") == "baked_sprite" and not slots.get("projectile", {}).get("usable"):
        warnings.append("projectile_baked_sprite_missing_or_unusable")
    if attack.get("impactSpriteStatus") and not slots.get("impact", {}).get("usable") and slots.get("impact", {}).get("status") not in {"", "skipped_not_authored_baked", "skipped_disabled_by_settings"}:
        warnings.append("impact_sprite_unusable")
    if str(data.get("concept", {}).get("weirdTwist", "") if isinstance(data.get("concept"), dict) else "").lower().find("shrapnel") >= 0 and not gameplay_children.get("enabled"):
        warnings.append("shrapnel_wording_without_gameplay_children")
    promise_truth = _maybe_json_obj(debug.get("runtimePromiseTruth"))
    if promise_truth:
        for warning in promise_truth.get("warnings") or []:
            if warning:
                warnings.append(str(warning)[:120])
        unsupported_promises = list(data.get("unsupportedPromises") or []) if isinstance(data.get("unsupportedPromises"), list) else []
        unsupported_promises += list(promise_truth.get("unsupportedPromises") or []) if isinstance(promise_truth.get("unsupportedPromises"), list) else []
        if unsupported_promises:
            warnings.append("runtime_unsupported_promises_present")

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
            "useFantasy": str(affordance.get("useFantasy") or ""),
            "heldVisibility": str(affordance.get("heldVisibility") or ""),
            "releaseTiming": str(affordance.get("releaseTiming") or ""),
            "handPose": str(affordance.get("handPose") or ""),
            "spawnStyle": str(affordance.get("spawnStyle") or ""),
            "rotationMode": str(affordance.get("rotationMode") or ""),
            "trailMode": str(affordance.get("trailMode") or ""),
            "drawDuringUse": bool(affordance.get("drawDuringUse", False)),
            "initialOffsetPx": int(affordance.get("initialOffsetPx") or 0) if str(affordance.get("initialOffsetPx") or "").lstrip("-").isdigit() else 0,
        },
        "visual": {
            "ok": visual_ok,
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
        data.setdefault("debug", {})["contractVersions"] = contract_versions
    data["recipeHealth"] = build_recipe_health(
        data,
        app_version=app_version,
        contract_versions=contract_versions,
        visual_report=visual_report,
    )
    data.setdefault("debug", {})["recipeHealthStatus"] = data["recipeHealth"].get("status", "")
    return data


def _compact_health_for_index(health: dict[str, Any]) -> dict[str, Any]:
    runtime = health.get("runtime") if isinstance(health.get("runtime"), dict) else {}
    visual = health.get("visual") if isinstance(health.get("visual"), dict) else {}
    slots = visual.get("slots") if isinstance(visual.get("slots"), dict) else {}
    return {
        "schema": health.get("schema", "infini.recipe-health.v1"),
        "ok": bool(health.get("ok")),
        "status": str(health.get("status") or "unknown"),
        "resultId": str(health.get("resultId") or ""),
        "resultName": str(health.get("resultName") or ""),
        "runtime": {
            "resultKind": str(runtime.get("resultKind") or ""),
            "delivery": str(runtime.get("delivery") or ""),
            "runtimeFamily": str(runtime.get("runtimeFamily") or ""),
            "damagePath": str(runtime.get("damagePath") or ""),
            "hasRealChildren": bool(runtime.get("hasRealChildren")),
            "pureVfx": bool(runtime.get("pureVfx")),
        },
        "runtimeAffordance": {
            k: v for k, v in (health.get("runtimeAffordance") if isinstance(health.get("runtimeAffordance"), dict) else {}).items()
            if k in {"useFantasy", "heldVisibility", "releaseTiming", "handPose", "spawnStyle", "rotationMode", "trailMode", "drawDuringUse", "initialOffsetPx"} and v not in (None, "")
        },
        "visual": {
            role: {
                "required": bool((slot or {}).get("required")),
                "usable": bool((slot or {}).get("usable")),
                "status": str((slot or {}).get("status") or ""),
                "assetMode": str((slot or {}).get("assetMode") or ""),
            }
            for role, slot in slots.items()
            if role in {"item", "projectile", "impact", "child", "field"}
        },
        "warnings": list(health.get("warnings") or [])[:8],
        "problems": list(health.get("problems") or [])[:8],
        "updatedAt": health.get("updatedAt", time.time()),
    }


def update_world_health_index(
    world_recipes_dir: Path,
    *,
    world_id: Any,
    world_name: Any = None,
    recipe_key_value: str,
    health: dict[str, Any],
    app_version: str,
) -> None:
    root = world_recipe_dir(world_recipes_dir, world_id)
    path = root / "health.json"
    index = read_json_file(path) or {
        "schema": "infini-world-recipe-health-index-v1",
        "worldId": str(world_id),
        "worldName": str(world_name or ""),
        "recipes": {},
    }
    index["schema"] = "infini-world-recipe-health-index-v1"
    index["worldId"] = str(world_id)
    if world_name:
        index["worldName"] = str(world_name)
    index["appVersion"] = str(app_version)
    recipes = index.setdefault("recipes", {})
    recipes[recipe_key_value] = _compact_health_for_index(health)
    counts: dict[str, int] = {}
    for row in recipes.values():
        if isinstance(row, dict):
            status = str(row.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
    index["counts"] = counts
    index["updatedAt"] = time.time()
    atomic_write_json(path, index)


def write_world_manifest(world_recipes_dir: Path, app_version: str, world_id: Any, world_name: Any = None) -> None:
    root = world_recipe_dir(world_recipes_dir, world_id)
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "manifest.json"
    old = read_json_file(manifest_path) or {}
    payload = {
        "schema": "infini-world-recipes-v1",
        "worldId": str(world_id),
        "worldName": str(world_name or old.get("worldName") or ""),
        "worldScoped": True,
        "recipesDir": "recipes",
        "updatedAt": time.time(),
        "createdAt": old.get("createdAt", time.time()),
        "appVersion": str(app_version),
    }
    atomic_write_json(manifest_path, payload)


def update_world_recipe_index(
    world_recipes_dir: Path,
    recipe_key_value: str,
    data: dict[str, Any],
    *,
    world_id: Any,
    parent_a_name: str = "",
    parent_b_name: str = "",
    world_name: Any = None,
) -> None:
    root = world_recipe_dir(world_recipes_dir, world_id)
    index_path = root / "index.json"
    index = read_json_file(index_path) or {
        "schema": "infini-world-recipe-index-v1",
        "worldId": str(world_id),
        "worldName": str(world_name or ""),
        "recipes": {},
    }
    index["schema"] = "infini-world-recipe-index-v1"
    index["worldId"] = str(world_id)
    if world_name:
        index["worldName"] = str(world_name)
    recipe_entry = {
        "file": f"recipes/{safe_file_part(recipe_key_value, 'recipe')}.json",
        "updatedAt": time.time(),
        "resultId": data.get("id", ""),
        "resultName": data.get("name", ""),
        "parentA": parent_a_name or data.get("recipeMeta", {}).get("parentA", ""),
        "parentB": parent_b_name or data.get("recipeMeta", {}).get("parentB", ""),
    }
    health = data.get("recipeHealth") if isinstance(data.get("recipeHealth"), dict) else {}
    if health:
        recipe_entry["health"] = _compact_health_for_index(health)
    index.setdefault("recipes", {})[recipe_key_value] = recipe_entry
    index["updatedAt"] = time.time()
    atomic_write_json(index_path, index)


def strip_runtime_only_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Remove fields that are only needed inside one in-memory generation pass."""
    if not isinstance(data, dict):
        return data
    out = dict(data)
    out.pop("_llmContinuation", None)
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
                text = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            text = repr(v)
        out[key] = text[:2000]
    return out


def sanitize_recipe_for_delivery(data: Any) -> Any:
    """Make a recipe payload safe to send to Terraria clients without changing runtime semantics."""
    if not isinstance(data, dict):
        return data
    out = strip_runtime_only_fields(data)
    attack = out.get("attack") if isinstance(out.get("attack"), dict) else None
    gameplay = out.get("gameplay") if isinstance(out.get("gameplay"), dict) else None
    if attack is not None:
        out["attack"] = {k: v for k, v in attack.items() if k not in ATTACK_DEBUG_ONLY_FIELDS}
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
    out["debug"] = delivery_safe_debug(out.get("debug"))
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
    payload.setdefault("recipeMeta", {})
    payload["recipeMeta"].update({
        "worldScoped": True,
        "worldId": str(world_id),
        "worldName": str(world_name or payload.get("recipeMeta", {}).get("worldName", "")),
        "recipeKey": recipe_key_value,
        "storage": "world_recipes_file",
        "parentA": parent_a_name or payload.get("recipeMeta", {}).get("parentA", ""),
        "parentB": parent_b_name or payload.get("recipeMeta", {}).get("parentB", ""),
    })
    if not isinstance(payload.get("recipeHealth"), dict):
        attach_recipe_health(payload, app_version=app_version, contract_versions=payload.get("contractVersions") if isinstance(payload.get("contractVersions"), dict) else None)
    atomic_write_json(world_recipe_file(world_recipes_dir, world_id, recipe_key_value), payload)
    update_world_recipe_index(
        world_recipes_dir,
        recipe_key_value,
        payload,
        world_id=world_id,
        parent_a_name=parent_a_name,
        parent_b_name=parent_b_name,
        world_name=world_name,
    )
    if isinstance(payload.get("recipeHealth"), dict):
        update_world_health_index(
            world_recipes_dir,
            world_id=world_id,
            world_name=world_name,
            recipe_key_value=recipe_key_value,
            health=payload["recipeHealth"],
            app_version=app_version,
        )


def read_world_recipe_cache(
    world_recipes_dir: Path,
    app_version: str,
    recipe_identity_version: str,
    recipe_key_value: str,
    world_id: Any,
    world_name: Any = None,
) -> dict[str, Any] | None:
    data = read_json_file(world_recipe_file(world_recipes_dir, world_id, recipe_key_value))
    if not data:
        return None
    data.pop("_llmContinuation", None)
    write_world_manifest(world_recipes_dir, app_version, world_id, world_name)
    data.setdefault("debug", {})["cacheHit"] = "world_file"
    data.setdefault("debug", {})["cacheScope"] = "world"
    data.setdefault("debug", {}).setdefault("recipeIdentityVersion", recipe_identity_version)
    data.setdefault("recipeMeta", {})["worldScoped"] = True
    data.setdefault("recipeMeta", {})["worldId"] = str(world_id)
    data.setdefault("recipeMeta", {})["storage"] = "world_recipes_file"
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
