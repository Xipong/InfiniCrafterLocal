from __future__ import annotations

import json
from pathlib import Path

import pytest

from infini_local.pipelines import visual_delivery_gate
from infini_local.pipelines import pipeline_visual_config as VISUAL_CONFIG

VISUAL = visual_delivery_gate


def _check_visual_delivery_gate_blocks_missing_required_item_sprite(monkeypatch):
    monkeypatch.setattr(VISUAL, "VISUAL_REQUIRE_ITEM_SPRITE", True)
    monkeypatch.setattr(VISUAL, "VISUAL_REQUIRE_ZIMAGE_BACKEND", False)
    data = {"id": "missing_sprite", "visual": {"spriteStatus": "failed", "spritePath": ""}, "attack": {}, "debug": {}}

    with pytest.raises(VISUAL.VisualDeliveryBlocked):
        VISUAL.assert_visual_delivery_ready(data)

    report = json.loads(data["debug"]["visualDeliveryReport"])
    assert report["ok"] is False
    assert report["problems"][0]["code"] == "required_item_sprite_missing"


def _check_visual_delivery_gate_accepts_existing_generated_item_sprite(monkeypatch, tmp_path):
    monkeypatch.setattr(VISUAL, "VISUAL_REQUIRE_ITEM_SPRITE", True)
    monkeypatch.setattr(VISUAL, "VISUAL_REQUIRE_ZIMAGE_BACKEND", False)
    sprite = tmp_path / "ok.png"
    sprite.write_bytes(b"\x89PNG\r\n\x1a\n")
    data = {"id": "ok_sprite", "visual": {"spriteStatus": "generated", "spritePath": str(sprite), "spriteTechnicalScore": 0.9, "semanticReviewStatus": "not_performed"}, "attack": {}, "debug": {}}

    out = VISUAL.assert_visual_delivery_ready(data)

    assert out is data
    report = json.loads(data["debug"]["visualDeliveryReport"])
    assert report["ok"] is True
    assert report["slots"][0]["usable"] is True
    assert report["slots"][0]["technicalScore"] == 0.9
    assert "score" not in report["slots"][0]
    assert report["semanticReviewStatus"] == "not_performed"


def _check_visual_delivery_gate_accepts_existing_warn_invalid_item_sprite(monkeypatch, tmp_path):
    monkeypatch.setattr(VISUAL, "VISUAL_REQUIRE_ITEM_SPRITE", True)
    monkeypatch.setattr(VISUAL, "VISUAL_REQUIRE_ZIMAGE_BACKEND", False)
    sprite = tmp_path / "warn_invalid.png"
    sprite.write_bytes(b"\x89PNG\r\n\x1a\n")
    data = {"id": "warn_invalid_sprite", "visual": {"spriteStatus": "generated_warn_invalid", "spritePath": str(sprite), "visualJudgeScore": 0.0}, "attack": {}, "debug": {}}

    out = VISUAL.assert_visual_delivery_ready(data)

    assert out is data
    report = json.loads(data["debug"]["visualDeliveryReport"])
    assert report["ok"] is True
    assert report["slots"][0]["usable"] is True
    assert any(w["code"] == "item_sprite_generated_warn_invalid" for w in report["warnings"])


def _check_visual_delivery_gate_can_require_zimage_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(VISUAL, "VISUAL_REQUIRE_ITEM_SPRITE", True)
    monkeypatch.setattr(VISUAL, "VISUAL_REQUIRE_ZIMAGE_BACKEND", True)
    monkeypatch.setattr(VISUAL_CONFIG, "IMAGE_BACKEND", "procedural")
    sprite = tmp_path / "ok.png"
    sprite.write_bytes(b"\x89PNG\r\n\x1a\n")
    data = {"id": "wrong_backend", "visual": {"spriteStatus": "generated", "spritePath": str(sprite)}, "attack": {}, "debug": {}}

    with pytest.raises(VISUAL.VisualDeliveryBlocked):
        VISUAL.assert_visual_delivery_ready(data)

    report = json.loads(data["debug"]["visualDeliveryReport"])
    assert any(p["code"] == "zimage_required_but_inactive" for p in report["problems"])

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_visual_delivery_gate_blocks_missing_required_item_sprite',
    '_check_visual_delivery_gate_accepts_existing_generated_item_sprite',
    '_check_visual_delivery_gate_accepts_existing_warn_invalid_item_sprite',
    '_check_visual_delivery_gate_can_require_zimage_backend'
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


def test_visual_delivery_gate_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
