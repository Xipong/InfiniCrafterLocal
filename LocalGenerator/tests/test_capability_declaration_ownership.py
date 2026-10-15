"""Capability facts belong to their declaration; projections remain mechanical."""
from dataclasses import replace

import pytest

import infini_local.core.runtime_authoring.capability_registry as registry


@pytest.mark.parametrize("declared", registry._CAPS, ids=lambda cap: cap.name)
def test_declared_metadata_survives_finalization(declared):
    final = registry.CAPABILITY_REGISTRY[declared.name]
    for field in (
        "csharp_owner", "component_slot", "network_authority", "authority_by_effect",
        "exclusive_group", "position_ownership", "emitted_events",
        "activation_spawn_count_param", "meaningful_for_stationary",
    ):
        assert getattr(final, field) == getattr(declared, field), (declared.name, field)
    assert final.requirements[:len(declared.requirements)] == declared.requirements
    if declared.final_wire_paths:
        assert final.final_wire_paths[:len(declared.final_wire_paths)] == declared.final_wire_paths
        assert not any("*" in path for path in declared.final_wire_paths)


def test_one_declaration_is_enough_for_a_new_explicit_metadata_projection():
    requirement = registry.RequirementSpec("capability_present", capability="configure_item_use")
    declared = registry._cap(
        "declaration_only_probe", "Metadata ownership probe, never installed in the registry.",
        "item", ("item_body",), {},
        py="probe.py::compile", cs="Probe.cs::Execute",
        wire=("gameplay.probe",), component_slot="probe",
        authority="owner_execute_sync", authority_by_effect={"probe": "client_visual_only"},
        exclusive_group="probe_group", position_ownership="probe_position",
        emitted_events=("on_hit",), requirements=(requirement,),
        activation_spawn_count_param="count", meaningful_for_stationary=True,
        provenance="test only", repair_group="probe",
    )
    final = registry._enrich_capability(declared)
    assert final.csharp_owner == "Probe.cs::Execute"
    assert final.final_wire_paths == ("gameplay.probe",)
    assert final.component_slot == "probe"
    assert final.network_authority == "owner_execute_sync"
    assert dict(final.authority_by_effect) == {"probe": "client_visual_only"}
    assert final.position_ownership == "probe_position"
    assert final.emitted_events == ("on_hit",)
    assert final.activation_spawn_count_param == "count"
    assert final.meaningful_for_stationary
    assert final.requirements == (requirement,)
    assert final.dependencies == ("configure_item_use",)
    assert final.conflicts == ("exclusive_group:probe_group",)


def test_existing_capability_metadata_is_not_overridden_by_its_name():
    declared = next(cap for cap in registry._CAPS if cap.name == "set_projectile_sentry")
    changed = replace(declared, csharp_owner="Changed.cs::Execute", component_slot="changed",
                      final_wire_paths=("runtimeProgram.entities[].changed",),
                      network_authority="client_visual_only")
    final = registry._enrich_capability(changed)
    assert final.csharp_owner == changed.csharp_owner
    assert final.component_slot == changed.component_slot
    assert final.final_wire_paths == changed.final_wire_paths
    assert final.network_authority == changed.network_authority
    assert registry.CAPABILITY_REGISTRY[declared.name].csharp_owner == declared.csharp_owner


def test_simple_component_wire_paths_still_follow_parameter_projection():
    declared = next(cap for cap in registry._CAPS if cap.name == "set_projectile_collision")
    assert declared.final_wire_paths == ()
    changed = replace(declared, params={**declared.params,
                                       "probe": registry.ParamSpec("integer", "test", wire_name="probeWire")})
    final = registry._enrich_capability(changed)
    assert final.final_wire_paths == (*registry.CAPABILITY_REGISTRY[declared.name].final_wire_paths,
                                     "runtimeProgram.entities[].collision.probeWire")


def test_effect_group_projection_and_dependencies_remain_derived():
    declared = next(cap for cap in registry._CAPS if cap.name == "restore_resources_on_use")
    final = registry._enrich_capability(declared)
    assert final.final_wire_paths == (
        *declared.final_wire_paths, "runtimeProgram.effectGroups[].id",
        *(path.replace("gameplay.", "runtimeProgram.effectGroups[].", 1)
          for path in declared.final_wire_paths),
    )
    tool = registry.CAPABILITY_REGISTRY["configure_tool"]
    assert tool.dependencies == ("configure_item_use",)
    assert registry.CAPABILITY_REGISTRY["select_targets_and_emit_on_event"].requirements[0].message == (
        "The source entity must actually emit the selected hit event."
    )
    assert sum(row.kind == "event_available" for row in
               registry.CAPABILITY_REGISTRY["select_targets_and_emit_on_event"].requirements) == 1
