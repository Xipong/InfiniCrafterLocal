from __future__ import annotations

from copy import deepcopy
import inspect

import pytest

from infini_local.core.boundary_models import runtime_plan_boundary_report
from infini_local.core.runtime_authoring import (
    compile_runtime_plan_to_genome_patch,
    runtime_plan_validation_report,
)
from infini_local.core.runtime_authoring.final_projection import (
    apply_runtime_final_sections,
    compile_runtime_plan_to_final_result,
)
from infini_local.core.runtime_contracts import structural_final_wire_report
from infini_local.pipelines.combine_gameplay import attach_gameplay_and_attack
from infini_local.pipelines.item_power_knowledge import canonicalize
from infini_local.pipelines.llm_authoring_prompt import normalize_runtime_authoring_fields
from infini_local.core.runtime_authoring.result_identity import project_runtime_result_identity


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
    stats = next(
        (call.get("params") for call in calls if call.get("fn") == "set_item_stats"),
        {},
    )
    stats = stats if isinstance(stats, dict) else {}
    has_root_executor = any(call.get("fn") != "set_item_stats" for call in calls)
    category = project_runtime_result_identity(
        result_kind,
        ammo_for=stats.get("ammoFor"),
        has_root_executor=has_root_executor,
    ).gameplay_kind
    return {
        "name": "Compiler Projection Probe",
        "category": category,
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


class _ProjectionWriteGuard(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._frozen: set[str] = set()

    def freeze(self, fields) -> None:
        self._frozen.update(str(field) for field in fields)

    def __setitem__(self, key, value):
        if key in self._frozen:
            raise AssertionError(f"post-projection write to compiler-owned field: {key}")
        super().__setitem__(key, value)

    def update(self, *args, **kwargs):
        values = dict(*args, **kwargs)
        blocked = self._frozen.intersection(values)
        if blocked:
            raise AssertionError(f"post-projection bulk write to compiler-owned fields: {sorted(blocked)}")
        super().update(values)

    def pop(self, key, *args):
        if key in self._frozen:
            raise AssertionError(f"post-projection delete of compiler-owned field: {key}")
        return super().pop(key, *args)


def test_composer_never_rewrites_runtime_final_projection_fields(monkeypatch) -> None:
    import infini_local.pipelines.combine_gameplay as combine_gameplay

    real_apply = combine_gameplay.apply_runtime_final_sections

    def apply_and_freeze(data, result):
        real_apply(data, result)
        for section, values in result["finalSections"].items():
            target = data[section]
            assert isinstance(target, _ProjectionWriteGuard)
            target.freeze(values)
        return data

    monkeypatch.setattr(combine_gameplay, "apply_runtime_final_sections", apply_and_freeze)
    cases = [
        _authored_item("weapon", [
            {"callId": "stats", "fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "ranged", "damage": 12, "useTimeTicks": 20, "useAnimationTicks": 20, "maxStack": 1, "craftYield": 1, "consumable": False}},
            {"callId": "root", "fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "speed": 8, "rangeTiles": 30, "lifetimeTicks": 90, "shotCount": 1, "spreadRadians": 0, "pierce": 1}},
        ]),
        _authored_item("armor", [
            {"callId": "stats", "fn": "set_item_stats", "params": {"resultKind": "armor", "armorSlot": "head", "defense": 9, "maxStack": 1, "craftYield": 1, "consumable": False, "autoReuse": False}},
            {"callId": "armor", "fn": "armor_effect", "params": {"armorSlot": "head", "defense": 9, "stats": {"lifeRegen": 1}}},
        ]),
        _authored_item("accessory", [
            {"callId": "stats", "fn": "set_item_stats", "params": {"resultKind": "accessory", "maxStack": 1, "craftYield": 1, "consumable": False, "autoReuse": False}},
            {"callId": "acc", "fn": "accessory_effect", "params": {"defense": 0, "stats": {"movementSpeed": 0.1}}},
        ]),
    ]
    for item in cases:
        for section in ("gameplay", "attack", "accessory", "armor"):
            item[section] = _ProjectionWriteGuard()
        _compile_final(item)


def _receipt(report: dict, call_id: str, authored_param: str, final_path: str) -> dict:
    return next(
        row
        for row in report["finalWireReceipts"]
        if row["callId"] == call_id
        and row["authoredParam"] == authored_param
        and row["finalPath"] == final_path
    )


def test_runtime_authoring_owner_emits_final_shaped_compile_result() -> None:
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
                "params": {"onHit": "poison", "aoeRadiusTiles": 1},
            },
        ],
    )
    compiled_input = deepcopy(authored)
    result = compile_runtime_plan_to_final_result(compiled_input)
    assert compile_runtime_plan_to_final_result(compiled_input) == result
    assert compiled_input["_runtimePlanCompileCache"] == {
        "signature": result["signature"],
        "result": result,
    }
    assert result["schema"] == "infini.runtime-final-compile-result.v2"
    assert isinstance(result["signature"], str) and result["signature"]
    assert result["finalSections"]["gameplay"] == {
        "kind": "weapon",
        "runtimeOutputKind": "consumable_weapon",
        "damageClass": "ranged",
        "damage": 18,
        "useTime": 24,
        "useAnimation": 24,
        "maxStack": 30,
        "craftYield": 10,
        "consumable": True,
    }
    assert result["finalSections"]["attack"]["runtimeFamily"] == "throw"
    assert result["finalSections"]["attack"]["lifetime"] == 90
    assert result["finalSections"]["attack"]["pierce"] == 1
    assert result["finalSections"]["attack"]["aoeDamageRadiusPx"] == 16
    receipt_paths = {
        (row["callId"], row["authoredParam"], row["finalPath"])
        for row in result["finalWireReceipts"]
    }
    assert ("stats", "damage", "gameplay.damage") in receipt_paths
    assert ("primary", "lifetimeTicks", "attack.lifetime") in receipt_paths
    assert ("impact", "aoeRadiusTiles", "attack.aoeDamageRadiusPx") in receipt_paths

    target = {"gameplay": {"stage": "code-owned"}, "attack": {"enabled": True}}
    applied = apply_runtime_final_sections(target, result)
    assert applied is target
    assert target["gameplay"]["stage"] == "code-owned"
    assert target["gameplay"]["damage"] == 18
    assert target["attack"]["enabled"] is True
    assert target["attack"]["runtimeFamily"] == "throw"
    assert target["runtimeContract"]["finalWireReceipts"] == result["finalWireReceipts"]


def test_runtime_authoring_final_projection_has_one_cache_and_apply_owner() -> None:
    from infini_local.core.runtime_authoring import final_projection
    from infini_local.pipelines import combine_gameplay, llm_authoring_prompt

    owner_source = inspect.getsource(final_projection)
    prompt_source = inspect.getsource(llm_authoring_prompt)
    combine_source = inspect.getsource(combine_gameplay)

    assert "_runtimePlanCompileCache" in owner_source
    assert "_runtimePlanCompileCache" not in prompt_source
    assert "runtimePlanGenomePatch" not in prompt_source
    assert "_flatten_final_wire" not in combine_source
    assert "_attach_compiler_final_wire_receipts" not in combine_source
    assert "_project_explicit_runtime_item_fields" not in combine_source
    assert combine_source.count("apply_runtime_final_sections(") == 1
    assert "project_runtime_result_identity" not in combine_source


def test_compile_result_owns_runtime_identity_projection() -> None:
    authored = _authored_item(
        "consumable_weapon",
        [
            {
                "callId": "stats",
                "fn": "set_item_stats",
                "params": {
                    "resultKind": "consumable_weapon",
                    "damageClass": "ranged",
                    "damage": 12,
                    "useTimeTicks": 24,
                    "maxStack": 30,
                    "craftYield": 4,
                    "consumable": True,
                },
            },
            {
                "callId": "root",
                "fn": "shoot_projectile",
                "params": {
                    "runtimeFamily": "throw",
                    "delivery": "throw",
                    "movement": "gravity_arc",
                    "speed": 8,
                    "lifetimeTicks": 60,
                    "shotCount": 1,
                    "spreadRadians": 0,
                    "pierce": 1,
                },
            },
        ],
    )
    result = compile_runtime_plan_to_final_result(authored)
    assert result["identity"] == {
        "authoredKind": "consumable_weapon",
        "gameplayKind": "weapon",
        "runtimeOutputKind": "consumable_weapon",
        "authoredAmmoFor": "",
        "finalAmmoFor": "",
        "unsupportedAmmoFor": "",
    }
    assert result["finalSections"]["gameplay"]["runtimeOutputKind"] == "consumable_weapon"


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
    report = structural_final_wire_report(final_item)

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
    apply_runtime_final_sections(
        tampered_snapshot,
        compile_runtime_plan_to_final_result(deepcopy(authored)),
    )
    tampered_snapshot_report = structural_final_wire_report(tampered_snapshot)
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
    corrupted_report = structural_final_wire_report(corrupted)
    assert corrupted_report["ok"] is False
    assert any(
        row["kind"] == "compiler_provenance_mismatched"
        and row["callId"] == "impact"
        and row["authoredParam"] == "aoeRadiusTiles"
        and row["compiledValue"] == 16
        and row["finalActual"] == 1
        for row in corrupted_report["blockingClaims"]
    )


def test_empty_optional_string_does_not_create_dropped_final_wire_receipt() -> None:
    authored = _authored_item(
        "weapon",
        [
            {
                "callId": "stats",
                "fn": "set_item_stats",
                "params": {
                    "resultKind": "weapon",
                    "damageClass": "magic",
                    "damage": 22,
                    "useTimeTicks": 25,
                    "useAnimationTicks": 25,
                    "maxStack": 1,
                    "craftYield": 1,
                    "consumable": False,
                },
            },
            {
                "callId": "root",
                "fn": "shoot_projectile",
                "params": {
                    "runtimeFamily": "shoot",
                    "delivery": "shoot",
                    "movement": "straight",
                    "speed": 10,
                    "rangeTiles": 60,
                    "lifetimeTicks": 300,
                    "shotCount": 1,
                    "spreadRadians": 0,
                    "pierce": 3,
                },
            },
            {
                "callId": "impact",
                "fn": "apply_on_hit_effect",
                "params": {
                    "onHit": "burst",
                    "aoeRadiusTiles": 3,
                    "debuffHint": "",
                    "debuffTime": 30,
                },
            },
        ],
    )

    result = compile_runtime_plan_to_final_result(authored)
    assert not any(
        row["callId"] == "impact" and row["authoredParam"] == "debuffHint"
        for row in result["finalWireReceipts"]
    )
    assert not any(row["status"] == "dropped" for row in result["finalWireReceipts"])


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
    final_report = structural_final_wire_report(final_item)
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
    corrupted_report = structural_final_wire_report(corrupted)
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
    report = structural_final_wire_report(final_item)

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
    report = structural_final_wire_report(final_item)

    assert report["ok"] is True, report["blockingClaims"]
    assert final_item["gameplay"]["ammoFor"] == authored_ammo
    receipt = _receipt(report, "stats", "ammoFor", "gameplay.ammoFor")
    assert receipt["authoredValue"] == authored_ammo
    assert receipt["compiledValue"] == authored_ammo
    assert receipt["finalActual"] == authored_ammo


def test_combat_pickaxe_keeps_native_tool_powers_and_authored_swing_effects() -> None:
    authored = _authored_item(
        "tool",
        [
            {
                "callId": "stats",
                "fn": "set_item_stats",
                "params": {
                    "resultKind": "tool",
                    "damageClass": "melee",
                    "damage": 38,
                    "useTimeTicks": 18,
                    "useAnimationTicks": 22,
                    "maxStack": 1,
                    "craftYield": 1,
                    "consumable": False,
                },
            },
            {
                "callId": "tool",
                "fn": "tool_capability",
                "params": {"pickPower": 120, "miningSpeedScale": 1.1},
            },
            {
                "callId": "body",
                "fn": "perform_melee_attack",
                "params": {
                    "family": "pickaxe",
                    "speed": 6,
                    "rangeTiles": 4,
                    "lifetimeTicks": 20,
                    "shotCount": 1,
                    "spreadRadians": 0,
                    "pierce": 1,
                },
            },
            {
                "callId": "impact",
                "fn": "apply_on_hit_effect",
                "params": {"onHit": "burn", "debuffTime": 120},
            },
        ],
    )

    boundary = runtime_plan_boundary_report(deepcopy(authored))
    assert boundary["ok"] is True, boundary["errors"]
    final_item = _compile_final(deepcopy(authored))
    report = structural_final_wire_report(final_item)

    assert report["ok"] is True, report["blockingClaims"]
    assert final_item["category"] == "tool"
    assert final_item["gameplay"]["kind"] == "tool"
    assert final_item["gameplay"]["pickPower"] == 120
    assert final_item["gameplay"]["axePower"] == 0
    assert final_item["gameplay"]["hammerPower"] == 0
    assert final_item["gameplay"]["miningSpeedScale"] == 1.1
    assert final_item["attack"]["enabled"] is True
    assert final_item["attack"]["runtimeFamily"] == "swing"
    assert final_item["attack"]["disableItemMeleeHitbox"] is False
    assert final_item["attack"]["onHit"] == "burn"


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

    first_report = structural_final_wire_report(final_item)
    second_report = structural_final_wire_report(final_item)

    assert first_report["ok"] is True, first_report["blockingClaims"]
    assert second_report["ok"] is True, second_report["blockingClaims"]
    assert len(first_report["finalWireReceipts"]) > 96
    assert second_report["finalWireReceipts"] == first_report["finalWireReceipts"]
