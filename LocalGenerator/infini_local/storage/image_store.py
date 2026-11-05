from __future__ import annotations

"""Persistent final PNGs, private attempts, and reversible legacy filename aliases.

The wire still carries a safe basename. Only indexed, complete final PNGs are
served; diagnostics are never discovered by a recursive HTTP search. An alias
is committed after its bytes, and old owned copies are removed only afterwards.
No gameplay schema, recipe identity, or authored visual is migrated here.
"""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import unicodedata
from typing import Any, Iterator

SCHEMA = "infini.image-store.v1"
_LOCK = threading.RLock()
_SAFE_FILE = re.compile(r"[A-Za-z0-9._@+\-]{1,156}\.png\Z", re.IGNORECASE)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def safe_label(value: Any, fallback: str, limit: int = 20) -> str:
    # The same conservative Windows rules apply on all generator platforms.
    text = unicodedata.normalize("NFC", str(value or ""))
    text = "".join(c if c.isalnum() or c in " _-" else "_" for c in text)
    text = re.sub(r"\s+", " ", text).strip(" ._")[:limit].rstrip(" ._")
    return text or fallback



def _owned_path(root: Path, path: Path) -> bool:
    try:
        absolute_root = Path(os.path.abspath(root))
        absolute = Path(os.path.abspath(path))
        if not absolute.is_relative_to(absolute_root):
            return False
        while True:
            if absolute.is_symlink():
                return False
            if absolute == absolute_root:
                return True
            absolute = absolute.parent
    except OSError:
        return False


def _read_metadata(root: Path, path: Path) -> dict[str, Any]:
    if not _owned_path(root, path) or path.stat().st_size > 16 * 1024:
        raise OSError("invalid image store metadata")
    with path.open("rb") as stream:
        raw = stream.read(16 * 1024 + 1)
    if len(raw) > 16 * 1024:
        raise OSError("oversized image store metadata")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("image metadata is not an object")
    return value

def _atomic_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_bytes(path, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


@contextmanager
def store_lock(root: Path) -> Iterator[None]:
    """One crash-released byte-range lock, shared with the native image store."""
    if not _owned_path(root, root / ".store.lock"):
        raise OSError("image store root or lock is linked")
    root.mkdir(parents=True, exist_ok=True)
    with _LOCK, (root / ".store.lock").open("a+b") as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.lockf(stream.fileno(), fcntl.LOCK_EX, 1)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.lockf(stream.fileno(), fcntl.LOCK_UN, 1)


def _identity_directory(parent: Path, identity: str, label: str, kind: str) -> Path:
    suffix = "--" + _digest(identity)[:16]
    if not _owned_path(parent, parent):
        raise OSError("image identity directory is linked")
    parent.mkdir(parents=True, exist_ok=True)
    for path in sorted(parent.glob("*" + suffix)):
        if not path.is_dir() or path.is_symlink():
            continue
        try:
            saved = _read_metadata(parent, path / ".identity.json")
        except (OSError, ValueError):
            continue
        if saved.get("id") == identity and saved.get("kind") == kind:
            if saved.get("name") != label:
                _atomic_json(path / ".identity.json", {"kind": kind, "id": identity, "name": label})
            return path
    path = parent / (safe_label(label or identity, kind) + suffix)
    # Never overwrite a directory with unknown ownership, even on hash collision.
    if path.exists():
        raise OSError("image directory ownership conflict: " + str(path))
    temporary = Path(tempfile.mkdtemp(prefix=".identity-", dir=parent))
    _atomic_json(temporary / ".identity.json", {"kind": kind, "id": identity, "name": label})
    # A crash before rename leaves an unreferenced private metadata folder, not
    # an incomplete identity directory that would block the next publication.
    temporary.rename(path)
    return path


def _item_directory(root: Path, data: dict[str, Any]) -> Path:
    meta = data.get("recipeMeta") if isinstance(data.get("recipeMeta"), dict) else {}
    world_id = str(meta.get("worldId") or "unscoped")
    item_id = str(data.get("id") or "unscoped")
    world = _identity_directory(root / "worlds", world_id, str(meta.get("worldName") or world_id), "world")
    return _identity_directory(world, item_id, str(data.get("name") or item_id), "item")


def item_directory(root: Path, data: dict[str, Any]) -> Path:
    with store_lock(root):
        return _item_directory(root, data)


def diagnostics_directory(root: Path, data: dict[str, Any], role: str) -> Path:
    with store_lock(root):
        parent = _item_directory(root, data) / "diagnostics"
        parent.mkdir(exist_ok=True)
        return Path(tempfile.mkdtemp(prefix=safe_label(role, "asset") + "-", dir=parent))


def _index_path(root: Path, name: str) -> Path:
    return root / ".index" / (_digest(name.lower()) + ".json")


def _declared_entry(root: Path, name: str) -> tuple[Path, dict[str, Any]] | None:
    if not _SAFE_FILE.fullmatch(name):
        return None
    try:
        entry = _read_metadata(root, _index_path(root, name))
        if entry.get("schema") != SCHEMA or str(entry.get("file", "")).lower() != name.lower():
            return None
        path = entry["path"]
        if not isinstance(path, str) or "\\" in path or ":" in path:
            return None
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts or "diagnostics" in {part.casefold() for part in relative.parts}:
            return None
        candidate = root / relative
        if candidate.parent.name != "final" or not _SAFE_FILE.fullmatch(candidate.name) or not _owned_path(root, candidate):
            return None
        if (type(entry.get("length")) is not int or not 0 < entry["length"] <= 8 * 1024 * 1024
                or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256") or ""))):
            return None
        return candidate, entry
    except (OSError, ValueError, KeyError, TypeError):
        return None


def resolve(root: Path, name: str) -> Path | None:
    declared = _declared_entry(root, name)
    if declared is None:
        return None
    candidate, entry = declared
    try:
        if candidate.is_file() and candidate.stat().st_size == entry["length"]:
            with candidate.open("rb") as stream:
                raw = stream.read(8 * 1024 * 1024 + 1)
            if len(raw) == entry["length"] and hashlib.sha256(raw).hexdigest() == entry["sha256"]:
                return candidate
    except OSError:
        pass
    return None


def has_index(root: Path, name: str) -> bool:
    return bool(_SAFE_FILE.fullmatch(name) and (_index_path(root, name).exists() or _index_path(root, name).is_symlink()))


def _register(root: Path, name: str, destination: Path, raw: bytes, data: dict[str, Any], role: str) -> None:
    if not _SAFE_FILE.fullmatch(name):
        raise ValueError("unsafe image transport filename")
    sha = hashlib.sha256(raw).hexdigest()
    index = _index_path(root, name)
    if not _owned_path(root, index):
        raise OSError("image index escapes its storage root")
    if index.exists():
        try:
            saved = _read_metadata(root, index)
        except (OSError, ValueError) as exc:
            raise OSError("unreadable image alias; preserving original") from exc
        if (saved.get("schema") != SCHEMA or str(saved.get("file", "")).lower() != name.lower()
                or saved.get("sha256") != sha or saved.get("length") != len(raw)):
            raise OSError("image transport filename collision: " + name)
    old = resolve(root, name)
    if old is not None and old.resolve() != destination.resolve() and old.read_bytes() != raw:
        raise OSError("image transport filename collision: " + name)
    meta = data.get("recipeMeta") if isinstance(data.get("recipeMeta"), dict) else {}
    _atomic_json(_index_path(root, name), {
        "schema": SCHEMA, "file": name, "path": destination.relative_to(root).as_posix(),
        "sha256": sha, "length": len(raw), "worldId": str(meta.get("worldId") or "unscoped"),
        "itemId": str(data.get("id") or "unscoped"), "role": role,
    })


def publish(root: Path, data: dict[str, Any], role: str, identity: bytes, source: Path,
            *, aliases: tuple[str, ...] = ()) -> Path:
    from infini_local.services.asset_sync_service import is_complete_png_file

    if not is_complete_png_file(source):
        raise ValueError("cannot publish an incomplete final PNG")
    raw = source.read_bytes()
    meta = data.get("recipeMeta") if isinstance(data.get("recipeMeta"), dict) else {}
    scope = json.dumps([str(meta.get("worldId") or "unscoped"), str(data.get("id") or "unscoped"), role],
                       ensure_ascii=True, separators=(",", ":")).encode("ascii")
    digest = hashlib.sha256(scope + b"\0" + identity + b"\0" + raw).hexdigest()
    label = re.sub(r"[^a-z0-9_-]+", "_", role.lower()).strip("_")[:24] or "asset"
    with store_lock(root):
        # Migration aliases are global transport identities. Resolve them again
        # under the process lock: another world/item can have adopted the same
        # legacy PNG while this caller was reading its source bytes.
        existing = None
        content_sha = hashlib.sha256(raw).hexdigest()
        for name in aliases:
            if not _SAFE_FILE.fullmatch(name):
                raise ValueError("unsafe image transport filename")
            if has_index(root, name):
                declared = _declared_entry(root, name)
                if declared is None or declared[1]["sha256"] != content_sha or declared[1]["length"] != len(raw):
                    raise OSError("image transport filename collision: " + name)
                existing = existing or declared[0]
        if existing is not None:
            if not existing.exists() or existing.read_bytes() != raw:
                _atomic_bytes(existing, raw)  # Restore this alias's declared bytes.
            for name in aliases:
                if not has_index(root, name):
                    _register(root, name, existing, raw, data, role)
            return existing.resolve()
        destination = _item_directory(root, data) / "final" / (label + "--" + digest + ".png")
        if not _owned_path(root, destination):
            raise OSError("image destination escapes its storage root")
        if destination.is_symlink():
            raise OSError("image destination is not an owned regular file")
        if destination.exists():
            if destination.read_bytes() != raw:
                raise OSError("immutable image content conflict: " + str(destination))
        else:
            _atomic_bytes(destination, raw)
        for name in (destination.name, *aliases):
            _register(root, name, destination, raw, data, role)
    return destination.resolve()


def legacy_roots(root: Path) -> tuple[Path, ...]:
    from infini_local.core.config_bootstrap import SPRITE_DIR, LEGACY_SPRITE_DIR

    if root.resolve() != SPRITE_DIR.resolve():
        return ()
    return (LEGACY_SPRITE_DIR, root.parent / "asset_cache")


def runtime_image_fields(data: dict[str, Any]):
    # This read-only projection is also used by the delivery sanitizer before a
    # malformed cached record is refused. It must not mask that refusal by
    # crashing on a non-object row, or reinterpret an invalid authored value.
    visual = data.get("visual")
    if isinstance(visual, dict):
        yield visual, "spritePath", "item"
        yield visual, "equipOverlayPath", "equip_overlay"
    runtime = data.get("runtimeProgram")
    entities = runtime.get("entities") if isinstance(runtime, dict) else None
    for entity in entities if isinstance(entities, list) else []:
        if not isinstance(entity, dict) or not isinstance(entity.get("visual"), dict):
            continue
        visual = entity["visual"]
        yield visual, "spritePath", "entity_" + str(entity.get("id") or "")
        yield visual, "impactSpritePath", "impact_" + str(entity.get("id") or "")
    manifest = data.get("vfxManifest")
    assets = manifest.get("assets") if isinstance(manifest, dict) else None
    for asset in assets if isinstance(assets, list) else []:
        if isinstance(asset, dict):
            yield asset, "spritePath", "vfx_" + str(asset.get("id") or "")


def compact_delivery_paths(root: Path, data: dict[str, Any]) -> None:
    """Transport normalization: indexed final identity needs no machine path.

    Keep historical paths untouched. Only paths to this store's exact canonical
    file become basenames, avoiding both Windows path limits and host path leaks.
    """
    from infini_local.services.asset_sync_service import asset_filename_from_path
    for owner, field, _ in runtime_image_fields(data):
        value = owner.get(field)
        name = asset_filename_from_path(value)
        canonical = resolve(root, name)
        if canonical is not None and Path(str(value)).resolve() == canonical.resolve():
            owner[field] = name


def adopt_recipe(root: Path, data: dict[str, Any], *, old_roots: tuple[Path, ...] | None = None) -> list[dict[str, str]]:
    """Relocate only referenced complete PNGs; preserve old DTOs via aliases.

    Run only after recipe/runtime identity validation. An interrupted operation
    leaves either the old file or the verified canonical bytes plus its alias.
    A later pass retries cleanup. Unknown files and conflicting bytes survive.
    """
    from infini_local.services.asset_sync_service import asset_filename_from_path, is_complete_png_file

    roots = legacy_roots(root) if old_roots is None else old_roots
    receipts = []
    for owner, field, role in runtime_image_fields(data):
        raw_path = owner.get(field)
        name = asset_filename_from_path(raw_path)
        if not name.lower().endswith(".png"):
            continue
        candidates = [old / name for old in roots if not old.is_symlink()]
        source = resolve(root, name)
        if source is None:
            source = next((p for p in candidates if not p.is_symlink() and is_complete_png_file(p)), None)
            if source is None:
                continue
            identity = json.dumps(["legacy", name], separators=(",", ":")).encode("utf-8")
            try:
                source = publish(root, data, role, identity, source, aliases=(name,))
            except (FileNotFoundError, ValueError):
                source = resolve(root, name)  # A concurrent adopter may have moved it.
                if source is None:
                    raise
        canonical = source.read_bytes()
        for candidate in candidates:
            if candidate.resolve() == source.resolve() or candidate.is_symlink():
                continue
            try:
                if candidate.is_file() and candidate.read_bytes() == canonical:
                    candidate.unlink()
                    receipts.append({"from": str(candidate), "to": str(source)})
            except OSError:
                # An in-use Windows file is retried on the next admission.
                continue
    return receipts


def finish_diagnostics(directory: Path, canonical: Path, attempts: list[dict[str, Any]], status: str) -> dict[str, str]:
    """Keep attempts, but replace their accepted bake copies with a receipt.

    Cleanup is restartable and best-effort: a locked diagnostic file must not
    revoke an already committed, usable final PNG. No unknown files are touched.
    """
    raw = canonical.read_bytes()
    retained = []
    redirected = {}
    for row in attempts:
        targets = [(row, "final")]
        if isinstance(row.get("refit"), dict):
            targets.append((row["refit"], "path"))
        for owner, key in targets:
            value = owner.get(key)
            if not value:
                continue
            old = Path(str(value))
            if not old.resolve().is_relative_to(directory.resolve()) or old.is_symlink():
                continue
            try:
                # Only exact accepted bytes, not a different failed bake.
                if old.is_file() and old.read_bytes() == raw:
                    old.unlink()
                    redirected[str(old)] = str(canonical)
                    owner[key] = str(canonical)
            except OSError:
                retained.append(str(old))
    # Optional stage capture otherwise saves another byte-identical final bake.
    for old in directory.glob("attempt-*/*_stage_30_baked_final.png"):
        try:
            if not old.is_symlink() and old.read_bytes() == raw:
                old.unlink()
        except OSError:
            retained.append(str(old))
    try:
        _atomic_json(directory / "result.json", {
            "final": str(canonical), "status": status, "attempts": attempts,
            "cleanupPending": retained,
        })
    except OSError:
        pass
    return redirected


def adopt_diagnostics(root: Path, data: dict[str, Any], *, old_root: Path | None = None) -> list[dict[str, str]]:
    """Relocate recorded legacy attempts without guessing at unowned files."""
    from infini_local.core.config_bootstrap import LEGACY_SPRITE_DIR
    from infini_local.services.asset_sync_service import asset_filename_from_path
    old_root = LEGACY_SPRITE_DIR.parent / "image-diagnostics" if old_root is None else old_root
    if not old_root.exists() or old_root.is_symlink():
        return []
    finals = {}
    for owner, field, _ in runtime_image_fields(data):
        canonical = resolve(root, asset_filename_from_path(owner.get(field)))
        if canonical is not None:
            finals[hashlib.sha256(canonical.read_bytes()).hexdigest()] = canonical
    receipts = []
    for key, value in (data.get("debug") or {}).items():
        if not key.endswith("SpriteDiagnostics"):
            continue
        try:
            entry = json.loads(value) if isinstance(value, str) else value
            original = str(entry.get("directory") or "").replace("\\", "/")
        except (ValueError, TypeError, AttributeError):
            continue
        parts = original.split("/")
        if len(parts) < 2 or parts[-2] != "image-diagnostics" or not re.fullmatch(r"image-[A-Za-z0-9_-]+", parts[-1]):
            continue
        old = old_root / parts[-1]
        if not old.is_dir() or old.is_symlink():
            continue
        with store_lock(root):
            destination = _item_directory(root, data) / "diagnostics" / ("legacy-" + parts[-1])
            for source in sorted(old.rglob("*.png")):
                relative = source.relative_to(old)
                if source.is_symlink() or not source.resolve().is_relative_to(old.resolve()):
                    continue
                if not relative.parts or not re.fullmatch(r"attempt-[0-9]+", relative.parts[0]):
                    continue
                raw = source.read_bytes()
                canonical = finals.get(hashlib.sha256(raw).hexdigest())
                known_intermediate = ("_raw_" in source.name or "_stage_" in source.name
                                      or relative.parts[1:] == ("refit-source", "master.png"))
                if canonical is not None:
                    target = canonical
                    # A receipt commits before retiring a proven accepted copy.
                    _atomic_json(destination / relative.with_suffix(".final.json"), {"final": str(canonical)})
                elif known_intermediate:
                    target = destination / relative
                    if not target.resolve().is_relative_to(root.resolve()):
                        raise OSError("diagnostic migration target escapes image store")
                    if target.exists() and target.read_bytes() != raw:
                        continue  # Preserve both sides of an unexpected conflict.
                    if not target.exists():
                        _atomic_bytes(target, raw)
                else:
                    continue
                if target.read_bytes() == raw and source.read_bytes() == raw:
                    source.unlink()
                    receipts.append({"from": str(source), "to": str(target)})
    return receipts
