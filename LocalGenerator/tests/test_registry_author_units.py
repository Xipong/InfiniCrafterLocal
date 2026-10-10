"""Author units -> compiler receipts -> frozen C# wire: no aliases or quantization."""

from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_SCHEMA, visible_capabilities
from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType
import hashlib
import json
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
from infini_local.core.runtime_authoring import compiler, technical_lowering
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
    ("apply_generated_buff_on_use", "movementSpeed", "moveSpeedBonusFactor", 0.1875, "generatedBuff"),
    ("apply_generated_buff_on_use", "jumpBoost", "jumpSpeedBonusPxPerTick", 0.1875, "generatedBuff"),
    ("apply_generated_buff_on_use", "manaRegen", "manaRegenBonusPoints", 7, "generatedBuff"),
)


def _registry_with_rename(monkeypatch, fn, old, new):
    registry = dict(CAPABILITY_REGISTRY)
    cap = registry[fn]
    params = dict(cap.params)
    spec = params.pop(old, None)
    if spec is None:
        spec = params[new]
    params[new] = replace(spec, wire_name=spec.wire_name or old)
    paths = tuple(
        path.removesuffix("." + new) + "." + (spec.wire_name or old) if path.endswith("." + new) else path for path in cap.final_wire_paths
    )
    registry[fn] = replace(cap, params=MappingProxyType(params), final_wire_paths=paths)
    monkeypatch.setattr(compiler, "CAPABILITY_REGISTRY", registry)
    monkeypatch.setattr(technical_lowering, "CAPABILITY_REGISTRY", registry)
    return registry[fn]


def _project(fn, new, value):
    call = {
        "id": "renamed",
        "fn": fn,
        "target": "item" if compiler.CAPABILITY_REGISTRY[fn].target_kinds == ("item_body",) else "shot",
        "_sourceIndex": 0,
        "params": {
            # This test calls the isolated projector, not the full compiler
            # that materializes omissions. Author neutrals explicitly here.
            **{name: spec.default for name, spec in compiler.CAPABILITY_REGISTRY[fn].params.items() if spec.default is not None},
            new: value,
        },
    }
    ctx = compiler._CompileContext(receipts=[])
    if call["target"] == "item":
        gameplay, runtime = {}, {}
        compiler._compile_item_call(
            ctx, call, gameplay=gameplay, accessory={}, armor={}, runtime=runtime, item_entity={}, entity_index=0, equipment_config=""
        )
        final = {"gameplay": gameplay, "runtimeProgram": runtime}
    else:
        entity = {"id": call["target"]}
        compiler._compile_entity_call(ctx, call, entity=entity, entity_index=0)
        final = {"runtimeProgram": {"entities": [entity]}}
    return call, ctx.receipts, final


def _get(document, path):
    import re

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
def test_identity_rename_reaches_packet_projector_and_frozen_wire(monkeypatch, author_cards, fn, old, new, value, component):
    cap = CAPABILITY_REGISTRY[fn]
    spec = cap.params[new]
    assert old not in cap.params and old not in author_cards[fn]["params"]
    assert new in author_cards[fn]["params"] and spec.wire_name
    assert any(path.endswith("." + spec.wire_name) for path in cap.final_wire_paths)
    for boundary in (spec.minimum, spec.maximum, spec.neutral):
        if boundary is not None:
            assert spec.to_wire(boundary) == boundary
    # Substitution proves registry consumption, independently of the full compiler.
    with monkeypatch.context() as patch:
        _registry_with_rename(patch, fn, old, new)
        call, receipts, final = _project(fn, new, value)
        selected = [r for r in receipts if r.get("authoredPath") == f"runtimeProgram.calls[0].params.{new}"]
        assert selected
        assert all(r["finalPath"].endswith("." + spec.wire_name) and _get(final, r["finalPath"]) == value for r in selected)
        if isinstance(value, float):
            assert all(struct.pack("!d", _get(final, r["finalPath"])) == struct.pack("!d", value) for r in selected)
        assert technical_lowering.audit_compiler_receipts(
            receipts, authored_document={"runtimeProgram": {"schema": RUNTIME_PROGRAM_SCHEMA, "calls": [call]}}, final_document=final
        )["ok"]
    authored = build_capability_witness(fn)
    call = next(c for c in authored["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    call["params"][new] = value
    wire = compile_runtime_program(authored)
    assert validate_runtime_wire(wire)["ok"]
    rows = [
        r
        for r in wire["runtimeContract"]["finalWireReceipts"]
        if r.get("callId") == "witness_call" and r.get("authoredPath", "").endswith(".params." + new)
    ]
    assert rows
    assert all(r["finalPath"].endswith("." + spec.wire_name) and _get(wire, r["finalPath"]) == value for r in rows)
    if isinstance(value, float):
        assert all(struct.pack("!d", _get(wire, r["finalPath"])) == struct.pack("!d", value) for r in rows)
    alias = deepcopy(authored)
    alias_call = next(c for c in alias["runtimeProgram"]["calls"] if c["id"] == "witness_call")
    alias_call["params"][old] = alias_call["params"].pop(new)
    assert not validate_runtime_program(alias)["ok"]
    if component in {"spawn", "collision", "movement.params", "itemUse"}:
        row = next(r for r in rows if r["finalPath"].startswith("runtimeProgram."))
        prefix, _, wire_key = row["finalPath"].rpartition(".")
        container = _get(wire, prefix)
        container[new] = container.pop(wire_key)
        errors = validate_runtime_wire(wire)["errors"]
        assert any(e["code"] == "unknown_final_wire_field" and e["path"].endswith("." + new) for e in errors)


@pytest.mark.parametrize(
    "field,path",
    [
        pytest.param("authoredPath", "runtimeProgram.calls[0].params.speedPxPerTick", id="stale-source"),
        pytest.param("finalPath", "runtimeProgram.entities[0].spawn.count", id="wrong-output"),
    ],
)
def test_renamed_receipt_identity_cannot_be_forged(monkeypatch, field, path):
    call, rows, final = _project("configure_spawn", "velocity", {"constantSpeedPxPerUpdate": 7.125})
    next(r for r in rows if r.get("authoredPath", "").endswith(".velocity.constantSpeedPxPerUpdate"))[field] = path
    assert not technical_lowering.audit_compiler_receipts(
        rows, authored_document={"runtimeProgram": {"schema": RUNTIME_PROGRAM_SCHEMA, "calls": [call]}}, final_document=final
    )["ok"]


def test_buff_factor_keeps_binary64_without_percent_roundtrip():
    value = 1.770282212988338
    authored = build_capability_witness("apply_generated_buff_on_use")
    call = next(row for row in authored["runtimeProgram"]["calls"] if row["id"] == "witness_call")
    call["params"]["moveSpeedBonusFactor"] = value
    wire = compiler.compile_runtime_program(authored)
    projected = wire["gameplay"]["generatedBuff"]["movementSpeed"]
    assert struct.pack("!d", projected) == struct.pack("!d", value)
    assert struct.pack("!d", projected) != struct.pack("!d", value * 100 / 100)


def test_fractional_author_unit_keeps_integer_saved_equipment_clamps():
    root = Path(__file__).resolve().parents[2]
    render = runpy.run_path(str(root / "tools/generate_equipment_bounds.py"))["render"]
    assert render() == (root / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedEquipmentBounds.g.cs").read_text()


def _stat_spec(fn, param):
    parts = param.split(".")
    spec = CAPABILITY_REGISTRY[fn].params[parts[0]]
    for part in parts[1:]:
        spec = spec.properties[part]
    return spec


def _set_stat(params, path, value):
    parts = path.split(".")
    for part in parts[:-1]:
        params = params.setdefault(part, {})
    params[parts[-1]] = value


# The old engine domains are exhausted as visible pytest cases, not hidden loops.
@pytest.mark.parametrize(
    "fn,param,path,author_per_engine,divisor,multiplier,old",
    [
        pytest.param(fn, param, path, scale, divisor, multiplier, old, id=f"{fn}-{param}-engine-{old}")
        for fn, param, path, scale, divisor, multiplier, domain in (
            ("configure_tool", "axePowerTooltipPercent", "gameplay.axePower", 5, 5, 1, range(101)),
            (FN, "lifeRegenHpPerSecond", "gameplay.generatedBuff.lifeRegen", 0.5, 1, 2, range(121)),
            (FN, "manaRegenBonusPoints", "gameplay.generatedBuff.manaRegen", 1, 1, 1, range(121)),
            ("configure_accessory", "lifeRegenHpPerSecond", "accessory.lifeRegen", 0.5, 1, 2, range(-100, 201)),
            ("configure_armor", "lifeRegenHpPerSecond", "armor.lifeRegen", 0.5, 1, 2, range(-100, 201)),
            ("configure_armor", "setBonuses.lifeRegenHpPerSecond", "armor.setBonusLifeRegen", 0.5, 1, 2, range(-100, 201)),
        )
        for old in domain
    ],
)
def test_discrete_author_units_exhaust_engine_domain(fn, param, path, author_per_engine, divisor, multiplier, old):
    spec = _stat_spec(fn, param)
    # The human unit is an independent historical contract, not derived from
    # the current converter: corrupting a registry scale must not cancel out.
    assert (spec.wire_divisor, spec.wire_multiplier) == (divisor, multiplier)
    human = old * author_per_engine
    if spec.kind == "integer":
        human = int(human)
    assert spec.to_wire(human) == old and isinstance(spec.to_wire(human), int)
    assert spec.to_wire(human) * spec.wire_divisor / spec.wire_multiplier == human
    doc = build_capability_witness(fn)
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)
    _set_stat(call["params"], param, human)
    if fn == FN:
        call["params"]["oreSenseEnabled"] = True
    wire = compile_runtime_program(doc)
    assert type(_get(wire, path)) is int and _get(wire, path) == old
    assert validate_runtime_wire(wire)["ok"]
    assert any(
        r.get("authoredPath", "").endswith(".params." + param) and r["finalPath"] == path and r["value"] == old
        for r in wire["runtimeContract"]["finalWireReceipts"]
    )
    for name, continuous in CAPABILITY_REGISTRY[FN].params.items():
        if continuous.consumer_storage:
            assert continuous.consumer_value_error(continuous.neutral) is None


@pytest.mark.parametrize(
    "fn,param,old,minimum,maximum,step,bad",
    [
        pytest.param(fn, param, old, minimum, maximum, step, bad, id=f"{fn}-{param}-{bad}")
        for fn, param, old, minimum, maximum, step, bads in (
            ("configure_tool", "axePowerTooltipPercent", "axePower", 0, 500, 5, (1, 501)),
            (FN, "lifeRegenHpPerSecond", "lifeRegen", 0, 60, 0.5, (0.25, 60.5)),
            ("configure_accessory", "lifeRegenHpPerSecond", "lifeRegenHalfHpPerSecond", -50, 100, 0.5, (-50.5, 100.5, 0.25)),
            ("configure_armor", "lifeRegenHpPerSecond", "lifeRegenHalfHpPerSecond", -50, 100, 0.5, (-50.5, 100.5, 0.25)),
            ("configure_armor", "setBonuses.lifeRegenHpPerSecond", "setBonusLifeRegenHalfHpPerSecond", -50, 100, 0.5, (-50.5, 100.5, 0.25)),
        )
        for bad in bads
    ],
)
def test_discrete_unit_schema_and_rejection(fn, param, old, minimum, maximum, step, bad):
    spec = _stat_spec(fn, param)
    assert (spec.minimum, spec.maximum, spec.multiple_of) == (minimum, maximum, step)
    schema = next(s["properties"]["params"] for s in capability_provider_union() if s["properties"]["fn"]["const"] == fn)
    root_schema = schema
    leaf = param.rsplit(".", 1)[-1]
    for part in param.split(".")[:-1]:
        schema = schema["properties"][part]
    assert leaf in schema["properties"] and old not in root_schema["properties"]
    assert schema["properties"][leaf]["multipleOf"] == step
    assert (leaf in schema["required"]) is spec.required
    if spec.default is not None:
        assert schema["properties"][param]["default"] == 0
    assert param.split(".")[0] in next(c["params"] for c in compact_capability_catalog() if c["fn"] == fn)
    doc = build_capability_witness(fn)
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == fn)
    _set_stat(call["params"], param, bad)
    assert not validate_runtime_program(doc)["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(doc)
    _set_stat(call["params"], param, 0)
    call["params"][old] = 2
    assert not validate_runtime_program(doc)["ok"]


def buff_document(name, value, companion):
    doc = build_capability_witness(FN)
    params = next(c["params"] for c in doc["runtimeProgram"]["calls"] if c["fn"] == FN)
    params.update(
        miningSpeedMultiplier=1,
        lightStrength=0,
        oreSenseEnabled=False,
        moveSpeedBonusFactor=0,
        jumpSpeedBonusPxPerTick=0,
        manaRegenBonusPoints=0,
        lifeRegenHpPerSecond=0,
    )
    params[name] = value
    if companion == "ore":
        params["oreSenseEnabled"] = True
    elif companion == "healing":
        doc["runtimeProgram"]["calls"].append(
            {
                "id": "healing",
                "fn": "restore_resources_on_use",
                "params": {"healLife": 1, "healMana": 0, "usesPotionRules": False},
            }
        )
    return doc


def test_consumer_error_is_registered_for_conditional_repair():
    from infini_local.core.runtime_authoring import VALIDATION_ERROR_CODES, REPAIR_VALIDATION_ERROR_CODES, REPAIR_ERROR_POLICY

    assert "consumer_representability" in VALIDATION_ERROR_CODES
    assert "consumer_representability" in REPAIR_VALIDATION_ERROR_CODES
    assert REPAIR_ERROR_POLICY["consumer_representability"]["llmRepairable"] is True


def test_consumer_collapse_repair_changes_only_the_exact_param():
    from infini_local.core.runtime_authoring import build_runtime_repair_scope, filter_repair_patch_scope, apply_repair_patch
    from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request, build_gameplay_repair_dossier
    import json

    doc = buff_document("miningSpeedMultiplier", 1.000000001, "ore")
    source = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == FN)
    candidate = deepcopy(source)
    candidate["params"].update(miningSpeedMultiplier=1.0005, durationTicks=21600)
    report = validate_runtime_program(doc)
    scope = build_runtime_repair_scope(doc, report["errors"])
    patch = {"note": "exact consumer repair", "realizationReplacement": deepcopy(doc["realization"]), "callsUpsert": [candidate]}
    filtered, audit = filter_repair_patch_scope(doc, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(doc, filtered)
    assert validate_runtime_program(repaired)["ok"]
    actual = next(c for c in repaired["runtimeProgram"]["calls"] if c["fn"] == FN)
    assert actual["params"] == dict(source["params"], miningSpeedMultiplier=1.0005)
    assert compile_runtime_program(repaired)["gameplay"]["generatedBuff"]["miningSpeedMultiplier"] == 1.0005
    _, author_packet, _ = build_initial_author_request({}, {}, {}, {}, "precision", model_name="test-model")
    repair_packet = json.dumps(build_gameplay_repair_dossier(doc, {}, {}, {}, {}, failure_report=report))
    for packet in (author_packet, repair_packet):
        assert "consumerConstraint" in packet and "nonneutral_must_remain_nonneutral" in packet


@pytest.mark.parametrize("companion", ["sole", "ore", "healing"])
@pytest.mark.parametrize(
    "name,value,accepted",
    [
        pytest.param(name, value, accepted, id=f"{name}-{value!r}-{'exact' if accepted else 'collapse'}")
        for name, value, accepted in (
            ("miningSpeedMultiplier", 1.000000001, False),
            ("miningSpeedMultiplier", 0.999999999, False),
            ("moveSpeedBonusFactor", 1e-50, False),
            ("moveSpeedBonusFactor", -1e-50, False),
            ("jumpSpeedBonusPxPerTick", 1e-50, False),
            ("lightStrength", 1e-50, False),
            ("miningSpeedMultiplier", 1.0005, True),
            ("miningSpeedMultiplier", 0.9995, True),
            ("moveSpeedBonusFactor", 0.0005, True),
            ("moveSpeedBonusFactor", -0.0005, True),
            ("jumpSpeedBonusPxPerTick", 0.0005, True),
            ("lightStrength", 0.0005, True),
            ("moveSpeedBonusFactor", 1e-40, True),
            ("miningSpeedMultiplier", 1 + 2**-23, True),
            ("miningSpeedMultiplier", 1 - 2**-24, True),
            ("miningSpeedMultiplier", 1 + 2**-24, False),
            ("miningSpeedMultiplier", 1 - 2**-25, False),
            ("moveSpeedBonusFactor", 2**-149, True),
            ("moveSpeedBonusFactor", -(2**-149), True),
            ("moveSpeedBonusFactor", 2**-150, False),
            ("moveSpeedBonusFactor", -(2**-150), False),
        )
    ],
)
def test_float32_consumer_boundary_is_exact_and_nonmutating(name, value, accepted, companion):
    doc = buff_document(name, value, companion)
    before = deepcopy(doc)
    report = validate_runtime_program(doc)
    assert report["ok"] is accepted, report
    assert doc == before
    if accepted:
        wire = compile_runtime_program(doc)
        assert wire["gameplay"]["generatedBuff"][CAPABILITY_REGISTRY[FN].params[name].wire_name or name] == value
    else:
        assert any(e["code"] == "consumer_representability" and e["path"].endswith(".params." + name) for e in report["errors"])


@pytest.mark.parametrize(
    "name,spec", [pytest.param(name, spec, id=name) for name, spec in CAPABILITY_REGISTRY[FN].params.items() if spec.consumer_storage]
)
def test_float32_constraint_is_model_visible(name, spec):
    constraint = CAPABILITY_REGISTRY[FN].author_prompt_card()["params"][name]["consumerConstraint"]
    assert constraint == spec.schema()["x-infini-consumerConstraint"]
    assert {k: constraint[k] for k in ("storage", "neutral", "rule")} == {
        "storage": "float32",
        "neutral": spec.neutral,
        "rule": "nonneutral_must_remain_nonneutral",
    }
    assert CAPABILITY_REGISTRY[FN].params["moveSpeedBonusFactor"].minimum == -0.5


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


def test_periodic_missing_fields_are_reported_once_by_canonical_shape():
    from infini_local.core.runtime_authoring.program_schema import strict_schema_errors

    cap = CAPABILITY_REGISTRY["spawn_entity_on_event"]
    schema = cap.provider_variant_schema()["properties"]["params"]
    when = schema["properties"]["when"]["oneOf"]
    assert next(row for row in when if row.get("type") == "object")["required"] == ["everyTicks"]
    doc = build_runtime_fixture("workbench_blade")
    params = next(c for c in doc["runtimeProgram"]["calls"] if c["fn"] == cap.name)["params"]
    params["when"] = {}
    params.pop("count")
    errors = strict_schema_errors(params, schema)
    paths = [row["path"] for row in errors if row["kind"] == "required"]
    assert paths.count("$.count") == 1
    assert paths.count("$.when.everyTicks") == 1


def test_generated_lowery_names_current_binding_target_path():
    root = Path(__file__).resolve().parents[2]
    projection = runpy.run_path(str(root / "tools/generate_lowery.py"))
    text = projection["render"]()
    assert "exact `binding.action.targetId`" in text
    assert "exact unique item-body identity" in text
    assert "Wire сохраняет `binding.usePolicy`" in text
    assert "exact `binding.usePolicy.action.targetId`" not in text
    assert "exact `binding.target`" not in text


# Captured scalar-name cases pin complete pre-rename wire and prior receipts.
_SCALAR_NAME_CAPTURE = json.loads((Path(__file__).parent / "fixtures/scalar_author_names_retained_receipts.json").read_text())
_SCALAR_NAME_CASES = _SCALAR_NAME_CAPTURE["cases"]


def _scalar_name_call(document):
    return next(row for row in document["runtimeProgram"]["calls"] if row["id"] == "witness_call")


def _scalar_name_current_source(case):
    # The captured Author is an immutable test oracle, never production input.
    source = deepcopy(case["authored"])
    params = _scalar_name_call(source)["params"]
    assert case["canonicalParameter"] not in params
    params[case["canonicalParameter"]] = params.pop(case["oldParameter"])
    return source


def _scalar_name_restored_wire(case):
    wire = compile_runtime_program(_scalar_name_current_source(case))
    rows = wire["runtimeContract"]["finalWireReceipts"]
    receipt = next(row for row in rows if row.get("callId") == "witness_call"
                   and row.get("authoredPath", "").endswith(".params." + case["canonicalParameter"]))
    expected = deepcopy(case["receipt"])
    expected["authoredPath"] = expected["authoredPath"].removesuffix(case["oldParameter"]) + case["canonicalParameter"]
    assert receipt == expected
    # Restore one pre-change receipt verbatim; every other output byte is pinned.
    receipt.update(deepcopy(case["receipt"]))
    return wire, receipt


def _scalar_name_parent(document, path):
    value = document
    parts = re.findall(r"[A-Za-z][A-Za-z0-9_]*|\[\d+\]", path)
    for part in parts[:-1]:
        value = value[int(part[1:-1])] if part.startswith("[") else value[part]
    return value, parts[-1]


@pytest.mark.parametrize("case", _SCALAR_NAME_CASES, ids=lambda case: case["fn"])
def test_scalar_name_captured_complete_wire_and_old_receipts_remain_exact(case):
    assert _SCALAR_NAME_CAPTURE["originCommit"] == "274d4c38849bff5b8f7ecde1c61d6276a4803712"
    source = _scalar_name_current_source(case)
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(rows, authored_document=source, final_document=wire)["ok"]

    retained, _ = _scalar_name_restored_wire(case)
    canonical_bytes = json.dumps(retained, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert hashlib.sha256(canonical_bytes).hexdigest() == case["compiledSha256"]
    assert validate_runtime_wire(retained)["ok"]
    saved_rows = retained["runtimeContract"]["finalWireReceipts"]
    report = audit_compiler_receipts(saved_rows, final_document=retained)
    assert report["ok"] and report["authoredSourceChecked"] is False
    # Retained receipt support cannot satisfy proof against the current source.
    report = audit_compiler_receipts(saved_rows, authored_document=source, final_document=retained)
    assert not report["ok"]
    assert any(row["reason"] == "compiler receipt used an undeclared authored parameter"
               for row in report["violations"])

    assert not validate_runtime_program(case["authored"])["ok"]
    with pytest.raises(ValueError):
        compile_runtime_program(case["authored"])


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_scalar_name_actual_author_packet_and_repair_schema_expose_only_current_names(monkeypatch, mode):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    request, user, _ = build_initial_author_request({}, {}, {}, {}, "scalar-names", model_name="offline-test")
    assert request["response_format"]["type"] == mode
    cards = {row["fn"]: row for row in json.loads(user)["runtimeCapabilityContract"]["catalog"]["capabilities"]}
    variants = author_item_repair_schema(capability_names=[case["fn"] for case in _SCALAR_NAME_CASES])["properties"]["callsUpsert"]["items"]["oneOf"]
    schemas = [{row["properties"]["fn"]["const"]: row["properties"]["params"] for row in variants}]
    if mode == "json_schema":
        provider_calls = request["response_format"]["json_schema"]["schema"]["properties"]["runtimeProgram"]["properties"]["calls"]["items"]["anyOf"]
        schemas.append({row["properties"]["fn"]["const"]: row["properties"]["params"]
                        for row in provider_calls if "params" in row["properties"]})
    for case in _SCALAR_NAME_CASES:
        fn, old, current = case["fn"], case["oldParameter"], case["canonicalParameter"]
        assert old not in cards[fn]["params"] and current in cards[fn]["params"]
        for group in schemas:
            assert old not in group[fn]["properties"] and current in group[fn]["required"]
        cap = CAPABILITY_REGISTRY[fn]
        assert old not in cap.params and old in cap.retained_receipt_params
        assert cap.params[current].required and cap.params[current].default is None


@pytest.mark.parametrize("case", _SCALAR_NAME_CASES, ids=lambda case: case["fn"])
def test_scalar_name_repair_uses_exact_current_leaf_and_refuses_previous_spelling(case):
    accepted = _scalar_name_current_source(case)
    broken = deepcopy(accepted)
    current = case["canonicalParameter"]
    _scalar_name_call(broken)["params"][current] = CAPABILITY_REGISTRY[case["fn"]].params[current].maximum + 1
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    assert next(row["paths"] for row in scope["fieldPermissions"]["calls"] if row["id"] == "witness_call") == ["params." + current]

    stale_patch = {"note": "old spelling is not a Repair alias", "callsUpsert": [deepcopy(_scalar_name_call(case["authored"]))]}
    assert not strict_repair_structure_report(stale_patch)["ok"]
    assert not strict_repair_shape_report(stale_patch)["ok"]
    _, audit = filter_repair_patch_scope(broken, stale_patch, scope)
    assert not audit["ok"]
    with pytest.raises(ValueError):
        apply_repair_patch(broken, stale_patch)

    frozen = deepcopy(next(row for row in accepted["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats"))
    frozen["params"]["damage"] += 1
    patch = {"note": "repair only the permitted scalar", "callsUpsert": [deepcopy(_scalar_name_call(accepted)), frozen]}
    filtered, audit = filter_repair_patch_scope(broken, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(broken, filtered)
    assert repaired == accepted
    assert validate_runtime_program(repaired)["ok"]


@pytest.mark.parametrize("mutation", ["wrong-output", "out-of-domain", "boolean", "omission"])
@pytest.mark.parametrize("case", _SCALAR_NAME_CASES, ids=lambda case: case["fn"])
def test_scalar_name_retained_receipt_cannot_widen_domain_or_forge_projection(case, mutation):
    wire, receipt = _scalar_name_restored_wire(case)
    if mutation == "wrong-output":
        receipt["finalPath"] = "gameplay.damage"
    elif mutation == "omission":
        receipt["status"] = "declared_neutral_omission"
    else:
        parent, key = _scalar_name_parent(wire, receipt["finalPath"])
        value = True if mutation == "boolean" else CAPABILITY_REGISTRY[case["fn"]].params[case["canonicalParameter"]].maximum + 1
        parent[key] = receipt["value"] = value
    report = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)
    assert not report["ok"]
    assert any(row["reason"] == "retained wire provenance has no exact declared prior projection"
               for row in report["violations"])


@pytest.mark.parametrize("case", _SCALAR_NAME_CASES, ids=lambda case: case["fn"])
def test_scalar_name_canonical_author_name_never_becomes_a_new_wire_field(case):
    wire, receipt = _scalar_name_restored_wire(case)
    parent, old = _scalar_name_parent(wire, receipt["finalPath"])
    parent[case["canonicalParameter"]] = parent.pop(old)
    errors = validate_runtime_wire(wire)["errors"]
    if receipt["finalPath"].startswith("runtimeProgram."):
        assert any(row["code"] == "unknown_final_wire_field" and row["path"].endswith("." + case["canonicalParameter"])
                   for row in errors)
    else:
        # Legacy gameplay has an open shape; its declared receipt still binds
        # the original wire field, never the new Author spelling.
        assert any(row["code"] == "undeclared_technical_lowering" for row in errors)
