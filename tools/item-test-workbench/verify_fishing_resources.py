#!/usr/bin/env python3
"""Native fishing render resource admission; exact PNGs, no catch selection or downloads."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import workbench as w
from verify_native_fishing import scene


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-dll',required=True,type=Path)
    parser.add_argument('--assets',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    dll=args.native_dll.resolve();before=w.native_binaries_state(dll);assets=args.assets.resolve()
    base=scene();base.update(playerUpdate='client_vfx',ticks=12,vanillaAssetRoot=str(assets))
    base['nativeRender']=dict(capture=True,width=640,height=360,cameraX=700,cameraY=650,
        lightingMode='viewport_fill',drawArtwork=True,drawPlayer=True,artworkFiles=[],
        drawVanillaProjectiles=True,vanillaItemTextures=[2290])
    checks=[]
    for name in ('loaded','missing','corrupt','too_many','duplicate','without_projectile_draw'):
        directory=out/name;directory.mkdir();s=copy.deepcopy(base)
        if name in ('missing','corrupt'):
            copied=directory/'assets';shutil.copytree(assets,copied);png=copied/'Images/Item_2290.png'
            if name=='missing':png.unlink()
            else:png.write_bytes(b'not a PNG')
            s['vanillaAssetRoot']=str(copied)
        if name=='too_many':s['nativeRender']['vanillaItemTextures']=list(range(1,18))
        if name=='duplicate':s['nativeRender']['vanillaItemTextures']=[2290,2290]
        if name=='without_projectile_draw':s['nativeRender']['drawVanillaProjectiles']=False
        (directory/'scenario.json').write_text(json.dumps(s))
        p=subprocess.run([os.environ.get('DOTNET','dotnet'),str(dll),'--vanilla-item','2289','--scenario',str(directory/'scenario.json'),'--output',str(directory/'native.json')],cwd=w.ROOT,capture_output=True,text=True,timeout=120)
        (directory/'process.log').write_text(p.stdout+p.stderr)
        trace=w.read_json(directory/'native.json') if (directory/'native.json').exists() else {}
        frames=trace.get('nativeRender',{}).get('frames',[])
        if name=='loaded':
            resources=trace.get('nativeRender',{}).get('vanillaProjectileAssets',{}).get('textures',[])
            passed=p.returncode==0 and trace.get('status')=='passed' and len(frames)==12 and any(Path(r.get('path','')).name=='Item_2290.png' for r in resources)
            # A declared fish texture is not an inventory grant.
            passed=passed and not any(i['type']==2290 for state in trace.get('fishing',{}).get('observations',[]) for i in state.get('inventory',[]))
        else:
            error=trace.get('error',p.stderr)
            cause={'missing':'FileNotFoundException: Missing native item PNG','corrupt':'InvalidDataException: Vanilla item PNG size differs from pinned source'}.get(name,'ArgumentException: vanillaItemTextures')
            passed=p.returncode==2 and not frames and cause in error
        checks.append(dict(name=name,passed=passed,exit=p.returncode,frames=len(frames)));print(name,passed,flush=True)
    unchanged=w.native_binaries_state(dll)==before
    summary=dict(passed=unchanged and all(c['passed'] for c in checks),checks=checks,binaryUnchanged=unchanged,nativeDllSha256=w.digest(dll))
    (out/'summary.json').write_text(json.dumps(summary,indent=2));return 0 if summary['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
