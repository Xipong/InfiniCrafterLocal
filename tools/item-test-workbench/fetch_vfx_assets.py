#!/usr/bin/env python3
"""Fetch pinned official ParticleLibrary assets; never install/replace its DLL.

  python fetch_vfx_assets.py --out /path/to/ParticleLibrary-assets --particle-dll /path/to/ParticleLibrary.dll
  export INFINI_PARTICLE_ASSET_DIR=/path/to/ParticleLibrary-assets

The output contains third-party GPL-3.0 resources and their LICENSE, fetched only
on explicit execution. No third-party binaries/assets are bundled in this utility.
Existing verified files are reused; corrupt or unexpected files are not overwritten.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import urllib.request

MANIFEST = Path(__file__).with_name("vfx-assets-manifest.json")
OFFICIAL_PREFIX = "https://raw.githubusercontent.com/SnowyStarfall/ParticleLibrary/"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify(data: bytes, entry: dict, label: str) -> None:
    if len(data) != entry["bytes"] or digest(data) != entry["sha256"]:
        raise ValueError(f"Integrity mismatch: {label}; refusing to install/overwrite")


def download(entry: dict) -> bytes:
    request = urllib.request.Request(entry["sourceURL"], headers={"User-Agent": "InfiniCrafter-item-workbench-dependency-setup"})
    with urllib.request.urlopen(request, timeout=45) as response:
        # Bounded read also rejects a larger-than-declared response.
        return response.read(entry["bytes"] + 1)


def destination(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if not relative or "\\" in relative or pure.is_absolute() or any(p in ("", ".", "..") for p in relative.split("/")):
        raise ValueError(f"Unsafe manifest path: {relative}")
    result = root.joinpath(*pure.parts)
    for part in (result, *result.parents):
        if part == root.parent:
            break
        if part.is_symlink():
            raise ValueError(f"Symlink destination is not admitted: {part}")
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Destination escapes output directory: {relative}")
    return result


def provision(out: Path, particle_dll: Path, manifest: dict, fetch=download) -> dict:
    dll = particle_dll.read_bytes()
    verify(dll, manifest["installedDll"], str(particle_dll))
    out = out.absolute()
    if out.is_symlink():
        raise ValueError("Output directory must not be a symlink")
    if out.exists() and not out.is_dir():
        raise ValueError("Output must be a directory")
    entries = manifest["files"]
    if not entries:
        raise ValueError("Manifest has no assets")
    paths = []
    seen = set()
    for entry in entries:
        relative = entry["path"]
        if relative in seen:
            raise ValueError("Duplicate manifest path: " + relative)
        seen.add(relative)
        if entry["sourceURL"] != OFFICIAL_PREFIX + manifest["commit"] + "/" + relative:
            raise ValueError("Asset URL is not the exact pinned official source: " + relative)
        path = destination(out, relative)
        if path.exists():
            verify(path.read_bytes(), entry, str(path))
        paths.append((entry, path))
    downloaded = reused = 0
    for entry, path in paths:
        if path.exists():
            verify(path.read_bytes(), entry, str(path))
            reused += 1
            continue
        data = fetch(entry)
        verify(data, entry, entry["sourceURL"])
        # Revalidate after the fetch, before creating anything.
        destination(out, entry["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(prefix=".asset-", dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            # Exclusive atomic creation: never replace a concurrently created file.
            try:
                os.link(temporary, path)
                downloaded += 1
            except FileExistsError:
                verify(path.read_bytes(), entry, str(path))
                reused += 1
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return {"status": "verified", "package": manifest["package"], "version": manifest["version"],
            "commit": manifest["commit"], "output": str(out), "downloaded": downloaded,
            "reused": reused, "verifiedFiles": len(entries), "verifiedDllSha256": digest(dll),
            "environment": {"INFINI_PARTICLE_ASSET_DIR": str(out)},
            "runtimeReady": False, "note": "Asset integrity verified; native resource initialization remains a separate runtime check."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--particle-dll", type=Path, help="Existing pinned ParticleLibrary.dll (otherwise INFINI_TML_DEPS_SRC/ParticleLibrary/ParticleLibrary.dll)")
    args = parser.parse_args()
    dll = args.particle_dll
    if dll is None:
        deps = os.environ.get("INFINI_TML_DEPS_SRC")
        if not deps:
            parser.error("Provide --particle-dll or INFINI_TML_DEPS_SRC; DLL downloads are deliberately unsupported")
        dll = Path(deps) / "ParticleLibrary" / "ParticleLibrary.dll"
    try:
        result = provision(args.out, dll, json.loads(MANIFEST.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "error", "error": str(error)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
