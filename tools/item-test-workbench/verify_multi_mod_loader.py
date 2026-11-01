#!/usr/bin/env python3
"""Execute real dependent tML fixtures and dependency-graph refusal cases."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-dll', type=Path, required=True)
    parser.add_argument('--dependency-dll', type=Path, required=True)
    parser.add_argument('--dependent-dll', type=Path, required=True)
    parser.add_argument('--dependency-root', type=Path, required=True)
    parser.add_argument('--dependent-root', type=Path, required=True)
    parser.add_argument('--server-mode', action='store_true')
    args = parser.parse_args()
    host = args.native_dll.resolve(strict=True)
    dependency = args.dependency_dll.resolve(strict=True)
    dependent = args.dependent_dll.resolve(strict=True)
    dependency_root = args.dependency_root.resolve(strict=True)
    dependent_root = args.dependent_root.resolve(strict=True)
    dotnet = os.environ.get('DOTNET', 'dotnet')
    scenario = {'playerUpdate': 'full', 'ticks': 120, 'seed': 1,
        'player': {'x': 640, 'y': 640, 'life': 100, 'mana': 200},
        'dummy': {'x': 850, 'y': 640, 'nativeType': 'WorkbenchObserverFixture/ProbeNpc'},
        'actions': [{'tick': 0, 'kind': 'aim', 'x': 850, 'y': 661},
                    {'tick': 0, 'kind': 'primary'}, {'tick': 1, 'kind': 'release'}],
        'assertions': [{'kind': 'spawned'}, {'kind': 'dummy_damaged'},
                       {'kind': 'all_inactive'}, {'kind': 'no_nonfinite'}]}
    if args.server_mode:
        # A dedicated server has no local client to drive item firing. Exercise
        # its real mount, NPC and ModSystem lifecycle without inventing shots.
        scenario['ticks'] = 2
        scenario['actions'] = []
        scenario['assertions'] = [{'kind': 'no_nonfinite'}]
    with tempfile.TemporaryDirectory(prefix='ifc-multiple-mods-') as directory:
        temp = Path(directory)
        scene = temp / 'scenario.json'
        scene.write_text(json.dumps(scenario), encoding='utf-8')

        def run(name, mods, disabled=None):
            trace_path = temp / (name + '.json')
            observer = temp / (name + '-observer.json')
            command = [dotnet, str(host), '--native-loader-scene',
                       '--native-item', 'WorkbenchDependentFixture/DependentItem',
                       '--scenario', str(scene), '--output', str(trace_path)]
            if args.server_mode:
                command += ['--server-mode', 'true']
            for dll, root in mods:
                command += ['--mod-dll', str(dll), '--mod-root', str(root)]
            env = os.environ.copy()
            env['IFC_WORKBENCH_OBSERVER_OUTPUT'] = str(observer)
            if args.server_mode:
                env['IFC_FIXTURE_EXPECT_SERVER'] = '1'
            for variable in ('IFC_FIXTURE_DISABLE_DEPENDENT_DAMAGE', 'IFC_FIXTURE_DISABLE_DAMAGE_MODIFIERS'):
                env.pop(variable, None)
            if disabled:
                env[disabled] = '1'
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=240)
            if not trace_path.is_file():
                raise AssertionError(f'{name}: missing terminal trace; exit={result.returncode}; {result.stderr[-3000:]}')
            trace = json.loads(trace_path.read_text(encoding='utf-8'))
            observed = json.loads(observer.read_text(encoding='utf-8')) if observer.is_file() else None
            return result, trace, observed

        # Deliberately supply the dependent assembly first. Its real Load()
        # requires the dependency's Load() to have completed, and its item
        # creates a projectile defined in the dependency's separate DLL.
        result, trace, observation = run('reverse-input', [
            (dependent, dependent_root), (dependency, dependency_root)])
        if result.returncode != 0 or trace.get('status') != 'passed':
            raise AssertionError(f'Cross-mod native scene failed: {trace.get("error")}; {result.stderr[-3000:]}')
        if trace['execution']['networkMode'] != (2 if args.server_mode else 0):
            raise AssertionError(f'Unexpected network mode: {trace["execution"]}')
        order = [item['name'] for item in trace['execution']['additionalMods']]
        if order != ['WorkbenchObserverFixture', 'WorkbenchDependentFixture']:
            raise AssertionError(f'Dependency load order incorrect: {order}')
        if trace['combat']['spawns'] < 1 or trace['combat']['hits'] < 1:
            raise AssertionError(f'Dependent item did not hit using dependency projectile: {trace["combat"]}')
        counts = (observation or {}).get('counts', {})
        if args.server_mode:
            for hook in ('GlobalNPC.SetDefaults.NpcSlotReady', 'GlobalNPC.OnSpawn', 'ModNPC.AI', 'ModSystem.PostUpdateEverything'):
                if counts.get(hook, 0) < 1:
                    raise AssertionError(f'Server hook {hook} did not run: {counts}')
            print('Native server mode and player index retained during actual mount, NPC and system hooks: PASS')
            return 0
        for hook in ('ModProjectile.AI', 'ModProjectile.OnHitNPC', 'GlobalProjectile.OnSpawn', 'GlobalNPC.OnSpawn'):
            if counts.get(hook, 0) < 1:
                raise AssertionError(f'Dependency gameplay hook {hook} did not run: {counts}')

        # Independently ablate each mod's real damage hook. The world, seed,
        # item, projectile and input remain otherwise identical.
        damage = trace['combat']['initialLife'] - trace['combat']['finalLife']
        controls = {}
        for name, disabled in [('dependent-hook-off', 'IFC_FIXTURE_DISABLE_DEPENDENT_DAMAGE'),
                               ('dependency-hook-off', 'IFC_FIXTURE_DISABLE_DAMAGE_MODIFIERS')]:
            proc, control, _ = run(name, [(dependent, dependent_root), (dependency, dependency_root)], disabled)
            if proc.returncode != 0 or control.get('status') != 'passed':
                raise AssertionError(f'{name} native scene failed: {control.get("error")}')
            controls[name] = control['combat']['initialLife'] - control['combat']['finalLife']
            if not damage > controls[name] > 0:
                raise AssertionError(f'{name} did not change native damage: {damage} vs {controls[name]}')

        missing_proc, missing, missing_observation = run('missing-dependency', [(dependent, dependent_root)])
        if missing_proc.returncode != 2 or missing.get('status') != 'error' or 'WorkbenchObserverFixture' not in missing.get('error', ''):
            raise AssertionError(f'Missing dependency not refused: {missing}')
        if missing_observation is not None:
            raise AssertionError('Missing dependency ran fixture hooks')

        # Same assemblies and sources, only the temporary dependency metadata is
        # changed to introduce a cycle; no fixture code or assets are replaced.
        cycle_root = temp / 'cycle-dependency'
        cycle_root.mkdir()
        original = (dependency_root / 'build.txt').read_text(encoding='utf-8')
        (cycle_root / 'build.txt').write_text(original.rstrip() + '\nmodReferences = WorkbenchDependentFixture\n', encoding='utf-8')
        cycle_proc, cycle, cycle_observation = run('dependency-cycle', [(dependent, dependent_root), (dependency, cycle_root)])
        if cycle_proc.returncode != 2 or cycle.get('status') != 'error' or 'cycl' not in cycle.get('error', '').lower():
            raise AssertionError(f'Dependency cycle not refused: {cycle}')
        if cycle_observation is not None:
            raise AssertionError('Cyclic graph ran fixture hooks')

        duplicate_proc, duplicate, duplicate_observation = run('duplicate-mod', [(dependency, dependency_root), (dependency, dependency_root)])
        if duplicate_proc.returncode != 2 or duplicate.get('status') != 'error' or 'duplicat' not in duplicate.get('error', '').lower():
            raise AssertionError(f'Duplicate mod not refused: {duplicate}')
        if duplicate_observation is not None:
            raise AssertionError('Duplicate graph ran fixture hooks')
    print(f'Native dependency/dependent hooks affect combat ({damage} vs {controls}); load order and graph refusals: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
