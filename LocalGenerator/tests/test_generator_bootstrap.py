from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "LocalGenerator" / "scripts" / "bootstrap.py"


def load_bootstrap():
    assert BOOTSTRAP.is_file(), "The one-click generator bootstrap is missing"
    spec = importlib.util.spec_from_file_location("infini_bootstrap_test", BOOTSTRAP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_doctor_is_read_only_and_does_not_require_installed_runtime():
    module = load_bootstrap()
    before = (ROOT / "LocalGenerator" / "config.env").read_bytes() if (ROOT / "LocalGenerator" / "config.env").exists() else None
    result = subprocess.run([sys.executable, str(BOOTSTRAP), "doctor"], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Python" in result.stdout and "config.env" in result.stdout
    after = (ROOT / "LocalGenerator" / "config.env").read_bytes() if (ROOT / "LocalGenerator" / "config.env").exists() else None
    assert after == before
    assert module.runtime_python(Path("project"), windows=True) == Path("project/.venv/Scripts/python.exe")
    assert module.runtime_python(Path("project"), windows=False) == Path("project/.venv/bin/python")


def test_environment_stamp_tracks_exact_requirements(tmp_path):
    module = load_bootstrap()
    requirements = tmp_path / "requirements.txt"
    requirements.write_bytes(b"Pillow>=10\npydantic>=2.13,<3\n")
    first = module.requirements_digest(requirements)
    requirements.write_bytes(b"Pillow>=11\npydantic>=2.13,<3\n")
    assert module.requirements_digest(requirements) != first


def test_failed_dependency_install_never_marks_environment_ready(tmp_path, monkeypatch):
    module = load_bootstrap()
    root = tmp_path / "LocalGenerator"
    root.mkdir()
    (root / "requirements.txt").write_text("example==1\n", encoding="utf-8")
    python = module.runtime_python(root)
    python.parent.mkdir(parents=True)
    python.touch()
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if "install" in command:
            raise subprocess.CalledProcessError(17, command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        module.prepare_runtime(root)
    assert not (root / ".venv" / ".infinicraft-requirements.sha256").exists()
    assert any("install" in command for command in calls)


def test_prepared_runtime_skips_install_but_explicit_setup_refreshes(tmp_path, monkeypatch):
    module = load_bootstrap()
    root = tmp_path / "LocalGenerator"
    root.mkdir()
    requirements = root / "requirements.txt"
    requirements.write_text("Pillow>=10\n", encoding="utf-8")
    python = module.runtime_python(root)
    python.parent.mkdir(parents=True)
    python.touch()
    stamp = root / ".venv" / ".infinicraft-requirements.sha256"
    stamp.write_text(module.requirements_digest(requirements), encoding="utf-8")
    calls = []
    monkeypatch.setattr(module.subprocess, "run", lambda command, **kwargs: calls.append(command) or subprocess.CompletedProcess(command, 0))
    assert module.prepare_runtime(root) == python
    assert not any("install" in command for command in calls)
    module.prepare_runtime(root, refresh=True)
    assert any("install" in command for command in calls)


def test_bootstrap_never_replaces_personal_configuration(tmp_path, monkeypatch):
    module = load_bootstrap()
    root = tmp_path / "LocalGenerator"
    root.mkdir()
    personal = root / "config.env"
    personal.write_bytes(b"INFINI_PRIVATE_UNKNOWN=value\r\n")
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "prepare_runtime", lambda *args, **kwargs: Path(sys.executable))
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0))
    assert module.main(["setup"]) == 0
    assert personal.read_bytes() == b"INFINI_PRIVATE_UNKNOWN=value\r\n"


def test_gui_bootstrap_opens_web_studio_not_legacy_tk_window(tmp_path, monkeypatch):
    module = load_bootstrap()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "prepare_runtime", lambda *args, **kwargs: Path(sys.executable))
    # The browser launcher must work even when Tcl/Tk is not installed.
    monkeypatch.setitem(sys.modules, "tkinter", None)
    calls = []
    monkeypatch.setattr(module.subprocess, "run", lambda command, **kwargs: calls.append(command) or subprocess.CompletedProcess(command, 0))
    assert module.main(["gui"]) == 0
    assert calls[-1][-2:] == ["-m", "infini_local.desktop.web_studio"]
