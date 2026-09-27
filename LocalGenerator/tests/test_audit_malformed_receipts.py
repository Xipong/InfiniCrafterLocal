"""A9: malformed receipt rows are indexed RED reports, never exceptions."""
from copy import deepcopy
import re

import pytest

from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_wire
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.qa.capability_witnesses import build_capability_witness


@pytest.mark.parametrize("bad", [None, [], 1, False, "row", {},
    {"fn": []}, {"authoredPaths": 7}, {"authoredPaths": "path"},
    {"authoredPaths": [None]}, {"finalPath": []}, {"status": None},
    {"callId": {}}, {"lowererId": True}, {"authoredPath": 0}])
def test_malformed_rows_have_original_index_in_direct_and_wire_audits(bad):
    source = build_capability_witness("configure_item_stats")
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    index = len(rows)
    rows.append(deepcopy(bad))
    for authored in (None, source):
        report = audit_compiler_receipts(rows, authored_document=authored, final_document=wire)
        assert not report["ok"]
        assert any(v.get("receiptIndex") == index and
                   v.get("path", "").startswith(f"$.runtimeContract.finalWireReceipts[{index}]")
                   for v in report["violations"])
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(v.get("receiptIndex") == index for v in report["technicalLowering"]["violations"])


@pytest.mark.parametrize("field", ["finalPath", "authoredPath", "authoredPaths"])
@pytest.mark.parametrize("bad_index", ["9" * 4301, "-1", "1.0", "not_an_index"],
                         ids=["oversized", "negative", "fractional", "text"])
@pytest.mark.parametrize("with_source", [False, True])
def test_malformed_path_indices_are_indexed_violations(field, bad_index, with_source):
    source = build_capability_witness("configure_item_stats")
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    if field == "authoredPath":
        bad = deepcopy(next(row for row in rows if row.get("fn") == "configure_item_stats"))
        bad[field] = re.sub(r"\[\d+\]", f"[{bad_index}]", bad[field], count=1)
    else:
        bad = deepcopy(rows[0])
        if field == "finalPath":
            bad[field] = f"runtimeProgram.entities[{bad_index}].id"
        else:
            bad[field][1] = f"runtimeProgram.entities[{bad_index}].id"
    # A preceding malformed row must not shift the original receipt index.
    rows.append(None)
    index = len(rows)
    rows.append(bad)
    report = audit_compiler_receipts(
        rows, authored_document=source if with_source else None, final_document=wire)
    assert not report["ok"]
    assert any(v.get("receiptIndex") == index and
               v.get("path", "").startswith(f"$.runtimeContract.finalWireReceipts[{index}]")
               for v in report["violations"])
    report = validate_runtime_wire(wire)
    assert not report["ok"]
    assert any(v.get("receiptIndex") == index for v in report["technicalLowering"]["violations"])
