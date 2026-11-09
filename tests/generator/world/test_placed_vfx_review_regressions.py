"""Localization data contract; native behavior lives in EngineRuntimeChecks."""
from suite_paths import REPO_ROOT
from pathlib import Path

ROOT = REPO_ROOT


def test_placement_feedback_localization_keys_exist():
    for locale in ("en-US", "ru-RU"):
        localization = ROOT / f"mod/InfiniCrafterLocal/Localization/{locale}_Mods.InfiniCrafterLocal.hjson"
        assert "PlacementUnsupported:" in localization.read_text(encoding="utf-8")
