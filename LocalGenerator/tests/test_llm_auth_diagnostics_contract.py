import io
from urllib.error import HTTPError

import pytest

from infini_local.pipelines import llm_transport


def test_openrouter_auth_diagnostics_are_exposed_and_fail_fast(monkeypatch):
    # Config-only boundary: exercise actual health shaping, not a source literal.
    from infini_local.web import server

    monkeypatch.setattr(server, "sdcpp_debug_snapshot", lambda **kwargs: {"autostart": False, "command": []})
    monkeypatch.setattr(server, "_multiplayer_connect_info", lambda: {})
    monkeypatch.setattr(server.generation_debug, "last_combine_failure_summary", lambda: None)
    primary = {"provider": "openrouter", "base_url": "https://openrouter.ai/api/v1",
               "model": "test-model", "api_key": ""}
    monkeypatch.setattr(llm_transport, "_legacy_primary_llm_context", lambda: primary)
    monkeypatch.setattr(llm_transport, "configured_llm_pool", lambda: [])
    monkeypatch.setattr(llm_transport, "_fallback_llm_context", lambda: None)
    snapshot = llm_transport.llm_auth_snapshot()
    assert snapshot["provider"] == "openrouter"
    assert snapshot["apiKeyConfigured"] is False
    assert snapshot["status"] == "missing_api_key"
    assert "INFINI_OPENROUTER_API_KEY" in snapshot["hint"]
    assert "api_key" not in snapshot
    assert server._health_payload()["llmAuth"] == snapshot
    with pytest.raises(RuntimeError, match="INFINI_OPENROUTER_API_KEY"):
        llm_transport.ensure_llm_auth_configured(primary)
    primary["api_key"] = "test-key-not-real"
    configured = llm_transport.llm_auth_snapshot()
    assert configured["status"] == "configured"
    llm_transport.ensure_llm_auth_configured(primary)
    health = server._health_payload()
    assert health["llmAuth"] == configured
    assert "api_key" not in health["llmAuth"]
    assert primary["api_key"] not in repr(health)


def test_openrouter_unauthorized_request_reports_actionable_secret_free_diagnosis(monkeypatch):
    context = {"provider": "openrouter", "base_url": "https://openrouter.ai/api/v1",
               "model": "test-model", "api_key": "offline-rejected-key-not-real",
               "api_mode": "chat_completions"}
    calls, logs = [], []

    def unauthorized(url, payload, **options):
        calls.append((url, payload))
        raise HTTPError(url, 401, "Unauthorized", {}, io.BytesIO(
            ('{"error":{"message":"invalid key ' + context["api_key"] + '"}}').encode()))

    monkeypatch.setattr(llm_transport, "http_json", unauthorized)
    monkeypatch.setattr(llm_transport, "log_event", lambda *args: logs.append(args))
    monkeypatch.delenv("INFINI_LLM_REPLAY_RAW", raising=False)
    payload = {"model": "test-model", "messages": [{"role": "user", "content": "literal request"}]}
    with pytest.raises(RuntimeError, match="OpenRouter auth failed") as caught:
        llm_transport._llm_json_single_context(payload, 3, context)
    assert len(calls) == 1
    assert calls[0][0] == context["base_url"] + "/chat/completions"
    assert "401" in str(caught.value) and "config.env" in str(caught.value)
    assert logs and context["api_key"] not in repr(logs)
    assert context["api_key"] not in str(caught.value)
