from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "infini_local" / "desktop" / "settings_gui.py"
SOURCE = GUI.read_text(encoding="utf-8")


def test_settings_gui_has_real_modernized_chrome_not_image_mockup_only() -> None:
    assert 'APP_TITLE = "InfiniCrafterLocal Settings GUI v0.4.237"' in SOURCE
    assert "def _modern_button" in SOURCE
    assert "def _card" in SOURCE
    assert "def _chip" in SOURCE
    assert "def _info_panel" in SOURCE
    assert "Settings GUI v0.4.226" not in SOURCE


def test_settings_gui_general_tab_uses_cards_for_key_sections() -> None:
    build_general_start = SOURCE.index("def _build_general")
    build_general_end = SOURCE.index("def _build_llm", build_general_start)
    general = SOURCE[build_general_start:build_general_end]
    assert '"Сервер и поведение крафта"' in general
    assert '"Radmin / LAN — сетевой оверлей, не отдельный AI-режим"' in general
    assert '"Trace / black box recorder"' in general
    assert "self._card(" in general
    assert "self._info_panel(" in general
    assert "Local only" in general


def test_settings_gui_headless_shim_covers_new_tk_widgets() -> None:
    assert "Frame = _TkHeadlessBase" in SOURCE
    assert "Button = _TkHeadlessBase" in SOURCE
