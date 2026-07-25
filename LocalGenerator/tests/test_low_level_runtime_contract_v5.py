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
from infini_local.pipelines.llm_authoring_prompt import (
    PLANNER_PROMPT_LIMIT_CHARS,
    PLANNER_PROMPT_MIN_HEADROOM_CHARS,
    planner_prompt_usability_report,
)
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def _codes(report: dict) -> set[str]:
    return {str(row.get("code")) for row in report.get("errors") or []}


def test_registry_provider_prompt_and_vertical_wire_are_one_inventory() -> None:
    names = set(CAPABILITY_REGISTRY)
    assert len(names) == 52
    assert {row["fn"] for row in compact_capability_catalog()} == names
    assert len(capability_provider_union()) == len(names)
    heal_capability = CAPABILITY_REGISTRY["heal_owner_on_event"]
    assert heal_capability.network_authority == "owner_execute_sync"
    parent_a = {"name": "Workbench", "id": "a", "damage": 0, "useTime": 20, "tags": ["furniture"]}
    parent_b = {"name": "Blade", "id": "b", "damage": 18, "useTime": 24, "tags": ["metal"]}
    report = planner_prompt_usability_report(parent_a, parent_b, parent_a, parent_b, "a+b")
    assert report["ok"] is True
    assert PLANNER_PROMPT_LIMIT_CHARS == 96_000
    assert report["limit"] == PLANNER_PROMPT_LIMIT_CHARS
    assert report["headroom"] >= PLANNER_PROMPT_MIN_HEADROOM_CHARS
    assert report["visibleCapabilities"] == len(names)
    assert report["missingCapabilities"] == []
    assert report["extraCapabilities"] == []
    assert report["containsWeaponMacro"] is False
    assert report["containsFamilyRouter"] is False

    rich_parent = build_runtime_fixture("held_and_deployed")
    rich_report = planner_prompt_usability_report(
        rich_parent, rich_parent, rich_parent, rich_parent, "rich+rich"
    )
    assert rich_report["ok"] is True
    assert rich_report["headroom"] >= PLANNER_PROMPT_MIN_HEADROOM_CHARS
    assert rich_report["visibleCapabilities"] == len(names)
    assert rich_report["missingCapabilities"] == []


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
    duplicate["runtimeProgram"]["bindings"].append({"id": "duplicate_primary", "input": "primary_use", "action": "spawn_entity", "role": "secondary", "target": "nail"})
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
        "id": "nail_returns_blade", "fn": "spawn_entity_on_event", "role": "secondary", "target": "nail",
        "params": {"event": "on_hit", "entity": "workbench_blade", "count": 1, "spreadRadians": 0.0, "damageMultiplier": 1.0, "delayTicks": 0},
    })
    assert "illegal_event_cycle" in _codes(validate_runtime_program(cycle))

    budget = build_runtime_fixture("workbench_blade")
    for index in range(3):
        budget["runtimeProgram"]["calls"].append({
            "id": f"extra_spawn_{index}", "fn": "spawn_entity_on_event", "role": "secondary", "target": "workbench_blade",
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


def test_explicit_primary_entity_projects_to_wire_and_gates_csharp_item_and_held_ownership() -> None:
    item_primary = build_runtime_fixture("workbench_blade")
    assert validate_runtime_program(item_primary)["stats"]["primaryEntityId"] == "item"
    item_wire = compile_runtime_program(item_primary)
    assert item_wire["runtimeProgram"]["primaryEntityId"] == "item"
    assert item_wire["runtimeProgram"]["primaryOwner"] == "item_body"
    assert item_wire["runtimeProgram"]["bindings"][0]["role"] == "secondary"

    projectile_primary = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    assert projectile_primary["runtimeProgram"]["primaryEntityId"] == "chained_door"
    assert projectile_primary["runtimeProgram"]["primaryOwner"] == "projectile"
    assert projectile_primary["runtimeProgram"]["bindings"][0]["role"] == "primary"

    mixed = build_runtime_fixture("workbench_blade")
    next(row for row in mixed["runtimeProgram"]["calls"] if row["id"] == "workbench_blade_damage")["role"] = "primary"
    assert "mixed_entity_role" in _codes(validate_runtime_program(mixed))

    tampered = copy.deepcopy(item_wire)
    tampered["runtimeProgram"]["primaryOwner"] = "projectile"
    assert "primary_owner_mismatch" in _codes(validate_runtime_wire(tampered))
    tampered = copy.deepcopy(item_wire)
    tampered["runtimeProgram"]["bindings"][0]["role"] = "primary"
    assert "binding_primary_role_mismatch" in _codes(validate_runtime_wire(tampered))

    mod = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal"
    apply_source = (mod / "Common" / "Models" / "GeneratedItemData.Apply.cs").read_text("utf-8")
    item_source = (mod / "Content" / "Items" / "GeneratedItem.cs").read_text("utf-8")
    projectile_source = (mod / "Content" / "Projectiles" / "GeneratedProjectile.cs").read_text("utf-8")
    executor_source = (mod / "Content" / "Projectiles" / "GeneratedProjectile.Executors.cs").read_text("utf-8")
    assert "RuntimeProgram.PrimaryOwner != RuntimeProgramSpec.ItemBodyOwner" in apply_source
    assert "Data.RuntimeProgram.PrimaryOwner != RuntimeProgramSpec.ItemBodyOwner" in item_source
    assert "_data?.RuntimeProgram.PrimaryOwner == RuntimeProgramSpec.ProjectileOwner" in projectile_source
    assert "PrimaryEntityId" in projectile_source
    assert "owner.heldProj = Projectile.whoAmI;" in projectile_source
    assert "owner.heldProj = Projectile.whoAmI;" not in executor_source


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


def test_delayed_item_events_have_a_bounded_runtime_consumer_and_keep_activation_budget() -> None:
    mod = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal"
    item_source = (mod / "Content" / "Items" / "GeneratedItem.cs").read_text("utf-8")
    projectile_source = (
        mod / "Content" / "Projectiles" / "GeneratedProjectile.RuntimeEvents.cs"
    ).read_text("utf-8")
    limits_source = (mod / "Common" / "InfiniRuntimeLimits.cs").read_text("utf-8")
    executor_source = (
        mod / "Common" / "Runtime" / "RuntimeProgramExecutor.cs"
    ).read_text("utf-8")
    scheduler_source = (
        mod / "Common" / "Runtime" / "RuntimeDelayedActionScheduler.cs"
    ).read_text("utf-8")

    run_item_event = item_source.split("private void RunItemEvent", 1)[1].split(
        "private void QueueOrExecuteItemAction", 1
    )[0]
    queue_method = item_source.split("private void QueueOrExecuteItemAction", 1)[1].split(
        "public override bool Shoot", 1
    )[0]

    assert "action.DelayTicks > 0" in queue_method
    assert "RuntimeDelayedActionScheduler.TrySchedule" in queue_method
    assert "_pendingItemActions" not in item_source
    assert "_pendingActions" not in projectile_source
    assert "RuntimeDelayedActionScheduler.TrySchedule" in projectile_source
    assert "RuntimeProgramExecutor.ExecuteAction" in scheduler_source
    assert "PostUpdateEverything" in scheduler_source
    assert "remainingSpawnBudget -= reservedSpawnBudget" in scheduler_source
    assert "new ItemEventBudgetState" not in run_item_event
    assert "MaxPendingRuntimeActions = 256" in limits_source
    assert "MaxRuntimeDelayedActionsPerTick = 64" in limits_source
    assert "InfiniRuntimeLimits.MaxPendingRuntimeActions" in scheduler_source
    assert "InfiniRuntimeLimits.MaxRuntimeDelayedActionsPerTick" in scheduler_source
    assert "for (int i = 0; i < Pending.Count;)" in scheduler_source
    assert "for (int i = Pending.Count - 1" not in scheduler_source
    assert "Pending[i] = pending with { Ticks = 1 }" in scheduler_source
    assert "includeDelayed" not in executor_source


def test_csharp_runtime_preserves_authored_tick_units_and_enforces_spawn_chokepoint_limits() -> None:
    mod = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal"
    projectile = (mod / "Content" / "Projectiles" / "GeneratedProjectile.cs").read_text("utf-8")
    executors = (
        mod / "Content" / "Projectiles" / "GeneratedProjectile.Executors.cs"
    ).read_text("utf-8")
    events = (
        mod / "Content" / "Projectiles" / "GeneratedProjectile.RuntimeEvents.cs"
    ).read_text("utf-8")
    vfx = (mod / "Common" / "VFX" / "InfiniVfxRuntime.cs").read_text("utf-8")

    assert "AuthoredTicksToProjectileUpdates" in projectile
    assert "AuthoredTicksToProjectileUpdates(entity.LifetimeTicks)" in projectile
    for temporal_use in (
        "AuthoredTicksToProjectileUpdates(_entity!.Controller.Params.WarmupTicks)",
        "AuthoredTicksToProjectileUpdates(p.ChargeTicks)",
        "AuthoredTicksToProjectileUpdates(returnAfterTicks)",
        "AuthoredTicksToProjectileUpdates(p.DurationTicks)",
    ):
        assert temporal_use in executors
    assert "AuthoredTicksToProjectileUpdates(Math.Max(6, action.PeriodTicks))" in events
    assert "state.LastGameUpdate == Main.GameUpdateCount" in vfx
    assert "record struct InfiniVfxSlotEmissionKey" in vfx
    assert "string SlotId" in vfx
    assert "new InfiniVfxSlotEmissionKey(projectile.identity, entityId, eventName, slot.Id)" in vfx
    on_event = vfx.split(" OnEvent(", 1)[1].split(
        "private static void BeginWorldTick", 1
    )[0]
    assert "foreach (VfxSlotSpec slot in manifest.Slots)" in on_event
    assert "TryMarkSlotEmission(projectile, entityId, eventName, slot" in on_event
    assert "EmitSlot(center, projectile.velocity, slot" in on_event
    run_event = events.split("private void RunRuntimeEvent", 1)[1].split(
        "private void RunPeriodicActions", 1
    )[0]
    assert "foreach (RuntimeEventActionSpec action" in run_event
    assert "RuntimeProgramExecutor.ExecuteAction" in run_event

    spawn = projectile.split("public static int SpawnRuntimeEntity", 1)[1].split(
        "private static int CountActiveGeneratedProjectiles", 1
    )[0]
    assert "remainingSpawnBudget <= 0" in spawn
    assert "MaxRuntimeActiveProjectilesPerOwner" in spawn
    assert "CountActiveGeneratedProjectiles(owner.whoAmI)" in spawn
