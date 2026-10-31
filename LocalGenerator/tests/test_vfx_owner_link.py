"""Explicit cosmetic owner→projectile connector; hand-authored offline witnesses only."""
from __future__ import annotations

import copy
import json

import pytest
from jsonschema import Draft202012Validator

import infini_local.core.vfx.contract as vfx_contract
import infini_local.core.vfx.projection as vfx_projection
import infini_local.core.vfx.validation as vfx_validation
import infini_local.pipelines.vfx.stage as vfx_stage
from infini_local.core.schema_validation import strict_schema_errors
from tests.vfx_material_fixtures import _data, _path, _sent
from tests.test_low_level_three_stage_pipeline import wire_transport


@pytest.mark.parametrize("anchor", ["mountedCenter", "frontHand"])
def test_owner_link_requires_exact_anchor_choice_on_actual_sent_schemas(anchor):
    data = _data("seek")
    raw = _owner_path(data, anchor)
    for repair in (False, True):
        schema = _sent(data, repair)["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]
        assert not strict_schema_errors(raw["slots"][0], schema)
        Draft202012Validator(schema).validate(raw["slots"][0])
    final = vfx_stage.attach_vfx_manifest(data, "chosen-owner-anchor", llm_director=lambda *_a, **_kw: raw)
    assert final["vfxManifest"]["slots"][0]["path"]["ownerAnchor"] == anchor
    assert vfx_validation.validate_vfx_manifest_wire(final)["ok"]


@pytest.mark.parametrize("choice", [None, "", "MountedCenter", "front_hand", " frontHand", True, 0])
def test_owner_link_refuses_nonexact_or_null_anchor(choice):
    data = _data("seek")
    raw = _owner_path(data, "mountedCenter")
    raw["slots"][0]["path"]["ownerAnchor"] = choice
    _assert_anchor_refused(data, raw)


def test_owner_link_refuses_missing_anchor_without_mutation():
    data = _data("seek")
    _assert_anchor_refused(data, _path(data, "ownerLink"))


@pytest.mark.parametrize("source,capability", [("anchorHistory", ""), ("beam", "beam_geometry"), ("whip", "lash_geometry")])
@pytest.mark.parametrize("choice", ["mountedCenter", "frontHand", None])
def test_other_sources_forbid_even_null_owner_anchor(source, capability, choice):
    data = _data(capability)
    raw = _path(data, source)
    raw["slots"][0]["path"]["ownerAnchor"] = choice
    _assert_anchor_refused(data, raw)


def _assert_anchor_refused(data, raw):
    before = copy.deepcopy(raw)
    for repair in (False, True):
        schema = _sent(data, repair)["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]
        assert strict_schema_errors(raw["slots"][0], schema)
        assert not Draft202012Validator(schema).is_valid(raw["slots"][0])
    assert not vfx_validation.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "refused-anchor")
    assert not vfx_validation.validate_vfx_manifest_wire(data)["ok"]
    assert raw == before


def _owner_path(data, anchor):
    raw = _path(data, "ownerLink")
    raw["slots"][0]["path"]["ownerAnchor"] = anchor
    return raw


def test_owner_link_real_builder_schema_compiler_tracer():
    data = _data("seek")
    raw = _owner_path(data, "mountedCenter")
    before = copy.deepcopy(data["runtimeProgram"])
    for repair in (False, True):
        packet = _sent(data, repair)
        surface = packet["runtimeSurfaceReadOnly" if repair else "runtimeSurface"]
        assert "ownerLink" in next(row["sources"] for row in surface["texturedPathSources"]
                                   if row["entityId"] == raw["slots"][0]["entityId"])
        schema = packet["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]
        Draft202012Validator.check_schema(schema)
        assert not strict_schema_errors(raw["slots"][0], schema)
        Draft202012Validator(schema).validate(raw["slots"][0])
    final = vfx_stage.attach_vfx_manifest(data, "explicit-owner-link", llm_director=lambda *_a, **_kw: raw)
    assert final["vfxManifest"]["slots"][0]["path"] == raw["slots"][0]["path"]
    assert vfx_validation.validate_vfx_manifest_wire(final)["ok"]
    assert final["debug"]["llmStageAccounting"]["vfxRepairCalls"] == 0
    assert data["runtimeProgram"] == before


def test_sent_director_instructions_explain_explicit_connector_without_forcing_one(monkeypatch):
    from prompt_packet_helpers import request_dossier
    from tests.test_repair_vfx_contract import _offline_transport
    from infini_local.pipelines.vfx import request as stage
    data = _data("seek")
    raw = {"schema": vfx_contract.VFX_DIRECTOR_SCHEMA, "slots": []}
    sent = _offline_transport(monkeypatch, "owner_link_guidance", [raw])
    final = vfx_stage.attach_vfx_manifest(data, "owner-link-guidance", llm_director=stage.call_llm_vfx_director)
    dossier = request_dossier(sent[0])
    semantics = dossier["runtimeVocabulary"]["rendererSemantics"]["texturedPath"]
    assert "ownerLink" in semantics and "hand" in semantics and "cosmetic" in semantics
    assert all(word in semantics for word in ("ownerAnchor", "mountedCenter", "frontHand", "compositeFrontArm.enabled", "retire"))
    assert "inventory" in semantics and "hidden" in semantics and "head-only" in semantics
    assert "explicit" in semantics and "not automatic" in semantics
    assert final["vfxManifest"]["slots"] == []


def test_actual_visual_packet_explains_owner_link_composition(wire_transport):
    from prompt_packet_helpers import request_dossier
    import infini_local.pipelines.visual.context as visual_context
    import infini_local.pipelines.visual.request as visual_request
    from tests.test_low_level_three_stage_pipeline import _accepted_visual_data
    data = _accepted_visual_data("workbench_blade")
    responses, sent = wire_transport
    responses.append({})
    visual_request._request_visual_kit(data, {}, {})
    packet = request_dossier(sent[0])
    assert packet["runtimeEntities"] == visual_context._runtime_card(data)
    assert packet["acceptedPresentationMechanicsReadOnly"]["itemUse"] == data["runtimeProgram"]["itemUse"]
    assert packet["assetModeCatalog"] == visual_request.visual_asset_mode_catalog()



@pytest.mark.parametrize("kind", ["owner_attached_projectile", "free_projectile", "stationary_projectile", "temporary_helper", "field", "child_projectile"])
def test_owner_link_surface_is_generic_registry_derived_not_a_flail_preset(kind):
    data = _data()
    entity = next(row for row in data["runtimeProgram"]["entities"] if row["kind"] != "item_body")
    entity["kind"] = kind  # VFX reads accepted kind facts, not movement/archetype.
    data.update(name="unrelated object", category="unrelated category")
    raw = _owner_path(data, "mountedCenter")
    assert vfx_validation.validate_vfx_director_output(raw, data)["ok"]
    assert "ownerLink" in next(row["sources"] for row in _sent(data, False)["runtimeSurface"]["texturedPathSources"] if row["entityId"] == entity["id"])


@pytest.mark.parametrize("field,bad", [
    ("path.source", "ownerlink"), ("path.source", "owner_link"), ("path.source", "ownerLinkFrontHand"), ("path.source", None),
    ("path.historyTicks", 2), ("path.historyTicks", True), ("path.minDistancePx", 1),
    ("path.profileDomain", "age"), ("anchor", "owner"), ("event", "on_hit"),
    ("entityId", "item"), ("path.widthPx", 97), ("path.maxSegmentLengthPx", 4097),
    ("path.texture.source", "entity"),
])
def test_owner_link_rejects_foreign_controls_at_director_schema_and_wire(field, bad):
    data = _data("seek")
    entity = next(row for row in data["runtimeProgram"]["entities"] if row["kind"] != "item_body")
    entity["visual"]["assetMode"] = "no_asset"
    raw = _owner_path(data, "mountedCenter")
    target = raw["slots"][0]
    for key in field.split(".")[:-1]:
        target = target[key]
    target[field.split(".")[-1]] = data["runtimeProgram"]["itemEntityId"] if field == "entityId" else bad
    before = copy.deepcopy(raw)
    for repair in (False, True):
        schema = _sent(data, repair)["outputSchema"]["properties"]["slotsUpsert" if repair else "slots"]["items"]
        assert strict_schema_errors(raw["slots"][0], schema), (field, bad)
        assert not Draft202012Validator(schema).is_valid(raw["slots"][0]), (field, bad)
    assert not vfx_validation.validate_vfx_director_output(raw, data)["ok"]
    data["vfxManifest"] = vfx_projection._compile_manifest(data, raw, "invalid-explicit-link")
    assert not vfx_validation.validate_vfx_manifest_wire(data)["ok"]
    assert raw == before


@pytest.mark.parametrize("broken_field,bad,good", [("widthPx", 97, 8), ("source", "ownerlink", "ownerLink")])
def test_owner_link_actual_repair_freezes_valid_design_and_mechanics(monkeypatch, broken_field, bad, good):
    from prompt_packet_helpers import request_dossier
    from tests.test_repair_vfx_contract import _offline_transport, _patch
    from infini_local.pipelines.vfx import request as stage
    data = _data("seek")
    raw = _owner_path(data, "mountedCenter")
    raw["slots"][0]["path"][broken_field] = bad
    before, mechanics = copy.deepcopy(raw), copy.deepcopy(data["runtimeProgram"])
    report = vfx_validation.validate_vfx_director_output(raw, data)
    assert not report["ok"]
    assert {row["path"] for row in report["errors"]} == {f"$.slots[0].path.{broken_field}"}
    candidate = copy.deepcopy(raw["slots"][0])
    candidate["path"].update({broken_field: good, "ownerAnchor": "frontHand", "repeatLengthPx": 512, "colorProfile": {"start": {"r": 1, "g": 2, "b": 3}, "middle": {"r": 4, "g": 5, "b": 6}, "end": {"r": 7, "g": 8, "b": 9}, "curve": "linear"}})
    if broken_field != "source":
        candidate["path"]["source"] = "beam"
    candidate.update(alpha=0.1, anchor="owner", event="on_hit")
    sent = _offline_transport(monkeypatch, "owner-link-frozen-" + broken_field, [raw, _patch(slotsUpsert=[candidate])])
    final = vfx_stage.attach_vfx_manifest(data, "owner-link-frozen", llm_director=stage.call_llm_vfx_director)
    expected = copy.deepcopy(before)
    expected["slots"][0]["path"][broken_field] = good
    assert final["debug"]["vfxDirectorRaw"] == expected
    assert request_dossier(sent[1])["repairScope"]["fieldPermissions"]["slots"] == [{"slotId": "connected_path", "paths": ["path." + ("width" if broken_field == "widthPx" else broken_field)]}]
    assert final["runtimeProgram"] == mechanics
    assert raw == before
    assert vfx_validation.validate_vfx_manifest_wire(final)["ok"]


def test_owner_link_delivery_preserves_explicit_strip_and_existing_paths(tmp_path, monkeypatch):
    from infini_local.core.runtime_authoring.capability_registry import RUNTIME_PROGRAM_API_VERSION
    from infini_local.storage import world_storage
    from infini_local.pipelines.visual import delivery as visual_delivery_gate
    from infini_local.qa.live_no_image_fixture import hydrate_no_image_fixture_assets, write_no_image_fixture_png, synthetic_no_image_execution_control
    from tests.vfx_material_fixtures import _asset
    data = _data("seek")
    data.update(id="owner_link_synthetic_witness", schemaVersion=5, runtimeApiVersion=RUNTIME_PROGRAM_API_VERSION,
                sourceMode="offline_contract_fixture")
    raw = _owner_path(data, "mountedCenter")
    raw["assets"] = [_asset("Connector", "strip")]
    raw["slots"][0]["path"]["texture"] = {"source": "asset", "assetId": "Connector", "uv": {"quarterTurns": 0, "mirrorU": False, "mirrorV": False}}
    history = _path(data)["slots"][0]
    history["id"] = "unchanged_history"
    raw["slots"].append(history)
    gameplay = copy.deepcopy(data["runtimeProgram"])
    data = vfx_stage.attach_vfx_manifest(data, "synthetic-owner-link", llm_director=lambda *_a, **_kw: raw)
    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", tmp_path)
    data["visual"] = {"preferredCanvasSize": 32}
    for entity in data["runtimeProgram"]["entities"]:
        entity["visual"]["assetMode"] = "baked_sprite" if entity["kind"] == "item_body" else "reuse_item_icon"
    # Explicitly test-only PNG hydration; no model/provider/image generation.
    fixture = write_no_image_fixture_png(tmp_path / "synthetic.png")
    hydrate_no_image_fixture_assets(data, fixture)
    data = synthetic_no_image_execution_control(data, fixture)
    before = copy.deepcopy(data)
    assert world_storage.is_deliverable_recipe_payload(data, check_assets=False)
    delivered = world_storage.sanitize_recipe_for_delivery(data)
    assert delivered["vfxManifest"]["slots"] == data["vfxManifest"]["slots"]
    assert delivered["vfxManifest"]["slots"][1]["path"] == raw["slots"][1]["path"]
    assert delivered["vfxManifest"]["assets"][0]["layout"] == "strip"
    assert delivered["vfxManifest"]["assets"][0]["prompt"] == raw["assets"][0]["prompt"]
    assert vfx_validation.validate_vfx_manifest_wire(delivered)["ok"]
    assert world_storage.is_deliverable_recipe_payload(delivered, check_assets=False)
    world_storage.write_world_recipe_cache(tmp_path, "owner-link", "owner-link", "world", data)
    cached = world_storage.read_world_recipe_cache(tmp_path, "owner-link", "v5", "owner-link", "world")
    assert cached is not None and cached["vfxManifest"]["slots"] == delivered["vfxManifest"]["slots"]
    assert data == before
    # Presentation changed only by explicit test hydration, not VFX compilation.
    for current, original in zip(data["runtimeProgram"]["entities"], gameplay["entities"]):
        assert {k: v for k, v in current.items() if k != "visual"} == {k: v for k, v in original.items() if k != "visual"}


@pytest.mark.parametrize("source,capability", [("anchorHistory", ""), ("beam", "beam_geometry"), ("whip", "lash_geometry")])
def test_existing_path_sources_compile_byte_semantics_unchanged(source, capability):
    data = _data(capability)
    raw = _path(data, source)
    assert "ownerAnchor" not in raw["slots"][0]["path"]
    authored = json.dumps(raw, sort_keys=True)
    final = vfx_stage.attach_vfx_manifest(data, "unchanged-path", llm_director=lambda *_a, **_kw: raw)
    assert json.dumps(final["vfxManifest"]["slots"][0]["path"], sort_keys=True) == json.dumps(raw["slots"][0]["path"], sort_keys=True)
    assert json.dumps(raw, sort_keys=True) == authored
    assert vfx_validation.validate_vfx_manifest_wire(final)["ok"]
