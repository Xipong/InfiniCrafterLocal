from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def dict_get_ci(d: Any, name: str, default: Any = None) -> Any:
    if not isinstance(d, dict):
        return default
    if name in d:
        return d.get(name, default)
    target = str(name).lower()
    for k, v in d.items():
        if str(k).lower() == target:
            return v
    return default


def name_of(item: dict[str, Any]) -> str:
    return str(item.get("name") or "Unknown")


def slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9а-яё]+", "_", text)
    return text.strip("_") or "item"


def stable_hash(*parts: Any, length: int = 16) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:length]


def generated_data_of(item: dict[str, Any]) -> dict[str, Any]:
    gd = item.get("generatedData")
    return gd if isinstance(gd, dict) else {}


def fingerprint_of(item: dict[str, Any]) -> dict[str, Any]:
    fp = item.get("fingerprint")
    return fp if isinstance(fp, dict) else {}


def item_identity(item: dict[str, Any]) -> str:
    gd = item.get("generatedData")
    gid = dict_get_ci(gd, "id") if isinstance(gd, dict) else None
    if gid:
        return "generated:" + str(gid)
    fp = fingerprint_of(item)
    source = str(item.get("sourceMod") or fp.get("sourceMod") or "Terraria")
    internal = str(item.get("internalName") or fp.get("internalName") or "")
    full = str(item.get("fullName") or fp.get("fullName") or "")
    if full:
        return "item:" + full + ":" + str(item.get("id", ""))
    if internal:
        return "item:" + source + ":" + internal + ":" + str(item.get("id", ""))
    return "item:" + source + ":" + str(item.get("id", "")) + ":" + slug(name_of(item))


def recipe_key(a: dict[str, Any], b: dict[str, Any], world_id: Any, recipe_identity_version: str) -> str:
    # Commutative and world-local recipe key: A+B equals B+A inside one world.
    # Do not fall back to a global scope here; /combine validates worldId before
    # calling this. A missing world id is a gameplay error, not a cache feature.
    ak = item_identity(a)
    bk = item_identity(b)
    pair = sorted([ak, bk])
    return "r_" + stable_hash(pair, "world:" + str(world_id), recipe_identity_version, length=24)


def item_field(item: dict[str, Any], name: str, default: Any = 0) -> Any:
    """Read a top-level wire field first, then its richer C# fingerprint twin."""
    if name in item and item.get(name) is not None:
        return item.get(name)
    fp = fingerprint_of(item)
    return fp.get(name, default)


def item_num(item: dict[str, Any], name: str, default: float = 0.0) -> float:
    try:
        return float(item_field(item, name, default) or 0)
    except Exception:
        return default


def item_bool(item: dict[str, Any], name: str) -> bool:
    v = item_field(item, name, False)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in {"1", "true", "yes", "y"}
    return bool(v)


def _stringish(x: Any, fallback: str = "") -> str:
    if x is None:
        return fallback
    if isinstance(x, (list, tuple)):
        return "; ".join(str(v) for v in x if str(v).strip()) or fallback
    if isinstance(x, dict):
        return json.dumps(x, ensure_ascii=False, separators=(",", ":"))
    return str(x)


def tags_of(item: dict[str, Any]) -> set[str]:
    tags = {str(t).lower() for t in item.get("tags", []) if str(t).strip()}
    tags |= {str(t).lower() for t in item.get("autoFeatures", []) if str(t).strip()}
    tags |= {str(t).lower() for t in item.get("nameTokens", []) if str(t).strip()}
    gd = generated_data_of(item)
    if gd:
        tags |= {str(t).lower() for t in dict_get_ci(gd, "tags", []) if str(t).strip()}
        can = dict_get_ci(gd, "canonical", {}) or {}
        if isinstance(can, dict):
            tags |= {str(t).lower() for t in dict_get_ci(can, "hardTags", []) if str(t).strip()}
            tags |= {str(t).lower() for t in dict_get_ci(can, "softTags", []) if str(t).strip()}
    fp = fingerprint_of(item)
    if fp:
        tags |= {str(t).lower() for t in fp.get("autoFeatures", []) if str(t).strip()}
    return tags


def generation_depth(item: dict[str, Any]) -> int:
    gd = generated_data_of(item)
    if not gd:
        return 0
    meta_raw = dict_get_ci(gd, "recipeMeta", {})
    for source in (meta_raw if isinstance(meta_raw, dict) else {},):
        for key in ("generationDepth", "depth"):
            try:
                if key in source:
                    return max(1, int(float(source[key])))
            except Exception:
                pass
    return 1
