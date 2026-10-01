"""PNG producer admission through real offline Director/Repair -> delivery/cache.

Only model HTTP and the explicit hand-authored image adapter are substituted.
No provider, GPU, game, model/Visual selection or mechanics changes.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.core.runtime_authoring.wire_validator import validate_runtime_wire
from infini_local.pipelines import llm_authoring_pipeline as stage
from infini_local.pipelines import visual_delivery_gate, visual_sprite_generation
from infini_local.pipelines.visual_generation_pipeline import _apply_kit, _validate_kit
from infini_local.services import asset_sync_service
from infini_local.storage import world_storage
from tests.test_vfx_asset_pipeline import _data, _request, _slot, offline_backend  # noqa: F401
from tests.test_vfx_empty_asset_domain_repair import _offline_transport
from tests.test_vfx_material_repair import _patch


BAD_SELECTORS = [
    ("projectileAfterimage", "runtime_geometry", "entity"),
    ("spriteStampTrail", "no_asset", "entity"),
    ("actorAfterimage", "no_asset", "projectile"),
    ("projectileAfterimage", "reuse_item_icon", "field"),
]


def visual_data(mode: str) -> dict:
    data = _data([])
    item = {"prompt": "one literal amber inventory fixture", "negativePrompt": "text, watermark",
            "silhouette": "compact ring", "visualIdentity": "amber ring", "palette": ["amber"],
            "preferredCanvasSize": 32, "inventoryScale": 1.0, "worldScale": 1.0}
    entity = {"entityId": "orb", "assetMode": mode,
              "visualProjectRef": "item" if mode == "reuse_item_icon" else "none", "scale": 1.0}
    if mode == "baked_sprite":
        entity.update(visualProjectRef="entity", prompt="one exact separate amber orb", silhouette="orb", visualIdentity="amber orb")
    kit = {"schema": "infini.visual-kit.runtime-entities.v1", "item": item,
           "entities": [{"entityId": "item", "assetMode": "baked_sprite", "visualProjectRef": "item",
                         **{key: item[key] for key in ("prompt", "silhouette", "visualIdentity")}, "scale": 1.0}, entity],
           "animationPlan": "Keep accepted movement, do not add gameplay."}
    accepted, errors = _validate_kit(kit, ["item", "orb"], "item")
    assert accepted is not None, errors
    data.pop("vfxManifest", None)
    return _apply_kit(data, accepted)


def authored_vfx(renderer: str, texture: str = "entity") -> dict:
    slot = _slot("selected", "")
    slot.update(spritePrompt="", spriteNegativePrompt="")
    if renderer in {"spriteElement", "texturedPath"}:
        slot = _slot("selected", "", renderer=renderer)
        slot.update(spritePrompt="", spriteNegativePrompt="")
        slot["element" if renderer == "spriteElement" else "path"]["texture"] = {"source": texture, "assetId": ""}
    else:
        slot.pop("element")
        slot.update(rendererKind=renderer, backend="Sprite", textureRole=texture)
        if renderer == "lightCue":
            slot.update(channel="light", lane="cue")
        elif renderer == "soundCue":
            slot.update(channel="sound", lane="cue")
    return {"schema": vfx.VFX_DIRECTOR_SCHEMA, "effectMagnitude": 0.5, "visualBudgetClass": "normal",
            "motif": {"element": "amber", "shapeLanguage": "ring", "motionLanguage": "quiet",
                      "paletteRole": "accent", "rhythm": 1.0, "chaos": 0.0}, "slots": [slot]}


def roundtrip(data, tmp_path):
    assert validate_runtime_wire(data)["ok"]
    assert world_storage.is_deliverable_recipe_payload(data)
    world_storage.write_world_recipe_cache(tmp_path, "dependencies", "probe", "offline-world", data)
    cached = world_storage.read_world_recipe_cache(tmp_path, "dependencies", "v5", "probe", "offline-world")
    assert cached is not None and cached["vfxManifest"]["slots"] == data["vfxManifest"]["slots"]
    evidence = os.environ.get("INFINI_VFX_DEPENDENCY_EVIDENCE_DIR")
    if evidence:
        target = Path(evidence)
        target.mkdir(parents=True, exist_ok=True)
        case = tmp_path.parent.name
        (target / (case + ".json")).write_text(json.dumps({
            "case": case, "data": world_storage.sanitize_recipe_for_delivery(cached),
            "dependencies": vfx.vfx_png_dependencies(data), "cacheReadAccepted": True,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cached


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


def test_item_body_entity_texture_requires_its_actual_projected_png(offline_backend, monkeypatch, tmp_path):
    data = visual_data("no_asset")
    raw = authored_vfx("actorAfterimage", "entity")
    raw["slots"][0]["entityId"] = "item"
    sent = _offline_transport(monkeypatch, "item_body_png", [raw])
    final = vfx.attach_hybrid_vfx_manifest(data, "item_body_dependency", llm_director=stage.call_llm_vfx_director)
    final = visual_sprite_generation.maybe_generate_visual_assets(final)
    assert len(sent) == 1
    assert visual_delivery_gate.visual_delivery_report(final, check_backend_config=False)["ok"]
    roundtrip(final, tmp_path / "body")
    body = next(row for row in final["runtimeProgram"]["entities"] if row["kind"] == "item_body")
    body["visual"]["spritePath"] = ""  # The real C# baked entity lookup no longer resolves.
    before = copy.deepcopy(final)
    report = visual_delivery_gate.visual_delivery_report(final, check_backend_config=False)
    assert not report["ok"]
    assert any(row["code"] == "required_vfx_texture_not_ready" for row in report["problems"])
    assert not world_storage.is_deliverable_recipe_payload(final) and final == before
    with pytest.raises(ValueError, match="refusing to cache"):
        world_storage.write_world_recipe_cache(tmp_path / "refused", "dependencies", "probe", "offline-world", final)
    target = world_storage.world_recipe_file(tmp_path / "body", "offline-world", "probe")
    saved = json.loads(target.read_text(encoding="utf-8"))
    next(row for row in saved["runtimeProgram"]["entities"] if row["kind"] == "item_body")["visual"]["spritePath"] = ""
    target.write_text(json.dumps(saved), encoding="utf-8")  # Explicit corrupt persisted fixture, not a repair.
    assert world_storage.read_world_recipe_cache(tmp_path / "body", "dependencies", "v5", "probe", "offline-world") is None
    assert not target.exists() and list((target.parent.parent / "invalid").glob("*.json"))


@pytest.mark.parametrize("selector", [None, ["entity"], "Entity"])
def test_persisted_png_selector_rejects_untyped_or_normalized_tokens(selector):
    data = visual_data("reuse_item_icon")
    raw = authored_vfx("projectileAfterimage")
    raw["slots"][0]["textureRole"] = selector
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "invalid_saved_selector")
    before = copy.deepcopy(data)
    report = vfx.validate_vfx_manifest_wire(data)
    assert not report["ok"]
    assert {error["path"] for error in report["errors"]} == {"$.vfxManifest.slots[0].textureRole"}
    assert data == before


@pytest.mark.parametrize("renderer,mode,selector,kind,role,jobs", [
    ("projectileAfterimage", "baked_sprite", "entity", "free_projectile", "entity:orb", 2),
    ("spriteStampTrail", "reuse_item_icon", "entity", "free_projectile", "item", 1),
    ("actorAfterimage", "baked_sprite", "projectile", "free_projectile", "entity:orb", 2),
    ("spriteStampTrail", "baked_sprite", "field", "field", "entity:orb", 2),
    ("spriteElement", "reuse_item_icon", "entity", "free_projectile", "item", 1),
    ("texturedPath", "baked_sprite", "entity", "free_projectile", "entity:orb", 2),
    ("impactRing", "runtime_geometry", "entity", "free_projectile", "", 1),
    ("childMotes", "no_asset", "impact", "free_projectile", "", 1),
    ("lightCue", "no_asset", "field", "free_projectile", "", 1),
    ("soundCue", "runtime_geometry", "impact", "free_projectile", "", 1),
])
def test_valid_png_or_untextured_renderer_retains_existing_producers(
    offline_backend, monkeypatch, tmp_path, renderer, mode, selector, kind, role, jobs,
):
    calls, _ = offline_backend
    data, raw = visual_data(mode), authored_vfx(renderer, selector)
    if kind == "field":  # Explicit independent authored fixture, never a repair.
        entity = data["runtimeProgram"]["entities"][1]
        entity.update(kind=kind, visualRole="field")
        entity["visual"]["role"] = "field"
    before = copy.deepcopy(data)
    projected = vfx.vfx_png_dependencies(data, raw, require_used=True)
    assert projected["errors"] == [] and data == before
    assert [row["role"] for row in projected["dependencies"]] == ([role] if role else [])
    sent = _offline_transport(monkeypatch, "positive_" + renderer + "_" + selector, [raw])
    final = vfx.attach_hybrid_vfx_manifest(data, "valid_dependencies", llm_director=stage.call_llm_vfx_director)
    assert len(sent) == 1 and final["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 0
    assert final["debug"]["vfxDirectorRaw"] == raw and final["runtimeProgram"] == before["runtimeProgram"]
    final = visual_sprite_generation.maybe_generate_visual_assets(final)
    report = visual_delivery_gate.visual_delivery_report(final, check_backend_config=False)
    assert report["ok"], report["problems"]
    assert len(calls) == jobs
    if role:
        assert next(row for row in report["slots"] if row["role"] == role)["required"]
    else:
        assert not any(row["role"].startswith(("impact:", "vfx:")) for row in report["slots"])
    roundtrip(final, tmp_path / "valid")
    tampered = copy.deepcopy(final)
    tampered["debug"]["visualAssetPlan"] = json.dumps([{"path": "invented.png", "status": "generated"}])
    tampered.setdefault("recipeMeta", {})["assetFiles"] = ["invented.png"]
    assert asset_sync_service.runtime_asset_files(tampered) == asset_sync_service.runtime_asset_files(final)
    assert visual_delivery_gate.visual_delivery_report(tampered, check_backend_config=False)["ok"]
    if role:
        # A present PNG is not a ready execution result; optional inventory art
        # policy cannot waive an independently selected VFX dependency.
        monkeypatch.setattr(visual_delivery_gate, "VISUAL_REQUIRE_ITEM_SPRITE", False)
        selected = final["visual"] if role == "item" else final["runtimeProgram"]["entities"][1]["visual"]
        selected["spriteStatus"] = "pending"
        pending = visual_delivery_gate.visual_delivery_report(final, check_backend_config=False)
        assert any(row["code"] == "required_vfx_texture_not_ready" for row in pending["problems"]), "selected producer readiness was bypassed"
        assert not world_storage.is_deliverable_recipe_payload(final)


@pytest.mark.parametrize("producer", ["impact", "asset"])
def test_shared_png_producer_stays_one_owned_request_through_delivery(offline_backend, monkeypatch, tmp_path, producer):
    calls, _ = offline_backend
    data = visual_data("no_asset")
    raw = authored_vfx("spriteElement", producer)
    second = authored_vfx("texturedPath", producer)["slots"][0]
    second["id"] = "other_material_consumer"
    raw["slots"].append(second)
    if producer == "impact":
        legacy = authored_vfx("actorAfterimage", "impact")["slots"][0]
        legacy["id"] = "legacy_consumer"
        impact = authored_vfx("impactSprite", "impact")["slots"][0]
        impact.update(id="exact_impact", event="on_hit", spritePrompt="one literal amber impact", spriteNegativePrompt="no text")
        raw["slots"].extend([legacy, impact])
    else:
        raw["assets"] = [_request("shared", layout="strip")]
        for slot in raw["slots"]:
            slot["element" if slot["rendererKind"] == "spriteElement" else "path"]["texture"]["assetId"] = "shared"
    before = copy.deepcopy(data["runtimeProgram"])
    sent = _offline_transport(monkeypatch, "shared_" + producer, [raw])
    final = vfx.attach_hybrid_vfx_manifest(data, "shared_dependency", llm_director=stage.call_llm_vfx_director)
    assert len(sent) == 1
    final = visual_sprite_generation.maybe_generate_visual_assets(final)
    report = visual_delivery_gate.visual_delivery_report(final, check_backend_config=False)
    assert report["ok"], report["problems"]
    assert len(calls) == 2  # Item plus one impact/ingredient, not one per consumer.
    assert len(asset_sync_service.runtime_asset_files(final)) == 2
    assert len([row for row in report["slots"] if row["role"].startswith(("impact:", "vfx:"))]) == 1
    after = copy.deepcopy(final["runtimeProgram"])
    for program in (before, after):
        for entity in program["entities"]:
            entity.pop("visual", None)
    assert after == before
    roundtrip(final, tmp_path / "shared")
