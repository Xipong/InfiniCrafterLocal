"""Versioned, consent-only default updates; never rewrite the full config."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from infini_local.desktop.settings_schema import DEFAULTS

DEFAULTS_VERSION = '0.5.02'
# Only defaults deliberately revised by this patch are eligible. Personal
# providers, models, paths, credentials and experimental controls stay outside.
UPDATED_DEFAULTS = {
    'INFINI_LLM_MAX_TOKENS': '18 000 — запас полного ответа вместе с reasoning; в успешном Live10 ответ использовал 10 687 токенов.',
    'INFINI_LLM_TIMEOUT': '600 секунд на LLM-стадию: успешные live-ответы превышали прежние 95 секунд.',
    'INFINI_LLM_REASONING_MODE': 'Medium — базовая глубина успешного Live10 для поддерживаемых удалённых reasoning-моделей; локальному серверу поле не отправляется.',
    'INFINI_LLM_TEMPERATURE': '0.5 — базовая вариативность Author в успешном Live10; сравнительное улучшение качества не измерено.',
    'INFINI_VISUAL_DIRECTOR_TEMPERATURE': '0.45 — согласованная базовая температура Visual Director в runtime и успешном Live10.',
}


def _atomic_write(path: Path, content: bytes, *, expected: bytes | None = None) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if expected is not None:
            if path.read_bytes() != expected:
                raise ValueError('config.env изменился после предпросмотра. Открой список изменений заново.')
            temporary.chmod(path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _decision_path(path: Path) -> Path:
    return path.with_name(path.name + '.defaults.json')


def _revision(raw: bytes) -> str:
    recommendations = {key: DEFAULTS[key] for key in UPDATED_DEFAULTS}
    return hashlib.sha256(raw + DEFAULTS_VERSION.encode() + json.dumps(recommendations, sort_keys=True).encode()).hexdigest()


def defaults_offer(path: Path) -> dict:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raw = b''
    recommendations = {key: DEFAULTS[key] for key in UPDATED_DEFAULTS}
    revision = _revision(raw)
    changes = []
    # Absent keys already inherit new defaults; do not materialize or write them.
    explicit = {}
    for line in raw.decode('utf-8-sig').splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and '=' in stripped:
            key, value = stripped.split('=', 1)
            explicit.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    for key, recommended in recommendations.items():
        if explicit.get(key, '').strip() and explicit[key] != recommended:
            changes.append({'key': key, 'current': explicit[key], 'recommended': recommended, 'reason': UPDATED_DEFAULTS[key]})
    try:
        decision = json.loads(_decision_path(path).read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError, UnicodeError):
        decision = {}
    signature = hashlib.sha256(json.dumps(recommendations, sort_keys=True).encode()).hexdigest()
    dismissed = isinstance(decision, dict) and decision.get('version') == DEFAULTS_VERSION and decision.get('recommendations') == signature
    return {'version': DEFAULTS_VERSION, 'revision': revision, 'changes': changes, 'dismissed': dismissed}


def decide_defaults(path: Path, revision: str, *, accept: bool) -> dict[str, str]:
    offer = defaults_offer(path)
    if revision != offer['revision']:
        raise ValueError('config.env изменился после предпросмотра. Открой список изменений заново.')
    changes = {row['key']: row['recommended'] for row in offer['changes']}
    if accept and changes:
        original = path.read_bytes()
        if _revision(original) != revision:
            raise ValueError('config.env изменился после предпросмотра. Открой список изменений заново.')
        text = original.decode('utf-8-sig')
        lines = []
        for line in text.splitlines(keepends=True):
            match = re.match(r'^(\s*([^=\r\n]+?)\s*=)([^\r\n]*)(\r?\n)?$', line)
            if match and not match[2].lstrip().startswith('#') and match[2].strip() in changes:
                value = match[3]
                leading = value[:len(value) - len(value.lstrip())]
                trailing = value[len(value.rstrip()):]
                stripped = value.strip()
                quote = stripped[0] if len(stripped) >= 2 and stripped[0] in ('"', "'") and stripped[-1] == stripped[0] else ''
                new_value = changes[match[2].strip()]
                if stripped.strip('"').strip("'") != new_value:
                    line = match[1] + leading + quote + new_value + quote + trailing + (match[4] or '')
            lines.append(line)
        output = ''.join(lines).encode('utf-8')
        if original.startswith(b'\xef\xbb\xbf'):
            output = b'\xef\xbb\xbf' + output
        _atomic_write(path, output, expected=original)
    elif path.exists() and defaults_offer(path)['revision'] != revision:
        raise ValueError('config.env изменился после предпросмотра. Открой список изменений заново.')
    if not accept:
        # Acceptance is witnessed by the actual config values. A second write can
        # fail after a committed update and would falsely report that it failed.
        recommendations = {key: DEFAULTS[key] for key in UPDATED_DEFAULTS}
        signature = hashlib.sha256(json.dumps(recommendations, sort_keys=True).encode()).hexdigest()
        _atomic_write(_decision_path(path), (json.dumps({'version': DEFAULTS_VERSION, 'recommendations': signature, 'accepted': False}) + '\n').encode())
    return changes if accept else {}
