"""Shared Gameplay/Visual scopes consume the canonical exact JSON locations."""
from __future__ import annotations

# pyright: reportPrivateUsage=false

import copy
import json
from typing import Any

import pytest

from infini_local.core.runtime_authoring import (
    apply_repair_patch, build_runtime_repair_scope, compile_runtime_program,
    filter_repair_patch_scope, validate_runtime_program,
)
from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.qa.capability_witnesses import build_capability_witness
from tests.test_visual_presentation_metadata import kit


@pytest.mark.parametrize("nested", [False, True])
def test_gameplay_foreign_literal_key_does_not_open_valid_call_or_parameter(nested: bool) -> None:
    raw = build_capability_witness("configure_item_stats")
    call = next(row for row in raw["runtimeProgram"]["calls"] if row["fn"] == "configure_item_stats")
    candidate = copy.deepcopy(call)
    candidate["params"]["damage"] += 1
    key = "damage.fake" if nested else "params.damage"
    container = call["params"] if nested else call
    container[key] = "foreign"
    before = copy.deepcopy(raw)
    prefix = "params" if nested else ""
    relative = prefix + "[" + json.dumps(key) + "]"
    report = validate_runtime_program(raw)
    assert not report["ok"]
    scope = build_runtime_repair_scope(raw, report["errors"])
    assert scope["fieldPermissions"]["calls"] == [{"id": call["id"], "paths": [relative]}]
    deletion = "callParamKeysDelete" if nested else "callPropertyKeysDelete"
    assert scope["deletable"]["callParamKeys" if nested else "callPropertyKeys"] == [{"callId": call["id"], "key": key}]
    patch = {"note": "remove exact foreign member", "callsUpsert": [candidate],
             deletion: [{"callId": call["id"], "key": key}]}
    filtered, audit = filter_repair_patch_scope(raw, patch, scope)
    assert audit["ok"], audit
    merged = apply_repair_patch(raw, filtered)
    expected = copy.deepcopy(raw)
    target = next(row for row in expected["runtimeProgram"]["calls"] if row["id"] == call["id"])
    (target["params"] if nested else target).pop(key)
    assert merged == expected
    assert validate_runtime_program(merged)["ok"]
    assert compile_runtime_program(merged)
    assert raw == before


@pytest.mark.parametrize("domain", ["entity", "item_grip"])
def test_visual_foreign_literal_key_does_not_open_valid_entity_or_grip(domain: str) -> None:
    raw = kit()
    if domain == "entity":
        original = raw["entities"][0]
        candidate = copy.deepcopy(original)
        candidate["scale"] = 2.0
        key = "scale.extra"
        original[key] = "foreign"
        relative = "[" + json.dumps(key) + "]"
        patch_edits = {"entitiesUpsert": [candidate]}
    else:
        original = raw["item"]
        original["grip"] = {"normalizedX": 0.25, "normalizedY": 0.75}
        candidate = {"grip": {"normalizedX": 0.9, "normalizedY": 0.1}}
        key = "normalizedX.extra"
        original["grip"][key] = "foreign"
        relative = "grip[" + json.dumps(key) + "]"
        patch_edits = {"itemPatch": candidate}
    before = copy.deepcopy(raw)
    _, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert errors
    scope = visual._build_visual_repair_scope(raw, errors, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    if domain == "entity":
        assert scope["fieldPermissions"]["entities"] == [{"entityId": "opaque_id", "paths": [relative]}]
    else:
        assert scope["fieldPermissions"]["itemPaths"] == [relative]
    patch: dict[str, Any] = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch=None, equipOverlayPatch=None,
                 entitiesUpsert=[], entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None,
                 note="remove exact foreign member")
    patch.update(patch_edits)
    repaired, audit = visual._apply_visual_repair_patch(raw, patch, scope, ["opaque_id"], return_audit=True)
    expected = copy.deepcopy(raw)
    (expected["entities"][0] if domain == "entity" else expected["item"]["grip"]).pop(key)
    assert repaired == expected
    assert audit["ok"] and audit["ignoredChanges"]
    assert not visual._validate_kit(repaired, ["opaque_id"], "opaque_id", equipment_overlay_required=True)[1]
    assert raw == before
