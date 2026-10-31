"""Declared full-Author neutrals, exact omission provenance, and frozen Repair absence."""

import json
from copy import deepcopy
from dataclasses import replace
from itertools import product

import infini_local.core.runtime_authoring.technical_lowering as technical_lowering
import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch, strict_schema_errors
from infini_local.core.runtime_authoring.registry_views import capability_provider_union
from infini_local.core.runtime_authoring.repair.filter import filter_repair_patch_scope
from infini_local.core.runtime_authoring.repair.scope import build_runtime_repair_scope
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.terraria_vocabulary import DAMAGE_CLASS_TOKENS
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.pipelines.author.request import build_initial_author_request
from infini_local.qa.capability_witnesses import build_capability_witness
from test_registry_receipt_identity import _call, _receipt

# The registry owns the permitted omission surface. Tests constrain its meaning
# (optional, type-exact neutral, admitted) instead of maintaining a second roster
# that fails whenever another safe omission is registered.
DEFAULTS = {
    fn: {name: spec.default for name, spec in cap.params.items() if spec.default is not None}
    for fn, cap in CAPABILITY_REGISTRY.items()
    if any(spec.default is not None for spec in cap.params.values())
}
DECLARED = {fn: values for fn, values in DEFAULTS.items() if CAPABILITY_REGISTRY[fn].author_visible}
RETAINED_WIRE_DEFAULTS = {fn: values for fn, values in DEFAULTS.items() if not CAPABILITY_REGISTRY[fn].author_visible}
BUFF_NEUTRALS = DECLARED["generated_buff_on_use"]


def _wire_payload(doc):
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    return {key: wire[key] for key in ("runtimeProgram", "gameplay", "accessory", "armor")}


def _stats(*, omit=True):
    source = build_capability_witness("item_stats")
    call = next(c for c in source["runtimeProgram"]["calls"] if c["fn"] == "item_stats")
    call["params"]["manaCost"] = 0
    if omit:
        del call["params"]["manaCost"]
    return source


def _audit(source, compiled, rows):
    return audit_compiler_receipts(rows, authored_document=source, final_document=compiled)


def test_declared_defaults_are_neutral_optional_and_reach_serialized_contract():
    assert DEFAULTS and DECLARED
    for fn, values in DEFAULTS.items():
        for name, value in values.items():
            spec = CAPABILITY_REGISTRY[fn].params[name]
            assert not spec.required, (fn, name)
            assert type(value) is type(spec.neutral) and value == spec.neutral, (fn, name)
            assert not strict_schema_errors(value, spec.schema()), (fn, name)
    _, user, _ = build_initial_author_request({}, {}, "omission-proof", model_name="test-model")
    catalog = json.loads(user)["runtimeCapabilityContract"]["catalog"]
    cards = {c["fn"]: c for c in catalog["capabilities"]}
    schemas = {c["properties"]["fn"]["const"]: c["properties"]["params"]
               for c in capability_provider_union() if "params" in c["properties"]}
    assert set(RETAINED_WIRE_DEFAULTS).isdisjoint(cards)
    assert set(RETAINED_WIRE_DEFAULTS).isdisjoint(schemas)
    for fn, values in DECLARED.items():
        for name, value in values.items():
            assert cards[fn]["params"][name]["optional"] is True
            assert cards[fn]["params"][name]["default"] == value
            variants = schemas[fn].get("oneOf", [schemas[fn]])
            assert any(name not in variant["required"] for variant in variants)
            projected = [variant["properties"][name] for variant in variants if name in variant["properties"]]
            assert projected
            for child in projected:
                assert child["default"] == value and type(child["default"]) is type(value)
                assert child["x-infini-neutral"] == value
                assert not strict_schema_errors(value, child)


@pytest.mark.parametrize(
    "fn,omitted,values",
    [pytest.param(fn, (n,), {}, id=fn + "-" + n) for fn, vs in DECLARED.items() for n in vs
     if CAPABILITY_REGISTRY[fn].params[n].omission_condition is None]
    + [
        pytest.param(
            "item_use",
            tuple(n for n, v in (("holdoutOffsetX", x), ("holdoutOffsetY", y)) if v is None),
            {n: v for n, v in (("holdoutOffsetX", x), ("holdoutOffsetY", y)) if v is not None},
            id=f"x-{x}-y-{y}",
        )
        for x, y in ((None, None), (0, 0), (None, -96), (96, None), (-96, 96), (-96, None), (None, 96))
    ],
)
def test_omission_materializes_only_declared_neutral_with_exact_receipts(fn, omitted, values):
    source = build_capability_witness(fn)
    call = _call(source, fn)
    call["params"].update(values)
    if fn == "set_owner_control":
        # Keep a real independent effect while each neutral leaf is omitted.
        call["params"].update(requireHeldItem=True, animation="keep_alive")
    elif fn == "return_when":
        call["params"]["afterSeconds"] = 1
    for rule in CAPABILITY_REGISTRY[fn].requirements:
        if rule.kind == "timing_pair_or_window" and rule.allow_absent and any(n in rule.any_of for n in omitted):
            # This declared default applies only without either scalar sibling;
            # a valid explicit pair instead preserves its original window absence.
            call["params"].pop(rule.param, None)
            call["params"].pop(rule.other_param, None)
    for param in omitted:
        call["params"][param] = CAPABILITY_REGISTRY[fn].params[param].default
    explicit = compile_runtime_program(source)
    for param in omitted:
        call["params"].pop(param)
    before = deepcopy(source)
    compiled = compile_runtime_program(source)
    assert source == before
    assert {k: compiled[k] for k in ("gameplay", "runtimeProgram", "accessory", "armor")} == {
        k: explicit[k] for k in ("gameplay", "runtimeProgram", "accessory", "armor")
    }
    rows = compiled["runtimeContract"]["finalWireReceipts"]
    for param in omitted:
        selected = [r for r in rows if r.get("callId") == call["id"]
                    and (r.get("authoredPath", "").endswith(".params." + param)
                         or ".params." + param + "." in r.get("authoredPath", ""))]
        assert selected
        spec = CAPABILITY_REGISTRY[fn].params[param]
        for row in selected:
            delivered = _receipt(explicit["runtimeContract"]["finalWireReceipts"], row["finalPath"])
            assert row == {**delivered, "status": "declared_neutral_omission"}
            assert delivered["status"] == "delivered"
            if spec.structured:
                projections = [p for p in spec.projected_fields(spec.default, param)
                               if row["finalPath"].endswith("." + p.wire_path)]
                assert len(projections) == 1 and row["value"] == projections[0].value
            else:
                assert row["value"] == spec.to_wire(spec.default)
    assert _audit(source, compiled, rows)["ok"] and audit_compiler_receipts(rows, final_document=compiled)["ok"]
    assert validate_runtime_wire(compiled)["ok"]
    if fn == "item_stats":
        assert type(compiled["gameplay"]["manaCost"]) is int and compiled["gameplay"]["manaCost"] == 0
        call["params"]["manaCost"] = 7
        assert _wire_payload(source)["gameplay"]["manaCost"] == 7


# Null, text and JSON-kind rejection share the same shape owner. Exercise each
# capability's indexed error routing once rather than crossing every bad type.
@pytest.mark.parametrize("fn,label", [
    ("spawn", "null"),
    ("projectile_collision", "text"),
    ("set_aim", "wrong-json-type"),
    ("attach", "null"),
    ("return_when", "wrong-json-type"),
    ("rotate_sprite", "wrong-json-type"),
    ("set_owner_control", "null"),
    ("spawn_on_event", "wrong-json-type"),
    ("item_stats", "wrong-json-type"),
    ("item_use", "null"),
    ("target_and_fire", "text"),
    ("generated_buff_on_use", "wrong-json-type"),
])
def test_optional_shape_owner_reports_every_broken_indexed_leaf(fn, label):
    doc = build_capability_witness(fn)
    index, call = next((i, row) for i, row in enumerate(doc["runtimeProgram"]["calls"]) if row["fn"] == fn)
    for name in DECLARED[fn]:
        spec = CAPABILITY_REGISTRY[fn].params[name]
        call["params"][name] = None if label == "null" else "missing" if label == "text" else False if spec.kind != "boolean" else 0
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    paths = {e["path"] for e in report["errors"]}
    assert not report["ok"] and {f"$.runtimeProgram.calls[{index}].params.{name}" for name in DECLARED[fn]} <= paths, report
    with pytest.raises(ValueError, match="runtime program rejected"):
        compile_runtime_program(doc)
    assert doc == before


MANA_SPEC = CAPABILITY_REGISTRY["item_stats"].params["manaCost"]


@settings(max_examples=40, derandomize=True, deadline=None)
@example(damage_class="magic", value=17, omitted=False)
@example(damage_class="default", value=17, omitted=True)
@given(
    damage_class=st.sampled_from(DAMAGE_CLASS_TOKENS),
    value=st.integers(min_value=MANA_SPEC.minimum, max_value=MANA_SPEC.maximum),
    omitted=st.booleans(),
)
def test_mana_presence_and_value_are_independent_of_damage_class(damage_class, value, omitted):
    doc = _stats(omit=omitted)
    params = _call(doc, "item_stats")["params"]
    params["damageClass"] = damage_class
    if not omitted:
        params["manaCost"] = value
    before = deepcopy(doc)
    wire = compile_runtime_program(doc)
    expected = 0 if omitted else value
    assert type(wire["gameplay"]["manaCost"]) is int
    assert wire["gameplay"]["manaCost"] == expected
    row = _receipt(wire["runtimeContract"]["finalWireReceipts"], "gameplay.manaCost")
    assert row["value"] == expected
    assert row["status"] == ("declared_neutral_omission" if omitted else "delivered")
    assert validate_runtime_wire(wire)["ok"]
    assert doc == before


# Absence and explicit zero are covered above; these are independent refusal
# classes and the two endpoints declared by the current public parameter.
@pytest.mark.parametrize("value,accepted", [
    pytest.param(MANA_SPEC.minimum, True, id="minimum"),
    pytest.param(MANA_SPEC.maximum, True, id="maximum"),
    pytest.param(str(MANA_SPEC.minimum), False, id="text"),
    pytest.param(MANA_SPEC.minimum - 1, False, id="below-minimum"),
    pytest.param(MANA_SPEC.maximum + 1, False, id="above-maximum"),
])
def test_present_optional_mana_keeps_bounds_and_literal_projection(value, accepted):
    doc = _stats(omit=False)
    _call(doc, "item_stats")["params"]["manaCost"] = value
    before = deepcopy(doc)
    if accepted:
        wire = compile_runtime_program(doc)
        assert wire["gameplay"]["manaCost"] == value
        row = _receipt(wire["runtimeContract"]["finalWireReceipts"], "gameplay.manaCost")
        assert row["value"] == value and row["status"] == "delivered"
        assert validate_runtime_wire(wire)["ok"]
    else:
        report = validate_runtime_program(doc)
        assert not report["ok"] and any(e["path"].endswith(".params.manaCost") for e in report["errors"])
        with pytest.raises(ValueError, match="runtime program rejected"):
            compile_runtime_program(doc)
    assert doc == before


@pytest.mark.parametrize("active", [False, True], ids=["inert", "selected-light"])
def test_joint_buff_omissions_preserve_light_or_reject_inert(active):
    # Complete joint omission is the composition boundary. Individual omissions
    # have exact receipt ownership above; each sole effect is exercised in wire tests.
    explicit = build_capability_witness("generated_buff_on_use")
    params = _call(explicit, "generated_buff_on_use")["params"]
    params.update(BUFF_NEUTRALS)
    if not active:
        params["lightStrength"] = 0
    sparse = deepcopy(explicit)
    for name in BUFF_NEUTRALS:
        _call(sparse, "generated_buff_on_use")["params"].pop(name)
    if active:
        assert _wire_payload(sparse) == _wire_payload(explicit)
    else:
        report = validate_runtime_program(sparse)
        assert not report["ok"] and any(e["code"] == "inert_component" for e in report["errors"])
        with pytest.raises(ValueError):
            compile_runtime_program(sparse)


@pytest.mark.parametrize(
    "fn,names,present",
    [
        pytest.param(fn, names, present, id=fn + "-" + "".join("1" if v else "0" for v in present))
        for fn, names in (
            ("generated_buff_on_use", ("lightStrength", "lightColor")),
            ("restore_resources_on_use", ("healLife", "healMana")),
            ("tool_stats", ("pickPower", "axePower", "hammerPower", "miningSpeedMultiplier")),
            ("projectile_collision", ("immunity", "updatesPerTick")),
            ("beam_geometry", ("length", "widthBlocks")),
        )
        for present in ([(False,) * len(names), (True,) * len(names)]
                        + [tuple(j != i for j in range(len(names))) for i in range(len(names))]
                        if len(names) > 2 else product([False, True], repeat=len(names)))
    ],
)
def test_coupled_parameters_do_not_gain_omission_permission(fn, names, present):
    doc = build_capability_witness(fn)
    for name, keep in zip(names, present):
        if not keep:
            _call(doc, fn)["params"].pop(name)
    assert validate_runtime_program(doc)["ok"] is all(present)


@pytest.mark.parametrize("original_mana,patch_mana", [(9, None), (None, 12)])
def test_repair_omission_is_no_change_and_valid_absence_stays_frozen(original_mana, patch_mana):

    doc = build_capability_witness("item_stats")
    call = _call(doc, "item_stats")
    call["params"]["damage"] = -1
    if original_mana is None:
        call["params"].pop("manaCost")
    else:
        call["params"]["manaCost"] = original_mana
    errors = validate_runtime_program(doc)["errors"]
    scope = build_runtime_repair_scope(doc, errors)
    fixed = deepcopy(call)
    fixed["params"]["damage"] = 20
    if patch_mana is None:
        fixed["params"].pop("manaCost", None)
    else:
        fixed["params"]["manaCost"] = patch_mana
    filtered, audit = filter_repair_patch_scope(doc, {"callsUpsert": [fixed], "note": "repair damage only"}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(doc, filtered)
    assert _call(repaired, "item_stats")["params"].get("manaCost") == original_mana
    assert _wire_payload(repaired)["gameplay"]["manaCost"] == (0 if original_mana is None else original_mana)


@pytest.mark.parametrize(
    "fn,mutation,code",
    [
        pytest.param("charge", "channel", "missing_item_capability_param", id="channel-remains-explicit"),
        pytest.param("generated_buff_on_use", "binding", "missing_binding_dependency", id="buff-keeps-executable-binding"),
    ],
)
def test_sparse_author_still_requires_executable_dependencies(fn, mutation, code):
    doc = build_capability_witness(fn)
    optional_fn = "item_use" if mutation == "channel" else fn
    params = _call(doc, optional_fn)["params"]
    for param in DECLARED[optional_fn]:
        params.pop(param)
    assert validate_runtime_program(doc)["ok"]
    if mutation == "channel":
        params["channel"] = False
    else:
        doc["runtimeProgram"]["bindings"] = []
    report = validate_runtime_program(doc)
    assert not report["ok"] and any(e["code"] == code for e in report["errors"])


@pytest.mark.parametrize(
    "mutation,bad,tamper_receipt,final_only,wire_rejects",
    [
        pytest.param(m, None, False, m != "reclassify", m != "reclassify", id=m)
        for m in ("swap_path", "change_value", "reclassify", "remove", "duplicate")
    ]
    + [pytest.param(m, None, False, False, False, id=m) for m in ("explicit-as-omitted", "wrong-call", "missing-wire-and-receipt")]
    + [
        pytest.param("wrong-zero-type", v, t, True, True, id=label + "-" + ("receipt-and-wire" if t else "wire-only"))
        for label, v in (("boolean", False), ("float", 0.0))
        for t in (False, True)
    ]
    + [pytest.param("multi-output-missing", None, False, True, False, id="holdout-secondary-projection-missing")],
)
def test_omission_provenance_rejects_every_forged_source_type_or_output(mutation, bad, tamper_receipt, final_only, wire_rejects):
    source = (
        build_capability_witness("item_use")
        if mutation == "multi-output-missing"
        else _stats(omit=mutation != "explicit-as-omitted")
    )
    if mutation == "multi-output-missing":
        call = _call(source, "item_use")
        call["params"].pop("holdoutOffsetX")
        call["params"]["holdoutOffsetY"] = 0
    else:
        _call(source, "item_stats")["params"]["damage"] = 0
    compiled = compile_runtime_program(source)
    rows = deepcopy(compiled["runtimeContract"]["finalWireReceipts"])
    row = _receipt(rows, "runtimeProgram.itemUse.holdoutOffsetX" if mutation == "multi-output-missing" else "gameplay.manaCost")
    if mutation == "multi-output-missing":
        assert compiled["gameplay"]["holdoutOffsetX"] == compiled["runtimeProgram"]["itemUse"]["holdoutOffsetX"] == 0
        for prefix in ("gameplay", "runtimeProgram.itemUse"):
            assert _receipt(rows, prefix + ".holdoutOffsetX")["status"] == "declared_neutral_omission"
            assert _receipt(rows, prefix + ".holdoutOffsetY")["status"] == "delivered"
        assert _audit(source, compiled, rows)["ok"]
        rows.remove(row)
    elif mutation == "swap_path":
        other = _receipt(rows, "gameplay.damage")
        assert row["value"] == other["value"] == 0
        row["finalPath"], other["finalPath"] = other["finalPath"], row["finalPath"]
    elif mutation == "change_value":
        row["value"] = 1
    elif mutation == "reclassify":
        row["status"] = "delivered"
    elif mutation == "remove":
        rows.remove(row)
    elif mutation == "duplicate":
        rows.append(deepcopy(row))
    elif mutation == "explicit-as-omitted":
        row["status"] = "declared_neutral_omission"
    elif mutation == "wrong-call":
        row["callId"] = "not_the_call"
    elif mutation == "missing-wire-and-receipt":
        rows.remove(row)
        del compiled["gameplay"]["manaCost"]
    else:
        if tamper_receipt:
            row["value"] = bad
        compiled["gameplay"]["manaCost"] = bad
    assert not _audit(source, compiled, rows)["ok"]
    if final_only:
        assert not audit_compiler_receipts(rows, final_document=compiled)["ok"]
    if wire_rejects:
        compiled["runtimeContract"]["finalWireReceipts"] = rows
        assert not validate_runtime_wire(compiled)["ok"]


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"default": None}, id="absent-default"),
        pytest.param({"default": 1}, id="nonneutral-default"),
        pytest.param({"default": False}, id="equal-value-wrong-json-type"),
        pytest.param({"required": True}, id="required"),
    ],
)
def test_omission_audit_consumes_registry_default_neutral_and_required(monkeypatch, changes):
    source = _stats()
    compiled = compile_runtime_program(source)
    rows = compiled["runtimeContract"]["finalWireReceipts"]
    cap = CAPABILITY_REGISTRY["item_stats"]
    changed = replace(cap, params={**cap.params, "manaCost": replace(cap.params["manaCost"], **changes)})
    monkeypatch.setattr(technical_lowering, "CAPABILITY_REGISTRY", {**CAPABILITY_REGISTRY, cap.name: changed})
    assert not _audit(source, compiled, rows)["ok"]
    assert not audit_compiler_receipts(rows, final_document=compiled)["ok"]


@pytest.mark.parametrize(
    "provenance,accepted",
    [
        pytest.param("absent", True, id="legacy-without-provenance"),
        pytest.param(None, False, id="null"),
        pytest.param({}, False, id="empty-object"),
        pytest.param({"finalWireReceipts": []}, False, id="empty-receipts"),
    ],
)
def test_wire_provenance_is_optional_but_present_must_be_complete(provenance, accepted):
    wire = compile_runtime_program(_stats())
    if provenance == "absent":
        wire.pop("runtimeContract")
    else:
        wire["runtimeContract"] = provenance
    assert validate_runtime_wire(wire)["ok"] is accepted


@pytest.mark.parametrize("fn,broken,good,frozen,present,hostile", [
    ("set_aim", "source", "initial", "turnOwner", True, False),
    ("attach", "anchor", "owner_center", "axisOffsetBlocks", 2, 3),
    ("rotate_sprite", "mode", "axis", "offsetRadians", 0.3, 0.4),
    ("return_when", "afterSeconds", 1, "onTileCollision", True, False),
    ("set_owner_control", "lifetime", "authored", "requireHeldItem", True, False),
])
@pytest.mark.parametrize("explicit", [False, True], ids=["accepted-absence", "explicit-nonneutral"])
def test_independent_primitive_repair_freezes_valid_absence_and_present_choice(fn, broken, good, frozen, present, hostile, explicit):
    doc = build_capability_witness(fn)
    call = _call(doc, fn)
    if fn == "set_owner_control":
        call["params"]["claimHeldProjectile"] = True
    elif fn == "return_when":
        call["params"]["ownerDistance"] = 3
    if explicit:
        call["params"][frozen] = present
    else:
        call["params"].pop(frozen, None)
    call["params"][broken] = good
    assert validate_runtime_program(doc)["ok"]
    call["params"][broken] = "invalid-choice"
    before = deepcopy(doc)
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    paths = ["params." + broken]
    if fn == "rotate_sprite":
        # An unknown mode cannot authenticate the contextual non-spin rate omission.
        paths.append("params.radiansPerSecond")
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": paths}]
    candidate = deepcopy(call)
    candidate["params"][broken] = good
    candidate["params"][frozen] = hostile if explicit else present
    filtered, audit = filter_repair_patch_scope(doc, {"callsUpsert": [candidate], "note": "repair exact primitive leaf"}, scope)
    assert audit["ok"] and audit["ignoredChanges"], audit
    repaired = apply_repair_patch(doc, filtered)
    actual = _call(repaired, fn)["params"]
    assert actual[broken] == good
    if explicit:
        assert actual[frozen] == present and type(actual[frozen]) is type(present)
    else:
        assert frozen not in actual
    wire = compile_runtime_program(repaired)
    assert validate_runtime_wire(wire)["ok"]
    rows = [r for r in wire["runtimeContract"]["finalWireReceipts"]
            if r.get("callId") == call["id"] and r["authoredPath"].endswith(".params." + frozen)]
    assert len(rows) == 1
    assert rows[0]["status"] == ("delivered" if explicit else "declared_neutral_omission")
    assert doc == before


@pytest.mark.parametrize("fn,params,code", [
    ("set_owner_control", {}, "inert_component"),
    ("set_owner_control", DECLARED["set_owner_control"], "inert_component"),
    ("return_when", {}, "empty_component"),
    ("return_when", DECLARED["return_when"], "empty_component"),
])
def test_neutral_omission_never_creates_an_owner_effect_or_return_trigger(fn, params, code):
    doc = build_capability_witness(fn)
    _call(doc, fn)["params"] = deepcopy(params)
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert not report["ok"] and code in {e["code"] for e in report["errors"]}, report
    with pytest.raises(ValueError):
        compile_runtime_program(doc)
    assert doc == before
