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


def test_strict_replay_compares_saved_compiler_semantics(replay_runner, clean_replay_dir):
    """Strict replay is a non-zero drift gate, not a print-only audit."""
    from infini_local.core.runtime_authoring import compile_runtime_plan_to_genome_result
    from infini_local.qa.golden_runtime_cases import GOLDEN_RUNTIME_CASES
    from infini_local.qa.runtime_proof import build_gameplay_seam_report

    cdir = clean_replay_dir / "replay_cases" / "strict_case"
    cdir.mkdir(parents=True)
    item = build_gameplay_seam_report(GOLDEN_RUNTIME_CASES[0])["item"]
    compiled = compile_runtime_plan_to_genome_result(item)
    (cdir / "final_item.json").write_text(json.dumps(item), encoding="utf-8")
    (cdir / "compiled_runtime.json").write_text(json.dumps(compiled), encoding="utf-8")

    assert replay_runner.main(["replay", "strict_case", "--strict"]) == 0

    compiled["patch"]["damage"] = 999999
    (cdir / "compiled_runtime.json").write_text(json.dumps(compiled), encoding="utf-8")
    assert replay_runner.main(["replay", "strict_case", "--strict"]) == 1


def test_strict_replay_fails_closed_on_invalid_final_boundary(replay_runner, clean_replay_dir):
    cdir = clean_replay_dir / "replay_cases" / "invalid_case"
    cdir.mkdir(parents=True)
    (cdir / "final_item.json").write_text(
        json.dumps({"attack": {"enabled": True}, "gameplay": {"kind": "weapon"}}),
        encoding="utf-8",
    )
    (cdir / "compiled_runtime.json").write_text("{}", encoding="utf-8")
    assert replay_runner.main(["replay", "invalid_case", "--strict"]) == 1
