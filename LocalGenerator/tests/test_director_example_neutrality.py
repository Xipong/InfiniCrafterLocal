"""Offline production packets: fewer build anecdotes, unchanged expressive contracts."""
from __future__ import annotations
from infini_local.pipelines import vfx_generation_pipeline as vfx_transport

from copy import deepcopy
import json

import pytest

from prompt_packet_helpers import request_dossier
from infini_local.core import vfx_manifest as vfx
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.pipelines import llm_authoring_pipeline as author
from infini_local.pipelines import llm_transport as transport
from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.qa.capability_witnesses import build_capability_witness


def _accepted_data():
    # A real compiled geometry driver; no provider or image service is invoked.
    return compile_runtime_program(build_capability_witness("move_whip_lash"))


def _capture_visual(monkeypatch, data, *, repair=False):
    sent = []

    def offline_response(request, **_kwargs):
        sent.append(deepcopy(request))
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", "json_object")
    monkeypatch.setattr(visual, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(visual, "llm_chat_json", offline_response)
    kwargs = {"repair_errors": [], "previous": {}, "repair_scope": {}} if repair else {}
    visual._request_visual_kit(data, {}, {}, **kwargs)
    assert len(sent) == 1
    return sent[0], request_dossier(sent[0])


def test_visual_packet_explains_geometry_without_prescribing_terminal_sprite_path_build(monkeypatch):
    data = _accepted_data()
    frozen = deepcopy(data)
    request, packet = _capture_visual(monkeypatch, data)
    rule = packet["spritePresentationReadOnly"]["geometryCoverage"]
    for fact in ("driverMeaningReadOnly", "movement/controller params", "runtime_geometry",
                 "beam/whip collision geometry", "baked_sprite/reuse_item_icon", "texturedPath",
                 "animationPlan", "VFX is not yet authored", "no_asset", "no automatic mode conversion",
                 "Do not alter accepted mechanics"):
        assert fact in rule
    assert packet["acceptedPresentationMechanicsReadOnly"]["bindings"] == data["runtimeProgram"]["bindings"]
    assert packet["runtimeEntities"] == visual._runtime_card(data)
    assert packet["assetModeCatalog"] == visual.visual_asset_mode_catalog()
    assert data == frozen
    assert "with a separately chosen texturedPath for the path" not in rule
    assert "represent only a terminal body" not in rule
    assert "with a separately chosen texturedPath for the path" not in json.dumps(request["messages"])


def _capture_vfx(monkeypatch, data, *, repair=False):
    sent = []

    def offline_response(request, **_kwargs):
        sent.append(deepcopy(request))
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", "json_object")
    monkeypatch.setattr(vfx_transport, "USE_LLM", True)
    monkeypatch.setattr(vfx_transport, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(vfx_transport, "llm_chat_json", offline_response)
    kwargs = {"repair_errors": [], "previous": {}, "repair_scope": {}} if repair else {}
    vfx._request(vfx_transport.call_llm_vfx_director, vfx._prompt_packet(data, {}, {}), **kwargs)
    assert len(sent) == 1
    return sent[0], request_dossier(sent[0])


def test_vfx_packet_keeps_path_coverage_facts_without_tip_plus_path_build_example(monkeypatch):
    data = _accepted_data()
    frozen = deepcopy(data)
    request, packet = _capture_vfx(monkeypatch, data)
    rule = packet["runtimeVocabulary"]["rendererSemantics"]["texturedPath"]
    for fact in ("anchor history", "beam/whip geometry", "baked_sprite/reuse_item_icon",
                 "single PNG", "whip terminal point", "runtime_geometry",
                 "Selection is not automatic", "slots may remain empty", "width",
                 "collision corner", "shared caps", "Read-only gameplay geometry"):
        assert fact in rule
    mechanics = deepcopy(data["runtimeProgram"])
    for row in mechanics["entities"]:
        row.pop("visual", None)
    assert packet["acceptedRuntimeProgramReadOnly"] == mechanics
    assert packet["runtimeVocabulary"] == {
        key: vfx.vfx_director_surface(data)[key] for key in vfx._VFX_RUNTIME_VOCABULARY_KEYS
    }
    assert data == frozen
    assert "can coexist with a baked tip/body" not in rule
    assert "If the intended body covers that path" not in rule
    assert "can coexist with a baked tip/body" not in json.dumps(request["messages"])


@pytest.mark.parametrize("director", ["visual", "vfx"])
def test_shared_geometry_guidance_remains_neutral_in_serialized_repair(monkeypatch, director):
    data = _accepted_data()
    capture = _capture_visual if director == "visual" else _capture_vfx
    request, packet = capture(monkeypatch, data, repair=True)
    scope = packet["repairScope"]
    assert scope == {}  # Shared presentation facts do not expand permissions.
    assert "optional unreported fields stay absent" in " ".join(packet["rules"])
    messages = json.dumps(request["messages"])
    assert "with a separately chosen texturedPath for the path" not in messages
    assert "can coexist with a baked tip/body" not in messages
    if director == "visual":
        assert "texturedPath is an independent VFX renderer" in packet["spritePresentationReadOnly"]["geometryCoverage"]
    else:
        assert "Path coverage is independent of PNG-body presentation" in packet["runtimeVocabularyReadOnly"]["rendererSemantics"]["texturedPath"]


def test_author_packet_retains_full_grammar_without_counterexample_item_anecdotes(monkeypatch):
    from infini_local.core.runtime_authoring.capability_registry import (
        BINDING_ACTION_REGISTRY, ENTITY_KIND_REGISTRY, EVENT_KIND_REGISTRY,
        INPUT_KIND_REGISTRY, CAPABILITY_REGISTRY,
    )
    from infini_local.pipelines.llm_authoring_prompt import sharp_engine_fn_catalog_for_llm

    monkeypatch.setattr(transport, "LLM_RESPONSE_FORMAT_MODE", "json_object")
    parent = {"name": "Source object", "damage": 13, "useTime": 21,
              "tooltipLines": ["Exact source fact, not a recipe example."]}
    frozen = deepcopy(parent)
    request, _, _ = author.build_initial_author_request(parent, {}, "neutrality", model_name="test-model")
    packet = request_dossier(request)
    catalog = packet["runtimeCapabilityContract"]["catalog"]
    assert catalog == sharp_engine_fn_catalog_for_llm(include_source_units=False)
    cards = {card["fn"]: card for card in catalog["capabilities"]}
    assert set(cards) == {cap.name for cap in CAPABILITY_REGISTRY.values()}
    for cap in CAPABILITY_REGISTRY.values():
        expected = cap.author_prompt_card()
        for key, value in expected.items():
            if key != "params":
                assert cards[cap.name][key] == value
        assert cards[cap.name]["params"].keys() == expected["params"].keys()
        for name, value in expected["params"].items():
            from test_author_request_compaction import _expand_constraint_references
            actual = _expand_constraint_references(
                cards[cap.name]["params"][name], catalog["fieldGuide"]["consumerConstraints"])
            assert actual == value
    for field, registry, identity in (
        ("entityKinds", ENTITY_KIND_REGISTRY, "kind"),
        ("inputs", INPUT_KIND_REGISTRY, "input"),
        ("bindingActions", BINDING_ACTION_REGISTRY, "action"),
        ("events", EVENT_KIND_REGISTRY, "event"),
    ):
        assert {row[identity] for row in catalog[field]} == set(registry)
    # Typed envelope/discriminator examples remain useful; they are not recipes.
    shape = packet["requiredJsonShape"]["runtimeProgram"]
    assert shape["bindings"] and shape["calls"]
    assert {"id", "fn", "target", "params"} <= shape["calls"][0].keys()
    assert "not defaults or edit permissions" in catalog["fieldGuide"]["rowShapes"]
    assert "permitted omissions remain valid" in catalog["fieldGuide"]["paramNotation"]
    rule = packet["requiredJsonShape"]["concept"]["coreMechanic"]
    assert "duration is not a cooldown" in rule
    assert "intentional free sustained utility remains a design choice" in rule
    assert parent == frozen
    assert "Exact source fact" in json.dumps(packet["parents"])
    instructions = " ".join(row["content"] for row in request["messages"][:2]).lower()
    for anecdote in ("railgun", "wunderwaffe", "ichor-book", "ichor book"):
        assert anecdote not in instructions


def test_image_packet_preserves_literal_art_and_selected_facts_without_build_examples(monkeypatch):
    from infini_local.pipelines import image_backend_pipeline as image
    from infini_local.pipelines import pipeline_visual_config as config
    from infini_local.pipelines.visual_prompt_contracts import normalize_asset_prompt

    monkeypatch.setattr(config, "BG_COLOR", "transparent")
    monkeypatch.setattr(image, "SDCPP_LORA_PROMPT_TAGS", "")
    monkeypatch.setattr(image, "SDCPP_LORA_FILE", "")
    data = _accepted_data()
    data["visual"] = {
        "renderSizePx": 48, "forwardAngleDegrees": 25,
        "silhouette": "two separate curved plates", "visualIdentity": "three offset inset marks",
        "grip": {"normalizedX": 0.2, "normalizedY": 0.7},
    }
    frozen = deepcopy(data)
    authored = "Two separate curved plates with three offset inset marks and a visible hand-contact region."
    prompt = normalize_asset_prompt(data, "item", authored, 64)
    # Serialize the actual adapter payload, without starting an image backend.
    payload = json.loads(json.dumps(image.sdcpp_server_payload(prompt, "no text", 64, 64, 7, "a1111")))
    text = payload["prompt"]
    assert text.startswith(authored)
    assert "transparent background" in text
    assert "Retain the literal authored silhouette, component count, spatial arrangement" in text
    assert "normalized final canvas coordinates" in text
    assert "Terraria (tModLoader) game asset" in text
    facts = json.JSONDecoder().raw_decode(text.split("Read-only final-frame facts: ", 1)[1])[0]
    for key, value in data["visual"].items():
        assert facts[key] == value
    assert facts["canvasSizePx"] == 64
    assert data == frozen
    assert "with a separately chosen texturedPath for the path" not in text
    assert "can coexist with a baked tip/body" not in text
