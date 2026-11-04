from __future__ import annotations

import os
import re
from pathlib import Path

from infini_local.core.config_migration import (
    apply_environment_values, migrate_config_file, migrate_environment, migrate_values, read_migration_source,
)

_TRUE_VALUES = {"1", "true", "yes", "on", "y", "t"}
_FALSE_VALUES = {"0", "false", "no", "off", "n", "f"}


def load_env_file(path: Path) -> None:
    """Load versioned config.env strings through the canonical codec.

    Existing process environment variables win over file values. This helper is
    deliberately tiny because the local generator must keep working on Windows
    GUI/bat launches without adding another dependency.
    """
    if os.environ.get("INFINI_SKIP_CONFIG_FILE", "").strip().lower() in _TRUE_VALUES:
        migrate_environment(os.environ)
        return
    # Resolve both original sources before applying canonical values. A key
    # created by migration is not an explicit modern setting; persisted
    # provenance retains that distinction until the user edits/saves the file.
    inherited = dict(os.environ)
    migrate_config_file(path, environment=inherited)
    source = read_migration_source(path)
    effective, changes = migrate_values({**source, **inherited})
    apply_environment_values(os.environ, effective, changes)


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


def env_credential_values() -> tuple[str, ...]:
    """Known configured secrets for diagnostics; never expose them in registry/UI."""
    return tuple(value for key, value in os.environ.items() if value
                 and (key in {"OPENAI_API_KEY", "OPENROUTER_API_KEY"} or
                      (key.startswith("INFINI_") and re.search(r"(?:^|_)(?:API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIALS?)(?:_|$)", key.upper()))))


def env_path(name: str, default: str | Path) -> Path:
    return Path(env_str(name, str(default)))
