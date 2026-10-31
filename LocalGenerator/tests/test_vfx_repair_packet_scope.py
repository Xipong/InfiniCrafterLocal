"""Scope grammar is exercised through real VFX sender requests, without a model."""
from __future__ import annotations

import copy
import json

import pytest

import infini_local.core.vfx.contract as vfx_contract
import infini_local.core.vfx.repair as vfx_repair
import infini_local.core.vfx.schema as vfx_schema
import infini_local.core.vfx.validation as vfx_validation
import infini_local.pipelines.vfx.prompt as vfx_prompt
import infini_local.pipelines.vfx.stage as vfx_stage
from infini_local.core.schema_validation import strict_schema_errors
from infini_local.core.vfx.materials import vfx_model_payload
from infini_local.pipelines.vfx import request as stage
from prompt_packet_helpers import request_dossier
from test_low_level_three_stage_pipeline import _accepted_visual_data, wire_transport
from vfx_material_fixtures import _shape, _native, _sprite, _with_asset


def _send_repair(wire_transport, data, raw, patch, parent=None):
    responses, sent = wire_transport
    responses.extend([raw, patch])
    result = vfx_stage.attach_vfx_manifest(data, "scope-path", parent, parent, llm_director=stage.call_llm_vfx_director)
    return result, request_dossier(sent[1])


def test_diagnosed_foreign_payload_is_omittable_in_request_grammar(wire_transport):
    data = _accepted_visual_data("workbench_blade")
    accepted = _shape(data)
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["element"] = _sprite(data)["slots"][0]["element"]
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "note": "delete foreign payload", "slotsUpsert": accepted["slots"]}
    result, packet = _send_repair(wire_transport, data, raw, patch)
    assert result["debug"]["vfxDirectorRaw"] == accepted
    assert not strict_schema_errors(vfx_model_payload(patch), packet["outputSchema"])
    assert "element" not in packet["outputSchema"]["properties"]["slotsUpsert"]["items"]["properties"]



@pytest.mark.parametrize("foreign_key", ["x.y", "", "r[0]", 'a"b'])
def test_nested_literal_foreign_member_is_omittable_without_thawing_color(wire_transport, foreign_key):
    from infini_local.core.repair_merge import json_path_child

    data = _accepted_visual_data("workbench_blade")
    accepted = _native(data)
    assert vfx_validation.validate_vfx_director_output(accepted, data)["ok"]
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["color"][foreign_key] = 1
    before = copy.deepcopy(raw)
    report = vfx_validation.validate_vfx_director_output(raw, data)
    path = json_path_child("$.slots[0].color", foreign_key)
    assert {error["path"] for error in report["errors"]} == {path}
    scope = vfx_repair._build_vfx_repair_scope(raw, report["errors"])
    relative = json_path_child("color", foreign_key)
    assert scope["fieldPermissions"]["slots"] == [{
        "slotId": accepted["slots"][0]["id"], "paths": [relative], "deletePaths": [relative],
    }]
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "note": "omit exact foreign color member",
             "slotsUpsert": accepted["slots"]}
    result, packet = _send_repair(wire_transport, data, raw, patch)
    assert result["debug"]["vfxDirectorRaw"] == accepted
    assert vfx_validation.validate_vfx_manifest_wire(result)["ok"]
    schema = packet["outputSchema"]
    assert not strict_schema_errors(vfx_model_payload(patch), schema)
    assert strict_schema_errors(vfx_model_payload(dict(patch, slotsUpsert=raw["slots"])), schema)
    hostile = copy.deepcopy(patch)
    hostile["slotsUpsert"][0]["color"]["r"] = 18
    assert strict_schema_errors(vfx_model_payload(hostile), schema)
    repaired, audit = vfx_repair._apply_vfx_repair_patch(data, raw, hostile, scope, return_audit=True)
    assert repaired == accepted and audit["ignoredChanges"]
    assert vfx_validation.validate_vfx_director_output(repaired, data)["ok"]
    assert raw == before


@pytest.mark.parametrize("leaf,bad,good", [
    ("element.count", True, 2), ("duration", 121, 20), ("color.r", 256, 17),
    ("element.widthProfile.middle", True, 1.0),
])
def test_exact_leaf_grammar_uses_canonical_limits_and_exact_frozen_companions(wire_transport, leaf, bad, good):
    data = _accepted_visual_data("workbench_blade")
    accepted = _native(data) if leaf.startswith("color.") else _sprite(data)
    raw = copy.deepcopy(accepted)
    node = raw["slots"][0]
    for part in leaf.split(".")[:-1]:
        node = node[part]
    node[leaf.split(".")[-1]] = bad
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "note": "exact leaf", "slotsUpsert": accepted["slots"]}
    result, packet = _send_repair(wire_transport, data, raw, patch)
    schema = packet["outputSchema"]
    assert not strict_schema_errors(vfx_model_payload(patch), schema)
    assert strict_schema_errors(vfx_model_payload(dict(patch, slotsUpsert=raw["slots"])), schema)
    assert result["debug"]["vfxDirectorRaw"] == accepted
    assert leaf in packet["repairScope"]["fieldPermissions"]["slots"][0]["paths"]
    node = schema["properties"]["slotsUpsert"]["items"]
    canonical = vfx_schema.vfx_director_schema(data)["properties"]["slots"]["items"]
    for part in leaf.split("."):
        node, canonical = node["properties"][part], canonical["properties"][part]
    assert node == canonical
    assert "soundId" not in json.dumps(schema)


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_actual_http_sender_carries_scoped_grammar_for_all_provider_routes(mode):
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    from tools.diagnostics.measure_llm_request_sizes import COHORT, ROUTES, OfflineCapture, dossier
    with OfflineCapture(root) as capture:
        request, evidence = capture.builder("vfx_repair", COHORT[0], mode)
        expected = dossier(request)["outputSchema"]
        assert set(expected["properties"]) == {"schema", "note", "slotsUpsert"}
        for route in ROUTES:
            wire = capture.wire(request, route)
            assert wire["method"] == "POST" and json.loads(wire["body"]) == wire["packet"]
            wrapper = wire["packet"].get("response_format", wire["packet"].get("text", {}).get("format"))
            actual_schema = wrapper.get("json_schema", wrapper).get("schema")
            assert actual_schema == (expected if mode == "json_schema" else None)


def test_new_frozen_literals_have_entailed_types_and_closed_nested_shape(wire_transport, monkeypatch):
    monkeypatch.setattr(stage, "llm_json_response_format", lambda name, **kw: {
        "type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": kw["schema"]},
    })
    data = _accepted_visual_data("workbench_blade")
    accepted = _sprite(data)
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["alpha"] = 2
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "note": "typed frozen companions", "slotsUpsert": accepted["slots"]}
    result, packet = _send_repair(wire_transport, data, raw, patch)
    assert result["debug"]["vfxDirectorRaw"] == accepted
    schema = packet["outputSchema"]
    assert wire_transport[1][1]["response_format"]["json_schema"]["schema"] == schema
    row = schema["properties"]["slotsUpsert"]["items"]
    assert row["properties"]["duration"] == {"type": "integer", "const": 20}
    assert row["properties"]["rendererKind"] == {"type": "string", "const": "spriteElement"}
    element = row["properties"]["element"]
    assert element["type"] == "object" and element["const"] == vfx_model_payload(accepted)["slots"][0]["element"]
    assert element["additionalProperties"] is False
    assert element["properties"]["width"] == {"type": "number", "const": 12.0}
    color = element["properties"]["colorProfile"]["properties"]["middle"]
    assert color["additionalProperties"] is False
    assert set(color["required"]) == set(color["properties"]) == {"r", "g", "b"}
    assert color["properties"] == {name: {"type": "integer", "const": value}
                                   for name, value in accepted["slots"][0]["element"]["colorProfile"]["middle"].items()}
    assert not strict_schema_errors(vfx_model_payload(patch), schema)
    assert strict_schema_errors(vfx_model_payload(dict(patch, slotsUpsert=raw["slots"])), schema)


@pytest.mark.parametrize("value,expected_type", [(True, "boolean"), (None, "null"), (1, "integer"), (1.5, "number"), ("text", "string")])
def test_frozen_literal_types_follow_json_source_values(value, expected_type):
    canonical = {"type": "object", "additionalProperties": False,
                 "properties": {"frozen": {}, "editable": {"type": "number"}}, "required": ["frozen", "editable"]}
    source = {"frozen": value, "editable": 2}
    scoped = vfx_repair._vfx_repair_row_schema(canonical, source, ["editable"], [])
    literal = scoped["properties"]["frozen"]
    assert literal == {"type": expected_type, "const": value}
    assert not strict_schema_errors({"frozen": value, "editable": 1}, scoped)
    assert canonical["properties"]["frozen"] == {}


@pytest.mark.parametrize("value", [[1, "a", {"nested": True}], []])
def test_frozen_array_literals_keep_typed_items_and_exact_order(value):
    schema = vfx_repair._vfx_frozen_literal_schema(value)
    assert schema["type"] == "array" and schema["const"] == value
    assert schema["minItems"] == schema["maxItems"] == len(value)
    assert schema["items"]
    assert not strict_schema_errors(value, schema)
    assert strict_schema_errors([*value, None], schema)
    if value:
        assert strict_schema_errors(list(reversed(value)), schema)


def test_indexed_scope_preserves_canonical_array_container():
    canonical = {"type": "object", "additionalProperties": False, "properties": {
        "knots": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
        "frozen": {"type": "string"}}, "required": ["knots", "frozen"]}
    source = {"knots": [True, 1.0], "frozen": "keep"}
    scoped = vfx_repair._vfx_repair_row_schema(canonical, source, ["knots[0]"], [])
    assert scoped["properties"]["knots"] == canonical["properties"]["knots"]
    assert not strict_schema_errors({"knots": [0.0, 1.0], "frozen": "keep"}, scoped)
    assert strict_schema_errors(source, scoped)


def test_asset_reference_grammar_keeps_exact_source_and_declared_choices(wire_transport):
    data = _accepted_visual_data("workbench_blade")
    accepted = _with_asset(data)
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["element"]["texture"]["assetId"] = "missing"
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "note": "reference only", "slotsUpsert": accepted["slots"]}
    parent = {"name": "parent identity", "directProjectileRaw": {"attackReference": {"source": "fixture"}}}
    result, packet = _send_repair(wire_transport, data, raw, patch, parent)
    assert "parentFactsReadOnly" not in packet
    assert "attackReference" in json.dumps(request_dossier(wire_transport[1][0])["parents"])
    assert result["debug"]["vfxDirectorRaw"] == accepted
    assert not strict_schema_errors(vfx_model_payload(patch), packet["outputSchema"])
    texture = packet["outputSchema"]["properties"]["slotsUpsert"]["items"]["properties"]["element"]["properties"]["texture"]
    assert texture["properties"]["source"] == {"type": "string", "const": "asset"}
    assert packet["validGeneratedContext"]["assets"] == accepted["assets"]
    assert "assetsUpsert" not in packet["outputSchema"]["properties"]


def test_delete_only_grammar_has_exact_original_indices_and_no_upsert_domain(wire_transport):
    data = _accepted_visual_data("workbench_blade")
    accepted = _with_asset(data)
    raw = copy.deepcopy(accepted)
    raw["assets"].append(copy.deepcopy(raw["assets"][0]))
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "note": "duplicate only", "assetIndicesDelete": [1]}
    result, packet = _send_repair(wire_transport, data, raw, patch)
    assert result["debug"]["vfxDirectorRaw"] == accepted
    assert set(packet["outputSchema"]["properties"]) == {"schema", "note", "assetIndicesDelete"}
    assert packet["outputSchema"]["properties"]["assetIndicesDelete"]["items"]["enum"] == [1]
    assert not strict_schema_errors(vfx_model_payload(patch), packet["outputSchema"])
    assert strict_schema_errors(dict(patch, assetIndicesDelete=[0]), packet["outputSchema"])


def test_duplicate_asset_grammar_freezes_first_occurrence_while_deleting_later_row(wire_transport):
    data = _accepted_visual_data("workbench_blade")
    accepted = _with_asset(data)
    assert vfx_validation.validate_vfx_director_output(accepted, data)["ok"]
    raw = copy.deepcopy(accepted)
    raw["assets"][0]["canvasSize"] = 13
    raw["assets"].append(dict(raw["assets"][0], prompt=None))
    before = copy.deepcopy(raw)
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "note": "first canvas and duplicate deletion",
             "assetsUpsert": accepted["assets"], "assetIndicesDelete": [1]}
    result, packet = _send_repair(wire_transport, data, raw, patch)
    assert result["debug"]["vfxDirectorRaw"] == accepted
    assert vfx_validation.validate_vfx_manifest_wire(result)["ok"]
    scope = packet["repairScope"]
    assert scope["fieldPermissions"]["assets"] == [{"assetId": accepted["assets"][0]["id"], "paths": ["canvasSize"]}]
    assert scope["deletableAssetIndices"] == [1] and scope["deletableAssetIds"] == []
    schema = packet["outputSchema"]
    assert not strict_schema_errors(vfx_model_payload(patch), schema)
    hostile = copy.deepcopy(patch)
    hostile["assetsUpsert"][0]["prompt"] = "unrequested replacement artwork"
    assert strict_schema_errors(vfx_model_payload(hostile), schema)
    repaired, audit = vfx_repair._apply_vfx_repair_patch(data, raw, hostile, scope, return_audit=True)
    assert repaired == accepted and audit["ignoredChanges"]
    assert vfx_validation.validate_vfx_director_output(repaired, data)["ok"]
    assert raw == before


def test_multiple_rows_have_separate_exact_id_and_path_branches(wire_transport):
    data = _accepted_visual_data("workbench_blade")
    accepted = _sprite(data)
    accepted["slots"].append(dict(accepted["slots"][0], id="second", alpha=.37))
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["alpha"] = 2
    raw["slots"][1]["duration"] = 121
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "note": "two independent leaves", "slotsUpsert": accepted["slots"]}
    result, packet = _send_repair(wire_transport, data, raw, patch)
    assert result["debug"]["vfxDirectorRaw"] == accepted
    schema = packet["outputSchema"]
    assert not strict_schema_errors(vfx_model_payload(patch), schema)
    assert len(schema["properties"]["slotsUpsert"]["items"]["anyOf"]) == 2
    hostile = copy.deepcopy(patch)
    hostile["slotsUpsert"][0]["duration"] = 21
    assert strict_schema_errors(vfx_model_payload(hostile), schema)


def test_whole_response_and_create_preserve_complete_capability_grammar(wire_transport):
    data = _accepted_visual_data("workbench_blade")
    packet = vfx_prompt._prompt_packet(data, None, None)
    full = vfx_repair.vfx_repair_schema(data)
    for previous, errors in ((None, [{"path": "$", "message": "object required"}]),
                             ({"schema": vfx_contract.VFX_DIRECTOR_SCHEMA}, [{"path": "$.slots", "message": "missing"}])):
        scope = vfx_repair._build_vfx_repair_scope(previous, errors)
        schema = vfx_repair._vfx_scoped_repair_schema(packet, previous, scope)
        assert schema["properties"]["slotsUpsert"] == full["properties"]["slotsUpsert"]
        assert "sound" in schema["properties"]["slotsUpsert"]["items"]["properties"]
    assert vfx_schema.vfx_director_schema(data) == packet["outputSchema"]


@pytest.mark.parametrize("response_format", ["json_schema", "json_object"])
def test_alpha_request_has_only_exact_edit_domain_and_preserves_hostile_siblings(wire_transport, monkeypatch, response_format):
    monkeypatch.setattr(stage, "llm_json_response_format", lambda name, **kw: (
        {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": kw["schema"]}}
        if response_format == "json_schema" else {"type": "json_object"}))
    data = _accepted_visual_data("workbench_blade")
    accepted = _sprite(data)
    sibling = dict(accepted["slots"][0], id="frozen_sibling", alpha=0.37)
    accepted["slots"].append(sibling)
    raw = copy.deepcopy(accepted)
    raw["slots"][0]["alpha"] = 2
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "note": "alpha only",
             "slotsUpsert": [dict(accepted["slots"][0], duration=4), dict(sibling, alpha=0)],
             "slotIdsDelete": ["frozen_sibling"]}
    responses, sent = wire_transport
    responses.extend([raw, patch])
    parent = {"directProjectileRaw": {"type": 42, "attackReference": {
        "source": "source-defined unrelated native observation", "sourceText": "native attack " * 3000}}}
    parent_before = copy.deepcopy(parent)
    final = vfx_stage.attach_vfx_manifest(data, "scope-alpha", parent, parent, llm_director=stage.call_llm_vfx_director)
    assert final["debug"]["vfxDirectorRaw"] == accepted
    dossier = request_dossier(sent[1])
    assert "parentFactsReadOnly" not in dossier
    assert "attackReference" not in json.dumps(dossier)
    assert "attackReference" in json.dumps(request_dossier(sent[0])["parents"])
    assert dossier["acceptedVisualKitReadOnly"] == data["visualKit"]
    assert parent == parent_before
    schema = dossier["outputSchema"]
    assert set(schema["properties"]) == {"schema", "note", "slotsUpsert"}
    assert schema["properties"]["slotsUpsert"]["items"]["properties"]["element"]["const"] == vfx_model_payload(accepted)["slots"][0]["element"]
    assert "soundId" not in json.dumps(schema)
    row = schema["properties"]["slotsUpsert"]["items"]
    assert row["properties"]["id"]["const"] == accepted["slots"][0]["id"]
    assert row["properties"]["alpha"] == vfx_schema.vfx_director_schema(data)["properties"]["slots"]["items"]["properties"]["alpha"]
    good = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "note": "alpha only", "slotsUpsert": [accepted["slots"][0]]}
    assert not strict_schema_errors(vfx_model_payload(good), schema)
    assert strict_schema_errors(vfx_model_payload(dict(good, slotsUpsert=[sibling])), schema)
    assert strict_schema_errors(vfx_model_payload(dict(good, slotsUpsert=[dict(accepted["slots"][0], alpha=2)])), schema)
    assert set(dossier["runtimeVocabularyReadOnly"]) == {"numericRanges", "rendererSemantics"}
    assert dossier["runtimeVocabularyReadOnly"]["numericRanges"] == {"alpha": [0.0, 1.0]}
    assert list(dossier["runtimeVocabularyReadOnly"]["rendererSemantics"]) == [accepted["slots"][0]["rendererKind"]]
    assert dossier["acceptedRuntimeProgramReadOnly"] == request_dossier(sent[0])["acceptedRuntimeProgramReadOnly"]
    assert len(json.dumps(sent[1])) < len(json.dumps(sent[0])) / 2
    if response_format == "json_schema":
        assert sent[1]["response_format"]["json_schema"]["schema"] == schema
    assert not responses


@pytest.mark.parametrize("leaf,bad,needs_parents", [("prompt", "", True), ("canvasSize", 7, False)])
def test_asset_repair_keeps_ancestry_only_for_new_artwork(wire_transport, leaf, bad, needs_parents):
    data = _accepted_visual_data("workbench_blade")
    accepted = _with_asset(data)
    raw = copy.deepcopy(accepted)
    raw["assets"][0][leaf] = bad
    parent = {"name": "parent identity", "directProjectileRaw": {"attackReference": {"source": "fixture"}}}
    before = copy.deepcopy(parent)
    patch = {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "note": "one asset leaf", "assetsUpsert": accepted["assets"]}
    result, packet = _send_repair(wire_transport, data, raw, patch, parent)
    assert result["debug"]["vfxDirectorRaw"] == accepted
    assert ("parentFactsReadOnly" in packet) is needs_parents
    if needs_parents:
        assert packet["parentFactsReadOnly"] == request_dossier(wire_transport[1][0])["parents"]
    assert packet["acceptedVisualKitReadOnly"] == data["visualKit"]
    assert packet["acceptedRuntimeProgramReadOnly"] == request_dossier(wire_transport[1][0])["acceptedRuntimeProgramReadOnly"]
    assert packet["repairScope"]["fieldPermissions"]["assets"] == [{"assetId": accepted["assets"][0]["id"], "paths": [leaf]}]
    assert parent == before
