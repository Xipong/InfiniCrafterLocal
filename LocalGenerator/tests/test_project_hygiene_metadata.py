"""Workspace indexes are not source folders or releasable content."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def hygiene(tmp_path, monkeypatch):
    tool = Path(__file__).resolve().parents[2] / "tools" / "check_project_hygiene.py"
    spec = importlib.util.spec_from_file_location("hygiene_metadata_regression", tool)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / "FOLDER_DOCS_RU.md").write_text("Project docs", encoding="utf-8")
    index = tmp_path / ".gitnexus" / "parsedfile-cache" / "entry"
    index.mkdir(parents=True)
    (index / "source.json").write_text("{}", encoding="utf-8")
    return module


def test_workspace_index_needs_no_folder_docs(hygiene):
    assert hygiene.iter_project_dirs() == [hygiene.ROOT]
    hygiene.check_folder_docs()
    hygiene.check_no_packaged_runtime_junk()


def test_workspace_index_is_rejected_in_release_archive(hygiene):
    with pytest.raises(SystemExit) as exc:
        hygiene.check_no_packaged_runtime_junk(strict_archive=True)
    assert exc.value.code == 1
