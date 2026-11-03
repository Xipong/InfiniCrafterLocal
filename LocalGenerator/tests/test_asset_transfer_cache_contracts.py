"""Offline canonical asset transfer cache contracts; no live services."""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
from urllib.parse import urlencode
import pytest
from infini_local.core.vfx.validation import validate_vfx_manifest_wire
from infini_local.pipelines.visual import delivery as visual_delivery_gate
from infini_local.pipelines.images import stage as visual_sprite_generation
from infini_local.pipelines.visual.assets import build_visual_asset_plan
from infini_local.pipelines.combine_pipeline import _cached_payload_report
from infini_local.services import asset_sync_service
from infini_local.storage import world_storage
from infini_local.web.server_utility_routes import ServerUtilityRoutes
import threading
from infini_local.pipelines.visual.stage import _apply_kit
from infini_local.pipelines.visual.contract import _validate_kit
from infini_local.core.vfx.projection import _compile_manifest, _hydrate_vfx_asset_prompts
from infini_local.qa.live_no_image_fixture import write_no_image_fixture_png
from infini_local.services.sdcpp_service import ImageRequestGate
from infini_local.web.vfx_debug_routes import _sample_data
from tests.vfx_image_fixtures import HttpCapture, _data, _request, _slot, offline_backend
from pipeline_test_support import isolated_serving_roots, png_assessments, selected_pngs


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
def test_malformed_renderer_consumers_preserve_indexed_canonical_rejection(offline_backend, order):
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
    with pytest.raises(ValueError, match="Invalid VFX asset request wire: ") as rejected:
        build_visual_asset_plan(data)
    assert json.loads(str(rejected.value).split(": ", 1)[1]) == canonical["errors"]
    assert data == before
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


def test_png_admission_bounds_file_io_before_rejecting_oversize(tmp_path, monkeypatch):
    from PIL import Image
    path = tmp_path / "bounded.png"
    Image.new("RGBA", (2, 2), (255, 100, 40, 255)).save(path)
    raw = path.read_bytes()
    monkeypatch.setattr(asset_sync_service, "_MAX_PNG_BYTES", len(raw))
    assert asset_sync_service.is_complete_png_file(path)
    path.write_bytes(raw + b"x" * 1024)
    opened = []
    real_open = Path.open

    class BoundedRead:
        def __enter__(self):
            self.stream = real_open(path, "rb")
            return self

        def read(self, size=-1):
            assert 0 < size <= len(raw) + 1
            result = self.stream.read(size)
            opened.append(len(result))
            return result

        def __exit__(self, *args):
            self.stream.close()

    monkeypatch.setattr(Path, "open", lambda self, *a, **kw: BoundedRead() if self == path else real_open(self, *a, **kw))
    assert not asset_sync_service.is_complete_png_file(path)
    assert sum(opened) <= len(raw) + 1, "oversize rejection must bound total file reads"

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
    assert report["ok"], json.dumps(report["problems"], ensure_ascii=False)
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

@pytest.mark.parametrize("consumer", ["delivery", "cache"])
@pytest.mark.parametrize("requests", [[], [_request(layout="cutout")], [_request(layout="strip")]],
                         ids=["shared-item", "cutout-ingredient", "strip-ingredient"])
def test_png_assessment_is_operation_local_and_once_per_selected_file(
    offline_backend, png_assessments, consumer, requests,
):
    data = visual_sprite_generation.maybe_generate_visual_assets(_data(requests))
    before = copy.deepcopy(data)
    files = selected_pngs(data)
    assess = _cached_payload_report if consumer == "cache" else lambda value: visual_delivery_gate.visual_delivery_report(value, check_backend_config=False)
    png_assessments.clear()  # Generation precedes the measured consumer transaction.
    report = assess(data)
    assert report["ok"], report
    assert dict(png_assessments) == dict.fromkeys(files, 1)
    assert data == before
    Path(data["visual"]["spritePath"]).write_bytes(b"explicit corrupt next-operation fixture")
    png_assessments.clear()
    refused = assess(data)
    visual = refused["visual"] if consumer == "cache" else refused
    assert not refused["ok"]
    assert "asset_roster_invalid_png" in {row["code"] for row in visual["problems"]}
    assert dict(png_assessments) == dict.fromkeys(files, 1)
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
    monkeypatch.setattr(visual_delivery_gate, "MAX_DELIVERABLE_ASSET_FILES", len(files))
    assert visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)["ok"]
    world_storage.write_world_recipe_cache(tmp_path / "at-count-cache", "test", "recipe", "world", data)
    assert world_storage.read_world_recipe_cache(tmp_path / "at-count-cache", "test", "v5", "recipe", "world")
    monkeypatch.setattr(visual_delivery_gate, "MAX_DELIVERABLE_ASSET_FILES", len(files) - 1)
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert {p["code"] for p in report["problems"]} == {"asset_roster_file_limit_exceeded"}
    _assert_cache_refusal(data, tmp_path / "over-count-cache")

def _equipment_data() -> dict:
    return {
        "id": "equipment_probe", "name": "Equipment Probe",
        "accessory": {"enabled": True}, "armor": {"enabled": False, "slot": ""},
        "runtimeProgram": {"itemEntityId": "item", "entities": [
            {"id": "item", "kind": "item_body", "visualRole": "inventory_item", "visual": {}},
            {"id": "shot", "kind": "free_projectile", "visualRole": "projectile",
             "visual": {}, "hitbox": {"widthPx": 18, "heightPx": 10}},
        ]},
    }


def _equipment_kit(*, include_overlay: bool) -> dict:
    from infini_local.pipelines.visual.contract import VISUAL_KIT_SCHEMA
    item = {
        "prompt": "literal inventory icon", "negativePrompt": "authored negative exact",
        "silhouette": "compact icon", "visualIdentity": "literal item", "palette": ["steel", "amber"],
        "preferredCanvasSize": 32, "renderSizePx": 40, "forwardAngleDegrees": 45,
        "inventoryScale": 1.0, "worldScale": 1.0,
    }
    kit = {
        "schema": VISUAL_KIT_SCHEMA, "item": item,
        "entities": [
            {"entityId": "item", "assetMode": "baked_sprite", "visualProjectRef": "item",
             "scale": 1.0},
            {"entityId": "shot", "assetMode": "baked_sprite", "visualProjectRef": "entity",
             "prompt": "literal projectile", "silhouette": "compact projectile", "visualIdentity": "literal shot",
             "preferredCanvasSize": 64, "renderSizePx": 32, "forwardAngleDegrees": 0, "scale": 1.0},
        ],
        "animationPlan": "Follow accepted runtime movement only.",
    }
    if include_overlay:
        kit["equipOverlay"] = {
            "prompt": "separate wearable amber brooch overlay", "silhouette": "small readable brooch",
            "visualIdentity": "amber brooch worn on the player", "preferredCanvasSize": 48,
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

    def fake_asset(_data: dict, role: str, prompt: str, negative: str, asset_id: str, canvas: int, *, entity_id: str = "", processing_role: str = "", publication_entity_id: str = ""):
        path = write_no_image_fixture_png(tmp_path / f"{asset_id}.png", size=canvas)
        if processing_role == "vfx_cutout":
            from PIL import Image, ImageDraw
            # Explicit offline provider pixels, not the no-image opaque marker.
            image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((canvas // 4, canvas // 4, canvas * 3 // 4, canvas * 3 // 4), fill=(220, 145, 40, 255))
            image.save(path)
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

@pytest.mark.parametrize("impact", [False, True], ids=["equipment-overlay-and-body", "vfx-authored-impact"])
def test_authored_asset_transaction_projects_generates_and_refuses_missing_bytes(monkeypatch, tmp_path, impact):
    kit, errors = _validate_kit(_equipment_kit(include_overlay=True), ["item", "shot"], "item", equipment_overlay_required=True)
    assert kit is not None, errors
    data = _apply_kit(_equipment_data(), kit)
    if impact:
        from tests.vfx_material_fixtures import _with_asset
        authored = _with_asset(data)
        authored["assets"][0].update(id="shot_impact", prompt="authored amber shard impact burst",
                                      negativePrompt="text, watermark, opaque square", canvasSize=32)
        authored["slots"][0].update(id="shot_impact", entityId="shot", event="on_spawn")
        authored["slots"][0]["element"]["texture"]["assetId"] = "shot_impact"
        data["vfxManifest"] = _compile_manifest(data, authored, "equipment-impact")
        _hydrate_vfx_asset_prompts(data, authored)
        assert validate_vfx_manifest_wire(data)["ok"]
        planned = next(row for row in build_visual_asset_plan(data) if row["role"] == "vfx:shot_impact")
        assert planned["required"] is True and planned["prompt"] == "authored amber shard impact burst"
    calls = _stub_image_generation(monkeypatch, tmp_path)
    out = visual_sprite_generation.maybe_generate_visual_assets(data)
    by_role = {role: (prompt, negative) for role, prompt, negative in calls}
    assert by_role["runtime:projectile"][1] == "authored negative exact"
    assert by_role["equip_overlay"] == ("separate wearable amber brooch overlay", "authored negative exact")
    assert out["visual"]["equipOverlayStatus"] == "generated"
    assert out["visual"]["equipOverlayPath"].endswith("equipment_probe_equip_overlay.png")
    owner = next(row for row in out["vfxManifest"]["assets"] if row["id"] == "shot_impact") if impact else out["visual"]
    prefix = "sprite" if impact else "equipOverlay"
    if impact:
        assert by_role["vfx:shot_impact"] == ("authored amber shard impact burst", "text, watermark, opaque square")
        assert owner[prefix + "Path"].endswith(".png")
        assert owner[prefix + "Status"] == "generated"
    report = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    assert report["ok"], json.dumps(report["problems"], ensure_ascii=False)
    assert {slot["role"] for slot in report["slots"] if slot["usable"]} == {"item", "equip_overlay", "entity:shot"} | ({"vfx:shot_impact"} if impact else set())
    problem = "required_vfx_sprite_missing_or_invalid" if impact else "required_equipment_overlay_missing"
    assert not any(row.get("code") == problem for row in report["problems"])
    path = Path(owner[prefix + "Path"])
    if impact:
        path.write_bytes(b"not a PNG")
    else:
        path.unlink()
    refused = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    assert not refused["ok"]
    assert problem in {row["code"] for row in refused["problems"]}


def _delivery_data(path: Path) -> dict:
    return {
        "visual": {"spriteStatus": "generated", "spritePath": str(path)},
        "runtimeProgram": {
            "itemEntityId": "item",
            "entities": [{"id": "item", "kind": "item_body", "visual": {}}],
        },
    }

@pytest.mark.parametrize("name,damage,status,accepted", [
    pytest.param("valid.png", "none", "generated", True, id="complete-png"),
    pytest.param("valid.PNG", "none", "generated", True, id="uppercase-png-extension"),
    pytest.param("placeholder.png", "none", "placeholder", False, id="healthy-placeholder-not-generated"),
    pytest.param("corrupt.png", "corrupt", "generated", False, id="corrupt-png"),
    pytest.param("truncated.png", "truncated", "generated", False, id="truncated-real-png"),
    pytest.param("sprite.txt", "none", "generated", False, id="valid-png-with-unsupported-extension"),
])
def test_delivery_png_admission_requires_complete_bytes_and_completed_status(monkeypatch, tmp_path, name, damage, status, accepted):
    monkeypatch.setattr(visual_delivery_gate, "VISUAL_REQUIRE_ITEM_SPRITE", True)
    path = write_no_image_fixture_png(tmp_path / name)
    if damage == "corrupt":
        path.write_bytes(b"not a png" if name.endswith(".png") else b"not an image")
    elif damage == "truncated":
        path.write_bytes(path.read_bytes()[:-1])
    data = _delivery_data(path)
    data["visual"]["spriteStatus"] = status
    before = copy.deepcopy(data)
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert report["ok"] is accepted, report
    if not accepted:
        assert report["slots"][0]["usable"] is False
        if damage != "none":
            assert report["slots"][0]["completePng"] is False
        else:
            assert "required_item_sprite_missing" in {row["code"] for row in report["problems"]}
    assert data == before


def test_real_backend_dispatch_owns_gate_and_releases_it_after_failure(monkeypatch) -> None:
    gate = ImageRequestGate(1)
    entered, release, queued = (threading.Event() for _ in range(3))
    calls = []
    failure = RuntimeError("synthetic backend failure")

    def backend(prompt, negative, asset_id, canvas, **kwargs):
        calls.append((asset_id, prompt, negative, canvas))
        if asset_id == "failing":
            entered.set()
            assert release.wait(5), "test did not release the backend"
            raise failure
        return [asset_id + ".png"]

    def dispatch(asset_id):
        if asset_id == "healthy":
            queued.set()
        return visual_sprite_generation._generate_backend_variants(
            {}, prompt="literal " + asset_id, negative="authored negative",
            asset_id=asset_id, canvas=32, role="item",
        )

    monkeypatch.setattr(visual_sprite_generation, "IMAGE_GENERATION_GATE", gate)
    monkeypatch.setattr(visual_sprite_generation, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(visual_sprite_generation, "IMAGE_BACKEND_CONFIG_ERROR", "")
    monkeypatch.setattr(visual_sprite_generation, "generate_sdcpp", backend)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(dispatch, "failing")
        second = None
        try:
            assert entered.wait(5), "backend was never entered"
            # Probe the actual admission primitive while the real dispatcher is
            # inside external I/O; scheduler timing cannot make this pass.
            spare = gate._semaphore.acquire(blocking=False)
            if spare:
                gate._semaphore.release()
            assert not spare, "backend dispatch did not hold its only admission slot"
            second = workers.submit(dispatch, "healthy")
            assert queued.wait(5), "sibling request never started"
            assert not second.done(), "sibling bypassed the occupied backend gate"
            release.set()
            with pytest.raises(RuntimeError) as caught:
                first.result(timeout=5)
            assert caught.value is failure
            assert second.result(timeout=5) == ["healthy.png"]
        finally:
            release.set()
            # Even a missing-release regression must not strand an executor
            # worker after its bounded result() assertion has failed.
            if second is not None and not second.done():
                try:
                    gate._semaphore.release()
                except ValueError:
                    pass
    assert sorted(calls) == [
        ("failing", "literal failing", "authored negative", 32),
        ("healthy", "literal healthy", "authored negative", 32),
    ]
    assert gate._semaphore.acquire(blocking=False), "successful sibling leaked its slot"
    gate._semaphore.release()

@pytest.fixture
def recipe(tmp_path, monkeypatch) -> dict:
    # The canonical sample references debug.png. A shape-only cache fixture can
    # no longer claim that nonempty member is ready without its served bytes.
    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(visual_delivery_gate, "WORLD_RECIPES_DIR", tmp_path / "world-recipes")
    write_no_image_fixture_png(tmp_path / "debug.png")
    data = _sample_data()
    data["visual"] = {"preferredCanvasSize": 32, "spritePath": "debug.png", "spriteStatus": "generated"}
    data["vfxManifest"] = _compile_manifest(data, {"slots": []}, "asset-cache-probe")
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
        # Authenticate scope before corrupting the targeted runtime/metadata lane.
        recipe["recipeKey"] = key
        recipe.setdefault("recipeMeta", {})["worldId"] = "world"
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
