from __future__ import annotations

from typing import Any


# AGENT MAP: pure engine-pressure/balance sanity helpers used by the
# runtime-authoring pipeline and the HTTP boundary. These estimate/clamp technical
# projectile/dust pressure only; do not add creative policy or category routing.


def effective_hit_cadence_ticks(genome: dict[str, Any], authored_use_time_ticks: float | int) -> float:
    """Return the real per-target damage cadence used by the executable runtime.

    Most projectiles create one damage opportunity per item use. A held beam stays alive
    and can hit the same NPC again when local immunity expires, so its damage envelope
    must use immunityCooldown rather than the item's spawn/use cadence. This is an exact
    runtime-family rule, not a weapon-name classifier.
    """
    try:
        use_time = max(6.0, min(150.0, float(authored_use_time_ticks)))
    except (TypeError, ValueError, OverflowError):
        use_time = 24.0
    if str(genome.get("runtimeFamily") or "").strip().lower() != "beam":
        return use_time
    try:
        cooldown = float(genome.get("immunityCooldown") or 12)
    except (TypeError, ValueError, OverflowError):
        cooldown = 12.0
    return max(4.0, min(60.0, cooldown))


def behavior_cost_multiplier(genome: dict[str, Any]) -> float:
    """Reference economy estimate, not the author of final stats.

    In production runtime-authoring mode this value is used for fallback/diagnostics and
    emergency sanity, not as a deterministic rewrite of sane LLM-authored damage.
    """
    shot_count = max(1.0, float(genome.get("shotCount") or 1))
    raw_pierce_for_cost = float(genome.get("pierce") if genome.get("pierce") is not None else 0)
    pierce = 8.0 if int(raw_pierce_for_cost) == -1 else max(0.0, raw_pierce_for_cost)
    aoe = max(0.0, float(genome.get("aoeRadiusTiles") or 0))
    homing = max(0.0, min(1.0, float(genome.get("homingStrength") or 0)))
    lifetime = max(20.0, min(1200.0, float(genome.get("lifetimeTicks") or 90)))
    extra_updates = max(0.0, min(3.0, float(genome.get("extraUpdates") or 0)))
    range_tiles = max(3.0, min(120.0, float(genome.get("rangeTiles") or 35)))
    child_pressure = _child_spawn_estimate(genome)
    runtime_family = str(genome.get("runtimeFamily") or "").strip().lower()
    beam_width = max(2.0, min(96.0, float(genome.get("beamWidthPx") or 14.0)))
    beam_charge = max(0.0, min(300.0, float(genome.get("beamChargeTicks") or 0.0)))
    pull_strength = max(0.0, min(1.0, float(genome.get("pullStrength") or 0.0)))
    pull_mode = str(genome.get("pullMode") or "none").strip().lower()
    cost = 1.0
    cost *= 1.0 + (shot_count - 1.0) * 0.55
    cost *= 1.0 + min(1.35, pierce * 0.22)
    cost *= 1.0 + min(2.4, (aoe ** 1.55) * 0.045)
    cost *= 1.0 + homing * 0.72
    cost *= 1.0 + min(0.55, max(0.0, lifetime - 90.0) / 700.0)
    cost *= 1.0 + extra_updates * 0.16
    cost *= 1.0 + min(0.32, max(0.0, range_tiles - 35.0) / 220.0)
    cost *= 1.0 + min(1.10, child_pressure * 0.075)
    if pull_mode in {"target_to_owner", "target_to_projectile"}:
        cost *= 1.0 + pull_strength * 0.35
    elif pull_mode == "owner_to_target":
        cost *= 1.0 + pull_strength * 0.25
    if runtime_family == "beam":
        # Persistent line collision can cover several targets even with shotCount=1.
        # Price geometry, while charge-up buys back a small amount of the cost.
        cost *= 1.20 + min(0.65, max(0.0, beam_width - 8.0) / 88.0)
        cost /= 1.0 + min(0.18, beam_charge / 600.0)
    # Only executable mechanics can buy or spend damage budget. Former metadata
    # (reliability/selfLockTicks/missPunish) never reached Terraria and is ignored.
    return max(0.35, cost)


def _child_spawn_estimate(genome: dict[str, Any]) -> float:
    onhit = str(genome.get("onHit") or "none")
    shot_count = max(1.0, float(genome.get("shotCount") or 1))
    aoe = max(0.0, float(genome.get("aoeRadiusTiles") or 0))
    if onhit in {"split"}:
        return max(0.0, min(8.0, float(genome.get("splitCount") if genome.get("splitCount") is not None else max(0.0, aoe + shot_count - 1.0))))
    if onhit in {"chain", "lightning_arc"}:
        authored = genome.get("chainCount") if genome.get("chainCount") is not None else genome.get("splitCount")
        if authored is not None:
            return max(0.0, min(8.0, float(authored or 0)))
        return 3.0 if onhit == "lightning_arc" else 2.0
    if onhit in {"starburst", "overhead_barrage", "radial_beams", "spore_cloud", "mini_missiles", "vortex_spawn"}:
        authored = genome.get("splitCount") if genome.get("splitCount") is not None else genome.get("maxChildProjectiles")
        if authored is not None:
            return max(0.0, min(8.0, float(authored or 0)))
        if onhit in {"starburst", "overhead_barrage", "radial_beams"}:
            return 7.0
        if onhit in {"spore_cloud", "mini_missiles"}:
            return min(8.0, 3.0 + aoe * 0.6)
        return 3.0
    return 0.0


def estimate_engine_metrics(genome: dict[str, Any], stage: dict[str, Any] | None = None) -> dict[str, Any]:
    """Derived engine-pressure metrics. These are functions, not LLM tags.

    Terraria has real Dust fields such as scale/alpha/velocity/fadeIn, but no universal
    'intensity'. We therefore estimate pressure from spawned projectiles, lifetime, useTime
    and dust emission cadence. This is a technical safety rail, not a fun/boring evaluator.
    """
    stage = stage or {}
    use_time = max(6.0, float(genome.get("useTimeTicks") or stage.get("useTime") or 24))
    shot_count = max(1.0, float(genome.get("shotCount") or 1))
    lifetime = max(10.0, min(1200.0, float(genome.get("lifetimeTicks") or 90)))
    extra_updates = max(0.0, min(3.0, float(genome.get("extraUpdates") or 0)))
    runtime_family = str(genome.get("runtimeFamily") or "").strip().lower()
    uses_per_second = 60.0 / use_time
    hit_cadence = effective_hit_cadence_ticks(genome, use_time)
    hit_events_per_second = 60.0 / hit_cadence if runtime_family == "beam" else uses_per_second
    # Exact held-root/sentry duplicate policies own one root projectile. Sentry shots are
    # bounded separately by authored cadence and lifetime.
    if runtime_family in {"beam", "charge_release", "sentry"}:
        active_primary = 1.0
    else:
        active_primary = shot_count * uses_per_second * (lifetime / 60.0)
    if runtime_family == "sentry":
        interval = max(12.0, min(180.0, float(genome.get("sentryAttackIntervalTicks") or 45)))
        shot_lifetime = max(5.0, min(180.0, float(genome.get("secondaryLifetimeTicks") or 24)))
        active_primary += shot_count * (60.0 / interval) * (shot_lifetime / 60.0)
    elif runtime_family == "charge_release":
        release_interval = max(use_time, max(10.0, min(300.0, float(genome.get("chargeTicks") or 10))))
        release_rate = 60.0 / release_interval
        active_primary += shot_count * release_rate * (lifetime / 60.0)
        hit_events_per_second = release_rate
    child_per_proc = _child_spawn_estimate(genome)
    # Children are proc-gated/on-hit and depth-limited. Persistent beams proc at
    # local-immunity cadence, not at item spawn cadence.
    child_pressure = child_per_proc * hit_events_per_second * 0.55
    active_projectiles = active_primary + child_pressure
    raw_dust = genome.get("dustSpawnDenom")
    try:
        dust_denom = float(raw_dust) if raw_dust is not None else 3.0
    except Exception:
        dust_denom = 3.0
    if dust_denom <= 0:
        dust_per_second = min(30.0, child_per_proc * 2.0)
    else:
        dust_denom = max(2.0, min(20.0, dust_denom))
        dust_per_second = active_projectiles * (60.0 / dust_denom) + min(30.0, child_per_proc * 2.0)
    sync_pressure = active_projectiles * (1.0 + extra_updates * 0.22)
    return {
        "usesPerSecond": round(uses_per_second, 3),
        "hitEventsPerSecond": round(hit_events_per_second, 3),
        "effectiveHitCadenceTicks": round(hit_cadence, 3),
        "activePrimaryProjectiles": round(active_primary, 3),
        "childProjectilesPerProc": round(child_per_proc, 3),
        "activeProjectileEstimate": round(active_projectiles, 3),
        "dustPerSecondEstimate": round(dust_per_second, 3),
        "networkSyncPressureEstimate": round(sync_pressure, 3),
    }


def sanitize_genome_engine(genome: dict[str, Any], stage: dict[str, Any]) -> dict[str, Any]:
    """Attach pressure diagnostics without silently redesigning an authored genome.

    Canonical runtime-plan validation owns rejection and absolute bounds. A late helper
    must not lower shot count, lifetime, update rate, or create dust because a derived
    pressure score or progression budget dislikes the model's explicit choice.
    """
    g = dict(genome)

    # Child recursion caps are executor bookkeeping derived only from explicit child
    # mechanics. They constrain recursive fan-out without changing the authored count,
    # damage, spread, lifetime, or trigger of the first-generation children.
    child_estimate = int(max(0, round(_child_spawn_estimate(g))))
    runtime_family = str(g.get("runtimeFamily") or "").strip().lower()
    child_requested = runtime_family == "sentry" or child_estimate > 0 or int(float(g.get("splitCount") or 0)) > 0
    if child_requested:
        authored_cap = int(float(g.get("maxChildProjectiles") or 0))
        exact_cap = authored_cap if authored_cap > 0 else max(1, child_estimate)
        cap_limit = 48 if runtime_family == "sentry" else 36
        g["maxChildProjectiles"] = int(max(1, min(cap_limit, exact_cap)))
        g["maxChildDepth"] = int(max(1, min(1, float(g.get("maxChildDepth") or 1))))
    else:
        g["maxChildProjectiles"] = 0
        g["maxChildDepth"] = 0

    # Explicit zero is meaningful. Missing visual emission fields are neutral rather
    # than an invitation for code to add visual feedback on the LLM's behalf.
    for field, upper in (("dustSpawnDenom", 20), ("burstDustCap", 40)):
        try:
            g[field] = int(max(0, min(upper, float(g.get(field) or 0))))
        except (TypeError, ValueError, OverflowError):
            g[field] = 0

    g["engineMetrics"] = estimate_engine_metrics(g, stage)
    return g


def clamp_float(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except Exception:
        return default


def dict_get_ci(d: dict[str, Any], name: str, default: Any = None) -> Any:
    if not isinstance(d, dict):
        return default
    if name in d:
        return d.get(name)
    pascal = name[:1].upper() + name[1:]
    if pascal in d:
        return d.get(pascal)
    lower = name.lower()
    for k, v in d.items():
        if str(k).lower() == lower:
            return v
    return default


__all__ = [
    "effective_hit_cadence_ticks",
    "behavior_cost_multiplier",
    "estimate_engine_metrics",
    "sanitize_genome_engine",
    "clamp_float",
    "dict_get_ci",
]
