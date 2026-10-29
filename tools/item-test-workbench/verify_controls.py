#!/usr/bin/env python3
"""Native Player.Update movement/jump input and release controls, no physics model."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import workbench as w


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--native-dll', type=Path)
    p.add_argument('--no-build', action='store_true')
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
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    before = digest(dll)
    fixture = w.HERE / 'fixtures/synthetic-reaction-accessory.json'
    base = {'playerUpdate': 'full', 'ticks': 120, 'seed': 1,
            'player': {'x': 800, 'y': 700, 'mana': 200, 'manaCrystals': 9},
            'dummy': {'x': 1200, 'y': 700, 'life': 10000},
            'tiles': [{'tileX': 1, 'tileY': 47, 'width': 97, 'height': 1}],
            'actions': [{'tick': 0, 'kind': 'controls', 'left': False, 'right': True, 'jump': False},
                        {'tick': 20, 'kind': 'controls', 'left': False, 'right': True, 'jump': True},
                        {'tick': 30, 'kind': 'controls', 'left': False, 'right': False, 'jump': False}],
            'assertions': [{'kind': 'no_nonfinite'}, {'kind': 'spawn_count', 'value': 0}]}
    cases = [('run-jump-release', base, 'passed')]
    bad = copy.deepcopy(base)
    bad['playerUpdate'] = 'item_check'
    cases.append(('requires-native-player-update', bad, 'error'))
    bad = copy.deepcopy(base)
    bad['actions'][0]['jump'] = 'false'
    cases.append(('reject-string-boolean', bad, 'error'))
    rows = []
    for name, scenario, expected in cases:
        directory = out / name
        directory.mkdir()
        sp = directory / 'scenario.json'
        sp.write_text(json.dumps(scenario, indent=2))
        r = subprocess.run([os.environ.get('DOTNET', 'dotnet'), str(dll), '--item', str(fixture),
                            '--scenario', str(sp), '--output', str(directory / 'native.json')],
                           cwd=w.ROOT, capture_output=True, text=True, timeout=120)
        (directory / 'stderr.log').write_text(r.stderr)
        t = json.loads((directory / 'native.json').read_text())
        checks = {'nativeStatus': t.get('status') == expected, 'exitCode': r.returncode == (0 if expected == 'passed' else 2)}
        if expected == 'passed':
            frames = {f['tick']: f['player'] for f in t['snapshots'] if 'phase' not in f}
            checks.update(nativeAcceleration=frames[19]['x'] > frames[0]['x'] and frames[19]['vx'] > 0,
                          nativeJump=any(frames[tick]['vy'] < 0 for tick in range(20, 30)),
                          nativeRelease=frames[119]['vx'] == 0 and frames[119]['vy'] == 0 and frames[119]['y'] == 710,
                          releasedInputs=all(frames[119]['movementControls'][key] is False for key in ('left', 'right', 'jump')))
        else:
            checks['preflightNoSnapshots'] = not t.get('snapshots')
        rows.append({'name': name, 'passed': all(checks.values()), 'checks': checks, 'error': t.get('error')})
    summary = {'passed': all(row['passed'] for row in rows) and digest(dll) == before,
               'nativeDllSha256': before, 'executableUnchanged': digest(dll) == before,
               'fullGameParity': False, 'scope': 'Commanded native input; real Player.Update movement, jump, floor collision and friction. No alternate gravity or keyboard polling certification.', 'cases': rows}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
