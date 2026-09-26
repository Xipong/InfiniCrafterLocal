"""Account-scoped subscription model discovery is read-only and fail-closed."""

import time

import pytest

from infini_local.services import codex_auth


@pytest.fixture
def account_credentials(monkeypatch):
    credentials = codex_auth.Credentials(
        "test-access-not-real", "test-refresh-not-real", "test-account", time.time() + 3600,
    )
    monkeypatch.setattr(codex_auth, "get_credentials", lambda: credentials)
    return credentials


def test_visible_subscription_text_models_keep_declared_reasoning_without_platform_filter(monkeypatch, account_credentials):
    from infini_local.services import codex_catalog

    captured = []
    def get(url, **options):
        captured.append((url, options))
        return {"models": [
            {"slug": "hidden-model", "display_name": "Hidden", "visibility": "hide", "priority": 0},
            {"slug": "model-high", "display_name": "High", "visibility": "list", "priority": 10,
             "supported_in_api": False, "default_reasoning_level": "low",
             "supported_reasoning_levels": [{"effort": "low", "description": "Low"}, {"effort": "high", "description": "High"}]},
            {"slug": "model-first", "display_name": "First", "visibility": "list", "priority": 1,
             "supported_reasoning_levels": [{"effort": "medium", "description": "Medium"}]},
            {"slug": "model-first", "display_name": "Duplicate", "visibility": "list", "priority": 2},
        ]}
    monkeypatch.setattr(codex_auth, "get_json", get)
    models = codex_catalog.list_text_models()
    assert [m.slug for m in models] == ["model-first", "model-high"]
    assert models[1].efforts == ("low", "high")
    assert models[1].default_effort == "low"
    assert captured[0][0].startswith("https://chatgpt.com/backend-api/codex/models?client_version=")
    assert captured[0][1]["headers"]["Authorization"] == "Bearer test-access-not-real"
    assert captured[0][1]["headers"]["ChatGPT-Account-Id"] == "test-account"
    assert "api.openai.com" not in captured[0][0]


def test_catalog_never_returns_echoed_session_credentials_as_model_metadata(monkeypatch, account_credentials):
    from infini_local.services import codex_catalog
    credentials = account_credentials
    monkeypatch.setattr(codex_auth, "get_json", lambda *a, **kw: {"models": [
        {"slug": credentials.access_token, "visibility": "list", "display_name": "unsafe"},
        {"slug": "gpt-safe", "visibility": "list", "display_name": "echo " + credentials.access_token,
         "supported_reasoning_levels": [{"effort": credentials.access_token}, {"effort": "low"}],
         "default_reasoning_level": credentials.access_token},
    ]})
    models = codex_catalog.list_text_models()
    assert len(models) == 1
    assert models[0].slug == "gpt-safe"
    assert models[0].label == "gpt-safe"
    assert models[0].efforts == ("low",)
    assert models[0].default_effort == ""
    assert credentials.access_token not in repr(models)


def test_empty_or_invalid_model_catalog_is_an_error_not_an_invented_slug(monkeypatch, account_credentials):
    from infini_local.services import codex_catalog

    monkeypatch.setattr(codex_auth, "get_json", lambda *a, **kw: {"models": [{"slug": "", "visibility": "list"}]})
    with pytest.raises(codex_auth.CodexError):
        codex_catalog.list_text_models()
