"""Exact leaf-local VFX Repair scopes, grammar projection and frozen merge."""
from __future__ import annotations

import copy
import json
import re
from typing import Any, Mapping

from infini_local.core.errors import PlannerUnavailable
from infini_local.core.repair_merge import (
    json_path_child,
    json_path_relative,
    json_values_equal,
    merge_frozen_subtree,
)
from infini_local.core.schema_validation import strict_schema_errors
from infini_local.core.vfx.contract import (
    VFX_DIRECTOR_SCHEMA,
    VFX_REPAIR_PATCH_SCHEMA,
    MalformedVfxDirectorOutput,
    _rows,
)
from infini_local.core.vfx.materials import ASSET_ID_PATTERN
from infini_local.core.vfx.schema import _director_schema


def vfx_repair_schema(data: Mapping[str, Any]) -> dict[str, Any]:
    return _vfx_repair_schema_from_packet({"outputSchema": _director_schema(data)})


def _build_vfx_repair_scope(raw: Any, errors: list[dict[str, Any]]) -> dict[str, Any]:
    source = raw if isinstance(raw, Mapping) else {}
    slots = _rows(source, "slots")
    mutable_slot_ids: set[str] = set()
    slot_paths: dict[str, set[str]] = {}
    slot_deletions: dict[str, set[str]] = {}
    delete_indices: set[int] = set()
    assets = _rows(source, "assets")
    asset_paths: dict[str, set[str]] = {}
    asset_deletions: dict[str, set[str]] = {}
    duplicate_asset_indices = {
        int(match.group(1)) for error in errors
        if "duplicate asset id" in str(error.get("message") or "")
        and (match := re.match(r"^\$\.assets\[(\d+)\]\.id$", str(error.get("path") or "")))
    }
    delete_asset_ids: set[str] = set()
    delete_asset_indices: set[int] = set()
    allow_create_assets = not isinstance(raw, Mapping)
    allow_create_slots = not isinstance(raw, Mapping)
    whole_response = not isinstance(raw, Mapping)

    def grant_slot(slot_id: str, relative: str) -> None:
        if slot_id:
            mutable_slot_ids.add(slot_id)
            slot_paths.setdefault(slot_id, set()).add(relative.strip("."))

    for error in errors:
        path = str(error.get("path") or "$")
        message = str(error.get("message") or "")
        exact_delete = message.startswith("schema additional_property:") or message == "schema enum: expected []"
        if path == "$":
            whole_response = True
        match = re.match(r"^\$\.slots\[(\d+)\]", path)
        relative = json_path_relative(path, match.group(0)) if match else None
        if match and relative is not None:
            index = int(match.group(1))
            if 0 <= index < len(slots) and isinstance(slots[index], Mapping):
                slot_id = str(slots[index].get("id") or "")
                if slot_id:
                    if relative:
                        grant_slot(slot_id, relative)
                        if exact_delete:
                            slot_deletions.setdefault(slot_id, set()).add(relative)
                    elif "entity/event pair" in message:
                        # Root-level semantic error, but only the exact pair is
                        # broken. Keep timing, style and already-valid cue data
                        # frozen while allowing the model to retarget the slot.
                        grant_slot(slot_id, "entityId")
                        grant_slot(slot_id, "event")
                    else:
                        grant_slot(slot_id, "")
                else:
                    delete_indices.add(index)
                    allow_create_slots = True
            else:
                delete_indices.add(index)
                allow_create_slots = True
        if path == "$.slots":
            if "array required" in message or "missing" in message:
                allow_create_slots = True
            if "at most" in message:
                for index, row in enumerate(slots):
                    if isinstance(row, Mapping) and str(row.get("id") or ""):
                        grant_slot(str(row.get("id") or ""), "")
                    else:
                        delete_indices.add(index)
        asset_match = re.match(r"^\$\.assets\[(\d+)\]", path)
        relative = json_path_relative(path, asset_match.group(0)) if asset_match else None
        if asset_match and relative is not None:
            index = int(asset_match.group(1))
            row = assets[index] if 0 <= index < len(assets) else None
            asset_id = row.get("id") if isinstance(row, Mapping) else None
            if index in duplicate_asset_indices:
                delete_asset_indices.add(index)
            elif "unused new asset request" in message and isinstance(asset_id, str):
                delete_asset_ids.add(asset_id)
            elif isinstance(asset_id, str) and re.fullmatch(ASSET_ID_PATTERN, asset_id) is not None:
                asset_paths.setdefault(asset_id, set()).add(relative)
                if exact_delete:
                    asset_deletions.setdefault(asset_id, set()).add(relative)
            else:
                delete_asset_indices.add(index)
        if path == "$.assets":
            if not isinstance(source.get("assets"), list):
                allow_create_assets = True
            elif len(assets) > 16:
                delete_asset_indices.update(range(16, len(assets)))
    if whole_response:
        allow_create_slots = True
        allow_create_assets = True
        for index, row in enumerate(assets):
            asset_id = row.get("id") if isinstance(row, Mapping) else None
            if isinstance(asset_id, str) and re.fullmatch(ASSET_ID_PATTERN, asset_id) is not None:
                asset_paths.setdefault(asset_id, set()).add("")
            else:
                delete_asset_indices.add(index)
        for index, row in enumerate(slots):
            if isinstance(row, Mapping) and str(row.get("id") or ""):
                grant_slot(str(row.get("id") or ""), "")
            else:
                delete_indices.add(index)
    return {
        "schema": "infini.vfx-repair-scope.v3",
        "mutableGlobals": [],
        "mutableSlotIds": sorted(mutable_slot_ids),
        "deletableSlotIds": sorted(slot_id for slot_id in mutable_slot_ids if "" in slot_paths[slot_id]),
        "deletableSlotIndices": sorted(delete_indices),
        "allowCreateSlots": allow_create_slots,
        "mutableAssetIds": sorted(asset_paths),
        "deletableAssetIds": sorted(delete_asset_ids),
        "deletableAssetIndices": sorted(delete_asset_indices),
        "allowCreateAssets": allow_create_assets,
        "fieldPermissions": {
            "globals": {},
            "slots": [{"slotId": slot_id, "paths": sorted(paths), **({"deletePaths": sorted(slot_deletions[slot_id])} if slot_id in slot_deletions else {})} for slot_id, paths in sorted(slot_paths.items())],
            "assets": [{"assetId": asset_id, "paths": sorted(paths), **({"deletePaths": sorted(asset_deletions[asset_id])} if asset_id in asset_deletions else {})} for asset_id, paths in sorted(asset_paths.items())],
        },
        "errorPaths": [str(row.get("path") or "$") for row in errors],
    }


def _vfx_repair_context(raw: Any, scope: Mapping[str, Any]) -> dict[str, Any]:
    source = raw if isinstance(raw, Mapping) else {}
    mutable_slot_ids = set(str(value) for value in scope.get("mutableSlotIds") or [])
    slots = _rows(source, "slots")
    mutable_asset_ids = set(scope.get("mutableAssetIds") or [])
    assets = _rows(source, "assets")
    return {
        # This is Repair's design source, not a bounded diagnostic preview.
        "malformedRawText": raw.raw_text if isinstance(raw, MalformedVfxDirectorOutput) else "",
        "broken": {
            "globals": {},
            "slots": [copy.deepcopy(row) for row in slots if isinstance(row, Mapping) and str(row.get("id") or "") in mutable_slot_ids],
            "assets": [copy.deepcopy(row) for row in assets if isinstance(row, Mapping) and isinstance(row.get("id"), str) and row["id"] in mutable_asset_ids],
        },
        "validReadOnly": {
            "globals": {},
            "slots": [copy.deepcopy(row) for row in slots if isinstance(row, Mapping) and str(row.get("id") or "") not in mutable_slot_ids],
            "assets": [copy.deepcopy(row) for row in assets if isinstance(row, Mapping) and isinstance(row.get("id"), str) and row["id"] not in mutable_asset_ids],
        },
    }


def _vfx_filter_ignored(path: str, requested: Any, preserved: Any, reason: str) -> dict[str, Any]:
    return {"path": path, "reason": reason, "requested": copy.deepcopy(requested), "preserved": copy.deepcopy(preserved)}


def _vfx_repair_structure(schema: Mapping[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(dict(schema))
    out.pop("allOf", None)
    # A typed attempt to rewrite an already-valid numeric leaf must reach the
    # frozen merge even when its requested value exceeds the semantic bounds.
    # Types, declared keys and required object shape stay checked here; bounds
    # and cross-field relations are enforced on the resulting merged manifest.
    for key in ("minimum", "maximum", "multipleOf"):
        out.pop(key, None)
    if isinstance(out.get("properties"), dict):
        out["properties"] = {name: _vfx_repair_structure(child) for name, child in out["properties"].items()}
    if isinstance(out.get("items"), Mapping):
        out["items"] = _vfx_repair_structure(out["items"])
    for union in ("anyOf", "oneOf"):
        if isinstance(out.get(union), list):
            out[union] = [_vfx_repair_structure(branch) for branch in out[union]]
    return out


def _filter_vfx_repair_patch(
    data: Mapping[str, Any],
    previous: Any,
    patch: Any,
    scope: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    from infini_local.core.schema_validation import strict_schema_errors

    shape_schema = vfx_repair_schema(data)
    # Renderer compatibility applies to the merged slot. Before frozen-first
    # filtering, an unrelated rewrite may contradict a valid frozen companion;
    # it must be ignored, not cancel an otherwise useful repair. Keep structural
    # validation here and the full renderer/schema gate after the merge.
    shape_schema["properties"]["slotsUpsert"]["items"] = _vfx_repair_structure(shape_schema["properties"]["slotsUpsert"]["items"])
    schema_errors = strict_schema_errors(patch, shape_schema)
    patch_mapping: Mapping[str, Any] = patch if isinstance(patch, Mapping) else {}
    if isinstance(patch, MalformedVfxDirectorOutput):
        schema_errors.insert(0, {
            "path": "$",
            "kind": "malformed_json",
            "expected": "strict VFX Repair JSON object",
            "actual": patch.error,
        })
    filtered: dict[str, Any] = {
        "schema": VFX_REPAIR_PATCH_SCHEMA,
        "slotsUpsert": [],
        "slotIdsDelete": [],
        "slotIndicesDelete": [],
        "assetsUpsert": [],
        "assetIdsDelete": [],
        "assetIndicesDelete": [],
        "note": str(patch_mapping.get("note") or "deterministically filtered VFX Repair"),
    }
    if schema_errors:
        return filtered, {"schema": "infini.vfx-repair-filter-report.v1", "ok": False, "errors": schema_errors, "acceptedPaths": [], "ignoredChanges": []}

    source = previous if isinstance(previous, Mapping) else {}
    mutable_slot_ids = set(str(value) for value in scope.get("mutableSlotIds") or [])
    deletable_slot_ids = set(str(value) for value in scope.get("deletableSlotIds") or [])
    deletable_indices = set(int(value) for value in scope.get("deletableSlotIndices") or [])
    raw_permission_root = scope.get("fieldPermissions")
    permission_root = raw_permission_root if isinstance(raw_permission_root, Mapping) else {}
    slot_permissions = {
        str(row.get("slotId") or ""): tuple(str(value) for value in row.get("paths") or [])
        for row in permission_root.get("slots") or [] if isinstance(row, Mapping)
    }
    slot_delete_permissions = {str(row.get("slotId") or ""): tuple(row.get("deletePaths") or []) for row in permission_root.get("slots") or [] if isinstance(row, Mapping)}
    ignored: list[dict[str, Any]] = []
    accepted: list[str] = []

    slots = _rows(source, "slots")
    for index, slot_id in enumerate(patch_mapping.get("slotIdsDelete") or []):
        path = f"$.slotIdsDelete[{index}]"
        if str(slot_id) in deletable_slot_ids:
            filtered["slotIdsDelete"].append(str(slot_id))
            accepted.append(path)
        else:
            ignored.append(_vfx_filter_ignored(path, slot_id, slot_id, "valid_slot_delete_ignored"))
    for index, source_index in enumerate(patch_mapping.get("slotIndicesDelete") or []):
        path = f"$.slotIndicesDelete[{index}]"
        numeric = int(source_index)
        if numeric in deletable_indices:
            filtered["slotIndicesDelete"].append(numeric)
            accepted.append(path)
        else:
            preserved = slots[numeric] if 0 <= numeric < len(slots) else None
            ignored.append(_vfx_filter_ignored(path, numeric, preserved, "valid_slot_index_delete_ignored"))

    by_id = {str(row.get("id") or ""): row for row in slots if isinstance(row, Mapping) and str(row.get("id") or "")}
    for index, candidate in enumerate(patch_mapping.get("slotsUpsert") or []):
        slot_id = str(candidate.get("id") or "")
        path = f"$.slotsUpsert[{index}]"
        original = by_id.get(slot_id)
        if original is not None:
            if slot_id not in mutable_slot_ids:
                if not json_values_equal(dict(candidate), dict(original)):
                    ignored.append(_vfx_filter_ignored(path, candidate, original, "independent_valid_slot_frozen"))
                continue
            merged, row_ignored, row_accepted = merge_frozen_subtree(
                original, candidate, mutable_paths=slot_permissions.get(slot_id, ()), audit_path=path, allow_additions=False,
                delete_paths=slot_delete_permissions.get(slot_id, ()), array_leaves=True,
            )
            ignored.extend(row_ignored)
            accepted.extend(row_accepted)
            if not json_values_equal(merged, original):
                filtered["slotsUpsert"].append(merged)
            continue
        if scope.get("allowCreateSlots"):
            filtered["slotsUpsert"].append(copy.deepcopy(candidate))
            accepted.append(path)
        else:
            ignored.append(_vfx_filter_ignored(path, candidate, None, "new_slot_not_required"))

    asset_permissions = {
        row["assetId"]: tuple(row.get("paths") or [])
        for row in permission_root.get("assets") or [] if isinstance(row, Mapping)
    }
    asset_delete_permissions = {row["assetId"]: tuple(row.get("deletePaths") or []) for row in permission_root.get("assets") or [] if isinstance(row, Mapping)}
    raw_assets = source.get("assets")
    assets = raw_assets if isinstance(raw_assets, list) else []
    # First occurrence owns ID-based leaf edits; later duplicates are index-only deletions.
    asset_by_id = {row["id"]: row for row in reversed(assets) if isinstance(row, Mapping) and isinstance(row.get("id"), str)}
    if "assets" in source and not isinstance(raw_assets, list) and scope.get("allowCreateAssets") and "assetsUpsert" in patch_mapping:
        accepted.append("$.assets")  # Explicit empty correction, never omission/default insertion.
    for index, asset_id in enumerate(patch_mapping.get("assetIdsDelete") or []):
        path = f"$.assetIdsDelete[{index}]"
        if asset_id in (scope.get("deletableAssetIds") or []):
            filtered["assetIdsDelete"].append(asset_id)
            accepted.append(path)
        else:
            ignored.append(_vfx_filter_ignored(path, asset_id, asset_id, "valid_asset_delete_ignored"))
    for index, source_index in enumerate(patch_mapping.get("assetIndicesDelete") or []):
        path = f"$.assetIndicesDelete[{index}]"
        if source_index in (scope.get("deletableAssetIndices") or []):
            filtered["assetIndicesDelete"].append(source_index)
            accepted.append(path)
        else:
            ignored.append(_vfx_filter_ignored(path, source_index, assets[source_index] if source_index < len(assets) else None, "valid_asset_index_delete_ignored"))
    for index, candidate in enumerate(patch_mapping.get("assetsUpsert") or []):
        asset_id = candidate["id"]
        path = f"$.assetsUpsert[{index}]"
        original = asset_by_id.get(asset_id)
        if original is not None:
            if asset_id not in asset_permissions:
                if not json_values_equal(candidate, original):
                    ignored.append(_vfx_filter_ignored(path, candidate, original, "independent_valid_asset_frozen"))
                continue
            permissions = asset_permissions[asset_id]
            merged, row_ignored, row_accepted = merge_frozen_subtree(original, candidate, mutable_paths=permissions, audit_path=path, allow_additions=False, delete_paths=asset_delete_permissions.get(asset_id, ()))
            ignored.extend(row_ignored)
            accepted.extend(row_accepted)
            if not json_values_equal(merged, original):
                filtered["assetsUpsert"].append(merged)
        elif scope.get("allowCreateAssets"):
            filtered["assetsUpsert"].append(copy.deepcopy(candidate))
            accepted.append(path)
        else:
            ignored.append(_vfx_filter_ignored(path, candidate, None, "new_asset_not_required"))
    return filtered, {
        "schema": "infini.vfx-repair-filter-report.v1",
        "ok": True,
        "errors": [],
        "acceptedPaths": sorted(set(accepted)),
        "ignoredChanges": ignored,
        "filteredPatch": copy.deepcopy(filtered),
    }


def _apply_vfx_repair_patch(
    data: Mapping[str, Any],
    previous: Any,
    patch: Any,
    scope: Mapping[str, Any],
    *,
    return_audit: bool = False,
) -> Any:
    filtered, audit = _filter_vfx_repair_patch(data, previous, patch, scope)
    if not audit.get("ok"):
        raise PlannerUnavailable("VFX Repair patch shape rejected: " + json.dumps(audit.get("errors", [])[:16], ensure_ascii=False))

    source = previous if isinstance(previous, Mapping) else {}
    out = copy.deepcopy(dict(source))
    out["schema"] = VFX_DIRECTOR_SCHEMA
    if any(filtered.get(key) for key in ("slotsUpsert", "slotIdsDelete", "slotIndicesDelete")):
        slots = _rows(out, "slots")
        doomed_indices = set(filtered["slotIndicesDelete"])
        doomed_ids = set(filtered["slotIdsDelete"])
        slots = [row for index, row in enumerate(slots) if index not in doomed_indices
                 and not (isinstance(row, Mapping) and str(row.get("id") or "") in doomed_ids)]
        # Keep every untouched row (including invalid/idless rows) in its original
        # position. Omission/empty edits are no-ops, never implicit normalization.
        for row in filtered["slotsUpsert"]:
            slot_id = str(row.get("id") or "")
            index = next((i for i, old in enumerate(slots)
                          if isinstance(old, Mapping) and str(old.get("id") or "") == slot_id), None)
            if index is None:
                slots.append(copy.deepcopy(row))
            else:
                slots[index] = copy.deepcopy(row)
        out["slots"] = slots
    if any(filtered.get(key) for key in ("assetsUpsert", "assetIdsDelete", "assetIndicesDelete")) or "$.assets" in audit["acceptedPaths"]:
        raw_assets = out.get("assets")
        assets = raw_assets if isinstance(raw_assets, list) else []
        doomed_ids = set(filtered["assetIdsDelete"])
        doomed_indices = set(filtered["assetIndicesDelete"])
        assets = [row for index, row in enumerate(assets) if index not in doomed_indices and not (isinstance(row, Mapping) and isinstance(row.get("id"), str) and row["id"] in doomed_ids)]
        for row in filtered["assetsUpsert"]:
            index = next((i for i, old in enumerate(assets) if isinstance(old, Mapping) and old.get("id") == row["id"]), None)
            if index is None:
                assets.append(copy.deepcopy(row))
            else:
                assets[index] = copy.deepcopy(row)
        out["assets"] = assets
    return (out, audit) if return_audit else out


def _vfx_scoped_repair_vocabulary(vocabulary: Mapping[str, Any], previous: Any, scope: Mapping[str, Any]) -> dict[str, Any]:
    permissions = scope.get("fieldPermissions") or {}
    rows = permissions.get("slots") or []
    paths = [path for row in rows for path in row.get("paths") or []]
    roots = {path.split(".", 1)[0] for path in paths}
    if (not isinstance(previous, Mapping) or not rows or "" in roots or "rendererKind" in roots
            or scope.get("allowCreateSlots") or scope.get("allowCreateAssets")
            or permissions.get("assets") or "$" in (scope.get("errorPaths") or [])):
        return copy.deepcopy(dict(vocabulary))
    selected_ids = {row.get("slotId") for row in rows}
    renderers = {row.get("rendererKind") for row in _rows(previous, "slots")
                 if isinstance(row, Mapping) and row.get("id") in selected_ids and isinstance(row.get("rendererKind"), str)}
    selected = {key: copy.deepcopy(value) for key, value in vocabulary.items() if key in roots}
    selected["numericRanges"] = {key: copy.deepcopy(value) for key, value in vocabulary.get("numericRanges", {}).items() if key in roots}
    selected["rendererSemantics"] = {key: copy.deepcopy(value) for key, value in vocabulary.get("rendererSemantics", {}).items() if key in renderers}
    # These nested owners contain selectors and semantic relations not expressed
    # by their root name alone. Keep their canonical read-only dependency facts.
    if roots & {"textureRole", "element", "path", "geometry", "entityId", "event"}:
        selected["textureDependencyTuples"] = copy.deepcopy(vocabulary.get("textureDependencyTuples") or {})
    if "color" in roots:
        selected["colorPolicy"] = copy.deepcopy(vocabulary.get("colorPolicy"))
    return selected


def _vfx_frozen_literal_schema(value: Any) -> dict[str, Any]:
    """Type exact source literals without changing the public VFX contract."""
    literal = {"const": copy.deepcopy(value)}
    if isinstance(value, Mapping):
        return {"type": "object", **literal, "additionalProperties": False,
                "properties": {name: _vfx_frozen_literal_schema(child) for name, child in value.items()},
                "required": list(value)}
    if isinstance(value, list):
        alternatives = [_vfx_frozen_literal_schema(child) for child in value]
        return {"type": "array", **literal, "minItems": len(value), "maxItems": len(value),
                "items": ({"anyOf": alternatives} if alternatives else {"type": "null"})}
    kind = ("null" if value is None else "boolean" if isinstance(value, bool)
            else "integer" if isinstance(value, int) else "number" if isinstance(value, float) else "string")
    return {"type": kind, **literal}


def _vfx_repair_row_schema(schema: Mapping[str, Any], old: Mapping[str, Any], paths: list[str], delete_paths: list[str]) -> dict[str, Any]:
    """Retain canonical editable leaves; frozen companions are exact source facts."""
    if "" in paths or {path.split(".", 1)[0] for path in paths} & {"rendererKind", "entityId", "event"}:
        # Discriminator/binding edits can select another real renderer/event
        # relation. Leave that row's canonical dependency domain intact; the
        # unchanged frozen merge remains the authority on companion edits.
        return copy.deepcopy(dict(schema))
    out = copy.deepcopy(dict(schema))
    properties = schema.get("properties") or {}
    selected: dict[str, Any] = {}
    for name, child in properties.items():
        child_path = json_path_child("", name)
        if child_path in delete_paths:
            continue
        relative = [relative for path in paths
                    if (relative := json_path_relative(path, child_path)) is not None]
        if "" in relative:
            selected[name] = copy.deepcopy(child)
        elif relative and isinstance(child.get("properties"), Mapping):
            value = old.get(name)
            selected[name] = _vfx_repair_row_schema(child, value if isinstance(value, Mapping) else {}, relative,
                                                  [relative for path in delete_paths
                                                   if (relative := json_path_relative(path, child_path)) is not None])
        elif relative:
            # Indexed/non-object descendants keep the canonical container;
            # the existing frozen filter still owns exact indexed permissions.
            selected[name] = copy.deepcopy(child)
        elif name in old:
            selected[name] = _vfx_frozen_literal_schema(old[name])
    out["properties"] = selected
    out["required"] = [name for name in selected if name in old or name in schema.get("required", [])]
    editable = {path.split(".", 1)[0] for path in paths}
    clauses = []
    for clause in schema.get("allOf") or []:
        condition = clause.get("if") or {}
        then = clause.get("then") or {}
        # A mutable discriminator keeps its complete canonical relation, even
        # to frozen companions. Otherwise only clauses touching editable roots
        # can constrain this repair, and false frozen branches are irrelevant.
        changing_condition = bool(editable & set(condition.get("properties") or {}))
        touching_result = bool(editable & (set(then.get("properties") or {}) | set(then.get("required") or [])))
        if changing_condition or (touching_result and not strict_schema_errors(old, condition)):
            clauses.append(copy.deepcopy(clause))
    if clauses:
        out["allOf"] = clauses
    else:
        out.pop("allOf", None)
    return out


def _vfx_scoped_repair_schema(packet: Mapping[str, Any], previous: Any, scope: Mapping[str, Any]) -> dict[str, Any]:
    """Request-only grammar; authoritative public admission stays unchanged."""
    full = _vfx_repair_schema_from_packet(packet)
    if (not scope or not isinstance(previous, Mapping) or "$" in (scope.get("errorPaths") or [])
            or not any(scope.get(key) for key in ("mutableSlotIds", "mutableAssetIds", "allowCreateSlots", "allowCreateAssets",
                                                "deletableSlotIds", "deletableSlotIndices", "deletableAssetIds", "deletableAssetIndices"))
            and not any((scope.get("fieldPermissions") or {}).get(key) for key in ("slots", "assets"))):
        return full
    out = copy.deepcopy(full)
    properties = out.get("properties")
    if not isinstance(properties, dict):
        return out
    permissions = scope.get("fieldPermissions") or {}
    for rows_key, upsert, permission_key, create in (
        ("slots", "slotsUpsert", "slotId", "allowCreateSlots"),
        ("assets", "assetsUpsert", "assetId", "allowCreateAssets"),
    ):
        if scope.get(create):
            continue  # New rows retain the complete real capability domain.
        canonical = properties[upsert]["items"]
        # Match each existing filter's ID ownership: assets reserve the first
        # occurrence; duplicate rows can only be removed by original index.
        source_rows = _rows(previous, rows_key)
        if rows_key == "assets":
            source_rows = reversed(source_rows)
        old_rows = {row.get("id"): row for row in source_rows if isinstance(row, Mapping) and isinstance(row.get("id"), str)}
        branches = []
        for permission in permissions.get(rows_key) or []:
            row_id = permission.get(permission_key)
            if row_id not in old_rows:
                continue
            branch = _vfx_repair_row_schema(canonical, old_rows[row_id], permission.get("paths") or [], permission.get("deletePaths") or [])
            branch["properties"]["id"] = {**copy.deepcopy(canonical["properties"]["id"]), "const": row_id}
            branches.append(branch)
        if branches:
            properties[upsert]["items"] = branches[0] if len(branches) == 1 else {"anyOf": branches}
            properties[upsert]["maxItems"] = min(properties[upsert]["maxItems"], len(branches))
        else:
            properties.pop(upsert)
    for field, permission in (("slotIdsDelete", "deletableSlotIds"), ("slotIndicesDelete", "deletableSlotIndices"),
                              ("assetIdsDelete", "deletableAssetIds"), ("assetIndicesDelete", "deletableAssetIndices")):
        allowed = scope.get(permission) or []
        if allowed:
            properties[field]["items"]["enum"] = copy.deepcopy(allowed)
        else:
            properties.pop(field)
    return out


def _vfx_repair_schema_from_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    # The packet's full output schema already contains the exact runtime pair enums.
    full = packet.get("outputSchema") if isinstance(packet.get("outputSchema"), Mapping) else {}
    if not full:
        return {"schema": VFX_REPAIR_PATCH_SCHEMA}
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema": {"const": VFX_REPAIR_PATCH_SCHEMA},
            "slotsUpsert": {"type": "array", "items": copy.deepcopy(full["properties"]["slots"]["items"]), "maxItems": full["properties"]["slots"]["maxItems"]},
            "slotIdsDelete": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 64}, "maxItems": full["properties"]["slots"]["maxItems"]},
            "slotIndicesDelete": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": max(0, full["properties"]["slots"]["maxItems"] * 2)}, "maxItems": max(1, full["properties"]["slots"]["maxItems"] * 2)},
            "assetsUpsert": {"type": "array", "items": copy.deepcopy(full["properties"]["assets"]["items"]), "maxItems": 16},
            "assetIdsDelete": {"type": "array", "items": copy.deepcopy(full["properties"]["assets"]["items"]["properties"]["id"]), "maxItems": 16},
            "assetIndicesDelete": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 32}, "maxItems": 32},
            "note": {"type": "string", "minLength": 1, "maxLength": 500},
        },
        "required": ["schema", "note"],
    }
