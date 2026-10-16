"""One current VFX format: local RGB, executable leaves, closed persistence."""
from __future__ import annotations

import copy

import pytest

from infini_local.core import vfx_manifest as vfx
from tests.vfx_material_fixtures import _data, _legacy


RETIRED_SLOT_FIELDS = (
    "backend", "particleRole", "jitter", "fadeIn", "fadeOut", "budgetWeight",
    "signatureWeight", "visualCost", "channel", "lane", "emissionMode",
)


def current_input(data):
    return _legacy(data)


@pytest.mark.parametrize("renderer,admitted", [("spriteStampTrail", True),
                                               ("projectileAfterimage", False), ("actorAfterimage", False)])
def test_texture_history_has_one_current_renderer_without_alias_translation(renderer, admitted):
    from infini_local.core.schema_validation import strict_schema_errors
    from tests.test_vfx_dependency_delivery_contracts import visual_data, authored_vfx

    data = visual_data("reuse_item_icon")
    raw = authored_vfx(renderer)
    before = copy.deepcopy(raw)
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"] is admitted
    if not admitted:
        assert {row["path"] for row in report["errors"]} == {"$.slots[0].rendererKind"}
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": raw["slots"], "note": "exact renderer"}
    assert (not strict_schema_errors(patch, vfx.vfx_repair_schema(data))) is admitted
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "texture-history")
    assert data["vfxManifest"]["slots"][0]["rendererKind"] == renderer
    report = vfx.validate_vfx_manifest_wire(data)
    assert report["ok"] is admitted
    if not admitted:
        assert {row["path"] for row in report["errors"]} == {"$.vfxManifest.slots[0].rendererKind"}
    assert raw == before


@pytest.mark.parametrize("renderer", [r for r in vfx._RENDERERS if r not in vfx.SPRITE_TEXTURE_RENDERERS])
def test_non_sprite_renderers_forbid_common_texture_selector_across_boundaries(renderer):
    from infini_local.core.schema_validation import strict_schema_errors
    from tests.test_vfx_material_admission_contracts import _renderer_material
    from tests.test_low_level_three_stage_pipeline import _accepted_visual_data

    data = _accepted_visual_data("workbench_blade")
    raw = _renderer_material(data, renderer)
    raw["slots"][0].pop("textureRole", None)
    before = copy.deepcopy(raw)
    assert vfx.validate_vfx_director_output(raw, data)["ok"]
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": raw["slots"], "note": "exact selector owner"}
    assert not strict_schema_errors(patch, vfx.vfx_repair_schema(data))
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "no-common-texture-selector")
    assert vfx.validate_vfx_manifest_wire(data)["ok"]
    assert "textureRole" not in data["vfxManifest"]["slots"][0]
    assert raw == before
    for value in ("none", "item", "entity", "impact", None):
        invalid = copy.deepcopy(raw)
        invalid["slots"][0]["textureRole"] = value
        assert not vfx.validate_vfx_director_output(invalid, data)["ok"]
        patch["slotsUpsert"] = invalid["slots"]
        assert strict_schema_errors(patch, vfx.vfx_repair_schema(data))
        data["vfxManifest"] = vfx._compile_manifest(data, invalid, "foreign-selector")
        assert not vfx.validate_vfx_manifest_wire(data)["ok"]


@pytest.mark.parametrize("renderer,unused", [
    ("lightCue", {"alpha", "blend", "layer", "duration", "spread", "particleSystemId", "textureRole"}),
    ("impactSprite", {"spread", "particleSystemId"}),
    ("childMotes", {"alpha", "blend", "layer", "duration"}),
])
def test_light_and_impact_forbid_always_unconsumed_fields(renderer, unused):
    from tests.test_vfx_dependency_delivery_contracts import visual_data, authored_vfx
    from infini_local.core.schema_validation import strict_schema_errors

    data = visual_data("reuse_item_icon")
    raw = authored_vfx(renderer, "impact" if renderer == "impactSprite" else "none")
    foreign = {field: raw["slots"][0].pop(field, {"alpha": 1, "blend": "alpha", "layer": "BeforeProjectiles", "duration": 10, "spread": 0, "particleSystemId": "none", "textureRole": "none"}[field]) for field in unused}
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "only-executed-controls")
    assert vfx.validate_vfx_manifest_wire(data)["ok"]
    for field, value in foreign.items():
        candidate = copy.deepcopy(raw)
        candidate["slots"][0][field] = value
        assert not vfx.validate_vfx_director_output(candidate, data)["ok"], field
        patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": candidate["slots"], "note": "foreign control"}
        assert strict_schema_errors(patch, vfx.vfx_repair_schema(data)), field


@pytest.mark.parametrize("renderer", ["lightCue", "impactSprite"])
@pytest.mark.parametrize("item,periodic,repeat", [(True, False, 0), (False, False, 0),
                                                (True, True, 0), (True, True, 3),
                                                (False, True, 0), (False, True, 3)])
def test_light_and_impact_cadence_fields_exist_only_at_native_read_sites(renderer, item, periodic, repeat):
    from infini_local.core.schema_validation import strict_schema_errors
    from tests.test_vfx_dependency_delivery_contracts import visual_data, authored_vfx

    data = visual_data("reuse_item_icon")
    raw = authored_vfx(renderer, "impact")
    slot = raw["slots"][0]
    slot.update(entityId="item" if item else "orb", event="periodic" if periodic else "on_use" if item else "on_hit")
    for field in ("startTick", "repeatEvery", "density"):
        slot.pop(field, None)
    if periodic:
        slot["repeatEvery"] = repeat
        if not item:
            slot["startTick"] = 2
            if repeat == 0:
                slot["density"] = 0.37
    before = copy.deepcopy(raw)
    assert vfx.validate_vfx_director_output(raw, data)["ok"]
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": raw["slots"], "note": "consumed cadence only"}
    assert not strict_schema_errors(patch, vfx.vfx_repair_schema(data))
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "cadence-presence")
    assert vfx.validate_vfx_manifest_wire(data)["ok"]
    assert raw == before
    for field in ("startTick", "repeatEvery", "density"):
        mutation = copy.deepcopy(raw)
        if field in slot:
            mutation["slots"][0].pop(field)
        else:
            mutation["slots"][0][field] = 0
        report = vfx.validate_vfx_director_output(mutation, data)
        assert not report["ok"], field
        assert {row["path"] for row in report["errors"]} == {f"$.slots[0].{field}"}
        patch["slotsUpsert"] = mutation["slots"]
        assert strict_schema_errors(patch, vfx.vfx_repair_schema(data)), field
        data["vfxManifest"] = vfx._compile_manifest(data, mutation, "invalid-cadence-presence")
        assert not vfx.validate_vfx_manifest_wire(data)["ok"], field


def test_current_rgb_survives_director_compile_and_persisted_gate():
    data = _data()
    raw = current_input(data)
    report = vfx.validate_vfx_director_output(raw, data)
    assert report["ok"], report["errors"]
    final = vfx.attach_vfx_manifest(data, "rgb-contract", llm_director=lambda *_a, **_kw: raw)
    manifest = final["vfxManifest"]
    assert manifest["schema"] == "infini.vfx.runtime-events.v16"
    assert raw["schema"] == "infini.vfx-director.runtime-events.v3"
    assert manifest["slots"][0]["color"] == raw["slots"][0]["color"]
    assert set(manifest) == {"schema", "recipeId", "budget", "slots"}
    assert set(manifest["budget"]) == {"maxParticlesPerTick", "maxParticlesTotal", "maxDrawCalls"}
    assert vfx.validate_vfx_manifest_wire(final)["ok"]
    for field in RETIRED_SLOT_FIELDS:
        assert field not in manifest["slots"][0]


@pytest.mark.parametrize("value", ["cyan", "effect", {"r": True, "g": 1, "b": 2},
                                   {"r": 256, "g": 1, "b": 2}, {"r": 1.0, "g": 1, "b": 2},
                                   {"r": 1, "g": 1, "b": 2, "a": 255}])
def test_color_rejects_tokens_noninteger_and_alpha(value):
    data = _data()
    raw = current_input(data)
    raw["slots"][0]["color"] = value
    assert not vfx.validate_vfx_director_output(raw, data)["ok"]


def test_persisted_gate_rejects_retired_fields_for_simple_renderers():
    data = _data()
    raw = current_input(data)
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "strict-current")
    assert vfx.validate_vfx_manifest_wire(data)["ok"]
    for field in (*RETIRED_SLOT_FIELDS, "bakedCommands", "effectName", "eventGroup", "stage", "source"):
        mutation = copy.deepcopy(data)
        mutation["vfxManifest"]["slots"][0][field] = [] if field == "bakedCommands" else "retired"
        assert not vfx.validate_vfx_manifest_wire(mutation)["ok"], field
    for field in ("motif", "effectMagnitude", "visualBudgetClass", "debug", "playbackMode"):
        mutation = copy.deepcopy(data)
        mutation["vfxManifest"][field] = "retired"
        assert not vfx.validate_vfx_manifest_wire(mutation)["ok"], field


@pytest.mark.parametrize("renderer", ["spriteElement", "texturedPath", "libraryParticle", "screenShakeCue", "soundCue"])
def test_nested_color_owners_and_nonvisual_cues_forbid_common_color(renderer):
    from tests.vfx_material_fixtures import _sprite, _path
    from tests.test_vfx_material_admission_contracts import _library_particle, _screen_shake
    from tests.test_vfx_sound_selection import _sound

    data = _data()
    raw = {"spriteElement": _sprite, "texturedPath": _path, "libraryParticle": _library_particle,
           "screenShakeCue": _screen_shake, "soundCue": _sound}[renderer](data)
    assert vfx.validate_vfx_director_output(raw, data)["ok"]
    assert "color" not in raw["slots"][0]
    raw["slots"][0]["color"] = {"r": 1, "g": 2, "b": 3}
    report = vfx.validate_vfx_director_output(raw, data)
    assert {row["path"] for row in report["errors"]} == {"$.slots[0].color"}
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "foreign-color")
    assert not vfx.validate_vfx_manifest_wire(data)["ok"]


def test_rgb_component_repair_is_exact_and_preserves_other_channels_profiles_and_resources():
    from tests.vfx_material_fixtures import _with_asset

    data = _data()
    accepted = _with_asset(data)
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["element"]["colorProfile"]["middle"]["g"] = 256
    report = vfx.validate_vfx_director_output(raw, data)
    scope = vfx._build_vfx_repair_scope(raw, report["errors"])
    assert scope["fieldPermissions"] == {"globals": {}, "slots": [
        {"slotId": "ingredient_element", "paths": ["element.colorProfile.middle.g"]}], "assets": []}
    candidate = copy.deepcopy(accepted["slots"][0])
    candidate["element"]["colorProfile"]["middle"].update(r=0, b=0)
    candidate["element"]["colorProfile"]["curve"] = "easeIn"
    candidate["element"]["opacityProfile"]["middle"] = 0
    candidate["element"]["texture"] = {"source": "item", "assetId": ""}
    patch = {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": [candidate],
             "assetsUpsert": [{**accepted["assets"][0], "prompt": "unrequested new artwork"}],
             "note": "only green channel is invalid"}
    replies = iter([raw, patch])
    final = vfx.attach_vfx_manifest(data, "rgb-leaf-repair", llm_director=lambda *_a, **_kw: next(replies))
    assert final["debug"]["vfxDirectorRaw"] == accepted
    assert final["debug"]["vfxRepairFilterAudit"]["acceptedPaths"] == ["$.slotsUpsert[0].element.colorProfile.middle.g"]
    assert vfx.validate_vfx_manifest_wire(final)["ok"]


@pytest.mark.parametrize("renderer", [renderer for renderer in vfx.vfx_director_surface(_data())["rendererKind"]
                                      if renderer not in {"spriteElement", "texturedPath", "libraryParticle", "screenShakeCue", "soundCue"}])
def test_every_simple_visible_renderer_requires_explicit_rgb(renderer):
    from tests.test_vfx_material_admission_contracts import _renderer_material
    from tests.test_low_level_three_stage_pipeline import _accepted_visual_data

    data = _accepted_visual_data("workbench_blade")
    raw = _renderer_material(data, renderer)
    assert vfx.validate_vfx_director_output(raw, data)["ok"]
    raw["slots"][0].pop("color")
    report = vfx.validate_vfx_director_output(raw, data)
    assert {error["path"] for error in report["errors"]} == {"$.slots[0].color"}
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "missing-local-rgb")
    assert not vfx.validate_vfx_manifest_wire(data)["ok"]


def test_persisted_impact_producers_remain_unique_per_entity():
    data = _data()
    raw = current_input(data)
    slot = raw["slots"][0]
    slot.update(rendererKind="impactSprite", textureRole="impact", spriteCanvasSize=32, spritePrompt="one exact impact", spriteNegativePrompt="")
    raw["slots"].append({**copy.deepcopy(slot), "id": "duplicate_producer"})
    data["vfxManifest"] = vfx._compile_manifest(data, raw, "duplicate-impact")
    assert not vfx.validate_vfx_manifest_wire(data)["ok"]


@pytest.mark.parametrize("retired,current,repair", [
    ("infini.vfx-director.runtime-events.v2", vfx.VFX_DIRECTOR_SCHEMA, False),
    ("infini.vfx-repair-patch.runtime-events.v1", vfx.VFX_REPAIR_PATCH_SCHEMA, True),
])
def test_only_current_director_and_repair_schema_ids_are_admitted(retired, current, repair):
    from infini_local.core.schema_validation import strict_schema_errors

    data = _data()
    raw = {"schema": current, "note": "no edits"} if repair else current_input(data)
    schema = vfx.vfx_repair_schema(data) if repair else vfx.vfx_director_schema(data)
    assert not strict_schema_errors(raw, schema)
    raw["schema"] = retired
    assert strict_schema_errors(raw, schema)
