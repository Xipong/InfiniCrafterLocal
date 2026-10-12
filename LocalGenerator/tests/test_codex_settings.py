from __future__ import annotations

import json
import sys

import pytest

from infini_local.services import codex_auth
from infini_local.desktop import settings_schema as schema
from infini_local.desktop.settings_gui_server_controls import SettingsGuiServerControlsMixin


def test_subscription_settings_and_login_controls_are_available():
    for key in ("INFINI_CODEX_IMAGE_MODEL", "INFINI_CODEX_IMAGE_QUALITY", "INFINI_CODEX_IMAGE_SIZE", "INFINI_CODEX_IMAGE_TIMEOUT"):
        assert key in schema.FIELD_ORDER
        assert key in schema.DEFAULTS
    assert "openai_codex" in schema.OPTION_HELP["INFINI_IMAGE_BACKEND"]
    assert callable(getattr(SettingsGuiServerControlsMixin, "codex_login", None))
    assert callable(getattr(SettingsGuiServerControlsMixin, "codex_status", None))


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
