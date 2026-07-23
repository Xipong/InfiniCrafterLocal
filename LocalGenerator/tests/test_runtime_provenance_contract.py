from __future__ import annotations

from copy import deepcopy

from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_result
from infini_local.core.runtime_authoring.final_projection import (
    attach_runtime_final_evidence,
    compile_runtime_plan_to_final_result,
)
from infini_local.core.runtime_authoring.reports import compiled_fields_for_authored_param
from infini_local.core.boundary_models import validate_executable_item_boundary
from infini_local.core.runtime_contracts import (
    apply_structural_final_wire_contract,
    structural_final_wire_report,
)


def _attach_evidence(output: dict, authored: dict) -> None:
    attach_runtime_final_evidence(
        output,
        compile_runtime_plan_to_final_result(deepcopy(authored)),
    )


def _contract_check_authored_runtime_fields_have_precise_provenance() -> None:
    data = {
        "category": "weapon",
        "runtimePlan": {
            "engineCalls": [
                {"callId": "stats", "fn": "set_item_stats", "params": {"resultKind": "weapon", "damageClass": "magic", "damage": 21, "useTimeTicks": 17}},
                {"callId": "shot", "fn": "shoot_projectile", "params": {"runtimeFamily": "cast", "delivery": "cast", "movement": "straight", "shotCount": 3, "spreadRadians": 0.2, "speed": 11, "pierce": 2, "rangeTiles": 44, "lifetimeTicks": 120}},
                {"fn": "spawn_secondary_projectiles", "params": {"trigger": "on_hit", "count": 2, "maxChildProjectiles": 4}},
                {"fn": "apply_on_hit_effect", "params": {"onHit": "burst", "aoeRadiusTiles": 3}},
                {"fn": "spawn_contact_particles", "params": {"effect": "star", "amount": 20}},
                {"fn": "leave_trail_or_field", "params": {"trailLength": 12, "fieldRadiusTiles": 5}},
            ]
        },
    }

    result = compile_runtime_plan_to_genome_result(data)
    provenance = result["provenance"]
    sources = provenance["fieldSources"]

    assert sources["damage"] == "set_item_stats"
    assert sources["useTimeTicks"] == "set_item_stats"
    assert sources["damageClass"] == "set_item_stats"
    assert sources["shotCount"] == "shoot_projectile"
    assert sources["speed"] == "shoot_projectile"
    assert sources["pierce"] == "shoot_projectile"
    assert sources["rangeTiles"] == "shoot_projectile"
    assert sources["range"] == "shoot_projectile"
    assert sources["lifetimeTicks"] == "shoot_projectile"
    assert sources["lifetime"] == "shoot_projectile"
    assert sources["runtimeFamily"] == "shoot_projectile"
    assert sources["splitCount"] == "spawn_secondary_projectiles"
    assert sources["maxChildProjectiles"] == "spawn_secondary_projectiles"
    assert sources["onHit"] == "apply_on_hit_effect"
    assert sources["aoeRadiusTiles"] == "apply_on_hit_effect"
    assert sources["burstDustCap"] == "spawn_contact_particles"
    assert sources["effect"] == "spawn_contact_particles"
    assert sources["trailLength"] == "leave_trail_or_field"
    assert sources["vfxFieldRadiusTiles"] == "leave_trail_or_field"
    assert sources["fieldRadius"] == "leave_trail_or_field"

    assert provenance["gameplayChildren"]["enabled"] is True
    assert provenance["gameplayChildren"]["source"] == "spawn_secondary_projectiles"
    assert provenance["pureVfx"]["enabled"] is True
    assert provenance["pureVfx"]["authoredCallCount"] >= 2
    assert provenance["authoredFields"]["damage"] is True
    assert {
        "callId": "stats",
        "fn": "set_item_stats",
        "param": "damage",
        "authoredValue": 21,
        "compiledFields": ["damage"],
        "claimableFields": ["damage"],
    } in provenance["authoredParameters"]
    assert {
        "callId": "shot",
        "fn": "shoot_projectile",
        "param": "speed",
        "authoredValue": 11,
        "compiledFields": ["speed"],
        "claimableFields": ["speed"],
    } in provenance["authoredParameters"]


def _contract_check_defaults_are_distinguishable_from_authored_fields() -> None:
    data = {
        "category": "weapon",
        "runtimePlan": {
            "engineCalls": [
                {"fn": "set_item_stats", "params": {"resultKind": "weapon", "damage": 8, "useTimeTicks": 24}},
                {"fn": "shoot_projectile", "params": {"runtimeFamily": "shoot", "delivery": "shoot", "movement": "straight", "speed": 9}},
            ]
        },
    }
    provenance = compile_runtime_plan_to_genome_result(data)["provenance"]
    sources = provenance["fieldSources"]

    assert sources["damage"] == "set_item_stats"
    assert sources["useTimeTicks"] == "set_item_stats"
    assert "shotCount" not in sources
    assert provenance["authoredFields"].get("shotCount") is not True
    assert sources["speed"] == "shoot_projectile"


def _contract_check_tool_and_accessory_params_publish_exact_final_wire_fields() -> None:

    assert compiled_fields_for_authored_param("tool_capability", "pickPower") == frozenset({"pickPower"})
    assert compiled_fields_for_authored_param("tool_capability", "miningSpeedScale") == frozenset({"miningSpeedScale"})
    assert compiled_fields_for_authored_param("accessory_effect", "stats.lifeRegen") == frozenset({"lifeRegen"})
    assert compiled_fields_for_authored_param("accessory_effect", "stats.movementSpeed") == frozenset({"movementSpeed"})


def _contract_check_final_wire_receipts_are_compiler_owned_per_authored_param() -> None:
    authored = {
        "concept": {"coreMechanic": "Deals direct magic damage."},
        "runtimeContract": {"primaryVerb": "cast", "controlStyle": "tap"},
        "runtimePlan": {"engineCalls": [{
            "callId": "stats",
            "fn": "set_item_stats",
            "params": {"resultKind": "weapon", "damage": 21, "useTimeTicks": 17},
        }]},
    }
    output = {
        **authored,
        "gameplay": {"kind": "weapon", "damage": 21, "useTime": 17},
        "attack": {},
    }
    _attach_evidence(output, authored)
    receipts = output["runtimeContract"]["finalWireReceipts"]
    assert {
        "callId": "stats",
        "authoredParam": "damage",
        "authoredValue": 21,
        "compiledField": "damage",
        "finalPath": "gameplay.damage",
        "compiledValue": 21,
        "status": "active",
    } in receipts
    assert {
        "callId": "stats",
        "authoredParam": "useTimeTicks",
        "authoredValue": 17,
        "compiledField": "useTimeTicks",
        "finalPath": "gameplay.useTime",
        "compiledValue": 17,
        "status": "active",
    } in receipts
    before_report = deepcopy(output)
    final_report = structural_final_wire_report(output)
    assert output == before_report
    assert final_report["ok"] is True
    assert set(final_report["componentGates"]) == {
        "receiptShape", "sourceIdentity", "finalProjection", "mechanic",
    }
    assert "tooltip" not in output
    apply_structural_final_wire_contract(output, final_report)
    assert output["tooltip"] == "Executable: weapon runtime."
    assert output["tooltip"] != authored["concept"]["coreMechanic"]

    dropped = {**authored, "gameplay": {}, "attack": {}}
    _attach_evidence(dropped, authored)
    assert any(
        row["callId"] == "stats"
        and row["authoredParam"] == "damage"
        and row["status"] == "active"
        for row in dropped["runtimeContract"]["finalWireReceipts"]
    )
    dropped_report = structural_final_wire_report(dropped)
    assert dropped_report["ok"] is False
    assert any(
        row["kind"] == "compiler_provenance_dropped"
        for row in dropped_report["blockingClaims"]
    )

    # Receipts must be computed from the compiler preimage, never from an already
    # corrupted final DTO that could otherwise certify itself.
    misprojected = {
        **authored,
        "gameplay": {"kind": "weapon", "damage": 12, "useTime": 17},
        "attack": {},
    }
    _attach_evidence(misprojected, authored)
    misprojected_report = structural_final_wire_report(misprojected)
    assert misprojected_report["ok"] is False
    assert any(
        row["kind"] == "compiler_provenance_mismatched"
        and row["authoredParam"] == "damage"
        and row["compiledValue"] == 21
        and row["finalActual"] == 12
        for row in misprojected_report["blockingClaims"]
    )

    list_authored = {
        "concept": {"coreMechanic": "Applies two finite vanilla buffs."},
        "runtimeContract": {"primaryVerb": "apply buffs", "controlStyle": "tap"},
        "runtimePlan": {"engineCalls": [{
            "callId": "buffs",
            "fn": "apply_player_effect_on_use",
            "params": {"buffs": [
                {"buffType": 5, "buffTime": 600},
                {"buffType": 6, "buffTime": 300},
            ]},
        }]},
    }
    list_output = {
        **list_authored,
        "gameplay": {"extraBuffs": [
            {"buffCode": 5, "buffTime": 600},
            {"buffCode": 6, "buffTime": 300},
        ]},
        "attack": {},
    }
    _attach_evidence(list_output, list_authored)
    list_receipt = next(
        row
        for row in list_output["runtimeContract"]["finalWireReceipts"]
        if row["callId"] == "buffs" and row["authoredParam"] == "buffs"
    )
    assert list_receipt["finalPath"] == "gameplay.extraBuffs"
    assert list_receipt["compiledValue"] == list_output["gameplay"]["extraBuffs"]
    assert structural_final_wire_report(list_output)["ok"] is True


def _contract_check_dormant_equipment_sections_publish_explicit_enabled_sentinel() -> None:
    authored = {
        "category": "accessory",
        "runtimePlan": {
            "resultKind": "accessory",
            "engineCalls": [
                {
                    "callId": "base_stats",
                    "fn": "set_item_stats",
                    "params": {
                        "resultKind": "accessory",
                        "damageClass": "generic",
                        "damage": 0,
                        "useTimeTicks": 0,
                        "useAnimationTicks": 0,
                        "maxStack": 1,
                        "defense": 0,
                    },
                },
                {
                    "callId": "mobility",
                    "fn": "accessory_effect",
                    "params": {
                        "archetype": "mobility",
                        "stats": {"movementSpeed": 0.15},
                    },
                },
            ],
        },
    }

    result = compile_runtime_plan_to_final_result(deepcopy(authored))
    sections = result["finalSections"]
    assert sections["accessory"]["enabled"] is True
    assert sections["armor"] == {"defense": 0, "enabled": False}
    assert any(
        row["callId"] == "base_stats"
        and row["authoredParam"] == "defense"
        and row["finalPath"] == "armor.defense"
        and row["status"] == "active"
        for row in result["finalWireReceipts"]
    )

    wire = deepcopy(sections)
    wire["attack"] = {"enabled": False}
    validate_executable_item_boundary(wire)


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_runtime_provenance_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_authored_runtime_fields_have_precise_provenance',
            '_contract_check_defaults_are_distinguishable_from_authored_fields',
            '_contract_check_tool_and_accessory_params_publish_exact_final_wire_fields',
            '_contract_check_final_wire_receipts_are_compiler_owned_per_authored_param',
            '_contract_check_dormant_equipment_sections_publish_explicit_enabled_sentinel',
        ),
    )
