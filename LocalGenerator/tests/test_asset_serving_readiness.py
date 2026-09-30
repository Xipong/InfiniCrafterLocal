"""Offline serving/cache acceptance through the real production route and gates.

The in-memory handler records HTTP output without opening a network listener.
Only the image backend supplies hand-authored fixtures; no readiness/PNG/wire
validator, storage or HTTP route is replaced.
"""
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

from test_vfx_asset_pipeline import _data, _request, _slot, offline_backend  # noqa: F401


class _HttpCapture:
    def __init__(self):
        self.status = None
        self.headers = {}
        self.wfile = io.BytesIO()

    def send_error(self, code):
        self.status = code

    def send_response(self, code):
        self.status = code

    def send_header(self, name, value):
        self.headers[name] = value

    def end_headers(self):
        pass


def _get_asset(filename: str) -> _HttpCapture:
    # These are exactly the three dependencies used by the unchanged asset route.
    routes = ServerUtilityRoutes.__new__(ServerUtilityRoutes)
    routes.sprite_dir = visual_delivery_gate.SPRITE_DIR
    routes.world_recipes_dir = visual_delivery_gate.WORLD_RECIPES_DIR
    routes.asset_sync_service = asset_sync_service
    handler = _HttpCapture()
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


@pytest.mark.parametrize("path_form", ["outside", "unsafe_basename"])
def test_required_ingredient_refuses_unservable_transfer_identity(offline_backend, tmp_path, path_form):
    data = visual_sprite_generation.maybe_generate_visual_assets(_data([_request(layout="strip")]))
    asset = data["vfxManifest"]["assets"][0]
    source = Path(asset["spritePath"])
    if path_form == "outside":
        target = tmp_path / "outside" / "safe.png"
        target.parent.mkdir()
    else:
        target = tmp_path / "unsafe space.png"
    target.write_bytes(source.read_bytes())
    asset.update(spritePath=str(target), spriteUrl="/sprite/" + target.name)
    assert validate_vfx_manifest_wire(data)["ok"]  # Shape is not readiness.
    response = _get_asset(target.name)
    assert response.status == 404
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert not report["ok"], report
    row = next(row for row in report["slots"] if row["role"] == "vfx:grain")
    assert not row["usable"]
    assert not row["exists"]
    _assert_cache_refusal(data, tmp_path / "cache")


@pytest.mark.parametrize("path_form", ["absolute", "basename", "stale_windows", "http_url"])
def test_required_ingredient_projection_validates_the_actual_served_png(offline_backend, tmp_path, path_form):
    data = visual_sprite_generation.maybe_generate_visual_assets(_data([_request(layout="strip")]))
    asset = data["vfxManifest"]["assets"][0]
    source = Path(asset["spritePath"])
    raw = source.read_bytes()
    projections = {
        "absolute": str(source), "basename": source.name,
        "stale_windows": "C:\\stale\\sprites\\" + source.name,
        "http_url": "https://offline.invalid/sprites/" + source.name + "?version=old",
    }
    asset["spritePath"] = projections[path_form]
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert report["ok"], report["problems"]
    assert visual_delivery_gate._resolved_asset_path(asset["spritePath"]).resolve() == source.resolve()
    response = _get_asset(source.name)
    assert response.status == 200
    assert response.wfile.getvalue() == raw
    assert response.headers["Content-Length"] == str(len(raw))
    assert "immutable" in response.headers["Cache-Control"]
    assert source.name in asset_sync_service.runtime_asset_files(data)
    world_storage.write_world_recipe_cache(tmp_path / "cache", "test", "recipe", "world", data)
    cached = world_storage.read_world_recipe_cache(tmp_path / "cache", "test", "v5", "recipe", "world")
    assert cached is not None
    assert cached["vfxManifest"]["assets"] == data["vfxManifest"]["assets"]


def test_ingredient_cannot_validate_a_local_shadow_instead_of_served_bytes(offline_backend, tmp_path):
    data = visual_sprite_generation.maybe_generate_visual_assets(_data([_request(layout="strip")]))
    asset = data["vfxManifest"]["assets"][0]
    canonical = Path(asset["spritePath"])
    shadow = tmp_path / "outside" / canonical.name
    shadow.parent.mkdir()
    shadow.write_bytes(canonical.read_bytes())
    canonical.write_bytes(b"offline corrupt canonical PNG")
    asset["spritePath"] = str(shadow)
    response = _get_asset(canonical.name)
    assert response.status == 200
    assert response.wfile.getvalue() == canonical.read_bytes()
    assert asset_sync_service.is_complete_png_file(shadow)
    assert not asset_sync_service.is_complete_png_file(canonical)
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert not report["ok"], report
    resolved = visual_delivery_gate._resolved_asset_path(shadow)
    assert resolved is not None and resolved.resolve() == canonical.resolve()
    _assert_cache_refusal(data, tmp_path / "cache")


@pytest.mark.parametrize("member,damage,http_status", [
    ("overlay", "missing", 404),
    ("overlay", "corrupt", 200),
    ("overlay", "oversize", 413),
    ("overlay", "unsafe_basename", 404),
    ("body", "missing", 404),
    ("impact", "corrupt", 200),
])
def test_nonempty_inactive_roster_member_must_be_transfer_ready(offline_backend, tmp_path, member, damage, http_status):
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo
    from infini_local.web.server_utility_routes import MAX_ASSET_RESPONSE_BYTES

    data = visual_sprite_generation.maybe_generate_visual_assets(_data())
    filename = "unsafe member.png" if damage == "unsafe_basename" else "offline_unused_member.png"
    path = tmp_path / filename
    if damage == "corrupt":
        path.write_bytes(b"offline corrupt PNG")
    elif damage != "missing":
        image = Image.new("RGBA", (32, 32), (120, 80, 40, 144))
        info = PngInfo()
        if damage == "oversize":
            info.add_text("offline_padding", "x" * MAX_ASSET_RESPONSE_BYTES)
        image.save(path, pnginfo=info)
        assert asset_sync_service.is_complete_png_file(path)
    orb = next(row for row in data["runtimeProgram"]["entities"] if row["id"] == "orb")
    target = data["visual"] if member == "overlay" else orb["visual"]
    field = {"overlay": "equipOverlayPath", "body": "spritePath", "impact": "impactSpritePath"}[member]
    target[field] = str(path)
    assert path in [Path(p) for p in asset_sync_service.runtime_asset_paths(data) if p]
    assert validate_vfx_manifest_wire(data)["ok"]
    response = _get_asset(filename)
    assert response.status == http_status
    if http_status == 200:
        assert response.wfile.getvalue() == path.read_bytes()
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert not report["equipmentOverlayRequired"]
    assert not report["ok"], report
    assert any(problem["code"].startswith("asset_roster_") for problem in report["problems"])
    _assert_cache_refusal(data, tmp_path / "cache")


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


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_legacy_cache_also_requires_its_nonempty_canonical_roster(offline_backend, tmp_path, damage):
    data = visual_sprite_generation.maybe_generate_visual_assets(_data([]))
    assert "assets" not in data["vfxManifest"] and data["vfxManifest"]["slots"] == []
    assert world_storage.is_deliverable_recipe_payload(data)
    assert _cached_payload_report(data)["ok"]
    path = tmp_path / "legacy_unused_overlay.png"
    if damage == "corrupt":
        path.write_bytes(b"offline corrupt legacy PNG")
    data["visual"]["equipOverlayPath"] = str(path)
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert not report["ok"]
    assert validate_vfx_manifest_wire(data)["ok"]
    _assert_cache_refusal(data, tmp_path / "legacy-cache")


@pytest.mark.parametrize("root_case", ["world_only", "sprite_precedence", "escape_symlink"])
def test_ingredient_readiness_uses_http_root_precedence_and_containment(offline_backend, tmp_path, root_case):
    data = visual_sprite_generation.maybe_generate_visual_assets(_data([_request(layout="strip")]))
    asset = data["vfxManifest"]["assets"][0]
    sprite = Path(asset["spritePath"])
    raw = sprite.read_bytes()
    world = visual_delivery_gate.WORLD_RECIPES_DIR / sprite.name
    world.parent.mkdir()
    if root_case == "escape_symlink":
        outside = tmp_path.parent / (tmp_path.name + "_outside") / sprite.name
        outside.parent.mkdir()
        outside.write_bytes(raw)
        sprite.unlink()
        sprite.symlink_to(outside)
    else:
        world.write_bytes(raw)
        asset["spritePath"] = str(world)
        if root_case == "world_only":
            sprite.unlink()
        else:
            sprite.write_bytes(b"offline corrupt higher-priority sprite")
    response = _get_asset(sprite.name)
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    if root_case == "world_only":
        assert response.status == 200 and response.wfile.getvalue() == raw
        assert report["ok"], report["problems"]
        assert visual_delivery_gate._resolved_asset_path(world) == world
        world_storage.write_world_recipe_cache(tmp_path / "cache", "test", "recipe", "world", data)
        assert world_storage.read_world_recipe_cache(tmp_path / "cache", "test", "v5", "recipe", "world")
    else:
        assert response.status == (404 if root_case == "escape_symlink" else 200)
        if root_case == "sprite_precedence":
            assert response.wfile.getvalue() == sprite.read_bytes()
        assert not report["ok"]
        _assert_cache_refusal(data, tmp_path / "cache")


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
        assert response.status == 200
        assert response.wfile.getvalue() == served.read_bytes()
        assert response.headers["Content-Length"] == str(served.stat().st_size)
    world_storage.write_world_recipe_cache(tmp_path / "cache", "test", "at_limit", "world", data)
    assert world_storage.read_world_recipe_cache(tmp_path / "cache", "test", "v5", "at_limit", "world")
    _pad_complete_png(overlay, overlay_bytes + 1)
    assert _get_asset(overlay.name).status == 200  # Individually servable, collectively refused.
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert {p["code"] for p in report["problems"]} == {"asset_roster_byte_limit_exceeded"}
    _assert_cache_refusal(data, tmp_path / "over-budget-cache")


def test_whole_roster_file_count_refusal_reaches_cache(offline_backend, monkeypatch, tmp_path):
    data = visual_sprite_generation.maybe_generate_visual_assets(_data())
    overlay = tmp_path / "unused_count_budget_member.png"
    overlay.write_bytes(Path(data["visual"]["spritePath"]).read_bytes())
    data["visual"]["equipOverlayPath"] = str(overlay)
    files = asset_sync_service.runtime_asset_files(data)
    assert len(files) == 3 and all(_get_asset(name).status == 200 for name in files)
    assert visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)["ok"]
    # The existing hard 32/33 boundary observer uses this same delivery owner.
    monkeypatch.setattr(visual_delivery_gate, "MAX_DELIVERABLE_ASSET_FILES", 2)
    report = visual_delivery_gate.visual_delivery_report(data, check_backend_config=False)
    assert {p["code"] for p in report["problems"]} == {"asset_roster_file_limit_exceeded"}
    _assert_cache_refusal(data, tmp_path / "over-count-cache")
