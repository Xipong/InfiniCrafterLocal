#!/usr/bin/env python3
"""Actual nativeLight buffer/sample/player pixels; no glow substitute or authored-item edits."""
import argparse
import copy
import json
import hashlib
import io
import os
from pathlib import Path
import subprocess
from PIL import Image, ImageChops
import workbench as w


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-dll',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    dll=args.native_dll.resolve();binary=w.digest(dll);cmd=[os.environ.get('DOTNET','dotnet'),str(dll)]
    subprocess.run(cmd+['--write-fixtures',str(out/'fixtures')],cwd=w.ROOT,check=True)
    item=w.read_json(out/'fixtures/synthetic-straight.json')
    # Explicit synthetic publication solely to exercise native player drawing, not fallback art.
    buffer=io.BytesIO();Image.new('RGBA',(32,32),(255,255,255,255)).save(buffer,format='PNG');raw=buffer.getvalue()
    identity=json.dumps([item['id'],'item','',item['id']],separators=(',',':')).encode('ascii')
    publication=out/('infini_asset_png_'+hashlib.sha256(identity+b'\0'+raw).hexdigest()+'.png');publication.write_bytes(raw)
    item['visual'].update(spritePath=publication.name,spriteStatus='generated',renderSizePx=32,forwardAngleDegrees=0)
    entity=next(e for e in item['runtimeProgram']['entities'] if e['id']=='root')
    entity['spawn']['speedPxPerTick']=0;entity['lifetimeTicks']=24
    item['vfxManifest']['slots']=[dict(id='native_light',entityId='root',event='periodic',rendererKind='nativeLight',
        anchor='self',startTick=0,repeatEvery=1,color=dict(r=80,g=178,b=195),light=dict(intensity=.35),slotSeed=165206511)]
    scene=dict(playerUpdate='client_vfx',ticks=64,seed=1,player=dict(x=800,y=1700,mana=200),
        dummy=dict(x=1800,y=2500,life=10000),tiles=[dict(tileX=1,tileY=109,width=97,height=1)],
        actions=[dict(kind='primary',tick=0),dict(kind='release',tick=1)],assertions=[dict(kind='spawned'),dict(kind='no_nonfinite')],
        nativeRender=dict(width=512,height=384,cameraX=650,cameraY=1550,capture=True,drawPlayer=True,drawArtwork=True,
        lightingMode='legacy_point',artworkFiles=[str(publication)]))
    off=copy.deepcopy(item);off['vfxManifest']['slots']=[]
    zero=copy.deepcopy(item);zero['vfxManifest']['slots'][0]['light']['intensity']=0
    silent=copy.deepcopy(scene);silent['nativeRender']['capture']=False
    fill=copy.deepcopy(scene);fill['nativeRender']['lightingMode']='viewport_fill'
    partial=copy.deepcopy(scene);partial['nativeRender']['drawPlayer']=False;partial['nativeRender']['drawArtwork']=False;partial['nativeRender'].pop('artworkFiles')
    cases=[('light',item,scene,0),('off',off,scene,0),('zero',zero,scene,0),('repeat',item,scene,0),
        ('silent',item,silent,0),('fill',item,fill,0),('fill-off',off,fill,0),('partial',item,partial,2)]
    traces={};checks=[]
    for name,value,scenario,expected in cases:
        d=out/name;d.mkdir();(d/'item.json').write_text(json.dumps(value));(d/'scenario.json').write_text(json.dumps(scenario))
        process=subprocess.run(cmd+['--item',str(d/'item.json'),'--scenario',str(d/'scenario.json'),'--output',str(d/'native.json')],cwd=w.ROOT,capture_output=True,text=True,timeout=180)
        (d/'process.log').write_text(process.stdout+process.stderr);trace=w.read_json(d/'native.json');traces[name]=trace
        good=process.returncode==expected and trace['status']==('passed' if expected==0 else 'error')
        if expected:good &= 'nativeLight requires' in trace.get('error','') and not trace.get('nativeRender',{}).get('frames')
        checks.append(dict(name=name,passed=bool(good)))
    frames=lambda t:t.get('nativeRender',{}).get('frames',[])
    snapshots=lambda t:t.get('nativeRender',{}).get('snapshots',[])
    colors=lambda t:[s['lightingScene']['player']['centerLightRgb'] for s in snapshots(t)]
    hashes=lambda t:[f['sha256'] for f in frames(t)]
    actual=traces['light'];off=traces['off'];pixels=[];integrity=len(frames(actual))==len(frames(off))==64
    for a,b in zip(frames(actual),frames(off)):
        p=out/'light'/a['path'];q=out/'off'/b['path'];integrity &= w.digest(p)==a['sha256'] and w.digest(q)==b['sha256']
        with Image.open(p) as ia,Image.open(q) as ib:pixels.append(sum(any(v) for v in ImageChops.difference(ia.convert('RGB'),ib.convert('RGB')).get_flattened_data()))
    changed=[a!=b for a,b in zip(colors(actual),colors(off))]
    observations={
        'native-sampled-light-changes':any(changed[:24]),
        'native-player-visible-pixel-change':any(pixels[:24]),
        'native-light-decays-after-source-expiry':bool(changed) and not any(changed[-16:]) and not any(pixels[-16:]),
        'zero-intensity-native-no-op':colors(traces['zero'])==colors(off) and hashes(traces['zero'])==hashes(off),
        'same-native-gameplay':actual.get('snapshots')==off.get('snapshots'),
        'fresh-process-reset':hashes(actual)==hashes(traces['repeat']) and snapshots(actual)==snapshots(traces['repeat']),
        'capture-off-keeps-light-lifecycle':snapshots(actual)==snapshots(traces['silent']) and not frames(traces['silent']),
        'viewport-fill-keeps-native-gameplay':traces['fill'].get('snapshots')==traces['fill-off'].get('snapshots'),
        'post-update-before-one-light-phase':actual.get('nativeRender',{}).get('lighting',{}).get('nativePhasesPerTick')==1 and 'PostUpdateEverything / Lighting.LightTiles' in actual.get('nativeRender',{}).get('lighting',{}).get('perTickOrder',''),
        'client-vfx-update-executed':actual.get('execution',{}).get('vfxCoverage',{}).get('globalVfxUpdateExecuted') is True,
        'png-integrity':integrity,'binary-unchanged':w.digest(dll)==binary,
    }
    checks += [dict(name=n,passed=v) for n,v in observations.items()]
    summary=dict(passed=all(c['passed'] for c in checks),checks=checks,nativeDllSha256=binary,
        nativePlayerRgb=colors(actual),offPlayerRgb=colors(off),changedPixelsByTick=pixels,
        scope='Synthetic native periodic/self light; real Lighting.AddLight/LightTiles/GetColor and player rendering. Native attenuation, not a fabricated light overlay. No item-quality or full-world parity claim.')
    (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
    return 0 if summary['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
