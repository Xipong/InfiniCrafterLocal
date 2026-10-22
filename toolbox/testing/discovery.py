from __future__ import annotations

from pathlib import Path


def find_tool(project: Path, name: str) -> Path:
    # Public entries may stay at tools/ or move into thematic directories.
    matches = sorted((project / 'tools').rglob(name))
    matches = [path for path in matches if path.is_file() and not any(part in ('bin', 'obj', '__pycache__') for part in path.relative_to(project / 'tools').parts)]
    if len(matches) != 1:
        raise ValueError(f'expected exactly one tools/**/{name}; found {len(matches)}')
    return matches[0]
