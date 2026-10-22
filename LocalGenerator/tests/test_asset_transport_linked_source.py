"""Run the complete C# asset owner against test-only packet/DTO boundaries.

This is a linked-source CPU check, not a native tML or live Steam match.
The fixture never starts the game, calls a model, or opens a network listener.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_asset_transport_linked_source(tmp_path: Path) -> None:
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        if os.environ.get("CI"):
            pytest.fail("Asset transport behavioral checks require the .NET 8 SDK in CI")
        pytest.skip(".NET SDK unavailable; asset transport execution is notRun")
    project = ROOT / "tools" / "native" / "AssetTransportChecks" / "AssetTransportChecks.csproj"
    environment = {**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}
    output_dir = tmp_path / "bin"
    build = subprocess.run(
        [dotnet, "build", str(project), "--configuration", "Release",
         "--output", str(output_dir),
         f"-p:BaseIntermediateOutputPath={tmp_path / 'obj'}/"],
        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=180,
        check=False,
    )
    build_output = build.stdout + build.stderr
    assert build.returncode == 0, build_output
    # `dotnet run` can resolve the default apphost despite redirected build paths.
    # Execute exactly the DLL just built, never an old project-local executable.
    result = subprocess.run(
        [dotnet, str(output_dir / "AssetTransportChecks.dll")],
        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=180,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, build_output + output
    assert "Asset transport checks: 14/14 passed" in output, output
