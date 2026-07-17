#!/usr/bin/env python3
"""Run Pyright against the selected interpreter's real import environment.

Pyright analyzes the repository as Python 3.10, but a release worker may itself
run from a newer virtualenv. Some Pyright hosts then choose a version-derived
``site-packages`` directory instead of the one reported by ``--pythonpath``.
This runner adds only the selected interpreter's existing import roots through
a temporary overlay; it extends the repository config and therefore does not
change the target Python version or any diagnostic severity.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]


def _normalize_import_paths(values: Sequence[str]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for value in values:
        if not value:
            continue
        path = Path(value).resolve()
        if path in seen or not path.is_dir():
            continue
        lowered = {part.lower() for part in path.parts}
        if "site-packages" not in lowered and "dist-packages" not in lowered:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def _selected_import_paths(pythonpath: Path) -> list[Path]:
    if str(pythonpath) == sys.executable:
        return _normalize_import_paths(sys.path)

    probe = subprocess.run(
        [str(pythonpath), "-c", "import json,sys; print(json.dumps(sys.path))"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if probe.returncode != 0:
        raise RuntimeError(
            f"selected Python import-path probe failed ({probe.returncode}): {probe.stderr.strip()}"
        )
    try:
        values = json.loads(probe.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("selected Python import-path probe returned invalid JSON") from exc
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise RuntimeError("selected Python import-path probe returned an invalid path list")
    return _normalize_import_paths(values)


def _overlay_config(import_paths: Sequence[Path]) -> dict[str, Any]:
    extra_paths = [ROOT / "LocalGenerator", ROOT / "tools", *import_paths]
    return {
        "extends": str(ROOT / "pyproject.toml"),
        "extraPaths": [str(path) for path in extra_paths],
    }


def _resolve_pyright_command(pythonpath: Path, explicit: str) -> list[str]:
    if explicit:
        return [explicit]
    if str(pythonpath) == sys.executable and importlib.util.find_spec("pyright") is not None:
        return [sys.executable, "-m", "pyright"]
    sibling_names = ("pyright.exe", "pyright.cmd", "pyright") if sys.platform == "win32" else ("pyright",)
    for name in sibling_names:
        sibling = pythonpath.with_name(name)
        if sibling.is_file():
            return [str(sibling)]
    executable = shutil.which("pyright")
    if executable:
        return [executable]
    raise RuntimeError("pyright is not installed for the selected Python or on PATH")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pythonpath", default=sys.executable)
    parser.add_argument("--pyright-command", default="")
    args, passthrough = parser.parse_known_args(argv)

    # Preserve a virtualenv interpreter symlink. Resolving it to the base Python
    # would discard the very environment whose imports this runner must bind.
    pythonpath = Path(args.pythonpath).absolute()
    try:
        import_paths = _selected_import_paths(pythonpath)
        command = _resolve_pyright_command(pythonpath, str(args.pyright_command or ""))
    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

    with TemporaryDirectory(prefix="infini-pyright-") as temp_dir:
        config_path = Path(temp_dir) / "pyrightconfig.json"
        config_path.write_text(
            json.dumps(_overlay_config(import_paths), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [*command, "--project", str(config_path), "--pythonpath", str(pythonpath), *passthrough],
            cwd=ROOT,
            check=False,
        )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
