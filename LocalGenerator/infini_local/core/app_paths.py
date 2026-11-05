"""Read-only application files and the optional, separate user data directory."""
from __future__ import annotations

import ntpath
import os
from pathlib import Path

from infini_local.core.env_utils import env_str

ROOT = Path(__file__).resolve().parents[2]
# Source launchers retain their existing layout. The packaged launcher sets this
# before importing application modules, so upgrades never replace user data.
_data_dir = env_str("INFINI_DATA_DIR", "")
STATE_ROOT = Path(_data_dir).expanduser().resolve() if _data_dir else ROOT
CONFIG_PATH = STATE_ROOT / "config.env"
EXAMPLE_PATH = ROOT / "config.example.env"


def windows_extended_path(path: str) -> str:
    """Keep ordinary drive/UNC paths usable beyond MAX_PATH without OS policy."""
    if path.startswith("\\\\?\\"):
        return path
    normalized = ntpath.normpath(path)
    if not ntpath.isabs(normalized):
        raise ValueError("extended Windows paths must be absolute")
    if normalized.startswith("\\\\"):
        return "\\\\?\\UNC\\" + normalized[2:]
    if not ntpath.splitdrive(normalized)[0]:
        raise ValueError("extended Windows paths require a drive or UNC share")
    return "\\\\?\\" + normalized


def persistent_filesystem_path(path: Path) -> Path:
    absolute = path.expanduser().resolve()
    return Path(windows_extended_path(str(absolute))) if os.name == "nt" else absolute
