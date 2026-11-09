"""Small, non-secret Studio help progress, separate from generator settings."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


_DEFAULT = {'version': 1, 'seen': False, 'step': 0, 'completed': False}


def _path(config_path: Path) -> Path:
    return config_path.with_name(config_path.name + '.studio.json')


def load_progress(config_path: Path) -> dict:
    try:
        path = _path(config_path)
        if path.stat().st_size > 4096:
            return dict(_DEFAULT)
        data = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(data, dict) or data.get('version') != 1
                or type(data.get('seen')) is not bool or type(data.get('completed')) is not bool
                or type(data.get('step')) is not int or not 0 <= data['step'] <= 4):
            return dict(_DEFAULT)
        return {key: data[key] for key in _DEFAULT}
    except (OSError, ValueError, UnicodeError):
        return dict(_DEFAULT)


def save_progress(config_path: Path, update: dict) -> dict:
    if (not isinstance(update, dict) or set(update) - {'step', 'completed'}
            or type(update.get('step')) is not int or not 0 <= update['step'] <= 4
            or ('completed' in update and type(update['completed']) is not bool)):
        raise ValueError('Invalid onboarding progress')
    data = {**load_progress(config_path), 'seen': True, 'step': update['step']}
    data['completed'] = data['completed'] or update.get('completed', False)
    path = _path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return data
