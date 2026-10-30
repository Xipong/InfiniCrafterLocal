"""Author units -> compiler receipts -> frozen C# wire: no aliases or quantization."""


from infini_local.core import llm_config
from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_SCHEMA, CAPABILITY_REGISTRY, capability_for_saved_receipt
from copy import deepcopy
import hashlib
import json
import math
import re
import runpy
import struct
from pathlib import Path

import pytest
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import filter_repair_patch_scope, build_runtime_repair_scope
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.program_schema import (
    strict_author_shape_report,
    strict_repair_shape_report,
    strict_repair_structure_report,
)
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness
from test_author_projectile_aliases import selected as _scalar_name_call
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request

FN = "generated_buff_on_use"

RENAMES = (
    ("move_gravity_arc", "gravityPerTick", "accelY", 0.1875, "movement.params", {}),
    ("move_orbit", "range", "radius", 7.125, "movement.params", {"turnRadiansPerSecond": 3.3}),
    ("move_yoyo_hover", "returnSpeed", "speedBlocksPerSecond", 7.125, "movement.params", {"range": 8}),
    ("tool_stats", "miningSpeedScale", "miningSpeedMultiplier", 1.125, "gameplay", {}),
    ("move_spiral", "turnRadiansPerTick", "turnRadiansPerSecond", -0.1875, "movement.params", {}),
    ("move_expanding_wave", "scalePerTick", "scaleGrowthPerUpdate", 0.1875, "movement.params", {"maxScale": 3}),
    ("move_accelerate", "acceleration", "speedMultiplierPerUpdate", 1.125, "movement.params", {"maxSpeed": 30}),
    ("move_sine_homing", "waveAmplitude", "waveVelocityCoefficient", 7.125, "movement.params", {"range": 8, "homingStrength": 0.1}),
    ("ammo_item", "shootSpeedPxPerTick", "speedBonus", 7.125, "gameplay", {}),
    ("restore_resources_on_use", "potionSickness", "usesPotionRules", True, "gameplay", {}),
    ("generated_buff_on_use", "jumpBoost", "jumpSpeedBonus", 0.1875, "generatedBuff", {}),
    ("generated_buff_on_use", "manaRegenBonusPoints", "manaRegen", 7, "generatedBuff", {}),
)


def _get(document, path):
    value = document
    for part in re.findall(r"[A-Za-z][A-Za-z0-9_]*|\[\d+\]", path):
        value = value[int(part[1:-1])] if part.startswith("[") else value[part]
    return value


@pytest.fixture(scope="module")
def author_cards():
    _, user, _ = build_initial_author_request({}, {}, "unit-proof", model_name="test-model")
    cards = {c["fn"]: c for c in json.loads(user)["runtimeCapabilityContract"]["catalog"]["capabilities"]}
    assert set(cards) == {cap.name for cap in CAPABILITY_REGISTRY.values() if cap.author_visible}
    return cards


def _retained_movement_wire(fn, params):
    """Synthetic saved-wire control, never fresh Author admission of a retired fn.

    Compile only the current straight-motion envelope, then replace its movement
    with an explicit retained component and registry-declared source-free receipts.
    No captured document is imported, normalized, or edited.
    """
    from infini_local.core.runtime_authoring.capability_registry import MOVEMENT_OPCODE

    source = build_capability_witness("move_straight")
    if fn == "move_yoyo_hover":
        next(row for row in source["runtimeProgram"]["calls"]
             if row["fn"] == "item_use")["params"]["channel"] = True
    wire = compile_runtime_program(source)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    identity = [row for row in receipts if row.get("callId") == "witness_call"]
    assert len(identity) == 2
    prefix = identity[0]["finalPath"].removesuffix(".name")
    movement = _get(wire, prefix)
    movement.update(name=fn, code=MOVEMENT_OPCODE[fn], params={})
    for row, key in zip(identity, ("name", "code")):
        row.update(fn=fn, value=movement[key])
    source_path = identity[0]["authoredPath"].removesuffix(".fn")
    cap = CAPABILITY_REGISTRY[fn]
    assert set(params) == {name for name, spec in cap.params.items() if spec.required}
    for name, value in params.items():
        for projection in cap.params[name].projected_fields(value, name, updates_per_tick=1):
            assert "." not in projection.wire_path and not projection.literal
            movement["params"][projection.wire_path] = projection.value
            receipts.append({
                "callId": "witness_call", "fn": fn,
                "authoredPath": source_path + ".params." + projection.authored_path,
                "finalPath": prefix + ".params." + projection.wire_path,
                "value": projection.value, "status": "delivered",
            })
    assert validate_runtime_wire(wire)["ok"], validate_runtime_wire(wire)["errors"]
    assert audit_compiler_receipts(receipts, final_document=wire)["ok"]
    stripped = deepcopy(wire)
    stripped.pop("runtimeContract")
    assert validate_runtime_wire(stripped)["ok"]
    return wire


@pytest.mark.parametrize("fn,old,new,value,component,companions", [pytest.param(*row, id=f"{row[0]}-{row[2]}") for row in RENAMES])
def test_identity_rename_reaches_packet_projector_and_frozen_wire(author_cards, fn, old, new, value, component, companions):
    cap, spec = CAPABILITY_REGISTRY[fn], CAPABILITY_REGISTRY[fn].params[new]
    assert old not in cap.params
    if cap.author_visible:
        assert old not in author_cards[fn]["params"] and new in author_cards[fn]["params"]
    else:
        assert fn not in author_cards
    assert spec.wire_name and any(path.endswith("." + spec.wire_name) for path in cap.final_wire_paths)
    if spec.predecessor_names:
        authored_value = spec.from_wire(value, updates_per_tick=1)
        assert _bytes(spec.to_wire(authored_value, updates_per_tick=1)) == _bytes(value)
    else:
        authored_value = value
        for boundary in (spec.minimum, spec.maximum, spec.neutral):
            if boundary is not None:
                assert _bytes(spec.to_wire(boundary)) == _bytes(boundary)
    if cap.author_visible:
        authored = build_capability_witness(fn)
        index, call = next((i, c) for i, c in enumerate(authored["runtimeProgram"]["calls"]) if c["id"] == "witness_call")
        call["params"][new] = authored_value
        wire = assert_delivered(authored, index, new, value)
        alias = deepcopy(authored)
        alias_call = alias["runtimeProgram"]["calls"][index]
        alias_call["params"][old] = alias_call["params"].pop(new)
        assert not validate_runtime_program(alias)["ok"]
    else:
        wire = _retained_movement_wire(fn, {**companions, new: authored_value})
    rows = [r for r in wire["runtimeContract"]["finalWireReceipts"]
            if r.get("callId") == "witness_call" and r.get("authoredPath", "").endswith(".params." + new)]
    assert rows and all(r["finalPath"].endswith("." + spec.wire_name) for r in rows)
    assert all(_bytes(r["value"]) == _bytes(value) for r in rows)
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


@pytest.mark.parametrize("fn,param,path,value,expected", [
    pytest.param("tool_stats", "axePower", "gameplay.axePower", 35, 7, id="axe-tooltip-to-engine"),
    pytest.param(FN, "lifeRegen", "gameplay.generatedBuff.lifeRegen", 3.5, 7, id="buff-half-hp-units"),
    pytest.param(FN, "manaRegen", "gameplay.generatedBuff.manaRegen", 7, 7, id="buff-mana-points"),
    pytest.param("accessory", "lifeRegen", "accessory.lifeRegen", -3.5, -7, id="signed-accessory-regen"),
    pytest.param("armor", "lifeRegen", "armor.lifeRegen", 3.5, 7, id="armor-regen"),
    pytest.param("armor", "setBonuses.lifeRegen", "armor.setBonusLifeRegen", 3.5, 7, id="set-bonus-regen"),
])
def test_discrete_author_units_reach_each_engine_destination(fn, param, path, value, expected):
    doc = build_capability_witness(fn)
    call = next(row for row in doc["runtimeProgram"]["calls"] if row["id"] == "witness_call")
    if fn == FN:
        call["params"]["oreSenseEnabled"] = True
    _set_stat(call["params"], param, value)
    before = _bytes(doc)
    wire = compile_runtime_program(doc)
    assert type(_get(wire, path)) is int and _get(wire, path) == expected
    assert validate_runtime_wire(wire)["ok"]
    assert _bytes(doc) == before


@pytest.mark.parametrize("boundary", ["minimum", "maximum", "below", "above", "off-step"], ids=["minimum", "maximum", "below-minimum", "above-maximum", "fractional-engine-unit"])
def test_discrete_domain_boundaries_are_admitted_or_refused_without_default(boundary):
    spec = CAPABILITY_REGISTRY["tool_stats"].params["axePower"]
    step = spec.multiple_of
    value = {"minimum": spec.minimum, "maximum": spec.maximum,
             "below": spec.minimum - step, "above": spec.maximum + step, "off-step": step / 2}[boundary]
    doc = build_capability_witness("tool_stats")
    call = next(row for row in doc["runtimeProgram"]["calls"] if row["id"] == "witness_call")
    call["params"]["axePower"] = value
    before = _bytes(doc)
    if boundary in {"minimum", "maximum"}:
        assert validate_runtime_wire(compile_runtime_program(doc))["ok"]
    else:
        assert not validate_runtime_program(doc)["ok"]
        with pytest.raises(ValueError):
            compile_runtime_program(doc)
    assert _bytes(doc) == before


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
    assert audit_compiler_receipts(serialized["runtimeContract"]["finalWireReceipts"],
                                   authored_document=json.loads(before), final_document=serialized)["ok"]
    assert _bytes(doc) == before
    return wire


# One nonneutral value per registry-declared destination; common numeric shapes
# are covered separately rather than repeated for every leaf.
PERCENT_WIRING = [pytest.param(fn, name, spec, value, True, True, id=f"{fn}-{name}-{label}")
                  for fn, name, spec in PERCENT_PARAMS
                  for label, value in (("decimal", 15.125),)]
PERCENT_SHAPES = [pytest.param(value, accepted, id=label) for label, value, accepted in (
    ("zero", 0, True), ("decimal", .007, True), ("signed-decimal", -.007, True),
    ("positive-subnormal", 100 * 2**-149, True), ("division-collapse", 5e-324, False),
    ("storage-collapse", 1e-50, False), ("negative-storage-collapse", -1e-50, False),
    ("half-tie", 100 * 2**-150, False),
    ("half-above", math.nextafter(100 * 2**-150, math.inf), True),
)]

IDENTITY_CONSUMER_CASES = [
    pytest.param("miningSpeedMultiplier", 1.000000001, False, "ore", id="valid-ore-cannot-hide-collapse"),
    pytest.param("miningSpeedMultiplier", .9995, True, "sole", id="signed-nonneutral-identity"),
    pytest.param("jumpSpeedBonus", 1e-50, False, "sole", id="jump-collapse"),
    pytest.param("lightStrength", .0005, True, "sole", id="small-light-effect"),
]


@pytest.mark.parametrize("fn,name,spec,value,accepted,companion", PERCENT_WIRING + [
    pytest.param(FN, "moveSpeedBonus", CAPABILITY_REGISTRY[FN].params["moveSpeedBonus"],
                 *case.values, True, id="shared-" + case.id) for case in PERCENT_SHAPES
] + [pytest.param(FN, case.values[0], CAPABILITY_REGISTRY[FN].params[case.values[0]],
                 *case.values[1:], id=case.id) for case in IDENTITY_CONSUMER_CASES])
def test_numeric_admission_projects_exact_bytes_and_checks_both_consumer_boundaries(fn, name, spec, value, accepted, companion):
    doc, index, _ = percent_document(fn, name, value, companion=companion)
    before = _bytes(doc)
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
    pytest.param("accessory", "moveSpeedBonus", None, id="null"),
    pytest.param("armor", "setBonuses.moveSpeedBonus", True, id="nested-boolean"),
    pytest.param("equipment_damage_bonus", "bonusPercent", "1e-50", id="numeric-string"),
    pytest.param(FN, "moveSpeedBonus", [], id="array"),
    pytest.param(FN, "moveSpeedBonus", float("nan"), id="nan"),
    pytest.param(FN, "moveSpeedBonus", float("inf"), id="infinity"),
    pytest.param(FN, "moveSpeedBonus", 10**1000, id="huge-integer"),
])
def test_percent_shape_owner_refuses_malformed_present_numbers_without_mutation(fn, name, bad):
    doc, _, _ = percent_document(fn, name, bad)
    before = json.dumps(doc, ensure_ascii=False)
    assert not validate_runtime_program(doc)["ok"]
    with pytest.raises(ValueError, match="runtime program rejected"):
        compile_runtime_program(doc)
    assert json.dumps(doc, ensure_ascii=False) == before


@pytest.mark.parametrize("fn,name,value,replacement", [
    pytest.param(FN, "moveSpeedBonus", 5e-324, 15.125, id="percent-consumer-collapse"),
    pytest.param("armor", "setBonuses.moveSpeedBonus", 5e-324, 15.125, id="nested-percent-collapse"),
    pytest.param(FN, "miningSpeedMultiplier", 1.000000001, 1.0005, id="identity-consumer-collapse"),
])
def test_numeric_collapse_has_exact_repair_authority_and_frozen_siblings(fn, name, value, replacement):
    from infini_local.core.runtime_authoring.validator import VALIDATION_ERROR_CODES
    from infini_local.core.runtime_authoring.repair_scope import REPAIR_VALIDATION_ERROR_CODES, REPAIR_ERROR_POLICY
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
    sibling, hostile = (("damageClass", "magic") if fn == "equipment_damage_bonus" else
                        ("duration", 360) if fn == FN else ("defensePoints", 77))
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


@pytest.mark.parametrize("fn", ["accessory", "armor", "generated_buff_on_use"])
@pytest.mark.parametrize("value", [5e-324, -1e-50])
def test_sole_percent_effect_is_rejected_without_thawing_valid_call_siblings(fn, value):
    name = "moveSpeedBonus"
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
    if fn in {"accessory", "generated_buff_on_use"}:
        assert not neutral_report["ok"]
        assert any(e["code"] == "inert_component" for e in neutral_report["errors"])
    else:
        assert_delivered(doc, index, name, -0.0)

def test_ordinary_binary64_collision_is_not_replaced_by_a_roundtrip_lattice():
    first, second = 0.007, 0.007000000000000001
    assert struct.pack("!d", first) != struct.pack("!d", second)
    assert first / 100 == second / 100
    assert first / 100 * 100 != first  # A proposed equality rule would ban this normal decimal.
    documents = [percent_document("accessory", "moveSpeedBonus", value)[0]
                 for value in (first, second)]
    assert all(validate_runtime_program(doc)["ok"] for doc in documents)
    assert _bytes(compile_runtime_program(documents[0])) == _bytes(compile_runtime_program(documents[1]))

@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_numeric_constraints_reach_serialized_author_and_exact_repair(monkeypatch, mode):
    from test_gameplay_repair_readonly_context import _capture_request

    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    request, text, _ = build_initial_author_request({}, {}, "numeric-contract", model_name="offline-test")
    assert request["response_format"]["type"] == mode
    catalog = json.loads(text)["runtimeCapabilityContract"]["catalog"]
    cards = {row["fn"]: row for row in catalog["capabilities"]}
    doc, _, call = percent_document(FN, "moveSpeedBonus", 5e-324)
    _, dossier = _capture_request(monkeypatch, doc, mode)
    repair_card = next(row for row in dossier["existingBrokenCapabilityCards"] if row["fn"] == FN)
    for card in (cards[FN], repair_card):
        constraint = card["params"]["moveSpeedBonus"]["consumerConstraint"]
        if isinstance(constraint, str):
            constraint = catalog["fieldGuide"]["consumerConstraints"][constraint]
        assert constraint["wireProjection"] == {"divisor": 100, "multiplier": 1}
        assert constraint["storage"] == "float32"
    assert dossier["repairScope"]["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ["params.moveSpeedBonus"]}]


def test_generated_equipment_bounds_stay_current():
    root = Path(__file__).resolve().parents[2]
    assert runpy.run_path(str(root / "tools/generate/generate_equipment_bounds.py"))["render"]() == (
        root / "ModSources/InfiniCrafterLocal/Common/Models/Runtime/GeneratedEquipmentBounds.g.cs").read_text()


@pytest.mark.parametrize("fn", ["spawn_on_event", "pull_on_event"])
def test_periodic_requires_explicit_period_ticks_and_repair_leaf(fn):
    doc = build_runtime_fixture("workbench_blade")
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == "spawn_on_event")
    if fn == "pull_on_event":
        call = {
            "id": "pull_periodic",
            "fn": fn,
            "target": call["target"],
            "params": {
                "when": {},
                "mode": "target_to_entity",
                "impulseBlocksPerSecond": 3.75,
                "radius": 8,
            },
        }
        doc["runtimeProgram"]["calls"].append(call)
    else:
        call["params"].update(when={})
    params = call["params"]
    params["when"] = {}
    if fn == "spawn_on_event":
        from infini_local.core.runtime_authoring.program_schema import strict_schema_errors
        schema = CAPABILITY_REGISTRY[fn].provider_variant_schema()["properties"]["params"]
        trigger_schema = schema["properties"]["when"]
        assert strict_schema_errors({}, trigger_schema)
        assert not strict_schema_errors({"everySeconds": 0.1}, trigger_schema)
        missing = {key: value for key, value in params.items() if key != "count"}
        paths = [row["path"] for row in strict_schema_errors(missing, schema) if row["kind"] == "required"]
        assert paths.count("$.count") == 1
        # Empty when no longer identifies periodic uniquely: equipment reactions
        # have their own object forms. Repair must let the Author choose a trigger.
        assert any(row["path"] == "$.when" and row["kind"] == "one_of" for row in strict_schema_errors(missing, schema))
    assert not strict_author_shape_report(doc)["ok"]
    report = validate_runtime_program(doc)
    assert not report["ok"]
    trigger_path = 'params.when' if fn == "spawn_on_event" else 'params.when.everySeconds'
    assert any(r["path"].endswith('.' + trigger_path) for r in report["errors"])
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": [trigger_path]}]
    if fn != "spawn_on_event":
        assert "everySeconds" in json.dumps(scope)
    with pytest.raises(ValueError):
        compile_runtime_program(doc)
    params["when"] = {"everySeconds": 0.1}
    assert validate_runtime_program(doc)["ok"], validate_runtime_program(doc)["errors"]
    params["when"] = "on_hit"
    assert validate_runtime_program(doc)["ok"], validate_runtime_program(doc)["errors"]


_SCALAR_NAME_CAPTURE = json.loads((Path(__file__).parent / "fixtures/scalar_author_names_retained_receipts.json").read_text())
_SCALAR_NAME_CASES = _SCALAR_NAME_CAPTURE["cases"]


def _captured_capability(case):
    cap = capability_for_saved_receipt(case["fn"])
    assert cap is not None
    return cap


def _scalar_name_current_source(case):
    assert _captured_capability(case).author_visible
    source = deepcopy(case["authored"])
    params = _scalar_name_call(source)["params"]
    assert case["canonicalParameter"] not in params
    params[case["canonicalParameter"]] = params.pop(case["oldParameter"])
    from captured_projectile_author import project_captured_world_units
    return project_captured_world_units(source)


def _current_scalar_name(case):
    return next((name for name, spec in _captured_capability(case).params.items()
                 if case["canonicalParameter"] in (*spec.predecessor_names, *spec.previous_author_names)), case["canonicalParameter"])


def _scalar_name_restored_wire(case):
    if _captured_capability(case).author_visible:
        wire = compile_runtime_program(_scalar_name_current_source(case))
    else:
        companions = next(row[5] for row in RENAMES if row[0] == _captured_capability(case).name)
        name = _current_scalar_name(case)
        spec = _captured_capability(case).params[name]
        wire = _retained_movement_wire(_captured_capability(case).name, {
            **companions, name: spec.from_wire(case["receipt"]["value"], updates_per_tick=1),
        })
    receipt = next(row for row in wire["runtimeContract"]["finalWireReceipts"]
                   if row.get("callId") == "witness_call" and row.get("authoredPath", "").endswith(".params." + _current_scalar_name(case)))
    expected = {**case["receipt"], "fn": _captured_capability(case).name, "authoredPath": case["receipt"]["authoredPath"].removesuffix(case["oldParameter"]) + _current_scalar_name(case)}
    assert receipt == expected
    receipt.update(deepcopy(case["receipt"]))  # Restore this historical scalar receipt on the current valid source.
    return wire, receipt


@pytest.mark.parametrize("case", _SCALAR_NAME_CASES, ids=lambda case: case["fn"])
def test_scalar_names_pin_complete_capture_current_provenance_and_exact_repair(case):
    assert _SCALAR_NAME_CAPTURE["originCommit"] == "274d4c38849bff5b8f7ecde1c61d6276a4803712"
    captured_before = _bytes(case)
    visible = _captured_capability(case).author_visible
    source = _scalar_name_current_source(case) if visible else case["authored"]
    if visible:
        wire = compile_runtime_program(source)
        assert validate_runtime_wire(wire)["ok"]

    retained, receipt = _scalar_name_restored_wire(case)
    retained_before = _bytes(retained)
    assert receipt == case["receipt"]  # Preserve archived claim, not old diagnostic compatibility.
    assert not validate_runtime_wire(retained)["ok"]
    saved = retained["runtimeContract"]["finalWireReceipts"]
    report = audit_compiler_receipts(saved, final_document=retained)
    assert not report["ok"] and report["authoredSourceChecked"] is False
    report = audit_compiler_receipts(saved, authored_document=source, final_document=retained)
    reason = ("compiler receipt used an undeclared authored parameter" if visible
              else "source provenance requires the sole current Author grammar")
    assert not report["ok"] and any(row["reason"] == reason for row in report["violations"])
    assert _bytes(retained) == retained_before
    assert not validate_runtime_program(case["authored"])["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(case["authored"])
    # Old name must not become an accepted fresh wire field, even for open gameplay.
    owner, _, old = receipt["finalPath"].rpartition(".")
    parent = _get(retained, owner)
    parent[_current_scalar_name(case)] = parent.pop(old)
    errors = validate_runtime_wire(retained)["errors"]
    if owner.startswith("runtimeProgram."):
        assert any(row["code"] == "unknown_final_wire_field" and row["path"].endswith("." + _current_scalar_name(case)) for row in errors)
    else:
        assert any(row["code"] == "undeclared_technical_lowering" for row in errors)
    assert _bytes(case) == captured_before
    if not visible:
        # Retained wire remains auditable, but no spelling revives retired fresh
        # Author/Repair admission. Do not compile or import that archived source.
        stale = {"note": "retained wire is not a fresh capability", "callsUpsert": [deepcopy(_scalar_name_call(source))]}
        assert not strict_repair_structure_report(stale)["ok"]
        assert not strict_repair_shape_report(stale)["ok"]
        return
    broken = deepcopy(source)
    current = _current_scalar_name(case)
    _scalar_name_call(broken)["params"][current] = _captured_capability(case).params[current].maximum + 1
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    assert next(row["paths"] for row in scope["fieldPermissions"]["calls"] if row["id"] == "witness_call") == ["params." + current]
    stale = {"note": "old spelling is not an alias", "callsUpsert": [deepcopy(_scalar_name_call(case["authored"]))]}
    assert not strict_repair_structure_report(stale)["ok"] and not strict_repair_shape_report(stale)["ok"]
    assert not filter_repair_patch_scope(broken, stale, scope)[1]["ok"]
    with pytest.raises(ValueError):
        apply_repair_patch(broken, stale)
    frozen = deepcopy(next(row for row in source["runtimeProgram"]["calls"] if row["fn"] == "item_stats"))
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
        value = True if mutation == "boolean" else _captured_capability(case).params[_current_scalar_name(case)].maximum + 1
        _get(wire, owner)[key] = receipt["value"] = value
    report = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)
    assert not report["ok"] and any(row["reason"] == "compiler receipt used an undeclared authored parameter" for row in report["violations"])


BUFF_SPEED_PERCENT = "moveSpeedBonus"
BUFF_SPEED_FACTOR = "moveSpeedBonusFactor"
BUFF_FACTOR_ARCHIVE = json.loads((Path(__file__).with_name("fixtures") / "buff_speed_factor_retained_wire.json").read_text())
BUFF_FACTOR_CASES = BUFF_FACTOR_ARCHIVE["cases"]


def _buff_speed_receipt(wire, name=BUFF_SPEED_FACTOR):
    return next(row for row in wire["runtimeContract"]["finalWireReceipts"]
                if row.get("fn") in (FN, CAPABILITY_REGISTRY[FN].persisted_name)
                and row.get("authoredPath", "").endswith(".params." + name))

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
    assert not report["ok"] and report["authoredSourceChecked"] is False, report
    assert not validate_runtime_wire(prior_wire)["ok"]
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
    call["params"]['duration'] = -1
    original = _bytes(document)
    scope_report = build_runtime_repair_scope(document, validate_runtime_program(document)["errors"])
    assert scope_report["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": ['params.duration']}]
    candidate = deepcopy(call)
    candidate["params"].update(duration=(60) / 60, moveSpeedBonus=25, miningSpeedMultiplier=2)
    patch, audit = filter_repair_patch_scope(document, {"note": "repair duration", "callsUpsert": [candidate]}, scope_report)
    assert audit["ok"] and audit["ignoredChanges"]
    repaired = apply_repair_patch(document, patch)
    assert _scalar_name_call(repaired)["params"] == {**call["params"], "duration": 1}
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
    ("current", "delivered", -.8, True, "minimum"),
    ("current", "delivered", 2.0, True, "maximum"),
    ("current", "delivered", math.nextafter(-.8, -math.inf), False, "below-minimum"),
    ("current", "delivered", math.nextafter(2.0, math.inf), False, "above-maximum"),
    ("current", "delivered", .007 / 100, True, "decimal-collision"),
    ("current", "delivered", 2**-149, True, "float32-subnormal"),
    ("current", "delivered", math.nextafter(2**-150, math.inf), True, "above-half"),
    # Retired parameter names are rejected before any numeric-domain admission.
    # Keep both receipt statuses and both owner slots, with malformed, neutral
    # and ordinary representations; old floating-point boundary grids no longer
    # exercise a distinct contract. Current-name numeric boundaries stay above.
    *(("prior", status, value, False, label) for status in ("delivered", "declared_neutral_omission")
      for value, label in ((None, "null"), (0, "int-zero"), (.2, "ordinary"))),
)


@pytest.mark.parametrize("scope,version,status,value,accepted", [
    pytest.param(scope, version, status, value, accepted, id=f"{scope}-{version}-{status}-{label}")
    for version, status, value, accepted, label in WIRE_VALUES
    for scope in (("global", "effect_group") if version == "prior" or label in {"int-zero", "float32-subnormal"} else ("global",))])
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
        name, reason = BUFF_SPEED_FACTOR, "compiler receipt used an undeclared authored parameter"
        accepted = False
    assert audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)["ok"] is (version == "current")
    assert validate_runtime_wire(wire)["ok"] is (version == "current")
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
        old["fn"] = "item_stats"
    elif mutation == "wrong-status":
        old["status"] = "alias_lowering"
    else:
        old["authoredPaths"] = [old["authoredPath"]]
    before = _bytes(wire)
    assert not audit_compiler_receipts(rows, final_document=wire)["ok"]
    assert not validate_runtime_wire(wire)["ok"]
    assert _bytes(wire) == before


@pytest.mark.parametrize("mutation", ["missing-marker", "stale-marker", "stale-source", "wrong-output"])
def test_numeric_provenance_refuses_stale_grammar_or_renamed_receipt_identity_causally(mutation):
    doc = build_capability_witness("spawn")
    call = _scalar_name_call(doc)
    call["params"]["velocity"] = {'speed': (7.125) * 60 / 16}
    wire = compile_runtime_program(doc)
    rows = wire["runtimeContract"]["finalWireReceipts"]

    assert doc["runtimeProgram"]["schema"] == RUNTIME_PROGRAM_SCHEMA
    assert audit_compiler_receipts(rows, final_document=wire)["ok"] and validate_runtime_wire(wire)["ok"]
    if mutation.endswith("marker"):
        if mutation == "missing-marker":
            doc["runtimeProgram"].pop("schema")
        else:
            doc["runtimeProgram"]["schema"] = "infini.runtime-program.authoring.v4"
        reason = "source provenance requires the sole current Author grammar"
    else:
        row = next(r for r in rows if r.get("callId") == "witness_call" and r.get("authoredPath", "").endswith(".velocity.speed"))
        field = "authoredPath" if mutation == "stale-source" else "finalPath"
        row[field] = "runtimeProgram.calls[0].params.speedPxPerTick" if field == "authoredPath" else "runtimeProgram.entities[0].spawn.count"
        reason = "compiler receipt used an undeclared authored parameter" if field == "authoredPath" else "structured parameter receipt is not a declared source/output pair"
    report = audit_compiler_receipts(rows, authored_document=doc, final_document=wire)
    assert not report["ok"] and any(v["reason"] == reason for v in report["violations"]), report


def test_same_unit_saved_names_are_readable_but_never_fresh_author_aliases():
    # Handwritten prior/current spellings: do not derive the negative vocabulary
    # from the resolver that is itself under test.
    source = build_capability_witness("generated_buff_on_use")
    call = _scalar_name_call(source)
    call["params"]["manaRegen"] = 7
    wire = compile_runtime_program(source)
    receipt = next(row for row in wire["runtimeContract"]["finalWireReceipts"]
                   if row.get("callId") == call["id"] and row.get("authoredPath", "").endswith(".params.manaRegen"))
    assert receipt["value"] == 7 and receipt["finalPath"].endswith(".manaRegen")
    receipt["fn"] = "apply_generated_buff_on_use"
    receipt["authoredPath"] = receipt["authoredPath"].removesuffix("manaRegen") + "manaRegenBonusPoints"
    before = _bytes(wire)
    receipts = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(receipts, final_document=wire)["ok"]
    assert validate_runtime_wire(wire)["ok"]
    assert not audit_compiler_receipts(receipts, authored_document=source, final_document=wire)["ok"]
    assert _bytes(wire) == before
    for old_identity in ("function", "parameter"):
        stale = deepcopy(source)
        old_call = _scalar_name_call(stale)
        if old_identity == "function":
            old_call["fn"] = "apply_generated_buff_on_use"
        else:
            old_call["params"]["manaRegenBonusPoints"] = old_call["params"].pop("manaRegen")
        assert not validate_runtime_program(stale)["ok"]
        assert not strict_repair_shape_report({"note": "not an alias", "callsUpsert": [old_call]})["ok"]
        with pytest.raises(ValueError):
            compile_runtime_program(stale)
