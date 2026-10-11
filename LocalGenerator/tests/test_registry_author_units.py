"""Author units -> compiler receipts -> frozen C# wire: no aliases or quantization."""

from infini_local.core.runtime_authoring.capability_registry import OmissionCondition, RUNTIME_PROGRAM_SCHEMA, visible_capabilities
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
import re
import runpy
import struct
from pathlib import Path

import pytest
from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY,
    apply_repair_patch,
    filter_repair_patch_scope,
    compile_runtime_program,
    validate_runtime_program,
    validate_runtime_wire,
    build_runtime_repair_scope,
    capability_provider_union,
    compact_capability_catalog,
)
from infini_local.core.runtime_authoring import technical_lowering
from infini_local.core.runtime_authoring.program_schema import (
    author_item_repair_schema, strict_author_shape_report,
    strict_repair_shape_report, strict_repair_structure_report,
)
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request

FN = "apply_generated_buff_on_use"

RENAMES = (
    ("move_gravity_arc", "gravityPerTick", "accelY", 0.1875, "movement.params"),
    ("move_orbit", "rangeTiles", "radiusTiles", 7.125, "movement.params"),
    ("move_yoyo_hover", "returnSpeed", "speed", 7.125, "movement.params"),
    ("configure_tool", "miningSpeedScale", "miningSpeedMultiplier", 1.125, "gameplay"),
    ("move_spiral", "turnRadiansPerTick", "turnRadiansPerUpdate", -0.1875, "movement.params"),
    ("move_expanding_wave", "scalePerTick", "scaleGrowthPerUpdate", 0.1875, "movement.params"),
    ("move_accelerate", "acceleration", "speedMultiplierPerUpdate", 1.125, "movement.params"),
    ("move_sine_homing", "waveAmplitude", "waveVelocityCoefficient", 7.125, "movement.params"),
    ("configure_vanilla_ammo_item", "shootSpeedPxPerTick", "shootSpeedContributionPxPerUpdate", 7.125, "gameplay"),
    ("restore_resources_on_use", "potionSickness", "usesPotionRules", True, "gameplay"),
    ("apply_generated_buff_on_use", "jumpBoost", "jumpSpeedBonusPxPerTick", 0.1875, "generatedBuff"),
    ("apply_generated_buff_on_use", "manaRegen", "manaRegenBonusPoints", 7, "generatedBuff"),
)


def _get(document, path):
    value = document
    for part in re.findall(r"[A-Za-z][A-Za-z0-9_]*|\[\d+\]", path):
        value = value[int(part[1:-1])] if part.startswith("[") else value[part]
    return value


@pytest.fixture(scope="module")
def author_cards():
    _, user, _ = build_initial_author_request({}, {}, {}, {}, "unit-proof", model_name="test-model")
    cards = {c["fn"]: c for c in json.loads(user)["runtimeCapabilityContract"]["catalog"]["capabilities"]}
    assert set(cards) == {cap.name for cap in visible_capabilities()}
    return cards


@pytest.mark.parametrize("fn,old,new,value,component", [pytest.param(*row, id=f"{row[0]}-{row[2]}") for row in RENAMES])
def test_identity_rename_reaches_packet_projector_and_frozen_wire(author_cards, fn, old, new, value, component):
    cap, spec = CAPABILITY_REGISTRY[fn], CAPABILITY_REGISTRY[fn].params[new]
    assert old not in cap.params and old not in author_cards[fn]["params"] and new in author_cards[fn]["params"]
    assert spec.wire_name and any(path.endswith("." + spec.wire_name) for path in cap.final_wire_paths)
    for boundary in (spec.minimum, spec.maximum, spec.neutral):
        if boundary is not None:
            assert _bytes(spec.to_wire(boundary)) == _bytes(boundary)
    authored = build_capability_witness(fn)
    index, call = next((i, c) for i, c in enumerate(authored["runtimeProgram"]["calls"]) if c["id"] == "witness_call")
    call["params"][new] = value
    wire = assert_delivered(authored, index, new, value)
    rows = [r for r in wire["runtimeContract"]["finalWireReceipts"]
            if r.get("callId") == "witness_call" and r.get("authoredPath", "").endswith(".params." + new)]
    assert all(r["finalPath"].endswith("." + spec.wire_name) for r in rows)
    alias = deepcopy(authored)
    alias_call = alias["runtimeProgram"]["calls"][index]
    alias_call["params"][old] = alias_call["params"].pop(new)
    assert not validate_runtime_program(alias)["ok"]
    if component in {"spawn", "collision", "movement.params", "itemUse"}:
        row = next(r for r in rows if r["finalPath"].startswith("runtimeProgram."))
        prefix, _, wire_key = row["finalPath"].rpartition(".")
        container = _get(wire, prefix)
        container[new] = container.pop(wire_key)
        assert any(e["code"] == "unknown_final_wire_field" and e["path"].endswith("." + new)
                   for e in validate_runtime_wire(wire)["errors"])


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _stat_spec(fn, param):
    spec = CAPABILITY_REGISTRY[fn].params[param.split(".")[0]]
    for part in param.split(".")[1:]:
        spec = spec.properties[part]
    return spec


def _set_stat(params, path, value):
    parts = path.split(".")
    for part in parts[:-1]:
        params = params.setdefault(part, {})
    params[parts[-1]] = value


def _parameter_leaves(params, prefix=""):
    for name, spec in params.items():
        if spec.properties:
            yield from _parameter_leaves(spec.properties, prefix + name + ".")
        else:
            yield prefix + name, spec


PERCENT_PARAMS = tuple((fn, name, spec) for fn, cap in CAPABILITY_REGISTRY.items()
                       for name, spec in _parameter_leaves(cap.params) if spec.wire_divisor == 100)


# Independent historical units: extrema, zero, first step and off-lattice refusals.
# No closed-domain enumeration: the shared projector's two arithmetic branches
# are checked below, while these rows check every distinct compiler destination.
DISCRETE_UNITS = (
    ("configure_tool", "axePowerTooltipPercent", "axePower", "gameplay.axePower", 0, 500, 5, 5, 1),
    (FN, "lifeRegenHpPerSecond", "lifeRegen", "gameplay.generatedBuff.lifeRegen", 0, 60, .5, 1, 2),
    (FN, "manaRegenBonusPoints", "manaRegen", "gameplay.generatedBuff.manaRegen", 0, 120, 1, 1, 1),
    ("configure_accessory", "lifeRegenHpPerSecond", "lifeRegenHalfHpPerSecond", "accessory.lifeRegen", -50, 100, .5, 1, 2),
    ("configure_armor", "lifeRegenHpPerSecond", "lifeRegenHalfHpPerSecond", "armor.lifeRegen", -50, 100, .5, 1, 2),
    ("configure_armor", "setBonuses.lifeRegenHpPerSecond", "setBonusLifeRegenHalfHpPerSecond", "armor.setBonusLifeRegen", -50, 100, .5, 1, 2),
)


@pytest.mark.parametrize("unit,value,accepted", [
    pytest.param(row, value, accepted, id=f"{row[0]}-{row[1]}-{label}")
    for row in DISCRETE_UNITS
    for label, value, accepted in (
        ("minimum", row[4], True), ("maximum", row[5], True), ("zero", 0, True),
        ("first-step", row[6], True), ("below-minimum", row[4] - row[6], False),
        ("above-maximum", row[5] + row[6], False), ("off-step", row[6] / 2, False))
])
def test_discrete_units_pin_schema_lattice_and_every_wire_destination(unit, value, accepted):
    fn, param, old, path, low, high, step, divisor, multiplier = unit
    spec = _stat_spec(fn, param)
    assert (spec.minimum, spec.maximum, spec.wire_divisor, spec.wire_multiplier) == (low, high, divisor, multiplier)
    assert spec.multiple_of == (None if param == "manaRegenBonusPoints" else step)
    schema = next(s["properties"]["params"] for s in capability_provider_union() if s["properties"]["fn"]["const"] == fn)
    assert old not in schema["properties"]
    for part in param.split(".")[:-1]:
        schema = schema["properties"][part]
    leaf = param.rsplit(".", 1)[-1]
    assert schema["properties"][leaf] == spec.schema()
    assert (leaf in schema["required"]) is spec.required
    assert param.split(".")[0] in next(c["params"] for c in compact_capability_catalog() if c["fn"] == fn)
    doc = build_capability_witness(fn)
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    if fn == FN:
        call["params"]["oreSenseEnabled"] = True
    _set_stat(call["params"], param, value)
    if not accepted:
        assert not validate_runtime_program(doc)["ok"]
        with pytest.raises(ValueError, match="runtime program rejected"):
            compile_runtime_program(doc)
        return
    expected = int(value * multiplier / divisor)
    assert type(spec.to_wire(value)) is int and spec.to_wire(value) == expected
    assert spec.to_wire(value) * divisor / multiplier == value
    wire = compile_runtime_program(doc)
    assert type(_get(wire, path)) is int and _get(wire, path) == expected
    rows = wire["runtimeContract"]["finalWireReceipts"]
    assert any(r.get("authoredPath", "").endswith(".params." + param)
               and r["finalPath"] == path and type(r["value"]) is int and r["value"] == expected for r in rows)
    assert audit_compiler_receipts(rows, authored_document=doc, final_document=wire)["ok"]
    assert validate_runtime_wire(wire)["ok"]
    _set_stat(call["params"], param, 0)
    call["params"][old] = 2
    assert not validate_runtime_program(doc)["ok"]


@pytest.mark.parametrize("fn,param,value,expected", [
    pytest.param("configure_tool", "axePowerTooltipPercent", 35, 7, id="integer-division"),
    pytest.param(FN, "lifeRegenHpPerSecond", 3.5, 7, id="fractional-multiplication"),
    pytest.param("configure_accessory", "lifeRegenHpPerSecond", -3.5, -7, id="signed-multiplication"),
    pytest.param(FN, "manaRegenBonusPoints", 7, 7, id="integer-identity"),
    pytest.param("configure_tool", "axePowerTooltipPercent", 1, None, id="nonintegral-division"),
    pytest.param(FN, "lifeRegenHpPerSecond", .25, None, id="nonintegral-multiplication"),
])
def test_shared_discrete_projector_preserves_integer_output_or_refuses_fraction(fn, param, value, expected):
    spec = _stat_spec(fn, param)
    if expected is None:
        with pytest.raises(ValueError, match="non-integral wire projection"):
            spec.to_wire(value)
    else:
        assert type(spec.to_wire(value)) is int and spec.to_wire(value) == expected


def percent_document(fn, name, value, *, companion=True):
    doc = build_capability_witness(fn)
    index, call = next((i, row) for i, row in enumerate(doc["runtimeProgram"]["calls"]) if row["id"] == "witness_call")
    if isinstance(companion, str):
        params = call["params"]
        params.update({key: spec.neutral for key, spec in CAPABILITY_REGISTRY[FN].params.items() if spec.neutral is not None})
        if companion == "ore":
            params["oreSenseEnabled"] = True
        elif companion == "healing":
            doc["runtimeProgram"]["calls"].append({"id": "healing", "fn": "restore_resources_on_use",
                "params": {"healLife": 1, "healMana": 0, "usesPotionRules": False}})
    elif not companion:
        call["params"].pop("defensePoints", None)
        if fn == FN:
            call["params"]["lightStrength"] = 0
    _set_stat(call["params"], name, value)
    return doc, index, call


def assert_delivered(doc, index, name, expected):
    before = _bytes(doc)
    wire = compile_runtime_program(doc)  # Compiler invokes canonical Author validation.
    rows = wire["runtimeContract"]["finalWireReceipts"]
    selected = [r for r in rows if r.get("authoredPath") == f"runtimeProgram.calls[{index}].params.{name}"]
    assert selected
    for row in selected:
        assert row["status"] == "delivered"
        assert _bytes(row["value"]) == _bytes(_get(wire, row["finalPath"])) == _bytes(expected)
    serialized = json.loads(_bytes(wire))
    assert validate_runtime_wire(serialized)["ok"]
    assert audit_compiler_receipts(rows, final_document=wire)["ok"]
    assert audit_compiler_receipts(serialized["runtimeContract"]["finalWireReceipts"],
                                   authored_document=json.loads(before), final_document=serialized)["ok"]
    assert _bytes(doc) == before
    return wire


# Every field gets its own signed/bounded destination controls; numeric shapes
# belong to the common ParamSpec owner, not leaf x shape Cartesian products.
PERCENT_WIRING = [pytest.param(fn, name, spec, value, True, True, id=f"{fn}-{name}-{label}")
                  for fn, name, spec in PERCENT_PARAMS
                  for label, value in (("minimum", spec.minimum), ("maximum", spec.maximum), ("decimal", 15.125))]
PERCENT_SHAPES = [
    pytest.param(value, accepted, id=label) for label, value, accepted in (
        ("int-zero", 0, True), ("float-zero", 0.0, True), ("signed-zero", -0.0, True),
        ("decimal", .007, True), ("adjacent-decimal", .007000000000000001, True),
        ("tenth", .1, True), ("integer", 15, True), ("integer-float", 15.0, True),
        ("negative-decimal", -.007, True), ("negative-tenth", -.1, True),
        ("positive-subnormal", 100 * 2**-149, True), ("negative-subnormal", -100 * 2**-149, True),
        ("tiny-nonzero", 1e-40, True), ("negative-tiny-nonzero", -1e-40, True),
        ("division-collapse", 5e-324, False), ("negative-division-collapse", -5e-324, False),
        ("storage-collapse", 1e-50, False), ("negative-storage-collapse", -1e-50, False),
        ("percent-not-wire-subnormal", 2**-149, False),
        ("half-below", math.nextafter(100 * 2**-150, 0), False),
        ("half-tie", 100 * 2**-150, False),
        ("half-above", math.nextafter(100 * 2**-150, math.inf), True),
        ("negative-half-below", -math.nextafter(100 * 2**-150, 0), False),
        ("negative-half-tie", -100 * 2**-150, False),
        ("negative-half-above", -math.nextafter(100 * 2**-150, math.inf), True),
    )]


IDENTITY_CONSUMER_CASES = [
    pytest.param(name, value, accepted, "sole", id=f"{name}-{label}")
    for name, value, accepted, label in (
        ("miningSpeedMultiplier", 1.000000001, False, "above-neutral-collapse"),
        ("miningSpeedMultiplier", .999999999, False, "below-neutral-collapse"),
        ("miningSpeedMultiplier", 1.0005, True, "above-neutral"),
        ("miningSpeedMultiplier", .9995, True, "below-neutral"),
        ("miningSpeedMultiplier", 1 + 2**-23, True, "above-step"),
        ("miningSpeedMultiplier", 1 - 2**-24, True, "below-step"),
        ("miningSpeedMultiplier", 1 + 2**-24, False, "above-half-tie"),
        ("miningSpeedMultiplier", 1 - 2**-25, False, "below-half-tie"),
        ("jumpSpeedBonusPxPerTick", 1e-50, False, "collapse"),
        ("jumpSpeedBonusPxPerTick", .0005, True, "small-effect"),
        ("lightStrength", 1e-50, False, "collapse"),
        ("lightStrength", .0005, True, "small-effect"))
] + [pytest.param("miningSpeedMultiplier", 1.000000001, False, companion, id="valid-" + companion + "-does-not-short-circuit")
     for companion in ("ore", "healing")]


@pytest.mark.parametrize("fn,name,spec,value,accepted,companion", PERCENT_WIRING + [
    pytest.param(FN, "moveSpeedBonusPercent", CAPABILITY_REGISTRY[FN].params["moveSpeedBonusPercent"],
                 *case.values, True, id="shared-" + case.id) for case in PERCENT_SHAPES
] + [pytest.param(FN, case.values[0], CAPABILITY_REGISTRY[FN].params[case.values[0]],
                 *case.values[1:], id=case.id) for case in IDENTITY_CONSUMER_CASES])
def test_numeric_admission_projects_exact_bytes_and_checks_both_consumer_boundaries(fn, name, spec, value, accepted, companion):
    doc, index, _ = percent_document(fn, name, value, companion=companion)
    before = _bytes(doc)
    report = validate_runtime_program(doc)
    assert report["ok"] is accepted, report
    if accepted:
        expected = value / 100 if spec.wire_divisor == 100 else value
        assert_delivered(doc, index, name, expected)
        if spec.wire_divisor == 100 and value != 0:
            assert struct.unpack("!f", struct.pack("!f", value / 100))[0] != 0
    else:
        assert [(e["code"], e["path"]) for e in validate_runtime_program(doc)["errors"]] == [
            ("consumer_representability", f"$.runtimeProgram.calls[{index}].params.{name}")]
        with pytest.raises(ValueError, match="runtime program rejected"):
            compile_runtime_program(doc)
    assert _bytes(doc) == before


@pytest.mark.parametrize("fn,name,bad", [
    pytest.param(fn, name, case.values[0], id=f"{fn}-{name}-{case.id}")
    for fn, name in (("configure_accessory", "moveSpeedBonusPercent"),
                     ("configure_armor", "setBonuses.moveSpeedBonusPercent"),
                     ("add_equipment_damage_bonus", "bonusPercent"), (FN, "moveSpeedBonusPercent"))
    for case in (
        pytest.param(None, id="null"), pytest.param(True, id="bool"), pytest.param("1e-50", id="string"),
        pytest.param([], id="array"), pytest.param({}, id="object"), pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="infinity"), pytest.param(-float("inf"), id="negative-infinity"),
        pytest.param(10**1000, id="huge-integer"))])
def test_percent_shape_owner_refuses_malformed_present_numbers_without_mutation(fn, name, bad):
    doc, _, _ = percent_document(fn, name, bad)
    before = json.dumps(doc, ensure_ascii=False)
    assert not validate_runtime_program(doc)["ok"]
    with pytest.raises(ValueError, match="runtime program rejected"):
        compile_runtime_program(doc)
    assert json.dumps(doc, ensure_ascii=False) == before


@pytest.mark.parametrize("fn,name,value,replacement", [
    pytest.param(fn, name, 5e-324, 15.125, id=f"{fn}-{name}") for fn, name, _ in PERCENT_PARAMS
] + [pytest.param(FN, "miningSpeedMultiplier", 1.000000001, 1.0005, id="identity-consumer-collapse")])
def test_numeric_collapse_has_exact_repair_authority_and_frozen_siblings(fn, name, value, replacement):
    from infini_local.core.runtime_authoring import VALIDATION_ERROR_CODES, REPAIR_VALIDATION_ERROR_CODES, REPAIR_ERROR_POLICY
    assert "consumer_representability" in VALIDATION_ERROR_CODES & REPAIR_VALIDATION_ERROR_CODES
    assert REPAIR_ERROR_POLICY["consumer_representability"]["llmRepairable"] is True
    doc, index, call = percent_document(fn, name, value)
    if name == "miningSpeedMultiplier":
        call["params"]["oreSenseEnabled"] = True
    before = _bytes(doc)
    report = validate_runtime_program(doc)
    assert [(e["code"], e["path"]) for e in report["errors"]] == [
        ("consumer_representability", f"$.runtimeProgram.calls[{index}].params.{name}")]
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": [f"params.{name}"]}]
    assert scope["fieldPermissions"]["bindings"] == scope["fieldPermissions"]["entities"] == []
    candidate = deepcopy(call)
    _set_stat(candidate["params"], name, replacement)
    sibling, hostile = (("damageClass", "magic") if fn == "add_equipment_damage_bonus" else
                        ("durationTicks", 21600) if fn == FN else ("defensePoints", 77))
    candidate["params"][sibling] = hostile
    unrelated = deepcopy(doc["runtimeProgram"]["calls"][0])
    unrelated["params"]["damage"] = 1999
    filtered, audit = filter_repair_patch_scope(doc, {
        "note": "explicit numeric correction", "realizationReplacement": deepcopy(doc["realization"]),
        "callsUpsert": [candidate, unrelated]}, scope)
    assert audit["ok"] and audit["ignoredChanges"], audit
    fixed = apply_repair_patch(doc, filtered)
    expected = deepcopy(doc)
    _set_stat(expected["runtimeProgram"]["calls"][index]["params"], name, replacement)
    assert _bytes(fixed) == _bytes(expected)
    assert_delivered(fixed, index, name, _stat_spec(fn, name).to_wire(replacement))
    assert _bytes(doc) == before


@pytest.mark.parametrize("fn", ["configure_accessory", "configure_armor", "apply_generated_buff_on_use"])
@pytest.mark.parametrize("value", [5e-324, -1e-50])
def test_sole_percent_effect_is_rejected_without_thawing_valid_call_siblings(fn, value):
    name = "moveSpeedBonusPercent"
    doc, index, call = percent_document(fn, name, value, companion=False)
    report = validate_runtime_program(doc)
    assert [(e["code"], e["path"]) for e in report["errors"]] == [
        ("consumer_representability", f"$.runtimeProgram.calls[{index}].params.{name}")
    ]
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": [f"params.{name}"]}]
    noop, audit = filter_repair_patch_scope(doc, {
        "note": "No implicit numeric rescue", "realizationReplacement": deepcopy(doc["realization"])
    }, scope)
    assert not audit["ok"]
    assert any(e["code"] == "repair_scope_violation" for e in audit["errors"])
    assert not validate_runtime_program(apply_repair_patch(doc, noop))["ok"]
    # Zero alone is inert for an accessory or generated buff; an armor still
    # has its explicit slot/set identity. Neither is precision loss.
    call["params"][name] = -0.0
    neutral_report = validate_runtime_program(doc)
    assert all(e["code"] != "consumer_representability" for e in neutral_report["errors"])
    if fn in {"configure_accessory", "apply_generated_buff_on_use"}:
        assert not neutral_report["ok"]
        assert any(e["code"] == "inert_component" for e in neutral_report["errors"])
    else:
        assert_delivered(doc, index, name, -0.0)

def test_ordinary_binary64_collision_is_not_replaced_by_a_roundtrip_lattice():
    first, second = 0.007, 0.007000000000000001
    assert struct.pack("!d", first) != struct.pack("!d", second)
    assert first / 100 == second / 100
    assert first / 100 * 100 != first  # A proposed equality rule would ban this normal decimal.
    documents = [percent_document("configure_accessory", "moveSpeedBonusPercent", value)[0]
                 for value in (first, second)]
    assert all(validate_runtime_program(doc)["ok"] for doc in documents)
    assert _bytes(compile_runtime_program(documents[0])) == _bytes(compile_runtime_program(documents[1]))

@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_numeric_names_and_constraints_reach_real_author_and_serialized_repair(monkeypatch, mode):
    from infini_local.pipelines import llm_transport as transport
    from test_gameplay_repair_readonly_context import _capture_request
    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", mode)
    request, text, _ = build_initial_author_request({}, {}, {}, {}, "numeric-contract", model_name="offline-test")
    assert request["response_format"]["type"] == mode
    catalog = json.loads(text)["runtimeCapabilityContract"]["catalog"]
    cards = {row["fn"]: row for row in catalog["capabilities"]}
    assert set(cards) == {cap.name for cap in visible_capabilities()}
    schemas = [{row["properties"]["fn"]["const"]: row["properties"]["params"]
                for row in author_item_repair_schema(capability_names=[case["fn"] for case in _SCALAR_NAME_CASES])
                ["properties"]["callsUpsert"]["items"]["oneOf"]}]
    if mode == "json_schema":
        variants = request["response_format"]["json_schema"]["schema"]["properties"]["runtimeProgram"]["properties"]["calls"]["items"]["anyOf"]
        schemas.append({row["properties"]["fn"]["const"]: row["properties"]["params"] for row in variants if "params" in row["properties"]})
    for case in _SCALAR_NAME_CASES:
        fn, old, current = case["fn"], case["oldParameter"], case["canonicalParameter"]
        assert old not in cards[fn]["params"] and current in cards[fn]["params"]
        for group in schemas:
            assert old not in group[fn]["properties"] and current in group[fn]["required"]
        cap = CAPABILITY_REGISTRY[fn]
        assert old not in cap.params and old in cap.retained_receipt_params
        assert cap.params[current].required and cap.params[current].default is None
    assert {fn for fn, _, _ in PERCENT_PARAMS} == {"configure_accessory", "configure_armor", "add_equipment_damage_bonus", FN}
    # One serialized Repair per capability, with every percentage leaf broken;
    # assert the exact registry identities survive together, including nesting.
    for fn in sorted({fn for fn, _, _ in PERCENT_PARAMS}):
        doc = build_capability_witness(fn)
        call = next(c for c in doc["runtimeProgram"]["calls"] if c["id"] == "witness_call")
        leaves = [(name, spec) for owner, name, spec in PERCENT_PARAMS if owner == fn]
        for name, _ in leaves:
            _set_stat(call["params"], name, 5e-324)
        _, dossier = _capture_request(monkeypatch, doc, mode)
        repair_cards = {row["fn"]: row for row in dossier["existingBrokenCapabilityCards"]}
        for name, spec in leaves:
            assert spec.neutral == 0 and spec.consumer_storage == "float32"
            for group in (cards, repair_cards):
                parts = name.split(".")
                row = group[fn]["params"][parts[0]]
                if len(parts) > 1:
                    row = row["shape"]
                    for part in parts[1:]:
                        row = row["properties"][part]
                constraint = row["x-infini-consumerConstraint"] if len(parts) > 1 else row["consumerConstraint"]
                if isinstance(constraint, str):
                    constraint = catalog["fieldGuide"]["consumerConstraints"][constraint]
                assert constraint == spec.schema()["x-infini-consumerConstraint"]
                assert (constraint["storage"], constraint["neutral"], constraint["rule"], constraint["wireProjection"]) == (
                    "float32", 0, "nonneutral_must_remain_nonneutral", {"divisor": 100, "multiplier": 1})
                assert all(text in constraint["meaning"] for text in ("binary64", "round-trip", "No rounding or replacement"))
    for name, spec in CAPABILITY_REGISTRY[FN].params.items():
        if spec.consumer_storage:
            constraint = cards[FN]["params"][name]["consumerConstraint"]
            if isinstance(constraint, str):
                constraint = catalog["fieldGuide"]["consumerConstraints"][constraint]
            assert constraint == spec.schema()["x-infini-consumerConstraint"]
            assert (constraint["storage"], constraint["neutral"], constraint["rule"]) == (
                "float32", spec.neutral, "nonneutral_must_remain_nonneutral")
            assert spec.consumer_value_error(spec.neutral) is None


def test_generated_unit_and_binding_contracts_stay_current():
    root = Path(__file__).resolve().parents[2]
    assert runpy.run_path(str(root / "tools/generate_equipment_bounds.py"))["render"]() == (
        root / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedEquipmentBounds.g.cs").read_text()
    text = runpy.run_path(str(root / "tools/generate_lowery.py"))["render"]()
    assert all(value in text for value in ("exact `binding.action.targetId`", "exact unique item-body identity", "Wire сохраняет `binding.usePolicy`"))
    assert all(value not in text for value in ("exact `binding.usePolicy.action.targetId`", "exact `binding.target`"))


@pytest.mark.parametrize("fn", ["spawn_entity_on_event", "pull_on_event"])
def test_periodic_requires_explicit_period_ticks_and_repair_leaf(fn):
    doc = build_runtime_fixture("workbench_blade")
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "spawn_entity_on_event")
    if fn == "pull_on_event":
        call = {
            "id": "pull_periodic",
            "fn": fn,
            "target": call["target"],
            "params": {
                "when": {},
                "mode": "target_to_entity",
                "strength": 1,
                "radiusTiles": 8,
            },
        }
        doc["runtimeProgram"]["calls"].append(call)
    else:
        call["params"].update(when={})
    params = call["params"]
    params["when"] = {}
    if fn == "spawn_entity_on_event":
        from infini_local.core.runtime_authoring.program_schema import strict_schema_errors
        schema = CAPABILITY_REGISTRY[fn].provider_variant_schema()["properties"]["params"]
        assert next(row for row in schema["properties"]["when"]["oneOf"] if row.get("type") == "object")["required"] == ["everyTicks"]
        missing = {key: value for key, value in params.items() if key != "count"}
        paths = [row["path"] for row in strict_schema_errors(missing, schema) if row["kind"] == "required"]
        assert paths.count("$.count") == paths.count("$.when.everyTicks") == 1
    assert not strict_author_shape_report(doc)["ok"]
    report = validate_runtime_program(doc)
    assert not report["ok"]
    assert any(r["path"].endswith(".params.when.everyTicks") for r in report["errors"])
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params.when.everyTicks"]}]
    assert "everyTicks" in json.dumps(scope)
    with pytest.raises(ValueError):
        compile_runtime_program(doc)
    params["when"] = {"everyTicks": 6}
    assert validate_runtime_program(doc)["ok"], validate_runtime_program(doc)["errors"]
    params["when"] = "on_hit"
    assert validate_runtime_program(doc)["ok"], validate_runtime_program(doc)["errors"]


_SCALAR_NAME_CAPTURE = json.loads((Path(__file__).parent / "fixtures/scalar_author_names_retained_receipts.json").read_text())
_SCALAR_NAME_CASES = _SCALAR_NAME_CAPTURE["cases"]


def _scalar_name_call(document):
    return next(row for row in document["runtimeProgram"]["calls"] if row["id"] == "witness_call")


def _scalar_name_current_source(case):
    source = deepcopy(case["authored"])
    params = _scalar_name_call(source)["params"]
    assert case["canonicalParameter"] not in params
    params[case["canonicalParameter"]] = params.pop(case["oldParameter"])
    return source


def _scalar_name_restored_wire(case):
    wire = compile_runtime_program(_scalar_name_current_source(case))
    receipt = next(row for row in wire["runtimeContract"]["finalWireReceipts"]
                   if row.get("callId") == "witness_call" and row.get("authoredPath", "").endswith(".params." + case["canonicalParameter"]))
    expected = {**case["receipt"], "authoredPath": case["receipt"]["authoredPath"].removesuffix(case["oldParameter"]) + case["canonicalParameter"]}
    assert receipt == expected
    receipt.update(deepcopy(case["receipt"]))  # Restore only this historical receipt; all other bytes remain pinned.
    return wire, receipt


@pytest.mark.parametrize("case", _SCALAR_NAME_CASES, ids=lambda case: case["fn"])
def test_scalar_names_pin_complete_capture_current_provenance_and_exact_repair(case):
    assert _SCALAR_NAME_CAPTURE["originCommit"] == "274d4c38849bff5b8f7ecde1c61d6276a4803712"
    source = _scalar_name_current_source(case)
    wire = compile_runtime_program(source)
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=source, final_document=wire)["ok"]
    retained, receipt = _scalar_name_restored_wire(case)
    assert hashlib.sha256(_bytes(retained)).hexdigest() == case["compiledSha256"]
    assert validate_runtime_wire(retained)["ok"]
    saved = retained["runtimeContract"]["finalWireReceipts"]
    report = audit_compiler_receipts(saved, final_document=retained)
    assert report["ok"] and report["authoredSourceChecked"] is False
    report = audit_compiler_receipts(saved, authored_document=source, final_document=retained)
    assert not report["ok"] and any(row["reason"] == "compiler receipt used an undeclared authored parameter" for row in report["violations"])
    assert not validate_runtime_program(case["authored"])["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(case["authored"])
    # Old name must not become an accepted fresh wire field, even for open gameplay.
    owner, _, old = receipt["finalPath"].rpartition(".")
    parent = _get(retained, owner)
    parent[case["canonicalParameter"]] = parent.pop(old)
    errors = validate_runtime_wire(retained)["errors"]
    if owner.startswith("runtimeProgram."):
        assert any(row["code"] == "unknown_final_wire_field" and row["path"].endswith("." + case["canonicalParameter"]) for row in errors)
    else:
        assert any(row["code"] == "undeclared_technical_lowering" for row in errors)
    broken = deepcopy(source)
    current = case["canonicalParameter"]
    _scalar_name_call(broken)["params"][current] = CAPABILITY_REGISTRY[case["fn"]].params[current].maximum + 1
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    assert next(row["paths"] for row in scope["fieldPermissions"]["calls"] if row["id"] == "witness_call") == ["params." + current]
    stale = {"note": "old spelling is not an alias", "callsUpsert": [deepcopy(_scalar_name_call(case["authored"]))]}
    assert not strict_repair_structure_report(stale)["ok"] and not strict_repair_shape_report(stale)["ok"]
    assert not filter_repair_patch_scope(broken, stale, scope)[1]["ok"]
    with pytest.raises(ValueError):
        apply_repair_patch(broken, stale)
    frozen = deepcopy(next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats"))
    frozen["params"]["damage"] += 1
    filtered, audit = filter_repair_patch_scope(broken, {"note": "exact leaf", "callsUpsert": [deepcopy(_scalar_name_call(source)), frozen]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(broken, filtered)
    assert repaired == source and validate_runtime_program(repaired)["ok"]


@pytest.mark.parametrize("mutation", ["wrong-output", "out-of-domain", "boolean", "omission"])
@pytest.mark.parametrize("case", _SCALAR_NAME_CASES, ids=lambda case: case["fn"])
def test_scalar_name_retained_receipt_cannot_widen_domain_or_forge_projection(case, mutation):
    wire, receipt = _scalar_name_restored_wire(case)
    if mutation == "wrong-output":
        receipt["finalPath"] = "gameplay.damage"
    elif mutation == "omission":
        receipt["status"] = "declared_neutral_omission"
    else:
        owner, _, key = receipt["finalPath"].rpartition(".")
        value = True if mutation == "boolean" else CAPABILITY_REGISTRY[case["fn"]].params[case["canonicalParameter"]].maximum + 1
        _get(wire, owner)[key] = receipt["value"] = value
    report = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)
    assert not report["ok"] and any(row["reason"] == "retained wire provenance has no exact declared prior projection" for row in report["violations"])


BUFF_SPEED_PERCENT = "moveSpeedBonusPercent"
BUFF_SPEED_FACTOR = "moveSpeedBonusFactor"
BUFF_FACTOR_ARCHIVE = json.loads((Path(__file__).with_name("fixtures") / "buff_speed_factor_retained_wire.json").read_text())
BUFF_FACTOR_CASES = BUFF_FACTOR_ARCHIVE["cases"]


def _buff_speed_receipt(wire, name=BUFF_SPEED_FACTOR):
    return next(row for row in wire["runtimeContract"]["finalWireReceipts"]
                if row.get("fn") == FN and row.get("authoredPath", "").endswith(".params." + name))

def _buff_speed_source(scope, value=None):
    document = build_capability_witness(FN)
    call = next(row for row in document["runtimeProgram"]["calls"] if row["id"] == "witness_call")
    if value is None:
        call["params"].pop(BUFF_SPEED_PERCENT)
    else:
        call["params"][BUFF_SPEED_PERCENT] = value
    if scope == "effect_group":
        call["params"]["effectGroupId"] = "swift"
        document["runtimeProgram"]["bindings"][0]["action"]["effectGroupId"] = "swift"
    return document, call

@pytest.mark.parametrize("case", BUFF_FACTOR_CASES, ids=lambda case: case["id"])
def test_buff_capture_keeps_prior_bytes_but_only_current_names_authenticate_fresh_source(case):
    assert BUFF_FACTOR_ARCHIVE["sourceHead"] == "274d4c38849bff5b8f7ecde1c61d6276a4803712"
    prior_wire = case["wire"]
    before = _bytes(prior_wire)
    assert hashlib.sha256(before).hexdigest() == case["wireSha256"]
    rows = prior_wire["runtimeContract"]["finalWireReceipts"]
    report = audit_compiler_receipts(rows, final_document=prior_wire)
    assert report["ok"] and report["authoredSourceChecked"] is False, report
    assert validate_runtime_wire(prior_wire)["ok"]
    prior = _buff_speed_receipt(prior_wire)
    value = case["authoredFactor"]
    if value is None:
        assert prior["status"] == "declared_neutral_omission" and type(prior["value"]) is int and prior["value"] == 0
    else:
        assert prior["status"] == "delivered" and _bytes(prior["value"]) == _bytes(value)
    document, call = _buff_speed_source(case["scope"], None if value is None else value * 100)
    source_before = _bytes(document)
    wire = compile_runtime_program(document)
    actual = _buff_speed_receipt(wire, BUFF_SPEED_PERCENT)
    assert actual["finalPath"] == prior["finalPath"]
    assert struct.pack("!f", actual["value"]) == struct.pack("!f", prior["value"])
    if value is None:
        assert BUFF_SPEED_PERCENT not in call["params"] and actual["status"] == "declared_neutral_omission"
        assert _bytes(actual["value"]) == b"0.0"
    assert validate_runtime_wire(wire)["ok"]
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=document, final_document=wire)["ok"]
    assert not audit_compiler_receipts(rows, authored_document=document, final_document=prior_wire)["ok"]
    assert _bytes(document) == source_before and _bytes(prior_wire) == before


@pytest.mark.parametrize("scope", ["global", "effect_group"])
def test_frozen_percent_absence_survives_duration_repair_and_requires_exact_zero_provenance(scope):
    document, call = _buff_speed_source(scope)
    call["params"]["durationTicks"] = 0
    original = _bytes(document)
    scope_report = build_runtime_repair_scope(document, validate_runtime_program(document)["errors"])
    assert scope_report["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params.durationTicks"]}]
    candidate = deepcopy(call)
    candidate["params"].update(durationTicks=60, moveSpeedBonusPercent=25, miningSpeedMultiplier=2)
    patch, audit = filter_repair_patch_scope(document, {"note": "repair duration", "callsUpsert": [candidate]}, scope_report)
    assert audit["ok"] and audit["ignoredChanges"]
    repaired = apply_repair_patch(document, patch)
    assert _scalar_name_call(repaired)["params"] == {**call["params"], "durationTicks": 60}
    assert _bytes(document) == original
    document = repaired
    source_before = _bytes(document)
    wire = compile_runtime_program(document)
    receipt = _buff_speed_receipt(wire, BUFF_SPEED_PERCENT)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    assert receipt["status"] == "declared_neutral_omission"
    assert _bytes(receipt["value"]) == b"0.0"
    assert audit_compiler_receipts(rows, authored_document=document, final_document=wire)["ok"]
    assert audit_compiler_receipts(rows, final_document=wire)["ok"]
    assert validate_runtime_wire(wire)["ok"]

    # A coherent receipt/output forgery survives JSON reload; equality with
    # zero is insufficient to authenticate the declared +0.0 omission.
    owner, _, key = receipt["finalPath"].rpartition(".")
    _get(wire, owner)[key] = receipt["value"] = -0.0
    wire = json.loads(_bytes(wire))
    before = _bytes(wire)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    for source in (document, None):
        report = audit_compiler_receipts(rows, authored_document=source, final_document=wire)
        assert not report["ok"], report
        assert any(row["reason"] == "omission receipt lacks an exact declared neutral default/projection"
                   and row["finalPath"] == receipt["finalPath"] for row in report["violations"])
    assert not validate_runtime_wire(wire)["ok"]
    assert _bytes(wire) == before
    assert _bytes(document) == source_before

# Wire numeric domain is shared by global and group slots. Distinct slots get
# type/ordinary/subnormal sentinels; the full status/type/sign matrix runs once.
WIRE_VALUES = (
    ("current", "delivered", None, False, "null"),
    ("current", "delivered", False, False, "bool"),
    ("current", "delivered", "0", False, "string"),
    ("current", "delivered", 0, False, "int-zero"),
    ("current", "delivered", 1, False, "int-one"),
    ("current", "delivered", 5e-324, False, "binary64-collapse"),
    ("current", "delivered", 1e-50, False, "positive-storage-collapse"),
    ("current", "delivered", -1e-50, False, "negative-storage-collapse"),
    ("current", "delivered", 0.0, True, "positive-zero"),
    ("current", "delivered", -0.0, True, "negative-zero"),
    ("current", "delivered", -.5, True, "minimum"),
    ("current", "delivered", 2.0, True, "maximum"),
    ("current", "delivered", math.nextafter(-.5, -math.inf), False, "below-minimum"),
    ("current", "delivered", math.nextafter(2.0, math.inf), False, "above-maximum"),
    ("current", "delivered", .007 / 100, True, "decimal-collision"),
    ("current", "delivered", 2**-149, True, "float32-subnormal"),
    ("current", "delivered", math.nextafter(2**-150, math.inf), True, "above-half"),
    *(("prior", status, value, accepted, label) for status in ("delivered", "declared_neutral_omission")
      for value, accepted, label in (
          (None, False, "null"), (False, False, "bool"), ("0", False, "string"),
          (-.6, False, "below-minimum"), (2.1, False, "above-maximum"), (1e-50, False, "collapse"),
          (0, True, "int-zero"), (0.0, status == "delivered", "float-zero"),
          (-0.0, status == "delivered", "signed-zero"), (.2, status == "delivered", "ordinary"))),
    *(('prior', 'delivered', value, True, label) for value, label in (
        (1.770282212988338, "binary64-no-reprojection"),
        (math.nextafter(2**-150, math.inf), "positive-half"),
        (math.nextafter(-2**-150, -math.inf), "negative-half"))),
)


@pytest.mark.parametrize("scope,version,status,value,accepted", [
    pytest.param(scope, version, status, value, accepted, id=f"{scope}-{version}-{status}-{label}")
    for version, status, value, accepted, label in WIRE_VALUES
    for scope in (("global", "effect_group") if label in {"int-zero", "ordinary", "float32-subnormal", "binary64-no-reprojection", "positive-half", "negative-half"} else ("global",))])
def test_buff_wire_domain_authenticates_representation_without_redividing(scope, version, status, value, accepted):
    document, source_before = {}, b""
    if version == "current":
        document, _ = _buff_speed_source(scope, 20)
        source_before = _bytes(document)
        wire = compile_runtime_program(document)
        assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], authored_document=document, final_document=wire)["ok"]
        name, reason = BUFF_SPEED_PERCENT, "scalar receipt is outside its exact declared wire domain"
    else:
        wire = deepcopy(next(case["wire"] for case in BUFF_FACTOR_CASES if case["id"] == scope + "_ordinary"))
        name, reason = BUFF_SPEED_FACTOR, "retained wire provenance has no exact declared prior projection"
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)["ok"]
    assert validate_runtime_wire(wire)["ok"]
    receipt = _buff_speed_receipt(wire, name)
    receipt.update(status=status, value=value)
    owner, _, key = receipt["finalPath"].rpartition(".")
    _get(wire, owner)[key] = value
    wire = json.loads(_bytes(wire))
    before = _bytes(wire)
    report = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)
    assert report["ok"] is accepted, report
    assert validate_runtime_wire(wire)["ok"] is accepted
    if version == "current":
        assert CAPABILITY_REGISTRY[FN].params[name].matches_scalar_projection(value) is accepted
        assert _bytes(document) == source_before
    if not accepted:
        assert any(row["reason"] == reason and row["finalPath"] == receipt["finalPath"] for row in report["violations"])
    elif version == "prior" and status == "delivered":
        bare = deepcopy(wire)
        bare.pop("runtimeContract")
        assert validate_runtime_wire(bare)["ok"]
    assert _bytes(wire) == before


@pytest.mark.parametrize("scope", ["global", "effect_group"])
@pytest.mark.parametrize("old_name", [BUFF_SPEED_FACTOR, "movementSpeed"])
def test_prior_author_names_are_rejected_without_inference_or_source_mutation(scope, old_name):
    document, call = _buff_speed_source(scope)
    call["params"][old_name] = 0.2
    before = _bytes(document)
    report = validate_runtime_program(document)
    assert any(row["code"] == "shape_additional_property" and row["path"].endswith(".params." + old_name)
               for row in report["errors"])
    with pytest.raises(ValueError):
        compile_runtime_program(document)
    old = next(case["wire"] for case in BUFF_FACTOR_CASES if case["id"] == scope + "_ordinary")
    assert not audit_compiler_receipts(old["runtimeContract"]["finalWireReceipts"],
                                       authored_document=document, final_document=old)["ok"]
    assert _bytes(document) == before

@pytest.mark.parametrize("scope", ["global", "effect_group"])
@pytest.mark.parametrize("mutation", ["drop", "duplicate", "current-and-prior", "wrong-slot", "wrong-fn", "wrong-status", "source-list"])
def test_retained_omission_needs_one_exact_prior_source_claim_for_the_wire_slot(scope, mutation):
    wire = deepcopy(next(case["wire"] for case in BUFF_FACTOR_CASES if case["id"] == scope + "_omitted"))
    rows = wire["runtimeContract"]["finalWireReceipts"]
    old = _buff_speed_receipt(wire)
    if mutation == "drop":
        rows.remove(old)
    elif mutation == "duplicate":
        rows.append(deepcopy(old))
    elif mutation == "current-and-prior":
        current = deepcopy(old)
        current["authoredPath"] = current["authoredPath"].removesuffix(BUFF_SPEED_FACTOR) + BUFF_SPEED_PERCENT
        rows.append(current)
    elif mutation == "wrong-slot":
        old["finalPath"] = old["finalPath"].removesuffix("movementSpeed") + "jumpBoost"
    elif mutation == "wrong-fn":
        old["fn"] = "configure_item_stats"
    elif mutation == "wrong-status":
        old["status"] = "alias_lowering"
    else:
        old["authoredPaths"] = [old["authoredPath"]]
    before = _bytes(wire)
    assert not audit_compiler_receipts(rows, final_document=wire)["ok"]
    assert not validate_runtime_wire(wire)["ok"]
    assert _bytes(wire) == before

@pytest.mark.parametrize("changes", [
    {"default": None}, {"default": 1}, {"neutral": False}, {"neutral": 0.0}, {"required": True},
    {"wire_divisor": 100}, {"wire_name": "jumpBoost"}, {"minimum": 1},
    {"omission_condition": OmissionCondition(target_kinds=("child_projectile",))},
])
def test_retained_omission_cannot_outlive_its_exact_prior_declaration(monkeypatch, changes):
    cap = CAPABILITY_REGISTRY[FN]
    prior = replace(cap.retained_receipt_params[BUFF_SPEED_FACTOR], **changes)
    changed = replace(cap, retained_receipt_params={**cap.retained_receipt_params, BUFF_SPEED_FACTOR: prior})
    monkeypatch.setattr(technical_lowering, "CAPABILITY_REGISTRY", {**CAPABILITY_REGISTRY, FN: changed})
    for case in BUFF_FACTOR_CASES:
        if case["selection"] == "omitted":
            wire = case["wire"]
            assert not audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)["ok"]


@pytest.mark.parametrize("factor", [pytest.param(value, id=label) for label, value in (
    ("positive-zero", 0.0), ("negative-zero", -0.0), ("smallest-positive-subnormal", 2**-149),
    ("smallest-negative-subnormal", -2**-149),
    ("largest-subnormal", struct.unpack("!f", struct.pack("!I", 0x7fffff))[0]),
    ("smallest-normal", 2**-126), ("normal-mantissa-edge", struct.unpack("!f", struct.pack("!I", 0x3f7fffff))[0]),
    ("minimum", -.5), ("maximum", 2.0), ("ordinary-binary64", 1.770282212988338))])
def test_percent_projection_is_declared_division_not_a_lossless_binary64_lattice(factor):
    spec = CAPABILITY_REGISTRY[FN].params[BUFF_SPEED_PERCENT]
    assert (spec.minimum, spec.maximum, spec.wire_divisor, spec.units, spec.semantic_type) == (-50, 200, 100, "additive_percent", "additive_percent")
    # float32 has <=24 significand bits; multiplication by 100 (=25*4)
    # requires <=29, within binary64's 53 at every admitted exponent.
    # These named representation edges check the same projector, not 513
    # exponent/fraction iterations masquerading as one pytest case.
    percent = factor * 100
    if factor == 1.770282212988338:
        doc, index, _ = percent_document(FN, BUFF_SPEED_PERCENT, percent)
        wire = assert_delivered(doc, index, BUFF_SPEED_PERCENT, percent / 100)
        projected = wire["gameplay"]["generatedBuff"]["movementSpeed"]
        assert struct.pack("!d", projected) != struct.pack("!d", factor)
        assert struct.pack("!f", projected) == struct.pack("!f", factor)
    else:
        assert spec.to_wire(percent).hex() == factor.hex()
    assert spec.consumer_value_error(percent) is None
    prior = CAPABILITY_REGISTRY[FN].retained_receipt_params[BUFF_SPEED_FACTOR]
    assert struct.pack("!d", prior.to_wire(factor)) == struct.pack("!d", factor)


@pytest.mark.parametrize("mutation", ["missing-marker", "stale-marker", "stale-source", "wrong-output"])
def test_numeric_provenance_refuses_stale_grammar_or_renamed_receipt_identity_causally(mutation):
    doc = build_capability_witness("configure_spawn")
    call = _scalar_name_call(doc)
    call["params"]["velocity"] = {"constantSpeedPxPerUpdate": 7.125}
    wire = compile_runtime_program(doc)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(rows, authored_document=doc, final_document=wire)["ok"]
    assert doc["runtimeProgram"]["schema"] == RUNTIME_PROGRAM_SCHEMA
    assert audit_compiler_receipts(rows, final_document=wire)["ok"] and validate_runtime_wire(wire)["ok"]
    if mutation.endswith("marker"):
        if mutation == "missing-marker":
            doc["runtimeProgram"].pop("schema")
        else:
            doc["runtimeProgram"]["schema"] = "infini.runtime-program.authoring.v4"
        reason = "source provenance requires the sole current Author grammar"
    else:
        row = next(r for r in rows if r.get("callId") == "witness_call" and r.get("authoredPath", "").endswith(".velocity.constantSpeedPxPerUpdate"))
        field = "authoredPath" if mutation == "stale-source" else "finalPath"
        row[field] = "runtimeProgram.calls[0].params.speedPxPerTick" if field == "authoredPath" else "runtimeProgram.entities[0].spawn.count"
        reason = "compiler receipt used an undeclared authored parameter" if field == "authoredPath" else "structured parameter receipt is not a declared source/output pair"
    report = audit_compiler_receipts(rows, authored_document=doc, final_document=wire)
    assert not report["ok"] and any(v["reason"] == reason for v in report["violations"]), report
