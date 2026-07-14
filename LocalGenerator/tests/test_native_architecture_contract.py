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


def _contract_check_native_source_has_no_wildcard_imports_or_migration_terms() -> None:
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


def _contract_check_native_source_has_no_legacy_named_modules() -> None:
    offenders = [
        p.relative_to(ROOT).as_posix()
        for p in (LOCAL / "infini_local").rglob("*_legacy_*.py")
    ]
    assert offenders == []
    retired = [
        LOCAL / "infini_local" / "core" / "vfx_composition.py",
        LOCAL / "infini_local" / "pipelines" / "combine_orchestrator.py",
        LOCAL / "infini_local" / "pipelines" / "pipeline_support.py",
        LOCAL / "infini_local" / "pipelines" / "repair_orchestrator.py",
        LOCAL / "infini_local" / "pipelines" / "sprite_processing_pipeline.py",
    ]
    assert [path.relative_to(ROOT).as_posix() for path in retired if path.exists()] == []


def _contract_check_runtime_authoring_public_api_is_package_owned() -> None:
    assert not (LOCAL / "infini_local" / "core" / "runtime_authoring.py").exists()
    pkg = LOCAL / "infini_local" / "core" / "runtime_authoring"
    for name in ["__init__.py", "schema.py", "common.py", "semantics.py", "normalize.py", "structural.py", "compiler.py", "reports.py"]:
        assert (pkg / name).exists()
    init = (pkg / "__init__.py").read_text(encoding="utf-8")
    assert "from infini_local.core.runtime_authoring.common import ENGINE_RUNTIME_API_VERSION" in init
    assert "from infini_local.core.runtime_authoring.compiler import compile_runtime_plan_to_genome_patch" in init
    assert "from infini_local.core.runtime_authoring.semantics import" not in init
    assert init.count("ENGINE_RUNTIME_API_VERSION") >= 2
    for sibling in ["schema.py", "semantics.py", "normalize.py", "structural.py", "compiler.py", "reports.py"]:
        assert "ENGINE_RUNTIME_API_VERSION =" not in (pkg / sibling).read_text(encoding="utf-8")


def _contract_check_web_server_is_native_entrypoint_without_cross_domain_api_barrel() -> None:
    assert not (LOCAL / "infini_local" / "web" / "_".join(["server", "legacy", "facade.py"])).exists()
    assert not (LOCAL / "infini_local" / "web" / "server_services.py").exists()
    assert not (LOCAL / "infini_local" / "web" / "api.py").exists()
    server = (LOCAL / "infini_local" / "web" / "server.py").read_text(encoding="utf-8")
    launcher = (LOCAL / "server.py").read_text(encoding="utf-8")
    assert "server_services" not in server
    assert "from infini_local.services import (" in server
    assert "def main()" in server
    assert "ThreadingHTTPServer" in server
    assert "infini_local.pipelines.combine_pipeline" in server
    assert "sys.modules" not in launcher
    assert "from infini_local.web import api" not in launcher
    assert "from infini_local.web.server import main" in launcher


def _contract_check_canonical_owner_apis_import() -> None:
    from infini_local.core import runtime_authoring
    from infini_local.pipelines.combine_validation import validate_and_repair
    from infini_local.pipelines.final_normalize import final_normalize
    from infini_local.pipelines.llm_authoring_prompt import build_llm_author_payload

    assert runtime_authoring.ENGINE_RUNTIME_API_VERSION.startswith("v")
    assert callable(runtime_authoring.compile_runtime_plan_to_genome_patch)
    assert callable(runtime_authoring.runtime_plan_validation_report)
    assert callable(build_llm_author_payload)
    assert callable(validate_and_repair)
    assert callable(final_normalize)
def _top_level_defined_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(target.id for target in targets if isinstance(target, ast.Name))
    return names


def _contract_check_web_server_does_not_redeclare_pipeline_owned_state_or_normalizers() -> None:
    server_path = LOCAL / "infini_local" / "web" / "server.py"
    visual_owner = LOCAL / "infini_local" / "pipelines" / "pipeline_visual_config.py"
    runtime_owner = LOCAL / "infini_local" / "pipelines" / "pipeline_runtime_constants.py"
    server_names = _top_level_defined_names(server_path)
    duplicated = server_names & (
        _top_level_defined_names(visual_owner) | _top_level_defined_names(runtime_owner)
    )
    assert duplicated == set()
    assert "PlannerUnavailable" not in server_names
    assert "final_normalize" not in server_names
    assert "_sdcpp_config" not in server_names


def _contract_check_repo_docs_do_not_pin_one_agent_absolute_workspace_path() -> None:
    offenders: list[str] = []
    for path in [ROOT / "docs" / "PROJECT_MAINTAINABILITY_RU.md"]:
        text = path.read_text(encoding="utf-8")
        if "/home/xipong" in text or "/tmp/icl_refactor" in text:
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_native_architecture_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_native_source_has_no_wildcard_imports_or_migration_terms',
            '_contract_check_native_source_has_no_legacy_named_modules',
            '_contract_check_runtime_authoring_public_api_is_package_owned',
            '_contract_check_web_server_is_native_entrypoint_without_cross_domain_api_barrel',
            '_contract_check_canonical_owner_apis_import',
            '_contract_check_web_server_does_not_redeclare_pipeline_owned_state_or_normalizers',
            '_contract_check_repo_docs_do_not_pin_one_agent_absolute_workspace_path',
        ),
    )
