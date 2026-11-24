from __future__ import annotations
from suite_paths import GENERATOR_ROOT, REPO_ROOT

import json
import os
import subprocess
import sys
import venv
import pytest

from infini_local.desktop import settings_env
from scripts import bootstrap

ROOT = REPO_ROOT


def test_new_user_template_has_no_personal_hardware_paths_or_automatic_gpu_launch():
    template = settings_env.parse_env(ROOT / "generator/config.example.env")
    assert template.get("INFINI_SDCPP_SERVER_AUTOSTART") == "0"
    assert template.get("INFINI_SDCPP_SERVER_EXE") == ""
    assert template.get("INFINI_SDCPP_MODEL") == ""
    assert template.get("INFINI_SDCPP_SERVER_EXTRA_ARGS") == ""
    assert template.get("INFINI_GUI_PIPELINE_PRESET") == "Custom"


def test_windows_launchers_have_no_control_bytes():
    paths = [ROOT / "OPEN_INFINICRAFT.bat", *(ROOT / "tools/windows").glob("*.bat")]
    for path in paths:
        assert all(byte >= 32 or byte in (9, 10, 13) for byte in path.read_bytes()), path.name


@pytest.mark.parametrize("args, flags", [([], []), (["gui", "--no-browser"], ["--no-browser"])])
def test_bootstrap_dispatches_to_the_canonical_studio(monkeypatch, args, flags):
    python = bootstrap.runtime_python(GENERATOR_ROOT)
    monkeypatch.setattr(bootstrap, "prepare_runtime", lambda root, *, refresh: python)
    calls = []

    def launch(command, **options):
        calls.append((command, options))
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(bootstrap.subprocess, "run", launch)
    assert bootstrap.main(args) == 7
    assert calls == [([str(python), "-u", "-B", "-m", "infini_local.desktop.web_studio", *flags],
                      {"cwd": GENERATOR_ROOT, "check": False})]


def test_headless_server_uses_another_extracted_root_and_keeps_its_config(tmp_path):
    checkout = tmp_path / "other Infinicraft"
    root = checkout / "generator"
    root.mkdir(parents=True)
    server = root / "server.py"
    server.write_text("from pathlib import Path\nimport json\n"
                      "print(json.dumps([str(Path.cwd()), Path('config.env').read_text()]))\n")
    config = root / "config.env"
    config.write_text("fixture")
    requirements = root / "requirements.txt"
    requirements.write_text("")
    venv.EnvBuilder(with_pip=False).create(root / ".venv")
    (root / ".venv" / bootstrap.STAMP_NAME).write_text(bootstrap.requirements_digest(requirements))
    if os.name == "nt":
        command = f'call "{ROOT / "OPEN_INFINICRAFT.bat"}" server --root "{checkout.name}"'
        launcher = ["cmd.exe", "/d", "/c", command]
    else:
        launcher = [sys.executable, str(GENERATOR_ROOT / "scripts/bootstrap.py"),
                    "server", "--root", checkout.name]
    result = subprocess.run(launcher, cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip()) == [str(root.resolve()), "fixture"]
    assert config.read_text() == "fixture"


def test_bootstrap_refuses_wrong_action_and_missing_root_without_preparing(tmp_path, monkeypatch, capsys):
    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid arguments must not prepare the runtime")

    monkeypatch.setattr(bootstrap, "prepare_runtime", forbidden)
    with pytest.raises(SystemExit) as error:
        bootstrap.main(["server", "--no-browser"])
    assert error.value.code == 2
    with pytest.raises(SystemExit) as error:
        bootstrap.main(["gui", "--root", str(tmp_path)])
    assert error.value.code == 2
    assert bootstrap.main(["server", "--root", str(tmp_path)]) == 1
    assert "Generator server.py not found" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(os.name != "nt", reason="Windows launcher execution requires cmd.exe")
def test_windows_launcher_runs_read_only_doctor():
    result = subprocess.run(["cmd.exe", "/d", "/c", str(ROOT / "OPEN_INFINICRAFT.bat"), "doctor"], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "read-only" in result.stdout
