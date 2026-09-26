from __future__ import annotations

import json
import sys

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


def test_auth_cli_dispatches_login_status_logout_without_real_auth(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(codex_auth, "login", lambda **kw: calls.append("login"))
    monkeypatch.setattr(codex_auth, "logout", lambda: calls.append("logout"))
    monkeypatch.setattr(codex_auth, "auth_status", lambda: {"authenticated": False})

    monkeypatch.setattr(sys, "argv", ["codex_auth", "login"])
    assert codex_auth.main() == 0
    assert calls == ["login"]
    assert json.loads(capsys.readouterr().out) == {"authenticated": False}

    monkeypatch.setattr(sys, "argv", ["codex_auth", "status"])
    assert codex_auth.main() == 0
    assert calls == ["login"]
    assert json.loads(capsys.readouterr().out) == {"authenticated": False}

    monkeypatch.setattr(sys, "argv", ["codex_auth", "logout"])
    assert codex_auth.main() == 0
    assert calls == ["login", "logout"]
    assert json.loads(capsys.readouterr().out) == {"authenticated": False}
