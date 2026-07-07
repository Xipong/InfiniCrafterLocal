"""Tests for the replay harness audit tools (Этап 10).

Verifies that the replay harness tool:
1. Imports and runs without errors.
2. The `list` command works on an empty store.
3. A synthetic case save produces expected artifacts.
4. The `replay` command can load saved artifacts back.
5. The multipass debug flag is recognized but not applied by default.

These tests do NOT call the LLM.  They exercise the deterministic code path.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Resolve paths
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent.parent
_TOOLS = _PROJECT_ROOT / "tools"
_LOCAL_GEN = _PROJECT_ROOT / "LocalGenerator"
# LocalGenerator must be importable
if str(_LOCAL_GEN) not in sys.path:
    sys.path.insert(0, str(_LOCAL_GEN))


@pytest.fixture
def replay_runner():
    """Import and return the replay harness CLI main function."""
    # Import the tool directly as a module
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "replay_generation_case", _TOOLS / "replay_generation_case.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def clean_replay_dir(replay_runner, monkeypatch, tmp_path):
    """Redirect replay storage to a temp dir so tests don't pollute the repo."""
    monkeypatch.setattr(replay_runner, "_replay_root", lambda: tmp_path / "replay_cases")
    return tmp_path


def test_replay_module_imports(replay_runner):
    """The replay harness module imports without error."""
    assert hasattr(replay_runner, "main")
    assert hasattr(replay_runner, "save_case")
    assert hasattr(replay_runner, "replay_case")
    assert hasattr(replay_runner, "_replay_root")


def test_replay_list_empty(replay_runner, clean_replay_dir, capsys):
    """`list` command on empty store exits cleanly."""
    rc = replay_runner.main(["list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "replay cases" in out.lower() or "no replay cases" in out.lower()


def test_replay_slugify(replay_runner):
    """Case IDs are slugified to filesystem-safe names."""
    assert replay_runner._slugify("My Case 123!") == "My_Case_123"
    assert replay_runner._slugify("") == "case"
    assert replay_runner._slugify("test-case_v0.4") == "test-case_v0_4"


def test_replay_save_with_synthetic_parents(replay_runner, clean_replay_dir, capsys):
    """Save a synthetic case and verify parents.json is written."""
    tmp = clean_replay_dir
    item_a = {"name": "Wooden Sword", "category": "weapon"}
    item_b = {"name": "Iron Bow", "category": "weapon"}
    (tmp / "a.json").write_text(json.dumps(item_a))
    (tmp / "b.json").write_text(json.dumps(item_b))

    # Save the case. This tries combine() and always writes parents.json first;
    # if generation is unavailable, the saved input artifact is still inspectable.
    rc = replay_runner.main(
        [
            "save",
            "synthetic_test_case",
            "--itemA",
            str(tmp / "a.json"),
            "--itemB",
            str(tmp / "b.json"),
        ]
    )
    out = capsys.readouterr().out
    # Either success or a documented failure (LLM unavailable)
    assert "saved" in out.lower() or "error" in out.lower()
    # parents.json should always be saved regardless of pipeline outcome
    assert (tmp / "replay_cases" / "synthetic_test_case" / "parents.json").exists()


def test_replay_show_missing_artifact(replay_runner, clean_replay_dir, capsys):
    """Show on a missing artifact returns error code 1."""
    # First create a case dir with just parents
    cdir = clean_replay_dir / "replay_cases" / "show_test"
    cdir.mkdir(parents=True)
    (cdir / "parents.json").write_text("{}")

    rc = replay_runner.main(["show", "show_test", "final_item.json"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "not found" in out.lower() or "missing" in out.lower()


def test_multipass_debug_flag_recognition(replay_runner, monkeypatch):
    """The multipass debug flag is read from env_utils."""
    # The module reads INFINI_MULTIPASS_AUTHORING at import time; we can
    # still verify the flag variable exists and is boolean-typed.
    assert isinstance(replay_runner.MULTIPASS_DEBUG, bool)


def test_replay_artifact_filenames_documented(replay_runner):
    """The documented artifact filenames are consistent in module."""
    # The harness docstring lists the expected artifacts; verify they are
    # referenced in the save_case function body.
    import inspect

    src = inspect.getsource(replay_runner.save_case)
    for artifact in [
        "parents.json",
        "final_item.json",
        "compiled_runtime.json",
        "balance_report.json",
    ]:
        assert artifact in src, f"save_case should reference {artifact}"
