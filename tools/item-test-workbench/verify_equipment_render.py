#!/usr/bin/env python3
"""Check actual native equipped overlay dispatch, pixels, and missing-asset refusal.

Supply an already-generated equipment JSON and its exact published PNGs. No image
or item is generated or rewritten, and no pixel difference is attributed to an
item unless the recorded native idle pose is identical.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from PIL import Image, ImageChops
import workbench as w


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--item', type=Path, required=True)
    p.add_argument('--artwork', type=Path, nargs='+', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--player-assets', type=Path, required=True)
    p.add_argument('--native-dll', type=Path)
    p.add_argument('--no-build', action='store_true')
    p.add_argument('--item-boundary', choices=['fresh', 'local_cache'], default='local_cache')
    args = p.parse_args()
    if args.native_dll and not args.no_build:
        p.error("--native-dll requires --no-build")
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        p.error('Use a fresh evidence directory')
    out.mkdir(parents=True, exist_ok=True)
    if not args.no_build:
        w.build()
    dll = args.native_dll.resolve() if args.native_dll else w.HERE / 'bin/Release/net8.0/ItemTestWorkbench.dll'
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    dll_hash = sha(dll)
    item = args.item.resolve()
    data = json.loads(item.read_text())
    if not (data.get('armor', {}).get('enabled') or data.get('accessory', {}).get('enabled')):
        p.error('This verifier requires declared equipment, not a category/name heuristic')
    overlay = data.get('visual', {}).get('equipOverlayPath', '').replace('\\', '/').split('/')[-1]
    if not overlay:
        p.error('Equipment definition has no authored overlay path')
    artifacts = [str(path.resolve()) for path in args.artwork]
    base = {'playerUpdate': 'client_vfx', 'ticks': 90, 'seed': 1,
            'worldId': int(data.get('recipeMeta', {}).get('worldId') or 0),
            'player': {'x': 800, 'y': 700, 'life': 100, 'mana': 200, 'manaCrystals': 9},
            'dummy': {'x': 1100, 'y': 700, 'life': 10000},
            'tiles': [{'tileX': 1, 'tileY': 47, 'width': 97, 'height': 1}],
            'actions': [{'tick': 10, 'kind': 'equip'}, {'tick': 40, 'kind': 'vanity'}, {'tick': 70, 'kind': 'unequip'}],
            'assertions': [{'kind': 'no_nonfinite'}],
            'nativeRender': {'width': 320, 'height': 320, 'cameraX': 650, 'cameraY': 580, 'zoom': 3,
                             'capture': True, 'drawArtwork': True, 'drawPlayer': True, 'lightingMode': 'viewport_fill',
                             'playerAssetRoot': str(args.player_assets.resolve()), 'artworkFiles': artifacts}}
    rows = []
    for name, scenario in [('native', base), ('missing-overlay', copy.deepcopy(base))]:
        directory = out / name
        directory.mkdir()
        if name == 'missing-overlay':
            scenario['nativeRender']['artworkFiles'] = [path for path in artifacts if Path(path).name != overlay]
        sp = directory / 'scenario.json'
        sp.write_text(json.dumps(scenario, indent=2))
        result = subprocess.run([os.environ.get('DOTNET', 'dotnet'), str(dll), '--item', str(item),
                                 '--scenario', str(sp), '--output', str(directory / 'native.json'),
                                 '--item-boundary', args.item_boundary], cwd=w.ROOT, capture_output=True, text=True, timeout=240)
        (directory / 'stdout.log').write_text(result.stdout)
        (directory / 'stderr.log').write_text(result.stderr)
        trace = json.loads((directory / 'native.json').read_text()) if (directory / 'native.json').exists() else {}
        if name == 'missing-overlay':
            rows.append({'name': name, 'passed': result.returncode == 2 and trace.get('status') == 'error'
                         and 'Missing explicit artwork file' in trace.get('error', '') and not trace.get('nativeRender', {}).get('frames')})
            continue
        frames = trace.get('nativeRender', {}).get('frames', [])
        by_tick = {f['tick']: f for f in frames}
        dispatch = len(frames) == 90 and all(f.get('equipmentOverlayDrawCount') == (1 if 10 <= f['tick'] < 70 else 0) for f in frames)
        integrity = all((directory / f['path']).is_file() and sha(directory / f['path']) == f['sha256'] for f in frames)
        visibility = None
        # Native diagnostic preview occupies top-left. Compare only recorded
        # player region (fixed camera here), never recolor/reconstruct the frames.
        if 10 in by_tick and 70 in by_tick:
            a, b = by_tick[10], by_tick[70]
            pose_same = a.get('nativePlayerDrawSet') == b.get('nativePlayerDrawSet')
            box = (96, 80, 256, 280)
            with Image.open(directory / a['path']) as ia, Image.open(directory / b['path']) as ib:
                delta = ImageChops.difference(ia.convert('RGB').crop(box), ib.convert('RGB').crop(box))
                changed = sum(any(pixel) for pixel in delta.get_flattened_data())
            visibility = {'sameNativeIdlePose': pose_same, 'region': list(box), 'changedRgbPixels': changed,
                          'visibleDifference': changed > 0 if pose_same else None,
                          'scope': 'Equipped versus unequipped native PNGs, excluding inventory preview. Not universal visibility across animations, facing or occluders.'}
        rows.append({'name': name, 'nativeStatus': trace.get('status'), 'nativeDispatchPassed': dispatch,
                     'pngIntegrityPassed': integrity, 'visibility': visibility, 'error': trace.get('error'),
                     'passed': result.returncode == 0 and trace.get('status') == 'passed' and dispatch and integrity
                               and visibility is not None and visibility['visibleDifference'] is True})
    summary = {'passed': all(row['passed'] for row in rows) and sha(dll) == dll_hash,
               'fullGameParity': False, 'itemSha256': sha(item), 'nativeDllSha256': dll_hash,
               'executableUnchanged': sha(dll) == dll_hash, 'cases': rows,
               'buildProvenance': 'Explicit native executable; retain independent source-build receipt.',
               'visualApproval': 'PNG pixels must still be inspected; dispatch counts alone are not visual approval.'}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
