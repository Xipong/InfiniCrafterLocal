from __future__ import annotations

import math
from typing import Any

from infini_local.core.vfx_manifest_config import VFX_LLM_DIRECTOR_MAX_SLOTS


# AGENT MAP: schema/range contract for optional LLM VFX Director output.
# This module defines the enum/range surface and validation report primitives only;
# final slot compilation still happens in vfx_manifest.py.

def vfx_director_surface() -> dict[str, Any]:
    """Compact runtime surface for the optional Gemma VFX Director.

    This is intentionally a tiny enum/range contract, not the recipe library and not C# code.
    The LLM authors slots; Python validates/clamps and freezes them into the normal manifest.
    """
    return {
        "events": ["travel", "active", "tick", "hit", "kill", "expire"],
        "rendererKind": [
            "projectileAfterimage", "spriteStampTrail", "historyRibbon", "tipTrail",
            "ghostArc", "wavyStrip", "beamLine", "fieldPulse", "orbitingMotes",
            "actorAfterimage", "impactRing", "impactSprite", "childMotes", "lightCue", "soundCue",
        ],
        "backend": ["Auto", "Realtime", "Primitive", "Sprite", "Particle"],
        "textureRole": ["projectile", "impact", "child", "field"],
        "particleRole": ["projectile", "impact", "child", "field"],
        "anchor": ["self", "owner", "tip", "tipHistory", "hitPoint", "velocity", "field"],
        "channel": ["motionTrail", "coreGlow", "ambientParticles", "impactShape", "impactParticles", "decaySmoke", "light", "sound"],
        "lane": ["primary", "support", "accent", "ornament", "cue"],
        "emissionMode": ["wake", "orbit", "residue", "burst", "cone", "ring", "spiral", "point"],
        "blend": ["alpha", "additive"],
        "particleSystemId": ["pl:glow", "pl:shard", "pl:smoke", "pl:spark", "dust"],
        "numericRanges": {
            "effectMagnitude": [0.0, 1.0],
            "scale": [0.15, 5.0],
            "density": [0.0, 1.0],
            "duration": [3, 120],
            "alpha": [0.0, 1.0],
            "spread": [0.0, 2.0],
            "jitter": [0.0, 1.5],
            "phaseOffset": [-1.0, 1.0],
            "budgetWeight": [0.1, 4.0],
            "signatureWeight": [0.0, 1.0],
            "visualCost": [0.0, 1.0],
            "fadeIn": [0.0, 0.8],
            "fadeOut": [0.0, 0.8],
            "startTick": [0, 120],
            "repeatEvery": [0, 120],
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

    allowed_top_fields = {"effectMagnitude", "visualBudgetClass", "identity", "slots"}
    for field in sorted(raw.keys()):
        if field not in allowed_top_fields:
            _vfx_director_error(errors, field, "forbidden_field", actual=raw.get(field), expected={"allowed": sorted(allowed_top_fields)})

    _vfx_director_check_number(errors, warnings, raw, "", "effectMagnitude", 0.0, 1.0)
    _vfx_director_check_enum(errors, raw, "", "visualBudgetClass", ["tiny", "small", "normal", "large", "signature"])

    raw_slots = raw.get("slots")
    if not isinstance(raw_slots, list):
        _vfx_director_error(errors, "slots", "invalid_type" if "slots" in raw else "missing_required", actual=raw_slots if "slots" in raw else None, expected="non-empty array")
        return {"valid": False, "errors": errors, "warnings": warnings}
    if not raw_slots:
        _vfx_director_error(errors, "slots", "missing_required", actual=[], expected="non-empty array")
        return {"valid": False, "errors": errors, "warnings": warnings}
    if max_slots is None:
        max_slots = max(2, min(8, VFX_LLM_DIRECTOR_MAX_SLOTS))
    if len(raw_slots) > max_slots:
        _vfx_director_error(errors, "slots", "out_of_range", actual=len(raw_slots), expected={"min": 1, "max": max_slots})

    numeric_ranges = surface.get("numericRanges", {}) if isinstance(surface.get("numericRanges"), dict) else {}
    enum_fields = {
        "event": surface["events"],
        "rendererKind": surface["rendererKind"],
        "backend": surface["backend"],
        "textureRole": surface["textureRole"],
        "particleRole": surface["particleRole"],
        "anchor": surface["anchor"],
        "channel": surface["channel"],
        "lane": surface["lane"],
        "emissionMode": surface["emissionMode"],
        "blend": surface["blend"],
        "particleSystemId": surface["particleSystemId"],
    }
    numeric_fields = {
        "scale": (0.15, 5.0, False, True),
        "density": (0.0, 1.0, False, True),
        "duration": (3, 120, True, True),
        "alpha": (0.0, 1.0, False, True),
        "spread": (0.0, 2.0, False, True),
        "jitter": (0.0, 1.5, False, True),
        "budgetWeight": (0.1, 4.0, False, True),
        "signatureWeight": (0.0, 1.0, False, True),
        "visualCost": (0.0, 1.0, False, True),
        "fadeIn": (0.0, 0.8, False, True),
        "fadeOut": (0.0, 0.8, False, True),
        "phaseOffset": (-1.0, 1.0, False, False),
        "startTick": (0, 120, True, False),
        "repeatEvery": (0, 120, True, False),
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

        channel = normalized_enums.get("channel")
        pid = normalized_enums.get("particleSystemId")
        
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
    return str(value or "").strip() in {"pl:glow", "pl:shard", "pl:smoke", "pl:spark", "dust"}

__all__ = [
    "vfx_director_surface",
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
