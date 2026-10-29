#!/usr/bin/env python3
"""Neutral sparse-support fixture: zero edge gap must not become visual approval."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from PIL import Image, ImageDraw
import workbench as w
from quality_review import report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--native-dll',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();dll=a.native_dll.resolve()
    if out.exists() and any(out.iterdir()):p.error('Use a fresh evidence directory')
    out.mkdir(parents=True,exist_ok=True);digest=w.digest(dll)
    subprocess.run([sys.executable,str(w.HERE/'verify_placed_render.py'),'--out',str(out/'baseline'),'--native-dll',str(dll),'--no-build'],cwd=w.ROOT,check=True)
    item=w.read_json(out/'baseline/synthetic-placed-art.json')
    image=Image.new('RGBA',(16,16));draw=ImageDraw.Draw(image)
    draw.rectangle((1,2,14,9),fill=(90,160,210,255));draw.rectangle((7,10,8,15),fill=(100,200,90,255))
    buffer=io.BytesIO();image.save(buffer,format='PNG');raw=buffer.getvalue()
    identity=json.dumps([item['id'],'item','',item['id']],separators=(',',':')).encode()
    name='infini_asset_png_'+hashlib.sha256(identity+b'\0'+raw).hexdigest()+'.png';asset=out/name;asset.write_bytes(raw)
    item['visual']['spritePath']=name
    for entity in item['runtimeProgram']['entities']:entity['visual']['spritePath']=name
    ip=out/'synthetic-support.json';ip.write_text(json.dumps(item))
    scene=w.read_json(out/'baseline/placed-render/scenario.json')
    scene['nativeRender'].update(artworkFiles=[str(asset)],drawDroppedItems=True)
    scene['ticks']=150;scene['world']['updateDroppedItems']=True
    # Native movement takes the player away after placing, preventing pickup UI
    # from replacing this intentionally focused settle-to-floor observation.
    scene['actions'] += [dict(tick=2,kind='controls',left=True,right=False,jump=False),dict(tick=45,kind='controls',left=False,right=False,jump=False)]
    sp=out/'scenario.json';sp.write_text(json.dumps(scene))
    result=subprocess.run([os.environ.get('DOTNET','dotnet'),str(dll),'--item',str(ip),'--scenario',str(sp),'--output',str(out/'native.json')],cwd=w.ROOT,capture_output=True,text=True,timeout=240)
    (out/'process.log').write_text(result.stdout+result.stderr);trace=w.read_json(out/'native.json')
    rows=[row for frame in trace.get('nativeRender',{}).get('placedBodyRendering',{}).get('frames',[]) for body in frame['draws'] for row in body['geometry']]
    drops=[drop for frame in trace.get('nativeRender',{}).get('frames',[]) for drop in frame.get('droppedItems',[])]
    world_items=[s['world']['returnedItems'][0] for s in trace.get('snapshots',[]) if s.get('world',{}).get('returnedItems') and s.get('phase') is None]
    floor=scene['tiles'][0]['tileY']*16
    checks={'nativePassed':result.returncode==0 and trace['status']=='passed',
            'zeroEdgeGapButMainBaseRaised':bool(rows) and all(abs(r['minimumGapPx'])<.001 and r['medianColumnGapPx']>=17.9 for r in rows),
            'sparseContactNotFullWidth':bool(rows) and all(0<r['contactColumnsWithin1Px']<r['contourColumns']/4 for r in rows),
            'neverVisualPass':bool(rows) and all(r['supportAssessment'].startswith('review_required') for r in rows),
            'droppedOriginalHookExecuted':bool(drops) and all(d['entrypoint']=='GeneratedItem.PreDrawInWorld' and d['draws'] for d in drops),
            'nativeDropMovedAndSettled':len(world_items)>10 and len({round(i['y'],3) for i in world_items})>2 and all(abs(i['y']+i['height']-floor)<.01 for i in world_items[-10:]),
            'binaryUnchanged':w.digest(dll)==digest}
    report(out/'native.json',out/'review',terrain=True)
    summary=dict(passed=all(checks.values()),checks=checks,nativeDllSha256=digest,visualVerdict='review_required',scope='Neutral synthetic support geometry and actual dropped hook; original Item.UpdateItem settling in explicit terrain; no full-world ecology, pickup UI or art approval')
    (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2));return int(not summary['passed'])

if __name__=='__main__':raise SystemExit(main())
