"""Actual typed Author/provider/compiler/provenance/Repair tests for initial velocity."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest
from repair_test_helpers import frozen_call_repair, provider_roundtrip, gameplay_repair

from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import filter_repair_patch_scope
from infini_local.core.runtime_authoring.program_schema import strict_author_shape_report
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.pipelines import author_item_contract as contract
from infini_local.qa.capability_witnesses import build_capability_witness


VELOCITIES = [
    {'speed': (8.5) * 60 / 16},
    {"fanSpeed": {'minSpeed': (4.5) * 60 / 16, 'maxSpeed': (8.5) * 60 / 16}},
    {"radial": {'minSpeed': (4) * 60 / 16, 'maxSpeed': (7) * 60 / 16}},
    {"disk": {'maxSpeed': (6) * 60 / 16}},
    {"cone": {'minSpeed': (4) * 60 / 16, 'maxSpeed': (7) * 60 / 16, "halfAngleRadians": 0.2}},
]


def fixture(velocity):
    document = build_capability_witness("spawn")
    call = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "spawn")
    call["params"]["velocity"] = deepcopy(velocity)
    return document, call


def component(wire, call):
    return next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == call["target"])["spawn"]


def child_fixture(velocity):
    document = build_capability_witness("spawn_on_event")
    call = next(row for row in document["runtimeProgram"]["calls"]
                if row["fn"] == "spawn" and row["target"] == "witness_child")
    call["params"].update(velocity=deepcopy(velocity), count=1, spreadRadians=0)
    return document, call


@pytest.mark.parametrize("velocity,omitted", [
    (VELOCITIES[0], ("count",)),
    (VELOCITIES[2], ("spreadRadians",)),
    (VELOCITIES[3], ("count", "spreadRadians")),
])
def test_child_neutral_omissions_preserve_explicit_wire_and_source_receipts(velocity, omitted):
    document, call = child_fixture(velocity)
    explicit = compile_runtime_program(document)
    for name in omitted:
        call["params"].pop(name)
    before = deepcopy(document)
    wire = compile_runtime_program(document)
    assert document == before
    assert {k: wire[k] for k in ("gameplay", "runtimeProgram", "accessory", "armor")} == {
        k: explicit[k] for k in ("gameplay", "runtimeProgram", "accessory", "armor")
    }
    assert component(wire, call)["count"] == 1 and component(wire, call)["spreadRadians"] == 0
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    omitted_rows = [row for row in receipts if row.get("callId") == call["id"]
                    and row["status"] == "declared_neutral_omission"]
    assert {row["authoredPath"].rsplit(".", 1)[-1] for row in omitted_rows} == set(omitted)
    for row in omitted_rows:
        delivered = next(r for r in explicit["runtimeContract"]["finalWireReceipts"] if r["finalPath"] == row["finalPath"])
        assert delivered["status"] == "delivered"
        assert row == {**delivered, "status": "declared_neutral_omission"}
    for source in (None, document):
        assert audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("velocity,omitted", [
    (VELOCITIES[0], ("count",)),
    (VELOCITIES[2], ("spreadRadians",)),
    (VELOCITIES[3], ("count", "spreadRadians")),
])
def test_root_distribution_count_required_and_count_one_spread_is_exact_neutral(velocity, omitted):
    document, call = fixture(velocity)
    for name in omitted:
        call["params"].pop(name)
    if omitted == ("spreadRadians",):
        wire = compile_runtime_program(document)
        assert component(wire, call)["spreadRadians"] == 0
        rows = wire["runtimeContract"]["finalWireReceipts"]
        assert any(r.get("callId") == call["id"] and r["status"] == "declared_neutral_omission"
            and r["authoredPath"].endswith(".params.spreadRadians") for r in rows)
        for source in (None, document):
            assert audit_compiler_receipts(rows, authored_document=source, final_document=wire)["ok"]
        return
    errors = validate_runtime_program(document)["errors"]
    assert {row["path"].rsplit(".", 1)[-1] for row in errors
            if row["code"] == "missing_dependency_param"} == set(omitted)
    if "spreadRadians" in omitted and "speed" not in velocity:
        assert any(row["code"] == "incompatible_param_variant" and row["path"].endswith(".params.spreadRadians")
                   for row in errors)
    with pytest.raises(ValueError):
        compile_runtime_program(document)


@pytest.mark.parametrize("velocity,spread", [
    (VELOCITIES[0], None), (VELOCITIES[2], False), (VELOCITIES[3], "0"),
    (VELOCITIES[0], 0.5), (VELOCITIES[2], 0.5), (VELOCITIES[3], 0.5),
])
def test_child_neutral_omission_does_not_replace_present_spread(velocity, spread):
    document, call = child_fixture(velocity)
    call["params"].pop("count")
    call["params"]["spreadRadians"] = spread
    before = deepcopy(document)
    accepted = "speed" in velocity and spread == 0.5
    report = validate_runtime_program(document)
    assert report["ok"] is accepted
    if "speed" not in velocity and spread is not False:
        assert any(row["code"] == "incompatible_param_variant" and row["path"].endswith(".params.spreadRadians")
                   for row in report["errors"])
    if accepted:
        assert component(compile_runtime_program(document), call)["spreadRadians"] == spread
    else:
        with pytest.raises(ValueError):
            compile_runtime_program(document)
    assert document == before


@pytest.mark.parametrize("changes", [
    {"default": None}, {"default": 1}, {"neutral": False}, {"neutral": 0.0}, {"required": True},
])
def test_child_equality_omission_requires_declared_typed_optional_neutral(monkeypatch, changes):
    import infini_local.core.runtime_authoring.technical_lowering as technical_lowering
    import infini_local.core.runtime_authoring.validator as validator

    document, call = child_fixture(VELOCITIES[2])
    call["params"].pop("spreadRadians")
    cap = CAPABILITY_REGISTRY["spawn"]
    changed = replace(cap, params={**cap.params, "spreadRadians": replace(cap.params["spreadRadians"], **changes)})
    registry = {**CAPABILITY_REGISTRY, cap.name: changed}
    monkeypatch.setattr(validator, "CAPABILITY_REGISTRY", registry)
    monkeypatch.setattr(technical_lowering, "CAPABILITY_REGISTRY", registry)
    errors = validate_runtime_program(document)["errors"]
    assert any(row["code"] == "incompatible_param_variant" and row["path"].endswith(".params.spreadRadians") for row in errors)
    with pytest.raises(ValueError):
        compile_runtime_program(document)


@pytest.mark.parametrize("velocity", [VELOCITIES[2], VELOCITIES[3]], ids=["radial", "disk"])
def test_unrelated_child_repair_keeps_accepted_neutral_omissions_frozen(velocity):
    document, call = child_fixture(velocity)
    call["params"].pop("count")
    call["params"].pop("spreadRadians")
    call["params"]['offsetBlocks'] = (257) / 16
    expected = deepcopy(document)
    next(row for row in expected["runtimeProgram"]["calls"] if row["id"] == call["id"])["params"]['offsetBlocks'] = (19) / 16
    candidate = deepcopy(call)
    candidate["params"].update(offsetBlocks=(19) / 16, count=12, spreadRadians=0, velocity=deepcopy(VELOCITIES[0]))
    repaired, wire = frozen_call_repair(document, [candidate],
        [{"id": call["id"], "paths": ['params.offsetBlocks']}], expected, note="repair offset")
    assert component(wire, call)["offsetPx"] == 19
    assert next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == call["id"])["params"] == {**call["params"], "offsetBlocks": 19 / 16}


@pytest.mark.parametrize("velocity,expected", [
    pytest.param(VELOCITIES[0], None, id="constant"),
    pytest.param(VELOCITIES[1], {"kind": "fan_speed", "minSpeedPxPerUpdate": 4.5, "maxSpeedPxPerUpdate": 8.5}, id="fan"),
    pytest.param(VELOCITIES[2], {"kind": "radial", "minSpeedPxPerUpdate": 4, "maxSpeedPxPerUpdate": 7}, id="radial"),
    pytest.param(VELOCITIES[3], {"kind": "disk", "maxSpeedPxPerUpdate": 6}, id="disk"),
    pytest.param(VELOCITIES[4], {"kind": "cone", "minSpeedPxPerUpdate": 4, "maxSpeedPxPerUpdate": 7, "halfAngleRadians": 0.2}, id="cone"),
])
def test_every_velocity_variant_has_strict_provider_inverse_and_exact_receipts(velocity, expected):
    document, call = fixture(velocity)
    assert strict_author_shape_report(document)["ok"]
    restored = provider_roundtrip(document, {
        "type": "json_schema", "json_schema": {"schema": contract.author_item_provider_response_schema()},
    })
    wire = compile_runtime_program(restored)
    assert validate_runtime_wire(wire)["ok"]
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    projected = CAPABILITY_REGISTRY["spawn"].params["velocity"].projected_fields(velocity, "velocity", updates_per_tick=1)
    actual = [row for row in receipts if row.get("callId") == call["id"] and ".params.velocity" in row.get("authoredPath", "")]
    assert len(actual) == len(projected)
    assert component(wire, call)["speedPxPerTick"] == (8.5 if expected is None else 0)
    assert component(wire, call).get("velocityDistribution") == expected
    for source in (None, document):
        assert audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
    sanitized = deepcopy(wire); sanitized.pop("runtimeContract")
    assert validate_runtime_wire(sanitized)["ok"]


@pytest.mark.parametrize("invalid", [None, {}, 8, "radial", {"speed": 8, "disk": {"maxSpeed": 6}},
    {"radial": {}}, {"radial": {"minSpeed": 4}}, {"disk": {"maxSpeed": 6, "minSpeed": 0}},
    {"cone": {"minSpeed": 4, "maxSpeed": 7}}, {"speed": True},
    {"fanSpeed": {"minSpeed": -1, "maxSpeed": 8}}, {"radial": {"minSpeed": 0, "maxSpeed": 1801}}])
def test_invalid_velocity_variants_remain_red_without_branch_guessing(invalid):
    document, _ = fixture(invalid)
    assert not strict_author_shape_report(document)["ok"]
    with pytest.raises(ValueError): compile_runtime_program(document)


@pytest.mark.parametrize("branch", ["fanSpeed", "radial", "cone"])
def test_reversed_range_repairs_only_minimum_and_freezes_the_selected_distribution(branch):
    velocity = {branch: {"minSpeed": 33.75, "maxSpeed": 26.25}}
    if branch == "cone": velocity[branch]["halfAngleRadians"] = 0.2
    document, call = fixture(velocity)
    errors = validate_runtime_program(document)["errors"]
    assert len([row for row in errors if row["code"] == "unordered_param_range"]) == 1
    expected = deepcopy(document)
    next(row for row in expected["runtimeProgram"]["calls"] if row["id"] == call["id"])["params"]["velocity"][branch]['minSpeed'] = (4) * 60 / 16
    candidate = deepcopy(call)
    candidate["params"]["velocity"][branch].update(minSpeed=(4) * 60 / 16, maxSpeed=(10) * 60 / 16)
    candidate["target"] = "item"
    repaired, final = frozen_call_repair(document, [candidate],
        [{"id": call["id"], "paths": [f"params.velocity.{branch}.minSpeed"]}], expected,
        note="fix exact minimum")
    assert component(final, call)["velocityDistribution"]["minSpeedPxPerUpdate"] == 4
    assert component(final, call)["velocityDistribution"]["maxSpeedPxPerUpdate"] == 7


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
        next(row for row in own if row["finalPath"].endswith(".kind"))["authoredPath"] += ".minSpeed"
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


def test_old_author_scalar_is_not_a_second_accepted_spelling():
    document, call = fixture(VELOCITIES[0])
    call["params"]["speedPxPerUpdate"] = call["params"].pop("velocity")['speed']
    assert not strict_author_shape_report(document)["ok"]
    with pytest.raises(ValueError): compile_runtime_program(document)


@pytest.mark.parametrize("kind", ["stationary_projectile", "temporary_helper", "field"])
def test_sampled_velocity_cannot_be_authored_for_a_stationary_kind(kind):
    document, call = fixture(VELOCITIES[2])
    next(row for row in document["runtimeProgram"]["entities"] if row["id"] == call["target"])["kind"] = kind
    report = validate_runtime_program(document)
    assert any(row["code"] == "unsupported_param_variant_target_kind" for row in report["errors"])


@pytest.mark.parametrize("capability", ["charge", "beam_geometry"])
def test_independent_charge_release_and_beam_geometry_keep_initial_sampled_flight(capability):
    document = build_capability_witness(capability)
    controller = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == capability)
    if capability == "charge":
        controller["params"]["releaseEffect"] = {"launchSpeed": 30}
    spawn = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "spawn" and row["target"] == controller["target"])
    spawn["params"].update(velocity=deepcopy(VELOCITIES[2]), spreadRadians=0)
    before = deepcopy(document)
    wire = compile_runtime_program(document)
    assert document == before
    assert component(wire, spawn)["velocityDistribution"] == {
        "kind": "radial", "minSpeedPxPerUpdate": 4, "maxSpeedPxPerUpdate": 7}
    assert validate_runtime_wire(wire)["ok"]
    rows = wire["runtimeContract"]["finalWireReceipts"]
    for source in (None, document):
        assert audit_compiler_receipts(rows, authored_document=source, final_document=wire)["ok"]
    wire.pop("runtimeContract")
    assert validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("driver,code,params", [
    ("charge_then_release", 2, {"chargeTicks": 30, "chargeDamageMultiplier": 2,
        "knockbackMultiplier": 1, "speedMultiplier": 1}),
    ("channel_beam", 1, {"rangeTiles": 20, "widthPx": 8, "warmupTicks": 0}),
])
def test_explicit_synthetic_saved_position_controller_refuses_ignored_sampled_launch(driver, code, params):
    # Synthetic *persisted wire*, not a current Author compilation of a retired Fn.
    document, spawn = fixture(VELOCITIES[0])
    next(c for c in document["runtimeProgram"]["calls"] if c["fn"] == "item_use")["params"]["channel"] = True
    wire = compile_runtime_program(document)
    wire.pop("runtimeContract")
    target = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == spawn["target"])
    target["kind"] = "owner_attached_projectile"
    target["controller"] = {"name": driver, "code": code, "params": params}
    before = deepcopy(wire)
    assert validate_runtime_wire(wire)["ok"]
    assert wire == before
    target["spawn"]["speedPxPerTick"] = 0
    target["spawn"]["velocityDistribution"] = {"kind": "radial", "minSpeedPxPerUpdate": 4, "maxSpeedPxPerUpdate": 7}
    assert not validate_runtime_wire(wire)["ok"]


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
@pytest.mark.parametrize("omit_child_neutrals", [False, True])
def test_event_spread_for_radial_child_is_repaired_without_changing_valid_child(velocity, omit_child_neutrals):
    document = build_capability_witness("spawn_on_event")
    event = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "spawn_on_event")
    child = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "spawn" and row["target"] == event["params"]["entity"])
    child["params"].update(velocity=deepcopy(velocity), spreadRadians=0)
    if omit_child_neutrals:
        child["params"].pop("count")
        child["params"].pop("spreadRadians")
    event["params"]["spreadRadians"] = 0
    wire = compile_runtime_program(document); wire.pop("runtimeContract")
    owner = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == event["target"])
    next(row for row in owner["events"] if row["id"] == event["id"])["spreadRadians"] = 0.5
    assert not validate_runtime_wire(wire)["ok"]
    event["params"]["spreadRadians"] = 0.5
    report = validate_runtime_program(document)
    errors = [row for row in report["errors"] if row["code"] == "incompatible_param_variant"]
    assert len(errors) == 1 and errors[0]["path"].endswith(".params.spreadRadians")
    expected = deepcopy(document)
    next(row for row in expected["runtimeProgram"]["calls"] if row["id"] == event["id"])["params"]["spreadRadians"] = 0
    candidate = deepcopy(event); candidate["params"].update(spreadRadians=0, count=12)
    changed_child = deepcopy(child); changed_child["params"]["velocity"] = VELOCITIES[0]
    repaired, final = frozen_call_repair(document, [candidate, changed_child],
        [{"id": event["id"], "paths": ["params.spreadRadians"]}], expected, note="explicit zero spread")
    assert next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == child["id"]) == child
    assert next(row for row in repaired["runtimeProgram"]["calls"] if row["id"] == event["id"])["params"]["count"] == event["params"]["count"]
    final_event = next(row for entity in final["runtimeProgram"]["entities"] for row in entity["events"] if row["id"] == event["id"])
    assert final_event["spreadRadians"] == 0


@pytest.mark.parametrize("velocity", [VELOCITIES[2], VELOCITIES[3]])
@pytest.mark.parametrize("invalid_spread", [False, None, "0", 0.5])
def test_raw_event_spread_for_independent_direction_requires_actual_numeric_zero(velocity, invalid_spread):
    document = build_capability_witness("spawn_on_event")
    event = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "spawn_on_event")
    child = next(row for row in document["runtimeProgram"]["calls"] if row["fn"] == "spawn" and row["target"] == event["params"]["entity"])
    child["params"].update(velocity=deepcopy(velocity), spreadRadians=0)
    event["params"]["spreadRadians"] = 0
    wire = compile_runtime_program(document); wire.pop("runtimeContract")
    owner = next(row for row in wire["runtimeProgram"]["entities"] if row["id"] == event["target"])
    next(row for row in owner["events"] if row["id"] == event["id"])["spreadRadians"] = invalid_spread
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(row["code"] == "incompatible_param_variant" and row["path"].endswith(".spreadRadians") for row in report["errors"])


@pytest.mark.parametrize("format_mode,capability,velocity", [
    ("json_object", "target_and_fire", VELOCITIES[1]),
    ("json_schema", "target_and_fire", VELOCITIES[2]),
    ("json_object", "target_and_fire", VELOCITIES[3]),
    ("json_schema", "target_and_fire", VELOCITIES[4]),
])
def test_explicit_invalid_velocity_variant_replacement_retires_old_branch(monkeypatch, format_mode, capability, velocity):
    doc = build_capability_witness(capability)
    controller = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == capability)
    call = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "spawn" and row["target"] == controller["target"])
    call["params"].update(velocity=deepcopy(velocity), spreadRadians=0)
    before = json.dumps(doc, sort_keys=True)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    permission = next(row for row in scope["fieldPermissions"]["calls"] if row["id"] == call["id"])
    assert permission["paths"] == ["params.velocity"]
    candidate = deepcopy(call)
    candidate["params"]["velocity"] = {'speed': (6) * 60 / 16}
    expected = apply_repair_patch(doc, {"note": "model selects full replacement", "callsUpsert": [candidate]})
    assert validate_runtime_program(expected)["ok"]
    candidate["target"] = "item"
    candidate["params"]["count"] = 12
    hostile = deepcopy(next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "item_stats"))
    hostile["params"]["damage"] = 999
    patch = {"note": "explicit constant replacement", "realizationReplacement": doc["realization"],
             "callsUpsert": [candidate, hostile]}
    repaired, dossier = gameplay_repair(monkeypatch, doc, patch, format_mode, out_of_scope_response=True)
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == scope["fieldPermissions"]["calls"]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
    assert json.dumps(doc, sort_keys=True) == before


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("case", ["noop", "omitted", "unchanged"])
def test_velocity_replacement_requires_an_explicit_new_variant(monkeypatch, format_mode, case):
    from infini_local.core.errors import PlannerUnavailable

    doc = build_capability_witness("target_and_fire")
    call = next(row for row in doc["runtimeProgram"]["calls"] if row["fn"] == "spawn")
    call["params"].update(velocity=deepcopy(VELOCITIES[2]), spreadRadians=0)
    before = deepcopy(doc)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    candidate = deepcopy(call)
    if case == "omitted":
        candidate["params"].pop("velocity")
    incoming = {"note": "no new variant selected", "realizationReplacement": doc["realization"]}
    if case != "noop":
        incoming["callsUpsert"] = [candidate]
        filtered, _ = filter_repair_patch_scope(doc, incoming, scope)
        assert apply_repair_patch(doc, filtered)["runtimeProgram"] == doc["runtimeProgram"]
    with pytest.raises(PlannerUnavailable):
        gameplay_repair(monkeypatch, doc, incoming, format_mode)
    assert doc == before
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
def test_velocity_leaf_permission_does_not_thaw_other_variant_leaves(monkeypatch, format_mode):
    doc, call = fixture({"cone": {"minSpeed": 33.75, "maxSpeed": 26.25, "halfAngleRadians": 0.2}})
    candidate = deepcopy(call)
    candidate["params"]["velocity"]["cone"]['minSpeed'] = (4) * 60 / 16
    expected = apply_repair_patch(doc, {"note": "exact minimum only", "callsUpsert": [candidate]})
    candidate["params"]["velocity"]["cone"].update(maxSpeed=(10) * 60 / 16, halfAngleRadians=0.4)
    repaired, dossier = gameplay_repair(monkeypatch, doc,
        {"note": "exact min with hostile siblings", "realizationReplacement": doc["realization"], "callsUpsert": [candidate]}, format_mode)
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ['params.velocity.cone.minSpeed']}]
    assert repaired["debug"]["gameplayRepairFilterAudit"]["ignoredChanges"]
    repaired.pop("debug")
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert validate_runtime_wire(compile_runtime_program(repaired))["ok"]
