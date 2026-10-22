"""Strict saved-wire replay through the canonical owner, in an offline child."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

from toolbox.infini_toolbox import discover_project
from toolbox.testing.discovery import find_tool


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Validate saved final_item.json and optional snapshot; never rerun inference.')
    parser.add_argument('case', type=Path)
    parser.add_argument('--compare', action='store_true')
    parser.add_argument('--project', type=Path)
    args = parser.parse_args(argv)
    project = discover_project(args.project)
    owner = find_tool(project, 'replay_generation_case.py')

    def no_network(event, _args):
        if event in ('socket.connect', 'socket.getaddrinfo', 'socket.sendto'):
            raise RuntimeError('network forbidden in saved-wire replay')
    sys.addaudithook(no_network)
    with tempfile.TemporaryDirectory(prefix='infini-toolbox-replay-') as temporary:
        for key in list(os.environ):
            if key.startswith('INFINI_'):
                del os.environ[key]
        os.environ.update(INFINI_SKIP_CONFIG_FILE='1', INFINI_USE_LLM='0', INFINI_SDCPP_SERVER_AUTOSTART='0',
                          INFINI_CACHE_DIR=str(Path(temporary) / 'cache'), INFINI_WORLD_RECIPES_DIR=str(Path(temporary) / 'worlds'))
        sys.path.insert(0, str(project / 'LocalGenerator'))
        spec = importlib.util.spec_from_file_location('_toolbox_canonical_replay', owner)
        if spec is None or spec.loader is None:
            raise RuntimeError('Cannot load canonical replay owner')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report = module.build_replay_report(args.case.resolve(), compare=args.compare, rerun=False, replay_raw=None)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
