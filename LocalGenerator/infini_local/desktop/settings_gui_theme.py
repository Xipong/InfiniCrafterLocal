from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config.env"
EXAMPLE_PATH = ROOT / "config.example.env"
APP_TITLE = "InfiniCrafterLocal — Мастерская"

def resolve_ui_font(families):
    """Prefer system sans families; bare X11 Tk otherwise collapses to fixed 9px."""
    available = {str(name).lower(): str(name) for name in families}
    for candidate in ("Segoe UI", "Inter", "DejaVu Sans", "Liberation Sans", "Ubuntu", "helvetica"):
        if candidate.lower() in available:
            return available[candidate.lower()]
    return "TkDefaultFont"


APP_BG = "#141618"
APP_PANEL_BG = "#1a1d20"
CARD_BG = "#202326"
CARD_MUTED_BG = "#191c1f"
HEADER_BG = "#111315"
HEADER_BG_2 = "#181b1e"
TEXT_FG = "#ebe5dc"
MUTED_FG = "#a39c93"
SOFT_FG = "#77756f"
ACCENT_BG = "#d99a67"
ACCENT_HOVER_BG = "#efb07c"
ACCENT_SOFT_BG = "#382b23"
ACCENT_FG = "#1b1612"
SUCCESS_BG = "#78a98c"
SUCCESS_SOFT_BG = "#24342c"
SUCCESS_FG = "#a2c6ac"
DANGER_BG = "#bf756c"
DANGER_SOFT_BG = "#3c2928"
DANGER_FG = "#e3a29b"
WARNING_SOFT_BG = "#372f23"
WARNING_FG = "#d4b37e"
BORDER_FG = "#34373a"
BORDER_DARK_FG = "#484a4c"

__all__ = [
    "ROOT", "CONFIG_PATH", "EXAMPLE_PATH", "APP_TITLE",
    "APP_BG", "APP_PANEL_BG", "CARD_BG", "CARD_MUTED_BG",
    "HEADER_BG", "HEADER_BG_2", "TEXT_FG", "MUTED_FG", "SOFT_FG",
    "ACCENT_BG", "ACCENT_HOVER_BG", "ACCENT_SOFT_BG", "ACCENT_FG",
    "SUCCESS_BG", "SUCCESS_SOFT_BG", "SUCCESS_FG",
    "DANGER_BG", "DANGER_SOFT_BG", "DANGER_FG",
    "WARNING_SOFT_BG", "WARNING_FG", "BORDER_FG", "BORDER_DARK_FG",
]
