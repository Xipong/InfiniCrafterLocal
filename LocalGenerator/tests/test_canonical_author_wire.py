"""Canonical source compiles directly to frozen gameplay and auditable wire v3."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

import pytest

from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import (
    BINDING_FIELDS_LOWERER_ID, ITEM_TARGET_LOWERER_ID, PRIMARY_BINDING_ROLE_LOWERER_ID,
    audit_compiler_receipts,
)
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture

FIXTURES = Path(__file__).with_name("fixtures")
BASELINE = json.loads((FIXTURES / "author_notation_baseline.json").read_text(encoding="utf-8"))


def _digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("group,name", [(group, name) for group in ("compositions", "capabilities") for name in BASELINE[group]])
def test_current_author_preserves_frozen_gameplay_wire(group, name):
    source = (build_runtime_fixture if group == "compositions" else build_capability_witness)(name)
    original = deepcopy(source)
    compiled = compile_runtime_program(source)
    assert source == original
    assert compiled["runtimeContract"]["authoringSchema"] == "infini.runtime-program.authoring.v5"
    assert "compactAuthorSource" not in compiled["runtimeContract"]
    assert "compactSourceReceipts" not in compiled["runtimeContract"]
    assert compiled["realization"] == source["realization"]
    for section, expected in BASELINE[group][name]["wireSha256"].items():
        assert _digest(compiled[section]) == expected, (name, section)
    assert validate_runtime_wire(compiled)["ok"]
    assert audit_compiler_receipts(compiled["runtimeContract"]["finalWireReceipts"],
                                   authored_document=source, final_document=compiled)["ok"]


def test_saved_wire_keeps_its_original_receipts_without_an_author_parser():
    saved = json.loads((FIXTURES / "saved_wire_v3_baseline.json").read_text(encoding="utf-8"))
    original = deepcopy(saved)
    assert "authoringSchema" not in saved["runtimeContract"]
    assert validate_runtime_wire(saved)["ok"]
    assert saved == original
    assert audit_compiler_receipts(saved["runtimeContract"]["finalWireReceipts"],
                                   final_document=saved)["authoredSourceChecked"] is False


@pytest.mark.parametrize("lowerer", [BINDING_FIELDS_LOWERER_ID, ITEM_TARGET_LOWERER_ID])
@pytest.mark.parametrize("mutation", ["drop", "duplicate", "split_entity_index", "value", "status"])
def test_native_projection_receipts_reject_missing_or_forged_evidence(lowerer, mutation):
    source = build_runtime_fixture("workbench_blade")
    compiled = compile_runtime_program(source)
    rows = compiled["runtimeContract"]["finalWireReceipts"]
    row = next(r for r in rows if r.get("lowererId") == lowerer)
    if mutation == "drop":
        rows.remove(row)
    elif mutation == "duplicate":
        rows.append(deepcopy(row))
    elif mutation == "split_entity_index":
        row["authoredPaths"][-1] = re.sub(r"\[\d+\]", "[999]", row["authoredPaths"][-1])
    elif mutation == "value":
        row["value"] = "forged"
    else:
        row["status"] = "delivered"
    assert not audit_compiler_receipts(rows, authored_document=source, final_document=compiled)["ok"]
    assert not validate_runtime_wire(compiled)["ok"]


@pytest.mark.parametrize("mutation", ["remove_item_target_evidence", "downgrade_binding_evidence"])
def test_current_provenance_claim_cannot_downgrade_to_saved_wire_receipts(mutation):
    compiled = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    contract = compiled["runtimeContract"]
    if mutation == "remove_item_target_evidence":
        contract["finalWireReceipts"] = [r for r in contract["finalWireReceipts"] if r.get("lowererId") != ITEM_TARGET_LOWERER_ID]
    else:
        contract["finalWireReceipts"] = [r for r in contract["finalWireReceipts"] if r.get("lowererId") != BINDING_FIELDS_LOWERER_ID]
        for row in contract["finalWireReceipts"]:
            if row.get("lowererId") == PRIMARY_BINDING_ROLE_LOWERER_ID:
                row["authoredPaths"] = [row["authoredPaths"][0], row["authoredPaths"][1] + ".usePolicy.action.targetId"]
    assert contract["authoringSchema"] == "infini.runtime-program.authoring.v5"
    assert not validate_runtime_wire(compiled)["ok"]


@pytest.mark.parametrize("entities", [None, 42, {}, "malformed"])
def test_source_audit_reports_malformed_placement_entities_without_throwing(entities):
    source = build_capability_witness("present_placed_item_sprite")
    compiled = compile_runtime_program(source)
    source["runtimeProgram"]["entities"] = entities
    before = deepcopy(source)
    report = audit_compiler_receipts(compiled["runtimeContract"]["finalWireReceipts"],
                                     authored_document=source, final_document=compiled)
    assert not report["ok"] and source == before


def test_same_valued_binding_source_cannot_be_substituted():
    source = build_runtime_fixture("equipment_tool_combat")
    compiled = compile_runtime_program(source)
    rows = compiled["runtimeContract"]["finalWireReceipts"]
    choices = [r for r in rows if r.get("lowererId") == BINDING_FIELDS_LOWERER_ID
               and r["finalPath"].endswith(".action.targetId")]
    assert len(choices) >= 2 and choices[0]["value"] == choices[1]["value"]
    choices[0]["authoredPaths"], choices[1]["authoredPaths"] = choices[1]["authoredPaths"], choices[0]["authoredPaths"]
    assert not audit_compiler_receipts(rows, authored_document=source, final_document=compiled)["ok"]


@pytest.mark.parametrize("identity", [pytest.param(..., id="missing"), None, 42, {}])
@pytest.mark.parametrize("mutated_side", ["source", "receipt", "both"])
def test_item_target_source_audit_rejects_missing_or_nonstring_call_identity(identity, mutated_side):
    source = build_runtime_fixture("workbench_blade")
    compiled = compile_runtime_program(source)
    rows = compiled["runtimeContract"]["finalWireReceipts"]
    receipt = next(row for row in rows if row.get("lowererId") == ITEM_TARGET_LOWERER_ID)
    call = next(row for row in source["runtimeProgram"]["calls"] if row["id"] == receipt["callId"])
    fields = []
    if mutated_side in {"source", "both"}:
        fields.append((call, "id"))
    if mutated_side in {"receipt", "both"}:
        fields.append((receipt, "callId"))
    for row, key in fields:
        if identity is ...:
            row.pop(key)
        else:
            row[key] = deepcopy(identity)
    before_source, before_compiled = deepcopy(source), deepcopy(compiled)
    report = audit_compiler_receipts(rows, authored_document=source, final_document=compiled)
    assert not report["ok"]
    assert source == before_source and compiled == before_compiled
