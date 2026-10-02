from pathlib import Path

import pytest

from infini_local.pipelines import llm_transport

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "infini_local" / "web" / "server.py"
LLM_TRANSPORT = ROOT / "infini_local" / "pipelines" / "llm_transport.py"
UTILITY_ROUTES = ROOT / "infini_local" / "web" / "server_utility_routes.py"


def _check_openrouter_auth_diagnostics_are_exposed_and_fail_fast(monkeypatch):
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

    assert "OpenRouter auth failed" in LLM_TRANSPORT.read_text(encoding="utf-8")


def _check_server_exposes_local_shutdown_endpoint_for_gui_restart():
    server_text = SERVER.read_text(encoding="utf-8")
    route_text = UTILITY_ROUTES.read_text(encoding="utf-8")
    assert "ServerUtilityRoutes" in server_text
    assert 'path.startswith("/shutdown")' in route_text
    assert '"shutdown scheduled"' in route_text
    assert 'cleanup_for_shutdown("http_shutdown")' in route_text
    assert 'handler.server.shutdown()' in route_text


# One collected item per contract module: the checks above keep source order and
# their own tracebacks. The shared runner discovers them by prefix, so a new check
# cannot be silently left out of a hand-maintained dispatch list.
def test_llm_auth_diagnostics_contract_coarse_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(globals(), request, prefix="_check_")
