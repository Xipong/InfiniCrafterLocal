"""Scoped Visual Repair grammar at the production sender, without model calls."""
import copy

import pytest
from jsonschema import Draft202012Validator

from prompt_packet_helpers import request_dossier
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.pipelines import visual_generation_pipeline as visual
from test_low_level_three_stage_pipeline import _visual_kit, wire_transport


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_size_leaf_sender_has_only_permitted_grammar_and_frozen_art(wire_transport, monkeypatch, mode):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    previous = _visual_kit(data)
    previous["item"]["renderSizePx"] = None
    responses, requests = wire_transport
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch={"renderSizePx": 48}, note="size only")
    responses.extend([previous, patch])
    result = visual.apply_visual_director(data, {"name": "parent A"}, {"name": "parent B"})
    packet = request_dossier(requests[1])
    schema = packet["responseSchema"]
    assert set(schema["properties"]) == {"schema", "note", "itemPatch"}
    assert set(schema["properties"]["itemPatch"]["anyOf"][0]["properties"]) == {"renderSizePx"}
    assert packet["repairScope"]["fieldPermissions"]["itemPaths"] == ["renderSizePx"]
    assert "placedBody" not in packet["spritePresentationReadOnly"]
    assert "parentFactsReadOnly" not in packet
    assert packet["brokenFragments"]["item"] == previous["item"]
    assert result["visualKit"]["item"] == dict(previous["item"], renderSizePx=48)
    assert result["visualKit"]["entities"] == previous["entities"]
    assert not responses
    if mode == "json_schema":
        assert Draft202012Validator(requests[1]["response_format"]["json_schema"]["schema"]).is_valid(patch)


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("target", ["grip", "entity", "overlay"])
def test_partial_owner_patch_retains_valid_siblings_and_exact_schema(wire_transport, monkeypatch, mode, target):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    data = compile_runtime_program(build_runtime_fixture("equipment_tool_combat" if target == "overlay" else "door_on_chain"))
    previous = _visual_kit(data)
    if target == "grip":
        previous["item"]["grip"] = {"normalizedX": 0.25, "normalizedY": 2}
        operation, leaf, value = "itemPatch", "grip", {"normalizedY": 0.75}
    elif target == "entity":
        previous["entities"][1]["scale"] = 99
        operation, leaf, value = "entitiesUpsert", "scale", 2
    else:
        previous["equipOverlay"] = dict(prompt="badge", silhouette="badge", visualIdentity="badge", preferredCanvasSize=32, accessoryMount="bad")
        operation, leaf, value = "equipOverlayPatch", "accessoryMount", "back"
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, note="one exact leaf")
    patch[operation] = [{"entityId": previous["entities"][1]["entityId"], leaf: value}] if target == "entity" else {leaf: value}
    responses, requests = wire_transport
    responses.extend([previous, patch])
    result = visual.apply_visual_director(data, {}, {})
    packet = request_dossier(requests[1])
    schema = packet["responseSchema"]
    assert set(schema["properties"]) == {"schema", "note", operation}
    node = schema["properties"][operation]["items"] if target == "entity" else schema["properties"][operation]["anyOf"][0]
    assert set(node["properties"]) == ({"entityId", leaf} if target == "entity" else {leaf})
    expected = copy.deepcopy(previous)
    if target == "grip":
        assert set(node["properties"]["grip"]["properties"]) == {"normalizedY"}
        expected["item"]["grip"]["normalizedY"] = 0.75
    elif target == "entity":
        expected["entities"][1]["scale"] = 2
    else:
        expected["equipOverlay"]["accessoryMount"] = "back"
    assert result["visualKit"] == expected
    assert not responses
    if mode == "json_schema":
        assert Draft202012Validator(requests[1]["response_format"]["json_schema"]["schema"]).is_valid(patch)


def test_hostile_complete_patch_still_hits_authoritative_frozen_filter(wire_transport):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    previous = _visual_kit(data)
    previous["item"]["renderSizePx"] = None
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, note="hostile siblings",
                 itemPatch={"renderSizePx": 48, "prompt": "rewrite", "grip": {"normalizedX": 0.5, "normalizedY": 0.5}},
                 entitiesUpsert=[dict(previous["entities"][1], scale=4)], entityIdsDelete=["chained_door"], entityIndicesDelete=[0])
    responses, requests = wire_transport
    responses.extend([previous, patch])
    result = visual.apply_visual_director(data, {}, {})
    assert result["visualKit"] == dict(previous, item=dict(previous["item"], renderSizePx=48))
    assert result["debug"]["visualRepairFilterAudit"]["ignoredChanges"]
    assert not Draft202012Validator(request_dossier(requests[1])["responseSchema"]).is_valid(patch)


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_whole_response_repair_keeps_complete_contract_and_raw_source(wire_transport, monkeypatch, mode):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    source = visual.MalformedVisualDirectorOutput(raw_text='{"schema":', error="syntax")
    errors = [{"path": "$", "message": "malformed_json"}]
    ids = [row["id"] for row in data["runtimeProgram"]["entities"]]
    scope = visual._build_visual_repair_scope(source, errors, ids, "item")
    responses, requests = wire_transport
    responses.append({})
    visual._request_visual_kit(data, {}, {}, repair_errors=errors, previous=source, repair_scope=scope)
    packet = request_dossier(requests[0])
    expected = visual._visual_repair_schema(ids, False, "item")
    assert packet["responseSchema"] == (visual._provider_strict_projection(expected) if mode == "json_schema" else expected)
    assert packet["malformedRawText"] == source.raw_text
    assert "parentFactsReadOnly" in packet
    assert "preserve all recoverable visual fields" in requests[0]["messages"][0]["content"]


@pytest.mark.parametrize("bad_rows", [True, 7, {"malformed": "container"}])
def test_malformed_entity_collection_keeps_complete_replacement_domain(wire_transport, bad_rows):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    accepted = _visual_kit(data)
    broken = dict(accepted, entities=bad_rows)
    patch = {"schema": visual.VISUAL_REPAIR_PATCH_SCHEMA, "note": "replace malformed collection",
             "entitiesUpsert": accepted["entities"]}
    responses, requests = wire_transport
    responses.extend([broken, patch])
    result = visual.apply_visual_director(data, {}, {})
    assert result["visualKit"] == accepted
    assert Draft202012Validator(request_dossier(requests[1])["responseSchema"]).is_valid(patch)
    assert not responses


@pytest.mark.parametrize("bad_id", [[], {}], ids=["array-id", "object-id"])
@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_malformed_entity_identity_reaches_authorized_replacement_repair(wire_transport, monkeypatch, mode, bad_id):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", mode)
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    accepted = _visual_kit(data)
    broken = copy.deepcopy(accepted)
    replacement = copy.deepcopy(accepted["entities"][1])
    broken["entities"][1]["entityId"] = bad_id
    patch = {"schema": visual.VISUAL_REPAIR_PATCH_SCHEMA, "note": "replace malformed identity",
             "entitiesUpsert": [replacement], "entityIndicesDelete": [1]}
    responses, requests = wire_transport
    responses.extend([broken, patch])
    result = visual.apply_visual_director(data, {}, {})
    packet = request_dossier(requests[1])
    assert packet["repairScope"]["deletableEntityIndices"] == [1]
    retained = [*packet["brokenFragments"]["entities"], *packet["validGeneratedContext"]["entities"]]
    assert any(row["entityId"] == bad_id for row in retained)
    assert Draft202012Validator(packet["responseSchema"]).is_valid(patch)
    assert result["visualKit"] == accepted
    assert not responses


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
def test_actual_http_sender_preserves_calibration_and_size_dependencies(mode):
    import json
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "tools"))
    from measure_llm_request_sizes import OfflineCapture, COHORT, ROUTES, dossier
    from test_generated_parent_exact_context import _accepted_appearance_parent
    parent = _accepted_appearance_parent()
    frozen_parent = copy.deepcopy(parent)
    with OfflineCapture(root) as capture:
        capture.recipes[COHORT[0]] = (parent, parent, "door_on_chain")
        packet, evidence = capture.builder("visual_repair", COHORT[0], mode)
        full = dossier(packet)
        expected = visual.raw_parent_card_for_llm(parent, include_visual_reference=True)["raw"]["generatedParent"]
        references = full["parentSizeReferencesReadOnly"]["parentA"]
        assert references["visual"] == expected["visual"]
        assert references["entities"] == [{"id": row["id"], "visual": row["visual"]} for row in expected["runtimeProgram"]["entities"]]
        assert full["brokenFragments"]["item"] == evidence["broken"]["item"]
        assert full["acceptedPresentationMechanicsReadOnly"]["gameplay"]["itemScale"] == evidence["inputs"]["data"]["gameplay"]["itemScale"]
        assert full["runtimeEntitiesReadOnly"] == visual._runtime_card(evidence["inputs"]["data"])
        for route in ROUTES:
            observed = capture.wire(packet, route)
            assert json.loads(observed["body"]) == observed["packet"]
            assert not any(key.startswith("_infini") for key in observed["packet"])
        assert parent == frozen_parent
