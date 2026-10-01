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
from infini_local.pipelines import llm_authoring_pipeline as stage
from test_low_level_three_stage_pipeline import _accepted_visual_data, _vfx_output
from test_vfx_empty_asset_domain_repair import _offline_transport


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


@pytest.mark.parametrize("repair", [False, True])
def test_serialized_director_and_repair_explain_legacy_png_dependencies(monkeypatch, repair):
    data = _accepted_visual_data("workbench_blade")
    accepted = _vfx_output(data)
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["entityId"] = "missing_entity"
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": accepted["slots"], "note": "retarget only the pair"}
    sent = _offline_transport(monkeypatch, "legacy_png_packet", [raw, patch])
    vfx.attach_hybrid_vfx_manifest(data, "legacy_png_guide", llm_director=stage.call_llm_vfx_director)
    assert len(sent) == 2
    packet = json.loads(sent[int(repair)]["messages"][1]["content"])
    surface = packet["runtimeSurfaceReadOnly" if repair else "runtimeSurface"]
    slot_schema = packet["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]
    description = slot_schema["properties"]["textureRole"]["description"]
    for renderer in vfx.SPRITE_TEXTURE_RENDERERS:
        assert renderer in description
    for clause in (
        "item=accepted item PNG", "entity=bound entity baked_sprite/reuse_item_icon PNG",
        "no_asset/runtime_geometry cannot supply one", "projectile/field alias entity only when equal to bound visualRole",
        "same mode requirement", "impact=same-entity impactSprite producer", "none invalid for sprites",
        "Primitive/Dust/cue renderer hints require no PNG",
    ):
        assert clause in description, clause
    assert "projectile/field aliases require exact bound visualRole" in surface["textureDependencyTuples"]["entity"]
    assert surface["textureRole"] == slot_schema["properties"]["textureRole"]["enum"]
    sources = {row["entityId"]: row for row in surface["entityTextureSources"]}
    for entity in data["runtimeProgram"]["entities"]:
        assert sources[entity["id"]]["assetMode"] == entity["visual"]["assetMode"]
    assert packet["acceptedVisualKitReadOnly" if repair else "acceptedVisualKit"] == data["visualKit"]


def test_renderer_channel_lane_domain_matches_existing_runtime_invariants():
    data = _accepted_visual_data("workbench_blade")
    surface = vfx.vfx_director_surface(data)
    schema = vfx.vfx_director_schema(data)["properties"]["slots"]["items"]
    raw = _vfx_output(data)
    slot = raw["slots"][0]
    # New payload-bearing branches have their own neutral-common-field and applicability matrix.
    legacy_renderers = [kind for kind in surface["rendererKind"] if kind not in {"spriteElement", "texturedPath"}]
    for renderer, channel, lane in product(legacy_renderers, surface["channel"], surface["lane"]):
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


@pytest.mark.parametrize("renderer,channel", [("lightCue", "light"), ("soundCue", "sound")])
@pytest.mark.parametrize("broken_fields", [
    ("spritePrompt",), ("spriteNegativePrompt",), ("spritePrompt", "spriteNegativePrompt"),
])
def test_non_sprite_prompt_errors_grant_exact_leaves_and_repair_at_public_boundary(renderer, channel, broken_fields):
    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    raw = _vfx_output(data)
    slot = raw["slots"][0]
    slot.update(rendererKind=renderer, channel=channel, lane="cue")
    for field in broken_fields:
        slot[field] = "unrelated opaque sprite description"
    before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert {row["path"] for row in report["errors"]} == {f"$.slots[0].{field}" for field in broken_fields}
    candidate = copy.deepcopy(slot)
    for field in broken_fields:
        candidate[field] = ""
    candidate["scale"] = 2.75  # Still frozen; fixing a prompt cannot redesign scale.
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [candidate],
             "effectMagnitude": None, "visualBudgetClass": None, "motif": None,
             "slotIdsDelete": [], "slotIndicesDelete": [], "note": "remove non-sprite prompts"}
    replies = iter([raw, patch])
    packets = []

    def respond(*_args, **kwargs):
        if kwargs.get("messages"):
            packets.append(json.loads(kwargs["messages"][1]["content"]))
        return next(replies)

    result = vfx.attach_hybrid_vfx_manifest(data, "non_sprite_prompts", llm_director=respond)
    assert packets[0]["repairScope"]["fieldPermissions"]["slots"] == [
        {"slotId": "slot_0", "paths": sorted(broken_fields)},
    ]
    assert result["vfxManifest"]["slots"][0]["scale"] == slot["scale"]
    assert result["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 1
    assert next(replies, None) is None
    assert raw == before
