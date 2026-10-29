#!/usr/bin/env python3
"""Optional genuine client-item calculation matrix. Requires real SDL offscreen/FNA; no fallback."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import workbench as w


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--no-build',action='store_true');args=parser.parse_args()
    out=args.out.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit('Use a fresh evidence directory')
    out.mkdir(parents=True,exist_ok=True)
    if not args.no_build:w.build()
    fixture=w.read_json(w.HERE/'fixtures/synthetic-client-contact.json')
    base=w.read_json(w.HERE/'scenarios/client-contact.json')
    nohit=[{'kind':'item_hit_count','value':0},{'kind':'dummy_undamaged'},{'kind':'spawn_count','value':0},{'kind':'no_nonfinite'}]
    cases=[('primary-right',fixture,base,0)]
    left=copy.deepcopy(base);left['player']['direction']=-1;left['dummy']['x']=764
    cases.append(('primary-left',fixture,left,0))
    alternate=copy.deepcopy(fixture);alternate['id']='workbench-synthetic-client-alternate';alternate['runtimeProgram']['bindings'][0]['input']='alternate_use'
    alt=copy.deepcopy(base);alt['actions'][0]['kind']='alt';cases.append(('alternate',alternate,alt,0))
    miss=copy.deepcopy(base);miss['dummy']['x']=1100;miss['assertions']=nohit+[{'kind':'item_contact_observed'}];cases.append(('miss',fixture,miss,0))
    disabled=copy.deepcopy(fixture);disabled['id']='workbench-synthetic-client-disabled';disabled['runtimeProgram']['bindings'][0]['usePolicy']['contactDamage']=False
    off=copy.deepcopy(base);off['assertions']=nohit+[{'kind':'no_item_contact'}];cases.append(('disabled-contact',disabled,off,0))
    scaled=copy.deepcopy(fixture);scaled['id']='workbench-synthetic-client-scaled';scaled['runtimeProgram']['itemContact']={'hitboxScale':1.5,'contactForgivenessPx':6}
    cases.append(('scaled',scaled,base,0))
    negative=copy.deepcopy(base);negative['assertions']=[{'kind':'item_hit_count','value':0}];cases.append(('negative-hit-expectation',fixture,negative,1))
    cases.append(('primary-repeat',fixture,base,0))
    wide=copy.deepcopy(fixture);wide['id']='workbench-synthetic-client-wall';wide['gameplay']['itemScale']=2
    wall=copy.deepcopy(base);wall['dummy'].update(x=850,y=680,noTileCollide=False);wall['tiles'].append({'tileX':52,'tileY':40,'width':1,'height':7});wall['assertions']=nohit+[{'kind':'item_contact_observed'}]
    cases.append(('wall-blocks-physical-target',wide,wall,0))
    ghost=copy.deepcopy(wall);ghost['dummy']['noTileCollide']=True;ghost['assertions']=copy.deepcopy(base['assertions']);cases.append(('wall-allows-noTileCollide-target',wide,ghost,0))
    clear=copy.deepcopy(wall);clear['tiles']=copy.deepcopy(base['tiles']);clear['assertions']=copy.deepcopy(base['assertions']);cases.append(('physical-target-without-wall',wide,clear,0))
    badflag=copy.deepcopy(wall);badflag['dummy']['noTileCollide']='false';cases.append(('negative-malformed-collision-flag',wide,badflag,2))
    held=copy.deepcopy(base);held['ticks']=120;held['actions']=[{'tick':0,'kind':'primary'}]
    for check in held['assertions']:
        if check['kind']=='item_hit_count':check['value']=5
    cases.append(('held-contact-cadence',fixture,held,0))
    rows=[];traces={}
    for name,item,scenario,expected in cases:
        ip=out/(name+'-item.json');ip.write_text(json.dumps(item,indent=2))
        sp=out/(name+'-scenario.json');sp.write_text(json.dumps(scenario,indent=2))
        proc=subprocess.run([sys.executable,str(w.HERE/'workbench.py'),'run','--item',str(ip),'--scenario',str(sp),'--out',str(out/name),'--no-build'],cwd=w.ROOT,capture_output=True,text=True,timeout=240)
        p=out/name/'native.json';trace=w.read_json(p) if p.exists() else {};traces[name]=trace
        passed=proc.returncode==expected and trace.get('status')=={0:'passed',1:'failed',2:'error'}[expected]
        passed=passed and (expected==2 or trace.get('execution',{}).get('clientGraphics',{}).get('nativeClientBranch') is True)
        rows.append({'name':name,'passed':passed,'expectedExitCode':expected,'actualExitCode':proc.returncode,'nativeStatus':trace.get('status'),'trace':str(p),'runnerStdout':proc.stdout,'runnerStderr':proc.stderr})
        print(name+': '+('PASS' if passed else 'FAIL'),flush=True)
    first=traces['primary-right'];repeat=traces['primary-repeat']
    rows.append({'name':'native-client-exact-repeat','passed':bool(first.get('snapshots')) and first.get('snapshots')==repeat.get('snapshots') and first.get('assertions')==repeat.get('assertions')})
    scaled_events=[e for s in traces['scaled'].get('snapshots',[]) for e in s.get('events',[]) if e.get('kind')=='item_contact_geometry' and not e.get('noHitbox')]
    rows.append({'name':'actual-native-rectangle-then-production-contact-scale','passed':bool(scaled_events) and all(e['final']['width']==round(e['native']['width']*1.5)+12 and e['final']['height']==round(e['native']['height']*1.5)+12 for e in scaled_events)})
    snapshots=first.get('snapshots',[]);queries=[(s,e) for s in snapshots for e in s.get('events',[]) if e.get('kind')=='item_contact_query']
    rows.append({'name':'queries-only-during-native-animation','passed':bool(queries) and all(e['itemAnimation']>0 for s,e in queries) and snapshots[-1]['player']['itemPose']['itemAnimation']==0})
    hit_ticks=[s['tick'] for s in traces['held-contact-cadence'].get('snapshots',[]) for e in s.get('events',[]) if e.get('kind')=='item_hit']
    rows.append({'name':'held-contact-native-cadence','passed':hit_ticks==[0,24,48,72,96],'observedHitTicks':hit_ticks})
    summary={'passed':all(r['passed'] for r in rows),'fullGameParity':False,'scope':'Original native client Player.Update/item contact; dedicated TargetDummy phase; real FNA proxy texture. Not full-client rendering or arbitrary projectile/NPC parity.','checks':rows}
    (out/'summary.json').write_text(json.dumps(summary,indent=2));return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
