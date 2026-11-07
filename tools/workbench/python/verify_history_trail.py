#!/usr/bin/env python3
"""Current native historyTrail draw, no-capture parity and refusal controls; no fake gameplay."""
# Direct script entrypoints resolve the same package as workbench.py.
if __package__ in (None, ""):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import copy
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
from python.native_review import native_frames


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
            particle=dict(spawn=dict(shape='point'),textureId=texture,sampling='point',count=2,speedMinPxPerTick=1,speedMaxPxPerTick=2,
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
            and all(d.get('nativeMagicPixel') is True and d.get('draw')=='stroke' and d.get('source')=='center'
                    and isinstance(d.get('geometry'),list) and len(d['geometry'])==d.get('submittedSegments') for d in draws),
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
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Use a fresh evidence directory')
    w.native_executable(args.no_build)
    w.fixtures(out / 'fixtures', no_build=True)
    item = w.read_json(out / 'fixtures/synthetic-straight.json')
    item['vfxManifest']['slots'] = [current_vfx_slots()[0]]
    scene: dict[str, Any] = dict(playerUpdate='client_vfx',ticks=100,seed=1,
        player=dict(x=800,y=700,mana=200),dummy=dict(x=840,y=900,life=10000),
        tiles=[dict(tileX=1,tileY=47,width=97,height=1)],
        actions=[dict(kind='primary',tick=0),dict(kind='release',tick=1)],
        assertions=[dict(kind='spawned'),dict(kind='no_nonfinite')],
        nativeRender=dict(width=512,height=384,cameraX=650,cameraY=550,capture=True,
                          drawProjectileVfx=True,drawNativeDust=True,lightingMode='viewport_fill'))
    cases = []
    # Explicit synthetic publication for the complete native PreDraw route.
    # All generated artwork here belongs only to the explicit synthetic controls.
    buffer=io.BytesIO();Image.new('RGBA',(16,16),(220,220,220,255)).save(buffer,format='PNG')
    raw=buffer.getvalue();identity=json.dumps([item['id'],'item','',item['id']],separators=(',',':')).encode('ascii')
    png=w.publish_artwork(out,item,'item',identity,raw)
    artwork_item=copy.deepcopy(item)
    artwork_item['visual'].update(spritePath=png.name,spriteStatus='generated',renderSizePx=24,forwardAngleDegrees=0)
    for entity in artwork_item['runtimeProgram']['entities']:
        entity['visual'].update(assetMode='baked_sprite' if entity['kind']=='item_body' else 'reuse_item_icon',
                                spritePath=png.name,spriteStatus='generated')
    artwork_path=out/'synthetic-artwork.json';artwork_path.write_text(json.dumps(artwork_item))
    artwork_scene=copy.deepcopy(scene)
    artwork_scene['nativeRender'].update(drawArtwork=True,drawPlayer=True,drawProjectileVfx=False,artworkFiles=[str(png)])
    cases += [('moving',artwork_path,artwork_scene,0,'',{}),
              ('repeat',artwork_path,copy.deepcopy(artwork_scene),0,'',{})]
    stationary=copy.deepcopy(artwork_item)
    for entity in stationary['runtimeProgram']['entities']:
        if entity['id']==stationary['runtimeProgram']['primaryEntityId']:
            entity['spawn']['speedPxPerTick']=0
    stationary_path=out/'synthetic-stationary.json';stationary_path.write_text(json.dumps(stationary))
    cases.append(('stationary',stationary_path,copy.deepcopy(artwork_scene),0,'',{}))
    uncaptured=copy.deepcopy(artwork_scene);uncaptured['nativeRender']['capture']=False
    cases.append(('capture-disabled',artwork_path,uncaptured,0,'',{}))
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
    cases.append(('missing-native-assets',artwork_path,copy.deepcopy(artwork_scene),2,'',
                  {'INFINI_PLAYER_ASSET_DIR':str(out/'missing-assets')}))
    traces={};rows=[]
    for name,source,chosen,expected,reason,env in cases:
        path=out/(name+'-scenario.json');path.write_text(json.dumps(chosen))
        command=[sys.executable,str(w.HERE/'workbench.py'),'run','--item',str(source),'--scenario',str(path),
                 '--out',str(out/name),'--no-build','--review','none']
        result=subprocess.run(command,cwd=w.ROOT,env={**os.environ,**env},capture_output=True,text=True,timeout=240)
        trace=w.read_native_json(out/name/'native.json');traces[name]=trace
        rows.append(dict(name=name,passed=result.returncode==expected and trace['status']=={0:'passed',2:'error'}[expected]
                         and reason in trace.get('error',''),exitCode=result.returncode,error=trace.get('error')))
        (out/(name+'.process.log')).write_text(result.stdout+result.stderr)
    def check(name,value):rows.append(dict(name=name,passed=bool(value)))
    def trails(trace: dict[str, Any]):
        return [d for s in trace.get('nativeRender',{}).get('snapshots',[])
                for d in s.get('activeProjectileVfx',{}).get('historyTrailDraws',[])]
    moving=traces['moving'];records=trails(moving)
    check('original-native-segments-submitted',bool(records) and sum(r['submittedSegments'] for r in records)>0
          and all(r['nativeMagicPixel'] and len(r['geometry'])==r['submittedSegments'] for r in records))
    check('stationary-history-does-not-fabricate-lines',bool(trails(traces['stationary']))
          and sum(r['submittedSegments'] for r in trails(traces['stationary']))==0)
    check('capture-does-not-change-native-gameplay',moving['snapshots']==traces['capture-disabled']['snapshots'])
    check('capture-does-not-change-live-trail-or-segments',records==trails(traces['capture-disabled']))
    check('no-capture-still-executes-gpu',traces['capture-disabled']['nativeRender']['gpuRenderLifecycleExecuted']
          and not traces['capture-disabled']['nativeRender']['frames'])
    check('repeat-native-gameplay-and-trail',moving['snapshots']==traces['repeat']['snapshots']
          and records==trails(traces['repeat']))
    check('repeat-pixels',[f['sha256'] for f in moving['nativeRender']['frames']]
          ==[f['sha256'] for f in traces['repeat']['nativeRender']['frames']])
    check('full-native-predraw-trail',moving.get('nativeRender',{}).get('fullProjectilePreDrawExecuted') is True)
    current=traces['current-trail-and-textures'];nocap=traces['current-no-capture']
    for name,value in current_vfx_checks(current).items():check(name,value)
    check('current-capture-independent-gameplay-and-draws',current['snapshots']==nocap['snapshots']
          and current['nativeRender']['snapshots']==nocap['nativeRender']['snapshots']
          and nocap['nativeRender']['gpuRenderLifecycleExecuted'] and not nocap['nativeRender']['frames'])
    for name,trace in traces.items():
        if trace['status']=='error':continue
        frames=native_frames(trace,out/name/'native.json') if trace['nativeRender']['frames'] else []
        check(name+'-finite-recorded-pixels',not trace['nativeRender']['capture'] or bool(frames))
    summary=dict(passed=all(r['passed'] for r in rows),fullGameParity=False,
                 scope='Original current projectile historyTrail/VFX; full player/artwork and procedural refusal controls; controlled hostiles unrendered, no complete world parity',checks=rows)
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
    return 0 if summary['passed'] else 1


if __name__=='__main__':
    sys.exit(main())
