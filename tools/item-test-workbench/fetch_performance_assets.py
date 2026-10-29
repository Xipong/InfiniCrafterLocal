#!/usr/bin/env python3
"""Fetch pinned community vanilla item geometry and optional projectile PNGs.

No official-byte or rendered-world parity claim. No downloaded code executes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import os
import re
import struct
import tempfile
from fetch_player_assets import COMMIT, PREFIX, verify_png
from fetch_vfx_assets import destination, download

MANIFEST = Path(__file__).with_name('performance-assets-manifest.json')
ITEM_INDEX = Path(__file__).with_name('vanilla-item-assets.json')
IDS = {46, 96, 98, 162, 168, 190, 930, 964, 2223, 3019, 3029, 3485}
PROJECTILE_IDS = {1, 14, 91, 92, 357, 485}


def item_entries(ids, index):
    if index.get('schemaVersion') != 1 or index.get('communityCommit') != COMMIT or index.get('entryFormat') != ['gitBlobSha1', 'bytes']:
        raise ValueError('Pinned vanilla item source index required')
    if not ids or len(ids) != len(set(ids)) or any(type(i) is not int or i < 1 for i in ids):
        raise ValueError('--items requires unique positive native item IDs')
    rows = []
    for i in ids:
        entry = index['items'].get(str(i))
        if not isinstance(entry, list) or len(entry) != 2 or not isinstance(entry[0], str) or not re.fullmatch(r'[0-9a-f]{40}', entry[0]):
            raise ValueError('Pinned source has no valid Item_' + str(i) + '.png')
        if type(entry[1]) is not int or not 33 <= entry[1] <= 4 * 1024 * 1024:
            raise ValueError('PNG size outside bounds')
        rows.append(dict(path=f'Images/Item_{i}.png', sourceURL=PREFIX + f'Item_{i}.png', gitBlobSha1=entry[0], bytes=entry[1]))
    return rows


def verify_asset(data, entry, label):
    if 'gitBlobSha1' not in entry:
        verify_png(data, entry, label)
        return
    blob = b'blob ' + str(len(data)).encode('ascii') + b'\0' + data
    if len(data) != entry['bytes'] or hashlib.sha1(blob).hexdigest() != entry['gitBlobSha1']:
        raise ValueError('Pinned Git blob mismatch: ' + label)
    if data[:8] != b'\x89PNG\r\n\x1a\n' or data[8:16] != b'\0\0\0\rIHDR':
        raise ValueError('PNG with canonical IHDR required: ' + label)
    width, height = struct.unpack('>II', data[16:24])
    if not 1 <= width <= 4096 or not 1 <= height <= 4096 or width * height > 16 * 1024 * 1024:
        raise ValueError('PNG dimensions outside bounds: ' + label)


def provision(out, manifest, fetch=download, *, include_projectiles=False, items=None, index=None):
    out = out.absolute()
    if any(p.is_symlink() for p in (out, *out.parents)) or (out.exists() and not out.is_dir()):
        raise ValueError('Output must be a non-symlink directory')
    if items is None:
        entries = list(manifest['files'])
        if manifest['commit'] != COMMIT or len(entries) != len(IDS) or {e['path'] for e in entries} != {f'Images/Item_{i}.png' for i in IDS}:
            raise ValueError('Pinned default geometry manifest required')
    else:
        entries = item_entries(items, index if index is not None else json.loads(ITEM_INDEX.read_text()))
    if include_projectiles:
        projectiles = manifest.get('projectileFiles', [])
        if len(projectiles) != len(PROJECTILE_IDS) or {e['path'] for e in projectiles} != {f'Images/Projectile_{i}.png' for i in PROJECTILE_IDS}:
            raise ValueError('Exact pinned vanilla projectile manifest required')
        entries += projectiles
    rows = []
    for entry in entries:
        if entry['sourceURL'] != PREFIX + Path(entry['path']).name or not 24 <= entry['bytes'] <= 4*1024*1024:
            raise ValueError('Invalid bounded pinned asset URL/size')
        path = destination(out.absolute(), entry['path'])
        if path.exists(): verify_asset(path.read_bytes(), entry, str(path))
        rows.append((entry, path))
    for entry, path in rows:
        if path.exists(): continue
        data = fetch(entry); verify_asset(data, entry, entry['sourceURL'])
        destination(out.absolute(), entry['path']); path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.parent-asset-', delete=False) as stream:
            temp = Path(stream.name); stream.write(data); stream.flush(); os.fsync(stream.fileno())
        try:
            try: os.link(temp, path)
            except FileExistsError: verify_asset(path.read_bytes(), entry, str(path))
        finally: temp.unlink(missing_ok=True)
    return {'verifiedFiles': len(rows), 'communityCommit': COMMIT, 'officialByteIdentityVerified': False, 'nativeRuntimeReady': False, 'includesProjectiles': include_projectiles}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--include-projectiles', action='store_true', help='Also fetch the six pinned vanilla projectile sprites admitted by original Main.DrawProj')
    parser.add_argument('--items', type=int, nargs='+', help='Fetch any native item IDs from the complete pinned source index; default is the original control set')
    args = parser.parse_args()
    try: print(json.dumps(provision(args.out, json.loads(MANIFEST.read_text()), include_projectiles=args.include_projectiles, items=args.items), indent=2))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, str(error)+'\n')
