from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from infini_local.desktop import settings_env

ROOT = Path(__file__).resolve().parents[2]


def test_new_user_template_has_no_personal_hardware_paths_or_automatic_gpu_launch():
    template = settings_env.parse_env(ROOT / "LocalGenerator/config.example.env")
    assert template.get("INFINI_SDCPP_SERVER_AUTOSTART") == "0"
    assert template.get("INFINI_SDCPP_SERVER_EXE") == ""
    assert template.get("INFINI_SDCPP_MODEL") == ""
    assert template.get("INFINI_SDCPP_SERVER_EXTRA_ARGS") == ""
    assert template.get("INFINI_GUI_PIPELINE_PRESET") == "Custom"


def test_windows_launchers_can_run_read_only_doctor_and_have_no_control_bytes():
    for name in ("OPEN_INFINICRAFT.bat", "02_INSTALL_LOCAL_GENERATOR.bat", "04_OPEN_SETTINGS_GUI.bat", "06_START_SERVER_DIRECT.bat"):
        payload = (ROOT / name).read_bytes()
        assert all(byte >= 32 or byte in (9, 10, 13) for byte in payload), name
    launcher = (ROOT / "OPEN_INFINICRAFT.bat").read_text(encoding="utf-8")
    assert '%~1' in launcher, "Entry point must support doctor without launching the interactive runtime"
    if os.name == "nt":
        result = subprocess.run(["cmd.exe", "/d", "/c", str(ROOT / "OPEN_INFINICRAFT.bat"), "doctor"], capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "read-only" in result.stdout
