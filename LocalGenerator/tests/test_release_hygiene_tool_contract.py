from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "check_project_hygiene.py"


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
    assert hygiene._is_runtime_junk(Path("LocalGenerator/cache/world/recipe.json"), Path("recipe.json"))
    assert hygiene._is_runtime_junk(Path("LocalGenerator/tests/.pytest_cache/v/cache/nodeids"), Path("nodeids"))
    assert not hygiene._is_runtime_junk(Path("LocalGenerator/infini_local/web/server.py"), Path("server.py"))
