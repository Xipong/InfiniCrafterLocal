"""Small public router; runtime imports belong only to deliberate live execution."""
from __future__ import annotations

import argparse
import json
import sys
import subprocess

from toolbox.infini_toolbox import BASE_ROOT

from toolbox.live.options import build_parser
from toolbox.live.preflight import prepare


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        description='Утилиты QA: безопасный offline-вход; live только с --run.',
        epilog='live10/live20: preflight или явная text-кампания; summary: saved ledgers; doctor: read-only prerequisites; replay: saved wire; verify: canonical affected checks.',
    )
    parser.add_argument('command', choices=('live10', 'live20', 'summary', 'doctor', 'verify', 'replay'))
    if not values or values[0] in ('-h', '--help'):
        parser.print_help()
        return 0
    if values[0] == 'verify':
        return subprocess.run([sys.executable, str(BASE_ROOT / 'tools/agentctl.py'), 'verify', *values[1:]], cwd=BASE_ROOT).returncode
    if values[0] == 'replay':
        child = subprocess.run([sys.executable, '-m', 'toolbox.testing.replay', *values[1:]], cwd=BASE_ROOT, text=True, capture_output=True)
        print(child.stdout, end='')
        print(child.stderr, end='', file=sys.stderr)
        return child.returncode
    if values[0] == 'doctor':
        from pathlib import Path
        from toolbox.infini_toolbox import discover_project
        from toolbox.testing.doctor import doctor
        doctor_parser = argparse.ArgumentParser(description='Read-only dependencies and registered native command (no credentials).')
        doctor_parser.add_argument('--project', type=Path)
        doctor_args = doctor_parser.parse_args(values[1:])
        try:
            report = doctor(discover_project(doctor_args.project))
        except (ValueError, OSError, KeyError) as exc:
            doctor_parser.error(str(exc))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['ok'] else 1
    if values[0] == 'summary':
        from pathlib import Path
        from toolbox.live.summary import summarize
        summary_parser = argparse.ArgumentParser(description='Offline accounting of a saved Live10/20 directory.')
        summary_parser.add_argument('directory', type=Path)
        summary_args = summary_parser.parse_args(values[1:])
        try:
            report = summarize(summary_args.directory)
        except (ValueError, OSError) as exc:
            summary_parser.error(str(exc))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['ok'] else 1
    command = parser.parse_args(values[:1]).command
    options = build_parser()
    args = options.parse_args(values[1:])
    args.panel = command
    try:
        report, _ = prepare(args)
        if args.run:
            # The child runs at BASE_ROOT; preserve the caller's selected files.
            forwarded = list(values[1:])
            for name in ('project', 'output', 'config', 'cases_file', 'runtime_dump'):
                path = getattr(args, name)
                if path is not None:
                    forwarded += ['--' + name.replace('_', '-'), str(path.expanduser().resolve())]
            return subprocess.run(
                [sys.executable, '-m', 'toolbox.live.runner', '--panel', command, *forwarded],
                cwd=BASE_ROOT,
            ).returncode
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        options.error(str(exc))
    return 2
