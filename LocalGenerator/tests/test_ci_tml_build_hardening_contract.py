from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ci_has_separate_python_strict_and_tml_jobs() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python-tests:" in ci
    assert "strict-hygiene:" in ci
    assert "tml-build:" in ci
    assert "python -m compileall LocalGenerator" in ci
    assert "python tools/check_project_hygiene.py --strict-archive" in ci
    assert "runs-on: windows-latest" in ci
    assert "tools/build_tml_windows.ps1" in ci
    assert "tools/parse_tml_build_log.py" in ci
    assert "actions/upload-artifact@v4" in ci
    assert "TML_BUILD_SKIPPED=true" in ci
    assert "TML_BUILD_FAILED=true" in ci
    assert "external mod reference DLLs not found" in ci
    assert "InfiniExternalDepsRoot" in ci
