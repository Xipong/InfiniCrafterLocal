from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

_TRUE_VALUES = {"1", "true", "yes", "on", "y", "t"}
_FALSE_VALUES = {"0", "false", "no", "off", "n", "f"}


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE lines from a config.env-style file.

    Existing process environment variables win over file values. This helper is
    deliberately tiny because the local generator must keep working on Windows
    GUI/bat launches without adding another dependency.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env_str(name: str, default: str = "", *, strip: bool = True) -> str:
    value = os.environ.get(name, default)
    if value is None:
        value = default
    value = str(value)
    return value.strip() if strip else value


def env_bool(name: str, default: bool = False) -> bool:
    raw = env_str(name, "")
    if not raw:
        return bool(default)
    norm = raw.strip().lower()
    if norm in _TRUE_VALUES:
        return True
    if norm in _FALSE_VALUES:
        return False
    return bool(default)


def env_int(name: str, default: int, *, lo: int | None = None, hi: int | None = None) -> int:
    raw = env_str(name, str(default))
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        value = int(default)
    if lo is not None and value < lo:
        value = lo
    if hi is not None and value > hi:
        value = hi
    return value


def env_float(name: str, default: float, *, lo: float | None = None, hi: float | None = None) -> float:
    raw = env_str(name, str(default))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = float(default)
    if lo is not None and value < lo:
        value = lo
    if hi is not None and value > hi:
        value = hi
    return value


def env_first(names: Iterable[str], default: str = "", *, strip: bool = True) -> str:
    for name in names:
        if name in os.environ and str(os.environ.get(name, "")).strip():
            return env_str(name, default, strip=strip)
    return env_str("__INFINI_ENV_MISSING__", default, strip=strip)


def env_first_allow_empty(names: Iterable[str], default: str = "", *, strip: bool = True) -> str:
    """Return the first present env value, preserving intentional empty strings.

    `env_first()` skips empty values because most config fallbacks want that.
    A few bootstrap surfaces need to distinguish an explicitly empty env value
    from a missing key, for example public URL overrides.
    """
    for name in names:
        if name in os.environ:
            return env_str(name, default, strip=strip)
    return env_str("__INFINI_ENV_MISSING__", default, strip=strip)


def env_path(name: str, default: str | Path) -> Path:
    return Path(env_str(name, str(default)))
