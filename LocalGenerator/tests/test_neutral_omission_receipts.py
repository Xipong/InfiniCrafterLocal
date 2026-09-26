"""Omitted registry-declared neutrals have distinct, verifiable wire provenance."""
from copy import deepcopy
from dataclasses import replace

import pytest

from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_wire
from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
from infini_local.core.runtime_authoring import technical_lowering
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness


def _stats(*, omit=True):
    source = build_capability_witness("configure_item_stats")
    call = next(c for c in source["runtimeProgram"]["calls"] if c["fn"] == "configure_item_stats")
    call["params"]["manaCost"] = 0
    if omit:
        del call["params"]["manaCost"]
    return source


def _receipt(rows, path):
    return next(row for row in rows if row.get("finalPath") == path)


def _audit(source, compiled, rows):
    return audit_compiler_receipts(rows, authored_document=source, final_document=compiled)


def test_omitted_mana_is_wire_equal_but_receipt_distinct_and_source_unchanged():
    omitted = _stats()
    before = deepcopy(omitted)
    explicit = _stats(omit=False)
    sparse_wire = compile_runtime_program(omitted)
    explicit_wire = compile_runtime_program(explicit)
    assert omitted == before
    assert sparse_wire["gameplay"] == explicit_wire["gameplay"]
    assert sparse_wire["gameplay"]["manaCost"] == 0
    rows = sparse_wire["runtimeContract"]["finalWireReceipts"]
    omitted_row = _receipt(rows, "gameplay.manaCost")
    explicit_row = _receipt(explicit_wire["runtimeContract"]["finalWireReceipts"], "gameplay.manaCost")
    assert omitted_row == {**explicit_row, "status": "declared_neutral_omission"}
    assert explicit_row["status"] == "delivered"
    assert _audit(omitted, sparse_wire, rows)["ok"]
    assert audit_compiler_receipts(rows, final_document=sparse_wire)["ok"]
    assert validate_runtime_wire(sparse_wire)["ok"]


@pytest.mark.parametrize("tamper", ["swap_path", "change_value", "reclassify", "remove", "duplicate"])
def test_omission_receipt_cannot_be_swapped_changed_reclassified_or_removed(tamper):
    source = _stats()
    next(c for c in source["runtimeProgram"]["calls"] if c["fn"] == "configure_item_stats")["params"]["damage"] = 0
    compiled = compile_runtime_program(source)
    rows = deepcopy(compiled["runtimeContract"]["finalWireReceipts"])
    omission = _receipt(rows, "gameplay.manaCost")
    assert omission["value"] == _receipt(rows, "gameplay.damage")["value"] == 0
    if tamper == "swap_path":
        other = _receipt(rows, "gameplay.damage")
        omission["finalPath"], other["finalPath"] = other["finalPath"], omission["finalPath"]
    elif tamper == "change_value":
        omission["value"] = 1
    elif tamper == "reclassify":
        omission["status"] = "delivered"
    elif tamper == "remove":
        rows.remove(omission)
    else:
        rows.append(deepcopy(omission))
    assert not _audit(source, compiled, rows)["ok"]
    if tamper != "reclassify":
        assert not audit_compiler_receipts(rows, final_document=compiled)["ok"]
    compiled["runtimeContract"]["finalWireReceipts"] = rows
    if tamper != "reclassify":
        assert not validate_runtime_wire(compiled)["ok"]


def test_explicit_value_cannot_claim_omission_and_omission_cannot_claim_other_call():
    explicit = _stats(omit=False)
    compiled = compile_runtime_program(explicit)
    rows = deepcopy(compiled["runtimeContract"]["finalWireReceipts"])
    _receipt(rows, "gameplay.manaCost")["status"] = "declared_neutral_omission"
    assert not _audit(explicit, compiled, rows)["ok"]
    omitted = _stats()
    compiled = compile_runtime_program(omitted)
    rows = deepcopy(compiled["runtimeContract"]["finalWireReceipts"])
    _receipt(rows, "gameplay.manaCost")["callId"] = "not_the_call"
    assert not _audit(omitted, compiled, rows)["ok"]


def test_registry_default_is_required_and_must_equal_declared_neutral(monkeypatch):
    source = _stats()
    compiled = compile_runtime_program(source)
    rows = compiled["runtimeContract"]["finalWireReceipts"]
    cap = CAPABILITY_REGISTRY["configure_item_stats"]
    for replacement in (replace(cap.params["manaCost"], default=None),
                        replace(cap.params["manaCost"], default=1),
                        replace(cap.params["manaCost"], required=True)):
        monkeypatch.setattr(technical_lowering, "CAPABILITY_REGISTRY", {
            **CAPABILITY_REGISTRY,
            cap.name: replace(cap, params={**cap.params, "manaCost": replacement}),
        })
        assert not _audit(source, compiled, rows)["ok"]
        assert not audit_compiler_receipts(rows, final_document=compiled)["ok"]


@pytest.mark.parametrize("param,wire_key,wire_value", [
    ("miningSpeedMultiplier", "miningSpeedMultiplier", 1.0),
    ("oreSenseEnabled", "oreSenseRadiusTiles", 0),
    ("moveSpeedBonusFactor", "movementSpeed", 0.0),
    ("jumpSpeedBonusPxPerTick", "jumpBoost", 0.0),
    ("manaRegenBonusPoints", "manaRegen", 0),
    ("lifeRegenHpPerSecond", "lifeRegen", 0),
])
def test_generated_buff_declared_neutral_receipt_and_conversion(param, wire_key, wire_value):
    source = build_capability_witness("apply_generated_buff_on_use")
    params = next(c for c in source["runtimeProgram"]["calls"]
                  if c["fn"] == "apply_generated_buff_on_use")["params"]
    params.pop(param)
    before = deepcopy(source)
    compiled = compile_runtime_program(source)
    row = _receipt(compiled["runtimeContract"]["finalWireReceipts"],
                   f"gameplay.generatedBuff.{wire_key}")
    assert source == before
    assert compiled["gameplay"]["generatedBuff"][wire_key] == wire_value
    assert row["value"] == wire_value
    assert row["authoredPath"].endswith(f".params.{param}")
    assert row["status"] == "declared_neutral_omission"
    assert _audit(source, compiled, compiled["runtimeContract"]["finalWireReceipts"])["ok"]
    assert validate_runtime_wire(compiled)["ok"]


def test_multi_output_omission_and_explicit_holdout_have_distinct_receipts():
    source = build_capability_witness("configure_item_use")
    call = next(c for c in source["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")
    call["params"].pop("holdoutOffsetX")
    call["params"]["holdoutOffsetY"] = 0
    compiled = compile_runtime_program(source)
    rows = compiled["runtimeContract"]["finalWireReceipts"]
    assert compiled["gameplay"]["holdoutOffsetX"] == 0
    assert compiled["runtimeProgram"]["itemUse"]["holdoutOffsetX"] == 0
    for prefix in ("gameplay", "runtimeProgram.itemUse"):
        assert _receipt(rows, f"{prefix}.holdoutOffsetX")["status"] == "declared_neutral_omission"
        assert _receipt(rows, f"{prefix}.holdoutOffsetY")["status"] == "delivered"
    assert _audit(source, compiled, rows)["ok"]
    rows = deepcopy(rows)
    rows.remove(_receipt(rows, "runtimeProgram.itemUse.holdoutOffsetX"))
    assert not _audit(source, compiled, rows)["ok"]
    assert not audit_compiler_receipts(rows, final_document=compiled)["ok"]


def test_omission_cannot_disappear_from_both_wire_and_receipts():
    source = _stats()
    compiled = compile_runtime_program(source)
    rows = deepcopy(compiled["runtimeContract"]["finalWireReceipts"])
    rows.remove(_receipt(rows, "gameplay.manaCost"))
    del compiled["gameplay"]["manaCost"]
    assert not _audit(source, compiled, rows)["ok"]


@pytest.mark.parametrize("tamper_receipt", [False, True])
@pytest.mark.parametrize("bad", [False, 0.0], ids=["boolean", "float"])
def test_omission_receipt_and_wire_preserve_integer_zero_type(tamper_receipt, bad):
    source = _stats()
    compiled = compile_runtime_program(source)
    rows = deepcopy(compiled["runtimeContract"]["finalWireReceipts"])
    if tamper_receipt:
        _receipt(rows, "gameplay.manaCost")["value"] = bad
    compiled["gameplay"]["manaCost"] = bad
    assert not _audit(source, compiled, rows)["ok"]
    assert not audit_compiler_receipts(rows, final_document=compiled)["ok"]
    compiled["runtimeContract"]["finalWireReceipts"] = rows
    assert not validate_runtime_wire(compiled)["ok"]


def test_delivery_without_provenance_is_allowed_but_present_empty_receipts_are_not():
    compiled = compile_runtime_program(_stats())
    delivery = deepcopy(compiled)
    delivery.pop("runtimeContract")
    assert validate_runtime_wire(delivery)["ok"]
    for broken in (None, {}, {"finalWireReceipts": []}):
        delivery["runtimeContract"] = broken
        assert not validate_runtime_wire(delivery)["ok"]
