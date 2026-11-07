from __future__ import annotations

import os
import socket

import pytest


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("network attempted by offline toolbox")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    for key in list(os.environ):
        if key.startswith('INFINI_'):
            monkeypatch.delenv(key)
    monkeypatch.setenv('INFINI_CACHE_DIR', str(tmp_path / 'untouched-cache'))
    monkeypatch.setenv('INFINI_SKIP_CONFIG_FILE', '1')
