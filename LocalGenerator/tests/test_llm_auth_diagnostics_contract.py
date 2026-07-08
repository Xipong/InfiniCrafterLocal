from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "infini_local" / "web" / "server.py"
LLM_PIPELINE = ROOT / "infini_local" / "pipelines" / "llm_authoring_pipeline.py"
LLM_TRANSPORT = ROOT / "infini_local" / "pipelines" / "llm_transport.py"
UTILITY_ROUTES = ROOT / "infini_local" / "web" / "server_utility_routes.py"


def _check_openrouter_auth_diagnostics_are_exposed_and_fail_fast():
    server_text = SERVER.read_text(encoding="utf-8")
    text = LLM_PIPELINE.read_text(encoding="utf-8") + LLM_TRANSPORT.read_text(encoding="utf-8")
    assert "def llm_auth_snapshot" in text
    assert "llm_auth_snapshot" in server_text
    assert "missing_api_key" in text
    assert "Set INFINI_OPENROUTER_API_KEY" in text
    assert '"llmAuth": llm_auth_snapshot()' in server_text
    assert "ensure_llm_auth_configured()" in text
    assert "OpenRouter auth failed" in text


def _check_server_exposes_local_shutdown_endpoint_for_gui_restart():
    server_text = SERVER.read_text(encoding="utf-8")
    route_text = UTILITY_ROUTES.read_text(encoding="utf-8")
    assert "ServerUtilityRoutes" in server_text
    assert 'path.startswith("/shutdown")' in route_text
    assert '"shutdown scheduled"' in route_text
    assert 'cleanup_for_shutdown("http_shutdown")' in route_text
    assert 'handler.server.shutdown()' in route_text

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_openrouter_auth_diagnostics_are_exposed_and_fail_fast',
    '_check_server_exposes_local_shutdown_endpoint_for_gui_restart'
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


def test_llm_auth_diagnostics_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
