"""Read-only application files and the optional, separate user data directory."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Source launchers retain their existing layout. The packaged launcher sets this
# before importing application modules, so upgrades never replace user data.
_data_dir = os.environ.get("INFINI_DATA_DIR", "").strip()
STATE_ROOT = Path(_data_dir).expanduser().resolve() if _data_dir else ROOT
CONFIG_PATH = STATE_ROOT / "config.env"
