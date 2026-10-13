"""Canonical registry inventories and real schema/validator/Repair/compiler consumers."""

from __future__ import annotations
from dataclasses import replace
from types import MappingProxyType
from infini_local.core.runtime_authoring.capability_registry import visible_capabilities
from copy import deepcopy
import pytest
from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY, BINDING_ACTION_REGISTRY, ENTITY_KIND_REGISTRY, EVENT_KIND_REGISTRY, INPUT_KIND_REGISTRY, runtime_authoring_registry_manifest, compact_capability_catalog, compile_runtime_program, validate_runtime_program, validate_runtime_wire, audit_compiler_receipts, validator, repair_scope
from infini_local.core.runtime_authoring import capability_registry
import infini_local.core.runtime_authoring.capability_registry as registry_module
import infini_local.core.runtime_authoring.validator as validator_module
from infini_local.core.runtime_authoring.program_schema import runtime_program_author_schema
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.qa.capability_library_audit import capability_library_audit


@pytest.mark.parametrize(
    "key,identity,registry",
    [
        pytest.param("entityKinds", "kind", ENTITY_KIND_REGISTRY, id="entity-kinds"),
        pytest.param("inputs", "input", INPUT_KIND_REGISTRY, id="inputs"),
        pytest.param("bindingActions", "action", BINDING_ACTION_REGISTRY, id="binding-actions"),
        pytest.param("events", "event", EVENT_KIND_REGISTRY, id="events"),
        pytest.param("capabilities", "fn", {cap.name: cap for cap in visible_capabilities()}, id="capabilities"),
    ],
)
def test_machine_manifest_has_exact_registry_identity(key, identity, registry):
    rows = runtime_authoring_registry_manifest()[key]
    expected = ({name for name, cap in registry.items() if cap.prompt_visible and cap.decision == "expose"}
                if key == "capabilities" else set(registry))
    assert {r[identity] for r in rows} == expected
    assert len(rows) == len(expected)
    if key == "capabilities":
        assert all(r["slot"] and r["authority"] for r in rows)
        assert all(
            {"requires", "positionOwnership", "activationSpawnCountParam", "meaningfulForStationary", "multiplicity"} <= r.keys()
            for r in rows
        )


@pytest.mark.parametrize("fn", [cap.name for cap in visible_capabilities()])
def test_registered_capability_compiles_and_authenticates_source_without_mutation(fn):
    from jsonschema import Draft202012Validator
    from infini_local.pipelines.author_item_contract import author_item_response_schema

    item = build_capability_witness(fn)
    before = deepcopy(item)
    assert Draft202012Validator(author_item_response_schema()).is_valid(item)
    assert validate_runtime_program(item)["ok"]
    wire = compile_runtime_program(item)
    assert validate_runtime_wire(wire)["ok"]
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"],
                                   authored_document=item, final_document=wire)["ok"]
    assert item == before


def test_registry_public_catalog_and_schema_remain_reachable():
    expected = {cap.name for cap in visible_capabilities()}
    schema = runtime_program_author_schema()["properties"]["calls"]["items"]["oneOf"]
    assert {row["properties"]["fn"]["const"] for row in schema} == expected
    assert {row["fn"] for row in compact_capability_catalog()} == expected
    report = capability_library_audit()
    assert report["ok"], report["issues"]


def test_registry_mutation_updates_schema_but_missing_executor_stays_red(monkeypatch: pytest.MonkeyPatch) -> None:
    source = CAPABILITY_REGISTRY["emit_light_while_active"]
    synthetic = replace(
        source,
        name="emit_test_light",
        summary="Synthetic mutation witness over an existing parameter surface.",
        compiler_owner="synthetic.missing.vertical.slice",
        csharp_owner="SyntheticMissingExecutor.cs",
        provenance="mutation test",
    )
    mutated = dict(CAPABILITY_REGISTRY)
    mutated[synthetic.name] = synthetic
    frozen = MappingProxyType(mutated)
    monkeypatch.setattr(registry_module, "CAPABILITY_REGISTRY", frozen)
    monkeypatch.setattr(validator_module, "CAPABILITY_REGISTRY", frozen)
    schema = runtime_program_author_schema()
    variants = schema["properties"]["calls"]["items"]["oneOf"]
    assert any(row["properties"]["fn"].get("const") == synthetic.name for row in variants)

    authored = build_runtime_fixture("door_on_chain")
    authored["runtimeProgram"]["calls"].append(
        {
            "id": "synthetic_light",
            "fn": synthetic.name,
            "target": "chained_door",
            "params": {"strength": 0.5, "color": "white"},
        }
    )
    with pytest.raises(AssertionError, match="unhandled runtime entity capability"):
        compile_runtime_program(authored)


def test_event_registry_mutation_reaches_validator_and_repair_projection(monkeypatch) -> None:
    # Without damage, this on_hit has no producer under the original registry;
    # its existing collision call becomes the producer after the registry edit.
    without_damage = build_runtime_fixture("workbench_blade")
    without_damage["runtimeProgram"]["calls"] = [
        row for row in without_damage["runtimeProgram"]["calls"] if row["id"] != "workbench_blade_damage"
    ]
    original_errors = validator.validate_runtime_program(without_damage)["errors"]
    assert [(row["code"], row["allowed"]) for row in original_errors] == [
        ("event_not_emitted", ["set_projectile_damage"]),
    ]

    # Conversely, removing collision leaves an unrelated required-component
    # error, but on_hit itself is still emitted by the original damage call.
    without_collision = build_runtime_fixture("workbench_blade")
    without_collision["runtimeProgram"]["calls"] = [
        row for row in without_collision["runtimeProgram"]["calls"] if row["id"] != "workbench_blade_collision"
    ]
    assert [row["code"] for row in validator.validate_runtime_program(without_collision)["errors"]] == [
        "missing_required_component",
    ]

    registry = dict(EVENT_KIND_REGISTRY)
    registry["on_hit"] = replace(
        registry["on_hit"],
        producer_capabilities=("set_projectile_collision",),
    )
    monkeypatch.setattr(capability_registry, "EVENT_KIND_REGISTRY", registry)
    assert validator.validate_runtime_program(without_damage)["ok"] is True

    changed_errors = validator.validate_runtime_program(without_collision)["errors"]
    event_errors = [row for row in changed_errors if row["code"] == "event_not_emitted"]
    assert len(event_errors) == 1
    assert event_errors[0]["allowed"] == ["set_projectile_collision"]
    assert event_errors[0]["relatedIds"] == ["workbench_blade"]
    scope = repair_scope.build_runtime_repair_scope(without_collision, event_errors)
    assert scope["create"]["calls"]["allowedFns"] == ["set_projectile_collision"]
    assert scope["create"]["calls"]["allowedTargetIds"] == ["workbench_blade"]
    assert scope["repairRequirements"][0]["requiredOneOfCapabilities"] == ["set_projectile_collision"]
