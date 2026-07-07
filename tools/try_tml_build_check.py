#!/usr/bin/env python3
"""Optional real tModLoader compile smoke check.

This repo normally contains a tModLoader ModSources folder, not a standalone
SDK-style .csproj.  In this container there is no dotnet/tModLoader install, so
CI uses tools/check_csharp_contracts.py for static compile-surface coverage.

On a real dev machine you can run this helper with one of:
  python tools/try_tml_build_check.py --project path/to/InfiniCrafterLocal.csproj
  python tools/try_tml_build_check.py --tmodloader path/to/tModLoader.dll

The helper fails only when an explicitly requested build target fails. If no
build target is provided, it prints SKIP and exits 0 so pytest can run anywhere.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODSRC = ROOT / "ModSources" / "InfiniCrafterLocal"
WINDOWS_DOTNET_CANDIDATES = (
    Path("/mnt/c/Program Files/dotnet/dotnet.exe"),
    Path("/mnt/c/Program Files (x86)/dotnet/dotnet.exe"),
)
LOG_DIR = ROOT / "build_logs"


def resolve_dotnet_command(extra_candidates: list[Path] | None = None) -> str:
    """Find a dotnet command usable from Linux/WSL.

    `shutil.which("dotnet")` is enough on Linux CI, but local WSL setups often
    expose only Windows `dotnet.exe`.  Return a string suitable as argv[0]; keep
    the command list-based so paths with spaces remain safe.
    """
    for name in ("dotnet", "dotnet.exe"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in list(extra_candidates or []) + list(WINDOWS_DOTNET_CANDIDATES):
        p = Path(candidate).expanduser()
        if p.exists():
            return str(p)
    return ""


def _uses_windows_dotnet(dotnet_cmd: str) -> bool:
    return Path(str(dotnet_cmd)).name.lower() == "dotnet.exe" or str(dotnet_cmd).lower().endswith("dotnet.exe")


def msbuild_path_value(path: Path, dotnet_cmd: str) -> str:
    """Return a path value that the selected dotnet/MSBuild process can read."""
    p = Path(path).expanduser().resolve()
    if not _uses_windows_dotnet(dotnet_cmd):
        return str(p)
    proc = subprocess.run(["wslpath", "-w", str(p)], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    distro = "Ubuntu-24.04"
    return "\\\\wsl.localhost\\" + distro + str(p).replace("/", "\\")


def parse_log(log_path: Path) -> int:
    parser = ROOT / "tools" / "parse_tml_build_log.py"
    if not parser.exists():
        return 0
    proc = subprocess.run([sys.executable, str(parser), str(log_path)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(proc.stdout)
    return proc.returncode


def run(cmd: list[str], cwd: Path) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"tml_build_{stamp}.log"
    print("[run]", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log_path.write_text(proc.stdout, encoding="utf-8", errors="ignore")
    print(proc.stdout)
    print(f"[log] {log_path}")
    parse_code = parse_log(log_path)
    return proc.returncode if proc.returncode != 0 else parse_code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", help="explicit SDK/tML csproj to dotnet build")
    ap.add_argument("--configuration", default="Debug", help="dotnet build configuration")
    ap.add_argument("--tmodloader", help="reserved path to tModLoader.dll/tML install; currently only validates presence")
    ap.add_argument("--external-deps-root", help="ParticleLibrary/Luminance dependency root to pass as InfiniExternalDepsRoot")
    args = ap.parse_args()

    dotnet_cmd = resolve_dotnet_command()
    if not dotnet_cmd:
        print("[SKIP] dotnet is not installed; static C# compile-surface tests still run via check_csharp_contracts.py")
        return 0

    if args.project:
        project = Path(args.project).expanduser().resolve()
        if not project.exists():
            print(f"[FAIL] project not found: {project}")
            return 2
        project_arg = msbuild_path_value(project, dotnet_cmd)
        cmd = [dotnet_cmd, "build", project_arg, "-c", args.configuration, "--nologo", "-v:minimal"]
        if args.external_deps_root:
            deps_root = Path(args.external_deps_root).expanduser()
            if not deps_root.exists():
                print(f"[FAIL] external deps root not found: {deps_root}")
                return 2
            cmd.append(f"/p:InfiniExternalDepsRoot={msbuild_path_value(deps_root, dotnet_cmd)}")
        return run(cmd, project.parent)

    if args.tmodloader:
        tml = Path(args.tmodloader).expanduser().resolve()
        if not tml.exists():
            print(f"[FAIL] tModLoader path not found: {tml}")
            return 2
        print("[SKIP] direct tModLoader command-line build target is install-specific; use --project when available.")
        return 0

    print(f"[SKIP] no standalone csproj in {MODSRC}; provide --project on a real tML dev install for a true compile.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
