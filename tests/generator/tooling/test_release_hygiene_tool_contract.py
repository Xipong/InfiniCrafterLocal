from __future__ import annotations
from suite_paths import REPO_ROOT

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import struct
import uuid

import pytest

ROOT = REPO_ROOT
TOOL = ROOT / "tools" / "checks" / "check_project_hygiene.py"
SANDBOX_TOOL = ROOT / "tools" / "testing" / "validate_sandbox.py"
PYTEST_RUNNER = ROOT / "tools" / "testing" / "run_pytest_shards.py"
RELEASE_RENDERER = ROOT / "tools" / "diagnostics" / "render_validation_report.py"
SELFTEST_CHECKER = ROOT / "tools" / "checks" / "check_tml_selftest_report.py"
SELFTEST_EMITTER = (
    ROOT / "mod" / "InfiniCrafterLocal" / "Common" / "Systems" / "Diagnostics" / "InfiniAgentContractSelfTestSystem.cs"
)


def _load_hygiene_module():
    spec = importlib.util.spec_from_file_location("check_project_hygiene_for_tests", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_metadata_patterns_are_rejected() -> None:
    hygiene = _load_hygiene_module()
    assert hygiene._is_forbidden_release_metadata(Path("Zone.Identifier"), Path("Zone.Identifier"))
    assert hygiene._is_forbidden_release_metadata(Path("sprite.png:Zone.Identifier"), Path("sprite.png:Zone.Identifier"))
    assert hygiene._is_forbidden_release_metadata(Path("nested/.DS_Store"), Path(".DS_Store"))
    assert hygiene._is_forbidden_release_metadata(Path("nested/Thumbs.db"), Path("Thumbs.db"))


def test_strict_archive_runtime_junk_patterns_are_recognized() -> None:
    hygiene = _load_hygiene_module()
    assert hygiene._is_runtime_junk(Path("pkg/__pycache__/module.cpython-312.pyc"), Path("module.cpython-312.pyc"))
    assert hygiene._is_runtime_junk(Path("generator/cache/world/recipe.json"), Path("recipe.json"))
    assert hygiene._is_runtime_junk(Path("build_logs/tml-build.log"), Path("tml-build.log"))
    assert hygiene._is_runtime_junk(Path("tests/generator/.pytest_cache/v/cache/nodeids"), Path("nodeids"))
    assert hygiene._is_runtime_junk(Path(".codex/session.json"), Path("session.json"))
    assert hygiene._is_runtime_junk(Path(".agents/worker.json"), Path("worker.json"))
    assert hygiene._is_runtime_junk(Path("generator/.venv/pyvenv.cfg"), Path("pyvenv.cfg"))
    assert not hygiene._is_runtime_junk(Path("generator/infini_local/web/server.py"), Path("server.py"))


def test_dependency_free_sandbox_gate_is_honest_and_bounded(tmp_path: Path, monkeypatch) -> None:
    spec = importlib.util.spec_from_file_location("sandbox_gate_contract", SANDBOX_TOOL)
    assert spec is not None and spec.loader is not None
    sandbox = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sandbox)
    # Keep the complete cheap repository scans, including all contracts/.agent JSON.
    # Manifest hygiene validates selected JSON owners, not this exhaustive roster.
    for check in (sandbox._python_and_json_syntax(), sandbox._test_process_safety(), sandbox._pytest_bootstrap_policy()):
        assert check["status"] == "passed", check

    # Exercise the actual dependency-free orchestration without repeating the five
    # whole-project static checks already owned by the release manifest.
    fixture = tmp_path / "repo"
    copied_tool = fixture / "tools/testing/validate_sandbox.py"
    copied_tool.parent.mkdir(parents=True)
    shutil.copyfile(SANDBOX_TOOL, copied_tool)
    tests = fixture / "tests/generator"
    tests.mkdir(parents=True)
    shutil.copyfile(ROOT / "tests/generator/conftest.py", tests / "conftest.py")
    for _, command in sandbox.STATIC_COMMANDS:
        checker = fixture / command[0]
        checker.parent.mkdir(parents=True, exist_ok=True)
        checker.write_text("import sys\nraise SystemExit(0)\n", encoding="utf-8")

    report_path = tmp_path / "sandbox-validation.json"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, "-S", str(copied_tool), "--json-out", str(report_path)],
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
    assert {"pytest", "pydantic", "pydantic_core", "Pillow", "Hypothesis", "jsonschema"}.issubset(
        report["missingFullSuiteDependencies"]
    )
    assert not report["failed"]
    assert {check["name"] for check in report["checks"]} == {
        "syntax_and_json", "test_process_safety", "pytest_bootstrap_policy",
        *(name for name, _ in sandbox.STATIC_COMMANDS),
    }
    failing_name, failing_command = sandbox.STATIC_COMMANDS[0]
    (fixture / failing_command[0]).write_text("raise SystemExit(9)\n", encoding="utf-8")
    failed = subprocess.run(
        [sys.executable, "-S", str(copied_tool), "--json-out", str(report_path)],
        cwd=fixture, env=env, text=True, capture_output=True, check=False, timeout=15,
    )
    assert failed.returncode == 1, failed.stdout
    failed_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert failed_report["failed"] == [failing_name]
    assert next(c for c in failed_report["checks"] if c["name"] == failing_name)["returnCode"] == 9
    with monkeypatch.context() as scoped:
        scoped.setattr(sandbox, "ROOT", fixture)
        slow = fixture / "slow.py"
        slow.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        timed = sandbox._run_static_command("slow", ("slow.py",), 0.05)
        assert timed["status"] == "timeout"
        assert timed["returnCode"] is not None
        (tests / "test_unsafe.py").write_text(
            "import os, subprocess\nos.environ['UNAPPROVED'] = '1'\nsubprocess.run([])\n",
            encoding="utf-8",
        )
        unsafe = sandbox._test_process_safety()
        assert unsafe["status"] == "failed" and len(unsafe["errors"]) == 2
        (tests / "conftest.py").write_text(
            "def _configure_deterministic_sandbox():\n    forbidden()\n"
            "_configure_deterministic_sandbox()\n", encoding="utf-8",
        )
        assert sandbox._pytest_bootstrap_policy()["status"] == "failed"

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
    assert runner_report["portableCommand"].endswith("tools/testing/validate_sandbox.py")


def test_release_report_rejects_an_incomplete_roster(tmp_path: Path) -> None:
    status_path = tmp_path / "status.tsv"
    report_path = tmp_path / "report.json"
    status_path.write_text("", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(RELEASE_RENDERER), "--status-file", str(status_path), "--out", str(report_path)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=15,
    )
    assert proc.returncode == 1, proc.stdout
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert {"pytest", "schema_check", "tml_build", "tml_runtime_selftest"}.issubset(report["missingChecks"])
    assert report["duplicateChecks"] == []


def _managed_metadata_fixture(path: Path, mvid: str, *, pe64: bool = False, wide: bool = False) -> None:
    """Minimal file-backed PE/CLI metadata fixture; never loaded as executable code."""
    image = bytearray(1024)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3c, 128)
    image[128:132] = b"PE\0\0"
    optional_size = 240 if pe64 else 224
    struct.pack_into("<H", image, 134, 1)
    struct.pack_into("<H", image, 148, optional_size)
    struct.pack_into("<H", image, 152, 0x20b if pe64 else 0x10b)
    directories = 152 + (112 if pe64 else 96)
    struct.pack_into("<II", image, directories + 14 * 8, 0x2000, 72)
    struct.pack_into("<IIII", image, 152 + optional_size + 8, 512, 0x2000, 512, 512)
    struct.pack_into("<II", image, 520, 0x2048, 160)
    metadata = 584
    image[metadata:metadata + 4] = b"BSJB"
    struct.pack_into("<I", image, metadata + 12, 4)
    image[metadata + 16:metadata + 20] = b"v4\0\0"
    struct.pack_into("<H", image, metadata + 22, 2)
    struct.pack_into("<II", image, metadata + 24, 64, 64)
    image[metadata + 32:metadata + 36] = b"#~\0\0"
    struct.pack_into("<II", image, metadata + 36, 128, 16)
    image[metadata + 44:metadata + 52] = b"#GUID\0\0\0"
    tables = metadata + 64
    image[tables + 6] = 3 if wide else 0
    struct.pack_into("<Q", image, tables + 8, 1)
    struct.pack_into("<I", image, tables + 24, 1)
    struct.pack_into("<I" if wide else "<H", image, tables + 28 + 2 + (4 if wide else 2), 1)
    image[metadata + 128:metadata + 144] = uuid.UUID(mvid).bytes_le
    path.write_bytes(image)


def test_runtime_selftest_checker_matches_the_csharp_emitter(tmp_path: Path) -> None:
    source = SELFTEST_EMITTER.read_text(encoding="utf-8")
    schema_match = re.search(r'schema\s*=\s*"([^"]+)"', source)
    assert schema_match is not None
    check_ids = sorted(set(re.findall(r'Check\(\s*"([^"]+)"', source)))
    assert check_ids
    report_path = tmp_path / "tml-selftest.json"
    mod_id, tml_id = str(uuid.uuid4()), str(uuid.uuid4())
    mod_dll, tml_dll = tmp_path / "mod.dll", tmp_path / "tml.dll"
    _managed_metadata_fixture(mod_dll, mod_id)
    _managed_metadata_fixture(tml_dll, tml_id, pe64=True, wide=True)
    command = [sys.executable, str(SELFTEST_CHECKER), str(report_path), "--mod-dll", str(mod_dll), "--tml-dll", str(tml_dll)]
    payload = {
        "schema": schema_match.group(1),
        "generatedAt": "2000-01-01T00:00:00Z",
        "assemblies": {"mod": {"moduleVersionId": mod_id}, "tml": {"moduleVersionId": tml_id}},
        "runtimeApi": "infini.runtime-program.v5",
        "ok": True,
        "checks": [{"id": check_id, "ok": True, "detail": "test"} for check_id in check_ids],
        "failures": [],
    }
    report_path.write_text(json.dumps(payload), encoding="utf-8")
    accepted = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=15,
    )
    assert accepted.returncode == 0, accepted.stdout

    payload["checks"][0]["ok"] = "true"
    report_path.write_text(json.dumps(payload), encoding="utf-8")
    rejected = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=15,
    )
    assert rejected.returncode == 1, rejected.stdout

    # Same API/check IDs/time do not authorize another build or a missing identity.
    payload["checks"][0]["ok"] = True
    original = json.loads(json.dumps(payload))
    for change in ("mod", "tml", "missing", "truncated", "non-object"):
        payload = json.loads(json.dumps(original))
        if change in {"mod", "tml"}:
            payload["assemblies"][change]["moduleVersionId"] = str(uuid.uuid4())
        elif change == "missing":
            payload.pop("assemblies")
        elif change == "truncated":
            mod_dll.write_bytes(b"MZ")
        else:
            _managed_metadata_fixture(mod_dll, mod_id)
            payload = []
        report_path.write_text(json.dumps(payload), encoding="utf-8")
        rejected = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=15, check=False)
        assert rejected.returncode == 1, (change, rejected.stdout, rejected.stderr)


@pytest.mark.parametrize("with_targets,matching,status", [(False, True, "notRun"), (True, True, "passed"), (True, False, "failed")])
def test_release_selftest_gate_binds_report_to_target_dlls(tmp_path, with_targets, matching, status):
    from tools import validate_release
    from tools.checks import check_tml_selftest_report as checker
    mod_id, tml_id = str(uuid.uuid4()), str(uuid.uuid4())
    mod_dll, tml_dll = tmp_path / "mod.dll", tmp_path / "tml.dll"
    _managed_metadata_fixture(mod_dll, mod_id)
    _managed_metadata_fixture(tml_dll, tml_id)
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "schema": checker.EXPECTED_SCHEMA, "runtimeApi": checker.EXPECTED_RUNTIME_API,
        "ok": True, "checks": [{"id": name, "ok": True} for name in checker.REQUIRED], "failures": [],
        "assemblies": {"mod": {"moduleVersionId": mod_id if matching else str(uuid.uuid4())},
                       "tml": {"moduleVersionId": tml_id}},
    }))
    env = {"INFINI_AGENT_SELFTEST_REPORT": str(report)}
    if with_targets:
        env.update(INFINI_AGENT_SELFTEST_MOD_DLL=str(mod_dll), INFINI_AGENT_SELFTEST_TML_DLL=str(tml_dll))
    result = validate_release.run_check("tml_runtime_selftest", [], env=env)
    assert result["status"] == status, result


def test_standard_schema_dependency_blocks_full_suite(monkeypatch) -> None:
    spec = importlib.util.spec_from_file_location("pytest_shards_dependency_probe", PYTEST_RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    real_find_spec = importlib.util.find_spec
    with monkeypatch.context() as scoped:
        scoped.setattr(importlib.util, "find_spec", lambda name: None if name == "jsonschema" else real_find_spec(name))
        assert module.missing_full_test_dependencies() == ["jsonschema"]


# One collected item per contract module; individual checks keep source order and tracebacks.

@pytest.mark.parametrize("payload", [None, [], ["report"], "report", 17, True])
def test_selftest_checker_rejects_non_object_reports(tmp_path, payload):
    from tools.checks import check_tml_selftest_report as checker
    report = tmp_path / "report.json"
    report.write_text(json.dumps(payload))
    assert checker.validate(report)["ok"] is False


@pytest.mark.parametrize("damage", ["truncated", "pe-offset", "signature", "stream-name", "zero-guid", "module-row", "guid-index"])
def test_selftest_checker_refuses_malformed_target_dll(tmp_path, damage):
    from tools.checks import check_tml_selftest_report as checker
    target = tmp_path / "target.dll"
    mvid = str(uuid.uuid4())
    _managed_metadata_fixture(target, mvid)
    image = bytearray(target.read_bytes())
    if damage == "truncated":
        image = image[:700]
    elif damage == "pe-offset":
        struct.pack_into("<I", image, 0x3c, 0xffffffff)
    elif damage == "signature":
        image[584:588] = b"NOPE"
    elif damage == "stream-name":
        image[616] = 255
    elif damage == "zero-guid":
        image[712:728] = bytes(16)
    elif damage == "module-row":
        struct.pack_into("<I", image, 672, 0)
    else:
        struct.pack_into("<H", image, 680, 2)
    target.write_bytes(image)
    report = tmp_path / "report.json"
    report.write_text(json.dumps({
        "schema": checker.EXPECTED_SCHEMA, "runtimeApi": checker.EXPECTED_RUNTIME_API,
        "ok": True, "checks": [{"id": name, "ok": True} for name in checker.REQUIRED], "failures": [],
        "assemblies": {"mod": {"moduleVersionId": mvid}, "tml": {"moduleVersionId": mvid}},
    }))
    result = checker.validate(report, mod_dll=target, tml_dll=target)
    assert result["ok"] is False
    assert any("target DLL unreadable" in message for message in result["errors"]), result
