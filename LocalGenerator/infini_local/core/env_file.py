"""Dependency-free config.env wire codec shared by runtime, Studio and toolbox.

Files declare json-string-v1 before assignments. Quoted values are JSON strings
on one physical line. Unversioned files are rejected, never guessed or migrated.
Reading is pure: no environment mutation, defaults, cache creation or migration.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

FORMAT_HEADER = '# infini-config-format: json-string-v1'
_HEADER_PREFIX = '# infini-config-format:'


def physical_lines(text: str, *, keepends: bool = False) -> list[str]:
    # JSON strings may contain Unicode paragraph separators literally. They are
    # value characters, unlike the LF/CRLF/CR record delimiters of config.env.
    if keepends:
        return re.findall(r'[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$', text)
    return re.split(r'\r\n|\r|\n', text)


def _validate_format(text: str) -> None:
    """Recognize only a leading format declaration, never a comment in a value."""
    declared = False
    assigned = False
    for number, raw in enumerate(physical_lines(text.lstrip('\ufeff')), 1):
        line = raw.strip()
        if line.startswith(_HEADER_PREFIX):
            if assigned or line != FORMAT_HEADER:
                raise ValueError(f'Unsupported or misplaced config.env format declaration at line {number}.')
            declared = True
        elif line and not line.startswith('#') and '=' in line:
            if not declared:
                raise ValueError('Missing config.env format declaration. Recreate settings with Studio or use the current config.example.env; automatic migration is not supported.')
            assigned = True


def decode_value(raw: str, *, line: int = 0) -> str:
    value = raw.strip()
    if value.startswith('"'):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            # Never echo the setting's value: it may contain credentials.
            raise ValueError(f'Invalid JSON string in config.env at line {line}.') from None
        if not isinstance(value, str):
            raise ValueError(f'Expected a config.env string at line {line}.')
    if '\x00' in value:
        raise ValueError(f'NUL is not allowed in config.env at line {line}.')
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ValueError(f'Unpaired Unicode surrogate in config.env at line {line}.')
    return value


def encode_value(value: str) -> str:
    if not isinstance(value, str) or '\x00' in value or any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ValueError('config.env values must be Unicode strings without NUL or unpaired surrogates.')
    return json.dumps(value, ensure_ascii=False)


def parse_env_text(text: str) -> dict[str, str]:
    """Return explicit settings; first occurrence wins, matching runtime loads."""
    _validate_format(text)
    lines = physical_lines(text.lstrip('\ufeff'))
    data = {}
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, raw_value = line.split('=', 1)
        key = key.strip()
        if not key:
            continue
        if '\x00' in key or any(0xD800 <= ord(character) <= 0xDFFF for character in key):
            raise ValueError(f'Invalid Unicode or NUL in config.env key at line {number}.')
        value = decode_value(raw_value, line=number)
        data.setdefault(key, value)
    return data


def read_env_file(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding='utf-8-sig')
    except FileNotFoundError:
        return {}
    return parse_env_text(text)


def replace_env_values(text: str, changes: dict[str, str]) -> str:
    """Replace explicit settings, preserving every unrelated character.

    This is the same wire codec as full saves and reads. It does not add missing
    keys or migrate a file; consent and atomic publication belong to the caller.
    Validate the whole input first so a malformed file cannot be partly patched.
    """
    parse_env_text(text)
    lines = []
    for line in physical_lines(text, keepends=True):
        match = re.match(r'^(\s*([^=\r\n]+?)\s*=)([^\r\n]*)(\r\n|\r|\n)?$', line)
        if match and not match[2].lstrip().startswith('#') and match[2].strip() in changes:
            value = match[3]
            leading = value[:len(value) - len(value.lstrip())]
            trailing = value[len(value.rstrip()):]
            stripped = value.strip()
            new_value = changes[match[2].strip()]
            if decode_value(stripped) != new_value:
                encoded = encode_value(new_value)
                line = match[1] + leading + encoded + trailing + (match[4] or '')
        lines.append(line)
    return ''.join(lines)
