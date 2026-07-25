from __future__ import annotations

import copy
import json
from pathlib import Path

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY,
    audit_compiler_receipts,
    capability_provider_union,
    compile_runtime_program,
    compact_capability_catalog,
    validate_runtime_program,
    validate_runtime_wire,
)
from infini_local.pipelines.llm_authoring_prompt import planner_prompt_usability_report
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def _codes(report: dict) -> set[str]:
    return {str(row.get("code")) for row in report.get("errors") or []}


def test_registry_provider_prompt_and_vertical_wire_are_one_inventory() -> None:
    names = set(CAPABILITY_REGISTRY)
    assert len(names) == 52
    assert {row["fn"] for row in compact_capability_catalog()} == names
    assert len(capability_provider_union()) == len(names)
    parent_a = {"name": "Workbench", "id": "a", "damage": 0, "useTime": 20, "tags": ["furniture"]}
    parent_b = {"name": "Blade", "id": "b", "damage": 18, "useTime": 24, "tags": ["metal"]}
    report = planner_prompt_usability_report(parent_a, parent_b, parent_a, parent_b, "a+b")
    assert report["ok"] is True
    assert report["visibleCapabilities"] == len(names)
    assert report["missingCapabilities"] == []
    assert report["extraCapabilities"] == []
    assert report["containsWeaponMacro"] is False
    assert report["containsFamilyRouter"] is False


def test_all_non_archetypal_fixtures_compile_to_strict_wire() -> None:
    for name in (
        "workbench_blade", "umbrella_grenade", "door_on_chain", "returning_potion",
        "fishing_platform_tool", "shield_and_disc", "held_and_deployed", "equipment_tool_combat",
    ):
        authored = build_runtime_fixture(name)
        assert validate_runtime_program(authored)["ok"], name
        compiled = compile_runtime_program(authored)
        wire = validate_runtime_wire(compiled)
        assert wire["ok"], (name, wire["errors"])
        encoded = json.dumps(compiled, ensure_ascii=False)
        assert "runtimeFamily" not in encoded
        assert "weaponFamily" not in encoded
        assert compiled["runtimeProgram"]["schema"] == "infini.runtime-program.wire.v1"
        assert "calls" not in compiled["runtimeProgram"]


def test_wrong_target_kind_duplicate_input_missing_reference_and_unknown_capability_fail_closed() -> None:
    wrong = build_runtime_fixture("workbench_blade")
    next(row for row in wrong["runtimeProgram"]["calls"] if row["id"] == "workbench_blade_motion")["target"] = "item"
    assert "wrong_target_kind" in _codes(validate_runtime_program(wrong))

    duplicate = build_runtime_fixture("workbench_blade")
    duplicate["runtimeProgram"]["bindings"].append({"id": "duplicate_primary", "input": "primary_use", "action": "spawn_entity", "target": "nail"})
    assert "duplicate_exclusive_input" in _codes(validate_runtime_program(duplicate))

    missing = build_runtime_fixture("workbench_blade")
    next(row for row in missing["runtimeProgram"]["bindings"] if row["id"] == "primary_workbench")["target"] = "absent"
    assert "missing_entity_reference" in _codes(validate_runtime_program(missing))

    unknown = build_runtime_fixture("workbench_blade")
    next(row for row in unknown["runtimeProgram"]["calls"] if row["id"] == "workbench_blade_motion")["fn"] = "unknown_runtime_magic"
    report = validate_runtime_program(unknown)
    assert report["ok"] is False
    assert any(code.startswith("shape_") or code == "unknown_capability" for code in _codes(report))


def test_event_cycles_child_budget_and_omitted_design_fields_are_rejected_not_repaired_in_code() -> None:
    cycle = build_runtime_fixture("workbench_blade")
    cycle["runtimeProgram"]["calls"].append({
        "id": "nail_returns_blade", "fn": "spawn_entity_on_event", "target": "nail",
        "params": {"event": "on_hit", "entity": "workbench_blade", "count": 1, "spreadRadians": 0.0, "damageMultiplier": 1.0, "delayTicks": 0},
    })
    assert "illegal_event_cycle" in _codes(validate_runtime_program(cycle))

    budget = build_runtime_fixture("workbench_blade")
    for index in range(3):
        budget["runtimeProgram"]["calls"].append({
            "id": f"extra_spawn_{index}", "fn": "spawn_entity_on_event", "target": "workbench_blade",
            "params": {"event": "on_hit", "entity": "nail", "count": 12, "spreadRadians": 0.0, "damageMultiplier": 0.2, "delayTicks": index},
        })
    assert "event_spawn_budget" in _codes(validate_runtime_program(budget))

    missing_motion = build_runtime_fixture("workbench_blade")
    missing_motion["runtimeProgram"]["calls"] = [row for row in missing_motion["runtimeProgram"]["calls"] if row["id"] != "workbench_blade_motion"]
    report = validate_runtime_program(missing_motion)
    assert "missing_movement_component" in _codes(report)
    assert all(row.get("fn") != "move_forward_then_retract" for row in missing_motion["runtimeProgram"]["calls"])


def test_technical_lowering_may_write_only_declared_paths() -> None:
    compiled = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    audit = compiled["runtimeContract"]["technicalLoweringAudit"]
    assert audit["ok"] is True
    fake = copy.deepcopy(compiled["runtimeContract"]["finalWireReceipts"])
    fake.append({
        "callId": "item_stats", "fn": "configure_item_stats",
        "authoredPath": "$.runtimeProgram.calls[0].params.damage",
        "finalPath": "runtimeProgram.entities[0].movement.code",
        "value": 7, "status": "technical_projection",
    })
    rejected = audit_compiler_receipts(fake)
    assert rejected["ok"] is False
    assert rejected["violations"]


def test_active_source_has_no_old_compiler_or_parallel_schema() -> None:
    root = Path(__file__).resolve().parents[1] / "infini_local"
    forbidden_files = {
        "root_lowering.py", "function_contract_registry.py", "combine_genome.py",
        "runtime_authored_composition.py", "presentation_sound.py",
    }
    assert not any(path.name in forbidden_files for path in root.rglob("*.py"))
    active = "\n".join(
        path.read_text("utf-8", errors="ignore")
        for path in (
            root / "pipelines" / "combine_pipeline.py",
            root / "pipelines" / "combine_gameplay.py",
            root / "pipelines" / "llm_authoring_prompt.py",
            root / "core" / "runtime_authoring" / "compiler.py",
        )
    )
    for token in ("perform_melee_attack", "fire_ranged_weapon", "cast_magic_weapon", "deploy_sentry"):
        assert token not in active
