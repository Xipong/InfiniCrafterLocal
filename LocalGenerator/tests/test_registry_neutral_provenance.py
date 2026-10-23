"""Declared full-Author neutrals, exact omission provenance, and frozen Repair absence."""

from copy import deepcopy
from dataclasses import replace
from itertools import product
import json
import pytest
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.core.runtime_authoring.program_schema import apply_repair_patch
from infini_local.core.runtime_authoring.repair_scope import build_runtime_repair_scope, filter_repair_patch_scope
import infini_local.core.runtime_authoring.technical_lowering as technical_lowering
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.program_schema import strict_schema_errors
from infini_local.qa.capability_witnesses import build_capability_witness
from test_registry_receipt_identity import _call, _receipt
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request, build_gameplay_repair_dossier

DECLARED = {
    "present_placed_item_sprite": {"pivotSpace": "frame"},
    "configure_spawn": {"count": 1, "spreadRadians": 0},
    "set_projectile_collision": {"bounceCount": 0, "bounceSpeedRetention": 1},
    "channel_beam": {"manaPayment": "initial_use_only", "initialDamageMultiplier": 1.0,
                     "initialWidthMultiplier": 1.0, "damageStartProgress": 1.0, "raycastTiles": False},
    "configure_item_stats": {"manaCost": 0, "manaCostInput": "both"},
    "configure_item_use": {"holdoutOffsetX": 0, "holdoutOffsetY": 0},
    "target_and_fire": {"count": 1, "spreadRadians": 0.0, "targetPolicy": "distance_score",
                        "requireLineOfSight": False, "hardRange": False,
                        "minimumRangeTiles": 0, "coneRadians": 6.283185307179586,
                        "coneDirection": "owner_facing", "bossFilter": "any",
                        "minimumHealthRatio": 0, "maximumHealthRatio": 1,
                        "targetPriority": "distance",
                        },
    "apply_generated_buff_on_use": {
        "miningSpeedMultiplier": 1,
        "oreSenseEnabled": False,
        "moveSpeedBonusPercent": 0,
        "jumpSpeedBonusBlocksPerSecond": 0.0,
        "manaRegenBonusPoints": 0,
        "lifeRegenHpPerSecond": 0,
    },
}
BUFF_NEUTRALS = DECLARED["apply_generated_buff_on_use"]


def _wire_payload(doc):
    wire = compile_runtime_program(doc)
    assert validate_runtime_wire(wire)["ok"]
    return {key: wire[key] for key in ("runtimeProgram", "gameplay", "accessory", "armor")}


def _stats(*, omit=True):
    source = build_capability_witness("configure_item_stats")
    call = next(c for c in source["runtimeProgram"]["calls"] if c["fn"] == "configure_item_stats")
    call["params"]["manaCost"] = 0
    if omit:
        del call["params"]["manaCost"]
    return source


def _audit(source, compiled, rows):
    return audit_compiler_receipts(rows, authored_document=source, final_document=compiled)


def test_declared_omission_roster_matches_registry_and_serialized_contract():
    actual = {
        fn: {n: s.default for n, s in c.params.items() if s.default is not None}
        for fn, c in CAPABILITY_REGISTRY.items()
        if any(s.default is not None for s in c.params.values())
    }
    assert actual == DECLARED
    _, user, _ = build_initial_author_request({}, {}, "omission-proof", model_name="test-model")
    catalog = json.loads(user)["runtimeCapabilityContract"]["catalog"]
    cards = {c["fn"]: c for c in catalog["capabilities"]}
    for fn, values in actual.items():
        for name, value in values.items():
            spec = CAPABILITY_REGISTRY[fn].params[name]
            assert not spec.required and spec.neutral == value and type(spec.neutral) is type(value)
            assert not strict_schema_errors(value, spec.schema())
            assert cards[fn]["params"][name]["optional"] is True
            assert cards[fn]["params"][name]["default"] == value
    guide = catalog["fieldGuide"]["paramNotation"]
    assert "default" in guide and "full Author" in guide and "not universal" in guide
    doc = build_capability_witness("configure_item_stats")
    _call(doc, "configure_item_stats")["params"]["damage"] = -1
    dossier = build_gameplay_repair_dossier(doc, {}, {}, failure_report=validate_runtime_program(doc))
    assert "omission means no change" in " ".join(json.loads(json.dumps(dossier))["rules"])


@pytest.mark.parametrize(
    "fn,omitted,values",
    [pytest.param(fn, (n,), {}, id=fn + "-" + n) for fn, vs in DECLARED.items() for n in vs
     if CAPABILITY_REGISTRY[fn].params[n].omission_condition is None]
    + [
        pytest.param("configure_item_stats", ("manaCost",), {"damageClass": dc}, id="mana-" + dc)
        for dc in ("melee", "ranged", "magic", "summon", "default")
    ]
    + [
        pytest.param(
            "configure_item_use",
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
        selected = [r for r in rows if r.get("callId") == call["id"] and r.get("authoredPath", "").endswith(".params." + param)]
        assert selected
        for row in selected:
            delivered = _receipt(explicit["runtimeContract"]["finalWireReceipts"], row["finalPath"])
            assert row == {**delivered, "status": "declared_neutral_omission"}
            assert delivered["status"] == "delivered" and row["value"] == CAPABILITY_REGISTRY[fn].params[param].to_wire(
                CAPABILITY_REGISTRY[fn].params[param].default
            )
    assert _audit(source, compiled, rows)["ok"] and audit_compiler_receipts(rows, final_document=compiled)["ok"]
    assert validate_runtime_wire(compiled)["ok"]
    if fn == "configure_item_stats":
        assert type(compiled["gameplay"]["manaCost"]) is int and compiled["gameplay"]["manaCost"] == 0
        call["params"]["manaCost"] = 7
        assert _wire_payload(source)["gameplay"]["manaCost"] == 7


# Null, text and JSON-kind rejection share the same shape owner. Exercise each
# capability's indexed error routing once rather than crossing every bad type.
@pytest.mark.parametrize("fn,label", [
    ("configure_spawn", "null"),
    ("set_projectile_collision", "text"),
    ("channel_beam", "wrong-json-type"),
    ("configure_item_stats", "wrong-json-type"),
    ("configure_item_use", "null"),
    ("target_and_fire", "text"),
    ("apply_generated_buff_on_use", "wrong-json-type"),
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


# Numeric units/projections belong to test_registry_author_units. Here the
# optional leaf must distinguish absence from a present invalid or boundary value.
@pytest.mark.parametrize("value,accepted", [(0, True), (500, True), ("0", False), (-1, False), (501, False)])
def test_present_optional_mana_keeps_bounds_and_literal_projection(value, accepted):
    doc = _stats(omit=False)
    _call(doc, "configure_item_stats")["params"]["manaCost"] = value
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
    explicit = build_capability_witness("apply_generated_buff_on_use")
    params = _call(explicit, "apply_generated_buff_on_use")["params"]
    params.update(BUFF_NEUTRALS)
    if not active:
        params["lightStrength"] = 0
    sparse = deepcopy(explicit)
    for name in BUFF_NEUTRALS:
        _call(sparse, "apply_generated_buff_on_use")["params"].pop(name)
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
            ("apply_generated_buff_on_use", ("lightStrength", "lightColor")),
            ("restore_resources_on_use", ("healLife", "healMana")),
            ("configure_tool", ("pickPower", "axePowerTooltipPercent", "hammerPower", "miningSpeedMultiplier")),
            ("set_projectile_collision", ("immunity", "updatesPerTick")),
            ("move_boomerang", ("returnAfterSeconds", "returnSpeedBlocksPerSecond")),
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

    doc = build_capability_witness("configure_item_stats")
    call = _call(doc, "configure_item_stats")
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
    assert _call(repaired, "configure_item_stats")["params"].get("manaCost") == original_mana
    assert _wire_payload(repaired)["gameplay"]["manaCost"] == (0 if original_mana is None else original_mana)


@pytest.mark.parametrize(
    "fn,mutation,code",
    [
        pytest.param("channel_beam", "channel", "missing_item_capability_param", id="channel-remains-explicit"),
        pytest.param("apply_generated_buff_on_use", "binding", "missing_binding_dependency", id="buff-keeps-executable-binding"),
    ],
)
def test_sparse_author_still_requires_executable_dependencies(fn, mutation, code):
    doc = build_capability_witness(fn)
    optional_fn = "configure_item_use" if mutation == "channel" else fn
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
        build_capability_witness("configure_item_use")
        if mutation == "multi-output-missing"
        else _stats(omit=mutation != "explicit-as-omitted")
    )
    if mutation == "multi-output-missing":
        call = _call(source, "configure_item_use")
        call["params"].pop("holdoutOffsetX")
        call["params"]["holdoutOffsetY"] = 0
    else:
        _call(source, "configure_item_stats")["params"]["damage"] = 0
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
        pytest.param({"required": True}, id="required"),
    ],
)
def test_omission_audit_consumes_registry_default_neutral_and_required(monkeypatch, changes):
    source = _stats()
    compiled = compile_runtime_program(source)
    rows = compiled["runtimeContract"]["finalWireReceipts"]
    cap = CAPABILITY_REGISTRY["configure_item_stats"]
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
