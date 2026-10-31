"""Shared explicit particle birth regions, independent of texture and velocity."""
from __future__ import annotations

import math
from typing import Any

from infini_local.core.schema_validation import strict_schema_errors

SPAWN_SEMANTICS = (
    "Uniform birth positions around the existing emission origin, sampled once per particle. "
    "point has no extra controls; line/rectangle are centered, with world +X or source-forward frame "
    "and an explicit rotation. annulus samples uniformly by area; inner radius zero gives a disk, "
    "equal radii a ring. Zero extents remain literal. Existing element offsets add once. "
    "Source-attached elements capture sampled offsets locally and then follow the source, without resampling. "
    "Position sampling has a separate deterministic seed stream and does not change velocity sampling."
)


def spawn_schema() -> dict[str, Any]:
    def number(maximum: float, description: str, minimum: float = 0) -> dict[str, Any]:
        return {"type": "number", "minimum": minimum, "maximum": maximum, "description": description}
    fields = {
        "lengthPx": number(512, "Centered line length in world pixels."),
        "widthPx": number(512, "Centered rectangle X extent in world pixels."),
        "heightPx": number(512, "Centered rectangle Y extent in world pixels."),
        "rotationRadians": number(math.tau, "Region rotation relative to selected frame.", -math.tau),
        "frame": {"type": "string", "enum": ["world", "source"]},
        "innerRadiusPx": number(256, "Inner radius; zero includes the center."),
        "outerRadiusPx": number(256, "Outer radius >= innerRadiusPx; equal radii form a ring."),
    }
    variants = {
        "point": set(),
        "line": {"lengthPx", "rotationRadians", "frame"},
        "rectangle": {"widthPx", "heightPx", "rotationRadians", "frame"},
        "annulus": {"innerRadiusPx", "outerRadiusPx"},
    }
    return {"type": "object", "additionalProperties": False, "description": SPAWN_SEMANTICS,
            "properties": {"shape": {"type": "string", "enum": list(variants)}, **fields}, "required": ["shape"],
            "allOf": [{"if": {"properties": {"shape": {"const": kind}}, "required": ["shape"]},
                       "then": {"required": sorted(owned), "properties": {
                           field: {"enum": []} for field in sorted(set(fields) - owned)}}}
                      for kind, owned in variants.items()]}


def spawn_slot_errors(slot: Any, path: str) -> list[dict[str, Any]]:
    """Relational error targets only the invalid outer radius; no repair broadening."""
    if not isinstance(slot, dict):
        return []
    renderer = slot.get("rendererKind")
    if not isinstance(renderer, str):
        return []  # The canonical slot schema reports the indexed renderer type error.
    key = {"spriteElement": "element", "libraryParticle": "particle", "nativeDust": "dust"}.get(renderer)
    payload = slot.get(key) if key else None
    spawn = payload.get("spawn") if isinstance(payload, dict) else None
    if not isinstance(spawn, dict) or spawn.get("shape") != "annulus":
        return []
    props = spawn_schema()["properties"]
    low, high = spawn.get("innerRadiusPx"), spawn.get("outerRadiusPx")
    if (not strict_schema_errors(low, props["innerRadiusPx"])
            and not strict_schema_errors(high, props["outerRadiusPx"]) and high < low):
        return [{"path": f"{path}.{key}.spawn.outerRadiusPx", "message": "must be >= innerRadiusPx"}]
    return []
