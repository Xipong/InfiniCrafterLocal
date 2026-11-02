"""Localization data contract; native behavior lives in EngineRuntimeChecks."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_placement_feedback_localization_keys_exist():
    for locale in ("en-US", "ru-RU"):
        localization = ROOT / f"ModSources/InfiniCrafterLocal/Localization/{locale}_Mods.InfiniCrafterLocal.hjson"
        assert "PlacementUnsupported:" in localization.read_text(encoding="utf-8")
