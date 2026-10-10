"""Explicit effect identities select native item effects without carrier entities."""
from copy import deepcopy

import pytest

from infini_local.core.runtime_authoring import (
    apply_repair_patch, build_runtime_repair_scope, compile_runtime_program,
    filter_repair_patch_scope, validate_runtime_program, validate_runtime_wire,
)
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts, EFFECT_GROUP_BINDING_LOWERER_ID
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY
from infini_local.qa import primitive_loss_audit


def _groups(fn="restore_resources_on_use"):
    doc = build_capability_witness(fn)
    program = doc["runtimeProgram"]
    call = next(c for c in program["calls"] if c["fn"] == fn)
    call["params"]["effectGroupId"] = "first"
    binding = program["bindings"][0]
    binding["usePolicy"]["action"]["effectGroupId"] = "first"
    alternate = deepcopy(binding)
    alternate.update(id="alternate_effect", input="alternate_use")
    alternate["usePolicy"]["action"]["effectGroupId"] = "second"
    other = deepcopy(call)
    other["id"] = "second_effect"
    other["params"]["effectGroupId"] = "second"
    if fn == "restore_resources_on_use":
        other["params"].update(healLife=0, healMana=35)
    elif fn == "move_player_on_use":
        other["params"].update(mode="blink_to_cursor", rangeTiles=12, cooldownTicks=90)
    elif fn == "apply_vanilla_buff_on_use":
        other["params"]["buffId"] = 2
    else:
        other["params"].update(lightStrength=0.5, durationTicks=120)
    program["bindings"].append(alternate)
    program["calls"].append(other)
    return doc


@pytest.mark.parametrize("fn", ["restore_resources_on_use", "apply_vanilla_buff_on_use", "apply_generated_buff_on_use", "move_player_on_use"])
def test_every_existing_item_effect_can_partition_explicit_main_and_alternate_groups(fn):
    doc = _groups(fn)
    before = deepcopy(doc)
    assert validate_runtime_program(doc)["ok"]
    final = compile_runtime_program(doc)
    assert validate_runtime_wire(final)["ok"]
    assert doc == before
    groups = final["runtimeProgram"]["effectGroups"]
    assert [group["id"] for group in groups] == ["first", "second"]
    assert len(final["runtimeProgram"]["entities"]) == 1
    assert {b["input"]: b["usePolicy"]["action"]["effectGroupId"] for b in final["runtimeProgram"]["bindings"]} == {"primary_use": "first", "alternate_use": "second"}
    if fn == "restore_resources_on_use":
        assert [(g["healLife"], g["healMana"]) for g in groups] == [(20, 0), (0, 35)]
    receipts = final["runtimeContract"]["finalWireReceipts"]
    assert sum(row.get("lowererId") == EFFECT_GROUP_BINDING_LOWERER_ID for row in receipts) == 2
    assert audit_compiler_receipts(receipts, authored_document=doc, final_document=final)["ok"]


def test_named_and_default_effects_remain_independent():
    doc = _groups()
    call = next(c for c in doc["runtimeProgram"]["calls"] if c["id"] == "second_effect")
    del call["params"]["effectGroupId"]
    del doc["runtimeProgram"]["bindings"][1]["usePolicy"]["action"]["effectGroupId"]
    final = compile_runtime_program(doc)
    assert len(final["runtimeProgram"]["effectGroups"]) == 1
    assert final["gameplay"]["healLife"] == 0 and final["gameplay"]["healMana"] == 35
    assert final["runtimeProgram"]["effectGroups"][0]["healLife"] == 20


def test_same_named_group_composes_explicit_components():
    doc = _groups()
    buff = next(c for c in build_capability_witness("apply_generated_buff_on_use")["runtimeProgram"]["calls"] if c["fn"] == "apply_generated_buff_on_use")
    buff["id"] = "primary_light"
    buff["params"]["effectGroupId"] = "first"
    doc["runtimeProgram"]["calls"].append(buff)
    final = compile_runtime_program(doc)
    assert "generatedBuff" in final["runtimeProgram"]["effectGroups"][0]
    assert "generatedBuff" not in final["runtimeProgram"]["effectGroups"][1]


def test_held_refresh_is_explicit_generated_utility_with_no_active_effect_binding():
    doc = build_capability_witness("refresh_generated_effect_group_while_held")
    final = compile_runtime_program(doc)
    assert final["runtimeProgram"]["heldEffectGroupId"] == "witness"
    assert set(final["runtimeProgram"]["effectGroups"][0]) == {"id", "generatedBuff"}
    assert all(b["usePolicy"]["action"]["kind"] != "apply_item_effects" for b in final["runtimeProgram"]["bindings"])
    assert len(final["runtimeProgram"]["entities"]) == 1


@pytest.mark.parametrize("extra", ["restore_resources_on_use", "apply_vanilla_buff_on_use", "move_player_on_use"])
def test_held_refresh_cannot_repeat_instant_heal_native_buffs_or_mobility(extra):
    doc = build_capability_witness("refresh_generated_effect_group_while_held")
    call = next(c for c in build_capability_witness(extra)["runtimeProgram"]["calls"] if c["fn"] == extra)
    call["id"] = "illegal_held_effect"
    call["params"]["effectGroupId"] = "witness"
    doc["runtimeProgram"]["calls"].append(call)
    assert any(e["code"] == "invalid_held_effect_group" for e in validate_runtime_program(doc)["errors"])


@pytest.mark.parametrize("value", [None, True, 3, [], {}, "", "Wrong", "a" * 49])
def test_effect_identity_is_strict_and_not_a_semantic_family(value):
    doc = _groups()
    doc["runtimeProgram"]["bindings"][0]["usePolicy"]["action"]["effectGroupId"] = value
    assert not validate_runtime_program(doc)["ok"]
    final = compile_runtime_program(_groups())
    final.pop("runtimeContract")
    final["runtimeProgram"]["bindings"][0]["usePolicy"]["action"]["effectGroupId"] = value
    assert not validate_runtime_wire(final)["ok"]


@pytest.mark.parametrize("held", [False, True])
def test_repair_retargets_only_invalid_reference_and_keeps_effects_frozen(held):
    doc = build_capability_witness("refresh_generated_effect_group_while_held") if held else _groups()
    rows = doc["runtimeProgram"]["calls" if held else "bindings"]
    row = next(r for r in rows if r.get("fn") == "refresh_generated_effect_group_while_held") if held else rows[0]
    holder = row["params"] if held else row["usePolicy"]["action"]
    expected = holder["effectGroupId"]
    holder["effectGroupId"] = "missing"
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    corrected = deepcopy(row)
    (corrected["params"] if held else corrected["usePolicy"]["action"])["effectGroupId"] = expected
    if not held:
        corrected["usePolicy"]["stackCost"] = 1
    key = "callsUpsert" if held else "bindingsUpsert"
    filtered, audit = filter_repair_patch_scope(doc, {"note": "Repair exact reference only", key: [corrected]}, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(doc, filtered)
    assert validate_runtime_program(repaired)["ok"]
    if not held:
        assert repaired["runtimeProgram"]["bindings"][0]["usePolicy"]["stackCost"] == 0
    if not held:
        assert repaired["runtimeProgram"]["calls"] == doc["runtimeProgram"]["calls"]


def test_unbound_group_repair_names_only_the_existing_group_in_new_consumer():
    doc = _groups()
    doc["runtimeProgram"]["bindings"].pop()
    scope = build_runtime_repair_scope(doc, validate_runtime_program(doc)["errors"])
    allowed = scope["create"]["bindings"]["allowedTransactions"]
    assert allowed and all(row["usePolicy"]["action"].get("effectGroupId") == "second" for row in allowed)
    candidate = {"id": "repaired_alternate", **deepcopy(allowed[0])}
    filtered, audit = filter_repair_patch_scope(doc, {"note": "Attach authored existing group", "bindingsUpsert": [candidate]}, scope)
    assert audit["ok"], audit
    assert validate_runtime_program(apply_repair_patch(doc, filtered))["ok"]


@pytest.mark.parametrize("mutation", ["binding_receipt_drop", "cross_group_receipt", "invent_group", "bad_effect_field", "held_heal", "empty_groups"])
def test_wire_or_receipts_reject_group_aliasing_and_unowned_fields(mutation):
    doc = _groups()
    final = compile_runtime_program(doc)
    receipts = final["runtimeContract"]["finalWireReceipts"]
    if mutation == "binding_receipt_drop":
        receipts[:] = [r for r in receipts if r.get("lowererId") != EFFECT_GROUP_BINDING_LOWERER_ID]
    elif mutation == "cross_group_receipt":
        receipt = next(r for r in receipts if r.get("fn") == "restore_resources_on_use" and r.get("finalPath") == "runtimeProgram.effectGroups[0].healLife")
        receipt["finalPath"] = "runtimeProgram.effectGroups[1].healLife"
        final["runtimeProgram"]["effectGroups"][1]["healLife"] = receipt["value"]
    elif mutation == "invent_group":
        final["runtimeProgram"]["effectGroups"][0]["id"] = "invented"
    elif mutation == "bad_effect_field":
        final["runtimeProgram"]["effectGroups"][0]["damage"] = 999
    elif mutation == "held_heal":
        final["runtimeProgram"]["heldEffectGroupId"] = "first"
    else:
        final["runtimeProgram"]["effectGroups"] = []
    assert not validate_runtime_wire(final)["ok"]


def test_ungrouped_omission_never_materializes_named_groups_or_binding_receipts():
    final = compile_runtime_program(build_capability_witness("restore_resources_on_use"))
    assert "effectGroups" not in final["runtimeProgram"] and "heldEffectGroupId" not in final["runtimeProgram"]
    assert not any(r.get("lowererId") == EFFECT_GROUP_BINDING_LOWERER_ID for r in final["runtimeContract"]["finalWireReceipts"])


@pytest.mark.parametrize("held", [False, True])
def test_named_generated_buff_neutral_omissions_have_exact_unique_group_receipts(held):
    doc = build_capability_witness("refresh_generated_effect_group_while_held") if held else _groups("apply_generated_buff_on_use")
    defaults = {name: spec.default for name, spec in CAPABILITY_REGISTRY["apply_generated_buff_on_use"].params.items()
                if spec.default is not None}
    for call in doc["runtimeProgram"]["calls"]:
        if call["fn"] == "apply_generated_buff_on_use":
            for name in defaults:
                call["params"].pop(name, None)
    before = deepcopy(doc)
    final = compile_runtime_program(doc)
    assert doc == before
    rows = final["runtimeContract"]["finalWireReceipts"]
    omissions = [row for row in rows if row.get("status") == "declared_neutral_omission" and row.get("fn") == "apply_generated_buff_on_use"]
    assert len(omissions) == len(defaults) * (1 if held else 2)
    assert all(row["finalPath"].startswith("runtimeProgram.effectGroups[") for row in omissions)
    assert audit_compiler_receipts(rows, authored_document=doc, final_document=final)["ok"]
    assert audit_compiler_receipts(rows, final_document=final)["ok"]
    damaged = deepcopy(final)
    damaged["runtimeContract"]["finalWireReceipts"].remove(omissions[0])
    assert not validate_runtime_wire(damaged)["ok"]


def test_effect_group_surface_audit_rejects_uncatalogued_native_storage():
    source = (primitive_loss_audit._MODEL_ROOT / "Common/Models/RuntimeItemEffectGroupSpec.cs").read_bytes()
    assert primitive_loss_audit.item_effect_group_surface_audit(source)["ok"]
    anchor = b'public string Id { get; set; } = "";'
    assert anchor in source
    changed = source.replace(anchor, b"public int Damage { get; set; }\n    " + anchor)
    report = primitive_loss_audit.item_effect_group_surface_audit(changed)
    assert not report["ok"]
    assert report["unclassifiedDtoFields"] == ["Damage"]


def test_named_group_dto_neutral_serialization_is_accepted_without_new_effects():
    final = compile_runtime_program(build_capability_witness("refresh_generated_effect_group_while_held"))
    final.pop("runtimeContract")  # DTO transport is validated without claiming source receipts.
    group = final["runtimeProgram"]["effectGroups"][0]
    group.update(healLife=0, healMana=0, potion=False, extraBuffs=[], mobilityMode="", mobilityRangeTiles=0,
                 mobilityCooldownTicks=0, mobilitySafeTileOnly=True)
    assert validate_runtime_wire(final)["ok"]
