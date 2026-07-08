from __future__ import annotations

from typing import Any

from infini_local.core.runtime_effect_policy import onhit_uses_burst_dust_feedback


# AGENT MAP: pure engine-pressure/balance sanity helpers used by the
# runtime-authoring pipeline and the HTTP facade. These estimate/clamp technical
# projectile/dust pressure only; do not add creative policy or category routing.


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
    reliability = max(0.35, min(1.35, float(genome.get("reliability") or 1.0)))
    range_tiles = max(3.0, min(120.0, float(genome.get("rangeTiles") or 35)))
    self_lock = max(0.0, min(120.0, float(genome.get("selfLockTicks") or 0)))
    miss_punish = max(0.0, min(1.0, float(genome.get("missPunish") or 0)))
    child_pressure = _child_spawn_estimate(genome)
    cost = 1.0
    cost *= 1.0 + (shot_count - 1.0) * 0.55
    cost *= 1.0 + min(1.35, pierce * 0.22)
    cost *= 1.0 + min(2.4, (aoe ** 1.55) * 0.045)
    cost *= 1.0 + homing * 0.72
    cost *= 1.0 + min(0.55, max(0.0, lifetime - 90.0) / 700.0)
    cost *= 1.0 + extra_updates * 0.16
    cost *= 1.0 + min(0.32, max(0.0, range_tiles - 35.0) / 220.0)
    cost *= 1.0 + min(1.10, child_pressure * 0.075)
    cost *= reliability
    discount = 1.0 + min(0.65, self_lock / 150.0) + miss_punish * 0.22
    return max(0.35, cost / discount)


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
    if onhit in {"starburst", "starfall", "radial_beams", "spore_cloud", "mini_missiles", "vortex_spawn"}:
        authored = genome.get("splitCount") if genome.get("splitCount") is not None else genome.get("maxChildProjectiles")
        if authored is not None:
            return max(0.0, min(8.0, float(authored or 0)))
        if onhit in {"starburst", "starfall", "radial_beams"}:
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
    reliability = max(0.05, min(1.35, float(genome.get("reliability") or 1.0)))
    uses_per_second = 60.0 / use_time
    active_primary = shot_count * uses_per_second * (lifetime / 60.0)
    child_per_proc = _child_spawn_estimate(genome)
    # Children are usually proc-gated/on-hit and depth-limited, so this is intentionally conservative.
    child_pressure = child_per_proc * uses_per_second * reliability * 0.55
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
        "activePrimaryProjectiles": round(active_primary, 3),
        "childProjectilesPerProc": round(child_per_proc, 3),
        "activeProjectileEstimate": round(active_projectiles, 3),
        "dustPerSecondEstimate": round(dust_per_second, 3),
        "networkSyncPressureEstimate": round(sync_pressure, 3),
    }


def sanitize_genome_engine(genome: dict[str, Any], stage: dict[str, Any]) -> dict[str, Any]:
    """Clamp only engine-pressure outliers. Does not judge creativity or similarity."""
    g = dict(genome)
    power = max(0.5, float(stage.get("powerBudget") or 1.0))
    max_active = 22.0 + power * 8.0
    max_sync = 26.0 + power * 8.0

    # First pass: technical pressure only. Preserve long-lived identity (orbit/boomerang/field)
    # unless the entity budget is actually unsafe; prefer trimming multiplicity/extraUpdates
    # before shortening lifetime. This keeps the validator from becoming a deterministic designer.
    for _ in range(5):
        metrics = estimate_engine_metrics(g, stage)
        if metrics["activeProjectileEstimate"] <= max_active and metrics["networkSyncPressureEstimate"] <= max_sync:
            break
        if int(g.get("shotCount") or 1) > 1:
            g["shotCount"] = max(1, int(g.get("shotCount") or 1) - 1)
        elif int(g.get("extraUpdates") or 0) > 0:
            g["extraUpdates"] = max(0, int(g.get("extraUpdates") or 0) - 1)
        elif float(g.get("lifetimeTicks") or 90) > 45:
            long_lived = str(g.get("movement") or "") in {"orbit", "boomerang", "returning_glaive", "drift", "vortex_orb", "blackhole_pull", "expanding_wave"}
            floor = 80 if long_lived else 35
            g["lifetimeTicks"] = max(floor, int(float(g.get("lifetimeTicks") or 90) * (0.88 if long_lived else 0.80)))
        else:
            break

    metrics = estimate_engine_metrics(g, stage)
    # Derived runtime knobs for C# projectile implementation. In v0.4.3 child projectiles
    # are only allocated when the LLM explicitly authored a secondary-projectile/on-hit child plan.
    child_estimate = int(max(0, round(_child_spawn_estimate(g))))
    child_requested = child_estimate > 0 or int(float(g.get("splitCount") or 0)) > 0
    if child_requested:
        authored_cap = int(float(g.get("maxChildProjectiles") or 0))
        exact_cap = authored_cap if authored_cap > 0 else max(1, child_estimate)
        g["maxChildProjectiles"] = int(max(1, min(36, exact_cap)))
        g["maxChildDepth"] = 1
    else:
        g["maxChildProjectiles"] = 0
        g["maxChildDepth"] = 0

    # Dust in Terraria is controlled by actual emission frequency/scale/alpha calls.
    # Preserve explicit 0 from runtimePlan: 0 means no ambient dust.
    target_dust_per_second = 120.0 + power * 24.0
    if g.get("dustSpawnDenom") is None:
        denom = int(max(2, min(20, 3 + max(0.0, metrics["activeProjectileEstimate"] - 8.0) / 3.0)))
        g["dustSpawnDenom"] = denom
        for _ in range(4):
            metrics = estimate_engine_metrics(g, stage)
            if metrics["dustPerSecondEstimate"] <= target_dust_per_second or int(g["dustSpawnDenom"]) >= 20:
                break
            g["dustSpawnDenom"] = int(g["dustSpawnDenom"]) + 2
    else:
        try:
            g["dustSpawnDenom"] = int(max(0, min(20, float(g.get("dustSpawnDenom")))))
        except Exception:
            g["dustSpawnDenom"] = 0
    metrics = estimate_engine_metrics(g, stage)

    # Burst dust is visual feedback, not damage. Preserve authored 0 for ambient/no-hit
    # dust, but a concrete burst-style on-hit executor needs at least a tiny visual cap.
    if g.get("burstDustCap") is None:
        g["burstDustCap"] = int(max(0, min(28, 6 + power * 2)))
    else:
        try:
            g["burstDustCap"] = int(max(0, min(28, float(g.get("burstDustCap")))))
        except Exception:
            g["burstDustCap"] = 0
    onhit_key = str(g.get("onHit") or "").strip().lower()
    try:
        onhit_code = int(float(g.get("onHitCode") or 0))
    except Exception:
        onhit_code = 0
    if int(g.get("burstDustCap") or 0) <= 0 and onhit_uses_burst_dust_feedback(onhit_key, onhit_code):
        g["burstDustCap"] = int(max(4, min(24, 6 + power * 2)))
        g.setdefault("engineSanityRepairs", []).append("burst_onhit_requires_nonzero_burstDustCap")
    g["engineMetrics"] = metrics
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
    "behavior_cost_multiplier",
    "estimate_engine_metrics",
    "sanitize_genome_engine",
    "clamp_float",
    "dict_get_ci",
]
