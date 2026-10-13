"""Portable station source seams; native behavior is covered by ForgePresentation checks."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CS = ROOT / "ModSources/InfiniCrafterLocal"


def test_station_hover_uses_full_read_only_details_and_canonical_feedback():
    ui = (CS / "Common/UI/InfiniCraftStationUISystem.cs").read_text()
    assert "CraftLaneDetails(lane)" in ui, "truncated lane text has no full hover details"
    assert "Main.instance.MouseText" in ui
    assert "StationCraftReadinessText(lane)" in ui
    assert 'ForgeText(craftPlayer.IsCraftLanePending(lane) ? "LaneBusy" : "NeedInputs")' not in ui
    assert "CanStartStationCraftLane(lane)" not in ui, "draw must not refresh material authority"
    assert "GetStationCraftReadiness(lane)" in ui
    start = ui[ui.index("if (craftButtons[lane].Contains(mouse))"):ui.index("if (clearButton.Contains(mouse))")]
    assert start.index("GetStationCraftReadiness(lane)") < start.index("TryStartCraftFromStation(lane)"), "failed preparation must not be mislabeled missing inputs after refund"
    assert "readiness == InfiniCraftPlayer.StationCraftReadiness.Ready" in start


def test_station_cancel_and_player_refund_wiring_uses_native_owners():
    ui = (CS / "Common/UI/InfiniCraftStationUISystem.cs").read_text()
    assert "StationCancelBounds(panel, lane)" in ui
    assert "TryCancelCraftLane(lane)" in ui
    assert "IsCraftLaneCancellationPending(lane)" in ui
    assert 'HasPendingCraftRefunds ? ForgeText("RefundPending")' in ui
    assert "RefundIngredients" not in ui and "_deferredExitRefunds" not in ui
