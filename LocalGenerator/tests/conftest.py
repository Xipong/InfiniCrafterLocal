"""Deterministic, offline bootstrap for the ordinary pytest suite.

The operator ``config.env`` may enable live LLM/image services.  Unit and
contract tests must instead start from the shipped code defaults while keeping
all external services inert.  Live configuration experiments are explicit via
``INFINI_TEST_USE_PROJECT_CONFIG=1``. Impact-focused agent checks may set
``INFINI_FOCUSED_PYTEST=1``; missing optional modules then fail only tests that
actually import them, while the full suite keeps its required runtime dependency gate. Optional
property-test packages are reported separately by release verification.
"""
from __future__ import annotations

import atexit
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile


_TRUE_VALUES = {"1", "true", "yes", "on", "y", "t"}
_FULL_SUITE_MODULES = {
    "pydantic": "pydantic",
    "pydantic_core": "pydantic_core",
    "Pillow": "PIL",
}


def _stop_dependency_poor_collection() -> None:
    if os.environ.get("INFINI_FOCUSED_PYTEST", "").strip().lower() in _TRUE_VALUES:
        return
    missing = [
        label
        for label, import_name in _FULL_SUITE_MODULES.items()
        if importlib.util.find_spec(import_name) is None
    ]
    if not missing:
        return
    pytest = __import__("pytest")

    pytest.exit(
        "full test dependencies are unavailable: "
        + ", ".join(missing)
        + "; run `python tools/validate_sandbox.py` instead",
        returncode=2,
    )


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE_VALUES


_TEST_CACHE_ROOT: Path | None = None


def _configure_deterministic_sandbox() -> None:
    global _TEST_CACHE_ROOT
    if _truthy("INFINI_TEST_USE_PROJECT_CONFIG"):
        return

    _TEST_CACHE_ROOT = Path(tempfile.mkdtemp(prefix="infini-pytest-"))
    cache_dir = _TEST_CACHE_ROOT / "cache"
    world_dir = _TEST_CACHE_ROOT / "world-recipes"
    cache_dir.mkdir(parents=True, exist_ok=True)
    world_dir.mkdir(parents=True, exist_ok=True)

    # Preserve shipped defaults that contracts verify.  Only live side effects
    # are disabled; the dev-only fallback remains off exactly as in production.
    os.environ.update(
        {
            "INFINI_SKIP_CONFIG_FILE": "1",
            "INFINI_USE_LLM": "0",
            "INFINI_ALLOW_DETERMINISTIC_DEV_FALLBACK": "0",
            "INFINI_IMAGE_BACKEND": "sdcpp",
            "INFINI_SDCPP_SERVER_AUTOSTART": "0",
            "INFINI_CACHE_DIR": str(cache_dir),
            "INFINI_WORLD_RECIPES_DIR": str(world_dir),
        }
    )
    atexit.register(shutil.rmtree, _TEST_CACHE_ROOT, ignore_errors=True)


def pytest_sessionstart(session) -> None:
    del session
    _stop_dependency_poor_collection()


_configure_deterministic_sandbox()
