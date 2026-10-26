#!/usr/bin/env python3
"""Native lifecycle/resource controls using synthetic definitions, never session assets."""
import argparse
import copy
import json
import hashlib
import os
from pathlib import Path
import subprocess
import workbench as w


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--no-build',action='store_true')
    parser.add_argument('--native-dll',type=Path,help='Explicit prebuilt native executable; does not claim normal build provenance')
    args=parser.parse_args();out=args.out.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit('Use a fresh output directory')
    out.mkdir(parents=True,exist_ok=True)
    if args.native_dll and not args.no_build:raise SystemExit('--native-dll requires --no-build')
    if not args.no_build:w.build()
    dll=(args.native_dll or w.HERE/'bin/Release/net8.0/ItemTestWorkbench.dll').resolve()
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    initial_hash=digest(dll)
    dotnet=os.environ.get('DOTNET','dotnet');fixtures=out/'fixtures'
    observer=subprocess.run([dotnet,str(dll),'--check-assertions'],cwd=w.ROOT,capture_output=True,text=True)
    (out/'assertion-controls.log').write_text(observer.stdout+observer.stderr)
    if observer.returncode:raise SystemExit('Pure observer assertion controls failed')
    subprocess.run([dotnet,str(dll),'--write-fixtures',str(fixtures)],cwd=w.ROOT,check=True)
    original=json.loads((fixtures/'synthetic-straight.json').read_text())
    consuming=copy.deepcopy(original);consuming['gameplay']['maxStack']=9999
    for binding in consuming['runtimeProgram']['bindings']:binding['usePolicy']['stackCost']=1
    (fixtures/'synthetic-consuming.json').write_text(json.dumps(consuming))
    flare=json.loads((fixtures/'synthetic-ammo-bullet-authored_spawn.json').read_text())
    flare['runtimeProgram']['weaponAmmo']['ammoCategory']='flare'
    (fixtures/'synthetic-flare.json').write_text(json.dumps(flare))
    base=dict(playerUpdate='full',ticks=150,seed=1,player=dict(x=800,y=1500,life=100,mana=200,manaCrystals=9),dummy=dict(x=920,y=1500,life=10000),tiles=[dict(tileX=1,tileY=97,width=97,height=1)],actions=[dict(tick=0,kind='primary'),dict(tick=1,kind='release')],assertions=[dict(kind='no_nonfinite')])
    def check(kind,**kw):return dict(kind=kind,**kw)
    def scene(**kw):s=copy.deepcopy(base);s.update(kw);return s
    finite=check('no_nonfinite');inactive=check('all_inactive')
    consumed=scene(itemStack=2,assertions=[finite,inactive,check('entity_spawn_count',entityId='root',value=1),check('generated_stack_at',tick=0,value=1),check('generated_stack_at',tick=149,value=1)])
    depleted=scene(itemStack=1,actions=base['actions']+[dict(tick=60,kind='primary'),dict(tick=61,kind='release')],assertions=[finite,check('entity_spawn_count',entityId='root',value=1),check('generated_stack_at',tick=149,value=0)])
    expiry=scene(ticks=2500,dummy=dict(x=920,y=1900),assertions=[finite,inactive,check('entity_spawn_count',entityId='root',value=1),check('entity_natural_expiry',entityId='root'),check('entity_peak_active_at_most',entityId='root',value=1)])
    ammo=scene(inventory=[dict(slot=54,itemId=931,stack=2)],assertions=[finite,check('spawn_count',value=1),check('inventory_stack',slot=54,itemId=931,value=1),check('ammo_consumed_count',itemId=931,value=1),check('ammo_source_spawn_count',itemId=931,value=1)])
    cases=[('consume','synthetic-consuming.json',consumed,0,[]),('deplete','synthetic-consuming.json',depleted,0,[]),('long-expiry','synthetic-straight.json',expiry,0,[]),('flare','synthetic-flare.json',ammo,0,[]),('flare-empty','synthetic-flare.json',scene(assertions=[finite,check('spawn_count',value=0)]),0,[]),('negative-entity-count','synthetic-consuming.json',scene(itemStack=2,assertions=[check('entity_spawn_count',entityId='root',value=2)]),1,['entity_spawn_count']),('negative-cap','synthetic-straight.json',scene(assertions=[check('entity_peak_active_at_most',entityId='root',value=0)]),1,['entity_peak_active_at_most']),('negative-stack','synthetic-consuming.json',scene(itemStack=2,assertions=[check('generated_stack_at',tick=149,value=2)]),1,['generated_stack_at']),('invalid-entity','synthetic-straight.json',scene(assertions=[check('entity_inactive',entityId='missing')]),2,[]),('invalid-timeline','synthetic-straight.json',scene(ticks=14401),2,[])]
    rows=[]
    for name,item,scenario,expected,failures in cases:
        folder=out/name;folder.mkdir();sp=folder/'scenario.json';sp.write_text(json.dumps(scenario,indent=2));dest=folder/'native.json'
        with (folder/'process.log').open('w') as log:r=subprocess.run([dotnet,str(dll),'--item',str(fixtures/item),'--scenario',str(sp),'--output',str(dest)],cwd=w.ROOT,stdout=log,stderr=log,timeout=180)
        trace=json.loads(dest.read_text()) if dest.exists() else {};actual=[a['name'] for a in trace.get('assertions',[]) if a.get('status')=='failed']
        ok=digest(dll)==initial_hash and r.returncode==expected and trace.get('status')=={0:'passed',1:'failed',2:'error'}[expected] and sorted(actual)==sorted(failures)
        if expected==2:ok=ok and ('existing projectile entityId' if name=='invalid-entity' else 'ticks must be') in trace.get('error','')
        rows.append(dict(name=name,passed=ok,exitCode=r.returncode,status=trace.get('status'),failedAssertions=actual));print(rows[-1],flush=True)
    summary=dict(passed=all(row['passed'] for row in rows),cases=rows,nativeDll=str(dll),nativeDllSha256=initial_hash,scope='Synthetic lifecycle/resource assertions; no whole-item or rendered-visual approval')
    (out/'summary.json').write_text(json.dumps(summary,indent=2));return 0 if summary['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
