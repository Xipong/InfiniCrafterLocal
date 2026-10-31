"""Explicit live-history presentation; no inferred fade, sampling or body pose."""
from __future__ import annotations

from typing import Any

from infini_local.core.vfx_material_contract import _number, _profile, rgb_schema, texture_schema

LEGACY_HISTORY_RENDERERS = frozenset({"historyRibbon", "tipTrail", "spriteStampTrail"})
HISTORY_RENDERERS = ("historyTrail",)
HISTORY_SEMANTICS = (
    "Live captured projectile history, never a guessed or relocated trajectory. One sample per world tick; "
    "historyTicks selects at most 32 retained samples, not a duration or emission cadence. "
    "Read samples firstSampleAgeTicks, then +sampleStepTicks while age<historyTicks and a real sample exists. "
    "Unavailable samples are omitted, never repeated or interpolated into new history. "
    "center is the actual entity center; tip is its existing captured geometric tip, not an inferred PNG nose. "
    "stroke connects successive selected samples with explicit world-pixel width independent of hitbox, scale and light. "
    "sprites use the selected texture and explicit scale with either the current body pose or each sample's captured "
    "rotation/flip/scale/pivot/gfx offset. Item/entity textures use selected PNG frame size/axis/pivot; "
    "asset/impact textures use their texel frame, centered pivot and raw projectile rotation, multiplied "
    "by captured/current body scale and explicit trail scale. No image-axis inference. "
    "No automatic current-pose substitution for missing sampled poses. "
    "Opacity profile uses sample age/historyTicks and is applied once; each stroke segment uses its older endpoint opacity. "
    "Missing scheduled samples break the stroke rather than bridging the gap. No additional linear age fade. "
    "Zero width/scale/opacity remains silent. One quad per segment/stamp shares the normal draw budget. "
    "Only periodic/on_spawn live projectile slots; ends with source, no detached event stamp, Dust or lighting. "
    "slot blend/layer remain explicit; anchor=self only because trail.source owns the path. "
    "For event-local individual texture elements use spriteElement explicitly."
)


def history_schema() -> dict[str, Any]:
    common = {
        "draw": {"type": "string", "enum": ["stroke", "sprites"]},
        "source": {"type": "string", "enum": ["center", "tip"]},
        "historyTicks": _number(2, 32, "Maximum sampled world-tick age window, not effect duration.", integer=True),
        "sampleStepTicks": _number(1, 32, "Distance between selected sample ages in world ticks; never update or emission cadence.", integer=True),
        "firstSampleAgeTicks": _number(0, 31, "Explicit first historical age, zero is newest. No implicit skip of the newest two samples.", integer=True),
        "opacityProfile": _profile(1),
        "color": rgb_schema(),
    }
    fields = {
        "widthPx": _number(0, 1024, "Stroke width in world pixels; zero is silent, independent of projectile/slot scale."),
        "texture": texture_schema(),
        "scale": _number(0, 5, "Multiplier on selected PNG's rendering size; zero is silent."),
        "pose": {"type": "string", "enum": ["current", "sampled"],
                 "description": "current reuses the live body's pose at all selected historical positions; sampled uses the actual pose captured at each selected world tick."},
    }
    owners = {"stroke": {"widthPx"}, "sprites": {"texture", "scale", "pose"}}
    return {
        "type": "object", "additionalProperties": False,
        "properties": {**common, **fields}, "required": list(common),
        "allOf": [
            {"if": {"properties": {"draw": {"const": draw}}, "required": ["draw"]},
             "then": {"required": sorted(owned), "properties": {
                 field: {"enum": []} for field in fields if field not in owned
             }}}
            for draw, owned in owners.items()
        ],
    }


def history_slot_clauses(item_ids: list[str], renderers: list[str], events: list[str]) -> list[dict[str, Any]]:
    del events
    selected = {"rendererKind": {"const": "historyTrail"}}
    unused = {"startTick", "duration", "repeatEvery", "phaseOffset", "scale", "density", "spread",
              "alpha", "particleSystemId", "textureRole"}
    return [
        {"if": {"properties": selected, "required": ["rendererKind"]},
         "then": {"required": ["trail", "blend", "layer"], "properties": {
             "event": {"enum": ["periodic", "on_spawn"]},
             "anchor": {"const": "self"},
             **{field: {"enum": []} for field in unused},
         }}},
        {"if": {"properties": {**selected, "entityId": {"enum": item_ids}}, "required": ["rendererKind", "entityId"]},
         "then": {"properties": {"rendererKind": {"enum": []}}}},
        {"if": {"properties": {"rendererKind": {"enum": [r for r in renderers if r != "historyTrail"]}}, "required": ["rendererKind"]},
         "then": {"properties": {"trail": {"enum": []}}}},
    ]


def history_texture_clauses(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"if": {"properties": {"rendererKind": {"const": "historyTrail"}, "entityId": {"const": row["entityId"]}},
                "required": ["rendererKind", "entityId"]},
         "then": {"properties": {"trail": {"properties": {"texture": {"properties": {"source": {"enum": row["sources"]}}}}}}}}
        for row in rows
    ]
