"""Portable source-seam checks. Native prefix/NBT behavior is in EngineRuntimeChecks."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "ModSources/InfiniCrafterLocal"


def _body(path: str, method: str) -> str:
    spec = importlib.util.spec_from_file_location("placement_prefix_csharp", ROOT / "tools/check_csharp_contracts.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    body = module.stripped(module.method_body((SRC / path).read_text(encoding="utf-8"), method, overload=-1))
    assert not module.ERRORS
    return "".join(body.split())


def test_prefix_capture_comes_only_from_exact_observed_held_instance():
    body = _body("Common/Systems/GeneratedPlacementLedgerSystem.cs", "AuthorizePlacement")
    for required in (
        "sourceItem.ModItemisnotGeneratedItemsourceGenerated",
        "!ReferenceEquals(sourceGenerated.Data,data)",
        "ReferenceEquals(existing.SourceItem,sourceItem)",
        "sourceGenerated.CapturePlacementPrefix()",
    ):
        assert required in body
    packet = _body("Common/Systems/GeneratedPlacementLedgerSystem.cs", "HandlePlacementIntentPacket")
    assert "AuthorizePlacement(player,held.Data,placement,x,y)" in packet
    assert "prefix" not in packet.lower()


def test_native_prefix_roundtrip_keeps_material_state_outside_canonical_definition():
    source = (SRC / "Common/Systems/GeneratedPlacementLedgerSystem.cs").read_text(encoding="utf-8")
    for transition in (
        "NativePrefixEnvelope = ReadPlacementPrefixEnvelope(row)",
        "NativePrefixEnvelope = authorization.NativePrefixEnvelope",
        "NativePrefixEnvelope = group.NativePrefixEnvelope",
        "NativePrefixEnvelope = prefixEnvelope",
    ):
        assert transition in source
    assert "WritePlacementPrefixEnvelope(row,group.NativePrefixEnvelope)" in _body(
        "Common/Systems/GeneratedPlacementLedgerSystem.PlacedBody.cs", "SavePlacementGroup")
    assert "WritePlacementPrefixEnvelope(claim,pending.NativePrefixEnvelope)" in _body(
        "Common/Systems/GeneratedPlacementLedgerSystem.cs", "ReturnClaim")
    body = _body("Common/Systems/GeneratedPlacementLedgerSystem.cs", "TrySpawnPendingReturnCore")
    assert body.index("ResolvePlacementPrefixEnvelope") < body.index("Item.NewItem")
    assert body.index("generated.SetData(data)") < body.index("generated.RestorePlacementPrefix(nativePrefix)") < body.index("NetMessage.SendData")
    for model in (SRC / "Common/Models").glob("GeneratedItemData*.cs"):
        assert "NativePrefix" not in model.read_text(encoding="utf-8")


def test_placement_prefix_shape_and_exact_native_application_have_no_reroll():
    body = _body("Content/Items/GeneratedItem.PrefixLifecycle.cs", "ResolvePlacementPrefix")
    assert "if(tagisnull)return0;" in body
    assert "isnotinttoken||token<0" in body
    assert "token<PrefixID.Count" in body and "elseif(token>=PrefixID.Count)" in body
    assert "isnotstring{Length:>0}" in body
    assert body.endswith("returnResolveNativePrefixIdentity(tag);")
    restore = _body("Content/Items/GeneratedItem.PrefixLifecycle.cs", "RestorePlacementPrefix")
    assert "RetainNativePrefixForHydration(prefix);ApplyDataWithNativePrefix();returnItem.prefix==prefix;" == restore
    replay = _body("Common/Systems/GeneratedPlacementLedgerSystem.cs", "TryRequeueQuarantinedReturn")
    assert "ResolvePlacementPrefixEnvelope(prefixEnvelope)" in replay
    assert "catch{returnfalse;}" in replay


def test_native_placement_prefix_cases_are_registered_and_compile_in_harness():
    tests = (ROOT / "tools/EngineRuntimeChecks.PlacementPrefix.cs").read_text(encoding="utf-8")
    runner = (ROOT / "tools/EngineRuntimeChecks.cs").read_text(encoding="utf-8")
    project = (ROOT / "tools/EngineRuntimeChecks.csproj").read_text(encoding="utf-8")
    assert 'Compile Include="EngineRuntimeChecks.PlacementPrefix.cs"' in project
    for case in ("PlacementPrefixServerSnapshotSurvivesEscrowSaveAndReturn", "PlacementPrefixMalformedIdentityIsDurableAndLegacyIsUnprefixed"):
        assert case in tests and case in runner
    assert "source.Item.TurnToAir()" in tests
    assert "PersistenceNbtRoundtrip" in tests
    assert "station.RestoreServerStationEscrowSlots(station.SnapshotServerStationEscrowSlots())" in tests
