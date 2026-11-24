from __future__ import annotations

"""One-click runtime setup/launch. No application imports or global pip installs."""

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
STAMP_NAME = ".infinicraft-requirements.sha256"


def runtime_python(root: Path, *, windows: bool | None = None) -> Path:
    windows = os.name == "nt" if windows is None else windows
    return root / ".venv" / ("Scripts/python.exe" if windows else "bin/python")


def requirements_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_runtime(root: Path, *, refresh: bool = False) -> Path:
    python = runtime_python(root)
    requirements = root / "requirements.txt"
    stamp = root / ".venv" / STAMP_NAME
    digest = requirements_digest(requirements)
    if not python.is_file():
        print("Preparing an isolated generator environment (.venv)...", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(root / ".venv")], check=True)
    # A reused/moved environment is checked before trusting its dependency stamp.
    subprocess.run([str(python), "-c", "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ is required'"], check=True)
    ready = stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == digest
    if refresh or not ready:
        print("Installing the generator's runtime dependencies...", flush=True)
        subprocess.run([str(python), "-m", "pip", "install", "-r", str(requirements)], check=True)
        stamp.write_text(digest, encoding="utf-8")
    return python


def print_doctor() -> None:
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    print(f"Generator: {ROOT}")
    print(f"Runtime Python: {runtime_python(ROOT)}")
    print(f"Requirements: {ROOT / 'requirements.txt'}")
    config = ROOT / "config.env"
    print(f"config.env: {config} ({'exists, preserved' if config.exists() else 'not saved yet'})")
    print("Doctor is read-only; no dependencies installed or models contacted.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare/open Infinicraft without installing into system Python.")
    parser.add_argument("action", choices=("gui", "setup", "server", "doctor"), nargs="?", default="gui")
    parser.add_argument("--no-browser", action="store_true", help="Print the local Studio URL instead of opening a browser.")
    parser.add_argument("--root", type=Path, help="Path to another extracted Infinicraft root (server only).")
    args = parser.parse_args(argv)
    if args.no_browser and args.action != "gui":
        parser.error("--no-browser requires gui")
    if args.root is not None and args.action != "server":
        parser.error("--root requires server")
    if args.action == "doctor":
        print_doctor()
        return 0
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required. Install it from python.org.", file=sys.stderr)
        return 2
    try:
        root = (args.root.expanduser().resolve() / "generator") if args.root is not None else ROOT
        if not (root / "server.py").is_file():
            raise FileNotFoundError(f"Generator server.py not found: {root}")
        python = prepare_runtime(root, refresh=args.action == "setup")
        if args.action == "setup":
            print("Runtime ready. Open OPEN_INFINICRAFT.bat. Personal config.env was not changed.")
            return 0
        command = [str(python), "-u", "-B"]
        if args.action == "gui":
            command.extend(("-m", "infini_local.desktop.web_studio"))
            if args.no_browser:
                command.append("--no-browser")
        else:
            command.append(str(root / "server.py"))
        return subprocess.run(command, cwd=root, check=False).returncode
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Generator setup/launch failed: {exc}", file=sys.stderr)
        print("Keep the error above. Check Python, internet access and write permissions; retry the launcher.", file=sys.stderr)
        return exc.returncode if isinstance(exc, subprocess.CalledProcessError) else 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
