"""Empty VFX asset domains must remain repairable without new artwork.

Explicit offline Director/Repair fixtures pass through the production request
builder, JSON parser, diagnostic scope, frozen merge, compiler and asset plan.
Only the network boundary and its test-local model/format are replaced; no
provider or image backend is called. Optional evidence export is opt-in.
"""
from __future__ import annotations

# These observers intentionally exercise the canonical diagnostic/merge seams.
# pyright: reportPrivateUsage=false

import copy
import json
import os
from pathlib import Path
from typing import Any

import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.core.errors import PlannerUnavailable
from infini_local.pipelines import llm_authoring_pipeline as stage
from infini_local.pipelines import llm_transport
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
from tests.test_vfx_material_contract import _asset, _data, _legacy, _path, _sprite
from tests.test_vfx_material_repair import _patch


_RENDERERS = [("spriteElement", "element"), ("texturedPath", "path")]


def _source(renderer: str, payload: str, domain: str) -> tuple[dict[str, Any], dict[str, Any]]:
    data = _data()
    # Accepted Visual modes are explicit fixture choices, not inferred by VFX.
    for entity in data["runtimeProgram"]["entities"]:
        entity["visual"]["assetMode"] = "baked_sprite" if entity["kind"] == "item_body" else "reuse_item_icon"
    raw = _sprite(data) if renderer == "spriteElement" else _path(data)
    raw["slots"][0][payload]["texture"] = {"source": "asset", "assetId": "missing"}
    if domain == "empty":
        raw["assets"] = []
    elif domain == "nonempty":
        raw["assets"] = [_asset()]
    return data, raw


def _evidence(case: str, payload: dict[str, Any]) -> None:
    directory = os.environ.get("INFINI_VFX_REPAIR_EVIDENCE_DIR")
    if directory:
        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)
        (out / (case + ".json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _offline_transport(monkeypatch: pytest.MonkeyPatch, case: str, replies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pending = iter(replies)
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(stage, "USE_LLM", True)
    # Avoid even model=auto's local /v1/models discovery; production selection is
    # untouched. Both real stage request builders must retain this exact choice.
    monkeypatch.setattr(stage, "resolve_llm_model", lambda: "explicit-offline-fixture-model")
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", "json_object")

    def send(request: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        captured.append(json.loads(json.dumps(request)))
        _evidence(case + "_requests", {"kind": "hand-authored offline responses, no provider call", "requests": captured, "responses": replies})
        return {"choices": [{"message": {"content": json.dumps(next(pending))}}]}

    monkeypatch.setattr(stage, "llm_chat_json", send)
    return captured


def _intrusive_patch(data: dict[str, Any], raw: dict[str, Any], payload: str, texture: dict[str, str]) -> dict[str, Any]:
    candidate = copy.deepcopy(raw["slots"][0])
    candidate[payload]["texture"] = texture
    candidate[payload]["widthProfile"].update(start=4.0, middle=4.0, end=4.0)
    candidate[payload]["colorProfile"]["middle"] = "pink"
    candidate[payload]["widthPx"] = 1.0
    if payload == "path":
        candidate[payload]["source"] = "beam"  # Geometry is frozen, unlike texture.source.
    other_id = next(row["id"] for row in data["runtimeProgram"]["entities"] if row["id"] != candidate["entityId"])
    candidate.update(entityId=other_id, event="on_hit", alpha=0.1, channel="light", lane="cue",
                     textureRole="impact", spritePrompt="unrequested replacement Visual/image design")
    new_slot = copy.deepcopy(_legacy(data)["slots"][0])
    new_slot["id"] = "unrequested_slot"
    assets = [{**_asset(), "prompt": "unrequested redesign", "canvasSize": 64, "layout": "strip"}] if raw.get("assets") else []
    return _patch(
        slotsUpsert=[candidate, new_slot], slotIdsDelete=[raw["slots"][0]["id"]],
        effectMagnitude=0.9, motif={**raw["motif"], "shapeLanguage": "unrequested redesign"},
        assetsUpsert=[*assets, _asset("missing")], assetIdsDelete=[_asset()["id"]],
    )


def _assert_source_frozen(data: dict[str, Any], before: dict[str, Any], raw: dict[str, Any], raw_before: dict[str, Any]) -> None:
    assert raw == raw_before
    # Includes all gameplay and per-entity accepted Visual fields, not just IDs.
    assert {key: data[key] for key in before if key != "debug"} == {key: value for key, value in before.items() if key != "debug"}
    assert ("visualKit" in data) == ("visualKit" in before)


def _assert_requests(sent: list[dict[str, Any]], data: dict[str, Any], raw: dict[str, Any], *, source_mutable: bool) -> None:
    assert len(sent) == 2
    assert [request["model"] for request in sent] == ["explicit-offline-fixture-model"] * 2
    assert [request["response_format"] for request in sent] == [{"type": "json_object"}] * 2
    director, repair = [json.loads(request["messages"][1]["content"]) for request in sent]
    assert repair["acceptedRuntimeProgramReadOnly"] == director["acceptedRuntimeProgramReadOnly"]
    assert repair["acceptedVisualKitReadOnly"] == director["acceptedVisualKit"]
    assert repair["exactErrors"] == vfx.validate_vfx_director_output(raw, data)["errors"]
    scope = repair["repairScope"]
    payload = "element" if raw["slots"][0]["rendererKind"] == "spriteElement" else "path"
    paths = [payload + ".texture.assetId", *([payload + ".texture.source"] if source_mutable else [])]
    assert scope["fieldPermissions"] == {"globals": {}, "slots": [{"slotId": raw["slots"][0]["id"], "paths": paths}], "assets": []}
    assert not scope["allowCreateAssets"] and not scope["allowCreateSlots"]
    assert scope["deletableSlotIds"] == scope["deletableSlotIndices"] == scope["deletableAssetIds"] == scope["deletableAssetIndices"] == []
    assert repair["brokenFragments"]["slots"] == raw["slots"]
    assert repair["validGeneratedContext"]["assets"] == raw.get("assets", [])


@pytest.mark.parametrize("renderer,payload", _RENDERERS)
@pytest.mark.parametrize("domain", ["omitted", "empty"])
@pytest.mark.parametrize("chosen_source", ["item", "entity"])
def test_empty_asset_domain_accepts_only_model_chosen_texture_leaves(
    monkeypatch: pytest.MonkeyPatch, renderer: str, payload: str, domain: str, chosen_source: str,
) -> None:
    data, raw = _source(renderer, payload, domain)
    before, raw_before = copy.deepcopy(data), copy.deepcopy(raw)
    plan_before = build_visual_asset_plan(data)
    texture = {"source": chosen_source, "assetId": ""}
    correction = _intrusive_patch(data, raw, payload, texture)
    case = "empty_domain_" + renderer + "_" + domain + "_" + chosen_source
    sent = _offline_transport(monkeypatch, case, [raw, correction])
    # This real bounded stage deadlocks on the original owner: source is ignored,
    # leaving source=asset with an empty ID. No defect-presence expectation here.
    final = vfx.attach_hybrid_vfx_manifest(data, case, llm_director=stage.call_llm_vfx_director)
    expected = copy.deepcopy(raw_before)
    expected["slots"][0][payload]["texture"] = texture
    assert final["debug"]["vfxDirectorRaw"] == expected
    assert final["vfxManifest"] == vfx._compile_manifest(before, expected, case)
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert build_visual_asset_plan(final) == plan_before
    assert not any(row["role"].startswith(("vfx:", "impact:")) for row in build_visual_asset_plan(final))
    assert ("assets" in final["vfxManifest"]) == (domain == "empty")
    _assert_source_frozen(final, before, raw, raw_before)
    _assert_requests(sent, final, raw_before, source_mutable=True)
    audit = final["debug"]["vfxRepairFilterAudit"]
    assert audit["acceptedPaths"] == [f"$.slotsUpsert[0].{payload}.texture.assetId", f"$.slotsUpsert[0].{payload}.texture.source"]
    ignored = {row["path"] for row in audit["ignoredChanges"]}
    assert {"$.effectMagnitude", "$.motif", "$.slotIdsDelete[0]", "$.slotsUpsert[0].entityId", "$.slotsUpsert[0].event",
            "$.slotsUpsert[0].textureRole", "$.slotsUpsert[0].spritePrompt", f"$.slotsUpsert[0].{payload}.widthProfile.middle",
            "$.slotsUpsert[1]", "$.assetsUpsert[0]", "$.assetIdsDelete[0]"} <= ignored
    if payload == "path":
        assert "$.slotsUpsert[0].path.source" in ignored
    assert final["debug"]["llmStageAccounting"]["vfxDirectorCalls"] == final["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 1
    _evidence(case + "_result", {"sourceBefore": before, "directorBefore": raw_before, "repair": correction,
                               "acceptedDirector": expected, "manifest": final["vfxManifest"], "audit": audit,
                               "planBefore": plan_before, "planAfter": build_visual_asset_plan(final),
                               "sourceFrozen": True, "directorFrozen": True})


@pytest.mark.parametrize("renderer,payload", _RENDERERS)
def test_nonempty_declared_domain_keeps_source_and_asset_request_frozen(
    monkeypatch: pytest.MonkeyPatch, renderer: str, payload: str,
) -> None:
    data, raw = _source(renderer, payload, "nonempty")
    before, raw_before = copy.deepcopy(data), copy.deepcopy(raw)
    correction = _intrusive_patch(data, raw, payload, {"source": "item", "assetId": _asset()["id"]})
    expected = copy.deepcopy(raw_before)
    expected["slots"][0][payload]["texture"]["assetId"] = _asset()["id"]
    case = "nonempty_domain_" + renderer
    expected_plan = build_visual_asset_plan({**before, "vfxManifest": vfx._compile_manifest(before, expected, case)})
    sent = _offline_transport(monkeypatch, case, [raw, correction])
    final = vfx.attach_hybrid_vfx_manifest(data, case, llm_director=stage.call_llm_vfx_director)
    assert final["debug"]["vfxDirectorRaw"] == expected
    assert final["vfxManifest"] == vfx._compile_manifest(before, expected, case)
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert build_visual_asset_plan(final) == expected_plan
    assert len([row for row in expected_plan if row["role"].startswith("vfx:")]) == 1
    _assert_source_frozen(final, before, raw, raw_before)
    _assert_requests(sent, final, raw_before, source_mutable=False)
    audit = final["debug"]["vfxRepairFilterAudit"]
    assert audit["acceptedPaths"] == [f"$.slotsUpsert[0].{payload}.texture.assetId"]
    assert f"$.slotsUpsert[0].{payload}.texture.source" in {row["path"] for row in audit["ignoredChanges"]}
    _evidence(case + "_result", {"sourceBefore": before, "directorBefore": raw_before, "repair": correction,
                               "acceptedDirector": expected, "manifest": final["vfxManifest"], "audit": audit,
                               "expectedPlan": expected_plan, "planAfter": build_visual_asset_plan(final),
                               "sourceFrozen": True, "directorFrozen": True})


@pytest.mark.parametrize("renderer,payload", _RENDERERS)
@pytest.mark.parametrize("domain", ["omitted", "empty"])
def test_empty_domain_noop_does_not_invent_texture_or_artwork(
    monkeypatch: pytest.MonkeyPatch, renderer: str, payload: str, domain: str,
) -> None:
    data, raw = _source(renderer, payload, domain)
    before, raw_before = copy.deepcopy(data), copy.deepcopy(raw)
    scope = vfx._build_vfx_repair_scope(raw, vfx.validate_vfx_director_output(raw, data)["errors"])
    merged, audit = vfx._apply_vfx_repair_patch(data, raw, _patch(), scope, return_audit=True)
    assert merged == raw_before and audit["acceptedPaths"] == []
    assert not vfx.validate_vfx_director_output(merged, data)["ok"]
    case = "noop_" + renderer + "_" + domain
    sent = _offline_transport(monkeypatch, case, [raw, _patch()])
    with pytest.raises(PlannerUnavailable, match="VFX Repair did not produce"):
        vfx.attach_hybrid_vfx_manifest(data, case, llm_director=stage.call_llm_vfx_director)
    assert len(sent) == 2 and "vfxManifest" not in data
    _assert_source_frozen(data, before, raw, raw_before)


@pytest.mark.parametrize("renderer,payload", _RENDERERS)
@pytest.mark.parametrize("domain", ["omitted", "empty"])
def test_valid_empty_domain_control_never_calls_repair_or_requests_new_images(
    monkeypatch: pytest.MonkeyPatch, renderer: str, payload: str, domain: str,
) -> None:
    data, raw = _source(renderer, payload, domain)
    raw["slots"][0][payload]["texture"] = {"source": "item", "assetId": ""}
    before, raw_before = copy.deepcopy(data), copy.deepcopy(raw)
    plan_before = build_visual_asset_plan(data)
    case = "valid_control_" + renderer + "_" + domain
    sent = _offline_transport(monkeypatch, case, [raw])
    final = vfx.attach_hybrid_vfx_manifest(data, case, llm_director=stage.call_llm_vfx_director)
    assert len(sent) == 1
    assert final["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 0
    assert "vfxRepairScope" not in final["debug"]
    assert final["vfxManifest"] == vfx._compile_manifest(before, raw_before, case)
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert build_visual_asset_plan(final) == plan_before
    _assert_source_frozen(final, before, raw, raw_before)
