#!/usr/bin/env python3
"""Controlled native hit callbacks: real AddBuff expiry and NPC pull, not synthetic hits."""
import argparse,copy,json,subprocess,sys
from pathlib import Path
import workbench as w


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--no-build',action='store_true');args=p.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    if not args.no_build:w.build()
    dll=w.HERE/'bin/Release/net8.0/ItemTestWorkbench.dll';binary=w.digest(dll)
    original=w.read_json(w.HERE/'fixtures/synthetic-client-hybrid.json')
    # Explicit current-contract synthetic counterpart; immutable repository fixture stays intact.
    original['runtimeProgram']['itemUse'].pop('releaseTiming',None)
    original.get('gameplay',{}).pop('releaseTiming',None)
    for entity in original['runtimeProgram']['entities']:entity['events']=[]
    base={'playerUpdate':'client_hybrid','ticks':90,'seed':1,'player':{'x':800,'y':700,'life':100,'maxLife':100,'mana':200},'dummy':{'nativeType':'zombie','x':828,'y':700,'life':10000,'noTileCollide':False},'tiles':[{'tileX':1,'tileY':47,'width':97,'height':1}],'actions':[{'tick':0,'kind':'primary'},{'tick':1,'kind':'release'}],'assertions':[{'kind':'no_nonfinite'}]}
    def item(action,body=False):
        d=copy.deepcopy(original);e=next(e for e in d['runtimeProgram']['entities'] if e['id']==('item' if body else 'workbench_blade'));e['events']=[action] if action else []
        return d
    status=lambda buff:{'id':'native_status','action':'apply_status_on_event','actionCode':2,'event':'on_hit','buffId':buff,'durationTicks':30}
    pull={'id':'native_pull','action':'pull_on_event','actionCode':5,'event':'on_hit','mode':'target_to_owner','strength':1.3333333333333333,'radiusTiles':7}
    cases=[]
    for buff in (153,70,69):cases.append((f'status-{buff}',item(status(buff)),copy.deepcopy(base),0))
    cases.append(('status-body',item(status(153),True),copy.deepcopy(base),0))
    cases.append(('no-callback',item(None),copy.deepcopy(base),0))
    miss=copy.deepcopy(base);miss['dummy']['x']=1300;cases.append(('status-miss',item(status(153)),miss,0))
    resist=copy.deepcopy(base);resist['dummy']['knockBackResist']=1
    cases += [('pull',item(pull),copy.deepcopy(resist),0),('pull-body',item(pull,True),copy.deepcopy(resist),0),('same-resist-no-callback',item(None),copy.deepcopy(resist),0),('pull-immune',item(pull),copy.deepcopy(base),0)]
    miss=copy.deepcopy(resist);miss['dummy']['x']=1300;cases.append(('pull-miss',item(pull),miss,0))
    bad=copy.deepcopy(resist);bad['dummy']['knockBackResist']=1.1;cases.append(('refused-resist-out-of-range',item(pull),bad,2))
    unsupported=copy.deepcopy(pull);unsupported['event']='on_expire';cases.append(('refused-unproven-expire-pull',item(unsupported),copy.deepcopy(base),2))
    rows=[];traces={}
    for name,d,s,expected in cases:
        ip=out/(name+'-item.json');ip.write_text(json.dumps(d,indent=2));sp=out/(name+'-scenario.json');sp.write_text(json.dumps(s,indent=2))
        r=subprocess.run([sys.executable,str(w.HERE/'workbench.py'),'run','--item',str(ip),'--scenario',str(sp),'--out',str(out/name),'--no-build'],cwd=w.ROOT,capture_output=True,text=True,timeout=180)
        tp=out/name/'native.json';t=w.read_json(tp) if tp.exists() else {};traces[name]=t
        rows.append({'name':name,'passed':r.returncode==expected and t.get('status')=={0:'passed',2:'error'}[expected],'exit':r.returncode,'error':t.get('error'),'trace':str(tp),'stderr':r.stderr});print(name,rows[-1]['passed'],t.get('error',''),flush=True)
    def snaps(name):return traces[name].get('snapshots',[])
    def hits(name):return [(s['tick'],e) for s in snaps(name) for e in s.get('events',[]) if e['kind'] in ('hit','item_hit')]
    def buffs(s):return s.get('dummy',{}).get('targetState',{}).get('nativeBuffs',[])
    def check(name,result):rows.append({'name':name,'passed':bool(result)});print(name,bool(result),flush=True)
    for buff in (153,70,69):
        name=f'status-{buff}';seen=[s['tick'] for s in snaps(name) if any(b['id']==buff for b in buffs(s))]
        check(name+'-actual-hit-before-buff-and-expiry',bool(hits(name) and seen) and min(seen)>=min(t for t,e in hits(name)) and not buffs(snaps(name)[-1]))
    check('item-body-real-contact-status',any(e['kind']=='item_hit' for _,e in hits('status-body')) and any(b['id']==153 for s in snaps('status-body') for b in buffs(s)))
    check('no-callback-and-miss-no-status',all(not buffs(s) for name in ('no-callback','status-miss') for s in snaps(name)))
    
    baseline={s['tick']:s['dummy']['vx'] for s in snaps('same-resist-no-callback')}
    for name in ('pull','pull-body'):
        check(name+'-native-impulse-toward-owner-after-hit',bool(hits(name)) and any(s['dummy']['vx'] < baseline.get(s['tick'],-999)-.01 for s in snaps(name)))
    check('knockback-immune-and-miss-no-pull',all(abs(s['dummy']['vx'])<1e-6 for name in ('pull-immune','pull-miss') for s in snaps(name)))
    check('binary-unchanged',w.digest(dll)==binary)
    summary={'passed':all(r['passed'] for r in rows),'binarySha256':binary,'providerCalls':0,'scope':'Synthetic native client_hybrid NPC.UpdateNPC and actual hit callback proof; no full world or multiplayer claim. Authored gallery DTOs untouched.','checks':rows}
    (out/'summary.json').write_text(json.dumps(summary,indent=2));return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
