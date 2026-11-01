"""Durable accepted craft stages and completed image jobs, separate from recipes.

The combine owner holds the recipe generation lock and validates restored stages.
Image workers inherit the active progress through their existing copied context;
one lock joins their receipts with the main thread's accepted-stage snapshots.
No provider sessions, credentials or executable fallback designs live here.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
from pathlib import Path
import threading
from typing import Any, Mapping

from infini_local.core import strict_json
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.item_identity_tools import safe_file_part
from infini_local.storage import world_storage
from infini_local.storage.trace_runtime import log_event, trace_event


PROGRESS_SCHEMA = "infini.craft-progress.v1"
_STAGES = ("author", "visual", "vfx")
_ACTIVE_PROGRESS: ContextVar[CraftProgress | None] = ContextVar("infini_craft_progress", default=None)


def _digest(value: Mapping[str, Any]) -> str:
    encoded = strict_json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def progress_path(world_dir: Path, recipe_key: str) -> Path:
    # The asset endpoint recursively serves .json beneath world roots. Pending
    # work must have neither a recipe basename nor a publicly served extension.
    return Path(world_dir) / "checkpoints" / f"{safe_file_part(recipe_key, 'recipe')}.checkpoint"


def discard_progress(world_dir: Path, recipe_key: str) -> None:
    """A committed recipe wins even if optional checkpoint cleanup fails."""
    path = progress_path(world_dir, recipe_key)
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        log_event("warning", "Committed craft checkpoint cleanup failed", {"path": str(path), "error": str(exc)})


class CraftProgress:
    def __init__(self, world_dir: Path, recipe_key: str, identity: Mapping[str, Any], *,
                 swapped_identity: Mapping[str, Any] | None = None):
        self.path = progress_path(world_dir, recipe_key)
        self.parents_swapped = False
        self._lock = threading.RLock()
        self._record: dict[str, Any] = {
            "schema": PROGRESS_SCHEMA,
            "identity": _digest(identity),
            "stage": "",
            "data": None,
            "images": {},
        }
        try:
            saved = strict_json.loads_object(self.path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            return
        except (UnicodeError, ValueError, TypeError) as exc:
            raise self.invalid("unreadable checkpoint JSON") from exc
        # Exact parent facts, world/lane and executable contracts are supplied by
        # combine. Connection repairs and round-robin leases do not change them.
        matches = saved.get("identity") == self._record["identity"]
        if not matches and swapped_identity is not None:
            self.parents_swapped = saved.get("identity") == _digest(swapped_identity)
            matches = self.parents_swapped
        if saved.get("schema") != PROGRESS_SCHEMA or not matches:
            self.parents_swapped = False
            trace_event("checkpoint", "craft_progress", "Saved craft inputs or contracts changed; starting a new design",
                        {"recipeKey": recipe_key, "path": str(self.path)})
            return
        if (saved.get("stage") not in _STAGES or not isinstance(saved.get("data"), dict)
                or not isinstance(saved.get("images"), dict)):
            raise self.invalid("invalid accepted-stage envelope")
        if saved.get("dataSha256") != _digest(saved["data"]):
            raise self.invalid("accepted design content changed")
        self._record = saved

    def invalid(self, reason: str) -> PlannerUnavailable:
        return PlannerUnavailable(
            f"Saved craft progress rejected: {reason}. Preserved at {self.path}. "
            "No new design was requested. To discard it deliberately, stop the generator and remove this checkpoint file."
        )

    def restore(self) -> tuple[str, dict[str, Any] | None]:
        return str(self._record["stage"]), copy.deepcopy(self._record["data"])

    def _write(self, record: dict[str, Any]) -> None:
        # Publish only after the atomic write succeeds. A failed replace keeps
        # both the previous file and the previous in-memory accepted snapshot.
        world_storage.atomic_write_json(self.path, record)
        self._record = record

    def accept(self, stage: str, data: Mapping[str, Any]) -> None:
        if stage not in _STAGES:
            raise ValueError(f"Unknown accepted craft stage: {stage}")
        with self._lock:
            record = dict(self._record)
            snapshot = copy.deepcopy(dict(data))
            record.update(stage=stage, data=snapshot, dataSha256=_digest(snapshot))
            self._write(record)

    def find_image(self, identity: Mapping[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            result = self._record["images"].get(_digest(identity))
            return copy.deepcopy(result) if isinstance(result, dict) else None

    def save_image(self, identity: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        with self._lock:
            if self._record["stage"] not in ("visual", "vfx"):
                raise ValueError("Image progress requires an accepted Visual design")
            record = dict(self._record)
            record["images"] = {**self._record["images"], _digest(identity): copy.deepcopy(dict(result))}
            self._write(record)


@contextmanager
def track_progress(world_dir: Path, recipe_key: str, identity: Mapping[str, Any], *,
                   swapped_identity: Mapping[str, Any] | None = None):
    progress = CraftProgress(world_dir, recipe_key, identity, swapped_identity=swapped_identity)
    token = _ACTIVE_PROGRESS.set(progress)
    try:
        yield progress
    finally:
        _ACTIVE_PROGRESS.reset(token)


def image_progress_active() -> bool:
    return _ACTIVE_PROGRESS.get() is not None


def find_image_result(request_identity: Mapping[str, Any]) -> dict[str, Any] | None:
    progress = _ACTIVE_PROGRESS.get()
    return progress.find_image(request_identity) if progress is not None else None


def save_image_result(request_identity: Mapping[str, Any], result: Mapping[str, Any]) -> None:
    progress = _ACTIVE_PROGRESS.get()
    if progress is not None:
        progress.save_image(request_identity, result)
