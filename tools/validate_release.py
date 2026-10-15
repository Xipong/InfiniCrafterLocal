#!/usr/bin/env python3
"""Shared validation execution for agentctl, CI and release wrappers.

The manifest owns commands and groups; existing tools own each actual gate.
Missing native environments are reported explicitly, never as successful builds.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def checks_for_group(name: str, manifest: dict[str, Any] | None = None) -> list[str]:
    data: dict[str, Any] = manifest if manifest is not None else json.loads((ROOT / '.agent/manifest.json').read_text(encoding='utf-8'))
    return list(data['fullChecks'] if name == 'full' else data['validationGroups'][name])


def _execute(command: list[str], root: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=root, env=env, text=True, encoding='utf-8', errors='replace',
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)


def _host_path(executable: str, value: str, root: Path) -> str:
    """Translate repository paths only for a Windows host launched from WSL."""
    if os.name != 'nt' and executable.lower().endswith('.exe') and shutil.which('wslpath'):
        path = (root / Path(value).expanduser()).resolve()
        converted = subprocess.run(['wslpath', '-w', str(path)], text=True, capture_output=True, check=False)
        if converted.returncode == 0 and converted.stdout.strip():
            return converted.stdout.strip()
    return value


def run_check(name: str, command: list[str], *, root: Path = ROOT, env: dict[str, str] | None = None) -> dict[str, Any]:
    start = time.monotonic()
    environment = dict(os.environ if env is None else env)
    environment.update(PYTHONPATH=str(root / 'LocalGenerator'), PYTHONUTF8='1', INFINI_SKIP_CONFIG_FILE='1', INFINI_TEST_USE_PROJECT_CONFIG='0')
    command = list(command)

    def result(status: str, output: str = '', code: int | None = None) -> dict[str, Any]:
        return {'name': name, 'status': status, 'command': command, 'exitCode': code,
                'durationSeconds': round(time.monotonic() - start, 3), 'outputTail': output[-12000:], 'output': output}

    if name == 'tml_ci_regression' and not (environment.get('TML_TEST_PWSH') or shutil.which('pwsh') or shutil.which('pwsh.exe')):
        return result('unavailable', 'Offline PowerShell control-flow regression requires pwsh (or TML_TEST_PWSH)')
    if name == 'tml_runtime_selftest':
        report = environment.get('INFINI_AGENT_SELFTEST_REPORT', '')
        if not report or not (root / report).is_file():
            return result('notRun', 'Real tModLoader runtime self-test report unavailable; run tML with INFINI_AGENT_SELFTEST=1')
        command = [sys.executable, 'tools/check_tml_selftest_report.py', report]
    if name in {'tml_build', 'native_checks'}:
        dotnet = shutil.which('dotnet') or shutil.which('dotnet.exe')
        if not dotnet:
            return result('unavailable', 'dotnet is not installed')
        deps = environment.get('INFINI_TML_DEPS_SRC', '')
        if deps:
            deps = str((root / Path(deps).expanduser()).resolve())
        project = environment.get('INFINI_VALIDATION_PROJECT', 'ModSources/InfiniCrafterLocal/InfiniCrafterLocal.csproj')
        project_path = root / project
        if name == 'tml_build' and not project_path.is_file():
            return result('failed', f'Project not found: {project_path}', 2)
        shell = environment.get('TML_TEST_PWSH') or shutil.which('pwsh') or shutil.which('pwsh.exe') or (shutil.which('powershell') if os.name == 'nt' else None)
        if name == 'tml_build' and shell:
            command = [shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', _host_path(shell, str(root / 'tools/build_tml_windows.ps1'), root),
                       '-Project', _host_path(shell, str(project_path), root), '-Configuration', 'Debug', '-WarningsAsErrors']
            if deps:
                command += ['-InfiniExternalDepsRoot', _host_path(shell, deps, root)]
            proc = _execute(command, root, environment)
            log = root / 'artifacts/validation/tml-build.log'
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(proc.stdout, encoding='utf-8')
            parsed = _execute([sys.executable, 'tools/parse_tml_build_log.py', str(log), '--mod', 'InfiniCrafterLocal'], root, environment)
            output = proc.stdout + parsed.stdout
            if proc.returncode == 77 and parsed.returncode == 0:
                return result('notRun', output, 77)
            code = proc.returncode if proc.returncode not in {0, 77} else parsed.returncode
            return result('passed' if code == 0 else 'failed', output, code)
        if not deps or not all((Path(deps) / part).is_file() for part in (
                'ParticleLibrary/ParticleLibrary.dll', 'Luminance/bin/Debug/net8.0/Luminance.dll')):
            return result('notRun', 'External mod reference DLLs unavailable; set INFINI_TML_DEPS_SRC')
        if name == 'native_checks':
            refs = environment.get('INFINI_TML_REFERENCE_DIR', '')
            if refs:
                refs = str((root / Path(refs).expanduser()).resolve())
            if not refs or not (Path(refs) / 'tModLoader.dll').is_file():
                return result('notRun', 'Native CPU checks need INFINI_TML_REFERENCE_DIR containing tModLoader.dll')
            filters = command[command.index('--check-filter'):] if '--check-filter' in command else []
            command = [dotnet, 'build', _host_path(dotnet, 'tools/EngineRuntimeChecks.csproj', root), '-c', 'Debug', '--nologo', '-v:minimal',
                       f'/p:InfiniTmlReferenceDir={_host_path(dotnet, refs, root)}', f'/p:InfiniExternalDepsRoot={_host_path(dotnet, deps, root)}']
            build = _execute(command, root, environment)
            if build.returncode:
                return result('failed', build.stdout, build.returncode)
            run = _execute([dotnet, _host_path(dotnet, 'tools/bin/Debug/net8.0/EngineRuntimeChecks.dll', root), *filters], root, environment)
            return result('passed' if run.returncode == 0 else 'failed', build.stdout + run.stdout, run.returncode)
        command = [dotnet, 'build', _host_path(dotnet, str(project_path), root), '-c', 'Debug', '--nologo', '-v:minimal', '-warnaserror',
                   f'/p:InfiniExternalDepsRoot={_host_path(dotnet, deps, root)}']
        build = _execute(command, root, environment)
        log = root / 'artifacts/validation/tml-build.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(build.stdout, encoding='utf-8')
        parsed = _execute([sys.executable, 'tools/parse_tml_build_log.py', str(log)], root, environment)
        code = build.returncode or parsed.returncode
        return result('passed' if code == 0 else 'failed', build.stdout + parsed.stdout, code)
    if command and command[0] in {'python', 'python3'}:
        command[0] = sys.executable
    if name in {'ruff', 'pyright'} and importlib.util.find_spec(name) is not None:
        command = [sys.executable, '-m', name, *command[1:]]
    if name == 'pyright' and importlib.util.find_spec('pyright') is None and not shutil.which('pyright'):
        return result('unavailable', 'pyright is not installed')
    if name == 'pyright':
        command = [sys.executable, 'tools/run_pyright.py', '--pythonpath', sys.executable]
    if not command:
        return result('unavailable', 'No command configured')
    if not Path(command[0]).is_file() and not shutil.which(command[0]):
        sibling = next((Path(sys.executable).with_name(command[0] + suffix) for suffix in ('', '.exe', '.cmd')
                        if Path(sys.executable).with_name(command[0] + suffix).is_file()), None)
        if sibling is None:
            return result('unavailable', f'{command[0]} is not installed')
        command[0] = str(sibling)
    try:
        proc = _execute(command, root, environment)
    except OSError as exc:
        return result('unavailable', str(exc))
    status = 'passed' if proc.returncode == 0 else 'failed'
    if proc.returncode == 2 and '"status": "unavailable"' in proc.stdout:
        status = 'unavailable'
    return result(status, proc.stdout, proc.returncode)


def refresh(group: str, manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data: dict[str, Any] = manifest if manifest is not None else json.loads((ROOT / '.agent/manifest.json').read_text(encoding='utf-8'))
    commands = list(data['refreshGroups'][group])
    if group != 'docs':
        commands.extend(data['refreshGroups']['docs'])
    rows: list[dict[str, Any]] = []
    for command in commands:
        row = run_check('refresh_' + Path(command[1]).stem, command)
        rows.append(row)
        print(f"[{row['status']}] {row['name']}", flush=True)
        if row['status'] != 'passed':
            print(row.get('output', ''), flush=True)
            break
    return rows


def main() -> int:
    os.environ.setdefault("INFINI_PYTHON", sys.executable)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', choices=['runtime', 'config', 'docs'])
    parser.add_argument('--group', choices=['full', 'python', 'static', 'build'], default='full')
    parser.add_argument('--require-build', action='store_true')
    parser.add_argument('--require-runtime-selftest', action='store_true')
    parser.add_argument('--skip-build', action='store_true')
    parser.add_argument('--project')
    parser.add_argument('--external-deps-root')
    parser.add_argument('--runtime-selftest-report')
    parser.add_argument('--report', type=Path, default=ROOT / 'artifacts/validation/validation_report.json')
    args = parser.parse_args()
    manifest = json.loads((ROOT / '.agent/manifest.json').read_text(encoding='utf-8'))
    if args.refresh:
        rows = refresh(args.refresh, manifest)
        return 0 if rows and all(row['status'] == 'passed' for row in rows) else 1
    env = dict(os.environ)
    for key, value in [('INFINI_VALIDATION_PROJECT', args.project), ('INFINI_TML_DEPS_SRC', args.external_deps_root),
                       ('INFINI_AGENT_SELFTEST_REPORT', args.runtime_selftest_report)]:
        if value:
            env[key] = value
    checks: list[dict[str, Any]] = []
    art = ROOT / 'artifacts/validation'
    art.mkdir(parents=True, exist_ok=True)
    for name in checks_for_group(args.group, manifest):
        if args.skip_build and name == 'tml_build':
            row: dict[str, Any] = {'name': name, 'status': 'notRun', 'output': 'Build explicitly skipped', 'durationSeconds': 0}
        else:
            row = run_check(name, manifest['checks'][name], env=env)
        output = row.pop('output', '')
        (art / f'{name}.log').write_text(output, encoding='utf-8')
        row['log'] = f'artifacts/validation/{name}.log'
        row['returnCode'] = row.get('exitCode')
        checks.append(row)
        print(f"[{row['status']}] {name}", flush=True)
        if row['status'] != 'passed' or args.group == 'build':
            print(output, flush=True)
        if name == 'tml_build' and env.get('GITHUB_ENV') and row['status'] != 'passed':
            with open(env['GITHUB_ENV'], 'a', encoding='utf-8') as stream:
                stream.write('TML_BUILD_' + ('FAILED' if row['status'] == 'failed' else 'SKIPPED') + '=true\n')
    optional = {'native_checks', 'tml_ci_regression'}
    if not args.require_build:
        optional.add('tml_build')
    if not args.require_runtime_selftest:
        optional.add('tml_runtime_selftest')
    failed = [row['name'] for row in checks if row['status'] == 'failed']
    unavailable = [row['name'] for row in checks if row['status'] in {'unavailable', 'notRun'} and row['name'] not in optional]
    report = {'schema': 'infini.release-validation.v1', 'ok': not failed and not unavailable,
              'releaseReady': args.group == 'full' and all(row['status'] == 'passed' for row in checks),
              'failed': failed, 'unavailableRequired': unavailable, 'missingChecks': [], 'duplicateChecks': [], 'checks': checks}
    (art / 'status.tsv').write_text(''.join(
        f"{row['name']}\t{row['status']}\t{row.get('exitCode') if row.get('exitCode') is not None else ''}\t{row['durationSeconds']}\t{row['log']}\n"
        for row in checks
    ), encoding='utf-8')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if args.group == 'build' and failed:
        return next(int(row.get('exitCode') or 1) for row in checks if row['status'] == 'failed')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
