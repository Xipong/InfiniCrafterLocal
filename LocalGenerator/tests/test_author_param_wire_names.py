"""Renamed Author fields remain lossless projections to the frozen C# DTO."""
from dataclasses import replace
from types import MappingProxyType
import copy
import struct

import pytest

from infini_local.core.runtime_authoring import compiler, technical_lowering
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring import validate_runtime_program, validate_runtime_wire
from infini_local.qa.capability_witnesses import build_capability_witness


# Scoped registry substitutions isolate compiler/receipt behavior from the parent
# registry migration; no persistent aliases or registry edits are installed here.
RENAMES = (
    ("configure_spawn", "speedPxPerTick", "speedPxPerUpdate", 7.125, "spawn"),
    ("set_projectile_collision", "localNpcHitCooldownTicks", "localNpcHitCooldownEngineUnits", -1, "collision"),
    ("move_gravity_arc", "gravityPerTick", "gravityVelocityPerUpdate", 0.1875, "movement.params"),
    ("move_bounce", "gravityPerTick", "gravityVelocityPerUpdate", 0.1875, "movement.params"),
    ("move_spiral", "turnRadiansPerTick", "turnRadiansPerUpdate", -0.1875, "movement.params"),
    ("move_expanding_wave", "scalePerTick", "scaleGrowthPerUpdate", 0.1875, "movement.params"),
    ("move_accelerate", "acceleration", "speedMultiplierPerUpdate", 1.125, "movement.params"),
    ("move_sine_homing", "waveAmplitude", "waveVelocityCoefficient", 7.125, "movement.params"),
    ("configure_item_use", "releaseTiming", "heldSpriteVisibilityHint", "on_release", "itemUse"),
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
    paths = tuple(path.removesuffix("." + new) + "." + (spec.wire_name or old)
                  if path.endswith("." + new) else path for path in cap.final_wire_paths)
    registry[fn] = replace(cap, params=MappingProxyType(params), final_wire_paths=paths)
    monkeypatch.setattr(compiler, "CAPABILITY_REGISTRY", registry)
    monkeypatch.setattr(technical_lowering, "CAPABILITY_REGISTRY", registry)
    return registry[fn]


def _project(fn, new, value):
    call = {"id": "renamed", "fn": fn, "target": "item" if fn.startswith(("configure_item", "configure_vanilla", "restore_", "apply_generated")) else "shot",
            "_sourceIndex": 0, "params": {
                # This test calls the isolated projector, not the full compiler
                # that materializes omissions. Author neutrals explicitly here.
                **{name: spec.default for name, spec in compiler.CAPABILITY_REGISTRY[fn].params.items()
                   if spec.default is not None}, new: value,
            }}
    ctx = compiler._CompileContext(receipts=[])
    if call["target"] == "item":
        gameplay, runtime = {}, {}
        compiler._compile_item_call(ctx, call, gameplay=gameplay, accessory={}, armor={}, runtime=runtime,
                                    item_entity={}, entity_index=0, equipment_config="")
        final = {"gameplay": gameplay, "runtimeProgram": runtime}
    else:
        entity = {}
        compiler._compile_entity_call(ctx, call, entity=entity, entity_index=0)
        final = {"runtimeProgram": {"entities": [entity]}}
    return call, ctx.receipts, final


def _get(document, path):
    import re
    value = document
    for part in re.findall(r"[A-Za-z][A-Za-z0-9_]*|\[\d+\]", path):
        value = value[int(part[1:-1])] if part.startswith("[") else value[part]
    return value


@pytest.mark.parametrize("fn,old,new,value,component", RENAMES)
def test_registry_declared_rename_projects_identical_wire_and_exact_receipt(monkeypatch, fn, old, new, value, component):
    cap = _registry_with_rename(monkeypatch, fn, old, new)
    call, receipts, final = _project(fn, new, value)
    matches = [row for row in receipts if row.get("authoredPath") == f"runtimeProgram.calls[0].params.{new}"]
    assert matches
    expected_suffix = cap.params[new].wire_name
    assert all(row["finalPath"].endswith("." + expected_suffix) for row in matches)
    assert all(_get(final, row["finalPath"]) == value for row in matches)
    if isinstance(value, float):
        assert all(struct.pack("!d", _get(final, row["finalPath"])) == struct.pack("!d", value) for row in matches)
    audit = technical_lowering.audit_compiler_receipts(receipts, authored_document={"runtimeProgram": {"calls": [call]}}, final_document=final)
    assert audit["ok"], audit["violations"]


def test_receipt_cannot_swap_authored_source_or_output(monkeypatch):
    _registry_with_rename(monkeypatch, "configure_spawn", "speedPxPerTick", "speedPxPerUpdate")
    call, receipts, final = _project("configure_spawn", "speedPxPerUpdate", 7.125)
    source = {"runtimeProgram": {"calls": [call]}}
    tampered = copy.deepcopy(receipts)
    next(row for row in tampered if row.get("authoredPath", "").endswith(".speedPxPerUpdate"))["authoredPath"] = "runtimeProgram.calls[0].params.speedPxPerTick"
    assert not technical_lowering.audit_compiler_receipts(tampered, authored_document=source, final_document=final)["ok"]
    tampered = copy.deepcopy(receipts)
    next(row for row in tampered if row.get("authoredPath", "").endswith(".speedPxPerUpdate"))["finalPath"] = "runtimeProgram.entities[0].spawn.count"
    assert not technical_lowering.audit_compiler_receipts(tampered, authored_document=source, final_document=final)["ok"]


@pytest.mark.parametrize("fn,old,new,value,component", RENAMES)
def test_actual_author_rejects_old_alias_and_compiles_new_to_historical_wire(fn, old, new, value, component):
    cap = CAPABILITY_REGISTRY[fn]
    assert new in cap.params and old not in cap.params
    assert cap.params[new].wire_name
    authored = build_capability_witness(fn)
    call = next(row for row in authored["runtimeProgram"]["calls"] if row["id"] == "witness_call")
    call["params"][new] = value
    assert validate_runtime_program(authored)["ok"]
    wire = compiler.compile_runtime_program(authored)
    assert validate_runtime_wire(wire)["ok"]
    receipts = [row for row in wire["runtimeContract"]["finalWireReceipts"]
                if row.get("callId") == "witness_call" and row.get("authoredPath", "").endswith(".params." + new)]
    assert receipts
    for row in receipts:
        assert row["finalPath"].endswith("." + cap.params[new].wire_name)
        projected = _get(wire, row["finalPath"])
        assert projected == value
        if isinstance(value, float):
            assert struct.pack("!d", projected) == struct.pack("!d", value)
    alias = copy.deepcopy(authored)
    alias_call = next(row for row in alias["runtimeProgram"]["calls"] if row["id"] == "witness_call")
    alias_call["params"][old] = alias_call["params"].pop(new)
    assert not validate_runtime_program(alias)["ok"]


def test_buff_factor_keeps_binary64_without_percent_roundtrip():
    value = 1.770282212988338
    authored = build_capability_witness("apply_generated_buff_on_use")
    call = next(row for row in authored["runtimeProgram"]["calls"] if row["id"] == "witness_call")
    call["params"]["moveSpeedBonusFactor"] = value
    wire = compiler.compile_runtime_program(authored)
    projected = wire["gameplay"]["generatedBuff"]["movementSpeed"]
    assert struct.pack("!d", projected) == struct.pack("!d", value)
    assert struct.pack("!d", projected) != struct.pack("!d", value * 100 / 100)


@pytest.mark.parametrize("fn,old,new,value,component", RENAMES[:9])
def test_wire_validator_rejects_author_key_in_frozen_runtime_dto(fn, old, new, value, component):
    authored = build_capability_witness(fn)
    call = next(row for row in authored["runtimeProgram"]["calls"] if row["id"] == "witness_call")
    call["params"][new] = value
    wire = compiler.compile_runtime_program(authored)
    receipt = next(row for row in wire["runtimeContract"]["finalWireReceipts"]
                   if row.get("callId") == "witness_call"
                   and row.get("authoredPath", "").endswith(".params." + new)
                   and row["finalPath"].startswith("runtimeProgram."))
    prefix, _, wire_key = receipt["finalPath"].rpartition(".")
    container = _get(wire, prefix)
    container[new] = container.pop(wire_key)
    errors = validate_runtime_wire(wire)["errors"]
    assert any(row["code"] == "unknown_final_wire_field" and row["path"].endswith("." + new)
               for row in errors)
