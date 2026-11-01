#!/usr/bin/env python3
"""Native source-bound world-frame orbit: pixels/count/rotation/lifecycle controls."""
import argparse
import copy
import json
import math
import os
from pathlib import Path
import subprocess
from PIL import Image, ImageChops
import workbench as w


def components(image):
    pixels=image.convert('RGB'); points={(x,y) for y in range(pixels.height) for x in range(pixels.width) if any(pixels.getpixel((x,y)))}
    result=[]
    while points:
        seed=points.pop(); group=[seed]; todo=[seed]
        while todo:
            x,y=todo.pop()
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    q=(x+dx,y+dy)
                    if q in points:points.remove(q);group.append(q);todo.append(q)
        result.append((sum(x for x,y in group)/len(group),sum(y for x,y in group)/len(group)))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-dll',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    dll=args.native_dll.resolve();binary=w.digest(dll);cmd=[os.environ.get('DOTNET','dotnet'),str(dll)]
    subprocess.run(cmd+['--write-fixtures',str(out/'fixtures')],cwd=w.ROOT,check=True)
    item=w.read_json(out/'fixtures/synthetic-straight.json')
    next(e for e in item['runtimeProgram']['entities'] if e['id']=='root')['spawn']['aim']='cursor'
    shape=dict(kind='orbit',attachment='source',rotationFrame='world',offsetForwardPx=0,offsetSidePx=0,
               rotationRadians=0,rotationSpeedRadiansPerTick=.035,colorStart=dict(r=131,g=230,b=255),
               colorEnd=dict(r=245,g=137,b=222),opacityCurve='linear',opacityStart=.65,opacityEnd=.65,
               radiusStartPx=25,radiusEndPx=25,count=3,moteOrientation='world',moteRotationRadians=math.pi/4,moteSizePx=2)
    item['vfxManifest']['slots']=[dict(id='orbit',entityId='root',event='on_spawn',rendererKind='shape',anchor='self',
        blend='additive',layer='AfterProjectiles',duration=24,startTick=3,repeatEvery=0,slotSeed=1,shape=shape)]
    scene=dict(playerUpdate='client_vfx',ticks=48,seed=1,player=dict(x=800,y=700,mana=200),
        dummy=dict(x=1800,y=1200,life=10000),tiles=[dict(tileX=1,tileY=47,width=97,height=1)],
        actions=[dict(kind='aim',tick=0,x=1000,y=600),dict(kind='primary',tick=0),dict(kind='release',tick=1)],
        assertions=[dict(kind='spawned'),dict(kind='no_nonfinite')],nativeRender=dict(width=512,height=384,cameraX=650,cameraY=550,
        capture=True,drawProjectileVfx=True,lightingMode='viewport_fill'))
    off=copy.deepcopy(item);off['vfxManifest']['slots']=[]
    one=copy.deepcopy(item);one['vfxManifest']['slots'][0]['shape']['count']=1
    eight=copy.deepcopy(item);eight['vfxManifest']['slots'][0]['shape']['count']=8
    fixed=copy.deepcopy(item);fixed['vfxManifest']['slots'][0]['shape']['rotationSpeedRadiansPerTick']=0
    silent=copy.deepcopy(scene);silent['nativeRender']['capture']=False
    partial=copy.deepcopy(scene);partial['nativeRender']['drawProjectileVfx']=False
    unsupported=copy.deepcopy(item);unsupported['vfxManifest']['slots'][0]['shape']['rotationFrame']='source'
    cases=[('orbit',item,scene,0),('off',off,scene,0),('one',one,scene,0),('eight',eight,scene,0),
        ('fixed',fixed,scene,0),('repeat',item,scene,0),('silent',item,silent,0),('partial',item,partial,2),
        ('source-rotation-unproven',unsupported,scene,2)]
    traces={};checks=[]
    for name,value,scenario,expected in cases:
        d=out/name;d.mkdir();(d/'item.json').write_text(json.dumps(value));(d/'scenario.json').write_text(json.dumps(scenario))
        process=subprocess.run(cmd+['--item',str(d/'item.json'),'--scenario',str(d/'scenario.json'),'--output',str(d/'native.json')],cwd=w.ROOT,capture_output=True,text=True,timeout=180)
        (d/'process.log').write_text(process.stdout+process.stderr);trace=w.read_json(d/'native.json');traces[name]=trace
        good=process.returncode==expected and trace['status']==('passed' if expected==0 else 'error')
        if expected:good=good and 'shape currently requires' in trace.get('error','') and not trace.get('nativeRender',{}).get('frames')
        checks.append(dict(name=name,passed=good))
    frames=lambda t:t.get('nativeRender',{}).get('frames',[])
    states=lambda t:t.get('nativeRender',{}).get('snapshots',[])
    hashes=lambda t:[f['sha256'] for f in frames(t)]
    actual=traces['orbit'];blank=traces['off'];changed={};counts={};integrity=True
    for name in ['orbit','one','eight','fixed']:
        diffs=[];centers=[]
        for f,b in zip(frames(traces[name]),frames(blank)):
            a=out/name/f['path'];z=out/'off'/b['path'];integrity &= w.digest(a)==f['sha256'] and w.digest(z)==b['sha256']
            with Image.open(a) as ia,Image.open(z) as ib:delta=ImageChops.difference(ia.convert('RGB'),ib.convert('RGB'))
            diffs.append(delta.getbbox() is not None);centers.append(components(delta) if f['tick'] in (3,10) else [])
        changed[name]=diffs;counts[name]=centers
        checks.append(dict(name=name+'-lifecycle',passed=len(diffs)==48 and any(diffs[3:27]) and not any(diffs[:3]) and not any(diffs[27:])))
        checks.append(dict(name=name+'-same-gameplay',passed=traces[name]['snapshots']==blank['snapshots']))
    observed={
        'actual-one-three-eight-motes':all(len(counts[name][3])==count for name,count in [('orbit',3),('one',1),('eight',8)]),
        'authored-angular-motion-visible':hashes(actual)[10]!=hashes(traces['fixed'])[10],
        'source-position-updated':len({(v['x'],v['y']) for s in states(actual) for v in s.get('shapes',[])})>3,
        'expired':bool(states(actual)) and states(actual)[-1]['shapeRecordCount']==0,
        'fresh-process-reset':hashes(actual)==hashes(traces['repeat']) and states(actual)==states(traces['repeat']),
        'capture-off-lifecycle':states(actual)==states(traces['silent']) and not frames(traces['silent']),
        'png-hashes-valid':integrity,'binary-unchanged':w.digest(dll)==binary,
    }
    checks += [dict(name=n,passed=v) for n,v in observed.items()]
    summary=dict(passed=all(c['passed'] for c in checks),checks=checks,nativeDllSha256=binary,
        scope='Synthetic native source/world orbit only; original authored Nebula unchanged, fresh-process reset not full-world parity.',
        observedMoteCenters={n:{'tick3':v[3],'tick10':v[10]} for n,v in counts.items()})
    (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
    return 0 if summary['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
