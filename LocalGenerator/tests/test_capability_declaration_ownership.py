"""Capability facts belong to their declaration; projections remain mechanical."""
from dataclasses import replace

from hypothesis import example, given, settings, strategies as st

import infini_local.core.runtime_authoring.capability_registry as registry


@settings(max_examples=60, derandomize=True, deadline=None)
@given(
    name=st.sampled_from(tuple(cap.name for cap in registry._CAPS)),
    suffix=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=12),
    enabled=st.booleans(),
)
@example(name="sentry", suffix="renamed", enabled=True)
@example(name="restore_resources_on_use", suffix="effects", enabled=False)
@example(name="spawn_on_event", suffix="events", enabled=True)
@example(name="turn_velocity", suffix="timing", enabled=False)
def test_declared_metadata_changes_reach_finalization_without_name_overrides(name, suffix, enabled):
    """Changing declared facts must change their projection, even for known names.

    The old per-capability snapshots compared two copies of today's metadata.
    Generated replacements exercise ownership with values absent from the real
    registry, while explicit examples retain event/effect-group special paths.
    """
    declared = next(cap for cap in registry._CAPS if cap.name == name)
    requirement = registry.RequirementSpec("capability_present", capability="item_use")
    facts = {
        "csharp_owner": f"{suffix}.cs::Execute",
        "component_slot": suffix,
        "network_authority": "client_visual_only" if enabled else "owner_execute_sync",
        "authority_by_effect": {suffix: "client_visual_only"},
        "exclusive_group": suffix,
        "position_ownership": suffix,
        "emitted_events": ("on_hit",) if enabled else (),
        "activation_spawn_count_param": suffix if enabled else "",
        "meaningful_for_stationary": enabled,
    }
    changed = replace(declared, **facts, requirements=(requirement,),
                      final_wire_paths=(f"gameplay.{suffix}",))
    final = registry._enrich_capability(changed)
    assert {field: getattr(final, field) for field in facts} == facts
    assert final.requirements[0] == requirement
    assert final.final_wire_paths[0] == f"gameplay.{suffix}"
    assert "item_use" in final.dependencies
    assert final.conflicts == (f"exclusive_group:{suffix}",)
    assert registry.CAPABILITY_REGISTRY[name].csharp_owner == declared.csharp_owner


def test_one_declaration_is_enough_for_a_new_explicit_metadata_projection():
    requirement = registry.RequirementSpec("capability_present", capability="item_use")
    declared = registry._cap(
        "declaration_only_probe", "Metadata ownership probe, never installed in the registry.",
        "item", ("item_body",), {},
        py="probe.py::compile", cs="Probe.cs::Execute",
        wire=("gameplay.probe",), component_slot="probe",
        authority="owner_execute_sync", authority_by_effect={"probe": "client_visual_only"},
        exclusive_group="probe_group", position_ownership="probe_position",
        emitted_events=("on_hit",), requirements=(requirement,),
        activation_spawn_count_param="count", meaningful_for_stationary=True,
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
    assert final.dependencies == ("item_use",)
    assert final.conflicts == ("exclusive_group:probe_group",)


def test_simple_component_wire_paths_still_follow_parameter_projection():
    declared = next(cap for cap in registry._CAPS if cap.name == "projectile_collision")
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
    tool = registry.CAPABILITY_REGISTRY["tool_stats"]
    assert tool.dependencies == ("item_use",)
    declared = next(cap for cap in registry._CAPS if cap.name == "emit_to_targets_on_event")
    required_event = next(row for row in declared.requirements if row.kind == "event_available")
    final_events = tuple(row for row in registry._enrich_capability(declared).requirements
                         if row.kind == "event_available")
    assert final_events == (required_event,)
