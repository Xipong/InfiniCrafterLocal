"""Subscription LLM is an owned provider, never an OpenAI Platform alias."""

import pytest

from infini_local.pipelines import llm_transport as llm


def test_subscription_responses_preserve_stage_packet_without_paid_fallback(monkeypatch):
    from infini_local.services import codex_auth, codex_text_backend
    import time
    credentials = codex_auth.Credentials("test-access-not-real", "test-refresh-not-real", "test-account", time.time() + 3600)
    monkeypatch.setattr(codex_auth, "get_credentials", lambda: credentials)
    calls = []
    def post(url, payload, **kwargs):
        calls.append((url, payload, kwargs))
        return {"id": "resp-test", "status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": '{"item":"ok"}'}]}], "usage": {"input_tokens": 10, "output_tokens": 4}}
    monkeypatch.setattr(codex_auth, "post_sse", post, raising=False)
    packet = {"model": "test-codex-model", "messages": [{"role": "system", "content": "Literal system contract"}, {"role": "user", "content": "Literal authored item"}], "max_tokens": 2048, "response_format": {"type": "json_object"}, "reasoning": {"effort": "low", "exclude": True}, "temperature": 0.38}
    result = codex_text_backend.generate_chat(packet, timeout=20)
    assert result["choices"][0]["message"]["content"] == '{"item":"ok"}'
    assert result["usage"]["output_tokens"] == 4
    url, body, options = calls[0]
    assert url == "https://chatgpt.com/backend-api/codex/responses"
    assert body["model"] == "test-codex-model"
    assert body["instructions"] == "Literal system contract"
    assert body["input"] == [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Literal authored item"}]}]
    assert body["reasoning"] == {"effort": "low"}
    assert body["text"]["format"] == {"type": "json_object"}
    assert body["stream"] is True and body["store"] is False and body["tools"] == []
    assert "max_output_tokens" not in body  # Subscription /responses rejects this (HTTP 400).
    assert "temperature" not in body
    assert options["headers"]["Authorization"] == "Bearer " + credentials.access_token
    assert options["headers"]["ChatGPT-Account-Id"] == credentials.account_id
    assert len(calls) == 1


def test_subscription_response_does_not_expose_provider_metadata_or_token(monkeypatch):
    from infini_local.services import codex_auth, codex_text_backend
    credentials = codex_auth.Credentials("test-access-not-real", "test-refresh-not-real", "test-account", 9999999999)
    monkeypatch.setattr(codex_auth, "get_credentials", lambda: credentials)
    monkeypatch.setattr(codex_auth, "post_sse", lambda *a, **kw: {
        "id": "test-access-not-real", "status": "completed",
        "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": '{"ok":true}'}]}],
        "usage": {"input_tokens": 3, "output_tokens": 5, "attribution": {"secret": "test-access-not-real"}},
    })
    result = codex_text_backend.generate_chat({"model": "test-model", "messages": [{"role": "user", "content": "test"}]}, timeout=3)
    assert result["usage"] == {"input_tokens": 3, "output_tokens": 5}
    assert "test-access-not-real" not in repr(result)


def test_codex_rejects_provider_output_echoing_session_credentials(monkeypatch):
    from infini_local.services import codex_auth, codex_text_backend
    credentials = codex_auth.Credentials("test-access-not-real", "test-refresh-not-real", "test-account", 9999999999)
    monkeypatch.setattr(codex_auth, "get_credentials", lambda: credentials)
    leaked = '{"nested":"\\u0074est-access-not-real"}'
    monkeypatch.setattr(codex_auth, "post_sse", lambda *a, **kw: {
        "status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": leaked}]}],
    })
    with pytest.raises(codex_auth.CodexError, match="credential") as caught:
        codex_text_backend.generate_chat({"model": "test-model", "messages": [{"role": "user", "content": "test"}]}, timeout=3)
    assert "test-access-not-real" not in str(caught.value)


def test_codex_urls_never_append_platform_v1():
    from infini_local.services import codex_auth, codex_catalog
    context = {"provider": "openai_codex", "base_url": "https://api.openai.com/v1", "model": "test-model"}
    assert llm.llm_responses_url(context) == "https://chatgpt.com/backend-api/codex/responses"
    assert llm.llm_models_url(context) == codex_catalog.MODELS_URL + "?client_version=" + codex_catalog.CLIENT_VERSION
    with pytest.raises(codex_auth.CodexError):
        llm.llm_chat_completions_url(context)


def test_codex_diagnostics_report_owned_session_not_local_server(monkeypatch):
    from infini_local.services import codex_auth
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai_codex")
    monkeypatch.setattr(llm, "CODEX_LLM_MODEL", "test-model", raising=False)
    monkeypatch.setattr(codex_auth, "auth_status", lambda: {"authenticated": False, "expired": False})
    snapshot = llm.llm_auth_snapshot()
    assert snapshot["provider"] == "openai_codex"
    assert snapshot["status"] == "sign_in_required"
    assert snapshot["apiKeyConfigured"] is None
    assert "api.openai.com" not in str(snapshot)


def test_explicit_codex_fallback_retains_subscription_origin(monkeypatch):
    monkeypatch.setattr(llm, "LLM_FALLBACK_PROVIDER", "openai_codex")
    monkeypatch.setattr(llm, "LLM_FALLBACK_MODEL", "test-model")
    monkeypatch.setattr(llm, "LLM_FALLBACK_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr(llm, "LLM_FALLBACK_API_KEY", "test-paid-key-not-real")
    monkeypatch.setattr(llm, "LLM_PROVIDER", "local")
    context = llm._fallback_llm_context()
    assert context is not None
    assert context["provider"] == "openai_codex"
    assert context["base_url"] == "https://chatgpt.com/backend-api/codex"
    assert context["api_key"] == ""
    assert context["api_mode"] == "responses"


def test_codex_rejects_untranslatable_reasoning_budget_instead_of_silently_ignoring():
    from infini_local.services import codex_auth, codex_text_backend
    packet = {"model": "test-model", "messages": [{"role": "user", "content": "test"}], "reasoning": {"max_tokens": 1500}}
    with pytest.raises(codex_auth.CodexError, match="reasoning"):
        codex_text_backend._request_payload(packet)


def test_codex_pool_profile_ignores_supplied_paid_endpoint_and_key():
    ctx = llm._pool_profile_context({"id": "llm_2", "enabled": True, "provider": "openai_codex", "model": "test-model", "base_url": "https://api.openai.com/v1", "api_key": "test-platform-key-not-real", "api_mode": "chat_completions"})
    assert ctx is not None
    assert ctx["provider"] == "openai_codex"
    assert ctx["base_url"] == "https://chatgpt.com/backend-api/codex"
    assert ctx["api_key"] == ""
    assert ctx["api_mode"] == "responses"


def test_visual_director_codex_reasoning_is_stage_scoped(monkeypatch):
    monkeypatch.setattr(llm, "CODEX_VISUAL_REASONING", "low", raising=False)
    ctx = {"provider": "openai_codex", "model": "test-model", "base_url": "https://chatgpt.com/backend-api/codex", "api_mode": "responses", "api_key": ""}
    packet = {"messages": [{"role": "user", "content": "literal image description"}], "reasoning": {"effort": "high"}, "_infini_stage": "visual_director"}
    prepared = llm._payload_for_context(packet, ctx)
    assert prepared["reasoning"]["effort"] == "low"
    assert llm._payload_for_context({**packet, "_infini_stage": "planner"}, ctx)["reasoning"]["effort"] == "high"


def test_codex_catalog_max_reasoning_reaches_stage_payload(monkeypatch):
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai_codex")
    monkeypatch.setattr(llm, "LLM_REASONING_MODE", "max")
    ctx = {"provider": "openai_codex", "model": "gpt-6-sol", "base_url": "https://chatgpt.com/backend-api/codex", "api_mode": "responses", "api_key": ""}
    configured = llm.llm_reasoning_payload("gpt-6-sol", ctx)
    assert configured is not None and configured["effort"] == "max"
    prepared = llm._payload_for_context({"messages": [{"role": "user", "content": "test"}], "reasoning": configured}, ctx)
    assert prepared["reasoning"]["effort"] == "max"
    authored = llm.apply_minimum_reasoning_effort({"reasoning": configured}, model_name="gpt-6-sol", minimum="medium")
    assert authored["reasoning"]["effort"] == "max"


def test_visual_stage_flows_from_pipeline_to_subscription_only(monkeypatch):
    from infini_local.services import codex_auth
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai_codex")
    monkeypatch.setattr(llm, "CODEX_LLM_MODEL", "test-model")
    monkeypatch.setattr(llm, "CODEX_VISUAL_REASONING", "low")
    monkeypatch.setattr(llm, "LLM_FALLBACK_PROVIDER", "openrouter")
    monkeypatch.setattr(llm, "LLM_FALLBACK_MODEL", "paid-model-not-allowed")
    monkeypatch.setattr(codex_auth, "get_credentials", lambda: codex_auth.Credentials("test-access-not-real", "test-refresh-not-real", "test-account", 9999999999))
    monkeypatch.setattr(llm, "http_json", lambda *a, **k: (_ for _ in ()).throw(AssertionError("paid/legacy HTTP called")))
    sent = []
    def post(url, body, **kwargs):
        sent.append((url, body, kwargs))
        return {"status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": '{"visual":"ok"}'}]}]}
    monkeypatch.setattr(codex_auth, "post_sse", post)
    result = llm.llm_chat_json(llm.with_llm_stage({"messages": [{"role": "system", "content": "authored constraints"}, {"role": "user", "content": "authored visual request"}], "response_format": {"type": "json_object"}, "max_tokens": 1024, "reasoning": {"effort": "high"}}, "visual_director"), timeout=5)
    assert result["choices"][0]["message"]["content"] == '{"visual":"ok"}'
    assert len(sent) == 1
    assert sent[0][0] == "https://chatgpt.com/backend-api/codex/responses"
    assert sent[0][1]["model"] == "test-model"
    assert sent[0][1]["reasoning"] == {"effort": "low"}
    assert sent[0][1]["instructions"] == "authored constraints"
    assert sent[0][1]["input"][0]["content"][0]["text"] == "authored visual request"


def test_codex_provider_does_not_fail_over_to_paid_route(monkeypatch):
    from infini_local.services.codex_auth import CodexError
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai_codex")
    monkeypatch.setattr(llm, "CODEX_LLM_MODEL", "test-codex-model", raising=False)
    monkeypatch.setattr(llm, "LLM_FALLBACK_PROVIDER", "openrouter")
    monkeypatch.setattr(llm, "LLM_FALLBACK_MODEL", "paid-route-not-authorized")
    monkeypatch.setattr(llm, "configured_llm_pool", lambda: [llm._legacy_primary_llm_context()])
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise CodexError("OpenAI HTTP 429: quota")
    monkeypatch.setattr(llm, "_llm_json_single_context", fail)
    with pytest.raises(CodexError, match="429"):
        llm.llm_chat_json({"model": "test-codex-model", "messages": [{"role": "user", "content": "test"}]}, timeout=3)
    assert calls == [1]


def test_primary_codex_profile_uses_separate_subscription_model_and_no_platform_key(monkeypatch):
    monkeypatch.setattr(llm, "LLM_PROVIDER", "openai_codex")
    monkeypatch.setattr(llm, "CODEX_LLM_MODEL", "test-codex-model", raising=False)
    monkeypatch.setattr(llm, "OPENAI_COMPAT_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr(llm, "OPENAI_COMPAT_API_KEY", "test-platform-key-not-real")

    context = llm._legacy_primary_llm_context()

    assert context["provider"] == "openai_codex"
    assert context["model"] == "test-codex-model"
    assert context["api_key"] == ""
    assert context["api_mode"] == "responses"
    assert context["base_url"] != "https://api.openai.com/v1"
