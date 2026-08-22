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


def test_parity_drift_is_reported_as_warning_not_error() -> None:
    wire = _wire([{
        "id": "claim_blink", "kind": "gameplay",
        "text": "Blinks the player toward the cursor on use.",
        "backedBy": [],
    }])
    report = validate_runtime_wire(wire)
    # Anchoring drift must NOT fail delivery - claims are intent/debug, not a player contract.
    parity_errors = [
        row for row in report.get("errors", [])
        if row.get("code") == "unbacked_promise_capability"
    ]
    assert parity_errors == [], parity_errors
    assert len(report["promiseParityWarnings"]) == 1
    warning = report["promiseParityWarnings"][0]
    assert warning["code"] == "unbacked_promise_capability"
    assert "mobilityMode" in warning["message"]


def test_aligned_promise_produces_no_warning() -> None:
    wire = _wire(
        [{
            "id": "claim_blink", "kind": "gameplay",
            "text": "Blinks the player toward the cursor on use.",
            "backedBy": [],
        }],
        gameplay={"mobilityMode": "blink_to_cursor"},
    )
    report = validate_runtime_wire(wire)
    assert report["promiseParityWarnings"] == []


def test_targeting_parity_warning_and_alignment() -> None:
    claims = [{"id": "c1", "kind": "gameplay", "text": "Summons a loyal minion companion.", "backedBy": []}]
    drifted = validate_runtime_wire(_wire(claims))
    assert len(drifted["promiseParityWarnings"]) == 1
    aligned = validate_runtime_wire(_wire(claims, targeting=True))
    assert aligned["promiseParityWarnings"] == []


def test_event_surface_parity_warning_and_alignment() -> None:
    wire = _wire([{"id": "c1", "kind": "gameplay", "text": "The vial explodes on impact.", "backedBy": []}])
    drifted = validate_runtime_wire(wire)
    assert len(drifted["promiseParityWarnings"]) == 1
    wire["runtimeProgram"]["entities"][0]["events"] = [{
        "id": "ev1", "event": "on_expire", "action": "damage_area_on_event",
        "actionCode": 3, "radiusPx": 120, "damageMultiplier": 1.5,
    }]
    aligned = validate_runtime_wire(wire)
    assert aligned["promiseParityWarnings"] == []


def test_non_gameplay_claims_are_not_scanned() -> None:
    wire = _wire([{"id": "c1", "kind": "physical", "text": "Blinks with reflected light.", "backedBy": []}])
    report = validate_runtime_wire(wire)
    assert report["promiseParityWarnings"] == []
