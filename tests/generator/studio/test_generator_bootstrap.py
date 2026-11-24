from __future__ import annotations
from suite_paths import REPO_ROOT

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

import pytest

from scripts import bootstrap


@pytest.fixture
def extracted(tmp_path):
    root = tmp_path / "other Infinicraft" / "generator"
    script = root / "scripts" / "bootstrap.py"
    script.parent.mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / "generator" / "scripts" / "bootstrap.py", script)
    (root / "server.py").write_text("raise AssertionError('not a server test')\n", encoding="utf-8")
    (root / "requirements.txt").write_bytes(b"fixture==1\n")
    (root / "config.env").write_bytes(b"# user bytes\r\nINFINI_PRIVATE_UNKNOWN=value\r\n")
    return root, script


def run_bootstrap(script, *args):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)  # Use the extracted fixture, not the shard's installed Studio.
    return subprocess.run([sys.executable, str(script), *args], cwd=script.parents[3],
                          env=env, capture_output=True, text=True, timeout=15)


def test_doctor_is_read_only_without_an_installed_runtime(extracted):
    root, script = extracted
    before = (root / "config.env").read_bytes()
    result = run_bootstrap(script, "doctor")
    assert result.returncode == 0, result.stdout + result.stderr
    assert str(root / "config.env") in result.stdout
    assert (root / "config.env").read_bytes() == before
    assert not (root / ".venv").exists()


def test_setup_preserves_config_and_only_marks_successful_install_ready(extracted, monkeypatch):
    root, _ = extracted
    monkeypatch.setattr(bootstrap, "ROOT", root)
    config = root / "config.env"
    before = config.read_bytes()
    python = bootstrap.runtime_python(root)
    python.parent.mkdir(parents=True)
    python.touch()
    stamp = root / ".venv" / bootstrap.STAMP_NAME
    fail_install = True
    installations = []

    def run(command, **kwargs):
        if command[1:4] == ["-m", "pip", "install"]:
            installations.append(Path(command[-1]).read_bytes())
            if fail_install:
                raise subprocess.CalledProcessError(17, command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(bootstrap.subprocess, "run", run)
    assert bootstrap.main(["setup"]) == 17
    assert not stamp.exists()
    assert config.read_bytes() == before

    fail_install = False
    assert bootstrap.main(["setup"]) == 0
    assert stamp.is_file()
    assert bootstrap.main(["setup"]) == 0  # Explicit setup refreshes a ready environment.
    assert installations == [b"fixture==1\n"] * 3
    assert config.read_bytes() == before


def test_regular_launch_reinstalls_only_when_requirements_change(extracted, monkeypatch):
    root, _ = extracted
    monkeypatch.setattr(bootstrap, "ROOT", root)
    req = root / "requirements.txt"
    python = bootstrap.runtime_python(root)
    python.parent.mkdir(parents=True)
    python.touch()
    installs = []

    def run(command, **kwargs):
        if command[1:4] == ["-m", "pip", "install"]:
            installs.append(Path(command[-1]).read_bytes())
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(bootstrap.subprocess, "run", run)
    assert bootstrap.main(["server"]) == 0
    assert bootstrap.main(["server"]) == 0
    assert installs == [b"fixture==1\n"]
    req.write_bytes(b"fixture==2\n")
    assert bootstrap.main(["server"]) == 0
    assert bootstrap.main(["server"]) == 0
    assert installs == [b"fixture==1\n", b"fixture==2\n"]


@pytest.mark.parametrize("args,flags", [((), []), (("gui", "--no-browser"), ["--no-browser"])])
def test_bootstrap_runs_studio_child_with_selected_browser_behavior(extracted, args, flags):
    root, script = extracted
    app = root / "infini_local" / "desktop" / "web_studio.py"
    app.parent.mkdir(parents=True)
    for package in (app.parent, app.parent.parent):
        (package / "__init__.py").touch()
    app.write_text("import json, sys\nfrom pathlib import Path\n"
                   "print(json.dumps([str(Path.cwd()), sys.argv[1:]]))\nraise SystemExit(7)\n",
                   encoding="utf-8")
    venv.EnvBuilder(with_pip=False).create(root / ".venv")
    (root / ".venv" / bootstrap.STAMP_NAME).write_text(
        bootstrap.requirements_digest(root / "requirements.txt"), encoding="utf-8")
    result = run_bootstrap(script, *args)
    assert result.returncode == 7, result.stdout + result.stderr
    assert json.loads(result.stdout.strip()) == [str(root.resolve()), flags]
