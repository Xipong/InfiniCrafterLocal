from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path


def _contract_check_infini_local_import_graph_is_acyclic() -> None:
    package_dir = Path(__file__).resolve().parents[1] / "infini_local"
    modules = {
        ".".join(path.relative_to(package_dir.parent).with_suffix("").parts): path
        for path in package_dir.rglob("*.py")
    }
    edges: dict[str, set[str]] = {module: set() for module in modules}
    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in modules:
                edges[module].add(node.module)
            elif isinstance(node, ast.Import):
                edges[module].update(alias.name for alias in node.names if alias.name in modules)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(module: str, path: tuple[str, ...]) -> None:
        if module in visiting:
            cycle_start = path.index(module)
            raise AssertionError(" -> ".join((*path[cycle_start:], module)))
        if module in visited:
            return
        visiting.add(module)
        for dependency in edges[module]:
            visit(dependency, (*path, module))
        visiting.remove(module)
        visited.add(module)

    for module in modules:
        visit(module, ())


def _contract_check_module_exports_are_static_not_globals_driven() -> None:
    package_dir = Path(__file__).resolve().parents[1] / "infini_local"
    offenders: list[str] = []
    for path in package_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
                continue
            if any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "globals"
                for child in ast.walk(node.value)
            ):
                offenders.append(str(path.relative_to(package_dir)))
    assert offenders == []


def _contract_check_declared_module_exports_exist_at_runtime() -> None:
    import infini_local

    missing: dict[str, list[str]] = {}
    for info in pkgutil.walk_packages(infini_local.__path__, infini_local.__name__ + "."):
        module = importlib.import_module(info.name)
        absent = [name for name in getattr(module, "__all__", ()) if not hasattr(module, name)]
        if absent:
            missing[info.name] = absent
    assert missing == {}


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_python_package_integrity_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_infini_local_import_graph_is_acyclic',
            '_contract_check_module_exports_are_static_not_globals_driven',
            '_contract_check_declared_module_exports_exist_at_runtime',
        ),
    )
