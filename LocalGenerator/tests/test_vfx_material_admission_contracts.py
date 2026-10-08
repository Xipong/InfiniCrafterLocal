"""Offline canonical vfx material admission contracts; no live services."""
from __future__ import annotations

import json
from pathlib import Path
from tests.vfx_image_fixtures import apply_edits

import copy
from typing import Any
import pytest
from infini_local.core import vfx_manifest as vfx
from infini_local.core.runtime_authoring import strict_schema_errors
from jsonschema import Draft202012Validator
from tests.test_repair_vfx_contract import _patch
from tests.test_low_level_three_stage_pipeline import _accepted_visual_data, _vfx_output
from tests.vfx_material_fixtures import _asset, _data, _legacy, _path, _sent, _sprite, _with_asset


@pytest.mark.parametrize("repair", [False, True])
@pytest.mark.parametrize("asset_id,valid", [
    ("leaf", True), ("Glow", True), ("glow", True), ("x" * 48, True),
    ("leaf\n", False), ("leaf\r\n", False), ("leaf\u2028", False),
    ("leaf\u2029", False), ("", False), ("x" * 49, False),
    ("../leaf", False), (" leaf", False),
])
def test_standard_schema_and_local_gate_agree_on_exact_asset_ids(repair: bool, asset_id: str, valid: bool) -> None:
    packet = _sent(_data(), repair)
    schema = packet["outputSchema"]
    Draft202012Validator.check_schema(schema)
    asset_schema = schema["properties"]["assetsUpsert" if repair else "assets"]["items"]
    row = _asset(asset_id)
    assert Draft202012Validator(asset_schema).is_valid(row) is valid
    assert (not strict_schema_errors(row, asset_schema)) is valid
    slots = schema["properties"]["slotsUpsert" if repair else "slots"]["items"]
    selector_schema = slots["properties"]["element"]["properties"]["texture"]
    selector = {"source": "asset", "assetId": asset_id}
    assert Draft202012Validator(selector_schema).is_valid(selector) is valid
    assert (not strict_schema_errors(selector, selector_schema)) is valid
    if repair:
        # Read the actual serialized Repair packet, not a rebuilt helper schema.
        deletions = schema["properties"]["assetIdsDelete"]
        assert Draft202012Validator(deletions).is_valid([asset_id]) is valid
        assert (not strict_schema_errors([asset_id], deletions)) is valid
        patch = {"schema": schema["properties"]["schema"]["const"],
                 "note": "delete exact diagnosed asset id", "assetIdsDelete": [asset_id]}
        assert Draft202012Validator(schema).is_valid(patch) is valid
        assert (not strict_schema_errors(patch, schema)) is valid


def _screen_shake(data: dict[str, Any]) -> dict[str, Any]:
    raw = _legacy(data)
    slot = raw["slots"][0]
    from infini_local.core.vfx_material_contract import NEUTRAL_FIELDS
    slot.update(NEUTRAL_FIELDS)
    slot.update(id="local_camera_cue", rendererKind="screenShakeCue", backend="Realtime",
                channel="screenShake", lane="cue", duration=3, alpha=1, startTick=0, repeatEvery=0)
    slot["screenShake"] = {
        "strengthPx": 3.0, "angularVarianceRadians": 1.0, "directionRadians": 0.5,
        "dissipationPxPerFrame": 0.25, "taperStartDistancePx": 400.0, "taperEndDistancePx": 1200.0,
    }
    return raw


def test_luminance_cue_reaches_director_compiler_wire_without_changing_gameplay() -> None:
    data = _data()
    raw = _screen_shake(data)
    frozen = copy.deepcopy(data["runtimeProgram"])
    admission = vfx.validate_vfx_director_output(raw, data)
    assert admission["ok"], admission["errors"]
    result = vfx.attach_hybrid_vfx_manifest(data, "library_cue", llm_director=lambda *_a, **_kw: raw)
    slot = result["vfxManifest"]["slots"][0]
    assert slot["screenShake"] == raw["slots"][0]["screenShake"]
    assert slot["rendererKind"] == "screenShakeCue"
    assert vfx.validate_vfx_manifest_wire(result) == {"ok": True, "errors": []}
    assert result["runtimeProgram"] == frozen
    assert "assets" not in result["vfxManifest"]
    assert "element" not in slot and "path" not in slot


@pytest.mark.parametrize("edits,valid", [
    pytest.param({"screenShake.strengthPx": 0}, True, id="explicit-zero"),
    pytest.param({"screenShake.taperEndDistancePx": 400}, False, id="equal-taper"),
    pytest.param({"screenShake.taperEndDistancePx": 300}, False, id="inverted-taper"),
    pytest.param({"screenShake.strengthPx": True}, False, id="boolean"),
    pytest.param({"screenShake.strengthPx": float("nan")}, False, id="nan"),
    pytest.param({"screenShake.strengthPx": float("inf")}, False, id="infinity"),
    pytest.param({"screenShake.strengthPx": 10 ** 400}, False, id="huge-number"),
    pytest.param({"screenShake": None}, False, id="null-payload"),
    pytest.param({"screenShake.strengthPx": None}, False, id="null-control"),
    pytest.param({"event": "periodic"}, False, id="periodic-forbidden"),
    pytest.param({"element": {}}, False, id="foreign-payload"),
    pytest.param({"rendererKind": "soundCue", "channel": "sound"}, False, id="payload-on-native-sound"),
])
def test_luminance_cue_bounds_are_shared_by_director_and_persisted_wire(edits: dict[str, Any], valid: bool) -> None:
    data = _data()
    raw = _screen_shake(data)
    for path, value in edits.items():
        target = raw["slots"][0]
        parts = path.split(".")
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]] = value
    assert vfx.validate_vfx_director_output(raw, data)["ok"] is valid
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "cue_admission")
    assert vfx.validate_vfx_manifest_wire(data)["ok"] is valid


def test_luminance_relation_repair_changes_only_diagnosed_endpoint() -> None:
    data = _data()
    raw = _screen_shake(data)
    raw["slots"][0]["screenShake"]["taperEndDistancePx"] = 300
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert {row["path"] for row in report["errors"]} == {"$.slots[0].screenShake.taperEndDistancePx"}
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    hostile = copy.deepcopy(raw["slots"][0])
    hostile["screenShake"].update(taperEndDistancePx=1200, strengthPx=12)
    repaired = vfx._apply_vfx_repair_patch(data, raw, _patch(slotsUpsert=[hostile]), scope)
    expected = copy.deepcopy(raw)
    expected["slots"][0]["screenShake"]["taperEndDistancePx"] = 1200
    assert repaired == expected
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]


def _library_particle(data: dict[str, Any]) -> dict[str, Any]:
    raw = _screen_shake(data)
    slot = raw["slots"][0]
    slot.pop("screenShake")
    slot.update(id="library_star", rendererKind="libraryParticle", backend="Particle",
                channel="impactParticles", lane="accent", duration=20, alpha=0.8, blend="additive")
    slot["particle"] = {
        "textureId": "star", "count": 3, "speedMinPxPerTick": 1.0, "speedMaxPxPerTick": 3.0,
        "spreadRadians": 0.5, "inheritVelocity": 0.25, "drag": 0.9,
        "accelerationXPxPerTickSquared": 0.0, "accelerationYPxPerTickSquared": 0.05,
        "widthPx": 8.0, "heightPx": 2.0, "rotationRadians": 0.0,
        "rotationSpeedRadiansPerTick": 0.1, "colorStart": "effect", "colorEnd": "gold",
        "endScaleMultiplier": 0.0, "endOpacity": 0.0,
    }
    return raw


@pytest.mark.parametrize("count", [0, 3, 64])
def test_library_particle_director_wire_keeps_explicit_controls_and_no_png_job(count: int) -> None:
    data = _data()
    raw = _library_particle(data)
    raw["slots"][0]["particle"]["count"] = count
    frozen = copy.deepcopy(data["runtimeProgram"])
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    result = vfx.attach_hybrid_vfx_manifest(data, "library_particles", llm_director=lambda *_a, **_kw: raw)
    assert result["vfxManifest"]["slots"][0]["particle"] == raw["slots"][0]["particle"]
    assert vfx.validate_vfx_manifest_wire(result) == {"ok": True, "errors": []}
    assert result["runtimeProgram"] == frozen
    assert "assets" not in result["vfxManifest"]
    assert vfx.vfx_png_dependencies(result, result["vfxManifest"])["errors"] == []


@pytest.mark.parametrize("edits,valid", [
    pytest.param({"particle.speedMaxPxPerTick": 0}, False, id="inverted-speed"),
    pytest.param({"particle.textureId": "smoke"}, False, id="unknown-texture"),
    pytest.param({"particle.count": True}, False, id="boolean-count"),
    pytest.param({"particle.count": 65}, False, id="overflow-count"),
    pytest.param({"particle.widthPx": float("nan")}, False, id="nan-width"),
    pytest.param({"particle.widthPx": 10 ** 400}, False, id="huge-width"),
    pytest.param({"particle.widthPx": 0}, True, id="zero-width"),
    pytest.param({"particle": None}, False, id="null-payload"),
    pytest.param({"screenShake": {}}, False, id="foreign-payload"),
    pytest.param({"event": "periodic"}, False, id="missing-periodic-cadence"),
    pytest.param({"event": "periodic", "repeatEvery": 2}, True, id="item-periodic"),
    pytest.param({"event": "periodic", "repeatEvery": 2, "startTick": 1}, False, id="item-unowned-clock"),
])
def test_library_particle_director_and_wire_share_typed_admission(edits: dict[str, Any], valid: bool) -> None:
    data = _data()
    raw = _library_particle(data)
    for path, value in edits.items():
        target = raw["slots"][0]
        parts = path.split(".")
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]] = value
    assert vfx.validate_vfx_director_output(raw, data)["ok"] is valid
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "particle_admission")
    assert vfx.validate_vfx_manifest_wire(data)["ok"] is valid


def test_library_particle_speed_repair_keeps_motion_color_and_gameplay_frozen() -> None:
    data = _data()
    raw = _library_particle(data)
    raw["slots"][0]["particle"]["speedMaxPxPerTick"] = 0
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert {row["path"] for row in report["errors"]} == {"$.slots[0].particle.speedMaxPxPerTick"}
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    hostile = copy.deepcopy(raw["slots"][0])
    hostile["particle"].update(speedMaxPxPerTick=3, drag=0.1, colorStart="black")
    repaired = vfx._apply_vfx_repair_patch(data, raw, _patch(slotsUpsert=[hostile]), scope)
    expected = copy.deepcopy(raw)
    expected["slots"][0]["particle"]["speedMaxPxPerTick"] = 3
    assert repaired == expected
    assert vfx.validate_vfx_director_output(repaired, data)["ok"]


@pytest.mark.parametrize("repair", [False, True])
@pytest.mark.parametrize("renderer,payload,factory", [
    pytest.param("libraryParticle", "particle", _library_particle, id="particle"),
    pytest.param("screenShakeCue", "screenShake", _screen_shake, id="camera"),
])
def test_library_choices_and_units_reach_actual_serialized_vfx_stage_packets(repair: bool, renderer: str, payload: str, factory: Any) -> None:
    data = _data()
    packet = _sent(data, repair)
    schema = packet["outputSchema"]
    Draft202012Validator.check_schema(schema)
    slot_schema = schema["properties"]["slotsUpsert" if repair else "slots"]["items"]
    authored = factory(data)["slots"][0]
    assert renderer in slot_schema["properties"]["rendererKind"]["enum"]
    assert Draft202012Validator(slot_schema).is_valid(authored)
    assert set(authored[payload]) == set(slot_schema["properties"][payload]["required"])
    assert all(field.get("description") for field in slot_schema["properties"][payload]["properties"].values())
    vocabulary = packet["runtimeVocabularyReadOnly" if repair else "runtimeVocabulary"]
    assert renderer in vocabulary["rendererSemantics"]
    assert "no" in vocabulary["rendererSemantics"][renderer].lower()
    assert "startTick" in vocabulary["rendererSemantics"][renderer]
    assert "delay" in vocabulary["rendererSemantics"][renderer]
    if payload == "particle":
        texture_description = slot_schema["properties"][payload]["properties"]["textureId"]["description"]
        assert "opaque" in texture_description and "black" in texture_description


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


def test_wire_slot_ceiling_is_not_bypassed_by_canonical_shape_gate() -> None:
    data = _data()
    raw = _sprite(data)
    vfx.attach_hybrid_vfx_manifest(data, "bounded_wire", llm_director=lambda *_a, **_kw: raw)
    slot = data["vfxManifest"]["slots"][0]
    data["vfxManifest"]["slots"] = [{**copy.deepcopy(slot), "id": f"row_{index}"} for index in range(13)]
    report = vfx.validate_vfx_manifest_wire(data)
    assert not report["ok"]
    assert "$.vfxManifest.slots" in {r["path"] for r in report["errors"]}

@pytest.mark.parametrize("mode,valid", [("baked_sprite", True), ("reuse_item_icon", True), ("no_asset", False), ("runtime_geometry", False), ("", False)])
def test_entity_texture_requires_that_exact_accepted_image_tuple(mode: str, valid: bool) -> None:
    data = _data()
    row = next(row for row in data["runtimeProgram"]["entities"] if row["kind"] != "item_body")
    row["visual"]["assetMode"] = mode
    raw = _sprite(data)
    raw["slots"][0].update(entityId=row["id"], event="on_spawn")
    raw["slots"][0]["element"]["texture"] = {"source": "entity", "assetId": ""}
    before = copy.deepcopy(data)
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"] is valid, report["errors"]
    for repair in (False, True):
        packet = _sent(data, repair)
        vocabulary = packet["runtimeVocabularyReadOnly" if repair else "runtimeVocabulary"]
        assert vocabulary["textureDependencyTuples"]
        schema = packet["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]
        assert bool(strict_schema_errors(raw["slots"][0], schema)) is not valid
    if not valid:
        assert {r["path"] for r in report["errors"]} == {"$.slots[0].element.texture.source"}
        candidate = copy.deepcopy(raw["slots"][0])
        candidate["element"]["texture"]["source"] = "item"
        candidate["element"]["widthPx"] = 40
        scope = vfx._build_vfx_repair_scope(raw, report["errors"])
        repaired = vfx._apply_vfx_repair_patch(data, raw, _patch(slotsUpsert=[candidate]), scope)
        assert repaired["slots"][0]["element"]["widthPx"] == 12.0
        assert vfx.validate_vfx_director_output(repaired, data)["ok"]
    assert data == before

@pytest.mark.parametrize("renderer", ["spriteElement", "texturedPath"])
def test_nested_impact_requires_same_entity_existing_image_producer(renderer: str) -> None:
    data = _data()
    raw = _sprite(data) if renderer == "spriteElement" else _path(data)
    name = "element" if renderer == "spriteElement" else "path"
    raw["slots"][0][name]["texture"] = {"source": "impact", "assetId": ""}
    unpaired = vfx.validate_vfx_director_output(raw, data)
    assert not unpaired["ok"]
    assert {r["path"] for r in unpaired["errors"]} == {f"$.slots[0].{name}.texture.source"}
    producer = _legacy(data)["slots"][0]
    producer.update(id="exact_impact", entityId=raw["slots"][0]["entityId"], event=raw["slots"][0]["event"], rendererKind="impactSprite", backend="Sprite", textureRole="impact", spritePrompt="one impact ingredient")
    raw["slots"].append(producer)
    assert vfx.validate_vfx_director_output(raw, data)["ok"]
    final = vfx.attach_hybrid_vfx_manifest(data, "nested_impact", llm_director=lambda *_a, **_kw: raw)
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    final["vfxManifest"]["slots"].pop()
    report = vfx.validate_vfx_manifest_wire(final)
    assert not report["ok"]
    assert f"$.vfxManifest.slots[0].{name}.texture.source" in {r["path"] for r in report["errors"]}


def test_beam_collision_precedence_does_not_advertise_dormant_whip() -> None:
    data = _data("channel_beam")
    entity = next(row for row in data["runtimeProgram"]["entities"] if row["kind"] != "item_body")
    entity["movement"] = {"name": "move_whip_lash", "code": 18, "params": {"rangeTiles": 4, "segments": 10}}
    assert vfx.vfx_director_surface(data)["texturedPathSources"] == [{"entityId": entity["id"], "sources": ["anchorHistory", "beam"]}]
    entity["controller"]["name"] = "not_accepted_beam"
    assert vfx.vfx_director_surface(data)["texturedPathSources"] == [{"entityId": entity["id"], "sources": ["anchorHistory"]}]


MATERIAL_BOUNDARIES = json.loads((Path(__file__).parent / "fixtures/vfx_image_material_boundaries.json").read_text())
BOUNDARY_TRANSPORTS = [pytest.param(case, repair, id=case["id"] + ("-repair" if repair else "-director"))
                       for case in MATERIAL_BOUNDARIES for repair in ((False, True) if case["schema"] else (False,))]


@pytest.mark.parametrize("case,repair", BOUNDARY_TRANSPORTS)
def test_material_boundary_rejection(case, repair):
    data = _data(case["capability"])
    kind = case["base"]
    if kind == "wire":
        target = _compiled()
    elif kind == "later":
        authored = _with_asset(data)
        authored["slots"].append({**copy.deepcopy(authored["slots"][0]), "id": "later_material"})
        target = vfx.attach_hybrid_vfx_manifest(data, "large_integer_wire", llm_director=lambda *_a, **_kw: authored)
    else:
        target = _with_asset(data) if kind == "asset" else _path(data, case["source"]) if kind in {"path", "anchor"} else _sprite(data)
    apply_edits(target, case["edits"])
    before = copy.deepcopy(target)
    validator = vfx.validate_vfx_manifest_wire if case["wire"] else vfx.validate_vfx_director_output
    assert callable(validator), "canonical persisted/admission boundary required"
    report = validator(target) if case["wire"] else validator(target, data)
    assert not report["ok"], case["id"]
    paths = {row["path"] for row in report["errors"]}
    assert case["path"] in paths, report
    if kind in {"anchor", "later"}:
        assert paths == {case["path"]}
    if case["schema"]:
        props = _sent(data, repair)["outputSchema"]["properties"]
        schema = props["assetsUpsert" if repair else "assets"]["items"] if case["schema"] == "asset" else props["slotsUpsert" if repair else "slots"]["items"]
        errors = strict_schema_errors(target["assets"][0] if case["schema"] == "asset" else target["slots"][0], schema)
        assert errors, case["id"]
        if case["schema"] == "asset":
            assert "$.id" in {row["path"] for row in errors}
    assert target == before

MATERIAL_PAYLOADS = (
    ("legacy", "", ""), ("sprite", "", ""), ("zero", "", ""), ("shared_asset", "", ""),
    ("path", "anchorHistory", ""), ("path", "beam", "channel_beam"),
    ("path", "whip", "move_whip_lash"), ("history_length", "anchorHistory", ""),
)

@pytest.mark.parametrize("kind,source,capability", MATERIAL_PAYLOADS, ids=[kind + ("-" + source if source else "") for kind, source, _ in MATERIAL_PAYLOADS])
@pytest.mark.parametrize("repair", [False, True])
def test_material_payload_roundtrip(kind, source, capability, repair):
    data = _data(capability)
    raw = _legacy(data) if kind == "legacy" else _with_asset(data) if kind == "shared_asset" else _path(data, source) if source else _sprite(data)
    slot = raw["slots"][0]
    if kind == "history_length":
        slot["path"]["profileDomain"] = "length"
    if kind == "zero":
        slot.update(alpha=0.0, startTick=7)
        element = slot["element"]
        element.update(attachment="source", count=0, widthPx=0.0, heightPx=0.0, inheritVelocity=0.0, drag=0.0)
        for field in ("widthProfile", "heightProfile", "opacityProfile"):
            element[field] = {"start": 0.0, "middle": 0.0, "end": 0.0, "curve": "linear"}
    if kind == "shared_asset":
        second = copy.deepcopy(slot); second.update(id="shared_ingredient", event="on_hit"); raw["slots"].append(second)
    before, gameplay = copy.deepcopy(raw), copy.deepcopy(data["runtimeProgram"])
    packet = _sent(data, repair)
    schema = packet["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]
    assert not strict_schema_errors(slot, schema)
    Draft202012Validator.check_schema(packet["outputSchema"])
    if not repair:
        assert not strict_schema_errors(raw, packet["outputSchema"])
        Draft202012Validator(packet["outputSchema"]).validate(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"] == before
    final = vfx.attach_hybrid_vfx_manifest(data, "legacy_material_abi" if kind == "legacy" else "material_roundtrip", llm_director=lambda *_a, **_kw: raw)
    compiled = final["vfxManifest"]["slots"]
    if kind == "legacy":
        expected = (Path(__file__).parent / "fixtures/vfx_material_legacy_manifest.json").read_text(encoding="utf-8")
        assert json.dumps(final["vfxManifest"], ensure_ascii=False, separators=(",", ":")) == expected
        assert "assets" not in final["vfxManifest"]
    else:
        payload = "path" if source else "element"
        assert [row[payload] for row in compiled] == [row[payload] for row in before["slots"]]
        if kind == "sprite":
            raw["slots"][0]["element"]["widthProfile"]["middle"] = 4
            assert compiled[0]["element"]["widthProfile"]["middle"] == 1
            raw["slots"][0]["element"]["widthProfile"]["middle"] = before["slots"][0]["element"]["widthProfile"]["middle"]
        if kind == "shared_asset":
            assert final["vfxManifest"]["assets"] == [{**_asset(), "spritePath": "", "spriteUrl": "", "spriteStatus": "pending", "spriteTechnicalScore": 0.0}]
            assert [row["element"]["texture"]["assetId"] for row in compiled] == ["Glow_A-1", "Glow_A-1"]
        if source:
            surface = packet["runtimeSurfaceReadOnly"] if repair else packet["runtimeSurface"]
            row = next(row for row in surface["texturedPathSources"] if row["entityId"] == slot["entityId"])
            assert source in row["sources"]
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert final["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 0
    assert data["runtimeProgram"] == gameplay and raw == before

ROUTE_SURFACE = vfx.vfx_director_surface(_accepted_visual_data("workbench_blade"))
RENDERER_ROUTES = [pytest.param(renderer, channel, lane, id=renderer + "-" + channel + "-" + lane)
                   for renderer in ROUTE_SURFACE["rendererKind"] for channel in ROUTE_SURFACE["channel"] for lane in ROUTE_SURFACE["lane"]]
COMPANION_FIELDS = [pytest.param(renderer, field, neutral, id=renderer + "-" + field)
                    for renderer, requirements in ROUTE_SURFACE["rendererRequirements"].items() for field, neutral in requirements.items()]

def _renderer_material(data, renderer):
    if renderer == "libraryParticle":
        return _library_particle(data)
    if renderer == "screenShakeCue":
        return _screen_shake(data)
    raw = _sprite(data) if renderer == "spriteElement" else _path(data) if renderer == "texturedPath" else _vfx_output(data)
    raw["slots"][0].update(rendererKind=renderer)
    if renderer == "soundCue":
        raw["slots"][0]["soundId"] = "Item1"
    if renderer == "impactSprite":
        raw["slots"][0].update(textureRole="impact", spritePrompt="one transparent impact sprite")
    return raw

@pytest.mark.parametrize("renderer,channel,lane", RENDERER_ROUTES)
def test_renderer_route_admission(renderer, channel, lane):
    data = _accepted_visual_data("workbench_blade")
    raw = _renderer_material(data, renderer)
    slot = raw["slots"][0]
    slot.update(channel=channel, lane=lane)
    if renderer == "screenShakeCue":
        expected = (channel, lane) == ("screenShake", "cue")
    elif renderer == "libraryParticle":
        expected = channel in {"ambientParticles", "impactParticles", "decaySmoke"} and lane != "cue"
    else:
        expected = channel != "screenShake" and (channel not in {"light", "sound"} if renderer in {"spriteElement", "texturedPath"} else renderer not in {"lightCue", "soundCue"} or (channel, lane) == ("light" if renderer == "lightCue" else "sound", "cue"))
    before = copy.deepcopy(raw)
    schema = _sent(data, False)["outputSchema"]["properties"]["slots"]["items"]
    assert (not strict_schema_errors(slot, schema)) is expected
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"] is expected, report["errors"]
    assert raw == before
    if expected:
        assert report["normalized"]["slots"][0] == slot

@pytest.mark.parametrize("renderer,field,neutral", COMPANION_FIELDS)
@pytest.mark.parametrize("repair", [False, True])
def test_renderer_companion_admission(renderer, field, neutral, repair):
    data = _data()
    raw = _renderer_material(data, renderer)
    required = ROUTE_SURFACE["rendererRequirements"][renderer]
    raw["slots"][0].update(required)
    packet = _sent(data, repair)
    schema = packet["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]
    assert not strict_schema_errors(raw["slots"][0], schema)
    assert vfx.validate_vfx_director_output(raw, data)["ok"]
    assert packet["runtimeVocabularyReadOnly" if repair else "runtimeVocabulary"]["rendererRequirements"][renderer] == required
    broken = copy.deepcopy(raw)
    broken["slots"][0][field] = "Auto" if field == "backend" else ("item" if isinstance(neutral, str) else neutral + 1)
    if renderer in {"lightCue", "soundCue"}:
        broken["slots"][0][field] = "coreGlow" if field == "channel" else "accent"
    assert not vfx.validate_vfx_director_output(broken, data)["ok"]
    errors = strict_schema_errors(broken["slots"][0], schema)
    assert errors
    if renderer in {"spriteElement", "texturedPath"}:
        assert "$." + field in {row["path"] for row in errors}
