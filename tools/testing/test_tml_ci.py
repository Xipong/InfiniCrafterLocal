"""Offline executable CI regression: real workflow, build script and log parser.

Only the native compiler is synthetic; no SDK restore or game build is run.
Run with python tools/testing/test_tml_ci.py. Requires PowerShell 7 (also on Linux).
TML_TEST_PWSH may select pwsh.exe under WSL; fixtures remain in tempfile's root.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
PWSH = os.environ.get("TML_TEST_PWSH") or shutil.which("pwsh") or shutil.which("pwsh.exe")
WINDOWS_SHELL = os.name == "nt" or bool(PWSH and PWSH.endswith(".exe"))


def shell_path(path: Path) -> str:
    if os.name != "nt" and WINDOWS_SHELL:
        return subprocess.check_output(["wslpath", "-w", str(path)], text=True).strip()
    return str(path)


def quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class TmlWorkflowTests(unittest.TestCase):
    def run_workflow(self, *, code: int = 0, diagnostic: bool = False,
                     deps: bool = True, parser_code: int | None = None) -> tuple[int, str, str]:
        self.assertIsNotNone(PWSH, "PowerShell 7 is required; this regression must not silently skip")
        with tempfile.TemporaryDirectory(prefix="tml-ci-") as directory:
            root = Path(directory)
            tools = root / "tools"
            tools.mkdir()
            # The CLI registers probe options before parsing doctor/build commands.
            for name in ("build/build_tml_windows.ps1", "build/parse_tml_build_log.py", "validate_release.py",
                         "item-test-workbench/workbench.py", "item-test-workbench/probe.py",
                         "item-test-workbench/campaign.py", "item-test-workbench/agent_evidence.py"):
                target = tools / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / "tools" / name, target)
            (root / ".agent").mkdir()
            shutil.copy2(ROOT / ".agent/manifest.json", root / ".agent/manifest.json")
            project = root / "ModSources/InfiniCrafterLocal/InfiniCrafterLocal.csproj"
            project.parent.mkdir(parents=True)
            project.write_text('<Project Sdk="Tomat.Terraria.ModLoader.Sdk" />', encoding="utf-8")
            if deps:
                for name in ("ParticleLibrary/ParticleLibrary.dll", "Luminance/bin/Debug/net8.0/Luminance.dll"):
                    dll = root / "deps" / name
                    dll.parent.mkdir(parents=True, exist_ok=True)
                    dll.touch()
            # Native boundary stub, not a reimplementation of CI classification.
            bin_dir = root / "bin"
            bin_dir.mkdir()
            message = ("InfiniCrafterLocal/Fixture.cs(1,1): error CS1002: ; expected"
                       if diagnostic else "Synthetic compiler completed")
            if WINDOWS_SHELL:
                (bin_dir / "dotnet.cmd").write_text(
                    f"@echo off\necho {message}\nexit /b {code}\n", encoding="utf-8")
            else:
                compiler = bin_dir / "dotnet"
                compiler.write_text(f"#!/bin/sh\nprintf '%s\\n' '{message}'\nexit {code}\n", encoding="utf-8")
                compiler.chmod(0o755)
            if parser_code is not None:
                (tools / "build/parse_tml_build_log.py").write_text(
                    f"raise SystemExit({parser_code})\n", encoding="utf-8")
            workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
            # Extract the actual step, without interpreting or copying its logic.
            step = workflow.split("        id: tml\n", 1)[1].split("        run: |\n", 1)[1]
            step = textwrap.dedent(step.split("      - name:", 1)[0])
            (root / "workflow.ps1").write_text(step, encoding="utf-8")
            separator = ";" if WINDOWS_SHELL else ":"
            runner = root / "run.ps1"
            runner.write_text(
                "$ErrorActionPreference = 'Stop'\n"
                "Set-Location $PSScriptRoot\n"
                f"$env:PATH = (Join-Path $PSScriptRoot 'bin') + '{separator}' + $env:PATH\n"
                "$env:INFINI_TML_DEPS_SRC = Join-Path $PSScriptRoot 'deps'\n"
                "$env:INFINI_TML_REFERENCE_DIR = ''\n"
                "$env:INFINI_AGENT_SELFTEST_REPORT = ''\n"
                "$env:GITHUB_ENV = Join-Path $PSScriptRoot 'github-env.txt'\n"
                "./workflow.ps1\n"
                # GitHub's pwsh shell checks LASTEXITCODE after the run block.
                "if (Test-Path variable:LASTEXITCODE) { exit $LASTEXITCODE }\n",
                encoding="utf-8",
            )
            result = subprocess.run([str(PWSH), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", shell_path(runner)],
                                    capture_output=True, text=True, errors="replace", timeout=60)
            env_file = root / "github-env.txt"
            flags = env_file.read_text(encoding="utf-8-sig") if env_file.exists() else ""
            return result.returncode, flags, result.stdout + result.stderr

    def test_native_failure_with_normal_sdk_preamble_is_not_skip(self) -> None:
        code, flags, output = self.run_workflow(code=1, diagnostic=True)
        self.assertIn("classic tModLoader.targets pre-check is not required", output)
        self.assertIn("/p:InfiniExternalDepsRoot=", output)
        self.assertIn("CS1002", output)
        self.assertEqual(code, 1, output)
        self.assertIn("TML_BUILD_FAILED=true", flags)
        self.assertNotIn("TML_BUILD_SKIPPED=true", flags)

    def test_missing_dependencies_fail_required_build_gate_but_remain_not_run(self) -> None:
        code, flags, output = self.run_workflow(deps=False)
        # The workflow now uses --require-build: a missing dependency must make CI red
        # while retaining the accurate notRun/skip classification (not a C# failure).
        self.assertEqual(code, 1, output)
        self.assertIn("[notRun] tml_build", output)
        self.assertIn("[notRun] item_workbench_build", output)
        self.assertIn("TML_BUILD_SKIPPED=true", flags)
        self.assertNotIn("TML_BUILD_FAILED=true", flags)
        self.assertIn("Exit code 77 = intentional skip", output)
        self.assertNotIn("[run] dotnet", output)
        self.assertNotIn("dotnet build succeeded", output)

    def test_clean_tml_build_does_not_hide_missing_required_workbench_references(self) -> None:
        code, flags, output = self.run_workflow()
        # This deliberately minimal fixture has no tML reference directory. The
        # clean mod compiler must stay passed, but the required workbench build
        # must remain notRun and make the overall workflow fail (not false green).
        self.assertEqual(code, 1, output)
        self.assertIn("[passed] tml_build", output)
        self.assertIn("[notRun] item_workbench_build", output)
        self.assertNotIn("[failed] item_workbench_build", output)
        self.assertEqual(flags, "", output)
        self.assertIn("dotnet build succeeded and log parser found no errors", output)

    def test_other_native_failure_preserves_exit(self) -> None:
        code, flags, output = self.run_workflow(code=2)
        self.assertEqual(code, 2, output)
        self.assertIn("TML_BUILD_FAILED=true", flags)
        self.assertNotIn("TML_BUILD_SKIPPED=true", flags)

    def test_real_parser_rejects_errors_even_when_compiler_exits_zero(self) -> None:
        code, flags, output = self.run_workflow(diagnostic=True)
        self.assertEqual(code, 1, output)
        self.assertIn("build log parser found errors", output)
        self.assertIn("TML_BUILD_FAILED=true", flags)
        self.assertNotIn("TML_BUILD_SKIPPED=true", flags)

    def test_native_exit_77_after_compilation_is_failure_not_preflight_skip(self) -> None:
        code, flags, output = self.run_workflow(code=77)
        self.assertEqual(code, 1, output)
        self.assertIn("TML_BUILD_FAILED=true", flags)
        self.assertNotIn("TML_BUILD_SKIPPED=true", flags)

    def test_build_parser_exit_77_is_failure_not_preflight_skip(self) -> None:
        code, flags, output = self.run_workflow(parser_code=77)
        self.assertEqual(code, 1, output)
        self.assertIn("build log parser found errors (code 77)", output)
        self.assertIn("TML_BUILD_FAILED=true", flags)
        self.assertNotIn("TML_BUILD_SKIPPED=true", flags)

    def test_parser_failure_cannot_be_hidden_by_preflight_skip(self) -> None:
        for parser_code in (1, 2, 77):
            with self.subTest(parser_code=parser_code):
                code, flags, output = self.run_workflow(deps=False, parser_code=parser_code)
                self.assertEqual(code, parser_code, output)
                self.assertIn("TML_BUILD_FAILED=true", flags)
                self.assertNotIn("TML_BUILD_SKIPPED=true", flags)


if __name__ == "__main__":
    unittest.main()
