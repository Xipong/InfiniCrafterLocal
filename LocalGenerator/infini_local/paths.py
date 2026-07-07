from __future__ import annotations

from pathlib import Path

# Absolute path to LocalGenerator/. Keep data/config/cache stable even when
# implementation files live under infini_local/* packages.
LOCAL_GENERATOR_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = LOCAL_GENERATOR_ROOT / "data"
