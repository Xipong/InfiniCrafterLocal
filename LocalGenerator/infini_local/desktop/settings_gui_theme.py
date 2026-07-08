from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config.env"
EXAMPLE_PATH = ROOT / "config.example.env"
APP_TITLE = "InfiniCrafterLocal Settings GUI v0.4.239"

APP_BG = "#f5f7fb"
APP_PANEL_BG = "#eef4ff"
CARD_BG = "#ffffff"
CARD_MUTED_BG = "#f8fafc"
HEADER_BG = "#081226"
HEADER_BG_2 = "#0f1f3d"
TEXT_FG = "#0f172a"
MUTED_FG = "#64748b"
SOFT_FG = "#94a3b8"
ACCENT_BG = "#2563eb"
ACCENT_HOVER_BG = "#1d4ed8"
ACCENT_SOFT_BG = "#eff6ff"
ACCENT_FG = "#ffffff"
SUCCESS_BG = "#16a34a"
SUCCESS_SOFT_BG = "#dcfce7"
SUCCESS_FG = "#166534"
DANGER_BG = "#dc2626"
DANGER_SOFT_BG = "#fee2e2"
DANGER_FG = "#991b1b"
WARNING_SOFT_BG = "#fef3c7"
WARNING_FG = "#92400e"
BORDER_FG = "#dbe3ef"
BORDER_DARK_FG = "#cbd5e1"

__all__ = [
    "ROOT", "CONFIG_PATH", "EXAMPLE_PATH", "APP_TITLE",
    "APP_BG", "APP_PANEL_BG", "CARD_BG", "CARD_MUTED_BG",
    "HEADER_BG", "HEADER_BG_2", "TEXT_FG", "MUTED_FG", "SOFT_FG",
    "ACCENT_BG", "ACCENT_HOVER_BG", "ACCENT_SOFT_BG", "ACCENT_FG",
    "SUCCESS_BG", "SUCCESS_SOFT_BG", "SUCCESS_FG",
    "DANGER_BG", "DANGER_SOFT_BG", "DANGER_FG",
    "WARNING_SOFT_BG", "WARNING_FG", "BORDER_FG", "BORDER_DARK_FG",
]
