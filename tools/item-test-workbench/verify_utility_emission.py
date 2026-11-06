#!/usr/bin/env python3
"""Behavioral checks for explicitly scoped native solution emission observations."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import workbench as w
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-dll', type=Path, required=True)
    parser.add_argument('--generated-item', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--player-assets', type=Path)
    parser.add_argument('--vanilla-assets', type=Path)
    args = parser.parse_args()
    if bool(args.player_assets) != bool(args.vanilla_assets):
        parser.error('Provide both asset roots for optional backpack refusal checks')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    scene = dict(playerUpdate='full', vanillaUtilityEmission=True, ticks=60, seed=1,
                 player=dict(x=800, y=710, life=100, mana=200, manaCrystals=9),
                 dummy=dict(x=960, y=707, width=32, height=48, life=10000),
                 tiles=[dict(tileX=1, tileY=47, width=97, height=1)],
                 inventory=[dict(slot=54, itemId=780, stack=100)],
                 actions=[dict(tick=0, kind='aim', x=960, y=731),
                          dict(tick=0, kind='primary'), dict(tick=12, kind='release')],
                 assertions=[dict(kind='no_nonfinite')])
    cases = [('solution', 'Clentaminator', {}, None),
             ('no-ammo', 'Clentaminator', {'inventory': []}, None),
             ('wrong-ammo', 'Clentaminator', {'inventory': [dict(slot=54,itemId=97,stack=100)]}, None),
             ('default-refuses', 'Clentaminator', {'vanillaUtilityEmission': False}, 'not an admitted damage weapon'),
             ('combat-refuses', 'Minishark', {}, 'Utility emission requires'),
             ('placement-refuses', 'DirtBlock', {}, 'Utility emission requires'),
             ('partial-player-refuses', 'Clentaminator', {'playerUpdate': 'item_check'}, 'Utility emission requires'),
             ('generated-refuses', None, {}, 'Utility emission requires'),
             ('combat-default', 'Minishark', {'vanillaUtilityEmission': False, 'inventory': [dict(slot=54,itemId=97,stack=100)]}, None)]
    results = []
    for name, item, changes, error in cases:
        folder = out / name
        folder.mkdir()
        current = copy.deepcopy(scene)
        current.update(changes)
        scenario = folder / 'scenario.json'
        scenario.write_text(json.dumps(current, indent=2))
        tracepath = folder / 'native.json'
        itemargs = ['--vanilla-item', item] if item else ['--item', str(args.generated_item.resolve())]
        process = subprocess.run([os.environ.get('DOTNET', 'dotnet'), str(args.native_dll.resolve()),
                                  *itemargs, '--scenario', str(scenario), '--output', str(tracepath)],
                                 capture_output=True, text=True, timeout=180)
        (folder / 'process.log').write_text(process.stdout + process.stderr)
        trace = w.read_native_json(tracepath)
        snapshots = trace.get('snapshots', [])
        events = [e for s in snapshots for e in s.get('events', [])]
        spawns = [e for e in events if e['kind'] == 'spawn']
        checks = {'expectedOutcome': (process.returncode == 2 and error in trace.get('error', '')) if error
                  else process.returncode == 0 and trace['status'] == 'passed'}
        if not error:
            checks['expectedEmission'] = not spawns if name in ('no-ammo', 'wrong-ammo') else bool(spawns)
            if name != 'combat-default':
                checks['scopeReceipt'] = 'utilityEmissionScope' in trace.get('coverage', {})
                checks['noFakeDamage'] = trace.get('combat', {}).get('totalHits') == 0
                checks['targetUnchanged'] = snapshots[0]['dummy']['life'] == snapshots[-1]['dummy']['life']
            if name in ('no-ammo', 'wrong-ammo'):
                checks['inventoryUnchanged'] = snapshots[0]['player']['inventory'] == snapshots[-1]['player']['inventory']
            if name == 'solution':
                stacks = [i['stack'] for i in snapshots[-1]['player']['inventory'] if i['slot'] == 54]
                checks['nativeSolutionConsumed'] = bool(stacks) and stacks[0] < 100
                checks['nativeAmmoSource'] = all(e.get('ammoItemIdUsed') == 780 for e in spawns)
                checks['nativeItemUnmodified'] = snapshots[0]['player']['itemProjection']['damage'] <= 0
        result = dict(name=name, passed=all(checks.values()), checks=checks)
        results.append(result)
        print(json.dumps(result), flush=True)
    if args.player_assets:
        for name, index, mutation, error in [
                ('backpack-missing', 2, 'missing', 'Missing exact starter-player source PNG: BackPack_2'),
                ('backpack-corrupt', 2, 'corrupt', 'Player PNG does not match pinned community source bytes: BackPack_2'),
                ('backpack-unsupported', 9, None, 'backpackTexture requires')]:
            folder = out / name
            folder.mkdir()
            assets = folder / 'player-assets'
            shutil.copytree(args.player_assets, assets)
            backpack = assets / 'Images/BackPack_2.png'
            if mutation == 'missing':
                backpack.unlink(missing_ok=True)
            elif mutation == 'corrupt':
                backpack.write_bytes(backpack.read_bytes() + b'corrupt-test-copy')
            current = copy.deepcopy(scene)
            current.update(playerUpdate='client_vfx', vanillaAssetRoot=str(args.vanilla_assets.resolve()),
                           nativeRender=dict(capture=False, drawArtwork=True, drawPlayer=True,
                                             artworkFiles=[], playerAssetRoot=str(assets), backpackTexture=index))
            scenario = folder / 'scenario.json'
            scenario.write_text(json.dumps(current, indent=2))
            tracepath = folder / 'native.json'
            process = subprocess.run([os.environ.get('DOTNET', 'dotnet'), str(args.native_dll.resolve()),
                                      '--vanilla-item', 'Clentaminator', '--scenario', str(scenario),
                                      '--output', str(tracepath)], capture_output=True, text=True, timeout=180)
            (folder / 'process.log').write_text(process.stdout + process.stderr)
            trace = w.read_native_json(tracepath)
            checks = dict(expectedRefusal=process.returncode == 2 and error in trace.get('error', ''))
            result = dict(name=name, passed=all(checks.values()), checks=checks)
            results.append(result)
            print(json.dumps(result), flush=True)
    summary = dict(passed=all(r['passed'] for r in results), cases=results,
                   scope='Native CPU admission, ammo and target controls; no world-conversion or rendered pose certification')
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    return int(not summary['passed'])

if __name__ == '__main__':
    raise SystemExit(main())
