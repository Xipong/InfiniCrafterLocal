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
    spec = importlib.util.spec_from_file_location("handbook_hygiene", ROOT / "tools/checks/check_project_hygiene.py")
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


def test_specialist_guides_are_reachable_from_their_topic_hub():
    import posixpath
    import re
    from urllib.parse import unquote, urlsplit

    for audience in ("development", "reference"):
        root = ROOT / "docs" / audience
        pending = [root / "README_RU.md"]
        visited = set()
        while pending:
            source = pending.pop()
            if source in visited:
                continue
            visited.add(source)
            for target in re.findall(r"\]\(([^\s)]+)\)", source.read_text(encoding="utf-8")):
                link = urlsplit(target)
                if link.scheme or link.netloc or not link.path:
                    continue
                relative = posixpath.normpath(posixpath.join(source.parent.relative_to(ROOT).as_posix(), unquote(link.path)))
                path = ROOT / relative
                if path.is_file() and path.suffix == ".md" and path.is_relative_to(root):
                    pending.append(path)
        specialist = {path for path in root.rglob("*.md")
                      if path.parent != root and "generated" not in path.relative_to(root).parts}
        assert specialist <= visited, sorted(str(path.relative_to(ROOT)) for path in specialist - visited)
        allowed_root = ({"README_RU.md", "BUILD_RU.md", "TESTING_RU.md", "CODE_MAP_RU.md", "DOCUMENTATION_RU.md", "ROADMAP_RU.md", "MODULES_RU.md", "ADDING_RUNTIME_CAPABILITY_FOR_AGENTS_RU.md"}
                        if audience == "development" else {"README_RU.md", "GENERATED_RU.md"})
        assert {path.name for path in root.glob("*.md")} == allowed_root


def test_manifest_commands_resolve_the_reorganized_tool_owners():
    import json

    manifest = json.loads((ROOT / ".agent/manifest.json").read_text(encoding="utf-8"))
    commands = [*manifest["checks"].values(),
                *(command for commands in manifest["refreshGroups"].values() for command in commands)]
    for command in commands:
        for argument in command:
            if argument.startswith("tools/"):
                assert (ROOT / argument).is_file(), argument
    project = manifest["checks"]["native_checks"][2]
    assert project == "tools/native/EngineRuntimeChecks.csproj"
    assert {p.name for p in (ROOT / "tools").glob("*.py")} == {
        "__init__.py", "agentctl.py", "validate_release.py", "build_documentation.py"}


def test_source_installer_resolves_root_from_build_directory(tmp_path):
    """Exercise the real script with a minimal disposable source/target, not an installation."""
    import shutil
    import subprocess
    import sys

    script = tmp_path / "repo/tools/build/install_to_tmodloader_modsources.py"
    script.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "tools/build/install_to_tmodloader_modsources.py", script)
    source = tmp_path / "repo/ModSources/InfiniCrafterLocal"
    source.mkdir(parents=True)
    (source / "build.txt").write_text("version = 0.5.1\n", encoding="utf-8")
    (source / "fixture.txt").write_text("canonical source", encoding="utf-8")
    target_root = tmp_path / "disposable-target"
    target = target_root / "InfiniCrafterLocal"
    target.mkdir(parents=True)
    (target / "old.txt").write_text("old disposable source", encoding="utf-8")
    result = subprocess.run([sys.executable, str(script), str(target_root)], cwd=tmp_path,
                            input="", text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (target / "fixture.txt").read_text(encoding="utf-8") == "canonical source"
    assert not (target / "old.txt").exists()
    assert (source / "fixture.txt").is_file()


def test_bash_release_wrapper_resolves_public_entrypoint_from_any_cwd(tmp_path):
    import os
    import shutil
    import subprocess
    import sys
    import pytest

    shell = shutil.which("bash")
    if shell is None:
        pytest.skip("bash unavailable; wrapper execution is notRun")
    environment = dict(os.environ, INFINI_PYTHON=sys.executable)
    result = subprocess.run([shell, str(ROOT / "tools/build/validate_release.sh"), "--help"],
                            cwd=tmp_path, env=environment, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--group" in result.stdout
