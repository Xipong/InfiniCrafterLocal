from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_wire
from infini_local.storage.world_storage import sanitize_recipe_for_delivery


_CORPUS = Path(__file__).with_name("fixtures") / "runtime_program_v5_seed_corpus.json"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _delivery_wire(compiled: dict[str, Any]) -> dict[str, Any]:
    wire = sanitize_recipe_for_delivery(compiled)
    assert isinstance(wire, dict)
    wire.pop("debug", None)
    return wire


def test_frozen_v5_seed_corpus_replays_exact_production_compile_and_detects_drift() -> None:
    corpus = json.loads(_CORPUS.read_text(encoding="utf-8"))
    assert corpus["schema"] == "infini.runtime-program-v5-seed-corpus.v1"
    assert corpus["historicalLiveEvidence"] is False
    cases = corpus["cases"]
    case_ids = [row["caseId"] for row in cases]
    assert len(cases) == 8
    assert case_ids == sorted(case_ids)
    assert len(case_ids) == len(set(case_ids))

    for row in cases:
        authored = row["authored"]
        actual_capabilities = sorted(
            {
                call["fn"]
                for call in authored["runtimeProgram"]["calls"]
                if isinstance(call, dict) and call.get("fn")
            }
        )
        assert actual_capabilities == row["capabilities"]

        compiled = compile_runtime_program(authored)
        assert validate_runtime_wire(compiled)["ok"] is True
        actual_wire = _delivery_wire(compiled)
        assert actual_wire == row["expectedDeliveryWire"]
        digest = hashlib.sha256(_canonical(actual_wire).encode("utf-8")).hexdigest()
        assert digest == row["expectedDeliveryWireSha256"]

    drifted = deepcopy(cases[0]["expectedDeliveryWire"])
    drifted["gameplay"]["damage"] += 1
    drifted_digest = hashlib.sha256(_canonical(drifted).encode("utf-8")).hexdigest()
    assert drifted_digest != cases[0]["expectedDeliveryWireSha256"]
