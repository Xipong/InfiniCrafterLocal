"""Frozen archives remain evidence, not a current compiler-equivalence target."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire


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
        # This saved wire remains supported; its old Author syntax does not.
        # Do not fabricate a current source or erase new receipts to match it.
        assert validate_runtime_wire(wire)["ok"]
        assert not validate_runtime_program(row["authored"])["ok"]
