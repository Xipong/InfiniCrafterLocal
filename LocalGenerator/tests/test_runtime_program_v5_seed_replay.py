"""Frozen archives remain evidence, not a current compiler-equivalence target."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


_CORPUS = Path(__file__).with_name("fixtures") / "runtime_program_v5_seed_corpus.json"


def test_frozen_seed_keeps_wire_identity_without_migrating_old_author():
    corpus = json.loads(_CORPUS.read_text(encoding="utf-8"))
    assert corpus["schema"] == "infini.runtime-program-v5-seed-corpus.v1"
    assert corpus["historicalLiveEvidence"] is False
    assert corpus["cases"]
    for row in corpus["cases"]:
        wire = row["expectedDeliveryWire"]
        encoded = json.dumps(wire, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        assert hashlib.sha256(encoded.encode()).hexdigest() == row["expectedDeliveryWireSha256"]
        # Archived tooltip is not part of the current native root. Two cases
        # also omit now-required child-combat choices; reject exactly these
        # retired shapes without rewriting the captured bytes.
        report = validate_runtime_wire(wire)
        assert not report["ok"]
        assert ("$.tooltip", "unknown_final_wire_field") in {
            (error["path"], error["code"]) for error in report["errors"]
        }
        remaining = [error for error in report["errors"] if error["path"] != "$.tooltip"]
        if row["caseId"] in {"held_and_deployed", "workbench_blade"}:
            assert remaining
            assert {error["code"] for error in remaining} == {"required_field"}
            assert all(error["path"].endswith((".damageBasis", ".knockbackBasis", ".damageMultiplier"))
                       for error in remaining)
        else:
            assert remaining == []
        assert not validate_runtime_program(row["authored"])["ok"]
        current = build_runtime_fixture(row["caseId"])
        assert validate_runtime_program(current)["ok"]
        assert validate_runtime_wire(compile_runtime_program(current))["ok"]
