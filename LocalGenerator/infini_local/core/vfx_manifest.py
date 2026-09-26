from __future__ import annotations

"""Finite VFX Director contract over exact runtime entity/event pairs.

Gameplay has already been accepted before this module runs.  VFX slots may only
bind presentation to an existing ``entityId + event`` pair and cannot add or
change gameplay, entities, hitboxes, damage, movement, or lifecycle.
"""

import copy
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Callable, Mapping

from infini_local.core.errors import PlannerUnavailable
from infini_local.core.llm_stage_messages import stage_chat_message
from infini_local.core.repair_merge import merge_frozen_subtree
from infini_local.core.runtime_authoring import runtime_event_inventory, runtime_visual_roles, strict_schema_errors
from infini_local.core.vfx_manifest_config import (
    VFX_LLM_DIRECTOR_MAX_SLOTS,
    VFX_LLM_DIRECTOR_MAX_TOKENS,
    VFX_LLM_REPAIR_TEMPERATURE,
    VFX_LLM_DIRECTOR_TEMPERATURE,
    VFX_LLM_DIRECTOR_TIMEOUT,
)


VFX_MANIFEST_SCHEMA = "infini.vfx.runtime-events.v15"
VFX_DIRECTOR_SCHEMA = "infini.vfx-director.runtime-events.v2"
VFX_REPAIR_PATCH_SCHEMA = "infini.vfx-repair-patch.runtime-events.v1"
# Exact pairs/roles and the output schema depend on the accepted runtime program.
VFX_PROMPT_STATIC_KEYS = ("schema", "rules")
VFX_REPAIR_PROMPT_STATIC_KEYS = ("task", "rules")


@dataclass(frozen=True)
class MalformedVfxDirectorOutput:
    raw_text: str
    error: str


_RENDERERS = (
    "projectileAfterimage", "spriteStampTrail", "historyRibbon", "tipTrail",
    "ghostArc", "wavyStrip", "beamLine", "fieldPulse", "orbitingMotes",
    "actorAfterimage", "impactRing", "impactSprite", "childMotes",
    "lightCue", "soundCue",
)
SPRITE_TEXTURE_RENDERERS = frozenset({
    "projectileAfterimage", "spriteStampTrail", "actorAfterimage", "impactSprite",
})
# Existing runtime invariants, shared by the model-facing surface/schema and
# semantic diagnostics. These constrain authored fields; they never fill them.
_RENDERER_REQUIREMENTS = {
    "lightCue": {"channel": "light", "lane": "cue"},
    "soundCue": {"channel": "sound", "lane": "cue"},
    "impactSprite": {"textureRole": "impact"},
}
_BACKENDS = ("Auto", "Realtime", "Primitive", "Sprite", "Particle")
_TEXTURE_ROLES = ("item", "entity", "projectile", "field", "impact", "none")
_ANCHORS = ("self", "owner", "tip", "tipHistory", "hitPoint", "velocity", "field")
_CHANNELS = ("motionTrail", "coreGlow", "ambientParticles", "impactShape", "impactParticles", "decaySmoke", "light", "sound")
_LANES = ("primary", "support", "accent", "ornament", "cue")
_EMISSIONS = ("wake", "orbit", "residue", "burst", "cone", "ring", "spiral", "none")
_BLENDS = ("alpha", "additive")
_LAYERS = ("BeforeProjectiles", "AfterProjectiles")
_PARTICLES = ("dust", "pl:glow", "pl:shard", "pl:smoke", "pl:spark", "none")
_BUDGET_CLASSES = ("tiny", "small", "normal", "large", "signature")

# These are annotations on the existing wire fields, not a conversion or an
# alternative semantic contract. Repair reuses the ordinary field schemas.
_VFX_NUMERIC_DESCRIPTIONS = {
    "effectMagnitude": "Engine units: Retained presentation metadata; currently no renderer consumer. Not a physical intensity or budget multiplier.",
    "rhythm": "Engine units: Retained motif metadata; currently no renderer consumer. Not beats per minute or a time unit.",
    "chaos": "Engine units: Retained motif metadata; currently no renderer consumer. Not a probability.",
    "scale": "Engine units: Renderer-specific coefficient (1 is nominal): sprite trail draw scale = max(0.05, projectile.scale * scale); primitive thickness max(1, 2*scale), beam length max(20, 48*scale), cross radius max(4, 9*scale); light strength clamp(0.22*scale, 0.04, 1.2) on projectile or clamp(0.2*scale, 0.04, 1.2) on item, then client multiplier; dust size clamp(scale, 0.2, 3); impactSprite draw scale further clamped. Not a universal size in pixels.",
    "density": "Engine units: Renderer-specific count/cadence coefficient, not particles per world tick: projectile periodic repeatEvery=0 uses clamp(14-round(8*density), 4, 18) world ticks; projectile impactRing/childMotes count clamp(2+round(8*density), 2, 10), item dust count clamp(1+round(7*density), 1, 8), subject to client scaling and budget.",
    "duration": "impactSprite lifetime in world ticks only; detached sprite fades linearly with elapsed world ticks and is removed at duration. Other renderer kinds do not consume duration.",
    "alpha": "Engine units: Renderer-specific opacity/volume coefficient: projectile sprite/primitive draw color multiplied by alpha; impactSprite fades from alpha over its lifetime; sound volume clamp(alpha, 0.05, 1). Projectile and item dust color paths do not use slot alpha; not universal opacity.",
    "spread": "Engine units: Particle-speed coefficient, not angle or radians: projectile dust speed clamp(0.35+1.7*spread, 0.2, 4) plus inherited velocity; item dust velocity sampled from circular radii 1+spread. Angle is selected separately; not one common physical speed.",
    "jitter": "Engine units: Retained metadata; currently no renderer consumer. No pixel, angle, or time unit.",
    "fadeIn": "Engine units: Retained metadata; currently no renderer consumer. Not seconds, world ticks, or a lifetime fraction.",
    "fadeOut": "Engine units: Retained metadata; currently no renderer consumer. Not seconds, world ticks, or a lifetime fraction; impactSprite has its own fixed linear fade.",
    "budgetWeight": "Engine units: Retained weighting metadata; currently no renderer consumer. Does not multiply an enforced particle/draw budget.",
    "signatureWeight": "Engine units: Retained weighting metadata; currently no renderer consumer. Not an enforced budget fraction.",
    "visualCost": "Engine units: Retained cost metadata; currently no renderer consumer. Not draw calls or an enforced budget fraction.",
    "startTick": "Projectile periodic only: initial gate on per-projectile state world tick (one increment per distinct GameUpdateCount); 0 means no initial gate. Item periodic and event paths ignore startTick.",
    "repeatEvery": "Periodic cadence in world ticks only; 0 means automatic, not zero ticks: projectile periodic uses clamp(14-round(8*density), 4, 18), item periodic uses 10. Positive values use projectile state ticks or item global update ticks with slot-seed phase; event paths ignore repeatEvery.",
}


def _stage_accounting(data: dict[str, Any]) -> dict[str, int]:
    debug = data.setdefault("debug", {})
    accounting = debug.setdefault("llmStageAccounting", {})
    for key in (
        "gameplayAuthorCalls", "gameplayRepairCalls", "visualDirectorCalls",
        "visualRepairCalls", "vfxDirectorCalls", "vfxRepairCalls",
    ):
        accounting.setdefault(key, 0)
    return accounting


def _seed(*parts: Any) -> int:
    digest = hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "little") & 0x7FFFFFFF


def _allowed_pairs(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in runtime_event_inventory(data):
        if not isinstance(row, Mapping):
            continue
        pair = (str(row.get("entityId") or ""), str(row.get("event") or ""))
        if not all(pair) or pair in seen:
            continue
        seen.add(pair)
        rows.append({"entityId": pair[0], "event": pair[1]})
    return sorted(rows, key=lambda row: (row["entityId"], row["event"]))


def vfx_director_surface(data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": VFX_DIRECTOR_SCHEMA,
        "rendererKind": list(_RENDERERS),
        "rendererRequirements": copy.deepcopy(_RENDERER_REQUIREMENTS),
        "backend": list(_BACKENDS),
        "textureRole": list(_TEXTURE_ROLES),
        "particleRole": list(_TEXTURE_ROLES),
        "anchor": list(_ANCHORS),
        "channel": list(_CHANNELS),
        "lane": list(_LANES),
        "emissionMode": list(_EMISSIONS),
        "blend": list(_BLENDS),
        "layer": list(_LAYERS),
        "particleSystemId": list(_PARTICLES),
        "visualBudgetClass": list(_BUDGET_CLASSES),
        "numericRanges": {
            "effectMagnitude": [0.0, 1.0], "scale": [0.15, 5.0],
            "density": [0.0, 1.0], "duration": [3, 120], "alpha": [0.0, 1.0],
            "spread": [0.0, 2.0], "jitter": [0.0, 1.5], "fadeIn": [0.0, 0.8],
            "fadeOut": [0.0, 0.8], "budgetWeight": [0.1, 4.0],
            "signatureWeight": [0.0, 1.0], "visualCost": [0.0, 1.0],
            "startTick": [0, 120], "repeatEvery": [0, 120],
        },
        "maxSlots": max(0, min(12, int(VFX_LLM_DIRECTOR_MAX_SLOTS))),
        "runtimePairs": _allowed_pairs(data),
        "runtimeVisualRoles": runtime_visual_roles(data),
    }


def _director_schema(data: Mapping[str, Any]) -> dict[str, Any]:
    pairs = _allowed_pairs(data)
    entity_ids = sorted({row["entityId"] for row in pairs})
    events = sorted({row["event"] for row in pairs})
    slot = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
            "entityId": {"type": "string", "enum": entity_ids},
            "event": {"type": "string", "enum": events},
            "rendererKind": {
                "type": "string", "enum": list(_RENDERERS),
                "description": "Select the renderer with the companion fields required by this slot's conditional clauses. lightCue emits world lighting, not a drawn glow sprite or trail. Sound/light cues use lane=cue, not a visual emphasis lane.",
            },
            "backend": {"type": "string", "enum": list(_BACKENDS)},
            "textureRole": {"type": "string", "enum": list(_TEXTURE_ROLES)},
            "particleRole": {"type": "string", "enum": list(_TEXTURE_ROLES)},
            "anchor": {"type": "string", "enum": list(_ANCHORS)},
            "channel": {"type": "string", "enum": list(_CHANNELS)},
            "lane": {"type": "string", "enum": list(_LANES)},
            "emissionMode": {"type": "string", "enum": list(_EMISSIONS)},
            "blend": {"type": "string", "enum": list(_BLENDS)},
            "layer": {"type": "string", "enum": list(_LAYERS)},
            "particleSystemId": {"type": "string", "enum": list(_PARTICLES)},
            "scale": {"type": "number", "minimum": 0.15, "maximum": 5.0},
            "density": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "duration": {"type": "integer", "minimum": 3, "maximum": 120},
            "alpha": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "spread": {"type": "number", "minimum": 0.0, "maximum": 2.0},
            "jitter": {"type": "number", "minimum": 0.0, "maximum": 1.5},
            "fadeIn": {"type": "number", "minimum": 0.0, "maximum": 0.8},
            "fadeOut": {"type": "number", "minimum": 0.0, "maximum": 0.8},
            "budgetWeight": {"type": "number", "minimum": 0.1, "maximum": 4.0},
            "signatureWeight": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "visualCost": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "startTick": {"type": "integer", "minimum": 0, "maximum": 120},
            "repeatEvery": {"type": "integer", "minimum": 0, "maximum": 120},
            "spritePrompt": {"type": "string", "maxLength": 1400},
            "spriteNegativePrompt": {"type": "string", "maxLength": 700},
        },
        "required": [
            "id", "entityId", "event", "rendererKind", "backend", "textureRole",
            "particleRole", "anchor", "channel", "lane", "emissionMode", "blend",
            "layer", "particleSystemId", "scale", "density", "duration", "alpha", "spread",
            "jitter", "fadeIn", "fadeOut", "budgetWeight", "signatureWeight",
            "visualCost", "startTick", "repeatEvery", "spritePrompt", "spriteNegativePrompt",
        ],
    }
    slot["allOf"] = [
        {
            "if": {"properties": {"rendererKind": {"const": renderer}}, "required": ["rendererKind"]},
            "then": {"properties": {field: {"const": value} for field, value in required.items()}},
        }
        for renderer, required in _RENDERER_REQUIREMENTS.items()
    ]
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "schema": {"const": VFX_DIRECTOR_SCHEMA},
            "effectMagnitude": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "visualBudgetClass": {"type": "string", "enum": list(_BUDGET_CLASSES)},
            "motif": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "element": {"type": "string", "minLength": 1, "maxLength": 48},
                    "shapeLanguage": {"type": "string", "minLength": 1, "maxLength": 96},
                    "motionLanguage": {"type": "string", "minLength": 1, "maxLength": 96},
                    "paletteRole": {"type": "string", "minLength": 1, "maxLength": 48},
                    "rhythm": {"type": "number", "minimum": 0.2, "maximum": 3.0},
                    "chaos": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["element", "shapeLanguage", "motionLanguage", "paletteRole", "rhythm", "chaos"],
            },
            "slots": {"type": "array", "items": slot, "minItems": 0, "maxItems": max(0, min(12, int(VFX_LLM_DIRECTOR_MAX_SLOTS)))},
        },
        "required": ["schema", "effectMagnitude", "visualBudgetClass", "motif", "slots"],
    }
    properties = schema["properties"]
    properties["effectMagnitude"]["description"] = _VFX_NUMERIC_DESCRIPTIONS["effectMagnitude"]
    for field in ("rhythm", "chaos"):
        properties["motif"]["properties"][field]["description"] = _VFX_NUMERIC_DESCRIPTIONS[field]
    for field in slot["properties"]:
        if field in _VFX_NUMERIC_DESCRIPTIONS:
            slot["properties"][field]["description"] = _VFX_NUMERIC_DESCRIPTIONS[field]
    return schema


def _number(value: Any, low: float, high: float, path: str, errors: list[dict[str, Any]], *, integer: bool = False) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append({"path": path, "message": "number required"})
        return int(low) if integer else low
    numeric = float(value)
    if numeric < low or numeric > high:
        errors.append({"path": path, "message": f"must be within [{low}, {high}]"})
    return int(value) if integer else numeric


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
    budget_class = str(raw.get("visualBudgetClass") or "")
    if budget_class not in _BUDGET_CLASSES:
        errors.append({"path": "$.visualBudgetClass", "message": "unsupported budget class"})
    magnitude = _number(raw.get("effectMagnitude"), 0.0, 1.0, "$.effectMagnitude", errors)
    raw_motif = raw.get("motif")
    motif = raw_motif if isinstance(raw_motif, Mapping) else {}
    if not isinstance(raw_motif, Mapping):
        errors.append({"path": "$.motif", "message": "object required"})
    motif_text: dict[str, str] = {}
    for field, maximum in {
        "element": 48,
        "shapeLanguage": 96,
        "motionLanguage": 96,
        "paletteRole": 48,
    }.items():
        value = motif.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            errors.append({"path": f"$.motif.{field}", "message": f"exact non-empty string of at most {maximum} chars required"})
        motif_text[field] = value if isinstance(value, str) else ""
    motif_rhythm = _number(motif.get("rhythm"), 0.2, 3.0, "$.motif.rhythm", errors)
    motif_chaos = _number(motif.get("chaos"), 0.0, 1.0, "$.motif.chaos", errors)
    slots = raw.get("slots")
    if not isinstance(slots, list):
        errors.append({"path": "$.slots", "message": "array required"})
        slots = []
    max_slots = max(0, min(12, int(VFX_LLM_DIRECTOR_MAX_SLOTS)))
    if len(slots) > max_slots:
        errors.append({"path": "$.slots", "message": f"at most {max_slots} slots"})
    seen_ids: set[str] = set()
    impact_sprite_entities: set[str] = set()
    impact_texture_consumers: list[tuple[int, str]] = []
    normalized_slots: list[dict[str, Any]] = []
    enum_fields = {
        "rendererKind": _RENDERERS, "backend": _BACKENDS, "textureRole": _TEXTURE_ROLES,
        "particleRole": _TEXTURE_ROLES, "anchor": _ANCHORS, "channel": _CHANNELS,
        "lane": _LANES, "emissionMode": _EMISSIONS, "blend": _BLENDS,
        "layer": _LAYERS,
        "particleSystemId": _PARTICLES,
    }
    number_fields = {
        "scale": (0.15, 5.0, False), "density": (0.0, 1.0, False),
        "duration": (3, 120, True), "alpha": (0.0, 1.0, False),
        "spread": (0.0, 2.0, False), "jitter": (0.0, 1.5, False),
        "fadeIn": (0.0, 0.8, False), "fadeOut": (0.0, 0.8, False),
        "budgetWeight": (0.1, 4.0, False), "signatureWeight": (0.0, 1.0, False),
        "visualCost": (0.0, 1.0, False), "startTick": (0, 120, True),
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
            value = str(slot.get(field) or "")
            if value not in values:
                errors.append({"path": f"{path}.{field}", "message": f"unsupported value {value!r}"})
            clean[field] = value
        for field, (low, high, integer) in number_fields.items():
            clean[field] = _number(slot.get(field), low, high, f"{path}.{field}", errors, integer=integer)
        sprite_prompt = str(slot.get("spritePrompt") or "")
        sprite_negative = str(slot.get("spriteNegativePrompt") or "")
        if clean["rendererKind"] == "impactSprite":
            if not sprite_prompt.strip():
                errors.append({"path": path + ".spritePrompt", "message": "impactSprite requires a dedicated non-empty transparent sprite prompt"})
            if clean["textureRole"] != _RENDERER_REQUIREMENTS["impactSprite"]["textureRole"]:
                errors.append({"path": path + ".textureRole", "message": "impactSprite requires textureRole=impact"})
            if entity_id in impact_sprite_entities:
                errors.append({"path": path + ".entityId", "message": "runtime wire supports at most one impactSprite asset per entity"})
            impact_sprite_entities.add(entity_id)
        elif sprite_prompt or sprite_negative:
            errors.append({"path": path + ".spritePrompt", "message": "sprite prompts are owned only by impactSprite slots and must be empty otherwise"})
        clean["spritePrompt"] = sprite_prompt
        clean["spriteNegativePrompt"] = sprite_negative
        for renderer in ("soundCue", "lightCue"):
            required = _RENDERER_REQUIREMENTS[renderer]
            if clean["rendererKind"] == renderer and any(clean[field] != value for field, value in required.items()):
                fields = " and ".join(f"{field}={value}" for field, value in required.items())
                errors.append({"path": path, "message": f"{renderer} requires {fields}"})
        if clean["rendererKind"] in SPRITE_TEXTURE_RENDERERS and clean["textureRole"] == "none":
            errors.append({"path": path + ".textureRole", "message": "sprite renderer requires a non-none textureRole"})
        if clean["rendererKind"] in SPRITE_TEXTURE_RENDERERS and clean["textureRole"] == "impact":
            impact_texture_consumers.append((index, entity_id))
        normalized_slots.append(clean)
    for index, entity_id in impact_texture_consumers:
        if entity_id not in impact_sprite_entities:
            errors.append({
                "path": f"$.slots[{index}].textureRole",
                "message": "sprite renderer using impact texture requires an impactSprite slot for the same entity",
            })
    return {
        "ok": not errors,
        "errors": errors,
        "normalized": {
            "schema": VFX_DIRECTOR_SCHEMA,
            "effectMagnitude": float(magnitude),
            "visualBudgetClass": budget_class,
            "motif": {
                **motif_text,
                "rhythm": float(motif_rhythm),
                "chaos": float(motif_chaos),
            },
            "slots": normalized_slots,
        },
    }


def _prompt_packet(data: Mapping[str, Any], parent_a: Mapping[str, Any] | None, parent_b: Mapping[str, Any] | None) -> dict[str, Any]:
    realization_raw = data.get("realization")
    realization: Mapping[str, Any] = realization_raw if isinstance(realization_raw, Mapping) else {}
    self_evaluation_raw = realization.get("selfEvaluation")
    self_evaluation: Mapping[str, Any] = self_evaluation_raw if isinstance(self_evaluation_raw, Mapping) else {}
    program_vs_report_raw = self_evaluation.get("programVsReport")
    program_vs_report: Mapping[str, Any] = program_vs_report_raw if isinstance(program_vs_report_raw, Mapping) else {}
    behavior_checks = [
        copy.deepcopy(dict(row))
        for row in program_vs_report.get("behaviorChecks") or []
        if isinstance(row, Mapping)
    ]

    def parent_packet(parent: Mapping[str, Any] | None) -> dict[str, Any]:
        source: Mapping[str, Any] = parent if isinstance(parent, Mapping) else {}
        generated_raw = source.get("generatedData")
        generated: Mapping[str, Any] = generated_raw if isinstance(generated_raw, Mapping) else {}
        summary_raw = generated.get("generatedParentSummary")
        if not isinstance(summary_raw, Mapping):
            summary_raw = source.get("generatedParentSummary")
        return {
            "name": str(source.get("name") or source.get("displayName") or ""),
            "internalName": str(source.get("internalName") or ""),
            "sourceMod": str(source.get("sourceMod") or ""),
            "generatedParentSummary": copy.deepcopy(dict(summary_raw)) if isinstance(summary_raw, Mapping) else {},
        }

    packet = {
        "schema": "infini.vfx-director-input.runtime-events.v1",
        "item": {
            "id": str(data.get("id") or ""), "name": str(data.get("name") or ""),
            "description": str(realization.get("description") or ""),
            "playerExperience": str(realization.get("playerExperience") or ""),
            "behaviorChecks": behavior_checks,
        },
        "parents": [parent_packet(parent_a), parent_packet(parent_b)],
        "acceptedVisualKit": copy.deepcopy(data.get("visualKit") or {}),
        "runtimeSurface": vfx_director_surface(data),
        "outputSchema": _director_schema(data),
        "rules": [
            "Bind every slot to one exact runtimeSurface.runtimePairs entityId+event pair.",
            "Do not add gameplay, entities, events, hitboxes, damage, movement, child spawning, or status effects.",
            "Use only enum values and numeric ranges from runtimeSurface; each selected rendererKind also requires the exact companion fields in rendererRequirements (encoded in the slot schema).",
            "projectileAfterimage, spriteStampTrail, and actorAfterimage consume textureRole through the exact bound entity; use item for the item PNG, entity for the bound entity PNG, or its exact visualRole when they match. impactSprite instead consumes its dedicated impact texture.",
            "Sprite renderers require a non-none textureRole. Primitive and particle renderers do not consume a gameplay PNG.",
            "Only rendererKind=impactSprite authors spritePrompt/spriteNegativePrompt; spritePrompt must request one dedicated transparent impact sprite. Any other sprite renderer using textureRole=impact needs that impactSprite slot for the same entity. Primitive and particle renderers do not consume textureRole; every non-impactSprite slot returns both sprite prompt strings empty.",
            "Slots may be empty when presentation should be restrained.",
            "Return only one JSON object matching outputSchema.",
        ],
    }
    return {
        **{key: packet[key] for key in VFX_PROMPT_STATIC_KEYS},
        **{key: value for key, value in packet.items() if key not in VFX_PROMPT_STATIC_KEYS},
    }


def _vfx_repair_schema(data: Mapping[str, Any]) -> dict[str, Any]:
    full = _director_schema(data)
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema": {"const": VFX_REPAIR_PATCH_SCHEMA},
            "effectMagnitude": {"anyOf": [full["properties"]["effectMagnitude"], {"type": "null"}]},
            "visualBudgetClass": {"anyOf": [full["properties"]["visualBudgetClass"], {"type": "null"}]},
            "motif": {"anyOf": [full["properties"]["motif"], {"type": "null"}]},
            "slotsUpsert": {"type": "array", "items": full["properties"]["slots"]["items"], "maxItems": full["properties"]["slots"]["maxItems"]},
            "slotIdsDelete": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 64}, "maxItems": full["properties"]["slots"]["maxItems"]},
            "slotIndicesDelete": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": max(0, full["properties"]["slots"]["maxItems"] * 2)}, "maxItems": max(1, full["properties"]["slots"]["maxItems"] * 2)},
            "note": {"type": "string", "minLength": 1, "maxLength": 500},
        },
        "required": ["schema", "effectMagnitude", "visualBudgetClass", "motif", "slotsUpsert", "slotIdsDelete", "slotIndicesDelete", "note"],
    }


def _build_vfx_repair_scope(raw: Any, errors: list[dict[str, Any]]) -> dict[str, Any]:
    source = raw if isinstance(raw, Mapping) else {}
    slots = source.get("slots") if isinstance(source.get("slots"), list) else []
    mutable_globals: set[str] = set()
    global_paths: dict[str, set[str]] = {}
    mutable_slot_ids: set[str] = set()
    slot_paths: dict[str, set[str]] = {}
    delete_indices: set[int] = set()
    allow_create_slots = not isinstance(raw, Mapping)
    whole_response = not isinstance(raw, Mapping)

    def grant_global(field: str, relative: str) -> None:
        mutable_globals.add(field)
        global_paths.setdefault(field, set()).add(relative.strip("."))

    def grant_slot(slot_id: str, relative: str) -> None:
        if slot_id:
            mutable_slot_ids.add(slot_id)
            slot_paths.setdefault(slot_id, set()).add(relative.strip("."))

    for error in errors:
        path = str(error.get("path") or "$")
        message = str(error.get("message") or "")
        if path == "$":
            whole_response = True
        for field in ("effectMagnitude", "visualBudgetClass", "motif"):
            prefix = f"$.{field}"
            if path == prefix:
                grant_global(field, "")
            elif path.startswith(prefix + "."):
                grant_global(field, path[len(prefix) + 1:])
        match = re.match(r"^\$\.slots\[(\d+)\](?:\.(.*))?$", path)
        if match:
            index = int(match.group(1))
            relative = str(match.group(2) or "")
            if 0 <= index < len(slots) and isinstance(slots[index], Mapping):
                slot_id = str(slots[index].get("id") or "")
                if slot_id:
                    if relative:
                        grant_slot(slot_id, relative)
                    elif "entity/event pair" in message:
                        # Root-level semantic error, but only the exact pair is
                        # broken. Keep timing, style and already-valid cue data
                        # frozen while allowing the model to retarget the slot.
                        grant_slot(slot_id, "entityId")
                        grant_slot(slot_id, "event")
                    elif "requires channel=" in message and "lane=cue" in message:
                        grant_slot(slot_id, "channel")
                        grant_slot(slot_id, "lane")
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
    if whole_response:
        for field in ("effectMagnitude", "visualBudgetClass", "motif"):
            grant_global(field, "")
        allow_create_slots = True
        for index, row in enumerate(slots):
            if isinstance(row, Mapping) and str(row.get("id") or ""):
                grant_slot(str(row.get("id") or ""), "")
            else:
                delete_indices.add(index)
    return {
        "schema": "infini.vfx-repair-scope.v3",
        "mutableGlobals": sorted(mutable_globals),
        "mutableSlotIds": sorted(mutable_slot_ids),
        "deletableSlotIds": sorted(mutable_slot_ids),
        "deletableSlotIndices": sorted(delete_indices),
        "allowCreateSlots": allow_create_slots,
        "fieldPermissions": {
            "globals": {field: sorted(paths) for field, paths in sorted(global_paths.items())},
            "slots": [{"slotId": slot_id, "paths": sorted(paths)} for slot_id, paths in sorted(slot_paths.items())],
        },
        "errorPaths": [str(row.get("path") or "$") for row in errors],
    }


def _vfx_repair_context(raw: Any, scope: Mapping[str, Any]) -> dict[str, Any]:
    source = raw if isinstance(raw, Mapping) else {}
    mutable_globals = set(str(value) for value in scope.get("mutableGlobals") or [])
    mutable_slot_ids = set(str(value) for value in scope.get("mutableSlotIds") or [])
    slots = source.get("slots") if isinstance(source.get("slots"), list) else []
    return {
        "malformedRawText": raw.raw_text[:12000] if isinstance(raw, MalformedVfxDirectorOutput) else "",
        "broken": {
            "globals": {field: copy.deepcopy(source.get(field)) for field in mutable_globals},
            "slots": [copy.deepcopy(row) for row in slots if isinstance(row, Mapping) and str(row.get("id") or "") in mutable_slot_ids],
        },
        "validReadOnly": {
            "globals": {field: copy.deepcopy(source.get(field)) for field in ("effectMagnitude", "visualBudgetClass", "motif") if field not in mutable_globals},
            "slots": [copy.deepcopy(row) for row in slots if isinstance(row, Mapping) and str(row.get("id") or "") not in mutable_slot_ids],
        },
    }


def _vfx_filter_ignored(path: str, requested: Any, preserved: Any, reason: str) -> dict[str, Any]:
    return {"path": path, "reason": reason, "requested": copy.deepcopy(requested), "preserved": copy.deepcopy(preserved)}


def _filter_vfx_repair_patch(
    data: Mapping[str, Any],
    previous: Any,
    patch: Any,
    scope: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    from infini_local.core.runtime_authoring import strict_schema_errors

    shape_schema = _vfx_repair_schema(data)
    # Renderer compatibility applies to the merged slot. Before frozen-first
    # filtering, an unrelated rewrite may contradict a valid frozen companion;
    # it must be ignored, not cancel an otherwise useful repair. Keep structural
    # validation here and the full renderer/schema gate after the merge.
    shape_schema["properties"]["slotsUpsert"]["items"].pop("allOf", None)
    schema_errors = strict_schema_errors(patch, shape_schema)
    patch_mapping: Mapping[str, Any] = patch if isinstance(patch, Mapping) else {}
    if isinstance(patch, MalformedVfxDirectorOutput):
        schema_errors.insert(0, {
            "path": "$",
            "kind": "malformed_json",
            "expected": "strict VFX Repair JSON object",
            "actual": patch.error,
        })
    filtered = {
        "schema": VFX_REPAIR_PATCH_SCHEMA,
        "effectMagnitude": None,
        "visualBudgetClass": None,
        "motif": None,
        "slotsUpsert": [],
        "slotIdsDelete": [],
        "slotIndicesDelete": [],
        "note": str(patch_mapping.get("note") or "deterministically filtered VFX Repair"),
    }
    if schema_errors:
        return filtered, {"schema": "infini.vfx-repair-filter-report.v1", "ok": False, "errors": schema_errors, "acceptedPaths": [], "ignoredChanges": []}

    source = previous if isinstance(previous, Mapping) else {}
    mutable_globals = set(str(value) for value in scope.get("mutableGlobals") or [])
    mutable_slot_ids = set(str(value) for value in scope.get("mutableSlotIds") or [])
    deletable_slot_ids = set(str(value) for value in scope.get("deletableSlotIds") or [])
    deletable_indices = set(int(value) for value in scope.get("deletableSlotIndices") or [])
    raw_permission_root = scope.get("fieldPermissions")
    permission_root = raw_permission_root if isinstance(raw_permission_root, Mapping) else {}
    raw_global_permissions = permission_root.get("globals")
    global_permissions = raw_global_permissions if isinstance(raw_global_permissions, Mapping) else {}
    slot_permissions = {
        str(row.get("slotId") or ""): tuple(str(value) for value in row.get("paths") or [])
        for row in permission_root.get("slots") or [] if isinstance(row, Mapping)
    }
    ignored: list[dict[str, Any]] = []
    accepted: list[str] = []

    for field in ("effectMagnitude", "visualBudgetClass", "motif"):
        candidate = patch_mapping.get(field)
        if candidate is None:
            continue
        path = f"$.{field}"
        original = source.get(field)
        if field not in mutable_globals:
            ignored.append(_vfx_filter_ignored(path, candidate, original, "valid_global_frozen"))
            continue
        if isinstance(original, Mapping) and isinstance(candidate, Mapping):
            merged, row_ignored, row_accepted = merge_frozen_subtree(
                original, candidate, mutable_paths=global_permissions.get(field) or (), audit_path=path, allow_additions=False,
            )
            filtered[field] = merged
            ignored.extend(row_ignored)
            accepted.extend(row_accepted)
        else:
            filtered[field] = copy.deepcopy(candidate)
            accepted.append(path)

    slots = source.get("slots") if isinstance(source.get("slots"), list) else []
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
                if dict(candidate) != dict(original):
                    ignored.append(_vfx_filter_ignored(path, candidate, original, "independent_valid_slot_frozen"))
                continue
            merged, row_ignored, row_accepted = merge_frozen_subtree(
                original, candidate, mutable_paths=slot_permissions.get(slot_id, ()), audit_path=path, allow_additions=False,
            )
            ignored.extend(row_ignored)
            accepted.extend(row_accepted)
            if merged != original:
                filtered["slotsUpsert"].append(merged)
            continue
        if scope.get("allowCreateSlots"):
            filtered["slotsUpsert"].append(copy.deepcopy(candidate))
            accepted.append(path)
        else:
            ignored.append(_vfx_filter_ignored(path, candidate, None, "new_slot_not_required"))

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
    for field in ("effectMagnitude", "visualBudgetClass", "motif"):
        if filtered.get(field) is not None:
            out[field] = copy.deepcopy(filtered[field])
    slots = list(out.get("slots") or []) if isinstance(out.get("slots"), list) else []
    slots = [row for index, row in enumerate(slots) if index not in set(filtered.get("slotIndicesDelete") or [])]
    doomed = set(str(value) for value in filtered.get("slotIdsDelete") or [])
    slots = [row for row in slots if not isinstance(row, Mapping) or str(row.get("id") or "") not in doomed]
    by_id = {str(row.get("id") or ""): copy.deepcopy(row) for row in slots if isinstance(row, Mapping) and str(row.get("id") or "")}
    order = [str(row.get("id") or "") for row in slots if isinstance(row, Mapping) and str(row.get("id") or "")]
    for row in filtered.get("slotsUpsert") or []:
        slot_id = str(row.get("id") or "")
        if slot_id not in by_id:
            order.append(slot_id)
        by_id[slot_id] = copy.deepcopy(row)
    out["slots"] = [by_id[slot_id] for slot_id in order if slot_id in by_id]
    return (out, audit) if return_audit else out



def _director_system(*, repair: bool = False) -> str:
    if repair:
        return (
            "You are the conditional VFX Repair. Repair only the explicit broken VFX fields. You may return a complete "
            "broken slot; deterministic merge freezes already-valid old values and ignores extra rewrites. Bind only accepted "
            "runtime entity/event pairs. Gameplay is immutable. Return strict JSON only."
        )
    return (
        "You are the VFX Director. Author finite Terraria presentation only for accepted low-level runtime entity/event pairs. "
        "Gameplay is immutable. Do not infer or create weapon families. Return strict JSON only."
    )


def _request(
    llm_director: Callable[..., Any],
    packet: dict[str, Any],
    *,
    repair_errors: list[dict[str, Any]] | None = None,
    previous: Any = None,
    repair_scope: Mapping[str, Any] | None = None,
) -> Any:
    messages = None
    if repair_errors is not None:
        context = _vfx_repair_context(previous, repair_scope or {})
        user = {
            "task": "Patch only exact invalid VFX fields/slots.",
            "item": copy.deepcopy(packet.get("item") or {}),
            "acceptedVisualKitReadOnly": copy.deepcopy(packet.get("acceptedVisualKit") or {}),
            "runtimeSurfaceReadOnly": copy.deepcopy(packet.get("runtimeSurface") or {}),
            "exactErrors": copy.deepcopy(repair_errors[:24]),
            "repairScope": copy.deepcopy(dict(repair_scope or {})),
            "brokenFragments": context["broken"],
            "malformedRawText": context["malformedRawText"],
            "validGeneratedContext": context["validReadOnly"],
            "outputSchema": _vfx_repair_schema_from_packet(packet),
            "rules": [
                "fill only fields listed in repairScope.fieldPermissions; optional unreported fields stay absent",
                "already-valid fields and independent slots are frozen; extra rewrites are ignored",
                "bind only exact runtime entityId+event pairs",
                "presentation only; gameplay is immutable",
            ],
        }
        user = {
            **{key: user[key] for key in VFX_REPAIR_PROMPT_STATIC_KEYS},
            **{key: value for key, value in user.items() if key not in VFX_REPAIR_PROMPT_STATIC_KEYS},
        }
        messages = [
            stage_chat_message("system", "vfx_repair_contract", _director_system(repair=True)),
            stage_chat_message("user", "vfx_repair_context", json.dumps(user, ensure_ascii=False, separators=(",", ":"))),
        ]
        return llm_director(
            _director_system(repair=True), user, int(VFX_LLM_DIRECTOR_MAX_TOKENS),
            float(VFX_LLM_REPAIR_TEMPERATURE), int(VFX_LLM_DIRECTOR_TIMEOUT), messages=messages,
        )
    user = copy.deepcopy(packet)
    return llm_director(
        _director_system(repair=False), user, int(VFX_LLM_DIRECTOR_MAX_TOKENS),
        float(VFX_LLM_DIRECTOR_TEMPERATURE), int(VFX_LLM_DIRECTOR_TIMEOUT), messages=messages,
    )


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
            "effectMagnitude": {"anyOf": [copy.deepcopy(full["properties"]["effectMagnitude"]), {"type": "null"}]},
            "visualBudgetClass": {"anyOf": [copy.deepcopy(full["properties"]["visualBudgetClass"]), {"type": "null"}]},
            "motif": {"anyOf": [copy.deepcopy(full["properties"]["motif"]), {"type": "null"}]},
            "slotsUpsert": {"type": "array", "items": copy.deepcopy(full["properties"]["slots"]["items"]), "maxItems": full["properties"]["slots"]["maxItems"]},
            "slotIdsDelete": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 64}, "maxItems": full["properties"]["slots"]["maxItems"]},
            "slotIndicesDelete": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": max(0, full["properties"]["slots"]["maxItems"] * 2)}, "maxItems": max(1, full["properties"]["slots"]["maxItems"] * 2)},
            "note": {"type": "string", "minLength": 1, "maxLength": 500},
        },
        "required": ["schema", "effectMagnitude", "visualBudgetClass", "motif", "slotsUpsert", "slotIdsDelete", "slotIndicesDelete", "note"],
    }


def _compile_manifest(data: Mapping[str, Any], authored: Mapping[str, Any], recipe_key_value: str) -> dict[str, Any]:
    magnitude = float(authored["effectMagnitude"])
    budget_class = str(authored["visualBudgetClass"])
    slots: list[dict[str, Any]] = []
    for source in authored["slots"]:
        slot = dict(source)
        # Director-only captions are consumed into RuntimeEntityVisualSpec below;
        # VfxSlotSpec is a fail-closed runtime DTO and must not carry them.
        slot.pop("spritePrompt", None)
        slot.pop("spriteNegativePrompt", None)
        slot.update({
            "eventGroup": "auto", "stage": "loop",
            "source": "llm_vfx_director",
            "slotSeed": _seed(recipe_key_value, slot.get("id")),
            "bakedClipId": "", "bakedClipHash": "", "bakedCommandCount": 0,
            "bakedCommands": [], "effectName": "",
        })
        slots.append(slot)
    return {
        "schema": VFX_MANIFEST_SCHEMA,
        "recipeId": str(recipe_key_value or data.get("id") or ""),
        "effectName": "runtime_entity_events",
        "inspirationNames": [],
        "playbackMode": "Realtime",
        "seed": _seed(recipe_key_value, data.get("id"), "vfx"),
        "confidence": 1.0,
        "effectMagnitude": magnitude,
        "visualBudgetClass": budget_class,
        "motif": copy.deepcopy(authored["motif"]),
        "budget": {
            "effectMagnitude": magnitude, "visualBudgetClass": budget_class,
            "emergencyCap": True,
            "maxParticlesPerTick": max(16, min(256, 32 + len(slots) * 24)),
            "maxParticlesTotal": max(256, min(12000, 1000 + len(slots) * 1200)),
            "maxDrawCalls": max(32, min(512, 64 + len(slots) * 36)),
            "spawnRateMultiplier": 1.0,
            "enableSoftGlow": True, "enablePointSparks": True,
            "enablePersistentSmoke": budget_class in {"large", "signature"},
        },
        "slots": slots,
        "overlayPolicy": "LocalOnly",
        "debug": {
            "pattern": "runtime_entity_events", "roles": [str(row.get("visualRole") or "") for row in runtime_visual_roles(data)],
            "selectedScore": 1.0, "selectedReasons": ["exact_entity_event_binding"],
            "topCandidates": [], "wordProbe": [],
        },
    }


def _hydrate_vfx_asset_prompts(data: dict[str, Any], authored: Mapping[str, Any]) -> None:
    """Losslessly move selected VFX captions into the known entity visual DTO."""

    runtime_raw = data.get("runtimeProgram")
    runtime: Mapping[str, Any] = runtime_raw if isinstance(runtime_raw, Mapping) else {}
    by_id = {
        str(row.get("id") or ""): row
        for row in runtime.get("entities") or []
        if isinstance(row, dict) and str(row.get("id") or "")
    }
    for source in authored.get("slots") or []:
        if not isinstance(source, Mapping) or str(source.get("rendererKind") or "") != "impactSprite":
            continue
        entity = by_id.get(str(source.get("entityId") or ""))
        if not isinstance(entity, dict):
            continue
        visual = entity.setdefault("visual", {})
        visual.update({
            "impactPrompt": str(source.get("spritePrompt") or "")[:1400],
            "impactNegativePrompt": str(source.get("spriteNegativePrompt") or "")[:700],
            "impactSpritePath": "",
            "impactSpriteUrl": "",
            "impactSpriteStatus": "pending",
            "impactSpriteTechnicalScore": 0.0,
        })


def _development_manifest(data: Mapping[str, Any], recipe_key_value: str) -> dict[str, Any]:
    return _compile_manifest(data, {
        "effectMagnitude": 0.0,
        "visualBudgetClass": "tiny",
        "motif": {"element": "neutral", "shapeLanguage": "none", "motionLanguage": "none", "paletteRole": "primary", "rhythm": 1.0, "chaos": 0.0},
        "slots": [],
    }, recipe_key_value)


def attach_hybrid_vfx_manifest(
    data: dict[str, Any],
    recipe_key_value: str,
    reroll_salt: Any = "",
    parent_a: dict[str, Any] | None = None,
    parent_b: dict[str, Any] | None = None,
    llm_director: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run one VFX Director call and at most one conditional VFX Repair."""
    del reroll_salt
    if llm_director is None:
        data["vfxManifest"] = _development_manifest(data, recipe_key_value)
        data.setdefault("debug", {})["vfxDirectorStatus"] = "development_inert_manifest"
        return data

    packet = _prompt_packet(data, parent_a, parent_b)
    accounting = _stage_accounting(data)
    accounting["vfxDirectorCalls"] += 1
    raw = _request(llm_director, packet)
    report = validate_vfx_director_output(raw, data)
    if not report["ok"]:
        accounting["vfxRepairCalls"] += 1
        repair_scope = _build_vfx_repair_scope(raw, report["errors"])
        patch = _request(llm_director, packet, repair_errors=report["errors"], previous=raw, repair_scope=repair_scope)
        repaired, repair_audit = _apply_vfx_repair_patch(data, raw, patch or {}, repair_scope, return_audit=True)
        report = validate_vfx_director_output(repaired, data)
        if not report["ok"]:
            raise PlannerUnavailable("VFX Repair did not produce an exact entity/event manifest: " + json.dumps(report["errors"][:16], ensure_ascii=False))
        raw = repaired
        data.setdefault("debug", {})["vfxRepairRawPatch"] = copy.deepcopy(patch)
        data["debug"]["vfxRepairPatch"] = copy.deepcopy(repair_audit.get("filteredPatch") or {})
        data["debug"]["vfxRepairFilterAudit"] = copy.deepcopy(repair_audit)
        data["debug"]["vfxRepairScope"] = copy.deepcopy(repair_scope)
    _hydrate_vfx_asset_prompts(data, report["normalized"])
    data["vfxManifest"] = _compile_manifest(data, report["normalized"], recipe_key_value)
    debug = data.setdefault("debug", {})
    debug["vfxDirectorStatus"] = "validated_and_compiled"
    debug["vfxDirectorRaw"] = copy.deepcopy(raw)
    debug["vfxRuntimePairs"] = _allowed_pairs(data)
    return data


# The former recipe/macro selector is intentionally absent from production.  A
# compact surface is retained only for diagnostics and tests.
def compact_vfx_recipe_card(recipe: Mapping[str, Any]) -> dict[str, Any]:
    return {"id": str(recipe.get("id") or ""), "status": "retired_recipe_macro"}


def vfx_director_schema(data: Mapping[str, Any]) -> dict[str, Any]:
    """Public generated schema owned by the VFX Director contract module."""

    return _director_schema(data)


def vfx_repair_schema(data: Mapping[str, Any]) -> dict[str, Any]:
    """Public generated schema for the bounded VFX Repair patch."""

    return _vfx_repair_schema(data)


__all__ = [
    "VFX_DIRECTOR_SCHEMA", "VFX_REPAIR_PATCH_SCHEMA", "VFX_MANIFEST_SCHEMA", "MalformedVfxDirectorOutput", "attach_hybrid_vfx_manifest",
    "VFX_PROMPT_STATIC_KEYS", "VFX_REPAIR_PROMPT_STATIC_KEYS",
    "compact_vfx_recipe_card", "validate_vfx_director_output", "vfx_director_schema", "vfx_director_surface",
    "vfx_repair_schema",
]
