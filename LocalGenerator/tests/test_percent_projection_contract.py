"""Percent admission guards neutral collapse, not a lossless float lattice.

The registry is the sole owner; validator, exact Repair and compiler consume it.
No provider or native runtime is contacted by these regressions.
"""
from copy import deepcopy
import json
import math
import struct

import pytest

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY,
    apply_repair_patch,
    build_runtime_repair_scope,
    compile_runtime_program,
    filter_repair_patch_scope,
    validate_runtime_program,
    validate_runtime_wire,
)
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness
from test_registry_author_units import _get


PERCENT_PARAMS = tuple(
    (fn, name, spec)
    for fn, cap in CAPABILITY_REGISTRY.items()
    for name, spec in cap.params.items()
    if spec.wire_divisor == 100
)


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def percent_document(fn, name, value, *, companion=True):
    doc = build_capability_witness(fn)
    index, call = next(
        (i, row) for i, row in enumerate(doc["runtimeProgram"]["calls"])
        if row["id"] == "witness_call"
    )
    if not companion:
        call["params"].pop("defensePoints", None)
    call["params"][name] = value
    return doc, index, call


def assert_delivered(doc, index, name, expected):
    before = _bytes(doc)
    report = validate_runtime_program(doc)
    assert report["ok"], report
    wire = compile_runtime_program(doc)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    selected = [r for r in rows if r.get("authoredPath") == f"runtimeProgram.calls[{index}].params.{name}"]
    assert selected
    for row in selected:
        assert row["status"] == "delivered"
        assert _bytes(row["value"]) == _bytes(expected)
        assert _bytes(_get(wire, row["finalPath"])) == _bytes(expected)
    assert audit_compiler_receipts(rows, authored_document=doc, final_document=wire)["ok"]
    serialized = json.loads(_bytes(wire))
    assert validate_runtime_wire(serialized)["ok"]
    assert audit_compiler_receipts(
        serialized["runtimeContract"]["finalWireReceipts"],
        authored_document=json.loads(before), final_document=serialized,
    )["ok"]
    assert _bytes(doc) == before
    return wire


@pytest.mark.parametrize(
    "fn,name,spec,value",
    [pytest.param(fn, name, spec, sign * magnitude, id=f"{fn}-{name}-{sign * magnitude!r}")
     for fn, name, spec in PERCENT_PARAMS
     for sign in (1, -1) if sign > 0 or spec.minimum < 0
     for magnitude in (json.loads("5e-324"), 1e-50, 2.0 ** -149)],
)
def test_nonneutral_percent_refused_at_exact_leaf_then_explicitly_repaired(fn, name, spec, value):
    doc, index, call = percent_document(fn, name, value)
    before = _bytes(doc)
    report = validate_runtime_program(doc)
    assert not report["ok"], "nonzero percent must not become zero in /100 or float32 storage"
    assert [(e["code"], e["path"]) for e in report["errors"]] == [
        ("consumer_representability", f"$.runtimeProgram.calls[{index}].params.{name}")
    ]
    with pytest.raises(ValueError, match="runtime program rejected"):
        compile_runtime_program(doc)
    scope = build_runtime_repair_scope(doc, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": [f"params.{name}"]}]
    assert scope["fieldPermissions"]["bindings"] == []
    assert scope["fieldPermissions"]["entities"] == []
    candidate = deepcopy(call)
    candidate["params"][name] = 15.125
    # A valid sibling/absence must remain frozen despite a useful correction.
    sibling = "damageClass" if fn == "add_equipment_damage_bonus" else "defensePoints"
    candidate["params"][sibling] = "magic" if sibling == "damageClass" else 77
    unrelated = deepcopy(doc["runtimeProgram"]["calls"][0])
    unrelated["params"]["damage"] = 1999
    patch = {"note": "offline explicit percent correction", "realizationReplacement": deepcopy(doc["realization"]),
             "callsUpsert": [candidate, unrelated]}
    filtered, audit = filter_repair_patch_scope(doc, patch, scope)
    assert audit["ok"], audit
    fixed = apply_repair_patch(doc, filtered)
    expected = deepcopy(doc)
    expected["runtimeProgram"]["calls"][index]["params"][name] = 15.125
    assert _bytes(fixed) == _bytes(expected)
    assert_delivered(fixed, index, name, 15.125 / 100)
    assert _bytes(doc) == before


@pytest.mark.parametrize("format_mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("fn,name,spec", [pytest.param(*row, id=f"{row[0]}-{row[1]}") for row in PERCENT_PARAMS])
def test_projection_constraint_reaches_actual_author_and_serialized_repair(monkeypatch, format_mode, fn, name, spec):
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
    from infini_local.pipelines import llm_transport as transport
    from test_gameplay_repair_readonly_context import _capture_request

    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", format_mode)
    _, author_text, _ = build_initial_author_request({}, {}, {}, {}, "offline-percent", model_name="test-model")
    author_cards = json.loads(author_text)["runtimeCapabilityContract"]["catalog"]["capabilities"]
    doc, _, _ = percent_document(fn, name, 5e-324)
    _, dossier = _capture_request(monkeypatch, doc, format_mode)
    for cards in (author_cards, dossier["existingBrokenCapabilityCards"]):
        row = next(c for c in cards if c["fn"] == fn)["params"][name]
        constraint = row["consumerConstraint"]
        assert constraint == spec.schema()["x-infini-consumerConstraint"]
        assert constraint["storage"] == "float32"
        assert constraint["neutral"] == 0
        assert constraint["rule"] == "nonneutral_must_remain_nonneutral"
        assert constraint.get("wireProjection") == {"divisor": 100, "multiplier": 1}
        assert "binary64" in constraint["meaning"]
        assert "round-trip" in constraint["meaning"]
        assert "No rounding or replacement" in constraint["meaning"]


def test_percent_roster_is_complete():
    assert len(PERCENT_PARAMS) == 21
    assert {fn: sum(row[0] == fn for row in PERCENT_PARAMS) for fn in {row[0] for row in PERCENT_PARAMS}} == {
        "configure_accessory": 8, "configure_armor": 12, "add_equipment_damage_bonus": 1,
    }
    assert all(spec.neutral == 0 and spec.consumer_storage == "float32" for _, _, spec in PERCENT_PARAMS)


@pytest.mark.parametrize(
    "fn,name,spec,value",
    [pytest.param(fn, name, spec, value, id=f"{fn}-{name}-{type(value).__name__}-{value!r}")
     for fn, name, spec in PERCENT_PARAMS
     for value in (0, 0.0, -0.0, 0.007, 0.007000000000000001, 0.1, 15, 15.0, 15.125,
                   1e-40, 100 * 2.0 ** -149, spec.minimum, spec.maximum,
                   *((-0.007, -0.1, -1e-40) if spec.minimum is not None and spec.minimum < 0 else ()))],
)
def test_regular_decimals_neutrals_endpoints_and_nonzero_subnormals_keep_wire_bytes(fn, name, spec, value):
    doc, index, _ = percent_document(fn, name, value)
    expected = value / 100
    assert_delivered(doc, index, name, expected)
    if value != 0:
        stored = struct.unpack("!f", struct.pack("!f", expected))[0]
        assert stored != 0


@pytest.mark.parametrize("fn,name,spec", [pytest.param(*row, id=f"{row[0]}-{row[1]}") for row in PERCENT_PARAMS])
@pytest.mark.parametrize("direction,accepted", [(0.0, False), (None, False), (math.inf, True)])
def test_float32_half_subnormal_boundary_is_checked_after_division(fn, name, spec, direction, accepted):
    tie = 100 * 2.0 ** -150
    magnitude = tie if direction is None else math.nextafter(tie, direction)
    for sign in (1, -1) if spec.minimum < 0 else (1,):
        value = sign * magnitude
        stored = struct.unpack("!f", struct.pack("!f", value / 100))[0]
        assert (stored != 0) is accepted
        doc, index, _ = percent_document(fn, name, value)
        before = _bytes(doc)
        report = validate_runtime_program(doc)
        assert report["ok"] is accepted, report
        if accepted:
            assert_delivered(doc, index, name, value / 100)
        else:
            assert [(e["code"], e["path"]) for e in report["errors"]] == [
                ("consumer_representability", f"$.runtimeProgram.calls[{index}].params.{name}")
            ]
        assert _bytes(doc) == before


@pytest.mark.parametrize("fn", ["configure_accessory", "configure_armor"])
@pytest.mark.parametrize("value", [5e-324, -5e-324, 1e-50, -1e-50])
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
    # Keep existing composition policy: zero alone is inert for an accessory;
    # an armor still has its explicit slot/set identity. Neither is precision loss.
    call["params"][name] = -0.0
    neutral_report = validate_runtime_program(doc)
    assert all(e["code"] != "consumer_representability" for e in neutral_report["errors"])
    if fn == "configure_accessory":
        assert not neutral_report["ok"]
        assert any(e["code"] == "inert_component" for e in neutral_report["errors"])
    else:
        assert_delivered(doc, index, name, -0.0)


@pytest.mark.parametrize("fn,name,spec", [pytest.param(*row, id=f"{row[0]}-{row[1]}") for row in PERCENT_PARAMS])
@pytest.mark.parametrize("bad", [None, True, "1e-50", [], {}, float("nan"), float("inf"), -float("inf"), 10 ** 1000])
def test_present_bad_percent_remains_rejected_without_exception_or_mutation(fn, name, spec, bad):
    doc, _, _ = percent_document(fn, name, bad)
    before = json.dumps(doc, ensure_ascii=False)
    assert not validate_runtime_program(doc)["ok"]
    with pytest.raises(ValueError, match="runtime program rejected"):
        compile_runtime_program(doc)
    assert json.dumps(doc, ensure_ascii=False) == before


def test_ordinary_binary64_collision_is_not_replaced_by_a_roundtrip_lattice():
    first, second = 0.007, 0.007000000000000001
    assert struct.pack("!d", first) != struct.pack("!d", second)
    assert first / 100 == second / 100
    assert first / 100 * 100 != first  # A proposed equality rule would ban this normal decimal.
    documents = [percent_document("configure_accessory", "moveSpeedBonusPercent", value)[0]
                 for value in (first, second)]
    assert all(validate_runtime_program(doc)["ok"] for doc in documents)
    assert _bytes(compile_runtime_program(documents[0])) == _bytes(compile_runtime_program(documents[1]))
