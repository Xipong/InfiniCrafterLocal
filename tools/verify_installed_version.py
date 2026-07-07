#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path


def read_mod_version(folder: Path) -> str:
    build = folder / "build.txt"
    if not build.exists():
        return "<no build.txt>"
    for line in build.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().lower().startswith("version") and "=" in line:
            return line.split("=", 1)[1].strip()
    return "<unknown>"


def candidates() -> list[Path]:
    out: list[Path] = []
    env_path = os.environ.get("TMODLOADER_MODSOURCES")
    if env_path:
        out.append(Path(env_path))
    userprofile = os.environ.get("USERPROFILE")
    bases: list[Path] = []
    if userprofile:
        bases.append(Path(userprofile))
    bases.append(Path.home())
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


def main() -> int:
    found = False
    for ms in candidates():
        folder = ms / "InfiniCrafterLocal"
        if folder.exists():
            found = True
            print(f"Found:   {folder}")
            print(f"Version: {read_mod_version(folder)}")
    if not found:
        print("InfiniCrafterLocal source folder was not found in common tModLoader ModSources paths.")
    pause()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
