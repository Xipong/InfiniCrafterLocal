from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from infini_local.core.vfx_manifest_config import VFX_LLM_DIRECTOR_MAX_SLOTS


# AGENT MAP: schema/range contract for optional LLM VFX Director output.
# This module defines the enum/range surface and validation report primitives only;
# final slot compilation still happens in vfx_manifest.py.

@dataclass(frozen=True, slots=True)
class VfxEnumFieldContract:
    name: str
    surface_key: str
    values: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True, slots=True)
class VfxNumericFieldContract:
    name: str
    minimum: float | int
    maximum: float | int
    integer: bool = False
    required: bool = True


VFX_SLOT_ENUM_FIELDS: tuple[VfxEnumFieldContract, ...] = (
    VfxEnumFieldContract("event", "events", ("travel", "active", "tick", "hit", "kill", "expire", "while_held", "while_equipped", "on_use", "on_alt_use")),
    VfxEnumFieldContract("rendererKind", "rendererKind", ("projectileAfterimage", "spriteStampTrail", "historyRibbon", "tipTrail", "ghostArc", "wavyStrip", "beamLine", "fieldPulse", "orbitingMotes", "actorAfterimage", "impactRing", "impactSprite", "childMotes", "lightCue", "soundCue")),
    VfxEnumFieldContract("backend", "backend", ("Auto", "Realtime", "Primitive", "Sprite", "Particle")),
    VfxEnumFieldContract("textureRole", "textureRole", ("projectile", "impact", "child", "field")),
    VfxEnumFieldContract("particleRole", "particleRole", ("projectile", "impact", "child", "field")),
    VfxEnumFieldContract("anchor", "anchor", ("self", "owner", "tip", "tipHistory", "hitPoint", "velocity", "field")),
    VfxEnumFieldContract("channel", "channel", ("motionTrail", "coreGlow", "ambientParticles", "impactShape", "impactParticles", "decaySmoke", "light", "sound")),
    VfxEnumFieldContract("lane", "lane", ("primary", "support", "accent", "ornament", "cue")),
    VfxEnumFieldContract("emissionMode", "emissionMode", ("wake", "orbit", "residue", "burst", "cone", "ring", "spiral", "point")),
    VfxEnumFieldContract("blend", "blend", ("alpha", "additive")),
    VfxEnumFieldContract("particleSystemId", "particleSystemId", ("pl:glow", "pl:shard", "pl:smoke", "pl:spark", "dust")),
)

VFX_TOP_ENUM_FIELDS: tuple[VfxEnumFieldContract, ...] = (
    VfxEnumFieldContract("visualBudgetClass", "", ("tiny", "small", "normal", "large", "signature")),
)

VFX_NUMERIC_FIELDS: tuple[VfxNumericFieldContract, ...] = (
    VfxNumericFieldContract("effectMagnitude", 0.0, 1.0),
    VfxNumericFieldContract("scale", 0.15, 5.0),
    VfxNumericFieldContract("density", 0.0, 1.0),
    VfxNumericFieldContract("duration", 3, 120, integer=True),
    VfxNumericFieldContract("alpha", 0.0, 1.0),
    VfxNumericFieldContract("spread", 0.0, 2.0),
    VfxNumericFieldContract("jitter", 0.0, 1.5),
    VfxNumericFieldContract("phaseOffset", -1.0, 1.0, required=False),
    VfxNumericFieldContract("budgetWeight", 0.1, 4.0),
    VfxNumericFieldContract("signatureWeight", 0.0, 1.0),
    VfxNumericFieldContract("visualCost", 0.0, 1.0),
    VfxNumericFieldContract("fadeIn", 0.0, 0.8),
    VfxNumericFieldContract("fadeOut", 0.0, 0.8),
    VfxNumericFieldContract("startTick", 0, 120, integer=True, required=False),
    VfxNumericFieldContract("repeatEvery", 0, 120, integer=True, required=False),
)

VFX_RENDERER_RULES = MappingProxyType({
    "soundCue": MappingProxyType({"channel": "sound", "lane": "cue"}),
    "lightCue": MappingProxyType({"channel": "light", "lane": "cue"}),
})


def vfx_director_surface() -> dict[str, Any]:
    """Compact runtime surface for the optional Gemma VFX Director.

    This is intentionally a tiny enum/range contract, not the recipe library and not C# code.
    The LLM authors slots; Python validates/clamps and freezes them into the normal manifest.
    """
    surface: dict[str, Any] = {
        contract.surface_key: list(contract.values)
        for contract in VFX_SLOT_ENUM_FIELDS[:8]
    }
    surface["rendererRules"] = {
        renderer: dict(fields)
        for renderer, fields in VFX_RENDERER_RULES.items()
    }
    for contract in VFX_SLOT_ENUM_FIELDS[8:]:
        surface[contract.surface_key] = list(contract.values)
    surface["numericRanges"] = {
        contract.name: [contract.minimum, contract.maximum]
        for contract in VFX_NUMERIC_FIELDS
    }
    return surface


def vfx_director_required_json_shape() -> dict[str, Any]:
    slot_numeric = [field for field in VFX_NUMERIC_FIELDS if field.name != "effectMagnitude"]
    numeric_descriptions = {
        field.name: (
            f"{'optional ' if not field.required else ''}"
            f"{'integer' if field.integer else 'float'} in vfxSurface.numericRanges.{field.name}"
        )
        for field in slot_numeric
    }
    return {
        "type": "object",
        "requiredTopLevelFields": ["effectMagnitude", "visualBudgetClass", "slots"],
        "optionalTopLevelFields": ["identity"],
        "additionalTopLevelFields": "do not add keys outside this contract. Known forbidden fields are rejected; unknown extras are validation errors.",
        "topLevelContract": {
            "effectMagnitude": "float in vfxSurface.numericRanges.effectMagnitude",
            "visualBudgetClass": "one of tiny|small|normal|large|signature",
            "identity": "optional short debug note only; runtime must not parse it",
        },
        "slots": {
            "type": "array",
            "count": "between constraints.slots[0] and constraints.slots[1]",
            "additionalSlotFields": "do not add keys outside this contract. Known forbidden fields are rejected; unknown extras are validation errors.",
            "requiredSlotFields": [
                *(field.name for field in VFX_SLOT_ENUM_FIELDS),
                *(field.name for field in slot_numeric if field.required),
            ],
            "enumFields": {
                field.name: (
                    "one explicit vfxSurface.particleSystemId value: pl:glow, pl:shard, pl:smoke, pl:spark, or dust"
                    if field.name == "particleSystemId"
                    else f"one vfxSurface.{field.surface_key} value"
                )
                for field in VFX_SLOT_ENUM_FIELDS
            },
            "numericFields": numeric_descriptions,
        },
    }

def _vfx_float(value: Any, lo: float, hi: float, fallback: float) -> float:
    try:
        x = float(value)
    except Exception:
        x = fallback
    if not math.isfinite(x):
        x = fallback
    return max(lo, min(hi, x))

def _vfx_int(value: Any, lo: int, hi: int, fallback: int) -> int:
    try:
        x = int(round(float(value)))
    except Exception:
        x = fallback
    return max(lo, min(hi, x))

def _vfx_director_enum(value: Any, allowed: list[str], fallback: str | None = None) -> str | None:
    raw = str(value or "").strip()
    return raw if raw in allowed else fallback

def _vfx_director_enum_required(slot: dict[str, Any], field: str, allowed: list[str]) -> str | None:
    if field not in slot:
        return None
    value = _vfx_director_enum(slot.get(field), allowed)
    return value if value in allowed else None

def _vfx_director_number_required(slot: dict[str, Any], field: str, lo: float, hi: float, integer: bool = False) -> float | int | None:
    if field not in slot:
        return None
    try:
        x = float(slot.get(field))
    except Exception:
        return None
    if not math.isfinite(x):
        return None
    # Clamp authored numeric values instead of rejecting the whole manifest for a small range miss.
    # Enum mistakes still invalidate; numeric range mistakes are safe to sanitize.
    x = max(lo, min(hi, x))
    return int(round(x)) if integer else x

def _vfx_director_error(errors: list[dict[str, Any]], path: str, error: str, actual: Any = None, expected: Any = None, allowed: Any = None) -> None:
    item: dict[str, Any] = {"path": path, "error": error}
    if actual is not None:
        item["actual"] = actual
    if expected is not None:
        item["expected"] = expected
    if allowed is not None:
        item["allowed"] = allowed
    errors.append(item)

def _vfx_director_warning(warnings: list[dict[str, Any]], path: str, warning: str, actual: Any = None, clamped: Any = None, expected: Any = None) -> None:
    item: dict[str, Any] = {"path": path, "warning": warning}
    if actual is not None:
        item["actual"] = actual
    if clamped is not None:
        item["clamped"] = clamped
    if expected is not None:
        item["expected"] = expected
    warnings.append(item)

def _vfx_director_check_enum(errors: list[dict[str, Any]], obj: dict[str, Any], path: str, field: str, allowed: list[str], required: bool = True) -> str | None:
    if field not in obj:
        if required:
            _vfx_director_error(errors, f"{path}.{field}" if path else field, "missing_required", expected={"allowed": allowed})
        return None
    value = obj.get(field)
    if not isinstance(value, str):
        _vfx_director_error(errors, f"{path}.{field}" if path else field, "invalid_type", actual=value, expected="string", allowed=allowed)
        return None
    normalized = _vfx_director_enum(value, allowed)
    if normalized not in allowed:
        _vfx_director_error(errors, f"{path}.{field}" if path else field, "unknown_enum", actual=value, allowed=allowed)
        return None
    return normalized

def _vfx_director_check_number(errors: list[dict[str, Any]], warnings: list[dict[str, Any]], obj: dict[str, Any], path: str, field: str, lo: float, hi: float, integer: bool = False, required: bool = True) -> float | int | None:
    full_path = f"{path}.{field}" if path else field
    if field not in obj:
        if required:
            _vfx_director_error(errors, full_path, "missing_required", expected={"min": lo, "max": hi})
        return None
    value = obj.get(field)
    if isinstance(value, bool):
        _vfx_director_error(errors, full_path, "invalid_type", actual=value, expected="integer" if integer else "number")
        return None
    try:
        x = float(value)
    except Exception:
        _vfx_director_error(errors, full_path, "invalid_type", actual=value, expected="integer" if integer else "number")
        return None
    if not math.isfinite(x):
        _vfx_director_error(errors, full_path, "invalid_type", actual=value, expected="finite number")
        return None
    if x < lo or x > hi:
        # Numeric range mistakes are clampable and should not make the entire VFX manifest invalid.
        # Record a warning so audits/debug can see that validation intervened without suffocating the model.
        clamped = int(round(max(lo, min(hi, x)))) if integer else max(lo, min(hi, x))
        _vfx_director_warning(warnings, full_path, "clamped_out_of_range", actual=value, clamped=clamped, expected={"min": lo, "max": hi})
        return clamped
    return int(round(x)) if integer else x

def _vfx_director_validation_report(raw: Any, max_slots: int | None = None) -> dict[str, Any]:
    surface = vfx_director_surface()
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not isinstance(raw, dict):
        _vfx_director_error(errors, "", "invalid_type", actual=type(raw).__name__, expected="object")
        return {"valid": False, "errors": errors, "warnings": warnings}

    allowed_top_fields = {
        *(field.name for field in VFX_TOP_ENUM_FIELDS),
        "effectMagnitude",
        "identity",
        "slots",
    }
    for field in sorted(raw.keys()):
        if field not in allowed_top_fields:
            _vfx_director_error(errors, field, "forbidden_field", actual=raw.get(field), expected={"allowed": sorted(allowed_top_fields)})

    effect_magnitude = next(field for field in VFX_NUMERIC_FIELDS if field.name == "effectMagnitude")
    _vfx_director_check_number(
        errors,
        warnings,
        raw,
        "",
        effect_magnitude.name,
        effect_magnitude.minimum,
        effect_magnitude.maximum,
        integer=effect_magnitude.integer,
        required=effect_magnitude.required,
    )
    for field in VFX_TOP_ENUM_FIELDS:
        _vfx_director_check_enum(
            errors,
            raw,
            "",
            field.name,
            list(field.values),
            required=field.required,
        )

    raw_slots = raw.get("slots")
    if not isinstance(raw_slots, list):
        _vfx_director_error(errors, "slots", "invalid_type" if "slots" in raw else "missing_required", actual=raw_slots if "slots" in raw else None, expected="array")
        return {"valid": False, "errors": errors, "warnings": warnings}
    if max_slots is None:
        max_slots = max(2, min(8, VFX_LLM_DIRECTOR_MAX_SLOTS))
    if len(raw_slots) > max_slots:
        _vfx_director_error(errors, "slots", "out_of_range", actual=len(raw_slots), expected={"min": 0, "max": max_slots})

    enum_fields = {
        field.name: list(field.values)
        for field in VFX_SLOT_ENUM_FIELDS
    }
    numeric_fields = {
        field.name: (
            field.minimum,
            field.maximum,
            field.integer,
            field.required,
        )
        for field in VFX_NUMERIC_FIELDS
        if field.name != "effectMagnitude"
    }

    allowed_slot_fields = set(enum_fields.keys()) | set(numeric_fields.keys())
    for i, slot in enumerate(raw_slots[:max_slots]):
        path = f"slots[{i}]"
        if not isinstance(slot, dict):
            _vfx_director_error(errors, path, "invalid_type", actual=type(slot).__name__, expected="object")
            continue
        for field in sorted(slot.keys()):
            if field not in allowed_slot_fields:
                _vfx_director_error(errors, f"{path}.{field}", "forbidden_field", actual=slot.get(field), expected={"allowed": sorted(allowed_slot_fields)})

        normalized_enums: dict[str, str | None] = {}
        for field, allowed in enum_fields.items():
            normalized_enums[field] = _vfx_director_check_enum(errors, slot, path, field, allowed)
        for field, (lo, hi, integer, required) in numeric_fields.items():
            _vfx_director_check_number(errors, warnings, slot, path, field, lo, hi, integer=integer, required=required)

        renderer = normalized_enums.get("rendererKind")
        renderer_rules = surface.get("rendererRules")
        renderer_rules = renderer_rules if isinstance(renderer_rules, dict) else {}
        required_fields = renderer_rules.get(renderer)
        if isinstance(required_fields, dict):
            for field, expected in required_fields.items():
                actual = normalized_enums.get(field)
                if actual is not None and actual != expected:
                    _vfx_director_error(
                        errors,
                        f"{path}.{field}",
                        "renderer_field_mismatch",
                        actual=actual,
                        expected=expected,
                    )

    return {"valid": not errors, "errors": errors, "warnings": warnings}

def _vfx_director_repair_prompt(previous_json: Any, validation_report: dict[str, Any], vfx_surface: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": "Repair the invalid VFX manifest fields only.",
        "instructions": [
            "Fix fields listed in VALIDATION_REPORT.",
            "Keep the effect design.",
            "No explanations or invented enums.",
            "Use VFX_SURFACE enums and ranges.",
            "Return the full corrected JSON object.",
        ],
        "PREVIOUS_JSON": previous_json,
        "VALIDATION_REPORT": validation_report,
        "VFX_SURFACE": vfx_surface,
    }

def _vfx_director_error_fields(report: dict[str, Any]) -> list[str]:
    return [str(e.get("path")) for e in report.get("errors", []) if isinstance(e, dict) and e.get("path")][:64]

def _vfx_particle_id_is_explicit(value: str | None) -> bool:
    contract = next(field for field in VFX_SLOT_ENUM_FIELDS if field.name == "particleSystemId")
    return str(value or "").strip() in contract.values

__all__ = [
    "VfxEnumFieldContract",
    "VfxNumericFieldContract",
    "VFX_SLOT_ENUM_FIELDS",
    "VFX_TOP_ENUM_FIELDS",
    "VFX_NUMERIC_FIELDS",
    "VFX_RENDERER_RULES",
    "vfx_director_surface",
    "vfx_director_required_json_shape",
    "_vfx_float",
    "_vfx_int",
    "_vfx_director_enum",
    "_vfx_director_enum_required",
    "_vfx_director_number_required",
    "_vfx_director_error",
    "_vfx_director_warning",
    "_vfx_director_check_enum",
    "_vfx_director_check_number",
    "_vfx_director_validation_report",
    "_vfx_director_repair_prompt",
    "_vfx_director_error_fields",
    "_vfx_particle_id_is_explicit",
]
