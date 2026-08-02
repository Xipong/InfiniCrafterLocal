from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CS = ROOT / "ModSources" / "InfiniCrafterLocal"


def _read(relative: str) -> str:
    return (CS / relative).read_text(encoding="utf-8")


def test_multidev_command_and_exact_window_profiles_are_explicit() -> None:
    command = _read("Common/Commands/MultiDevCraftCommand.cs")
    station = _read("Common/Players/InfiniCraftPlayer.Station.cs")
    multi = _read("Common/Players/InfiniCraftPlayer.MultiDev.cs")
    generator = _read("Common/Services/GeneratorClient.cs")

    assert 'Command => "multidevcraft"' in command
    assert 'Usage => "/multidevcraft [2|3|off]"' in command
    assert '"llm_1"' in station
    assert 'string profileId = $"llm_{laneIndex + 1}";' in multi
    assert "multiDevCraft: true" in multi
    assert "multiDevCraft," in generator
    assert "llmProfileId = multiDevCraft" in generator


def test_three_windows_have_independent_slots_jobs_and_ui_controls() -> None:
    state = _read("Common/Players/InfiniCraftPlayer.MultiDev.cs")
    station = _read("Common/Players/InfiniCraftPlayer.Station.cs")
    ui = _read("Common/UI/InfiniCraftStationUISystem.cs")

    for field in ("InputC", "InputD", "InputE", "InputF"):
        assert f"public Item {field}" in state
    for index in range(6):
        assert f"index == {index}" in station
    assert "new MultiDevCraftJob?[2]" in state
    assert "for (int lane = 0; lane < laneCount; lane++)" in ui
    assert "TryStartCraftFromStation(lane)" in ui
    assert "CraftLaneProgress(lane)" in ui
    assert "Window {lane + 1} · LLM {lane + 1}" in ui


def test_multiplayer_lane_identity_authority_and_refunds_are_request_scoped() -> None:
    packets = _read("Common/InfiniNetPacketIds.cs")
    mod = _read("InfiniCrafterLocal.cs")
    mp = _read("Common/Players/InfiniCraftPlayer.Multiplayer.cs")
    multi = _read("Common/Players/InfiniCraftPlayer.MultiDev.cs")
    craft_state = _read("Common/Players/InfiniCraftPlayer.CraftState.cs")

    assert "SetMultiDevCraftMode = 20" in packets
    assert "HandleSetMultiDevCraftModePacket(reader, whoAmI)" in mod
    assert "int laneIndex = Math.Clamp((int)reader.ReadByte(), 0, 2);" in mp
    assert "packet.Write((byte)Math.Clamp(laneIndex, 0, 2));" in multi
    assert "!modPlayer.IsCraftLaneVisible(laneIndex)" in mp
    assert "modPlayer.IsCraftLanePending(laneIndex)" in mp
    assert "int firstInputIndex = laneIndex * 2;" in mp
    assert "TrySnapshotServerEscrowInput(firstInputIndex" in mp
    assert "TrySnapshotServerEscrowInput(firstInputIndex + 1" in mp
    assert "GeneratedStationEscrowStateSystem.TryBeginCraft" in mp
    assert "TryHandleExtraCraftCommit(requestId" in mp
    assert "TryCancelExtraServerCraft(requestId" in mp
    assert "AddMultiDevPendingRefunds(refunds, includeRemoteAwaiting: !_stationEscrowUsesRemoteAuthority);" in craft_state
    assert "SavePendingRemoteCrafts" in craft_state
    assert "RestoreMultiDevPendingRemoteCraft" in multi
    assert "AbortMultiDevCraftsForWorldExit" in craft_state
    assert "CompleteServerCraftTransaction(job.RequestId, job.LaneIndex" in multi


def test_request_local_failure_state_prevents_cross_lane_races() -> None:
    generator = _read("Common/Services/GeneratorClient.cs")
    craft = _read("Common/Players/InfiniCraftPlayer.CraftState.cs")
    multi = _read("Common/Players/InfiniCraftPlayer.MultiDev.cs")

    for field in ("FailureIsFatal", "FailureMessage", "FailurePlayerMessage", "FailureStatusCode"):
        assert f"public " in generator and field in generator
    assert "request.FailureIsFatal = true;" in generator
    assert "_request?.FailureIsFatal == true" in craft
    assert "job.Request.FailureIsFatal" in multi
