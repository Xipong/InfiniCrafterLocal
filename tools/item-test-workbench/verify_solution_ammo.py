#!/usr/bin/env python3
"""Native solution admission/payment controls; optional intact authored-item proof."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import workbench as w


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-dll', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--item', type=Path, help='Intact authored solution item; only test world identity changes')
    args = parser.parse_args()
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    dll = args.native_dll.resolve(); binaries = w.native_binaries_state(dll)
    command = [os.environ.get('DOTNET', 'dotnet'), str(dll)]
    subprocess.run(command + ['--write-fixtures', str(out/'fixtures')], cwd=w.ROOT, check=True)
    base = w.read_json(out/'fixtures/synthetic-straight.json')
    base['runtimeProgram']['weaponAmmo'] = dict(ammoCategory='solution',speedBasis='authored_spawn')
    scene = dict(playerUpdate='full',ticks=50,worldId=12,seed=1,
                 player=dict(x=800,y=700,mana=200),dummy=dict(x=1000,y=700,life=10000),
                 tiles=[dict(tileX=1,tileY=47,width=97,height=1)],
                 actions=[dict(tick=0,kind='aim',x=1050,y=720),dict(tick=0,kind='primary'),dict(tick=1,kind='release')])
    checks = []; cases = []
    def add(name,item,ammo,spawns,consumed,remaining=None,expected=0):
        value=copy.deepcopy(item);value.setdefault('recipeMeta',{})['worldId']='12'
        s=copy.deepcopy(scene);s['inventory']=[] if ammo is None else [dict(slot=54,itemId=ammo,stack=3)]
        s['assertions']=[dict(kind='no_nonfinite'),dict(kind='spawn_count',value=spawns),
                         dict(kind='ammo_consumed_count',itemId=ammo or 780,value=consumed),
                         dict(kind='ammo_source_spawn_count',itemId=ammo or 780,value=spawns)]
        if remaining is not None:s['assertions'].append(dict(kind='inventory_stack',slot=54,itemId=ammo,value=remaining))
        cases.append((name,value,s,expected))
    add('solution-native',base,780,1,1,2)
    add('solution-empty',base,None,0,0)
    add('solution-wrong-bullet',base,97,0,0,3)
    bullet=copy.deepcopy(base);bullet['runtimeProgram']['weaponAmmo']['ammoCategory']='bullet'
    add('bullet-control',bullet,97,1,1,2)
    add('solution-false-no-debit',base,780,1,0,2,1)
    # Unsupported inventory remains a refusal, not a silent item substitution.
    add('ordinary-item-refused',base,1,0,0,3,2)
    if args.item:
        raw=args.item.read_bytes(); item=json.loads(raw)
        if item['runtimeProgram'].get('weaponAmmo',{}).get('ammoCategory')!='solution':raise ValueError('authored item must actually require solution')
        binding=next(b for b in item['runtimeProgram']['bindings'] if b['input']=='primary_use')
        root=next(e for e in item['runtimeProgram']['entities'] if e['id']==binding['usePolicy']['action']['targetId'])
        count=root['spawn']['count']
        add('authored-solution',item,780,count,1,2)
        add('authored-no-ammo',item,None,0,0)
        (out/'authored-original.json').write_bytes(raw)
    rows=[]
    for name,item,s,expected in cases:
        directory=out/name;directory.mkdir();(directory/'item.json').write_text(json.dumps(item));(directory/'scenario.json').write_text(json.dumps(s))
        proc=subprocess.run(command+['--item',str(directory/'item.json'),'--scenario',str(directory/'scenario.json'),'--output',str(directory/'native.json')],cwd=w.ROOT,capture_output=True,text=True,timeout=180)
        (directory/'process.log').write_text(proc.stdout+proc.stderr)
        trace=w.read_json(directory/'native.json') if (directory/'native.json').exists() else {}
        passed=proc.returncode==expected and trace.get('status')=={0:'passed',1:'failed',2:'error'}[expected]
        if expected==2:passed=passed and 'inventory entries are admitted' in trace.get('error','')
        rows.append(dict(name=name,passed=passed,exit=proc.returncode,status=trace.get('status')))
        print(name,passed,flush=True)
    unchanged=w.native_binaries_state(dll)==binaries
    authored_unchanged=args.item is None or args.item.read_bytes()==raw
    summary=dict(passed=all(r['passed'] for r in rows) and unchanged and authored_unchanged,checks=rows,binaryUnchanged=unchanged,nativeDllSha256=w.digest(dll),scope='Native Item.SetDefaults/PickAmmo/OnConsumeAmmo and generated root spawn; no provider calls or manual projectile creation.')
    if args.item:
        summary['authoredInput']={'sourceSha256':hashlib.sha256(raw).hexdigest(),'unchanged':authored_unchanged,'testOnlyChange':'recipeMeta.worldId=12'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
    return 0 if summary['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
