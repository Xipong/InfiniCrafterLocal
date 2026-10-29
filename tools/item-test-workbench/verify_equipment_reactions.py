#!/usr/bin/env python3
"""Native single-instance equipment, real damage/death, cooldown and vanity controls."""
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--no-build', action='store_true')
    parser.add_argument('--native-dll', type=Path)
    args = parser.parse_args()
    if args.native_dll and not args.no_build:
        parser.error('--native-dll requires --no-build')
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error('Use a fresh evidence directory')
    out.mkdir(parents=True, exist_ok=True)
    if not args.no_build:
        w.build()
    dll = args.native_dll.resolve() if args.native_dll else w.HERE / 'bin/Release/net8.0/ItemTestWorkbench.dll'
    dll_hash = hashlib.sha256(dll.read_bytes()).hexdigest()
    dotnet = os.environ.get('DOTNET', 'dotnet')
    base = {'playerUpdate': 'full', 'ticks': 320, 'seed': 1,
            'player': {'x': 800, 'y': 700, 'life': 100, 'mana': 200, 'manaCrystals': 9},
            'dummy': {'x': 1100, 'y': 700, 'life': 10000},
            'tiles': [{'tileX': 1, 'tileY': 47, 'width': 97, 'height': 1}],
            'actions': [], 'assertions': [{'kind': 'no_nonfinite'}]}
    rows = []
    for slot in ('accessory', 'head', 'body', 'legs'):
        case = copy.deepcopy(base)
        stimulus = 'hurt_player' if slot == 'accessory' else 'strike_hostile'
        case['actions'] = [{'tick': 0, 'kind': 'equip'}, {'tick': 5, 'kind': stimulus, 'damage': 10},
                           {'tick': 85, 'kind': stimulus, 'damage': 10}, {'tick': 150, 'kind': 'vanity'},
                           {'tick': 155, 'kind': stimulus, 'damage': 10}, {'tick': 200, 'kind': 'equip'},
                           {'tick': 225, 'kind': stimulus, 'damage': 10}, {'tick': 250, 'kind': 'unequip'}]
        defense = 2 if slot == 'accessory' else 3
        case['assertions'] += [{'kind': 'generated_buff_seen'}, {'kind': 'generated_buff_expired'}]
        for tick, stat, value in ((0, 'defense', defense), (151, 'defense', 0), (201, 'defense', defense),
                                  (251, 'defense', 0), (5, 'generatedBuffTicks', 60),
                                  (85, 'generatedBuffTicks', 0), (65, 'generatedBuffTicks', 0),
                                  (155, 'generatedBuffTicks', 0), (225, 'generatedBuffTicks', 60)):
            case['assertions'].append({'kind': 'player_stat_at', 'tick': tick, 'stat': stat, 'value': value})
        item = w.HERE / 'fixtures' / f'synthetic-reaction-{slot}.json'
        for suffix, scenario, expected in [('positive', case, 'passed'), ('negative-detector', copy.deepcopy(case), 'failed')]:
            name = f'{slot}-{suffix}'
            if suffix == 'negative-detector':
                scenario['assertions'] = [{'kind': 'player_stat_at', 'tick': 151, 'stat': 'defense', 'value': defense}]
            directory = out / name
            directory.mkdir()
            sp = directory / 'scenario.json'
            sp.write_text(json.dumps(scenario, indent=2))
            command = [dotnet, str(dll), '--item', str(item), '--scenario', str(sp), '--output', str(directory / 'native.json')]
            result = subprocess.run(command, cwd=w.ROOT, capture_output=True, text=True, timeout=180)
            (directory / 'stdout.log').write_text(result.stdout)
            (directory / 'stderr.log').write_text(result.stderr)
            trace = json.loads((directory / 'native.json').read_text()) if (directory / 'native.json').exists() else {}
            callbacks = [e for frame in trace.get('snapshots', []) for e in frame.get('events', []) if e.get('kind') == 'native_equipment_kill_callback']
            rows.append({'name': name, 'expectedStatus': expected, 'status': trace.get('status'),
                         'passed': trace.get('status') == expected and result.returncode == (0 if expected == 'passed' else 1)
                                   and (slot == 'accessory' or len(callbacks) == 4),
                         'nativeDeathCallbacks': len(callbacks), 'assertions': trace.get('assertions'), 'error': trace.get('error'),
                         'itemSha256': hashlib.sha256(item.read_bytes()).hexdigest(),
                         'scenarioSha256': hashlib.sha256(sp.read_bytes()).hexdigest()})
    summary = {'passed': all(r['passed'] for r in rows) and hashlib.sha256(dll.read_bytes()).hexdigest() == dll_hash, 'fullGameParity': False,
               'scope': 'Original Player.Update equipment reset; real Player.Hurt and Player.StrikeNPCDirect death dispatch. Controlled hostile has empty native loot table; no vanilla-loot, armor-art or multiplayer claim.',
               'nativeDll': str(dll), 'nativeDllSha256': dll_hash, 'executableUnchanged': hashlib.sha256(dll.read_bytes()).hexdigest() == dll_hash,
               'buildProvenance': 'Explicit executable selection; this script does not certify normal wrapper build provenance. Retain the independent source-build receipt.', 'cases': rows}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps({'passed': summary['passed'], 'cases': len(rows), 'failed': [r['name'] for r in rows if not r['passed']]}))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
