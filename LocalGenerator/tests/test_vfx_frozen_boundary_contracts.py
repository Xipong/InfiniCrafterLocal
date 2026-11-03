"""Offline canonical vfx frozen boundary contracts; no live services."""
from __future__ import annotations
from prompt_packet_helpers import request_dossier

from pathlib import Path
from tests.vfx_image_fixtures import apply_edits

import copy
import json
import pytest
import infini_local.core.vfx.contract as vfx_contract
import infini_local.core.vfx.projection as vfx_projection
import infini_local.core.vfx.repair as vfx_repair
import infini_local.core.vfx.validation as vfx_validation
import infini_local.pipelines.vfx.stage as vfx_stage
from infini_local.core.errors import PlannerUnavailable
from tests.test_repair_vfx_contract import _patch
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.pipelines.vfx import request as stage
from tests.test_low_level_three_stage_pipeline import _vfx_output
from tests.test_repair_vfx_contract import _offline_transport
from infini_local.pipelines.visual import delivery as visual_delivery_gate
from infini_local.pipelines.images import stage as visual_sprite_generation
from infini_local.storage import world_storage
from tests.vfx_material_fixtures import _data, _legacy, _native, _shape, _sprite, _with_asset
from tests.test_vfx_dependency_delivery_contracts import visual_data, authored_vfx, roundtrip
from tests.vfx_image_fixtures import _request, offline_backend as offline_backend

BAD_SELECTORS = [
    pytest.param("historyTrail", "runtime_geometry", "entity", id="geometry-afterimage"),
    pytest.param("historyTrail", "no_asset", "entity", id="missing-stamp-png"),
    pytest.param("historyTrail", "no_asset", "projectile", id="missing-actor-png"),
    pytest.param("historyTrail", "reuse_item_icon", "field", id="field-role-mismatch"),
]


def _serialized_vfx_repair(monkeypatch, data, raw, patch, case, image_calls):
    sent = _offline_transport(monkeypatch, case, [raw, patch])
    final = vfx_stage.attach_vfx_manifest(data, case, llm_director=stage.call_llm_vfx_director)
    assert len(sent) == 2 and image_calls == []
    assert [request["model"] for request in sent] == ["explicit-offline-fixture-model"] * 2
    assert vfx_validation.validate_vfx_manifest_wire(final)["ok"]
    director, repair = [request_dossier(request) for request in sent]
    return final, director, repair


def test_public_vfx_boundary_rejects_invalid_tuple_after_one_repair():
    data = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    raw = _native(data, "nativeLight")
    raw["slots"][0]["color"]["r"] = 256
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["color"]["r"] = 256
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA,
               "slotsUpsert": [candidate],
             "slotIdsDelete": [], "slotIndicesDelete": [], "note": "still-invalid local RGB byte"}
    replies = iter([raw, patch])
    with pytest.raises(PlannerUnavailable, match="VFX Repair did not produce"):
        vfx_stage.attach_vfx_manifest(data, "renderer_boundary", llm_director=lambda *_a, **_kw: next(replies))
    assert next(replies, None) is None
    assert "vfxManifest" not in data
    assert data["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 1


@pytest.mark.parametrize("renderer,selector", [
    pytest.param("historyTrail", "entity", id="entity-texture"),

    pytest.param("spriteElement", "asset", id="named-asset-producer"),
    pytest.param("spriteElement", "entity", id="element-source"),
    pytest.param("texturedPath", "entity", id="path-source"),
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
    if selector == "asset":
        accepted["assets"] = [_request("exact_impact")]
        accepted["slots"][0]["element"]["texture"]["assetId"] = "exact_impact"
    assert vfx_validation.validate_vfx_director_output(accepted, data)["ok"]
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["entityId"] = "missing_entity"
    before, raw_before = copy.deepcopy(data), copy.deepcopy(raw)
    projection = vfx_validation.vfx_png_dependencies(data, raw, require_used=True)
    assert projection["errors"] == [], "unresolved entity is not a diagnosed broken PNG selector"
    if selector == "asset":
        assert [row["role"] for row in projection["dependencies"]] == ["vfx:exact_impact"]
    else:
        assert all(row["slotId"] != "selected" for row in projection["dependencies"])
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert {error["path"] for error in report["errors"]} == {"$.slots[0]", "$.slots[0].entityId"}
    candidate = copy.deepcopy(accepted["slots"][0])
    candidate.update(alpha=0.1)
    selector_path = "textureRole"
    if renderer in {"spriteElement", "texturedPath", "historyTrail"}:
        name = "element" if renderer == "spriteElement" else "trail" if renderer == "historyTrail" else "path"
        candidate[name]["texture"]["source"] = "item"
        selector_path = name + ".texture.source"
    else:
        candidate["textureRole"] = "item"
    patch = _patch(slotsUpsert=[candidate], slotIdsDelete=["selected"],
                   assetsUpsert=[_request("compensation")])
    final, director, repair = _serialized_vfx_repair(
        monkeypatch, data, raw, patch, "unknown_entity_" + renderer + "_" + selector, calls)
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
    assert vfx_validation.validate_vfx_manifest_wire(final)["ok"]
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
    assert vfx_validation.validate_vfx_director_output(accepted, data)["ok"]
    raw = copy.deepcopy(accepted)
    for slot in raw["slots"]:
        slot["entityId"] = "missing_entity"
    projection = vfx_validation.vfx_png_dependencies(data, raw, require_used=True)
    assert projection["errors"] == []
    assert [row["role"] for row in projection["dependencies"]] == ["vfx:shared", "vfx:shared"]
    hostile_asset = {**accepted["assets"][0], "prompt": "unrequested replacement artwork"}
    patch = _patch(slotsUpsert=accepted["slots"], assetsUpsert=[hostile_asset], assetIdsDelete=["shared"])
    final, _, repair = _serialized_vfx_repair(monkeypatch, data, raw, patch, "unknown_pairs_shared_ingredient", calls)
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
    assert vfx_validation.validate_vfx_manifest_wire(final)["ok"]

@pytest.mark.parametrize("renderer,mode,selector", BAD_SELECTORS)
def test_bad_legacy_selector_repairs_only_exact_leaf_before_image_jobs(
    offline_backend, monkeypatch, tmp_path, renderer, mode, selector,
):
    calls, _ = offline_backend
    data, raw = visual_data(mode), authored_vfx(renderer, selector)
    before, raw_before = copy.deepcopy(data), copy.deepcopy(raw)
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert calls == [] and data == before and raw == raw_before
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["trail"]["texture"]["source"] = "item"
    candidate.update(entityId="item", event="on_hit", alpha=0.1, duration=120,
                     rendererKind="spriteElement", element=_sprite(data)["slots"][0]["element"])
    correction = _patch(slotsUpsert=[candidate], slotIdsDelete=["selected"],
                        assetsUpsert=[{"id": "compensation", "prompt": "unrequested art", "negativePrompt": "",
                                       "canvasSize": 64, "layout": "strip"}])
    final, director, repair = _serialized_vfx_repair(
        monkeypatch, data, raw, correction, "legacy_" + renderer + "_" + mode + "_" + selector, calls)
    assert not report["ok"], "legacy PNG consumer admitted a producer that cannot resolve"
    assert {error["path"] for error in report["errors"]} == {"$.slots[0].trail.texture.source"}
    assert repair["repairScope"]["fieldPermissions"] == {
        "globals": {}, "slots": [{"slotId": "selected", "paths": ["trail.texture.source"]}], "assets": [],
    }
    assert not repair["repairScope"]["allowCreateSlots"] and not repair["repairScope"]["allowCreateAssets"]
    assert repair["acceptedVisualKitReadOnly"] == director["acceptedVisualKit"] == before["visualKit"]
    assert repair["acceptedRuntimeProgramReadOnly"] == director["acceptedRuntimeProgramReadOnly"]
    expected = copy.deepcopy(raw_before)
    expected["slots"][0]["trail"]["texture"]["source"] = "item"  # This choice is the explicit offline Repair response.
    assert final["debug"]["vfxDirectorRaw"] == expected
    assert final["runtimeProgram"] == before["runtimeProgram"] and final["visualKit"] == before["visualKit"]
    assert final["debug"]["vfxRepairFilterAudit"]["acceptedPaths"] == ["$.slotsUpsert[0].trail.texture.source"]
    final = visual_sprite_generation.maybe_generate_visual_assets(final)
    assert len(calls) == 1
    assert visual_delivery_gate.visual_delivery_report(final, check_backend_config=False)["ok"]
    roundtrip(final, tmp_path / "accepted")
    stale = copy.deepcopy(final)
    stale["vfxManifest"] = vfx_projection._compile_manifest(before, raw_before, "png_dependencies")
    assert not vfx_validation.validate_vfx_manifest_wire(stale)["ok"]
    assert not visual_delivery_gate.visual_delivery_report(stale, check_backend_config=False)["ok"]
    assert not world_storage.is_deliverable_recipe_payload(stale)
    assert raw == raw_before

FROZEN_MERGES = json.loads((Path(__file__).parent / "fixtures/vfx_image_frozen_merges.json").read_text())

@pytest.mark.parametrize("case", FROZEN_MERGES, ids=[case["id"] for case in FROZEN_MERGES])
def test_frozen_material_boundary(case):
    data = _data()
    templates = {"sprite": _sprite(data), "asset": _with_asset(data), "legacy": _legacy(data)}
    if case["base"] == "legacy" and case["bindings"].get("relative") == "element":
        templates["legacy"] = _shape(data)
        templates["legacy"]["slots"][0]["id"] = "old_slot"
    raw = apply_edits(copy.deepcopy(templates[case["base"]]), case["rawEdits"])
    # Literal whole-slot replacements retain retired placeholder controls. Their
    # historical successful merges are refusal witnesses, not current inputs.
    retired = any(isinstance(slot, dict) and (
        slot.get("rendererKind") not in vfx_contract._FRESH_RENDERERS
        or slot.get("rendererKind") != "impactSprite" and set(slot) & {"spritePrompt", "spriteNegativePrompt"}
        or slot.get("rendererKind") == "texturedPath" and set(slot) & {"duration", "repeatEvery"}
        or slot.get("rendererKind") in {"spriteElement", "texturedPath", "soundCue"}
        and set(slot) & {"scale", "density", "spread", "particleSystemId", "textureRole"}
    ) for slot in raw["slots"])
    if retired:
        before = copy.deepcopy(raw)
        assert not vfx_validation.validate_vfx_director_output(raw, data)["ok"]
        historical_merge = apply_edits(copy.deepcopy(raw), case["mergedEdits"])
        assert not vfx_validation.validate_vfx_director_output(historical_merge, data)["ok"]
        current = _shape(data) if case["base"] == "legacy" else templates[case["base"]]
        assert vfx_validation.validate_vfx_director_output(current, data)["ok"]
        final = vfx_stage.attach_vfx_manifest(data, "current-control-for-retired-witness", llm_director=lambda *_a, **_k: current)
        assert vfx_validation.validate_vfx_manifest_wire(final)["ok"]
        assert raw == before
        return
    before, gameplay = copy.deepcopy(raw), copy.deepcopy(data["runtimeProgram"])
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert sorted({row["path"] for row in report["errors"]}) == case["errorPaths"]
    scope = vfx_repair._build_vfx_repair_scope(raw, report["errors"])
    assert scope == case["scope"]
    patch = _patch(slotsUpsert=[copy.deepcopy(raw["slots"][index]) for index in case["slotIndices"]],
                   assetsUpsert=[copy.deepcopy(raw["assets"][index]) for index in case["assetIndices"]])
    apply_edits(patch, case["patchEdits"])
    expected = apply_edits(copy.deepcopy(raw), case["mergedEdits"])
    repaired, audit = vfx_repair._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    assert repaired == expected
    assert audit["ok"] is case["auditOk"]
    assert audit["acceptedPaths"] == case["acceptedPaths"]
    assert [row["path"] for row in audit["ignoredChanges"]] == case["ignoredPaths"]
    assert vfx_validation.validate_vfx_director_output(repaired, data)["ok"] is case["validMerged"]
    responses = iter([raw, patch])
    packets = []
    def reply(_system, _user, *_args, **kwargs):
        if kwargs.get("messages"):
            packets.append(request_dossier(kwargs))
        return next(responses)
    if case["validMerged"]:
        final = vfx_stage.attach_vfx_manifest(data, "frozen_material", llm_director=reply)
        assert final["debug"]["vfxDirectorRaw"] == expected
        assert vfx_validation.validate_vfx_manifest_wire(final)["ok"]
        assert len(final["vfxManifest"]["slots"]) == len(expected["slots"])
        for compiled, accepted in zip(final["vfxManifest"]["slots"], expected["slots"]):
            for payload in ("element", "path"):
                assert compiled.get(payload) == accepted.get(payload)
            assert ("alpha" in compiled) == ("alpha" in accepted)
            assert compiled.get("alpha") == accepted.get("alpha")
    else:
        with pytest.raises(PlannerUnavailable, match="VFX Repair did not produce"):
            vfx_stage.attach_vfx_manifest(data, "frozen_material", llm_director=reply)
        assert "vfxManifest" not in data
    assert len(packets) == 1 and packets[0]["repairScope"] == scope
    assert data["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 1
    assert next(responses, None) is None
    assert raw == before and data["runtimeProgram"] == gameplay
