from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


# AGENT MAP: final asset filename contract shared with C# asset sync. Only safe
# basename `.png`/`.json` files are exposed; raw generation intermediates and
# arbitrary paths/URLs are deliberately stripped. C# downloads these by `/get_asset`.
def asset_filename_from_path(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        if parsed.scheme in {"http", "https"}:
            raw = parsed.path
    except Exception:
        pass
    name = Path(raw.replace("\\", "/")).name
    if not name or name in {".", ".."}:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9._@+\-]{1,160}", name):
        return ""
    if not name.lower().endswith((".png", ".json")):
        return ""
    return name


def runtime_asset_files(data: dict[str, Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def add(v: Any) -> None:
        name = asset_filename_from_path(v)
        if name and name not in seen:
            seen.add(name)
            out.append(name)

    visual_raw = data.get("visual")
    attack_raw = data.get("attack")
    visual: dict[str, Any] = visual_raw if isinstance(visual_raw, dict) else {}
    attack: dict[str, Any] = attack_raw if isinstance(attack_raw, dict) else {}
    # Multiplayer clients only need final gameplay-facing assets, not raw generation intermediates.
    add(visual.get("spritePath"))
    add(visual.get("equipOverlayPath"))
    add(visual.get("assetManifestPath"))
    for key in ["projectileSpritePath", "impactSpritePath", "childSpritePath", "fieldSpritePath"]:
        add(attack.get(key))
    assets = visual.get("assets") or data.get("assets") or []
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            status = str(asset.get("status") or "").strip().lower()
            if status in {"failed", "prompt_only", ""}:
                continue
            add(asset.get("path") or asset.get("file"))
    return out[:64]


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
            if (sprite_dir / n).exists() or (world_recipes_dir / n).exists():
                return n
    return ""


def find_asset_file(name: str, *, sprite_dir: Path, world_recipes_dir: Path) -> Path | None:
    if not name:
        return None
    roots = [sprite_dir, world_recipes_dir]
    for root in roots:
        candidate = root / name
        try:
            if candidate.exists() and candidate.is_file() and candidate.resolve().is_relative_to(root.resolve()):
                return candidate
        except Exception:
            pass
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
