"""Build the private Studio runtime embedded in the official .tmod package.

Players do not run pip: the release builder vendors binary wheels beside an
isolated CPython distribution. The ZIP preserves web images from tML's PNG
conversion. Generated payloads belong to build output, never to Git.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import queue
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[2]
RESOURCE_MANIFEST = "Studio/manifest.json"
PLATFORM = "win-x64"
RESOURCE_ARCHIVE = f"Studio/runtime-{PLATFORM}.zip"
PYTHON_VERSION = "3.14.10"
PYTHON_TAG = "314"
# Published by https://www.python.org/downloads/release/python-31410/.
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
PYTHON_SHA256 = "90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159"
ENTRY_POINT = "LocalGenerator/scripts/bundled_studio.py"
SOURCE_FILES = (
    "LocalGenerator/server.py",
    "LocalGenerator/config.example.env",
    "LocalGenerator/requirements.txt",
    ENTRY_POINT,
    "LocalGenerator/data/item_knowledge.json",
    "LocalGenerator/data/vanilla_seed_items.json",
    "START_HERE.html",
    "LICENSE",
    "LICENSE_RU.md",
)
SOURCE_DIRS = ("LocalGenerator/infini_local", "contracts", "docs/user")
MAX_UNPACKED_BYTES = 512 * 1024 * 1024


def source_files(root: Path) -> dict[str, Path]:
    """An allowlist of code/resources, excluding operator state and credentials."""
    files = {name: root / name for name in SOURCE_FILES}
    for name in SOURCE_DIRS:
        directory = root / name
        if not directory.is_dir():
            raise ValueError(f"Required Studio source directory missing: {name}")
        for path in directory.rglob("*"):
            relative = path.relative_to(root)
            if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
                continue
            if path.name == "AGENTS.md" or path.suffix in {".pyc", ".pyo"}:
                continue
            if path.is_symlink():
                raise ValueError(f"Studio sources must not contain symlinks: {relative}")
            if path.is_file():
                files[relative.as_posix()] = path
    for name, path in files.items():
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Required Studio source file missing or linked: {name}")
    return files


def safe_archive_entries(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    files: dict[str, zipfile.ZipInfo] = {}
    seen: set[str] = set()
    total = 0
    for entry in archive.infolist():
        name = entry.filename
        parts = name.rstrip("/").split("/")
        if (not name or "\\" in name or ":" in name or name.startswith("/")
                or any(part in {"", ".", ".."} for part in parts)
                or stat.S_ISLNK(entry.external_attr >> 16)):
            raise ValueError(f"Unsafe Studio archive path: {name}")
        key = name.rstrip("/").casefold()
        if key in seen:
            raise ValueError(f"Duplicate Studio archive path: {name}")
        seen.add(key)
        total += entry.file_size
        if len(seen) > 20000 or total > MAX_UNPACKED_BYTES:
            raise ValueError("Studio archive exceeds its extraction budget")
        if not entry.is_dir():
            files[name] = entry
    return files


def verify_resources(read: Callable[[str], bytes], *, source_root: Path | None = None) -> dict:
    """Check the same manifest and nested bytes that the game's launcher reads."""
    try:
        manifest = json.loads(read(RESOURCE_MANIFEST))
    except (KeyError, FileNotFoundError) as exc:
        raise ValueError("Studio manifest missing from package") from exc
    if manifest.get("schemaVersion") != 1 or not isinstance(manifest.get("platforms"), dict):
        raise ValueError("Unsupported Studio manifest")
    platforms = manifest["platforms"]
    if PLATFORM not in platforms:
        raise ValueError("Studio package has no Windows x64 runtime")
    reports = {}
    for platform, descriptor in platforms.items():
        name = descriptor.get("archive", "")
        if not name.startswith("Studio/") or PurePosixPath(name).name != f"runtime-{platform}.zip":
            raise ValueError("Invalid Studio runtime resource name")
        if any(part in {"", ".", ".."} for part in name.split("/")) or "\\" in name:
            raise ValueError("Invalid Studio runtime resource name")
        try:
            payload = read(name)
        except (KeyError, FileNotFoundError) as exc:
            raise ValueError(f"Studio runtime missing: {name}") from exc
        digest = hashlib.sha256(payload).hexdigest()
        if digest != descriptor.get("sha256"):
            raise ValueError(f"Studio runtime hash mismatch: {name}")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            files = safe_archive_entries(archive)
            required = {
                descriptor.get("python", ""), descriptor.get("entryPoint", ""),
                "LocalGenerator/server.py", "LocalGenerator/config.example.env",
                "LocalGenerator/infini_local/desktop/web_studio.py",
                "LocalGenerator/infini_local/desktop/webui/index.html",
                "LocalGenerator/infini_local/desktop/webui/studio.js",
                "LocalGenerator/infini_local/desktop/webui/studio.css",
                "python/Lib/site-packages/PIL/__init__.py",
                "python/Lib/site-packages/pydantic/__init__.py",
                "python/Lib/site-packages/pydantic_core/__init__.py",
                "START_HERE.html", "LICENSE", "python/LICENSE.txt",
                f"python/python{PYTHON_TAG}.dll",
                f"python/python{PYTHON_TAG}.zip", f"python/python{PYTHON_TAG}._pth",
            }
            if not required.issubset(files):
                raise ValueError(f"Incomplete Studio runtime: {sorted(required - files.keys())}")
            # These native dependencies must be present, not imported from the build machine.
            for prefix in ("python/Lib/site-packages/pydantic_core/_pydantic_core",
                           "python/Lib/site-packages/PIL/_imaging"):
                if not any(path.startswith(prefix) and path.endswith(".pyd") for path in files):
                    raise ValueError(f"Studio native dependency missing: {prefix}")
            if not archive.read(descriptor["python"]).startswith(b"MZ"):
                raise ValueError("Studio Python executable is not a Windows executable")
            if source_root is not None:
                for path, source in source_files(source_root).items():
                    if path not in files or archive.read(path) != source.read_bytes():
                        raise ValueError(f"Studio source missing or changed: {path}")
            bad_state = ("config.env", "config.env.defaults.json", "gui_user_presets.json", "codex-auth.json")
            for path in files:
                parts = PurePosixPath(path).parts
                if (PurePosixPath(path).name in bad_state
                        or any(part in {".git", ".venv", "__pycache__", "cache", "prompt_traces", ".codex"} for part in parts)):
                    raise ValueError(f"Operator state/development debris in Studio runtime: {path}")
            bad = archive.testzip()
            if bad is not None:
                raise ValueError(f"Corrupt Studio archive entry: {bad}")
            reports[platform] = {"sha256": digest, "bytes": len(payload), "files": len(files)}
    return reports


def copy_sources(root: Path, destination: Path) -> None:
    for name, source in source_files(root).items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def prepare_python(archive_path: Path, destination: Path) -> None:
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != PYTHON_SHA256:
        raise ValueError("Official embedded Python archive SHA256 mismatch")
    destination.mkdir(parents=True)
    with zipfile.ZipFile(archive_path) as archive:
        safe_archive_entries(archive)
        archive.extractall(destination)
    (destination / f"python{PYTHON_TAG}._pth").write_text(
        f"python{PYTHON_TAG}.zip\n.\nLib/site-packages\n../LocalGenerator\nimport site\n", encoding="utf-8")


def install_dependencies(root: Path, destination: Path, wheelhouse: Path | None) -> None:
    command = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-compile",
               "--only-binary=:all:", "--platform", "win_amd64", "--python-version", PYTHON_VERSION,
               "--implementation", "cp", "--abi", f"cp{PYTHON_TAG}", "--no-warn-script-location",
               "--target", str(destination / "Lib/site-packages"),
               "--report", str(destination / "dependencies.json"),
               "-r", str(root / "LocalGenerator/requirements.txt"),
               "-c", str(root / "LocalGenerator/requirements-dev.lock")]
    if wheelhouse is not None:
        command += ["--no-index", "--find-links", str(wheelhouse)]
    subprocess.run(command, check=True)


def smoke_test(staged: Path) -> None:
    """Exercise the shipped interpreter and real HTTP server, without opening a browser."""
    if os.name != "nt":
        raise RuntimeError("The Windows Studio runtime smoke must run on Windows")
    python = staged / "python/python.exe"
    with tempfile.TemporaryDirectory(prefix="ifc-studio-smoke-") as temporary:
        data = Path(temporary)
        environment = {name: value for name, value in os.environ.items() if not name.startswith("INFINI_")}
        environment["INFINI_DATA_DIR"] = str(data / "data")
        environment["PYTHONIOENCODING"] = "utf-8"
        subprocess.run([str(python), "-X", "utf8", "-B", "-c",
                        "from PIL import Image; from pydantic import BaseModel; "
                        "import infini_local.web.server; import infini_local.desktop.web_studio"],
                       env=environment, cwd=temporary, check=True, timeout=30)
        process = subprocess.Popen(
            [str(python), "-X", "utf8", "-u", "-B", str(staged / ENTRY_POINT), "--data-dir", str(data / "data"),
             "--tml-save-dir", str(data / "tModLoader"), "--managed"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=environment, cwd=temporary, text=True, encoding="utf-8")
        output: queue.Queue[str | None] = queue.Queue()
        lines: list[str] = []

        def collect() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                output.put(line)
            output.put(None)

        reader = threading.Thread(target=collect, daemon=True)
        reader.start()
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    line = output.get(timeout=max(0, deadline - time.monotonic()))
                except queue.Empty as exc:
                    raise RuntimeError("Bundled Studio readiness timed out:\n" + "".join(lines)) from exc
                if line is None:
                    raise RuntimeError("Bundled Studio exited before readiness:\n" + "".join(lines))
                lines.append(line)
                if line.startswith("IFC_STUDIO_READY "):
                    ready = json.loads(line.removeprefix("IFC_STUDIO_READY "))
                    break
            with urllib.request.urlopen(ready["url"], timeout=10) as response:
                if response.status != 200 or not response.read():
                    raise RuntimeError("Bundled Studio did not serve its frontend")
            assert process.stdin is not None
            process.stdin.write("STOP\n")
            process.stdin.flush()
            process.stdin.close()
            if process.wait(timeout=15) != 0:
                raise RuntimeError("Bundled Studio did not shut down cleanly:\n" + "".join(lines))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            reader.join(timeout=5)
            if process.stdout is not None:
                process.stdout.close()


def write_bundle(staged: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / PurePosixPath(RESOURCE_ARCHIVE).name
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(staged.rglob("*")):
            if path.is_file():
                name = path.relative_to(staged).as_posix()
                entry = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, path.read_bytes())
    manifest = {"schemaVersion": 1, "platforms": {PLATFORM: {
        "archive": RESOURCE_ARCHIVE, "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "python": "python/python.exe", "pythonVersion": PYTHON_VERSION, "entryPoint": ENTRY_POINT,
    }}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--python-archive", type=Path, help="Use a cached official archive; its pinned hash is still checked.")
    parser.add_argument("--wheelhouse", type=Path, help="Install pinned runtime wheels offline from this directory.")
    parser.add_argument("--skip-smoke", action="store_true", help="Build on another OS; never used by release packaging.")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = (args.output or root / "ModSources/InfiniCrafterLocal/Studio").resolve()
    source_files(root)  # Fail before downloading when the source tree is incomplete.
    with tempfile.TemporaryDirectory(prefix="ifc-studio-build-") as temporary:
        work = Path(temporary)
        python_archive = args.python_archive
        if python_archive is None:
            python_archive = work / "python.zip"
            with urllib.request.urlopen(PYTHON_URL, timeout=90) as response, python_archive.open("wb") as file:
                shutil.copyfileobj(response, file)
        staged = work / "runtime"
        copy_sources(root, staged)
        prepare_python(python_archive, staged / "python")
        install_dependencies(root, staged / "python", args.wheelhouse)
        if not args.skip_smoke:
            smoke_test(staged)
        manifest = write_bundle(staged, output)
        report = verify_resources(lambda name: (output / PurePosixPath(name).name).read_bytes(), source_root=root)
        print(json.dumps({"resources": str(output), "platforms": report,
                          "python": manifest["platforms"][PLATFORM]["pythonVersion"],
                          "runtimeSmoke": "notRun: explicitly skipped" if args.skip_smoke else "passed"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
