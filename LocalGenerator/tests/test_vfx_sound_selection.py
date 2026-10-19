"""Explicit offline sound choices through the real VFX stage, never a provider call."""
from __future__ import annotations

from prompt_packet_helpers import request_dossier, dossier_text

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from infini_local.core import llm_config
from infini_local.core import vfx_manifest as vfx
from infini_local.pipelines import vfx_generation_pipeline as stage
from tests.test_repair_vfx_contract import _offline_transport
from tests.vfx_material_fixtures import _data, _legacy

# Exact installed Terraria.ID.SoundID members; no weapon/archetype aliases.
_INVENTORY = json.loads((Path(__file__).parent / "fixtures/vfx_sound_inventory.json").read_text())
SOUND_IDS = tuple(sorted(set(_INVENTORY["historicalCatalog"].values()) | set(_INVENTORY["precedingCatalog"]),
                         key=lambda value: (0, int(value[4:])) if value.startswith("Item") else (1, value)))


def _sound(data, sound_id: Any = "Item4", *, projectile=False):
    raw = _legacy(data)
    slot = raw["slots"][0]
    slot.update(id="explicit_sound", rendererKind="soundCue",
                particleSystemId="none", textureRole="none", soundId=sound_id,
                sound={"volume": 0.37, "pitch": -0.2, "pitchVariance": 0.12})
    if projectile:
        slot.update(entityId=next(e["id"] for e in data["runtimeProgram"]["entities"] if e["kind"] != "item_body"), event="on_spawn")
    for field in ("color", "scale", "spread", "particleSystemId", "textureRole", "duration", "alpha", "blend", "layer", "density", "startTick", "repeatEvery"):
        slot.pop(field)
    return raw


# Palette completeness belongs to vocabulary/schema equality and the native
# SoundID mapping gate. Copying needs a numeric name, a named sound and binding.
@pytest.mark.parametrize("sound_id,projectile", [
    pytest.param("Item169", False, id="item-numeric-sample"),
    pytest.param("ResearchComplete", False, id="item-named-sample"),
    pytest.param("Item4", True, id="projectile-sample"),
])
def test_selected_sample_survives_director_compiler_and_wire(monkeypatch, sound_id, projectile):
    data = _data()
    before = copy.deepcopy(data)
    raw = _sound(data, sound_id, projectile=projectile)
    raw_before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"]["slots"][0]["soundId"] == sound_id
    sent = _offline_transport(monkeypatch, f"sound_{projectile}_{sound_id}", [raw])
    final = vfx.attach_vfx_manifest(data, "exact-sound", llm_director=stage.call_llm_vfx_director)
    assert len(sent) == 1
    packet = request_dossier(sent[0])
    assert packet["runtimeVocabulary"]["soundId"] == list(SOUND_IDS)
    assert packet["outputSchema"]["properties"]["slots"]["items"]["properties"]["soundId"]["enum"] == list(SOUND_IDS)
    assert final["vfxManifest"]["slots"][0]["soundId"] == sound_id
    assert vfx.validate_vfx_manifest_wire(json.loads(json.dumps(final)))["ok"]
    assert final["runtimeProgram"] == before["runtimeProgram"]
    assert final["gameplay"] == before["gameplay"]
    assert raw == raw_before


@pytest.mark.parametrize("bad,renderer,field", [
    pytest.param(bad, "soundCue", "soundId", id=name)
    for name, bad in (("null", None), ("empty", ""), ("case", "item4"), ("whitespace", " Item4"),
                      ("unknown", "Item9999"), ("alias", "frozenRepair"), ("integer", 4),
                      ("boolean", True), ("object", {}), ("array", []))
] + [
    pytest.param("Item4", "impactRing", "soundId", id="foreign-impactRing"),
    pytest.param("Item4", "lightCue", "soundId", id="foreign-lightCue"),
    pytest.param({"soundId": "Item4"}, "soundCue", "frozenRepair", id="unknown-payload"),
])
def test_invalid_present_sound_is_rejected_by_director_and_persisted_wire(bad, renderer, field):
    data = _data()
    raw = _sound(data) if renderer == "soundCue" else _legacy(data)
    raw["slots"][0].update(rendererKind=renderer)
    if renderer == "lightCue":
        for unused in ("alpha", "blend", "layer", "duration", "spread", "particleSystemId", "textureRole", "startTick", "repeatEvery", "density"):
            raw["slots"][0].pop(unused, None)
    raw["slots"][0][field] = bad
    before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert {e["path"] for e in report["errors"]} == {"$.slots[0]." + field}
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "bad-sound")
    wire_before = copy.deepcopy(data)
    persisted = vfx.validate_vfx_manifest_wire(data)
    assert not persisted["ok"], persisted
    assert {e["path"] for e in persisted["errors"]} == {"$.vfxManifest.slots[0]." + field}
    assert data == wire_before and raw == before


@pytest.mark.parametrize("missing", [
    pytest.param(("soundId", "sound"), id="old-item1-alpha-phase-absence"),
    pytest.param(("soundId",), id="selector-absence"),
    pytest.param(("sound",), id="old-alpha-phase-controls-absence"),
])
def test_sound_absence_refuses_director_persisted_wire_and_cache_without_defaults(missing, tmp_path, monkeypatch):
    from infini_local.storage import world_storage
    data = _data()
    raw = _sound(data)
    for field in missing:
        raw["slots"][0].pop(field)
    raw_before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert {e["path"] for e in report["errors"]} == {"$.slots[0]." + field for field in missing}
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "retired-sound-absence")
    # Historical alpha/phase values must not make missing audio choices valid.
    data["vfxManifest"]["slots"][0].update(alpha=0.61, phaseOffset=-0.75)
    persisted = json.loads(json.dumps(data))
    before = copy.deepcopy(persisted)
    report = vfx.validate_vfx_manifest_wire(persisted)
    assert not report["ok"], report
    assert {e["path"] for e in report["errors"]} == {"$.vfxManifest.slots[0]." + field for field in (*missing, "alpha")}
    assert not world_storage.is_deliverable_recipe_payload(persisted, check_assets=False)
    assert persisted == before and raw == raw_before
    assert all(field not in persisted["vfxManifest"]["slots"][0] for field in missing)
    # Exercise the actual file reader with a valid current cache record whose
    # only mutations are the retired audio absences and old alpha/phase inputs.
    current = _data()
    current["vfxManifest"] = vfx._compile_manifest(current, _sound(current), "current-cache-sound")
    from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION
    current.update(id="sound_cache_probe", schemaVersion=5, runtimeApiVersion=RUNTIME_PROGRAM_API_VERSION,
                   sourceMode="offline_contract_fixture")
    from infini_local.pipelines import visual_delivery_gate
    from infini_local.qa.live_no_image_fixture import hydrate_no_image_fixture_assets, write_no_image_fixture_png, synthetic_no_image_execution_control
    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", tmp_path)
    current["visual"] = {"preferredCanvasSize": 32}
    for entity in current["runtimeProgram"]["entities"]:
        entity["visual"]["assetMode"] = "reuse_item_icon" if entity["kind"] != "item_body" else "baked_sprite"
    fixture = write_no_image_fixture_png(tmp_path / "sound.png")
    hydrate_no_image_fixture_assets(current, fixture)
    current = synthetic_no_image_execution_control(current, fixture)
    world_storage.write_world_recipe_cache(tmp_path, "sound-test", "sound", "world", current)
    cached = world_storage.read_world_recipe_cache(tmp_path, "sound-test", "v5", "sound", "world")
    assert cached is not None and cached["vfxManifest"]["slots"] == current["vfxManifest"]["slots"]
    path = world_storage.world_recipe_file(tmp_path, "world", "sound")
    stored = json.loads(path.read_text())
    slot = stored["vfxManifest"]["slots"][0]
    for field in missing:
        slot.pop(field)
    slot.update(alpha=0.61, phaseOffset=-0.75)
    old_bytes = json.dumps(stored).encode()
    path.write_bytes(old_bytes)
    assert world_storage.read_world_recipe_cache(tmp_path, "sound-test", "v5", "sound", "world") is None
    assert not path.exists()
    invalid = world_storage.world_recipe_dir(tmp_path, "world") / "invalid"
    originals = [p for p in invalid.glob("*.json") if not p.name.endswith(".reason.json")]
    assert len(originals) == 1 and originals[0].read_bytes() == old_bytes
    reason = json.loads(originals[0].with_suffix(".reason.json").read_text())
    assert {row["path"] for row in reason["details"]["vfx"]["errors"]} == {
        "$.vfxManifest.slots[0]." + field for field in (*missing, "alpha")}


@pytest.mark.parametrize("bad,mode", [
    pytest.param(None, "json_schema", id="schema-null"),
    pytest.param("missing-sample", "json_object", id="object-unknown"),
    pytest.param("absent", "json_schema", id="schema-absent"),
    pytest.param("both-absent", "json_schema", id="schema-both-absent"),
    pytest.param("both-absent", "json_object", id="object-both-absent"),
])
def test_real_repair_corrects_only_diagnosed_sound_leaf(monkeypatch, bad, mode):
    data = _data()
    before = copy.deepcopy(data)
    accepted = _sound(data, "Splash")
    raw = copy.deepcopy(accepted)
    paths = ["soundId"]
    if bad == "both-absent":
        raw["slots"][0].pop("sound")
        paths = ["sound", "soundId"]
    if bad in {"absent", "both-absent"}:
        raw["slots"][0].pop("soundId")
    else:
        raw["slots"][0]["soundId"] = bad
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    assert scope["fieldPermissions"] == {"globals": {}, "slots": [{"slotId": "explicit_sound", "paths": paths}], "assets": []}
    candidate = copy.deepcopy(accepted["slots"][0])
    candidate.update(alpha=0.1, rendererKind="lightCue",  entityId=data["runtimeProgram"]["entities"][1]["id"], event="on_kill")
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "sound only", "slotsUpsert": [candidate], "slotIdsDelete": ["explicit_sound"]}
    raw_before = copy.deepcopy(raw)
    sent = _offline_transport(monkeypatch, "sound_repair_" + str(bad) + mode, [raw, patch])
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    final = vfx.attach_vfx_manifest(data, "sound-repair", llm_director=stage.call_llm_vfx_director)
    assert final["debug"]["vfxDirectorRaw"] == accepted
    assert raw == raw_before
    assert final["gameplay"] == before["gameplay"] and final["runtimeProgram"] == before["runtimeProgram"]
    assert final["debug"]["vfxRepairFilterAudit"]["acceptedPaths"] == ["$.slotsUpsert[0]." + path for path in paths]
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert len(sent) == 2
    director, repair = [request_dossier(r) for r in sent]
    assert repair["runtimeVocabularyReadOnly"]["soundId"] == director["runtimeVocabulary"]["soundId"] == list(SOUND_IDS)
    assert "soundCue requires an explicit soundId" in director["runtimeVocabulary"]["rendererSemantics"]["soundCue"]
    assert repair["repairScope"] == scope
    for request in sent:
        assert request["response_format"]["type"] == mode
        if mode == "json_schema":
            assert "soundId" in json.dumps(request["response_format"]["json_schema"]["schema"])


@pytest.mark.parametrize("sound_id", ["Item1", "ResearchComplete"], ids=["explicit-item1", "explicit-named-sample"])
def test_sound_wire_survives_delivery_projection_and_real_cache_shape_admission(sound_id, tmp_path, monkeypatch):
    from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION
    from infini_local.storage import world_storage
    data = _data()
    data.update(id="sound_cache_probe", schemaVersion=5, runtimeApiVersion=RUNTIME_PROGRAM_API_VERSION,
                sourceMode="offline_contract_fixture")
    raw = _sound(data, sound_id)
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "cache-sound")
    from infini_local.pipelines import visual_delivery_gate
    from infini_local.qa.live_no_image_fixture import hydrate_no_image_fixture_assets, write_no_image_fixture_png, synthetic_no_image_execution_control
    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", tmp_path)
    data["visual"] = {"preferredCanvasSize": 32}
    for entity in data["runtimeProgram"]["entities"]:
        entity["visual"]["assetMode"] = "reuse_item_icon" if entity["kind"] != "item_body" else "baked_sprite"
    fixture = write_no_image_fixture_png(tmp_path / "sound.png")
    hydrate_no_image_fixture_assets(data, fixture)
    data = synthetic_no_image_execution_control(data, fixture)
    data = json.loads(json.dumps(data))
    before = copy.deepcopy(data)
    assert world_storage.is_deliverable_recipe_payload(data, check_assets=False)
    delivered = world_storage.sanitize_recipe_for_delivery(data)
    assert delivered["vfxManifest"]["slots"] == data["vfxManifest"]["slots"]
    assert world_storage.is_deliverable_recipe_payload(delivered, check_assets=False)
    assert delivered["vfxManifest"]["slots"][0]["soundId"] == sound_id
    assert delivered["vfxManifest"]["slots"][0]["sound"] == raw["slots"][0]["sound"]
    world_storage.write_world_recipe_cache(tmp_path, "sound-test", "sound", "world", data)
    cached = world_storage.read_world_recipe_cache(tmp_path, "sound-test", "v5", "sound", "world")
    assert cached is not None and cached["vfxManifest"]["slots"] == delivered["vfxManifest"]["slots"]
    for invalid in (None, "missing", "frozenRepair"):
        corrupted = copy.deepcopy(delivered)
        corrupted["vfxManifest"]["slots"][0]["soundId"] = invalid
        assert not world_storage.is_deliverable_recipe_payload(corrupted, check_assets=False)
    assert data == before


@pytest.mark.parametrize("silent", [False, True], ids=["non-sound-renderer", "empty-slots"])
def test_non_sound_wire_omission_remains_valid_without_audio_materialization(silent):
    data = _data()
    raw = _legacy(data)
    if silent:
        raw["slots"] = []
    assert vfx.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "non-sound-omission")
    persisted = json.loads(json.dumps(data))
    before = copy.deepcopy(persisted)
    assert vfx.validate_vfx_manifest_wire(persisted)["ok"]
    assert persisted == before
    assert all("soundId" not in slot and "sound" not in slot for slot in persisted["vfxManifest"]["slots"])


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_real_transport_never_strips_present_null_to_legacy_absence(monkeypatch, mode):
    from infini_local.core.errors import PlannerUnavailable
    data = _data()
    raw = _sound(data, None)
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "no sound correction"}
    sent = _offline_transport(monkeypatch, "null_sound_noop_" + mode, [raw, patch])
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    with pytest.raises(PlannerUnavailable, match="VFX Repair did not produce"):
        vfx.attach_vfx_manifest(data, "null-audio", llm_director=stage.call_llm_vfx_director)
    assert len(sent) == 2 and "vfxManifest" not in data
    assert raw["slots"][0]["soundId"] is None
    assert request_dossier(sent[1])["repairScope"]["fieldPermissions"]["slots"] == [{"slotId": "explicit_sound", "paths": ["soundId"]}]


def test_foreign_sound_leaf_can_be_deleted_without_thawing_valid_renderer(monkeypatch):
    data = _data()
    accepted = _legacy(data)
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["soundId"] = "Item4"
    report = vfx.validate_vfx_director_output(raw, data)
    assert {e["path"] for e in report["errors"]} == {"$.slots[0].soundId"}
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    assert scope["fieldPermissions"]["slots"] == [{"slotId": "old_slot", "paths": ["soundId"], "deletePaths": ["soundId"]}]
    candidate = copy.deepcopy(accepted["slots"][0])
    candidate.update(rendererKind="lightCue",  alpha=0.1)
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "delete only foreign sound field", "slotsUpsert": [candidate]}
    _offline_transport(monkeypatch, "foreign_sound_delete", [raw, patch])
    final = vfx.attach_vfx_manifest(data, "foreign-sound", llm_director=stage.call_llm_vfx_director)
    assert final["debug"]["vfxDirectorRaw"] == accepted
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
