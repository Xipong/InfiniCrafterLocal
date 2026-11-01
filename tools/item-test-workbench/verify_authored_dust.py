#!/usr/bin/env python3
"""Bounded original nativeDust emitter/update/draw proof; synthetic controls, not item substitution."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
from PIL import Image, ImageChops
import workbench as w


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-dll',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--dust-type',choices=['TintableDustLighted','Glass','GemDiamond','Electric'],default='TintableDustLighted')
    args=parser.parse_args()
    out=args.out.resolve(); out.mkdir(parents=True,exist_ok=False)
    dll=args.native_dll.resolve(); binary=w.digest(dll)
    command=[os.environ.get('DOTNET','dotnet'),str(dll)]
    subprocess.run(command+['--write-fixtures',str(out/'fixtures')],cwd=w.ROOT,check=True)
    item=w.read_json(out/'fixtures/synthetic-straight.json')
    slot=dict(id='native_dust',entityId='root',event='on_spawn',rendererKind='nativeDust',anchor='self',
              startTick=0,repeatEvery=0,slotSeed=1175933628,color=dict(r=255,g=221,b=112),
              dust=dict(spawn=dict(shape='point'),type=args.dust_type,count=6,size=.9,
                        speedMinPxPerTick=1,speedMaxPxPerTick=2.8,angularDistribution='random',
                        directionFrame='world',angleOffsetRadians=0,spreadRadians=6.283185307179586,
                        inheritVelocity=0,nativeAlpha=30,noGravity=True))
    item['vfxManifest']['slots']=[slot]
    scene=dict(playerUpdate='client_vfx',ticks=240,seed=1,
               player=dict(x=800,y=700,mana=200),dummy=dict(x=1800,y=1200,life=10000),
               tiles=[dict(tileX=1,tileY=47,width=97,height=1)],
               actions=[dict(kind='primary',tick=0),dict(kind='release',tick=1)],
               assertions=[dict(kind='spawned'),dict(kind='no_nonfinite')],
               nativeRender=dict(width=512,height=384,cameraX=650,cameraY=550,capture=True,
                                 drawProjectileVfx=True,drawNativeDust=True,lightingMode='viewport_fill'))
    blank=copy.deepcopy(item);blank['vfxManifest']['slots']=[]
    unsupported=copy.deepcopy(item);unsupported['vfxManifest']['slots'][0]['dust']['type']='Smoke'
    no_draw=copy.deepcopy(scene);no_draw['nativeRender']['drawNativeDust']=False
    no_capture=copy.deepcopy(scene);no_capture['nativeRender']['capture']=False
    missing=out/'missing-dust';shutil.copytree(os.environ['INFINI_PLAYER_ASSET_DIR'],missing,
                                            ignore=lambda _p,n:['Dust.png'] if 'Dust.png' in n else [])
    cases=[('dust',item,scene,0,None),('blank',blank,scene,0,None),('repeat',item,scene,0,None),
           ('no-capture',item,no_capture,0,None),('unproven-selector',unsupported,scene,2,'nativeDust requires'),
           ('no-native-draw',item,no_draw,2,'nativeDust requires'),('missing-resource',item,scene,2,'Missing exact starter-player source PNG: Dust')]
    traces={};checks=[]
    for name,value,scenario,expected,error in cases:
        directory=out/name;directory.mkdir()
        (directory/'item.json').write_text(json.dumps(value));(directory/'scenario.json').write_text(json.dumps(scenario))
        env=dict(os.environ)
        if name=='missing-resource':env['INFINI_PLAYER_ASSET_DIR']=str(missing)
        proc=subprocess.run(command+['--item',str(directory/'item.json'),'--scenario',str(directory/'scenario.json'),
                                    '--output',str(directory/'native.json')],cwd=w.ROOT,env=env,
                            capture_output=True,text=True,timeout=180)
        (directory/'process.log').write_text(proc.stdout+proc.stderr)
        trace=w.read_json(directory/'native.json');traces[name]=trace
        passed=proc.returncode==expected and trace['status']==('passed' if expected==0 else 'error')
        if error:passed=passed and error in trace.get('error','') and not trace.get('nativeRender',{}).get('frames')
        checks.append(dict(name=name,passed=passed,exitCode=proc.returncode))
    actual=traces['dust'];control=traces['blank']
    snapshots=actual.get('nativeRender',{}).get('snapshots',[])
    before=[s.get('nativeDustBeforeDraw',[]) for s in snapshots]
    after=[s.get('nativeDustAfterDraw',[]) for s in snapshots]
    dust=[d for frame in before for d in frame]
    onframes=actual.get('nativeRender',{}).get('frames',[]);offframes=control.get('nativeRender',{}).get('frames',[])
    pixels=[];integrity=len(onframes)==len(offframes)==240
    for on,off in zip(onframes,offframes):
        a=out/'dust'/on['path'];b=out/'blank'/off['path']
        integrity=integrity and w.digest(a)==on['sha256'] and w.digest(b)==off['sha256'] and on['tick']==off['tick']
        with Image.open(a) as ia,Image.open(b) as ib:
            pixels.append(sum(any(p) for p in ImageChops.difference(ia.convert('RGB'),ib.convert('RGB')).get_flattened_data()))
    hashes=lambda trace:[f['sha256'] for f in trace.get('nativeRender',{}).get('frames',[])]
    observed={
        'native-exact-type-no-shader':bool(dust) and all(d['type']=={'TintableDustLighted':43,'Glass':13,'GemDiamond':91,'Electric':226}[args.dust_type] and d['shaderType'] is None and d['frameWidth']>0 for d in dust),
        'native-update-changes-scale':len({d['scale'] for d in dust})>1,
        'native-expiry-not-draw-culling':bool(before) and bool(before[0]) and not before[-1] and all(len(a)==len(b) for a,b in zip(before,after)),
        'visible-pixels':any(pixels),
        'no-late-pixels':bool(pixels) and not any(pixels[-10:]),
        'native-png-integrity':integrity,
        'fresh-process-reset':hashes(actual)==hashes(traces['repeat']) and snapshots==traces['repeat'].get('nativeRender',{}).get('snapshots'),
        'no-capture-keeps-native-lifecycle':snapshots==traces['no-capture'].get('nativeRender',{}).get('snapshots') and not traces['no-capture'].get('nativeRender',{}).get('frames'),
        'binary-unchanged':w.digest(dll)==binary,
    }
    checks.extend(dict(name=k,passed=v) for k,v in observed.items())
    summary=dict(selector=args.dust_type,passed=all(c['passed'] for c in checks),checks=checks,nativeDllSha256=binary,
                 changedRgbPixelsByTick=pixels,observedDustTypes=sorted({d['type'] for d in dust}),
                 scope='Synthetic authored on_spawn native dust, original emitter/update/draw. Fresh-process reset only; not full Main.Draw or art acceptance.')
    (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
    return 0 if summary['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
