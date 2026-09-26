"""Renderer-dependent choices must be visible before Director/Repair emits a slot."""
from __future__ import annotations

import copy
import json
from itertools import product

import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring import compile_runtime_program, strict_schema_errors
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from test_low_level_three_stage_pipeline import _vfx_output


def _packet(data: dict, repair: bool) -> dict:
    sent = []

    def capture(_system, user, *args, **kwargs):
        sent.append(json.loads(kwargs["messages"][1]["content"]) if repair else user)
        return {}

    packet = vfx._prompt_packet(data, None, None)
    if repair:
        vfx._request(capture, packet, repair_errors=[{"path": "$.slots[0].lane", "message": "invalid"}],
                     previous={"slots": []}, repair_scope={"fieldPermissions": {"slots": []}})
    else:
        vfx._request(capture, packet)
    return json.loads(json.dumps(sent[0]))


@pytest.mark.parametrize("repair", [False, True])
@pytest.mark.parametrize("renderer,required,invalid", [
    ("lightCue", {"channel": "light", "lane": "cue"}, {"channel": "coreGlow", "lane": "accent"}),
    ("soundCue", {"channel": "sound", "lane": "cue"}, {"channel": "ambientParticles", "lane": "support"}),
    ("impactSprite", {"textureRole": "impact"}, {"textureRole": "entity"}),
])
def test_sent_slot_schema_expresses_existing_renderer_requirements(repair, renderer, required, invalid):
    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    packet = _packet(data, repair)
    key = "slotsUpsert" if repair else "slots"
    schema = packet["outputSchema"]["properties"][key]["items"]
    raw = _vfx_output(data)
    slot = raw["slots"][0]
    slot.update({"rendererKind": renderer, **required})
    if renderer == "impactSprite":
        slot["spritePrompt"] = "one transparent impact sprite"
    assert not strict_schema_errors(slot, schema)
    assert vfx.validate_vfx_director_output(raw, data)["ok"]
    for field, value in invalid.items():
        broken = copy.deepcopy(raw)
        broken["slots"][0][field] = value
        assert not vfx.validate_vfx_director_output(broken, data)["ok"]
        assert strict_schema_errors(broken["slots"][0], schema), (
            "The model-facing schema permits a combination rejected by the runtime", renderer, field,
        )
    surface = packet["runtimeSurfaceReadOnly"] if repair else packet["runtimeSurface"]
    assert surface["rendererRequirements"][renderer] == required


def test_renderer_channel_lane_domain_matches_existing_runtime_invariants():
    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    surface = vfx.vfx_director_surface(data)
    schema = vfx.vfx_director_schema(data)["properties"]["slots"]["items"]
    raw = _vfx_output(data)
    slot = raw["slots"][0]
    for renderer, channel, lane in product(surface["rendererKind"], surface["channel"], surface["lane"]):
        slot.update(rendererKind=renderer, channel=channel, lane=lane,
                    textureRole="impact" if renderer == "impactSprite" else "entity",
                    spritePrompt="one transparent impact sprite" if renderer == "impactSprite" else "")
        expected = (renderer not in {"lightCue", "soundCue"}
                    or (channel, lane) == ("light" if renderer == "lightCue" else "sound", "cue"))
        before = copy.deepcopy(raw)
        assert (not strict_schema_errors(slot, schema)) == expected, (renderer, channel, lane)
        result = vfx.validate_vfx_director_output(raw, data)
        assert result["ok"] == expected, (renderer, channel, lane, result["errors"])
        assert raw == before
        if expected:
            assert result["normalized"]["slots"][0] == slot


def test_renderer_conditional_errors_keep_repair_leaf_local():
    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    raw = _vfx_output(data)
    raw["slots"][0].update(rendererKind="lightCue", channel="coreGlow", lane="accent")
    report = vfx.validate_vfx_director_output(raw, data)
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    assert scope["fieldPermissions"]["slots"] == [{"slotId": "slot_0", "paths": ["channel", "lane"]}]
    corrected = copy.deepcopy(raw["slots"][0])
    corrected.update(channel="light", lane="cue", scale=2.75)
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "effectMagnitude": None,
             "visualBudgetClass": None, "motif": None, "slotsUpsert": [corrected],
             "slotIdsDelete": [], "slotIndicesDelete": [], "note": "repair the cue tuple"}
    repaired, audit = vfx._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    assert audit["ok"]
    expected = copy.deepcopy(raw)
    expected["slots"][0].update(channel="light", lane="cue")
    assert repaired == expected
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]
    assert any(row["path"].endswith(".scale") for row in audit["ignoredChanges"])


def test_repair_filters_frozen_tuple_before_semantic_validation():
    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    raw = _vfx_output(data)
    valid_event = raw["slots"][0]["event"]
    raw["slots"][0].update(rendererKind="lightCue", channel="light", lane="cue", event="on_spawn")
    report = vfx.validate_vfx_director_output(raw, data)
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    assert scope["fieldPermissions"]["slots"] == [{"slotId": "slot_0", "paths": ["entityId", "event"]}]
    candidate = copy.deepcopy(raw["slots"][0])
    candidate.update(event=valid_event, lane="primary")
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "effectMagnitude": None,
             "visualBudgetClass": None, "motif": None, "slotsUpsert": [candidate],
             "slotIdsDelete": [], "slotIndicesDelete": [], "note": "fix event, freeze unrelated lane rewrite"}
    repaired, audit = vfx._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    expected = copy.deepcopy(raw)
    expected["slots"][0]["event"] = valid_event
    assert repaired == expected
    assert audit["ok"] and any(row["path"].endswith(".lane") for row in audit["ignoredChanges"])
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]


def test_public_vfx_boundary_rejects_invalid_tuple_after_one_repair():
    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    raw = _vfx_output(data)
    raw["slots"][0].update(rendererKind="lightCue", channel="light", lane="primary")
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["lane"] = "support"
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "effectMagnitude": None,
             "visualBudgetClass": None, "motif": None, "slotsUpsert": [candidate],
             "slotIdsDelete": [], "slotIndicesDelete": [], "note": "still-invalid cue lane"}
    replies = iter([raw, patch])
    with pytest.raises(PlannerUnavailable, match="VFX Repair did not produce"):
        vfx.attach_hybrid_vfx_manifest(data, "renderer_boundary", llm_director=lambda *_a, **_kw: next(replies))
    assert next(replies, None) is None
    assert "vfxManifest" not in data
    assert data["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 1
