#!/usr/bin/env python3
"""Verify native loader autoload and fail-closed dependency handling, without starting Terraria."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def report_from_stdout(output):
    # tML may log before the final machine-readable result.
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get('status') == 'passed':
            return value
    raise AssertionError('Native loader did not emit its passed JSON report')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-dll', type=Path, required=True, help='Built ItemTestWorkbench.dll with a sibling IFC DLL')
    parser.add_argument('--probe-dll', type=Path, required=True, help='Separately built WorkbenchObserverFixture DLL')
    parser.add_argument('--probe-mod-root', type=Path, default=HERE / 'fixtures/WorkbenchObserverFixture')
    args = parser.parse_args()
    host, probe, root = args.native_dll.resolve(strict=True), args.probe_dll.resolve(strict=True), args.probe_mod_root.resolve(strict=True)
    production = host.parent / 'InfiniCrafterLocal.dll'
    build_file = root / 'build.txt'
    if not production.is_file() or not build_file.is_file():
        parser.error('A sibling InfiniCrafterLocal.dll and the fixture build.txt are required')
    baseline = {path: sha256(path) for path in (host, production, probe, build_file)}
    dotnet = os.environ.get('DOTNET', 'dotnet')
    with tempfile.TemporaryDirectory(prefix='ifc-native-loader-') as directory:
        temp = Path(directory)
        observer = temp / 'observer.json'
        command = [dotnet, str(host), '--check-native-loader', '--probe-dll', str(probe),
                   '--probe-mod-root', str(root), '--probe-npc', 'WorkbenchObserverFixture/ProbeNpc']
        env = os.environ.copy()
        env['IFC_WORKBENCH_OBSERVER_OUTPUT'] = str(observer)
        positive = subprocess.run(command, env=env, capture_output=True, text=True, timeout=180)
        if positive.returncode != 0:
            raise AssertionError(f'Native loader failed ({positive.returncode}): {positive.stderr}')
        report = report_from_stdout(positive.stdout)
        if not report.get('nativePlayerAttached') or not report.get('npcSpawnHook') or report.get('ContentCount', 0) < 1:
            raise AssertionError(f'IFC lifecycle not confirmed: {report}')
        extra = report.get('additionalMod') or {}
        if extra.get('name') != 'WorkbenchObserverFixture' or extra.get('sha256') != baseline[probe]:
            raise AssertionError(f'Loaded additional mod is not the supplied fixture: {extra}')
        if Path(report.get('productionAssembly', '')).resolve() != production.resolve():
            raise AssertionError('Loader did not use the host sibling IFC production DLL')
        if not observer.is_file():
            raise AssertionError('Independent fixture did not produce its observer file')
        observed = json.loads(observer.read_text(encoding='utf-8'))
        counts = observed.get('counts', {})
        for hook in ('GlobalNPC.OnSpawn', 'ModSystem.PostSetupContent', 'ModSystem.PostUpdateEverything'):
            if counts.get(hook, 0) < 1:
                raise AssertionError(f'Independent native hook {hook} did not execute: {counts}')

        # Change only the temporary copy of the fixture metadata; the same DLL
        # must fail closed before any gameplay if a dependency is missing.
        missing_root = temp / 'missing-dependency'
        missing_root.mkdir()
        original = build_file.read_text(encoding='utf-8')
        if any(line.strip().startswith('modReferences') for line in original.splitlines()):
            raise AssertionError('Fixture unexpectedly already declares modReferences')
        (missing_root / 'build.txt').write_text(original.rstrip() + '\nmodReferences = WorkbenchMissingDependency\n', encoding='utf-8')
        missing_observer = temp / 'missing-observer.json'
        env['IFC_WORKBENCH_OBSERVER_OUTPUT'] = str(missing_observer)
        missing_command = [dotnet, str(host), '--check-native-loader', '--probe-dll', str(probe),
                           '--probe-mod-root', str(missing_root), '--probe-npc', 'WorkbenchObserverFixture/ProbeNpc']
        negative = subprocess.run(missing_command, env=env, capture_output=True, text=True, timeout=180)
        if negative.returncode != 2 or 'dependencies not loaded' not in negative.stderr or 'WorkbenchMissingDependency' not in negative.stderr:
            raise AssertionError(f'Missing dependency did not fail closed ({negative.returncode}): {negative.stderr}')
        if missing_observer.exists():
            raise AssertionError('Missing-dependency case unexpectedly executed the fixture')

        # A CLR-loaded assembly does not get tML's conditional type filtering.
        # It must also refuse missing weak references instead of silently
        # autoloading content that may require the absent mod.
        weak_root = temp / 'missing-weak-dependency'
        weak_root.mkdir()
        (weak_root / 'build.txt').write_text(original.rstrip() + '\nweakReferences = WorkbenchMissingWeakDependency\n', encoding='utf-8')
        weak_command = [dotnet, str(host), '--check-native-loader', '--probe-dll', str(probe),
                        '--probe-mod-root', str(weak_root), '--probe-npc', 'WorkbenchObserverFixture/ProbeNpc']
        weak = subprocess.run(weak_command, env=env, capture_output=True, text=True, timeout=180)
        if weak.returncode != 2 or 'dependencies not loaded' not in weak.stderr or 'WorkbenchMissingWeakDependency' not in weak.stderr:
            raise AssertionError(f'Missing weak dependency did not fail closed ({weak.returncode}): {weak.stderr}')
        if any(not path.is_file() or sha256(path) != digest for path, digest in baseline.items()):
            raise AssertionError('Host, IFC, fixture assembly or fixture metadata changed during verification')
    print('Native IFC and independent mod autoload, hook dispatch and missing-dependency refusal: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
