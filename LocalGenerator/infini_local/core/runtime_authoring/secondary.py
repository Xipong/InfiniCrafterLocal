from __future__ import annotations

from typing import Any

from infini_local.core.runtime_authoring.common import _clamp, _norm_name, _num
from infini_local.core.runtime_authoring.schema import NUMERIC_LIMITS
from infini_local.core.runtime_secondary_policy import (
    SECONDARY_TRIGGER_ON_EXPIRE,
    SECONDARY_TRIGGER_ON_HIT,
    normalize_secondary_trigger,
)

# AGENT MAP: compilation of spawn_secondary_projectiles only.
# Keep trigger/count/damage/lifetime rules here. Do not grow compiler.py with
# another copy and do not infer child gameplay from names, tooltip or materials.

_CHILD_ONHITS = {
    "split", "starburst", "overhead_barrage", "radial_beams", "mini_missiles",
    "vortex_spawn", "spore_cloud",
}
_DEBUFF_ONHITS = {"burn", "frostburn", "poison", "shadowflame", "bleed"}


def apply_secondary_projectile_calls(
    patch: dict[str, Any],
    secondary_calls: list[dict[str, Any]],
    *,
    secondary_from_rejected_primary: bool = False,
) -> dict[str, Any]:
    """Compile one explicit secondary trigger family into bounded AttackSpec fields.

    Multiple calls may contribute counts/knobs, but they must use the same exact
    trigger. Mixed triggers are rejected instead of creating an implicit state graph.
    """
    total_secondary = 0
    selected_trigger = ""
    spread_values: list[float] = []
    damage_values: list[float] = []
    lifetime_values: list[float] = []
    bias_values: list[float] = []
    materials: list[str] = []
    shapes: list[str] = []
    accepted_indices: list[Any] = []
    rejected: list[dict[str, Any]] = []

    for call in secondary_calls:
        raw_trigger = call.get("trigger")
        trigger = normalize_secondary_trigger(raw_trigger)
        count = int(round(_clamp(call.get("count"), "splitCount", 0) or 0))
        if count <= 0:
            continue
        if not trigger:
            rejected.append({
                "index": call.get("_index"),
                "trigger": _norm_name(raw_trigger),
                "count": count,
                "reason": "unsupported_secondary_trigger",
            })
            continue
        if selected_trigger and trigger != selected_trigger:
            rejected.append({
                "index": call.get("_index"),
                "trigger": trigger,
                "count": count,
                "reason": f"mixed_secondary_triggers_not_supported:{selected_trigger}",
            })
            continue
        selected_trigger = trigger
        total_secondary += count
        accepted_indices.append(call.get("_index"))
        for key, target, limit_name in (
            ("spreadRadians", spread_values, "secondarySpreadRadians"),
            ("damageMultiplier", damage_values, "secondaryDamageMultiplier"),
            ("lifetimeTicks", lifetime_values, "secondaryLifetimeTicks"),
            ("sameTargetBias", bias_values, "sameTargetBias"),
        ):
            value = _clamp(call.get(key), limit_name) if call.get(key) not in (None, "") else None
            if value is not None:
                target.append(float(value))
        if call.get("material") not in (None, ""):
            materials.append(str(call.get("material"))[:40])
        if call.get("projectileShape") not in (None, ""):
            shapes.append(str(call.get("projectileShape"))[:80])

    if total_secondary <= 0:
        existing_split = int(_num(patch.get("splitCount"), 0) or 0)
        current_onhit = _norm_name(patch.get("onHit"))
        if current_onhit in _CHILD_ONHITS and existing_split > 0:
            patch.setdefault("maxChildProjectiles", int(max(1, min(48, existing_split))))
            patch.setdefault("maxChildDepth", 1)
        elif current_onhit == "split" and existing_split > 0:
            patch.setdefault("maxChildProjectiles", int(max(1, min(48, existing_split))))
            patch.setdefault("maxChildDepth", 1)
        else:
            patch["splitCount"] = 0
            patch.setdefault("maxChildProjectiles", 0)
            if current_onhit == "split":
                patch["onHitDemotedReason"] = "split_requires_secondary_count_gt_0"
                patch["onHit"] = "none"
        if rejected:
            patch["rejectedSecondaryCalls"] = rejected[:8]
        return patch

    current_onhit = _norm_name(patch.get("onHit"))
    existing_split = int(_num(patch.get("splitCount"), 0) or 0)
    runtime_family = _norm_name(patch.get("runtimeFamily") or patch.get("delivery"))
    if selected_trigger == SECONDARY_TRIGGER_ON_EXPIRE and runtime_family == "overhead_barrage":
        rejected.extend({
            "index": index,
            "trigger": SECONDARY_TRIGGER_ON_EXPIRE,
            "count": total_secondary,
            "reason": "on_expire_conflicts_with_overhead_barrage_child_budget",
        } for index in accepted_indices[:8])
        patch["splitCount"] = existing_split if current_onhit in _CHILD_ONHITS else 0
        patch.pop("secondaryTrigger", None)
        patch["rejectedSecondaryCalls"] = rejected[:8]
        return patch
    if selected_trigger == SECONDARY_TRIGGER_ON_EXPIRE and current_onhit in _CHILD_ONHITS and existing_split > 0:
        rejected.extend({
            "index": index,
            "trigger": SECONDARY_TRIGGER_ON_EXPIRE,
            "count": total_secondary,
            "reason": "on_expire_conflicts_with_child_producing_on_hit",
        } for index in accepted_indices[:8])
        patch.setdefault("maxChildProjectiles", int(max(1, min(48, existing_split))))
        patch.setdefault("maxChildDepth", 1)
        patch["rejectedSecondaryCalls"] = rejected[:8]
        return patch

    split_count = int(max(1, min(NUMERIC_LIMITS["splitCount"][1], total_secondary)))
    patch["secondaryTrigger"] = selected_trigger or SECONDARY_TRIGGER_ON_HIT
    patch["splitCount"] = split_count
    patch["maxChildProjectiles"] = int(max(1, min(48, split_count)))
    patch["maxChildDepth"] = 1

    current_onhit = _norm_name(patch.get("onHit"))

    if patch["secondaryTrigger"] == SECONDARY_TRIGGER_ON_HIT:
        if not current_onhit or current_onhit in {"none", "burst"}:
            patch["onHit"] = "split"
            patch["onHitForcedBySecondary"] = True
        elif current_onhit in _DEBUFF_ONHITS:
            patch.setdefault("debuffHint", current_onhit)
            patch.setdefault("debuffTime", 180 if current_onhit != "burn" else 240)
            patch["onHit"] = "split"
            patch["onHitForcedBySecondary"] = True
            patch["secondaryPreservedDebuffOnHit"] = current_onhit
        elif current_onhit not in _CHILD_ONHITS:
            if secondary_from_rejected_primary and runtime_family in {"swing", "thrust"}:
                patch["secondaryPreservedAlongsidePrimaryOnHit"] = current_onhit
            else:
                patch["secondarySuppressedByPrimaryOnHit"] = current_onhit
                patch["splitCount"] = 0
                patch["maxChildProjectiles"] = 0
                patch["maxChildDepth"] = 0
        elif current_onhit != "split":
            patch.setdefault("maxChildProjectiles", split_count)
            patch.setdefault("maxChildDepth", 1)
    elif patch["secondaryTrigger"] == SECONDARY_TRIGGER_ON_EXPIRE:
        # Swing has no runtime projectile to expire. Other projectile-owned families
        # use the same finite GeneratedProjectile lifecycle and can execute this trigger.
        if runtime_family == "swing":
            patch["secondarySuppressedByRuntimeFamily"] = "on_expire_requires_runtime_projectile"
            patch["splitCount"] = 0
            patch["maxChildProjectiles"] = 0
            patch["maxChildDepth"] = 0

    if spread_values:
        patch["secondarySpreadRadians"] = round(max(spread_values), 3)
    if damage_values:
        patch["secondaryDamageMultiplier"] = round(sum(damage_values) / len(damage_values), 3)
    if lifetime_values:
        patch["secondaryLifetimeTicks"] = int(round(max(lifetime_values)))
    if bias_values:
        patch["sameTargetBias"] = round(sum(bias_values) / len(bias_values), 3)
    if materials:
        patch["secondaryMaterial"] = ", ".join(dict.fromkeys(materials))[:80]
    if shapes:
        patch["secondaryProjectileShape"] = "; ".join(dict.fromkeys(shapes))[:120]
        patch.setdefault("projectileShape", patch["secondaryProjectileShape"])

    melee_core = runtime_family in {"swing", "thrust"}
    explicit_child_body = bool(materials or shapes)
    if melee_core and not explicit_child_body:
        patch["secondarySuppressedByMeleeCore"] = "spawn_secondary_projectiles_requires_secondaryMaterial_or_projectileShape_for_swing_thrust"
        patch["splitCount"] = 0
        patch["maxChildProjectiles"] = 0
        patch["maxChildDepth"] = 0
        patch["secondaryDamageMultiplier"] = 0
        if patch.get("onHitForcedBySecondary"):
            patch["onHit"] = "none"
            patch.pop("onHitForcedBySecondary", None)

    patch["secondaryCallIndices"] = [index for index in accepted_indices if index is not None]
    if rejected:
        patch["rejectedSecondaryCalls"] = rejected[:8]
    return patch


__all__ = ["apply_secondary_projectile_calls"]
