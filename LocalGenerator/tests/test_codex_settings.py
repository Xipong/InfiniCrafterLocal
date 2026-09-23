from __future__ import annotations

import subprocess
import sys

from infini_local.desktop import settings_schema as schema
from infini_local.desktop.settings_gui_server_controls import SettingsGuiServerControlsMixin


def test_subscription_settings_and_login_controls_are_available():
    for key in ("INFINI_CODEX_IMAGE_MODEL", "INFINI_CODEX_IMAGE_QUALITY", "INFINI_CODEX_IMAGE_SIZE", "INFINI_CODEX_IMAGE_TIMEOUT"):
        assert key in schema.FIELD_ORDER
        assert key in schema.DEFAULTS
    assert "openai_codex" in schema.OPTION_HELP["INFINI_IMAGE_BACKEND"]
    assert callable(getattr(SettingsGuiServerControlsMixin, "codex_login", None))
    assert callable(getattr(SettingsGuiServerControlsMixin, "codex_status", None))
    assert callable(getattr(SettingsGuiServerControlsMixin, "codex_logout", None))


def test_auth_cli_has_explicit_login_logout_status_commands():
    result = subprocess.run([sys.executable, "-m", "infini_local.services.codex_auth", "--help"], capture_output=True, text=True, check=True, timeout=15)
    assert "login" in result.stdout
    assert "status" in result.stdout
    assert "logout" in result.stdout
