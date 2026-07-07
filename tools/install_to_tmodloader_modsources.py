#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def read_mod_version(folder: Path) -> str:
    build = folder / "build.txt"
    if not build.exists():
        return "<no build.txt>"
    for line in build.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().lower().startswith("version") and "=" in line:
            return line.split("=", 1)[1].strip()
    return "<unknown>"


def candidate_modsources() -> list[Path]:
    out: list[Path] = []
    env_path = os.environ.get("TMODLOADER_MODSOURCES")
    if env_path:
        out.append(Path(env_path))

    userprofile = os.environ.get("USERPROFILE")
    home = Path.home()
    bases: list[Path] = []
    if userprofile:
        bases.append(Path(userprofile))
    bases.append(home)

    for base in bases:
        out.append(base / "Documents" / "My Games" / "Terraria" / "tModLoader" / "ModSources")
        out.append(base / "OneDrive" / "Documents" / "My Games" / "Terraria" / "tModLoader" / "ModSources")
        out.append(base / "OneDrive" / "Документы" / "My Games" / "Terraria" / "tModLoader" / "ModSources")
        out.append(base / "Документы" / "My Games" / "Terraria" / "tModLoader" / "ModSources")

    unique: list[Path] = []
    seen: set[str] = set()
    for p in out:
        key = str(p).lower()
        if key not in seen:
            unique.append(p)
            seen.add(key)
    return unique


def pause() -> None:
    try:
        input("Press Enter to close")
    except EOFError:
        pass


def main(argv: list[str]) -> int:
    script_dir = Path(__file__).resolve().parent
    root = script_dir.parent
    source = root / "ModSources" / "InfiniCrafterLocal"
    if not source.exists():
        print(f"Source mod folder not found: {source}")
        print("Extract the archive first, then run this installer from the extracted folder.")
        pause()
        return 1

    if len(argv) > 1:
        mod_sources = Path(argv[1])
    else:
        existing = next((p for p in candidate_modsources() if p.exists()), None)
        if existing is not None:
            mod_sources = existing
        else:
            mod_sources = Path.home() / "Documents" / "My Games" / "Terraria" / "tModLoader" / "ModSources"

    dest = mod_sources / "InfiniCrafterLocal"
    source_version = read_mod_version(source)

    print("InfiniCrafterLocal source installer")
    print(f"Source:      {source}")
    print(f"Source ver:  {source_version}")
    print(f"ModSources:  {mod_sources}")
    print(f"Destination: {dest}")

    mod_sources.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        old_version = read_mod_version(dest)
        print(f"Removing previous installed source: {old_version}")
        shutil.rmtree(dest)

    shutil.copytree(source, dest)
    installed_version = read_mod_version(dest)
    print(f"Installed version: {installed_version}")
    if installed_version != source_version:
        print(f"Installed version mismatch. Source={source_version} Installed={installed_version}")
        pause()
        return 1

    print("")
    print("Next steps:")
    print("1) Open tModLoader.")
    print("2) Workshop > Develop Mods.")
    print("3) Build + Reload InfiniCrafterLocal.")
    print("4) In the mod list you should see exactly this version.")
    print("")
    pause()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
