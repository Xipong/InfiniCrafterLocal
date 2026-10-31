"""Strict VFX admission, dependency checks and persisted-wire validation."""
from __future__ import annotations

import copy
import math
import re
from typing import Any, Mapping

from infini_local.core.schema_validation import strict_schema_errors
from infini_local.core.vfx import config
from infini_local.core.vfx.contours import (
    MAX_DRAW_WORK_UNITS,
    contour_budget_errors,
    contour_slot_errors,
)
from infini_local.core.vfx.contract import (
    _ANCHORS,
    _BLENDS,
    _LAYERS,
    _PARTICLES,
    _RENDERER_REQUIREMENTS,
    _RENDERERS,
    _TEXTURE_ROLES,
    SPRITE_TEXTURE_RENDERERS,
    VFX_DIRECTOR_SCHEMA,
    VFX_MANIFEST_SCHEMA,
    MalformedVfxDirectorOutput,
    _rows,
    _sound_slot_errors,
)
from infini_local.core.vfx.materials import (
    ASSET_ID_PATTERN,
    LIBRARY_PARTICLE_TEXTURES,
    MATERIAL_RENDERERS,
    element_schema,
    library_particle_schema,
    runtime_asset_schema,
    screen_shake_schema,
)
from infini_local.core.vfx.native_cues import native_cue_errors
from infini_local.core.vfx.native_effects import native_effect_budget_errors
from infini_local.core.vfx.schema import _director_schema
from infini_local.core.vfx.shapes import shape_slot_errors
from infini_local.core.vfx.spawn import spawn_slot_errors
from infini_local.core.vfx.surface import _allowed_pairs


def _number(value: Any, low: float, high: float, path: str, errors: list[dict[str, Any]], *, integer: bool = False) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append({"path": path, "message": "number required"})
        return int(low) if integer else low
    try:
        numeric = float(value)
    except OverflowError:
        errors.append({"path": path, "message": "finite number required"})
        return int(low) if integer else low
    if not math.isfinite(numeric):
        errors.append({"path": path, "message": "finite number required"})
        return int(low) if integer else low
    if numeric < low or numeric > high:
        errors.append({"path": path, "message": f"must be within [{low}, {high}]"})
    return int(value) if integer else numeric


def vfx_png_dependencies(
    data: Mapping[str, Any], manifest: Mapping[str, Any] | None = None, *, require_used: bool = False,
) -> dict[str, Any]:
    """Read-only projection of the PNG producers actually consumed by slots.

    Producer roles name the existing image owners, not another asset registry or
    request. Primitive, Dust and cue renderers consume no PNG. Admission checks selectors; delivery checks these exact owners'
    execution results. No mode, reference, image request or saved wire is changed.
    """
    if manifest is None:
        raw = data.get("vfxManifest")
        manifest = raw if isinstance(raw, Mapping) else {}
    errors: list[dict[str, Any]] = []
    dependencies: list[dict[str, Any]] = []
    assets = _rows(manifest, "assets")
    known: set[str] = set()
    for index, row in enumerate(assets):
        asset_id = row.get("id") if isinstance(row, Mapping) else None
        if not isinstance(asset_id, str) or re.fullmatch(ASSET_ID_PATTERN, asset_id) is None:
            continue  # Shape/format gates precede lookup; never hash hostile JSON.
        if asset_id in known:
            errors.append({"path": f"$.assets[{index}].id", "message": "duplicate asset id"})
        known.add(asset_id)
    runtime = data.get("runtimeProgram")
    entities = {row["id"]: row for row in _rows(runtime, "entities")
                if isinstance(row, Mapping) and isinstance(row.get("id"), str)} if isinstance(runtime, Mapping) else {}
    slots = _rows(manifest, "slots")
    impacts = {slot["entityId"] for slot in slots if isinstance(slot, Mapping)
               and slot.get("rendererKind") == "impactSprite" and isinstance(slot.get("entityId"), str)}
    used: set[str] = set()
    dangling = False
    for index, slot in enumerate(slots):
        if not isinstance(slot, Mapping):
            continue
        renderer = slot.get("rendererKind")
        if not isinstance(renderer, str):
            continue
        texture_refs=[]
        if renderer == "contour":
            geometry=slot.get("geometry")
            draws=geometry.get("draws") if isinstance(geometry,Mapping) else []
            for draw_index,draw in enumerate(draws if isinstance(draws,list) else []):
                material=draw.get("material") if isinstance(draw,Mapping) else None
                texture=material.get("texture") if isinstance(material,Mapping) else None
                if isinstance(texture,Mapping):
                    texture_refs.append((f"$.slots[{index}].geometry.draws[{draw_index}].material.texture.source",texture.get("source"),texture.get("assetId")))
        elif renderer in MATERIAL_RENDERERS or renderer == "historyTrail":
            name = "trail" if renderer == "historyTrail" else "element" if renderer == "spriteElement" else "path"
            payload = slot.get(name)
            texture = payload.get("texture") if isinstance(payload, Mapping) else None
            if isinstance(texture,Mapping):
                texture_refs.append((f"$.slots[{index}].{name}.texture.source",texture.get("source"),texture.get("assetId")))
        elif renderer in SPRITE_TEXTURE_RENDERERS:
            source=slot.get("textureRole")
            selector=f"$.slots[{index}].textureRole"
            if not isinstance(source,str) or source not in _TEXTURE_ROLES:
                errors.append({"path":selector,"message":"exact textureRole enum required"})
            else:texture_refs.append((selector,source,""))
        for selector,source,asset_id in texture_refs:
            if not isinstance(source, str):
                continue  # Scalar enum/type diagnostics belong to the shape gate.
            entity_id = slot.get("entityId")
            if not isinstance(entity_id, str):
                continue
            if entity_id not in entities and source in ("entity", "impact"):
                # Pair validation owns the unresolved entity; it cannot diagnose
                # that entity's mode or impact producer. Independent item/
                # asset references still resolve below, including asset usage.
                continue
            entity = entities.get(entity_id, {})
            raw_visual = entity.get("visual")
            entity_visual = raw_visual if isinstance(raw_visual, Mapping) else {}
            mode = entity_visual.get("assetMode")
            role = ""
            if source == "library" and (renderer in MATERIAL_RENDERERS or renderer in {"historyTrail", "contour"}):
                if not isinstance(asset_id, str) or asset_id not in LIBRARY_PARTICLE_TEXTURES:
                    errors.append({"path": selector.removesuffix("source") + "assetId", "message": "exact registered library texture id required; no paths or generated artwork"})
                # Native installed resource, never a generated PNG dependency/job.
                continue
            if source == "asset" and (renderer in MATERIAL_RENDERERS or renderer in {"historyTrail", "contour"}):
                if not isinstance(asset_id, str) or re.fullmatch(ASSET_ID_PATTERN, asset_id) is None or asset_id not in known:
                    dangling = True
                    errors.append({"path": selector.removesuffix("source") + "assetId", "message": "exact declared VFX asset id required; repair the reference, never create compensating artwork"})
                    # Preserve empty-domain Repair: both selector leaves are broken,
                    # never permission to invent a request or redesign valid assets.
                    if not known:
                        errors.append({"path": selector, "message": "asset texture source requires a declared VFX asset; repair the reference, never create compensating artwork"})
                    continue
                used.add(asset_id)
                role = "vfx:" + asset_id
            elif source == "item":
                role = "item"
            elif source == "impact":
                if entity_id not in impacts:
                    errors.append({"path": selector, "message": "impact texture requires a same-entity impactSprite image producer"})
                    continue
                role = "impact:" + entity_id
            elif source == "entity":
                if mode not in ("baked_sprite", "reuse_item_icon"):
                    errors.append({"path": selector, "message": "entity texture requires the exact entity baked_sprite/reuse_item_icon producer; no_asset/runtime_geometry provide no PNG"})
                    continue
                role = "item" if mode == "reuse_item_icon" or entity.get("kind") == "item_body" else "entity:" + entity_id
            elif source == "none" and renderer in SPRITE_TEXTURE_RENDERERS:
                errors.append({"path": selector, "message": "sprite renderer requires a non-none textureRole"})
                continue
            else:
                continue  # Unsupported enum values already have exact shape errors.
            if source == "asset":
                producer = next(row for row in assets if isinstance(row, Mapping) and row.get("id") == asset_id)
            elif source == "item" or (source == "entity" and mode == "reuse_item_icon"):
                raw_visual = data.get("visual")
                producer = raw_visual if isinstance(raw_visual, Mapping) else {}
            else:
                producer = entity_visual
            prefix = "impactSprite" if source == "impact" else "sprite"
            dependencies.append({"slotId": slot.get("id"), "entityId": entity_id,
                                 "source": source, "role": role, "selectorPath": selector,
                                 "spritePath": producer.get(prefix + "Path"), "spriteStatus": producer.get(prefix + "Status")})
    # A dangling selector is not permission to delete/redesign a valid request.
    if require_used and not dangling:
        for index, row in enumerate(assets):
            if isinstance(row, Mapping) and isinstance(row.get("id"), str) and row["id"] in known - used:
                errors.append({"path": f"$.assets[{index}].id", "message": "unused new asset request"})
    return {"dependencies": dependencies, "errors": errors}


def _material_slot_errors(slot: Mapping[str, Any], path: str) -> list[dict[str, Any]]:
    relations = {
        "spriteElement": ("element", element_schema, "speedMinPxPerTick", "speedMaxPxPerTick", False),
        "libraryParticle": ("particle", library_particle_schema, "speedMinPxPerTick", "speedMaxPxPerTick", False),
        "screenShakeCue": ("screenShake", screen_shake_schema, "taperStartDistancePx", "taperEndDistancePx", True),
    }
    relation = relations.get(str(slot.get("rendererKind") or ""))
    if relation is None:
        return []
    payload_name, schema_factory, low_name, high_name, strictly_greater = relation
    payload = slot.get(payload_name)
    if not isinstance(payload, Mapping):
        return []
    minimum, maximum = payload.get(low_name), payload.get(high_name)
    properties = schema_factory()["properties"]
    # A scalar failure is not permission to redesign its valid sibling. Compare
    # each operand through its canonical field gate, independently of other leaves.
    if (isinstance(minimum, (int, float)) and isinstance(maximum, (int, float))
            and not strict_schema_errors(minimum, properties[low_name])
            and not strict_schema_errors(maximum, properties[high_name])
            and (maximum < minimum or (strictly_greater and maximum == minimum))):
        operator = ">" if strictly_greater else ">="
        return [{"path": f"{path}.{payload_name}.{high_name}", "message": f"must be {operator} {low_name}"}]
    return []


def validate_vfx_director_output(raw: Any, data: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if isinstance(raw, MalformedVfxDirectorOutput):
        return {"ok": False, "errors": [{"path": "$", "message": f"malformed_json: {raw.error}"}]}
    if not isinstance(raw, Mapping):
        return {"ok": False, "errors": [{"path": "$", "message": "object required"}]}
    for schema_error in strict_schema_errors(raw, _director_schema(data)):
        errors.append({
            "path": str(schema_error.get("path") or "$"),
            "message": f"schema {schema_error.get('kind')}: expected {schema_error.get('expected')!r}",
        })
    if str(raw.get("schema") or "") != VFX_DIRECTOR_SCHEMA:
        errors.append({"path": "$.schema", "message": f"expected {VFX_DIRECTOR_SCHEMA}"})
    allowed = {(row["entityId"], row["event"]) for row in _allowed_pairs(data)}
    slots = raw.get("slots")
    if not isinstance(slots, list):
        errors.append({"path": "$.slots", "message": "array required"})
        slots = []
    max_slots = max(0, min(12, int(config.VFX_LLM_DIRECTOR_MAX_SLOTS)))
    if len(slots) > max_slots:
        errors.append({"path": "$.slots", "message": f"at most {max_slots} slots"})
    seen_ids: set[str] = set()
    impact_sprite_entities: set[str] = set()
    normalized_slots: list[dict[str, Any]] = []
    enum_fields = {
        "rendererKind": _RENDERERS, "textureRole": _TEXTURE_ROLES,
        "anchor": _ANCHORS, "blend": _BLENDS,
        "layer": _LAYERS,
        "particleSystemId": _PARTICLES,
    }
    number_fields = {
        "scale": (0.15, 5.0, False), "density": (0.0, 1.0, False),
        "duration": (3, 120, True), "alpha": (0.0, 1.0, False),
        "spread": (0.0, 2.0, False), "startTick": (0, 120, True),
        "repeatEvery": (0, 120, True),
    }
    for index, slot in enumerate(slots):
        path = f"$.slots[{index}]"
        if not isinstance(slot, Mapping):
            errors.append({"path": path, "message": "object required"})
            continue
        slot_id = str(slot.get("id") or "")
        if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", slot_id) is None:
            errors.append({"path": path + ".id", "message": "exact lowercase runtime id required"})
        elif slot_id in seen_ids:
            errors.append({"path": path + ".id", "message": "duplicate id"})
        seen_ids.add(slot_id)
        entity_id = str(slot.get("entityId") or "")
        event = str(slot.get("event") or "")
        if (entity_id, event) not in allowed:
            errors.append({"path": path, "message": f"entity/event pair {(entity_id, event)!r} is absent from runtimeProgram"})
        clean: dict[str, Any] = {"id": slot_id, "entityId": entity_id, "event": event}
        for field, values in enum_fields.items():
            if field not in slot:
                continue  # The canonical branch schema owns requiredness.
            value = str(slot.get(field) or "")
            if value not in values:
                errors.append({"path": f"{path}.{field}", "message": f"unsupported value {value!r}"})
            clean[field] = value
        for field, (low, high, integer) in number_fields.items():
            if field == "duration" and slot.get("rendererKind") in {"shape", "contour"}:
                low = 1
            if field in slot:
                clean[field] = _number(slot[field], low, high, f"{path}.{field}", errors, integer=integer)
        sprite_prompt = str(slot.get("spritePrompt") or "")
        if clean.get("rendererKind") == "impactSprite":
            if not sprite_prompt.strip():
                errors.append({"path": path + ".spritePrompt", "message": "impactSprite requires a dedicated non-empty transparent sprite prompt"})
            if clean.get("textureRole") != _RENDERER_REQUIREMENTS["impactSprite"]["textureRole"]:
                errors.append({"path": path + ".textureRole", "message": "impactSprite requires textureRole=impact"})
            if entity_id in impact_sprite_entities:
                errors.append({"path": path + ".entityId", "message": "runtime wire supports at most one impactSprite asset per entity"})
            impact_sprite_entities.add(entity_id)
        for field in ("spritePrompt", "spriteNegativePrompt", "spriteCanvasSize"):
            if field in slot:
                clean[field] = copy.deepcopy(slot[field])
        if "placementBindingId" in slot:
            clean["placementBindingId"] = slot["placementBindingId"]
        if "color" in slot:
            clean["color"] = copy.deepcopy(slot["color"])
        for payload in ("dust", "light", "trail", "geometry", "nativeEffect"):
            if payload in slot:
                clean[payload] = copy.deepcopy(slot[payload])
        if "shape" in slot:
            clean["shape"] = copy.deepcopy(slot["shape"])
        if "element" in slot:
            clean["element"] = copy.deepcopy(slot["element"])
        if "path" in slot:
            clean["path"] = copy.deepcopy(slot["path"])
        if "screenShake" in slot:
            clean["screenShake"] = copy.deepcopy(slot["screenShake"])
        if "particle" in slot:
            clean["particle"] = copy.deepcopy(slot["particle"])
        if "soundId" in slot:
            clean["soundId"] = slot["soundId"]
        if "sound" in slot:
            clean["sound"] = copy.deepcopy(slot["sound"])
        errors.extend(_sound_slot_errors(slot, path))
        errors.extend(_material_slot_errors(slot, path))
        errors.extend(spawn_slot_errors(slot, path))
        errors.extend(shape_slot_errors(slot, path))
        errors.extend(contour_slot_errors(slot, path))
        errors.extend(native_cue_errors(slot, path))
        normalized_slots.append(clean)
    errors.extend(contour_budget_errors(slots))
    errors.extend(vfx_png_dependencies(data, raw, require_used=True)["errors"])
    return {
        "ok": not errors,
        "errors": errors,
        "normalized": {
            "schema": VFX_DIRECTOR_SCHEMA,
            "slots": normalized_slots,
            **({"assets": copy.deepcopy(raw["assets"])} if "assets" in raw else {}),
        },
    }


def validate_vfx_manifest_wire(data: Any) -> dict[str, Any]:
    """Shared persisted-recipe shape gate; image delivery separately owns readiness.

    Reuse Director's additive branch definitions, never strip/coerce authored
    controls or hydrate an image here. Invalid PNG selectors fail explicitly;
    collection IDs/pairs are checked before lookup across both renderer domains.
    """
    if not isinstance(data, Mapping) or not isinstance(data.get("vfxManifest"), Mapping):
        return {"ok": False, "errors": [{"path": "$.vfxManifest", "message": "object required"}]}
    manifest = data["vfxManifest"]
    errors: list[dict[str, Any]] = []
    if manifest.get("schema") != VFX_MANIFEST_SCHEMA:
        errors.append({"path": "$.vfxManifest.schema", "message": f"expected {VFX_MANIFEST_SCHEMA}"})
    raw_slots = manifest.get("slots")
    if not isinstance(raw_slots, list):
        errors.append({"path": "$.vfxManifest.slots", "message": "array required"})
    slots = raw_slots if isinstance(raw_slots, list) else []
    # Runtime carries technical fields instead of Director-only image captions.
    slots_schema = _director_schema(data, include_legacy=True)["properties"]["slots"]
    if len(slots) > slots_schema["maxItems"]:
        errors.append({"path": "$.vfxManifest.slots", "message": f"at most {slots_schema['maxItems']} slots"})
    slot_schema = slots_schema["items"]
    # Captions/canvas are projected into the exact entity visual image owner,
    # never retained or synthesized as runtime slot controls.
    for field in ("spritePrompt", "spriteNegativePrompt", "spriteCanvasSize"):
        slot_schema["properties"].pop(field)
        for clause in slot_schema["allOf"]:
            consequent = clause.get("then", {})
            if "required" in consequent:
                consequent["required"] = [name for name in consequent["required"] if name != field]
            consequent.get("properties", {}).pop(field, None)
    slot_schema["properties"].update({
        "slotSeed": {"type": "integer", "minimum": 0, "maximum": 2147483647},
        "phaseOffset": {"type": "number", "minimum": -1.0, "maximum": 1.0},
    })
    manifest_schema = {
        "x-nativeFloat32Bounds": True,
        "type": "object", "additionalProperties": False,
        "properties": {
            "schema": {"const": VFX_MANIFEST_SCHEMA},
            "recipeId": {"type": "string"},
            "budget": {"type": "object", "additionalProperties": False,
                       "properties": {field: {"type": "integer", "minimum": 0, "maximum": maximum}
                                      for field, maximum in (("maxParticlesPerTick", 256), ("maxParticlesTotal", 12000), ("maxDrawCalls", MAX_DRAW_WORK_UNITS))},
                       "required": ["maxParticlesPerTick", "maxParticlesTotal", "maxDrawCalls"]},
            "slots": {"type": "array", "maxItems": slots_schema["maxItems"], "items": slot_schema},
            "assets": {"type": "array", "maxItems": 16, "items": runtime_asset_schema()},
        },
        "required": ["schema", "recipeId", "budget", "slots"],
    }
    for error in strict_schema_errors(manifest, manifest_schema, path="$.vfxManifest"):
        errors.append({"path": error["path"], "message": f"schema {error['kind']}: expected {error.get('expected')!r}"})
    allowed = {(row["entityId"], row["event"]) for row in _allowed_pairs(data)}
    seen: set[str] = set()
    impact_entities: set[str] = set()
    for index, slot in enumerate(slots):
        path = f"$.vfxManifest.slots[{index}]"
        if not isinstance(slot, Mapping):
            errors.append({"path": path, "message": "object required"})
            continue
        slot_id, entity_id, event = slot.get("id"), slot.get("entityId"), slot.get("event")
        if not isinstance(slot_id, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", slot_id) is None:
            errors.append({"path": path + ".id", "message": "exact lowercase runtime id required"})
        elif slot_id in seen:
            errors.append({"path": path + ".id", "message": "duplicate id"})
        else:
            seen.add(slot_id)
        if not isinstance(entity_id, str):
            errors.append({"path": path + ".entityId", "message": "string required"})
        if not isinstance(event, str):
            errors.append({"path": path + ".event", "message": "string required"})
        if isinstance(entity_id, str) and isinstance(event, str) and (entity_id, event) not in allowed:
            errors.append({"path": path, "message": "entity/event pair absent from runtimeProgram"})
        renderer = slot.get("rendererKind")
        if not isinstance(renderer, str) or renderer not in _RENDERERS:
            errors.append({"path": path + ".rendererKind", "message": "unsupported renderer"})
        if renderer == "impactSprite" and isinstance(entity_id, str):
            if entity_id in impact_entities:
                errors.append({"path": path + ".entityId", "message": "runtime wire supports at most one impactSprite asset per entity"})
            impact_entities.add(entity_id)
        errors.extend(_material_slot_errors(slot, path))
        errors.extend(spawn_slot_errors(slot, path))
        errors.extend(shape_slot_errors(slot, path))
        errors.extend(contour_slot_errors(slot, path))
        errors.extend(native_effect_budget_errors(slot, manifest.get("budget")))
        errors.extend(native_cue_errors(slot, path, persisted_wire=True))
        errors.extend(_sound_slot_errors(slot, path, persisted_wire=True))
    available = manifest.get("budget", {}).get("maxDrawCalls", 0) if isinstance(manifest.get("budget"), Mapping) else 0
    if isinstance(available, int) and not isinstance(available, bool):
        errors.extend(contour_budget_errors(slots, available, "$.vfxManifest"))
    for error in vfx_png_dependencies(data, manifest)["errors"]:
        errors.append({**error, "path": error["path"].replace("$.", "$.vfxManifest.", 1)})
    return {"ok": not errors, "errors": errors}
