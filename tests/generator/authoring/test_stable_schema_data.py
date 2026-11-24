"""Canonical grammar is application instructions; case constraints stay USER."""
import copy
import json
import time

import infini_local.pipelines.transport.http as transport_http
import pytest
from infini_local.pipelines.transport import client as transport
from tests.generator.authoring.test_craft_instruction_segments import stage_packets


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, "connect", lambda *args: pytest.fail("offline schema test attempted network"))


def capture_wire(monkeypatch, packet, context):
    from types import SimpleNamespace

    from infini_local.services import codex_auth as auth
    from tests.generator.authoring.test_craft_instruction_segments import Captured
    wires = []
    def stop(url, wire, **kwargs):
        wires.append(copy.deepcopy(wire))
        if context["provider"] == "openai_codex":
            assert kwargs["headers"]["session-id"] == wire["prompt_cache_key"]
        raise Captured()
    monkeypatch.setattr(transport_http, "http_json", stop)
    monkeypatch.setattr(auth, "get_credentials", lambda: SimpleNamespace(access_token="offline", account_id="offline"))
    monkeypatch.setattr(auth, "post_sse", stop)
    # This fixture proves serialization, not wall-clock CPU speed. Captured is a
    # BaseException, so the first fake send exits without entering retry logic.
    with monkeypatch.context() as clock, pytest.raises(Captured):
        clock.setattr(time, "monotonic", lambda: 100.0)
        transport._llm_json_single_context(packet, 3, context)
    assert len(wires) == 1
    return wires[0]


def wire_text(row):
    content = row["content"]
    return content if isinstance(content, str) else "".join(block["text"] for block in content)


@pytest.mark.parametrize("provider,base,api,model,mode,stage", [
    pytest.param("openai_compat", "https://inference-api.nousresearch.com/v1", "chat_completions", "openai/gpt-6-luna", "json_object", "author", id="nous-author-json"),
    pytest.param("openai_compat", "https://api.openai.com/v1", "chat_completions", "gpt-6.1-sol", "json_schema", "author", id="platform-author-schema"),
    pytest.param("openrouter", "https://openrouter.ai/api/v1", "chat_completions", "openai/gpt-6.1-sol", "json_schema", "visual", id="router-visual-schema"),
    pytest.param("openai_codex", "https://chatgpt.com/backend-api/codex", "responses", "gpt-6.1-sol", "json_object", "vfx", id="subscription-vfx-json"),
    pytest.param("openai_compat", "https://api.openai.com/v1", "responses", "gpt-6.1-sol", "off", "author", id="platform-responses-unformatted"),
    pytest.param("openai_codex", "https://chatgpt.com/backend-api/codex", "responses", "gpt-6.1-sol", "json_schema", "repair", id="subscription-scoped-repair"),
    pytest.param("openrouter", "https://openrouter.ai/api/v1", "chat_completions", "openai/gpt-6.1-sol", "json_object", "visual_repair", id="router-visual-repair"),
    pytest.param("openai_compat", "https://api.openai.com/v1", "responses", "gpt-6.1-sol", "json_schema", "vfx_repair", id="responses-vfx-repair"),
    pytest.param("openai_compat", "https://api.openai.com/v1", "chat_completions", "gpt-6.1-sol", "off", "author", id="platform-author-unformatted"),
    pytest.param("local", "http://127.0.0.1:8085/v1", "chat_completions", "offline/loaded-model", "json_object", "author", id="local-author"),
])
def test_actual_senders_cache_grammar_instructions_and_preserve_author(monkeypatch, provider, base, api, model, mode, stage):
    # Fixture captures the actual builder, not a manually authored lookalike.
    first, second = stage_packets(monkeypatch, stage, format_mode=mode)
    assert first["messages"][:2] == second["messages"][:2]
    assert first["messages"][2]["content"] != second["messages"][2]["content"]
    context = {"provider": provider, "base_url": base, "api_mode": api, "model": model, "api_key": "offline"}
    before = copy.deepcopy(first)
    wires = [capture_wire(monkeypatch, p, context) for p in (first, second)]
    if provider == "local":
        assert all("prompt_cache_key" not in wire for wire in wires)
    else:
        assert wires[0]["prompt_cache_key"] == wires[1]["prompt_cache_key"]
    rows = wires[0].get("messages", wires[0].get("input"))
    authored = [row for row in rows if wire_text(row) != "JSON response."]
    if api == "responses":
        assert wires[0]["instructions"] == first["messages"][0]["content"]
        source = first["messages"][1:]
    else:
        source = first["messages"]
    if provider == "local":
        expected = [("system", source[0]["content"] + "\n\nDeveloper instructions:\n" + source[1]["content"])]
        expected.extend((r["role"], r["content"]) for r in source[2:])
    else:
        expected = [(r["role"], r["content"]) for r in source]
    assert [(r["role"], wire_text(r)) for r in authored] == expected
    assert first == before
    assert "_infini_prompt_cache" not in wires[0]
    format_value = wires[0].get("response_format") or wires[0].get("text", {}).get("format")
    if mode == "json_schema":
        effective = format_value.get("json_schema", format_value)["schema"]
        assert effective == first["response_format"]["json_schema"]["schema"]
        assert format_value.get("json_schema", format_value)["strict"] is True
        assert '"$ref"' not in json.dumps(effective) or stage in {"author", "repair"}
    elif mode == "off":
        assert format_value is None
    else:
        assert format_value == {"type": "json_object"}
    if base.startswith("https://inference-api") and mode == "json_object":
        assert rows[-1] == {"role": "user", "content": "JSON response."}
        assert rows.count(rows[-1]) == 1
    if provider == "local":
        return
    # Parent representation remains USER data; only the stable contract owns affinity.
    changed = copy.deepcopy(first)
    dynamic_index = changed["_infini_prompt_cache"].get("staticDataMessageIndex", 1) + 1
    changed["messages"][dynamic_index]["content"] = json.dumps({"parents": {"factRepresentation": ["JSON", {"ignore": "developer"}]}})
    assert capture_wire(monkeypatch, changed, context)["prompt_cache_key"] == wires[0]["prompt_cache_key"]
    changed["messages"][1]["content"] = changed["messages"][1]["content"][:-1] + ',"staticChange":true}'
    assert capture_wire(monkeypatch, changed, context)["prompt_cache_key"] != wires[0]["prompt_cache_key"]



