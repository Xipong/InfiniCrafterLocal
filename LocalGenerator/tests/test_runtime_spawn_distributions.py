"""Actual typed Author/provider/compiler/provenance/Repair tests for initial velocity."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, compile_runtime_program, validate_runtime_program, validate_runtime_wire,
    apply_repair_patch, filter_repair_patch_scope,
)
from infini_local.core.runtime_authoring.program_schema import strict_author_shape_report
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.pipelines import author_item_contract as contract
from infini_local.qa.capability_witnesses import build_capability_witness
from test_codex_subscription_contract import _encode_nullable_fixture


VELOCITIES = [
    {"constantSpeedPxPerUpdate": 8.5},
    {"fanSpeed": {"minSpeedPxPerUpdate": 4.5, "maxSpeedPxPerUpdate": 8.5}},
    {"radial": {"minSpeedPxPerUpdate": 4, "maxSpeedPxPerUpdate": 7}},
    {"disk": {"maxSpeedPxPerUpdate": 6}},
    {"cone": {"minSpeedPxPerUpdate": 4, "maxSpeedPxPerUpdate": 7, "halfAngleRadians": 0.2}},
]


def fixture(velocity):
    document = build_capability_witness("configure_spawn")
    call = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "configure_spawn")
    call["params"]["velocity"] = deepcopy(velocity)
    return document, call


def component(wire, call):
    return next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == call["target"])["spawn"]


@pytest.mark.parametrize("velocity", VELOCITIES)
def test_every_velocity_variant_has_strict_provider_inverse_and_exact_receipts(velocity):
    document, call = fixture(velocity)
    assert strict_author_shape_report(document)["ok"]
    assert validate_runtime_program(document)["ok"]
    schema, provider = contract.author_item_response_schema(), contract.author_item_provider_response_schema()
    encoded = _encode_nullable_fixture(document, schema)
    assert Draft202012Validator(provider).is_valid(encoded)
    restored = contract.project_provider_author_item_to_local(encoded, response_format={"type": "json_schema", "json_schema": {"schema": provider}})
    assert restored == document
    wire = compile_runtime_program(restored)
    assert validate_runtime_wire(wire)["ok"]
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    expected = CAPABILITY_REGISTRY["configure_spawn"].params["velocity"].projected_fields(velocity, "velocity")
    actual = [row for row in receipts if row.get("callId") == call["id"] and ".params.velocity" in row.get("authoredPath", "")]
    assert len(actual) == len(expected)
    assert component(wire, call)["speedPxPerTick"] == (8.5 if "constantSpeedPxPerUpdate" in velocity else 0)
    for source in (None, document):
        assert audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
    sanitized = deepcopy(wire); sanitized.pop("runtimeContract")
    assert validate_runtime_wire(sanitized)["ok"]


@pytest.mark.parametrize("invalid", [None, {}, 8, "radial", {"constantSpeedPxPerUpdate": 8, "disk": {"maxSpeedPxPerUpdate": 6}},
    {"radial": {}}, {"radial": {"minSpeedPxPerUpdate": 4}}, {"disk": {"maxSpeedPxPerUpdate": 6, "minSpeedPxPerUpdate": 0}},
    {"cone": {"minSpeedPxPerUpdate": 4, "maxSpeedPxPerUpdate": 7}}, {"constantSpeedPxPerUpdate": True},
    {"fanSpeed": {"minSpeedPxPerUpdate": -1, "maxSpeedPxPerUpdate": 8}}, {"radial": {"minSpeedPxPerUpdate": 0, "maxSpeedPxPerUpdate": 81}}])
def test_invalid_velocity_variants_remain_red_without_branch_guessing(invalid):
    document, _ = fixture(invalid)
    assert not strict_author_shape_report(document)["ok"]
    with pytest.raises(ValueError): compile_runtime_program(document)


@pytest.mark.parametrize("branch", ["fanSpeed", "radial", "cone"])
def test_reversed_range_repairs_only_minimum_and_freezes_the_selected_distribution(branch):
    velocity = {branch: {"minSpeedPxPerUpdate": 9, "maxSpeedPxPerUpdate": 7}}
    if branch == "cone": velocity[branch]["halfAngleRadians"] = 0.2
    document, call = fixture(velocity)
    report = validate_runtime_program(document)
    errors = [row for row in report["errors"] if row["code"] == "unordered_param_range"]
    assert len(errors) == 1
    scope = build_runtime_repair_scope(document, report["errors"])
    permission = next(row for row in scope["fieldPermissions"]["calls"] if row["id"] == call["id"])
    assert permission["paths"] == [f"params.velocity.{branch}.minSpeedPxPerUpdate"]
    candidate = deepcopy(call)
    candidate["params"]["velocity"][branch].update(minSpeedPxPerUpdate=4, maxSpeedPxPerUpdate=10)
    candidate["target"] = "item"
    patch, audit = filter_repair_patch_scope(document, {"note": "fix exact minimum", "callsUpsert": [candidate]}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    repaired = apply_repair_patch(document, patch)
    result = next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == call["id"])
    assert result["params"]["velocity"][branch]["minSpeedPxPerUpdate"] == 4
    assert result["params"]["velocity"][branch]["maxSpeedPxPerUpdate"] == 7 and result["target"] == call["target"]
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]


@pytest.mark.parametrize("mutation", ["drop", "duplicate", "wrong-call", "wrong-variant", "wrong-literal", "old-speed", "scalar-swap"])
def test_new_distribution_provenance_requires_one_consistent_variant_and_owner(mutation):
    document, call = fixture(VELOCITIES[2])
    wire = compile_runtime_program(document)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    own = [row for row in receipts if row.get("callId") == call["id"] and ".params.velocity" in row.get("authoredPath", "")]
    minimum = next(row for row in own if row["finalPath"].endswith(".minSpeedPxPerUpdate"))
    if mutation == "drop": receipts.remove(minimum)
    elif mutation == "duplicate": receipts.append(deepcopy(minimum))
    elif mutation == "wrong-call": minimum["callId"] = "unknown_call"
    elif mutation == "wrong-variant": minimum["authoredPath"] = minimum["authoredPath"].replace(".radial.", ".fanSpeed.")
    elif mutation == "wrong-literal":
        next(row for row in own if row["finalPath"].endswith(".kind"))["authoredPath"] += ".minSpeedPxPerUpdate"
    elif mutation == "old-speed":
        speed = next(row for row in own if row["finalPath"].endswith(".speedPxPerTick"))
        speed["authoredPath"] = speed["authoredPath"].split(".params.")[0] + ".params.speedPxPerUpdate"
        speed["status"] = "delivered"
    else:
        maximum = next(row for row in own if row["finalPath"].endswith(".maxSpeedPxPerUpdate"))
        minimum["authoredPath"], maximum["authoredPath"] = maximum["authoredPath"], minimum["authoredPath"]
    for source in (None, document):
        assert not audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("mutation", ["null", "unknown-kind", "missing-max", "extra-min", "extra-field", "nonzero-constant", "reversed", "boolean", "foreign-half-angle"])
def test_new_velocity_wire_is_strict_without_diagnostic_receipts(mutation):
    document, call = fixture(VELOCITIES[2])
    wire = compile_runtime_program(document); wire.pop("runtimeContract")
    spawn = component(wire, call); dist = spawn["velocityDistribution"]
    if mutation == "null": spawn["velocityDistribution"] = None
    elif mutation == "unknown-kind": dist["kind"] = "Radial"
    elif mutation == "missing-max": del dist["maxSpeedPxPerUpdate"]
    elif mutation == "extra-min": dist["kind"] = "disk"
    elif mutation == "extra-field": dist["range"] = 3
    elif mutation == "nonzero-constant": spawn["speedPxPerTick"] = 1
    elif mutation == "reversed": dist["minSpeedPxPerUpdate"] = 8
    elif mutation == "boolean": dist["maxSpeedPxPerUpdate"] = True
    else: dist["halfAngleRadians"] = 0
    assert not validate_runtime_wire(wire)["ok"]


def test_old_full_saved_wire_and_receipts_keep_constant_velocity_without_reconstruction():
    archive = json.loads((Path(__file__).with_name("fixtures") / "parent_combat_retained_wire.json").read_text())
    for case in archive["cases"]:
        wire = case["wire"]; before = deepcopy(wire)
        assert validate_runtime_wire(wire)["ok"]
        assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)["ok"]
        assert wire == before


def test_old_author_scalar_is_not_a_second_accepted_spelling():
    document, call = fixture(VELOCITIES[0])
    call["params"]["speedPxPerUpdate"] = call["params"].pop("velocity")["constantSpeedPxPerUpdate"]
    assert not strict_author_shape_report(document)["ok"]
    with pytest.raises(ValueError): compile_runtime_program(document)


@pytest.mark.parametrize("class_name", ["RuntimeSpawnVelocitySpec", "RuntimeHitTargetSpawnSpec"])
def test_nested_runtime_surface_audit_does_not_hide_new_fields(class_name):
    from infini_local.qa import primitive_loss_audit as audit
    source = (Path(__file__).resolve().parents[2] / "ModSources/InfiniCrafterLocal/Common/Models/RuntimeProgramSpec.cs").read_bytes()
    assert audit.runtime_component_surface_audit(source)["ok"]
    marker = f"public sealed class {class_name}\n{{".encode()
    assert marker in source
    mutant = source.replace(marker, marker + b"\n    public float UndeclaredRuntimeChoice { get; set; }")
    report = audit.runtime_component_surface_audit(mutant)
    assert not report["ok"] and report["unclassifiedByClass"][class_name] == ["UndeclaredRuntimeChoice"]


@pytest.mark.parametrize("kind", ["stationary_projectile", "temporary_helper", "field"])
def test_sampled_velocity_cannot_be_authored_for_a_stationary_kind(kind):
    document, call = fixture(VELOCITIES[2])
    next(row for row in document["runtimeProgram"]["entities"] if row["id"] == call["target"])["kind"] = kind
    report = validate_runtime_program(document)
    assert any(row["code"] == "unsupported_param_variant_target_kind" for row in report["errors"])


@pytest.mark.parametrize("capability", ["charge_then_release", "channel_beam"])
def test_launch_owning_controller_does_not_accept_an_ignored_random_velocity(capability):
    document = build_capability_witness(capability)
    controller = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == capability)
    spawn = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "configure_spawn" and row["target"] == controller["target"])
    spawn["params"].update(velocity=deepcopy(VELOCITIES[2]), spreadRadians=0)
    assert any(row["code"] == "incompatible_param_variant" for row in validate_runtime_program(document)["errors"])


@pytest.mark.parametrize("velocity,leaf,value", [(VELOCITIES[1], "aim", "none"), (VELOCITIES[4], "aim", "none"),
    (VELOCITIES[2], "spreadRadians", 0.4), (VELOCITIES[3], "spreadRadians", 0.4)])
def test_distribution_dependencies_diagnose_the_exact_other_leaf(velocity, leaf, value):
    document, call = fixture(velocity)
    call["params"][leaf] = value
    errors = [row for row in validate_runtime_program(document)["errors"] if row["code"] == "incompatible_param_variant"]
    assert len(errors) == 1 and errors[0]["path"].endswith(".params." + leaf)
    wire = compile_runtime_program(fixture(velocity)[0]); wire.pop("runtimeContract")
    component(wire, call)[leaf] = value
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("velocity", [VELOCITIES[2], VELOCITIES[3]])
def test_event_spread_for_radial_child_is_repaired_without_changing_valid_child(velocity):
    document = build_capability_witness("spawn_entity_on_event")
    event = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "spawn_entity_on_event")
    child = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "configure_spawn" and row["target"] == event["params"]["entity"])
    child["params"].update(velocity=deepcopy(velocity), spreadRadians=0)
    event["params"]["spreadRadians"] = 0
    wire = compile_runtime_program(document); wire.pop("runtimeContract")
    owner = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == event["target"])
    next(row for row in owner["events"] if row["id"] == event["id"])["spreadRadians"] = 0.5
    assert not validate_runtime_wire(wire)["ok"]
    event["params"]["spreadRadians"] = 0.5
    report = validate_runtime_program(document)
    errors = [row for row in report["errors"] if row["code"] == "incompatible_param_variant"]
    assert len(errors) == 1 and errors[0]["path"].endswith(".params.spreadRadians")
    scope = build_runtime_repair_scope(document, report["errors"])
    permission = next(row for row in scope["fieldPermissions"]["calls"] if row["id"] == event["id"])
    assert permission["paths"] == ["params.spreadRadians"]
    candidate = deepcopy(event); candidate["params"].update(spreadRadians=0, count=12)
    changed_child = deepcopy(child); changed_child["params"]["velocity"] = VELOCITIES[0]
    patch, audit = filter_repair_patch_scope(document, {"note": "explicit zero spread", "callsUpsert": [candidate, changed_child]}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    repaired = apply_repair_patch(document, patch)
    assert next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == child["id"]) == child
    assert next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == event["id"])["params"]["count"] == event["params"]["count"]
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]


@pytest.mark.parametrize("velocity", [VELOCITIES[2], VELOCITIES[3]])
@pytest.mark.parametrize("invalid_spread", [False, None, "0", 0.5])
def test_raw_event_spread_for_independent_direction_requires_actual_numeric_zero(velocity, invalid_spread):
    document = build_capability_witness("spawn_entity_on_event")
    event = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "spawn_entity_on_event")
    child = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "configure_spawn" and row["target"] == event["params"]["entity"])
    child["params"].update(velocity=deepcopy(velocity), spreadRadians=0)
    event["params"]["spreadRadians"] = 0
    wire = compile_runtime_program(document); wire.pop("runtimeContract")
    owner = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == event["target"])
    next(row for row in owner["events"] if row["id"] == event["id"])["spreadRadians"] = invalid_spread
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(row["code"] == "incompatible_param_variant" and row["path"].endswith(".spreadRadians") for row in report["errors"])

