"""Canonical paths for tests; fixtures are independent of module categories."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR_ROOT = REPO_ROOT / "generator"
TEST_ROOT = REPO_ROOT / "tests" / "generator"
