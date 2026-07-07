from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER_SOURCE = (ROOT / "LocalGenerator" / "infini_local" / "web" / "server.py").read_text(encoding="utf-8")
NETWORK_INFO_SOURCE = (ROOT / "LocalGenerator" / "infini_local" / "services" / "network_info_service.py").read_text(encoding="utf-8")
UTILITY_ROUTES_SOURCE = (ROOT / "LocalGenerator" / "infini_local" / "web" / "server_utility_routes.py").read_text(encoding="utf-8")
CONFIG_EXAMPLE = (ROOT / "LocalGenerator" / "config.example.env").read_text(encoding="utf-8")


def _check_network_info_service_owns_multiplayer_connect_card() -> None:
    assert "from infini_local.services import network_info_service" in SERVER_SOURCE
    assert "def multiplayer_connect_info" not in SERVER_SOURCE
    assert "def multiplayer_connect_info" in NETWORK_INFO_SOURCE
    assert "def radmin_ipv4_candidates" in NETWORK_INFO_SOURCE
    assert '"transportPolicy"' in NETWORK_INFO_SOURCE
    assert "friendText" in NETWORK_INFO_SOURCE
    assert "Steam Invite/Join" in NETWORK_INFO_SOURCE
    assert "server-authoritative" in NETWORK_INFO_SOURCE
    assert '"multiplayer": _multiplayer_connect_info()' in SERVER_SOURCE
    assert "/mp_connect.json" in UTILITY_ROUTES_SOURCE
    assert "/mp_connect" in UTILITY_ROUTES_SOURCE


def _check_config_documents_radmin_terraria_port() -> None:
    assert "INFINI_HOST=0.0.0.0" in CONFIG_EXAMPLE
    assert "INFINI_ASSET_PUBLIC_BASE_URL=http://26.x.x.x:5055" in CONFIG_EXAMPLE
    assert "INFINI_TERRARIA_PORT=7777" in CONFIG_EXAMPLE


def _check_asset_url_guess_prefers_radmin_and_docs_explain_steam_boundary() -> None:
    asset_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Services" / "GeneratedAssetSyncService.cs").read_text(encoding="utf-8")
    readme = (ROOT / "README_RU.md").read_text(encoding="utf-8")
    assert 'StartsWith("26."' in asset_source
    assert "Steam не проксирует HTTP" in readme
    assert "не нужно руками открывать `/get_asset`" in readme

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_network_info_service_owns_multiplayer_connect_card',
    '_check_config_documents_radmin_terraria_port',
    '_check_asset_url_guess_prefers_radmin_and_docs_explain_steam_boundary'
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


def test_radmin_connect_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
