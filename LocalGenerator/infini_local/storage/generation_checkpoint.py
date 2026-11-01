"""Durable accepted generation progress, separate from deliverable recipes.

The pipeline owns identity and semantic acceptance. This owner stores only its
accepted snapshots and successful image receipts, atomically merging the two
while image workers and the main pipeline run concurrently.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import threading
import time
from typing import Any, Iterator
import uuid

from infini_local.core import strict_json
from infini_local.core.item_identity_tools import safe_file_part
from infini_local.storage import world_storage


CHECKPOINT_SCHEMA = "infini.generation-checkpoint.v1"
CHECKPOINT_STAGES = frozenset({"gameplay", "visual", "vfx"})
MAX_CHECKPOINT_BYTES = 16 * 1024 * 1024
MAX_IMAGE_RECEIPTS = 128
_RECORD_FIELDS = frozenset({
    "schema", "identity", "stage", "data", "images", "savedAt", "checkpointId", "sha256",
})


def _canonical_json(value: Any) -> bytes:
    return strict_json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _record_digest(record: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json({key: value for key, value in record.items() if key != "sha256"})).hexdigest()


class GenerationCheckpoint:
    """One exact craft's last accepted stage and detached image receipts.

    Missing or rejected files provide no reusable progress. Filesystem failures
    propagate: an inaccessible checkpoint is never treated as permission to
    repeat already paid authoring. No file is created until a stage is accepted.
    The caller holds the existing per-recipe generation lock across attempts;
    this object's lock additionally serializes its concurrent image workers.
    """

    def __init__(self, world_dir: Path, recipe_key: str, identity: dict[str, Any]) -> None:
        self.path = Path(world_dir) / "drafts" / f"{safe_file_part(recipe_key, 'recipe')}.json"
        self._identity = deepcopy(identity)
        self._identity_json = _canonical_json(self._identity)
        self._lock = threading.RLock()
        self.rejection_reason: str | None = None
        self._record = self._load()

    def _reject(self, reason: str) -> None:
        # Importing this storage owner does not initialize diagnostic storage.
        from infini_local.storage.trace_runtime import log_event

        self.rejection_reason = reason
        log_event("warn", "generation checkpoint rejected: " + reason, {"path": str(self.path)})

    def _load(self) -> dict[str, Any] | None:
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(MAX_CHECKPOINT_BYTES + 1)
        except FileNotFoundError:
            return None
        if len(raw) > MAX_CHECKPOINT_BYTES:
            self._reject("file exceeds checkpoint size limit")
            return None
        try:
            record = strict_json.loads_object(raw)
            if set(record) != _RECORD_FIELDS or record.get("schema") != CHECKPOINT_SCHEMA:
                raise ValueError("unsupported checkpoint envelope")
            if not isinstance(record["identity"], dict) or _canonical_json(record["identity"]) != self._identity_json:
                raise ValueError("craft identity or contract versions changed")
            if not isinstance(record["stage"], str) or record["stage"] not in CHECKPOINT_STAGES:
                raise ValueError("unknown accepted stage")
            if not isinstance(record["data"], dict):
                raise ValueError("accepted data must be an object")
            images = record["images"]
            if (not isinstance(images, dict) or len(images) > MAX_IMAGE_RECEIPTS
                    or any(not key or not isinstance(value, dict) for key, value in images.items())):
                raise ValueError("invalid image receipt collection")
            saved_at = record["savedAt"]
            if type(saved_at) not in (int, float) or not math.isfinite(saved_at) or saved_at <= 0:
                raise ValueError("invalid checkpoint timestamp")
            checkpoint_id = record["checkpointId"]
            if (not isinstance(checkpoint_id, str) or len(checkpoint_id) != 32
                    or any(character not in "0123456789abcdef" for character in checkpoint_id)):
                raise ValueError("invalid checkpoint identity")
            if record["sha256"] != _record_digest(record):
                raise ValueError("checkpoint checksum mismatch")
        except (UnicodeError, ValueError, TypeError, OverflowError) as error:
            self._reject(str(error))
            return None
        return record

    @property
    def stage(self) -> str | None:
        with self._lock:
            return self._record["stage"] if self._record is not None else None

    @property
    def data(self) -> dict[str, Any] | None:
        with self._lock:
            return deepcopy(self._record["data"]) if self._record is not None else None

    @property
    def checkpoint_id(self) -> str | None:
        with self._lock:
            return self._record["checkpointId"] if self._record is not None else None

    @property
    def saved_at(self) -> float | None:
        with self._lock:
            return self._record["savedAt"] if self._record is not None else None

    def _commit(self, record: dict[str, Any]) -> None:
        record["savedAt"] = time.time()
        record["sha256"] = _record_digest(record)
        # Match the canonical writer's formatting so a file we publish can also
        # be read under the same bound, even with verbose accepted diagnostics.
        encoded = strict_json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        if len(encoded) + 1 > MAX_CHECKPOINT_BYTES:
            raise ValueError("generation checkpoint exceeds size limit")
        world_storage.atomic_write_json(self.path, record)
        self._record = record
        self.rejection_reason = None

    def save_stage(self, stage: str, data: dict[str, Any]) -> None:
        if not isinstance(stage, str) or stage not in CHECKPOINT_STAGES:
            raise ValueError(f"unknown generation checkpoint stage: {stage!r}")
        if not isinstance(data, dict):
            raise TypeError("accepted generation data must be an object")
        with self._lock:
            record = deepcopy(self._record) if self._record is not None else {
                "schema": CHECKPOINT_SCHEMA,
                "identity": deepcopy(self._identity),
                "checkpointId": uuid.uuid4().hex,
                "images": {},
            }
            record.update(stage=stage, data=deepcopy(data))
            self._commit(record)

    def image_get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            receipt = self._record["images"].get(key) if self._record is not None else None
            return deepcopy(receipt) if receipt is not None else None

    def image_put(self, key: str, receipt: dict[str, Any]) -> None:
        if not isinstance(key, str) or not key or not isinstance(receipt, dict):
            raise TypeError("image receipt requires a nonempty string key and object value")
        with self._lock:
            if self._record is None:
                raise ValueError("image receipt requires an accepted generation stage")
            record = deepcopy(self._record)
            images = record["images"]
            if key not in images and len(images) >= MAX_IMAGE_RECEIPTS:
                raise ValueError("generation checkpoint image receipt limit exceeded")
            images[key] = deepcopy(receipt)
            self._commit(record)

    def clear(self) -> None:
        """Remove progress after recipe commit; retain memory if deletion fails."""
        with self._lock:
            self.path.unlink(missing_ok=True)
            self._record = None
            self.rejection_reason = None


_CURRENT_CHECKPOINT: ContextVar[GenerationCheckpoint | None] = ContextVar("infini_generation_checkpoint", default=None)


@contextmanager
def use_generation_checkpoint(checkpoint: GenerationCheckpoint | None) -> Iterator[None]:
    token = _CURRENT_CHECKPOINT.set(checkpoint)
    try:
        yield
    finally:
        _CURRENT_CHECKPOINT.reset(token)


def current_generation_checkpoint() -> GenerationCheckpoint | None:
    return _CURRENT_CHECKPOINT.get()


__all__ = [
    "GenerationCheckpoint",
    "use_generation_checkpoint",
    "current_generation_checkpoint",
]
