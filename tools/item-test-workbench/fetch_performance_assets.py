#!/usr/bin/env python3
"""Fetch seven pinned community vanilla item PNGs for native contact geometry.

No official-byte or rendered-world parity claim. No downloaded code executes.
"""
import argparse
import json
from pathlib import Path
import os
import tempfile
from fetch_player_assets import COMMIT, PREFIX, verify_png
from fetch_vfx_assets import destination, download

MANIFEST = Path(__file__).with_name('performance-assets-manifest.json')
IDS = {46, 162, 168, 190, 930, 964, 3485}


def provision(out, manifest, fetch=download):
    entries = manifest['files']
    if manifest['commit'] != COMMIT or len(entries) != len(IDS) or {e['path'] for e in entries} != {f'Images/Item_{i}.png' for i in IDS}:
        raise ValueError('Exact pinned seven-item geometry manifest required')
    rows = []
    for entry in entries:
        if entry['sourceURL'] != PREFIX + Path(entry['path']).name or not 24 <= entry['bytes'] <= 4*1024*1024:
            raise ValueError('Invalid bounded pinned asset URL/size')
        path = destination(out.absolute(), entry['path'])
        if path.exists(): verify_png(path.read_bytes(), entry, str(path))
        rows.append((entry, path))
    for entry, path in rows:
        if path.exists(): continue
        data = fetch(entry); verify_png(data, entry, entry['sourceURL'])
        destination(out.absolute(), entry['path']); path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.parent-asset-', delete=False) as stream:
            temp = Path(stream.name); stream.write(data); stream.flush(); os.fsync(stream.fileno())
        try:
            try: os.link(temp, path)
            except FileExistsError: verify_png(path.read_bytes(), entry, str(path))
        finally: temp.unlink(missing_ok=True)
    return {'verifiedFiles': len(rows), 'communityCommit': COMMIT, 'officialByteIdentityVerified': False, 'nativeRuntimeReady': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try: print(json.dumps(provision(args.out, json.loads(MANIFEST.read_text())), indent=2))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, str(error)+'\n')
