from __future__ import annotations

"""Conservative merge helpers for conditional LLM Repair stages.

Existing generated values are frozen by default.  A repair response may:
- replace values on deterministic broken paths;
- add only exact missing fields named by deterministic repair permissions;
- create/delete nodes only when the stage scope explicitly permits it.

Attempts to rewrite already-valid values are ignored and recorded instead of
cancelling an otherwise useful repair.
"""

import copy
from typing import Any, Iterable, Mapping


MISSING = object()


def _normalize_paths(paths: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted({str(value or "").strip(".") for value in paths}))


def _path_intersects(path: str, permissions: tuple[str, ...]) -> bool:
    if "" in permissions:
        return True
    return any(
        permission == path
        or permission.startswith(path + ".")
        or path.startswith(permission + ".")
        for permission in permissions
        if permission
    )


def _leaf_allowed(path: str, permissions: tuple[str, ...]) -> bool:
    if "" in permissions:
        return True
    return any(path == permission or path.startswith(permission + ".") for permission in permissions if permission)


def _ignored_row(path: str, requested: Any, preserved: Any, reason: str) -> dict[str, Any]:
    return {
        "path": path,
        "reason": reason,
        "requested": copy.deepcopy(requested),
        "preserved": copy.deepcopy(preserved),
    }


def merge_frozen_subtree(
    original: Any,
    candidate: Any,
    *,
    mutable_paths: Iterable[Any],
    audit_path: str,
    allow_additions: bool = True,
) -> tuple[Any, list[dict[str, Any]], list[str]]:
    """Merge ``candidate`` into ``original`` without rewriting valid values.

    ``mutable_paths`` are dot-separated paths relative to the node root.  A path
    grants replacement for that leaf or whole subtree. Existing values outside
    those paths stay frozen. ``allow_additions`` exists only for callers whose
    deterministic scope explicitly permits arbitrary completion; Gameplay,
    Visual and VFX Repair pass ``False`` and accept only exact missing paths.
    """

    permissions = _normalize_paths(mutable_paths)
    ignored: list[dict[str, Any]] = []
    accepted: list[str] = []

    def visit(old: Any, new: Any, relative: str, absolute: str) -> Any:
        if old is MISSING:
            # Missing values are accepted only when the caller explicitly allows
            # arbitrary additions or when the exact missing path is in the
            # deterministic repair permission set.  This prevents a model from
            # smuggling new optional design choices into an otherwise narrow
            # repair subtree.
            if allow_additions or _leaf_allowed(relative, permissions):
                accepted.append(absolute)
                return copy.deepcopy(new)
            ignored.append(_ignored_row(absolute, new, None, "addition_not_permitted"))
            return MISSING

        if old == new:
            return copy.deepcopy(old)

        if isinstance(old, Mapping) and isinstance(new, Mapping):
            out = copy.deepcopy(dict(old))
            for key, value in new.items():
                child_rel = f"{relative}.{key}" if relative else str(key)
                child_abs = f"{absolute}.{key}"
                previous = old.get(key, MISSING)
                if previous is not MISSING and previous == value:
                    continue
                if previous is MISSING:
                    merged = visit(MISSING, value, child_rel, child_abs)
                    if merged is not MISSING:
                        out[key] = merged
                    continue
                if isinstance(previous, Mapping) and isinstance(value, Mapping):
                    # Recurse even when the parent itself is frozen: missing
                    # nested parameters may still be accepted.
                    out[key] = visit(previous, value, child_rel, child_abs)
                    continue
                if _leaf_allowed(child_rel, permissions):
                    out[key] = copy.deepcopy(value)
                    accepted.append(child_abs)
                else:
                    ignored.append(_ignored_row(child_abs, value, previous, "frozen_valid_value"))
            return out

        if _leaf_allowed(relative, permissions):
            accepted.append(absolute)
            return copy.deepcopy(new)

        # A container can have a more specific permitted descendant.  We cannot
        # safely synthesize a partial merge for incompatible container types, so
        # retain the old value and record the ignored request.
        reason = "incompatible_container_on_broken_descendant" if _path_intersects(relative, permissions) else "frozen_valid_value"
        ignored.append(_ignored_row(absolute, new, old, reason))
        return copy.deepcopy(old)

    merged = visit(original, candidate, "", audit_path)
    return merged, ignored, accepted


__all__ = ["merge_frozen_subtree"]
