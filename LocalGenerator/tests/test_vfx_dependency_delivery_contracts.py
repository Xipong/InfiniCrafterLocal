"""Offline canonical vfx dependency delivery contracts; no live services."""
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
from tests.test_repair_vfx_contract import _offline_transport
from tests.vfx_image_fixtures import _data, _request, _slot, _existing_texture_data, offline_backend

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
            "preferredCanvasSize": 32, "renderSizePx": 40, "forwardAngleDegrees": 45, "inventoryScale": 1.0, "worldScale": 1.0}
    entity = {"entityId": "orb", "assetMode": mode,
              "visualProjectRef": "item" if mode == "reuse_item_icon" else "none", "scale": 1.0}
    if mode == "baked_sprite":
        entity.update(visualProjectRef="entity", prompt="one exact separate amber orb", silhouette="orb", visualIdentity="amber orb", preferredCanvasSize=64, renderSizePx=24, forwardAngleDegrees=0)
    kit = {"schema": "infini.visual-kit.runtime-entities.v2", "item": item,
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

def test_storage_admission_uses_canonical_vfx_references():
    from infini_local.storage import world_storage
    data = _data()
    data["vfxManifest"]["slots"][0]["element"]["texture"]["assetId"] = "dangling"
    assert world_storage.is_deliverable_recipe_payload(data) is False

def test_storage_cache_roundtrip_preserves_assets_refs_pixels_and_runtime(offline_backend, tmp_path):
    from infini_local.storage import world_storage
    data = visual_sprite_generation.maybe_generate_visual_assets(_data([_request(), _request("band", layout="strip")]))
    before = copy.deepcopy(data)
    world_storage.write_world_recipe_cache(tmp_path / "world", "test", "recipe", "world", data)
    assert data == before
    cached = world_storage.read_world_recipe_cache(tmp_path / "world", "test", "v5", "recipe", "world")
    assert cached is not None
    assert cached["vfxManifest"]["assets"] == before["vfxManifest"]["assets"]
    assert cached["vfxManifest"]["slots"] == before["vfxManifest"]["slots"]
    assert cached["runtimeProgram"] == before["runtimeProgram"]
    path = world_storage.world_recipe_file(tmp_path / "world", "world", "recipe")
    stored = path.read_bytes()
    Path(data["vfxManifest"]["assets"][0]["spritePath"]).unlink()
    assert world_storage.is_deliverable_recipe_payload(data) is False
    assert world_storage.read_world_recipe_cache(tmp_path / "world", "test", "v5", "recipe", "world") is None
    invalid = path.parent.parent / "invalid"
    originals = [p for p in invalid.glob("*.json") if not p.name.endswith(".reason.json")]
    assert len(originals) == 1
    assert originals[0].read_bytes() == stored

def test_storage_requires_ready_nested_existing_texture_even_without_new_requests():
    from infini_local.core.vfx_manifest import validate_vfx_manifest_wire
    from infini_local.storage import world_storage
    data = _data([])
    slot = _slot("reuse", "")
    slot["element"]["texture"] = {"source": "item", "assetId": ""}
    data["vfxManifest"]["slots"] = [slot]
    assert validate_vfx_manifest_wire(data)["ok"]
    assert world_storage.is_deliverable_recipe_payload(data) is False

@pytest.mark.parametrize("source", ["item", "entity", "impact"])
@pytest.mark.parametrize("renderer", ["spriteElement", "texturedPath"])
@pytest.mark.parametrize("damage", ["missing", "pending"])
def test_nested_existing_texture_requires_ready_exact_producer(offline_backend, monkeypatch, source, renderer, damage):
    from infini_local.core.vfx_manifest import validate_vfx_manifest_wire
    from infini_local.storage import world_storage
    monkeypatch.setattr(visual_sprite_generation, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(visual_delivery_gate, "VISUAL_REQUIRE_ITEM_SPRITE", False)
    data = _existing_texture_data(source, renderer)
    out = visual_sprite_generation.maybe_generate_visual_assets(data)
    assert validate_vfx_manifest_wire(out)["ok"]
    assert visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)["ok"]
    orb_visual = next(row for row in out["runtimeProgram"]["entities"] if row["id"] == "orb")["visual"]
    producer = out["visual"] if source == "item" else orb_visual
    prefix = "impactSprite" if source == "impact" else "sprite"
    if damage == "missing":
        Path(producer[prefix + "Path"]).unlink()
    else:
        producer[prefix + "Status"] = "pending"
    assert validate_vfx_manifest_wire(out)["ok"]  # shape is intentionally not an image gate
    report = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    assert not report["ok"], report
    assert any(problem["code"] == "required_vfx_texture_not_ready" for problem in report["problems"])
    assert world_storage.is_deliverable_recipe_payload(out) is False
    assert "assets" not in out["vfxManifest"]

@pytest.mark.parametrize("status", ["pending", "failed", "fallback", "fallback_after_failed_generation", "prompt_only"])
def test_ready_pixels_do_not_allow_pending_or_fallback_ingredient_admission(offline_backend, tmp_path, status):
    from infini_local.core.vfx_manifest import validate_vfx_manifest_wire
    from infini_local.pipelines.combine_pipeline import _cached_payload_report, _vfx_manifest_report
    from infini_local.storage import world_storage
    out = visual_sprite_generation.maybe_generate_visual_assets(_data())
    asset = out["vfxManifest"]["assets"][0]
    asset["spriteStatus"] = status
    assert asset_sync_service.is_complete_png_file(asset["spritePath"])
    assert validate_vfx_manifest_wire(out)["ok"]
    assert _vfx_manifest_report(out)["ok"]  # wire helper remains the authority
    assert not visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)["ok"]
    assert not world_storage.is_deliverable_recipe_payload(out)
    assert not _cached_payload_report(out)["ok"]
    root = tmp_path / "world"
    with pytest.raises(ValueError, match="non-deliverable"):
        world_storage.write_world_recipe_cache(root, "test", "recipe", "world", out)
    path = world_storage.world_recipe_file(root, "world", "recipe")
    assert not path.exists()
    world_storage.atomic_write_json(path, out)  # explicit old/incomplete cache fixture
    assert world_storage.read_world_recipe_cache(root, "test", "v5", "recipe", "world") is None
    assert not path.exists()

def test_network_stripped_caption_fixture_retains_ready_pngs_refs_and_metadata(offline_backend):
    """Python admission of an ABI transport fixture, not a C# ToNetworkJson claim."""
    from infini_local.core.vfx_manifest import validate_vfx_manifest_wire
    from infini_local.pipelines.combine_pipeline import _cached_payload_report
    from infini_local.storage import world_storage
    full = visual_sprite_generation.maybe_generate_visual_assets(_data([_request(), _request("band", layout="strip")]))
    stripped = copy.deepcopy(full)
    for asset in stripped["vfxManifest"]["assets"]:
        asset["prompt"] = asset["negativePrompt"] = ""
        asset["spritePath"] = Path(asset["spritePath"]).name
    assert validate_vfx_manifest_wire(stripped)["ok"]
    assert visual_delivery_gate.visual_delivery_report(stripped, check_backend_config=False)["ok"]
    assert world_storage.is_deliverable_recipe_payload(stripped)
    assert _cached_payload_report(stripped)["ok"]
    clean = world_storage.sanitize_recipe_for_delivery(stripped)
    assert clean["vfxManifest"]["assets"] == stripped["vfxManifest"]["assets"]
    assert clean["vfxManifest"]["slots"] == full["vfxManifest"]["slots"]
    assert asset_sync_service.runtime_asset_files(clean) == asset_sync_service.runtime_asset_files(full)
    assert full["vfxManifest"]["assets"][0]["prompt"] == _request()["prompt"]
