#!/usr/bin/env python3
"""Native placement/mining and fail-closed controls. Synthetic inputs only."""
import argparse
import copy
import json
import os
import hashlib
import subprocess
import sys
from pathlib import Path
import workbench as w


def cases(fixtures):
    place=w.read_json(w.HERE/'scenarios/world-placement.json')
    mine=w.read_json(w.HERE/'scenarios/world-mining.json')
    yield 'placement-return', fixtures/'synthetic-world-campfire.json',place,0,None
    miss=copy.deepcopy(place)
    miss['actions']=[a for a in miss['actions'] if a['kind'] not in ('primary','break_tile')]
    miss['assertions']=[{'kind':'placement_groups_at','tick':99,'value':0},{'kind':'generated_world_items_at','tick':99,'value':0},{'kind':'no_nonfinite'}]
    yield 'placement-no-use',fixtures/'synthetic-world-campfire.json',miss,0,None
    unsupported=copy.deepcopy(place)
    unsupported['actions']=[{'tick':0,'kind':'tile_target','tileX':54,'tileY':43},{'tick':0,'kind':'primary'},{'tick':1,'kind':'release'}]
    unsupported['assertions']=[{'kind':'placement_groups_at','tick':99,'value':0},{'kind':'generated_world_items_at','tick':99,'value':0},{'kind':'generated_stack_at','tick':99,'value':1}]
    yield 'placement-missing-support',fixtures/'synthetic-world-campfire.json',unsupported,0,None
    wrong=copy.deepcopy(place);wrong['assertions']=[{'kind':'generated_world_items_at','tick':99,'value':2}]
    yield 'negative-duplicate-return',fixtures/'synthetic-world-campfire.json',wrong,1,['generated_world_items_at']
    yield 'native-mining',fixtures/'synthetic-world-mining.json',mine,0,None
    no_use=copy.deepcopy(mine);no_use['actions']=[a for a in no_use['actions'] if a['kind']!='primary'];no_use['assertions']=[{'kind':'tile_at','tick':99,'tileX':54,'tileY':46,'hasTile':True,'tileId':0}]
    yield 'no-use-no-mining',fixtures/'synthetic-world-mining.json',no_use,0,None
    wrong_target=copy.deepcopy(mine);wrong_target['actions'][0].update(tileX=60,tileY=44)
    wrong_target['assertions']=[{'kind':'tile_at','tick':99,'tileX':54,'tileY':46,'hasTile':True,'tileId':0}]
    yield 'wrong-target-no-mining',fixtures/'synthetic-world-mining.json',wrong_target,0,None
    invalid=copy.deepcopy(mine);invalid['actions'][0]['tileX']=99
    yield 'refused-outside-target',fixtures/'synthetic-world-mining.json',invalid,2,None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--no-build',action='store_true')
    parser.add_argument('--native-dll',type=Path,help='Explicit direct native binary; no wrapper/build-provenance claim')
    args=parser.parse_args();out=args.out.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit('Use a fresh evidence directory')
    out.mkdir(parents=True,exist_ok=True)
    if args.native_dll and not args.no_build:raise SystemExit('--native-dll requires --no-build')
    if not args.no_build:w.build()
    dll=args.native_dll.resolve() if args.native_dll else None
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    initial_hash=digest(dll) if dll else None
    fixtures=out/'fixtures'
    if dll:subprocess.run([os.environ.get('DOTNET','dotnet'),str(dll),'--write-fixtures',str(fixtures)],cwd=w.ROOT,check=True)
    else:w.fixtures(fixtures,no_build=True)
    rows=[]
    for name,item,scenario,exit_code,failures in cases(fixtures):
        scenario_path=out/(name+'.json');scenario_path.write_text(json.dumps(scenario,indent=2))
        command=([os.environ.get('DOTNET','dotnet'),str(dll),'--item',str(item),'--scenario',str(scenario_path),'--output',str(out/name/'native.json')] if dll else [sys.executable,str(w.HERE/'workbench.py'),'run','--item',str(item),'--scenario',str(scenario_path),'--out',str(out/name),'--review','none','--no-build'])
        result=subprocess.run(command,cwd=w.ROOT,capture_output=True,text=True,timeout=180)
        path=out/name/'native.json';trace=w.read_json(path) if path.exists() else {}
        failed=[a['name'] for a in trace.get('assertions',[]) if a['status']=='failed']
        passed=(dll is None or digest(dll)==initial_hash) and result.returncode==exit_code and trace.get('status')=={0:'passed',1:'failed',2:'error'}[exit_code]
        if failures is not None:passed=passed and sorted(failed)==sorted(failures)
        if name=='refused-outside-target':passed=passed and 'World target must be inside initialized tilemap margin' in trace.get('error','')
        rows.append({'name':name,'passed':passed,'expectedExitCode':exit_code,'actualExitCode':result.returncode,'nativeStatus':trace.get('status'),'trace':str(path),'stdout':result.stdout,'stderr':result.stderr})
        print(name+': '+('PASS' if passed else 'FAIL'),flush=True)
    (out/'summary.json').write_text(json.dumps({'passed':all(r['passed'] for r in rows),'cases':rows,'nativeDllSha256':initial_hash,'executionScope':'Direct native only; normal wrapper/build provenance not tested' if dll else 'Standard workbench wrapper'},indent=2))
    return 0 if all(r['passed'] for r in rows) else 1

if __name__=='__main__':raise SystemExit(main())
