"""Offline transport fixtures: effect semantics, not a buff-name choice list."""
from copy import deepcopy
import json

import pytest

from infini_local.core import llm_config
from infini_local.pipelines.llm_authoring_pipeline import build_initial_author_request
from prompt_packet_helpers import request_dossier, expand_native_source_references
from test_source_unit_guidance import _serialized_chat_request


@pytest.mark.parametrize("mode", ["json_schema", "json_object"])
def test_parent_local_buff_effect_reference_reaches_provider_without_reinterpretation(monkeypatch, mode):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    # This tests literal transport only, not discovery of a real native effect.
    effect = {
        "source": "synthetic_transport_fixture", "receiver": "player", "complete": False,
        "effects": [{"member": "Player.pickSpeed", "operation": "add", "value": -0.25}],
        "unresolved": ["Receiver-specific conditions and unknown hooks remain unknown"],
        "literalWitness": {"zero": 0, "flag": False, "absence": None, "notes": ["", "  exact text  "]},
    }
    npc_effect = {**deepcopy(effect), "receiver": "npc"}
    source = {
        "name": "Effect transport fixture", "buffType": 104, "buffTime": 60,
        "nativeBuffEffectReference": effect,
        "nativeContactHitStatusReference": {"effects": [{"buffId": 20, "buffEffectReference": npc_effect}]},
    }
    before = deepcopy(source)
    request, _, _ = build_initial_author_request(source, source, "effect-transport", model_name="offline")
    sent = _serialized_chat_request(monkeypatch, request)
    packet = request_dossier(sent, declaration=request)
    expanded = expand_native_source_references(packet)
    for side in ("A", "B"):
        item = expanded["parents"][side]["packet"]["raw"]["item"]
        assert item.get("nativeBuffEffectReference") == effect
        assert item["nativeContactHitStatusReference"]["effects"][0]["buffEffectReference"] == npc_effect
    assert "statusIdentityChoices" not in json.dumps(sent)
    assert source == before


@pytest.mark.parametrize("mode", ["json_schema", "json_object"])
def test_author_explicitly_composes_buffs_and_debuffs_without_requiring_native_identity(monkeypatch, mode):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    request, _, _ = build_initial_author_request({}, {}, "effect-composition", model_name="offline")
    packet = request_dossier(_serialized_chat_request(monkeypatch, request), declaration=request)
    guidance = packet["runtimeCapabilityContract"]["catalog"]["fieldGuide"]["statusEffects"]
    assert "status effects" in guidance
    assert "native buff immunity or AI" in guidance
    assert "listed operations and conditions" in guidance
    assert "statusIdentityChoices" not in json.dumps(packet)


@pytest.mark.parametrize("mode", ["json_schema", "json_object"])
def test_exact_repeated_source_facts_fit_original_budget_without_losing_any_value(monkeypatch, mode):
    from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    scope = "Synthetic transport proof, not native behavior: " + "Ж" * 5000
    source = {
        "name": "Repeated source transport fixture", "tooltipLines": [scope, scope],
        "nativeContactHitStatusReference": {
            "scope": scope,
            "clauses": [{"scope": scope, "branch": n, "value": False if n == 0 else 0}
                        for n in range(8)],
            "effects": [{"buffId": 20, "durationTicks": 420, "probabilityNumerator": 1,
                         "probabilityDenominator": 4, "literalNull": None}],
        },
    }
    before = deepcopy(source)
    request, text, _ = build_initial_author_request(source, source, "exact-source-sharing", model_name="offline")
    packet = request_dossier(_serialized_chat_request(monkeypatch, request), declaration=request)
    assert len(text) <= 225_000
    assert "sourceSameAs" in text
    source_rows = [(row["role"], json.loads(row["content"])) for row in request["messages"][1:]]
    assert any(role == "user" and "nativeSourceFacts" in value for role, value in source_rows)
    assert all("nativeSourceFacts" not in value for role, value in source_rows if role == "developer")
    expanded = expand_native_source_references(packet)
    expected = raw_parent_card_for_llm(source)
    encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True)
    assert all(encode(expanded["parents"][side]["packet"]) == encode(expected) for side in ("A", "B"))
    for side in ("A", "B"):
        assert packet["parents"][side]["packet"]["raw"]["item"]["tooltipLines"] == source["tooltipLines"]
    assert source == before
