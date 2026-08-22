from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire


def _wire(claims: list[dict], *, gameplay: dict | None = None, targeting: bool = False) -> dict:
    entity: dict = {
        "id": "item_body",
        "kind": "item_body",
        "visualRole": "inventory_item",
        "events": [],
    }
    if targeting:
        entity["targeting"] = {"shotEntity": "shot_proj", "intervalTicks": 60, "rangeTiles": 10, "sameTargetBias": 0.5}
    data: dict = {
        "runtimeProgram": {
            "apiVersion": "infini.runtime-program.v5",
            "schema": "infini.runtime-program.wire.v3",
            "primaryEntityId": "item_body",
            "itemEntityId": "item_body",
            "limits": {"maxEntityCount": 12, "maxChildDepth": 3, "maxEventSpawnsPerActivation": 32},
            "entities": [entity],
            "bindings": [],
        },
        "runtimeContract": {
            "schema": "infini.runtime-contract.low-level.v1",
            "parentSynthesis": {
                "composition": "c",
                "parentA": {"facts": ["f"], "runtimeRoles": ["r"]},
                "parentB": {"facts": ["f"], "runtimeRoles": ["r"]},
            },
            "finalWireReceipts": [],
            "claims": claims,
        },
    }
    if gameplay is not None:
        data["gameplay"] = gameplay
    return data


def test_mobility_promise_requires_delivered_mobility_mode() -> None:
    wire = _wire([{
        "id": "claim_blink", "kind": "gameplay",
        "text": "Blinks the player toward the cursor on use.",
        "backedBy": [],
    }])
    report = validate_runtime_wire(wire)
    codes = {row.get("code") for row in report.get("errors", [])}
    assert "unbacked_promise_capability" in codes, codes


def test_mobility_promise_with_delivered_mode_passes() -> None:
    wire = _wire(
        [{
            "id": "claim_blink", "kind": "gameplay",
            "text": "Blinks the player toward the cursor on use.",
            "backedBy": [],
        }],
        gameplay={"mobilityMode": "blink_to_cursor"},
    )
    report = validate_runtime_wire(wire)
    parity = [row for row in report.get("errors", []) if row.get("code") == "unbacked_promise_capability"]
    assert parity == [], parity


def test_minion_promise_requires_targeting_component() -> None:
    claims = [{"id": "c1", "kind": "gameplay", "text": "Summons a loyal minion companion.", "backedBy": []}]
    without = validate_runtime_wire(_wire(claims))
    assert any(row.get("code") == "unbacked_promise_capability" for row in without.get("errors", []))
    with_targeting = validate_runtime_wire(_wire(claims, targeting=True))
    assert not any(row.get("code") == "unbacked_promise_capability" for row in with_targeting.get("errors", []))


def test_explosion_promise_requires_damage_area_event() -> None:
    wire = _wire([{"id": "c1", "kind": "gameplay", "text": "The vial explodes on impact.", "backedBy": []}])
    report = validate_runtime_wire(wire)
    assert any(row.get("code") == "unbacked_promise_capability" for row in report.get("errors", []))
    wire["runtimeProgram"]["entities"][0]["events"] = [{
        "id": "ev1", "event": "on_expire", "action": "damage_area_on_event",
        "actionCode": 3, "radiusPx": 120, "damageMultiplier": 1.5,
    }]
    report_ok = validate_runtime_wire(wire)
    assert not any(row.get("code") == "unbacked_promise_capability" for row in report_ok.get("errors", []))


def test_non_gameplay_claims_are_not_scanned() -> None:
    wire = _wire([{"id": "c1", "kind": "physical", "text": "Blinks with reflected light.", "backedBy": []}])
    report = validate_runtime_wire(wire)
    assert not any(row.get("code") == "unbacked_promise_capability" for row in report.get("errors", []))
