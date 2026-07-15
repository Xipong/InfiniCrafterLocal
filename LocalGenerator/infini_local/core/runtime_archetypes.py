from __future__ import annotations

import math
from typing import Any

from infini_local.core.runtime_overhead_barrage_policy import (
    OVERHEAD_BARRAGE_RUNTIME_FAMILY,
    apply_overhead_barrage_contract,
    normalize_overhead_barrage_family,
)

RUNTIME_ARCHETYPE_SCHEMA = "infini.runtime-archetype.v1"

KNOWN_SOURCES = {"none", "generated", "vanilla", "hybrid"}
KNOWN_FAMILIES = {
    "custom_executor",
    "boomerang",
    "yoyo",
    "flail",
    "whip",
    "held_swing",
    "held_thrust",
    "channel_beam",
    "charge_release",
    "overhead_barrage",
    "sentry",
    "secondary_attack",
    "unsupported",
}
KNOWN_PHASE_MODELS = {"none", "outbound_return", "charge_release", "swing_phase", "channel_hold"}
EXECUTABLE_FAMILIES = {"custom_executor", "boomerang", "yoyo", "flail", "whip", "held_swing", "held_thrust", "channel_beam", "charge_release", "overhead_barrage", "sentry"}
PRESERVED_ONLY_FAMILIES = {"secondary_attack", "unsupported"}

KNOB_LIMITS: dict[str, tuple[float, float, str]] = {
    "returnDelayTicks": (0, 180, "int"),
    "outboundPierce": (-1, 20, "int"),
    "returnPierce": (-1, 50, "int"),
    "localImmunityTicks": (0, 60, "int"),
    "arcDegrees": (10, 220, "int"),
    "windupTicks": (0, 90, "int"),
    "activeTicks": (1, 120, "int"),
    "recoveryTicks": (0, 120, "int"),
    "chargeTicks": (0, 300, "int"),
    "chargePowerMultiplier": (1, 3, "float"),
    "beamWidthPx": (2, 96, "int"),
    "maxActiveProjectiles": (0, 32, "int"),
}
KNOWN_TEXT_KNOBS = {"trailProfile"}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _text(value: Any, max_len: int = 120) -> str:
    if value in (None, ""):
        return ""
    return str(value).replace("\0", " ").strip()[:max_len]


def _finite(value: Any, default: float) -> float:
    try:
        f = float(value)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _clamp(value: Any, lo: float, hi: float, default: float, kind: str = "int") -> int | float:
    f = max(lo, min(hi, _finite(value, default)))
    return int(round(f)) if kind == "int" else round(float(f), 3)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = _norm(value)
    return text in {"1", "true", "yes", "y", "on", "channel", "channelled", "channeled"}


def _default_phase_for_family(family: str) -> str:
    if family == "boomerang":
        return "outbound_return"
    if family in {"held_swing", "held_thrust", "whip"}:
        return "swing_phase"
    if family in {"channel_beam", "charge_release", "yoyo"}:
        return "channel_hold"
    if family == OVERHEAD_BARRAGE_RUNTIME_FAMILY:
        return "charge_release"
    return "none"


def normalize_override_knobs(raw: Any) -> dict[str, Any]:
    knobs = raw if isinstance(raw, dict) else {}
    out: dict[str, Any] = {}
    for key, value in knobs.items():
        name = str(key or "").strip()
        if not name:
            continue
        if name in KNOB_LIMITS:
            lo, hi, kind = KNOB_LIMITS[name]
            default = 18 if name == "beamWidthPx" else lo
            out[name] = _clamp(value, lo, hi, default, kind)
        elif name in KNOWN_TEXT_KNOBS:
            out[name] = _text(value, 64)
        else:
            # Unknown knobs are intentionally inert but preserved for debug/future schema.
            out[name] = value
    return out


def normalize_runtime_archetype(raw: Any) -> dict[str, Any]:
    obj = raw if isinstance(raw, dict) else {}
    source = _norm(obj.get("source"))
    if not source:
        source = "none"
    elif source not in KNOWN_SOURCES:
        source = "generated"

    family = normalize_overhead_barrage_family(_norm(obj.get("family"))) or "custom_executor"
    notes: list[str] = []
    if family not in KNOWN_FAMILIES:
        notes.append(f"unknown_family:{family}")
        family = "unsupported"

    phase = _norm(obj.get("phaseModel")) or _default_phase_for_family(family)
    if family == "boomerang" and phase != "outbound_return":
        notes.append("phaseModel_fixed_to_outbound_return")
        phase = "outbound_return"
    elif phase not in KNOWN_PHASE_MODELS:
        notes.append(f"unknown_phaseModel:{phase}")
        phase = _default_phase_for_family(family)

    support_status = _norm(obj.get("supportStatus"))
    if family in EXECUTABLE_FAMILIES:
        support_status = "executable"
    elif family in PRESERVED_ONLY_FAMILIES:
        support_status = "unsupported" if family == "unsupported" else "preserved_intent"
    elif support_status not in {"executable", "preserved_intent", "unsupported", "disabled_by_config"}:
        support_status = "unsupported"

    raw_notes = obj.get("supportNotes") if isinstance(obj.get("supportNotes"), list) else []
    support_notes = [_text(x, 160) for x in raw_notes if _text(x, 160)]
    support_notes.extend(notes)
    if family in PRESERVED_ONLY_FAMILIES and family != "unsupported":
        support_notes.append(f"{family}_preserved_not_executed")

    return {
        "schema": _text(obj.get("schema"), 64) or RUNTIME_ARCHETYPE_SCHEMA,
        "source": source,
        "family": family,
        "vanillaProjectileId": _text(obj.get("vanillaProjectileId"), 64),
        "vanillaItemId": _text(obj.get("vanillaItemId"), 64),
        "aiType": _text(obj.get("aiType"), 64),
        "channelled": _coerce_bool(obj.get("channelled")) or family in {"yoyo", "channel_beam", "charge_release"},
        "usesHeldProjectile": _coerce_bool(obj.get("usesHeldProjectile")) or family in {"yoyo", "flail", "whip", "held_thrust", "channel_beam", "charge_release"},
        "phaseModel": phase,
        "overrideKnobs": normalize_override_knobs(obj.get("overrideKnobs")),
        "supportStatus": support_status,
        "supportNotes": list(dict.fromkeys(x for x in support_notes if x))[:16],
    }


def _append_unique_list(data: dict[str, Any], key: str, values: list[str]) -> None:
    current = data.get(key) if isinstance(data.get(key), list) else []
    merged = list(dict.fromkeys([str(x) for x in current if x] + [str(x) for x in values if x]))
    data[key] = merged[:32]



def _has_utility_engine_calls(data: dict[str, Any]) -> bool:
    """True when the plan already authors a finite non-attack utility executor."""
    rp = data.get("runtimePlan") if isinstance(data.get("runtimePlan"), dict) else {}
    calls = rp.get("engineCalls") if isinstance(rp.get("engineCalls"), list) else []
    utility = {
        "accessory_effect",
        "armor_effect",
        "tool_capability",
        "mobility_effect",
        "hold_item_effect",

        "apply_player_effect_on_use",
    }
    for call in calls:
        if isinstance(call, dict) and str(call.get("fn") or "") in utility:
            return True
    return False

def _has_finite_executable_attack_patch(patch: dict[str, Any]) -> bool:
    """True when runtimePlan.engineCalls already compiled to a finite runtime primitive.

    This is based only on compiled engine-call fields, not item names, tooltip text,
    or visual prompts. It lets invalid high-level archetype words from the LLM
    fall back to the existing custom executor instead of converting playable items
    into unsupported intent.
    """
    runtime_family = _norm(patch.get("runtimeFamily"))
    delivery = _norm(patch.get("delivery"))
    movement = _norm(patch.get("movement"))
    if runtime_family in {"", "none", "unsupported"}:
        return False
    return bool(delivery or movement or patch.get("damage") or patch.get("shoot"))


def boomerang_hit_estimate_from_patch(patch: dict[str, Any]) -> dict[str, Any]:
    pierce = int(_finite(patch.get("pierce"), 0)) if str(patch.get("pierce", "")).lstrip("-").replace(".", "", 1).isdigit() else patch.get("pierce")
    return_pierce = patch.get("returnPierce", pierce)
    infinite = pierce == -1 or return_pierce == -1
    return {
        "schema": "infini.boomerang-hit-estimate.v1",
        "baselineHits": 3 if infinite else max(1, min(3, int(_finite(pierce, 0)) + 1)),
        "skillReturnHits": 5 if infinite else max(1, min(5, int(_finite(return_pierce, 0)) + 1)),
        "rareGeometryHits": 8 if infinite else max(1, min(8, int(_finite(return_pierce, 0)) + 2)),
        "scorerCapped": bool(infinite),
        "note": "Boomerang return pierce is phase potential; baseline DPS uses capped expected hits, not infinite pierce.",
    }


def compile_runtime_archetype_to_attack_patch(data: dict[str, Any], patch: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    patch = dict(patch or {})
    raw_present = isinstance(data.get("runtimeArchetype"), dict)
    if not raw_present:
        return patch, {"schema": "infini.archetype-compiler-report.v1", "active": False, "supportStatus": "omitted"}

    raw_spec = data.get("runtimeArchetype") if isinstance(data.get("runtimeArchetype"), dict) else {}
    raw_family_input = _norm(raw_spec.get("family")) if isinstance(raw_spec, dict) else ""
    raw_family = normalize_overhead_barrage_family(raw_family_input)
    if raw_family and raw_family not in KNOWN_FAMILIES and (_has_finite_executable_attack_patch(patch) or _has_utility_engine_calls(data)):
        raw_spec = dict(raw_spec)
        raw_spec["family"] = "custom_executor"
        raw_notes = raw_spec.get("supportNotes") if isinstance(raw_spec.get("supportNotes"), list) else []
        raw_spec["supportNotes"] = list(raw_notes) + [
            f"unknown_family:{raw_family}",
            "fell_back_to_custom_executor_from_engine_calls",
        ]
    elif raw_family == "unsupported" and (_has_finite_executable_attack_patch(patch) or _has_utility_engine_calls(data)):
        # LLM sometimes marks family=unsupported while still authoring finite utility/attack calls.
        raw_spec = dict(raw_spec)
        raw_spec["family"] = "custom_executor"
        raw_notes = raw_spec.get("supportNotes") if isinstance(raw_spec.get("supportNotes"), list) else []
        raw_spec["supportNotes"] = list(raw_notes) + [
            "unsupported_family_overridden_by_executable_engine_calls",
        ]
    spec = normalize_runtime_archetype(raw_spec)
    data["runtimeArchetype"] = spec
    family = spec["family"]
    knobs: dict[str, Any] = dict(spec.get("overrideKnobs") or {}) if isinstance(spec.get("overrideKnobs"), dict) else {}
    report: dict[str, Any] = {
        "schema": "infini.archetype-compiler-report.v1",
        "active": True,
        "family": family,
        "phaseModel": spec.get("phaseModel", "none"),
        "supportStatus": spec.get("supportStatus", ""),
        "appliedFields": {},
        "preservedKnobs": knobs,
        "warnings": [],
    }

    def apply(**fields: Any) -> None:
        for key, value in fields.items():
            if value not in (None, ""):
                patch[key] = value
                report["appliedFields"][key] = value

    consumed_knobs: set[str] = set()

    if family == "custom_executor":
        report["supportStatus"] = "executable"
    elif family == "boomerang":
        apply(runtimeFamily="returning", delivery="throw", movement="boomerang", weaponFamily="boomerang", archetypePhaseModel="outbound_return")
        if "localImmunityTicks" in knobs:
            patch["immunityCooldown"] = knobs["localImmunityTicks"]
            report["appliedFields"]["immunityCooldown"] = knobs["localImmunityTicks"]
            consumed_knobs.add("localImmunityTicks")
        patch["boomerangHitEstimate"] = boomerang_hit_estimate_from_patch(patch)
        report["supportStatus"] = "executable"
    elif family == "yoyo":
        apply(runtimeFamily="yoyo", delivery="yoyo", movement="yoyo_hover", weaponFamily="yoyo", archetypePhaseModel="channel_hold", channelUse=True)
        report["supportStatus"] = "executable"
    elif family == "flail":
        apply(runtimeFamily="flail", delivery="flail", movement="flail_tether", weaponFamily="flail", archetypePhaseModel="swing_phase")
        report["supportStatus"] = "executable"
    elif family == "whip":
        apply(runtimeFamily="whip", delivery="whip", movement="whip_lash", weaponFamily="whip", archetypePhaseModel="swing_phase", ownerHitCheck=True)
        report["supportStatus"] = "executable"
    elif family == "held_swing":
        apply(runtimeFamily="swing", delivery="swing", movement=patch.get("movement") or "straight", weaponFamily=patch.get("weaponFamily") or "broadsword", archetypePhaseModel="swing_phase")
        report["supportStatus"] = "executable"
    elif family == "held_thrust":
        apply(runtimeFamily="thrust", delivery="thrust", movement=patch.get("movement") or "straight", weaponFamily=patch.get("weaponFamily") or "spear", archetypePhaseModel="swing_phase", hideUseGraphic=True, disableItemMeleeHitbox=True, ownerHitCheck=True)
        report["supportStatus"] = "executable"
    elif family == "channel_beam":
        apply(runtimeFamily="beam", delivery="cast", movement="phase", weaponFamily=patch.get("weaponFamily") or "beam_staff", projectileFamily="beam", archetypePhaseModel="channel_hold", channelUse=True, hideUseGraphic=True, disableItemMeleeHitbox=True, ownerHitCheck=True)
        if "beamWidthPx" in knobs:
            patch["beamWidthPx"] = knobs["beamWidthPx"]
            report["appliedFields"]["beamWidthPx"] = knobs["beamWidthPx"]
            consumed_knobs.add("beamWidthPx")
        if "chargeTicks" in knobs:
            patch["beamChargeTicks"] = knobs["chargeTicks"]
            report["appliedFields"]["beamChargeTicks"] = knobs["chargeTicks"]
            consumed_knobs.add("chargeTicks")
        if "localImmunityTicks" in knobs:
            patch["immunityCooldown"] = knobs["localImmunityTicks"]
            report["appliedFields"]["immunityCooldown"] = knobs["localImmunityTicks"]
            consumed_knobs.add("localImmunityTicks")
        if "activeTicks" in knobs:
            report["warnings"].append("activeTicks_not_executed_for_hold_until_release_beam")
        report["supportStatus"] = "executable"
    elif family == "charge_release":
        apply(runtimeFamily="charge_release", delivery=patch.get("delivery") or "shoot", archetypePhaseModel="charge_release", channelUse=True, hideUseGraphic=True, disableItemMeleeHitbox=True, ownerHitCheck=True)
        if "chargeTicks" in knobs:
            patch["chargeTicks"] = knobs["chargeTicks"]
            report["appliedFields"]["chargeTicks"] = knobs["chargeTicks"]
            consumed_knobs.add("chargeTicks")
        if "chargePowerMultiplier" in knobs:
            patch["chargePowerMultiplier"] = knobs["chargePowerMultiplier"]
            report["appliedFields"]["chargePowerMultiplier"] = knobs["chargePowerMultiplier"]
            consumed_knobs.add("chargePowerMultiplier")
        report["supportStatus"] = "executable"
    elif family == "sentry":
        apply(runtimeFamily="sentry", delivery="summon", archetypePhaseModel="none", channelUse=False, hideUseGraphic=False, disableItemMeleeHitbox=True, ownerHitCheck=False)
        report["supportStatus"] = "executable"
    elif family == OVERHEAD_BARRAGE_RUNTIME_FAMILY:
        apply(
            runtimeFamily=OVERHEAD_BARRAGE_RUNTIME_FAMILY,
            delivery=patch.get("delivery") or "shoot",
            movement="phase",
            weaponFamily=patch.get("weaponFamily") or "ranged",
            projectileFamily=patch.get("projectileFamily") or "projectile",
            archetypePhaseModel="charge_release",
            hideUseGraphic=True,
            disableItemMeleeHitbox=True,
        )
        patch["delayTicks"] = knobs.get("chargeTicks", patch.get("delayTicks", 30))
        if "chargeTicks" in knobs:
            consumed_knobs.add("chargeTicks")
        apply_overhead_barrage_contract(patch)
        report["appliedFields"].update({
            "delayTicks": patch["delayTicks"],
            "shotCount": patch["shotCount"],
            "maxChildProjectiles": patch["maxChildProjectiles"],
            "maxChildDepth": 1,
        })
        report["supportStatus"] = "executable"
    else:
        report["supportStatus"] = spec.get("supportStatus") or "preserved_intent"
        report["warnings"].append(f"{family}_preserved_not_executed")
        _append_unique_list(data, "unsupportedPromises", [f"unsupported:{family}"])

    unused_knobs = sorted(set(knobs) - consumed_knobs)
    if unused_knobs:
        report["warnings"].extend(f"overrideKnob_not_executed:{key}" for key in unused_knobs)
        _append_unique_list(
            data,
            "unsupportedPromises",
            [f"runtimeArchetype.overrideKnob_not_executed:{key}" for key in unused_knobs],
        )

    patch["archetypeCompiler"] = report
    return patch, report
