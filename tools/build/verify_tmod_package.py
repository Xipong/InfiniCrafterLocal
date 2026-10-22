"""Read-only validation of official tML packages; never creates a .tmod.

Format: tModLoader/Terraria/ModLoader/Core/TmodFile.cs (official repository).
Checks every payload, container hash, manifest version/dependencies, source
localization/resources and exact compiled assembly identity.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import zlib


def exact(stream: io.BytesIO, size: int) -> bytes:
    if size < 0:
        raise ValueError('Negative length')
    data = stream.read(size)
    if len(data) != size:
        raise ValueError('Truncated package')
    return data


def integer(stream: io.BytesIO) -> int:
    return struct.unpack('<i', exact(stream, 4))[0]


def string(stream: io.BytesIO) -> str:
    size = 0
    for shift in range(0, 35, 7):
        value = exact(stream, 1)[0]
        size |= (value & 127) << shift
        if not value & 128:
            return exact(stream, size).decode('utf-8')
    raise ValueError('Invalid string length')


def read_package(data: bytes) -> tuple[str, str, str, dict[str, bytes]]:
    stream = io.BytesIO(data)
    if exact(stream, 4) != b'TMOD':
        raise ValueError('Not a TMOD package')
    tml_version = string(stream)
    digest = exact(stream, 20)
    exact(stream, 256)  # Optional Workshop signature, not required for local mods.
    size = integer(stream)
    payload = stream.read()
    if len(payload) != size or hashlib.sha1(payload).digest() != digest:
        raise ValueError('Package length/hash mismatch')
    stream = io.BytesIO(payload)
    name, version = string(stream), string(stream)
    count = integer(stream)
    if not 1 <= count <= 100000:
        raise ValueError('Invalid file count')
    table = [(string(stream), integer(stream), integer(stream)) for _ in range(count)]
    files = {}
    for path, length, stored in table:
        if path in files or path.startswith('/') or '..' in path.split('/'):
            raise ValueError('Duplicate or unsafe file path')
        content = exact(stream, stored)
        if length != stored:
            content = zlib.decompress(content, -15)
        if len(content) != length:
            raise ValueError(f'Payload length mismatch: {path}')
        files[path] = content
    if stream.read():
        raise ValueError('Unexpected trailing payload')
    return tml_version, name, version, files


def read_info(data: bytes) -> dict:
    stream = io.BytesIO(data)
    values = {}
    lists = {'dllReferences', 'modReferences', 'weakReferences', 'sortAfter', 'sortBefore'}
    flags = {'noCompile', '!playableOnPreview', 'translationMod', '!hideCode', '!hideResources', 'includeSource'}
    strings = {'author', 'version', 'displayName', 'homepage', 'description', 'eacPath', 'modSource', 'buildVersion'}
    while tag := string(stream):
        if tag in lists:
            items = []
            while item := string(stream):
                items.append(item)
            values[tag] = items
        elif tag in flags:
            values[tag] = True
        elif tag in strings:
            values[tag] = string(stream)
        elif tag == 'side':
            values[tag] = exact(stream, 1)[0]
        else:
            raise ValueError(f'Unknown Info field: {tag}')
    if stream.read():
        raise ValueError('Trailing Info payload')
    return values


def verify(path: Path, source: Path, assembly: Path, expected_tml: str) -> dict:
    data = path.read_bytes()
    tml, name, version, files = read_package(data)
    manifest = dict(line.split('=', 1) for line in source.joinpath('build.txt').read_text().splitlines() if '=' in line)
    manifest = {key.strip(): value.strip() for key, value in manifest.items()}
    if name != source.name or version != manifest['version'] or tml != expected_tml:
        raise ValueError('Package name/version/tML version differs from source/build')
    info = read_info(files['Info'])
    refs = [ref.strip() for ref in manifest.get('modReferences', '').split(',') if ref.strip()]
    if info.get('version') != version or info.get('modReferences', []) != refs:
        raise ValueError('Embedded manifest version/dependencies mismatch')
    if files[f'{name}.dll'] != assembly.read_bytes() or not files[f'{name}.dll'].startswith(b'MZ'):
        raise ValueError('Packaged assembly differs from the Release build')
    for resource in source.rglob('*'):
        relative = resource.relative_to(source)
        if not resource.is_file() or any(part.startswith('.') or part in {'bin', 'obj'} for part in relative.parts):
            continue
        key = relative.as_posix()
        if resource.suffix == '.hjson' and files.get(key) != resource.read_bytes():
            raise ValueError(f'Localization missing or changed: {key}')
        # Official content conversion may convert PNG textures to .rawimg.
        if resource.suffix == '.png' and key not in files and str(relative.with_suffix('.rawimg')).replace('\\', '/') not in files:
            raise ValueError(f'Texture missing: {key}')
    if any(path.startswith(('bin/', 'obj/')) or path.endswith(('.cs', '.csproj')) for path in files):
        raise ValueError('Build/source debris in package')
    return {'status': 'passed', 'name': name, 'version': version, 'tmlVersion': tml,
            'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'fileCount': len(files), 'modReferences': refs, 'files': sorted(files),
            'runtimeSmoke': 'notRun: container validation is not an in-game test'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--assembly', type=Path, required=True)
    parser.add_argument('--tml-version', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.package, args.source, args.assembly, args.tml_version)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f"Verified {report['name']} {report['version']}: {report['fileCount']} entries, SHA256 {report['sha256']}")
