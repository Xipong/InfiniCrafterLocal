from __future__ import annotations
from infini_local.core.asset_files import asset_filename_from_path

import json
import re
from pathlib import Path
from typing import Any


def runtime_asset_paths(data: dict[str, Any], *, include_vfx_assets: bool = True) -> list[Any]:
    """Canonical DTO path projection shared by roster and image delivery gates."""
    out: list[Any] = []
    manifest_raw = data.get("vfxManifest")
    manifest = manifest_raw if isinstance(manifest_raw, dict) else {}
    assets = manifest.get("assets")
    if include_vfx_assets and isinstance(assets, list):
        out.extend(asset.get("spritePath") for asset in assets if isinstance(asset, dict))
    visual_raw = data.get("visual")
    visual = visual_raw if isinstance(visual_raw, dict) else {}
    out.extend((visual.get("spritePath"), visual.get("equipOverlayPath")))
    runtime_raw = data.get("runtimeProgram")
    runtime = runtime_raw if isinstance(runtime_raw, dict) else {}
    entities = runtime.get("entities")
    for entity in entities if isinstance(entities, list) else []:
        if isinstance(entity, dict):
            visual_raw = entity.get("visual")
            entity_visual = visual_raw if isinstance(visual_raw, dict) else {}
            out.append(entity_visual.get("spritePath"))
    return out


def runtime_asset_files(data: dict[str, Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    # Same DTO paths and case-insensitive PNG identity as C#. Diagnostic JSON,
    # debug plans, generic asset arrays and recipeMeta lists are not authorities.
    for path in runtime_asset_paths(data):
        name = asset_filename_from_path(path)
        key = name.casefold()
        if name.lower().endswith(".png") and key not in seen:
            seen.add(key)
            out.append(name)
    if len(out) > 32:
        raise ValueError("generated asset roster exceeds 32 files")
    return out


def attach_asset_sync_meta(data: dict[str, Any], *, asset_public_base_url: str = "") -> dict[str, Any]:
    meta = data.setdefault("recipeMeta", {})
    files = runtime_asset_files(data)
    meta["assetFiles"] = files
    if asset_public_base_url:
        meta["assetBaseUrl"] = asset_public_base_url
    meta["assetSync"] = {"mode": "http_by_filename", "endpoint": "/get_asset", "fileCount": len(files), "finalOnly": True}
    data.setdefault("debug", {})["assetFiles"] = json.dumps(files, ensure_ascii=False)
    return data


def safe_asset_file_from_query(q: dict[str, list[str]], *, sprite_dir: Path, world_recipes_dir: Path) -> str:
    value = (q.get("file") or q.get("name") or q.get("hash") or [""])[0]
    name = asset_filename_from_path(value)
    if name:
        return name
    # Convenience for user-facing hash=abc without extension: prefer png, then json.
    raw = str(value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9._@+\-]{1,140}", raw):
        for suffix in [".png", ".json"]:
            n = raw + suffix
            if find_asset_file(n, sprite_dir=sprite_dir, world_recipes_dir=world_recipes_dir) is not None:
                return n
    return ""


def find_asset_file(name: str, *, sprite_dir: Path, world_recipes_dir: Path) -> Path | None:
    if not name or asset_filename_from_path(name) != name:
        return None
    if name.lower().endswith(".png"):
        from infini_local.storage.image_store import resolve
        return resolve(sprite_dir, name)
    # World recipes live in per-world subdirs; only allow exact filename match, no path input.
    if name.lower().endswith(".json") and world_recipes_dir.exists():
        for candidate in world_recipes_dir.rglob(name):
            try:
                if candidate.is_file() and candidate.resolve().is_relative_to(world_recipes_dir.resolve()):
                    return candidate
            except Exception:
                continue
    return None


def asset_content_type(p: Path) -> str:
    return "image/png" if p.suffix.lower() == ".png" else "application/json; charset=utf-8"
