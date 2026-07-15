from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "check_project_hygiene.py"
SANDBOX_TOOL = ROOT / "tools" / "validate_sandbox.py"
PYTEST_RUNNER = ROOT / "tools" / "run_pytest_shards.py"


def _load_hygiene_module():
    spec = importlib.util.spec_from_file_location("check_project_hygiene_for_tests", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _contract_check_release_metadata_patterns_are_rejected() -> None:
    hygiene = _load_hygiene_module()
    assert hygiene._is_forbidden_release_metadata(Path("Zone.Identifier"), Path("Zone.Identifier"))
    assert hygiene._is_forbidden_release_metadata(Path("sprite.png:Zone.Identifier"), Path("sprite.png:Zone.Identifier"))
    assert hygiene._is_forbidden_release_metadata(Path("nested/.DS_Store"), Path(".DS_Store"))
    assert hygiene._is_forbidden_release_metadata(Path("nested/Thumbs.db"), Path("Thumbs.db"))


def _contract_check_strict_archive_runtime_junk_patterns_are_recognized() -> None:
    hygiene = _load_hygiene_module()
    assert hygiene._is_runtime_junk(Path("pkg/__pycache__/module.cpython-312.pyc"), Path("module.cpython-312.pyc"))
    assert hygiene._is_runtime_junk(Path("LocalGenerator/cache/world/recipe.json"), Path("recipe.json"))
    assert hygiene._is_runtime_junk(Path("build_logs/tml-build.log"), Path("tml-build.log"))
    assert hygiene._is_runtime_junk(Path("LocalGenerator/tests/.pytest_cache/v/cache/nodeids"), Path("nodeids"))
    assert not hygiene._is_runtime_junk(Path("LocalGenerator/infini_local/web/server.py"), Path("server.py"))


def _contract_check_dependency_free_sandbox_gate_is_honest_and_bounded(tmp_path: Path) -> None:
    report_path = tmp_path / "sandbox-validation.json"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, "-S", str(SANDBOX_TOOL), "--json-out", str(report_path)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["coverage"] == "portable-static"
    assert report["releaseReady"] is False
    assert report["fullSuiteAvailable"] is False
    assert {"pytest", "pydantic", "pydantic_core", "Pillow", "Hypothesis"}.issubset(
        report["missingFullSuiteDependencies"]
    )
    assert not report["failed"]

    runner_report_path = tmp_path / "pytest-unavailable.json"
    runner = subprocess.run(
        [
            sys.executable,
            "-S",
            str(PYTEST_RUNNER),
            "--compact",
            "--json-out",
            str(runner_report_path),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=15,
    )
    assert runner.returncode == 2, runner.stdout
    runner_report = json.loads(runner_report_path.read_text(encoding="utf-8"))
    assert runner_report["status"] == "unavailable"
    assert runner_report["fullSuiteAvailable"] is False
    assert not runner_report["shards"]
    assert runner_report["portableCommand"].endswith("tools/validate_sandbox.py")


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_release_hygiene_tool_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_release_metadata_patterns_are_rejected',
            '_contract_check_strict_archive_runtime_junk_patterns_are_recognized',
            '_contract_check_dependency_free_sandbox_gate_is_honest_and_bounded',
        ),
    )
