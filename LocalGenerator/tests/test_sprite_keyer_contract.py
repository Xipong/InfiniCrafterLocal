from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw
from infini_local.pipelines import sprite_postprocess as SPRITE_POSTPROCESS
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


# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_sprite_keyer_removes_magenta_without_eating_white_shape',
    '_check_sprite_keyer_samples_uniform_shifted_zimage_pink_background',
    '_check_validation_rejects_opaque_inner_poster_card_as_fatal_background_failure',
    '_check_sprite_keyer_removes_enclosed_sampled_magenta_holes',
    '_check_sprite_keyer_removes_inner_white_poster_card_when_foreground_exists',
    '_check_sprite_keyer_removes_disconnected_nested_pink_frame',
    '_check_technical_score_describes_final_validation_not_raw_candidate',
    '_check_postprocess_failure_preserves_the_original_asset_path',
    '_check_nearest_downscale_is_not_a_supported_runtime_or_gui_path'
    ]:
        _fn = globals()[_name]
        _sig = _inspect.signature(_fn)
        _kwargs = {}
        if "tmp_path" in _sig.parameters:
            _case_dir = tmp_path / _name
            _case_dir.mkdir(parents=True, exist_ok=True)
            _kwargs["tmp_path"] = _case_dir
        if "monkeypatch" in _sig.parameters:
            with _pytest.MonkeyPatch.context() as _mp:
                _kwargs["monkeypatch"] = _mp
                _fn(**_kwargs)
        else:
            _fn(**_kwargs)


def test_sprite_keyer_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
