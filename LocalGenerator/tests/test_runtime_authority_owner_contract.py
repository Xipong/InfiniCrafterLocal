"""Canonical runtime result/economy/defense authority owner contracts."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from infini_local.core.runtime_authoring.reports import runtime_plan_validation_report
from infini_local.core.runtime_authoring.result_identity import effective_runtime_result_kind
from infini_local.pipelines.combine_validation import (
    _consumable_parent_economy_report,
    _parent_role_preservation_report,
    _placeable_parent_role_report,
)


def _call(call_id: str, fn: str, **params: object) -> dict[str, Any]:
    return {"callId": call_id, "fn": fn, "params": params}


def _plan(
    plan_kind: str | None,
    *calls: dict[str, Any],
    category: str | None = None,
) -> dict[str, Any]:
    runtime_plan: dict[str, Any] = {
        "engineCalls": list(calls),
        "sourceRolePreservation": {"itemA": "body", "itemB": "effect"},
        "runtimeStateIntent": "",
        "visualIntent": {"item": "", "projectile": "", "impact": "", "vfxIntent": "", "vfxAvoid": ""},
        "sourceReading": "",
        "balanceIntent": "",
        "anomalyFlags": [],
    }
    if plan_kind is not None:
        runtime_plan["resultKind"] = plan_kind
    resolved_category = category if category is not None else (plan_kind or "")
    data: dict[str, Any] = {"runtimePlan": runtime_plan}
    if resolved_category:
        data["category"] = resolved_category
    return data


def _weapon_root(**overrides: object) -> dict[str, Any]:
    params: dict[str, object] = {
        "runtimeFamily": "throw",
        "delivery": "throw",
        "movement": "gravity_arc",
        "speed": 10,
        "rangeTiles": 25,
        "lifetimeTicks": 60,
        "shotCount": 1,
        "spreadRadians": 0,
        "pierce": 1,
    }
    params.update(overrides)
    return _call("root", "shoot_projectile", **params)


def test_effective_runtime_result_kind_prefers_set_item_stats_over_plan() -> None:
    only_stats = _plan(
        None,
        _call("stats", "set_item_stats", resultKind="armor", armorSlot="head", defense=4, maxStack=1),
    )
    assert effective_runtime_result_kind(only_stats) == "armor"

    only_plan = _plan("tool")
    assert effective_runtime_result_kind(only_plan) == "tool"

    both = _plan(
        "weapon",
        _call("stats", "set_item_stats", resultKind="accessory", maxStack=1, craftYield=1, consumable=False),
    )
    assert effective_runtime_result_kind(both) == "accessory"

    empty = _plan(None)
    assert effective_runtime_result_kind(empty) == ""


def test_duplicate_set_item_stats_is_rejected_and_diagnostic_projection_is_deterministic() -> None:
    duplicate = _plan(
        "weapon",
        _call("stats-a", "set_item_stats", resultKind="weapon", damage=10),
        _call("stats-b", "set_item_stats", resultKind="accessory", damage=0),
    )
    # Diagnostic/compiler preview follows the existing later-non-empty merge order,
    # but the authored contract must reject the duplicate owner.
    assert effective_runtime_result_kind(duplicate) == "accessory"
    report = runtime_plan_validation_report(deepcopy(duplicate))
    assert report["ok"] is False
    assert any("multiple set_item_stats" in error for error in report["errors"])
    assert any(
        detail.get("path") == "$.runtimePlan.engineCalls[1]"
        and detail.get("callId") == "stats-b"
        for detail in report["errorDetails"]
    )


def test_reusable_parent_economy_treats_missing_consumable_as_durable_gear() -> None:
    """Strong-role parent without explicit consumable=true is reusable gear."""
    spear_missing = {
        "name": "Spear",
        "damage": 8,
        # consumable intentionally absent — durable weapon default
        "accessory": False,
        "headSlot": -1,
        "bodySlot": -1,
        "legSlot": -1,
    }
    rope = {
        "name": "Rope",
        "damage": -1,
        "consumable": True,
        "accessory": False,
        "headSlot": -1,
        "bodySlot": -1,
        "legSlot": -1,
    }
    current = _plan(
        "consumable_weapon",
        _call(
            "stats",
            "set_item_stats",
            resultKind="consumable_weapon",
            damageClass="ranged",
            damage=14,
            useTimeTicks=25,
            maxStack=99,
            craftYield=1,
            consumable=True,
        ),
        _weapon_root(pierce=2),
    )
    blocked = _consumable_parent_economy_report(current, spear_missing, rope)
    assert blocked["ok"] is False
    assert blocked["reusableGearParents"] == ["Spear"]

    spear_false = {**spear_missing, "consumable": False}
    still_blocked = _consumable_parent_economy_report(current, spear_false, rope)
    assert still_blocked["ok"] is False
    assert still_blocked["reusableGearParents"] == ["Spear"]

    grenade = {**spear_missing, "name": "Grenade", "consumable": True}
    gel = {**rope, "name": "Gel"}
    allowed = _consumable_parent_economy_report(current, grenade, gel)
    assert allowed["ok"] is True
    assert allowed["applicable"] is False


def test_parent_economy_and_role_gates_read_canonical_effective_result_kind() -> None:
    """Gates must not miss set_item_stats.resultKind when plan-level kind is absent/stale."""
    armor_parent = {
        "name": "Mining Helmet",
        "damage": -1,
        "accessory": False,
        "headSlot": 11,
        "bodySlot": -1,
        "legSlot": -1,
    }
    torch = {
        "name": "Torch",
        "damage": -1,
        "accessory": False,
        "headSlot": -1,
        "bodySlot": -1,
        "legSlot": -1,
    }
    # Plan-level resultKind missing; authority lives on set_item_stats only.
    weaponish_stats_only = _plan(
        None,
        _call(
            "stats",
            "set_item_stats",
            resultKind="weapon",
            damageClass="melee",
            damage=12,
            useTimeTicks=24,
            maxStack=1,
            craftYield=1,
            consumable=False,
        ),
        _weapon_root(runtimeFamily="swing", delivery="swing", movement="straight"),
        category="weapon",
    )
    role = _parent_role_preservation_report(weaponish_stats_only, armor_parent, torch)
    assert role["applicable"] is True
    assert role["expectedResultKind"] == "armor"
    assert role["actualResultKind"] == "weapon"
    assert role["ok"] is False

    armor_stats_only = _plan(
        None,
        _call(
            "stats",
            "set_item_stats",
            resultKind="armor",
            armorSlot="head",
            defense=6,
            maxStack=1,
            craftYield=1,
            consumable=False,
            autoReuse=False,
        ),
        _call("armor", "armor_effect", armorSlot="head", defense=6, stats={"lifeRegen": 1}),
        category="armor",
    )
    assert _parent_role_preservation_report(armor_stats_only, armor_parent, torch)["ok"] is True

    spear = {
        "name": "Spear",
        "damage": 8,
        "consumable": False,
        "accessory": False,
        "headSlot": -1,
        "bodySlot": -1,
        "legSlot": -1,
    }
    rope = {
        "name": "Rope",
        "damage": -1,
        "consumable": True,
        "accessory": False,
        "headSlot": -1,
        "bodySlot": -1,
        "legSlot": -1,
    }
    economy_stats_only = _plan(
        None,
        _call(
            "stats",
            "set_item_stats",
            resultKind="consumable_weapon",
            damageClass="ranged",
            damage=14,
            useTimeTicks=25,
            maxStack=99,
            craftYield=1,
            consumable=True,
        ),
        _weapon_root(pierce=2),
        category="weapon",
    )
    economy = _consumable_parent_economy_report(economy_stats_only, spear, rope)
    assert economy["ok"] is False
    assert economy["actualResultKind"] == "consumable_weapon"
    assert economy["reusableGearParents"] == ["Spear"]

    extractinator = {
        "name": "Extractinator",
        "damage": -1,
        "consumable": True,
        "accessory": False,
        "headSlot": -1,
        "bodySlot": -1,
        "legSlot": -1,
        "createTile": 219,
        "createWall": -1,
        "placeStyle": 0,
    }
    silt = {
        "name": "Silt Block",
        "damage": -1,
        "consumable": True,
        "accessory": False,
        "headSlot": -1,
        "bodySlot": -1,
        "legSlot": -1,
        "createTile": 123,
        "createWall": -1,
        "placeStyle": 0,
    }
    furniture_stats_only = _plan(
        None,
        _call(
            "stats",
            "set_item_stats",
            resultKind="furniture",
            damageClass="generic",
            damage=0,
            useTimeTicks=15,
            useAnimationTicks=15,
            maxStack=99,
            craftYield=1,
            consumable=True,
        ),
        _call("place", "placeable_behavior", createTile=219, createWall=-1, placeStyle=0),
        category="furniture",
    )
    placeable = _placeable_parent_role_report(furniture_stats_only, extractinator, silt)
    assert placeable["ok"] is True
    assert placeable["actualResultKind"] == "furniture"


def test_set_item_stats_defense_is_armor_only_structurally() -> None:
    weapon = _plan(
        "weapon",
        _call(
            "stats",
            "set_item_stats",
            resultKind="weapon",
            damageClass="melee",
            damage=18,
            useTimeTicks=28,
            useAnimationTicks=28,
            maxStack=1,
            craftYield=1,
            consumable=False,
            defense=5,
        ),
        _weapon_root(runtimeFamily="swing", delivery="swing", movement="straight"),
    )
    weapon_report = runtime_plan_validation_report(deepcopy(weapon))
    assert weapon_report["ok"] is False
    assert any("defense" in err and "armor" in err.lower() for err in weapon_report["errors"])
    assert any(
        "defense" in (detail.get("repairParamNames") or [])
        for detail in weapon_report.get("errorDetails") or []
    )

    accessory = _plan(
        "accessory",
        _call(
            "stats",
            "set_item_stats",
            resultKind="accessory",
            maxStack=1,
            craftYield=1,
            consumable=False,
            autoReuse=False,
            defense=3,
        ),
        _call("acc", "accessory_effect", defense=0, stats={"movementSpeed": 0.1}),
    )
    accessory_report = runtime_plan_validation_report(deepcopy(accessory))
    assert accessory_report["ok"] is False
    assert any(
        "accessory_effect.defense" in err and "set_item_stats.defense" in err
        for err in accessory_report["errors"]
    )

    # Neutral zero remains a dormant required-field sentinel on non-armor kinds.
    weapon_zero = deepcopy(weapon)
    weapon_zero["runtimePlan"]["engineCalls"][0]["params"]["defense"] = 0
    zero_report = runtime_plan_validation_report(weapon_zero)
    assert not any("defense" in err and "armor-only" in err for err in zero_report["errors"])

    armor = _plan(
        "armor",
        _call(
            "stats",
            "set_item_stats",
            resultKind="armor",
            armorSlot="head",
            defense=9,
            maxStack=1,
            craftYield=1,
            consumable=False,
            autoReuse=False,
        ),
        _call("armor", "armor_effect", armorSlot="head", defense=9, stats={"lifeRegen": 1}),
    )
    armor_report = runtime_plan_validation_report(deepcopy(armor))
    assert armor_report["ok"] is True, armor_report
    assert not any("armor-only" in err for err in armor_report["errors"])
