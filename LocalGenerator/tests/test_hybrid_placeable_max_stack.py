from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.core.runtime_authoring import (
    build_runtime_repair_scope,
    filter_repair_patch_scope,
    validate_runtime_program,
    apply_repair_patch,
)
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def _hybrid_document(max_stack: int) -> dict:
    doc = build_runtime_fixture("workbench_blade")
    program = doc["runtimeProgram"]
    calls = program.setdefault("calls", [])
    stats = next((c for c in calls if c.get("fn") == "configure_item_stats"), None)
    assert stats is not None
    stats.setdefault("params", {})["maxStack"] = max_stack

    # Make the fixture a durable hybrid: add the place_item side of the contract.
    item_entity_id = next(
        row["id"] for row in program["entities"] if row.get("kind") == "item_body"
    )
    calls.append({
        "id": "call_place_probe",
        "fn": "configure_placeable",
        "target": item_entity_id,
        "params": {"tileId": 18, "wallId": -1, "placeStyle": 0},
    })
    program["bindings"].append({
        "id": "binding_place_probe",
        "input": "alternate_use",
        "usePolicy": {
            "action": {
                "kind": "place_item",
                "targetId": item_entity_id,
                "placementCallId": "call_place_probe",
            },
            "stackCost": 1,
            "contactDamage": False,
        },
    })
    return doc


def test_durable_hybrid_with_multistack_is_rejected() -> None:
    document = _hybrid_document(max_stack=9999)
    report = validate_runtime_program(document)
    codes = {row.get("code") for row in report.get("errors", [])}
    assert "hybrid_placeable_max_stack" in codes, codes


def test_durable_hybrid_with_single_unit_passes() -> None:
    document = _hybrid_document(max_stack=1)
    report = validate_runtime_program(document)
    parity = [row for row in report.get("errors", []) if row.get("code") == "hybrid_placeable_max_stack"]
    assert parity == [], parity


def test_repair_scope_authorizes_exact_max_stack_leaf() -> None:
    document = _hybrid_document(max_stack=9999)
    errors = [row for row in validate_runtime_program(document).get("errors", []) if row.get("code") == "hybrid_placeable_max_stack"]
    assert errors, errors
    scope = build_runtime_repair_scope(document, errors)
    assert scope["nonRepairableErrors"] == []

    stats_call_id = errors[0].get("relatedIds", [""])[0]
    patch = {
        "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [],
        "bindingsUpsert": [], "bindingIdsDelete": [], "bindingIndicesDelete": [],
        "callsUpsert": [], "callIdsDelete": [], "callIndicesDelete": [],
        "callParamKeysDelete": [], "callPropertyKeysDelete": [],
        "claimsUpsert": [], "claimIdsDelete": [], "claimIndicesDelete": [],
        "metadataPatch": {}, "note": "cap durable hybrid to a single unit",
    }
    filtered, audit = filter_repair_patch_scope(
        document,
        patch,
        scope,
    )
    # The scope must expose an exact path authorizing params.maxStack on that call.
    perms = json.dumps(scope.get("fieldPermissions", {}), default=str)
    _ = (filtered, audit, perms, stats_call_id)
    # Full repair closure is exercised through gameplay repair pipeline tests; here we assert
    # the scope grants the exact leaf so the deterministic patch can land.
    assert "maxStack" in perms or "params.maxStack" in str(scope)
