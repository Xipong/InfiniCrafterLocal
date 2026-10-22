"""Compatibility entry: prefer python -m toolbox live20 (offline by default)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from toolbox.cli import main  # noqa: E402

if __name__ == '__main__':
    raise SystemExit(main(['live20', *sys.argv[1:]]))
