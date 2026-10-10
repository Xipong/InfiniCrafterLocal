"""Canonical scalar names keep captured wire bytes without accepting old Author."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

import pytest

from infini_local.core.runtime_authoring import (
    CAPABILITY_REGISTRY, apply_repair_patch, build_runtime_repair_scope,
    compile_runtime_program, filter_repair_patch_scope, validate_runtime_program,
    validate_runtime_wire,
)
from infini_local.core.runtime_authoring.program_schema import (
    author_item_repair_schema, strict_repair_shape_report,
    strict_repair_structure_report,
)
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request


_CAPTURE = json.loads((Path(__file__).parent / "fixtures/scalar_author_names_retained_receipts.json").read_text())
_CASES = _CAPTURE["cases"]


def _call(document):
    return next(row for row in document["runtimeProgram"]["calls"] if row["id"] == "witness_call")


def _current_source(case):
    # The captured Author is an immutable test oracle, never production input.
    source = deepcopy(case["authored"])
    params = _call(source)["params"]
    assert case["canonicalParameter"] not in params
    params[case["canonicalParameter"]] = params.pop(case["oldParameter"])
    return source


def _restored_wire(case):
    wire = compile_runtime_program(_current_source(case))
    rows = wire["runtimeContract"]["finalWireReceipts"]
    receipt = next(row for row in rows if row.get("callId") == "witness_call"
                   and row.get("authoredPath", "").endswith(".params." + case["canonicalParameter"]))
    expected = deepcopy(case["receipt"])
    expected["authoredPath"] = expected["authoredPath"].removesuffix(case["oldParameter"]) + case["canonicalParameter"]
    assert receipt == expected
    # Restore one pre-change receipt verbatim; every other output byte is pinned.
    receipt.update(deepcopy(case["receipt"]))
    return wire, receipt


def _parent(document, path):
    value = document
    parts = re.findall(r"[A-Za-z][A-Za-z0-9_]*|\[\d+\]", path)
    for part in parts[:-1]:
        value = value[int(part[1:-1])] if part.startswith("[") else value[part]
    return value, parts[-1]


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["fn"])
def test_captured_complete_wire_and_old_receipts_remain_exact(case):
    assert _CAPTURE["originCommit"] == "274d4c38849bff5b8f7ecde1c61d6276a4803712"
    source = _current_source(case)
    wire = compile_runtime_program(source)
    rows = wire["runtimeContract"]["finalWireReceipts"]
    assert audit_compiler_receipts(rows, authored_document=source, final_document=wire)["ok"]

    retained, _ = _restored_wire(case)
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
def test_actual_author_packet_and_repair_schema_expose_only_current_names(monkeypatch, mode):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    request, user, _ = build_initial_author_request({}, {}, {}, {}, "scalar-names", model_name="offline-test")
    assert request["response_format"]["type"] == mode
    cards = {row["fn"]: row for row in json.loads(user)["runtimeCapabilityContract"]["catalog"]["capabilities"]}
    variants = author_item_repair_schema(capability_names=[case["fn"] for case in _CASES])["properties"]["callsUpsert"]["items"]["oneOf"]
    schemas = [{row["properties"]["fn"]["const"]: row["properties"]["params"] for row in variants}]
    if mode == "json_schema":
        provider_calls = request["response_format"]["json_schema"]["schema"]["properties"]["runtimeProgram"]["properties"]["calls"]["items"]["anyOf"]
        schemas.append({row["properties"]["fn"]["const"]: row["properties"]["params"]
                        for row in provider_calls if "params" in row["properties"]})
    for case in _CASES:
        fn, old, current = case["fn"], case["oldParameter"], case["canonicalParameter"]
        assert old not in cards[fn]["params"] and current in cards[fn]["params"]
        for group in schemas:
            assert old not in group[fn]["properties"] and current in group[fn]["required"]
        cap = CAPABILITY_REGISTRY[fn]
        assert old not in cap.params and old in cap.retained_receipt_params
        assert cap.params[current].required and cap.params[current].default is None


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["fn"])
def test_repair_uses_exact_current_leaf_and_refuses_previous_spelling(case):
    accepted = _current_source(case)
    broken = deepcopy(accepted)
    current = case["canonicalParameter"]
    _call(broken)["params"][current] = CAPABILITY_REGISTRY[case["fn"]].params[current].maximum + 1
    scope = build_runtime_repair_scope(broken, validate_runtime_program(broken)["errors"])
    assert next(row["paths"] for row in scope["fieldPermissions"]["calls"] if row["id"] == "witness_call") == ["params." + current]

    stale_patch = {"note": "old spelling is not a Repair alias", "callsUpsert": [deepcopy(_call(case["authored"]))]}
    assert not strict_repair_structure_report(stale_patch)["ok"]
    assert not strict_repair_shape_report(stale_patch)["ok"]
    _, audit = filter_repair_patch_scope(broken, stale_patch, scope)
    assert not audit["ok"]
    with pytest.raises(ValueError):
        apply_repair_patch(broken, stale_patch)

    frozen = deepcopy(next(row for row in accepted["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats"))
    frozen["params"]["damage"] += 1
    patch = {"note": "repair only the permitted scalar", "callsUpsert": [deepcopy(_call(accepted)), frozen]}
    filtered, audit = filter_repair_patch_scope(broken, patch, scope)
    assert audit["ok"], audit
    repaired = apply_repair_patch(broken, filtered)
    assert repaired == accepted
    assert validate_runtime_program(repaired)["ok"]


@pytest.mark.parametrize("mutation", ["wrong-output", "out-of-domain", "boolean", "omission"])
@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["fn"])
def test_retained_receipt_cannot_widen_domain_or_forge_projection(case, mutation):
    wire, receipt = _restored_wire(case)
    if mutation == "wrong-output":
        receipt["finalPath"] = "gameplay.damage"
    elif mutation == "omission":
        receipt["status"] = "declared_neutral_omission"
    else:
        parent, key = _parent(wire, receipt["finalPath"])
        value = True if mutation == "boolean" else CAPABILITY_REGISTRY[case["fn"]].params[case["canonicalParameter"]].maximum + 1
        parent[key] = receipt["value"] = value
    report = audit_compiler_receipts(wire["runtimeContract"]["finalWireReceipts"], final_document=wire)
    assert not report["ok"]
    assert any(row["reason"] == "retained wire provenance has no exact declared prior projection"
               for row in report["violations"])


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["fn"])
def test_canonical_author_name_never_becomes_a_new_wire_field(case):
    wire, receipt = _restored_wire(case)
    parent, old = _parent(wire, receipt["finalPath"])
    parent[case["canonicalParameter"]] = parent.pop(old)
    errors = validate_runtime_wire(wire)["errors"]
    if receipt["finalPath"].startswith("runtimeProgram."):
        assert any(row["code"] == "unknown_final_wire_field" and row["path"].endswith("." + case["canonicalParameter"])
                   for row in errors)
    else:
        # Legacy gameplay has an open shape; its declared receipt still binds
        # the original wire field, never the new Author spelling.
        assert any(row["code"] == "undeclared_technical_lowering" for row in errors)
