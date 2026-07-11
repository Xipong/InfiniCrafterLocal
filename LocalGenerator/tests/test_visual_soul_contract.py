from __future__ import annotations

import sys
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


def _check_visual_soul_is_extracted_from_finished_png(tmp_path: Path) -> None:
    path = tmp_path / "soul.png"
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    for y in range(8, 24):
        for x in range(8, 24):
            img.putpixel((x, y), (255, 72, 32, 255))
    img.putpixel((16, 16), (255, 240, 80, 255))
    img.save(path)

    data = {"id": "soul_test", "visual": {"palette": ["tin"]}, "debug": {}}
    VISUAL.attach_visual_soul_from_sprite(data, str(path), validation={"ok": True}, score=0.77)
    visual = data["visual"]

    assert visual["visualSoulSignature"]
    assert visual["visualSoulArchetype"] in {"ember", "solar", "crimson"}
    assert visual["accentColorHex"].startswith("#")
    assert visual["dominantColorHex"].startswith("#")
    assert 0.0 < visual["visualSoulGlow"] <= 1.0
    assert 0.0 <= visual["visualSoulPulse"] <= 1.0
    assert "Visual soul:" in visual["visualSoulTooltip"]
    assert "visualSoul" in data["debug"]


def _check_csharp_visual_soul_runtime_contract_exists() -> None:
    model = read_text_with_partial_bundles(MODEL)
    item = ITEM.read_text(encoding="utf-8")
    held = HELD.read_text(encoding="utf-8")
    player = read_text_with_partial_bundles(PLAYER)

    assert "public string VisualSoulSignature" in model
    assert "public string AccentColorHex" in model
    assert "VisualSoulGlow = ClampFloat" in model
    assert "InfiniVisualSoul" in item
    assert "VisualSoulAuraEligible" in item
    assert "GenerationDepth >= 6" in item or "depth >= 6" in item
    assert "depth < 3" in item
    assert "post_golem" in item and "lunar" in item and "endgame" in item
    assert "DrawSoulGlow" in item
    assert "VisualSoulColor" in item
    assert "SpawnSoulDust" in item
    assert "GeneratedItem.AddSoulDrawData" in held
    assert "RunLocalCraftReveal" in player
    assert "VisualSoulAuraEligible(data)" in player
    assert "✦ Discovered:" in player

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_visual_soul_is_extracted_from_finished_png',
    '_check_csharp_visual_soul_runtime_contract_exists'
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
