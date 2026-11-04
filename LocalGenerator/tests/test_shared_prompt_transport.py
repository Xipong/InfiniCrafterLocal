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


@pytest.mark.parametrize("stage", ["author", "format"])
@pytest.mark.parametrize("mode", ["json_object", "json_schema", "off"])
def test_presentation_art_style_does_not_change_gameplay_or_syntax_packets(monkeypatch, stage, mode):
    from infini_local.core import llm_config

    monkeypatch.setattr(llm_config, "PROMPT_STYLE", "Default")
    default, = stage_packets(monkeypatch, stage, format_mode=mode, labels=("same-design",))
    monkeypatch.setattr(llm_config, "PROMPT_STYLE", "Terraria Like")
    styled, = stage_packets(monkeypatch, stage, format_mode=mode, labels=("same-design",))
    assert styled == default


@pytest.mark.parametrize("mode", ["json_object", "json_schema", "off"])
def test_gameplay_repair_receives_user_art_direction_without_changing_scope(monkeypatch, mode):
    from infini_local.core import llm_config
    from infini_local.core.llm_stage_messages import generation_art_direction

    monkeypatch.setattr(llm_config, "PROMPT_STYLE", "Default")
    default, = stage_packets(monkeypatch, "repair", format_mode=mode, labels=("same-design",))
    monkeypatch.setattr(llm_config, "PROMPT_STYLE", "Terraria Like")
    styled, = stage_packets(monkeypatch, "repair", format_mode=mode, labels=("same-design",))
    direction = generation_art_direction()
    assert direction and direction not in default["messages"][0]["content"]
    assert styled["messages"][0]["content"].count(direction) == 1
    normalized = copy.deepcopy(styled)
    normalized["messages"][0]["content"] = normalized["messages"][0]["content"].replace("\n\nArt direction is advisory and does not override the output contract, accepted gameplay or frozen fields. " + direction, "")
    assert normalized == default


@pytest.mark.parametrize("stage", ["vfx", "vfx_repair"])
def test_vfx_packet_guides_actual_child_events_and_supported_timing(monkeypatch, stage):
    packet, = stage_packets(monkeypatch, stage, labels=("child-cue",))
    wire = "\n".join(message["content"] for message in packet["messages"])
    assert "exact child's available spawn/periodic/hit pairs" in wire
    assert "only with a renderer that consumes it" in wire
    assert "on_hit cue starts from that hit occurrence" in wire


def test_author_and_repair_deliver_composition_context(monkeypatch):
    author, = stage_packets(monkeypatch, "author", labels=("composition",))
    repair, = stage_packets(monkeypatch, "repair", labels=("composition",))
    author_text = "\n".join(message["content"] for message in author["messages"])
    repair_text = "\n".join(message["content"] for message in repair["messages"])
    assert "held body, an independently moving object or a detached effect" in author_text
    assert "Independent poses remain valid" in repair_text
    assert "Deliberately displaced bodies remain valid" in repair_text
    assert "does not cancel physical axis/normal offsets or reachCurve" in repair_text
    assert "beam_geometry uses the same Aim world unit axis" in repair_text
    assert "weapon family, archetype, semantic root, or code-authored default" in repair_text


def test_visual_packet_keeps_exact_entity_roster_and_json_guidance(monkeypatch):
    packet, = stage_packets(monkeypatch, "visual", format_mode="off", labels=("visual",))
    wire = "\n".join(message["content"] for message in packet["messages"])
    assert "For each exact required entityId, author one row and choose one finite assetMode" in wire
    assert "no trailing commas or JavaScript expressions" in wire
    assert "only entityId/assetMode/visualProjectRef/scale" in wire
