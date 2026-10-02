"""Canonical VFX Repair contracts; actual serialized stage, exact merge and final wire.

Responses are explicit offline choices, never live model or image calls. Director,
Repair and final manifest assertions remain distinct acceptance boundaries.
"""
import copy
import json
import os
from pathlib import Path

import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring import strict_schema_errors
from infini_local.pipelines import llm_authoring_pipeline as stage, llm_transport
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
from tests.vfx_material_fixtures import _asset, _data, _legacy, _path, _sent, _sprite, _with_asset


def _patch(**edits):
    return {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "repair exact diagnosed leaves only", **edits}


def _offline_transport(monkeypatch, case, replies):
    pending, captured = iter(replies), []
    monkeypatch.setattr(stage, "USE_LLM", True)
    monkeypatch.setattr(stage, "resolve_llm_model", lambda: "explicit-offline-fixture-model")
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", "json_object")

    def send(request, **_kwargs):
        captured.append(json.loads(json.dumps(request)))
        if directory := os.environ.get("INFINI_VFX_REPAIR_EVIDENCE_DIR"):
            out = Path(directory)
            out.mkdir(parents=True, exist_ok=True)
            (out / (case + "_requests.json")).write_text(json.dumps({"kind": "hand-authored offline responses, no provider call", "requests": captured, "responses": replies}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"choices": [{"message": {"content": json.dumps(next(pending))}}]}

    monkeypatch.setattr(stage, "llm_chat_json", send)
    return captured


_DOMAIN_CASES = [pytest.param(domain, outcome, id=domain + "-" + outcome)
                 for domain in ("omitted", "empty") for outcome in ("item", "entity", "noop", "valid")]
_DOMAIN_CASES.append(pytest.param("nonempty", "asset", id="nonempty-source-frozen"))


@pytest.mark.parametrize("renderer,payload", [("spriteElement", "element"), ("texturedPath", "path")], ids=["sprite", "path"])
@pytest.mark.parametrize("domain,outcome", _DOMAIN_CASES)
def test_vfx_asset_domain_stage_contract(monkeypatch, renderer, payload, domain, outcome):
    data = _data()
    for entity in data["runtimeProgram"]["entities"]:
        entity["visual"]["assetMode"] = "baked_sprite" if entity["kind"] == "item_body" else "reuse_item_icon"
    raw = _sprite(data) if renderer == "spriteElement" else _path(data)
    raw["slots"][0][payload]["texture"] = {"source": "item" if outcome == "valid" else "asset", "assetId": "" if outcome == "valid" else "missing"}
    if domain != "omitted":
        raw["assets"] = [_asset()] if domain == "nonempty" else []
    before, raw_before = copy.deepcopy(data), copy.deepcopy(raw)
    if outcome != "valid":
        initial_report = vfx.validate_vfx_director_output(raw, data)
        assert not initial_report["ok"]
        initial_scope = vfx._build_vfx_repair_scope(raw, initial_report["errors"])
        initial_paths = [payload + ".texture.assetId", *([payload + ".texture.source"] if domain != "nonempty" else [])]
        assert initial_scope["fieldPermissions"] == {"globals": {}, "slots": [{"slotId": raw["slots"][0]["id"], "paths": initial_paths}], "assets": []}, "empty_domain_selector_permission"
    plan_before = build_visual_asset_plan(data)
    texture = {"source": "item" if outcome == "asset" else outcome, "assetId": _asset()["id"] if outcome == "asset" else ""}
    correction = _patch()
    if outcome in {"item", "entity", "asset"}:
        candidate = copy.deepcopy(raw["slots"][0])
        candidate[payload]["texture"] = texture
        candidate[payload]["widthProfile"].update(start=4.0, middle=4.0, end=4.0)
        candidate[payload]["colorProfile"]["middle"] = "pink"
        candidate[payload]["widthPx"] = 1.0
        if payload == "path":
            candidate[payload]["source"] = "beam"
        candidate.update(entityId=next(row["id"] for row in data["runtimeProgram"]["entities"] if row["id"] != candidate["entityId"]), event="on_hit", alpha=0.1, channel="light", lane="cue", textureRole="impact", spritePrompt="unrequested replacement Visual/image design")
        new_slot = {**copy.deepcopy(_legacy(data)["slots"][0]), "id": "unrequested_slot"}
        assets = [{**_asset(), "prompt": "unrequested redesign", "canvasSize": 64, "layout": "strip"}] if raw.get("assets") else []
        correction = _patch(slotsUpsert=[candidate, new_slot], slotIdsDelete=[raw["slots"][0]["id"]], effectMagnitude=0.9,
                            motif={**raw["motif"], "shapeLanguage": "unrequested redesign"}, assetsUpsert=[*assets, _asset("missing")], assetIdsDelete=[_asset()["id"]])
    case = renderer + "_" + domain + "_" + outcome
    sent = _offline_transport(monkeypatch, case, [raw] if outcome == "valid" else [raw, correction])
    if outcome == "noop":
        scope = vfx._build_vfx_repair_scope(raw, vfx.validate_vfx_director_output(raw, data)["errors"])
        merged, audit = vfx._apply_vfx_repair_patch(data, raw, correction, scope, return_audit=True)
        assert merged == raw_before and audit["acceptedPaths"] == []
        assert not vfx.validate_vfx_director_output(merged, data)["ok"]
        with pytest.raises(PlannerUnavailable, match="VFX Repair did not produce"):
            vfx.attach_hybrid_vfx_manifest(data, case, llm_director=stage.call_llm_vfx_director)
        assert len(sent) == 2 and "vfxManifest" not in data
        final = data
    else:
        expected = copy.deepcopy(raw_before)
        if outcome != "valid":
            expected["slots"][0][payload]["texture"] = ({"source": "asset", "assetId": _asset()["id"]} if domain == "nonempty" else texture)
        expected_plan = build_visual_asset_plan({**before, "vfxManifest": vfx._compile_manifest(before, expected, case)}) if domain == "nonempty" else plan_before
        final = vfx.attach_hybrid_vfx_manifest(data, case, llm_director=stage.call_llm_vfx_director)
        assert final["debug"]["vfxDirectorRaw"] == expected, "only_diagnosed_texture_leaves_change"
        assert final["vfxManifest"] == vfx._compile_manifest(before, expected, case)
        assert vfx.validate_vfx_manifest_wire(final)["ok"]
        assert build_visual_asset_plan(final) == expected_plan
        assert len([row for row in expected_plan if row["role"].startswith(("vfx:", "impact:"))]) == int(domain == "nonempty")
        assert ("assets" in final["vfxManifest"]) == (domain != "omitted")
        assert final["debug"]["llmStageAccounting"]["vfxDirectorCalls"] == 1
        assert final["debug"]["llmStageAccounting"]["vfxRepairCalls"] == int(outcome != "valid")
        if outcome == "valid":
            assert len(sent) == 1 and "vfxRepairScope" not in final["debug"]
        else:
            audit = final["debug"]["vfxRepairFilterAudit"]
            paths = [f"$.slotsUpsert[0].{payload}.texture.assetId", *([f"$.slotsUpsert[0].{payload}.texture.source"] if domain != "nonempty" else [])]
            assert audit["acceptedPaths"] == paths
            ignored = {row["path"] for row in audit["ignoredChanges"]}
            assert {"$.effectMagnitude", "$.motif", "$.slotIdsDelete[0]", "$.slotsUpsert[0].entityId", "$.slotsUpsert[0].event", "$.slotsUpsert[0].textureRole", "$.slotsUpsert[0].spritePrompt", f"$.slotsUpsert[0].{payload}.widthProfile.middle", "$.slotsUpsert[1]", "$.assetsUpsert[0]", "$.assetIdsDelete[0]"} <= ignored
            if payload == "path":
                assert "$.slotsUpsert[0].path.source" in ignored
            if domain == "nonempty":
                assert f"$.slotsUpsert[0].{payload}.texture.source" in ignored
    assert raw == raw_before
    assert {key: final[key] for key in before if key != "debug"} == {key: value for key, value in before.items() if key != "debug"}
    assert ("visualKit" in final) == ("visualKit" in before)
    assert [request["model"] for request in sent] == ["explicit-offline-fixture-model"] * len(sent)
    assert [request["response_format"] for request in sent] == [{"type": "json_object"}] * len(sent)
    if outcome != "valid":
        assert len(sent) == 2
        director, repair = [json.loads(request["messages"][1]["content"]) for request in sent]
        assert repair["acceptedRuntimeProgramReadOnly"] == director["acceptedRuntimeProgramReadOnly"]
        assert repair["acceptedVisualKitReadOnly"] == director["acceptedVisualKit"]
        assert repair["exactErrors"] == vfx.validate_vfx_director_output(raw, final)["errors"]
        scope = repair["repairScope"]
        paths = [payload + ".texture.assetId", *([payload + ".texture.source"] if domain != "nonempty" else [])]
        assert scope["fieldPermissions"] == {"globals": {}, "slots": [{"slotId": raw["slots"][0]["id"], "paths": paths}], "assets": []}
        assert not scope["allowCreateAssets"] and not scope["allowCreateSlots"]
        assert scope["deletableSlotIds"] == scope["deletableSlotIndices"] == scope["deletableAssetIds"] == scope["deletableAssetIndices"] == []
        assert repair["brokenFragments"]["slots"] == raw["slots"]
        assert repair["validGeneratedContext"]["assets"] == raw.get("assets", [])
    if directory := os.environ.get("INFINI_VFX_REPAIR_EVIDENCE_DIR"):
        target = Path(directory) / (case + "_result.json")
        target.write_text(json.dumps({"sourceBefore": before, "directorBefore": raw_before, "repair": correction, "manifest": final.get("vfxManifest"), "planBefore": plan_before, "planAfter": build_visual_asset_plan(final), "sourceFrozen": True, "directorFrozen": True}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.mark.parametrize("case", ["profile-knot", "asset-canvas", "asset-reference", "foreign-payload", "scale-type-repair", "scale-type-frozen"])
def test_vfx_exact_leaf_stage_contract(monkeypatch, case):
    data = _data()
    raw = _with_asset(data) if case.startswith("asset") else _sprite(data) if case == "profile-knot" else _legacy(data)
    candidate = copy.deepcopy(raw["slots"][0])
    domain, leaf = "slots", "scale"
    if case == "profile-knot":
        raw["slots"][0]["element"]["widthProfile"]["middle"] = True
        candidate["element"]["widthProfile"].update(start=4.0, middle=1.0, end=4.0)
        candidate["element"]["texture"] = {"source": "entity", "assetId": ""}
        leaf = "element.widthProfile.middle"
        patch = _patch(slotsUpsert=[candidate], assetsUpsert=[_asset()])
    elif case == "asset-canvas":
        raw["assets"][0]["canvasSize"] = True
        domain, leaf = "assets", "canvasSize"
        patch = _patch(assetsUpsert=[{**_asset(), "prompt": "unrequested redesign", "negativePrompt": "rewrite", "layout": "strip"}])
    elif case == "asset-reference":
        raw["slots"][0]["element"]["texture"]["assetId"] = "missing"
        candidate["element"]["texture"] = {"source": "item", "assetId": _asset()["id"]}
        leaf = "element.texture.assetId"
        patch = _patch(slotsUpsert=[candidate], assetsUpsert=[_asset("missing")], assetIdsDelete=[_asset()["id"]])
    elif case == "foreign-payload":
        raw["slots"][0]["element"] = _sprite(data)["slots"][0]["element"]
        candidate["alpha"] = 0.1
        leaf = "element"
        patch = _patch(slotsUpsert=[candidate])
    else:
        raw["slots"][0]["scale"] = 1 if case == "scale-type-frozen" else True
        candidate["scale"] = 1.0 if case == "scale-type-frozen" else 1
        patch = _patch(slotsUpsert=[candidate], effectMagnitude=None, visualBudgetClass=None, motif=None, slotIdsDelete=[], slotIndicesDelete=[])
    before, patch_before = copy.deepcopy(raw), json.dumps(patch)
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"] is (case == "scale-type-frozen")
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    row_id = raw[domain][0]["id"]
    expected_permissions = [] if case == "scale-type-frozen" else [{"assetId" if domain == "assets" else "slotId": row_id, "paths": [leaf], **({"deletePaths": [leaf]} if case == "foreign-payload" else {})}]
    assert scope["fieldPermissions"][domain] == expected_permissions
    repaired, audit = vfx._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    expected = copy.deepcopy(before)
    if case == "profile-knot":
        expected["slots"][0]["element"]["widthProfile"]["middle"] = 1.0
    elif case == "asset-canvas":
        expected["assets"][0]["canvasSize"] = 32
    elif case == "asset-reference":
        expected["slots"][0]["element"]["texture"]["assetId"] = _asset()["id"]
        assert not scope["allowCreateAssets"]
    elif case == "foreign-payload":
        expected["slots"][0].pop("element")
    elif case == "scale-type-repair":
        expected["slots"][0]["scale"] = 1
    assert audit["ok"], audit
    assert json.dumps(repaired, sort_keys=True) == json.dumps(expected, sort_keys=True), "typed_exact_leaf_survives_filter_apply"
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]
    if case.startswith("scale"):
        assert type(repaired["slots"][0]["scale"]) is int
        assert audit["acceptedPaths"] == ([] if case == "scale-type-frozen" else ["$.slotsUpsert[0].scale"])
        assert len(audit["filteredPatch"]["slotsUpsert"]) == int(case == "scale-type-repair")
        if case == "scale-type-frozen":
            assert len(audit["ignoredChanges"]) == 1
            ignored = audit["ignoredChanges"][0]
            assert ignored["path"] == "$.slotsUpsert[0]" and ignored["reason"] == "independent_valid_slot_frozen"
            assert type(ignored["requested"]["scale"]) is float and type(ignored["preserved"]["scale"]) is int
        else:
            assert audit["ignoredChanges"] == []
    if case == "asset-canvas":
        assert any(row["path"].endswith(".prompt") for row in audit["ignoredChanges"])
    sent = _offline_transport(monkeypatch, case, [raw] if case == "scale-type-frozen" else [raw, patch])
    final = vfx.attach_hybrid_vfx_manifest(data, case, llm_director=stage.call_llm_vfx_director)
    assert json.dumps(final["debug"]["vfxDirectorRaw"], sort_keys=True) == json.dumps(expected, sort_keys=True)
    assert final["vfxManifest"] == vfx._compile_manifest(data, expected, case)
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert len(sent) == (1 if case == "scale-type-frozen" else 2)
    if case != "scale-type-frozen":
        request = json.loads(sent[1]["messages"][1]["content"])
        assert request["repairScope"] == scope
        if case == "asset-canvas":
            assert request["brokenFragments"]["assets"] == before["assets"]
            packet = vfx._prompt_packet(data, None, None)
            assert request["outputSchema"]["properties"]["assetsUpsert"]["items"] == packet["outputSchema"]["properties"]["assets"]["items"]
    if case == "profile-knot":
        assert type(final["vfxManifest"]["slots"][0]["element"]["widthProfile"]["middle"]) is float
        assert "assets" not in final["vfxManifest"]
    assert json.dumps(raw, sort_keys=True) == json.dumps(before, sort_keys=True) and json.dumps(patch) == patch_before


@pytest.mark.parametrize("duplicate", [False, True], ids=["unused-id", "duplicate-index"])
def test_vfx_asset_delete_permission_preserves_first_request(duplicate):
    data = _data()
    raw = _with_asset(data)
    raw["assets"].append(_asset() if duplicate else _asset("unused"))
    scope = vfx._build_vfx_repair_scope(raw, vfx.validate_vfx_director_output(raw, data)["errors"])
    repaired = vfx._apply_vfx_repair_patch(data, raw, _patch(assetIndicesDelete=[1]) if duplicate else _patch(assetIdsDelete=["unused"]), scope)
    assert repaired["assets"] == [_asset()]
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]


@pytest.mark.parametrize("field", ["slotsUpsert", "slotIdsDelete", "slotIndicesDelete", "assetsUpsert", "assetIdsDelete", "assetIndicesDelete"])
def test_vfx_repair_optional_edit_absence_is_not_null(field):
    schema = _sent(_data(), True)["outputSchema"]
    assert not strict_schema_errors(_patch(), schema)
    assert strict_schema_errors(_patch(**{field: None}), schema)
