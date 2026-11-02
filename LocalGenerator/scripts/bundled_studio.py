from __future__ import annotations

"""Start the packaged Studio with writable state outside its versioned runtime."""

import argparse
import os
from pathlib import Path
import sys


def configure_environment(data_dir: Path, save_dir: Path | None) -> None:
    data_dir = data_dir.expanduser().resolve()
    save_dir = save_dir.expanduser().resolve() if save_dir else None
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["INFINI_DATA_DIR"] = str(data_dir)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.chdir(data_dir)

    # Load configuration before optional discovery defaults, so saved paths win.
    from infini_local.core.env_utils import load_env_file
    load_env_file(data_dir / "config.env")
    if save_dir is not None:
        dump_dir = save_dir / "InfiniCrafterLocal"
        for name, filename in (("INFINI_ITEMS_RUNTIME_DUMP", "items_runtime_dump.jsonl"),
                               ("INFINI_PROJECTILES_RUNTIME_DUMP", "projectiles_runtime_dump.jsonl")):
            os.environ.setdefault(name, str(dump_dir / filename))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open the Studio included in InfiniCrafterLocal.tmod.")
    parser.add_argument("--data-dir", type=Path, required=True, help="Persistent settings and cache directory.")
    parser.add_argument("--tml-save-dir", type=Path, help="The actual tModLoader save directory, including custom installs.")
    parser.add_argument("--managed", action="store_true", help="Follow the owning tModLoader process over stdin.")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    configure_environment(args.data_dir, args.tml_save_dir)

    from infini_local.desktop.web_studio import main as open_studio
    arguments = ["--port", str(args.port)]
    if args.managed:
        arguments.append("--managed")
    if args.no_browser or args.managed:
        arguments.append("--no-browser")
    open_studio(arguments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
