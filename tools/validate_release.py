#!/usr/bin/env python3
"""Platform dispatcher for the real shell/PowerShell validation runners."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if os.name == "nt":
        script = ROOT / "tools" / "validate_release_windows.ps1"
        proc = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script), *sys.argv[1:]],
            cwd=ROOT,
            check=False,
        )
        return proc.returncode
    script = ROOT / "tools" / "validate_release.sh"
    os.execv("/usr/bin/env", ["env", "bash", str(script), *sys.argv[1:]])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
