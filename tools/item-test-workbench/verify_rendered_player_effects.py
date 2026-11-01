#!/usr/bin/env python3
"""Real native Player.Hurt / selected native player-buff flags with render controls.

Inputs are explicit native item/scenario files. Originals are immutable; short
buff expiry and unproven-pet refusal use labelled synthetic test counterparts.
"""
import argparse,copy,json,subprocess,sys
from pathlib import Path
import workbench as w


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--item',type=Path,required=True);p.add_argument('--scenario',type=Path,required=True);p.add_argument('--kind',choices=['hurt','buff'],required=True);p.add_argument('--buff-id',type=int,choices=[18,122]);p.add_argument('--out',type=Path,required=True);p.add_argument('--no-build',action='store_true');a=p.parse_args()
 if a.kind=='buff' and not a.buff_id:p.error('buff proof requires --buff-id')
 out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 if not a.no_build:w.build()
 item=w.read_json(a.item);base=w.read_json(a.scenario);base['ticks']=90;base['actions']=[x for x in base['actions'] if x['tick']<90];base['assertions']=[{'kind':'no_nonfinite'}]
 if a.kind=='buff' and a.buff_id==18:
  base['actions'] += [{'tick':20,'kind':'controls','left':False,'right':False,'jump':False,'up':True},{'tick':21,'kind':'controls','left':False,'right':False,'jump':False,'up':False}]
 cases=[('positive',item,base,0)]
 no=copy.deepcopy(base)
 if a.kind=='hurt':
  no['actions']=[x for x in no['actions'] if x['kind']!='hurt_player'];cases.append(('no-hurt',item,no,0))
  vanity=copy.deepcopy(base)
  for action in vanity['actions']:
   if action['kind']=='equip':action['kind']='vanity'
  cases.append(('vanity-hurt',item,vanity,0))
  refused=copy.deepcopy(base);refused['nativeRender']['drawNativeDust']=False;cases.append(('refused-no-native-dust',item,refused,2))
 else:
  no['actions']=[x for x in no['actions'] if x['kind'] not in ('primary','alt')];cases.append(('no-use',item,no,0))
  short=copy.deepcopy(item)
  for buff in short['gameplay']['extraBuffs']:buff['buffTime']=3
  once=copy.deepcopy(base);once['actions']=[x for x in once['actions'] if x['kind']!='release'];once['actions'].append({'tick':1,'kind':'release'})
  cases.append(('synthetic-short-expiry',short,once,0))
  refused=copy.deepcopy(item);refused['gameplay']['extraBuffs']=[{'buffCode':40,'buffTime':60}];cases.append(('refused-unproven-buff',refused,copy.deepcopy(base),2))
 dll=w.HERE/'bin/Release/net8.0/ItemTestWorkbench.dll';binary=w.digest(dll);ih=w.digest(a.item);sh=w.digest(a.scenario);rows=[];traces={}
 for name,data,scene,expected in cases:
  ip=out/(name+'-item.json');ip.write_text(json.dumps(data,indent=2));sp=out/(name+'-scenario.json');sp.write_text(json.dumps(scene,indent=2))
  r=subprocess.run([sys.executable,str(w.HERE/'workbench.py'),'run','--item',str(ip),'--scenario',str(sp),'--out',str(out/name),'--no-build'],cwd=w.ROOT,capture_output=True,text=True,timeout=240)
  tp=out/name/'native.json';t=w.read_json(tp) if tp.exists() else {};traces[name]=t
  rows.append({'name':name,'passed':r.returncode==expected and t.get('status')=={0:'passed',2:'error'}[expected],'exit':r.returncode,'error':t.get('error'),'stderr':r.stderr});print(name,rows[-1]['passed'],t.get('error',''),flush=True)
 def snaps(name):return traces[name].get('snapshots',[])
 def render(name):return traces[name].get('nativeRender',{})
 def count(s):return s.get('shapeRecordCount',0)+s.get('particleCount',0)+s.get('materialRecordCount',0)
 def check(name,value):rows.append({'name':name,'passed':bool(value)});print(name,bool(value),flush=True)
 check('real-native-pngs',len(render('positive').get('frames',[]))==90 and all((out/'positive'/f['path']).is_file() and w.digest(out/'positive'/f['path'])==f['sha256'] for f in render('positive').get('frames',[])))
 if a.kind=='hurt':
  hurt=[e for s in snaps('positive') for e in s.get('events',[]) if e['kind']=='native_player_hurt']
  check('actual-native-damage-and-client-reaction-phase',bool(hurt) and all(e['nativeDamage']>0 and e['lifeAfter']<e['lifeBefore'] for e in hurt) and any(e['kind']=='native_phase' and e.get('phase')=='reaction stimulus' and e.get('dedServ') is False for s in snaps('positive') for e in s.get('events',[])))
  check('equipped-actual-buff-and-vfx',any(s['player']['generatedBuffTicks']>0 for s in snaps('positive')) and any(count(s)>0 for s in render('positive').get('snapshots',[])))
  check('no-hurt-and-vanity-no-generated-reaction',all(s['player']['generatedBuffTicks']==0 for n in ('no-hurt','vanity-hurt') for s in snaps(n)) and all(count(s)==0 for n in ('no-hurt','vanity-hurt') for s in render(n).get('snapshots',[])))
  check('native-blood-dust-draw',render('positive').get('nativeDustDrawExecuted') is True and any(s.get('nativeDustBeforeDraw') for s in render('positive').get('snapshots',[])))
 else:
  flag='gravitation' if a.buff_id==18 else 'sonar'
  seen=lambda s:any(b['id']==a.buff_id for b in s['player']['nativeBuffs'])
  check('native-buff-and-actual-player-flag',any(seen(s) and s['player'].get('nativeBuffFlags',{}).get(flag) is True for s in snaps('positive')))
  check('no-use-no-buff-or-flag',all(not seen(s) and not s['player'].get('nativeBuffFlags',{}).get(flag,False) for s in snaps('no-use')))
  check('synthetic-short-buff-expires-natively',any(seen(s) for s in snaps('synthetic-short-expiry')) and not seen(snaps('synthetic-short-expiry')[-1]) and not snaps('synthetic-short-expiry')[-1]['player'].get('nativeBuffFlags',{}).get(flag,False))
  if a.buff_id==18:check('native-gravity-control-flips-only-with-buff',any(s['player'].get('nativeBuffFlags',{}).get('gravityDirection')==-1 for s in snaps('positive')) and all(s['player'].get('nativeBuffFlags',{}).get('gravityDirection')==1 for s in snaps('no-use')))
 check('original-inputs-and-binary-unchanged',w.digest(a.item)==ih and w.digest(a.scenario)==sh and w.digest(dll)==binary)
 summary={'passed':all(x['passed'] for x in rows),'kind':a.kind,'nativeDllSha256':binary,'itemSha256':ih,'scenarioSha256':sh,'providerCalls':0,'scope':'Native controlled client Player.Update/Hurt and actual draw; no full world, audio audibility or multiplayer claim; shortened/refused DTOs are explicitly synthetic controls.','checks':rows}
 (out/'summary.json').write_text(json.dumps(summary,indent=2));return 0 if summary['passed'] else 1
if __name__=='__main__':sys.exit(main())
