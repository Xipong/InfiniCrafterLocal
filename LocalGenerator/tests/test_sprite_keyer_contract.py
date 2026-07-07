from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

# Keep this import-time config local to the test process.
TMP_CACHE = Path(tempfile.gettempdir()) / "infini_sprite_keyer_contract_cache"
if TMP_CACHE.exists():
    shutil.rmtree(TMP_CACHE)
os.environ.setdefault("INFINI_USE_LLM", "0")
os.environ.setdefault("INFINI_IMAGE_BACKEND", "off")
os.environ["INFINI_CACHE_DIR"] = str(TMP_CACHE)
os.environ["INFINI_BG_REMOVE_MODE"] = "sprite_keyer"
os.environ["INFINI_SPRITE_PROCESSING_PROFILE"] = "master_soft"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw
import server


def _rgba_pixels(image: Image.Image) -> list[tuple[int, int, int, int]]:
    raw = image.tobytes()
    return [tuple(raw[i:i + 4]) for i in range(0, len(raw), 4)]


def _check_sprite_keyer_removes_magenta_without_eating_white_shape() -> None:
    TMP_CACHE.mkdir(parents=True, exist_ok=True)

    raw_path = TMP_CACHE / "raw_magenta_white_square.png"
    img = Image.new("RGBA", (64, 64), (255, 0, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle((16, 16, 47, 47), fill=(250, 250, 250, 255))
    img.save(raw_path)

    out = server.postprocess_sprite(str(raw_path), "sprite_keyer_contract", target_size=32, role="item")
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


def _check_sprite_keyer_samples_uniform_shifted_zimage_pink_background() -> None:
    TMP_CACHE.mkdir(parents=True, exist_ok=True)

    raw_path = TMP_CACHE / "raw_shifted_pink_coin_stack.png"
    img = Image.new("RGBA", (64, 64), (202, 6, 140, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse((20, 16, 45, 40), fill=(230, 230, 220, 255), outline=(50, 50, 50, 255), width=2)
    img.save(raw_path)

    out = server.postprocess_sprite(str(raw_path), "sprite_keyer_shifted_pink", target_size=32, role="item")
    assert out is not None
    result = Image.open(out).convert("RGBA")
    assert result.getpixel((0, 0))[3] == 0
    validation = server.validate_processed_sprite(str(out), "item")
    assert validation["ok"], validation
    visible = [px for px in _rgba_pixels(result) if px[3] > 0]
    pink_visible = sum(1 for r, g, b, a in visible if r > 150 and b > 90 and g < 80)
    assert pink_visible == 0


if __name__ == "__main__":
    test_sprite_keyer_removes_magenta_without_eating_white_shape()
    print("OK sprite keyer contract")


def _check_validation_rejects_opaque_inner_poster_card_as_fatal_background_failure() -> None:
    TMP_CACHE.mkdir(parents=True, exist_ok=True)
    path = TMP_CACHE / "bad_inner_white_card.png"
    img = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle((2, 2, 45, 45), fill=(250, 250, 250, 255))
    draw.line((10, 38, 38, 10), fill=(70, 35, 15, 255), width=4)
    img.save(path)

    validation = server.validate_processed_sprite(str(path), "item")
    assert not validation["ok"], validation
    assert any(str(r).startswith("very_dense_opaque_area") for r in validation["reasons"]), validation
    assert server.sprite_validation_fatal(validation), validation


def _check_sprite_keyer_removes_enclosed_sampled_magenta_holes() -> None:
    TMP_CACHE.mkdir(parents=True, exist_ok=True)
    raw_path = TMP_CACHE / "raw_enclosed_magenta_hole.png"
    img = Image.new("RGBA", (128, 128), (229, 84, 210, 255))
    draw = ImageDraw.Draw(img)
    # Simulate a curved bow/string enclosing a key-colored interior pocket.
    draw.arc((28, 14, 104, 114), 250, 105, fill=(40, 22, 14, 255), width=8)
    draw.line((40, 96, 92, 28), fill=(55, 20, 12, 255), width=4)
    draw.line((48, 84, 86, 36), fill=(180, 92, 35, 255), width=5)
    img.save(raw_path)
    out = server.postprocess_sprite(str(raw_path), "sprite_keyer_enclosed_hole", target_size=48, role="item")
    assert out is not None
    validation = server.validate_processed_sprite(str(out), "item")
    assert validation["ok"], validation
    result = Image.open(out).convert("RGBA")
    visible = [px for px in _rgba_pixels(result) if px[3] > 0]
    key_visible = sum(1 for r, g, b, a in visible if r > 170 and b > 150 and g < 110)
    assert key_visible == 0


def _check_sprite_keyer_removes_inner_white_poster_card_when_foreground_exists() -> None:
    TMP_CACHE.mkdir(parents=True, exist_ok=True)
    raw_path = TMP_CACHE / "raw_inner_white_poster_card.png"
    img = Image.new("RGBA", (128, 128), (229, 84, 210, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle((18, 18, 110, 110), fill=(250, 250, 250, 255))
    draw.line((36, 90, 92, 35), fill=(50, 25, 12, 255), width=9)
    draw.line((40, 86, 88, 39), fill=(180, 90, 34, 255), width=4)
    img.save(raw_path)
    out = server.postprocess_sprite(str(raw_path), "sprite_keyer_inner_card", target_size=48, role="item")
    assert out is not None
    validation = server.validate_processed_sprite(str(out), "item")
    assert validation["ok"], validation
    result = Image.open(out).convert("RGBA")
    stats = server.alpha_stats(result)
    assert stats["transparentPct"] > 0.45, stats
    visible = [px for px in _rgba_pixels(result) if px[3] > 0]
    white_visible = sum(1 for r, g, b, a in visible if r > 220 and g > 220 and b > 220)
    assert white_visible < 20

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
    '_check_sprite_keyer_removes_inner_white_poster_card_when_foreground_exists'
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
