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
    monkeypatch.setattr(lp, "_RESOLVED_LLM_MODELS", {})
    calls = []

    def fake_http_json(url, payload, timeout=10, headers=None):
        calls.append((url, payload.get("model"), headers.get("Authorization")))
        if "primary.example" in url:
            raise _http_error(url, 402, "insufficient credits")
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(lp, "http_json", fake_http_json)
    out = lp.llm_chat_json({"messages": [], "model": "ignored"}, timeout=1)
    assert out["choices"][0]["message"]["content"] == "{}"
    assert len(calls) == 2
    assert calls[0][1] == "primary-model"
    assert calls[1][1] == "backup-model"
    assert calls[1][2] == "Bearer fk"


def _check_llm_chat_json_switches_to_fallback_after_two_transport_failures(monkeypatch) -> None:
    monkeypatch.setattr(lp, "LLM_PROVIDER", "local")
    monkeypatch.setattr(lp, "LMSTUDIO_URL", "http://primary.local:1234")
    monkeypatch.setattr(lp, "LMSTUDIO_MODEL", "primary-local")
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
    assert calls == [
        ("http://primary.local:1234/v1/chat/completions", "primary-local"),
        ("http://primary.local:1234/v1/chat/completions", "primary-local"),
        ("http://fallback.local:1234/v1/chat/completions", "backup-local"),
    ]

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_gui_exposes_fallback_model_fields',
    '_check_llm_chat_json_switches_to_fallback_on_budget_error',
    '_check_llm_chat_json_switches_to_fallback_after_two_transport_failures'
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
