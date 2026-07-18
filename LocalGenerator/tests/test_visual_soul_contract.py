from __future__ import annotations

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image
from infini_local.pipelines import visual_soul as VISUAL

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.cs"
ITEM = ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Items" / "GeneratedItem.cs"
HELD = ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Players" / "GeneratedHeldItemDrawLayer.cs"
PLAYER = ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Players" / "InfiniCraftPlayer.cs"


def _check_finished_png_metrics_are_debug_only(tmp_path: Path) -> None:
    path = tmp_path / "soul.png"
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    for y in range(8, 24):
        for x in range(8, 24):
            img.putpixel((x, y), (255, 72, 32, 255))
    img.putpixel((16, 16), (255, 240, 80, 255))
    img.save(path)

    data = {"id": "soul_test", "visual": {"palette": ["tin"]}, "debug": {}}
    VISUAL.attach_visual_soul_from_sprite(data, str(path), validation={"ok": True}, score=0.77)
    assert data["visual"] == {"palette": ["tin"]}
    metrics = json.loads(data["debug"]["spritePixelMetrics"])
    assert metrics["spriteSignature"]
    assert metrics["accentColorHex"].startswith("#")
    assert metrics["dominantColorHex"].startswith("#")
    assert 0.0 < metrics["coverage"] <= 1.0
    assert 0.0 <= metrics["edgeDensity"] <= 1.0
    assert "visualSoulGlow" not in metrics
    assert "visualSoulPulse" not in metrics


def _check_csharp_does_not_execute_png_derived_presentation() -> None:
    model = read_text_with_partial_bundles(MODEL)
    item = ITEM.read_text(encoding="utf-8")
    held = HELD.read_text(encoding="utf-8")
    player = read_text_with_partial_bundles(PLAYER)

    assert "public string VisualSoulSignature" in model  # legacy wire stays readable
    for forbidden in (
        "InfiniVisualSoul", "VisualSoulAuraEligible", "DrawSoulGlow",
        "VisualSoulColor", "SpawnSoulDust", "AddSoulDrawData",
    ):
        assert forbidden not in item
    assert "GeneratedItem.AddSoulDrawData" not in held
    assert "RunLocalCraftReveal" in player
    assert "VisualSoulAuraEligible(data)" not in player
    assert "✦ Discovered:" not in player

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_finished_png_metrics_are_debug_only',
    '_check_csharp_does_not_execute_png_derived_presentation'
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


def test_visual_soul_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
