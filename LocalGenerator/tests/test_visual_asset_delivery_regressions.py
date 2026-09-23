from __future__ import annotations

import contextlib
import threading
import time
from pathlib import Path

from infini_local.pipelines import visual_delivery_gate, visual_sprite_generation
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
from infini_local.pipelines.visual_generation_pipeline import _apply_kit, _validate_kit
from infini_local.core.vfx_manifest import _hydrate_vfx_asset_prompts
from infini_local.qa.live_no_image_fixture import write_no_image_fixture_png
from infini_local.services.sdcpp_service import ImageRequestGate


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
                    "kind": "projectile",
                    "visualRole": "projectile",
                    "visual": {},
                    "hitbox": {"widthPx": 18, "heightPx": 10},
                },
            ],
        },
    }


def _equipment_kit(*, include_overlay: bool) -> dict:
    kit = {
        "schema": "infini.visual-kit.runtime-entities.v1",
        "item": {
            "prompt": "literal inventory icon",
            "negativePrompt": "authored negative exact",
            "silhouette": "compact icon",
            "visualIdentity": "literal item",
            "palette": ["steel", "amber"],
            "preferredCanvasSize": 32,
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
    item_path = tmp_path / "item.png"
    item_path.write_bytes(b"item-fixture")

    def fake_item(candidate: dict) -> dict:
        candidate["visual"].update({
            "spritePath": str(item_path),
            "spriteUrl": "/sprite/item.png",
            "spriteStatus": "generated",
            "spriteTechnicalScore": 1.0,
        })
        return candidate

    calls: list[tuple[str, str, str]] = []

    def fake_asset(_data: dict, role: str, prompt: str, negative: str, asset_id: str, canvas: int):
        del asset_id, canvas
        path = tmp_path / f"{role}.png"
        path.write_bytes(b"fixture")
        calls.append((role, prompt, negative))
        return str(path), f"/sprite/{path.name}", 1.0, "generated"

    monkeypatch.setattr(visual_sprite_generation, "maybe_generate_sprite", fake_item)
    monkeypatch.setattr(visual_sprite_generation, "generate_visual_asset", fake_asset)
    monkeypatch.setattr(visual_sprite_generation, "write_visual_manifest", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(visual_sprite_generation, "VISUAL_ASSET_MODE", "full")

    out = visual_sprite_generation.maybe_generate_visual_assets(data)
    by_role = {role: (prompt, negative) for role, prompt, negative in calls}
    assert by_role["entity_shot"][1] == "authored negative exact"
    assert by_role["equip_overlay"] == (
        "separate wearable amber brooch overlay",
        "authored negative exact",
    )
    assert out["visual"]["equipOverlayStatus"] == "generated"
    assert out["visual"]["equipOverlayPath"].endswith("equip_overlay.png")


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
        "slots": [{"entityId": "shot", "rendererKind": "impactSprite", "textureRole": "impact"}],
    }
    impact = next(row for row in build_visual_asset_plan(data) if row["role"] == "impact:shot")
    assert impact["required"] is True
    assert impact["prompt"] == "authored amber shard impact burst"

    item_path = tmp_path / "item.png"
    item_path.write_bytes(b"item-fixture")

    def fake_item(candidate: dict) -> dict:
        candidate["visual"].update({
            "spritePath": str(item_path),
            "spriteUrl": "/sprite/item.png",
            "spriteStatus": "generated",
            "spriteTechnicalScore": 1.0,
        })
        return candidate

    calls: list[tuple[str, str, str]] = []

    def fake_asset(_data: dict, role: str, prompt: str, negative: str, asset_id: str, canvas: int):
        del asset_id, canvas
        path = tmp_path / f"{role}.png"
        path.write_bytes(b"fixture")
        calls.append((role, prompt, negative))
        return str(path), f"/sprite/{path.name}", 1.0, "generated"

    monkeypatch.setattr(visual_sprite_generation, "maybe_generate_sprite", fake_item)
    monkeypatch.setattr(visual_sprite_generation, "generate_visual_asset", fake_asset)
    monkeypatch.setattr(visual_sprite_generation, "write_visual_manifest", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(visual_sprite_generation, "VISUAL_ASSET_MODE", "full")

    out = visual_sprite_generation.maybe_generate_visual_assets(data)
    assert ("impact_shot", "authored amber shard impact burst", "text, watermark, opaque square") in calls
    shot = next(row for row in out["runtimeProgram"]["entities"] if row["id"] == "shot")
    assert shot["visual"]["impactSpritePath"].endswith("impact_shot.png")
    assert shot["visual"]["impactSpriteStatus"] == "generated"
    monkeypatch.setattr(visual_delivery_gate, "_asset_path_exists", lambda _path: True)
    report = visual_delivery_gate.visual_delivery_report(out, check_backend_config=False)
    impact_slot = next(slot for slot in report["slots"] if slot["role"] == "impact:shot")
    assert impact_slot["usable"] is True
    assert not any(problem.get("code") == "required_impact_sprite_missing" for problem in report["problems"])


def test_delivery_asset_roster_is_bounded_by_count_and_total_bytes(tmp_path: Path) -> None:
    many: list[Path] = []
    for index in range(33):
        path = tmp_path / f"asset-{index}.png"
        path.write_bytes(b"x")
        many.append(path)
    assert {problem["code"] for problem in visual_delivery_gate._asset_roster_problems(many)} == {
        "asset_roster_file_limit_exceeded"
    }

    large: list[Path] = []
    for index in range(2):
        path = tmp_path / f"large-{index}.png"
        with path.open("wb") as stream:
            stream.truncate(9 * 1024 * 1024)
        large.append(path)
    assert "asset_roster_byte_limit_exceeded" in {
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
