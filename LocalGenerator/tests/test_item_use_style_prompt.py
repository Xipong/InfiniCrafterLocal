from infini_local.pipelines.vfx import request as vfx_transport
from prompt_packet_helpers import request_dossier
"""Verify complete animation vocabulary reaches the production serialized Author request."""

import copy
import json

import pytest

from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.runtime_authoring.validator import validate_runtime_program
from infini_local.pipelines.author import request as gameplay
import infini_local.pipelines.visual.contract as visual_contract
import infini_local.pipelines.visual.stage as visual_stage
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from test_low_level_three_stage_pipeline import _visual_kit, _vfx_output
from test_low_level_three_stage_pipeline import wire_transport as wire_transport

from infini_local.pipelines.author.request import build_initial_author_request


@pytest.mark.parametrize("format_mode", ["json_schema", "json_object"])
@pytest.mark.parametrize("hidden", [False, True])
def test_visibility_advisory_reaches_real_packets_without_changing_choices(wire_transport, monkeypatch, format_mode, hidden):
    monkeypatch.setattr('infini_local.core.llm_config.LLM_RESPONSE_FORMAT_MODE', format_mode)
    responses, requests = wire_transport
    parent = {"id": "literal", "name": "Literal object", "damage": 7, "useTime": 20}
    author, user, _ = build_initial_author_request(parent, parent, "visibility", model_name="test-model")
    author_packet = json.loads(user)
    author_card = next(c for c in author_packet["runtimeCapabilityContract"]["catalog"]["capabilities"] if c["fn"] == "item_use")
    good = build_runtime_fixture("returning_potion")  # Free projectile, not a replacement held body.
    use = next(c for c in good["runtimeProgram"]["calls"] if c["fn"] == "item_use")
    use["params"].update(hideUseGraphic=hidden)
    baseline = compile_runtime_program(good)
    broken = copy.deepcopy(good)
    next(c for c in broken["runtimeProgram"]["calls"] if c["id"] == use["id"])["params"]["useStyle"] = "invalid"
    report = validate_runtime_program(broken)
    hostile_use = copy.deepcopy(use)
    hostile_use["params"].update(hideUseGraphic=not hidden)
    responses.append({"callsUpsert": [hostile_use], "realizationReplacement": good["realization"], "note": "repair useStyle only"})
    fixed = gameplay.repair_author_item_after_failure(broken, parent, parent, "visibility", failure_report={"stage": "validation", "errors": report["errors"]})
    repaired_packet = request_dossier(requests[0])
    repair_card = next(c for c in repaired_packet["existingBrokenCapabilityCards"] if c["fn"] == "item_use")
    assert repaired_packet["repairScope"]["fieldPermissions"]["calls"] == [{"id": use["id"], "paths": ["params.useStyle"]}]
    assert compile_runtime_program(fixed)["runtimeProgram"] == baseline["runtimeProgram"]
    assert validate_runtime_program(good)["ok"]

    accepted_kit = _visual_kit(baseline)
    broken_kit = copy.deepcopy(accepted_kit)
    broken_kit["item"]["inventoryScale"] = 99
    responses.extend([broken_kit, {"schema": visual_contract.VISUAL_REPAIR_PATCH_SCHEMA, "itemPatch": {"inventoryScale": 1.0}, "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [], "note": "inventoryScale only"}])
    projected = visual_stage.apply_visual_director(baseline, parent, parent)
    visual_packets = [request_dossier(r) for r in requests[1:]]
    assert projected["visualKit"] == accepted_kit
    assert projected["runtimeProgram"]["itemUse"] == baseline["runtimeProgram"]["itemUse"]
    assert visual_packets[1]["repairScope"]["fieldPermissions"]["itemPaths"] == ["inventoryScale"]
    import infini_local.core.vfx.contract as vfx_contract
    import infini_local.pipelines.vfx.stage as vfx_stage
    accepted_vfx = _vfx_output(projected)
    broken_vfx = copy.deepcopy(accepted_vfx)
    broken_vfx["slots"][0]["alpha"] = 2
    responses.extend([broken_vfx, {"schema": vfx_contract.VFX_REPAIR_PATCH_SCHEMA, "slotsUpsert": accepted_vfx["slots"], "note": "alpha only"}])
    final = vfx_stage.attach_vfx_manifest(projected, "visibility", llm_director=vfx_transport.call_llm_vfx_director)
    vfx_packets = [request_dossier(r) for r in requests[3:]]
    assert final["debug"]["vfxDirectorRaw"] == accepted_vfx
    assert final["runtimeProgram"]["itemUse"] == baseline["runtimeProgram"]["itemUse"]
    assert vfx_packets[1]["repairScope"]["fieldPermissions"] == {"globals": {}, "slots": [{"slotId": "slot_0", "paths": ["alpha"]}], "assets": []}
    descriptions = [author_card["params"]["hideUseGraphic"]["meaning"], repair_card["params"]["hideUseGraphic"]["meaning"]]
    # Initial stages retain visibility semantics. Scale/alpha-only Repairs have
    # no permission to change these frozen choices and omit unrelated guidance.
    descriptions.append(visual_packets[0]["spritePresentationReadOnly"]["heldRootVisibility"]["hideUseGraphic"])
    descriptions.append(vfx_packets[0]["runtimeVocabulary"]["heldRootVisibility"]["hideUseGraphic"])
    assert "heldRootVisibility" not in visual_packets[1]["spritePresentationReadOnly"]
    assert "heldRootVisibility" not in vfx_packets[1]["runtimeVocabularyReadOnly"]
    assert visual_packets[1]["acceptedPresentationMechanicsReadOnly"]["itemUse"] == baseline["runtimeProgram"]["itemUse"]
    assert vfx_packets[1]["acceptedRuntimeProgramReadOnly"]["itemUse"] == baseline["runtimeProgram"]["itemUse"]
    from infini_local.core.runtime_authoring.capability_registry import CAPABILITY_REGISTRY
    expected_meaning = CAPABILITY_REGISTRY["item_use"].params["hideUseGraphic"].description
    assert descriptions == [expected_meaning] * len(descriptions)
    for request in [author, *requests]:
        assert request["response_format"]["type"] == format_mode
    assert not responses
