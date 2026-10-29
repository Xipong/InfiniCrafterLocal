#!/usr/bin/env python3
"""Compact native visual review: original frames + labeled geometry, never an art PASS."""
from __future__ import annotations
import argparse
import copy
import html
import json
import math
import os
from pathlib import Path
import subprocess
import shutil
from PIL import Image, ImageDraw
import workbench as w


def variants(base, hold_ticks, equipment=False):
    """Four bounded scenes; native Player.Update owns movement, jump and gravity."""
    if base.get('playerUpdate') != 'client_vfx' or not base.get('nativeRender', {}).get('drawPlayer'):
        raise ValueError('Use a proven client_vfx scene with drawPlayer and explicit art/assets/ammo')
    ticks = base['ticks']
    if not equipment and not 1 <= hold_ticks < ticks:
        raise ValueError('hold_ticks must be positive and earlier than scene end')
    for direction in (1, -1):
        for moving in (False, True):
            scene = copy.deepcopy(base)
            scene['player']['direction'] = direction
            # Preserve explicit environmental/equipment/world stimuli, not old input shortcuts.
            scene['actions'] = [a for a in scene['actions'] if a['kind'] not in {'primary', 'alt', 'release', 'controls', 'equip', 'unequip', 'vanity'}]
            for action in scene['actions']:
                if action['kind'] == 'aim' and direction == -1:
                    action['x'] = 2 * (scene['player']['x'] + 10) - action['x']
            if not any(a['kind']=='aim' and a['tick']==0 for a in scene['actions']):
                scene['actions'].insert(0,dict(tick=0,kind='aim',x=scene['player']['x']+10+direction*200,y=scene['player']['y']+21))
            scene['actions'] += ([{'tick': 0, 'kind': 'equip'}] if equipment else [
                {'tick': 0, 'kind': 'primary'}, {'tick': hold_ticks, 'kind': 'release'}])
            if moving:
                scene['actions'] += [dict(tick=2, kind='controls', left=direction < 0, right=direction > 0, jump=True),
                                     dict(tick=min(ticks-1, 12), kind='controls', left=False, right=False, jump=False)]
            scene['actions'].sort(key=lambda a: a['tick'])
            # Old item-specific counts/timing cannot be inherited after changing input.
            scene['assertions'] = [{'kind': 'no_nonfinite'}]
            yield ('right' if direction == 1 else 'left') + ('-move-jump' if moving else '-idle'), scene


def geometry_rows(frame, placed):
    yield from frame.get('heldGeometry', [])
    yield from frame.get('projectileGeometry', [])
    for drop in frame.get('droppedItems', []):
        yield from drop.get('draws', [])
    for body in placed:
        yield from body.get('geometry', [])


def summarize(trace):
    frames = trace.get('nativeRender', {}).get('frames', [])
    grips = [r['gripDistancePx'] for f in frames for r in geometry_rows(f, []) if isinstance(r.get('gripDistancePx'),(int,float))]
    states = [f.get('visualReview', {}) for f in frames]
    return {'nativeStatus': trace.get('status', 'notRun'), 'error': trace.get('error'),
            'renderedFrames': len(frames), 'visualVerdict': 'review_required',
            'maxObservedGripDistancePx': max(grips) if grips else None,
            'facingObserved': sorted({s['direction'] for s in states if 'direction' in s}),
            'activeFacingObserved': sorted({s['direction'] for s in states if 'direction' in s and (s.get('controlUseItem') or s.get('itemAnimation',0)>0)}),
            'gravityObserved': sorted({s['gravityDirection'] for s in states if 'gravityDirection' in s}),
            'useHeldFrames': sum(s.get('controlUseItem') is True for s in states),
            'movingFrames': sum(abs(s.get('velocity', {}).get('x', 0)) > .01 for s in states),
            'airborneMotionFrames': sum(abs(s.get('velocity', {}).get('y', 0)) > .01 for s in states),
            'scope': 'Distances are observations, not universal grip failures. Authored reach may intentionally detach. Input hold and ammo must be inspected independently.'}


def report(trace_path, out, terrain=False):
    trace_path = Path(trace_path).resolve();trace = w.read_json(trace_path)
    out = Path(out).resolve();out.mkdir(parents=True, exist_ok=True)
    render = trace.get('nativeRender', {});frames = render.get('frames', [])
    placed = {f['tick']: f['draws'] for f in render.get('placedBodyRendering', {}).get('frames', [])}
    # Include lifecycle endpoints and peak measured separation; not every screenshot.
    chosen = {0, len(frames)//4, len(frames)//2, 3*len(frames)//4, len(frames)-1}
    if frames:
        chosen.add(max(range(len(frames)), key=lambda i: max([(r.get('gripDistancePx') or 0) for r in geometry_rows(frames[i], [])] or [0])))
    cards=[]
    for index in sorted(i for i in chosen if 0 <= i < len(frames)):
        frame=frames[index];source=(trace_path.parent/frame['path']).resolve()
        if not source.is_relative_to(trace_path.parent) or w.digest(source) != frame['sha256']:
            raise ValueError('Frame path escaped trace or PNG hash changed')
        with Image.open(source) as image: native=image.convert('RGB')
        shutil.copyfile(source,out/f"{frame['tick']:06d}-native.png")
        marked=native.copy();draw=ImageDraw.Draw(marked)
        cx,cy=render.get('cameraX',0),render.get('cameraY',0);zoom=render.get('zoom',1)
        def point(x,y):return ((x-cx-native.width/2)*zoom+native.width/2,(y-cy-native.height/2)*zoom+native.height/2)
        def cross(p,color):
            x,y=point(p['x'],p['y']);draw.line((x-4,y,x+4,y),fill=color,width=1);draw.line((x,y-4,x,y+4),fill=color,width=1)
        def box(r,color):
            a=point(r['x'],r['y']);b=point(r['x']+r['width'],r['y']+r['height']);draw.rectangle((*a,*b),outline=color)
        if terrain:
            # Schematic overlay only; never exported as the original native frame.
            for tile in trace.get('scene',{}).get('tiles',[]):box(tile,'#705236')
        state=frame.get('visualReview',{})
        if 'collider' in state:box(state['collider'],'#55ddff')
        if 'nativeRenderedFrontHand' in state:cross(state['nativeRenderedFrontHand'],'#00ff80')
        elif 'nativeFrontHand' in state:cross(state['nativeFrontHand'],'#00ff80')
        for body in placed.get(frame['tick'],[]):box(dict(x=body['footprintX'],y=body['footprintY'],width=body['footprintWidth'],height=body['footprintHeight']),'#ffcc33')
        for drop in frame.get('droppedItems',[]):box(drop['collider'],'#ffcc33')
        rows=list(geometry_rows(frame,placed.get(frame['tick'],[])))
        for row in rows:
            if 'authoredGrip' in row:cross(row['authoredGrip'],'#ff55cc')
            if 'collider' in row:box(row['collider'],'#ffcc33')
            contour=row.get('supportContour',[])
            if len(contour)>1:draw.line([point(c['x']+.5,c['bottomY']) for c in contour],fill='#ff9933',width=1)
        for entry in frame.get('equipmentOverlayDrawData',[]):
            cross({'x':entry['positionX']+cx,'y':entry['positionY']+cy},'#ff55cc')
        marked.save(out/f"{frame['tick']:06d}-diagnostic.png")
        cards.append(f'<h3>Tick {frame["tick"]}</h3><img src="{frame["tick"]:06d}-native.png" alt="Original native render"><img src="{frame["tick"]:06d}-diagnostic.png" alt="Diagnostic geometry overlay"><details><summary>Observed geometry / support / input</summary><pre>{html.escape(json.dumps(dict(player=state,geometry=rows,equipment=frame.get("equipmentOverlayDrawData",[])),indent=2))}</pre></details>')
    summary=summarize(trace);(out/'summary.json').write_text(json.dumps(summary,indent=2))
    text='''<!doctype html><meta charset="utf-8"><title>Native item quality review</title><style>body{background:#20242c;color:#eee;font:16px system-ui;max-width:1200px;margin:24px auto}img{max-width:48%;image-rendering:pixelated}pre{white-space:pre-wrap;overflow-wrap:anywhere}details{margin:1em 0}</style><h1>Native item quality review — human/vision review required</h1><p>Left: original hash-verified native PNG. Right: diagnostic overlay. Green: native composite hand getter (not authoritative for ordinary frame arms); pink: authored grip or equipment draw anchor; blue: player collider; yellow: item collider/placement footprint; orange: alpha support envelope. No visibility or zero-gap aesthetic PASS.</p>'''
    text+=('<p><b>CONTEXT REFERENCE ONLY:</b> brown rectangles show configured terrain boundaries, not Terraria world pixels. Full-world rendering was not run.</p>' if terrain else '<p>Neutral native background; full-world terrain rendering not run.</p>')
    text+='<pre>'+html.escape(json.dumps(summary,indent=2))+'</pre>'+''.join(cards)
    (out/'index.html').write_text(text)
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    view=sub.add_parser('report');view.add_argument('trace',type=Path);view.add_argument('--out',type=Path,required=True);view.add_argument('--terrain-reference',action='store_true')
    run=sub.add_parser('cycle');run.add_argument('--item',type=Path,required=True);run.add_argument('--scenario',type=Path,required=True);run.add_argument('--native-dll',type=Path,required=True);run.add_argument('--out',type=Path,required=True);run.add_argument('--hold-ticks',type=int,required=True);run.add_argument('--equipment',action='store_true');run.add_argument('--item-boundary',choices=['fresh','local_cache'],default='local_cache')
    a=p.parse_args()
    if a.command=='report':print(json.dumps(report(a.trace,a.out,a.terrain_reference),indent=2));return 0
    if a.out.exists() and any(a.out.iterdir()):p.error('Use a fresh output directory')
    a.out.mkdir(parents=True,exist_ok=True);dll=a.native_dll.resolve();digest=w.digest(dll);item_digest=w.digest(a.item);cases=[]
    for name,scene in variants(w.read_json(a.scenario),a.hold_ticks,a.equipment):
        folder=a.out/name;folder.mkdir();sp=folder/'scenario.json';sp.write_text(json.dumps(scene,indent=2));target=folder/'native.json'
        result=subprocess.run([os.environ.get('DOTNET','dotnet'),str(dll),'--item',str(a.item.resolve()),'--scenario',str(sp.resolve()),'--output',str(target.resolve()),'--item-boundary',a.item_boundary],cwd=w.ROOT,capture_output=True,text=True,timeout=300)
        (folder/'process.log').write_text(result.stdout+result.stderr)
        summary=report(target,folder/'review') if target.exists() else {'nativeStatus':'notRun','error':result.stderr}
        cases.append(dict(name=name,exitCode=result.returncode,requestedFacing=scene['player']['direction'],requestedFacingObserved=(summary.get('facingObserved',[]) if a.equipment else summary.get('activeFacingObserved',[]))==[scene['player']['direction']],**summary))
        if w.digest(dll)!=digest or w.digest(a.item)!=item_digest:raise RuntimeError('Native executable or item changed during review')
    summary=dict(cases=cases,nativeDllSha256=digest,itemSha256=item_digest,visualVerdict='review_required',invertedGravity='notRun: supply an explicit separate native scene; do not infer from normal gravity')
    (a.out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2));return int(any(c['exitCode']!=0 or not c['requestedFacingObserved'] for c in cases))

if __name__=='__main__':raise SystemExit(main())
