#!/usr/bin/env python3
"""Verify genuine tML-written archive inputs, metadata and original file access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-dll', type=Path, required=True)
    parser.add_argument('--dependency-tmod', type=Path, required=True)
    parser.add_argument('--dependent-tmod', type=Path, required=True)
    args = parser.parse_args()
    host, dependency, dependent = (p.resolve(strict=True) for p in
                                   (args.native_dll, args.dependency_tmod, args.dependent_tmod))
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (dependency, dependent)}
    env = os.environ.copy()
    env['IFC_FIXTURE_REQUIRE_ARCHIVE'] = '1'
    base = [os.environ.get('DOTNET', 'dotnet'), str(host), '--check-native-loader']
    result = subprocess.run(base + ['--tmod', str(dependent), '--tmod', str(dependency),
                                   '--probe-npc', 'WorkbenchObserverFixture/ProbeNpc'],
                            env=env, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise AssertionError(f'Native archive loader failed: {result.stderr}')
    reports = []
    for line in result.stdout.splitlines():
        try:
            reports.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    report = next((r for r in reversed(reports) if r.get('status') == 'passed'), None)
    if not report or [m['name'] for m in report['additionalMods']] != ['WorkbenchObserverFixture', 'WorkbenchDependentFixture']:
        raise AssertionError(f'Archive metadata did not determine dependency order: {report}')
    if any(hashlib.sha256(p.read_bytes()).hexdigest() != before[p] for p in before):
        raise AssertionError('Native loader modified a source archive')
    duplicate = subprocess.run(base + ['--tmod', str(dependency), '--tmod', str(dependency)],
                               env=env, capture_output=True, text=True, timeout=180)
    if duplicate.returncode != 2 or 'duplicate' not in duplicate.stderr.lower():
        raise AssertionError(f'Duplicate archive was not refused: {duplicate.stderr}')
    print('tML-written archives: original file access, Info dependency order and duplicate refusal: PASS')


if __name__ == '__main__':
    main()
