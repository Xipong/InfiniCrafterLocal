from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / "LocalGenerator"
SOURCE_ROOTS = [LOCAL / "infini_local", ROOT / "tools", LOCAL / "server.py", LOCAL / "settings_gui.py"]
BANNED_TEXT = (
    "compatibility " + "facade",
    "historical " + "import path",
    "legacy " + "facade",
    "back" + "compat",
    "formerly " + "declared directly",
)


def _source_files() -> list[Path]:
    files: list[Path] = []
    for root in SOURCE_ROOTS:
        if root.is_file():
            files.append(root)
        else:
            files.extend(root.rglob("*.py"))
    return [p for p in files if "__pycache__" not in p.parts]


def test_native_source_has_no_wildcard_imports_or_migration_terms() -> None:
    failures: list[str] = []
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(ROOT).as_posix()
        if re.search(r"^\s*from\s+[\w.]+\s+import\s+\*", text, re.M):
            failures.append(f"{rel}: wildcard import")
        lowered = text.lower()
        for needle in BANNED_TEXT:
            if needle in lowered:
                failures.append(f"{rel}: banned text {needle!r}")
    assert failures == []


def test_native_source_has_no_legacy_named_modules() -> None:
    offenders = [
        p.relative_to(ROOT).as_posix()
        for p in (LOCAL / "infini_local").rglob("*_legacy_*.py")
    ]
    assert offenders == []


def test_runtime_authoring_public_api_is_package_owned() -> None:
    assert not (LOCAL / "infini_local" / "core" / "runtime_authoring.py").exists()
    pkg = LOCAL / "infini_local" / "core" / "runtime_authoring"
    for name in ["__init__.py", "schema.py", "common.py", "semantics.py", "normalize.py", "structural.py", "compiler.py", "reports.py"]:
        assert (pkg / name).exists()
    init = (pkg / "__init__.py").read_text(encoding="utf-8")
    assert "from infini_local.core.runtime_authoring.common import (" in init
    assert init.count("ENGINE_RUNTIME_API_VERSION") >= 2
    for sibling in ["schema.py", "semantics.py", "normalize.py", "structural.py", "compiler.py", "reports.py"]:
        assert "ENGINE_RUNTIME_API_VERSION =" not in (pkg / sibling).read_text(encoding="utf-8")


def test_web_public_api_is_canonical_and_server_is_entrypoint() -> None:
    assert not (LOCAL / "infini_local" / "web" / "_".join(["server", "legacy", "facade.py"])).exists()
    server = (LOCAL / "infini_local" / "web" / "server.py").read_text(encoding="utf-8")
    api = (LOCAL / "infini_local" / "web" / "api.py").read_text(encoding="utf-8")
    services = (LOCAL / "infini_local" / "web" / "server_services.py").read_text(encoding="utf-8")
    assert "from infini_local.web.server_services import (" in server
    assert "def main()" in server
    assert "ThreadingHTTPServer" in server
    assert "from infini_local.web.server_services import (" in api
    assert "from infini_local.web.server import (" in api
    assert "infini_local.pipelines.combine_pipeline" in services


def test_canonical_public_apis_import() -> None:
    from infini_local.core import runtime_authoring
    from infini_local.web import api

    assert runtime_authoring.ENGINE_RUNTIME_API_VERSION.startswith("v")
    assert callable(runtime_authoring.compile_runtime_plan_to_genome_patch)
    assert callable(runtime_authoring.runtime_plan_validation_report)
    assert callable(api.build_llm_author_payload)
    assert callable(api.validate_and_repair)
    assert callable(api.final_normalize)
