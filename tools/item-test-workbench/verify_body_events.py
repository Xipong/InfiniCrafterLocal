#!/usr/bin/env python3
"""Native hybrid item-body callback controls; all inputs are explicit synthetic fixtures."""
import argparse,copy,json,subprocess,sys
from pathlib import Path
import workbench as w


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--no-build',action='store_true');args=p.parse_args()
    out=args.out.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit('Use a fresh evidence directory')
    out.mkdir(parents=True,exist_ok=True)
    if not args.no_build:w.build()
    item=w.read_json(w.HERE/'fixtures/synthetic-body-events.json');base=w.read_json(w.HERE/'scenarios/body-events.json')
    def body(x):return next(e for e in x['runtimeProgram']['entities'] if e['kind']=='item_body')
    def root(x):return next(e for e in x['runtimeProgram']['entities'] if e['id']=='workbench_blade')
    def scenario(spawns=1,hits=1,heal=1,mana=7):
        s=copy.deepcopy(base);s['assertions']=[{'kind':k,'value':v} for k,v in [('spawn_count',spawns),('item_hit_count',hits),('direct_healing',heal),('mana_debited',mana)]]+[{'kind':'no_nonfinite'}];return s
    cases=[('hit',item,scenario(),0),('hit-repeat',item,scenario(),0)]
    s=scenario(hits=0,heal=0);s['dummy']['x']=1300;cases.append(('miss',item,s,0))
    s=scenario(spawns=0,hits=0,heal=0,mana=0);s['player']['mana']=3;cases.append(('insufficient-mana',item,s,0))
    s=scenario(spawns=5,hits=5,heal=5,mana=35);s['actions']=[{'tick':0,'kind':'primary'}];cases.append(('held-cadence',item,s,0))
    a=copy.deepcopy(item);alt=copy.deepcopy(a['runtimeProgram']['bindings'][0]);alt.update(id='alternate_body',input='alternate_use');alt['usePolicy']['contactDamage']=False;a['runtimeProgram']['bindings'].append(alt)
    s=scenario(spawns=0,hits=0,heal=0);s['actions'][0]['kind']='alt';cases.append(('alternate-input-filter',copy.deepcopy(a),s,0))
    body(a)['events'][0]['useInput']='alternate_use';s=scenario(hits=0,heal=0);s['actions'][0]['kind']='alt';cases.append(('alternate-contact-disabled',a,s,0))
    a=copy.deepcopy(item);body(a)['events'][0]['delayTicks']=3;cases.append(('delayed-use',a,scenario(),0))
    a=copy.deepcopy(item);body(a)['events'][1]['event']='on_crit';s=scenario(spawns=5,hits=5,heal=1,mana=35);s['actions']=[{'tick':0,'kind':'primary'}];cases.append(('natural-native-crit',a,s,0))
    a=copy.deepcopy(item);body(a)['events'][1]['maxHeal']=10;s=scenario(heal=1);s['player']['life']=99;cases.append(('native-heal-cap',a,s,0))
    s=scenario(heal=0);s['player']['life']=100;cases.append(('full-health-no-heal-call',item,s,0))
    a=copy.deepcopy(item);body(a)['events'][0]['event']='on_hit';body(a)['events'][0].pop('useInput');cases.append(('on-hit-spawn',a,scenario(),0))
    a=copy.deepcopy(item);a['runtimeProgram']['bindings'][0]['usePolicy']['action']={'kind':'spawn_entity','targetId':'workbench_blade'};a['runtimeProgram']['bindings'][0]['role']='secondary';a['runtimeProgram']['limits']['maxEventSpawnsPerActivation']=2
    root(a)['events']=[{'id':'root_child','action':'spawn_entity_on_event','actionCode':1,'event':'on_hit','entityId':'nail','count':1,'damageMultiplier':.35,'damageBasis':'authored_child','knockbackBasis':'authored_child'}]
    cases.append(('shared-body-root-event-budget',a,scenario(spawns=3),0))
    a=copy.deepcopy(item);body(a)['events'][0]['delayTicks']=30;s=scenario(spawns=2,hits=2,heal=2,mana=14);s['actions']=[{'tick':t,'kind':k} for t,k in [(0,'primary'),(1,'release'),(24,'primary'),(25,'release')]];cases.append(('delayed-across-next-activation',a,s,0))
    s=scenario();s['assertions']=[{'kind':'direct_healing','value':2}];cases.append(('negative-double-heal',item,s,1))
    a=copy.deepcopy(item);body(a)['events'][1]['event']='on_use';cases.append(('refused-heal-on-use',a,scenario(),2))
    a=copy.deepcopy(item);body(a)['events'][0]['event']='periodic';body(a)['events'][0]['periodTicks']=30;cases.append(('refused-periodic',a,scenario(),2))
    s=scenario();s['playerUpdate']='client';cases.append(('pure-client-still-refuses-body-events',item,s,2))
    rows=[];traces={}
    for name,data,s,expected in cases:
        ip=out/(name+'-item.json');ip.write_text(json.dumps(data,indent=2));sp=out/(name+'-scenario.json');sp.write_text(json.dumps(s,indent=2))
        r=subprocess.run([sys.executable,str(w.HERE/'workbench.py'),'run','--item',str(ip),'--scenario',str(sp),'--out',str(out/name),'--no-build'],cwd=w.ROOT,capture_output=True,text=True,timeout=240)
        tp=out/name/'native.json';t=w.read_json(tp) if tp.exists() else {};traces[name]=t
        ok=r.returncode==expected and t.get('status')=={0:'passed',1:'failed',2:'error'}[expected]
        rows.append({'name':name,'passed':ok,'expectedExitCode':expected,'actualExitCode':r.returncode,'nativeStatus':t.get('status'),'trace':str(tp),'runnerStdout':r.stdout,'runnerStderr':r.stderr});print(name+': '+('PASS' if ok else 'FAIL'),flush=True)
    def events(name,kind=None):return [(s['tick'],i,e) for s in traces[name].get('snapshots',[]) for i,e in enumerate(s.get('events',[])) if kind is None or e.get('kind')==kind]
    def check(name,value):rows.append({'name':name,'passed':bool(value)})
    check('same-seed-exact-repeat',bool(traces['hit'].get('snapshots')) and traces['hit'].get('snapshots')==traces['hit-repeat'].get('snapshots'))
    dispatch=[(t,e) for t,_,e in events('held-cadence','item_event_dispatch') if e['event']=='on_use']
    check('on-use-once-per-native-activation',[t for t,e in dispatch]==[0,24,48,72,96])
    check('mana-rejection-no-body-dispatch',not events('insufficient-mana','item_event_dispatch'))
    check('miss-only-on-use-dispatch',[e['event'] for _,_,e in events('miss','item_event_dispatch')]==['on_use'])
    crits=[t for t,_,e in events('natural-native-crit','item_hit') if e.get('crit') is True]
    check('crit-dispatch-and-heal-follow-actual-native-critical-hit',bool(crits) and crits==[t for t,_,e in events('natural-native-crit','item_event_dispatch') if e['event']=='on_crit']==[t for t,_,e in events('natural-native-crit','native_heal')])
    heals=[e for _,_,e in events('native-heal-cap','native_heal')]
    check('native-heal-request-vs-clamped-gain',len(heals)==1 and heals[0]['requested']==10 and heals[0]['before']==99 and heals[0]['after']==100 and heals[0]['gained']==1)
    check('delayed-use-tick',[t for t,_,e in events('delayed-use','spawn')]==[3])
    immediate=[e for _,_,e in events('hit','spawn')];delayed=[e for _,_,e in events('delayed-use','spawn')]
    check('native-immediate-item-source-reference',len(immediate)==1 and immediate[0].get('sourceItemIsLiveInventoryReference') is True and immediate[0].get('sourceItemDataId')==item['id'])
    check('native-delayed-cloned-item-source',len(delayed)==1 and delayed[0].get('sourceItemIsLiveInventoryReference') is False and delayed[0].get('sourceItemDataId')==item['id'] and delayed[0].get('sourceItemStack')==1)
    check('delayed-item-source-survives-next-activation',[t for t,_,e in events('delayed-across-next-activation','spawn')]==[30,54])
    configs=[e for _,_,e in events('shared-body-root-event-budget','entity_configured')]
    check('root-not-charged-as-event-child-budget',len(configs)==3 and sum(e['entityId']=='workbench_blade' for e in configs)==1 and sum(e['entityId']=='nail' for e in configs)==2)
    for name,t in traces.items():
        if not t.get('snapshots'):continue
        f=t['snapshots'];hits=[e for _,_,e in events(name) if e['kind'] in ('item_hit','hit')]
        check(name+'-native-damage-reconciliation',sum(e['damageDone'] for e in hits)==f[0]['dummy']['life']-f[-1]['dummy']['life'])
    summary={'passed':all(r['passed'] for r in rows),'fullGameParity':False,'scope':'Native body OnUse/OnHit/OnCrit spawn/heal callbacks in bounded hybrid mode; synthetic fixtures, not captured generation; no global VFX/world/MP','checks':rows}
    (out/'summary.json').write_text(json.dumps(summary,indent=2));return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
