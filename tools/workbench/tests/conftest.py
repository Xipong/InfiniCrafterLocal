"""Resolve the public CLI and its package when pytest collects this directory."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
