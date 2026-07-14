from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INF = ROOT / "LocalGenerator" / "infini_local"

ALLOWED_RAW_ENV_FILES = {
    INF / "core" / "env_utils.py",
}


def _is_os_environ(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _raw_env_reads(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if _is_os_environ(node.func.value):
                # Explicitly not a config read; useful in tests/tools and allowed by the contract.
                if node.func.attr in {"copy", "setdefault"}:
                    continue
                hits.append(f"{path.relative_to(ROOT)}:{node.lineno}:os.environ.{node.func.attr}")
        elif isinstance(node, ast.Subscript) and _is_os_environ(node.value):
            hits.append(f"{path.relative_to(ROOT)}:{node.lineno}:os.environ[]")
    return hits


def _contract_check_infini_local_env_config_reads_go_through_env_utils() -> None:
    offenders: list[str] = []
    for path in sorted(INF.rglob("*.py")):
        if path in ALLOWED_RAW_ENV_FILES:
            continue
        offenders.extend(_raw_env_reads(path))
    assert not offenders, "raw env config reads must use env_utils:\n" + "\n".join(offenders)


def _contract_check_env_contract_scan_ignores_comments_and_os_environ_copy(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text(
        '# os.environ.get("INFINI_COMMENT_ONLY")\n'
        'import os\n'
        'snapshot = os.environ.copy()\n',
        encoding="utf-8",
    )
    assert _raw_env_reads(probe) == []


def _contract_check_bad_infini_env_values_fallback_instead_of_crashing() -> None:
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(ROOT / "LocalGenerator"),
        "INFINI_USE_LLM": "abc",
        "INFINI_LLM_MAX_TOKENS": "abc",
        "INFINI_SDCPP_WIDTH": "abc",
        "INFINI_SDCPP_HEIGHT": "abc",
        "INFINI_SDCPP_TIMEOUT": "abc",
        "INFINI_COMFYUI_HEIGHT": "abc",
        "INFINI_IMAGE_API_TIMEOUT": "abc",
        "INFINI_PATTERN_REPAIR_ATTEMPTS": "abc",
        "INFINI_IMAGE_BACKEND": "off",
    })
    proc = subprocess.run(
        [sys.executable, "-c", "from infini_local.core.llm_config import LLM_MAX_TOKENS; from infini_local.pipelines.pipeline_visual_config import SDCPP_HEIGHT, SDCPP_TIMEOUT; print(LLM_MAX_TOKENS, SDCPP_HEIGHT, SDCPP_TIMEOUT)"],
        cwd=ROOT / "LocalGenerator",
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip()


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_environment_access_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_infini_local_env_config_reads_go_through_env_utils',
            '_contract_check_env_contract_scan_ignores_comments_and_os_environ_copy',
            '_contract_check_bad_infini_env_values_fallback_instead_of_crashing',
        ),
    )
