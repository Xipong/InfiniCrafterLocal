"""Static import/export shape lives in check_project_hygiene; resolve real exports here."""
from __future__ import annotations

import importlib
import pkgutil


def test_declared_module_exports_exist_at_runtime() -> None:
    import infini_local

    missing: dict[str, list[str]] = {}
    for info in pkgutil.walk_packages(infini_local.__path__, infini_local.__name__ + "."):
        module = importlib.import_module(info.name)
        absent = [name for name in getattr(module, "__all__", ()) if not hasattr(module, name)]
        if absent:
            missing[info.name] = absent
    assert missing == {}
