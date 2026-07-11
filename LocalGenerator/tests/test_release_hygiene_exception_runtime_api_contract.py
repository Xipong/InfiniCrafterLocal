from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "check_project_hygiene.py"


def load_hygiene_tool():
    spec = importlib.util.spec_from_file_location("check_project_hygiene", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_python_exception_hygiene_baseline_is_visible_and_not_growing():
    tool = load_hygiene_tool()
    stats = tool._count_python_exception_handlers(ROOT / "LocalGenerator" / "infini_local")
    assert stats["bare_except"] == tool.PYTHON_BARE_EXCEPT_BASELINE == 0
    assert stats["broad_exception"] <= tool.PYTHON_BROAD_EXCEPTION_BASELINE
    # Keep the current broad-exception debt explicit.  If this count changes,
    # either lower the baseline after cleanup or justify a new recovery boundary.
    assert tool.PYTHON_BROAD_EXCEPTION_BASELINE == 227


def test_runtime_api_sync_guard_reads_python_and_csharp_contracts():
    tool = load_hygiene_tool()
    py_runtime_api = tool._version_literal(
        "LocalGenerator/infini_local/core/runtime_authoring/common.py",
        r'ENGINE_RUNTIME_API_VERSION = "([^"]+)"',
        "Python engine runtime API",
    )
    cs_runtime_api = tool._version_literal(
        "ModSources/InfiniCrafterLocal/Common/InfiniRuntimeLimits.cs",
        r'RuntimeApiCurrent = "([^"]+)"',
        "C# runtime API",
    )
    assert py_runtime_api == cs_runtime_api == "v0.4.48"
