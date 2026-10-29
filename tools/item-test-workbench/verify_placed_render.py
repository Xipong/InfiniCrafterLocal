#!/usr/bin/env python3
"""Synthetic native placed-body rendering, retirement and missing-path controls."""
import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
from PIL import Image
import workbench as w


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--no-build',action='store_true')
    parser.add_argument('--native-dll',type=Path,help='Explicit direct binary; no standard-wrapper provenance claim')
    args=parser.parse_args();out=args.out.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit('Use a fresh evidence directory')
    if args.native_dll and not args.no_build:raise SystemExit('--native-dll requires --no-build')
    out.mkdir(parents=True,exist_ok=True)
    if not args.no_build:w.build()
    dll=(args.native_dll or w.HERE/'bin/Release/net8.0/ItemTestWorkbench.dll').resolve();binary=w.digest(dll)
    command=[os.environ.get('DOTNET','dotnet'),str(dll)];fixtures=out/'fixtures'
    subprocess.run(command+['--write-fixtures',str(fixtures)],cwd=w.ROOT,check=True)
    item=w.read_json(fixtures/'synthetic-world-campfire.json')
    buf=io.BytesIO();Image.new('RGBA',(16,16),(80,180,240,255)).save(buf,format='PNG');raw=buf.getvalue()
    identity=[item['id'],'item','',item['id']]
    name='infini_asset_png_'+hashlib.sha256(json.dumps(identity,separators=(',',':')).encode()+b'\0'+raw).hexdigest()+'.png'
    asset=out/name;asset.write_bytes(raw)
    item['visual'].update(spritePath=name,spriteStatus='generated',renderSizePx=24,preferredCanvasSize=24,forwardAngleDegrees=0)
    for entity in item['runtimeProgram']['entities']:entity['visual'].update(assetMode='baked_sprite',spritePath=name,spriteStatus='generated')
    item['runtimeProgram']['bindings'][0]['usePolicy']['action']['placement']['placedBody']=dict(renderSizePx=48,footprintAnchorX=.5,footprintAnchorY=1,imagePivotX=.5,imagePivotY=1,offsetXPx=0,offsetYPx=0,rotationDegrees=0,flipX=False,flipY=False,pivotSpace='alpha_bounds')
    path=out/'synthetic-placed-art.json';path.write_text(json.dumps(item))
    scene=w.read_json(w.HERE/'scenarios/world-placement.json');scene['playerUpdate']='client_vfx'
    for actor in ['player','dummy']:scene[actor]['y']+=800
    for tile in scene['tiles']:tile['tileY']+=50
    for tile in scene['world']['trackTiles']:tile['tileY']+=50
    for action in scene['actions']:
        if 'tileY' in action:action['tileY']+=50
    for check in scene['assertions']:
        if 'tileY' in check:check['tileY']+=50
    scene['assertions'].append(dict(kind='placed_body_draw_count_at_least',minimum=1))
    scene['nativeRender']=dict(width=512,height=512,cameraX=600,cameraY=1200,zoom=1,capture=True,drawArtwork=True,drawPlacedBodies=True,lightingMode='viewport_fill',artworkFiles=[str(asset)])
    wrong=copy.deepcopy(scene);wrong['assertions']=[dict(kind='placed_body_draw_count_at_least',minimum=1000)]
    missing=copy.deepcopy(scene);missing['nativeRender']['artworkFiles']=[]
    rows=[]
    for label,s,expected,reason in [('placed-render',scene,0,''),('negative-draw-count',wrong,1,''),('missing-png',missing,2,'Missing explicit artwork file')]:
        folder=out/label;folder.mkdir();sp=folder/'scenario.json';sp.write_text(json.dumps(s,indent=2))
        result=subprocess.run(command+['--item',str(path),'--scenario',str(sp),'--output',str(folder/'native.json')],cwd=w.ROOT,capture_output=True,text=True,timeout=180)
        (folder/'process.log').write_text(result.stdout+result.stderr);trace=w.read_json(folder/'native.json')
        failed=[a['name'] for a in trace.get('assertions',[]) if a['status']=='failed']
        ok=w.digest(dll)==binary and result.returncode==expected and trace['status']=={0:'passed',1:'failed',2:'error'}[expected] and reason in trace.get('error','')
        if expected==1:ok=ok and failed==['placed_body_draw_count_at_least']
        if expected==0:
            frames=trace.get('nativeRender',{}).get('placedBodyRendering',{}).get('frames',[])
            ok=ok and any(a['nativeDrawReturned'] for f in frames for a in f['draws']) and bool(frames) and not frames[-1]['draws']
        rows.append(dict(name=label,passed=ok,exitCode=result.returncode,failedAssertions=failed));print(rows[-1],flush=True)
    summary=dict(passed=all(r['passed'] for r in rows),cases=rows,nativeDllSha256=binary,scope='Synthetic original placed-body renderer and native ledger retirement; no full-world or authored visual approval')
    (out/'summary.json').write_text(json.dumps(summary,indent=2));return 0 if summary['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
