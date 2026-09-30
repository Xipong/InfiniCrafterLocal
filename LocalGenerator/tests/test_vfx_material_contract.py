"""Offline authored examples exercise the material ABI, not model/art quality."""
from __future__ import annotations

# Contract observers intentionally exercise the private request/scope/merge seams.
# pyright: reportPrivateUsage=false

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.core.runtime_authoring import compile_runtime_program, strict_schema_errors
from infini_local.qa.capability_witnesses import build_capability_witness
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def _data(capability: str = "") -> dict[str, Any]:
    return compile_runtime_program(build_capability_witness(capability) if capability else build_runtime_fixture("workbench_blade"))


def _legacy(data: dict[str, Any]) -> dict[str, Any]:
    item_id = data["runtimeProgram"]["itemEntityId"]
    return {
        "schema": vfx.VFX_DIRECTOR_SCHEMA, "effectMagnitude": 0.5, "visualBudgetClass": "normal",
        "motif": {"element": "metal", "shapeLanguage": "sparks", "motionLanguage": "short wake", "paletteRole": "accent", "rhythm": 1.0, "chaos": 0.2},
        "slots": [{
            "id": "old_slot", "entityId": item_id, "event": "on_use", "rendererKind": "impactRing",
            "backend": "Realtime", "textureRole": "none", "particleRole": "none", "anchor": "self",
            "channel": "impactShape", "lane": "primary", "emissionMode": "burst", "blend": "alpha",
            "layer": "BeforeProjectiles", "particleSystemId": "none", "scale": 1.0,
            "density": 0.4, "duration": 20, "alpha": 0.8, "spread": 0.1, "jitter": 0.1,
            "fadeIn": 0.1, "fadeOut": 0.4, "budgetWeight": 1.0, "signatureWeight": 0.5,
            "visualCost": 0.5, "startTick": 0, "repeatEvery": 0, "spritePrompt": "", "spriteNegativePrompt": "",
        }],
    }


def _profile(start: Any = 1.0, middle: Any = 1.0, end: Any = 0.0, curve: str = "linear") -> dict[str, Any]:
    return {"start": start, "middle": middle, "end": end, "curve": curve}


def _sprite(data: dict[str, Any]) -> dict[str, Any]:
    raw = _legacy(data)
    raw["slots"][0].update({
        "id": "ingredient_element", "rendererKind": "spriteElement", "backend": "Sprite", "emissionMode": "none",
        "scale": 1.0, "density": 0.0, "spread": 0.0, "jitter": 0.0, "fadeIn": 0.0, "fadeOut": 0.0,
        "signatureWeight": 0.0, "visualCost": 0.0,
        "element": {
            "texture": {"source": "item", "assetId": ""}, "attachment": "world", "count": 2,
            "offsetForwardPx": 8.0, "offsetSidePx": -3.0, "speedMinPxPerTick": 1.0, "speedMaxPxPerTick": 2.0,
            "spreadRadians": 0.75, "inheritVelocity": 0.2, "drag": 0.95,
            "accelerationXPxPerTickSquared": 0.0, "accelerationYPxPerTickSquared": 0.05,
            "rotationRadians": 0.0, "rotationSpeedRadiansPerTick": -0.1, "widthPx": 12.0, "heightPx": 5.0,
            "widthProfile": _profile(0.0, 1.0, 2.0, "easeIn"), "heightProfile": _profile(2.0, 1.0, 0.0, "easeOut"),
            "opacityProfile": _profile(0.0, 0.8, 0.0, "smoothStep"), "colorProfile": _profile("white", "effect", "tan"),
        },
    })
    return raw


def _sent(data: dict[str, Any], repair: bool) -> dict[str, Any]:
    sent: list[dict[str, Any]] = []

    def capture(_system: str, user: dict[str, Any], *_args: Any, **kwargs: Any) -> dict[str, Any]:
        sent.append(json.loads(kwargs["messages"][1]["content"]) if repair else json.loads(json.dumps(user)))
        return {}

    packet = vfx._prompt_packet(data, None, None)
    if repair:
        vfx._request(capture, packet, repair_errors=[{"path": "$.slots[0].alpha", "message": "invalid"}],
                     previous={"slots": []}, repair_scope={"fieldPermissions": {"slots": []}})
    else:
        vfx._request(capture, packet)
    return sent[0]


def test_handwritten_legacy_manifest_preserves_pre_extension_bytes() -> None:
    data = _data()
    raw = _legacy(data)
    expected = (Path(__file__).parent / "fixtures" / "vfx_material_legacy_manifest.json").read_text(encoding="utf-8")
    result = vfx.attach_hybrid_vfx_manifest(data, "legacy_material_abi", llm_director=lambda *_a, **_kw: raw)
    assert json.dumps(result["vfxManifest"], ensure_ascii=False, separators=(",", ":")) == expected
    assert "assets" not in result["vfxManifest"]


@pytest.mark.parametrize("repair", [False, True])
def test_sprite_payload_survives_transported_schema_validation_and_compilation(repair: bool) -> None:
    data = _data()
    raw = _sprite(data)
    packet = _sent(data, repair)
    schema = packet["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]
    assert not strict_schema_errors(raw["slots"][0], schema)
    before = copy.deepcopy(data["runtimeProgram"])
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"] == raw
    result = vfx.attach_hybrid_vfx_manifest(data, "material_element", llm_director=lambda *_a, **_kw: copy.deepcopy(raw))
    assert result["vfxManifest"]["slots"][0]["element"] == raw["slots"][0]["element"]
    raw["slots"][0]["element"]["widthProfile"]["middle"] = 4
    assert result["vfxManifest"]["slots"][0]["element"]["widthProfile"]["middle"] == 1
    assert data["runtimeProgram"] == before


def _asset(asset_id: str = "Glow_A-1", layout: str = "cutout") -> dict[str, Any]:
    return {"id": asset_id, "prompt": "one isolated luminous ingredient, no text/UI/atlas", "negativePrompt": "", "canvasSize": 32, "layout": layout}


def _with_asset(data: dict[str, Any]) -> dict[str, Any]:
    raw = _sprite(data)
    raw["assets"] = [_asset()]
    raw["slots"][0]["element"]["texture"] = {"source": "asset", "assetId": "Glow_A-1"}
    return raw


def test_exact_asset_request_shared_reuse_compiles_once_with_pending_metadata() -> None:
    data = _data()
    raw = _with_asset(data)
    second = copy.deepcopy(raw["slots"][0])
    second.update(id="shared_ingredient", event="on_hit")
    raw["slots"].append(second)
    before = copy.deepcopy(raw)
    packet = _sent(data, False)
    assert not strict_schema_errors(raw, packet["outputSchema"])
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"] == before
    final = vfx.attach_hybrid_vfx_manifest(data, "shared_material", llm_director=lambda *_a, **_kw: raw)
    assert final["vfxManifest"]["assets"] == [{**_asset(), "spritePath": "", "spriteUrl": "", "spriteStatus": "pending", "spriteTechnicalScore": 0.0}]
    assert [slot["element"]["texture"]["assetId"] for slot in final["vfxManifest"]["slots"]] == ["Glow_A-1", "Glow_A-1"]
    assert raw == before
    assert data["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 0


@pytest.mark.parametrize("case,path", [
    ("null", "$.assets"), ("duplicate", "$.assets[1].id"), ("unused", "$.assets[1].id"),
    ("dangling", "$.slots[0].element.texture.assetId"), ("invalid_id", "$.assets[0].id"),
    ("newline_id", "$.assets[0].id"),
    ("unhashable_id", "$.assets[0].id"), ("canvas_bool", "$.assets[0].canvasSize"),
    ("bad_canvas", "$.assets[0].canvasSize"), ("blank_prompt", "$.assets[0].prompt"),
    ("authored_path", "$.assets[0].spritePath"), ("too_many", "$.assets"),
])
def test_asset_requests_reject_invalid_exact_identity_and_unrelated_artwork(case: str, path: str) -> None:
    data = _data()
    raw = _with_asset(data)
    if case == "null":
        raw["assets"] = None
    elif case == "duplicate":
        raw["assets"].append(_asset())
    elif case == "unused":
        raw["assets"].append(_asset("unrelated"))
    elif case == "dangling":
        raw["slots"][0]["element"]["texture"]["assetId"] = "glow_a-1"
    elif case == "invalid_id":
        raw["assets"][0]["id"] = "../Glow_A-1"
    elif case == "newline_id":
        raw["assets"][0]["id"] = "Glow_A-1\n"
    elif case == "unhashable_id":
        raw["assets"][0]["id"] = ["Glow_A-1"]
    elif case == "canvas_bool":
        raw["assets"][0]["canvasSize"] = True
    elif case == "bad_canvas":
        raw["assets"][0]["canvasSize"] = 40
    elif case == "blank_prompt":
        raw["assets"][0]["prompt"] = "   "
    elif case == "authored_path":
        raw["assets"][0]["spritePath"] = "filesystem.png"
    elif case == "too_many":
        raw["assets"] = [_asset(f"asset_{index}") for index in range(5)]
    before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert path in {row["path"] for row in report["errors"]}, report["errors"]
    if case == "newline_id":
        assets = raw["assets"]
        assert isinstance(assets, list)
        for repair in (False, True):
            props = _sent(data, repair)["outputSchema"]["properties"]
            schema = props["assetsUpsert" if repair else "assets"]["items"]
            assert "$.id" in {row["path"] for row in strict_schema_errors(assets[0], schema)}
    assert raw == before


@pytest.mark.parametrize("case,relative", [
    ("reverse_speed", "element.speedMaxPxPerTick"), ("event_repeat", "repeatEvery"),
    ("periodic_zero", "repeatEvery"), ("item_periodic_delay", "startTick"),
    ("terminal_source", "element.attachment"), ("foreign_element", "element"),
    ("light_route", "channel"), ("null_element", "element"), ("unknown_payload", "element.code"),
    ("bool_count", "element.count"), ("nan_width", "element.widthPx"),
    ("texture_wrong_id", "element.texture.assetId"), ("numeric_curve_null", "element.widthProfile.middle"),
    ("color_case", "element.colorProfile.middle"),
])
def test_sprite_cross_field_and_strict_payload_constraints(case: str, relative: str) -> None:
    data = _data()
    raw = _sprite(data)
    slot = raw["slots"][0]
    if case == "reverse_speed":
        slot["element"]["speedMaxPxPerTick"] = 0.5
    elif case == "event_repeat":
        slot["repeatEvery"] = 1
    elif case == "periodic_zero":
        slot["event"] = "periodic"
    elif case == "item_periodic_delay":
        slot.update(event="periodic", repeatEvery=5, startTick=2)
    elif case == "terminal_source":
        projectile = next(row for row in data["runtimeProgram"]["entities"] if row["kind"] != "item_body")
        slot.update(entityId=projectile["id"], event="on_kill")
        slot["element"]["attachment"] = "source"
    elif case == "foreign_element":
        slot["rendererKind"] = "impactRing"
    elif case == "light_route":
        slot["channel"] = "light"
    elif case == "null_element":
        slot["element"] = None
    elif case == "unknown_payload":
        slot["element"]["code"] = "shader"
    elif case == "bool_count":
        slot["element"]["count"] = True
    elif case == "nan_width":
        slot["element"]["widthPx"] = float("nan")
    elif case == "texture_wrong_id":
        slot["element"]["texture"]["assetId"] = "forbidden_with_item_source"
    elif case == "numeric_curve_null":
        slot["element"]["widthProfile"]["middle"] = None
    elif case == "color_case":
        slot["element"]["colorProfile"]["middle"] = "WHITE"
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"], case
    assert "$.slots[0]." + relative in {row["path"] for row in report["errors"]}
    if case != "reverse_speed":  # JSON Schema cannot compare two sibling numbers.
        for repair in (False, True):
            packet = _sent(data, repair)
            schema = packet["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]
            assert strict_schema_errors(slot, schema), case


def test_sprite_explicit_zero_and_source_delay_preserve_all_authored_values() -> None:
    data = _data()
    raw = _sprite(data)
    raw["slots"][0].update(alpha=0.0, startTick=7)
    element = raw["slots"][0]["element"]
    element.update(attachment="source", count=0, widthPx=0.0, heightPx=0.0, inheritVelocity=0.0, drag=0.0)
    for field in ("widthProfile", "heightProfile", "opacityProfile"):
        element[field] = _profile(0.0, 0.0, 0.0)
    assert vfx.validate_vfx_director_output(raw, data)["ok"]
    final = vfx.attach_hybrid_vfx_manifest(data, "zero_material", llm_director=lambda *_a, **_kw: raw)
    assert final["vfxManifest"]["slots"][0]["element"] == element


def _path(data: dict[str, Any], source: str = "anchorHistory") -> dict[str, Any]:
    raw = _sprite(data)
    slot = raw["slots"][0]
    slot.pop("element")
    projectile = next(row for row in data["runtimeProgram"]["entities"] if row["kind"] != "item_body")
    slot.update(id="connected_path", entityId=projectile["id"], event="periodic", rendererKind="texturedPath", backend="Primitive", duration=3)
    slot["path"] = {
        "texture": {"source": "item", "assetId": ""}, "source": source,
        "historyTicks": 12 if source == "anchorHistory" else 0, "minDistancePx": 2.0 if source == "anchorHistory" else 0.0,
        "maxSegmentLengthPx": 64.0, "widthPx": 8.0, "widthProfile": _profile(0.0, 2.0, 0.0),
        "opacityProfile": _profile(0.0, 1.0, 0.0), "colorProfile": _profile("gold", "effect", "white"),
        "profileDomain": "age" if source == "anchorHistory" else "length", "uvMode": "repeat",
        "repeatLengthPx": 24.0, "scrollPxPerTick": -2.0,
    }
    return raw


@pytest.mark.parametrize("source,capability", [("anchorHistory", ""), ("beam", "channel_beam"), ("whip", "move_whip_lash")])
@pytest.mark.parametrize("repair", [False, True])
def test_path_modes_reach_transport_compile_and_exact_accepted_geometry(source: str, capability: str, repair: bool) -> None:
    data = _data(capability)
    raw = _path(data, source)
    before = copy.deepcopy(data["runtimeProgram"])
    packet = _sent(data, repair)
    schema = packet["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]
    assert not strict_schema_errors(raw["slots"][0], schema)
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"] == raw
    final = vfx.attach_hybrid_vfx_manifest(data, "literal_path", llm_director=lambda *_a, **_kw: raw)
    assert final["vfxManifest"]["slots"][0]["path"] == raw["slots"][0]["path"]
    assert data["runtimeProgram"] == before
    surface = packet["runtimeSurfaceReadOnly"] if repair else packet["runtimeSurface"]
    row = next(row for row in surface["texturedPathSources"] if row["entityId"] == raw["slots"][0]["entityId"])
    assert source in row["sources"]


@pytest.mark.parametrize("case,relative", [
    ("no_beam", "path.source"), ("current_history", "path.historyTicks"), ("current_distance", "path.minDistancePx"),
    ("current_age", "path.profileDomain"), ("stretch_length", "path.repeatLengthPx"), ("stretch_scroll", "path.scrollPxPerTick"),
    ("short_history", "path.historyTicks"), ("event", "event"), ("item", "entityId"),
    ("repeat", "repeatEvery"), ("duration", "duration"), ("foreign_path", "path"), ("null_path", "path"),
])
def test_path_conditions_visible_in_both_sent_schemas(case: str, relative: str) -> None:
    data = _data("channel_beam" if case.startswith("current") else "")
    raw = _path(data, "beam" if case.startswith("current") else "anchorHistory")
    slot = raw["slots"][0]
    if case == "no_beam":
        slot["path"].update(source="beam", historyTicks=0, minDistancePx=0.0, profileDomain="length")
    elif case == "current_history":
        slot["path"]["historyTicks"] = 12
    elif case == "current_distance":
        slot["path"]["minDistancePx"] = 1.0
    elif case == "current_age":
        slot["path"]["profileDomain"] = "age"
    elif case == "stretch_length":
        slot["path"].update(uvMode="stretch", scrollPxPerTick=0.0)
    elif case == "stretch_scroll":
        slot["path"].update(uvMode="stretch", repeatLengthPx=1.0)
    elif case == "short_history":
        slot["path"]["historyTicks"] = 1
    elif case == "event":
        slot["event"] = "on_hit"
    elif case == "item":
        slot["entityId"] = data["runtimeProgram"]["itemEntityId"]
    elif case == "repeat":
        slot["repeatEvery"] = 3
    elif case == "duration":
        slot["duration"] = 20
    elif case == "foreign_path":
        slot["rendererKind"] = "spriteElement"
        slot["element"] = _sprite(data)["slots"][0]["element"]
        slot["backend"] = "Sprite"
    elif case == "null_path":
        slot["path"] = None
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert "$.slots[0]." + relative in {row["path"] for row in report["errors"]}, report["errors"]
    for repair in (False, True):
        packet = _sent(data, repair)
        schema = packet["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]
        assert strict_schema_errors(slot, schema), case


def test_history_path_may_select_length_profile_without_changing_accepted_geometry() -> None:
    data = _data()
    raw = _path(data)
    raw["slots"][0]["path"]["profileDomain"] = "length"
    before = copy.deepcopy(data["runtimeProgram"])
    for repair in (False, True):
        schema = _sent(data, repair)["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]
        assert not strict_schema_errors(raw["slots"][0], schema)
    assert vfx.validate_vfx_director_output(raw, data)["ok"]
    final = vfx.attach_hybrid_vfx_manifest(data, "history_length", llm_director=lambda *_a, **_kw: raw)
    assert final["vfxManifest"]["slots"][0]["path"] == raw["slots"][0]["path"]
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert data["runtimeProgram"] == before
