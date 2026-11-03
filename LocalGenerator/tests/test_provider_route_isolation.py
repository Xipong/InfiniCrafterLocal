"""Regression witnesses for configured provider routes and account isolation."""
from __future__ import annotations

import copy

import pytest

from infini_local.pipelines.transport import client, http, profiles
from test_provider_transport_contract import packet, wire  # noqa: F401 - imported pytest fixture


@pytest.mark.parametrize("base,path", [
    ("https://generativelanguage.googleapis.com/v1beta/openai/", "/v1beta/openai"),
    ("https://provider.example/compatible/api", "/compatible/api"),
    ("http://127.0.0.1:1234", "/v1"),
    ("https://provider.example/v1", "/v1"),
])
def test_explicit_provider_api_base_is_used_for_generation_and_discovery(wire, monkeypatch, base, path):
    context = {"provider": "openai_compat", "base_url": base, "model": "auto",
               "api_mode": "chat_completions", "api_key": "synthetic-route-key"}
    discoveries = []

    def discover(url, **_kwargs):
        discoveries.append(url)
        return {"data": [{"id": "advertised-model"}]}

    monkeypatch.setattr(http, "http_get_json", discover)
    client._llm_json_single_context(packet(), 1, context)
    origin = base.split("/", 3)[:3]
    expected = "/".join(origin) + path
    assert discoveries == [expected + "/models"]
    assert wire.calls[0][0] == expected + "/chat/completions"
    assert profiles.llm_responses_url(context) == expected + "/responses"


def test_auto_model_discovery_is_scoped_to_the_configured_account(wire, monkeypatch):
    contexts = [{"provider": "openai_compat", "base_url": "https://provider.example/v1",
                 "model": "auto", "api_mode": "chat_completions", "profile_id": f"llm_{index}",
                 "api_key": f"synthetic-account-{index}"} for index in (1, 2)]
    discoveries = []

    def discover(_url, *, headers, **_kwargs):
        account = headers["Authorization"].rsplit("-", 1)[1]
        discoveries.append(account)
        return {"data": [{"id": f"account-{account}-model"}]}

    monkeypatch.setattr(http, "http_get_json", discover)
    for context in (*contexts, contexts[0]):
        client._llm_json_single_context(packet(), 1, context)
    assert [body["model"] for _, body, _ in wire.calls] == [
        "account-1-model", "account-2-model", "account-1-model",
    ]
    assert discoveries == ["1", "2"]


@pytest.mark.parametrize("mode", ["chat_completions", "responses"])
def test_explicit_xhigh_effort_is_preserved_across_api_modes(wire, mode):
    context = {"provider": "openai_compat", "base_url": "https://api.openai.com/v1",
               "model": "gpt-6-sol", "api_mode": mode, "api_key": "synthetic-platform-key"}
    request = packet()
    request["reasoning"] = {"effort": "xhigh", "exclude": True}
    before = copy.deepcopy(request)
    client._llm_json_single_context(request, 1, context)
    sent = wire.calls[0][1]
    effort = sent.get("reasoning_effort") or sent.get("reasoning", {}).get("effort")
    assert effort == "xhigh"
    assert request == before


def test_openai_chat_uses_its_native_reasoning_field(wire):
    context = {"provider": "openai_compat", "base_url": "https://api.openai.com/v1",
               "model": "gpt-6-sol", "api_mode": "chat_completions",
               "api_key": "synthetic-platform-key"}
    request = packet()
    request["reasoning"] = {"effort": "medium", "exclude": True}
    client._llm_json_single_context(request, 1, context)
    sent = wire.calls[0][1]
    assert sent.get("reasoning_effort") == "medium"
    assert "reasoning" not in sent


def test_openai_chat_rejects_numeric_reasoning_budget_before_sending(wire):
    wire.configure(LLM_PROVIDER="openai_compat", LLM_API_MODE="chat_completions",
                   OPENAI_COMPAT_BASE_URL="https://api.openai.com/v1",
                   OPENAI_COMPAT_MODEL="gpt-6-sol")
    request = packet()
    request["reasoning"] = {"max_tokens": 4096, "exclude": True}
    before = copy.deepcopy(request)
    with pytest.raises(ValueError, match="numeric reasoning budget; select a reasoning effort"):
        client.llm_chat_json(request, timeout=1)
    assert wire.calls == []
    assert request == before


@pytest.mark.parametrize("provider,base,model,expected", [
    ("openrouter", "https://openrouter.ai/api/v1", "vendor/reasoning-model",
     {"reasoning": {"max_tokens": 4096, "exclude": True}}),
    ("openai_compat", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.5-flash-lite",
     {"reasoning_effort": "medium"}),
])
def test_other_provider_numeric_reasoning_budgets_keep_existing_projection(wire, provider, base, model, expected):
    context = {"provider": provider, "base_url": base, "model": model,
               "api_mode": "chat_completions", "api_key": "synthetic-budget-key"}
    request = packet()
    request["reasoning"] = {"max_tokens": 4096, "exclude": True}
    before = copy.deepcopy(request)
    client._llm_json_single_context(request, 1, context)
    assert len(wire.calls) == 1
    sent = wire.calls[0][1]
    assert {name: sent[name] for name in ("reasoning", "reasoning_effort") if name in sent} == expected
    assert request == before
