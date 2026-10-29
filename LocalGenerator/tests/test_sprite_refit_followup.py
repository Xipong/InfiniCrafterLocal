"""Offline retained-master/refit/publication contracts (real PNG pixels)."""
from __future__ import annotations

import errno
import json
from pathlib import Path

import pytest
from PIL import Image

from infini_local.pipelines import pipeline_visual_config as config
from infini_local.pipelines import sprite_postprocess as post
from infini_local.pipelines import visual_sprite_generation as generation


@pytest.fixture
def source_pixels():
    image = Image.new("RGBA", (64, 64))
    # Small native artwork hits the production master-upscale ceiling. The
    # ordinary final bake is readable but undersized, requiring real refit.
    for y in range(26, 38):
        image.paste((210, 40, 20, 255) if y % 2 else (220, 180, 30, 140), (28, y, 36, y + 1))
    return image


@pytest.fixture
def pipeline(tmp_path, monkeypatch, source_pixels):
    monkeypatch.setattr(config, "BG_COLOR", "transparent")
    monkeypatch.setattr(post, "SAVE_SPRITE_STAGES", False)
    monkeypatch.setattr(generation, "SPRITE_DIR", tmp_path / "public")
    monkeypatch.setattr(generation, "WORLD_RECIPES_DIR", tmp_path / "recipes")
    monkeypatch.setattr(generation, "IMAGE_BACKEND", "image_api")
    monkeypatch.setattr(generation, "IMAGE_BACKEND_CONFIG_ERROR", "")
    monkeypatch.setattr(generation, "SPRITE_RETRIES", 2)
    calls = []

    def provider(_data, **kwargs):
        calls.append(kwargs)
        source = kwargs["output_dir"] / "fixture_raw_image_api.png"
        source_pixels.save(source)
        kwargs["source"] = source
        kwargs["source_bytes"] = source.read_bytes()
        return [str(source)]

    monkeypatch.setattr(generation, "_generate_backend_variants", provider)
    return calls


@pytest.mark.parametrize("role", ["field", "runtime:projectile"])
def test_production_refit_publishes_master_detail_without_second_generation(tmp_path, pipeline, role):
    data = {"id": "refit-pixels"}
    published, _, _, status = generation.generate_visual_asset(data, role, "authored striped mark", "", "stripe", 24)
    assert published and status == "generated", data
    assert len(pipeline) == 1
    output_dir = pipeline[0]["output_dir"]
    original = output_dir / "stripe.png"
    refit = output_dir / "stripe_refit.png"
    assert refit.exists()
    assert json.loads(data["debug"][role + "SpriteRefit"])["samplingSource"] == "pre_bake_master"
    assert Path(published).read_bytes() == refit.read_bytes()
    assert pipeline[0]["source"].read_bytes() == pipeline[0]["source_bytes"]
    before = post.validate_processed_sprite(str(original), role, expected_canvas=24)
    assert not before["ok"] and not post.sprite_validation_fatal(before)
    assert post.validate_processed_sprite(published, role, expected_canvas=24)["ok"]
    original_bytes = original.read_bytes()
    low = generation.refit_processed_sprite_to_contract(str(original), "low-detail", 24, role, before, output_dir=tmp_path)
    assert original.read_bytes() == original_bytes
    with Image.open(published) as final, Image.open(low) as degraded:
        assert final.size == (24, 24)
        assert final.tobytes() != degraded.tobytes()
        assert bool(set(final.getchannel("A").tobytes()) - {0, 255}) == (role == "field")


def test_retained_master_cannot_alias_the_logical_asset_output(pipeline):
    deliveries = []
    for asset_id in ("stripe", "refit-master"):
        data = {"id": "same-author"}
        published, _, _, status = generation.generate_visual_asset(data, "field", "authored striped mark", "", asset_id, 24)
        assert published and status == "generated", data
        deliveries.append(Path(published).read_bytes())
    # Logical identity must not turn the master into an already-degraded bake.
    assert deliveries[0] == deliveries[1]
    assert len(pipeline) == 2


@pytest.mark.parametrize("master_state", ["absent", "malformed"])
def test_unavailable_master_preserves_bake_and_uses_only_safe_existing_source(pipeline, monkeypatch, master_state):
    save = Image.Image.save

    def damaged_master(image, path, *args, **kwargs):
        save(image, path, *args, **kwargs)
        if Path(path).name == "master.png":
            if master_state == "absent":
                Path(path).unlink()
            else:
                Path(path).write_bytes(b"not a PNG")

    monkeypatch.setattr(Image.Image, "save", damaged_master)
    data = {"id": "master-state"}
    published, _, _, status = generation.generate_visual_asset(data, "field", "authored striped mark", "", "stripe", 24)
    assert published and len(pipeline) == 1, data
    original = pipeline[0]["output_dir"] / "stripe.png"
    assert pipeline[0]["source"].read_bytes() == pipeline[0]["source_bytes"]
    if master_state == "malformed":
        assert status == "generated_warn_invalid"
        assert Path(published).read_bytes() == original.read_bytes()
        assert "fieldSpriteRefit" not in data["debug"]
    else:
        assert status == "generated"
        assert json.loads(data["debug"]["fieldSpriteRefit"])["samplingSource"] == "processed_sprite"
    assert not post.sprite_validation_fatal(post.validate_processed_sprite(published, "field", expected_canvas=24))


@pytest.mark.parametrize("fault", ["master-write", "master-read", "refit-write", "publication"])
def test_local_refit_io_fault_never_spends_another_generation(tmp_path, pipeline, monkeypatch, fault):
    save = Image.Image.save
    image_open = Image.open

    def failing_save(image, path, *args, **kwargs):
        target = Path(path)
        if ((fault == "master-write" and target.name == "master.png")
                or (fault == "refit-write" and target.name.endswith("_refit.png"))):
            raise OSError(errno.ENOSPC, "offline injected disk full")
        return save(image, path, *args, **kwargs)

    def failing_open(path, *args, **kwargs):
        if fault == "master-read" and Path(path).name == "master.png":
            raise OSError(errno.EACCES, "offline injected read denial")
        return image_open(path, *args, **kwargs)

    def failing_replace(*_args):
        raise OSError(errno.EIO, "offline injected atomic replace failure")

    monkeypatch.setattr(Image.Image, "save", failing_save)
    monkeypatch.setattr(Image, "open", failing_open)
    public = tmp_path / "public"
    public.mkdir()
    previous = public / "previous.png"
    Image.new("RGBA", (24, 24), (30, 60, 90, 100)).save(previous)
    previous_bytes = previous.read_bytes()
    if fault == "publication":
        monkeypatch.setattr(generation.os, "replace", failing_replace)
    data = {"id": "io-fault"}
    published, url, _, status = generation.generate_visual_asset(data, "field", "authored striped mark", "", "stripe", 24)
    assert not published and not url and status == "failed", data
    assert len(pipeline) == 1
    assert pipeline[0]["source"].read_bytes() == pipeline[0]["source_bytes"]
    assert previous.read_bytes() == previous_bytes
    assert list(public.iterdir()) == [previous]  # no exposed candidate or .part
    assert data["debug"]["fieldSpriteFailurePhase"] == ("publication" if fault == "publication" else "processing")


def test_mixed_fatal_and_fit_validation_retries_without_refit(pipeline, monkeypatch):
    # Increase only the existing opacity admission scalar so the same real small
    # PNG has both fit and fatal opacity findings. No validator/refit is mocked.
    monkeypatch.setattr(post, "SPRITE_MIN_OPAQUE_PCT", 0.20)
    data = {"id": "mixed-reasons"}
    published, _, _, status = generation.generate_visual_asset(data, "runtime:projectile", "authored striped mark", "", "stripe", 24)
    assert not published and status == "failed", data
    assert len(pipeline) == 3  # quality retry, unlike local IO failure
    rows = json.loads(data["debug"]["runtime:projectileSpriteValidation"])
    assert len(rows) == 3
    for row, call in zip(rows, pipeline):
        reasons = row["validation"]["reasons"]
        assert any(reason.startswith("core_silhouette_too_small:") for reason in reasons)
        assert any(reason.startswith("too_few_opaque_pixels:") for reason in reasons)
        assert "refit" not in row
        assert not list(call["output_dir"].glob("*_refit.png"))
        assert call["source"].read_bytes() == call["source_bytes"]


@pytest.mark.parametrize("topology", ["multipart_separated", "connected"])
def test_refit_preserves_authored_parts_without_topology_retry(pipeline, source_pixels, topology):
    source_pixels.paste((0, 0, 0, 0), (0, 0, 64, 64))
    source_pixels.paste((210, 40, 20, 255), (25, 26, 28, 38))
    source_pixels.paste((20, 100, 210, 255), (34, 26, 37, 38))
    data = {"id": "two-parts", "visual": {"topology": topology, "partCountMin": 2, "partCountMax": 2}}
    published, _, _, status = generation.generate_visual_asset(data, "item", "two authored separated colored marks", "", "parts", 24)
    assert published and status == "generated" and len(pipeline) == 1, data
    checked = post.validate_processed_sprite(published, "item", expected_canvas=24, topology=topology, part_count_min=2, part_count_max=2)
    assert checked["ok"] and checked["bboxStats"]["significantAlphaComponents"] == 2
    assert checked["topology"] == topology
    with Image.open(published) as image:
        red_x = [x for y in range(24) for x in range(24) if image.getpixel((x, y))[0] > image.getpixel((x, y))[2] + 60]
        blue_x = [x for y in range(24) for x in range(24) if image.getpixel((x, y))[2] > image.getpixel((x, y))[0] + 60]
        assert red_x and blue_x and max(red_x) < min(blue_x)
        assert set(image.getchannel("A").tobytes()) == {0, 255}
    assert pipeline[0]["source"].read_bytes() == pipeline[0]["source_bytes"]
    assert "itemSpriteRefit" in data["debug"]


def test_fatal_refit_is_not_published_over_usable_original(pipeline, source_pixels, monkeypatch):
    monkeypatch.setattr(post, "SPRITE_MAX_OPAQUE_PCT", 0.50)
    source_pixels.paste((0, 0, 0, 0), (0, 0, 64, 64))
    source_pixels.paste((180, 100, 30, 255), (26, 26, 38, 38))
    data = {"id": "solid-square"}
    published, _, _, status = generation.generate_visual_asset(data, "item", "authored solid square", "", "square", 24)
    assert published and status == "generated_warn_invalid" and len(pipeline) == 1, data
    original = pipeline[0]["output_dir"] / "square.png"
    assert Path(published).read_bytes() == original.read_bytes()
    rows = json.loads(data["debug"]["itemSpriteValidation"])
    assert not post.sprite_validation_fatal(rows[0]["validation"])
    assert post.sprite_validation_fatal(rows[0]["refit"]["validation"])
    assert "itemSpriteRefit" not in data["debug"]
    assert pipeline[0]["source"].read_bytes() == pipeline[0]["source_bytes"]
