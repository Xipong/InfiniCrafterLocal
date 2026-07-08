from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "infini_local" / "desktop" / "settings_gui.py"
GUI_UI = ROOT / "infini_local" / "desktop" / "settings_gui_ui.py"
GUI_THEME = ROOT / "infini_local" / "desktop" / "settings_gui_theme.py"
TK_COMPAT = ROOT / "infini_local" / "desktop" / "tk_compat.py"
SETTINGS_WIDGETS = ROOT / "infini_local" / "desktop" / "settings_widgets.py"
SOURCE = "\n".join(p.read_text(encoding="utf-8") for p in [GUI, GUI_THEME, GUI_UI])
TK_COMPAT_SOURCE = TK_COMPAT.read_text(encoding="utf-8")
SETTINGS_WIDGETS_SOURCE = SETTINGS_WIDGETS.read_text(encoding="utf-8")


def test_settings_gui_has_real_modernized_chrome_not_image_mockup_only() -> None:
    assert 'APP_TITLE = "InfiniCrafterLocal Settings GUI v0.4.239"' in SOURCE
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
    assert "from infini_local.desktop.tk_compat import (" in SOURCE
    assert "Frame = _TkHeadlessBase" in TK_COMPAT_SOURCE
    assert "Button = _TkHeadlessBase" in TK_COMPAT_SOURCE


def test_settings_gui_small_widgets_are_extracted_from_main_gui() -> None:
    assert "from infini_local.desktop.settings_widgets import (" in SOURCE
    assert "class ToolTip" not in SOURCE
    assert "class ScrollFrame" not in SOURCE
    assert "class ToolTip" in SETTINGS_WIDGETS_SOURCE
    assert "class ScrollFrame" in SETTINGS_WIDGETS_SOURCE
