from __future__ import annotations

from copy import deepcopy

import pytest

from infini_local.core.boundary_models import runtime_plan_boundary_report
from infini_local.core.runtime_authoring import (
    compile_runtime_plan_to_genome_patch,
    runtime_plan_validation_report,
)
from infini_local.core.runtime_contracts import validate_structural_final_wire_contract
from infini_local.pipelines.combine_gameplay import (
    _attach_compiler_final_wire_receipts,
    attach_gameplay_and_attack,
)
from infini_local.pipelines.item_power_knowledge import canonicalize
from infini_local.pipelines.llm_authoring_prompt import normalize_runtime_authoring_fields


def _parent(name: str) -> dict:
    return {
        "name": name,
        "internalName": name.replace(" ", ""),
        "sourceMod": "Terraria",
        "damage": 0,
        "damageClass": "generic",
        "useTime": 24,
        "useAnimation": 24,
        "knockback": 0,
        "rare": 0,
        "value": 0,
        "maxStack": 1,
        "consumable": False,
        "material": False,
        "tags": [],
    }


def _authored_item(result_kind: str, calls: list[dict]) -> dict:
    return {
        "name": "Compiler Projection Probe",
        "category": "weapon",
        "concept": {
            "fantasy": "A finite probe for the authored compiler contract.",
            "mergeLogic": "Both parent facts remain presentation context only.",
            "coreMechanic": "Uses the exact authored finite projectile behavior.",
        },
        "runtimeContract": {
            "primaryVerb": "fire",
            "controlStyle": "tap",
            "playerViewTimeline": [],
        },
        "runtimePlan": {
            "resultKind": result_kind,
            "engineCalls": calls,
        },
    }


def _compile_final(item: dict) -> dict:
    parent_a = _parent("Parent A")
    parent_b = _parent("Parent B")
    normalize_runtime_authoring_fields(item)
    return attach_gameplay_and_attack(
        item,
        parent_a,
        parent_b,
        canonicalize(parent_a),
        canonicalize(parent_b),
    )


def _receipt(report: dict, call_id: str, authored_param: str, final_path: str) -> dict:
    return next(
        row
        for row in report["finalWireReceipts"]
        if row["callId"] == call_id
        and row["authoredParam"] == authored_param
        and row["finalPath"] == final_path
    )


def test_compiler_owned_projections_reach_final_wire_and_detect_corruption() -> None:
    authored = _authored_item(
        "consumable_weapon",
        [
            {
                "callId": "stats",
                "fn": "set_item_stats",
                "params": {
                    "resultKind": "consumable_weapon",
                    "damageClass": "ranged",
                    "damage": 18,
                    "useTimeTicks": 24,
                    "useAnimationTicks": 24,
                    "maxStack": 30,
                    "craftYield": 10,
                    "consumable": True,
                },
            },
            {
                "callId": "primary",
                "fn": "shoot_projectile",
                "params": {
                    "runtimeFamily": "throw",
                    "delivery": "throw",
                    "movement": "gravity_arc",
                    "speed": 8,
                    "rangeTiles": 30,
                    "lifetimeTicks": 90,
                    "shotCount": 1,
                    "spreadRadians": 0,
                    "pierce": 1,
                },
            },
            {
                "callId": "impact",
                "fn": "apply_on_hit_effect",
                "params": {
                    "onHit": "poison",
                    "aoeRadiusTiles": 1,
                    "debuffHint": "Workbench Spawned",
                    "debuffTime": 180,
                },
            },
        ],
    )

    final_item = _compile_final(deepcopy(authored))
    report = validate_structural_final_wire_contract(final_item)

    assert report["ok"] is True, report["blockingClaims"]
    assert final_item["gameplay"]["kind"] == "weapon"
    assert final_item["gameplay"]["runtimeOutputKind"] == "consumable_weapon"
    assert final_item["attack"]["aoeDamageRadiusPx"] == 16
    assert final_item["attack"]["debuffHint"] == "Workbench Spawned"

    kind_receipt = _receipt(report, "stats", "resultKind", "gameplay.kind")
    assert kind_receipt["compiledValue"] == "weapon"
    assert kind_receipt["finalActual"] == "weapon"
    assert kind_receipt["status"] == "normalized"

    radius_receipt = _receipt(
        report,
        "impact",
        "aoeRadiusTiles",
        "attack.aoeDamageRadiusPx",
    )
    assert radius_receipt["compiledValue"] == 16
    assert radius_receipt["finalActual"] == 16

    hint_receipt = _receipt(report, "impact", "debuffHint", "attack.debuffHint")
    assert hint_receipt["compiledValue"] == "Workbench Spawned"
    assert hint_receipt["finalActual"] == "Workbench Spawned"

    # Debug genome is a derived view, never the receipt's compiler evidence.
    tampered_snapshot = deepcopy(final_item)
    tampered_snapshot["attack"]["genome"]["aoeDamageRadiusPx"] = 1
    _attach_compiler_final_wire_receipts(
        tampered_snapshot,
        deepcopy(authored),
        {},
        {},
        {},
        {},
    )
    tampered_snapshot_report = validate_structural_final_wire_contract(tampered_snapshot)
    assert tampered_snapshot_report["ok"] is True, tampered_snapshot_report["blockingClaims"]
    snapshot_radius_receipt = _receipt(
        tampered_snapshot_report,
        "impact",
        "aoeRadiusTiles",
        "attack.aoeDamageRadiusPx",
    )
    assert snapshot_radius_receipt["compiledValue"] == 16

    corrupted = deepcopy(final_item)
    corrupted["attack"]["aoeDamageRadiusPx"] = 1
    corrupted_report = validate_structural_final_wire_contract(corrupted)
    assert corrupted_report["ok"] is False
    assert any(
        row["kind"] == "compiler_provenance_mismatched"
        and row["callId"] == "impact"
        and row["authoredParam"] == "aoeRadiusTiles"
        and row["compiledValue"] == 16
        and row["finalActual"] == 1
        for row in corrupted_report["blockingClaims"]
    )


def test_temporary_helper_spread_has_one_validated_compiler_to_dto_path() -> None:
    authored = _authored_item(
        "weapon",
        [
            {
                "callId": "stats",
                "fn": "set_item_stats",
                "params": {
                    "resultKind": "weapon",
                    "damageClass": "summon",
                    "damage": 14,
                    "useTimeTicks": 30,
                },
            },
            {
                "callId": "helper",
                "fn": "spawn_temporary_helper_projectile",
                "params": {
                    "family": "drone",
                    "movement": "drift",
                    "speed": 7,
                    "rangeTiles": 24,
                    "lifetimeTicks": 180,
                    "shotCount": 3,
                    "spreadRadians": 0.2,
                    "pierce": 1,
                    "projectileShape": "one compact helper drone",
                },
            },
        ],
    )

    source_boundary = runtime_plan_boundary_report(deepcopy(authored))
    assert source_boundary["ok"] is True, source_boundary["errors"]
    validation = runtime_plan_validation_report(deepcopy(authored))
    assert validation["ok"] is True, validation["errors"]

    patch = compile_runtime_plan_to_genome_patch(deepcopy(authored))
    assert patch["spreadRadians"] == 0.2

    final_item = _compile_final(deepcopy(authored))
    assert final_item["attack"]["spreadRadians"] == 0.2
    final_report = validate_structural_final_wire_contract(final_item)
    assert final_report["ok"] is True, final_report["blockingClaims"]
    spread_receipt = _receipt(
        final_report,
        "helper",
        "spreadRadians",
        "attack.spreadRadians",
    )
    assert spread_receipt["compiledValue"] == 0.2
    assert spread_receipt["finalActual"] == 0.2
    assert spread_receipt["authoredValue"] == 0.2
    assert spread_receipt["compiledField"] == "spreadRadians"
    assert spread_receipt["status"] == "active"

    corrupted = deepcopy(final_item)
    corrupted["attack"]["spreadRadians"] = 0.05
    corrupted_report = validate_structural_final_wire_contract(corrupted)
    assert corrupted_report["ok"] is False
    assert any(
        row["kind"] == "compiler_provenance_mismatched"
        and row["callId"] == "helper"
        and row["authoredParam"] == "spreadRadians"
        and row["compiledValue"] == 0.2
        and row["finalActual"] == 0.05
        for row in corrupted_report["blockingClaims"]
    )


@pytest.mark.parametrize(
    ("authored_pierce", "wire_pierce"),
    [(0, 1), (1, 1), (-1, -1)],
)
def test_authored_pierce_sentinels_have_explicit_wire_projection(
    authored_pierce: int,
    wire_pierce: int,
) -> None:
    authored = _authored_item(
        "weapon",
        [
            {
                "callId": "stats",
                "fn": "set_item_stats",
                "params": {
                    "resultKind": "weapon",
                    "damageClass": "ranged",
                    "damage": 12,
                    "useTimeTicks": 24,
                },
            },
            {
                "callId": "primary",
                "fn": "shoot_projectile",
                "params": {
                    "runtimeFamily": "shoot",
                    "delivery": "shoot",
                    "movement": "straight",
                    "speed": 8,
                    "rangeTiles": 30,
                    "lifetimeTicks": 90,
                    "shotCount": 1,
                    "spreadRadians": 0,
                    "pierce": authored_pierce,
                },
            },
        ],
    )

    final_item = _compile_final(deepcopy(authored))
    report = validate_structural_final_wire_contract(final_item)

    assert report["ok"] is True, report["blockingClaims"]
    assert final_item["attack"]["pierce"] == wire_pierce
    receipt = _receipt(report, "primary", "pierce", "attack.pierce")
    assert receipt["authoredValue"] == authored_pierce
    assert receipt["compiledValue"] == wire_pierce
    assert receipt["finalActual"] == wire_pierce


@pytest.mark.parametrize(
    "authored_ammo",
    ["arrow", "bullet"],
)
def test_actual_ammo_canonical_values_have_explicit_wire_projection(
    authored_ammo: str,
) -> None:
    authored = _authored_item(
        "ammo",
        [
            {
                "callId": "stats",
                "fn": "set_item_stats",
                "params": {
                    "resultKind": "ammo",
                    "damageClass": "ranged",
                    "damage": 2,
                    "useTimeTicks": 10,
                    "maxStack": 999,
                    "craftYield": 50,
                    "consumable": True,
                    "ammoFor": authored_ammo,
                },
            },
        ],
    )

    final_item = _compile_final(deepcopy(authored))
    report = validate_structural_final_wire_contract(final_item)

    assert report["ok"] is True, report["blockingClaims"]
    assert final_item["gameplay"]["ammoFor"] == authored_ammo
    receipt = _receipt(report, "stats", "ammoFor", "gameplay.ammoFor")
    assert receipt["authoredValue"] == authored_ammo
    assert receipt["compiledValue"] == authored_ammo
    assert receipt["finalActual"] == authored_ammo


def test_large_compiler_receipt_set_is_idempotent() -> None:
    calls = [
        {
            "callId": "stats",
            "fn": "set_item_stats",
            "params": {
                "resultKind": "weapon",
                "damageClass": "ranged",
                "damage": 12,
                "useTimeTicks": 24,
            },
        },
        {
            "callId": "primary",
            "fn": "shoot_projectile",
            "params": {
                "runtimeFamily": "shoot",
                "delivery": "shoot",
                "movement": "straight",
                "speed": 8,
                "rangeTiles": 30,
                "lifetimeTicks": 90,
                "shotCount": 1,
                "spreadRadians": 0,
                "pierce": 1,
            },
        },
    ]
    calls.extend(
        {
            "callId": f"particle_{index}",
            "fn": "spawn_contact_particles",
            "params": {
                "effect": "dust",
                "amount": 4,
                "scale": 1.0,
                "durationTicks": 10,
                "material": "wood",
            },
        }
        for index in range(20)
    )
    final_item = _compile_final(_authored_item("weapon", calls))

    first_report = validate_structural_final_wire_contract(final_item)
    second_report = validate_structural_final_wire_contract(final_item)

    assert first_report["ok"] is True, first_report["blockingClaims"]
    assert second_report["ok"] is True, second_report["blockingClaims"]
    assert len(first_report["finalWireReceipts"]) > 96
    assert second_report["finalWireReceipts"] == first_report["finalWireReceipts"]
