"""Explicit offline sound choices through the real VFX stage, never a provider call."""
from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from infini_local.core import vfx_manifest as vfx
from infini_local.pipelines import llm_authoring_pipeline as stage
from tests.test_repair_vfx_contract import _offline_transport
from tests.vfx_material_fixtures import _data, _legacy

# Exact installed Terraria.ID.SoundID members; no weapon/archetype aliases.
SOUND_IDS = (
    "Item1", "Item2", "Item3", "Item4", "Item8", "Item9", "Item14", "Item20", "Item21", "Item29", "Item43",
    "Dig", "Tink", "Grab", "Shatter", "Splash", "Coins", "Unlock", "MaxMana", "ResearchComplete",
)


def _sound(data, sound_id: Any = "Item4", *, projectile=False):
    raw = _legacy(data)
    slot = raw["slots"][0]
    slot.update(id="explicit_sound", rendererKind="soundCue", channel="sound", lane="cue",
                emissionMode="none", particleSystemId="none", textureRole="none", soundId=sound_id)
    if projectile:
        slot.update(entityId=next(e["id"] for e in data["runtimeProgram"]["entities"] if e["kind"] != "item_body"), event="on_spawn")
    return raw


@pytest.mark.parametrize("projectile", [False, True], ids=["item", "projectile"])
@pytest.mark.parametrize("sound_id", SOUND_IDS)
def test_selected_sample_survives_director_compiler_and_wire(monkeypatch, sound_id, projectile):
    data = _data()
    before = copy.deepcopy(data)
    raw = _sound(data, sound_id, projectile=projectile)
    raw_before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    assert report["normalized"]["slots"][0]["soundId"] == sound_id
    sent = _offline_transport(monkeypatch, f"sound_{projectile}_{sound_id}", [raw])
    final = vfx.attach_hybrid_vfx_manifest(data, "exact-sound", llm_director=stage.call_llm_vfx_director)
    assert len(sent) == 1
    packet = json.loads(sent[0]["messages"][1]["content"])
    assert packet["runtimeVocabulary"]["soundId"] == list(SOUND_IDS)
    assert packet["outputSchema"]["properties"]["slots"]["items"]["properties"]["soundId"]["enum"] == list(SOUND_IDS)
    assert final["vfxManifest"]["slots"][0]["soundId"] == sound_id
    assert vfx.validate_vfx_manifest_wire(json.loads(json.dumps(final)))["ok"]
    assert final["runtimeProgram"] == before["runtimeProgram"]
    assert final["gameplay"] == before["gameplay"]
    assert raw == raw_before


@pytest.mark.parametrize("bad", [None, "", "item4", " Item4", "Item9999", "frozenRepair", 4, True, {}, []])
def test_invalid_present_sound_is_rejected_by_director_and_persisted_wire(bad):
    data = _data()
    raw = _sound(data, bad)
    before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert {e["path"] for e in report["errors"]} == {"$.slots[0].soundId"}
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "bad-sound")
    wire_before = copy.deepcopy(data)
    persisted = vfx.validate_vfx_manifest_wire(data)
    assert not persisted["ok"], persisted
    assert {e["path"] for e in persisted["errors"]} == {"$.vfxManifest.slots[0].soundId"}
    assert data == wire_before and raw == before


def test_fresh_sound_requires_explicit_choice_but_legacy_wire_absence_stays_absent():
    data = _data()
    raw = _sound(data)
    raw["slots"][0].pop("soundId")
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert {e["path"] for e in report["errors"]} == {"$.slots[0].soundId"}
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "legacy-sound")
    before = copy.deepcopy(data)
    assert vfx.validate_vfx_manifest_wire(data)["ok"]
    assert data == before and "soundId" not in data["vfxManifest"]["slots"][0]
    # Native DTO serialization has always carried this legacy pitch input.
    data["vfxManifest"]["slots"][0]["phaseOffset"] = -0.75
    assert vfx.validate_vfx_manifest_wire(data)["ok"]


@pytest.mark.parametrize("renderer", ["impactRing", "lightCue"])
def test_sound_selector_is_forbidden_on_other_legacy_renderer_branches(renderer):
    data = _data()
    raw = _legacy(data)
    raw["slots"][0].update(rendererKind=renderer, soundId="Item4")
    if renderer == "lightCue":
        raw["slots"][0].update(channel="light", lane="cue")
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert {e["path"] for e in report["errors"]} == {"$.slots[0].soundId"}
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "foreign-sound")
    assert not vfx.validate_vfx_manifest_wire(data)["ok"]


def test_wire_sound_branch_rejects_unknown_frozen_repair_payload():
    data = _data()
    raw = _sound(data)
    raw["slots"][0]["frozenRepair"] = {"soundId": "Item4"}
    assert not vfx.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "unknown-payload")
    report = vfx.validate_vfx_manifest_wire(data)
    assert not report["ok"]
    assert {e["path"] for e in report["errors"]} == {"$.vfxManifest.slots[0].frozenRepair"}


@pytest.mark.parametrize("bad", [None, "missing-sample", "absent"])
@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_real_repair_corrects_only_diagnosed_sound_leaf(monkeypatch, bad, mode):
    from infini_local.pipelines import llm_transport
    data = _data()
    before = copy.deepcopy(data)
    accepted = _sound(data, "Splash")
    raw = copy.deepcopy(accepted)
    if bad == "absent":
        raw["slots"][0].pop("soundId")
    else:
        raw["slots"][0]["soundId"] = bad
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    assert scope["fieldPermissions"] == {"globals": {}, "slots": [{"slotId": "explicit_sound", "paths": ["soundId"]}], "assets": []}
    candidate = copy.deepcopy(accepted["slots"][0])
    candidate.update(alpha=0.1, rendererKind="lightCue", channel="light", lane="support", entityId=data["runtimeProgram"]["entities"][1]["id"], event="on_kill")
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "sound only", "slotsUpsert": [candidate], "slotIdsDelete": ["explicit_sound"]}
    raw_before = copy.deepcopy(raw)
    sent = _offline_transport(monkeypatch, "sound_repair_" + str(bad) + mode, [raw, patch])
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", mode)
    final = vfx.attach_hybrid_vfx_manifest(data, "sound-repair", llm_director=stage.call_llm_vfx_director)
    assert final["debug"]["vfxDirectorRaw"] == accepted
    assert raw == raw_before
    assert final["gameplay"] == before["gameplay"] and final["runtimeProgram"] == before["runtimeProgram"]
    assert final["debug"]["vfxRepairFilterAudit"]["acceptedPaths"] == ["$.slotsUpsert[0].soundId"]
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert len(sent) == 2
    director, repair = [json.loads(r["messages"][1]["content"]) for r in sent]
    assert repair["runtimeVocabularyReadOnly"]["soundId"] == director["runtimeVocabulary"]["soundId"] == list(SOUND_IDS)
    assert "fresh soundCue requires an explicit soundId" in director["runtimeVocabulary"]["rendererSemantics"]["soundCue"]
    assert repair["repairScope"] == scope
    for request in sent:
        assert request["response_format"]["type"] == mode
        if mode == "json_schema":
            assert "soundId" in json.dumps(request["response_format"]["json_schema"]["schema"])


@pytest.mark.parametrize("silent", [False, True])
def test_unrelated_repair_keeps_explicit_sample_or_silence_frozen(monkeypatch, silent):
    data = _data()
    accepted = _sound(data, "Tink")
    if silent:
        accepted["slots"] = []
    raw = copy.deepcopy(accepted)
    raw["effectMagnitude"] = 2
    hostile = _sound(data, "Item14")["slots"][0]
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "metadata only", "effectMagnitude": 0.5,
             "slotsUpsert": [hostile], "slotIdsDelete": ["explicit_sound"]}
    _offline_transport(monkeypatch, "frozen_audio_" + str(silent), [raw, patch])
    final = vfx.attach_hybrid_vfx_manifest(data, "frozen-audio", llm_director=stage.call_llm_vfx_director)
    assert final["debug"]["vfxDirectorRaw"] == accepted
    assert final["debug"]["vfxRepairFilterAudit"]["acceptedPaths"] == ["$.effectMagnitude"]
    assert vfx.validate_vfx_manifest_wire(final)["ok"]


@pytest.mark.parametrize("sound_id", [None, "Item1", "Item4", "Dig", "ResearchComplete"])
def test_sound_wire_survives_delivery_projection_and_real_cache_shape_admission(sound_id):
    from infini_local.core.runtime_authoring import RUNTIME_PROGRAM_API_VERSION
    from infini_local.storage import world_storage
    data = _data()
    data.update(id="sound_cache_probe", schemaVersion=5, runtimeApiVersion=RUNTIME_PROGRAM_API_VERSION,
                sourceMode="offline_contract_fixture")
    raw = _sound(data, sound_id)
    if sound_id is None:
        raw["slots"][0].pop("soundId")
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "cache-sound")
    before = copy.deepcopy(data)
    assert world_storage.is_deliverable_recipe_payload(data, check_assets=False)
    delivered = world_storage.sanitize_recipe_for_delivery(data)
    assert delivered["vfxManifest"]["slots"] == data["vfxManifest"]["slots"]
    assert world_storage.is_deliverable_recipe_payload(delivered, check_assets=False)
    assert ("soundId" in delivered["vfxManifest"]["slots"][0]) is (sound_id is not None)
    for invalid in (None, "missing", "frozenRepair"):
        corrupted = copy.deepcopy(delivered)
        corrupted["vfxManifest"]["slots"][0]["soundId"] = invalid
        assert not world_storage.is_deliverable_recipe_payload(corrupted, check_assets=False)
    assert data == before


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_real_transport_never_strips_present_null_to_legacy_absence(monkeypatch, mode):
    from infini_local.core.errors import PlannerUnavailable
    from infini_local.pipelines import llm_transport
    data = _data()
    raw = _sound(data, None)
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "no sound correction"}
    sent = _offline_transport(monkeypatch, "null_sound_noop_" + mode, [raw, patch])
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", mode)
    with pytest.raises(PlannerUnavailable, match="VFX Repair did not produce"):
        vfx.attach_hybrid_vfx_manifest(data, "null-audio", llm_director=stage.call_llm_vfx_director)
    assert len(sent) == 2 and "vfxManifest" not in data
    assert raw["slots"][0]["soundId"] is None
    assert json.loads(sent[1]["messages"][1]["content"])["repairScope"]["fieldPermissions"]["slots"] == [{"slotId": "explicit_sound", "paths": ["soundId"]}]


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
    candidate.update(rendererKind="lightCue", channel="light", lane="cue", alpha=0.1)
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "delete only foreign sound field", "slotsUpsert": [candidate]}
    _offline_transport(monkeypatch, "foreign_sound_delete", [raw, patch])
    final = vfx.attach_hybrid_vfx_manifest(data, "foreign-sound", llm_director=stage.call_llm_vfx_director)
    assert final["debug"]["vfxDirectorRaw"] == accepted
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
