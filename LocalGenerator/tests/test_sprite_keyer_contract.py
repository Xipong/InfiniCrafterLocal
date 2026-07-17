from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw
from infini_local.pipelines import sprite_postprocess as SPRITE_POSTPROCESS
from infini_local.pipelines import visual_sprite_generation as SPRITE_GENERATION
from infini_local.pipelines.sprite_postprocess import (
    alpha_stats,
    postprocess_sprite,
    sprite_validation_fatal,
    technical_validation_score,
    validate_processed_sprite,
)


def _rgba_pixels(image: Image.Image) -> list[tuple[int, int, int, int]]:
    raw = image.tobytes()
    return [tuple(raw[i:i + 4]) for i in range(0, len(raw), 4)]


def _check_sprite_keyer_removes_magenta_without_eating_white_shape(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw_magenta_white_square.png"
    img = Image.new("RGBA", (64, 64), (255, 0, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle((16, 16, 47, 47), fill=(250, 250, 250, 255))
    img.save(raw_path)

    out = postprocess_sprite(str(raw_path), "sprite_keyer_contract", target_size=32, role="item")
    assert out is not None
    result = Image.open(out).convert("RGBA")
    assert result.size == (32, 32)
    assert result.getpixel((0, 0))[3] == 0

    raw = result.tobytes()
    pixels = [tuple(raw[i:i + 4]) for i in range(0, len(raw), 4)]
    visible = [(r, g, b, a) for r, g, b, a in pixels if a > 0]
    assert len(visible) >= 600
    magenta_visible = sum(1 for r, g, b, a in visible if r > 180 and b > 180 and g < 80)
    white_visible = sum(1 for r, g, b, a in visible if r > 200 and g > 200 and b > 200)
    assert magenta_visible == 0
    assert white_visible >= 500


def _check_sprite_keyer_samples_uniform_shifted_zimage_pink_background(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw_shifted_pink_coin_stack.png"
    img = Image.new("RGBA", (64, 64), (202, 6, 140, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse((20, 16, 45, 40), fill=(230, 230, 220, 255), outline=(50, 50, 50, 255), width=2)
    img.save(raw_path)

    out = postprocess_sprite(str(raw_path), "sprite_keyer_shifted_pink", target_size=32, role="item")
    assert out is not None
    result = Image.open(out).convert("RGBA")
    assert result.getpixel((0, 0))[3] == 0
    validation = validate_processed_sprite(str(out), "item")
    assert validation["ok"], validation
    visible = [px for px in _rgba_pixels(result) if px[3] > 0]
    pink_visible = sum(1 for r, g, b, a in visible if r > 150 and b > 90 and g < 80)
    assert pink_visible == 0


def _check_validation_rejects_opaque_inner_poster_card_as_fatal_background_failure(tmp_path: Path) -> None:
    path = tmp_path / "bad_inner_white_card.png"
    img = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle((2, 2, 45, 45), fill=(250, 250, 250, 255))
    draw.line((10, 38, 38, 10), fill=(70, 35, 15, 255), width=4)
    img.save(path)

    validation = validate_processed_sprite(str(path), "item")
    assert not validation["ok"], validation
    assert any(str(r).startswith("very_dense_opaque_area") for r in validation["reasons"]), validation
    assert sprite_validation_fatal(validation), validation


def _check_sprite_keyer_removes_enclosed_sampled_magenta_holes(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw_enclosed_magenta_hole.png"
    img = Image.new("RGBA", (128, 128), (229, 84, 210, 255))
    draw = ImageDraw.Draw(img)
    # Simulate a curved bow/string enclosing a key-colored interior pocket.
    draw.arc((28, 14, 104, 114), 250, 105, fill=(40, 22, 14, 255), width=8)
    draw.line((40, 96, 92, 28), fill=(55, 20, 12, 255), width=4)
    draw.line((48, 84, 86, 36), fill=(180, 92, 35, 255), width=5)
    img.save(raw_path)
    out = postprocess_sprite(str(raw_path), "sprite_keyer_enclosed_hole", target_size=48, role="item")
    assert out is not None
    validation = validate_processed_sprite(str(out), "item")
    assert validation["ok"], validation
    result = Image.open(out).convert("RGBA")
    visible = [px for px in _rgba_pixels(result) if px[3] > 0]
    key_visible = sum(1 for r, g, b, a in visible if r > 170 and b > 150 and g < 110)
    assert key_visible == 0


def _check_sprite_keyer_removes_inner_white_poster_card_when_foreground_exists(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw_inner_white_poster_card.png"
    img = Image.new("RGBA", (128, 128), (229, 84, 210, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle((18, 18, 110, 110), fill=(250, 250, 250, 255))
    draw.line((36, 90, 92, 35), fill=(50, 25, 12, 255), width=9)
    draw.line((40, 86, 88, 39), fill=(180, 90, 34, 255), width=4)
    img.save(raw_path)
    out = postprocess_sprite(str(raw_path), "sprite_keyer_inner_card", target_size=48, role="item")
    assert out is not None
    validation = validate_processed_sprite(str(out), "item")
    assert validation["ok"], validation
    result = Image.open(out).convert("RGBA")
    stats = alpha_stats(result)
    assert stats["transparentPct"] > 0.45, stats
    visible = [px for px in _rgba_pixels(result) if px[3] > 0]
    white_visible = sum(1 for r, g, b, a in visible if r > 220 and g > 220 and b > 220)
    assert white_visible < 20


def _check_sprite_keyer_removes_disconnected_nested_pink_frame(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw_nested_white_and_pink_card.png"
    img = Image.new("RGBA", (128, 128), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle((10, 10, 117, 117), fill=(229, 79, 200, 255))
    draw.rectangle((10, 10, 117, 117), outline=(242, 182, 230, 255), width=1)
    draw.rectangle((11, 11, 116, 116), outline=(220, 120, 198, 255), width=1)
    # A compact purple glaive that does not touch the generated card border.
    draw.polygon([(28, 30), (39, 24), (91, 80), (82, 89)], fill=(74, 18, 160, 255))
    draw.line((82, 84, 103, 105), fill=(38, 22, 55, 255), width=8)
    img.save(raw_path)

    out = postprocess_sprite(str(raw_path), "sprite_keyer_nested_pink_frame", target_size=48, role="item")
    assert out is not None
    result = Image.open(out).convert("RGBA")
    visible = [px for px in _rgba_pixels(result) if px[3] > 0]
    pale_pink = sum(1 for r, g, b, _a in visible if r > 190 and b > 175 and 80 < g < 215)

    assert pale_pink < 12, {"palePink": pale_pink, "alpha": alpha_stats(result)}


def _check_technical_score_describes_final_validation_not_raw_candidate() -> None:
    clean = technical_validation_score({"ok": True, "reasons": [], "warnings": []})
    fatal = technical_validation_score({
        "ok": False,
        "reasons": ["magenta_key_background_left:0.31"],
        "warnings": [],
    })
    accepted_warning = technical_validation_score({
        "ok": False,
        "reasons": ["core_silhouette_too_small:8px<12px"],
        "warnings": ["item_diagonal_or_thin_core:0.12"],
    })

    assert clean == 1.0
    assert fatal == 0.0
    assert 0.0 < accepted_warning < 1.0


def _check_postprocess_failure_preserves_the_original_asset_path(monkeypatch) -> None:
    original = "/tmp/original_generated_sprite.png"

    def fail_open(_path):
        raise OSError("synthetic decode failure")

    monkeypatch.setattr(SPRITE_POSTPROCESS.Image, "open", fail_open)
    assert postprocess_sprite(original, "decode_failure", target_size=32, role="item") == original


def _check_nearest_downscale_is_not_a_supported_runtime_or_gui_path(monkeypatch) -> None:
    source = (Path(__file__).resolve().parents[1] / "infini_local/pipelines/sprite_postprocess.py").read_text(encoding="utf-8")
    gui = (Path(__file__).resolve().parents[1] / "infini_local/desktop/settings_gui_image_args.py").read_text(encoding="utf-8")
    schema = (Path(__file__).resolve().parents[1] / "infini_local/desktop/settings_schema.py").read_text(encoding="utf-8")

    monkeypatch.setattr(SPRITE_POSTPROCESS, "SPRITE_PROCESSING_PROFILE", "master_soft")
    monkeypatch.setattr(SPRITE_POSTPROCESS, "SPRITE_DOWNSCALE_FILTER", "nearest")

    assert SPRITE_POSTPROCESS.sprite_resample_filter() == Image.Resampling.BOX
    assert "Resampling.NEAREST" not in source
    assert 'values=["nearest"' not in gui
    assert '"nearest":' not in schema
    assert "legacy_nearest" not in gui
    assert "pixel_strict" not in gui


def _check_item_topology_rejects_multiple_disconnected_significant_bodies(tmp_path) -> None:
    path = tmp_path / "disconnected_item.png"
    img = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle((5, 12, 20, 35), fill=(190, 90, 30, 255))
    draw.rectangle((28, 12, 43, 35), fill=(70, 150, 220, 255))
    img.save(path)

    validation = validate_processed_sprite(str(path), "item")
    assert validation["ok"] is True
    assert "missing_authored_topology" in validation["warnings"]


def _check_authored_multipart_topology_is_not_forced_into_one_body(tmp_path) -> None:
    path = tmp_path / "authored_multipart_item.png"
    img = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle((5, 12, 20, 35), fill=(190, 90, 30, 255))
    draw.rectangle((28, 12, 43, 35), fill=(70, 150, 220, 255))
    img.save(path)

    separated = validate_processed_sprite(
        str(path), "item", topology="multipart_separated", part_count_min=2, part_count_max=2
    )
    touching = validate_processed_sprite(
        str(path), "item", topology="multipart_touching", part_count_min=2, part_count_max=2
    )

    assert separated["ok"], separated
    assert separated["topology"] == "multipart_separated"
    assert touching["ok"] is False
    assert "multipart_touching_requires_connected_body" in touching["reasons"]
    assert sprite_validation_fatal(touching)

    wrong_count = validate_processed_sprite(
        str(path), "item", topology="multipart_separated", part_count_min=3, part_count_max=3
    )
    assert wrong_count["ok"] is False
    assert any(reason.startswith("multipart_separated_too_few_bodies") for reason in wrong_count["reasons"])
    assert sprite_validation_fatal(wrong_count)

    draw.rectangle((20, 12, 28, 35), fill=(190, 90, 30, 255))
    img.save(path)
    touching_authored = validate_processed_sprite(
        str(path), "item", topology="multipart_touching", part_count_min=2, part_count_max=2
    )
    assert touching_authored["ok"], touching_authored


def _check_multipart_part_list_supplies_default_component_count_contract() -> None:
    authored = {
        "runtimePlan": {
            "visualIntent": {
                "topology": "multipart_separated",
                "parts": ["orbiting head", "central grip", "trailing counterweight"],
                "arrangement": "the grip sits between two intentionally separated bodies",
            },
        },
    }
    assert SPRITE_GENERATION._authored_sprite_topology(authored, "item") == (
        "multipart_separated", 3, 3,
    )
    authored["runtimePlan"]["visualIntent"].update({"partCountMin": 2, "partCountMax": 4})
    assert SPRITE_GENERATION._authored_sprite_topology(authored, "item") == (
        "multipart_separated", 2, 4,
    )


def _check_debug_keeps_the_exact_last_prompt_sent_to_the_image_backend(tmp_path, monkeypatch) -> None:
    raw = tmp_path / "backend-result.png"
    Image.new("RGBA", (32, 32), (90, 120, 160, 255)).save(raw)
    sent_prompts: list[str] = []

    def fake_backend(_data, *, prompt, negative, asset_id, canvas, role):
        del negative, asset_id, canvas, role
        sent_prompts.append(prompt)
        return [] if len(sent_prompts) == 1 else [str(raw)]

    monkeypatch.setattr(SPRITE_GENERATION, "IMAGE_BACKEND", "sdcpp")
    monkeypatch.setattr(SPRITE_GENERATION, "SPRITE_RETRIES", 1)
    monkeypatch.setattr(SPRITE_GENERATION, "SPRITE_DIR", tmp_path)
    monkeypatch.setattr(SPRITE_GENERATION, "_backend_configuration_error", lambda: "")
    monkeypatch.setattr(SPRITE_GENERATION, "_generate_backend_variants", fake_backend)
    monkeypatch.setattr(SPRITE_GENERATION, "pick_best_sprite", lambda variants, _role, _canvas: (variants[0], 1.0))
    monkeypatch.setattr(SPRITE_GENERATION, "postprocess_sprite", lambda path, *_args, **_kwargs: path)
    monkeypatch.setattr(
        SPRITE_GENERATION,
        "validate_processed_sprite",
        lambda *_args, **_kwargs: {"ok": True, "reasons": [], "warnings": []},
    )

    data = {"debug": {"visualDirectorStatus": "visual_director_degraded"}}
    path, _url, _score, status = SPRITE_GENERATION.generate_visual_asset(
        data, "item", "authored separated item", "", "prompt_trace", 32,
    )

    assert path
    assert status.startswith("generated")
    assert len(sent_prompts) == 2
    assert sent_prompts[1] != sent_prompts[0]
    assert data["debug"]["itemFinalPrompt"] == sent_prompts[-1]

    sent_prompts.clear()
    monkeypatch.setattr(SPRITE_GENERATION, "attach_visual_soul_from_sprite", lambda *_args, **_kwargs: None)
    item_data = {
        "id": "prompt_trace_item",
        "visual": {"imagePrompt": "authored separated item", "preferredCanvasSize": 32},
        "debug": {"visualDirectorStatus": "visual_director_degraded"},
    }
    item_result = SPRITE_GENERATION.maybe_generate_sprite(item_data)
    assert item_result["visual"]["spritePath"]
    assert len(sent_prompts) == 2
    assert item_result["debug"]["itemFinalPrompt"] == sent_prompts[-1]
    assert item_result["visual"]["finalItemPrompt"] == sent_prompts[-1]


# One collected item; local checks are discovered and isolated in source order.
def test_sprite_keyer_contract_coarse_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(globals(), request, prefix="_check_")
