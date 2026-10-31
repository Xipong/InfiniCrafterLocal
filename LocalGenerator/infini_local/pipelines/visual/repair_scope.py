"""Exact Visual repair permissions, context and scoped output schemas."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from infini_local.core.repair_merge import json_path_child, json_path_relative
from infini_local.pipelines.visual.contract import (
    MalformedVisualDirectorOutput,
    _visual_entity_schema,
    _visual_equip_overlay_schema,
    _visual_item_schema,
    _visual_repair_schema,
)


def _scoped_visual_patch_node(schema: Mapping[str, Any], paths: list[str]) -> dict[str, Any]:
    """Project only exact permitted descendants; canonical admission stays full."""
    if "" in paths:
        return copy.deepcopy(dict(schema))
    if "oneOf" in schema:
        projected = []
        for branch in schema["oneOf"]:
            node = _scoped_visual_patch_node(branch, paths)
            if node not in projected:
                projected.append(node)
        return projected[0] if len(projected) == 1 else {"anyOf": projected}
    properties = {}
    for field, child in (schema.get("properties") or {}).items():
        relative = [value for path in paths
                    if (value := json_path_relative(path, json_path_child("", field))) is not None]
        if relative:
            properties[field] = _scoped_visual_patch_node(child, relative)
    if "properties" not in schema:
        return copy.deepcopy(dict(schema))
    return {"type": "object", "additionalProperties": False, "properties": properties, "required": list(properties)}


def _scoped_visual_repair_schema(
    entity_ids: list[str], equipment_overlay_required: bool, item_body_id: str,
    scope: Mapping[str, Any], previous: Any,
) -> dict[str, Any]:
    full = _visual_repair_schema(entity_ids, equipment_overlay_required, item_body_id)
    permissions = scope.get("fieldPermissions") or {}
    properties = {key: copy.deepcopy(full["properties"][key]) for key in ("schema", "note")}
    for key, paths_key, owner in (("itemPatch", "itemPaths", _visual_item_schema()),
                                  ("equipOverlayPatch", "equipOverlayPaths", _visual_equip_overlay_schema())):
        paths = permissions.get(paths_key) or []
        if paths and key in full["properties"]:
            properties[key] = {"anyOf": [_scoped_visual_patch_node(owner, paths), {"type": "null"}]}
    source = previous if isinstance(previous, Mapping) else {}
    rows = {}
    raw_rows = source.get("entities")
    source_rows = raw_rows if isinstance(raw_rows, list) else []
    for row in source_rows:
        if isinstance(row, Mapping) and isinstance(row.get("entityId"), str):
            rows.setdefault(row["entityId"], row)
    entity_schema = _visual_entity_schema(entity_ids, item_body_id)
    branches = entity_schema.get("oneOf") or [entity_schema]
    variants = []
    for permission in permissions.get("entities") or []:
        entity_id, paths = permission["entityId"], permission["paths"]
        old = rows.get(entity_id, {})
        for branch in branches:
            props = branch["properties"]
            if entity_id not in props["entityId"]["enum"]:
                continue
            if any(field not in paths and "" not in paths and field in old and old[field] != props[field].get("const")
                   for field in ("assetMode", "visualProjectRef")):
                continue
            partial = _scoped_visual_patch_node(branch, paths)
            partial["properties"]["entityId"] = {"const": entity_id}
            partial["required"] = list(dict.fromkeys([*partial.get("required", []), "entityId"]))
            if partial not in variants:
                variants.append(partial)
    if variants:
        properties["entitiesUpsert"] = {"type": "array", "items": variants[0] if len(variants) == 1 else {"anyOf": variants}, "maxItems": len(permissions.get("entities") or [])}
    for key, scope_key in (("entityIdsDelete", "deletableEntityIds"), ("entityIndicesDelete", "deletableEntityIndices")):
        allowed = scope.get(scope_key) or []
        if allowed:
            properties[key] = copy.deepcopy(full["properties"][key])
            properties[key]["items"] = {"type": "integer" if key == "entityIndicesDelete" else "string", "enum": list(allowed)}
    return {"type": "object", "additionalProperties": False, "properties": properties, "required": list(properties)}


def _build_visual_repair_scope(
    raw: Any,
    errors: list[dict[str, Any]],
    entity_ids: list[str],
    item_body_id: str,
    *,
    equipment_overlay_required: bool = False,
) -> dict[str, Any]:
    rows_raw = raw.get("entities") if isinstance(raw, Mapping) else None
    rows = rows_raw if isinstance(rows_raw, list) else []
    original_indices: dict[str, int] = {}
    for index, row in enumerate(rows):
        if isinstance(row, Mapping) and row.get("entityId") in entity_ids:
            original_indices.setdefault(row["entityId"], index)
    entity_child_error_indices: set[int] = set()
    for diagnostic in errors:
        diagnostic_path = str(diagnostic.get("path") or "")
        child_match = __import__("re").match(r"^\$\.entities\[(\d+)\]", diagnostic_path)
        if child_match and json_path_relative(diagnostic_path, child_match.group(0)):
            entity_child_error_indices.add(int(child_match.group(1)))
    mutable_ids: set[str] = set()
    delete_indices: set[int] = set()
    missing_ids: set[str] = set()
    item_mutable = False
    overlay_mutable = False
    item_paths: set[str] = set()
    overlay_paths: set[str] = set()
    entity_paths: dict[str, set[str]] = {}
    whole_response = not isinstance(raw, Mapping)

    def grant_entity(entity_id: str, relative: str) -> None:
        if entity_id:
            mutable_ids.add(entity_id)
            entity_paths.setdefault(entity_id, set()).add(relative.strip("."))

    for error in errors:
        path = str(error.get("path") or "$")
        message = str(error.get("message") or "")
        if "schema one_of" in message and any(
            json_path_relative(str(other.get("path") or ""), path)
            for other in errors
        ):
            # A discriminated nested object (including geometry) may report an
            # aggregate plus exact invalid leaves. The aggregate grants no
            # authority to rewrite already-valid siblings.
            continue
        if path == "$":
            whole_response = True
        relative_item_path = json_path_relative(path, "$.item")
        if relative_item_path is not None:
            item_mutable = True
            item_paths.add(relative_item_path)
        relative_overlay_path = json_path_relative(path, "$.equipOverlay")
        if equipment_overlay_required and relative_overlay_path is not None:
            overlay_mutable = True
            overlay_paths.add(relative_overlay_path)
        match = __import__("re").match(r"^\$\.entities\[(\d+)\]", path)
        relative = json_path_relative(path, match.group(0)) if match else None
        if match and relative is not None:
            index = int(match.group(1))
            if not relative and index in entity_child_error_indices and "schema one_of" in message:
                # oneOf emits an aggregate row marker alongside exact branch
                # diagnostics. The aggregate must not widen exact field scope.
                continue
            if 0 <= index < len(rows) and isinstance(rows[index], Mapping):
                entity_id = str(rows[index].get("entityId") or "")
                if entity_id in entity_ids:
                    if original_indices[entity_id] != index:
                        # The first occurrence owns ID-keyed leaf repairs. A
                        # later duplicate's errors grant only original-index
                        # deletion, never permissions on the first row.
                        delete_indices.add(index)
                        continue
                    grant_entity(entity_id, relative)
                else:
                    delete_indices.add(index)
            else:
                delete_indices.add(index)
        if path == "$.entities":
            if "missing entity rows:" in message:
                tail = message.split("missing entity rows:", 1)[1]
                for value in tail.split(","):
                    entity_id = value.strip()
                    if entity_id in entity_ids:
                        missing_ids.add(entity_id)
                        grant_entity(entity_id, "")
            if "item entity" in message:
                grant_entity(item_body_id, "assetMode")
            seen: dict[str, int] = {}
            for index, row in enumerate(rows):
                if not isinstance(row, Mapping):
                    delete_indices.add(index)
                    continue
                entity_id = str(row.get("entityId") or "")
                if entity_id not in entity_ids:
                    delete_indices.add(index)
                elif entity_id in seen:
                    delete_indices.add(index)
                else:
                    seen[entity_id] = index
            for entity_id in entity_ids:
                if entity_id not in seen:
                    grant_entity(entity_id, "")
    if whole_response:
        item_mutable = True
        overlay_mutable = equipment_overlay_required
        item_paths.add("")
        if equipment_overlay_required:
            overlay_paths.add("")
        for entity_id in entity_ids:
            grant_entity(entity_id, "")
        delete_indices.update(range(len(rows)))
    replacement_transactions: list[dict[str, Any]] = []
    if not whole_response and len(delete_indices) == 1 and len(missing_ids) == 1:
        replacement_transactions.append({
            "entityId": next(iter(missing_ids)),
            "replaceIndex": next(iter(delete_indices)),
        })
    return {
        "schema": "infini.visual-repair-scope.v3",
        "itemMutable": item_mutable,
        "equipmentOverlayRequired": equipment_overlay_required,
        "equipOverlayMutable": overlay_mutable,
        "mutableEntityIds": sorted(mutable_ids),
        "deletableEntityIds": [],
        "deletableEntityIndices": sorted(delete_indices),
        "entityReplacementTransactions": replacement_transactions,
        "fieldPermissions": {
            "itemPaths": sorted(item_paths),
            "equipOverlayPaths": sorted(overlay_paths),
            "entities": [
                {"entityId": entity_id, "paths": sorted(paths)}
                for entity_id, paths in sorted(entity_paths.items())
            ],
        },
        "errorPaths": [str(row.get("path") or "$") for row in errors],
    }


def _visual_repair_context(raw: Any, scope: Mapping[str, Any]) -> dict[str, Any]:
    source = raw if isinstance(raw, Mapping) else {}
    mutable_ids = set(str(value) for value in scope.get("mutableEntityIds") or [])
    rows = source.get("entities") if isinstance(source.get("entities"), list) else []
    return {
        "malformedRawText": raw.raw_text if isinstance(raw, MalformedVisualDirectorOutput) else "",
        "broken": {
            "item": copy.deepcopy(source.get("item")) if scope.get("itemMutable") else None,
            "equipOverlay": copy.deepcopy(source.get("equipOverlay")) if scope.get("equipOverlayMutable") else None,
            "entities": [copy.deepcopy(row) for row in rows if isinstance(row, Mapping) and str(row.get("entityId") or "") in mutable_ids],
        },
        "validReadOnly": {
            "item": copy.deepcopy(source.get("item")) if not scope.get("itemMutable") else None,
            "equipOverlay": copy.deepcopy(source.get("equipOverlay")) if scope.get("equipmentOverlayRequired") and not scope.get("equipOverlayMutable") else None,
            "entities": [copy.deepcopy(row) for row in rows if isinstance(row, Mapping) and str(row.get("entityId") or "") not in mutable_ids],
            **({"animationPlan": source["animationPlan"]} if isinstance(source.get("animationPlan"), str) else {}),
        },
    }
