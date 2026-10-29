#!/usr/bin/env python3
"""Unchanged captured honey primary, explicit world identity, unconfigured alternate refused."""
import argparse,copy,json,subprocess,sys
from pathlib import Path
import workbench as w


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--no-build',action='store_true');args=p.parse_args();out=args.out.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit('Use a fresh evidence directory')
    out.mkdir(parents=True,exist_ok=True)
    if not args.no_build:w.build()
    original=w.ROOT/'tools/fixtures/video-ui-buffs/g_89cda498eb1f9925.json';base=w.read_json(w.HERE/'scenarios/full-honey-primary.json')
    short=copy.deepcopy(base);short['ticks']=120;short['actions']=short['actions'][:4];short['assertions']=[a for a in short['assertions'] if a.get('tick',0)<120]
    cases=[('captured-recovery',original,base,0),('captured-primary',original,short,0),('captured-primary-repeat',original,short,0)]
    wrong=copy.deepcopy(short);wrong['worldId']=0;wrong['assertions']=[a for a in wrong['assertions'] if a['kind'] not in ('generated_buff_seen','player_stat_at')]+[{'kind':'player_stat_never_above','stat':'generatedBuffTicks','value':0}];cases.append(('wrong-world-native-refusal',original,wrong,0))
    idle=copy.deepcopy(short);idle['actions']=[];idle['assertions']=[a for a in wrong['assertions']];cases.append(('idle-no-effects',original,idle,0))
    never=copy.deepcopy(wrong);never['assertions']=[{'kind':'generated_buff_expired'}];cases.append(('negative-never-applied-is-not-expired',original,never,1))
    alt=copy.deepcopy(short);alt['actions']=[{'tick':0,'kind':'alt'}];cases.append(('unsupported-alternate-before-mutation',original,alt,2))
    late=copy.deepcopy(short);late['actions']=[{'tick':0,'kind':'primary'},{'tick':1,'kind':'release'},{'tick':90,'kind':'alt'}];cases.append(('unsupported-late-alternate-preflight',original,late,2))
    diagnostic=w.read_json(original);diagnostic['runtimeProgram']['bindings']=[b for b in diagnostic['runtimeProgram']['bindings'] if b['input']=='primary_use'];cases.append(('diagnostic-alternate-removed',diagnostic,short,0))
    bad=copy.deepcopy(short);bad['assertions']=[{'kind':'generated_buff_expired'}];cases.append(('negative-premature-expiry',original,bad,1))
    too=copy.deepcopy(short);too['ticks']=14401;cases.append(('bounded-tick-cap',original,too,2))
    malformed=copy.deepcopy(short);malformed['worldId']='853355558';cases.append(('world-id-must-be-integer',original,malformed,2))
    rows=[];traces={}
    for name,data,s,expected in cases:
        ip=data if isinstance(data,Path) else out/(name+'-item.json')
        if not isinstance(data,Path):ip.write_text(json.dumps(data,indent=2))
        sp=out/(name+'-scenario.json');sp.write_text(json.dumps(s,indent=2))
        r=subprocess.run([sys.executable,str(w.HERE/'workbench.py'),'run','--item',str(ip),'--scenario',str(sp),'--out',str(out/name),'--no-build'],cwd=w.ROOT,capture_output=True,text=True,timeout=240)
        tp=out/name/'native.json';t=w.read_json(tp) if tp.exists() else {};traces[name]=t
        ok=r.returncode==expected and t.get('status')=={0:'passed',1:'failed',2:'error'}[expected]
        rows.append({'name':name,'passed':ok,'expectedExitCode':expected,'actualExitCode':r.returncode,'nativeStatus':t.get('status'),'inputProvenance':'unchanged captured JSON' if isinstance(data,Path) else 'diagnostic derivative; alternate binding removed, not captured original','trace':str(tp),'runnerStdout':r.stdout,'runnerStderr':r.stderr});print(name+': '+('PASS' if ok else 'FAIL'),flush=True)
    def check(name,value):rows.append({'name':name,'passed':bool(value)})
    def frames(name):return [s for s in traces[name].get('snapshots',[]) if s.get('phase')!='after_input_before_update']
    def frame(name,tick):return next(s for s in frames(name) if s['tick']==tick)
    def events(name,kind):return [(s['tick'],e) for s in traces[name].get('snapshots',[]) for e in s.get('events',[]) if e.get('kind')==kind]
    check('same-seed-exact-primary-repeat',bool(traces['captured-primary'].get('snapshots')) and traces['captured-primary'].get('snapshots')==traces['captured-primary-repeat'].get('snapshots'))
    for name,data,s,expected in cases:
        if isinstance(data,Path) and (out/name/'run.json').exists():
            receipt=w.read_json(out/name/'run.json');check(name+'-unchanged-captured-input',w.digest(original)==w.digest(out/name/'item.json')==receipt.get('itemSha256'))
    recovery=traces['captured-recovery']
    if recovery.get('snapshots'):
        selected={t:frame('captured-recovery',t)['player'] for t in (0,1,60,599,600,601,1799,1800,1801,1849)}
        check('native-buff-expiry-and-reapply',[selected[t]['generatedBuffTicks'] for t in (0,60,599,600,601,1801,1849)]==[600,540,1,0,0,600,552])
        def fatigue(t):return max([e['remainingTicks'] for e in selected[t]['generatedItemExhaustion']]+[0])
        check('canonical-exhaustion-clock-and-recovery',[fatigue(t) for t in (0,60,601,1799,1800,1801)]==[1800,1740,1199,1,0,1800])
        check('native-stat-update-lifetime-preserved',selected[0]['moveSpeed']==1 and abs(selected[1]['moveSpeed']-1.1)<1e-6 and abs(selected[600]['moveSpeed']-1.1)<1e-6 and selected[601]['moveSpeed']==1)
        check('retry-use-runs-without-refreshing-exhausted-effect',[t for t,e in events('captured-recovery','item_event_dispatch') if e['event']=='on_use']==[0,60,601,1801])
    else:check('native-recovery-trace-present',False)
    for name in ('captured-primary','captured-recovery','wrong-world-native-refusal','idle-no-effects'):
        t=traces[name];f=frames(name);coverage=t.get('coverage',{})
        check(name+'-no-inactive-placement-projection',bool(f) and all(s['player']['itemProjection']['createTile']==-1 and s['player']['itemProjection']['createWall']==-1 and s['player']['itemProjection']['consumable'] is False and s['player']['itemProjection']['stack']==1 for s in f))
        check(name+'-alternate-explicitly-untested-not-whole-item-pass',coverage.get('wholeItemValidated') is False and any(b.get('input')=='alternate_use' and b.get('action')=='place_item' and b.get('status')=='untested' for b in coverage.get('untestedBindings',[])))
    wrong=frames('wrong-world-native-refusal');check('wrong-world-use-but-no-generated-effect',bool(wrong) and traces['wrong-world-native-refusal'].get('scene',{}).get('currentWorldSource') is False and all(s['player']['generatedBuffTicks']==0 and not s['player']['generatedItemExhaustion'] for s in wrong) and len(events('wrong-world-native-refusal','item_event_dispatch'))==2)
    check('matched-world-recorded',recovery.get('scene',{}).get('worldId')==853355558 and recovery.get('scene',{}).get('sourceWorldId')=='853355558' and recovery.get('scene',{}).get('currentWorldSource') is True)
    for name in ('unsupported-alternate-before-mutation','unsupported-late-alternate-preflight'):
        check(name+'-zero-scene-snapshots',traces[name].get('status')=='error' and not traces[name].get('snapshots'))
    def mechanics(name):
        f=copy.deepcopy(traces[name].get('snapshots',[]))
        for s in f:
            for e in s['player'].get('generatedItemExhaustion',[]):e.pop('definitionIdentity',None)
        return f
    check('unused-alternate-does-not-change-primary-native-mechanics',bool(mechanics('captured-primary')) and mechanics('captured-primary')==mechanics('diagnostic-alternate-removed'))
    summary={'passed':all(r['passed'] for r in rows),'fullGameParity':False,'scope':'Unchanged captured primary in explicit matching world; unconfigured placement alternate preflight refused; canonical ModPlayer generated utility buffs/exhaustion, no placement or sound rendering','checks':rows}
    (out/'summary.json').write_text(json.dumps(summary,indent=2));return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
