#!/usr/bin/env python3
"""Actual authored recall through production TryRecallHome -> native Teleport."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import workbench as w


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-dll',type=Path,required=True)
    parser.add_argument('--item',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    dll=args.native_dll.resolve();binary=w.native_binaries_state(dll);raw=args.item.read_bytes();item=json.loads(raw)
    binding=next(b for b in item['runtimeProgram']['bindings'] if b['input']=='alternate_use')
    if binding['usePolicy']['action']['kind']!='apply_item_effects':raise ValueError('requires authored alternate item effect')
    item['recipeMeta']['worldId']='12';(out/'item.json').write_text(json.dumps(item));(out/'original.json').write_bytes(raw)
    scene=dict(playerUpdate='full',ticks=120,worldId=12,seed=1,player=dict(x=800,y=700,life=100,mana=200),
        dummy=dict(x=1200,y=700,life=10000),tiles=[dict(tileX=1,tileY=47,width=97,height=1)],
        recallSpawn=dict(worldTileX=43,worldTileY=47),actions=[dict(tick=0,kind='alt'),dict(tick=1,kind='release')])
    ready=copy.deepcopy(scene)
    cooldown=copy.deepcopy(scene);cooldown['ticks']=380;cooldown['actions'] += [dict(tick=60,kind='alt'),dict(tick=61,kind='release'),dict(tick=340,kind='alt'),dict(tick=341,kind='release')]
    no_use=copy.deepcopy(scene);no_use['actions']=[]
    missing=copy.deepcopy(scene);missing['recallSpawn']=dict(worldTileX=0,worldTileY=0)
    bed=copy.deepcopy(scene);bed['recallSpawn'].update(playerTileX=53,playerTileY=47)
    bed_only=copy.deepcopy(bed);bed_only['recallSpawn'].update(worldTileX=0,worldTileY=0)
    outside=copy.deepcopy(scene);outside['recallSpawn']['worldTileX']=1000
    unconfigured=copy.deepcopy(scene);del unconfigured['recallSpawn']
    primary=copy.deepcopy(unconfigured);primary['actions'][0]['kind']='primary'
    cases=[('ready',ready,1,0,(43,47)),('cooldown-and-expiry',cooldown,2,0,(43,47)),('no-use',no_use,0,0,None),
        ('missing-spawn',missing,0,0,None),('player-spawn-override',bed,1,0,(53,47)),('player-spawn-without-world-spawn',bed_only,1,0,(53,47)),
        ('out-of-world-refused',outside,0,2,None),('unconfigured-refused',unconfigured,0,2,None),('primary-without-recall-scene',primary,0,0,None)]
    checks=[]
    for name,s,count,expected,coords in cases:
        directory=out/name;directory.mkdir();s['assertions']=[dict(kind='no_nonfinite'),dict(kind='teleport_count',value=count),dict(kind='mana_debited',value=6 if name=='primary-without-recall-scene' else 0)]
        if name=='primary-without-recall-scene':s['assertions'].append(dict(kind='spawn_count',value=1))
        (directory/'scenario.json').write_text(json.dumps(s))
        proc=subprocess.run([os.environ.get('DOTNET','dotnet'),str(dll),'--item',str(out/'item.json'),'--scenario',str(directory/'scenario.json'),'--output',str(directory/'native.json')],cwd=w.ROOT,capture_output=True,text=True,timeout=180)
        (directory/'process.log').write_text(proc.stdout+proc.stderr)
        trace=w.read_json(directory/'native.json') if (directory/'native.json').exists() else {};snapshots=trace.get('snapshots',[])
        events=[e for f in snapshots for e in f.get('events',[]) if e.get('kind')=='native_teleport']
        passed=proc.returncode==expected and trace.get('status')==('passed' if expected==0 else 'error')
        if coords and snapshots:
            player=snapshots[0]['player'];x=coords[0]*16+8-player['width']/2;y=coords[1]*16-player['height']
            passed=passed and len(events)==count and all(e['afterX']==x and e['afterY']==y for e in events)
            passed=passed and snapshots[-1]['player']['x']==x and snapshots[-1]['player']['y']==y
        if expected:passed=passed and ('Recall spawn' in trace.get('error','') or 'recallSpawn' in trace.get('error',''))
        checks.append(dict(name=name,passed=passed,exitCode=proc.returncode,teleports=events));print(name,passed,flush=True)
    unchanged=w.native_binaries_state(dll)==binary and args.item.read_bytes()==raw
    summary=dict(passed=all(c['passed'] for c in checks) and unchanged,checks=checks,inputsAndBinariesUnchanged=unchanged,
        sourceSha256=hashlib.sha256(raw).hexdigest(),nativeDllSha256=w.digest(dll),testOnlyDTOChange='recipeMeta.worldId=12',
        scope='Production TryRecallHome selects explicit world/player spawn coordinates then calls original Player.Teleport. Not Player.Spawn, bed validation, destination safety, multiplayer or complete world parity.')
    (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2));return 0 if summary['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
