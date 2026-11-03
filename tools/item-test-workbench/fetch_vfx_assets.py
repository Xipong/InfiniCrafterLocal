#!/usr/bin/env python3
"""Install the pinned ParticleLibrary DLL and resources, or verify an existing DLL.

  python fetch_vfx_assets.py --setup
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
    blob_id = entry.get("gitBlobSha1")
    actual_blob = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest() if blob_id else None
    if (len(data) != entry["bytes"] or
        (entry.get("sha256") is not None and digest(data) != entry["sha256"]) or
        (blob_id is not None and actual_blob != blob_id) or
        (entry.get("sha256") is None and blob_id is None)):
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


def install_file(root: Path, entry: dict, fetch=download) -> bool:
    """Verify an existing file or install downloaded bytes without replacing it."""
    path = destination(root, entry["path"])
    if path.exists():
        verify(path.read_bytes(), entry, str(path))
        return False
    data = fetch(entry)
    verify(data, entry, entry["sourceURL"])
    destination(root, entry["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".asset-", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
            return True
        except FileExistsError:
            verify(path.read_bytes(), entry, str(path))
            return False
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def setup_particle(deps_root: Path, manifest: dict, fetch=download) -> dict:
    """Prepare the real pinned DLL and assets in the standard dependency layout."""
    root = deps_root.expanduser().absolute()
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise ValueError("Dependency root must be a directory, not a symlink")
    installed = manifest["installedDll"]
    if installed["relativePath"] != "ParticleLibrary/ParticleLibrary.dll":
        raise ValueError("Unexpected ParticleLibrary DLL destination")
    expected_url = OFFICIAL_PREFIX + manifest["commit"] + "/ParticleLibrary.dll"
    if installed["sourceURL"] != expected_url:
        raise ValueError("DLL URL is not the exact pinned official source")
    dll_entry = {**installed, "path": installed["relativePath"]}
    downloaded = install_file(root, dll_entry, fetch)
    dll = destination(root, installed["relativePath"])
    result = provision(root / "particle-assets", dll, manifest, fetch)
    result["dll"] = {"path": str(dll), "downloaded": downloaded, "sha256": installed["sha256"]}
    result["environment"]["INFINI_TML_DEPS_SRC"] = str(root)
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
    for entry, _ in paths:
        if install_file(out, entry, fetch):
            downloaded += 1
        else:
            reused += 1
    return {"status": "verified", "package": manifest["package"], "version": manifest["version"],
            "commit": manifest["commit"], "output": str(out), "downloaded": downloaded,
            "reused": reused, "verifiedFiles": len(entries), "verifiedDllSha256": digest(dll),
            "environment": {"INFINI_PARTICLE_ASSET_DIR": str(out)},
            "runtimeReady": False, "note": "Asset integrity verified; native resource initialization remains a separate runtime check."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, help="Asset directory when verifying an existing DLL")
    parser.add_argument("--particle-dll", type=Path, help="Existing pinned ParticleLibrary.dll (otherwise INFINI_TML_DEPS_SRC/ParticleLibrary/ParticleLibrary.dll)")
    parser.add_argument("--setup", action="store_true", help="Install pinned official DLL and assets in the standard dependency layout")
    parser.add_argument("--deps-root", type=Path, help="Dependency root for --setup (default: artifacts/dependencies)")
    args = parser.parse_args()
    if args.setup:
        if args.out or args.particle_dll:
            parser.error("--setup uses its own layout; do not combine with --out or --particle-dll")
        try:
            root = args.deps_root or Path(__file__).resolve().parents[2] / "artifacts/dependencies"
            result = setup_particle(root, json.loads(MANIFEST.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError) as error:
            print(json.dumps({"status": "error", "error": str(error)}))
            return 2
        print(json.dumps(result, indent=2))
        return 0
    if args.out is None or args.deps_root is not None:
        parser.error("Use --out with an existing DLL, or --setup with optional --deps-root")
    dll = args.particle_dll
    if dll is None:
        deps = os.environ.get("INFINI_TML_DEPS_SRC")
        if not deps:
            parser.error("Provide --particle-dll or INFINI_TML_DEPS_SRC, or use --setup to install the pinned DLL")
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
