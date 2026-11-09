"""Thin explicit dispatcher to the existing native parent-capture owner."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

from toolbox.live.catalog import DEFAULT_PRESETS, load_panel


def main(argv: list[str], *, panel_command: str = 'live40') -> int:
    parser = argparse.ArgumentParser(
        prog=f'python -m toolbox {panel_command}',
        description='Capture the selected raw native Prepare inputs. No provider, Author, or gameplay execution.',
    )
    parser.add_argument('--offline', action='store_true', required=True)
    parser.add_argument('--native-executable', type=Path, required=True,
                        help='Existing trusted EngineRuntimeChecks executable or DLL; no automatic build/install.')
    parser.add_argument('--dotnet', type=Path,
                        help='Explicit dotnet host for a DLL (otherwise dotnet from PATH). Not valid for an executable.')
    parser.add_argument('--output', type=Path, required=True,
                        help='New or empty capture directory; never combine with previous evidence.')
    args = parser.parse_args(argv)
    try:
        executable = args.native_executable.expanduser().resolve()
        output = args.output.expanduser().resolve()
        if not executable.is_file():
            raise ValueError('--native-executable must name an existing native harness executable or DLL')
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise ValueError('--output must be a new or empty directory')
        if executable.suffix.lower() == '.dll':
            if args.dotnet is None:
                host = 'dotnet'
            else:
                host_path = args.dotnet.expanduser().resolve()
                if not host_path.is_file():
                    raise ValueError('--dotnet must name an existing host executable')
                host = str(host_path)
            command = [host, str(executable)]
        else:
            if args.dotnet is not None:
                raise ValueError('--dotnet is only valid with a native DLL')
            command = [str(executable)]
        panel = load_panel(DEFAULT_PRESETS[panel_command])
        command += ['--capture-parent-panel', str(panel['sourcePath']), str(output)]
        # The native owner validates manifest/identities and writes all receipts.
        # Do not initialize generator configuration, credentials, or providers here.
        return subprocess.run(command).returncode
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 2
