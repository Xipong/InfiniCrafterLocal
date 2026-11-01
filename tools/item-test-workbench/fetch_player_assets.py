#!/usr/bin/env python3
"""Explicitly fetch 20 pinned COMMUNITY Terraria source PNGs, not official assets.

  python fetch_player_assets.py --out /path/to/terraria-player-assets
  python fetch_player_assets.py --out /path/to/terraria-player-assets --include-dummy
  python fetch_player_assets.py --out /path/to/terraria-player-assets --include-zombie

Use that output root (containing Images/) as the native player asset directory.
--include-dummy adds exactly two optional native training-dummy textures.
--include-zombie adds the original community NPC_3 texture for the controlled target.
These are original source-pngs from a community repository labelled 1.4.4.9,
NOT its generated HD textures. Official byte identity is not certified. No game
assets are bundled with this utility; no downloaded code is executed.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import struct
import tempfile
from fetch_vfx_assets import destination, verify, download

MANIFEST = Path(__file__).with_name("player-assets-manifest.json")
COMMIT = "c835594415e31ed88734dc778661014b48ffb648"
PREFIX = f"https://raw.githubusercontent.com/sullerandras/terraria-hd-textures/{COMMIT}/source-pngs/"
REQUIRED = {f"Player_0_{i}.png" for i in [*range(14), 15]} | {"Player_Hair_1.png", "Player_HairAlt_1.png", "MagicPixel.png", "Dust.png", "Item_0.png"}

DUMMY_REQUIRED = {"NPC_488.png", "Tiles_378.png"}
ZOMBIE_REQUIRED = {"NPC_3.png"}

def verify_png(data: bytes, entry: dict, label: str) -> None:
    verify(data, entry, label)
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError(f"Not a PNG with IHDR: {label}")
    width, height = struct.unpack(">II", data[16:24])
    if (width, height) != (entry["width"], entry["height"]):
        raise ValueError(f"PNG geometry mismatch: {label}")


def provision(out: Path, manifest: dict, fetch=download, *, include_dummy: bool = False, include_zombie: bool = False) -> dict:
    if manifest["commit"] != COMMIT:
        raise ValueError("Unsupported community source commit")
    entries = list(manifest["files"])
    if len(entries) != len(REQUIRED) or {e["path"] for e in entries} != {"Images/" + name for name in REQUIRED}:
        raise ValueError("Manifest must contain exactly the 20 admitted player/source textures")
    if include_dummy:
        extra = manifest.get("trainingDummyFiles", [])
        if len(extra) != 2 or {e["path"] for e in extra} != {"Images/" + name for name in DUMMY_REQUIRED}:
            raise ValueError("Optional dummy manifest must contain exactly NPC_488 and Tiles_378")
        entries += extra
    if include_zombie:
        extra = manifest.get("zombieFiles", [])
        if len(extra) != 1 or {e["path"] for e in extra} != {"Images/" + name for name in ZOMBIE_REQUIRED}:
            raise ValueError("Optional zombie manifest must contain exactly NPC_3")
        entries += extra
    out = out.absolute()
    if any(part.is_symlink() for part in (out, *out.parents)) or (out.exists() and not out.is_dir()):
        raise ValueError("Output must be a non-symlink directory")
    rows = []
    for entry in entries:
        name = Path(entry["path"]).name
        if entry["sourceURL"] != PREFIX + name:
            raise ValueError("Not the exact pinned community source URL: " + name)
        if not 24 <= entry["bytes"] <= 4 * 1024 * 1024:
            raise ValueError("Invalid bounded asset size")
        path = destination(out, entry["path"])
        if path.exists():
            verify_png(path.read_bytes(), entry, str(path))
        rows.append((entry, path))
    fetched = reused = 0
    for entry, path in rows:
        if path.exists():
            verify_png(path.read_bytes(), entry, str(path)); reused += 1; continue
        data = fetch(entry)
        verify_png(data, entry, entry["sourceURL"])
        destination(out, entry["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(prefix=".player-asset-", dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name); stream.write(data); stream.flush(); os.fsync(stream.fileno())
            try:
                os.link(temporary, path); fetched += 1
            except FileExistsError:
                verify_png(path.read_bytes(), entry, str(path)); reused += 1
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return {"status": "verified", "output": str(out), "downloaded": fetched, "reused": reused,
            "verifiedFiles": len(entries), "includesTrainingDummy": include_dummy, "includesZombie": include_zombie, "communityCommit": COMMIT, "versionClaim": "1.4.4.9",
            "officialByteIdentityVerified": False, "nativeRuntimeReady": False,
            "scope": "Pinned community source PNG integrity and dimensions verified; original native rendering is checked separately."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--include-dummy", action="store_true", help="Also fetch the two pinned native training-dummy textures (default: 20 player/empty-item textures)")
    parser.add_argument("--include-zombie", action="store_true", help="Also fetch the pinned controlled zombie texture")
    args = parser.parse_args()
    try:
        result = provision(args.out, json.loads(MANIFEST.read_text(encoding="utf-8")), include_dummy=args.include_dummy, include_zombie=args.include_zombie)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "error", "error": str(error)})); return 2
    print(json.dumps(result, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
