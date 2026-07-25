from __future__ import annotations

"""Manifest serialization for exact runtime-entity sprite assets."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from infini_local.core.config_bootstrap import APP_VERSION, SPRITE_DIR, WORLD_RECIPES_DIR
from infini_local.pipelines.pipeline_visual_config import VISUAL_PIPELINE_PROFILE
from infini_local.pipelines.visual_prompt_contracts import sprite_contract_for
from infini_local.services import asset_sync_service


def _asset_sha256(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except Exception:
        return ""


def _asset_descriptor(value: Any, required: bool = False) -> dict[str, Any] | None:
    name = asset_sync_service.asset_filename_from_path(value)
    if not name:
        return None
    found = asset_sync_service.find_asset_file(name, sprite_dir=SPRITE_DIR, world_recipes_dir=WORLD_RECIPES_DIR)
    out: dict[str, Any] = {"file": name, "required": bool(required), "exists": bool(found)}
    if found is not None:
        out["bytes"] = int(found.stat().st_size)
        out["contentType"] = asset_sync_service.asset_content_type(found)
        sha = _asset_sha256(found)
        if sha:
            out["sha256"] = sha
    return out


def sprite_contract_for_asset(data: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    del data
    return sprite_contract_for(str(asset.get("role") or "asset"), int(asset.get("canvas") or 32))


def _compact_text(value: Any, limit: int = 360) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def _parent_manifest_summary(parent: Any) -> dict[str, Any]:
    if not isinstance(parent, dict):
        return {}
    fingerprint = parent.get("fingerprint") if isinstance(parent.get("fingerprint"), dict) else {}
    return {
        "name": parent.get("name") or fingerprint.get("name"),
        "sourceMod": parent.get("sourceMod") or fingerprint.get("sourceMod") or "Terraria",
        "internalName": parent.get("internalName") or fingerprint.get("internalName"),
        "type": parent.get("type") or parent.get("id") or fingerprint.get("type"),
    }


def _asset_manifest_entry(data: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    role = str(asset.get("role") or "asset")
    desc = _asset_descriptor(asset.get("path") or asset.get("file"), bool(asset.get("required"))) or {"required": bool(asset.get("required")), "exists": False}
    out = {
        "role": role,
        "entityId": asset.get("entityId"),
        "entityKind": asset.get("entityKind"),
        "visualRole": asset.get("visualRole"),
        "assetId": asset.get("assetId"),
        "canvas": int(asset.get("canvas") or 32),
        "required": bool(asset.get("required")),
        "status": asset.get("status"),
        "assetMode": asset.get("assetMode"),
        "runtimeGateReason": asset.get("runtimeGateReason"),
        "prompt": _compact_text(asset.get("prompt"), 520),
        "file": desc.get("file"), "exists": bool(desc.get("exists")), "bytes": desc.get("bytes"),
        "sha256": desc.get("sha256"), "contentType": desc.get("contentType"),
        "contract": sprite_contract_for_asset(data, asset),
    }
    return {key: value for key, value in out.items() if value not in (None, "", [])}


def write_visual_manifest(data: dict[str, Any], plan: list[dict[str, Any]]) -> None:
    try:
        item_id = str(data.get("id") or "sprite")
        path = SPRITE_DIR / f"{item_id}_asset_manifest.json"
        runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), dict) else {}
        manifest = {
            "schema": "infini.visual.runtime-entity-assets.v3",
            "version": APP_VERSION,
            "pipelineProfile": VISUAL_PIPELINE_PROFILE,
            "recipe": {"id": data.get("id"), "recipeKey": data.get("recipeKey"), "name": data.get("name")},
            "runtime": {
                "apiVersion": runtime.get("apiVersion"), "schema": runtime.get("schema"),
                "entities": [
                    {"id": row.get("id"), "kind": row.get("kind"), "visualRole": row.get("visualRole")}
                    for row in runtime.get("entities") or [] if isinstance(row, dict)
                ],
            },
            "parents": [_parent_manifest_summary(data.get("parentA")), _parent_manifest_summary(data.get("parentB"))],
            "authoringPolicy": "visual_director_exact_runtime_entities",
            "assets": [_asset_manifest_entry(data, row) for row in plan if isinstance(row, dict)],
        }
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        data.setdefault("visual", {})["assetManifestPath"] = str(path.resolve())
        data.setdefault("debug", {})["visualAssetManifest"] = str(path.resolve())
    except Exception as exc:
        data.setdefault("debug", {})["visualManifestError"] = repr(exc)


__all__ = ["_asset_sha256", "_asset_descriptor", "sprite_contract_for_asset", "_compact_text", "_parent_manifest_summary", "_asset_manifest_entry", "write_visual_manifest"]
