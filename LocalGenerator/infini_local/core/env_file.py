"""Dependency-free config.env wire codec shared by runtime, Studio and toolbox.

New generated files carry an explicit header before assignments. Their quoted
values are JSON strings on one physical line; legacy files never decode escapes.
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


def config_format(text: str) -> str:
    """Recognize only a leading format declaration, never a comment in a value."""
    version = 'legacy'
    assigned = False
    for number, raw in enumerate(physical_lines(text.lstrip('\ufeff')), 1):
        line = raw.strip()
        if line.startswith(_HEADER_PREFIX):
            if assigned or line != FORMAT_HEADER:
                raise ValueError(f'Unsupported or misplaced config.env format declaration at line {number}.')
            version = 'json-string-v1'
        elif line and not line.startswith('#') and '=' in line:
            assigned = True
    return version


def legacy_quote(value: str) -> str:
    """Return an enclosing quote only when it is one literal, not argv quotes.

    Backslashes remain literal, including Windows paths. Escaped interior quote
    characters do not close the wrapper; no legacy escape is decoded here.
    """
    if len(value) < 2 or value[0] not in ('"', "'") or value[-1] != value[0]:
        return ''
    quote = value[0]
    slashes = 0
    for character in value[1:-1]:
        if character == quote and slashes % 2 == 0:
            return ''
        slashes = slashes + 1 if character == '\\' else 0
    return quote


def decode_value(raw: str, version: str, *, line: int = 0) -> str:
    value = raw.strip()
    if version == 'json-string-v1' and value.startswith('"'):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            # Never echo the setting's value: it may contain credentials.
            raise ValueError(f'Invalid JSON string in config.env at line {line}.') from None
        if not isinstance(value, str):
            raise ValueError(f'Expected a config.env string at line {line}.')
    elif legacy_quote(value):
        value = value[1:-1]
    if '\x00' in value:
        raise ValueError(f'NUL is not allowed in config.env at line {line}.')
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ValueError(f'Unpaired Unicode surrogate in config.env at line {line}.')
    return value


def encode_value(value: str) -> str:
    if not isinstance(value, str) or '\x00' in value or any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ValueError('config.env values must be Unicode strings without NUL or unpaired surrogates.')
    return json.dumps(value, ensure_ascii=False)


def _reject_legacy_multiline(lines: list[str]) -> None:
    """Refuse recognizable old-writer continuation blocks, never guess values.

    A value beginning with an unmatched quote alone is not enough: argv can
    contain literal/partial quotes, and legacy Windows paths keep backslashes.
    Only a later non-assignment continuation closing the wrapper proves the
    unsafe physical-multiline shape. Report locations without exposing values.
    """
    opened = None
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        assignment = not line.startswith('#') and '=' in line and bool(line.split('=', 1)[0].strip())
        if opened is not None and line and not line.startswith('#') and not assignment and line.endswith('"'):
            raise ValueError(f'Legacy multiline config.env value at lines {opened}–{number}. '
                             'Restore this value as one physical line before saving; no automatic reconstruction was attempted.')
        if not assignment:
            continue
        value = line.split('=', 1)[1].strip()
        if not value.startswith('"'):
            continue
        # The old writer escaped quotes but left existing backslashes literal.
        # Any immediately preceding slash therefore marks an interior quote;
        # JSON's backslash parity rule cannot decode that historical grammar.
        closed = any(character == '"' and value[index - 1] != '\\'
                     for index, character in enumerate(value[1:], 1))
        if not closed and opened is None:
            opened = number


def parse_env_text(text: str) -> dict[str, str]:
    """Return explicit settings; first occurrence wins, matching runtime loads."""
    version = config_format(text)
    lines = physical_lines(text.lstrip('\ufeff'))
    if version == 'legacy':
        _reject_legacy_multiline(lines)
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
        value = decode_value(raw_value, version, line=number)
        data.setdefault(key, value)
    return data


def read_env_file(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding='utf-8-sig')
    except FileNotFoundError:
        return {}
    return parse_env_text(text)
