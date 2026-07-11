from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from infini_local.core.config_bootstrap import (
    APP_VERSION,
    SPRITE_DIR,
    WORLD_RECIPES_DIR,
)
from infini_local.pipelines.pipeline_visual_config import VISUAL_PIPELINE_PROFILE
from infini_local.services import asset_sync_service
from infini_local.pipelines.projectile_affordance import infer_projectile_visual_family
from infini_local.pipelines.visual_prompt_contracts import (
    effective_projectile_canvas,
    family_prompt_clause,
    sprite_contract_for,
)


# AGENT MAP: visual asset manifest/file-descriptor serialization only.
# Do not add generation, validation, or gameplay decisions here.


def _asset_sha256(path: Path) -> str:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""

def _asset_descriptor(value: Any, required: bool = False) -> dict[str, Any] | None:
    name = asset_sync_service.asset_filename_from_path(value)
    if not name:
        return None
    found = asset_sync_service.find_asset_file(name, sprite_dir=SPRITE_DIR, world_recipes_dir=WORLD_RECIPES_DIR)
    out = {"file": name, "required": bool(required), "exists": bool(found)}
    if found is not None:
        try:
            out["bytes"] = int(found.stat().st_size)
        except Exception:
            pass
        sha = _asset_sha256(found)
        if sha:
            out["sha256"] = sha
        out["contentType"] = asset_sync_service.asset_content_type(found)
    return out

def sprite_contract_for_asset(data: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    role = str(asset.get("role") or "item")
    out = sprite_contract_for(role, int(asset.get("canvas") or 32))
    if role == "projectile":
        fam = infer_projectile_visual_family(data)
        out["projectileVisualFamily"] = fam
        out["promptPoseWords"] = family_prompt_clause(data, "projectile", int(asset.get("canvas") or 32))
    return out

def _compact_text(value: Any, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text[:limit]

def _parent_manifest_summary(parent: Any) -> dict[str, Any]:
    if not isinstance(parent, dict):
        return {}
    fp = parent.get("fingerprint") if isinstance(parent.get("fingerprint"), dict) else {}
    gd = parent.get("generatedData") if isinstance(parent.get("generatedData"), dict) else {}
    return {
        "name": parent.get("name") or fp.get("name"),
        "sourceMod": parent.get("sourceMod") or fp.get("sourceMod") or "Terraria",
        "internalName": parent.get("internalName") or fp.get("internalName"),
        "type": parent.get("type") or parent.get("id") or fp.get("type"),
        "damage": parent.get("damage") if parent.get("damage") is not None else fp.get("damage"),
        "damageClass": parent.get("damageClass") or fp.get("damageClass"),
        "useStyle": parent.get("useStyle") if parent.get("useStyle") is not None else fp.get("useStyle"),
        "useTime": parent.get("useTime") if parent.get("useTime") is not None else fp.get("useTime"),
        "generated": bool(gd),
        "generatedId": gd.get("id") if gd else None,
    }

def _asset_manifest_entry(data: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    role = str(asset.get("role") or "asset")
    path_value = asset.get("path") or asset.get("file")
    desc = _asset_descriptor(path_value, bool(asset.get("required"))) or {"required": bool(asset.get("required")), "exists": False}
    out = {
        "role": role,
        "assetId": asset.get("assetId"),
        "canvas": int(asset.get("canvas") or 32),
        "required": bool(asset.get("required")),
        "status": asset.get("status"),
        "assetMode": asset.get("assetMode"),
        "assetDecisionBy": asset.get("assetDecisionBy"),
        "skipReason": asset.get("skipReason"),
        "handledBy": asset.get("handledBy") or "visual_asset_pipeline",
        "authoringPolicy": asset.get("authoringPolicy") or "ai_primary_non_procedural",
        "prompt": _compact_text(asset.get("prompt"), 520),
        "file": desc.get("file"),
        "exists": bool(desc.get("exists")),
        "bytes": desc.get("bytes"),
        "sha256": desc.get("sha256"),
        "contentType": desc.get("contentType"),
        "contract": sprite_contract_for_asset(data, asset),
    }
    return {k: v for k, v in out.items() if v not in (None, "", [])}

def write_visual_manifest(data: dict[str, Any], plan: list[dict[str, Any]]) -> None:
    try:
        mid = str(data.get("id") or "sprite")
        path = SPRITE_DIR / f"{mid}_asset_manifest.json"
        visual = data.get("visual") if isinstance(data.get("visual"), dict) else {}
        gameplay = data.get("gameplay") if isinstance(data.get("gameplay"), dict) else {}
        attack = data.get("attack") if isinstance(data.get("attack"), dict) else {}
        clean_assets = [_asset_manifest_entry(data, asset) for asset in plan if isinstance(asset, dict)]
        vanilla_hitbox_damage = (
            int(float(gameplay.get("damage") or 0)) > 0
            and int(float(gameplay.get("useStyle") or 0)) > 0
            and str(gameplay.get("kind") or data.get("category") or "").strip().lower() not in {"ammo", "accessory", "material", "furniture"}
            and not (bool(attack.get("enabled")) and bool(attack.get("disableItemMeleeHitbox")))
        )
        manifest = {
            "schema": "infini.visual.assets.v2",
            "version": APP_VERSION,
            "pipelineProfile": VISUAL_PIPELINE_PROFILE,
            "recipe": {
                "id": data.get("id"),
                "recipeKey": data.get("recipeKey"),
                "name": data.get("name"),
                "category": data.get("category"),
                "tags": data.get("tags") if isinstance(data.get("tags"), list) else [],
            },
            "gameplay": {
                "kind": gameplay.get("kind"),
                "damageClass": gameplay.get("damageClass"),
                "damage": gameplay.get("damage"),
                "useStyle": gameplay.get("useStyle"),
                "useTime": gameplay.get("useTime"),
                "preferredCanvasSize": visual.get("preferredCanvasSize"),
            },
            "attack": {
                # Shared field. Semantics: generated runtime executor, not
                # "can this item deal vanilla Terraria contact damage".
                "enabled": bool(attack.get("enabled")),
                "runtimeExecutorEnabled": bool(attack.get("enabled")),
                "customAttackEnabled": bool(attack.get("enabled")),
                "vanillaItemHitboxDamage": bool(vanilla_hitbox_damage),
                "damagePath": (
                    "generated_executor_plus_vanilla_hitbox" if bool(attack.get("enabled")) and vanilla_hitbox_damage
                    else "generated_runtime_executor" if bool(attack.get("enabled"))
                    else "vanilla_item_hitbox" if vanilla_hitbox_damage
                    else "utility_or_non_damaging"
                ),
                "pattern": attack.get("pattern") or attack.get("attackPattern"),
                "runtimeFamily": attack.get("runtimeFamily"),
                "weaponFamily": attack.get("weaponFamily"),
                "projectileWidth": attack.get("projectileWidth"),
                "projectileHeight": attack.get("projectileHeight"),
                "projectileScale": attack.get("projectileScale"),
                "effectiveProjectileCanvas": effective_projectile_canvas(data) if attack.get("enabled") else None,
            },
            "parents": [_parent_manifest_summary(data.get("parentA")), _parent_manifest_summary(data.get("parentB"))],
            "visualIntent": {
                "palette": visual.get("palette"),
                "requiredAnchors": visual.get("requiredAnchors"),
                "itemSilhouetteContract": visual.get("itemSilhouetteContract") or visual.get("silhouetteContract") or visual.get("shapeContract"),
                "styleGuide": _compact_text(visual.get("styleGuide"), 520),
                "imagePrompt": _compact_text(visual.get("imagePrompt"), 520),
                "projectileImagePrompt": _compact_text(visual.get("projectileImagePrompt") or attack.get("projectileSpritePrompt"), 520),
            },
            "projectileVisualFamily": infer_projectile_visual_family(data),
            "authoringPolicy": "ai_primary_non_procedural",
            "assets": clean_assets,
        }
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        data.setdefault("visual", {})["assetManifestPath"] = str(path.resolve())
        data.setdefault("debug", {})["visualAssetManifest"] = str(path.resolve())
    except Exception as e:
        data.setdefault("debug", {})["visualManifestError"] = repr(e)


__all__ = [
    "_asset_sha256",
    "_asset_descriptor",
    "sprite_contract_for_asset",
    "_compact_text",
    "_parent_manifest_summary",
    "_asset_manifest_entry",
    "write_visual_manifest",
]
