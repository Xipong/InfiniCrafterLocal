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


_HISTORICAL_DELIVERY_SHA256 = {
    "door_on_chain": "6ce7a898fcaa947880f5516184fbe5130098df0af498f91c7fdd2bf942f52f4f",
    "equipment_tool_combat": "1b1eab483aeac5ba4a4e6d0d93dc9e2269c54540b9173319ef9c1c35903efce8",
    "fishing_platform_tool": "bf73362ca7a0bd880aa2e0b496e62817be702b688cb1d9d10ea57c5afd1ecd92",
    "held_and_deployed": "6fd405b9187aecfed86f6a313da5429c1308bebc364834b334660268600e7307",
    "returning_potion": "e4223710287cceb4b4d7a445b1ba34ff1eddf77b3537ae5e47a3cc1140ebabb5",
    "shield_and_disc": "3c95b1bf58298f98062f7f1162a2736e9c3af459655686286517b3ba88ad5c3a",
    "umbrella_grenade": "cdcc5cc94bdc4a2b6bef9bd156ddb95cb5b1d1d475c70cb069c3ced01dd061ac",
    "workbench_blade": "81cefc52e6b60c5c8e95ac5962d0247da49f4b127d03390dfe52a90845db52db",
}


def test_frozen_seed_reconstructs_historical_delivery_after_only_inert_omissions() -> None:
    """Legacy `channelUse` was unread; zero accessory stats are C# DTO defaults."""
    corpus = json.loads(_CORPUS.read_text(encoding="utf-8"))
    assert {row["caseId"] for row in corpus["cases"]} == set(_HISTORICAL_DELIVERY_SHA256)
    for row in corpus["cases"]:
        wire = deepcopy(row["expectedDeliveryWire"])
        gameplay = wire["gameplay"]
        assert "channelUse" not in gameplay  # C# reads runtimeProgram.itemUse.channel instead.
        gameplay["channelUse"] = False
        if row["caseId"] == "equipment_tool_combat":
            accessory = wire["accessory"]
            for field in ("maxLife", "maxMana", "lifeRegen", "manaRegen", "minionSlots", "sentrySlots"):
                assert field not in accessory
                accessory[field] = 0  # GeneratedAccessoryData initializes each field to zero.
        actual = hashlib.sha256(_canonical(wire).encode("utf-8")).hexdigest()
        assert actual == _HISTORICAL_DELIVERY_SHA256[row["caseId"]]


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
