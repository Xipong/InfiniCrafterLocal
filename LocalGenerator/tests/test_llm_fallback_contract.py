from __future__ import annotations

from pathlib import Path
import io
import sys
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infini_local.pipelines import llm_transport as lp
from infini_local.desktop import settings_schema


def _http_error(url: str, code: int, body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "error", hdrs=None, fp=io.BytesIO(body.encode("utf-8")))


def _check_gui_exposes_fallback_model_fields() -> None:
    for key in [
        "INFINI_LLM_FALLBACK_PROVIDER",
        "INFINI_LLM_FALLBACK_MODEL",
        "INFINI_LLM_FALLBACK_BASE_URL",
        "INFINI_LLM_FALLBACK_API_KEY",
        "INFINI_LLM_FALLBACK_NETWORK_FAILS",
    ]:
        assert key in settings_schema.FIELD_ORDER
        assert key in settings_schema.DEFAULTS
    assert settings_schema.DEFAULTS["INFINI_LLM_FALLBACK_MODEL"] == ""
    assert settings_schema.DEFAULTS["INFINI_LLM_FALLBACK_NETWORK_FAILS"] == "2"


def _check_llm_chat_json_switches_to_fallback_on_budget_error(monkeypatch) -> None:
    monkeypatch.setattr(lp, "LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(lp, "OPENROUTER_BASE_URL", "https://primary.example/v1")
    monkeypatch.setattr(lp, "OPENROUTER_API_KEY", "pk")
    monkeypatch.setattr(lp, "OPENROUTER_MODEL", "primary-model")
    monkeypatch.setattr(lp, "LLM_FALLBACK_PROVIDER", "openai_compat")
    monkeypatch.setattr(lp, "LLM_FALLBACK_MODEL", "backup-model")
    monkeypatch.setattr(lp, "LLM_FALLBACK_BASE_URL", "https://fallback.example/v1")
    monkeypatch.setattr(lp, "LLM_FALLBACK_API_KEY", "fk")
    monkeypatch.setattr(lp, "LLM_FALLBACK_NETWORK_FAILS", 2)
    monkeypatch.setattr(lp, "LLM_POOL_PROFILES", ())
    monkeypatch.setattr(lp, "_RESOLVED_LLM_MODELS", {})
    lp._reset_llm_pool_runtime_for_tests()
    calls = []

    def fake_http_json(url, payload, timeout=10, headers=None):
        calls.append((url, dict(payload), (headers or {}).get("Authorization")))
        if "primary.example" in url:
            raise _http_error(url, 402, "insufficient credits")
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(lp, "http_json", fake_http_json)
    request = {"messages": [], "model": "ignored", lp.LLM_MODEL_OVERRIDE_KEY: "replacement-model"}
    with lp.llm_item_lease("legacy-fallback-boundary") as lease:
        out = lp.llm_chat_json(request, timeout=1)
        assert out["choices"][0]["message"]["content"] == "{}"
        assert lease.initial_profile_id == "llm_1"
        assert lease.profile_id == "legacy_fallback"
        second_out = lp.llm_chat_json(request, timeout=1)
        assert second_out["choices"][0]["message"]["content"] == "{}"
        assert lease.profile_id == "legacy_fallback"
    assert len(calls) == 3
    assert [payload["model"] for _, payload, _ in calls] == ["replacement-model", "backup-model", "backup-model"]
    assert calls[1][2] == "Bearer fk"
    assert all(lp.LLM_MODEL_OVERRIDE_KEY not in payload for _, payload, _ in calls)


def _check_llm_chat_json_switches_to_fallback_after_two_transport_failures(monkeypatch) -> None:
    monkeypatch.setattr(lp, "LLM_PROVIDER", "local")
    monkeypatch.setattr(lp, "LMSTUDIO_URL", "http://primary.local:1234")
    monkeypatch.setattr(lp, "LMSTUDIO_MODEL", "primary-local")
    monkeypatch.setattr(lp, "LLM_API_MODE", "chat_completions")
    monkeypatch.setattr(lp, "LLM_FALLBACK_PROVIDER", "local")
    monkeypatch.setattr(lp, "LLM_FALLBACK_MODEL", "backup-local")
    monkeypatch.setattr(lp, "LLM_FALLBACK_BASE_URL", "http://fallback.local:1234")
    monkeypatch.setattr(lp, "LLM_FALLBACK_API_KEY", "")
    monkeypatch.setattr(lp, "LLM_FALLBACK_NETWORK_FAILS", 2)
    monkeypatch.setattr(lp, "_RESOLVED_LLM_MODELS", {})
    calls = []

    def fake_http_json(url, payload, timeout=10, headers=None):
        calls.append((url, payload.get("model")))
        if "primary.local" in url:
            raise urllib.error.URLError("timed out")
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(lp, "http_json", fake_http_json)
    out = lp.llm_chat_json({"messages": [], "model": "ignored"}, timeout=1)
    assert out["choices"][0]["message"]["content"] == "{}"
    assert out["_debug"]["transportRetryCount"] == 2
    assert out["_debug"]["transportRetryCauses"] == ["primary_transport", "primary_transport_fallback"]
    assert calls == [
        ("http://primary.local:1234/v1/chat/completions", "primary-local"),
        ("http://primary.local:1234/v1/chat/completions", "primary-local"),
        ("http://fallback.local:1234/v1/chat/completions", "backup-local"),
    ]

def _check_llm_chat_json_retries_transient_http_without_fallback(monkeypatch) -> None:
    monkeypatch.setattr(lp, "LLM_PROVIDER", "local")
    monkeypatch.setattr(lp, "LMSTUDIO_URL", "http://single.local:1234")
    monkeypatch.setattr(lp, "LMSTUDIO_MODEL", "single-model")
    monkeypatch.setattr(lp, "LLM_API_MODE", "chat_completions")
    monkeypatch.setattr(lp, "LLM_FALLBACK_MODEL", "")
    monkeypatch.setattr(lp, "LLM_FALLBACK_NETWORK_FAILS", 2)
    monkeypatch.setattr(lp, "_RESOLVED_LLM_MODELS", {})
    monkeypatch.setattr(lp.time, "sleep", lambda _seconds: None)
    calls = []

    def fake_http_json(url, payload, timeout=10, headers=None):
        calls.append((url, payload.get("model")))
        if len(calls) == 1:
            raise _http_error(url, 503, "temporarily unavailable")
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(lp, "http_json", fake_http_json)
    out = lp.llm_chat_json({"messages": [], "model": "ignored"}, timeout=1)
    assert out["choices"][0]["message"]["content"] == "{}"
    assert out["_debug"]["transportRetryCount"] == 1
    assert out["_debug"]["transportRetryCauses"] == ["transient_http"]
    assert calls == [
        ("http://single.local:1234/v1/chat/completions", "single-model"),
        ("http://single.local:1234/v1/chat/completions", "single-model"),
    ]


def _check_network_attempt_budget_one_disables_inner_retry(monkeypatch) -> None:
    monkeypatch.setattr(lp, "LLM_PROVIDER", "local")
    monkeypatch.setattr(lp, "LMSTUDIO_URL", "http://single.local:1234")
    monkeypatch.setattr(lp, "LMSTUDIO_MODEL", "single-model")
    monkeypatch.setattr(lp, "LLM_API_MODE", "chat_completions")
    monkeypatch.setattr(lp, "LLM_FALLBACK_MODEL", "")
    monkeypatch.setattr(lp, "LLM_FALLBACK_NETWORK_FAILS", 1)
    monkeypatch.setattr(lp, "_RESOLVED_LLM_MODELS", {})
    calls = []

    def fake_http_json(url, payload, timeout=10, headers=None):
        calls.append((url, payload.get("model"), payload.get("response_format"), payload.get("reasoning")))
        raise _http_error(url, 400, "structured request rejected")

    monkeypatch.setattr(lp, "http_json", fake_http_json)
    structured_payload = {
        "messages": [],
        "model": "ignored",
        "response_format": {"type": "json_object"},
        "reasoning": {"effort": "low"},
    }
    try:
        lp.llm_chat_json(structured_payload, timeout=1)
    except urllib.error.HTTPError as error:
        assert error.code == 400
    else:
        raise AssertionError("expected the single structured transport attempt to fail")
    assert calls == [(
        "http://single.local:1234/v1/chat/completions",
        "single-model",
        {"type": "json_object"},
        None,
    )]


def _check_gemini_length_response_retries_once_with_minimal_reasoning(monkeypatch) -> None:
    calls = []

    def fake_single(payload, timeout, context):
        calls.append(payload)
        if len(calls) == 1:
            return {"choices": [{"finish_reason": "length", "message": {"content": "{"}}]}
        return {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}

    monkeypatch.setattr(lp, "_llm_json_single_context", fake_single)
    monkeypatch.setattr(lp, "_is_google_openai_compat_reasoning_model", lambda _model, _context: True)
    monkeypatch.setattr(lp, "log_event", lambda *_args, **_kwargs: None)
    payload = {
        "model": "gemini-3.1-flash-lite",
        "messages": [],
        lp._REASONING_INTENT_KEY: {"effort": "low", "exclude": True},
    }
    out = lp._llm_json_single_context_with_length_retry(payload, 1, {"model": payload["model"]})
    assert out["choices"][0]["finish_reason"] == "stop"
    assert len(calls) == 2
    assert calls[1][lp._REASONING_INTENT_KEY]["effort"] == "minimal"
    assert payload[lp._REASONING_INTENT_KEY]["effort"] == "low"


def _check_gemini_length_complete_json_prefix_is_not_retried(monkeypatch) -> None:
    calls = []
    content = '{"ok":true}\n' + ('}\n' * 128)

    def fake_single(payload, timeout, context):
        calls.append(payload)
        return {"choices": [{"finish_reason": "length", "message": {"content": content}}]}

    monkeypatch.setattr(lp, "_llm_json_single_context", fake_single)
    monkeypatch.setattr(lp, "_is_google_openai_compat_reasoning_model", lambda _model, _context: True)
    monkeypatch.setattr(lp, "log_event", lambda *_args, **_kwargs: None)
    payload = {
        "model": "gemini-3.1-flash-lite",
        "messages": [],
        "response_format": {"type": "json_object"},
        lp._REASONING_INTENT_KEY: {"effort": "minimal", "exclude": True},
    }
    out = lp._llm_json_single_context_with_length_retry(payload, 1, {"model": payload["model"]})
    assert lp.parse_first_valid_llm_json(out["choices"][0]["message"]["content"]) == {"ok": True}
    assert len(calls) == 1
    assert "transportRetryCount" not in out.get("_debug", {})


def _check_malformed_json_response_retries_once_inside_logical_call(monkeypatch) -> None:
    calls = []

    def fake_single(payload, timeout, context):
        calls.append(payload)
        content = '{"broken":' if len(calls) == 1 else '{"ok":true}'
        return {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}

    monkeypatch.setattr(lp, "_llm_json_single_context", fake_single)
    monkeypatch.setattr(lp, "log_event", lambda *_args, **_kwargs: None)
    context = {
        "provider": "openai_compat",
        "base_url": "http://single.local:1234",
        "model": "gemma-4-31b-it",
        "profile_id": "llm_1",
    }
    monkeypatch.setattr(lp, "_primary_llm_context", lambda: context)
    monkeypatch.setattr(lp, "_fallback_llm_context", lambda: None)
    payload = {
        "model": "gemma-4-31b-it",
        "messages": [],
        "response_format": {"type": "json_object"},
    }
    lease = lp.LlmItemLease(
        recipe_key="retry-accounting",
        lease_id="llm_1:1",
        profile_id="llm_1",
        context=context,
        pool_size=1,
    )
    token = lp._CURRENT_LLM_ITEM_LEASE.set(lease)
    try:
        out = lp.llm_chat_json(payload, timeout=1)
    finally:
        lp._CURRENT_LLM_ITEM_LEASE.reset(token)
    assert out["choices"][0]["message"]["content"] == '{"ok":true}'
    assert len(calls) == 2
    assert calls[1] == payload
    assert lease.call_count == 1
    assert len(lease.stages) == 1
    assert out["_debug"]["transportRetryCount"] == 1
    assert out["_debug"]["transportRetryCauses"] == ["malformed_json"]


# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_gui_exposes_fallback_model_fields',
    '_check_llm_chat_json_switches_to_fallback_on_budget_error',
    '_check_llm_chat_json_switches_to_fallback_after_two_transport_failures',
    '_check_llm_chat_json_retries_transient_http_without_fallback',
    '_check_network_attempt_budget_one_disables_inner_retry',
    '_check_gemini_length_response_retries_once_with_minimal_reasoning',
    '_check_gemini_length_complete_json_prefix_is_not_retried',
    '_check_malformed_json_response_retries_once_inside_logical_call'
    ]:
        _fn = globals()[_name]
        _sig = _inspect.signature(_fn)
        _kwargs = {}
        if "tmp_path" in _sig.parameters:
            _case_dir = tmp_path / _name
            _case_dir.mkdir(parents=True, exist_ok=True)
            _kwargs["tmp_path"] = _case_dir
        if "monkeypatch" in _sig.parameters:
            with _pytest.MonkeyPatch.context() as _mp:
                _kwargs["monkeypatch"] = _mp
                _fn(**_kwargs)
        else:
            _fn(**_kwargs)


def test_llm_fallback_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
