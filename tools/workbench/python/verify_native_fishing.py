#!/usr/bin/env python3
"""Real native rod/bait/water lifecycle. No manually spawned bobber, forced bite or fish grant."""
# Direct script entrypoints resolve the same package as workbench.py.
if __package__ in (None, ""):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import workbench as w


def scene(*, seed=1):
    return dict(playerUpdate='full', ticks=2400, seed=seed, worldWidthTiles=400, worldId=12,
                player=dict(x=800, y=918, mana=20), dummy=dict(x=3000, y=700, life=10000),
                tiles=[dict(tileX=2, tileY=60, width=395, height=4)],
                fishing=dict(water=dict(tileX=62, tileY=48, width=50, height=12), reelOnBite=True),
                inventory=[dict(slot=2, itemId=2002, stack=20)],
                actions=[dict(kind='aim', tick=0, x=1150, y=850), dict(kind='primary', tick=0), dict(kind='release', tick=1)],
                assertions=[dict(kind='no_nonfinite')])


def inspect(trace):
    observations=trace.get('fishing', {}).get('observations', [])
    states=[o for o in observations if o.get('kind')=='native_state']
    last=states[-1] if states else {}
    inventory=last.get('inventory', [])
    # Exclude the held synthetic item and provisioned bait, not a guessed fish identity.
    catches=[i for i in inventory if i['slot'] not in (0, 2)]
    return dict(initialBobber=any(o.get('tick',80)<80 and o.get('bobbers') for o in states), nativeCatchIds=sorted({int(b['ai1']) for o in states for b in o['bobbers'] if b.get('ai0')==1 and b.get('ai1',0)>0}), bite=any(o.get('kind')=='natural_bite_reel_input' for o in observations),
                spawned=any(o.get('bobbers') for o in states), wet=any(b['wet'] for o in states for b in o['bobbers']),
                caught=catches, lastBobbers=last.get('bobbers', []),
                bait=next((i['stack'] for i in inventory if i['slot']==2), 0),
                manaDebited=trace.get('resources', {}).get('observedManaDebited'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-dll', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True, exist_ok=False)
    dll=args.native_dll.resolve();before=w.native_binaries_state(dll)
    item=w.read_json(Path(__file__).resolve().parents[1] / 'fixtures'/'synthetic-native-fishing.json')
    cases=[]
    for name in ('vanilla', 'generated', 'no_bait', 'dry', 'no_mana', 'cancel', 'switch', 'death', 'bait_debit'):
        s=scene(seed=6 if name=='bait_debit' else 1)
        if name=='no_bait':s['inventory']=[]
        if name=='dry':del s['fishing']['water']
        if name=='no_mana':s['player']['mana']=0
        if name=='cancel':
            s['fishing']['reelOnBite']=False
            s['actions'] += [dict(kind='primary',tick=80),dict(kind='release',tick=81)]
        if name=='death':
            s['ticks']=600;s['fishing']['reelOnBite']=False
            s['actions'].append(dict(kind='hurt_player',tick=80,damage=10000))
        if name=='switch':s['actions'].append(dict(kind='select_slot',tick=80,slot=1))
        cases.append((name,s,name=='vanilla'))
    rows=[]
    for name,s,vanilla in cases:
        directory=out/name;directory.mkdir();(directory/'scenario.json').write_text(json.dumps(s));(directory/'item.json').write_text(json.dumps(item))
        command=[os.environ.get('DOTNET','dotnet'),str(dll)]+(['--vanilla-item','2289'] if vanilla else ['--item',str(directory/'item.json')])+['--scenario',str(directory/'scenario.json'),'--output',str(directory/'native.json')]
        proc=subprocess.run(command,cwd=w.ROOT,capture_output=True,text=True,timeout=180)
        (directory/'process.log').write_text(proc.stdout+proc.stderr)
        trace=w.read_native_json(directory/'native.json') if (directory/'native.json').exists() else {}
        facts=inspect(trace);positive=name in ('vanilla','generated','bait_debit')
        passed=proc.returncode==0 and trace.get('status')=='passed' and bool(facts['caught'])==positive and facts['bite']==positive
        if positive:passed=passed and facts['wet'] and facts['spawned'] and all(i['stack']>0 and i['type'] in facts['nativeCatchIds'] for i in facts['caught'])
        if name in ('cancel','switch','death','no_mana'):passed=passed and not facts['lastBobbers']
        if name in ('cancel','switch','death'):passed=passed and facts['initialBobber'] and facts['bait']==20
        if name in ('no_bait','dry'):passed=passed and facts['spawned']
        if name=='no_bait':passed=passed and facts['wet'] and facts['bait']==0
        if name in ('dry','no_mana'):passed=passed and facts['bait']==20
        if name=='no_mana':passed=passed and not facts['spawned'] and facts['manaDebited']==0
        if name=='dry':passed=passed and not facts['wet']
        if name in ('generated','bait_debit'):passed=passed and facts['manaDebited']==7
        if name=='bait_debit':passed=passed and facts['bait']==19
        if name=='death':passed=passed and any(e.get('kind')=='native_player_hurt' and e.get('dead') for frame in trace.get('snapshots',[]) for e in frame.get('events',[]))
        rows.append(dict(name=name,passed=passed,exit=proc.returncode,status=trace.get('status'),facts=facts));print(name,passed,flush=True)
    summary=dict(passed=all(r['passed'] for r in rows) and before==w.native_binaries_state(dll),checks=rows,binaryUnchanged=before==w.native_binaries_state(dll),scope='Native single-process full Player.Update/ItemCheck/Projectile.Update and inventory catch; static water, bounded negative windows, no multiplayer session or fish-art certification.')
    (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2));return 0 if summary['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
