#!/usr/bin/env python3
"""Index pinned community Projectile/Extra/Glow/BackPack/FishingLine source PNGs, not official bytes.

The index contains identities, not redistributed game images or execution code.
"""
# Direct script entrypoints resolve the same package as workbench.py.
if __package__ in (None, ""):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import json
from pathlib import Path
import re
import urllib.request

from python.fetch_player_assets import COMMIT

NAME = re.compile(r'(?:Projectile_(?:0|[1-9][0-9]*)|Extra_(?:0|[1-9][0-9]*)|Glow_(?:0|[1-9][0-9]*)|BackPack_(?:0|[1-9][0-9]*)|FishingLine)\.png')


def build_index(root, source, misc=None):
    if root.get('sha') != COMMIT or root.get('truncated') is not False or source.get('truncated') is not False:
        raise ValueError('Complete pinned commit Git trees required')
    directories = [r for r in root['tree'] if r.get('path') == 'source-pngs' and r.get('type') == 'tree']
    if len(directories) != 1 or source.get('sha') != directories[0]['sha']:
        raise ValueError('Source tree does not belong to pinned commit')
    entries = {}
    for row in sorted(source['tree'], key=lambda r: r['path']):
        if not NAME.fullmatch(row['path']):
            continue
        if (row['path'] in entries or row.get('type') != 'blob' or row.get('mode') != '100644'
                or not isinstance(row.get('sha'), str) or not re.fullmatch(r'[0-9a-f]{40}', row['sha'])
                or type(row.get('size')) is not int or not 33 <= row['size'] <= 4 * 1024 * 1024):
            raise ValueError('Invalid or duplicate native draw PNG entry')
        entries[row['path']] = [row['sha'], row['size']]
    if misc is not None:
        folders = [r for r in source['tree'] if r.get('path') == 'Misc' and r.get('type') == 'tree']
        if len(folders) != 1 or misc.get('sha') != folders[0]['sha'] or misc.get('truncated') is not False:
            raise ValueError('Complete Misc tree must belong to pinned source tree')
        ripples = [r for r in misc['tree'] if r.get('path') == 'Ripples.png']
        if len(ripples) != 1:
            raise ValueError('Pinned water distortion texture missing or duplicated')
        row = ripples[0]
        if (row.get('type') != 'blob' or row.get('mode') != '100644' or not isinstance(row.get('sha'), str)
                or not re.fullmatch(r'[0-9a-f]{40}', row['sha']) or type(row.get('size')) is not int
                or not 33 <= row['size'] <= 4 * 1024 * 1024):
            raise ValueError('Invalid pinned water distortion texture')
        entries['Misc/Ripples.png'] = [row['sha'], row['size']]
    if not entries:
        raise ValueError('Empty native draw source tree')
    return dict(schemaVersion=1, communityCommit=COMMIT, sourceTreeSha=source['sha'],
                entryFormat=['gitBlobSha1', 'bytes'], entries=entries)


def encode_index(index):
    header = [f'  {json.dumps(k)}: {json.dumps(v)},' for k, v in index.items() if k != 'entries']
    rows = [f'    {json.dumps(k)}: {json.dumps(v, separators=(",", ":"))}' for k, v in index['entries'].items()]
    return '{\n' + '\n'.join(header) + '\n  "entries": {\n' + ',\n'.join(rows) + '\n  }\n}\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    def fetch(sha):
        request = urllib.request.Request('https://api.github.com/repos/sullerandras/terraria-hd-textures/git/trees/' + sha,
                                         headers={'User-Agent': 'IFC-workbench-source-index'})
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.load(response)
    root = fetch(COMMIT)
    directory = next(row for row in root['tree'] if row['path'] == 'source-pngs')
    source = fetch(directory['sha'])
    misc = next(row for row in source['tree'] if row['path'] == 'Misc' and row['type'] == 'tree')
    index = build_index(root, source, fetch(misc['sha']))
    args.out.write_text(encode_index(index), encoding='utf-8')
    print(json.dumps({'entries': len(index['entries']), 'commit': COMMIT, 'officialByteIdentityVerified': False}))


if __name__ == '__main__':
    main()
