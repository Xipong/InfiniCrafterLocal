from __future__ import annotations

"""Visual Director over accepted low-level runtime entities.

The Director sees the already-validated runtime program and parent facts.  It may
choose appearance and per-entity asset modes, but it cannot add/change gameplay,
entities, bindings, events, movement, damage, or lifecycle.
"""

import copy
import json
from typing import Any, Mapping

from infini_local.core.env_utils import env_float, env_int
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.llm_config import USE_LLM
from infini_local.core.llm_json_tools import parse_first_valid_llm_json
from infini_local.core.llm_stage_messages import stage_chat_message
from infini_local.core.repair_merge import merge_frozen_subtree
from infini_local.core.runtime_authoring import runtime_event_inventory, runtime_visual_roles, strict_schema_errors
from infini_local.pipelines.llm_transport import (
    apply_llm_common_options,
    llm_chat_json,
    llm_json_response_format,
    llm_reasoning_system_suffix,
    resolve_llm_model,
    visual_director_max_tokens,
    with_llm_stage,
)
from infini_local.pipelines.pipeline_visual_config import VISUAL_ASSET_MODE, VISUAL_DIRECTOR_LLM


VISUAL_KIT_SCHEMA = "infini.visual-kit.runtime-entities.v1"
VISUAL_REPAIR_PATCH_SCHEMA = "infini.visual-kit-repair-patch.runtime-entities.v1"
_ALLOWED_ASSET_MODES = {"baked_sprite", "reuse_item_icon", "runtime_geometry", "no_asset"}


def _stage_accounting(data: dict[str, Any]) -> dict[str, int]:
    debug = data.setdefault("debug", {})
    accounting = debug.setdefault("llmStageAccounting", {})
    for key in (
        "gameplayAuthorCalls", "gameplayRepairCalls", "visualDirectorCalls",
        "visualRepairCalls", "vfxDirectorCalls", "vfxRepairCalls",
    ):
        accounting.setdefault(key, 0)
    return accounting


def attach_visual(
    data: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    ca: dict[str, Any],
    cb: dict[str, Any],
) -> dict[str, Any]:
    del a, b, ca, cb
    visual = data.setdefault("visual", {})
    visual.setdefault("style", "terraria_item_sprite")
    visual.setdefault("preferredCanvasSize", 32)
    visual.setdefault("inventoryScale", 1.0)
    visual.setdefault("worldScale", 1.0)
    visual.setdefault("drawOffsetX", 0)
    visual.setdefault("drawOffsetY", 0)
    visual.setdefault("palette", [])
    visual.setdefault("requiredAnchors", [])
    visual.setdefault("spriteStatus", "")
    visual.setdefault("spritePath", "")
    visual.setdefault("spriteUrl", "")
    visual.setdefault("spriteTechnicalScore", 0.0)
    data.setdefault("debug", {})["runtimeVisualRoles"] = runtime_visual_roles(data)
    return data


def _visual_item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "prompt": {"type": "string", "minLength": 1, "maxLength": 1400},
            "negativePrompt": {"type": "string", "maxLength": 700},
            "silhouette": {"type": "string", "minLength": 1, "maxLength": 700},
            "visualIdentity": {"type": "string", "minLength": 1, "maxLength": 700},
            "palette": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 48}, "minItems": 1, "maxItems": 8},
            "preferredCanvasSize": {"type": "integer", "enum": [24, 32, 48, 64, 96, 128]},
            "inventoryScale": {"type": "number", "minimum": 0.25, "maximum": 4.0},
            "worldScale": {"type": "number", "minimum": 0.25, "maximum": 4.0},
        },
        "required": ["prompt", "negativePrompt", "silhouette", "visualIdentity", "palette", "preferredCanvasSize", "inventoryScale", "worldScale"],
    }


def _visual_entity_schema(entity_ids: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "entityId": {"type": "string", "enum": entity_ids},
            "assetMode": {"type": "string", "enum": sorted(_ALLOWED_ASSET_MODES)},
            "prompt": {"type": "string", "minLength": 1, "maxLength": 1400},
            "silhouette": {"type": "string", "minLength": 1, "maxLength": 700},
            "visualIdentity": {"type": "string", "minLength": 1, "maxLength": 700},
            "scale": {"type": "number", "minimum": 0.25, "maximum": 4.0},
        },
        "required": ["entityId", "assetMode", "prompt", "silhouette", "visualIdentity", "scale"],
    }


def _visual_repair_schema(entity_ids: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema": {"const": VISUAL_REPAIR_PATCH_SCHEMA},
            "itemPatch": {"anyOf": [_visual_item_schema(), {"type": "null"}]},
            "entitiesUpsert": {"type": "array", "items": _visual_entity_schema(entity_ids), "maxItems": len(entity_ids)},
            "entityIdsDelete": {"type": "array", "items": {"type": "string", "enum": entity_ids}, "maxItems": len(entity_ids)},
            "entityIndicesDelete": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": max(0, len(entity_ids) * 2)}, "maxItems": max(1, len(entity_ids) * 2)},
            "animationPlan": {"anyOf": [{"type": "string", "minLength": 1, "maxLength": 1200}, {"type": "null"}]},
            "note": {"type": "string", "minLength": 1, "maxLength": 500},
        },
        "required": ["schema", "itemPatch", "entitiesUpsert", "entityIdsDelete", "entityIndicesDelete", "animationPlan", "note"],
    }


def _response_schema(entity_ids: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema": {"const": VISUAL_KIT_SCHEMA},
            "item": _visual_item_schema(),
            "entities": {"type": "array", "items": _visual_entity_schema(entity_ids), "minItems": len(entity_ids), "maxItems": len(entity_ids)},
            "animationPlan": {"type": "string", "minLength": 1, "maxLength": 1200},
        },
        "required": ["schema", "item", "entities", "animationPlan"],
    }


def _runtime_card(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), Mapping) else {}
    events_by_entity: dict[str, list[str]] = {}
    for row in runtime_event_inventory(data):
        if isinstance(row, Mapping):
            events_by_entity.setdefault(str(row.get("entityId") or ""), []).append(str(row.get("event") or ""))
    rows: list[dict[str, Any]] = []
    for entity in runtime.get("entities") or []:
        if not isinstance(entity, Mapping):
            continue
        movement = entity.get("movement") if isinstance(entity.get("movement"), Mapping) else {}
        controller = entity.get("controller") if isinstance(entity.get("controller"), Mapping) else {}
        rows.append({
            "id": str(entity.get("id") or ""),
            "kind": str(entity.get("kind") or ""),
            "visualRole": str(entity.get("visualRole") or ""),
            "movement": str(movement.get("name") or ""),
            "controller": str(controller.get("name") or ""),
            "events": sorted(set(events_by_entity.get(str(entity.get("id") or ""), []))),
            "hitbox": copy.deepcopy(entity.get("hitbox") or {}),
        })
    return rows


def _validate_kit(raw: Any, entity_ids: list[str], item_body_id: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    if not isinstance(raw, dict):
        return None, [{"path": "$", "message": "Visual Director response must be an object"}]
    for schema_error in strict_schema_errors(raw, _response_schema(entity_ids)):
        errors.append({
            "path": str(schema_error.get("path") or "$"),
            "message": f"schema {schema_error.get('kind')}: expected {schema_error.get('expected')!r}",
        })
    if raw.get("schema") != VISUAL_KIT_SCHEMA:
        errors.append({"path": "$.schema", "message": f"expected {VISUAL_KIT_SCHEMA}"})
    item = raw.get("item")
    if not isinstance(item, dict):
        errors.append({"path": "$.item", "message": "required object"})
    else:
        for field in ("prompt", "silhouette", "visualIdentity"):
            if not str(item.get(field) or "").strip():
                errors.append({"path": f"$.item.{field}", "message": "required non-empty string"})
        if not isinstance(item.get("palette"), list) or not [x for x in item.get("palette", []) if str(x).strip()]:
            errors.append({"path": "$.item.palette", "message": "at least one palette entry required"})
    rows = raw.get("entities")
    if not isinstance(rows, list):
        errors.append({"path": "$.entities", "message": "required array"})
        rows = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        path = f"$.entities[{index}]"
        if not isinstance(row, dict):
            errors.append({"path": path, "message": "must be object"})
            continue
        entity_id = str(row.get("entityId") or "")
        if entity_id not in entity_ids:
            errors.append({"path": path + ".entityId", "message": f"unknown entity id {entity_id!r}"})
        elif entity_id in seen:
            errors.append({"path": path + ".entityId", "message": "duplicate entity id"})
        seen.add(entity_id)
        mode = str(row.get("assetMode") or "")
        if mode not in _ALLOWED_ASSET_MODES:
            errors.append({"path": path + ".assetMode", "message": f"unsupported mode {mode!r}"})
        for field in ("prompt", "silhouette", "visualIdentity"):
            if not str(row.get(field) or "").strip():
                errors.append({"path": path + "." + field, "message": "required non-empty string"})
    missing = [entity_id for entity_id in entity_ids if entity_id not in seen]
    if missing:
        errors.append({"path": "$.entities", "message": "missing entity rows: " + ", ".join(missing)})
    if len(rows) != len(entity_ids):
        errors.append({"path": "$.entities", "message": f"expected exactly {len(entity_ids)} rows"})
    # Item body always needs the canonical generated inventory PNG.
    item_row = next((row for row in rows if isinstance(row, dict) and row.get("entityId") == item_body_id), None)
    if isinstance(item_row, dict) and item_row.get("assetMode") != "baked_sprite":
        errors.append({"path": "$.entities", "message": f"item entity {item_body_id!r} must use baked_sprite"})
    return (copy.deepcopy(raw) if not errors else None), errors


def _build_visual_repair_scope(raw: Any, errors: list[dict[str, Any]], entity_ids: list[str], item_body_id: str) -> dict[str, Any]:
    rows = raw.get("entities") if isinstance(raw, Mapping) and isinstance(raw.get("entities"), list) else []
    mutable_ids: set[str] = set()
    delete_indices: set[int] = set()
    item_mutable = False
    animation_mutable = False
    item_paths: set[str] = set()
    entity_paths: dict[str, set[str]] = {}
    whole_response = not isinstance(raw, Mapping)

    def grant_entity(entity_id: str, relative: str) -> None:
        if entity_id:
            mutable_ids.add(entity_id)
            entity_paths.setdefault(entity_id, set()).add(relative.strip("."))

    for error in errors:
        path = str(error.get("path") or "$")
        message = str(error.get("message") or "")
        if path == "$":
            whole_response = True
        if path.startswith("$.item"):
            item_mutable = True
            item_paths.add("" if path == "$.item" else path.removeprefix("$.item."))
        if path.startswith("$.animationPlan"):
            animation_mutable = True
        match = __import__("re").match(r"^\$\.entities\[(\d+)\](?:\.(.*))?$", path)
        if match:
            index = int(match.group(1))
            relative = str(match.group(2) or "")
            if 0 <= index < len(rows) and isinstance(rows[index], Mapping):
                entity_id = str(rows[index].get("entityId") or "")
                if entity_id in entity_ids:
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
        animation_mutable = True
        item_paths.add("")
        for entity_id in entity_ids:
            grant_entity(entity_id, "")
        delete_indices.update(range(len(rows)))
    return {
        "schema": "infini.visual-repair-scope.v3",
        "itemMutable": item_mutable,
        "animationPlanMutable": animation_mutable,
        "mutableEntityIds": sorted(mutable_ids),
        "deletableEntityIds": [],
        "deletableEntityIndices": sorted(delete_indices),
        "fieldPermissions": {
            "itemPaths": sorted(item_paths),
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
        "broken": {
            "item": copy.deepcopy(source.get("item")) if scope.get("itemMutable") else None,
            "entities": [copy.deepcopy(row) for row in rows if isinstance(row, Mapping) and str(row.get("entityId") or "") in mutable_ids],
            "animationPlan": copy.deepcopy(source.get("animationPlan")) if scope.get("animationPlanMutable") else None,
        },
        "validReadOnly": {
            "item": copy.deepcopy(source.get("item")) if not scope.get("itemMutable") else None,
            "entities": [copy.deepcopy(row) for row in rows if isinstance(row, Mapping) and str(row.get("entityId") or "") not in mutable_ids],
            "animationPlan": copy.deepcopy(source.get("animationPlan")) if not scope.get("animationPlanMutable") else None,
        },
    }


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
    if schema.get("additionalProperties") is not False:
        return out
    valid_fields = set(schema.get("properties") or {})
    forbidden_fields = {
        path.split(".", 1)[0]
        for path in mutable_paths
        if path and path.split(".", 1)[0] not in valid_fields
    }
    for field in sorted(forbidden_fields):
        if field in source and field in out:
            out.pop(field, None)
            accepted.append(f"{audit_path}.{field}")
    return out


def _filter_visual_repair_patch(
    previous: Any,
    patch: Mapping[str, Any],
    scope: Mapping[str, Any],
    entity_ids: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    schema_errors = strict_schema_errors(patch, _visual_repair_schema(entity_ids))
    filtered = {
        "schema": VISUAL_REPAIR_PATCH_SCHEMA,
        "itemPatch": None,
        "entitiesUpsert": [],
        "entityIdsDelete": [],
        "entityIndicesDelete": [],
        "animationPlan": None,
        "note": str(patch.get("note") or "deterministically filtered Visual Repair"),
    }
    if schema_errors:
        return filtered, {"schema": "infini.visual-repair-filter-report.v1", "ok": False, "errors": schema_errors, "acceptedPaths": [], "ignoredChanges": []}

    source = previous if isinstance(previous, Mapping) else {}
    mutable_ids = set(str(value) for value in scope.get("mutableEntityIds") or [])
    deletable_ids = set(str(value) for value in scope.get("deletableEntityIds") or [])
    deletable_indices = set(int(value) for value in scope.get("deletableEntityIndices") or [])
    permission_root = scope.get("fieldPermissions") if isinstance(scope.get("fieldPermissions"), Mapping) else {}
    item_paths = tuple(str(value) for value in permission_root.get("itemPaths") or [])
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

    if patch.get("animationPlan") is not None:
        if scope.get("animationPlanMutable"):
            filtered["animationPlan"] = str(patch["animationPlan"])
            accepted.append("$.animationPlan")
        else:
            ignored.append(_visual_filter_ignored("$.animationPlan", patch.get("animationPlan"), source.get("animationPlan"), "valid_animation_plan_frozen"))

    for index, entity_id in enumerate(patch.get("entityIdsDelete") or []):
        path = f"$.entityIdsDelete[{index}]"
        if str(entity_id) in deletable_ids:
            filtered["entityIdsDelete"].append(str(entity_id))
            accepted.append(path)
        else:
            ignored.append(_visual_filter_ignored(path, entity_id, entity_id, "valid_entity_delete_ignored"))
    rows = source.get("entities") if isinstance(source.get("entities"), list) else []
    for index, source_index in enumerate(patch.get("entityIndicesDelete") or []):
        path = f"$.entityIndicesDelete[{index}]"
        numeric = int(source_index)
        if numeric in deletable_indices:
            filtered["entityIndicesDelete"].append(numeric)
            accepted.append(path)
        else:
            preserved = rows[numeric] if 0 <= numeric < len(rows) else None
            ignored.append(_visual_filter_ignored(path, numeric, preserved, "valid_entity_index_delete_ignored"))

    by_id = {str(row.get("entityId") or ""): row for row in rows if isinstance(row, Mapping) and str(row.get("entityId") or "")}
    for index, candidate in enumerate(patch.get("entitiesUpsert") or []):
        entity_id = str(candidate.get("entityId") or "")
        path = f"$.entitiesUpsert[{index}]"
        original = by_id.get(entity_id)
        if entity_id not in mutable_ids:
            if original is None or dict(candidate) != dict(original):
                ignored.append(_visual_filter_ignored(path, candidate, original, "independent_valid_entity_frozen"))
            continue
        if original is None:
            filtered["entitiesUpsert"].append(copy.deepcopy(candidate))
            accepted.append(path)
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
        if merged != original:
            filtered["entitiesUpsert"].append(merged)

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
    if filtered.get("animationPlan") is not None:
        out["animationPlan"] = str(filtered["animationPlan"])
    rows = list(out.get("entities") or []) if isinstance(out.get("entities"), list) else []
    rows = [row for index, row in enumerate(rows) if index not in set(filtered.get("entityIndicesDelete") or [])]
    doomed = set(str(value) for value in filtered.get("entityIdsDelete") or [])
    rows = [row for row in rows if not isinstance(row, Mapping) or str(row.get("entityId") or "") not in doomed]
    by_id = {str(row.get("entityId") or ""): copy.deepcopy(row) for row in rows if isinstance(row, Mapping) and str(row.get("entityId") or "")}
    order = [str(row.get("entityId") or "") for row in rows if isinstance(row, Mapping) and str(row.get("entityId") or "")]
    for row in filtered.get("entitiesUpsert") or []:
        entity_id = str(row.get("entityId") or "")
        if entity_id not in by_id:
            order.append(entity_id)
        by_id[entity_id] = copy.deepcopy(row)
    out["entities"] = [by_id[entity_id] for entity_id in order if entity_id in by_id]
    return (out, audit) if return_audit else out



def _request_visual_kit(
    data: dict[str, Any],
    a: dict[str, Any],
    b: dict[str, Any],
    ca: dict[str, Any],
    cb: dict[str, Any],
    *,
    repair_errors: list[dict[str, Any]] | None = None,
    previous: Any = None,
    repair_scope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    runtime_rows = _runtime_card(data)
    entity_ids = [row["id"] for row in runtime_rows]
    repair = repair_errors is not None
    schema = _visual_repair_schema(entity_ids) if repair else _response_schema(entity_ids)
    if repair:
        system = (
            "You are the conditional Visual Repair. Return only a narrow patch for exact invalid visual fields/rows. "
            "You may return a complete broken row; deterministic merge freezes every already-valid old field and keeps "
            "the exact repaired or newly missing fields. Extra rewrites are ignored. Runtime gameplay is immutable. Return JSON only."
        )
        context = _visual_repair_context(previous, repair_scope or {})
        payload: dict[str, Any] = {
            "task": "Patch only exact invalid visualKit fields/rows.",
            "exactErrors": copy.deepcopy(repair_errors or []),
            "repairScope": copy.deepcopy(dict(repair_scope or {})),
            "brokenFragments": context["broken"],
            "validGeneratedContext": context["validReadOnly"],
            "parentFactsReadOnly": {
                "parentA": {"item": copy.deepcopy(a), "facts": copy.deepcopy(ca)},
                "parentB": {"item": copy.deepcopy(b), "facts": copy.deepcopy(cb)},
            },
            "runtimeEntitiesReadOnly": runtime_rows,
            "rules": [
                "fill only fields listed in repairScope.fieldPermissions; optional unreported fields stay absent",
                "already-valid fields and independent rows are frozen; extra rewrites are ignored",
                "preserve valid literal parent composition and accepted runtime entity set",
                "item_body must use baked_sprite; no placeholder PNG",
            ],
            "responseSchema": schema,
        }
    else:
        system = (
            "You are Visual Director for InfiniCrafterLocal. Design appearance only for the accepted runtime entities. "
            "Do not add, remove, merge, rename or reinterpret gameplay entities/events. Do not classify the item as a weapon family. "
            "Preserve literal parent objects and their physical relationships. For each exact entityId choose one finite assetMode: "
            "baked_sprite, reuse_item_icon, runtime_geometry, or no_asset. item_body must be baked_sprite. "
            "A baked sprite is mandatory delivery: never request or accept a placeholder. Return JSON only."
        )
        payload = {
            "task": "Author one visualKit for the accepted runtime program.",
            "item": {"name": data.get("name"), "tooltip": data.get("tooltip"), "concept": copy.deepcopy(data.get("concept") or {})},
            "parents": {
                "parentA": {"item": copy.deepcopy(a), "facts": copy.deepcopy(ca)},
                "parentB": {"item": copy.deepcopy(b), "facts": copy.deepcopy(cb)},
            },
            "runtimeEntities": runtime_rows,
            "requiredEntityIds": entity_ids,
            "rules": [
                "appearance only; runtime program is immutable",
                "literal furniture, tools and materials may remain literal",
                "movement/controller names describe motion, not a weapon taxonomy",
                "baked_sprite requires a real generated PNG; no placeholder",
            ],
            "responseSchema": schema,
        }
    model = resolve_llm_model()
    request = {
        "model": model,
        "messages": [
            stage_chat_message("system", "visual_repair_contract" if repair else "visual_director_contract", system + llm_reasoning_system_suffix(model)),
            stage_chat_message("user", "visual_repair_context" if repair else "visual_director_context", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
        ],
        "temperature": (
            env_float("INFINI_VISUAL_REPAIR_TEMPERATURE", 0.12)
            if repair
            else env_float("INFINI_VISUAL_DIRECTOR_TEMPERATURE", 0.45)
        ),
        "max_tokens": visual_director_max_tokens(),
        "response_format": llm_json_response_format(
            "infini_visual_kit_repair_patch" if repair else "infini_visual_kit_runtime_entities",
            schema=schema,
            strict=True,
            auto_preference="json_schema",
        ),
    }
    request = apply_llm_common_options(request, model_name=model, default_max_tokens=visual_director_max_tokens())
    raw = llm_chat_json(with_llm_stage(request, "visual_repair" if repair else "visual_director"), timeout=env_int("INFINI_LLM_TIMEOUT", 95))
    content = raw["choices"][0]["message"]["content"]
    parsed = parse_first_valid_llm_json(content)
    return parsed if isinstance(parsed, dict) else {"_raw": str(content)[:6000]}


def _apply_kit(data: dict[str, Any], kit: Mapping[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(data)
    item = dict(kit.get("item") or {})
    visual = out.setdefault("visual", {})
    visual.update({
        "imagePrompt": str(item.get("prompt") or "")[:1400],
        "negativePrompt": str(item.get("negativePrompt") or "")[:700],
        "silhouette": str(item.get("silhouette") or "")[:700],
        "visualIdentity": str(item.get("visualIdentity") or "")[:700],
        "palette": [str(x)[:48] for x in item.get("palette") or []][:8],
        "preferredCanvasSize": int(item.get("preferredCanvasSize") or 32),
        "inventoryScale": float(item.get("inventoryScale") or 1.0),
        "worldScale": float(item.get("worldScale") or 1.0),
    })
    runtime = out.get("runtimeProgram") if isinstance(out.get("runtimeProgram"), dict) else {}
    by_id = {str(row.get("entityId")): row for row in kit.get("entities") or [] if isinstance(row, dict)}
    for entity in runtime.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        row = by_id[str(entity.get("id") or "")]
        entity_visual = entity.setdefault("visual", {})
        entity_visual.update({
            "role": str(entity.get("visualRole") or ""),
            "assetMode": str(row.get("assetMode") or ""),
            "prompt": str(row.get("prompt") or "")[:1400],
            "silhouette": str(row.get("silhouette") or "")[:700],
            "visualIdentity": str(row.get("visualIdentity") or "")[:700],
            "scale": float(row.get("scale") or 1.0),
            "spritePath": "",
            "spriteUrl": "",
            "spriteStatus": "pending" if row.get("assetMode") == "baked_sprite" else "not_required",
            "spriteTechnicalScore": 0.0,
        })
    out["visualKit"] = copy.deepcopy(dict(kit))
    out["visualKit"]["animationPlan"] = str(kit.get("animationPlan") or "")[:1200]
    return out


def apply_visual_director(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any], ca: dict[str, Any], cb: dict[str, Any]) -> dict[str, Any]:
    runtime = data.get("runtimeProgram") if isinstance(data.get("runtimeProgram"), dict) else {}
    entities = [row for row in runtime.get("entities") or [] if isinstance(row, dict)]
    entity_ids = [str(row.get("id") or "") for row in entities]
    item_body_id = next((str(row.get("id") or "") for row in entities if row.get("kind") == "item_body"), "")
    if not entity_ids or not item_body_id:
        raise PlannerUnavailable("Visual Director has no accepted runtime entities")
    if not (USE_LLM and VISUAL_DIRECTOR_LLM):
        # Explicit development mode only. Production LLM crafts must not silently
        # manufacture a visual design in code.
        if str((data.get("debug") or {}).get("planner") or "").startswith("llm_"):
            raise PlannerUnavailable("Visual Director is required for LLM-authored craft")
        kit = {
            "schema": VISUAL_KIT_SCHEMA,
            "item": {
                "prompt": f"Terraria pixel-art inventory sprite of {data.get('name')}; literal combined parent object, transparent background",
                "negativePrompt": "placeholder, text, watermark",
                "silhouette": "compact readable combined object",
                "visualIdentity": str((data.get("concept") or {}).get("literalSynthesis") or data.get("name") or "generated item"),
                "palette": ["neutral", "accent"],
                "preferredCanvasSize": 32,
                "inventoryScale": 1.0,
                "worldScale": 1.0,
            },
            "entities": [
                {
                    "entityId": entity_id,
                    "assetMode": "baked_sprite" if entity_id == item_body_id else "reuse_item_icon",
                    "prompt": f"Terraria pixel-art visual for runtime entity {entity_id}",
                    "silhouette": "readable runtime entity",
                    "visualIdentity": entity_id,
                    "scale": 1.0,
                }
                for index, entity_id in enumerate(entity_ids)
            ],
            "animationPlan": "Use the authored runtime movement without changing gameplay.",
        }
        data.setdefault("debug", {})["visualDirectorStatus"] = "development_fixture"
        return _apply_kit(data, kit)

    accounting = _stage_accounting(data)
    accounting["visualDirectorCalls"] += 1
    raw = _request_visual_kit(data, a, b, ca, cb)
    kit, errors = _validate_kit(raw, entity_ids, item_body_id)
    if kit is None:
        accounting["visualRepairCalls"] += 1
        repair_scope = _build_visual_repair_scope(raw, errors, entity_ids, item_body_id)
        patch = _request_visual_kit(data, a, b, ca, cb, repair_errors=errors, previous=raw, repair_scope=repair_scope)
        repaired, repair_audit = _apply_visual_repair_patch(raw, patch, repair_scope, entity_ids, return_audit=True)
        kit, errors = _validate_kit(repaired, entity_ids, item_body_id)
        if kit is None:
            raise PlannerUnavailable("Visual Repair did not produce an entity-complete visual kit: " + json.dumps(errors[:16], ensure_ascii=False))
        raw = repaired
        data.setdefault("debug", {})["visualRepairRawPatch"] = copy.deepcopy(patch)
        data["debug"]["visualRepairPatch"] = copy.deepcopy(repair_audit.get("filteredPatch") or {})
        data["debug"]["visualRepairFilterAudit"] = copy.deepcopy(repair_audit)
        data["debug"]["visualRepairScope"] = copy.deepcopy(repair_scope)
    out = _apply_kit(data, kit)
    out.setdefault("debug", {})["visualDirectorStatus"] = "validated_and_applied"
    out["debug"]["visualDirectorEntityIds"] = entity_ids
    out["debug"]["visualDirectorRaw"] = copy.deepcopy(raw)
    return out


def build_image_prompt(data: dict[str, Any], visual: dict[str, Any]) -> str:
    return str(visual.get("imagePrompt") or "")[:1400]


def visual_response_schema(entity_ids: list[str]) -> dict[str, Any]:
    """Public generated schema owned by the Visual Director contract module."""

    return _response_schema(entity_ids)


def visual_repair_schema(entity_ids: list[str]) -> dict[str, Any]:
    """Public generated schema for the bounded Visual Repair patch."""

    return _visual_repair_schema(entity_ids)


__all__ = [
    "VISUAL_KIT_SCHEMA",
    "VISUAL_REPAIR_PATCH_SCHEMA",
    "apply_visual_director",
    "attach_visual",
    "build_image_prompt",
    "visual_repair_schema",
    "visual_response_schema",
]
