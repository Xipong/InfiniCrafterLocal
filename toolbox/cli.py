"""Small public router; execution stays with the existing command owners."""
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
        epilog='live10/live20: versioned inputs, preflight или явная text/image-кампания; panels: каталог запросов; summary: saved ledgers; doctor: read-only prerequisites; replay: saved wire; verify: canonical affected checks; workbench: native item tests and recorded frames.',
    )
    parser.add_argument('command', choices=('live10', 'live20', 'panels', 'summary', 'doctor', 'verify', 'replay', 'workbench'))
    if not values or values[0] in ('-h', '--help'):
        parser.print_help()
        return 0
    if values[0] == 'workbench':
        # Keep caller-relative item/scenario/output paths and stream semantics.
        # The existing owner alone parses arguments and decides whether to execute.
        return subprocess.run(
            [sys.executable, str(BASE_ROOT / 'tools/item-test-workbench/workbench.py'), *values[1:]],
        ).returncode
    if values[0] == 'panels':
        from toolbox.live.catalog import panel_catalog
        catalog_parser = argparse.ArgumentParser(description='Исходные пакеты запросов и родители; без inference.')
        catalog_parser.parse_args(values[1:])
        try:
            entries = panel_catalog()
        except (ValueError, OSError) as exc:
            catalog_parser.error(str(exc))
        print(json.dumps({'offlineOnly': True, 'panels': entries}, ensure_ascii=False, indent=2))
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
            for name in ('project', 'output', 'config', 'cases_file', 'runtime_dump', 'attempt_budget',
                         'reuse_images_from', 'vfx_only_from'):
                path = getattr(args, name)
                if path is not None:
                    forwarded += ['--' + name.replace('_', '-'), str(path.expanduser().resolve())]
            return subprocess.run(
                [sys.executable, '-m', 'toolbox.live.runner', '--panel', command, *forwarded],
                cwd=BASE_ROOT,
            ).returncode
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, EOFError) as exc:
        options.error(str(exc))
    return 2
