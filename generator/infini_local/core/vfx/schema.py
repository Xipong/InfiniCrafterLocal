"""Canonical VFX Director grammar and invariant schema instruction paths."""
from __future__ import annotations

from typing import Any, Mapping

from infini_local.core.vfx import config
from infini_local.core.vfx.contours import (
    contour_schema,
    contour_slot_clauses,
    contour_texture_clauses,
)
from infini_local.core.vfx.contract import (
    _ANCHORS,
    _BLENDS,
    _COLORLESS_RENDERERS,
    _LAYERS,
    _RENDERER_UNUSED_FIELDS,
    _RENDERERS,
    _SOUND_IDS,
    _VFX_NUMERIC_DESCRIPTIONS,
    VFX_DIRECTOR_SCHEMA,
    _sound_schema,
)
from infini_local.core.vfx.history import (
    history_schema,
    history_slot_clauses,
    history_texture_clauses,
)
from infini_local.core.vfx.materials import (
    MATERIAL_RENDERERS,
    asset_schema,
    element_schema,
    library_particle_schema,
    material_slot_clauses,
    material_texture_clauses,
    path_schema,
    rgb_schema,
    screen_shake_schema,
)
from infini_local.core.vfx.native_cues import (
    native_cue_slot_clauses,
    native_dust_schema,
    native_light_schema,
)
from infini_local.core.vfx.native_effects import (
    native_effect_schema,
    native_effect_slot_clauses,
)
from infini_local.core.vfx.shapes import (
    shape_schema,
    shape_slot_clauses,
)
from infini_local.core.vfx.surface import (
    _allowed_pairs,
    _entity_texture_sources,
    _placement_bindings,
    _textured_path_sources,
)


def _director_schema(data: Mapping[str, Any]) -> dict[str, Any]:
    renderers = _RENDERERS
    pairs = _allowed_pairs(data)
    entity_ids = sorted({row["entityId"] for row in pairs})
    events = sorted({row["event"] for row in pairs})
    slot: dict[str, Any] = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
            "entityId": {"type": "string", "enum": entity_ids},
            "placementBindingId": {"type": "string", "enum": [r["id"] for r in _placement_bindings(data)],
                "description": "Optional exact accepted placement binding, not held/equipped item. Omit for unchanged item/projectile behavior. Only periodic/self spriteElement/libraryParticle/nativeLight. Gate reads top-left native TileFrameY; footprint center is self, +forward right/+side down, velocity zero. Fresh activation after gate off; world particles may finish bounded lifetime."},
            "event": {"type": "string", "enum": events},
            "rendererKind": {
                "type": "string", "enum": list(renderers),
                "description": "Select the renderer with its exact payload. nativeLight emits world lighting, not a drawn glow sprite or trail; presentation never changes gameplay.",
            },
            "anchor": {"type": "string", "enum": list(_ANCHORS), "description": "Primitive/cue/event placement: self/field=bound entity center; owner=active owner center; tip/tipHistory=projectile geometric tip (item uses engine itemLocation); velocity=center with motion axis; hitPoint=captured event point, NPC center for item hit/crit. Item hitPoint without a captured point is silent. Projectile event anchors and sprite pose are frozen at emission and carried through the relay, including after source removal; unavailable owner is silent. History renderers use their named center/tip histories instead of relocating the path."},
            "blend": {"type": "string", "enum": list(_BLENDS)},
            "layer": {"type": "string", "enum": list(_LAYERS)},
            "duration": {"type": "integer", "minimum": 1, "maximum": 120},
            "alpha": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "startTick": {"type": "integer", "minimum": 0, "maximum": 120},
            "repeatEvery": {"type": "integer", "minimum": 0, "maximum": 120},
            "color": rgb_schema(),
            "element": element_schema(),
            "shape": shape_schema(),
            "geometry": contour_schema(),
            "trail": history_schema(),
            "nativeEffect": native_effect_schema(),
            "dust": native_dust_schema(),
            "light": native_light_schema(),
            "path": path_schema(),
            "screenShake": screen_shake_schema(),
            "particle": library_particle_schema(),
            "sound": _sound_schema(),
            "soundId": {"type": "string", "enum": list(_SOUND_IDS), "description": "Exact Terraria.ID.SoundID member, selected independently of entity kind, item name, useStyle or damage class. General sample palette, no weapon presets. Only soundCue may carry it; every soundCue requires an explicit selection and complete sound playback controls in Director output and persisted wire. No absent/unknown/null replacement."},
        },
        "required": ["id", "entityId", "event", "rendererKind", "anchor"],
    }
    slot["allOf"] = []
    slot["allOf"].append({
        "if": {"properties": {"rendererKind": {"enum": [r for r in renderers if r not in {"shape", "contour"}]}}, "required": ["rendererKind"]},
        "then": {"properties": {"duration": {"minimum": 3}}},
    })
    slot["allOf"].append({
        "if": {"required": ["placementBindingId"]},
        "then": {"properties": {"event": {"const": "periodic"}, "anchor": {"const": "self"},
            "rendererKind": {"enum": ["spriteElement", "libraryParticle", "nativeLight"]},
            "repeatEvery": {"minimum": 1}}},
    })
    slot["allOf"].extend({
        "if": {"properties": {"placementBindingId": {"const": row["id"]}}, "required": ["placementBindingId"]},
        "then": {"properties": {"entityId": {"const": row["entityId"]}}},
    } for row in _placement_bindings(data))
    branch_fields = {"startTick", "duration", "repeatEvery", "alpha", "blend", "layer"}
    slot["allOf"].extend({
        "if": {"properties": {"rendererKind": {"const": renderer}}, "required": ["rendererKind"]},
        "then": {
            "required": sorted(branch_fields - _RENDERER_UNUSED_FIELDS.get(renderer, frozenset())
                               - ({"startTick", "repeatEvery"} if renderer == "soundCue" else set())),
            "properties": {field: {"enum": []} for field in sorted(_RENDERER_UNUSED_FIELDS.get(renderer, ()))},
        },
    } for renderer in renderers)
    runtime = data.get("runtimeProgram")
    entities = runtime.get("entities") if isinstance(runtime, Mapping) else []
    item_ids = [row["id"] for row in entities or [] if isinstance(row, Mapping) and row.get("kind") == "item_body" and isinstance(row.get("id"), str)]
    slot["allOf"].extend(material_slot_clauses(item_ids, [r for r in renderers if r not in MATERIAL_RENDERERS], events, _textured_path_sources(data)))
    slot["allOf"].extend(shape_slot_clauses(item_ids, list(renderers), events))
    slot["allOf"].extend(contour_slot_clauses(item_ids, list(renderers), events))
    slot["allOf"].extend(contour_texture_clauses(_entity_texture_sources(data)))
    slot["allOf"].extend(history_slot_clauses(item_ids, list(renderers), events))
    use = runtime.get("itemUse") if isinstance(runtime, Mapping) else None
    if isinstance(use, Mapping) and use.get("hideUseGraphic"):
        slot["allOf"].append({
            "if": {"properties": {"entityId": {"enum": item_ids}}, "required": ["entityId"]},
            "then": {"properties": {"rendererKind": {"enum": [r for r in renderers if r != "historyTrail"]}}},
        })
    slot["allOf"].extend(history_texture_clauses(_entity_texture_sources(data)))
    slot["allOf"].extend(native_effect_slot_clauses(item_ids, list(renderers), events))
    slot["allOf"].extend(native_cue_slot_clauses(item_ids, list(renderers), events))
    slot["allOf"].extend(material_texture_clauses(_entity_texture_sources(data)))
    slot["allOf"].extend([
        {"if": {"properties": {"rendererKind": {"const": "soundCue"}, "event": {"enum": [event for event in events if event != "periodic"]}}, "required": ["rendererKind", "event"]},
         "then": {"properties": {field: {"enum": []} for field in ("startTick", "repeatEvery")}}},
        {"if": {"properties": {"rendererKind": {"enum": list(_COLORLESS_RENDERERS)}}, "required": ["rendererKind"]},
         "then": {"properties": {"color": {"enum": []}}}},
        {"if": {"properties": {"rendererKind": {"enum": [r for r in renderers if r not in _COLORLESS_RENDERERS]}}, "required": ["rendererKind"]},
         "then": {"required": ["color"]}},
    ])
    # Early-return cues have only caller-consumed cadence; events never schedule here.
    slot["allOf"].extend([
        {"if": {"properties": {"rendererKind": {"const": "soundCue"}, "event": {"const": "periodic"}}, "required": ["rendererKind", "event"]},
         "then": {"required": ["repeatEvery"]}},
        {"if": {"properties": {"rendererKind": {"const": "soundCue"}, "event": {"const": "periodic"}, "entityId": {"enum": item_ids}}, "required": ["rendererKind", "event", "entityId"]},
         "then": {"properties": {field: {"enum": []} for field in ("startTick",)}}},
        {"if": {"properties": {"rendererKind": {"const": "soundCue"}, "event": {"const": "periodic"}, "entityId": {"enum": [entity_id for entity_id in entity_ids if entity_id not in item_ids]}}, "required": ["rendererKind", "event", "entityId"]},
         "then": {
             "required": ["startTick"],
         }},
    ])
    slot["allOf"].append({
        "if": {"properties": {"rendererKind": {"const": "soundCue"}}, "required": ["rendererKind"]},
        "then": {"required": ["soundId", "sound"]},
    })
    slot["allOf"].append({
        "if": {"properties": {"rendererKind": {"enum": [renderer for renderer in renderers if renderer != "soundCue"]}}, "required": ["rendererKind"]},
        "then": {"properties": {field: {"enum": []} for field in ("soundId", "sound")}},
    })
    slot["allOf"].extend([
        {"if": {"properties": {"rendererKind": {"const": "libraryParticle"}}, "required": ["rendererKind"]},
         "then": {"required": ["particle"]}},
        {"if": {"properties": {"rendererKind": {"enum": [renderer for renderer in renderers if renderer != "libraryParticle"]}}, "required": ["rendererKind"]},
         "then": {"properties": {"particle": {"enum": []}}}},
        {"if": {"properties": {"rendererKind": {"const": "libraryParticle"}, "event": {"const": "periodic"}}, "required": ["rendererKind", "event"]},
         "then": {"properties": {"repeatEvery": {"minimum": 1}}}},
        {"if": {"properties": {"rendererKind": {"const": "libraryParticle"}, "event": {"enum": [event for event in events if event != "periodic"]}}, "required": ["rendererKind", "event"]},
         "then": {"properties": {"repeatEvery": {"const": 0}}}},
        {"if": {"properties": {"rendererKind": {"const": "libraryParticle"}, "event": {"const": "periodic"}, "entityId": {"enum": item_ids}}, "required": ["rendererKind", "event", "entityId"]},
         "then": {"properties": {"startTick": {"const": 0}}}},
        {"if": {"properties": {"rendererKind": {"const": "screenShakeCue"}}, "required": ["rendererKind"]},
         "then": {"required": ["screenShake"], "properties": {"event": {"enum": [event for event in events if event != "periodic"]}}}},
        {"if": {"properties": {"rendererKind": {"enum": [renderer for renderer in renderers if renderer != "screenShakeCue"]}}, "required": ["rendererKind"]},
         "then": {"properties": {"screenShake": {"enum": []}}}},
    ])
    slot["allOf"].append({
        "if": {"properties": {"rendererKind": {"const": "soundCue"}, "event": {"const": "periodic"}}, "required": ["rendererKind", "event"]},
        "then": {"properties": {"repeatEvery": {"minimum": 1}}},
    })
    schema: dict[str, Any] = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "schema": {"const": VFX_DIRECTOR_SCHEMA},
            "slots": {"type": "array", "items": slot, "minItems": 0, "maxItems": max(0, min(12, int(config.VFX_LLM_DIRECTOR_MAX_SLOTS)))},
            "assets": {"type": "array", "items": asset_schema(), "maxItems": 16, "description": "Optional independent VFX ingredients, declared once and reused by exact ID. Absence requests none; null invalid. Every new request must be used. Image pipeline alone writes execution metadata."},
        },
        "required": ["schema", "slots"],
    }
    for field in slot["properties"]:
        if field in _VFX_NUMERIC_DESCRIPTIONS:
            slot["properties"][field]["description"] = _VFX_NUMERIC_DESCRIPTIONS[field]
    return schema


def vfx_schema_instruction_paths(*, repair: bool, schema: Mapping[str, Any] | None = None) -> dict[str, tuple[str | int, ...]]:
    """Owner-declared invariant grammar; entity/event clauses stay USER.

    Material/event/texture clauses depend on the accepted roster.
    No recursive field matching or inferred invariant subtrees are used.
    """
    slot = ("properties", "slotsUpsert" if repair else "slots", "items")
    fields = (
        "id", "rendererKind", "anchor", "blend", "layer", "duration",
        "alpha", "startTick", "repeatEvery", "soundId", "color",
    )
    paths: dict[str, tuple[str | int, ...]] = {"slot_" + field: slot + ("properties", field) for field in fields}
    paths.update({field: slot + ("properties", field)
                  for field in ("element", "path", "screenShake", "particle", "sound", "shape", "trail", "dust", "light", "nativeEffect")})
    paths["asset"] = ("properties", "assetsUpsert" if repair else "assets", "items")
    if schema is not None:
        present = {}
        for name, path in paths.items():
            node: Any = schema
            try:
                for key in path:
                    node = node[key]
            except (KeyError, IndexError, TypeError):
                continue
            # Scoped nodes contain request-specific frozen values/IDs. They
            # must never be promoted into the invariant developer vocabulary.
            if repair and ("const" in node or name.startswith("rendererRule_")
                           or "properties" in node):
                continue
            present[name] = path
        return present
    return paths


def vfx_director_schema(data: Mapping[str, Any]) -> dict[str, Any]:
    """Public generated schema owned by the VFX Director contract module."""

    return _director_schema(data)
