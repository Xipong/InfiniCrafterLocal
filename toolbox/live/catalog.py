"""Read-only index of versioned request panels and their paired parent fixtures."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
PANELS = FIXTURES / 'panels'
DEFAULT_PRESETS = {'live10': 'live10-midgame', 'live20': 'live20-classic'}


def load_panel(name: str) -> dict[str, Any]:
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name):
        raise ValueError('invalid built-in preset name')
    source = (PANELS / (name + '.json')).resolve()
    if not source.is_relative_to(PANELS.resolve()) or not source.is_file():
        raise ValueError(f'unknown built-in preset: {name}')
    payload = json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or payload.get('id') != name or payload.get('command') not in DEFAULT_PRESETS:
        raise ValueError(f'invalid built-in panel metadata: {name}')
    if not isinstance(payload.get('cases'), list) or not payload['cases']:
        raise ValueError(f'empty built-in panel: {name}')
    dump_name = payload.get('runtimeDump')
    if not isinstance(dump_name, str) or not dump_name:
        raise ValueError(f'missing parent fixture for panel: {name}')
    dump = (source.parent / dump_name).resolve()
    if not dump.is_relative_to(FIXTURES.resolve()) or not dump.is_file():
        raise ValueError(f'parent fixture escapes toolbox or is missing: {name}')
    return {**payload, 'sourcePath': source, 'runtimeDumpPath': dump}


def panel_catalog() -> list[dict[str, Any]]:
    entries = []
    root = FIXTURES.parents[1]
    for source in sorted(PANELS.glob('*.json')):
        panel = load_panel(source.stem)
        entries.append({
            'id': panel['id'], 'command': panel['command'], 'title': panel['title'],
            'caseCount': len(panel['cases']), 'historical': panel['historical'],
            'casesFile': panel['sourcePath'].relative_to(root).as_posix(),
            'runtimeDump': panel['runtimeDumpPath'].relative_to(root).as_posix(),
            'provenance': panel['provenance'], 'notes': panel.get('notes', ''),
            'cases': panel['cases'],
        })
    return entries
