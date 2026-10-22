from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys
from typing import Any

from toolbox.testing.discovery import find_tool


def doctor(project: Path) -> dict[str, Any]:
    manifest = json.loads((project / '.agent/manifest.json').read_text(encoding='utf-8'))
    command = manifest['checks']['native_checks']
    projects = [part for part in command if part.endswith('.csproj')]
    native_exists = len(projects) == 1 and (project / projects[0]).is_file()
    return {
        'ok': (project / 'tools/agentctl.py').is_file() and native_exists,
        'project': str(project), 'python': sys.executable,
        'dependencies': {name: importlib.util.find_spec(name) is not None for name in ('pytest', 'PIL', 'pydantic', 'jsonschema')},
        'executables': {name: shutil.which(name) is not None for name in ('git', 'dotnet', 'ruff')},
        'replayOwner': str(find_tool(project, 'replay_generation_case.py')),
        'native': {'command': command, 'projectExists': native_exists, 'executed': False,
                   'note': 'Registered build command only. Execution belongs to agentctl verify --area csharp; requires .NET/tML/FNA/dependencies. Missing dotnet in PATH is not proof no host SDK exists.'},
        'note': 'Read-only discovery. Dependencies reported, not installed; provider credentials/config are not read.',
    }
