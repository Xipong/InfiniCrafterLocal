"""Read-only presentation facts derived from already accepted runtime wire."""
from __future__ import annotations

import copy
from typing import Any, Mapping

from infini_local.core.runtime_authoring.capability_registry import ENTITY_KIND_REGISTRY
from infini_local.core.runtime_authoring.wire_views import (
    runtime_event_inventory,
    runtime_visual_roles,
)
from infini_local.core.vfx import config
from infini_local.core.vfx.contract import (
    _ANCHORS,
    _BLENDS,
    _FRESH_RENDERERS,
    _LAYERS,
    _RENDERER_REQUIREMENTS,
    _RENDERER_SEMANTICS,
    _SOUND_IDS,
    VFX_DIRECTOR_SCHEMA,
    _sound_schema,
)
from infini_local.core.visual_contract_schema import collision_path_source


def _allowed_pairs(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    inventory: list[Any] = runtime_event_inventory(data)
    for row in inventory:
        if not isinstance(row, Mapping):
            continue
        pair = (str(row.get("entityId") or ""), str(row.get("event") or ""))
        if not all(pair) or pair in seen:
            continue
        seen.add(pair)
        rows.append({"entityId": pair[0], "event": pair[1]})
    return sorted(rows, key=lambda row: (row["entityId"], row["event"]))


def _textured_path_sources(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    runtime = data.get("runtimeProgram")
    entities = runtime.get("entities") if isinstance(runtime, Mapping) else []
    rows: list[dict[str, Any]] = []
    for entity in entities or []:
        if not isinstance(entity, Mapping) or not isinstance(entity.get("id"), str) or not isinstance(entity.get("kind"), str):
            continue
        kind = ENTITY_KIND_REGISTRY.get(entity["kind"])
        if kind is None or not kind.projectile:
            continue
        sources = ["anchorHistory"]
        geometry = collision_path_source(entity)
        if geometry is not None:
            sources.append(geometry)
        sources.append("ownerLink")  # Generic explicit connector; no movement/preset selection.
        rows.append({"entityId": entity["id"], "sources": sources})
    return rows


def _entity_texture_sources(data: Mapping[str, Any], *, include_legacy: bool = False) -> list[dict[str, Any]]:
    runtime = data.get("runtimeProgram")
    raw_entities = runtime.get("entities") if isinstance(runtime, Mapping) else []
    entities = raw_entities if isinstance(raw_entities, list) else []
    rows: list[dict[str, Any]] = []
    for entity in entities:
        if not isinstance(entity, Mapping) or not isinstance(entity.get("id"), str):
            continue
        visual = entity.get("visual")
        mode = visual.get("assetMode") if isinstance(visual, Mapping) else None
        rows.append({"entityId": entity["id"], "assetMode": mode, "sources": ["item", "asset", "library", *(["impact"] if include_legacy else []), *(["entity"] if mode in ("baked_sprite", "reuse_item_icon") else [])]})
    return rows


def _body_presentation_frame(entity: Mapping[str, Any], geometry: str | None) -> dict[str, Any]:
    """Small typed view of admitted frame operands, never a pose/contact prediction."""
    fields = {
        "aim": ("source", "turnOwner"),
        "rotation": ("mode", "offsetRadians", "radiansPerUpdate", "window"),
        "attachment": ("anchor", "axisOffsetPx", "normalOffsetPx", "window"),
        "reach": ("durationTicks", "startOffsetPx", "peakOffsetPx", "endOffsetPx", "peakProgress", "window"),
        "armPose": ("durationTicks", "startStretch", "peakStretch", "endStretch", "peakProgress", "window"),
    }
    if geometry == "beam":
        fields.update(beamGeometry=("lengthPx", "widthPx", "raycastTiles", "startOffsetPx"),
                      beamRamp=("warmupTicks", "initialWidthMultiplier"))
    frame: dict[str, Any] = {
        component: {key: copy.deepcopy(value[key]) for key in keys if key in value}
        for component, keys in fields.items() if isinstance(value := entity.get(component), Mapping)
    }
    attachment = frame.get("attachment", {})
    selector = attachment.get("anchor")
    anchor = {"owner_mounted": "owner.MountedCenter", "owner_center": "owner.Center",
              "front_hand": "owner.current_composite_front_hand"}.get(selector) if isinstance(selector, str) else None
    if anchor is not None:
        frame["attachmentAnchor"] = anchor
    if geometry == "beam":
        current = "beamGeometry" in frame
        frame["beamStart"] = {"anchor": "projectile.Center"} if current else {
            "anchor": "owner.MountedCenter", "forwardOffsetPx": 18}
        frame["beamAxis"] = "motion_axis" if current else "velocity_or_initial_direction"
    if frame:
        frame["units"] = {"distance": "native_world_pixels", "duration": "world_ticks"}
    return frame


def _body_presentation(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Exact selected body coverage, without asset paths or inferred art choices.

    VFX can decorate accepted bodies, but cannot erase an already selected solid
    primitive. Conversely no_asset supplies no body underneath a textured path.
    These are read-only render facts, not another authored schema or design gate.
    """
    runtime = data.get("runtimeProgram")
    entities = runtime.get("entities") if isinstance(runtime, Mapping) else []
    root = data.get("visual")
    rows: list[dict[str, Any]] = []
    for entity in entities or []:
        if not isinstance(entity, Mapping) or not isinstance(entity.get("id"), str):
            continue
        visual = entity.get("visual")
        if not isinstance(visual, Mapping):
            continue
        mode = visual.get("assetMode")
        geometry = collision_path_source(entity)
        row: dict[str, Any] = {"entityId": entity["id"], "assetMode": mode}
        frame = _body_presentation_frame(entity, geometry)
        if frame:
            row["frame"] = frame
        if mode in ("baked_sprite", "reuse_item_icon"):
            selected = root if mode == "reuse_item_icon" or entity.get("kind") == "item_body" else visual
            row["coverage"] = "single_sprite_at_body"
            if isinstance(selected, Mapping):
                row["image"] = {key: copy.deepcopy(selected[key]) for key in
                    ("renderSizePx", "forwardAngleDegrees", "grip", "silhouette", "visualIdentity") if key in selected}
            if entity.get("kind") == "item_body":
                row["coverage"] = "inventory_and_item_use"
                use = runtime.get("itemUse") if isinstance(runtime, Mapping) else None
                if isinstance(use, Mapping):
                    row["itemUse"] = {key: copy.deepcopy(use[key]) for key in
                        ("hideUseGraphic",) if key in use}
            elif geometry == "whip":
                row["coverage"] = "single_sprite_at_curve_tip"
        elif mode == "no_asset":
            row["coverage"] = "no_body"
        elif mode == "runtime_geometry":
            row["material"] = "solid_untextured"
            row["coverage"] = "body_segment"
            authored = visual.get("geometry")
            if isinstance(authored, Mapping):
                row["geometry"] = copy.deepcopy(dict(authored))
                row["widthPx"] = authored.get("widthPx")
                if authored.get("source") == "collision_path":
                    row["coverage"] = "collision_beam" if geometry == "beam" else "collision_curve"
                # An explicit body_segment remains a segment even on an entity
                # with beam/lash collision. Presentation does not inherit shape.
            elif geometry == "beam":
                row["coverage"] = "collision_beam"
            elif geometry == "whip":
                row["coverage"] = "collision_curve"
                hitbox = entity.get("hitbox")
                if isinstance(hitbox, Mapping):
                    width, scale = hitbox.get("widthPx"), hitbox.get("hitboxScale")
                    if type(width) in (int, float) and type(scale) in (int, float):
                        row["widthPx"] = max(4.0, width * scale * 0.5)
        rows.append(row)
    return rows


def _placement_bindings(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Read accepted placement wire; never compile or infer a source from prose."""
    runtime = data.get("runtimeProgram")
    if not isinstance(runtime, Mapping):
        return []
    item_ids = {e.get("id") for e in runtime.get("entities", [])
                if isinstance(e, Mapping) and e.get("kind") == "item_body"}
    rows = []
    for binding in runtime.get("bindings", []):
        if not isinstance(binding, Mapping):
            continue
        action = binding.get("usePolicy", {}).get("action", {})
        placement = action.get("placement", {})
        gate = placement.get("placedVfx") if isinstance(placement, Mapping) else None
        if (action.get("kind") == "place_item" and action.get("targetId") in item_ids
                and isinstance(gate, Mapping)):
            rows.append({"id": binding["id"], "entityId": action["targetId"],
                         "minFrameY": gate["minFrameY"], "maxFrameY": gate["maxFrameY"]})
    return sorted(rows, key=lambda r: r["id"])


def vfx_director_surface(data: Mapping[str, Any]) -> dict[str, Any]:
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    return {
        "schema": VFX_DIRECTOR_SCHEMA,
        "rendererKind": list(_FRESH_RENDERERS),
        "rendererRequirements": {k: copy.deepcopy(v) for k, v in _RENDERER_REQUIREMENTS.items() if k in _FRESH_RENDERERS},
        "rendererSemantics": {k: copy.deepcopy(v) for k, v in _RENDERER_SEMANTICS.items() if k in _FRESH_RENDERERS},
        "soundId": list(_SOUND_IDS),
        "sound": _sound_schema(),
        "heldRootVisibility": {
            field: CAPABILITY_REGISTRY["item_use"].params[field].description
            for field in ("hideUseGraphic",)
        },
        "colorPolicy": "Local RGB bytes, opacity separate. nativeDust/nativeLight own common color; spriteElement/texturedPath own colorProfile, shape/libraryParticle own colorStart/colorEnd, historyTrail owns trail.color. Sound/camera and nested-color renderers forbid common color. No prose-based palette selection.",
        "anchor": list(_ANCHORS),
        "blend": list(_BLENDS),
        "layer": list(_LAYERS),
        "numericRanges": {
            "duration": [1, 120], "alpha": [0.0, 1.0],
            "startTick": [0, 120], "repeatEvery": [0, 120],
        },
        "texturedPathSources": _textured_path_sources(data),
        "textureDependencyTuples": {
            "item": "existing accepted item image; assetId empty",
            "entity": "same exact entity baked_sprite/reuse_item_icon image; assetId empty; no_asset/runtime_geometry forbidden",
            "asset": "exact declared VFX asset ID; no compensating artwork for a bad reference",
        },
        "entityTextureSources": _entity_texture_sources(data),
        "bodyPresentation": _body_presentation(data),
        "maxSlots": max(0, min(12, int(config.VFX_LLM_DIRECTOR_MAX_SLOTS))),
        "runtimePairs": _allowed_pairs(data),
        "placementBindings": _placement_bindings(data),
        "runtimeVisualRoles": runtime_visual_roles(data),
    }
