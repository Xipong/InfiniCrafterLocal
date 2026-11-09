from __future__ import annotations

"""Start the packaged Studio with writable state outside its versioned runtime."""

import argparse
import base64
import os
from pathlib import Path
import sys


def configure_environment(data_dir: Path, save_dir: Path | None, image_root: str | None = None) -> None:
    data_dir = data_dir.expanduser().resolve()
    save_dir = save_dir.expanduser().resolve() if save_dir else None
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["INFINI_DATA_DIR"] = str(data_dir)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.chdir(data_dir)

    # The game-selected root is authoritative in both bundled launch modes.
    if image_root is not None:
        os.environ["INFINI_IMAGE_DIR"] = image_root

    # Load configuration before optional discovery defaults, so saved paths win.
    from infini_local.core.env_utils import load_env_file
    load_env_file(data_dir / "config.env")
    if save_dir is not None:
        dump_dir = save_dir / "InfiniCrafterLocal"
        os.environ.setdefault("INFINI_IMAGE_DIR", str(dump_dir / "images"))
        for name, filename in (("INFINI_ITEMS_RUNTIME_DUMP", "items_runtime_dump.jsonl"),
                               ("INFINI_PROJECTILES_RUNTIME_DUMP", "projectiles_runtime_dump.jsonl")):
            os.environ.setdefault(name, str(dump_dir / filename))

    # Preserve this launch binding across Studio saves and generator restarts.
    if os.environ.get("INFINI_IMAGE_DIR"):
        os.environ["INFINI_STUDIO_IMAGE_ROOT"] = os.environ["INFINI_IMAGE_DIR"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open the Studio included in InfiniCrafterLocal.tmod.")
    parser.add_argument("--data-dir", type=Path, required=True, help="Persistent settings and cache directory.")
    parser.add_argument("--tml-save-dir", type=Path, help="The actual tModLoader save directory, including custom installs.")
    parser.add_argument("--image-root-base64", help="Game-selected UTF-8 image root, encoded for safe BAT transport.")
    parser.add_argument("--managed", action="store_true", help="Follow the owning tModLoader process over stdin.")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    image_root = None
    if args.image_root_base64 is not None:
        try:
            image_root = base64.b64decode(args.image_root_base64, validate=True).decode("utf-8")
            if not image_root or "\x00" in image_root:
                raise ValueError("Empty or NUL-containing path")
        except (ValueError, UnicodeError) as exc:
            parser.error(f"Invalid encoded image root: {exc}")
    configure_environment(args.data_dir, args.tml_save_dir, image_root)

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
