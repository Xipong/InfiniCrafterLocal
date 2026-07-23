from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER_SOURCE = (ROOT / "LocalGenerator" / "infini_local" / "web" / "server.py").read_text(encoding="utf-8")
NETWORK_INFO_SOURCE = (ROOT / "LocalGenerator" / "infini_local" / "services" / "network_info_service.py").read_text(encoding="utf-8")
UTILITY_ROUTES_SOURCE = (ROOT / "LocalGenerator" / "infini_local" / "web" / "server_utility_routes.py").read_text(encoding="utf-8")
CONFIG_EXAMPLE = (ROOT / "LocalGenerator" / "config.example.env").read_text(encoding="utf-8")
GUI_SOURCE = (ROOT / "LocalGenerator" / "infini_local" / "desktop" / "settings_gui_ui.py").read_text(encoding="utf-8")
SETTINGS_SCHEMA_SOURCE = (ROOT / "LocalGenerator" / "infini_local" / "desktop" / "settings_schema.py").read_text(encoding="utf-8")


def _check_network_info_service_owns_multiplayer_connect_card() -> None:
    assert "network_info_service" in SERVER_SOURCE
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


def _check_asset_transport_toggle_reaches_gui_handshake_definition_and_runtime() -> None:
    from infini_local.services import network_info_service as service

    assert '"INFINI_MP_ASSET_TRANSPORT": "native"' in SETTINGS_SCHEMA_SOURCE
    assert '"INFINI_MP_ASSET_TRANSPORT"' in SETTINGS_SCHEMA_SOURCE
    assert 'self.row(radmin_card, "Asset transport", "INFINI_MP_ASSET_TRANSPORT", values=["native", "http"]' in GUI_SOURCE
    assert "INFINI_MP_ASSET_TRANSPORT=native" in CONFIG_EXAMPLE

    native = service.multiplayer_connect_info(
        local_generator_port=5055,
        terraria_port="7777",
        asset_public_base_url="",
        asset_transport="native",
        host="0.0.0.0",
    )
    http = service.multiplayer_connect_info(
        local_generator_port=5055,
        terraria_port="7777",
        asset_public_base_url="http://26.1.2.3:5055",
        asset_transport="HTTP",
        host="0.0.0.0",
    )
    assert native["assetTransport"] == "native"
    assert http["assetTransport"] == "http"
    assert "Terraria" in native["transportPolicy"]
    assert "/get_asset" in http["transportPolicy"]

    model = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.Model.cs").read_text(encoding="utf-8")
    data_profiles = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.cs").read_text(encoding="utf-8")
    generator = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Services" / "GeneratorClient.cs").read_text(encoding="utf-8")
    registry = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Services" / "GeneratedItemRegistryService.cs").read_text(encoding="utf-8")
    assets = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Services" / "GeneratedAssetSyncService.cs").read_text(encoding="utf-8")
    assert "public string AssetTransport" in model
    assert "var minimal = MinimalNetworkClone(clone);" in data_profiles
    assert "private static GeneratedItemData MinimalNetworkClone" in data_profiles
    assert 'TryGetProperty("assetTransport"' in generator
    assert "AssetTransportForSharing" in generator
    assert "public void StampAssetTransportMetadata" in generator
    stamp_block = generator[generator.index("public void StampAssetTransportMetadata"):generator.index("private string ReadGeneratorAdvertisedAssetBaseUrl")]
    assert 'data.RecipeMeta.AssetBaseUrl = "";' in stamp_block
    assert "StampAssetTransportMetadata(data, refreshBaseUrl: force)" in registry
    assert "data.RecipeMeta.AssetTransport =" in registry
    assert "IsHttpAssetTransport(data)" in assets
    assert "QueueDownloads(httpBaseUrl, missing, forceRetry: forceRetry, itemId: itemId)" in assets
    assert "SendAssetRequest(itemId, missing)" in assets
    assert "QueueDownloads(pending.BaseUrl" not in assets
    ensure_block = assets[assets.index("public void EnsureAssetsForData(GeneratedItemData? data, bool forceRetry)"):assets.index("internal bool NeedsRemoteDescriptorRefresh")]
    assert ensure_block.index("if (IsHttpAssetTransport(data))") < ensure_block.index("BestBaseUrl(data)")


def _check_asset_url_guess_prefers_radmin_and_docs_explain_steam_boundary() -> None:
    asset_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Services" / "GeneratedAssetSyncService.cs").read_text(encoding="utf-8")
    readme = (ROOT / "README_RU.md").read_text(encoding="utf-8")
    assert 'StartsWith("26."' in asset_source
    assert "Steam не проксирует HTTP" in readme
    assert "не нужно руками открывать `/get_asset`" in readme


def _check_link_local_apipa_is_never_advertised_to_peers(monkeypatch) -> None:
    from infini_local.services import network_info_service as service

    monkeypatch.setattr(
        service.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (service.socket.AF_INET, 0, 0, "", ("169.254.241.48", 0)),
            (service.socket.AF_INET, 0, 0, "", ("192.168.31.123", 0)),
        ],
    )

    class _Socket:
        def connect(self, _address):
            return None

        def getsockname(self):
            return ("169.254.241.48", 5055)

        def close(self):
            return None

    monkeypatch.setattr(service.socket, "socket", lambda *_args, **_kwargs: _Socket())
    assert service.local_ipv4_candidates() == ["192.168.31.123"]
    card = service.multiplayer_connect_info(
        local_generator_port=5055,
        terraria_port="7777",
        asset_public_base_url="",
        host="0.0.0.0",
    )
    assert "169.254." not in str(card)

    asset_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Services" / "GeneratedAssetSyncService.cs").read_text(encoding="utf-8")
    assert "IsUsablePeerIPv4" in asset_source
    assert "bytes[0] == 169 && bytes[1] == 254" in asset_source
    generator_source = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Services" / "GeneratorClient.cs").read_text(encoding="utf-8")
    assert 'new Uri(combineUri, "/mp_connect.json")' in generator_source
    assert 'TryGetProperty("multiplayer"' in generator_source
    assert 'multiplayer.TryGetProperty("assetPublicBaseUrl"' in generator_source
    assert "AssetBaseUrlForSharing(data.RecipeMeta.AssetBaseUrl)" in generator_source

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_network_info_service_owns_multiplayer_connect_card',
    '_check_config_documents_radmin_terraria_port',
    '_check_asset_transport_toggle_reaches_gui_handshake_definition_and_runtime',
    '_check_asset_url_guess_prefers_radmin_and_docs_explain_steam_boundary',
    '_check_link_local_apipa_is_never_advertised_to_peers'
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
