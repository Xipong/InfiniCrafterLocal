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
    _CADENCE_ONLY_RENDERERS,
    _COLORLESS_RENDERERS,
    _FRESH_RENDERERS,
    _FRESH_VFX_NUMERIC_DESCRIPTIONS,
    _LAYERS,
    _PARTICLES,
    _RENDERER_REQUIREMENTS,
    _RENDERER_UNUSED_FIELDS,
    _RENDERERS,
    _SOUND_IDS,
    _TEXTURE_ROLES,
    _VFX_NUMERIC_DESCRIPTIONS,
    SPRITE_TEXTURE_RENDERERS,
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
from infini_local.core.visual_contract_schema import SPRITE_CANVAS_SIZES


def _impact_sprite_background_rule() -> str:
    from infini_local.core.images.contracts import sprite_background_positive_clause

    return (
        "The final impact PNG has a transparent background; describe the raw image "
        + sprite_background_positive_clause()
        + ". Local postprocess owns final alpha; do not confuse raw background with final transparency."
    )


def _director_schema(data: Mapping[str, Any], *, include_legacy: bool = False) -> dict[str, Any]:
    renderers = _RENDERERS if include_legacy else _FRESH_RENDERERS
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
            "textureRole": {
                "type": "string", "enum": list(_TEXTURE_ROLES),
                "description": (
                    "PNG selector for " + ", ".join(renderer for renderer in renderers if renderer in SPRITE_TEXTURE_RENDERERS) + ": "
                    "item=accepted item PNG; entity=bound entity baked_sprite/reuse_item_icon PNG "
                    "(no_asset/runtime_geometry cannot supply one); impact=same-entity impactSprite producer "
                    "(required companion slot for other sprite renderers); none invalid for sprites. "
                    "Every non-sprite renderer forbids this common field. spriteElement and texturedPath "
                    "consume only their explicit nested texture selector and textureDependencyTuples."
                ),
            },
            "anchor": {"type": "string", "enum": list(_ANCHORS), "description": "Primitive/cue/event placement: self/field=bound entity center; owner=active owner center; tip/tipHistory=projectile geometric tip (item uses engine itemLocation); velocity=center with motion axis; hitPoint=captured event point, NPC center for item hit/crit. Item hitPoint without a captured point is silent. Projectile event anchors and sprite pose are frozen at emission and carried through the relay, including after source removal; unavailable owner is silent. History renderers use their named center/tip histories instead of relocating the path."},
            "blend": {"type": "string", "enum": list(_BLENDS)},
            "layer": {"type": "string", "enum": list(_LAYERS)},
            "particleSystemId": {"type": "string", "enum": list(_PARTICLES), "description": "Exact Terraria.ID.DustID member, separate from ParticleLibrary instances: GemDiamond, TintableDustLighted, Glass, Smoke, Electric. none suppresses particles, not independently selected primitive/sprite/light/sound rendering."},
            "scale": {"type": "number", "minimum": 0.15, "maximum": 5.0},
            "density": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "duration": {"type": "integer", "minimum": 1, "maximum": 120},
            "alpha": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "spread": {"type": "number", "minimum": 0.0, "maximum": 2.0},
            "startTick": {"type": "integer", "minimum": 0, "maximum": 120},
            "repeatEvery": {"type": "integer", "minimum": 0, "maximum": 120},
            "spritePrompt": {"type": "string", "maxLength": 1400, "description": _impact_sprite_background_rule()},
            "spriteCanvasSize": {"type": "integer", "enum": list(SPRITE_CANVAS_SIZES), "description": "Exact final square impact PNG canvas in pixels, independent of gameplay hitbox or world scale; only impactSprite owns this request."},
            "spriteNegativePrompt": {"type": "string", "maxLength": 700},
            "color": rgb_schema(),
            "element": element_schema(include_legacy=include_legacy),
            "shape": shape_schema(persisted_wire=include_legacy),
            "geometry": contour_schema(),
            "trail": history_schema(),
            "nativeEffect": native_effect_schema(),
            "dust": native_dust_schema(persisted_wire=include_legacy),
            "light": native_light_schema(),
            "path": path_schema(),
            "screenShake": screen_shake_schema(),
            "particle": library_particle_schema(include_legacy=include_legacy),
            "sound": _sound_schema(),
            "soundId": {"type": "string", "enum": list(_SOUND_IDS), "description": "Exact Terraria.ID.SoundID member, selected independently of entity kind, item name, useStyle or damage class. General sample palette, no weapon presets. Only soundCue may carry it; every soundCue requires an explicit selection and complete sound playback controls in Director output and persisted wire. No absent/unknown/null replacement."},
        },
        "required": ["id", "entityId", "event", "rendererKind", "anchor"],
    }
    slot["allOf"] = [
        {
            "if": {"properties": {"rendererKind": {"const": renderer}}, "required": ["rendererKind"]},
            "then": {"properties": {field: {"const": value} for field, value in required.items()}},
        }
        for renderer, required in _RENDERER_REQUIREMENTS.items()
    ]
    slot["allOf"].append({
        "if": {"properties": {"rendererKind": {"enum": [r for r in renderers if r not in {"shape", "contour"}]}}, "required": ["rendererKind"]},
        "then": {"properties": {"duration": {"minimum": 3}}},
    })
    slot["allOf"].append({
        "if": {"required": ["placementBindingId"]},
        "then": {"properties": {"event": {"const": "periodic"}, "anchor": {"const": "self"},
            "rendererKind": {"enum": ["spriteElement", "libraryParticle", "nativeLight"] + (["lightCue"] if include_legacy else [])},
            "repeatEvery": {"minimum": 1}}},
    })
    slot["allOf"].extend({
        "if": {"properties": {"placementBindingId": {"const": row["id"]}}, "required": ["placementBindingId"]},
        "then": {"properties": {"entityId": {"const": row["entityId"]}}},
    } for row in _placement_bindings(data))
    branch_fields = set().union(*_RENDERER_UNUSED_FIELDS.values())
    branch_fields.add("startTick")
    slot["allOf"].extend({
        "if": {"properties": {"rendererKind": {"const": renderer}}, "required": ["rendererKind"]},
        "then": {
            "required": sorted(branch_fields - _RENDERER_UNUSED_FIELDS.get(renderer, frozenset())
                               - ({"startTick", "repeatEvery", "density"} if renderer in _CADENCE_ONLY_RENDERERS else set())),
            "properties": {field: {"enum": []} for field in sorted(_RENDERER_UNUSED_FIELDS.get(renderer, ()))},
        },
    } for renderer in renderers)
    runtime = data.get("runtimeProgram")
    entities = runtime.get("entities") if isinstance(runtime, Mapping) else []
    item_ids = [row["id"] for row in entities or [] if isinstance(row, Mapping) and row.get("kind") == "item_body" and isinstance(row.get("id"), str)]
    slot["allOf"].extend(material_slot_clauses(item_ids, [r for r in renderers if r not in MATERIAL_RENDERERS], events, _textured_path_sources(data)))
    slot["allOf"].extend(shape_slot_clauses(item_ids, list(renderers), events))
    slot["allOf"].extend(contour_slot_clauses(item_ids, list(renderers), events))
    slot["allOf"].extend(contour_texture_clauses(_entity_texture_sources(data, include_legacy=include_legacy)))
    slot["allOf"].extend(history_slot_clauses(item_ids, list(renderers), events))
    use = runtime.get("itemUse") if isinstance(runtime, Mapping) else None
    if isinstance(use, Mapping) and use.get("hideUseGraphic"):
        slot["allOf"].append({
            "if": {"properties": {"entityId": {"enum": item_ids}}, "required": ["entityId"]},
            "then": {"properties": {"rendererKind": {"enum": [r for r in renderers if r != "historyTrail"]}}},
        })
    slot["allOf"].extend(history_texture_clauses(_entity_texture_sources(data, include_legacy=include_legacy)))
    slot["allOf"].extend(native_effect_slot_clauses(item_ids, list(renderers), events))
    slot["allOf"].extend(native_cue_slot_clauses(item_ids, list(renderers), events))
    slot["allOf"].extend(material_texture_clauses(_entity_texture_sources(data, include_legacy=include_legacy)))
    slot["allOf"].extend([
        {"if": {"properties": {"rendererKind": {"const": "impactSprite"}}, "required": ["rendererKind"]},
         "then": {"required": ["spritePrompt", "spriteNegativePrompt", "spriteCanvasSize"]}},
        {"if": {"properties": {"rendererKind": {"enum": [renderer for renderer in renderers if renderer != "impactSprite"]}}, "required": ["rendererKind"]},
         "then": {"properties": {field: {"enum": []} for field in ("spritePrompt", "spriteNegativePrompt", "spriteCanvasSize")}}},
        {"if": {"properties": {"rendererKind": {"enum": list(_CADENCE_ONLY_RENDERERS)}, "event": {"enum": [event for event in events if event != "periodic"]}}, "required": ["rendererKind", "event"]},
         "then": {"properties": {field: {"enum": []} for field in ("startTick", "repeatEvery", "density")}}},
        {"if": {"properties": {"rendererKind": {"enum": list(_COLORLESS_RENDERERS)}}, "required": ["rendererKind"]},
         "then": {"properties": {"color": {"enum": []}}}},
        {"if": {"properties": {"rendererKind": {"enum": [r for r in renderers if r not in _COLORLESS_RENDERERS]}}, "required": ["rendererKind"]},
         "then": {"required": ["color"]}},
    ])
    # Early-return cues have only caller-consumed cadence; events never schedule here.
    slot["allOf"].extend([
        {"if": {"properties": {"rendererKind": {"enum": list(_CADENCE_ONLY_RENDERERS)}, "event": {"const": "periodic"}}, "required": ["rendererKind", "event"]},
         "then": {"required": ["repeatEvery"]}},
        {"if": {"properties": {"rendererKind": {"enum": list(_CADENCE_ONLY_RENDERERS)}, "event": {"const": "periodic"}, "entityId": {"enum": item_ids}}, "required": ["rendererKind", "event", "entityId"]},
         "then": {"properties": {field: {"enum": []} for field in ("startTick", "density")}}},
        {"if": {"properties": {"rendererKind": {"enum": list(_CADENCE_ONLY_RENDERERS)}, "event": {"const": "periodic"}, "entityId": {"enum": [entity_id for entity_id in entity_ids if entity_id not in item_ids]}}, "required": ["rendererKind", "event", "entityId"]},
         "then": {
             "required": ["startTick"],
             "allOf": [
                 {"if": {"properties": {"repeatEvery": {"const": 0}}, "required": ["repeatEvery"]}, "then": {"required": ["density"]}},
                 {"if": {"properties": {"repeatEvery": {"minimum": 1}}, "required": ["repeatEvery"]}, "then": {"properties": {"density": {"enum": []}}}},
             ],
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
    if not include_legacy:
        for payload in ("element", "path", "trail"):
            texture = slot["properties"][payload]["properties"]["texture"]
            texture["required"].append("uv")
            texture["properties"]["source"]["enum"] = ["item", "entity", "asset", "library"]
            texture["description"] = "Exact accepted item/entity PNG, declared asset ID, or registered library texture ID (no PNG generation). No paths, URLs or cross-entity guesses; UV and blend remain literal."
            for clause in texture["allOf"]:
                source_gate = clause["if"]["properties"]["source"]
                if "enum" in source_gate:
                    source_gate["enum"] = ["item", "entity"]
        # Old artistic presets are persisted readers only, not hidden fresh options.
        for field in ("spritePrompt", "spriteNegativePrompt", "spriteCanvasSize", "textureRole", "particleSystemId", "scale", "spread", "density"):
            slot["properties"].pop(field, None)
        filtered = []
        for clause in slot["allOf"]:
            kind = clause.get("if", {}).get("properties", {}).get("rendererKind", {})
            if "const" in kind and kind["const"] not in renderers:
                continue
            if "enum" in kind:
                kind["enum"] = [r for r in kind["enum"] if r in renderers]
                if not kind["enum"]:
                    continue
            filtered.append(clause)
        slot["allOf"] = filtered
        slot["allOf"].append({
            "if": {"properties": {"rendererKind": {"const": "soundCue"}, "event": {"const": "periodic"}}, "required": ["rendererKind", "event"]},
            "then": {"properties": {"repeatEvery": {"minimum": 1}}},
        })
        # Native Dust is an independently authored slot, never shape/trail accompaniment.
        # No fresh renderer owns the legacy particleSystemId field.
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
            slot["properties"][field]["description"] = (_VFX_NUMERIC_DESCRIPTIONS if include_legacy else _FRESH_VFX_NUMERIC_DESCRIPTIONS)[field]
    return schema


def vfx_schema_instruction_paths(*, repair: bool, schema: Mapping[str, Any] | None = None) -> dict[str, tuple[str | int, ...]]:
    """Owner-declared invariant grammar; runtime compatibility clauses stay USER.

    Only the initial rendererRequirements clauses have fixed positions: the
    subsequent material/event/texture clauses depend on the accepted roster.
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
