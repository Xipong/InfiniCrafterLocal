from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "agent_reports" / "run_full_sprite_20_after_cleanup.py"


def _load_harness():
    spec = importlib.util.spec_from_file_location("run_full_sprite_20_after_cleanup", HARNESS)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeRgbaImage:
    def __init__(self) -> None:
        self.size = (1, 1)
        self.flattened_calls = 0
        self.getdata_calls = 0

    def convert(self, _mode: str):
        return self

    def get_flattened_data(self):
        self.flattened_calls += 1
        return [(1, 2, 3, 255)]

    def getdata(self):
        self.getdata_calls += 1
        raise AssertionError("deprecated getdata() should not be used when get_flattened_data() exists")


def test_full_sprite_harness_prefers_pillow_flattened_data(monkeypatch, tmp_path):
    harness = _load_harness()
    from PIL import Image

    fake = _FakeRgbaImage()
    png = tmp_path / "sprite.png"
    png.write_bytes(b"not a real png; Image.open is monkeypatched")
    monkeypatch.setattr(Image, "open", lambda _path: fake)

    metrics = harness.sprite_metrics([{
        "n": 1,
        "result": "Harness Polish Blade",
        "spritePath": str(png),
        "spriteRawPath": str(png),
    }])

    assert metrics[0]["finalOpaquePixels"] == 1
    assert metrics[0]["rawOpaquePixels"] == 1
    assert fake.flattened_calls == 2
    assert fake.getdata_calls == 0
