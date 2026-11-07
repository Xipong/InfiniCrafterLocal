"""Strict port contract shared by Studio, preflight and the HTTP bind owner."""
from types import SimpleNamespace

import pytest

from infini_local.core.server_endpoint import resolve_server_endpoint
from infini_local.desktop.settings_controller import SettingsController
from infini_local.desktop.settings_env import write_env
from infini_local.desktop.settings_schema import DEFAULTS


@pytest.mark.parametrize('port', ['abc', '70000', '5055.9', '0', '-1', '65536', '+5055'])
def test_invalid_port_refused_by_studio_preflight_save_and_server(tmp_path, monkeypatch, port):
    from infini_local.web import server
    config = tmp_path / 'config.env'
    write_env(config, {**DEFAULTS, 'INFINI_PORT': port, 'INFINI_IMAGE_BACKEND': 'off'})
    before = config.read_bytes()
    app = SettingsController(config)
    try:
        assert not app.validate_paths()['ok']
        with pytest.raises(ValueError, match='INFINI_PORT'):
            app._server_base_url()
        with pytest.raises(ValueError, match='INFINI_PORT'):
            app.save()
        assert config.read_bytes() == before
        monkeypatch.setenv('INFINI_PORT', port)
        monkeypatch.setattr(server, 'ThreadingHTTPServer', lambda *_: pytest.fail('invalid port reached bind'))
        monkeypatch.setattr(server, 'initialize_trace_storage', lambda: pytest.fail('invalid port initialized runtime'))
        with pytest.raises(ValueError, match='INFINI_PORT'):
            server.main()
    finally:
        app.on_close()


@pytest.mark.parametrize('host,port,access', [
    ('0.0.0.0', ' 5055 ', 'http://127.0.0.1:5055'),
    ('127.0.0.1', '65535', 'http://127.0.0.1:65535'),
    ('::', '1', 'http://[::1]:1'),
    ('localhost', '', 'http://localhost:5055'),
])
def test_bind_and_access_addresses_are_distinct(host, port, access):
    endpoint = resolve_server_endpoint({'INFINI_HOST': host, 'INFINI_PORT': port})
    assert endpoint.bind_host == host
    assert endpoint.base_url == access


def test_server_binds_validated_port_without_rewriting_wildcard(monkeypatch):
    from infini_local.web import server
    monkeypatch.setenv('INFINI_HOST', '0.0.0.0')
    monkeypatch.setenv('INFINI_PORT', '6066')
    monkeypatch.setattr(server, 'USE_LLM', False)
    monkeypatch.setattr(server, 'initialize_trace_storage', lambda: None)
    monkeypatch.setattr(server, 'install_cleanup_handlers', lambda *_: None)
    bound = []
    monkeypatch.setattr(server, 'ThreadingHTTPServer', lambda address, _: (bound.append(address) or SimpleNamespace(serve_forever=lambda: None)))
    server.main()
    assert bound == [('0.0.0.0', 6066)]
