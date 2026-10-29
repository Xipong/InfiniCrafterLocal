#!/usr/bin/env python3
"""Bounded no-VFX client hybrid matrix; real native use/contact/projectiles/scheduler."""
import argparse,copy,json,subprocess,sys
from pathlib import Path
import workbench as w


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--no-build',action='store_true');args=parser.parse_args()
    out=args.out.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit('Use a fresh evidence directory')
    out.mkdir(parents=True,exist_ok=True)
    if not args.no_build:w.build()
    item=w.read_json(w.HERE/'fixtures/synthetic-client-hybrid.json')
    base={'playerUpdate':'client_hybrid','ticks':160,'seed':1,'player':{'x':800,'y':700,'life':100,'maxLife':100,'mana':200},'dummy':{'x':828,'y':700,'life':10000,'noTileCollide':False},'tiles':[{'tileX':1,'tileY':47,'width':97,'height':1}],'actions':[{'tick':0,'kind':'primary'},{'tick':1,'kind':'release'}]}
    def root(data):return next(e for e in data['runtimeProgram']['entities'] if e['id']=='workbench_blade')
    def scenario(items=1,projectiles=12,spawns=11,mana=7,inactive=True):
        s=copy.deepcopy(base);s['assertions']=[{'kind':'item_hit_count','value':items},{'kind':'projectile_hit_count','value':projectiles},{'kind':'spawn_count','value':spawns},{'kind':'mana_debited','value':mana},{'kind':'no_nonfinite'}]
        if inactive:s['assertions'].append({'kind':'all_inactive'})
        return s
    cases=[('contrasting',item,scenario(),0),('contrasting-repeat',item,scenario(),0)]
    off=copy.deepcopy(item);off['runtimeProgram']['bindings'][0]['usePolicy']['contactDamage']=False
    cases.append(('contact-disabled',off,scenario(items=0),0))
    offroot=copy.deepcopy(item);root(offroot)['damage']['enabled']=False;root(offroot)['events']=[]
    cases.append(('root-damage-disabled',offroot,scenario(projectiles=0,spawns=1),0))
    body=copy.deepcopy(item);body['runtimeProgram']['bindings'][0].update(role='primary');body['runtimeProgram']['bindings'][0]['usePolicy']['action']={'kind':'use_item_body','targetId':'item'};body['runtimeProgram']['primaryEntityId']='item';body['runtimeProgram']['primaryOwner']='item_body'
    cases.append(('body-only',body,scenario(projectiles=0,spawns=0),0))
    poor=scenario(items=0,projectiles=0,spawns=0,mana=0);poor['player']['mana']=6;cases.append(('insufficient-mana',item,poor,0))
    miss=scenario(items=0,projectiles=0,spawns=1);miss['dummy'].update(x=1200,y=900);cases.append(('miss',item,miss,0))
    owner=copy.deepcopy(item)
    root(owner)['collision']['npcImmunityMode']='owner'
    cases.append(('root-owner-immunity',owner,scenario(projectiles=2),0))
    delayed=copy.deepcopy(item);root(delayed)['events'][0]['delayTicks']=3;cases.append(('delayed3',delayed,scenario(),0))
    reuse=copy.deepcopy(item);root(reuse)['events'][0]['delayTicks']=60
    twice=scenario(items=2,projectiles=9,spawns=7,mana=14);twice['ticks']=180;twice['actions']=[{'tick':t,'kind':kind} for t,kind in [(0,'primary'),(1,'release'),(50,'primary'),(51,'release')]]
    cases.append(('delayed-source-reuse',reuse,twice,0))
    held=scenario(items=5,projectiles=60,spawns=55,mana=35,inactive=False);held['ticks']=120;held['actions']=[{'tick':0,'kind':'primary'}];cases.append(('held-cadence',item,held,0))
    alternate=copy.deepcopy(item);alternate['runtimeProgram']['bindings'][0]['input']='alternate_use';alt=scenario();alt['actions'][0]['kind']='alt';cases.append(('alternate',alternate,alt,0))
    wrong=scenario();wrong['assertions']=[{'kind':'mana_debited','value':14}];cases.append(('negative-double-payment',item,wrong,1))
    wronghit=scenario();wronghit['assertions']=[{'kind':'projectile_hit_count','value':0}];cases.append(('negative-zero-projectile-hit',item,wronghit,1))
    wrongcontact=scenario(items=0);wrongcontact['assertions']=[{'kind':'item_hit_count','value':1}];cases.append(('negative-disabled-contact-hit',off,wrongcontact,1))
    unsupported=copy.deepcopy(item);unsupported['vfxManifest']=w.read_json(w.HERE/'fixtures/synthetic-client-contact.json')['vfxManifest'];cases.append(('refused-vfx',unsupported,scenario(),2))
    invalid=copy.deepcopy(item);root(invalid)['damage']['enabled']=False;cases.append(('refused-invalid-hit-producer',invalid,scenario(),2))
    original=w.ROOT/'tools/fixtures/docx-image-ready-delivered.json';orig=scenario(items=0,mana=0);orig['ticks']=180;orig['dummy']['x']=850;cases.append(('unchanged-offline-delivery-fixture',original,orig,0))
    rows=[];traces={}
    for name,data,s,expected in cases:
        ip=data if isinstance(data,Path) else out/(name+'-item.json')
        if not isinstance(data,Path):ip.write_text(json.dumps(data,ensure_ascii=False,indent=2))
        sp=out/(name+'-scenario.json');sp.write_text(json.dumps(s,indent=2))
        p=subprocess.run([sys.executable,str(w.HERE/'workbench.py'),'run','--item',str(ip),'--scenario',str(sp),'--out',str(out/name),'--no-build'],cwd=w.ROOT,capture_output=True,text=True,timeout=240)
        tp=out/name/'native.json';trace=w.read_json(tp) if tp.exists() else {};traces[name]=trace
        ok=p.returncode==expected and trace.get('status')=={0:'passed',1:'failed',2:'error'}[expected]
        if expected!=2:ok=ok and trace.get('execution',{}).get('clientGraphics',{}).get('phaseFlags',{}).get('Projectile.Update.dedServ') is False
        rows.append({'name':name,'passed':ok,'expectedExitCode':expected,'actualExitCode':p.returncode,'nativeStatus':trace.get('status'),'inputProvenance':'unchanged offline repository fixture, not authentic capture' if isinstance(data,Path) else 'explicit synthetic/test fixture','trace':str(tp),'runnerStdout':p.stdout,'runnerStderr':p.stderr});print(name+': '+('PASS' if ok else 'FAIL'),flush=True)
    def events(name):return [(s['tick'],i,e) for s in traces[name].get('snapshots',[]) for i,e in enumerate(s.get('events',[]))]
    main=traces['contrasting'];repeat=traces['contrasting-repeat']
    rows.append({'name':'same-seed-exact-hybrid-repeat','passed':bool(main.get('snapshots')) and main.get('snapshots')==repeat.get('snapshots') and main.get('assertions')==repeat.get('assertions')})
    configs=[e for _,_,e in events('contrasting') if e['kind']=='entity_configured'];queries=[e for _,_,e in events('contrasting') if e['kind']=='item_contact_query']
    rows.append({'name':'distinct-body-root-child-canonical-budgets','passed':bool(configs and queries) and all(e['damage']==17 for e in queries) and all((e['damage'],e['knockback'])==((43,6) if e['entityId']=='workbench_blade' else (4,4)) for e in configs)})
    for name,trace in traces.items():
        if not trace.get('snapshots'):continue
        hits=[e for _,_,e in events(name) if e['kind'] in ['hit','item_hit']];frames=trace['snapshots']
        rows.append({'name':name+'-native-damage-reconciliation-and-no-active-dust','passed':sum(e['damageDone'] for e in hits)==frames[0]['dummy']['life']-frames[-1]['dummy']['life'] and all(s.get('nativeActiveDust',-1)==0 for s in frames)})
    roots=[(tick,index,e) for tick,index,e in events('contrasting') if e['kind']=='hit' and e.get('childDepth')==0]
    children=[(tick,index,e) for tick,index,e in events('contrasting') if e['kind']=='spawn' and e.get('parentProjectileId') is not None]
    rows.append({'name':'native-hit-before-child-allocation-lineage','passed':bool(roots and children) and all(any(t==tick and i<index and h['projectileId']==e['parentProjectileId'] for t,i,h in roots) for tick,index,e in children)})
    delayed_spawns=[(tick,e) for tick,_,e in events('delayed3') if e['kind']=='spawn' and e.get('parentProjectileId') is not None]
    rows.append({'name':'native-delayed-child-ticks','passed':[t for t,e in delayed_spawns]==[3]*5+[18]*5 and all(e['parentProjectileId']==0 for t,e in delayed_spawns)})
    reused=[(tick,e) for tick,_,e in events('delayed-source-reuse') if e['kind']=='spawn' and e.get('parentProjectileId') is not None]
    rows.append({'name':'native-stale-source-cancellation-and-surviving-lineage','passed':len(reused)==5 and all(t==110 and e['parentProjectileId']==1 for t,e in reused)})
    summary={'passed':all(r['passed'] for r in rows),'fullGameParity':False,'scope':'Actual client item/projectile/delayed phases with controlled dedicated dummy; empty authored VFX and measured zero active native dust; not full world/render/MP parity','checks':rows}
    (out/'summary.json').write_text(json.dumps(summary,indent=2));return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
