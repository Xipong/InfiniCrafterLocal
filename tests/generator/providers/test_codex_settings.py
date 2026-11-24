from __future__ import annotations

import json
import sys

import pytest

from infini_local.services import codex_auth


@pytest.mark.parametrize("command,expected_calls", [
    pytest.param("login", ["login"], id="login"),
    pytest.param("status", [], id="status-read-only"),
    pytest.param("logout", ["logout"], id="logout"),
])
def test_auth_cli_dispatches_login_status_logout_without_real_auth(monkeypatch, capsys, command, expected_calls):
    calls = []
    monkeypatch.setattr(codex_auth, "login", lambda **kw: calls.append("login"))
    monkeypatch.setattr(codex_auth, "logout", lambda: calls.append("logout"))
    monkeypatch.setattr(codex_auth, "auth_status", lambda: {"authenticated": False})
    monkeypatch.setattr(sys, "argv", ["codex_auth", command])
    assert codex_auth.main() == 0
    assert calls == expected_calls
    assert json.loads(capsys.readouterr().out) == {"authenticated": False}
