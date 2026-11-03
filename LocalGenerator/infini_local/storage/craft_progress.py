"""Accepted text stages, private and separate from committed recipes.

The combine owner holds the recipe generation lock and revalidates restored
wire. This stores no provider sessions or image-job state and never repairs a
saved design. PNG generation continues through its existing owner.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any, Mapping

from infini_local.core import strict_json
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.item_identity_tools import safe_file_part
from infini_local.storage import world_storage
from infini_local.storage.trace_runtime import log_event, trace_event


PROGRESS_SCHEMA = "infini.craft-stages.v1"
_STAGES = ("author", "visual", "vfx")


def _digest(value: Mapping[str, Any]) -> str:
    encoded = strict_json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def progress_path(world_dir: Path, recipe_key: str) -> Path:
    # The asset endpoint recursively discovers .json beneath world roots.
    # Neither this extension nor atomic_write_json's .tmp files are served.
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
        self._record: dict[str, Any] = {
            "schema": PROGRESS_SCHEMA, "identity": _digest(identity), "stage": "", "data": None,
        }
        try:
            saved = strict_json.loads_object(self.path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            return
        except (UnicodeError, ValueError, TypeError) as exc:
            raise self.invalid("unreadable checkpoint JSON") from exc
        # Check the whole envelope before comparing identities. A damaged
        # identity/schema is not evidence that the user requested a new design.
        checksum = saved.pop("sha256", None)
        if checksum != _digest(saved):
            raise self.invalid("accepted checkpoint content changed")
        if saved.get("schema") != PROGRESS_SCHEMA:
            raise self.invalid("unsupported checkpoint schema")
        if (saved.get("stage") not in _STAGES or not isinstance(saved.get("data"), dict)
                or not isinstance(saved.get("identity"), str)):
            raise self.invalid("invalid accepted-stage envelope")
        matches = saved["identity"] == self._record["identity"]
        if not matches and swapped_identity is not None:
            self.parents_swapped = saved["identity"] == _digest(swapped_identity)
            matches = self.parents_swapped
        if not matches:
            trace_event("checkpoint", "craft_progress", "Saved craft inputs or contracts changed; starting a new design",
                        {"recipeKey": recipe_key, "path": str(self.path)})
            return
        self._record = saved

    def invalid(self, reason: str) -> PlannerUnavailable:
        return PlannerUnavailable(
            f"Saved craft progress rejected: {reason}. Preserved at {self.path}. "
            "No new design was requested. To discard it deliberately, stop the generator and remove this checkpoint file."
        )

    def restore(self) -> tuple[str, dict[str, Any] | None]:
        return str(self._record["stage"]), copy.deepcopy(self._record["data"])

    def accept(self, stage: str, data: Mapping[str, Any]) -> None:
        if stage not in _STAGES:
            raise ValueError(f"Unknown accepted craft stage: {stage}")
        record = {**self._record, "stage": stage, "data": copy.deepcopy(dict(data))}
        # Only publish the in-memory snapshot after atomic replacement succeeds.
        world_storage.atomic_write_json(self.path, {**record, "sha256": _digest(record)})
        self._record = record
