#!/usr/bin/env python3
"""Original vanilla PlayerRenderer controls: both facings, no generated replacement."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import workbench as w
from quality_review import report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native-dll',type=Path,required=True);p.add_argument('--vanilla-assets',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();dll=a.native_dll.resolve();digest=w.digest(dll)
    if out.exists() and any(out.iterdir()):p.error('Use a fresh evidence directory')
    out.mkdir(parents=True,exist_ok=True);results=[]
    for name in ('Minishark','Musket'):
        for direction in (1,-1):
            folder=out/(name+('-right' if direction==1 else '-left'));folder.mkdir()
            scene=dict(playerUpdate='client_vfx',ticks=45,seed=1,vanillaAssetRoot=str(a.vanilla_assets.resolve()),
                player=dict(x=800,y=710,direction=direction,life=100,mana=200,manaCrystals=9),dummy=dict(x=1100,y=710,life=1000000),
                inventory=[dict(slot=54,itemId=97,stack=99)],tiles=[dict(tileX=1,tileY=47,width=97,height=1)],
                actions=[dict(tick=0,kind='aim',x=810+direction*200,y=732),dict(tick=0,kind='primary'),dict(tick=30,kind='release')],
                assertions=[dict(kind='no_nonfinite')],nativeRender=dict(width=512,height=384,cameraX=565,cameraY=540,zoom=2,capture=True,drawArtwork=True,drawPlayer=True,drawNativeDust=True,lightingMode='viewport_fill',artworkFiles=[]))
            sp=folder/'scenario.json';sp.write_text(json.dumps(scene,indent=2));tp=folder/'native.json'
            process=subprocess.run([os.environ.get('DOTNET','dotnet'),str(dll),'--vanilla-item',name,'--scenario',str(sp),'--output',str(tp)],cwd=w.ROOT,capture_output=True,text=True,timeout=180)
            (folder/'process.log').write_text(process.stdout+process.stderr);trace=w.read_json(tp);frames=trace.get('nativeRender',{}).get('frames',[])
            geometry=[r for f in frames for r in f.get('heldGeometry',[])]
            checks=dict(nativePassed=process.returncode==0 and trace['status']=='passed',
                exactFacing=len(frames)==45 and all(f['visualReview']['direction']==direction for f in frames),
                nativeVanillaDraw=bool(geometry) and all(r['kind']=='vanilla_held_item' and 'authoredGrip' not in r for r in geometry),
                noGeneratedReplacement=bool(frames) and all(f['nativeProxyVetoCount']==0 and f.get('nativeGeneratedHeldDrawDataCount',0)==0 for f in frames),
                pixelsIntact=bool(frames) and all(w.digest(folder/f['path'])==f['sha256'] for f in frames),binaryUnchanged=w.digest(dll)==digest)
            report(tp,folder/'review');results.append(dict(name=folder.name,checks=checks,passed=all(checks.values())));print(results[-1],flush=True)
    summary=dict(passed=all(r['passed'] for r in results),cases=results,nativeDllSha256=digest,scope='Actual vanilla player/item draw; native projectile simulation and dust, but bullet sprites not rendered; no inferred vanilla grip or aesthetic verdict')
    (out/'summary.json').write_text(json.dumps(summary,indent=2));return int(not summary['passed'])

if __name__=='__main__':raise SystemExit(main())
