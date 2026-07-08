from __future__ import annotations

from pathlib import Path
from typing import Any

from infini_local.core.config_bootstrap import APP_VERSION, RECIPE_IDENTITY_VERSION, WORLD_RECIPES_DIR
from infini_local.core.item_identity_tools import name_of, recipe_key as _world_recipe_key
from infini_local.storage import world_storage


# AGENT MAP: world-scoped recipe storage wrappers shared by pipeline support and
# the HTTP server. This is storage identity/sanitization glue only; no generation
# or fallback authoring belongs here.


def safe_file_part(text: Any, default: str = "value", max_len: int = 80) -> str:
    return world_storage.safe_file_part(text, default, max_len)


def world_recipe_dir(world_id: Any) -> Path:
    # Directory is keyed by the real Terraria worldId. worldName is metadata only,
    # because a human-readable name may change while recipe discovery should stay
    # tied to the world identity.
    return world_storage.world_recipe_dir(WORLD_RECIPES_DIR, world_id)


def world_recipe_file(world_id: Any, recipe_key_value: str) -> Path:
    return world_storage.world_recipe_file(WORLD_RECIPES_DIR, world_id, recipe_key_value)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    world_storage.atomic_write_json(path, payload)


def read_json_file(path: Path) -> dict[str, Any] | None:
    return world_storage.read_json_file(path)


def write_world_manifest(world_id: Any, world_name: Any = None) -> None:
    world_storage.write_world_manifest(WORLD_RECIPES_DIR, APP_VERSION, world_id, world_name)


def update_world_recipe_index(world_id: Any, recipe_key_value: str, data: dict[str, Any], a: Any = None, b: Any = None, world_name: Any = None) -> None:
    world_storage.update_world_recipe_index(
        WORLD_RECIPES_DIR,
        recipe_key_value,
        data,
        world_id=world_id,
        parent_a_name=name_of(a) if isinstance(a, dict) else data.get("recipeMeta", {}).get("parentA", ""),
        parent_b_name=name_of(b) if isinstance(b, dict) else data.get("recipeMeta", {}).get("parentB", ""),
        world_name=world_name,
    )


def strip_runtime_only_fields(data: dict[str, Any]) -> dict[str, Any]:
    return world_storage.strip_runtime_only_fields(data)


def _delivery_safe_debug(debug: Any) -> dict[str, str]:
    return world_storage.delivery_safe_debug(debug)


def sanitize_recipe_for_delivery(data: Any) -> Any:
    return world_storage.sanitize_recipe_for_delivery(data)


def write_world_recipe_cache(recipe_key_value: str, world_id: Any, data: dict[str, Any], a: Any = None, b: Any = None, world_name: Any = None) -> None:
    world_storage.write_world_recipe_cache(
        WORLD_RECIPES_DIR,
        APP_VERSION,
        recipe_key_value,
        world_id,
        data,
        parent_a_name=name_of(a) if isinstance(a, dict) else data.get("recipeMeta", {}).get("parentA", ""),
        parent_b_name=name_of(b) if isinstance(b, dict) else data.get("recipeMeta", {}).get("parentB", ""),
        world_name=world_name,
    )


def read_world_recipe_cache(recipe_key_value: str, world_id: Any, world_name: Any = None) -> dict[str, Any] | None:
    return world_storage.read_world_recipe_cache(
        WORLD_RECIPES_DIR,
        APP_VERSION,
        RECIPE_IDENTITY_VERSION,
        recipe_key_value,
        world_id,
        world_name,
    )


def is_deliverable_recipe_payload(data: Any) -> bool:
    return world_storage.is_deliverable_recipe_payload(data)


def cache_get(key: str, world_id: Any | None = None, world_name: Any = None) -> dict[str, Any] | None:
    # Primary and only gameplay storage: explicit per-world recipe files.
    if world_id is None:
        return None
    return read_world_recipe_cache(key, world_id, world_name)


def cache_put(key: str, a: dict[str, Any], b: dict[str, Any], data: dict[str, Any], world_id: Any | None = None, world_name: Any = None) -> None:
    # No old-storage mirror. If this is a gameplay recipe, it must be world-scoped.
    if world_id is None:
        raise WorldScopeMissing("missing worldId while writing recipe; refusing non-world recipe storage")
    write_world_recipe_cache(key, world_id, data, a, b, world_name)


def recipe_key(a: dict[str, Any], b: dict[str, Any], world_id: Any, recipe_identity_version: str = RECIPE_IDENTITY_VERSION) -> str:
    return _world_recipe_key(a, b, world_id, recipe_identity_version)


class WorldScopeMissing(RuntimeError):
    """Raised when a gameplay craft is missing a real Terraria world id.

    InfiniCraft recipes are world-local discoveries: the same pair in the same
    world must resolve to the same item, while another world may discover a
    different result. Falling back to a silent global key would leak recipes
    between worlds and break that architecture.
    """


def normalize_world_id_from_payload(payload: dict[str, Any]) -> str:
    if "worldId" not in payload:
        raise WorldScopeMissing("missing worldId; InfiniCraft recipe cache is world-local and refuses global gameplay recipes")
    raw = payload.get("worldId")
    if raw is None:
        raise WorldScopeMissing("worldId is null; InfiniCraft recipe cache is world-local and refuses global gameplay recipes")
    world_id = str(raw).strip()
    if not world_id or world_id.lower() in {"global", "none", "null"}:
        raise WorldScopeMissing("invalid worldId; InfiniCraft recipe cache is world-local and refuses global gameplay recipes")
    return world_id


__all__ = [
    "WorldScopeMissing",
    "safe_file_part",
    "world_recipe_dir",
    "world_recipe_file",
    "atomic_write_json",
    "read_json_file",
    "write_world_manifest",
    "update_world_recipe_index",
    "strip_runtime_only_fields",
    "_delivery_safe_debug",
    "sanitize_recipe_for_delivery",
    "write_world_recipe_cache",
    "read_world_recipe_cache",
    "is_deliverable_recipe_payload",
    "cache_get",
    "cache_put",
    "recipe_key",
    "normalize_world_id_from_payload",
]
