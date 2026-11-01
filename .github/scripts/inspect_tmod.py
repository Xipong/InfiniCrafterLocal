#!/usr/bin/env python3
"""Inspect pinned TMOD v0.11+ packages; extract resources and reconstruct build metadata in runner temp.

Layout follows tML Core/TmodFile.cs. Data and whole-file hashes are verified;
DLLs remain in the runner's temporary directory and must not be published.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import io
from pathlib import Path, PurePosixPath
import struct
import zlib

EXPECTED = {
    'CalamityMod': 'd50fea9025f88ee2073c00e3482976ca1e6ea54d0b8770eb7810bb7b280397d6',
    'CalamityModMusic': 'ca202bc18ae690d5ea7267b42c9ec8162241a19aafc9efdf40eff0a59eada9e5',
}


def take(stream, count):
    result = stream.read(count)
    if len(result) != count:
        raise ValueError('truncated TMOD')
    return result


def integer(stream):
    return struct.unpack('<i', take(stream, 4))[0]


def string(stream):
    length = 0
    for index in range(5):
        byte = take(stream, 1)[0]
        length |= (byte & 127) << (index * 7)
        if byte < 128:
            break
    else:
        raise ValueError('invalid BinaryReader string length')
    if length > 16384:
        raise ValueError('oversized TMOD table string')
    return take(stream, length).decode('utf-8', errors='strict')


def file_hash(path, algorithm='sha256'):
    digest = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


# Mirrors tML BuildProperties.ReadFromStream / InfoToBuildTxt. Info stores
# already-resolved sortAfter, not buildIgnore or the original source build.txt.
def build_txt(info, expected_version):
    stream = io.BytesIO(info)
    lists = {'dllReferences', 'modReferences', 'weakReferences', 'sortAfter', 'sortBefore'}
    values = {'author', 'version', 'displayName', 'homepage', 'description', 'eacPath', 'buildVersion', 'modSource'}
    flags = {'noCompile', '!playableOnPreview', 'translationMod', 'libraryMod', '!hideCode', '!hideResources', 'includeSource'}
    parsed = {}
    while (tag := string(stream)):
        if tag in parsed:
            raise ValueError(f'duplicate Info tag: {tag}')
        if tag in lists:
            items = []
            while (value := string(stream)):
                items.append(value)
            parsed[tag] = items
        elif tag in values:
            parsed[tag] = string(stream)
        elif tag in flags:
            parsed[tag] = True
        elif tag == 'side':
            side = take(stream, 1)[0]
            if side not in (0, 1, 2, 3):
                raise ValueError('invalid Info side')
            parsed[tag] = ('Both', 'Client', 'Server', 'NoSync')[side]
        else:
            raise ValueError(f'unknown Info tag: {tag}')
    if stream.read(1) or parsed.get('version') != expected_version:
        raise ValueError('Info trailing data or version mismatch')
    lines = []
    for key in ('displayName', 'author', 'version', 'homepage'):
        if parsed.get(key): lines.append(f"{key} = {parsed[key]}")
    for key in ('dllReferences', 'modReferences', 'weakReferences', 'sortAfter', 'sortBefore'):
        if parsed.get(key): lines.append(f"{key} = {', '.join(parsed[key])}")
    refs = [item.split('@', 1)[0] for key in ('modReferences', 'weakReferences') for item in parsed.get(key, [])]
    ignored = [x for x in refs if x not in parsed.get('sortAfter', []) and x not in parsed.get('sortBefore', [])]
    if ignored: lines.append(f"sortIgnore = {', '.join(ignored)}")
    for key in ('noCompile', 'translationMod', 'libraryMod', 'includeSource'):
        if parsed.get(key): lines.append(f'{key} = true')
    if '!playableOnPreview' in parsed: lines.append('playableOnPreview = false')
    if '!hideCode' not in parsed: lines.append('hideCode = true')
    if '!hideResources' not in parsed: lines.append('hideResources = true')
    if parsed.get('side', 'Both') != 'Both': lines.append(f"side = {parsed['side']}")
    return '\n'.join(lines) + '\n', parsed


def safe_target(output, entry):
    path = PurePosixPath(entry)
    if (not entry or path.is_absolute() or '\\' in entry or ':' in entry or
        any(part in ('', '.', '..') for part in entry.split('/'))):
        raise ValueError(f'unsafe TMOD entry: {entry!r}')
    target = output.joinpath(*path.parts)
    if not target.resolve().is_relative_to(output.resolve()):
        raise ValueError(f'TMOD path escapes root: {entry!r}')
    return target


def inspect(path, output, expected_name):
    if file_hash(path) != EXPECTED[expected_name]:
        raise ValueError(f'{path}: differs from the officially obtained pinned package')
    size = path.stat().st_size
    with path.open('rb') as stream:
        if take(stream, 4) != b'TMOD':
            raise ValueError('invalid TMOD magic')
        tml_version = string(stream)
        expected_hash = take(stream, 20)
        take(stream, 256)  # Signature is retained by Steam; no authenticity claim here.
        payload_size = integer(stream)
        payload_start = stream.tell()
        if payload_size < 0 or payload_start + payload_size != size:
            raise ValueError('invalid TMOD payload length')
        digest = hashlib.sha1()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
        if digest.digest() != expected_hash:
            raise ValueError('TMOD payload SHA-1 mismatch')
        stream.seek(payload_start)
        name, version = string(stream), string(stream)
        if name != expected_name:
            raise ValueError(f'unexpected internal mod name {name!r}')
        count = integer(stream)
        if not 1 <= count <= 500_000:
            raise ValueError('invalid TMOD file count')
        entries, relative_offset = {}, 0
        for _ in range(count):
            key = string(stream)
            length, compressed = integer(stream), integer(stream)
            if key in entries or length < 0 or compressed < 0:
                raise ValueError('invalid TMOD file table')
            entries[key] = (relative_offset, length, compressed)
            relative_offset += compressed
        start = stream.tell()
        if start + relative_offset != size:
            raise ValueError('TMOD file table does not span payload')
        output.mkdir(parents=True, exist_ok=False)
        files = []
        expanded = sum(length for _, length, _ in entries.values())
        print(f'{name} expanded bytes: {expanded}; largest entries: ' +
              repr(sorted(((length, key) for key, (_, length, _) in entries.items()), reverse=True)[:5]), flush=True)
        if expanded > 8_000_000_000:
            raise ValueError('TMOD expanded size exceeds diagnostic limit (8 GB)')
        if shutil.disk_usage(output).free < expanded + 1_000_000_000:
            raise ValueError('insufficient temporary runner disk space for extraction plus 1 GB reserve')
        for required in (name + '.dll', 'Info'):
            if required not in entries: raise ValueError(f'missing required TMOD entry: {required}')
        for entry, (offset, length, compressed) in entries.items():
            target = safe_target(output, entry)
            if length > 300_000_000 or compressed > 300_000_000:
                raise ValueError(f'oversized TMOD entry: {entry}')
            stream.seek(start + offset)
            raw = take(stream, compressed)
            if length != compressed:
                decoder = zlib.decompressobj(-zlib.MAX_WBITS)
                raw = decoder.decompress(raw, length + 1)
                if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                    raise ValueError(f'invalid deflate stream: {entry}')
            if len(raw) != length:
                raise ValueError(f'invalid decoded length: {entry}')
            if entry == name + '.dll' and not raw.startswith(b'MZ'):
                raise ValueError('mod assembly has no PE signature')
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as dest: dest.write(raw)
            if entry in (name + '.dll', 'Info'):
                files.append({'name': entry, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
        metadata, info = build_txt((output / 'Info').read_bytes(), version)
        with (output / 'build.txt').open('x', encoding='utf-8') as dest: dest.write(metadata)
        print(f'{name} build.txt reconstructed from packaged Info; not original source metadata:\n{metadata}')
    interest = [key for key in entries if 'terratomere' in key.lower()]
    localization = [key for key in entries if key.startswith('Localization/')]
    return {'name': name, 'version': version, 'tModLoaderBuildVersion': tml_version,
            'packageSha256': EXPECTED[expected_name], 'packageBytes': size,
            'payloadSha1Verified': True, 'fileCount': count, 'extracted': files,
            'terratomereEntries': sorted(interest), 'localizationEntries': len(localization),
            'dllDirectory': str(output), 'infoFields': sorted(info), 'binaryFilesPublished': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('package', type=Path)
    p.add_argument('--name', required=True, choices=sorted(EXPECTED))
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(inspect(args.package, args.out, args.name), indent=2))


if __name__ == '__main__':
    main()
