"""Owner-contract tests for runtime_plan_validation_report gaps and ordering.

Covers:
1. anti-spoof strict raw boundary (bare ``_normalization`` must not skip)
2. every authored apply_on_hit_effect call is validated in order
3. consumable_weapon low stack/yield warning names consumable_weapon
4. ordered rule-block decomposition preserves error/warning contract order
"""
from __future__ import annotations

import ast
from copy import deepcopy
from pathlib import Path
from typing import Any

from infini_local.core.runtime_authoring.normalize import normalize_runtime_plan_inplace
from infini_local.core.runtime_authoring.reports import runtime_plan_validation_report

REPORTS_PATH = (
    Path(__file__).resolve().parents[1]
    / "infini_local"
    / "core"
    / "runtime_authoring"
    / "reports.py"
)


def _call(fn: str, **params: object) -> dict[str, Any]:
    return {"fn": fn, "params": dict(params)}


def _weapon_root(**overrides: object) -> dict[str, Any]:
    params: dict[str, object] = {
        "runtimeFamily": "swing",
        "delivery": "swing",
        "movement": "straight",
        "speed": 8,
        "rangeTiles": 4,
        "lifetimeTicks": 20,
        "shotCount": 1,
        "spreadRadians": 0,
        "pierce": 0,
    }
    params.update(overrides)
    return _call("shoot_projectile", **params)


def _valid_weapon_plan() -> dict[str, Any]:
    return {
        "category": "weapon",
        "runtimePlan": {
            "engineCalls": [
                _call(
                    "set_item_stats",
                    resultKind="weapon",
                    damageClass="melee",
                    damage=12,
                    useTimeTicks=20,
                    maxStack=1,
                    craftYield=1,
                    consumable=False,
                ),
                _weapon_root(),
            ]
        },
    }


def test_spoofed_empty_normalization_marker_does_not_skip_strict_raw_boundary() -> None:
    spoofed = {
        "runtimePlan": {
            "_normalization": {},
            "engineCalls": [
                {
                    "fn": "fire_ranged_weapon",
                    "params": {"family": "charge_release", "chargeTicks": "много"},
                }
            ],
        }
    }
    report = runtime_plan_validation_report(deepcopy(spoofed))
    assert report["ok"] is False
    assert report.get("strictBoundary", {}).get("mode") != "canonical_already_normalized"
    assert any("chargeTicks" in str(err) for err in report["errors"])
    assert any("chargeTicks" in str(err) for err in (report.get("strictBoundary") or {}).get("errors") or [])


def test_genuine_already_normalized_second_pass_remains_green() -> None:
    data = _valid_weapon_plan()
    first = runtime_plan_validation_report(deepcopy(data))
    assert first["ok"] is True

    second_input = deepcopy(data)
    normalize_runtime_plan_inplace(second_input)
    assert isinstance(second_input["runtimePlan"].get("_normalization"), dict)
    assert all(
        isinstance(call.get("_index"), int) and str(call.get("_rawFn") or "").strip()
        for call in second_input["runtimePlan"]["engineCalls"]
    )
    second = runtime_plan_validation_report(second_input)
    assert second["ok"] is True
    assert second.get("strictBoundary", {}).get("mode") == "canonical_already_normalized"
    assert second["errors"] == []


def test_every_apply_on_hit_effect_is_validated_in_authored_order() -> None:
    data = {
        "category": "weapon",
        "runtimePlan": {
            "engineCalls": [
                _call(
                    "set_item_stats",
                    resultKind="weapon",
                    damageClass="melee",
                    damage=10,
                    useTimeTicks=20,
                    maxStack=1,
                    craftYield=1,
                    consumable=False,
                ),
                _weapon_root(),
                _call("apply_on_hit_effect", onHit="burn"),
                _call("apply_on_hit_effect", onHit="split"),
                _call("apply_on_hit_effect", onHit="frostburn", debuffTime=40),
            ]
        },
    }
    report = runtime_plan_validation_report(deepcopy(data))
    assert report["ok"] is False
    on_hit_errors = [err for err in report["errors"] if str(err).startswith("apply_on_hit_effect ")]
    assert on_hit_errors[0] == "apply_on_hit_effect onHit=burn requires explicit debuffTime"
    # First-call diagnostics stay first; extra call diagnostics append in authored order.
    assert "apply_on_hit_effect onHit=split requires explicit count > 0" in on_hit_errors
    assert "apply_on_hit_effect onHit=split requires explicit secondaryDamageMultiplier > 0" in on_hit_errors
    assert "apply_on_hit_effect onHit=split requires explicit secondaryLifetimeTicks" in on_hit_errors
    burn_idx = report["errors"].index("apply_on_hit_effect onHit=burn requires explicit debuffTime")
    split_count_idx = report["errors"].index(
        "apply_on_hit_effect onHit=split requires explicit count > 0"
    )
    assert burn_idx < split_count_idx
    # Valid third call must not invent missing-debuffTime noise.
    assert not any("onHit=frostburn" in str(err) and "debuffTime" in str(err) for err in on_hit_errors)


def test_consumable_weapon_low_stack_warning_names_consumable_weapon() -> None:
    data = {
        "category": "weapon",
        "runtimePlan": {
            "resultKind": "consumable_weapon",
            "engineCalls": [
                _call(
                    "set_item_stats",
                    resultKind="consumable_weapon",
                    damageClass="ranged",
                    damage=10,
                    useTimeTicks=20,
                    maxStack=7,
                    craftYield=3,
                    consumable=True,
                ),
                _call(
                    "shoot_projectile",
                    runtimeFamily="throw",
                    delivery="throw",
                    movement="gravity_arc",
                    speed=10,
                    rangeTiles=25,
                    lifetimeTicks=60,
                    shotCount=1,
                    spreadRadians=0,
                    pierce=1,
                ),
            ],
        },
    }
    report = runtime_plan_validation_report(deepcopy(data))
    assert report["ok"] is True
    assert report["warnings"]
    assert any("consumable_weapon" in str(w) for w in report["warnings"])
    assert not any(str(w).startswith("ammo output has low stack/yield") for w in report["warnings"])
    assert any("low stack/yield" in str(w) for w in report["warnings"])


def test_ammo_low_stack_warning_still_names_ammo_output() -> None:
    data = {
        "category": "ammo",
        "runtimePlan": {
            "resultKind": "ammo",
            "engineCalls": [
                _call(
                    "set_item_stats",
                    resultKind="ammo",
                    damageClass="ranged",
                    damage=4,
                    maxStack=10,
                    craftYield=10,
                    consumable=True,
                    ammoFor="arrow",
                ),
                _call("ammo_behavior", ammoFor="arrow"),
            ],
        },
    }
    report = runtime_plan_validation_report(deepcopy(data))
    assert report["ok"] is True
    assert any(
        str(w) == "ammo output has low stack/yield; playable ammo should usually output 25+"
        for w in report["warnings"]
    )


def test_validation_error_order_contract_across_rule_blocks() -> None:
    """E→F→G→H→I style: combat/root, structural, VFX, economy, on-hit keep relative order."""
    data = {
        "category": "weapon",
        "runtimePlan": {
            "engineCalls": [
                _call(
                    "set_item_stats",
                    resultKind="weapon",
                    damageClass="melee",
                    damage=0,
                    useTimeTicks=20,
                    maxStack=5,
                    craftYield=2,
                    consumable=True,
                    defense=3,
                ),
                _weapon_root(delivery="shoot", movement="straight"),
                _call("apply_on_hit_effect", onHit="burn"),
                _call(
                    "visual_effect_cue",
                    event="while_equipped",
                    rendererKind="bad",
                ),
            ]
        },
    }
    report = runtime_plan_validation_report(deepcopy(data))
    errors = [str(e) for e in report["errors"]]
    assert report["ok"] is False

    def _first_index(predicate) -> int:
        for idx, text in enumerate(errors):
            if predicate(text):
                return idx
        raise AssertionError(f"missing expected error class in {errors!r}")

    combat_idx = _first_index(
        lambda t: t.startswith("root executable action did not compile")
        or t.startswith("combat ")
    )
    defense_idx = _first_index(lambda t: "defense is armor-only" in t)
    delivery_idx = _first_index(
        lambda t: t.startswith("shoot_projectile runtimeFamily=") and "rejects delivery=" in t
    )
    vfx_idx = _first_index(lambda t: t.startswith("visual_effect_cue "))
    economy_idx = _first_index(lambda t: t.startswith("invalid_result_kind:"))
    on_hit_idx = _first_index(lambda t: t.startswith("apply_on_hit_effect "))

    assert combat_idx < defense_idx < delivery_idx < vfx_idx < economy_idx < on_hit_idx


def test_reports_module_keeps_private_ordered_rule_helpers() -> None:
    source = REPORTS_PATH.read_text(encoding="utf-8")
    module = ast.parse(source)
    fn_names = {
        node.name
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    required = {
        "_validate_combat_root_compile",
        "_validate_economy_and_ammo_identity",
        "_validate_effect_and_alt_calls",
    }
    assert required.issubset(fn_names), sorted(required - fn_names)

    entry = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "runtime_plan_validation_report"
    )
    end_lineno = entry.end_lineno if entry.end_lineno is not None else entry.lineno
    entry_loc = end_lineno - entry.lineno + 1
    assert 120 <= entry_loc <= 220, f"entry LOC out of band: {entry_loc}"
