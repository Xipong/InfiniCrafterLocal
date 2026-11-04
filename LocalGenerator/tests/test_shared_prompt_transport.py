"""Shared guidance survives actual provider framing and schema negotiation."""
import copy

import pytest

from infini_local.core.llm_stage_messages import generation_system_suffix
from infini_local.core.provider_schema import provider_nullable_transport_rule
from infini_local.pipelines.transport.client import _payload_without_strict_schema
from test_craft_instruction_segments import stage_packets
from test_stable_schema_data import capture_wire, wire_text


@pytest.mark.parametrize("response_format", [None, {}, {"type": "json_object"}])
def test_nullable_guidance_is_absent_without_schema(response_format):
    assert provider_nullable_transport_rule(response_format) == ""


@pytest.mark.parametrize("stage", ["author", "repair", "format", "visual", "visual_repair", "vfx", "vfx_repair"])
@pytest.mark.parametrize("provider,base,api,model", [
    ("openai_compat", "https://api.openai.com/v1", "chat_completions", "gpt-6.1-sol"),
    ("openai_compat", "https://api.openai.com/v1", "responses", "gpt-6.1-sol"),
    ("openai_codex", "https://chatgpt.com/backend-api/codex", "responses", "gpt-6.1-sol"),
    ("openrouter", "https://openrouter.ai/api/v1", "chat_completions", "anthropic/claude-opus-4.6"),
])
def test_shared_guidance_reaches_wire_once_and_fallback_retains_contract(monkeypatch, stage, provider, base, api, model):
    packet, = stage_packets(monkeypatch, stage, format_mode="json_schema", labels=("shared-guidance",))
    before = copy.deepcopy(packet)
    context = {"provider": provider, "base_url": base, "api_mode": api, "model": model, "api_key": "offline"}
    nullable = provider_nullable_transport_rule(packet["response_format"])
    assert nullable and packet["messages"][0]["content"].count(nullable) == 1
    relaxed = _payload_without_strict_schema(packet)
    assert relaxed["messages"] == packet["messages"]
    assert relaxed["response_format"] == {"type": "json_object"}
    for candidate in (packet, relaxed):
        wire = capture_wire(monkeypatch, candidate, context)
        if api == "responses":
            assert wire["instructions"] == packet["messages"][0]["content"]
            rows = wire["input"]
            source = packet["messages"][1:]
        else:
            rows = wire["messages"]
            source = packet["messages"]
        # JSON mode may add a provider-required marker; the authored schema and
        # all instructions/data retain their exact content and authority.
        authored = [row for row in rows if wire_text(row) != "JSON response."]
        assert [(row["role"], wire_text(row)) for row in authored] == [
            (row["role"], row["content"]) for row in source]
        sent = wire.get("instructions", "") + "".join(wire_text(row) for row in rows)
        assert sent.count(nullable) == 1
        suffix = generation_system_suffix()
        assert sent.count(suffix) == packet["messages"][0]["content"].count(suffix)
    assert packet == before


@pytest.mark.parametrize("stage", ["author", "repair", "format"])
@pytest.mark.parametrize("mode", ["json_object", "json_schema", "off"])
def test_presentation_art_style_does_not_change_gameplay_or_syntax_packets(monkeypatch, stage, mode):
    from infini_local.core import llm_config

    monkeypatch.setattr(llm_config, "PROMPT_STYLE", "Default")
    default, = stage_packets(monkeypatch, stage, format_mode=mode, labels=("same-design",))
    monkeypatch.setattr(llm_config, "PROMPT_STYLE", "Terraria Like")
    styled, = stage_packets(monkeypatch, stage, format_mode=mode, labels=("same-design",))
    assert styled == default
