#!/usr/bin/env python3
"""Refresh the complete pinned vanilla item Git-blob index; no PNGs or code fetched."""
import argparse
import json
from pathlib import Path
import re
import urllib.request

from fetch_player_assets import COMMIT


def build_index(root, source):
    if root.get('truncated') is not False or source.get('truncated') is not False:
        raise ValueError('Complete upstream Git trees required')
    directory = next(row for row in root['tree'] if row['path'] == 'source-pngs' and row['type'] == 'tree')
    if source['sha'] != directory['sha']:
        raise ValueError('Source tree does not belong to pinned commit')
    rows = [row for row in source['tree'] if re.fullmatch(r'Item_[0-9]+\.png', row['path'])]
    items = {}
    for row in sorted(rows, key=lambda r: int(r['path'][5:-4])):
        name = str(int(row['path'][5:-4]))
        if name in items or row['type'] != 'blob' or row['mode'] != '100644' or not re.fullmatch(r'[0-9a-f]{40}', row['sha']):
            raise ValueError('Invalid or duplicate native PNG entry')
        if type(row['size']) is not int or not 33 <= row['size'] <= 4 * 1024 * 1024:
            raise ValueError('Native PNG size outside bounds')
        items[name] = [row['sha'], row['size']]
    if not items:
        raise ValueError('Empty vanilla item source tree')
    return dict(schemaVersion=1, communityCommit=COMMIT, sourceTreeSha=source['sha'],
                entryFormat=['gitBlobSha1', 'bytes'], items=items)


def encode_index(index):
    header = [f'  {json.dumps(k)}: {json.dumps(v)},' for k, v in index.items() if k != 'items']
    rows = [f'    {json.dumps(k)}: {json.dumps(v,separators=(",", ":"))}' for k, v in index['items'].items()]
    return '{\n' + '\n'.join(header) + '\n  "items": {\n' + ',\n'.join(rows) + '\n  }\n}\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    def fetch(sha):
        request = urllib.request.Request('https://api.github.com/repos/sullerandras/terraria-hd-textures/git/trees/' + sha,
                                         headers={'User-Agent': 'IFC-workbench-source-index'})
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.load(response)
    root = fetch(COMMIT)
    directory = next(row for row in root['tree'] if row['path'] == 'source-pngs')
    index = build_index(root, fetch(directory['sha']))
    args.out.write_text(encode_index(index), encoding='utf-8')
    print(json.dumps({'items': len(index['items']), 'commit': COMMIT, 'index': str(args.out)}))


if __name__ == '__main__':
    main()
