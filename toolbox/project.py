from __future__ import annotations

import os
import importlib.util
from pathlib import Path


TOOLBOX_ROOT = Path(__file__).resolve().parent
BASE_ROOT = TOOLBOX_ROOT.parent


def discover_project(explicit: str | Path | None = None) -> Path:
    project = Path(explicit or os.environ.get("INFINI_PROJECT_ROOT") or BASE_ROOT).expanduser().resolve()
    if not (project / "generator/infini_local").is_dir():
        raise FileNotFoundError(f"not an InfiniCrafterLocal worktree: {project}")
    return project

def read_config_env(path: Path) -> dict[str, str]:
    """Read the canonical dependency-free codec without runtime bootstrap."""
    source = BASE_ROOT / 'generator/infini_local/core/env_file.py'
    spec = importlib.util.spec_from_file_location('_toolbox_env_codec', source)
    if spec is None or spec.loader is None:
        raise RuntimeError('Cannot load canonical env codec')
    codec = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(codec)
    return codec.read_env_file(path)
