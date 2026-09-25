from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path


TOOLBOX_ROOT = Path(__file__).resolve().parent
BASE_ROOT = TOOLBOX_ROOT.parent


def discover_project(explicit: str | Path | None = None) -> Path:
    requested = explicit or os.environ.get("INFINI_PROJECT_ROOT")
    if requested:
        project = Path(requested).expanduser().resolve()
        if not (project / "LocalGenerator/infini_local").is_dir():
            raise FileNotFoundError(f"not an InfiniCrafterLocal worktree: {project}")
        return project
    if (BASE_ROOT / "LocalGenerator/infini_local").is_dir():
        return BASE_ROOT.resolve()
    candidates = [
        path
        for path in BASE_ROOT.iterdir()
        if path.is_dir() and (path / "LocalGenerator/infini_local").is_dir()
    ]
    if not candidates:
        raise FileNotFoundError(
            f"no InfiniCrafterLocal worktree found under {BASE_ROOT}; pass --project or INFINI_PROJECT_ROOT"
        )
    if len(candidates) > 1:
        names = ", ".join(sorted(path.name for path in candidates))
        raise RuntimeError(f"multiple worktrees found ({names}); pass --project or INFINI_PROJECT_ROOT")
    return candidates[0].resolve()


def load_config_env(project: Path) -> None:
    path = project / "LocalGenerator/config.env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip().rstrip("\r")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            os.environ.setdefault(key, value.strip())


def new_run_dir(label: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return BASE_ROOT / "artifacts/tool-runs" / f"{label}-{timestamp}"
