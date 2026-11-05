#!/usr/bin/env python3
"""Verify real loader Player.Update + FNA draw with an independent fixture mod.

This is a bounded diagnostic scene, not full-client or multiplayer coverage.
Existing pinned player assets and matching native graphics libraries are required.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

from workbench import validate_loader_render


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-dll', type=Path, required=True)
    parser.add_argument('--mod-dll', type=Path, required=True)
    parser.add_argument('--mod-root', type=Path, required=True)
    parser.add_argument('--player-assets', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    output = args.out.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a fresh output directory')
    output.mkdir(parents=True, exist_ok=True)
    dotnet = os.environ.get('DOTNET', 'dotnet')
    from PIL import Image

    def run(name, item, scene, render, extra_env=None):
        case = output / name; case.mkdir()
        scenario = case / 'scenario.json'; scenario.write_text(json.dumps(scene), encoding='utf-8')
        report_path = case / 'native.json'; observer = case / 'observer.json'
        command = [dotnet, str(args.native_dll.resolve()), '--native-loader-scene',
                   '--native-item', 'WorkbenchObserverFixture/' + item,
                   '--scenario', str(scenario), '--output', str(report_path),
                   '--mod-dll', str(args.mod_dll.resolve()), '--mod-root', str(args.mod_root.resolve())]
        if render:
            command += ['--loader-render-output', str(case / 'render'), '--player-assets', str(args.player_assets.resolve())]
        env = os.environ.copy(); env['IFC_WORKBENCH_OBSERVER_OUTPUT'] = str(observer)
        env.pop('IFC_FIXTURE_THROW_ON_DRAW', None)
        env.update(extra_env or {})
        proc = subprocess.run(command, env=env, capture_output=True, text=True, timeout=180)
        (case / 'stdout.log').write_text(proc.stdout, encoding='utf-8')
        (case / 'stderr.log').write_text(proc.stderr, encoding='utf-8')
        if not report_path.is_file():
            raise AssertionError((name, proc.returncode, proc.stderr))
        report = json.loads(report_path.read_text(encoding='utf-8'))
        observations = json.loads(observer.read_text(encoding='utf-8')) if observer.is_file() else {}
        return proc.returncode, report, observations

    scene = {'ticks': 80, 'seed': 1, 'playerUpdate': 'full',
             'player': {'x': 800, 'y': 710}, 'dummy': {'x': 1100, 'y': 710},
             'tiles': [{'tileX': 1, 'tileY': 47, 'width': 97, 'height': 1}],
             'actions': [{'tick': 45, 'kind': 'aim', 'x': 1100, 'y': 731},
                         {'tick': 45, 'kind': 'primary'}, {'tick': 46, 'kind': 'release'}],
             'assertions': [{'kind': 'spawned'}, {'kind': 'all_inactive'}, {'kind': 'no_nonfinite'}]}
    results = []
    for suffix, item in [('free', 'RenderProbeItem'), ('held', 'RenderHeldProbeItem')]:
        cpu_exit, cpu, cpu_observer = run(suffix + '-cpu', item, scene, False)
        draw_exit, draw, observed = run(suffix + '-draw', item, scene, True)
        assert cpu_exit == draw_exit == 0 and cpu['status'] == draw['status'] == 'passed', (suffix, cpu.get('error'), draw.get('error'))
        assert cpu['snapshots'] == draw['snapshots'], suffix + ': drawing changed the CPU timeline'
        assert cpu['combat'] == draw['combat'], suffix + ': drawing changed combat'
        validate_loader_render(draw['nativeRender'], output / (suffix + '-draw/render'), scene['ticks'])
        frames, snapshots = draw['nativeRender']['frames'], draw['snapshots']
        expected_draws = sum(len(frame['projectileDrawAttempts']) for frame in frames)
        inactive_held = [attempt for frame in frames for attempt in frame['projectileDrawAttempts'] if not attempt['activeAtDraw']]
        assert len(inactive_held) == (1 if suffix == 'held' else 0), (suffix, inactive_held)
        assert all(attempt['pass'] == 'native_player_held' for attempt in inactive_held), inactive_held
        counts = observed.get('counts', {})
        assert expected_draws > 0 and counts.get('RenderProbe.PreDraw') == expected_draws, (suffix, expected_draws, counts)
        assert counts.get('RenderProbe.AI') == cpu_observer.get('counts', {}).get('RenderProbe.AI'), suffix
        assert counts.get('ModSystem.PostUpdateEverything') == scene['ticks'], counts
        assert all(f['player']['gfxOffY'] == 0 for f in snapshots[40:]), 'Settled scene must not fake away native gfxOffY'
        assert snapshots[45]['commandedInput']['useItem'] and not snapshots[46]['commandedInput']['useItem']
        red_frames = 0
        for frame, state in zip(frames, snapshots):
            assert frame['worldProjectileDrawAttempts'] == (0 if suffix == 'held' else len(state['projectiles'])), (suffix, frame)
            with Image.open(frame['path']) as image:
                pixels = list(image.convert('RGB').get_flattened_data()) if hasattr(image, 'get_flattened_data') else list(image.convert('RGB').getdata())
            assert any(pixel != (20, 24, 32) for pixel in pixels), (suffix, frame['tick'], 'empty frame')
            red = sum(r > 220 and g < 20 and b < 20 for r, g, b in pixels)
            assert bool(red) == bool(frame['projectileDrawAttempts']), (suffix, frame['tick'], red)
            red_frames += bool(red)
        results.append({'case': suffix, 'ticks': len(frames), 'nativePreDrawCalls': expected_draws,
                        'framesWithFixturePixels': red_frames, 'nativeInactiveHeldDraws': len(inactive_held), 'cpuTimelineIdentical': True})
    fail_exit, failed, _ = run('draw-error', 'RenderProbeItem', scene, True, {'IFC_FIXTURE_THROW_ON_DRAW': '1'})
    assert fail_exit == 2 and failed['status'] == 'error' and 'fixture draw failure' in failed.get('error', ''), failed
    alias_exit, alias, _ = run('unsupported-vanilla-alias', 'ProbeItem', scene, True)
    assert alias_exit == 2 and alias['status'] == 'error' and 'explicitly supplied mod PNG' in alias.get('error', ''), alias
    summary = {'status': 'passed', 'scope': 'Independent fixture mod, actual Player.Update/Main.DrawProj/PlayerRenderer; not full-client parity',
               'cases': results, 'negativeControls': ['swallowed native draw exception', 'unsupported vanilla texture alias']}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
