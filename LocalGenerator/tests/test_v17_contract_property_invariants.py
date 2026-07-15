from __future__ import annotations

from copy import deepcopy

from hypothesis import given, settings, strategies as st
import pytest

from infini_local.core.runtime_authoring import (
    compile_runtime_plan_to_genome_patch,
    normalize_runtime_plan_inplace,
)
from infini_local.core.runtime_secondary_policy import normalize_secondary_trigger
from infini_local.core.runtime_sentry_policy import SENTRY_CHILD_ONHIT, SENTRY_MAX_TOTAL_SHOTS


@st.composite
def canonical_calls(draw: st.DrawFn) -> list[dict]:
    call_count = draw(st.integers(min_value=1, max_value=4))
    out: list[dict] = []
    for _ in range(call_count):
        kind = draw(st.sampled_from(["plain", "charge", "sentry", "overhead", "stats"]))
        if kind == "plain":
            out.append({
                "fn": "shoot_projectile",
                "params": {
                    "runtimeFamily": "shoot",
                    "delivery": "shoot",
                    "pierce": draw(st.integers(min_value=-1, max_value=10)),
                    "shotCount": draw(st.integers(min_value=1, max_value=8)),
                },
            })
        elif kind == "charge":
            out.append({
                "fn": "fire_ranged_weapon",
                "params": {
                    "family": "charge_release",
                    "chargeTicks": draw(st.integers(min_value=1, max_value=300)),
                    "chargePowerMultiplier": draw(st.floats(min_value=1.0, max_value=3.0, allow_nan=False, allow_infinity=False)),
                },
            })
        elif kind == "sentry":
            out.append({
                "fn": "deploy_sentry",
                "params": {
                    "placement": draw(st.sampled_from(["grounded", "floating"])),
                    "attackIntervalTicks": draw(st.integers(min_value=12, max_value=180)),
                    "targetRangeTiles": draw(st.floats(min_value=8.0, max_value=60.0, allow_nan=False, allow_infinity=False)),
                    "helperLifetimeTicks": draw(st.integers(min_value=120, max_value=36000)),
                    "shotCount": draw(st.integers(min_value=1, max_value=4)),
                },
            })
        elif kind == "overhead":
            out.append({
                "fn": "shoot_projectile",
                "params": {
                    "runtimeFamily": "overhead_barrage",
                    "delivery": "shoot",
                    "delayTicks": draw(st.integers(min_value=0, max_value=300)),
                    "shotCount": draw(st.integers(min_value=1, max_value=8)),
                },
            })
        else:
            out.append({
                "fn": "set_item_stats",
                "params": {
                    "resultKind": "weapon",
                    "damageClass": draw(st.sampled_from(["melee", "ranged", "magic", "summon"])),
                    "useTimeTicks": draw(st.integers(min_value=6, max_value=150)),
                    "useAnimationTicks": draw(st.integers(min_value=6, max_value=150)),
                },
            })
    return out


@given(canonical_calls())
@settings(max_examples=80, deadline=None)
def test_runtime_plan_normalization_is_idempotent(calls: list[dict]) -> None:
    payload = {"runtimePlan": {"engineCalls": calls}}
    normalize_runtime_plan_inplace(payload)
    once = deepcopy(payload)
    normalize_runtime_plan_inplace(payload)
    assert payload == once


@given(st.text(min_size=1).filter(lambda value: value.strip().lower().replace("-", "_").replace(" ", "_") not in {"on_hit", "on_expire"}))
@settings(max_examples=50, deadline=None)
def test_unknown_secondary_trigger_never_becomes_executable(trigger: str) -> None:
    assert normalize_secondary_trigger(trigger) == ""
    patch = compile_runtime_plan_to_genome_patch({
        "runtimePlan": {"engineCalls": [
            {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot"}},
            {"fn": "spawn_secondary_projectiles", "params": {"trigger": trigger, "count": 2}},
        ]}
    })
    assert patch.get("secondaryTrigger") in {None, ""}
    assert patch.get("splitCount", 0) == 0
    assert any(row.get("reason") == "unsupported_secondary_trigger" for row in patch.get("rejectedSecondaryCalls", []))


@given(
    delay=st.integers(min_value=0, max_value=300),
    beam_charge=st.integers(min_value=0, max_value=300),
)
@settings(max_examples=50, deadline=None)
def test_explicit_zero_and_bounded_values_survive_compilation(delay: int, beam_charge: int) -> None:
    overhead = compile_runtime_plan_to_genome_patch({
        "runtimePlan": {"engineCalls": [{
            "fn": "shoot_projectile",
            "params": {"runtimeFamily": "overhead_barrage", "delivery": "shoot", "delayTicks": delay},
        }]}
    })
    assert overhead["delayTicks"] == delay

    beam = compile_runtime_plan_to_genome_patch({
        "runtimePlan": {"engineCalls": [{
            "fn": "cast_magic_weapon",
            "params": {"family": "channelled_beam", "beamChargeTicks": beam_charge},
        }]}
    })
    assert beam["beamChargeTicks"] == beam_charge


@given(
    interval=st.integers(min_value=12, max_value=180),
    lifetime=st.integers(min_value=120, max_value=36000),
    volley=st.integers(min_value=1, max_value=4),
)
@settings(max_examples=80, deadline=None)
def test_sentry_total_shot_budget_is_always_bounded(interval: int, lifetime: int, volley: int) -> None:
    patch = compile_runtime_plan_to_genome_patch({
        "runtimePlan": {"engineCalls": [{
            "fn": "deploy_sentry",
            "params": {
                "placement": "grounded",
                "attackIntervalTicks": interval,
                "helperLifetimeTicks": lifetime,
                "shotCount": volley,
            },
        }]}
    })
    assert 1 <= patch["maxChildProjectiles"] <= SENTRY_MAX_TOTAL_SHOTS
    assert patch["maxChildDepth"] == 1
    assert patch["runtimeFamily"] == "sentry"


@given(
    charge_ticks=st.integers(min_value=1, max_value=300),
    multiplier=st.floats(min_value=1.0, max_value=3.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=35, deadline=None)
def test_charge_compiler_owned_fields_survive_final_projection(charge_ticks: int, multiplier: float) -> None:
    from infini_local.qa.runtime_proof import build_gameplay_seam_report

    report = build_gameplay_seam_report({
        "caseId": "property_charge_projection",
        "description": "property charge projection",
        "input": {
            "name": "Contract Charge Blade",
            "runtimePlan": {"engineCalls": [
                {"fn": "set_item_stats", "params": {
                    "resultKind": "weapon", "damageClass": "ranged", "damage": 15,
                    "useTimeTicks": 20, "useAnimationTicks": 20,
                }},
                {"fn": "fire_ranged_weapon", "params": {
                    "family": "charge_release", "chargeTicks": charge_ticks,
                    "chargePowerMultiplier": multiplier,
                    "movement": "straight", "speed": 10.0, "rangeTiles": 55.0,
                    "lifetimeTicks": 120, "shotCount": 1,
                    "spreadRadians": 0.0, "pierce": 1,
                }},
            ]},
        },
        "expectGameplay": {},
    })
    assert report["error"] is None
    attack = report["item"]["attack"]
    assert attack["runtimeFamily"] == "charge_release"
    assert attack["chargeTicks"] == charge_ticks
    expected = compile_runtime_plan_to_genome_patch({"runtimePlan": {"engineCalls": [{
        "fn": "fire_ranged_weapon", "params": {
            "family": "charge_release", "chargeTicks": charge_ticks,
            "chargePowerMultiplier": multiplier,
            "movement": "straight", "speed": 10.0, "rangeTiles": 55.0,
            "lifetimeTicks": 120, "shotCount": 1,
            "spreadRadians": 0.0, "pierce": 1,
        },
    }]}})
    assert attack["chargePowerMultiplier"] == expected["chargePowerMultiplier"]


@given(
    interval=st.integers(min_value=12, max_value=180),
    target_range=st.floats(min_value=8.0, max_value=60.0, allow_nan=False, allow_infinity=False),
    lifetime=st.integers(min_value=120, max_value=36000),
    volley=st.integers(min_value=1, max_value=4),
)
@settings(max_examples=30, deadline=None)
def test_sentry_compiler_owned_fields_survive_final_projection(
    interval: int, target_range: float, lifetime: int, volley: int,
) -> None:
    from infini_local.qa.runtime_proof import build_gameplay_seam_report

    report = build_gameplay_seam_report({
        "caseId": "property_sentry_projection",
        "description": "property sentry projection",
        "input": {
            "name": "Contract Sentry Staff",
            "runtimePlan": {"engineCalls": [
                {"fn": "set_item_stats", "params": {
                    "resultKind": "weapon", "damageClass": "summon", "damage": 15,
                    "useTimeTicks": 20, "useAnimationTicks": 20,
                }},
                {"fn": "deploy_sentry", "params": {
                    "placement": "grounded", "attackIntervalTicks": interval,
                    "targetRangeTiles": target_range, "helperLifetimeTicks": lifetime,
                    "movement": "straight", "speed": 9.0,
                    "shotCount": volley, "spreadRadians": 0.0, "pierce": 1,
                }},
            ]},
        },
        "expectGameplay": {},
    })
    assert report["error"] is None
    attack = report["item"]["attack"]
    assert attack["runtimeFamily"] == "sentry"
    assert attack["sentryAttackIntervalTicks"] == interval
    expected = compile_runtime_plan_to_genome_patch({"runtimePlan": {"engineCalls": [{
        "fn": "deploy_sentry", "params": {
            "placement": "grounded", "attackIntervalTicks": interval,
            "targetRangeTiles": target_range, "helperLifetimeTicks": lifetime,
            "movement": "straight", "speed": 9.0,
            "shotCount": volley, "spreadRadians": 0.0, "pierce": 1,
        },
    }]}})
    assert attack["sentryTargetRangeTiles"] == round(float(expected["sentryTargetRangeTiles"]), 2)
    assert attack["sentryLifetimeTicks"] == lifetime
    assert attack["shotCount"] == volley
    assert 1 <= attack["maxChildProjectiles"] <= SENTRY_MAX_TOTAL_SHOTS


@given(
    pierce=st.just(-1),
    lifetime=st.integers(min_value=300, max_value=900),
    split=st.integers(min_value=1, max_value=8),
)
@settings(max_examples=35, deadline=None)
def test_infinite_pierce_long_lifetime_split_stays_bounded(pierce: int, lifetime: int, split: int) -> None:
    patch = compile_runtime_plan_to_genome_patch({
        "runtimePlan": {"engineCalls": [
            {"fn": "shoot_projectile", "params": {
                "runtimeFamily": "shoot", "delivery": "shoot",
                "pierce": pierce, "lifetimeTicks": lifetime,
            }},
            {"fn": "spawn_secondary_projectiles", "params": {
                "trigger": "on_hit", "count": split,
            }},
        ]}
    })
    assert patch["pierce"] == -1
    assert patch["lifetimeTicks"] == lifetime
    assert patch["splitCount"] == split
    assert patch["maxChildProjectiles"] == split
    assert patch["maxChildDepth"] == 1


@given(delay=st.integers(min_value=0, max_value=300), children=st.integers(min_value=1, max_value=8))
@settings(max_examples=30, deadline=None)
def test_overhead_barrage_rejects_competing_on_expire_child_budget(delay: int, children: int) -> None:
    patch = compile_runtime_plan_to_genome_patch({
        "runtimePlan": {"engineCalls": [
            {"fn": "shoot_projectile", "params": {
                "runtimeFamily": "overhead_barrage", "delivery": "shoot",
                "delayTicks": delay, "shotCount": 3,
            }},
            {"fn": "spawn_secondary_projectiles", "params": {
                "trigger": "on_expire", "count": children,
            }},
        ]}
    })
    assert patch["runtimeFamily"] == "overhead_barrage"
    assert patch["delayTicks"] == delay
    assert patch.get("splitCount", 0) == 0
    assert any(
        row.get("reason") == "on_expire_conflicts_with_overhead_barrage_child_budget"
        for row in patch.get("rejectedSecondaryCalls", [])
    )


@given(on_hit=st.sampled_from(sorted(SENTRY_CHILD_ONHIT)), volley=st.integers(min_value=1, max_value=4))
@settings(max_examples=35, deadline=None)
def test_sentry_child_producing_onhit_is_always_rejected(on_hit: str, volley: int) -> None:
    with pytest.raises(ValueError, match="sentry_does_not_support_child_producing_onhit"):
        compile_runtime_plan_to_genome_patch({
            "runtimePlan": {"engineCalls": [{
                "fn": "deploy_sentry",
                "params": {"placement": "grounded", "shotCount": volley, "onHit": on_hit},
            }]}
        })


@given(ammo_for=st.sampled_from(["arrow", "bullet"]))
@settings(max_examples=12, deadline=None)
def test_charge_release_with_vanilla_ammo_is_always_rejected(ammo_for: str) -> None:
    with pytest.raises(ValueError, match="charge_release_does_not_support_vanilla_ammo"):
        compile_runtime_plan_to_genome_patch({
            "runtimePlan": {"engineCalls": [{
                "fn": "fire_ranged_weapon",
                "params": {
                    "family": "charge_release",
                    "ammoFor": ammo_for,
                    "chargeTicks": 45,
                },
            }]}
        })


@given(count=st.integers(min_value=1, max_value=8), trigger=st.sampled_from(["on_hit", "on_expire"]))
@settings(max_examples=24, deadline=None)
def test_sentry_secondary_projectile_trigger_is_always_rejected(count: int, trigger: str) -> None:
    with pytest.raises(ValueError, match="sentry_does_not_support_secondary_projectile_triggers"):
        compile_runtime_plan_to_genome_patch({
            "runtimePlan": {"engineCalls": [
                {"fn": "deploy_sentry", "params": {"placement": "floating"}},
                {"fn": "spawn_secondary_projectiles", "params": {"trigger": trigger, "count": count}},
            ]}
        })
