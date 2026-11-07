#!/usr/bin/env python3
"""Native on-hit debuff dust: real lighting/update/draw, expiry and no-hit controls."""
# Direct script entrypoints resolve the same package as workbench.py.
if __package__ in (None, ""):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
from PIL import Image, ImageChops
import workbench as w


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native-dll',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    dll=a.native_dll.resolve();binary=w.digest(dll);cmd=[os.environ.get('DOTNET','dotnet'),str(dll)]
    subprocess.run(cmd+['--write-fixtures',str(out/'fixtures')],cwd=w.ROOT,check=True)
    item=w.read_json(out/'fixtures/synthetic-straight.json');root=next(e for e in item['runtimeProgram']['entities'] if e['id']=='root')
    root['spawn']['aim']='cursor';root['events']=[dict(id='shadow',action='apply_status_on_event',actionCode=2,event='on_hit',buffId=153,durationTicks=30),dict(id='frost',action='apply_status_on_event',actionCode=2,event='on_hit',buffId=324,durationTicks=45)]
    item['vfxManifest']['slots']=[]
    scene=dict(playerUpdate='client_vfx',ticks=180,seed=1,player=dict(x=800,y=710,mana=200),
        dummy=dict(nativeType='zombie',x=848,y=710,width=32,height=48,life=10000),
        tiles=[dict(tileX=1,tileY=47,width=97,height=1)],actions=[dict(kind='aim',tick=0,x=864,y=734),dict(kind='primary',tick=0),dict(kind='release',tick=1)],
        assertions=[dict(kind='no_nonfinite')],nativeRender=dict(width=512,height=384,cameraX=650,cameraY=550,capture=True,drawProjectileVfx=True,drawNativeDust=True,lightingMode='viewport_fill'))
    blank=copy.deepcopy(item)
    # Find by identity rather than relying on the fixture entity order.
    next(e for e in blank['runtimeProgram']['entities'] if e['id']=='root')['events']=[]
    hidden=copy.deepcopy(scene);hidden['nativeRender']['drawNativeDust']=False
    miss=copy.deepcopy(scene);miss['dummy']['y']=900
    cases=[('status',item,scene),('blank',blank,scene),('repeat',item,scene),('hidden-dust',item,hidden),('miss',item,miss)]
    traces={};checks=[]
    for name,value,sc in cases:
        d=out/name;d.mkdir();(d/'item.json').write_text(json.dumps(value));(d/'scenario.json').write_text(json.dumps(sc))
        r=subprocess.run(cmd+['--item',str(d/'item.json'),'--scenario',str(d/'scenario.json'),'--output',str(d/'native.json')],cwd=w.ROOT,capture_output=True,text=True,timeout=180)
        (d/'process.log').write_text(r.stdout+r.stderr);t=w.read_native_json(d/'native.json');traces[name]=t
        checks.append(dict(name=name,passed=r.returncode==0 and t['status']=='passed'))
    actual=traces['status'];render=lambda t:t.get('nativeRender',{}).get('snapshots',[])
    frames=lambda t:t.get('nativeRender',{}).get('frames',[])
    dust=lambda t:[v for s in render(t) for v in s.get('nativeDustBeforeDraw',[])]
    hits=lambda t:[e for s in t.get('snapshots',[]) for e in s.get('events',[]) if e.get('kind')=='hit']
    pixels=[]
    for f,g in zip(frames(actual),frames(traces['hidden-dust'])):
        with Image.open(out/'status'/f['path']) as x,Image.open(out/'hidden-dust'/g['path']) as y:
            pixels.append(ImageChops.difference(x.convert('RGB'),y.convert('RGB')).getbbox() is not None)
    # HitEffect observation is installed with native dust drawing; it is not a gameplay event.
    def gameplay(t):
        return [{**s,'events':[e for e in s.get('events',[]) if e.get('kind')!='native_npc_hit_effect']} for s in t['snapshots']]
    checks.extend(dict(name=n,passed=v) for n,v in {
        'native-hit':bool(hits(actual)), 'miss-no-hit':not hits(traces['miss']),
        'both-native-buffs-observed':{153,324}.issubset({b['id'] for s in actual['snapshots'] for b in s['dummy']['targetState']['nativeBuffs']}),
        'buffs-expired':not actual['snapshots'][-1]['dummy']['targetState']['nativeBuffs'],
        'status-adds-dust':len(dust(actual))>len(dust(traces['blank'])),
        'real-dust-pixels':any(pixels),
        'draw-does-not-change-gameplay':gameplay(actual)==gameplay(traces['hidden-dust']),
        'draw-does-not-mutate-visible-dust':all(s.get('nativeDustBeforeDraw')==s.get('nativeDustAfterDraw') for s in render(actual)),
        'expired-dust':bool(render(actual)) and not render(actual)[-1].get('nativeDustBeforeDraw'),
        'fresh-process-reset':actual['snapshots']==traces['repeat']['snapshots'] and [f['sha256'] for f in frames(actual)]==[f['sha256'] for f in frames(traces['repeat'])],
        'binary-unchanged':w.digest(dll)==binary}.items())
    result=dict(passed=all(c['passed'] for c in checks),checks=checks,nativeDllSha256=binary,
        actualDustTypes=sorted({v['type'] for v in dust(actual)}),scope='Synthetic on-hit Shadowflame/Frostburn2 through native NPC/Dust update; no authored VFX substitution or full-world parity')
    (out/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
