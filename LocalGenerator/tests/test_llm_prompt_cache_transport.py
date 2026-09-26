from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from infini_local.core.llm_prompt_cache import with_prompt_cache_prefix, json_prefix_chars
from infini_local.pipelines import llm_transport as llm


def packet(suffix='{"recipeKey":"one"}'):
    return {"messages": [{"role": "system", "content": "Shared rules"},
                         {"role": "user", "content": '{"catalog":[], ' + suffix}],
            "response_format": {"type": "json_object"}}


def test_json_prefix_chars_requires_initial_static_keys_and_keeps_dynamic_tail():
    payload = {"catalog": "рецепт", "rules": [1], "recipeKey": "one"}
    assert json_prefix_chars(payload, ["catalog", "rules"]) == len('{"catalog":"рецепт","rules":[1],')
    assert json_prefix_chars(payload, ["catalog", "rules", "recipeKey"]) == len('{"catalog":"рецепт","rules":[1],"recipeKey":"one"}')
    for keys in ([], ["rules"], ["catalog", "recipeKey"], ["catalog", "missing"]):
        with pytest.raises(ValueError):
            json_prefix_chars(payload, keys)


def test_marker_copies_and_validates_exact_user_boundary():
    original = packet()
    marked = with_prompt_cache_prefix(original, message_index=1, prefix_chars=len('{"catalog":[], '))
    assert original == packet()
    assert marked["messages"] == original["messages"]
    assert marked["_infini_prompt_cache"] == {"messageIndex": 1, "prefixChars": len('{"catalog":[], ')}
    assert "_infini_prompt_cache" not in llm._clean_llm_payload(marked)
    for index, chars in [(0, 3), (1, 0), (1, 999), (True, 3), (1, True)]:
        with pytest.raises(ValueError):
            with_prompt_cache_prefix(original, message_index=index, prefix_chars=chars)


def test_identical_static_prefix_has_same_content_key_across_crafts_and_schema_changes_it():
    first = with_prompt_cache_prefix(packet(), message_index=1, prefix_chars=len('{"catalog":[], '))
    second = with_prompt_cache_prefix(packet('{"recipeKey":"two"}'), message_index=1, prefix_chars=len('{"catalog":[], '))
    a = llm._prompt_cache_identity(first, "gpt-5.5")
    b = llm._prompt_cache_identity(second, "gpt-5.5")
    assert a == b and a.startswith("infini-")
    assert "recipe" not in a and "Shared rules" not in a
    assert a != llm._prompt_cache_identity(first, "gpt-5.4")
    changed = dict(first, response_format={"type": "json_schema", "json_schema": {"schema": {"type": "object"}}})
    assert a != llm._prompt_cache_identity(changed, "gpt-5.5")
    reasoning_changed = dict(first, reasoning={"effort": "high"})
    assert a != llm._prompt_cache_identity(reasoning_changed, "gpt-5.5")
    role_changed = dict(first, messages=[{"role": "developer", "content": "Shared rules"}, first["messages"][1]])
    assert a != llm._prompt_cache_identity(role_changed, "gpt-5.5")
    # The key must not depend on Python's process-randomized hash seed.
    script = ("from infini_local.core.llm_prompt_cache import with_prompt_cache_prefix; "
              "from infini_local.pipelines.llm_transport import _prompt_cache_identity; "
              "p={'messages':[{'role':'system','content':'Shared rules'},"
              "{'role':'user','content':'{\"catalog\":[], {\"recipeKey\":\"another\"}'}],"
              "'response_format':{'type':'json_object'}}; "
              "print(_prompt_cache_identity(with_prompt_cache_prefix(p,message_index=1,prefix_chars=15),'gpt-5.5'))")
    child = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                           check=True, timeout=30, cwd=Path(__file__).resolve().parents[1])
    assert child.stdout.strip() == a


def test_platform_responses_explicit_breakpoint_preserves_exact_content_and_is_stateless(monkeypatch):
    monkeypatch.setattr(llm, "http_json", lambda url, body, **kw: sent.append(body) or {
        "id": "resp-id", "output_text": "{}", "usage": {"input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 12}}})
    sent = []
    ctx = {"provider": "openai_compat", "base_url": "https://api.openai.com/v1", "model": "gpt-5.6", "api_mode": "responses", "api_key": "test"}
    marked = with_prompt_cache_prefix(packet(), message_index=1, prefix_chars=len('{"catalog":[], '))
    with llm.llm_item_lease("first") as lease:
        # Exercise the actual same-profile lease branch, including a pre-existing
        # continuation. A distinct context object would bypass this guard.
        lease.context = ctx
        lease.previous_response_id = "previous-craft-stage"
        result = llm._llm_responses_json_single_context(marked, 1, ctx)
        llm._llm_responses_json_single_context(marked, 1, ctx)
        assert not lease.previous_response_id
    assert len(sent) == 2
    for wire in sent:
        assert "previous_response_id" not in wire
        assert "_infini_prompt_cache" not in str(wire)
        assert wire["prompt_cache_options"] == {"mode": "explicit"}
        blocks = wire["input"][0]["content"]
        assert blocks[0]["prompt_cache_breakpoint"] == {"mode": "explicit"}
        assert ''.join(block["text"] for block in blocks) == marked["messages"][1]["content"]
    assert result["_debug"]["cachedInputTokens"] == 0
    assert result["_debug"]["cacheHit"] is False
    assert result["_debug"]["cacheWriteTokens"] == 12


@pytest.mark.parametrize("provider,base,model", [
    ("openai_compat", "https://api.openai.com/v1", "gpt-5.6"),
    ("openrouter", "https://openrouter.ai/api/v1", "openai/gpt-5.6"),
    ("openai_compat", "https://api.openai.com/v1", "gpt-6-astra"),
])
def test_explicit_prefix_also_preserves_provider_routing_across_recipes(provider, base, model):
    ctx = {"provider": provider, "base_url": base, "model": model, "api_mode": "responses"}
    wires = []
    for suffix in ('{"recipeKey":"one"}', '{"recipeKey":"two"}'):
        source = with_prompt_cache_prefix(packet(suffix), message_index=1, prefix_chars=len('{"catalog":[], '))
        prepared = llm._payload_for_context(source, ctx)
        wires.append(llm._responses_payload_from_chat(prepared, cache_source=source, context=ctx))
    assert wires[0].get("prompt_cache_key"), "breakpoints alone leave sticky routing recipe-dependent"
    assert wires[0]["prompt_cache_key"] == wires[1]["prompt_cache_key"]
    assert wires[0]["prompt_cache_options"] == {"mode": "explicit"}
    assert wires[0]["input"] != wires[1]["input"]


def test_codex_subscription_keeps_prefix_routing_key_through_actual_adapter(monkeypatch):
    from infini_local.services import codex_text_backend as codex
    sent = []

    def capture(prepared, **_kwargs):
        sent.append(codex._request_payload(prepared))
        return {"choices": [{"message": {"content": "{}"}}], "usage": {}}

    monkeypatch.setattr(codex, "generate_chat", capture)
    ctx = {"provider": "openai_codex", "base_url": "https://chatgpt.com/backend-api/codex", "model": "gpt-5.4", "api_mode": "responses"}
    for suffix in ('{"recipeKey":"one"}', '{"recipeKey":"two"}'):
        source = with_prompt_cache_prefix(packet(suffix), message_index=1, prefix_chars=len('{"catalog":[], '))
        llm._llm_json_single_context(source, 1, ctx)
    assert sent[0].get("prompt_cache_key"), "Codex must not drop the supported cache routing hint"
    assert sent[0]["prompt_cache_key"] == sent[1]["prompt_cache_key"]
    assert sent[0]["input"] != sent[1]["input"]
    for wire in sent:
        assert wire["store"] is False
        assert "_infini_prompt_cache" not in str(wire)
        assert "prompt_cache_breakpoint" not in str(wire)
        assert "prompt_cache_options" not in wire


def test_unknown_compat_endpoint_gets_no_foreign_cache_fields():
    ctx = {"provider": "openai_compat", "base_url": "https://other.example/v1", "model": "gpt-5.6", "api_mode": "responses"}
    marked = with_prompt_cache_prefix(packet(), message_index=1, prefix_chars=5)
    prepared = llm._payload_for_context(marked, ctx)
    wire = llm._responses_payload_from_chat(prepared)
    assert "prompt_cache_key" not in wire
    assert "prompt_cache_options" not in wire
    assert wire["input"][0]["content"] == marked["messages"][1]["content"]
    assert "_infini_prompt_cache" not in prepared


def test_chat_route_is_provider_and_model_scoped_and_never_sends_internal_marker(monkeypatch):
    sent = []
    monkeypatch.setattr(llm, "http_json", lambda url, body, **kwargs: sent.append(body) or
                        {"choices": [{"message": {"content": "{}"}}]})
    marked = with_prompt_cache_prefix(packet(), message_index=1, prefix_chars=15)
    contexts = [
        ({"provider": "openai_compat", "base_url": "https://api.openai.com/v1", "model": "gpt-5.4", "api_mode": "chat_completions", "api_key": "secret-one"}, "key"),
        ({"provider": "openrouter", "base_url": "https://openrouter.ai/api/v1", "model": "openai/gpt-5.6", "api_mode": "chat_completions", "api_key": "secret-two"}, "explicit"),
        ({"provider": "openrouter", "base_url": "https://openrouter.ai/api/v1", "model": "google/gemini-3", "api_mode": "chat_completions", "api_key": "secret-three"}, "none"),
        ({"provider": "openai_compat", "base_url": "https://custom.example/v1", "model": "gpt-5.6", "api_mode": "chat_completions", "api_key": "secret-four"}, "none"),
    ]
    for ctx, route in contexts:
        llm._llm_chat_json_exact_context(marked, 1, ctx)
        body = sent[-1]
        assert "_infini_prompt_cache" not in str(body)
        if route == "key":
            assert body["prompt_cache_key"] == llm._prompt_cache_identity(marked, ctx["model"])
            assert "secret-one" not in str(body)
        elif route == "explicit":
            assert body["prompt_cache_options"] == {"mode": "explicit"}
            assert ''.join(part["text"] for part in body["messages"][1]["content"]) == marked["messages"][1]["content"]
            assert body["prompt_cache_key"] == llm._prompt_cache_identity(marked, ctx["model"])
        else:
            assert "prompt_cache_key" not in body and "prompt_cache_options" not in body
            assert body["messages"] == marked["messages"]


def test_codex_adapter_reports_missing_usage_distinct_from_zero(monkeypatch):
    from infini_local.services import codex_auth
    monkeypatch.setattr(codex_auth, "get_credentials", lambda: codex_auth.Credentials("fake-access", "fake-refresh", "fake-account", 9999999999))
    monkeypatch.setattr(codex_auth, "post_sse", lambda url, body, **kwargs: {
        "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "{}"}]}],
        "usage": {"input_tokens": 7}})
    ctx = {"provider": "openai_codex", "base_url": "https://chatgpt.com/backend-api/codex", "model": "test-model", "api_mode": "responses", "api_key": ""}
    result = llm._llm_json_single_context(with_prompt_cache_prefix(packet(), message_index=1, prefix_chars=5), 1, ctx)
    assert result["_debug"]["cachedInputTokens"] is None
    assert result["_debug"]["cacheHit"] is None


def test_codex_adapter_preserves_provider_cache_write_counter(monkeypatch):
    from infini_local.services import codex_auth, codex_text_backend
    monkeypatch.setattr(codex_auth, "get_credentials", lambda: codex_auth.Credentials("fake-access", "fake-refresh", "fake-account", 9999999999))
    monkeypatch.setattr(codex_auth, "post_sse", lambda url, body, **kwargs: {
        "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "{}"}]}],
        "usage": {"input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 30, "not_a_counter": "private"}}})
    result = codex_text_backend.generate_chat({"model": "test-model", "messages": packet()["messages"]}, timeout=1)
    assert result["usage"]["input_tokens_details"] == {"cached_tokens": 0, "cache_write_tokens": 30}


def test_usage_missing_is_not_zero_or_hit_and_real_positive_is_hit():
    missing = llm._usage_fields({"usage": {"input_tokens": 50}})
    zero = llm._usage_fields({"usage": {"prompt_tokens_details": {"cached_tokens": 0}}})
    positive = llm._usage_fields({"usage": {"input_tokens_details": {"cached_tokens": 20, "cache_write_tokens": 0}}})
    assert missing["cachedInputTokens"] is None and missing["cacheHit"] is None
    assert zero["cachedInputTokens"] == 0 and zero["cacheHit"] is False
    assert positive["cachedInputTokens"] == 20 and positive["cacheHit"] is True
    assert positive["cacheWriteTokens"] == 0
