#!/usr/bin/env python3
"""Synthetic native air-jump registration, held impulse and on_jump render controls.

No model calls or game launch. --render executes offscreen FNA and requires the
ordinary stand resource environment. Generated art below is explicit fixture data,
never a fallback for an authored item. Each case runs in its own native process.
"""
# Direct script entrypoints resolve the same package as workbench.py.
if __package__ in (None, ""):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import copy
import io
import json
from pathlib import Path
import subprocess
from typing import Any

import workbench as w


def prepare(out: Path, render: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    item = w.read_json(w.HERE / 'fixtures/synthetic-reaction-accessory.json')
    item.update(id='workbench-synthetic-air-jump', name='Synthetic native air jump')
    item['runtimeProgram']['entities'][0]['events'] = []
    item['runtimeProgram'].pop('effectGroups', None)
    item['accessory'] = dict(enabled=True, playerEffect=dict(airJump=dict(
        count=2, launchSpeedPxPerTick=9.25, holdDurationTicks=4,
        horizontalAccelerationMultiplier=1.5, horizontalSpeedMultiplier=2)))
    item['visual']['spritePath'] = 'synthetic-unused-in-cpu.png'
    item['vfxManifest'] = dict(schema='infini.vfx.runtime-events.v16', recipeId=item['id'],
        budget=dict(maxParticlesPerTick=80, maxParticlesTotal=3400, maxDrawCalls=136), slots=[])
    scene: dict[str, Any] = dict(playerUpdate='full', ticks=100, seed=1,
        player=dict(x=800, y=1558, mana=200), dummy=dict(x=1200, y=1558, life=10000),
        # Stay below native top-world margin (656px), leaving genuine headroom.
        tiles=[dict(tileX=1, tileY=100, width=97, height=1)],
        actions=[dict(kind='equip', tick=0)], assertions=[dict(kind='no_nonfinite'), dict(kind='spawn_count', value=0)])
    for tick, jump in [(5, True), (9, False), (15, True), (20, False), (25, True), (30, False), (35, True), (40, False)]:
        scene['actions'].append(dict(kind='controls', tick=tick, left=False, right=False, jump=jump))
    if render:
        from PIL import Image, ImageDraw
        import hashlib
        files = []
        for role, suffix, size in [('item', '', (16, 16)), ('equip_overlay', '_equip_overlay', (8, 8))]:
            image = Image.new('RGBA', size)
            ImageDraw.Draw(image).ellipse((0, 0, size[0]-1, size[1]-1), outline=(80, 200, 255, 255), width=2)
            buffer = io.BytesIO(); image.save(buffer, format='PNG'); raw = buffer.getvalue()
            identity = json.dumps([item['id'], role, '', item['id']+suffix], separators=(',', ':')).encode('ascii')
            scope = json.dumps([item['recipeMeta']['worldId'], item['id'], role], separators=(',', ':')).encode('ascii')
            path = out / (role+'--'+hashlib.sha256(scope+b'\0'+identity+b'\0'+raw).hexdigest()+'.png')
            path.write_bytes(raw); files.append(str(path))
        item['visual'].update(spritePath=Path(files[0]).name, spriteStatus='generated', renderSizePx=16,
                              forwardAngleDegrees=0, equipOverlayPath=Path(files[1]).name, equipOverlayStatus='generated')
        from python.verify_history_trail import current_vfx_slots
        slot = copy.deepcopy(current_vfx_slots()[2])
        slot.update(id='jump_star', entityId='item', event='on_jump', duration=18)
        slot['particle'].update(count=8, spreadRadians=6.28, speedMinPxPerTick=1, speedMaxPxPerTick=2,
                                widthPx=12, heightPx=12)
        item['vfxManifest']['slots'] = [slot]
        scene.update(playerUpdate='client_vfx', nativeRender=dict(width=320, height=512, cameraX=650,
            cameraY=1150, capture=True, drawArtwork=True, drawPlayer=True, drawNativeDust=True,
            lightingMode='viewport_fill', artworkFiles=files))
    return item, scene


def events(trace: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [dict(tick=s['tick'], **e) for s in trace.get('snapshots', []) for e in s.get('events', []) if e.get('kind') == kind]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--native-dll', type=Path)
    p.add_argument('--no-build', action='store_true')
    p.add_argument('--render', action='store_true')
    args = p.parse_args()
    if args.native_dll and not args.no_build:
        p.error('--native-dll requires --no-build')
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=False)
    if args.native_dll:
        dll = args.native_dll.resolve()
    else:
        dll, _ = w.native_executable(args.no_build)
    pin = w.native_binaries_state(dll)
    env, _ = w.native_environment()
    item, scene = prepare(out, args.render)
    idle = copy.deepcopy(scene); idle['actions'] = [dict(kind='equip', tick=0)]
    ground = copy.deepcopy(scene); ground['actions'] = [a for a in ground['actions'] if a['tick'] < 15]
    vanity = copy.deepcopy(scene); vanity['actions'][0]['kind'] = 'vanity'
    cases = [('extra', item, scene, [15, 25]), ('ground-only', item, ground, []),
             ('no-input', item, idle, []), ('vanity', item, vanity, [])]
    if args.render:
        blank = copy.deepcopy(item); blank['vfxManifest']['slots'] = []
        cases.append(('no-vfx', blank, scene, [15, 25]))
    rows, traces = [], {}
    for name, value, scenario, starts in cases:
        d = out / name; d.mkdir()
        (d/'item.json').write_text(json.dumps(value))
        (d/'scenario.json').write_text(json.dumps(scenario))
        proc = subprocess.run([env.get('DOTNET', 'dotnet'), str(dll), '--item', str(d/'item.json'),
            '--scenario', str(d/'scenario.json'), '--output', str(d/'native.json')],
            cwd=out, env=env, capture_output=True, text=True, timeout=180)
        (d/'process.log').write_text(proc.stdout+proc.stderr)
        trace = w.read_native_json(d/'native.json'); traces[name] = trace
        started = events(trace, 'native_extra_jump_started')
        movement = events(trace, 'native_jump_movement')
        ground_ticks = [e['tick'] for e in movement if e['groundJumpStarted']]
        dispatch = events(trace, 'native_air_jump_vfx_dispatch')
        checks = dict(nativePassed=proc.returncode == 0 and trace['status'] == 'passed',
            extraStarts=[e['tick'] for e in started] == starts,
            groundSeparate=ground_ticks == ([] if name == 'no-input' else [5]),
            productionVfxEntry=[e['tick'] for e in dispatch] == starts,
            nativeImpulse=all(e['vyAfter'] == -9.25 and e['jumpTicks'] == 4 for e in started),
            sharedSpeedRestored=all(e['sharedJumpSpeedBefore'] == e['sharedJumpSpeedAfter'] for e in movement))
        if starts:
            held = [e for e in movement if e['tick'] in (15, 16, 17, 18, 25, 26, 27, 28)]
            checks['authoredHoldAtNativeConsumer'] = len(held) == 8 and all(e['vyAfter'] == -9.25 for e in held)
            snapshots = {s['tick']: s['player'] for s in trace.get('snapshots', []) if 'phase' not in s}
            checks['gravityPreservedAfterImpulse'] = all(-9.25 < snapshots[t]['vy'] < 0 for t in (15, 16, 17, 18, 25, 26, 27, 28)) if snapshots else False
        if args.render:
            render = trace.get('nativeRender', {})
            counts = {s['tick']: s['particleCount'] for s in render.get('snapshots', [])}
            expects_vfx = bool(starts) and name != 'no-vfx'
            checks.update(originalPlayerRendered=render.get('playerArtworkRendered') is True,
                completeFrames=len(render.get('frames', [])) == scene['ticks'],
                nativeVfxPresent=(max(counts.values(), default=0) > 0) == expects_vfx,
                noGroundJumpVfx=all(counts.get(t) == 0 for t in range(15)),
                vfxExpired=counts.get(99) == 0,
                clientDispatch=all(e['dedServ'] is False for e in dispatch))
        rows.append(dict(name=name, passed=all(checks.values()), checks=checks, starts=started,
            groundTicks=ground_ticks, dispatch=dispatch, error=trace.get('error')))
    if args.render and all(t.get('status') == 'passed' for t in traces.values()):
        from PIL import Image, ImageChops
        a, b = traces['extra'], traces['no-vfx']
        changed = []
        for frame, blank in zip(a['nativeRender']['frames'], b['nativeRender']['frames']):
            with Image.open(out/'extra'/frame['path']) as ia, Image.open(out/'no-vfx'/blank['path']) as ib:
                if ImageChops.difference(ia.convert('RGB'), ib.convert('RGB')).getbbox(): changed.append(frame['tick'])
        checks = dict(visibleOriginalVfx=bool(changed) and min(changed) == 15,
                      noGroundPixels=not any(t < 15 for t in changed), noExpiredPixels=not any(t >= 43 for t in changed))
        rows.append(dict(name='native-pixel-control', passed=all(checks.values()), checks=checks, changedTicks=changed))
    summary = dict(passed=all(r['passed'] for r in rows) and pin == w.native_binaries_state(dll),
        **pin, sourceSha256=w.source_fingerprint(), checks=rows, fullGameParity=False,
        scope='Actual Player.Update and production ExtraJump/JumpMovement; synthetic fixture. Render mode uses original native player and VFX draw paths. Explicit DLL selection needs an independent source-build receipt.')
    (out/'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(dict(passed=summary['passed'], cases=[dict(name=r['name'], passed=r['passed'], checks=r['checks'], error=r.get('error')) for r in rows])))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
