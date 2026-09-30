"""The shared persisted-wire admission is structural, never a substitute for image readiness."""
from __future__ import annotations

# Contract observers intentionally exercise the private request/scope/merge seams.
# pyright: reportPrivateUsage=false

import copy
from typing import Any

import pytest

from infini_local.core import vfx_manifest as vfx
from tests.test_vfx_material_contract import _data, _legacy, _path, _with_asset


def _compiled() -> dict[str, Any]:
    data = _data()
    raw = _with_asset(data)
    raw["slots"].append(_path(data)["slots"][0])
    return vfx.attach_hybrid_vfx_manifest(data, "wire_material", llm_director=lambda *_a, **_kw: raw)


def _validate(data: Any) -> dict[str, Any]:
    validator = getattr(vfx, "validate_vfx_manifest_wire", None)
    assert callable(validator), "one canonical persisted-wire VFX validator is required"
    return vfx.validate_vfx_manifest_wire(data)


def test_pending_compiled_and_stripped_ready_runtime_wire_have_distinct_caption_domains() -> None:
    data = _compiled()
    before = copy.deepcopy(data)
    assert _validate(data) == {"ok": True, "errors": []}
    asset = data["vfxManifest"]["assets"][0]
    asset.update(prompt="", negativePrompt="", spritePath="canonical_vfx.png", spriteStatus="generated", spriteTechnicalScore=0.8)
    assert _validate(data) == {"ok": True, "errors": []}
    assert before["vfxManifest"]["assets"][0]["spriteStatus"] == "pending"
    assert not vfx.validate_vfx_director_output({**_with_asset(data), "assets": [asset]}, data)["ok"]


@pytest.mark.parametrize("case,path", [
    ("null_assets", "$.vfxManifest.assets"), ("null_element", "$.vfxManifest.slots[0].element"),
    ("foreign_path", "$.vfxManifest.slots[0].path"), ("bad_canvas", "$.vfxManifest.assets[0].canvasSize"),
    ("newline_id", "$.vfxManifest.assets[0].id"),
    ("duplicate_asset", "$.vfxManifest.assets[1].id"), ("dangling", "$.vfxManifest.slots[0].element.texture.assetId"),
    ("bad_profile", "$.vfxManifest.slots[0].element.opacityProfile.middle"),
    ("empty_pending", "$.vfxManifest.assets[0].spriteStatus"), ("half_stripped", "$.vfxManifest.assets[0].negativePrompt"),
    ("stripped_no_path", "$.vfxManifest.assets[0].spritePath"), ("bad_runtime_metadata", "$.vfxManifest.assets[0].spriteTechnicalScore"),
    ("unhashable_pair", "$.vfxManifest.slots[1].entityId"), ("mixed_duplicate_slot", "$.vfxManifest.slots[2].id"),
])
def test_wire_gate_rejects_malformed_later_siblings_without_coercion_or_crash(case: str, path: str) -> None:
    data = _compiled()
    manifest = data["vfxManifest"]
    asset = manifest["assets"][0]
    if case == "null_assets":
        manifest["assets"] = None
    elif case == "null_element":
        manifest["slots"][0]["element"] = None
    elif case == "foreign_path":
        manifest["slots"][0]["path"] = copy.deepcopy(manifest["slots"][1]["path"])
    elif case == "bad_canvas":
        asset["canvasSize"] = 40
    elif case == "newline_id":
        asset["id"] += "\n"
        manifest["slots"][0]["element"]["texture"]["assetId"] = asset["id"]
    elif case == "duplicate_asset":
        manifest["assets"].append(copy.deepcopy(asset))
    elif case == "dangling":
        manifest["slots"][0]["element"]["texture"]["assetId"] = "other"
    elif case == "bad_profile":
        manifest["slots"][0]["element"]["opacityProfile"]["middle"] = 1.1
    elif case == "empty_pending":
        asset.update(prompt="", negativePrompt="")
    elif case == "half_stripped":
        asset.update(prompt="", negativePrompt="not empty", spriteStatus="generated", spritePath="vfx.png")
    elif case == "stripped_no_path":
        asset.update(prompt="", negativePrompt="", spriteStatus="generated")
    elif case == "bad_runtime_metadata":
        asset["spriteTechnicalScore"] = True
    elif case == "unhashable_pair":
        manifest["slots"][1]["entityId"] = ["bad"]
    elif case == "mixed_duplicate_slot":
        old = _legacy(data)["slots"][0]
        old.update(id=manifest["slots"][0]["id"])
        old.pop("spritePrompt")
        old.pop("spriteNegativePrompt")
        manifest["slots"].append(old)
    before = copy.deepcopy(data)
    report = _validate(data)
    assert not report["ok"]
    assert path in {row["path"] for row in report["errors"]}, report
    assert data == before


def test_shared_schema_mutation_reaches_wire_consumer_not_a_duplicate_definition(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _compiled()
    original = vfx.element_schema

    def tightened() -> dict[str, Any]:
        schema = original()
        schema["properties"]["widthPx"]["maximum"] = 4
        return schema

    monkeypatch.setattr(vfx, "element_schema", tightened)
    report = _validate(data)
    assert not report["ok"]
    assert "$.vfxManifest.slots[0].element.widthPx" in {row["path"] for row in report["errors"]}


def test_wire_gate_keeps_legacy_absence_and_does_not_require_new_defaults() -> None:
    data = _data()
    vfx.attach_hybrid_vfx_manifest(data, "legacy_wire", llm_director=lambda *_a, **_kw: _legacy(data))
    before = copy.deepcopy(data)
    assert _validate(data) == {"ok": True, "errors": []}
    assert data == before and "assets" not in data["vfxManifest"]
