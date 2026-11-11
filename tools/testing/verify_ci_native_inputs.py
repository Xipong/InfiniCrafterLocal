#!/usr/bin/env python3
"""Bind parallel native checks and packaging to the same run and DLL bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from collections.abc import Mapping

SCHEMA = 'infini.ci-native-inputs.v1'
ROLES = {'native', 'package'}
EXTERNAL_DLLS = (
    'ParticleLibrary/ParticleLibrary.dll',
    'Luminance/bin/Debug/net8.0/Luminance.dll',
)


def run_identity(env: Mapping[str, str]) -> dict[str, str]:
    identity = {key: env.get(key, '') for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')}
    if not re.fullmatch(r'[0-9a-f]{40}', identity['GITHUB_SHA']):
        raise ValueError('Exact GitHub checkout SHA is required')
    if any(not re.fullmatch(r'[1-9][0-9]*', identity[key]) for key in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')):
        raise ValueError('GitHub run and attempt are required')
    return identity


def _hash(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def capture(role: str, env: Mapping[str, str]) -> dict:
    if role not in ROLES:
        raise ValueError('Unknown native CI role')
    identity = run_identity(env)
    if any(not env.get(key) for key in ('INFINI_TML_REFERENCE_DIR', 'INFINI_TML_DEPS_SRC')):
        raise ValueError('Both restored native reference directories are required')
    refs, deps = Path(env['INFINI_TML_REFERENCE_DIR']), Path(env['INFINI_TML_DEPS_SRC'])
    if not (refs / 'tModLoader.dll').is_file():
        raise ValueError('Restored tModLoader.dll is required')
    inputs = {f'tml/{path.relative_to(refs).as_posix()}': _hash(path)
              for path in sorted(refs.rglob('*')) if path.is_file() and path.suffix.lower() == '.dll'}
    inputs.update({f'external/{relative}': _hash(deps / relative) for relative in EXTERNAL_DLLS})
    return {'schema': SCHEMA, 'role': role, 'run': identity, 'inputs': inputs}


def verify(directory: Path, env: Mapping[str, str]) -> None:
    identity = run_identity(env)
    reports = list(directory.rglob('*.json'))
    if len(reports) != len(ROLES):
        raise ValueError('Expected exactly one native and one package receipt')
    by_role: dict[str, dict] = {}
    for path in reports:
        report = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(report, dict) or report.get('schema') != SCHEMA or not isinstance(report.get('run'), dict):
            raise ValueError('Native input receipt has the wrong schema or run identity')
        receipt_run = run_identity(report['run'])
        # A failed-job rerun reuses the successful leg from an earlier attempt.
        # The unchanged SHA/run, needs.result and full DLL comparison still bind it.
        if any(receipt_run[key] != identity[key] for key in ('GITHUB_SHA', 'GITHUB_RUN_ID')) or (
                int(receipt_run['GITHUB_RUN_ATTEMPT']) > int(identity['GITHUB_RUN_ATTEMPT'])):
            raise ValueError('Native input receipt has the wrong checkout, run or future attempt')
        role, inputs = report.get('role'), report.get('inputs')
        if not isinstance(role, str) or role not in ROLES or role in by_role:
            raise ValueError('Missing, duplicate or unknown native CI role')
        required = {'tml/tModLoader.dll', *(f'external/{relative}' for relative in EXTERNAL_DLLS)}
        if not isinstance(inputs, dict) or not required <= inputs.keys():
            raise ValueError('Required native DLL identities are missing')
        if any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value) for value in inputs.values()):
            raise ValueError('Invalid native DLL digest')
        by_role[role] = inputs
    if by_role['native'] != by_role['package']:
        raise ValueError('Native checks and packaging resolved different DLL bytes or reference rosters')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write-role', choices=sorted(ROLES))
    mode.add_argument('--verify', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.write_role:
            if args.output is None:
                parser.error('--output is required with --write-role')
            report = capture(args.write_role, os.environ)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
            print(f'Recorded {len(report["inputs"])} native DLL identities for {args.write_role}')
        else:
            verify(args.verify, os.environ)
            print('Native checks and packaging used identical native DLL inputs for this checkout/run')
    except (OSError, ValueError) as exc:
        print(f'Native CI input verification failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
