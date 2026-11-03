#!/usr/bin/env python3
"""Native historyRibbon draw, no-capture parity and refusal controls; no fake gameplay."""
import argparse
import copy
import hashlib
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
from typing import Any
from PIL import Image

import workbench as w
from native_review import native_frames


def current_vfx_slots() -> list[dict[str, Any]]:
    """Explicit synthetic current-wire controls; never edits an authored input."""
    trail=dict(id='current_history',entityId='root',event='periodic',rendererKind='historyTrail',
        anchor='self',layer='BeforeProjectiles',blend='alpha',slotSeed=1,
        trail=dict(draw='stroke',source='center',historyTicks=12,sampleStepTicks=1,firstSampleAgeTicks=0,
                   opacityProfile=dict(start=1,middle=0.5,end=0,curve='linear'),color=dict(r=80,g=180,b=255),widthPx=3))
    slots: list[dict[str, Any]]=[trail]
    for texture in ('solidPixel','star'):
        slots.append(dict(id='particle_'+texture.lower(),entityId='root',event='on_spawn',rendererKind='libraryParticle',
            anchor='self',layer='AfterProjectiles',blend='alpha',alpha=1,slotSeed=2,startTick=0,repeatEvery=0,duration=12,
            particle=dict(textureId=texture,sampling='point',count=2,speedMinPxPerTick=1,speedMaxPxPerTick=2,
                spreadRadians=1,inheritVelocity=0,drag=1,accelerationXPxPerTickSquared=0,accelerationYPxPerTickSquared=0,
                widthPx=8,heightPx=8,rotationRadians=0,rotationSpeedRadiansPerTick=0,
                colorStart=dict(r=255,g=200,b=80),colorEnd=dict(r=255,g=255,b=255),endScaleMultiplier=1,endOpacity=0)))
    return slots


def missing_selected_texture_root(source: Path, target: Path) -> Path:
    """Retain every library bootstrap resource; omit only the selected texel source."""
    shutil.copytree(source, target)
    (target / 'Assets/Textures/WhitePixel.png').unlink()
    return target


def current_vfx_checks(trace: dict[str, Any]) -> dict[str, bool]:
    """Independent detectors: emission/admission alone cannot certify rendering or hits."""
    render=trace.get('nativeRender',{})
    draws=[d for s in render.get('snapshots',[]) for d in s.get('activeProjectileVfx',{}).get('historyTrailDraws',[])]
    events=[e for s in trace.get('snapshots',[]) for e in s.get('events',[])]
    hostiles=[e for e in events if e.get('phase')=='controlled hostile NPC.UpdateNPC']
    hits=[e for e in events if e.get('kind')=='hit' and e.get('entityId')=='root' and e.get('npcId')==2]
    return {
        'current-trail-original-submissions':render.get('fullProjectilePreDrawExecuted') is True and bool(draws)
            and sum(d.get('submittedSegments',0) for d in draws)>0
            and all(d.get('nativeMagicPixel') is True and d.get('draw')=='stroke' and d.get('source')=='center' for d in draws),
        'current-selected-textures-ready':render.get('readyLibraryTexturePaths')==[
            'ParticleLibrary/Assets/Textures/WhitePixel','ParticleLibrary/Assets/Textures/Star'] and render.get('libraryBuffers')==4,
        'current-native-particles-started':any(s.get('particleCount',0)>0 for s in render.get('snapshots',[])),
        'controlled-hostile-update-restores-client':bool(hostiles) and all(e.get('dedServ') is True
            and e.get('restoredDedServ') is False and e.get('artworkRendered') is False for e in hostiles),
        'controlled-hostile-hit-remains-native-client':bool(hits) and all(e.get('dedServ') is False and e.get('damageDone',0)>0 for e in hits),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--no-build', action='store_true')
    parser.add_argument('--item', type=Path, help='Optional unchanged authored item for the same native VFX-only scene')
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Use a fresh evidence directory')
    w.native_executable(args.no_build)
    w.fixtures(out / 'fixtures', no_build=True)
    item = w.read_json(out / 'fixtures/synthetic-straight.json')
    item['vfxManifest']['slots'] = [dict(id='native_history', entityId='root', event='periodic',
        rendererKind='historyRibbon', anchor='self', layer='BeforeProjectiles', color=dict(r=80,g=180,b=255),
        alpha=1, blend='alpha', scale=2, density=0.5, spread=0, slotSeed=1, startTick=0,
        repeatEvery=1, duration=12, particleSystemId='none')]
    item_path = out / 'synthetic-history.json'
    item_path.write_text(json.dumps(item))
    stationary = copy.deepcopy(item)
    # Locate the authored primary projectile rather than relying on its array position.
    for entity in stationary['runtimeProgram']['entities']:
        if entity['id'] == stationary['runtimeProgram']['primaryEntityId']:
            entity['spawn']['speedPxPerTick'] = 0
    stationary_path = out / 'synthetic-stationary.json'
    stationary_path.write_text(json.dumps(stationary))
    scene: dict[str, Any] = dict(playerUpdate='client_vfx',ticks=100,seed=1,
        player=dict(x=800,y=700,mana=200),dummy=dict(x=840,y=900,life=10000),
        tiles=[dict(tileX=1,tileY=47,width=97,height=1)],
        actions=[dict(kind='primary',tick=0),dict(kind='release',tick=1)],
        assertions=[dict(kind='spawned'),dict(kind='no_nonfinite')],
        nativeRender=dict(width=512,height=384,cameraX=650,cameraY=550,capture=True,
                          drawProjectileVfx=True,drawNativeDust=True,lightingMode='viewport_fill'))
    cases=[('moving',item_path,scene,0,'',{}),('repeat',item_path,copy.deepcopy(scene),0,'',{}),
           ('stationary',stationary_path,copy.deepcopy(scene),0,'',{})]
    # Explicit synthetic publication for the complete native PreDraw route.
    # This fixture is separate from the optional unchanged authored item.
    buffer=io.BytesIO();Image.new('RGBA',(16,16),(220,220,220,255)).save(buffer,format='PNG')
    raw=buffer.getvalue();identity=json.dumps([item['id'],'item','',item['id']],separators=(',',':')).encode('ascii')
    png=out/('infini_asset_png_'+hashlib.sha256(identity+b'\0'+raw).hexdigest()+'.png');png.write_bytes(raw)
    artwork_item=copy.deepcopy(item)
    artwork_item['visual'].update(spritePath=png.name,spriteStatus='generated',renderSizePx=24,forwardAngleDegrees=0)
    for entity in artwork_item['runtimeProgram']['entities']:
        entity['visual'].update(assetMode='baked_sprite' if entity['kind']=='item_body' else 'reuse_item_icon',
                                spritePath=png.name,spriteStatus='generated')
    artwork_path=out/'synthetic-artwork.json';artwork_path.write_text(json.dumps(artwork_item))
    artwork_scene=copy.deepcopy(scene)
    artwork_scene['nativeRender'].update(drawArtwork=True,drawPlayer=True,drawProjectileVfx=False,artworkFiles=[str(png)])
    cases.append(('full-native-predraw',artwork_path,artwork_scene,0,'',{}))
    full_uncaptured=copy.deepcopy(artwork_scene);full_uncaptured['nativeRender']['capture']=False
    cases.append(('full-native-predraw-no-capture',artwork_path,full_uncaptured,0,'',{}))
    current=copy.deepcopy(artwork_item);current['vfxManifest']['slots']=current_vfx_slots()
    current_path=out/'synthetic-current-vfx.json';current_path.write_text(json.dumps(current))
    current_scene=copy.deepcopy(artwork_scene)
    current_scene['dummy']=dict(mode='native_training_dummy',tileX=60,tileY=44)
    current_scene['hostiles']=[dict(x=900,y=680,width=32,height=100,life=10000,vx=0.5)]
    current_scene['assertions'].append(dict(kind='entity_hit_count_at_least',entityId='root',npcId=2,value=1))
    cases.append(('current-trail-and-textures',current_path,current_scene,0,'',{}))
    current_nocap=copy.deepcopy(current_scene);current_nocap['nativeRender']['capture']=False
    cases.append(('current-no-capture',current_path,current_nocap,0,'',{}))
    partial=copy.deepcopy(artwork_scene);partial['nativeRender']['drawPlayer']=False;partial['nativeRender']['drawNativeDust']=False
    cases.append(('current-partial-predraw-refused',current_path,partial,2,'historyTrail requires',{}))
    cases.append(('current-procedural-only-refused',current_path,copy.deepcopy(scene),2,'historyTrail requires',{}))
    # Preserve ParticleLibrary's EmptyPixel/other bootstrap resources: only the
    # explicitly selected WhitePixel is absent in this owned negative fixture.
    source=Path(os.environ['INFINI_PARTICLE_ASSET_DIR'])
    missing_texture_root=missing_selected_texture_root(source,out/'missing-selected-texture')
    cases.append(('current-selected-texture-missing',current_path,current_scene,2,'Assets/Textures/WhitePixel',
                  {'INFINI_PARTICLE_ASSET_DIR':str(missing_texture_root)}))
    uncaptured=copy.deepcopy(scene);uncaptured['nativeRender']['capture']=False
    cases.append(('capture-disabled',item_path,uncaptured,0,'',{}))
    missing=copy.deepcopy(scene);missing['nativeRender']['drawProjectileVfx']=False;missing['nativeRender']['drawNativeDust']=False
    cases.append(('missing-draw-context',item_path,missing,2,'historyRibbon requires',{}))
    cases.append(('missing-native-assets',item_path,copy.deepcopy(scene),2,'',{'INFINI_PLAYER_ASSET_DIR':str(out/'missing-assets')}))
    if args.item:
        authored=copy.deepcopy(scene);authored['dummy']['y']=700
        authored['assertions']=[dict(kind='dummy_damaged'),dict(kind='no_nonfinite')]
        cases.append(('authored',args.item.resolve(),authored,0,'',{}))
    traces={};rows=[]
    for name,source,chosen,expected,reason,env in cases:
        path=out/(name+'-scenario.json');path.write_text(json.dumps(chosen))
        command=[sys.executable,str(w.HERE/'workbench.py'),'run','--item',str(source),'--scenario',str(path),
                 '--out',str(out/name),'--no-build','--review','none']
        result=subprocess.run(command,cwd=w.ROOT,env={**os.environ,**env},capture_output=True,text=True,timeout=240)
        trace=w.read_json(out/name/'native.json');traces[name]=trace
        rows.append(dict(name=name,passed=result.returncode==expected and trace['status']=={0:'passed',2:'error'}[expected]
                         and reason in trace.get('error',''),exitCode=result.returncode,error=trace.get('error')))
        (out/(name+'.process.log')).write_text(result.stdout+result.stderr)
    def check(name,value):rows.append(dict(name=name,passed=bool(value)))
    def ribbon(trace):
        return [d for s in trace.get('nativeRender',{}).get('snapshots',[])
                for d in s.get('activeProjectileVfx',{}).get('historyRibbonDraws',[])]
    moving=traces['moving'];records=ribbon(moving)
    check('original-native-segments-submitted',bool(records) and sum(r['submittedSegments'] for r in records)>0
          and all(r['nativeMagicPixel'] and r['historyCount']<=20 for r in records))
    check('stationary-history-does-not-fabricate-lines',bool(ribbon(traces['stationary']))
          and sum(r['submittedSegments'] for r in ribbon(traces['stationary']))==0)
    check('capture-does-not-change-native-gameplay',moving['snapshots']==traces['capture-disabled']['snapshots'])
    check('capture-does-not-change-live-history-or-segments',ribbon(moving)==ribbon(traces['capture-disabled']))
    check('no-capture-still-executes-gpu',traces['capture-disabled']['nativeRender']['gpuRenderLifecycleExecuted']
          and not traces['capture-disabled']['nativeRender']['frames'])
    check('repeat-native-gameplay-and-history',moving['snapshots']==traces['repeat']['snapshots']
          and records==ribbon(traces['repeat']))
    check('repeat-pixels',[f['sha256'] for f in moving['nativeRender']['frames']]
          ==[f['sha256'] for f in traces['repeat']['nativeRender']['frames']])
    full=traces['full-native-predraw']
    check('full-native-predraw-ribbon',full.get('nativeRender',{}).get('fullProjectilePreDrawExecuted') is True
          and sum(r['submittedSegments'] for r in ribbon(full))>0)
    full_nocap=traces['full-native-predraw-no-capture']
    check('full-predraw-capture-independent',full['snapshots']==full_nocap['snapshots'] and ribbon(full)==ribbon(full_nocap)
          and full_nocap['nativeRender']['gpuRenderLifecycleEnabled'] and full_nocap['nativeRender']['gpuRenderLifecycleExecuted']
          and not full_nocap['nativeRender']['frames'])
    current=traces['current-trail-and-textures'];nocap=traces['current-no-capture']
    for name,value in current_vfx_checks(current).items():check(name,value)
    check('current-capture-independent-gameplay-and-draws',current['snapshots']==nocap['snapshots']
          and current['nativeRender']['snapshots']==nocap['nativeRender']['snapshots']
          and nocap['nativeRender']['gpuRenderLifecycleExecuted'] and not nocap['nativeRender']['frames'])
    for name,trace in traces.items():
        if trace['status']=='error':continue
        frames=native_frames(trace,out/name/'native.json') if trace['nativeRender']['frames'] else []
        check(name+'-finite-recorded-pixels',not trace['nativeRender']['capture'] or bool(frames))
    if args.item:
        check('authored-bytes-preserved',w.digest(args.item)==w.digest(out/'authored/item.json'))
        check('authored-original-ribbon-executed',sum(r['submittedSegments'] for r in ribbon(traces['authored']))>0)
    summary=dict(passed=all(r['passed'] for r in rows),fullGameParity=False,
                 scope='Original native projectile history/VFX; explicit procedural-only and full player/artwork cases; controlled hostiles unrendered, no complete world parity',checks=rows)
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
    return 0 if summary['passed'] else 1


if __name__=='__main__':
    sys.exit(main())
