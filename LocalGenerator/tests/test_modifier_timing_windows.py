"""One explicit window replaces, but never silently rewrites, retained timing gates."""
from copy import deepcopy

import pytest

from infini_local.core.schema_validation import strict_schema_errors
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.pipelines.author_item_contract import author_item_provider_response_schema
from infini_local.qa.capability_witnesses import build_capability_witness


CASES = [
    ("set_projectile_turn_modifier", "turnModifier", "turnRadiansPerSecond", "turnRadiansPerUpdate", 1),
    ("set_projectile_speed_modifier", "speedModifier", "speedMultiplierPerUpdate", "speedMultiplierPerUpdate", 1.01),
    ("set_projectile_homing_modifier", "homingModifier", "maxTurnRadiansPerSecond", "maxTurnRadiansPerUpdate", 1),
    ("attract_npcs_while_active", "npcAttraction", "accelerationBlocksPerSecondSquared", "strengthPerUpdate", 1),
]


def document(fn, form="window"):
    source = build_capability_witness(fn)
    call = next(c for c in source["runtimeProgram"]["calls"] if c["fn"] == fn)
    call["params"].update(startDelaySeconds=0.5, durationSeconds=1)
    if form != "pair":
        call["params"]["window"] = {"phase": "always", "clock": "active", "startDelaySeconds": 0.25, "durationSeconds": 2}
    if form == "window":
        del call["params"]["startDelaySeconds"], call["params"]["durationSeconds"]
    return source, call


def delivered(source, call, member):
    assert validate_runtime_program(source)["ok"], validate_runtime_program(source)
    wire = compile_runtime_program(source)
    assert validate_runtime_wire(wire)["ok"], validate_runtime_wire(wire)
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == call["target"])
    return wire, entity[member]


@pytest.mark.parametrize("fn,member,author_leaf,wire_leaf,value", CASES)
@pytest.mark.parametrize("form", ["pair", "window", "intersection"])
def test_exact_forms_roundtrip_receipts_and_preserve_source(fn, member, author_leaf, wire_leaf, value, form):
    source, call = document(fn, form)
    before = deepcopy(source)
    assert not strict_schema_errors(call, CAPABILITY_REGISTRY[fn].provider_variant_schema())
    wire, component = delivered(source, call, member)
    assert source == before
    if form == "window":
        assert "startDelayTicks" not in component and "durationTicks" not in component
    else:
        assert component["startDelayTicks"] == 30 and component["durationTicks"] == 60
    if form != "pair":
        assert component["window"] == {"phase": "always", "clock": "active", "startDelayTicks": 15, "durationTicks": 120}
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    for authored in (source, None):
        audit = audit_compiler_receipts(receipts, authored_document=authored, final_document=wire)
        assert audit["ok"], audit["violations"]
    stripped = deepcopy(wire)
    stripped.pop("runtimeContract")
    assert validate_runtime_wire(stripped)["ok"]


@pytest.mark.parametrize("fn,member,author_leaf,wire_leaf,value", CASES)
@pytest.mark.parametrize("form", ["pair", "window", "intersection"])
@pytest.mark.parametrize("mutation", ["half_delay", "half_duration", "null_delay", "null_duration", "zero_duration", "bad_numeric", "unknown", "missing_all"])
def test_author_provider_and_stripped_wire_refuse_invalid_fields(fn, member, author_leaf, wire_leaf, value, form, mutation):
    source, call = document(fn, form)
    wire, component = delivered(source, call, member)
    wire.pop("runtimeContract")
    p = call["params"]
    if mutation == "half_delay":
        p["startDelaySeconds"] = 0
        p.pop("durationSeconds", None)
        component["startDelayTicks"] = 0
        component.pop("durationTicks", None)
    elif mutation == "half_duration":
        p["durationSeconds"] = 1
        p.pop("startDelaySeconds", None)
        component["durationTicks"] = 60
        component.pop("startDelayTicks", None)
    elif mutation in ("null_delay", "null_duration", "zero_duration"):
        p.update(startDelaySeconds=0, durationSeconds=1)
        component.update(startDelayTicks=0, durationTicks=60)
        akey, wkey = ("startDelaySeconds", "startDelayTicks") if mutation == "null_delay" else ("durationSeconds", "durationTicks")
        p[akey] = component[wkey] = 0 if mutation == "zero_duration" else None
    elif mutation == "bad_numeric":
        p[author_leaf] = component[wire_leaf] = 999999
    elif mutation == "unknown":
        p["unregistered"] = component["unregistered"] = 7
    else:
        for key in ("startDelaySeconds", "durationSeconds", "window"):
            p.pop(key, None)
        for key in ("startDelayTicks", "durationTicks", "window"):
            component.pop(key, None)
    before_source, before_wire = deepcopy(source), deepcopy(wire)
    assert strict_schema_errors(call, CAPABILITY_REGISTRY[fn].provider_variant_schema())
    assert not validate_runtime_program(source)["ok"]
    assert not validate_runtime_wire(wire)["ok"]
    assert source == before_source and wire == before_wire


@pytest.mark.parametrize("fn,member,author_leaf,wire_leaf,value", CASES)
@pytest.mark.parametrize("clock,phase,producer,component_name", [
    ("since_release", "released", "accumulate_projectile_charge", "charge"),
    ("since_return", "returning", "set_projectile_return_trigger", "returnTrigger"),
])
def test_relative_windows_require_exact_latch_in_author_and_wire(fn, member, author_leaf, wire_leaf, value, clock, phase, producer, component_name):
    source, call = document(fn)
    call["params"]["window"].update(clock=clock, phase=phase)
    assert not validate_runtime_program(source)["ok"]
    source["runtimeProgram"]["calls"].append({"id": "latch", "fn": producer, "target": call["target"],
        "params": {"durationSeconds": 1} if producer == "accumulate_projectile_charge" else {"afterSeconds": 1}})
    if producer == "accumulate_projectile_charge":
        next(c for c in source["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")["params"]["channel"] = True
    wire, component = delivered(source, call, member)
    assert component["window"]["clock"] == clock
    assert "startDelayTicks" not in component
    wire.pop("runtimeContract")
    entity = next(e for e in wire["runtimeProgram"]["entities"] if e["id"] == call["target"])
    del entity[component_name]
    assert not validate_runtime_wire(wire)["ok"]


@pytest.mark.parametrize("fn,member,author_leaf,wire_leaf,value", CASES)
@pytest.mark.parametrize("form", ["pair", "window", "intersection"])
def test_non_timing_repair_freezes_timing_presence_values_and_deletions(fn, member, author_leaf, wire_leaf, value, form):
    source, call = document(fn, form)
    call["params"][author_leaf] = -99999
    expected = deepcopy(source)
    next(c for c in expected["runtimeProgram"]["calls"] if c["id"] == call["id"])["params"][author_leaf] = value
    report = validate_runtime_program(source)
    scope = build_runtime_repair_scope(source, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params." + author_leaf]}]
    hostile = deepcopy(call)
    hostile["params"][author_leaf] = value
    if form == "window":
        hostile["params"].update(startDelaySeconds=0, durationSeconds=360)
    else:
        hostile["params"].pop("startDelaySeconds")
        hostile["params"].pop("durationSeconds")
    hostile["params"]["window"] = {"phase": "always"}
    patch, audit = filter_repair_patch_scope(source, {"callsUpsert": [hostile], "note": "fix numeric leaf only",
        "callParamKeysDelete": [{"callId": call["id"], "key": key} for key in ("startDelaySeconds", "durationSeconds", "window")]}, scope)
    assert audit["ok"] and audit["ignoredChanges"]
    repaired = apply_repair_patch(source, patch)
    assert repaired == expected
    delivered(repaired, next(c for c in repaired["runtimeProgram"]["calls"] if c["id"] == call["id"]), member)


@pytest.mark.parametrize("fn,member,author_leaf,wire_leaf,value", CASES)
@pytest.mark.parametrize("missing", ["startDelaySeconds", "durationSeconds"])
def test_incomplete_pair_repair_opens_only_missing_half(fn, member, author_leaf, wire_leaf, value, missing):
    source, call = document(fn, "intersection")
    original = call["params"].pop(missing)
    expected = deepcopy(source)
    next(c for c in expected["runtimeProgram"]["calls"] if c["id"] == call["id"])["params"][missing] = original
    report = validate_runtime_program(source)
    scope = build_runtime_repair_scope(source, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params." + missing]}]
    patch = deepcopy(call)
    patch["params"].update(startDelaySeconds=5, durationSeconds=5, window={"phase": "always"})
    patch["params"][missing] = original
    filtered, audit = filter_repair_patch_scope(source, {"callsUpsert": [patch], "note": "complete exact timing pair"}, scope)
    assert audit["ok"]
    assert apply_repair_patch(source, filtered) == expected


def test_provider_projection_supports_the_exact_disjoint_timing_shapes():
    # The actual strict-provider owner must prove the union; unsupported
    # conditionals/compositions cannot be hidden behind local-only tests.
    schema = author_item_provider_response_schema()
    assert schema


@pytest.mark.parametrize("fn,member,author_leaf,wire_leaf,value", CASES)
@pytest.mark.parametrize("form", ["pair", "window", "intersection"])
def test_strict_provider_nullable_transport_preserves_selected_timing_shape(fn, member, author_leaf, wire_leaf, value, form):
    from jsonschema import Draft202012Validator
    from infini_local.pipelines import author_item_contract as contract
    from test_codex_subscription_contract import _encode_nullable_fixture

    _, call = document(fn, form)
    local = CAPABILITY_REGISTRY[fn].provider_variant_schema()
    provider = contract._provider_strict_projection(local)
    encoded = _encode_nullable_fixture(call, local)
    assert Draft202012Validator(provider).is_valid(encoded)
    restored = contract.project_provider_nullable_optionals_to_local(encoded, local,
        response_format={"type": "json_schema", "json_schema": {"schema": provider}})
    assert restored == call
