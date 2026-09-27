"""Offline real-Pillow coverage; only model transport and unrelated IO are mocked."""
import copy
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from infini_local.pipelines import sprite_postprocess as post
from infini_local.pipelines import visual_sprite_generation as generation
from infini_local.pipelines.visual_asset_plan import build_visual_asset_plan
from infini_local.core.runtime_authoring.capability_registry import VISUAL_ROLE_BY_ENTITY_KIND


def source_image():
    image = Image.new("RGBA", (96, 96), (255, 0, 255, 255))
    draw = ImageDraw.Draw(image)
    for radius in range(34, 0, -1):
        draw.ellipse((48-radius, 48-radius, 48+radius, 48+radius),
                     fill=(35, 130, 225, 20 + (34-radius)*5))
    return image


@pytest.mark.parametrize("role,soft", [("impact", True), ("field", True), ("runtime:field", True),
                                      ("item", False), ("equip_overlay", False), ("runtime:projectile", False)])
def test_full_pipeline_alpha_and_source_preservation(tmp_path, monkeypatch, role, soft):
    monkeypatch.setattr(post, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(post, "SAVE_SPRITE_STAGES", True)
    raw = tmp_path / "pristine.png"
    source_image().save(raw)
    original = raw.read_bytes()
    output = Path(post.postprocess_sprite(str(raw), "result", 32, role))
    assert output != raw
    assert raw.read_bytes() == original
    image = Image.open(output).convert("RGBA")
    assert image.size == (32, 32)
    values = set(image.getchannel("A").tobytes())
    assert bool(values - {0, 255}) == soft
    if soft:
        for stage in ("10_sprite_keyer_fullres", "20_master_norm", "30_baked_final"):
            stage_image = Image.open(tmp_path / f"result_stage_{stage}.png")
            assert set(stage_image.getchannel("A").tobytes()) - {0, 255}
        validation = post.validate_processed_sprite(str(output), role)
        assert validation["ok"], validation
        assert "many_partial_alpha_pixels" not in validation["warnings"]


def run_plan(tmp_path, monkeypatch, entity_id, kind, declared=None):
    monkeypatch.setattr(post, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(generation, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(generation, "IMAGE_BACKEND", "image_api")
    monkeypatch.setattr(generation, "IMAGE_BACKEND_CONFIG_ERROR", "")
    monkeypatch.setattr(generation, "SPRITE_RETRIES", 0)
    monkeypatch.setattr(generation, "VISUAL_ASSET_MODE", "full")
    monkeypatch.setattr(generation, "maybe_generate_sprite", lambda data: data)
    monkeypatch.setattr(generation, "write_visual_manifest", lambda *args: None)
    raw = tmp_path / "source.png"
    source_image().save(raw)
    calls = []
    def backend(data, **kwargs):
        calls.append(kwargs)
        return [str(raw)]
    monkeypatch.setattr(generation, "_generate_backend_variants", backend)
    entity = {"id": entity_id, "kind": kind, "visualRole": declared if declared is not None else VISUAL_ROLE_BY_ENTITY_KIND[kind],
              "hitbox": {"widthPx": 32, "heightPx": 32},
              "visual": {"assetMode": "baked_sprite", "prompt": "blue authored shape"}}
    data = {"id": "fixture", "runtimeProgram": {"entities": [entity]},
            "vfxManifest": {"slots": [{"entityId": entity_id, "rendererKind": "impactSprite"}]}}
    entity["visual"]["impactPrompt"] = "blue authored impact"
    plan = build_visual_asset_plan(copy.deepcopy(data))
    result = generation.maybe_generate_visual_assets(data)
    return plan, result, calls


@pytest.mark.parametrize("kind", [k for k in VISUAL_ROLE_BY_ENTITY_KIND if k != "item_body"])
def test_plan_backend_postprocess_is_independent_of_entity_id(tmp_path, monkeypatch, kind):
    snapshots = []
    for entity_id in ("fire_blade", "frost_cloud_unrelated"):
        plan, result, calls = run_plan(tmp_path, monkeypatch, entity_id, kind)
        assert plan[0]["visualRole"] == VISUAL_ROLE_BY_ENTITY_KIND[kind]
        assert [c["role"] for c in calls] == ["runtime:" + VISUAL_ROLE_BY_ENTITY_KIND[kind], "impact"]
        assert all(entity_id not in c["prompt"] for c in calls)
        visual = result["runtimeProgram"]["entities"][0]["visual"]
        assert visual["spritePath"] and visual["impactSpritePath"]
        body = Image.open(visual["spritePath"]).convert("RGBA")
        impact = Image.open(visual["impactSpritePath"]).convert("RGBA")
        assert bool(set(body.getchannel("A").tobytes()) - {0, 255}) == (kind == "field")
        assert set(impact.getchannel("A").tobytes()) - {0, 255}
        snapshots.append((body.tobytes(), impact.tobytes(), [c["prompt"] for c in calls]))
    assert snapshots[0] == snapshots[1]


@pytest.mark.parametrize("role", ["impact", "runtime:field"])
def test_soft_policy_preserves_low_alpha_but_rejects_empty(tmp_path, role):
    image = Image.new("RGBA", (32, 32), (35, 130, 225, 1))
    assert post.cleanup_alpha(image, role).getpixel((0, 0))[3] == 1
    empty = tmp_path / "empty.png"
    Image.new("RGBA", (32, 32)).save(empty)
    validation = post.validate_processed_sprite(str(empty), role)
    assert "empty_alpha_bbox" in validation["reasons"]
    assert post.sprite_validation_fatal(validation)


def test_runtime_projectile_does_not_canonicalize_to_legacy_x():
    image = Image.new("RGBA", (64, 64))
    ImageDraw.Draw(image).rectangle((28, 8, 36, 56), fill=(200, 100, 30, 255))
    output, evidence = post.canonicalize_projectile_forward_axis(image, "runtime:projectile")
    assert output.tobytes() == image.tobytes()
    assert not evidence["rotated"] and not evidence["flipped"]


def test_mismatched_role_is_not_reinterpreted(tmp_path, monkeypatch):
    _, result, calls = run_plan(tmp_path, monkeypatch, "field_named_body", "free_projectile", "field")
    assert result["runtimeProgram"]["entities"][0]["visual"]["spriteStatus"] == "invalid_runtime_visual_role"
    assert [call["role"] for call in calls] == ["impact"]
