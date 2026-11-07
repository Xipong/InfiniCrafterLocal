"""Documentation packaging keeps source catalogs out of the user entry surface."""
from __future__ import annotations
from suite_paths import REPO_ROOT

from pathlib import Path

ROOT = REPO_ROOT




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



def test_manifest_commands_resolve_the_reorganized_tool_owners():
    import json

    manifest = json.loads((ROOT / ".agent/manifest.json").read_text(encoding="utf-8"))
    commands = [*manifest["checks"].values(),
                *(command for commands in manifest["refreshGroups"].values() for command in commands)]
    for command in commands:
        for argument in command:
            if argument.startswith("tools/"):
                assert (ROOT / argument).is_file(), argument


def test_source_installer_resolves_root_from_build_directory(tmp_path):
    """Exercise the real script with a minimal disposable source/target, not an installation."""
    import shutil
    import subprocess
    import sys

    script = tmp_path / "repo/tools/build/install_to_tmodloader_modsources.py"
    script.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "tools/build/install_to_tmodloader_modsources.py", script)
    source = tmp_path / "repo/mod/InfiniCrafterLocal"
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
