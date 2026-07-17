from __future__ import annotations

from infini_local.pipelines import llm_transport as transport


def _contract_check_google_openai_compat_uses_native_reasoning_effort(monkeypatch) -> None:
    monkeypatch.setattr(transport, "active_llm_provider", lambda context=None: "openai_compat")
    monkeypatch.setattr(
        transport,
        "llm_base_url",
        lambda context=None: "https://generativelanguage.googleapis.com/v1beta/openai",
    )
    monkeypatch.setattr(transport, "LLM_REASONING_MODE", "auto")

    automatic = transport.apply_llm_common_options({}, model_name="gemini-3.1-flash-lite")
    assert automatic["reasoning_effort"] == "medium"
    assert "reasoning" not in automatic

    monkeypatch.setattr(transport, "LLM_REASONING_MODE", "xhigh")
    strongest = transport.apply_llm_common_options({}, model_name="gemini-3.1-flash-lite")
    assert strongest["reasoning_effort"] == "high"
    assert "reasoning" not in strongest

    monkeypatch.setattr(transport, "LLM_REASONING_MODE", "minimal")
    gemma = transport.apply_llm_common_options({}, model_name="gemma-4-31b-it")
    assert gemma["reasoning_effort"] == "minimal"
    assert "reasoning" not in gemma


def _contract_check_non_google_remote_keeps_reasoning_envelope(monkeypatch) -> None:
    monkeypatch.setattr(transport, "active_llm_provider", lambda context=None: "openrouter")
    monkeypatch.setattr(transport, "llm_base_url", lambda context=None: "https://openrouter.ai/api/v1")
    monkeypatch.setattr(transport, "LLM_REASONING_MODE", "medium")

    req = transport.apply_llm_common_options({}, model_name="google/gemini-3.1-flash-lite")
    assert req["reasoning"] == {"effort": "medium", "exclude": transport.LLM_REASONING_EXCLUDE}
    assert "reasoning_effort" not in req


def _contract_check_reasoning_control_is_remapped_for_each_fallback_context(monkeypatch) -> None:
    monkeypatch.setattr(transport, "LLM_REASONING_MODE", "medium")
    monkeypatch.setattr(transport, "resolve_llm_model", lambda context=None: (context or {})["model"])
    monkeypatch.setattr(transport, "active_llm_provider", lambda context=None: (context or {})["provider"])
    monkeypatch.setattr(transport, "llm_base_url", lambda context=None: (context or {})["base_url"])
    google = {
        "provider": "openai_compat",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-3.1-flash-lite",
    }
    openrouter = {
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "google/gemini-3.1-flash-lite",
    }

    to_google = transport._payload_for_context(
        {"model": "google/gemini-3.1-flash-lite", "reasoning": {"effort": "medium", "exclude": True}},
        google,
    )
    assert to_google["reasoning_effort"] == "medium"
    assert "reasoning" not in to_google

    to_openrouter = transport._payload_for_context(
        {"model": "gemini-3.1-flash-lite", "reasoning_effort": "medium"},
        openrouter,
    )
    assert to_openrouter["reasoning"] == {"effort": "medium", "exclude": transport.LLM_REASONING_EXCLUDE}
    assert "reasoning_effort" not in to_openrouter


def _contract_check_local_primary_preserves_reasoning_intent_for_remote_fallback(monkeypatch) -> None:
    monkeypatch.setattr(transport, "LLM_REASONING_MODE", "medium")
    contexts = {
        "local": {"provider": "local", "base_url": "http://127.0.0.1:1234/v1", "model": "local-model"},
        "google": {"provider": "openai_compat", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-3.1-flash-lite"},
    }
    monkeypatch.setattr(transport, "resolve_llm_model", lambda context=None: (context or {})["model"])
    monkeypatch.setattr(transport, "active_llm_provider", lambda context=None: (context or contexts["local"])["provider"])
    monkeypatch.setattr(transport, "llm_base_url", lambda context=None: (context or contexts["local"])["base_url"])

    authored = transport.apply_llm_common_options({}, model_name="local-model")
    local_payload = transport._payload_for_context(authored, contexts["local"])
    google_payload = transport._payload_for_context(authored, contexts["google"])

    assert "reasoning" not in local_payload and "reasoning_effort" not in local_payload
    assert google_payload["reasoning_effort"] == "medium"
    assert all(not key.startswith("_infini_") for key in local_payload)
    assert all(not key.startswith("_infini_") for key in google_payload)


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_llm_reasoning_compat_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_google_openai_compat_uses_native_reasoning_effort',
            '_contract_check_non_google_remote_keeps_reasoning_envelope',
            '_contract_check_reasoning_control_is_remapped_for_each_fallback_context',
            '_contract_check_local_primary_preserves_reasoning_intent_for_remote_fallback',
        ),
    )
