"""Filesystem locations shared by the browser Studio and settings persistence."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config.env"
EXAMPLE_PATH = ROOT / "config.example.env"
