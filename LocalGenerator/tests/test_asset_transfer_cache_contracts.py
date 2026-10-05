"""Offline canonical asset transfer cache contracts; no live services."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
from urllib.parse import urlencode
import pytest
from infini_local.core.vfx_manifest import validate_vfx_manifest_wire
from infini_local.pipelines import visual_delivery_gate, visual_sprite_generation
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
from infini_local.pipelines.combine_pipeline import _cached_payload_report
from infini_local.services import asset_sync_service
from infini_local.storage import world_storage
from infini_local.web.server_utility_routes import ServerUtilityRoutes
import contextlib
import threading
import time
from infini_local.pipelines.visual_generation_pipeline import _apply_kit, _validate_kit
from infini_local.core.vfx_manifest import VFX_MANIFEST_SCHEMA, _hydrate_vfx_asset_prompts
from infini_local.qa.live_no_image_fixture import write_no_image_fixture_png
from infini_local.services.sdcpp_service import ImageRequestGate
from infini_local.web.vfx_debug_routes import _sample_data
from tests.vfx_image_fixtures import HttpCapture, _data, _request, _slot, offline_backend


def test_full_cache_callback_performs_one_png_assessment(offline_backend, monkeypatch):
    from collections import Counter
    from infini_local.pipelines import sprite_postprocess

    data = visual_sprite_generation.maybe_generate_visual_assets(_data([_request(layout='strip')]))
    calls = Counter()
    validate = asset_sync_service.is_complete_png_file

    def observe(path):
        calls[Path(path).resolve()] += 1
        return validate(path)

    monkeypatch.setattr(asset_sync_service, 'is_complete_png_file', observe)
    monkeypatch.setattr(sprite_postprocess, 'is_complete_png_file', observe)
    report = _cached_payload_report(data)
    assert report['ok'], report['errors']
    selected = [visual_delivery_gate._resolved_asset_path(name)
                for name in asset_sync_service.runtime_asset_files(data)]
    assert all(path is not None for path in selected)
    files = {path.resolve() for path in selected if path is not None}
    assert set(calls) == files and all(calls[path] == 1 for path in files), calls


def _get_asset(filename: str) -> HttpCapture:
    # These are exactly the three dependencies used by the unchanged asset route.
    routes = ServerUtilityRoutes.__new__(ServerUtilityRoutes)
    routes.sprite_dir = visual_delivery_gate.SPRITE_DIR
    routes.world_recipes_dir = visual_delivery_gate.WORLD_RECIPES_DIR
    routes.asset_sync_service = asset_sync_service
    handler = HttpCapture()
    assert routes.handle_get(handler, "/get_asset?" + urlencode({"file": filename}))
    return handler

def _assert_cache_refusal(data: dict, root: Path) -> None:
    before = copy.deepcopy(data)
    assert not world_storage.is_deliverable_recipe_payload(data)
    assert not _cached_payload_report(data)["ok"]
    with pytest.raises(ValueError, match="non-deliverable"):
        world_storage.write_world_recipe_cache(root, "test", "recipe", "world", data)
    target = world_storage.world_recipe_file(root, "world", "recipe")
    assert not target.exists()
    # An explicitly stale cache fixture must be quarantined, not returned/repaired.
    world_storage.atomic_write_json(target, data)
    raw = target.read_bytes()
    assert world_storage.read_world_recipe_cache(root, "test", "v5", "recipe", "world") is None
    assert not target.exists()
    quarantined = [p for p in (target.parent.parent / "invalid").glob("*.json")
                   if not p.name.endswith(".reason.json")]
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == raw
    assert data == before


@pytest.mark.parametrize("order", ["first", "later", "only"])
@pytest.mark.parametrize("consumer", ["plan", "delivery"])
def test_malformed_renderer_consumer_preserves_indexed_canonical_rejection(offline_backend, order, consumer):
    calls, _ = offline_backend
    data = _data([])
    good = _slot("good", "")
    good["element"]["texture"] = {"source": "item", "assetId": ""}
    bad = copy.deepcopy(good)
    bad.update(id="hostile", rendererKind=["spriteElement"])
    data["vfxManifest"]["slots"] = [bad, good] if order == "first" else [good, bad]
    if order == "only":
        data["vfxManifest"]["slots"] = [bad]
    index = 1 if order == "later" else 0
    before = copy.deepcopy(data)
    canonical = validate_vfx_manifest_wire(data)
    assert not canonical["ok"]
    assert f"$.vfxManifest.slots[{index}].rendererKind" in {row["path"] for row in canonical["errors"]}
    if consumer == "plan":
        with pytest.raises(ValueError, match="Invalid VFX asset request wire: ") as rejected:
            build_visual_asset_plan(data)
        assert json.loads(str(rejected.value).split(": ", 1)[1]) == canonical["errors"]
    else:
        report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
        assert not report["ok"]
        problem = next(row for row in report["problems"] if row["code"] == "vfx_manifest_invalid")
        assert problem["errors"] == canonical["errors"]
    assert data == before
    assert calls == []
    _assert_cache_refusal(data, visual_delivery_gate.SPRITE_DIR / "malformed-cache")


def _pad_complete_png(path: Path, target_size: int) -> None:
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo

    with Image.open(path) as source:
        image = source.copy()
    empty = PngInfo()
    empty.add_text("offline_padding", "")
    stream = io.BytesIO()
    image.save(stream, format="PNG", pnginfo=empty)
    info = PngInfo()
    info.add_text("offline_padding", "x" * (target_size - len(stream.getvalue())))
    image.save(path, pnginfo=info)
    assert path.stat().st_size == target_size
    assert asset_sync_service.is_complete_png_file(path)

@pytest.mark.parametrize('width,height,accepted', [
    (512, 1, True), (1, 512, True), (513, 1, False), (1, 513, False),
])
def test_final_png_dimension_admission_matches_client_512_ceiling(
    offline_backend, tmp_path, width, height, accepted,
):
    from PIL import Image

    data = visual_sprite_generation.maybe_generate_visual_assets(_data([]))
    target = Path(data['visual']['spritePath'])
    # Fully encoded manual pixels, not a forged/truncated IHDR.
    Image.new('RGBA', (width, height), (210, 100, 20, 255)).save(target)
    with Image.open(target) as source:
        source.load()
        assert source.size == (width, height)
    assert asset_sync_service.is_complete_png_file(target) is accepted
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert report['ok'] is accepted, report['problems']
    if accepted:
        world_storage.write_world_recipe_cache(tmp_path / 'dimension-cache', 'test', 'recipe', 'world', data)
        assert world_storage.read_world_recipe_cache(tmp_path / 'dimension-cache', 'test', 'v5', 'recipe', 'world')
    else:
        assert any(row['code'] == 'asset_roster_invalid_png' for row in report['problems'])
        _assert_cache_refusal(data, tmp_path / 'dimension-cache')


def test_whole_roster_exact_byte_limits_include_inactive_members_and_cache(offline_backend, tmp_path):
    from infini_local.web.server_utility_routes import MAX_ASSET_RESPONSE_BYTES

    data = visual_sprite_generation.maybe_generate_visual_assets(_data([_request(layout="strip")]))
    item = Path(data["visual"]["spritePath"])
    ingredient = Path(data["vfxManifest"]["assets"][0]["spritePath"])
    overlay = tmp_path / "unused_byte_budget_member.png"
    overlay.write_bytes(item.read_bytes())
    data["visual"]["equipOverlayPath"] = str(overlay)
    _pad_complete_png(ingredient, MAX_ASSET_RESPONSE_BYTES)
    overlay_bytes = visual_delivery_gate.MAX_DELIVERABLE_ASSET_BYTES - MAX_ASSET_RESPONSE_BYTES - item.stat().st_size
    _pad_complete_png(overlay, overlay_bytes)
    files = asset_sync_service.runtime_asset_files(data)
    assert len(files) == 3
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert not report["equipmentOverlayRequired"]
    assert report["ok"], report["problems"]
    for filename in files:
        response = _get_asset(filename)
        served = visual_delivery_gate._resolved_asset_path(filename)
        assert served is not None
        assert response.code == 200
        assert response.wfile.getvalue() == served.read_bytes()
        assert response.headers["Content-Length"] == str(served.stat().st_size)
    world_storage.write_world_recipe_cache(tmp_path / "cache", "test", "at_limit", "world", data)
    assert world_storage.read_world_recipe_cache(tmp_path / "cache", "test", "v5", "at_limit", "world")
    _pad_complete_png(overlay, overlay_bytes + 1)
    assert _get_asset(overlay.name).code == 200  # Individually servable, collectively refused.
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert {p["code"] for p in report["problems"]} == {"asset_roster_byte_limit_exceeded"}
    _assert_cache_refusal(data, tmp_path / "over-budget-cache")

@pytest.mark.parametrize('requests', [[], [_request(layout='cutout')], [_request(layout='strip')]],
                         ids=['shared-item', 'cutout-ingredient', 'strip-ingredient'])
def test_delivery_assesses_each_selected_png_once_and_rechecks_next_operation(
    offline_backend, monkeypatch, requests,
):
    from collections import Counter
    from infini_local.pipelines import sprite_postprocess

    data = visual_sprite_generation.maybe_generate_visual_assets(_data(requests))
    before = copy.deepcopy(data)
    calls = Counter()
    real = asset_sync_service.is_complete_png_file

    def counted(path):
        calls[Path(path).resolve()] += 1
        return real(path)

    monkeypatch.setattr(asset_sync_service, 'is_complete_png_file', counted)
    monkeypatch.setattr(sprite_postprocess, 'is_complete_png_file', counted)
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert report['ok'], report['problems']
    selected_files = [visual_delivery_gate._resolved_asset_path(name)
                      for name in asset_sync_service.runtime_asset_files(data)]
    assert all(path is not None for path in selected_files)
    files = {path.resolve() for path in selected_files if path is not None}
    assert set(calls) == files and all(calls[path] == 1 for path in files), calls
    assert data == before
    # No operation result may survive into a later assessment.
    Path(data['visual']['spritePath']).write_bytes(b'explicit corrupt next-operation fixture')
    calls.clear()
    next_report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert not next_report['ok']
    assert any(row['code'] == 'asset_roster_invalid_png' for row in next_report['problems'])
    assert set(calls) == files and all(calls[path] == 1 for path in files), calls
    assert data == before


@pytest.mark.parametrize('change', ['same_size', 'serving_precedence'])
def test_delivery_refuses_png_snapshot_changed_during_assessment(
    offline_backend, monkeypatch, tmp_path, change,
):
    import os

    data = visual_sprite_generation.maybe_generate_visual_assets(_data([]))
    item = Path(data['visual']['spritePath'])
    raw = item.read_bytes()
    real = asset_sync_service.is_complete_png_file
    mutated = []
    if change == 'serving_precedence':
        world = visual_delivery_gate.WORLD_RECIPES_DIR / item.name
        world.parent.mkdir(parents=True)
        item.replace(world)
        selected = world
    else:
        selected = item

    def change_after_validation(path):
        result = real(path)
        if Path(path) == selected and not mutated:
            stat = selected.stat()
            if change == 'same_size':
                # A same-length overwrite with restored mtime still changes ctime.
                selected.write_bytes(b'X' * len(raw))
                os.utime(selected, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            else:
                item.write_bytes(b'X' * len(raw))
            mutated.append(True)
        return result

    monkeypatch.setattr(asset_sync_service, 'is_complete_png_file', change_after_validation)
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert mutated and not report['ok'], 'delivery reused stale bytes or serving-root selection'
    assert any(row['code'] in {'asset_roster_changed_during_assessment', 'asset_roster_invalid_png'}
               for row in report['problems'])


def test_delivery_refuses_valid_symlink_retarget_between_slots_and_roster(
    offline_backend, monkeypatch, tmp_path,
):
    from PIL import Image

    data = visual_sprite_generation.maybe_generate_visual_assets(_data([]))
    item = Path(data['visual']['spritePath'])
    original = tmp_path / 'selected_before.png'
    replacement = tmp_path / 'selected_after.png'
    item.replace(original)
    Image.new('RGBA', (32, 32), (30, 180, 210, 255)).save(replacement)
    assert asset_sync_service.is_complete_png_file(original)
    assert asset_sync_service.is_complete_png_file(replacement)
    assert original.read_bytes() != replacement.read_bytes()
    item.symlink_to(original)
    roster = visual_delivery_gate._asset_roster_problems
    changed = []

    def retarget(paths, **kwargs):
        item.unlink()
        item.symlink_to(replacement)
        changed.append(True)
        return roster(paths, **kwargs)

    monkeypatch.setattr(visual_delivery_gate, '_asset_roster_problems', retarget)
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert changed and not report['ok'], 'two healthy files were combined into a nonexistent stable snapshot'
    assert any(row['code'] == 'asset_roster_changed_during_assessment' for row in report['problems'])


def test_unique_png_assessment_does_not_discount_distinct_transfer_names(
    offline_backend, monkeypatch, tmp_path,
):
    data = visual_sprite_generation.maybe_generate_visual_assets(_data([]))
    item = Path(data['visual']['spritePath'])
    alias = tmp_path / 'inactive_transfer_alias.png'
    alias.symlink_to(item)
    data['visual']['equipOverlayPath'] = str(alias)
    size = item.stat().st_size
    assert len(asset_sync_service.runtime_asset_files(data)) == 2
    assert _get_asset(item.name).wfile.getvalue() == _get_asset(alias.name).wfile.getvalue()
    monkeypatch.setattr(visual_delivery_gate, 'MAX_DELIVERABLE_ASSET_BYTES', size * 2)
    control = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert control['ok'], control['problems']
    monkeypatch.setattr(visual_delivery_gate, 'MAX_DELIVERABLE_ASSET_BYTES', size * 2 - 1)
    refused = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert not refused['ok'], 'physical-file validation dedupe discounted actual transfer bytes'
    assert {row['code'] for row in refused['problems']} == {'asset_roster_byte_limit_exceeded'}


def test_whole_roster_file_count_refusal_reaches_cache(offline_backend, monkeypatch, tmp_path):
    data = visual_sprite_generation.maybe_generate_visual_assets(_data())
    overlay = tmp_path / "unused_count_budget_member.png"
    overlay.write_bytes(Path(data["visual"]["spritePath"]).read_bytes())
    data["visual"]["equipOverlayPath"] = str(overlay)
    files = asset_sync_service.runtime_asset_files(data)
    assert len(files) == 3 and all(_get_asset(name).code == 200 for name in files)
    assert visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)["ok"]
    # The existing hard 32/33 boundary observer uses this same delivery owner.
    monkeypatch.setattr(visual_delivery_gate, "MAX_DELIVERABLE_ASSET_FILES", 2)
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert {p["code"] for p in report["problems"]} == {"asset_roster_file_limit_exceeded"}
    _assert_cache_refusal(data, tmp_path / "over-count-cache")

@pytest.fixture(autouse=True)
def isolated_serving_roots(monkeypatch, tmp_path):
    # Temporary PNGs must belong to the real filename-serving owner, not bypass
    # delivery's canonical root resolution via an arbitrary existing local path.
    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(visual_delivery_gate, "WORLD_RECIPES_DIR", tmp_path / "world-recipes")

def _equipment_data() -> dict:
    return {
        "id": "equipment_probe",
        "name": "Equipment Probe",
        "accessory": {"enabled": True},
        "armor": {"enabled": False, "slot": ""},
        "runtimeProgram": {
            "itemEntityId": "item",
            "entities": [
                {
                    "id": "item",
                    "kind": "item_body",
                    "visualRole": "inventory_item",
                    "visual": {},
                },
                {
                    "id": "shot",
                    "kind": "free_projectile",
                    "visualRole": "projectile",
                    "visual": {},
                    "hitbox": {"widthPx": 18, "heightPx": 10},
                },
            ],
        },
    }

def _equipment_kit(*, include_overlay: bool) -> dict:
    kit = {
        "schema": "infini.visual-kit.runtime-entities.v2",
        "item": {
            "prompt": "literal inventory icon",
            "negativePrompt": "authored negative exact",
            "silhouette": "compact icon",
            "visualIdentity": "literal item",
            "palette": ["steel", "amber"],
            "preferredCanvasSize": 32,
            "renderSizePx": 40, "forwardAngleDegrees": 45,
            "inventoryScale": 1.0,
            "worldScale": 1.0,
        },
        "entities": [
            {
                "entityId": "item",
                "assetMode": "baked_sprite",
                "visualProjectRef": "item",
                "prompt": "literal inventory icon",
                "silhouette": "compact icon",
                "visualIdentity": "literal item",
                "scale": 1.0,
            },
            {
                "entityId": "shot",
                "assetMode": "baked_sprite",
                "visualProjectRef": "entity",
                "prompt": "literal projectile",
                "silhouette": "compact projectile",
                "visualIdentity": "literal shot",
                "preferredCanvasSize": 64, "renderSizePx": 32, "forwardAngleDegrees": 0,
                "scale": 1.0,
            },
        ],
        "animationPlan": "Follow accepted runtime movement only.",
    }
    if include_overlay:
        kit["equipOverlay"] = {
            "prompt": "separate wearable amber brooch overlay",
            "silhouette": "small readable brooch",
            "visualIdentity": "amber brooch worn on the player",
            "preferredCanvasSize": 48,
        }
    return kit

def _stub_image_generation(monkeypatch, tmp_path: Path) -> list[tuple[str, str, str]]:
    """Intercept imagegen while leaving final PNG validation on its real path."""
    item_path = write_no_image_fixture_png(tmp_path / "item.png")
    calls: list[tuple[str, str, str]] = []

    def fake_item(candidate: dict) -> dict:
        candidate["visual"].update({
            "spritePath": str(item_path),
            "spriteUrl": "/sprite/item.png",
            "spriteStatus": "generated",
            "spriteTechnicalScore": 1.0,
        })
        return candidate

    def fake_asset(_data: dict, role: str, prompt: str, negative: str, asset_id: str, canvas: int, *, entity_id: str = "", publication_entity_id: str = ""):
        path = write_no_image_fixture_png(tmp_path / f"{asset_id}.png", size=canvas)
        calls.append((role, prompt, negative))
        return str(path), f"/sprite/{path.name}", 1.0, "generated"

    monkeypatch.setattr(visual_sprite_generation, "maybe_generate_sprite", fake_item)
    monkeypatch.setattr(visual_sprite_generation, "generate_visual_asset", fake_asset)
    monkeypatch.setattr(visual_sprite_generation, "write_visual_manifest", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(visual_sprite_generation, "VISUAL_ASSET_MODE", "full")
    return calls

def test_equipment_visual_kit_requires_and_projects_separate_overlay() -> None:
    missing, errors = _validate_kit(
        _equipment_kit(include_overlay=False),
        ["item", "shot"],
        "item",
        equipment_overlay_required=True,
    )
    assert missing is None
    assert any(row["path"] == "$.equipOverlay" for row in errors)

    kit, errors = _validate_kit(
        _equipment_kit(include_overlay=True),
        ["item", "shot"],
        "item",
        equipment_overlay_required=True,
    )
    assert kit is not None, errors
    data = _apply_kit(_equipment_data(), kit)
    assert data["visual"]["equipOverlayPrompt"] == "separate wearable amber brooch overlay"
    assert data["visual"]["equipOverlayStatus"] == "pending"
    assert data["visual"]["equipOverlayPath"] == ""
    overlay = next(row for row in build_visual_asset_plan(data) if row["role"] == "equip_overlay")
    assert overlay["required"] is True
    assert overlay["assetMode"] == "baked_sprite"
    assert overlay["canvas"] == 48

def test_overlay_and_entity_generation_receive_exact_authored_negative_prompt(monkeypatch, tmp_path: Path) -> None:
    kit, errors = _validate_kit(
        _equipment_kit(include_overlay=True),
        ["item", "shot"],
        "item",
        equipment_overlay_required=True,
    )
    assert kit is not None, errors
    data = _apply_kit(_equipment_data(), kit)
    calls = _stub_image_generation(monkeypatch, tmp_path)

    out = visual_sprite_generation.maybe_generate_visual_assets(data)
    by_role = {role: (prompt, negative) for role, prompt, negative in calls}
    assert by_role["runtime:projectile"][1] == "authored negative exact"
    assert by_role["equip_overlay"] == (
        "separate wearable amber brooch overlay",
        "authored negative exact",
    )
    assert out["visual"]["equipOverlayStatus"] == "generated"
    assert out["visual"]["equipOverlayPath"].endswith("equipment_probe_equip_overlay.png")
    delivery = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    assert delivery["ok"], delivery["problems"]
    assert {slot["role"] for slot in delivery["slots"] if slot["usable"]} == {
        "item", "equip_overlay", "entity:shot"
    }
    Path(out["visual"]["equipOverlayPath"]).unlink()
    missing_overlay = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    assert not missing_overlay["ok"]
    assert "required_equipment_overlay_missing" in {p["code"] for p in missing_overlay["problems"]}

def test_impact_texture_is_vfx_authored_planned_generated_and_projected(monkeypatch, tmp_path: Path) -> None:
    kit, errors = _validate_kit(
        _equipment_kit(include_overlay=True),
        ["item", "shot"],
        "item",
        equipment_overlay_required=True,
    )
    assert kit is not None, errors
    data = _apply_kit(_equipment_data(), kit)
    _hydrate_vfx_asset_prompts(data, {"slots": [{
        "entityId": "shot", "rendererKind": "impactSprite",
        "spritePrompt": "authored amber shard impact burst",
        "spriteNegativePrompt": "text, watermark, opaque square",
    }]})
    data["vfxManifest"] = {
        "schema": VFX_MANIFEST_SCHEMA,
        "slots": [{"id": "shot_impact", "entityId": "shot", "event": "on_spawn",
                   "rendererKind": "impactSprite", "textureRole": "impact"}],
    }
    assert validate_vfx_manifest_wire(data)["ok"]
    impact = next(row for row in build_visual_asset_plan(data) if row["role"] == "impact:shot")
    assert impact["required"] is True
    assert impact["prompt"] == "authored amber shard impact burst"

    calls = _stub_image_generation(monkeypatch, tmp_path)

    out = visual_sprite_generation.maybe_generate_visual_assets(data)
    assert ("impact", "authored amber shard impact burst", "text, watermark, opaque square") in calls
    shot = next(row for row in out["runtimeProgram"]["entities"] if row["id"] == "shot")
    assert shot["visual"]["impactSpritePath"].endswith("equipment_probe_shot_impact.png")
    assert shot["visual"]["impactSpriteStatus"] == "generated"
    report = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    impact_slot = next(slot for slot in report["slots"] if slot["role"] == "impact:shot")
    assert impact_slot["usable"] is True
    assert not any(problem.get("code") == "required_impact_sprite_missing" for problem in report["problems"])
    Path(shot["visual"]["impactSpritePath"]).write_bytes(b"not a PNG")
    corrupt_impact = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    assert not corrupt_impact["ok"]
    assert "required_impact_sprite_missing" in {p["code"] for p in corrupt_impact["problems"]}

def test_delivery_asset_roster_is_bounded_by_count_and_total_bytes(tmp_path: Path) -> None:
    many: list[Path] = []
    for index in range(33):
        path = tmp_path / f"asset-{index}.png"
        write_no_image_fixture_png(path)
        many.append(path)
    assert {problem["code"] for problem in visual_delivery_gate._asset_roster_problems(many)} == {
        "asset_roster_file_limit_exceeded"
    }
    assert visual_delivery_gate._asset_roster_problems(many[:32]) == []

    large: list[Path] = []
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo
    for index in range(3):
        path = tmp_path / f"large-{index}.png"
        write_no_image_fixture_png(path)
        info = PngInfo()
        info.add_text("offline_padding", "x" * (6 * 1024 * 1024))
        with Image.open(path) as image:
            image.save(path, pnginfo=info)
        large.append(path)
    assert {"asset_roster_byte_limit_exceeded"} == {
        problem["code"] for problem in visual_delivery_gate._asset_roster_problems(large)
    }

def _delivery_data(path: Path) -> dict:
    return {
        "visual": {"spriteStatus": "generated", "spritePath": str(path)},
        "runtimeProgram": {
            "itemEntityId": "item",
            "entities": [{"id": "item", "kind": "item_body", "visual": {}}],
        },
    }

def test_visual_delivery_rejects_corrupt_and_truncated_png(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(visual_delivery_gate, "VISUAL_REQUIRE_ITEM_SPRITE", True)
    valid = write_no_image_fixture_png(tmp_path / "valid.png")
    assert visual_delivery_gate.visual_delivery_report(
        _delivery_data(valid), check_backend_config=False
    )["ok"] is True
    placeholder = _delivery_data(valid)
    placeholder["visual"]["spriteStatus"] = "placeholder"
    placeholder_report = visual_delivery_gate.visual_delivery_report(placeholder, check_backend_config=False)
    assert not placeholder_report["ok"]
    assert "required_item_sprite_missing" in {p["code"] for p in placeholder_report["problems"]}

    corrupt = tmp_path / "corrupt.png"
    corrupt.write_bytes(b"not a png")
    corrupt_report = visual_delivery_gate.visual_delivery_report(
        _delivery_data(corrupt), check_backend_config=False
    )
    assert corrupt_report["ok"] is False
    assert corrupt_report["slots"][0]["completePng"] is False

    truncated = tmp_path / "truncated.png"
    truncated.write_bytes(valid.read_bytes()[:-1])
    truncated_report = visual_delivery_gate.visual_delivery_report(
        _delivery_data(truncated), check_backend_config=False
    )
    assert truncated_report["ok"] is False
    assert truncated_report["slots"][0]["completePng"] is False

def test_visual_delivery_rejects_non_png_sprite_files(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(visual_delivery_gate, "VISUAL_REQUIRE_ITEM_SPRITE", True)
    for name in ("sprite.txt", "sprite.json", "sprite"):
        path = tmp_path / name
        path.write_bytes(b"not an image")
        report = visual_delivery_gate.visual_delivery_report(
            _delivery_data(path), check_backend_config=False
        )
        assert report["ok"] is False, name
        assert report["slots"][0]["completePng"] is False, name
        assert report["slots"][0]["usable"] is False, name

    # An intact PNG with the supported extension must still be delivered.
    valid = write_no_image_fixture_png(tmp_path / "valid.PNG")
    assert visual_delivery_gate.visual_delivery_report(
        _delivery_data(valid), check_backend_config=False
    )["ok"] is True

def test_image_request_gate_bounds_parallel_backend_ownership() -> None:
    gate = ImageRequestGate(1)
    active = 0
    maximum = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal active, maximum
        with gate.slot():
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.03)
            with lock:
                active -= 1

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
    assert maximum == 1

def test_backend_dispatch_enters_shared_image_gate(monkeypatch) -> None:
    events: list[str] = []

    class ProbeGate:
        @contextlib.contextmanager
        def slot(self):
            events.append("enter")
            try:
                yield
            finally:
                events.append("exit")

    monkeypatch.setattr(visual_sprite_generation, "IMAGE_GENERATION_GATE", ProbeGate())
    monkeypatch.setattr(visual_sprite_generation, "IMAGE_BACKEND", "off")
    assert visual_sprite_generation._generate_backend_variants(
        {}, prompt="x", negative="", asset_id="x", canvas=32, role="item"
    ) == []
    assert events == ["enter", "exit"]

@pytest.fixture
def recipe(tmp_path, monkeypatch) -> dict:
    # The canonical sample references debug.png. A shape-only cache fixture can
    # no longer claim that nonempty member is ready without its served bytes.
    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(visual_delivery_gate, "WORLD_RECIPES_DIR", tmp_path / "world-recipes")
    write_no_image_fixture_png(tmp_path / "debug.png")
    data = _sample_data()
    data["vfxManifest"] = {"schema": VFX_MANIFEST_SCHEMA, "slots": []}
    assert world_storage.is_deliverable_recipe_payload(data) is True
    return data

@pytest.mark.parametrize("schema_version", ["broken", [], {}, [5], "5", 5.0, 5.9, True, None])
def test_deliverability_rejects_invalid_schema_version_without_coercion(recipe, schema_version):
    recipe["schemaVersion"] = schema_version
    original = copy.deepcopy(recipe)

    assert world_storage.is_deliverable_recipe_payload(recipe) is False
    assert recipe == original


@pytest.mark.parametrize("include_metadata", [False, True])
def test_valid_recipe_roundtrip_preserves_gameplay_and_stored_bytes(tmp_path, recipe, include_metadata):
    if include_metadata:
        recipe["debug"] = {"recipeIdentityVersion": "original", "custom": "keep"}
        recipe["recipeMeta"] = {"generationDepth": 2}
    original = copy.deepcopy(recipe)
    world_storage.write_world_recipe_cache(tmp_path, "test", "recipe", "world", recipe)
    assert recipe == original
    path = world_storage.world_recipe_file(tmp_path, "world", "recipe")
    stored = path.read_bytes()

    result = world_storage.read_world_recipe_cache(tmp_path, "test", "v5", "recipe", "world")

    assert result is not None
    assert world_storage.is_deliverable_recipe_payload(result) is True
    assert result["runtimeProgram"] == original["runtimeProgram"]
    assert result["vfxManifest"] == original["vfxManifest"]
    assert result["recipeMeta"]["worldId"] == "world"
    assert result["recipeMeta"]["worldScoped"] is True
    assert result["debug"]["cacheHit"] == "world_file"
    assert result["debug"]["cacheScope"] == "world"
    assert result["debug"]["recipeIdentityVersion"] == ("original" if include_metadata else "v5")
    if include_metadata:
        assert result["recipeMeta"]["generationDepth"] == 2
        assert result["debug"]["custom"] == "keep"
    assert path.read_bytes() == stored
    assert not (path.parent.parent / "invalid").exists()


TRANSFER_SELECTIONS = (
    [(form, "ingredient", "", 200, True, False) for form in ("absolute", "basename", "stale_windows", "http_url", "world_only")]
    + [(form, "ingredient", "", status, False, False) for form, status in
       (("outside", 404), ("unsafe_basename", 404), ("shadow", 200), ("sprite_precedence", 200), ("escape_symlink", 404))]
    + [("inactive", member, damage, status, False, False) for member, damage, status in
       (("overlay", "missing", 404), ("overlay", "corrupt", 200), ("overlay", "oversize", 413),
        ("overlay", "unsafe_basename", 404), ("body", "missing", 404), ("impact", "corrupt", 200))]
    + [("inactive", "overlay", damage, 404 if damage == "missing" else 200, False, True) for damage in ("missing", "corrupt")]
)

@pytest.mark.parametrize("form,member,damage,http_status,accepted,legacy", TRANSFER_SELECTIONS,
                         ids=[form + "-" + member + ("-" + damage if damage else "") + ("-legacy" if legacy else "") for form, member, damage, _, _, legacy in TRANSFER_SELECTIONS])
def test_transfer_selection_matches_readiness_and_cache(offline_backend, tmp_path, form, member, damage, http_status, accepted, legacy):
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo
    from infini_local.web.server_utility_routes import MAX_ASSET_RESPONSE_BYTES
    data = visual_sprite_generation.maybe_generate_visual_assets(_data([]) if legacy else _data([_request(layout="strip")]))
    assert world_storage.is_deliverable_recipe_payload(data) and _cached_payload_report(data)["ok"]
    asset = data["vfxManifest"]["assets"][0] if not legacy else None
    canonical = Path(asset["spritePath"]) if asset else Path(data["visual"]["spritePath"])
    raw = canonical.read_bytes()
    expected_owner = canonical
    if legacy:
        assert "assets" not in data["vfxManifest"] and data["vfxManifest"]["slots"] == []
    if form in {"absolute", "basename", "stale_windows", "http_url"}:
        asset["spritePath"] = {"absolute": str(canonical), "basename": canonical.name,
                               "stale_windows": "C:\\stale\\sprites\\" + canonical.name,
                               "http_url": "https://offline.invalid/sprites/" + canonical.name + "?version=old"}[form]
        filename = canonical.name
    elif form in {"outside", "unsafe_basename", "shadow"}:
        target = tmp_path / "unsafe space.png" if form == "unsafe_basename" else tmp_path / "outside" / (canonical.name if form == "shadow" else "safe.png")
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(raw)
        asset.update(spritePath=str(target), spriteUrl="/sprite/" + target.name)
        filename = target.name
        if form == "shadow":
            canonical.write_bytes(b"offline corrupt canonical PNG")
            assert asset_sync_service.is_complete_png_file(target) and not asset_sync_service.is_complete_png_file(canonical)
    elif form in {"world_only", "sprite_precedence", "escape_symlink"}:
        world = visual_delivery_gate.WORLD_RECIPES_DIR / canonical.name
        world.parent.mkdir()
        if form == "escape_symlink":
            outside = tmp_path.parent / (tmp_path.name + "_outside") / canonical.name
            outside.parent.mkdir(); outside.write_bytes(raw)
            canonical.unlink(); canonical.symlink_to(outside)
        else:
            world.write_bytes(raw); asset["spritePath"] = str(world)
            if form == "world_only":
                canonical.unlink(); expected_owner = world
            else:
                canonical.write_bytes(b"offline corrupt higher-priority sprite")
        filename = canonical.name
    else:
        filename = "unsafe member.png" if damage == "unsafe_basename" else "offline_unused_member.png"
        path = tmp_path / filename
        if damage == "corrupt":
            path.write_bytes(b"offline corrupt PNG")
        elif damage != "missing":
            info = PngInfo()
            if damage == "oversize": info.add_text("offline_padding", "x" * MAX_ASSET_RESPONSE_BYTES)
            Image.new("RGBA", (32, 32), (120, 80, 40, 144)).save(path, pnginfo=info)
            assert asset_sync_service.is_complete_png_file(path)
        orb = next(row for row in data["runtimeProgram"]["entities"] if row["id"] == "orb")
        target = data["visual"] if member == "overlay" else orb["visual"]
        target[{"overlay": "equipOverlayPath", "body": "spritePath", "impact": "impactSpritePath"}[member]] = str(path)
        assert path in [Path(p) for p in asset_sync_service.runtime_asset_paths(data) if p]
        expected_owner = path
    assert validate_vfx_manifest_wire(data)["ok"], "wire shape is independent of served pixel readiness"
    response = _get_asset(filename)
    assert response.code == http_status
    if http_status == 200:
        assert response.wfile.getvalue() == expected_owner.read_bytes()
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert report["ok"] is accepted, report["problems"]
    if accepted:
        assert visual_delivery_gate._resolved_asset_path(asset["spritePath"]).resolve() == expected_owner.resolve()
        assert response.wfile.getvalue() == raw
        assert response.headers["Content-Length"] == str(len(raw)) and "immutable" in response.headers["Cache-Control"]
        assert filename in asset_sync_service.runtime_asset_files(data)
        world_storage.write_world_recipe_cache(tmp_path / "cache", "test", "recipe", "world", data)
        cached = world_storage.read_world_recipe_cache(tmp_path / "cache", "test", "v5", "recipe", "world")
        assert cached is not None and cached["vfxManifest"].get("assets") == data["vfxManifest"].get("assets")
    else:
        if form in {"outside", "unsafe_basename"}:
            row = next(row for row in report["slots"] if row["role"] == "vfx:grain")
            assert not row["usable"] and not row["exists"]
        if form == "shadow":
            resolved = visual_delivery_gate._resolved_asset_path(asset["spritePath"])
            assert resolved is not None and resolved.resolve() == canonical.resolve()
        if form == "inactive":
            assert not report["equipmentOverlayRequired"]
            if not legacy:
                assert any(row["code"].startswith("asset_roster_") for row in report["problems"])
        _assert_cache_refusal(data, tmp_path / "refused-cache")

CACHE_CORRUPTIONS = [("metadata", field, value) for field in ("debug", "recipeMeta") for value in (None, [], "broken", 7)] + [
    ("unreadable", "", content) for content in (b"{broken", b"{}", b"[]", b"\xff")
] + [("combine", "schemaVersion", value) for value in ("broken", [5], "5", 5.9)]

@pytest.mark.parametrize("mode,field,value", CACHE_CORRUPTIONS)
def test_cache_corruption_quarantine_keeps_exact_bytes(tmp_path, monkeypatch, recipe, mode, field, value):
    key = "recipe"
    if mode == "combine":
        from infini_local.storage import world_recipe_runtime
        from infini_local.pipelines.combine_pipeline import combine_cache_lookup
        monkeypatch.setattr(world_recipe_runtime, "WORLD_RECIPES_DIR", tmp_path)
        payload = {"worldId": "world", "itemA": {"type": 1}, "itemB": {"type": 2}}
        key, cached = combine_cache_lookup(payload)
        assert cached is None
    target = world_storage.world_recipe_file(tmp_path, "world", key)
    if mode == "unreadable":
        target.parent.mkdir(parents=True); target.write_bytes(value)
    else:
        recipe[field] = value
        world_storage.atomic_write_json(target, recipe)
    raw = target.read_bytes()
    if mode == "combine":
        assert combine_cache_lookup(payload) == (key, None)
    else:
        assert world_storage.read_world_recipe_cache(tmp_path, "test", "v5", key, "world") is None
    assert not target.exists()
    invalid = target.parent.parent / "invalid"
    reasons = list(invalid.glob("*.reason.json"))
    assert len(reasons) == 1
    reason = world_storage.read_json_file(reasons[0])
    assert isinstance(reason, dict)
    assert reason["reason"] == {"metadata": "invalid_cache_metadata", "unreadable": "json_unreadable_or_empty", "combine": "low_level_runtime_contract_invalid"}[mode]
    assert (reasons[0].parent / reason["payloadFile"]).read_bytes() == raw
    if mode == "metadata":
        assert reason["details"]["invalidFields"] == [field]
        originals = [p for p in invalid.glob("*.json") if not p.name.endswith(".reason.json")]
        assert len(originals) == 1 and originals[0].read_bytes() == raw
    assert world_storage.read_world_recipe_cache(tmp_path, "test", "v5", key, "world") is None
    assert len(list(invalid.glob("*.reason.json"))) == 1
