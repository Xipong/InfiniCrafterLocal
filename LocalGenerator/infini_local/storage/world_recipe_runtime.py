from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from infini_local.core.config_bootstrap import APP_VERSION, RECIPE_IDENTITY_VERSION, WORLD_RECIPES_DIR
from infini_local.core.item_identity_tools import name_of
from infini_local.storage import world_storage
from infini_local.storage.recipe_identity_index import resolve_recipe_key


# Bind application configuration and parent identity to the storage owner.
# File operations, delivery projection and admission live in world_storage.


def world_recipe_dir(world_id: Any) -> Path:
    # Directory is keyed by the real Terraria worldId. worldName is metadata only,
    # because a human-readable name may change while recipe discovery should stay
    # tied to the world identity.
    return world_storage.world_recipe_dir(WORLD_RECIPES_DIR, world_id)


def world_recipe_file(world_id: Any, recipe_key_value: str) -> Path:
    return world_storage.world_recipe_file(WORLD_RECIPES_DIR, world_id, recipe_key_value)


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


def read_world_recipe_cache(
    recipe_key_value: str, world_id: Any, world_name: Any = None, *,
    validate_payload: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    return world_storage.read_world_recipe_cache(
        WORLD_RECIPES_DIR,
        APP_VERSION,
        RECIPE_IDENTITY_VERSION,
        recipe_key_value,
        world_id,
        world_name,
        validate_payload=validate_payload,
    )


def cache_get(
    key: str, world_id: Any | None = None, world_name: Any = None, *,
    validate_payload: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    # Primary and only gameplay storage: explicit per-world recipe files.
    if world_id is None:
        return None
    return read_world_recipe_cache(key, world_id, world_name, validate_payload=validate_payload)


def cache_put(key: str, a: dict[str, Any], b: dict[str, Any], data: dict[str, Any], world_id: Any | None = None, world_name: Any = None) -> None:
    # No old-storage mirror. If this is a gameplay recipe, it must be world-scoped.
    if world_id is None:
        raise WorldScopeMissing("missing worldId while writing recipe; refusing non-world recipe storage")
    write_world_recipe_cache(key, world_id, data, a, b, world_name)


def recipe_key(
    a: dict[str, Any],
    b: dict[str, Any],
    world_id: Any,
    recipe_identity_version: str = RECIPE_IDENTITY_VERSION,
    variant_id: str = "",
) -> str:
    # Resolve accepted discoveries before choosing a generation/checkpoint key.
    # The pure core hash is only for genuinely new discoveries.
    return resolve_recipe_key(world_recipe_dir(world_id), a, b, world_id,
                              recipe_identity_version, variant_id)


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
    if type(raw) not in (int, str):
        raise WorldScopeMissing("worldId must be an integer or string identity")
    world_id = str(raw).strip()
    if not world_id or world_id.lower() in {"global", "none", "null"}:
        raise WorldScopeMissing("invalid worldId; InfiniCraft recipe cache is world-local and refuses global gameplay recipes")
    if any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in world_id):
        raise WorldScopeMissing("worldId contains invalid identity characters")
    return world_id


__all__ = [
    "WorldScopeMissing",
    "world_recipe_dir",
    "world_recipe_file",
    "write_world_recipe_cache",
    "read_world_recipe_cache",
    "cache_get",
    "cache_put",
    "recipe_key",
    "normalize_world_id_from_payload",
]
