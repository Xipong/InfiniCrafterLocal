"""Presentation sees source appearance and complete accepted child light, not parent attack templates."""
import copy
import json
from pathlib import Path

import pytest

from infini_local.pipelines.native_attack_tables import unpack_attack_tables
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
from infini_local.pipelines.parent_presentation_context import presentation_attack_reference, presentation_parent_card_for_llm


def captured_parent():
    return json.loads((Path(__file__).parent / "fixtures" / "native_excalibur_parent_capture.json").read_text())


@pytest.mark.parametrize("stage", ["visual", "vfx"])
@pytest.mark.parametrize("light", [0, 0.6])
def test_presentation_parent_keeps_literal_draw_and_lighting_not_attack_implementation(stage, light):
    parent = captured_parent()
    parent["directProjectileRaw"]["light"] = light
    before = copy.deepcopy(parent)
    full = raw_parent_card_for_llm(parent, include_visual_reference=True)
    result = presentation_parent_card_for_llm(parent, stage=stage)
    original_attack = unpack_attack_tables(full["raw"]["directProjectile"]["attackReference"])
    attack = unpack_attack_tables(result["raw"]["directProjectile"]["attackReference"])
    assert attack["draw"] == original_attack["draw"]
    assert attack["coverage"] == original_attack["coverage"]
    assert attack["identityPredicates"] == original_attack["identityPredicates"]
    assert not {"motion", "motionDispatch", "collision", "positionIntegration"}.intersection(attack)
    assert result["raw"]["directProjectile"]["light"] == light
    assert result["raw"]["directProjectile"]["alpha"] == full["raw"]["directProjectile"]["alpha"]
    assert result["raw"]["item"] == full["raw"]["item"]
    assert parent == before


@pytest.mark.parametrize("stage", ["visual", "vfx"])
def test_unknown_parent_attack_schema_and_generated_appearance_remain_literal(stage):
    source = {"source": "future", "version": 2, "motion": {"futureAppearanceFact": 1}, "draw": {"unknown": True}}
    parent = {"directProjectileRaw": {"attackReference": source}}
    result = presentation_parent_card_for_llm(parent, stage=stage)
    assert result["raw"]["directProjectile"]["attackReference"] == source
    assert parent["directProjectileRaw"]["attackReference"] == source


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("strength", [0.0, 0.6])
@pytest.mark.parametrize("repair", [False, True])
def test_actual_visual_request_exposes_exact_readonly_child_light(monkeypatch, mode, strength, repair):
    from infini_local.core import llm_config
    from infini_local.pipelines import visual_generation_pipeline as visual
    from prompt_packet_helpers import request_dossier
    from test_low_level_three_stage_pipeline import _accepted_visual_data, _visual_kit
    from test_parent_attack_reference import _capture_stage, _CapturedRequest
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    child = _accepted_visual_data("workbench_blade")
    entity = next(row for row in child["runtimeProgram"]["entities"] if row["kind"] != "item_body")
    entity["light"] = {"strength": strength, "color": "yellow"}
    before = copy.deepcopy(child)
    captured = []
    _capture_stage(monkeypatch, visual, captured)
    scope = {"fieldPermissions": {"itemPaths": ["prompt"], "entities": [], "equipOverlayPaths": []}}
    kwargs = {"repair_errors": [{"path": "$.item.prompt"}], "previous": _visual_kit(child), "repair_scope": scope} if repair else {}
    with pytest.raises(_CapturedRequest):
        visual._request_visual_kit(child, {}, {}, **kwargs)
    packet = request_dossier(captured[0])
    rows = packet["runtimeEntitiesReadOnly" if repair else "runtimeEntities"]
    assert next(row for row in rows if row["id"] == entity["id"])["light"] == {"strength": strength, "color": "yellow"}
    for source in child["runtimeProgram"]["entities"]:
        if "light" not in source:
            assert "light" not in next(row for row in rows if row["id"] == source["id"])
    if repair:
        assert packet["repairScope"] == scope
    assert child == before


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("strength", [0.0, 0.6])
@pytest.mark.parametrize("repair", [False, True])
def test_actual_vfx_request_retains_child_light_even_without_parent_design_context(monkeypatch, mode, strength, repair):
    from infini_local.core import llm_config, vfx_manifest as vfx
    from infini_local.pipelines import vfx_generation_pipeline as transport
    from prompt_packet_helpers import request_dossier
    from test_low_level_three_stage_pipeline import _accepted_visual_data
    from test_parent_attack_reference import _capture_stage, _CapturedRequest
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    monkeypatch.setattr(transport, "USE_LLM", True)
    child = _accepted_visual_data("workbench_blade")
    entity = next(row for row in child["runtimeProgram"]["entities"] if row["kind"] != "item_body")
    entity["light"] = {"strength": strength, "color": "yellow"}
    before = copy.deepcopy(child)
    captured = []
    _capture_stage(monkeypatch, transport, captured)
    scope = {"fieldPermissions": {"globals": {}, "slots": [], "assets": []}}
    kwargs = {"repair_errors": [], "previous": {}, "repair_scope": scope} if repair else {}
    with pytest.raises(_CapturedRequest):
        vfx._request(transport.call_llm_vfx_director, vfx._prompt_packet(child, {}, {}), **kwargs)
    packet = request_dossier(captured[0])
    rows = packet["acceptedRuntimeProgramReadOnly"]["entities"]
    assert next(row for row in rows if row["id"] == entity["id"])["light"] == {"strength": strength, "color": "yellow"}
    if repair:
        assert "parentFactsReadOnly" not in packet
        assert "parentBriefs" not in packet
        assert packet["repairScope"] == scope
    assert child == before


@pytest.mark.parametrize("stage", ["visual", "vfx"])
@pytest.mark.parametrize("extension", ["outer_link", "metadata_link", "metadata_type"])
def test_future_attack_links_preserve_full_source_context(stage, extension):
    full = raw_parent_card_for_llm(captured_parent(), include_visual_reference=True)
    attack = unpack_attack_tables(full["raw"]["directProjectile"]["attackReference"])
    if extension == "outer_link":
        attack["futureBinding"] = {"source": "motion.programs[0]"}
    elif extension == "metadata_link":
        attack["behaviorView"]["futureBinding"] = "collision.predicates"
    else:
        attack["behaviorView"]["scope"] = {"source": "motion.programs[0]"}
    before = copy.deepcopy(attack)
    assert presentation_attack_reference(attack, stage=stage) == before
    assert attack == before
