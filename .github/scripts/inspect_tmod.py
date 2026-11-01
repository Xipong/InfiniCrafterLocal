#!/usr/bin/env python3
"""Inspect pinned TMOD v0.11+ packages; extract only their assembly and Info.

Layout follows tML Core/TmodFile.cs. Data and whole-file hashes are verified;
DLLs remain in the runner's temporary directory and must not be published.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
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
        for entry in (name + '.dll', 'Info'):
            if entry not in entries:
                raise ValueError(f'missing required TMOD entry: {entry}')
            offset, length, compressed = entries[entry]
            if length > 100_000_000 or compressed > 100_000_000:
                raise ValueError('unexpectedly large assembly/metadata')
            stream.seek(start + offset)
            raw = take(stream, compressed)
            if length != compressed:
                decoder = zlib.decompressobj(-zlib.MAX_WBITS)
                raw = decoder.decompress(raw, length + 1)
                raw += decoder.flush()
                if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                    raise ValueError(f'invalid deflate stream: {entry}')
            if len(raw) != length:
                raise ValueError(f'invalid decoded length: {entry}')
            if entry.endswith('.dll') and not raw.startswith(b'MZ'):
                raise ValueError('mod assembly has no PE signature')
            target = output / entry
            target.write_bytes(raw)
            files.append({'name': entry, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    interest = [key for key in entries if 'terratomere' in key.lower()]
    localization = [key for key in entries if key.startswith('Localization/')]
    return {'name': name, 'version': version, 'tModLoaderBuildVersion': tml_version,
            'packageSha256': EXPECTED[expected_name], 'packageBytes': size,
            'payloadSha1Verified': True, 'fileCount': count, 'extracted': files,
            'terratomereEntries': sorted(interest), 'localizationEntries': len(localization),
            'dllDirectory': str(output), 'binaryFilesPublished': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('package', type=Path)
    p.add_argument('--name', required=True, choices=sorted(EXPECTED))
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(inspect(args.package, args.out, args.name), indent=2))


if __name__ == '__main__':
    main()
