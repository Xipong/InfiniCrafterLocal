"""Frozen-first Visual patch filtering and application."""

from __future__ import annotations

import copy
import json
from typing import Any, Mapping

from infini_local.core.errors import PlannerUnavailable
from infini_local.core.repair_merge import (
    json_path_child,
    json_path_relative,
    json_values_equal,
    merge_frozen_subtree,
)
from infini_local.core.schema_validation import strict_schema_errors
from infini_local.pipelines.visual.contract import (
    VISUAL_KIT_SCHEMA,
    VISUAL_REPAIR_PATCH_SCHEMA,
    _visual_entity_schema,
    _visual_equip_overlay_schema,
    _visual_item_schema,
    _visual_repair_schema,
)


def _expand_scoped_visual_repair_patch(patch: Any, previous: Any, scope: Mapping[str, Any], entity_ids: list[str]) -> Any:
    """Lossless transport completion before the unchanged frozen-first filter."""
    if not isinstance(patch, dict):
        return patch
    out = copy.deepcopy(patch)
    source = previous if isinstance(previous, Mapping) else {}
    canonical = _visual_repair_schema(entity_ids, bool(scope.get("equipmentOverlayRequired")))
    for key in canonical["required"]:
        if key not in out and key not in ("schema", "note"):
            out[key] = [] if canonical["properties"][key].get("type") == "array" else None
    # Complete only existing authored fields, never invent absent design choices.
    def complete(old: Any, new: Any) -> Any:
        if not isinstance(old, Mapping) or not isinstance(new, Mapping):
            return copy.deepcopy(new)
        return {**copy.deepcopy(dict(old)), **{key: complete(old.get(key), value) for key, value in new.items()}}
    if isinstance(out.get("itemPatch"), dict):
        original_item = source.get("item")
        out["itemPatch"] = complete(original_item, out["itemPatch"])
        if isinstance(original_item, Mapping):
            out["itemPatch"] = _drop_schema_forbidden_mutable_fields(
                original_item, out["itemPatch"],
                mutable_paths=tuple((scope.get("fieldPermissions") or {}).get("itemPaths") or []),
                schema=_visual_item_schema(), audit_path="", accepted=[])
    if isinstance(out.get("equipOverlayPatch"), dict):
        out["equipOverlayPatch"] = complete(source.get("equipOverlay"), out["equipOverlayPatch"])
    by_id = {}
    raw_rows = source.get("entities")
    source_rows = raw_rows if isinstance(raw_rows, list) else []
    for row in source_rows:
        if isinstance(row, Mapping) and isinstance(row.get("entityId"), str):
            by_id.setdefault(row["entityId"], row)
    for index, row in enumerate(out.get("entitiesUpsert") or []):
        if isinstance(row, Mapping):
            merged = complete(by_id.get(row.get("entityId")), row)
            # Invalid extra source keys are removed by the existing exact-scope
            # structural-deletion filter, not advertised as output grammar.
            permitted = next((entry["paths"] for entry in (scope.get("fieldPermissions") or {}).get("entities") or [] if entry["entityId"] == row.get("entityId")), [])
            merged = _drop_schema_forbidden_mutable_fields(by_id.get(row.get("entityId"), {}), merged,
                mutable_paths=tuple(permitted), schema=_visual_entity_schema(entity_ids), audit_path="", accepted=[])
            out["entitiesUpsert"][index] = merged
    return out


def _visual_filter_ignored(path: str, requested: Any, preserved: Any, reason: str) -> dict[str, Any]:
    return {"path": path, "reason": reason, "requested": copy.deepcopy(requested), "preserved": copy.deepcopy(preserved)}


def _drop_schema_forbidden_mutable_fields(
    source: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    mutable_paths: tuple[str, ...],
    schema: Mapping[str, Any],
    audit_path: str,
    accepted: list[str],
) -> dict[str, Any]:
    """Delete only exact mutable fields forbidden by the strict row schema."""

    out: dict[str, Any] = copy.deepcopy(dict(candidate))
    branches = [row for row in schema.get("oneOf") or [] if isinstance(row, Mapping)]
    if branches:
        # Select only a unique exact literal discriminator branch. Never use the
        # union of fields or a smallest-error guess to authorize deletion.
        selected = []
        for branch in branches:
            constants = {field: spec["const"] for field, spec in (branch.get("properties") or {}).items()
                         if isinstance(spec, Mapping) and "const" in spec}
            # candidate has already passed frozen merge; only permitted repairs
            # can change its discriminator. Select that effective branch, not
            # the source branch whose dependent fields may now be inapplicable.
            if constants and all(field in out and type(out[field]) is type(value) and out[field] == value
                                 for field, value in constants.items()):
                selected.append(branch)
        if len(selected) != 1:
            return out
        schema = selected[0]
    strict_shapes = [schema]
    if not strict_shapes or any(row.get("additionalProperties") is not False for row in strict_shapes):
        return out
    valid_fields = {
        str(field)
        for row in strict_shapes
        for field in (row.get("properties") or {})
    }
    forbidden_fields = {
        str(field) for field in source
        if field not in valid_fields
        and json_path_child("", str(field)) in mutable_paths
    }
    for field in sorted(forbidden_fields):
        if field in source and field in out:
            out.pop(field, None)
            accepted.append(json_path_child(audit_path, field))
    # Nested strict objects (the atomic grip) still repair exact leaves: an extra
    # child key must be removable without granting either valid coordinate.
    for field, child_schema in (schema.get("properties") or {}).items():
        child_paths = tuple(relative for path in mutable_paths
                            if (relative := json_path_relative(path, json_path_child("", field))))
        if child_paths and isinstance(source.get(field), Mapping) and isinstance(out.get(field), Mapping):
            out[field] = _drop_schema_forbidden_mutable_fields(
                source[field], out[field], mutable_paths=child_paths, schema=child_schema,
                audit_path=json_path_child(audit_path, field), accepted=accepted,
            )
    return out


def _filter_visual_repair_patch(
    previous: Any,
    patch: Mapping[str, Any],
    scope: Mapping[str, Any],
    entity_ids: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    equipment_overlay_required = bool(scope.get("equipmentOverlayRequired"))
    # Advisory prose is not a Repair edit target or a structural requirement.
    # Ignore any echoed advisory value before checking executable patch shape.
    patch = {key: value for key, value in patch.items() if key != "animationPlan"}
    schema_errors = strict_schema_errors(patch, _visual_repair_schema(entity_ids, equipment_overlay_required))
    filtered = {
        "schema": VISUAL_REPAIR_PATCH_SCHEMA,
        "itemPatch": None,
        "entitiesUpsert": [],
        "entityIdsDelete": [],
        "entityIndicesDelete": [],
        "note": str(patch.get("note") or "deterministically filtered Visual Repair"),
    }
    if equipment_overlay_required:
        filtered["equipOverlayPatch"] = None
    if schema_errors:
        return filtered, {"schema": "infini.visual-repair-filter-report.v1", "ok": False, "errors": schema_errors, "acceptedPaths": [], "ignoredChanges": []}

    source = previous if isinstance(previous, Mapping) else {}
    mutable_ids = set(str(value) for value in scope.get("mutableEntityIds") or [])
    deletable_ids = set(str(value) for value in scope.get("deletableEntityIds") or [])
    deletable_indices = set(int(value) for value in scope.get("deletableEntityIndices") or [])
    raw_permissions = scope.get("fieldPermissions")
    permission_root: Mapping[str, Any] = raw_permissions if isinstance(raw_permissions, Mapping) else {}
    item_paths = tuple(str(value) for value in permission_root.get("itemPaths") or [])
    overlay_paths = tuple(str(value) for value in permission_root.get("equipOverlayPaths") or [])
    entity_permissions = {
        str(row.get("entityId") or ""): tuple(str(value) for value in row.get("paths") or [])
        for row in permission_root.get("entities") or [] if isinstance(row, Mapping)
    }
    ignored: list[dict[str, Any]] = []
    accepted: list[str] = []

    item_patch = patch.get("itemPatch")
    if item_patch is not None:
        original_item = source.get("item")
        if not scope.get("itemMutable"):
            ignored.append(_visual_filter_ignored("$.itemPatch", item_patch, original_item, "valid_item_block_frozen"))
        elif isinstance(original_item, Mapping):
            merged, row_ignored, row_accepted = merge_frozen_subtree(
                original_item, item_patch, mutable_paths=item_paths, audit_path="$.itemPatch", allow_additions=False,
            )
            filtered["itemPatch"] = merged
            ignored.extend(row_ignored)
            accepted.extend(row_accepted)
        else:
            filtered["itemPatch"] = copy.deepcopy(item_patch)
            accepted.append("$.itemPatch")

    # Strict Repair rows cannot repeat a schema-forbidden source field. Its
    # exact diagnostic path authorizes structural deletion instead of preserving
    # the invalid key through frozen merge.
    original_item = source.get("item")
    if scope.get("itemMutable") and isinstance(original_item, Mapping):
        candidate_item = filtered.get("itemPatch")
        repair_source: Mapping[str, Any] = candidate_item if isinstance(candidate_item, Mapping) else original_item
        filtered["itemPatch"] = _drop_schema_forbidden_mutable_fields(
            original_item,
            repair_source,
            mutable_paths=item_paths,
            schema=_visual_item_schema(),
            audit_path="$.itemPatch",
            accepted=accepted,
        )

    if equipment_overlay_required:
        overlay_patch = patch.get("equipOverlayPatch")
        original_overlay = source.get("equipOverlay")
        if overlay_patch is not None:
            if not scope.get("equipOverlayMutable"):
                ignored.append(_visual_filter_ignored("$.equipOverlayPatch", overlay_patch, original_overlay, "valid_equip_overlay_block_frozen"))
            elif isinstance(original_overlay, Mapping):
                merged, row_ignored, row_accepted = merge_frozen_subtree(
                    original_overlay,
                    overlay_patch,
                    mutable_paths=overlay_paths,
                    audit_path="$.equipOverlayPatch",
                    allow_additions=False,
                )
                filtered["equipOverlayPatch"] = merged
                ignored.extend(row_ignored)
                accepted.extend(row_accepted)
            else:
                filtered["equipOverlayPatch"] = copy.deepcopy(overlay_patch)
                accepted.append("$.equipOverlayPatch")
        if scope.get("equipOverlayMutable") and isinstance(original_overlay, Mapping):
            candidate_overlay = filtered.get("equipOverlayPatch")
            repair_overlay: Mapping[str, Any] = candidate_overlay if isinstance(candidate_overlay, Mapping) else original_overlay
            filtered["equipOverlayPatch"] = _drop_schema_forbidden_mutable_fields(
                original_overlay,
                repair_overlay,
                mutable_paths=overlay_paths,
                schema=_visual_equip_overlay_schema(),
                audit_path="$.equipOverlayPatch",
                accepted=accepted,
            )

    for index, entity_id in enumerate(patch.get("entityIdsDelete") or []):
        path = f"$.entityIdsDelete[{index}]"
        if str(entity_id) in deletable_ids:
            filtered["entityIdsDelete"].append(str(entity_id))
            accepted.append(path)
        else:
            ignored.append(_visual_filter_ignored(path, entity_id, entity_id, "valid_entity_delete_ignored"))
    rows_raw = source.get("entities")
    rows = rows_raw if isinstance(rows_raw, list) else []
    for index, source_index in enumerate(patch.get("entityIndicesDelete") or []):
        path = f"$.entityIndicesDelete[{index}]"
        numeric = int(source_index)
        if numeric in deletable_indices:
            filtered["entityIndicesDelete"].append(numeric)
            accepted.append(path)
        else:
            preserved = rows[numeric] if 0 <= numeric < len(rows) else None
            ignored.append(_visual_filter_ignored(path, numeric, preserved, "valid_entity_index_delete_ignored"))

    by_id: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if isinstance(row, Mapping) and str(row.get("entityId") or ""):
            by_id.setdefault(str(row["entityId"]), row)
    replacement_indices: dict[str, int] = {}
    for transaction in scope.get("entityReplacementTransactions") or []:
        if not isinstance(transaction, Mapping):
            continue
        entity_id = str(transaction.get("entityId") or "")
        replace_index = transaction.get("replaceIndex")
        if entity_id and isinstance(replace_index, int) and not isinstance(replace_index, bool):
            replacement_indices[entity_id] = replace_index
    for index, candidate in enumerate(patch.get("entitiesUpsert") or []):
        entity_id = str(candidate.get("entityId") or "")
        path = f"$.entitiesUpsert[{index}]"
        original = by_id.get(entity_id)
        if entity_id not in mutable_ids:
            if original is None or not json_values_equal(dict(candidate), dict(original)):
                ignored.append(_visual_filter_ignored(path, candidate, original, "independent_valid_entity_frozen"))
            continue
        if original is None:
            filtered["entitiesUpsert"].append(copy.deepcopy(candidate))
            accepted.append(path)
            replace_index = replacement_indices.get(entity_id)
            if replace_index is not None and replace_index in deletable_indices:
                if replace_index not in filtered["entityIndicesDelete"]:
                    filtered["entityIndicesDelete"].append(replace_index)
                accepted.append(f"$.entityReplacementTransactions[{entity_id}]")
            continue
        permissions = entity_permissions.get(entity_id, ())
        merged, row_ignored, row_accepted = merge_frozen_subtree(
            original, candidate, mutable_paths=permissions, audit_path=path, allow_additions=False,
        )
        ignored.extend(row_ignored)
        accepted.extend(row_accepted)
        merged = _drop_schema_forbidden_mutable_fields(
            original,
            merged,
            mutable_paths=permissions,
            schema=_visual_entity_schema(entity_ids),
            audit_path=path,
            accepted=accepted,
        )
        if not json_values_equal(merged, original):
            filtered["entitiesUpsert"].append(merged)

    filtered["entityIndicesDelete"] = sorted(set(filtered["entityIndicesDelete"]))
    return filtered, {
        "schema": "infini.visual-repair-filter-report.v1",
        "ok": True,
        "errors": [],
        "acceptedPaths": sorted(set(accepted)),
        "ignoredChanges": ignored,
        "filteredPatch": copy.deepcopy(filtered),
    }


def _apply_visual_repair_patch(
    previous: Any,
    patch: Mapping[str, Any],
    scope: Mapping[str, Any],
    entity_ids: list[str],
    *,
    return_audit: bool = False,
) -> Any:
    filtered, audit = _filter_visual_repair_patch(previous, patch, scope, entity_ids)
    if not audit.get("ok"):
        raise PlannerUnavailable("Visual Repair patch shape rejected: " + json.dumps(audit.get("errors", [])[:16], ensure_ascii=False))

    out = copy.deepcopy(dict(previous)) if isinstance(previous, Mapping) else {}
    out["schema"] = VISUAL_KIT_SCHEMA
    if filtered.get("itemPatch") is not None:
        out["item"] = copy.deepcopy(filtered["itemPatch"])
    if filtered.get("equipOverlayPatch") is not None:
        out["equipOverlay"] = copy.deepcopy(filtered["equipOverlayPatch"])
    rows = list(out.get("entities") or []) if isinstance(out.get("entities"), list) else []
    rows = [row for index, row in enumerate(rows) if index not in set(filtered.get("entityIndicesDelete") or [])]
    doomed = set(str(value) for value in filtered.get("entityIdsDelete") or [])
    rows = [row for row in rows if not isinstance(row, Mapping) or str(row.get("entityId") or "") not in doomed]
    original_indices: dict[str, int] = {}
    for index, row in enumerate(rows):
        if isinstance(row, Mapping) and str(row.get("entityId") or ""):
            original_indices.setdefault(str(row["entityId"]), index)
    for row in filtered.get("entitiesUpsert") or []:
        entity_id = str(row.get("entityId") or "")
        index = original_indices.get(entity_id)
        if index is None:
            original_indices[entity_id] = len(rows)
            rows.append(copy.deepcopy(row))
        else:
            rows[index] = copy.deepcopy(row)
    # Keep every other original slot, including undeleted malformed/duplicate
    # rows. An ID-keyed upsert repairs only its first surviving occurrence.
    out["entities"] = rows
    return (out, audit) if return_audit else out
