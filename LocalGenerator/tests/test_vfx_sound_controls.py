"""Explicit sound controls survive the real VFX boundary and frozen Repair."""
from __future__ import annotations

import copy
import json

import pytest

from infini_local.core import vfx_manifest as vfx
from infini_local.core.errors import PlannerUnavailable
from infini_local.pipelines import llm_authoring_pipeline as stage
from tests.test_repair_vfx_contract import _offline_transport
from tests.test_vfx_sound_selection import _sound, _INVENTORY, SOUND_IDS
from tests.vfx_material_fixtures import _data, _legacy


def test_palette_restores_every_historical_sample_and_keeps_every_recent_sample():
    historical = set(_INVENTORY["historicalCatalog"].values())
    preceding = set(_INVENTORY["precedingCatalog"])
    assert len(_INVENTORY["historicalCatalog"]) == 92
    assert len(historical) == 71 and len(preceding) == 20
    assert len(historical & preceding) == 7
    assert len(SOUND_IDS) == len(set(SOUND_IDS)) == 84
    assert historical | preceding == set(vfx.vfx_director_surface(_data())["soundId"])


@pytest.mark.parametrize("controls", [
    {"volume": 0, "pitch": 0, "pitchVariance": 0},
    {"volume": 1, "pitch": -0.9, "pitchVariance": 0.2},
    {"volume": 0.13, "pitch": 0.9, "pitchVariance": 0},
    {"volume": 0.71, "pitch": 0.7, "pitchVariance": 0.6},
    {"volume": 0.6, "pitch": -0.7, "pitchVariance": 0.6},
])
def test_exact_controls_reach_source_receipts_wire_and_cache_without_alpha_coupling(controls):
    from infini_local.storage import world_storage
    data = _data()
    raw = _sound(data, "Item26")
    raw["slots"][0].update(alpha=0.01, sound=controls)
    before = copy.deepcopy(raw)
    final = vfx.attach_hybrid_vfx_manifest(data, "sound-controls", llm_director=lambda *_args, **_kwargs: raw)
    assert final["vfxManifest"]["slots"][0]["sound"] == controls
    assert final["vfxManifest"]["slots"][0]["alpha"] == 0.01
    assert raw == before and vfx.validate_vfx_manifest_wire(final)["ok"]
    receipts = final["debug"]["vfxSoundReceipts"]
    assert len(receipts) == 4
    assert {row["finalPath"] for row in receipts} == {
        "vfxManifest.slots[0].soundId", "vfxManifest.slots[0].sound.volume",
        "vfxManifest.slots[0].sound.pitch", "vfxManifest.slots[0].sound.pitchVariance",
    }
    assert vfx.audit_vfx_sound_projection(raw, final["vfxManifest"], receipts)["ok"]
    delivered = world_storage.sanitize_recipe_for_delivery(final)
    assert delivered["vfxManifest"]["slots"][0]["sound"] == controls
    assert vfx.validate_vfx_manifest_wire(delivered)["ok"]


@pytest.mark.parametrize("field,value", [
    ("volume", -0.01), ("volume", 1.01), ("volume", None), ("volume", True),
    ("volume", "0.4"), ("volume", {}), ("volume", []), ("volume", float("nan")),
    ("pitch", -0.91), ("pitch", 0.91), ("pitch", None), ("pitch", False),
    ("pitch", float("inf")), ("pitchVariance", -0.1), ("pitchVariance", 0.61),
    ("pitchVariance", None), ("pitchVariance", True), ("pitchVariance", "native"),
])
def test_invalid_sound_scalar_is_strict_and_repairs_only_its_own_leaf(field, value):
    data = _data()
    raw = _sound(data)
    raw["slots"][0]["sound"][field] = value
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert {row["path"] for row in report["errors"]} == {f"$.slots[0].sound.{field}"}
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    assert scope["fieldPermissions"]["slots"] == [{"slotId": "explicit_sound", "paths": [f"sound.{field}"]}]
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "invalid-sound-scalar")
    assert not vfx.validate_vfx_manifest_wire(data)["ok"]


@pytest.mark.parametrize("bad", [None, {}, [], "native", True])
def test_present_sound_container_never_becomes_legacy_absence(bad):
    data = _data()
    raw = _sound(data)
    raw["slots"][0]["sound"] = bad
    assert not vfx.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "invalid-sound-object")
    assert not vfx.validate_vfx_manifest_wire(data)["ok"]
    assert "sound" in data["vfxManifest"]["slots"][0]


@pytest.mark.parametrize("missing", ["volume", "pitch", "pitchVariance"])
def test_each_control_is_required_inside_both_fresh_and_persisted_presence(missing):
    data = _data()
    raw = _sound(data)
    del raw["slots"][0]["sound"][missing]
    report = vfx.validate_vfx_director_output(raw, data)
    assert {row["path"] for row in report["errors"]} == {f"$.slots[0].sound.{missing}"}
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "partial-sound")
    assert not vfx.validate_vfx_manifest_wire(data)["ok"]


def test_fresh_absence_requires_sound_but_saved_selector_and_phase_stay_unchanged():
    data = _data()
    raw = _sound(data, "Item169")
    del raw["slots"][0]["sound"]
    report = vfx.validate_vfx_director_output(raw, data)
    assert {row["path"] for row in report["errors"]} == {"$.slots[0].sound"}
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "persisted-sound")
    slot = data["vfxManifest"]["slots"][0]
    slot["phaseOffset"] = -0.75
    before = copy.deepcopy(data)
    assert vfx.validate_vfx_manifest_wire(data)["ok"]
    assert data == before and "sound" not in slot
    slot["sound"] = {"volume": 0.4, "pitch": 0, "pitchVariance": 0}
    del slot["soundId"]
    assert not vfx.validate_vfx_manifest_wire(data)["ok"]


def test_interval_relation_only_thaws_variance_and_never_chooses_a_new_pitch():
    data = _data()
    raw = _sound(data)
    raw["slots"][0]["sound"].update(pitch=0.9, pitchVariance=0.6)
    report = vfx.validate_vfx_director_output(raw, data)
    assert {row["path"] for row in report["errors"]} == {"$.slots[0].sound.pitchVariance"}
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["sound"].update(volume=0.9, pitch=-0.5, pitchVariance=0.2)
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "narrow interval", "slotsUpsert": [candidate]}
    merged, audit = vfx._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    assert audit["ok"]
    assert merged["slots"][0]["sound"] == {"volume": 0.37, "pitch": 0.9, "pitchVariance": 0.2}
    assert vfx.validate_vfx_director_output(merged, data)["ok"]


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("missing_container", [False, True])
def test_actual_repair_transport_restores_only_sound_scope_and_keeps_other_choices(monkeypatch, mode, missing_container):
    from infini_local.pipelines import llm_transport
    data = _data()
    accepted = _sound(data, "Item152")
    raw = copy.deepcopy(accepted)
    if missing_container:
        del raw["slots"][0]["sound"]
    else:
        raw["slots"][0]["sound"]["volume"] = 2
    candidate = copy.deepcopy(accepted["slots"][0])
    candidate.update(soundId="Item26", alpha=0.9, entityId=data["runtimeProgram"]["entities"][1]["id"], event="on_kill")
    if not missing_container:
        candidate["sound"].update(pitch=0.7, pitchVariance=0.6)
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "restore diagnosed sound choices", "slotsUpsert": [candidate]}
    sent = _offline_transport(monkeypatch, "sound_controls_" + mode + str(missing_container), [raw, patch])
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", mode)
    final = vfx.attach_hybrid_vfx_manifest(data, "sound-control-repair", llm_director=stage.call_llm_vfx_director)
    assert final["debug"]["vfxDirectorRaw"] == accepted
    assert final["debug"]["vfxRepairFilterAudit"]["acceptedPaths"] == [
        "$.slotsUpsert[0].sound" if missing_container else "$.slotsUpsert[0].sound.volume"]
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    assert len(sent) == 2
    director, repair = [json.loads(row["messages"][1]["content"]) for row in sent]
    assert director["runtimeVocabulary"]["sound"] == repair["runtimeVocabularyReadOnly"]["sound"] == vfx._sound_schema()


@pytest.mark.parametrize("renderer", ["impactRing", "lightCue", "childMotes"])
def test_foreign_sound_object_can_only_be_deleted_without_changing_renderer(renderer):
    data = _data()
    accepted = _legacy(data)
    accepted["slots"][0]["rendererKind"] = renderer
    if renderer == "lightCue":
        accepted["slots"][0].update(channel="light", lane="cue")
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["sound"] = {"volume": 1, "pitch": 0, "pitchVariance": 0}
    # Unknown branch payload is the error; its presence must not require a new sample.
    raw["slots"][0]["soundId"] = "Item26"
    report = vfx.validate_vfx_director_output(raw, data)
    assert {row["path"] for row in report["errors"]} == {"$.slots[0].sound", "$.slots[0].soundId"}
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "remove foreign audio", "slotsUpsert": [accepted["slots"][0]]}
    merged, audit = vfx._apply_vfx_repair_patch(data, raw, patch, scope, return_audit=True)
    assert audit["ok"] and merged == accepted
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "foreign-sound")
    assert not vfx.validate_vfx_manifest_wire(data)["ok"]


@pytest.mark.parametrize("mutation", ["missing_receipt", "wrong_value", "wrong_source", "duplicate", "retarget", "hidden_volume", "absent_to_default"])
def test_source_backed_projection_audit_rejects_silent_changes(mutation):
    data = _data()
    raw = _sound(data)
    manifest = vfx._compile_manifest(data, raw, "audit-sound")
    receipts = vfx._sound_projection_receipts(raw)
    if mutation == "missing_receipt":
        receipts.pop()
    elif mutation == "wrong_value":
        receipts[1]["value"] = 0.999
    elif mutation == "wrong_source":
        receipts[1]["authoredPath"] = "slots[0].alpha"
    elif mutation == "duplicate":
        receipts.append(copy.deepcopy(receipts[0]))
    elif mutation == "retarget":
        manifest["slots"][0]["event"] = "on_kill"
    elif mutation == "hidden_volume":
        manifest["slots"][0]["sound"]["volume"] = 0.65
    else:
        del raw["slots"][0]["sound"]
        receipts = vfx._sound_projection_receipts(raw)
    assert not vfx.audit_vfx_sound_projection(raw, manifest, receipts)["ok"]


def test_identity_receipts_do_not_alias_json_boolean_and_number():
    data = _data()
    raw = _sound(data)
    raw["slots"][0]["sound"]["volume"] = 1
    manifest = vfx._compile_manifest(data, raw, "typed-sound-receipt")
    receipts = vfx._sound_projection_receipts(raw)
    next(row for row in receipts if row["authoredPath"].endswith("sound.volume"))["value"] = True
    assert not vfx.audit_vfx_sound_projection(raw, manifest, receipts)["ok"]
    receipts = vfx._sound_projection_receipts(raw)
    manifest["slots"][0]["sound"]["volume"] = True
    assert not vfx.audit_vfx_sound_projection(raw, manifest, receipts)["ok"]


def test_unrelated_repair_cannot_unmute_explicit_zero_volume(monkeypatch):
    data = _data()
    accepted = _sound(data)
    accepted["slots"][0]["sound"]["volume"] = 0
    raw = copy.deepcopy(accepted)
    raw["effectMagnitude"] = 2
    hostile = copy.deepcopy(accepted["slots"][0])
    hostile["sound"]["volume"] = 1
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "repair magnitude", "effectMagnitude": accepted["effectMagnitude"], "slotsUpsert": [hostile]}
    _offline_transport(monkeypatch, "sound-frozen-zero", [raw, patch])
    final = vfx.attach_hybrid_vfx_manifest(data, "sound-frozen-zero", llm_director=stage.call_llm_vfx_director)
    assert final["debug"]["vfxDirectorRaw"] == accepted
    assert final["vfxManifest"]["slots"][0]["sound"]["volume"] == 0
    assert final["debug"]["vfxRepairFilterAudit"]["acceptedPaths"] == ["$.effectMagnitude"]


@pytest.mark.parametrize("valid_fix", [False, True])
def test_frozen_out_of_bounds_numeric_attempt_is_ignored_before_strict_mutable_validation(monkeypatch, valid_fix):
    data = _data()
    accepted = _sound(data)
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["sound"]["volume"] = 2
    candidate = copy.deepcopy(accepted["slots"][0])
    candidate["sound"].update(volume=0.37 if valid_fix else 2, pitch=99, pitchVariance=99)
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "fix volume while leaving other choices frozen", "slotsUpsert": [candidate]}
    sent = _offline_transport(monkeypatch, "sound-numeric-frozen-" + str(valid_fix), [raw, patch])
    if valid_fix:
        final = vfx.attach_hybrid_vfx_manifest(data, "sound-numeric-frozen", llm_director=stage.call_llm_vfx_director)
        assert final["debug"]["vfxDirectorRaw"] == accepted
        audit = final["debug"]["vfxRepairFilterAudit"]
        assert audit["acceptedPaths"] == ["$.slotsUpsert[0].sound.volume"]
        assert {row["path"] for row in audit["ignoredChanges"]} == {"$.slotsUpsert[0].sound.pitch", "$.slotsUpsert[0].sound.pitchVariance"}
    else:
        with pytest.raises(PlannerUnavailable, match="VFX Repair did not produce"):
            vfx.attach_hybrid_vfx_manifest(data, "sound-numeric-frozen", llm_director=stage.call_llm_vfx_director)
        assert "vfxManifest" not in data
    assert len(sent) == 2


@pytest.mark.parametrize("bad", [True, "0", None])
def test_repair_still_rejects_structurally_invalid_numeric_types(bad):
    data = _data()
    raw = _sound(data)
    raw["slots"][0]["sound"]["volume"] = 2
    scope = vfx._build_vfx_repair_scope(raw, vfx.validate_vfx_director_output(raw, data)["errors"])
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["sound"]["volume"] = bad
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "note": "bad typed correction", "slotsUpsert": [candidate]}
    _filtered, report = vfx._filter_vfx_repair_patch(data, raw, patch, scope)
    assert not report["ok"]
    assert any(row["path"] == "$.slotsUpsert[0].sound.volume" for row in report["errors"])


def test_sound_dto_grammar_exposes_every_authored_control_and_no_other_design():
    from infini_local.qa.primitive_loss_audit import _MODEL_ROOT, _class_properties
    source = (_MODEL_ROOT / "Common/Models/VfxSoundSpec.cs").read_bytes()
    declared = {key[0].upper() + key[1:] for key in vfx._sound_schema()["properties"]}
    assert _class_properties(source, "VfxSoundSpec") == declared
    mutant = source.replace(b"public sealed class VfxSoundSpec\n{", b"public sealed class VfxSoundSpec\n{\npublic bool RouteFromWeaponName { get; set; }")
    assert _class_properties(mutant, "VfxSoundSpec") - declared == {"RouteFromWeaponName"}


def test_actual_vfx_attachment_refuses_a_mutated_compiler_projection(monkeypatch):
    data = _data()
    raw = _sound(data)
    compile_manifest = vfx._compile_manifest

    def corrupt(*args, **kwargs):
        manifest = compile_manifest(*args, **kwargs)
        manifest["slots"][0]["sound"]["volume"] = 0.9
        return manifest

    monkeypatch.setattr(vfx, "_compile_manifest", corrupt)
    with pytest.raises(PlannerUnavailable, match="sound projection lost"):
        vfx.attach_hybrid_vfx_manifest(data, "refuse-corrupt-sound", llm_director=lambda *_args, **_kwargs: raw)
    assert "vfxManifest" not in data
