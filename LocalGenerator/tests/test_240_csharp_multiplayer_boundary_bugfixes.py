from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "ModSources" / "InfiniCrafterLocal"


def _text(relative: str) -> str:
    return (MOD / relative).read_text(encoding="utf-8")


def _method(source: str, name: str, next_name: str) -> str:
    return source.split(name, 1)[1].split(next_name, 1)[0]


def _contract_check_asset_notifications_are_server_authored_and_downloads_are_stream_bounded() -> None:
    source = _text("Common/Services/GeneratedAssetSyncService.cs")
    request = _method(source, "public void HandleAssetRequestPacket", "public void HandleAssetChunkPacket")
    chunk = _method(source, "public void HandleAssetChunkPacket", "private bool TryReadVerifiedAssetBundle")

    assert "Main.netMode != NetmodeID.Server" in request
    assert "GeneratedItems.TryGet(itemId, out GeneratedItemData data)" in request
    assert "BuildServerAssetDescriptors(data)" in request
    assert "packet.Send" not in request
    assert "ComputeSha256Hex(complete)" in chunk
    assert "SHA256.HashData" in source
    assert "CommitVerifiedAsset" in chunk
    assert "HttpCompletionOption.ResponseHeadersRead" in source
    assert "ContentLength" in source
    assert "MaxAssetBytes" in source
    assert "GetByteArrayAsync" not in source
    assert "total > MaxAssetBytes" in source
    assert "MaxInFlightDownloads" in source
    assert "MaxKnownMissing" in source
    assert "SemaphoreSlim" in source


def _contract_check_registry_bounds_only_hydration_request_state_not_authoritative_definitions() -> None:
    source = _text("Common/Services/GeneratedItemRegistryService.cs")
    assert "MaxHydrationRequestStateEntries" in source
    assert "EnforceBoundedTickDictionary" in source
    assert "_byId.Remove(" not in source
    assert "_cachedDefinitionTouchTick" not in source


def _contract_check_projectile_extra_ai_is_versioned_bounded_and_fail_closed() -> None:
    source = _text("Content/Projectiles/GeneratedProjectile.NetSync.cs")
    send = _method(source, "public override void SendExtraAI", "public override void ReceiveExtraAI")
    receive = source.split("public override void ReceiveExtraAI", 1)[1]

    assert "RuntimeNetVersion" in source
    assert "writer.Write(_generatedItemId" in send
    assert "writer.Write(_entityId" in send
    assert "reader.ReadByte() != RuntimeNetVersion" in receive
    assert "_generatedItemId.Length > 96" in receive
    assert "_entityId.Length > 48" in receive
    assert "Projectile.friendly = false" in receive
    assert "Projectile.velocity = Vector2.Zero" in receive
    assert "TryHydrate();" in receive
    assert "_preserveSyncedStateOnHydrate = true" in receive

    runtime = _text("Content/Projectiles/GeneratedProjectile.cs")
    configure = _method(runtime, "internal void Configure", "private void ApplyEntityStats")
    assert "preserveSyncedState" in configure
    assert "Projectile.timeLeft = Math.Max(1, syncedTimeLeft)" in configure
    assert "_remainingBounces = Math.Clamp(syncedBounces" in configure
    assert "_activationDelayTicks = Math.Max(0, syncedActivationDelay)" in configure


def _contract_check_v5_lifesteal_is_owner_local_and_npc_damage_is_server_authored() -> None:
    source = _text("Common/Runtime/RuntimeProgramExecutor.cs")
    heal = _method(source, "private static void HealOwner", "private static void MoveOwner")
    area = _method(source, "private static void DamageArea", "private static void ChainDamage")
    chain = _method(source, "private static void ChainDamage", "private static void Pull")

    assert "ShouldRunLocalPlayerAction(owner)" in heal
    assert "ShouldRunPlayerGameplay(owner)" not in heal
    assert "owner.Heal(heal)" in heal
    assert "ShouldRunNpcGameplay()" in area
    assert "ShouldRunNpcGameplay()" in chain


def _contract_check_projectile_vfx_event_relay_is_server_authored_exact_and_lifetime_independent() -> None:
    root = _text("InfiniCrafterLocal.cs")
    packet_ids = _text("Common/InfiniNetPacketIds.cs")
    net_sync = _text("Content/Projectiles/GeneratedProjectile.NetSync.cs")
    events = _text("Content/Projectiles/GeneratedProjectile.RuntimeEvents.cs")
    executors = _text("Content/Projectiles/GeneratedProjectile.Executors.cs")
    handler = net_sync.split("public static void HandleVfxEventSyncPacket", 1)[1]

    assert "SyncGeneratedProjectileVfxEvent = 9" in packet_ids
    assert "GeneratedProjectile.HandleVfxEventSyncPacket(reader, whoAmI)" in root
    assert "Main.netMode != NetmodeID.MultiplayerClient" in handler
    assert "GeneratedItemRegistryService" in handler
    assert "HasExactVfxSlot(data, entity.Id, payload.EventName)" in handler
    assert "InfiniVfxRuntime.OnDetachedEvent" in handler
    assert "remote?._data" not in handler
    assert "BroadcastAuthoritativeVfxEvent" in net_sync
    assert "packet.Send(-1, Projectile.owner)" in net_sync
    assert "SourceToken" in net_sync
    assert "EmitAndSyncVfxEvent" in events
    assert "foreach (RuntimeEventActionSpec action" in events
    assert "EmitAndSyncVfxEvent(RuntimeEventKind.OnRelease" in executors
    assert "EmitAndSyncVfxEvent(RuntimeEventKind.ChannelComplete" in executors


def _contract_check_generated_utility_sync_consumes_payload_before_every_reject() -> None:
    source = _text("Common/Players/InfiniCraftPlayer.Multiplayer.cs")
    handler = _method(source, "public static void HandleGeneratedUtilityBuffSyncPacket", "public void RequestGeneratedAltUseFromServer")
    for reason in (
        "playerId >= Main.maxPlayers",
        "Main.netMode == NetmodeID.Server && playerId != whoAmI",
        "player is null || !player.active",
    ):
        # Stop at this guard's closing brace: searching the rest of the method
        # could mistake the next guard's discard for this one's.
        branch = handler.split(reason, 1)[1].split("}", 1)[0]
        assert branch.index("DiscardGeneratedBuffState(reader);") < branch.index("return;")
    server = handler.split("if (Main.netMode == NetmodeID.Server)\n        {", 1)[1].split("}", 1)[0]
    assert server.index("DiscardGeneratedBuffState(reader);") < server.index("SendGeneratedBuffState(-1, whoAmI)")


def _contract_check_server_craft_transactions_log_reservation_commit_and_refund_with_slots() -> None:
    source = _text("Common/Players/InfiniCraftPlayer.Multiplayer.cs")
    request = _method(source, "public static void HandleRequestServerCraftPacket", "public static void HandleCancelServerCraftPacket")
    result = _method(source, "private void SendServerAuthoritativeResultIfNeeded", "public void HandleCraftCommitResult")
    assert "private static void LogServerCraftTransaction" in source
    assert "[InfiniCraftTx]" in source
    assert '"received"' in request
    assert '"reserve_rejected"' in request
    assert '"reserved"' in request
    assert "int firstInputIndex = laneIndex * 2" in request
    assert "aInput={firstInputIndex}" in request
    assert "bInput={firstInputIndex + 1}" in request
    assert "TrySnapshotServerEscrowInput(firstInputIndex, aRef" in request
    assert "TrySnapshotServerEscrowInput(firstInputIndex + 1, bRef" in request
    assert "GeneratedStationEscrowStateSystem.TryBeginCraft" in request
    assert 'success ? "committed" : "failed"' in result
    assert "if (success)\n            ClearServerStationEscrowLane(laneIndex);" in result


def test_240_csharp_multiplayer_boundary_bugfixes_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(globals(), request)
