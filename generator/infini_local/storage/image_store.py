from __future__ import annotations

"""Persistent final PNGs and private attempts.

The wire carries a safe basename resolved through the shared filename index.
Only indexed final PNGs are served; diagnostics are never HTTP assets.
Index entries are committed after their immutable bytes.
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


def publish(root: Path, data: dict[str, Any], role: str, identity: bytes, source: Path) -> Path:
    from infini_local.core.asset_files import MAX_ASSET_RESPONSE_BYTES, is_complete_png_file

    if source.stat().st_size > MAX_ASSET_RESPONSE_BYTES:
        raise ValueError("final PNG exceeds the asset transfer byte limit")
    if not is_complete_png_file(source):
        raise ValueError("cannot publish an incomplete final PNG")
    raw = source.read_bytes()
    meta = data.get("recipeMeta") if isinstance(data.get("recipeMeta"), dict) else {}
    scope = json.dumps([str(meta.get("worldId") or "unscoped"), str(data.get("id") or "unscoped"), role],
                       ensure_ascii=True, separators=(",", ":")).encode("ascii")
    digest = hashlib.sha256(scope + b"\0" + identity + b"\0" + raw).hexdigest()
    label = re.sub(r"[^a-z0-9_-]+", "_", role.lower()).strip("_")[:24] or "asset"
    with store_lock(root):
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
        _register(root, destination.name, destination, raw, data, role)
    return destination.resolve()


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
    manifest = data.get("vfxManifest")
    assets = manifest.get("assets") if isinstance(manifest, dict) else None
    for asset in assets if isinstance(assets, list) else []:
        if isinstance(asset, dict):
            yield asset, "spritePath", "vfx_" + str(asset.get("id") or "")


def compact_delivery_paths(root: Path, data: dict[str, Any]) -> None:
    """Transport normalization: indexed final identity needs no machine path.

    Only paths to this store's exact canonical file become basenames, avoiding
    both Windows path limits and host path leaks.
    """
    from infini_local.core.asset_files import asset_filename_from_path
    for owner, field, _ in runtime_image_fields(data):
        value = owner.get(field)
        name = asset_filename_from_path(value)
        canonical = resolve(root, name)
        if canonical is not None and Path(str(value)).resolve() == canonical.resolve():
            owner[field] = name


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
