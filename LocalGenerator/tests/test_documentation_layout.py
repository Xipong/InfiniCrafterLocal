"""Documentation packaging keeps source catalogs out of the user entry surface."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_generated_contract_docs_have_one_reference_home():
    for name in ("LOWERY_RU.md", "TECHNICAL_LOWERING_AUDIT_RU.md", "LOW_LEVEL_CAPABILITY_INVENTORY_RU.md", "CAPABILITY_LIBRARY_MACHINE_READABILITY_AUDIT_RU.md", "PRIMITIVE_PARITY_RU.md"):
        assert (ROOT / "docs/reference/generated" / name).is_file(), name
    assert not (ROOT / "lowery.md").exists()
    assert not (ROOT / "TECHNICAL_LOWERING_AUDIT_RU.md").exists()


def test_handbook_navigation_replaces_per_folder_notes(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("handbook_hygiene", ROOT / "tools/check_project_hygiene.py")
    assert spec and spec.loader
    hygiene = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hygiene)
    monkeypatch.setattr(hygiene, "ROOT", tmp_path)
    for name in ("README.md", "START_HERE.html", "docs/user/START_RU.md", "docs/development/README_RU.md", "docs/development/MODULES_RU.md", "docs/reference/README_RU.md", "docs/archive/README_RU.md"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('Useful documentation', encoding='utf-8')
    (tmp_path / 'LocalGenerator/infini_local/deep_module').mkdir(parents=True)
    hygiene.check_documentation_layout()


def test_old_redirects_are_not_returned_to_the_source_archive():
    retired = ("AGENT_INDEX_RU.md", "BUILD_QOL_RU.md", "PROJECT_ARCHITECTURE_RU.md", "PROJECT_MAP_RU.md", "QUICK_START_RU.md", "README_RU.md", "TODO_ROADMAP_VERY_LATER_RU.md", "command.md", "LocalGenerator/PROJECT_ARCHITECTURE_RU.md", "LocalGenerator/PROJECT_MAP_RU.md", "LocalGenerator/QUICK_START_RU.md", "LocalGenerator/README_RU.md")
    assert not [name for name in retired if (ROOT / name).exists()]
