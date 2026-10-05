"""Verify complete animation vocabulary reaches the production serialized Author request."""

import copy
import json

import pytest

from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_program
from infini_local.pipelines import llm_authoring_pipeline as gameplay, visual_generation_pipeline as visual
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from test_low_level_three_stage_pipeline import _visual_kit, _vfx_output, wire_transport

from infini_local.core.runtime_authoring.terraria_vocabulary import (
    ITEM_USE_STYLE_MEANINGS, ITEM_USE_STYLE_TMODLOADER_NAMES, ITEM_USE_STYLE_TOKENS,
)
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from infini_local.pipelines.llm_authoring_prompt import (
    PLANNER_PROMPT_LIMIT_CHARS, PLANNER_PROMPT_MIN_HEADROOM_CHARS,
)


def test_serialized_item_use_style_guide_covers_exact_enum_and_no_mechanics(monkeypatch):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", "json_object")
    parent_a = {"id": "blade", "name": "Blade", "damage": 7, "useTime": 20}
    parent_b = {"id": "bench", "name": "Workbench", "createTile": 18, "useTime": 15}
    request, user_content, _ = build_initial_author_request(
        parent_a, parent_b, parent_a, parent_b, "blade+bench", model_name="gemini-2.5-flash",
    )
    assert request["messages"][1]["content"] == user_content
    assert request["response_format"] == {"type": "json_object"}
    assert len(user_content) <= PLANNER_PROMPT_LIMIT_CHARS - PLANNER_PROMPT_MIN_HEADROOM_CHARS
    payload = json.loads(user_content)
    guide = payload["runtimeCapabilityContract"]["catalog"]["fieldGuide"]["itemUseStyle"]
    card = next(row for row in payload["runtimeCapabilityContract"]["catalog"]["capabilities"]
                if row["fn"] == "configure_item_use")
    assert guide["builtInTokens"] == list(ITEM_USE_STYLE_TOKENS)
    assert set(guide["meaningByToken"]) == set(card["params"]["useStyle"]["enum"])
    assert set(guide["meaningByToken"]) == set(ITEM_USE_STYLE_TOKENS) == set(ITEM_USE_STYLE_TMODLOADER_NAMES)
    assert guide["meaningByToken"] == dict(ITEM_USE_STYLE_MEANINGS)
    assert all(text.strip().endswith(".") for text in guide["meaningByToken"].values())
    meanings = guide["meaningByToken"]
    assert "horizontally" in meanings["thrust"] and "any angle" in meanings["rapier"]
    assert "early" in meanings["drink_long"] and "front arm" in meanings["drink_liquid"]
    assert "off hand" in meanings["raise_lamp"] and "animation" in meanings["hidden_animation"]
    assert "cursor" in meanings["shoot"] and "golf club" in meanings["golf_play"]
    assert all(term in guide["scope"] for term in (
        "configure_item_use.useStyle", "animation", "during active use only",
        "not a functional tool/use mechanic", "input binding", "executable effects separately", "not weapon presets",
    ))
    assert "meaningByToken" in payload["runtimeCapabilityContract"]["catalog"]["fieldGuide"]["damageClass"]


@pytest.mark.parametrize("format_mode", ["json_schema", "json_object"])
@pytest.mark.parametrize("hidden,hint", [(False, ""), (True, ""), (True, "on_release")])
def test_visibility_advisory_reaches_real_packets_without_changing_choices(wire_transport, monkeypatch, format_mode, hidden, hint):
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", format_mode)
    responses, requests = wire_transport
    parent = {"id": "literal", "name": "Literal object", "damage": 7, "useTime": 20}
    author, user, _ = build_initial_author_request(parent, parent, parent, parent, "visibility", model_name="test-model")
    author_packet = json.loads(user)
    author_card = next(c for c in author_packet["runtimeCapabilityContract"]["catalog"]["capabilities"] if c["fn"] == "configure_item_use")
    good = build_runtime_fixture("returning_potion")  # Free projectile, not a replacement held body.
    use = next(c for c in good["runtimeProgram"]["calls"] if c["fn"] == "configure_item_use")
    use["params"].update(hideUseGraphic=hidden, heldSpriteVisibilityHint=hint)
    baseline = compile_runtime_program(good)
    broken = copy.deepcopy(good)
    next(c for c in broken["runtimeProgram"]["calls"] if c["id"] == use["id"])["params"]["useStyle"] = "invalid"
    report = validate_runtime_program(broken)
    hostile_use = copy.deepcopy(use)
    hostile_use["params"].update(hideUseGraphic=not hidden, heldSpriteVisibilityHint="after_charge")
    responses.append({"callsUpsert": [hostile_use], "realizationReplacement": good["realization"], "note": "repair useStyle only"})
    fixed = gameplay.repair_author_item_after_failure(broken, parent, parent, parent, parent, "visibility", failure_report={"stage": "validation", "errors": report["errors"]})
    repaired_packet = json.loads(requests[0]["messages"][1]["content"])
    repair_card = next(c for c in repaired_packet["existingBrokenCapabilityCards"] if c["fn"] == "configure_item_use")
    assert repaired_packet["repairScope"]["fieldPermissions"]["calls"] == [{"id": use["id"], "paths": ["params.useStyle"]}]
    assert compile_runtime_program(fixed)["runtimeProgram"] == baseline["runtimeProgram"]
    assert validate_runtime_program(good)["ok"]

    accepted_kit = _visual_kit(baseline)
    broken_kit = copy.deepcopy(accepted_kit)
    broken_kit["item"]["inventoryScale"] = 99
    responses.extend([broken_kit, {"schema": visual.VISUAL_REPAIR_PATCH_SCHEMA, "itemPatch": {"inventoryScale": 1.0}, "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [], "animationPlan": None, "note": "inventoryScale only"}])
    projected = visual.apply_visual_director(baseline, parent, parent, parent, parent)
    visual_packets = [json.loads(r["messages"][1]["content"]) for r in requests[1:]]
    assert projected["visualKit"] == accepted_kit
    assert projected["runtimeProgram"]["itemUse"] == baseline["runtimeProgram"]["itemUse"]
    assert visual_packets[1]["repairScope"]["fieldPermissions"]["itemPaths"] == ["inventoryScale"]
    from infini_local.core import vfx_manifest as vfx
    accepted_vfx = _vfx_output(projected)
    broken_vfx = copy.deepcopy(accepted_vfx)
    broken_vfx["effectMagnitude"] = 2
    responses.extend([broken_vfx, {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "effectMagnitude": accepted_vfx["effectMagnitude"], "note": "effectMagnitude only"}])
    final = vfx.attach_hybrid_vfx_manifest(projected, "visibility", llm_director=gameplay.call_llm_vfx_director)
    vfx_packets = [json.loads(r["messages"][1]["content"]) for r in requests[3:]]
    assert final["debug"]["vfxDirectorRaw"] == accepted_vfx
    assert final["runtimeProgram"]["itemUse"] == baseline["runtimeProgram"]["itemUse"]
    assert vfx_packets[1]["repairScope"]["fieldPermissions"] == {"globals": {"effectMagnitude": [""]}, "slots": [], "assets": []}
    descriptions = [author_card["params"]["hideUseGraphic"]["meaning"], repair_card["params"]["hideUseGraphic"]["meaning"]]
    descriptions += [p["spritePresentationReadOnly"]["heldRootVisibility"]["hideUseGraphic"] for p in visual_packets]
    descriptions += [p["runtimeVocabularyReadOnly" if i else "runtimeVocabulary"]["heldRootVisibility"]["hideUseGraphic"] for i, p in enumerate(vfx_packets)]
    for description in descriptions:
        assert all(term in description for term in ("deliberate invisibility", "physical held-body replacement", "Free projectiles", "not", "heldSpriteVisibilityHint")), description
    for request in [author, *requests]:
        assert request["response_format"]["type"] == format_mode
    assert not responses
