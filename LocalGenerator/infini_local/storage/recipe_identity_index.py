from __future__ import annotations

"""Derived native-name lookup. Recipe JSON files remain the only authority.

The index stores lineage/scope and file witnesses, not accepted definitions.
Every candidate must independently prove its literal old or stable recipe hash.
No record is migrated, renamed, quarantined or rewritten by this owner.
"""

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from infini_local.core.item_identity_tools import (
    item_identity, recipe_key_from_identities, stable_recipe_identity,
)
from infini_local.storage.world_storage import read_json_file


class RecipeIdentityConflict(RuntimeError):
    """Multiple proven records (or a changing join) must not trigger a reroll."""


def _pair(identities: list[str]) -> str:
    return json.dumps(sorted(stable_recipe_identity(value) for value in identities), ensure_ascii=False)


def _witness(path: Path) -> str:
    stat = path.stat(follow_symlinks=False)
    return json.dumps([stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino, stat.st_dev])


def _read_record(path: Path) -> dict[str, Any] | None:
    return read_json_file(path, raise_io=True)


def _projection(record: dict[str, Any] | None) -> tuple[str | None, str]:
    """Keep absence distinct from explicit invalid or contradictory diagnostics."""
    if not record:
        return None, "{}"
    meta, debug = record.get("recipeMeta"), record.get("debug", {})
    if not isinstance(meta, dict) or not isinstance(debug, dict):
        return None, "{}"
    parents = meta.get("parentIdentities", [])
    fields = {"parents": parents, "key": record.get("recipeKey"), "world": meta.get("worldId")}
    for name in ("recipeIdentityVersion", "multiDevProfileId"):
        if name in debug:
            fields[name] = debug[name]
    pair = _pair(parents) if isinstance(parents, list) and len(parents) == 2 and all(isinstance(p, str) and p for p in parents) else None
    return pair, json.dumps(fields, ensure_ascii=False)


def _refresh(connection: sqlite3.Connection, root: Path) -> None:
    # BEGIN IMMEDIATE serializes refreshes across threads/processes. Listing and
    # stat failures propagate: an incomplete archive view is never a cache miss.
    connection.execute("BEGIN IMMEDIATE")
    if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
        connection.execute("DROP TABLE IF EXISTS recipes")
        connection.execute("PRAGMA user_version = 1")
    connection.execute("CREATE TABLE IF NOT EXISTS recipes (file TEXT PRIMARY KEY, witness TEXT NOT NULL, pair TEXT, identity TEXT NOT NULL)")
    connection.execute("CREATE INDEX IF NOT EXISTS recipes_pair ON recipes(pair)")
    previous = dict(connection.execute("SELECT file, witness FROM recipes"))
    folder = root / "recipes"
    try:
        entries = os.scandir(folder)
    except FileNotFoundError:
        entries = None
    if entries is not None:
        with entries:
            for entry in entries:
                if not entry.name.endswith(".json"):
                    continue
                if entry.is_symlink():
                    raise OSError(f"recipe identity cannot assess a symlink: {entry.path}")
                if not entry.is_file(follow_symlinks=False):
                    continue
                path = Path(entry.path)
                witness = _witness(path)
                if previous.pop(entry.name, None) == witness:
                    continue
                pair, fields = _projection(_read_record(path))
                if _witness(path) != witness:
                    raise OSError(f"recipe changed during identity assessment: {path}")
                connection.execute("INSERT OR REPLACE INTO recipes VALUES (?, ?, ?, ?)",
                                   (entry.name, witness, pair, fields))
    connection.executemany("DELETE FROM recipes WHERE file = ?", ((name,) for name in previous))


def _proves(fields: dict[str, Any], filename: str, world: str, version: str, profile: str) -> bool:
    if fields.get("world") != world:
        return False
    # Missing debug can be proven by the requested version/profile hash; an
    # explicit mismatch or invalid value is never treated as historical absence.
    for name, expected in (("recipeIdentityVersion", version), ("multiDevProfileId", profile)):
        if name in fields and fields[name] != expected:
            return False
    key = fields.get("key")
    if not isinstance(key, str) or filename != key + ".json":
        return False
    return any(key == recipe_key_from_identities(fields["parents"], world, version,
                                                stable_names=stable, variant_id=profile)
               for stable in (False, True))


def resolve_recipe_key(
    world_dir: Path, a: dict[str, Any], b: dict[str, Any], world_id: Any,
    recipe_identity_version: str, variant_id: str = "",
) -> str:
    """Return the unique proven original key, or the new stable key on absence.

    SQLite/recipe I/O errors and ambiguity propagate, before any Author stage.
    Removing the derived database rebuilds it from the unchanged recipe files.
    Full strict wire/asset admission remains the canonical reader's job.
    """
    parents = [item_identity(a), item_identity(b)]
    profile = str(variant_id or "").strip().lower()
    new_key = recipe_key_from_identities(parents, world_id, recipe_identity_version,
                                         stable_names=True, variant_id=profile)
    root = Path(world_dir)
    root.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(root / "recipe_identity.sqlite3", timeout=30)) as connection:
        with connection:
            _refresh(connection, root)
            requested_pair = _pair(parents)
            direct = connection.execute("SELECT file, pair, identity FROM recipes WHERE file = ?",
                                        (new_key + ".json",)).fetchone()
            if direct and direct[1] is not None and (
                direct[1] != requested_pair or not _proves(json.loads(direct[2]), direct[0], str(world_id), recipe_identity_version, profile)
            ):
                raise RecipeIdentityConflict("stored recipe contradicts the requested stable key: " + new_key)
            matches = []
            # Exact current legacy hashing remains proof when old optional
            # lineage is absent. Do not lose a same-ID discovery just because
            # its body predates parentIdentities; no numeric search or inference.
            old_key = recipe_key_from_identities(parents, world_id, recipe_identity_version,
                                                 stable_names=False, variant_id=profile)
            old = connection.execute("SELECT file, witness, pair, identity FROM recipes WHERE file = ?",
                                     (old_key + ".json",)).fetchone()
            if old and old[2] is None:
                fields = json.loads(old[3])
                if fields.get("parents") == [] and _proves({**fields, "parents": parents}, old[0],
                                                          str(world_id), recipe_identity_version, profile):
                    if _witness(root / "recipes" / old[0]) != old[1]:
                        raise OSError("recipe changed during identity lookup")
                    matches.append(old_key)
            for filename, witness, raw in connection.execute(
                "SELECT file, witness, identity FROM recipes WHERE pair = ?", (requested_pair,),
            ):
                fields = json.loads(raw)
                if _proves(fields, filename, str(world_id), recipe_identity_version, profile):
                    if _witness(root / "recipes" / filename) != witness:
                        raise OSError("recipe changed during identity lookup")
                    matches.append(fields["key"])
            if len(matches) > 1:
                raise RecipeIdentityConflict("multiple accepted recipes prove this parent pair: " + ", ".join(sorted(matches)))
            if matches:
                return matches[0]
    return new_key
