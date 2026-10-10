"""Offline canonical vfx frozen boundary contracts; no live services."""
from __future__ import annotations

from pathlib import Path
from tests.vfx_image_fixtures import apply_edits

import copy
import json
import pytest
from infini_local.core import vfx_manifest as vfx
from infini_local.core.errors import PlannerUnavailable
from tests.test_repair_vfx_contract import _patch
from infini_local.core.runtime_authoring import compile_runtime_program
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.pipelines import llm_authoring_pipeline as stage
from tests.test_low_level_three_stage_pipeline import _vfx_output
from tests.test_repair_vfx_contract import _offline_transport
from infini_local.pipelines import visual_delivery_gate, visual_sprite_generation
from infini_local.storage import world_storage
from tests.vfx_material_fixtures import _data, _legacy, _sprite, _with_asset
from tests.test_vfx_dependency_delivery_contracts import visual_data, authored_vfx, roundtrip
from tests.vfx_image_fixtures import _request, offline_backend

BAD_SELECTORS = [
    ("projectileAfterimage", "runtime_geometry", "entity"),
    ("spriteStampTrail", "no_asset", "entity"),
    ("actorAfterimage", "no_asset", "projectile"),
    ("projectileAfterimage", "reuse_item_icon", "field"),
]


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


@pytest.mark.parametrize("renderer,selector", [
    ("projectileAfterimage", "entity"),
    ("projectileAfterimage", "projectile"),
    ("projectileAfterimage", "field"),
    ("projectileAfterimage", "impact"),
    ("spriteElement", "entity"),
    ("texturedPath", "entity"),
])
def test_unknown_entity_pair_repairs_without_thawing_valid_texture_selector(
    offline_backend, monkeypatch, renderer, selector,
):
    calls, _ = offline_backend
    data = visual_data("reuse_item_icon")
    if selector == "field":
        entity = data["runtimeProgram"]["entities"][1]
        entity.update(kind="field", visualRole="field")
        entity["visual"]["role"] = "field"
    accepted = authored_vfx(renderer, selector)
    if selector == "impact":
        producer = authored_vfx("impactSprite", "impact")["slots"][0]
        producer.update(id="impact_producer", spritePrompt="one literal amber impact")
        accepted["slots"].append(producer)
        vfx._hydrate_vfx_asset_prompts(data, accepted)
    assert vfx.validate_vfx_director_output(accepted, data)["ok"]
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["entityId"] = "missing_entity"
    before, raw_before = copy.deepcopy(data), copy.deepcopy(raw)
    projection = vfx.vfx_png_dependencies(data, raw, require_used=True)
    assert projection["errors"] == [], "unresolved entity is not a diagnosed broken PNG selector"
    assert all(row["slotId"] != "selected" for row in projection["dependencies"])
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert {error["path"] for error in report["errors"]} == {"$.slots[0]", "$.slots[0].entityId"}
    candidate = copy.deepcopy(accepted["slots"][0])
    candidate.update(alpha=0.1, scale=2.0)
    selector_path = "textureRole"
    if renderer in {"spriteElement", "texturedPath"}:
        name = "element" if renderer == "spriteElement" else "path"
        candidate[name]["texture"]["source"] = "item"
        selector_path = name + ".texture.source"
    else:
        candidate["textureRole"] = "item"
    patch = _patch(slotsUpsert=[candidate], slotIdsDelete=["selected"], effectMagnitude=0.9,
                   assetsUpsert=[_request("compensation")])
    sent = _offline_transport(monkeypatch, "unknown_entity_" + renderer + "_" + selector, [raw, patch])
    final = vfx.attach_hybrid_vfx_manifest(data, "unknown_pair", llm_director=stage.call_llm_vfx_director)
    assert len(sent) == 2 and calls == []
    director, repair = [json.loads(request["messages"][1]["content"]) for request in sent]
    scope = repair["repairScope"]
    assert scope["fieldPermissions"] == {
        "globals": {}, "slots": [{"slotId": "selected", "paths": ["entityId", "event"]}], "assets": [],
    }
    assert not scope["allowCreateSlots"] and not scope["allowCreateAssets"]
    assert final["debug"]["vfxDirectorRaw"] == accepted
    assert final["runtimeProgram"] == before["runtimeProgram"] and final["visualKit"] == before["visualKit"]
    assert repair["acceptedVisualKitReadOnly"] == director["acceptedVisualKit"] == before["visualKit"]
    audit = final["debug"]["vfxRepairFilterAudit"]
    assert audit["acceptedPaths"] == ["$.slotsUpsert[0].entityId"]
    assert any(row["path"] == "$.slotsUpsert[0]." + selector_path for row in audit["ignoredChanges"])
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert raw == raw_before

def test_unknown_entity_pairs_keep_shared_ingredient_request_frozen(offline_backend, monkeypatch):
    calls, _ = offline_backend
    data = visual_data("reuse_item_icon")
    accepted = authored_vfx("spriteElement", "asset")
    other = authored_vfx("texturedPath", "asset")["slots"][0]
    other["id"] = "other_consumer"
    accepted["slots"].append(other)
    accepted["assets"] = [_request("shared")]
    for slot in accepted["slots"]:
        name = "element" if slot["rendererKind"] == "spriteElement" else "path"
        slot[name]["texture"]["assetId"] = "shared"
    assert vfx.validate_vfx_director_output(accepted, data)["ok"]
    raw = copy.deepcopy(accepted)
    for slot in raw["slots"]:
        slot["entityId"] = "missing_entity"
    projection = vfx.vfx_png_dependencies(data, raw, require_used=True)
    assert projection["errors"] == []
    assert [row["role"] for row in projection["dependencies"]] == ["vfx:shared", "vfx:shared"]
    hostile_asset = {**accepted["assets"][0], "prompt": "unrequested replacement artwork"}
    patch = _patch(slotsUpsert=accepted["slots"], assetsUpsert=[hostile_asset], assetIdsDelete=["shared"])
    sent = _offline_transport(monkeypatch, "unknown_pairs_shared_ingredient", [raw, patch])
    final = vfx.attach_hybrid_vfx_manifest(data, "unknown_pairs_shared_ingredient", llm_director=stage.call_llm_vfx_director)
    assert len(sent) == 2 and calls == []
    repair = json.loads(sent[1]["messages"][1]["content"])
    scope = repair["repairScope"]
    assert scope["fieldPermissions"] == {
        "globals": {}, "slots": [
            {"slotId": "other_consumer", "paths": ["entityId", "event"]},
            {"slotId": "selected", "paths": ["entityId", "event"]},
        ], "assets": [],
    }
    assert scope["deletableAssetIds"] == scope["deletableAssetIndices"] == []
    assert not scope["allowCreateAssets"]
    assert final["debug"]["vfxDirectorRaw"] == accepted
    assert vfx.validate_vfx_manifest_wire(final)["ok"]

@pytest.mark.parametrize("renderer,mode,selector", BAD_SELECTORS)
def test_bad_legacy_selector_repairs_only_exact_leaf_before_image_jobs(
    offline_backend, monkeypatch, tmp_path, renderer, mode, selector,
):
    calls, _ = offline_backend
    data, raw = visual_data(mode), authored_vfx(renderer, selector)
    before, raw_before = copy.deepcopy(data), copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert calls == [] and data == before and raw == raw_before
    candidate = copy.deepcopy(raw["slots"][0])
    candidate.update(textureRole="item", entityId="item", event="on_hit", alpha=0.1, duration=120,
                     rendererKind="impactSprite", spritePrompt="unrequested compensating image")
    correction = _patch(slotsUpsert=[candidate], slotIdsDelete=["selected"],
                        assetsUpsert=[{"id": "compensation", "prompt": "unrequested art", "negativePrompt": "",
                                       "canvasSize": 64, "layout": "strip"}], effectMagnitude=0.9)
    sent = _offline_transport(monkeypatch, "legacy_" + renderer + "_" + mode + "_" + selector, [raw, correction])
    final = vfx.attach_hybrid_vfx_manifest(data, "png_dependencies", llm_director=stage.call_llm_vfx_director)
    assert len(sent) == 2 and calls == [], "real VFX stage failed to invoke the required bounded Repair"
    assert not report["ok"], "legacy PNG consumer admitted a producer that cannot resolve"
    assert {error["path"] for error in report["errors"]} == {"$.slots[0].textureRole"}
    director, repair = [json.loads(request["messages"][1]["content"]) for request in sent]
    assert [request["model"] for request in sent] == ["explicit-offline-fixture-model"] * 2
    assert repair["repairScope"]["fieldPermissions"] == {
        "globals": {}, "slots": [{"slotId": "selected", "paths": ["textureRole"]}], "assets": [],
    }
    assert not repair["repairScope"]["allowCreateSlots"] and not repair["repairScope"]["allowCreateAssets"]
    assert repair["acceptedVisualKitReadOnly"] == director["acceptedVisualKit"] == before["visualKit"]
    assert repair["acceptedRuntimeProgramReadOnly"] == director["acceptedRuntimeProgramReadOnly"]
    expected = copy.deepcopy(raw_before)
    expected["slots"][0]["textureRole"] = "item"  # This choice is the explicit offline Repair response.
    assert final["debug"]["vfxDirectorRaw"] == expected
    assert final["runtimeProgram"] == before["runtimeProgram"] and final["visualKit"] == before["visualKit"]
    assert final["debug"]["vfxRepairFilterAudit"]["acceptedPaths"] == ["$.slotsUpsert[0].textureRole"]
    final = visual_sprite_generation.maybe_generate_visual_assets(final)
    assert len(calls) == 1
    assert visual_delivery_gate.visual_delivery_report(final, check_backend_config=False)["ok"]
    roundtrip(final, tmp_path / "accepted")
    stale = copy.deepcopy(final)
    stale["vfxManifest"] = vfx._compile_manifest(before, raw_before, "png_dependencies")
    assert not vfx.validate_vfx_manifest_wire(stale)["ok"]
    assert not visual_delivery_gate.visual_delivery_report(stale, check_backend_config=False)["ok"]
    assert not world_storage.is_deliverable_recipe_payload(stale)
    assert raw == raw_before

FROZEN_MERGES = json.loads((Path(__file__).parent / "fixtures/vfx_image_frozen_merges.json").read_text())

@pytest.mark.parametrize("case", FROZEN_MERGES, ids=[case["id"] for case in FROZEN_MERGES])
def test_frozen_material_boundary(case):
    data = _data()
    templates = {"sprite": _sprite(data), "asset": _with_asset(data), "legacy": _legacy(data)}
    raw = apply_edits(templates[case["base"]], case["rawEdits"])
    # Adapt only the old sound witnesses to the new fresh-author requirement;
    # captured edits/scopes stay byte-identical and keep their original oracle.
    for slot in raw["slots"]:
        if isinstance(slot, dict) and slot.get("rendererKind") == "soundCue":
            slot["soundId"] = "Item1"
            slot["sound"] = {"volume": 0.4, "pitch": 0, "pitchVariance": 0}
    before, gameplay = copy.deepcopy(raw), copy.deepcopy(data["runtimeProgram"])
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert sorted({row["path"] for row in report["errors"]}) == case["errorPaths"]
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    assert scope == case["scope"]
    patch = _patch(slotsUpsert=[copy.deepcopy(raw["slots"][index]) for index in case["slotIndices"]],
                   assetsUpsert=[copy.deepcopy(raw["assets"][index]) for index in case["assetIndices"]])
    apply_edits(patch, case["patchEdits"])
    expected = apply_edits(copy.deepcopy(raw), case["mergedEdits"])
    repaired, audit = vfx._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    assert repaired == expected
    assert audit["ok"] is case["auditOk"]
    assert audit["acceptedPaths"] == case["acceptedPaths"]
    assert [row["path"] for row in audit["ignoredChanges"]] == case["ignoredPaths"]
    assert vfx.validate_vfx_director_output(repaired, data)["ok"] is case["validMerged"]
    responses = iter([raw, patch])
    packets = []
    def reply(_system, _user, *_args, **kwargs):
        if kwargs.get("messages"):
            packets.append(json.loads(kwargs["messages"][1]["content"]))
        return next(responses)
    if case["validMerged"]:
        final = vfx.attach_hybrid_vfx_manifest(data, "frozen_material", llm_director=reply)
        assert final["debug"]["vfxDirectorRaw"] == expected
        assert vfx.validate_vfx_manifest_wire(final)["ok"]
        assert len(final["vfxManifest"]["slots"]) == len(expected["slots"])
        for compiled, accepted in zip(final["vfxManifest"]["slots"], expected["slots"]):
            for payload in ("element", "path"):
                assert compiled.get(payload) == accepted.get(payload)
            assert compiled["alpha"] == accepted["alpha"]
    else:
        with pytest.raises(PlannerUnavailable, match="VFX Repair did not produce"):
            vfx.attach_hybrid_vfx_manifest(data, "frozen_material", llm_director=reply)
        assert "vfxManifest" not in data
    assert len(packets) == 1 and packets[0]["repairScope"] == scope
    assert data["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 1
    assert next(responses, None) is None
    assert raw == before and data["runtimeProgram"] == gameplay
