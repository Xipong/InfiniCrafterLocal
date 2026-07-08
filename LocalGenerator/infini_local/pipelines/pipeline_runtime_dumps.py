from __future__ import annotations

from pathlib import Path
from typing import Any

from infini_local.core.config_bootstrap import DATA_DIR
from infini_local.core.item_identity_tools import item_field
from infini_local.services import runtime_dump_service

# AGENT MAP: live tModLoader runtime dump indexes and lookups. These are factual
# item/projectile snapshots loaded from /infinidump outputs; no authoring policy lives here.


def _runtime_dump_candidates(filename: str, explicit_env: str, legacy_env: str) -> list[Path]:
    return runtime_dump_service.runtime_dump_candidates(DATA_DIR, filename, explicit_env, legacy_env)


def _resolve_runtime_dump_path(filename: str, explicit_env: str, legacy_env: str) -> Path:
    return runtime_dump_service.resolve_runtime_dump_path(DATA_DIR, filename, explicit_env, legacy_env)


ITEMS_RUNTIME_DUMP_PATH = _resolve_runtime_dump_path("items_runtime_dump.jsonl", "INFINI_ITEMS_RUNTIME_DUMP", "INFINI_ITEMS_DUMP")
PROJECTILES_RUNTIME_DUMP_PATH = _resolve_runtime_dump_path("projectiles_runtime_dump.jsonl", "INFINI_PROJECTILES_RUNTIME_DUMP", "INFINI_PROJECTILES_DUMP")


def load_jsonl_index(path: Path, key_fields: tuple[str, ...]) -> tuple[list[dict[str, Any]], dict[Any, dict[str, Any]], dict[str, dict[str, Any]]]:
    return runtime_dump_service.load_jsonl_index(path, key_fields)


RUNTIME_ITEMS, RUNTIME_ITEMS_BY_TYPE, RUNTIME_ITEMS_BY_NAME = load_jsonl_index(ITEMS_RUNTIME_DUMP_PATH, ("sourceMod", "internalName"))
RUNTIME_PROJECTILES, RUNTIME_PROJECTILES_BY_TYPE, RUNTIME_PROJECTILES_BY_NAME = load_jsonl_index(PROJECTILES_RUNTIME_DUMP_PATH, ("sourceMod", "internalName"))


def runtime_item_lookup(item: dict[str, Any]) -> dict[str, Any]:
    return runtime_dump_service.runtime_item_lookup(
        item,
        RUNTIME_ITEMS_BY_TYPE,
        RUNTIME_ITEMS_BY_NAME,
        item_field=item_field,
    )


def runtime_projectile_lookup(type_id: Any) -> dict[str, Any]:
    return runtime_dump_service.runtime_projectile_lookup(type_id, RUNTIME_PROJECTILES_BY_TYPE)


__all__ = [
    "ITEMS_RUNTIME_DUMP_PATH",
    "PROJECTILES_RUNTIME_DUMP_PATH",
    "RUNTIME_ITEMS",
    "RUNTIME_ITEMS_BY_TYPE",
    "RUNTIME_ITEMS_BY_NAME",
    "RUNTIME_PROJECTILES",
    "RUNTIME_PROJECTILES_BY_TYPE",
    "RUNTIME_PROJECTILES_BY_NAME",
    "_runtime_dump_candidates",
    "_resolve_runtime_dump_path",
    "load_jsonl_index",
    "runtime_item_lookup",
    "runtime_projectile_lookup",
]
