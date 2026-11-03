#!/usr/bin/env python3
"""Bounded original contour-renderer proof, with distinct authored polylines."""
import argparse
import copy
import json
import os
import shutil
from pathlib import Path
import subprocess
from PIL import Image, ImageChops
import workbench as w


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-dll',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    dll=args.native_dll.resolve();binary=w.native_binaries_state(dll)
    command=[os.environ.get('DOTNET','dotnet'),str(dll)]
    subprocess.run(command+['--write-fixtures',str(out/'fixtures')],cwd=w.ROOT,check=True)
    item=w.read_json(out/'fixtures/synthetic-straight.json')
    geometry=dict(attachment='world',rotationFrame='world',
        transformStart=dict(translate=[0,0],scale=[.22,.22],rotationRadians=0),
        transformEnd=dict(translate=[8,-5],scale=[1,1],rotationRadians=.3),
        contours=[dict(id='edge',kind='polyline',points=[[-32,-24],[32,-24],[32,24],[-32,24],[-32,-24]])],
        draws=[dict(op='stroke',contour='edge',widthPx=3,join='bevel',cap='butt',miterLimit=2,
            mapping=dict(mode='stretch',repeatLengthPx=1,scrollPxPerTick=0),
            opacityProfile=dict(start=1,middle=1,end=1,curve='linear'),
            material=dict(texture=dict(source='library',assetId='solidPixel',uv=dict(quarterTurns=0,mirrorU=False,mirrorV=False)),
                sampling='point',colorStart=dict(r=154,g=255,b=246),colorEnd=dict(r=39,g=151,b=218),opacityStart=.85,opacityEnd=0))])
    slot=dict(id='contour_proof',entityId='root',event='on_spawn',rendererKind='contour',anchor='self',blend='alpha',
              layer='AfterProjectiles',duration=12,startTick=3,repeatEvery=0,slotSeed=1,geometry=geometry)
    item['vfxManifest']['slots']=[slot]
    scene=dict(playerUpdate='client_vfx',ticks=36,seed=1,player=dict(x=800,y=700,mana=200),
        dummy=dict(x=1100,y=900,life=10000),tiles=[dict(tileX=1,tileY=47,width=97,height=1)],
        actions=[dict(kind='primary',tick=0),dict(kind='release',tick=1)],
        assertions=[dict(kind='spawned'),dict(kind='no_nonfinite')],
        nativeRender=dict(width=512,height=384,cameraX=650,cameraY=550,capture=True,drawProjectileVfx=True,lightingMode='viewport_fill'))
    off=copy.deepcopy(item);off['vfxManifest']['slots']=[]
    triangle=copy.deepcopy(item);triangle['vfxManifest']['slots'][0]['geometry']['contours'][0]['points']=[[-28,20],[0,-32],[36,16],[-28,20]]
    nocapture=copy.deepcopy(scene);nocapture['nativeRender']['capture']=False
    nodraw=copy.deepcopy(scene);nodraw['nativeRender']['drawProjectileVfx']=False
    star=copy.deepcopy(item);star['vfxManifest']['slots'][0]['geometry']['draws'][0]['material']['texture']['assetId']='star'
    unknown=copy.deepcopy(star);unknown['vfxManifest']['slots'][0]['geometry']['draws'][0]['material']['texture']['assetId']='unknown-proof-texture'
    attached=copy.deepcopy(item);attached['vfxManifest']['slots'][0]['geometry']['attachment']='source'
    line=copy.deepcopy(item);line['vfxManifest']['slots'][0]['geometry']['contours']=[dict(id='edge',kind='line',**{'from':[-20,0],'to':[20,0]})]
    cases=[('box',item,scene,0),('off',off,scene,0),('triangle',triangle,scene,0),('repeat',item,scene,0),
           ('no-capture',item,nocapture,0),('no-draw',item,nodraw,2),('unproven-texture',star,scene,2),
           ('unknown-texture',unknown,scene,2),('source-attachment',attached,scene,2),('unproven-node',line,scene,2)]
    missing=out/'missing-white-pixel-assets';shutil.copytree(os.environ['INFINI_PARTICLE_ASSET_DIR'],missing)
    (missing/'Assets/Textures/WhitePixel.png').unlink()
    cases.append(('missing-white-pixel',item,scene,2))
    traces={};checks=[]
    for name,value,s,expected in cases:
        directory=out/name;directory.mkdir();(directory/'item.json').write_text(json.dumps(value));(directory/'scenario.json').write_text(json.dumps(s))
        environment=None if name!='missing-white-pixel' else dict(os.environ,INFINI_PARTICLE_ASSET_DIR=str(missing))
        proc=subprocess.run(command+['--item',str(directory/'item.json'),'--scenario',str(directory/'scenario.json'),'--output',str(directory/'native.json')],cwd=w.ROOT,capture_output=True,text=True,timeout=180,env=environment)
        (directory/'process.log').write_text(proc.stdout+proc.stderr)
        trace=w.read_json(directory/'native.json') if (directory/'native.json').exists() else {};traces[name]=trace
        passed=proc.returncode==expected and trace.get('status')==('passed' if expected==0 else 'error')
        if expected:passed=passed and bool(trace.get('error'))
        if name=='missing-white-pixel':passed=passed and ('WhitePixel' in trace.get('error','') or 'library texture' in trace.get('error',''))
        checks.append(dict(name=name,passed=passed,exitCode=proc.returncode));print(name,passed,flush=True)
    blank=traces['off'];pixel_counts={}
    for name in ('box','triangle'):
        trace=traces[name];frames=trace.get('nativeRender',{}).get('frames',[]);controls=blank.get('nativeRender',{}).get('frames',[])
        pixels=[];integrity=len(frames)==len(controls)==36
        for a,b in zip(frames,controls):
            ap=out/name/a['path'];bp=out/'off'/b['path'];integrity=integrity and w.digest(ap)==a['sha256'] and w.digest(bp)==b['sha256'] and a['tick']==b['tick']
            with Image.open(ap) as ia,Image.open(bp) as ib:pixels.append(sum(any(p) for p in ImageChops.difference(ia.convert('RGB'),ib.convert('RGB')).get_flattened_data()))
        snapshots=trace.get('nativeRender',{}).get('snapshots',[]);present=[s for s in snapshots if s.get('contourRecordCount',0)>0]
        observed=bool(present) and all(d['triangleCount']>0 and len(d['strokePath'])>=4 and d['texturePath']=='ParticleLibrary/Assets/Textures/WhitePixel' for s in present for c in s['contours'] for d in c['draws'])
        checks += [dict(name=name+'-native-resolved-geometry',passed=observed),dict(name=name+'-expiry',passed=bool(snapshots) and snapshots[-1].get('contourRecordCount')==0),
            dict(name=name+'-pixels-only-during-life',passed=bool(pixels) and any(pixels[3:15]) and not any(pixels[:3]) and not any(pixels[15:])),
            dict(name=name+'-png-integrity',passed=integrity),dict(name=name+'-unchanged-gameplay',passed=trace.get('snapshots')==blank.get('snapshots'))]
        pixel_counts[name]=pixels
    hashes=lambda t:[f['sha256'] for f in t.get('nativeRender',{}).get('frames',[])]
    checks += [dict(name='distinct-polyline-pixels',passed=bool(hashes(traces['box'])) and hashes(traces['box'])!=hashes(traces['triangle'])),
        dict(name='fresh-process-reset',passed=bool(hashes(traces['box'])) and hashes(traces['box'])==hashes(traces['repeat'])),
        dict(name='capture-off-retains-lifecycle',passed=traces['box'].get('nativeRender',{}).get('snapshots')==traces['no-capture'].get('nativeRender',{}).get('snapshots') and not hashes(traces['no-capture'])),
        dict(name='binary-unchanged',passed=w.native_binaries_state(dll)==binary)]
    summary=dict(passed=all(c['passed'] for c in checks),checks=checks,changedRgbPixelsByTick=pixel_counts,nativeDllSha256=w.digest(dll),
        scope='Original production resolved stroke paths/triangle counts and actual GPU pixels; observer is not final GPU vertex capture. Reset is fresh-process, not same-process unload; no item-quality claim.')
    (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2));return 0 if summary['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
