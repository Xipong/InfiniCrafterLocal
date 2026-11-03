#!/usr/bin/env python3
"""Native passive accessory admission and wide-ground movement controls."""
import argparse,copy,json,subprocess,sys,statistics
from pathlib import Path
import workbench as w


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--no-build',action='store_true');a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
 if not a.no_build:w.build()
 dll=w.HERE/'bin/Release/net8.0/ItemTestWorkbench.dll';binary=w.digest(dll)
 base={'playerUpdate':'full','worldWidthTiles':400,'ticks':720,'seed':1,'player':{'x':800,'y':710,'life':100,'maxLife':100,'mana':200,'manaCrystals':9},'dummy':{'x':1400,'y':700,'life':10000},'tiles':[{'tileX':1,'tileY':47,'width':397,'height':1}],'actions':[{'tick':0,'kind':'equip'},{'tick':5,'kind':'controls','left':False,'right':True,'jump':False},{'tick':600,'kind':'controls','left':False,'right':False,'jump':False}],'assertions':[{'kind':'no_nonfinite'}]}
 cases=[]
 for name,item,placement in [('hermes','HermesBoots','equip'),('frostspark','FrostsparkBoots','equip'),('vanity','HermesBoots','vanity'),('inventory','HermesBoots','unequip')]:
  s=copy.deepcopy(base);s['actions'][0]['kind']=placement;cases.append((name,item,s,0))
 small=copy.deepcopy(base);small.pop('worldWidthTiles');small['ticks']=40;small['tiles'][0]['width']=97;small['actions']=[x for x in small['actions'] if x['tick']<40]
 cases.append(('default-width','HermesBoots',small,0));explicit=copy.deepcopy(small);explicit['worldWidthTiles']=100;cases.append(('explicit-default-width','HermesBoots',explicit,0))
 for width in (99,401):
  bad=copy.deepcopy(small);bad['worldWidthTiles']=width;cases.append((f'refused-width-{width}','HermesBoots',bad,2))
 bad=copy.deepcopy(small);bad['playerUpdate']='item_check';cases.append(('refused-item-check-equipment','HermesBoots',bad,2))
 bad=copy.deepcopy(small);bad['actions'].append({'tick':1,'kind':'primary'});cases.append(('refused-accessory-as-weapon','HermesBoots',bad,2))
 cases.append(('refused-weapon-as-equipment','WoodenBow',copy.deepcopy(small),2))
 rows=[];traces={}
 for name,item,s,expected in cases:
  sp=out/(name+'.json');sp.write_text(json.dumps(s,indent=2));r=subprocess.run([sys.executable,str(w.HERE/'workbench.py'),'run','--vanilla-item',item,'--scenario',str(sp),'--out',str(out/name),'--no-build'],cwd=w.ROOT,capture_output=True,text=True,timeout=180)
  tp=out/name/'native.json';t=w.read_json(tp) if tp.exists() else {};traces[name]=t;rows.append({'name':name,'passed':r.returncode==expected and t.get('status')=={0:'passed',2:'error'}[expected],'exit':r.returncode,'error':t.get('error'),'stderr':r.stderr});print(name,rows[-1]['passed'],flush=True)
 def frames(name):return [s for s in traces[name].get('snapshots',[]) if s.get('phase') is None]
 def coords(name):return [(s['tick'],s['player']['x'],s['player']['y'],s['player']['vx'],s['player']['vy']) for s in frames(name)]
 def check(name,value):rows.append({'name':name,'passed':bool(value)});print(name,bool(value),flush=True)
 check('default-width-unchanged',coords('default-width')==coords('explicit-default-width') and bool(coords('default-width')))
 check('vanity-equals-no-accessory-motion',coords('vanity')==coords('inventory') and bool(coords('inventory')))
 for name,item_id in [('hermes',54),('frostspark',1862)]:
  ss=frames(name);by={s['tick']:s['player'] for s in ss};plateau=[by[t]['vx'] for t in range(540,600)]
  check(name+'-native-identity-single-equip-no-buffs',traces[name]['input']['nativeItemId']==item_id and all(len(s['player']['armor'])==1 and s['player']['armor'][0]['nativeType']==item_id and s['player']['armor'][0]['placement']=='functional' and not s['player']['nativeBuffs'] and s['player']['generatedBuffTicks']==0 for s in ss if s['tick']>=0))
  check(name+'-actual-acceleration-plateau-stop-no-edge',max(plateau)-min(plateau)<=by[599]['movementStats']['runSlowdown']+by[599]['movementStats']['runAcceleration'] and abs(statistics.mean(plateau[:30])-statistics.mean(plateau[30:]))<by[599]['movementStats']['runAcceleration'] and min(plateau)>3 and by[5]['vx']<by[50]['vx']<by[599]['vx'] and abs(by[719]['vx'])<1e-5 and all(s['player']['y']==710 and 700<s['player']['x']<5700 and s['nativeWorldWidthTiles']==400 and s['nativeTilemapWidth']==400 for s in ss) and max(abs((by[t]['x']-by[t-1]['x'])-by[t]['vx']) for t in range(1,720))<.001)
 check('binary-unchanged',w.digest(dll)==binary)
 summary={'passed':all(x['passed'] for x in rows),'nativeDllSha256':binary,'scope':'Actual native Player.Update, one passive vanilla accessory slot, flat controlled terrain. No synthetic movement, full game-world, native equipment artwork or multiplayer claim.','checks':rows}
 (out/'summary.json').write_text(json.dumps(summary,indent=2));return 0 if summary['passed'] else 1
if __name__=='__main__':sys.exit(main())
