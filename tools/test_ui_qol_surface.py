"""Narrow source-boundary regression; native behavior lives in EngineRuntimeChecks.UiQol."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ModSources/InfiniCrafterLocal/Common/UI"


def test_station_suppression_returns_before_transactions_without_global_blocking():
    source = (UI / "InfiniCraftStationUISystem.cs").read_text(encoding="utf-8")
    handler = source.split("private static void HandleMouse(", 1)[1].split("private static", 1)[0]
    assert handler.index("if (PlayerInput.IgnoreMouseInterface) return;") < handler.index("TryClearInputToInventory")
    assert "Main.blockInput =" not in source
    assert "controlUseItem =" not in source
    assert "!PlayerInput.IgnoreMouseInterface && panel.Contains" in source


def test_short_journal_controls_are_drawn_before_short_page_return():
    source = (UI / "RecipeJournalUISystem.cs").read_text(encoding="utf-8")
    detail = source.split("private static void DrawDetail(", 1)[1]
    assert detail.index("Button(sb, controls.Back") < detail.index("if (area.Height < 200)")
    assert detail.index("Button(sb, controls.Save") < detail.index("if (area.Height < 200)")
    assert 'KeybindLoader.RegisterKeybind(Mod, "ToggleRecipeJournal", Keys.K)' in source
